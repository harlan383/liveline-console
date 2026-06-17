import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import ValidationError
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.db.redis import get_rq_redis_client
from app.db.session import get_db
from app.models.node import Node
from app.models.task import Task
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer
from app.schemas.common import error_response, success_response
from app.schemas.transit_route import (
    PROTECTED_CREATE_PORT_MESSAGES,
    PROTECTED_CREATE_PORTS,
    ReadonlyPreflightPlanCheck,
    ReadonlyPreflightPlanRequest,
    ReadonlyPreflightPlanResponse,
    TransitReadonlyPreflightCommandRequest,
    TransitRouteCreateFields,
)
from app.services.auth_service import record_audit
from app.services.credentials import store_temp_credential
from app.services.task_logging import add_task_log
from app.services.worker_commands import create_worker_command, serialize_worker_command
from app.services.worker_targeting import (
    WorkerTargetError,
    minimum_worker_version_for_command,
    resolve_command_target_worker,
)
from app.worker.jobs import (
    create_socat_route_job,
    create_transit_route_job,
    diagnose_transit_route_job,
    restart_socat_route_job,
)
from app.worker.ssh_socat_route import (
    ACCEPTED_SOCAT_RESOURCE_ID,
    service_name_for as socat_service_name_for,
    service_path_for as socat_service_path_for,
)

router = APIRouter()


TRANSIT_READONLY_PREFLIGHT_COMMAND = "transit_readonly_preflight"
TRANSIT_READONLY_PREFLIGHT_BOUNDARY = [
    "remote readonly preflight only",
    "no arbitrary shell accepted",
    "no real forwarding route created",
    "no socat/gost install, start, stop, or restart",
    "no real listening port added",
    "no firewall or cloud security group change",
    "no Xray modification",
    "no nodes.share_link read or modification",
    "no full client link export",
    "no cutover",
]
READONLY_PREFLIGHT_SAFETY_BOUNDARY = [
    "readonly preflight plan only",
    "no SSH executed",
    "no remote commands executed",
    "no remote server connection",
    "no database write",
    "no task created",
    "no temp credential written",
    "no real forwarding created",
    "no real listening port added",
    "no node.share_link modification",
    "no cutover",
]


def redact_hint(value: str | None) -> str:
    if not value:
        return "Pending confirmation"
    cleaned = value.strip()
    lowered = cleaned.lower()
    if "://" in lowered or "begin " in lowered or "private key" in lowered:
        return "[redacted sensitive value]"
    if len(cleaned) > 80:
        return f"{cleaned[:40]}...{cleaned[-12:]}"
    return cleaned


def parse_optional_port(value: int | str | None) -> tuple[int | None, str | None]:
    if value is None:
        return None, "端口尚未填写。"
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None, "端口尚未填写。"
        if not stripped.isdigit():
            return None, "端口必须是 1-65535 之间的整数。"
        value = int(stripped)
    if not isinstance(value, int) or isinstance(value, bool):
        return None, "端口必须是 1-65535 之间的整数。"
    if value < 1 or value > 65535:
        return value, "端口必须是 1-65535 之间的整数。"
    return value, None


def make_preflight_check(
    *,
    check_id: str,
    label: str,
    category: str,
    passed: bool,
    message: str,
    next_action: str,
    status: str | None = None,
    evidence_summary: str | None = None,
) -> ReadonlyPreflightPlanCheck:
    resolved_status = status or ("passed" if passed else "blocked")
    return ReadonlyPreflightPlanCheck(
        id=check_id,
        label=label,
        category=category,
        status=resolved_status,
        passed=passed,
        message=message,
        evidence_summary=evidence_summary or message,
        next_action=next_action,
        sensitive_output_redacted=True,
    )


def future_preflight_check(check_id: str, label: str, category: str) -> ReadonlyPreflightPlanCheck:
    return make_preflight_check(
        check_id=check_id,
        label=label,
        category=category,
        passed=False,
        status="skipped",
        message="future check / not executed in this stage",
        evidence_summary="No remote evidence collected.",
        next_action="Enter a separately authorized Workbuddy read-only preflight stage before executing this check.",
    )


def build_readonly_preflight_plan(payload: ReadonlyPreflightPlanRequest) -> ReadonlyPreflightPlanResponse:
    planned_port, planned_port_error = parse_optional_port(payload.planned_listen_port)
    landing_port, landing_port_error = parse_optional_port(payload.landing_target_port)
    protected_port_message = PROTECTED_CREATE_PORT_MESSAGES.get(planned_port or 0)
    planned_port_valid = planned_port is not None and planned_port_error is None
    planned_port_not_reserved = planned_port_valid and planned_port not in PROTECTED_CREATE_PORTS
    firewall_confirmations_present = (
        payload.firewall_security_group_confirmed
        and payload.cloud_firewall_confirmed
        and payload.server_firewall_confirmed
    )

    checks = [
        make_preflight_check(
            check_id="transit_resource_selected",
            label="Transit resource selected",
            category="local_input",
            passed=bool(payload.transit_resource_id),
            message="Transit resource is selected." if payload.transit_resource_id else "Transit resource is missing.",
            next_action="Select a transit resource before requesting read-only preflight.",
        ),
        make_preflight_check(
            check_id="landing_node_selected",
            label="Landing node selected",
            category="local_input",
            passed=bool(payload.landing_node_id),
            message="Landing node is selected." if payload.landing_node_id else "Landing node is missing.",
            next_action="Select an active landing node before requesting read-only preflight.",
        ),
        make_preflight_check(
            check_id="planned_port_valid",
            label="Planned listen port is valid",
            category="port_safety",
            passed=planned_port_valid,
            message="Planned listen port is a valid TCP port." if planned_port_valid else (planned_port_error or "Planned listen port is invalid."),
            next_action="Use an integer TCP port from 1 to 65535.",
        ),
        make_preflight_check(
            check_id="planned_port_not_reserved",
            label="Planned listen port is not reserved",
            category="port_safety",
            passed=planned_port_not_reserved,
            message=(
                "Planned listen port is not reserved."
                if planned_port_not_reserved
                else protected_port_message or "Planned listen port must avoid protected ports."
            ),
            next_action="Avoid 22, 8443, 18443, and 20575.",
        ),
        make_preflight_check(
            check_id="landing_target_port_valid",
            label="Landing target port is valid",
            category="port_safety",
            passed=landing_port is not None and landing_port_error is None,
            message="Landing target port is valid." if landing_port is not None and landing_port_error is None else (landing_port_error or "Landing target port is invalid."),
            next_action="Use an integer TCP port from 1 to 65535.",
        ),
        make_preflight_check(
            check_id="firewall_confirmations_present",
            label="Firewall confirmations are present",
            category="firewall",
            passed=firewall_confirmations_present,
            message="Cloud security group, cloud firewall, and server firewall are confirmed." if firewall_confirmations_present else "Firewall confirmations are incomplete.",
            next_action="Confirm cloud security group, cloud firewall, and server firewall allow the planned TCP port.",
        ),
        make_preflight_check(
            check_id="local_backup_confirmed",
            label="Local database backup confirmed",
            category="local_safety",
            passed=payload.local_backup_confirmed,
            message="Local database backup is confirmed." if payload.local_backup_confirmed else "Local database backup is not confirmed.",
            next_action="Run and verify a local database backup before requesting read-only preflight.",
        ),
        make_preflight_check(
            check_id="user_approved_readonly_preflight",
            label="User approved read-only preflight",
            category="authorization",
            passed=payload.user_approved_readonly_preflight,
            message="User approval for read-only preflight is present." if payload.user_approved_readonly_preflight else "User approval for read-only preflight is missing.",
            next_action="Confirm that the request is only for read-only preflight.",
        ),
        make_preflight_check(
            check_id="no_cutover_confirmed",
            label="No cutover confirmed",
            category="authorization",
            passed=payload.no_cutover_confirmed,
            message="No-cutover boundary is confirmed." if payload.no_cutover_confirmed else "No-cutover boundary is not confirmed.",
            next_action="Confirm that this request will not perform cutover.",
        ),
        make_preflight_check(
            check_id="no_node_share_link_change_confirmed",
            label="No node.share_link change confirmed",
            category="authorization",
            passed=payload.no_node_share_link_change_confirmed,
            message="No node.share_link change boundary is confirmed." if payload.no_node_share_link_change_confirmed else "No node.share_link change boundary is not confirmed.",
            next_action="Confirm that node.share_link will not be read or modified.",
        ),
        make_preflight_check(
            check_id="workbuddy_authorization_status",
            label="Workbuddy authorization status",
            category="authorization",
            passed=payload.workbuddy_authorized,
            message="Workbuddy read-only preflight authorization is present." if payload.workbuddy_authorized else "Workbuddy read-only preflight authorization is missing.",
            next_action="Obtain explicit Workbuddy authorization before any future remote read-only execution.",
        ),
        future_preflight_check("future_transit_reachable", "Transit server reachable", "future_remote"),
        future_preflight_check("future_planned_port_available", "Planned port available", "future_remote"),
        future_preflight_check("future_formal_socat_18443_preserved", "Formal socat 18443 preserved", "future_route_safety"),
        future_preflight_check("future_fallback_gost_8443_preserved", "Fallback gost 8443 preserved", "future_route_safety"),
        future_preflight_check("future_transit_to_landing_tcp_connectivity", "Transit to landing TCP connectivity", "future_remote"),
    ]

    required_checks = [check for check in checks if not check.id.startswith("future_")]
    ready = all(check.passed for check in required_checks)
    structural_blocked = any(
        not check.passed
        for check in checks
        if check.id in {
            "transit_resource_selected",
            "landing_node_selected",
            "planned_port_valid",
            "planned_port_not_reserved",
            "landing_target_port_valid",
        }
    )
    status = "ready" if ready else ("blocked" if structural_blocked else "no_go")
    summary = (
        "Ready for readonly preflight approval / execution stage. This does not authorize real forwarding."
        if ready
        else "Readonly preflight plan is No-Go. No remote execution is authorized."
    )
    next_action = (
        "Proceed only to a separately authorized read-only preflight execution stage."
        if ready
        else "Resolve blocked or No-Go checks before requesting read-only preflight execution approval."
    )
    redacted_summary = "\n".join(
        [
            "LiveLine readonly preflight no-op plan",
            f"Status: {status}",
            f"Transit resource: {redact_hint(payload.transit_resource_name)}",
            f"Transit host hint: {redact_hint(payload.transit_host_hint)}",
            f"Landing node: {redact_hint(payload.landing_node_name)}",
            f"Landing host hint: {redact_hint(payload.landing_host_hint)}",
            f"Planned listen port: {planned_port if planned_port is not None else 'Pending confirmation'}",
            f"Landing target port: {landing_port if landing_port is not None else 'Pending confirmation'}",
            f"Purpose: {redact_hint(payload.route_purpose)}",
            "Remote execution: not performed by this API",
            "Real forwarding creation: not authorized",
            "node.share_link modification: not authorized",
            "Cutover: not authorized",
        ]
    )

    return ReadonlyPreflightPlanResponse(
        ready=ready,
        blocked=not ready,
        status=status,
        summary=summary,
        next_action=next_action,
        checks=checks,
        safety_boundary=READONLY_PREFLIGHT_SAFETY_BOUNDARY,
        redacted_summary=redacted_summary,
    )


async def read_private_key_payload(
    private_key_text: str | None,
    private_key_file: UploadFile | None,
) -> str | None:
    if private_key_file is not None and private_key_file.filename:
        content = await private_key_file.read()
        if len(content) > 128 * 1024:
            return None
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return None

    if private_key_text and private_key_text.strip():
        return private_key_text

    return None


def serialize_transit_route(route: TransitRoute) -> dict:
    resource = route.transit_resource
    node = route.node
    vps = route.landing_vps
    return {
        "id": route.id,
        "name": route.name,
        "transit_resource_id": route.transit_resource_id,
        "transit_resource_name": resource.name if resource else None,
        "node_id": route.node_id,
        "node_name": node.node_name if node else None,
        "landing_vps_id": route.landing_vps_id,
        "landing_vps_ip": vps.ip if vps else None,
        "listen_port": route.listen_port,
        "target_host": route.target_host,
        "target_port": route.target_port,
        "forwarding_method": route.forwarding_method,
        "service_name": route.service_name,
        "service_path": route.service_path,
        "status": route.status,
        "share_link": route.share_link,
        "created_at": route.created_at.isoformat() if route.created_at else None,
        "updated_at": route.updated_at.isoformat() if route.updated_at else None,
        "deleted_at": route.deleted_at.isoformat() if route.deleted_at else None,
    }


def get_route_or_error(db: Session, route_id: str) -> TransitRoute | None:
    return db.scalar(
        select(TransitRoute).where(
            TransitRoute.id == route_id,
            TransitRoute.deleted_at.is_(None),
        )
    )


@router.get("")
@router.get("/")
def list_transit_routes(request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    routes = db.scalars(
        select(TransitRoute)
        .where(TransitRoute.deleted_at.is_(None))
        .order_by(TransitRoute.created_at.desc())
    ).all()
    return success_response({"routes": [serialize_transit_route(route) for route in routes]}, "ok")


@router.get("/{route_id}")
def get_transit_route(
    route_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not require_admin_session(db, request):
        return auth_error()

    route = get_route_or_error(db, route_id)
    if not route:
        return error_response(404, "TRANSIT_ROUTE_NOT_FOUND", "中转规则不存在。")

    return success_response(serialize_transit_route(route), "ok")


@router.post("/readonly-preflight-plan")
def readonly_preflight_plan(
    payload: ReadonlyPreflightPlanRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if not require_admin_session(db, request):
        return auth_error()

    plan = build_readonly_preflight_plan(payload)
    return success_response(plan.model_dump(), "readonly preflight plan generated locally")


@router.post("/readonly-preflight-command")
def create_transit_readonly_preflight_command(
    payload: TransitReadonlyPreflightCommandRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    if not payload.readonly:
        return error_response(
            400,
            "READONLY_CONFIRMATION_REQUIRED",
            "必须明确确认 readonly=true，才允许创建远程只读预检命令。",
        )
    if payload.planned_listen_port in PROTECTED_CREATE_PORTS:
        return error_response(
            400,
            "PROTECTED_LISTEN_PORT",
            PROTECTED_CREATE_PORT_MESSAGES[payload.planned_listen_port],
        )

    resource = db.get(TransitResource, payload.transit_resource_id)
    if not resource or resource.deleted_at is not None:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转服务器记录不存在。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_TYPE_UNSUPPORTED", "只允许 server 类型中转资源执行只读预检。")
    if resource.status == "disabled":
        return error_response(400, "TRANSIT_RESOURCE_DISABLED", "已停用的中转资源不能执行只读预检。")

    node = db.get(Node, payload.landing_node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "LANDING_NODE_NOT_FOUND", "落地节点不存在。")
    if node.status != "active":
        return error_response(400, "LANDING_NODE_NOT_ACTIVE", "只允许 active 落地节点执行只读预检。")
    landing_host = node.vps.ip if node.vps else None
    if not landing_host:
        return error_response(400, "LANDING_HOST_MISSING", "落地节点缺少目标 IP，不能执行只读预检。")
    if node.xray_port and payload.landing_target_port != node.xray_port:
        return error_response(
            400,
            "LANDING_TARGET_PORT_MISMATCH",
            "落地目标端口必须与当前 active 节点端口一致。",
        )

    try:
        target = resolve_command_target_worker(
            db,
            server_type="transit",
            server_id=resource.id,
            role="transit",
            command_type=TRANSIT_READONLY_PREFLIGHT_COMMAND,
        )
    except WorkerTargetError as exc:
        return error_response(400, exc.code, exc.message)

    target_worker = target.worker
    if target_worker.role != "transit":
        return error_response(400, "WORKER_ROLE_MISMATCH", "只允许 transit role Worker 执行中转只读预检。")

    command_payload = {
        "transit_resource_id": resource.id,
        "transit_resource_name": resource.name,
        "landing_node_id": node.id,
        "landing_node_name": node.node_name,
        "planned_listen_port": payload.planned_listen_port,
        "landing_target_host": landing_host,
        "landing_target_port": payload.landing_target_port,
        "forwarding_method": payload.forwarding_method,
        "purpose": payload.purpose,
        "readonly": True,
        "safety_boundary": TRANSIT_READONLY_PREFLIGHT_BOUNDARY,
    }
    command = create_worker_command(db, target_worker, TRANSIT_READONLY_PREFLIGHT_COMMAND, command_payload)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_transit_readonly_preflight_command",
        result="success",
        request=request,
        resource_type="worker_command",
        resource_id=command.id,
    )
    db.commit()
    db.refresh(command)
    return success_response(
        {
            "command": serialize_worker_command(command, include_payload=True, worker=target_worker),
            "target_worker_id": target_worker.id,
            "target_worker_version": target_worker.worker_version,
            "minimum_supported_worker_version": minimum_worker_version_for_command(TRANSIT_READONLY_PREFLIGHT_COMMAND),
            "safety_boundary": TRANSIT_READONLY_PREFLIGHT_BOUNDARY,
        },
        "远程只读预检 Worker command 已创建；不会创建真实转发。",
    )


@router.post("/{route_id}/diagnose")
async def diagnose_transit_route(
    route_id: str,
    request: Request,
    ssh_key: str | None = Form(None),
    private_key_text: str | None = Form(None),
    ssh_key_passphrase: str | None = Form(None),
    ssh_key_file: UploadFile | None = File(None),
    private_key_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    route = get_route_or_error(db, route_id)
    if not route:
        return error_response(404, "TRANSIT_ROUTE_NOT_FOUND", "中转规则不存在。")
    if route.status != "active":
        return error_response(400, "TRANSIT_ROUTE_NOT_ACTIVE", "只允许诊断 active 中转线路。")
    if route.forwarding_method not in ("gost", "socat"):
        return error_response(400, "UNSUPPORTED_FORWARDING_METHOD", "只支持 gost / socat 中转线路诊断。")

    resource = route.transit_resource
    if not resource or resource.deleted_at is not None:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")
    if resource.resource_type != "server" or resource.status != "active":
        return error_response(400, "TRANSIT_RESOURCE_NOT_ACTIVE", "只允许诊断 active server 中转资源。")
    if not resource.has_ssh or not resource.ssh_host or not resource.ssh_port or not resource.ssh_username:
        return error_response(400, "TRANSIT_SSH_METADATA_MISSING", "中转资源缺少 SSH 元数据。")

    running_task = db.scalar(
        select(Task).where(
            Task.task_type == "diagnose_transit_route",
            Task.status.in_(("pending", "running")),
        )
    )
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前已有中转线路诊断任务正在执行。")

    private_key = await read_private_key_payload(ssh_key or private_key_text, ssh_key_file or private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴香港服务器 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None

    task = Task(
        vps_id=route.landing_vps_id,
        node_id=route.node_id,
        task_type="diagnose_transit_route",
        status="pending",
        current_step="queued",
        progress=0,
    )
    db.add(task)
    db.flush()
    add_task_log(
        db,
        task.id,
        level="info",
        step="queued",
        message="中转线路只读诊断任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="diagnose_transit_route",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(diagnose_transit_route_job, task.id, route.id, temp_credential_id)

    return success_response(
        {
            "task_id": task.id,
            "transit_route_id": route.id,
        },
        "中转线路只读诊断任务已创建。",
    )


@router.post("/{route_id}/restart-socat")
async def restart_socat_route(
    route_id: str,
    request: Request,
    ssh_key: str | None = Form(None),
    private_key_text: str | None = Form(None),
    ssh_key_passphrase: str | None = Form(None),
    ssh_key_file: UploadFile | None = File(None),
    private_key_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    route = get_route_or_error(db, route_id)
    if not route:
        return error_response(404, "TRANSIT_ROUTE_NOT_FOUND", "中转规则不存在。")
    if route.status != "active":
        return error_response(400, "TRANSIT_ROUTE_NOT_ACTIVE", "只允许重启 active socat 测试链路。")
    if route.forwarding_method != "socat":
        return error_response(400, "SOCAT_ROUTE_REQUIRED", "只允许重启 socat 测试链路，禁止操作 gost 正式链路。")
    if route.listen_port != 18443:
        return error_response(400, "SOCAT_TEST_PORT_REQUIRED", "只允许重启 18443 socat 测试链路。")
    if not route.service_name:
        return error_response(400, "SOCAT_SERVICE_MISSING", "socat 测试链路缺少 systemd service 名称。")

    resource = route.transit_resource
    if not resource or resource.deleted_at is not None:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")
    if resource.resource_type != "server" or resource.status != "active":
        return error_response(400, "TRANSIT_RESOURCE_NOT_ACTIVE", "只允许操作 active server 中转资源。")
    if not resource.has_ssh or not resource.ssh_host or not resource.ssh_port or not resource.ssh_username:
        return error_response(400, "TRANSIT_SSH_METADATA_MISSING", "中转资源缺少 SSH 元数据。")

    running_task = db.scalar(
        select(Task).where(
            Task.task_type.in_(("restart_socat_route", "diagnose_transit_route")),
            Task.status.in_(("pending", "running")),
        )
    )
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前已有中转线路诊断或重启任务正在执行。")

    private_key = await read_private_key_payload(ssh_key or private_key_text, ssh_key_file or private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴香港服务器 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None

    task = Task(
        vps_id=route.landing_vps_id,
        node_id=route.node_id,
        task_type="restart_socat_route",
        status="pending",
        current_step="queued",
        progress=0,
    )
    db.add(task)
    db.flush()
    add_task_log(
        db,
        task.id,
        level="info",
        step="queued",
        message="socat 测试链路重启任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="restart_socat_route",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(restart_socat_route_job, task.id, route.id, temp_credential_id)

    return success_response(
        {
            "task_id": task.id,
            "transit_route_id": route.id,
        },
        "socat 测试链路重启任务已创建。",
    )


@router.post("")
@router.post("/")
async def create_transit_route(
    request: Request,
    transit_resource_id: str = Form(...),
    node_id: str = Form(...),
    listen_port: int = Form(...),
    forwarding_method: str = Form("gost"),
    route_name: str = Form(...),
    confirm: bool = Form(False),
    ssh_key: str | None = Form(None),
    private_key_text: str | None = Form(None),
    ssh_key_passphrase: str | None = Form(None),
    ssh_key_file: UploadFile | None = File(None),
    private_key_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    try:
        fields = TransitRouteCreateFields(
            transit_resource_id=transit_resource_id,
            node_id=node_id,
            listen_port=listen_port,
            forwarding_method=forwarding_method,
            route_name=route_name,
            confirm=confirm,
        )
    except ValidationError:
        return error_response(400, "INVALID_TRANSIT_ROUTE_INPUT", "中转规则参数不合法。")

    if not fields.confirm:
        return error_response(400, "CONFIRM_REQUIRED", "创建中转规则前必须确认风险提示。")

    if fields.listen_port in PROTECTED_CREATE_PORTS:
        return error_response(
            400,
            "TRANSIT_PORT_PROTECTED",
            PROTECTED_CREATE_PORT_MESSAGES[fields.listen_port],
        )

    resource = db.get(TransitResource, fields.transit_resource_id)
    if not resource or resource.deleted_at is not None:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_NOT_SERVER", "只允许 server 类型中转资源。")
    if resource.status != "active":
        return error_response(400, "TRANSIT_RESOURCE_NOT_ACTIVE", "只允许 active 中转资源。")
    if not resource.has_ssh:
        return error_response(400, "TRANSIT_RESOURCE_SSH_REQUIRED", "该中转资源未启用 SSH 元数据。")
    if not resource.ssh_host or not resource.ssh_port or not resource.ssh_username:
        return error_response(400, "TRANSIT_SSH_METADATA_MISSING", "中转资源缺少 SSH 元数据。")
    if fields.forwarding_method == "socat" and resource.id != ACCEPTED_SOCAT_RESOURCE_ID:
        return error_response(
            400,
            "SOCAT_RESOURCE_NOT_ACCEPTED",
            "Stage 3.3.3-fix-b1 只允许正式香港中转资源创建 socat 测试转发。",
        )
    if fields.forwarding_method == "gost" and not resource.entry_host:
        return error_response(400, "TRANSIT_ENTRY_HOST_REQUIRED", "中转资源缺少入口 Host，无法生成中转链接。")

    node = db.get(Node, fields.node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "NODE_NOT_FOUND", "节点不存在。")
    if node.status != "active":
        return error_response(400, "NODE_NOT_ACTIVE", "只允许给 active 节点创建中转规则。")
    if fields.forwarding_method == "gost" and not node.share_link:
        return error_response(400, "NODE_SHARE_LINK_REQUIRED", "节点缺少分享链接，不能创建中转链接。")

    vps = db.get(VpsServer, node.vps_id)
    if not vps or not vps.ip:
        return error_response(400, "LANDING_VPS_NOT_FOUND", "节点对应落地 VPS 不存在或缺少 IP。")
    if fields.forwarding_method == "socat" and not node.xray_port:
        return error_response(400, "NODE_PORT_REQUIRED", "节点缺少 Xray 端口，不能创建 socat 测试转发。")

    if fields.forwarding_method == "gost":
        active_route = db.scalar(
            select(TransitRoute).where(
                TransitRoute.status == "active",
                TransitRoute.deleted_at.is_(None),
            )
        )
        if active_route:
            return error_response(409, "TRANSIT_ROUTE_LIMIT_REACHED", "Stage 3.3.3 只允许创建一条 active 中转规则。")

    same_port_route = db.scalar(
        select(TransitRoute).where(
            TransitRoute.transit_resource_id == resource.id,
            TransitRoute.listen_port == fields.listen_port,
            TransitRoute.status.in_(("creating", "active")),
            TransitRoute.deleted_at.is_(None),
        )
    )
    if same_port_route:
        return error_response(409, "TRANSIT_PORT_IN_USE", "该中转资源已存在相同监听端口的 active 规则。")

    running_task = db.scalar(
        select(Task).where(
            Task.task_type.in_(("create_transit_route", "create_socat_route")),
            Task.status.in_(("pending", "running")),
        )
    )
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前已有中转规则创建任务正在执行。")

    private_key = await read_private_key_payload(ssh_key or private_key_text, ssh_key_file or private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴香港服务器 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None

    task_type = "create_socat_route" if fields.forwarding_method == "socat" else "create_transit_route"
    task = Task(vps_id=node.vps_id, node_id=node.id, task_type=task_type, status="pending", current_step="queued", progress=0)
    db.add(task)
    db.flush()
    route_id = str(uuid.uuid4())
    socat_route: TransitRoute | None = None
    if fields.forwarding_method == "socat":
        service_name = socat_service_name_for(route_id)
        socat_route = TransitRoute(
            id=route_id,
            name=fields.route_name,
            transit_resource_id=resource.id,
            node_id=node.id,
            landing_vps_id=vps.id,
            listen_port=fields.listen_port,
            target_host=vps.ip,
            target_port=node.xray_port or 0,
            forwarding_method="socat",
            service_name=service_name,
            service_path=socat_service_path_for(service_name),
            status="creating",
            share_link=None,
        )
        db.add(socat_route)
    add_task_log(
        db,
        task.id,
        level="info",
        step="queued",
        message=(
            "单条 socat TCP 测试转发任务已创建，等待 Worker 执行。"
            if fields.forwarding_method == "socat"
            else "单条 gost TCP 中转规则创建任务已创建，等待 Worker 执行。"
        ),
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_socat_route" if fields.forwarding_method == "socat" else "create_transit_route",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    if fields.forwarding_method == "socat":
        queue.enqueue(create_socat_route_job, task.id, route_id, temp_credential_id)
    else:
        queue.enqueue(
            create_transit_route_job,
            task.id,
            resource.id,
            node.id,
            temp_credential_id,
            {
                "route_name": fields.route_name,
                "listen_port": fields.listen_port,
                "forwarding_method": fields.forwarding_method,
            },
        )

    return success_response(
        {
            "task_id": task.id,
            "transit_resource_id": resource.id,
            "node_id": node.id,
        },
        "单条 socat TCP 测试转发任务已创建。" if fields.forwarding_method == "socat" else "单条 gost TCP 中转规则创建任务已创建。",
    )
