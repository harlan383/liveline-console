from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.db.session import get_db
from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.worker_command import WorkerCommand
from app.schemas.common import error_response, success_response
from app.schemas.transit_route import (
    APPROVED_LANDING_NODE_ID,
    APPROVED_LANDING_TARGET_HOST,
    APPROVED_LANDING_TARGET_PORT,
    APPROVED_TRANSIT_FORWARDING_METHOD,
    APPROVED_TRANSIT_INTERFACE_NAME,
    APPROVED_TRANSIT_LISTEN_PORT,
    APPROVED_TRANSIT_CANDIDATE_NAME,
    APPROVED_TRANSIT_ROUTE_ID,
    APPROVED_TRANSIT_ROUTE_NAME,
    APPROVED_TRANSIT_RESOURCE_ID,
    APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE,
    APPROVED_TRANSIT_SERVICE_NAME,
    APPROVED_TRANSIT_WORKER_ID,
    APPROVED_TRANSIT_ROUTE_CREATE_STAGE,
    PROTECTED_CREATE_PORT_MESSAGES,
    PROTECTED_CREATE_PORTS,
    ReadonlyPreflightPlanCheck,
    ReadonlyPreflightPlanRequest,
    ReadonlyPreflightPlanResponse,
    TransitReadonlyPreflightCommandRequest,
    TransitRouteCandidateExportRequest,
    TransitRouteWorkerCreateExecuteRequest,
    TransitRouteWorkerCreatePlanRequest,
)
from app.services.auth_service import record_audit
from app.services.redaction import mask_share_link
from app.services.worker_commands import create_worker_command, serialize_worker_command
from app.services.worker_targeting import (
    WorkerTargetError,
    minimum_worker_version_for_command,
    resolve_command_target_worker,
)

router = APIRouter()


TRANSIT_READONLY_PREFLIGHT_COMMAND = "transit_readonly_preflight"
TRANSIT_ROUTE_CREATE_COMMAND = "transit_route_create"
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
TRANSIT_ROUTE_CREATE_DRY_RUN_BOUNDARY = [
    "dry-run plan only",
    "approval required before real execution",
    "no arbitrary shell accepted",
    "no systemd unit content accepted from API",
    "fixed socat forwarding template only",
    "no real transit route created",
    "no socat/gost install, start, stop, or restart",
    "no listener binding",
    "no firewall or cloud security group change",
    "no Xray modification",
    "no nodes.share_link read or modification",
    "no full client link export",
    "no cutover",
]
TRANSIT_ROUTE_CREATE_REAL_BOUNDARY = [
    "approved real create only for hk-socat-live-23843",
    "no arbitrary shell accepted",
    "no systemd unit content accepted from API",
    "fixed socat forwarding template only",
    "no nodes.share_link read or modification",
    "no full client link export",
    "no Xray modification",
    "no landing node configuration modification",
    "no firewall or cloud security group change",
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
TRANSIT_CANDIDATE_EXPORT_BOUNDARY = [
    "transient candidate export only",
    "no database write",
    "no nodes.share_link mutation",
    "no transit_routes.share_link mutation",
    "no original direct node replacement",
    "no full link stored in audit logs",
    "no Worker command created",
    "no socat restart, stop, disable, or delete",
    "no Xray modification",
    "no firewall or cloud security group change",
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


def _payload_int(payload: dict | None, key: str) -> int | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _payload_text(payload: dict | None, key: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if value is None:
        return None
    return str(value).strip()


def has_matching_successful_transit_readonly_preflight(
    db: Session,
    *,
    transit_resource_id: str,
    landing_node_id: str,
    planned_listen_port: int,
    landing_target_host: str,
    landing_target_port: int,
    forwarding_method: str,
) -> bool:
    commands = db.scalars(
        select(WorkerCommand)
        .where(WorkerCommand.command_type == TRANSIT_READONLY_PREFLIGHT_COMMAND)
        .where(WorkerCommand.status == "succeeded")
        .where(WorkerCommand.server_type == "transit")
        .where(WorkerCommand.server_id == transit_resource_id)
        .order_by(WorkerCommand.completed_at.desc().nullslast(), WorkerCommand.created_at.desc())
        .limit(20)
    ).all()
    for command in commands:
        payload = command.payload_json if isinstance(command.payload_json, dict) else {}
        result = command.result_json if isinstance(command.result_json, dict) else {}
        if _payload_text(payload, "transit_resource_id") != transit_resource_id:
            continue
        if _payload_text(payload, "landing_node_id") != landing_node_id:
            continue
        if _payload_int(payload, "planned_listen_port") != planned_listen_port:
            continue
        if _payload_text(payload, "landing_target_host") != landing_target_host:
            continue
        if _payload_int(payload, "landing_target_port") != landing_target_port:
            continue
        if _payload_text(payload, "forwarding_method") != forwarding_method:
            continue
        if result.get("passed") is True or result.get("status") == "passed":
            return True
    return False


def has_in_flight_transit_route_create_command(db: Session, transit_resource_id: str) -> bool:
    command = db.scalar(
        select(WorkerCommand)
        .where(WorkerCommand.command_type == TRANSIT_ROUTE_CREATE_COMMAND)
        .where(WorkerCommand.server_type == "transit")
        .where(WorkerCommand.server_id == transit_resource_id)
        .where(WorkerCommand.status.in_(("pending", "running", "claimed")))
        .order_by(WorkerCommand.created_at.desc())
    )
    return command is not None


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


def route_entry_host(route: TransitRoute) -> str | None:
    resource = route.transit_resource
    return resource.entry_host if resource and resource.entry_host else None


def is_approved_candidate_route(route: TransitRoute) -> bool:
    return (
        route.id == APPROVED_TRANSIT_ROUTE_ID
        and route.name == APPROVED_TRANSIT_ROUTE_NAME
        and route.transit_resource_id == APPROVED_TRANSIT_RESOURCE_ID
        and route.node_id == APPROVED_LANDING_NODE_ID
        and route.listen_port == APPROVED_TRANSIT_LISTEN_PORT
        and route.target_host == APPROVED_LANDING_TARGET_HOST
        and route.target_port == APPROVED_LANDING_TARGET_PORT
        and route.forwarding_method == APPROVED_TRANSIT_FORWARDING_METHOD
        and route.service_name == APPROVED_TRANSIT_SERVICE_NAME
        and route.deleted_at is None
    )


def candidate_summary_payload(route: TransitRoute) -> dict:
    resource = route.transit_resource
    node = route.node
    vps = route.landing_vps
    entry_host = route_entry_host(route) or ""
    return {
        "route_id": route.id,
        "route_name": route.name,
        "transit_resource_id": route.transit_resource_id,
        "transit_resource_name": resource.name if resource else None,
        "entry_host": entry_host,
        "listen_port": route.listen_port,
        "target_host": route.target_host,
        "target_port": route.target_port,
        "forwarding_method": route.forwarding_method,
        "service_name": route.service_name,
        "service_path": route.service_path,
        "status": route.status,
        "landing_node_id": route.node_id,
        "landing_node_name": node.node_name if node else None,
        "landing_vps_ip": vps.ip if vps else None,
        "route_share_link_present": bool(route.share_link),
        "share_link_present": bool(route.share_link),
        "recommended_candidate": True,
        "cutover_status": "not_cutover",
        "safety_boundary": TRANSIT_CANDIDATE_EXPORT_BOUNDARY,
    }


def build_transient_candidate_link(route: TransitRoute, node: Node) -> tuple[str | None, str | None]:
    entry_host = route_entry_host(route)
    if not entry_host:
        return None, "中转入口 IP 缺失，不能生成临时候选配置。"
    required_values = {
        "uuid": node.uuid,
        "reality_public_key": node.reality_public_key,
        "reality_short_id": node.reality_short_id,
        "sni": node.sni,
    }
    missing = [name for name, value in required_values.items() if not value]
    if missing:
        return None, f"落地节点缺少必要 Reality 参数：{', '.join(missing)}。"

    values = {
        "encryption": "none",
        "security": "reality",
        "sni": node.sni or "",
        "fp": node.fingerprint or "",
        "pbk": node.reality_public_key or "",
        "sid": node.reality_short_id or "",
        "type": node.transport or "tcp",
    }
    if node.flow:
        values["flow"] = node.flow
    scheme = "vless"
    fragment = quote(APPROVED_TRANSIT_CANDIDATE_NAME, safe="")
    link = (
        f"{scheme}://{quote(node.uuid or '', safe='')}@{entry_host}:{route.listen_port}"
        f"?{urlencode(values)}#{fragment}"
    )
    return link, None


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


@router.get("/{route_id}/candidate-summary")
def get_transit_route_candidate_summary(
    route_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not require_admin_session(db, request):
        return auth_error()

    route = get_route_or_error(db, route_id)
    if not route:
        return error_response(404, "TRANSIT_ROUTE_NOT_FOUND", "中转规则不存在。")
    if not is_approved_candidate_route(route):
        return error_response(400, "TRANSIT_ROUTE_NOT_APPROVED_CANDIDATE", "该中转链路不是当前审批候选链路。")
    if route.status != "active":
        return error_response(400, "TRANSIT_ROUTE_NOT_ACTIVE", "只有 active 候选链路可以查看候选摘要。")

    return success_response(candidate_summary_payload(route), "candidate summary generated")


@router.post("/{route_id}/candidate-export")
def export_transit_route_candidate(
    route_id: str,
    payload: TransitRouteCandidateExportRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    if not payload.confirm_transient_export:
        return error_response(400, "TRANSIENT_EXPORT_CONFIRMATION_REQUIRED", "必须确认这是临时导出。")
    if not payload.confirm_no_database_write:
        return error_response(400, "NO_DATABASE_WRITE_CONFIRMATION_REQUIRED", "必须确认本次导出不写入数据库。")
    if not payload.confirm_no_share_link_mutation:
        return error_response(400, "NO_SHARE_LINK_MUTATION_CONFIRMATION_REQUIRED", "必须确认不修改 nodes.share_link。")
    if not payload.confirm_no_cutover:
        return error_response(400, "NO_CUTOVER_CONFIRMATION_REQUIRED", "必须确认本次导出不执行 cutover。")

    route = get_route_or_error(db, route_id)
    if not route:
        return error_response(404, "TRANSIT_ROUTE_NOT_FOUND", "中转规则不存在。")
    if not is_approved_candidate_route(route):
        return error_response(400, "TRANSIT_ROUTE_NOT_APPROVED_CANDIDATE", "该中转链路不是当前审批候选链路。")
    if route.status != "active":
        return error_response(400, "TRANSIT_ROUTE_NOT_ACTIVE", "只有 active 候选链路可以临时导出测试配置。")

    node = route.node
    if not node or node.deleted_at is not None:
        return error_response(404, "LANDING_NODE_NOT_FOUND", "候选链路关联的落地节点不存在。")
    if node.status != "active":
        return error_response(400, "LANDING_NODE_NOT_ACTIVE", "只有 active 落地节点可以临时导出测试配置。")
    if node.xray_port != route.target_port:
        return error_response(400, "LANDING_TARGET_PORT_MISMATCH", "落地节点端口与候选链路目标端口不一致。")

    candidate_link, link_error = build_transient_candidate_link(route, node)
    if not candidate_link:
        return error_response(409, "CANDIDATE_LINK_MATERIAL_INCOMPLETE", link_error or "候选配置参数不完整。")

    record_audit(
        db,
        admin_id=session.admin_id,
        action="export_transit_route_candidate",
        result="success",
        request=request,
        resource_type="transit_route",
        resource_id=route.id,
    )
    db.commit()

    return success_response(
        {
            "route_id": route.id,
            "route_name": route.name,
            "candidate_name": APPROVED_TRANSIT_CANDIDATE_NAME,
            "server": route_entry_host(route),
            "port": route.listen_port,
            "protocol": node.protocol,
            "security": node.security,
            "network": node.transport or "tcp",
            "flow": node.flow,
            "sni": node.sni,
            "fingerprint": node.fingerprint,
            "reality_public_key_present": bool(node.reality_public_key),
            "reality_short_id_present": bool(node.reality_short_id),
            "uuid_present": bool(node.uuid),
            "masked_candidate_link": mask_share_link(candidate_link),
            "candidate_link": candidate_link,
            "warning": "This is a transient export. It is not written to nodes.share_link and does not perform cutover.",
            "cutover_status": "not_cutover",
            "database_write_performed": False,
            "nodes_share_link_mutated": False,
            "transit_route_share_link_mutated": False,
            "safety_boundary": TRANSIT_CANDIDATE_EXPORT_BOUNDARY,
        },
        "候选测试配置已临时导出。本响应是唯一明文返回位置，请勿写入日志、文档或 PR。",
    )


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


@router.post("/worker-create-plan")
def create_transit_route_worker_create_plan(
    payload: TransitRouteWorkerCreatePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    if not payload.dry_run:
        return error_response(
            400,
            "TRANSIT_ROUTE_CREATE_DRY_RUN_REQUIRED",
            "Stage 3.3.71 只允许 dry_run=true 的中转链路创建计划。",
        )
    if not payload.approval_required:
        return error_response(
            400,
            "TRANSIT_ROUTE_CREATE_APPROVAL_REQUIRED",
            "Stage 3.3.71 仍需要下一阶段再次审批，approval_required 必须为 true。",
        )
    if not payload.user_approved_execution_boundary:
        return error_response(
            400,
            "EXECUTION_BOUNDARY_CONFIRMATION_REQUIRED",
            "必须确认本阶段只创建 dry-run 计划，不执行真实中转链路创建。",
        )
    if not payload.no_node_share_link_change_confirmed:
        return error_response(
            400,
            "NODE_SHARE_LINK_BOUNDARY_REQUIRED",
            "必须确认本阶段不读取或修改 nodes.share_link。",
        )
    if not payload.no_cutover_confirmed:
        return error_response(400, "NO_CUTOVER_CONFIRMATION_REQUIRED", "必须确认本阶段不执行 cutover。")

    if payload.transit_resource_id != APPROVED_TRANSIT_RESOURCE_ID:
        return error_response(400, "TRANSIT_RESOURCE_APPROVAL_MISMATCH", "中转资源与 Stage 3.3.70 审批记录不一致。")
    if payload.landing_node_id != APPROVED_LANDING_NODE_ID:
        return error_response(400, "LANDING_NODE_APPROVAL_MISMATCH", "落地节点与 Stage 3.3.70 审批记录不一致。")
    if payload.planned_listen_port != APPROVED_TRANSIT_LISTEN_PORT:
        return error_response(400, "LISTEN_PORT_APPROVAL_MISMATCH", "监听端口与 Stage 3.3.70 审批记录不一致。")
    if payload.landing_target_host != APPROVED_LANDING_TARGET_HOST:
        return error_response(400, "LANDING_HOST_APPROVAL_MISMATCH", "落地目标 Host 与 Stage 3.3.70 审批记录不一致。")
    if payload.landing_target_port != APPROVED_LANDING_TARGET_PORT:
        return error_response(400, "LANDING_PORT_APPROVAL_MISMATCH", "落地目标端口与 Stage 3.3.70 审批记录不一致。")
    if payload.forwarding_method != APPROVED_TRANSIT_FORWARDING_METHOD:
        return error_response(400, "FORWARDING_METHOD_APPROVAL_MISMATCH", "转发方式与 Stage 3.3.70 审批记录不一致。")
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
        return error_response(400, "TRANSIT_RESOURCE_TYPE_UNSUPPORTED", "只允许 server 类型中转资源进入创建计划。")
    if resource.status == "disabled":
        return error_response(400, "TRANSIT_RESOURCE_DISABLED", "已停用的中转资源不能进入创建计划。")

    node = db.get(Node, payload.landing_node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "LANDING_NODE_NOT_FOUND", "落地节点不存在。")
    if node.status != "active":
        return error_response(400, "LANDING_NODE_NOT_ACTIVE", "只允许 active 落地节点进入创建计划。")
    landing_host = node.vps.ip if node.vps else None
    if landing_host != payload.landing_target_host:
        return error_response(400, "LANDING_HOST_MISMATCH", "落地节点当前 IP 与审批目标不一致。")
    if node.xray_port != payload.landing_target_port:
        return error_response(400, "LANDING_TARGET_PORT_MISMATCH", "落地节点当前端口与审批目标不一致。")

    existing_route = db.scalar(
        select(TransitRoute).where(
            TransitRoute.transit_resource_id == resource.id,
            TransitRoute.listen_port == payload.planned_listen_port,
            TransitRoute.status.in_(("creating", "active")),
            TransitRoute.deleted_at.is_(None),
        )
    )
    if existing_route:
        return error_response(409, "TRANSIT_PORT_ALREADY_PLANNED", "该中转资源已有相同监听端口的 creating/active 线路记录。")

    if not has_matching_successful_transit_readonly_preflight(
        db,
        transit_resource_id=resource.id,
        landing_node_id=node.id,
        planned_listen_port=payload.planned_listen_port,
        landing_target_host=payload.landing_target_host,
        landing_target_port=payload.landing_target_port,
        forwarding_method=payload.forwarding_method,
    ):
        return error_response(
            400,
            "READONLY_PREFLIGHT_REQUIRED",
            "未找到匹配的已成功远程只读预检记录，不能创建中转链路 dry-run 计划。",
        )

    try:
        target = resolve_command_target_worker(
            db,
            server_type="transit",
            server_id=resource.id,
            role="transit",
            command_type=TRANSIT_ROUTE_CREATE_COMMAND,
        )
    except WorkerTargetError as exc:
        return error_response(400, exc.code, exc.message)

    target_worker = target.worker
    if target_worker.interface_name != APPROVED_TRANSIT_INTERFACE_NAME:
        return error_response(
            400,
            "WORKER_INTERFACE_MISMATCH",
            "目标 Worker interface_name 与 Stage 3.3.70 审批记录不一致。",
        )
    command_payload = {
        "transit_resource_id": resource.id,
        "transit_resource_name": resource.name,
        "landing_node_id": node.id,
        "landing_node_name": node.node_name,
        "planned_listen_port": payload.planned_listen_port,
        "landing_target_host": payload.landing_target_host,
        "landing_target_port": payload.landing_target_port,
        "forwarding_method": payload.forwarding_method,
        "purpose": payload.purpose,
        "approval_stage": payload.approval_stage,
        "dry_run": True,
        "approval_required": True,
        "route_name": "hk-socat-live-23843",
        "safety_boundary": TRANSIT_ROUTE_CREATE_DRY_RUN_BOUNDARY,
    }
    command = create_worker_command(db, target_worker, TRANSIT_ROUTE_CREATE_COMMAND, command_payload)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_transit_route_worker_create_plan",
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
            "minimum_supported_worker_version": minimum_worker_version_for_command(TRANSIT_ROUTE_CREATE_COMMAND),
            "execution_mode": "dry_run",
            "approval_required": True,
            "safety_boundary": TRANSIT_ROUTE_CREATE_DRY_RUN_BOUNDARY,
        },
        "中转链路 Worker 创建路径 dry-run command 已创建；不会创建真实转发。",
    )


@router.post("/worker-create-execute")
def create_transit_route_worker_create_execute(
    payload: TransitRouteWorkerCreateExecuteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    if payload.dry_run:
        return error_response(400, "TRANSIT_ROUTE_REAL_CREATE_REQUIRED", "真实执行入口必须 dry_run=false。")
    if payload.approval_required:
        return error_response(
            400,
            "TRANSIT_ROUTE_APPROVAL_ALREADY_REQUIRED",
            "Stage 3.3.73d 需要显式真实执行授权，approval_required 必须为 false。",
        )
    if not payload.user_approved_real_execution:
        return error_response(400, "REAL_EXECUTION_APPROVAL_REQUIRED", "必须确认允许真实创建本次固定中转链路。")
    if not payload.firewall_security_group_confirmed:
        return error_response(400, "SECURITY_GROUP_CONFIRMATION_REQUIRED", "必须确认云安全组已放行 23843/TCP。")
    if not payload.cloud_firewall_confirmed:
        return error_response(400, "CLOUD_FIREWALL_CONFIRMATION_REQUIRED", "必须确认云防火墙已放行 23843/TCP。")
    if not payload.server_firewall_confirmed:
        return error_response(400, "SERVER_FIREWALL_CONFIRMATION_REQUIRED", "必须确认服务器防火墙已放行或无阻断。")
    if not payload.no_node_share_link_change_confirmed:
        return error_response(
            400,
            "NODE_SHARE_LINK_BOUNDARY_REQUIRED",
            "必须确认本阶段不读取或修改 nodes.share_link。",
        )
    if not payload.no_full_client_link_confirmed:
        return error_response(400, "NO_FULL_CLIENT_LINK_CONFIRMATION_REQUIRED", "必须确认不生成或展示完整节点链接。")
    if not payload.no_cutover_confirmed:
        return error_response(400, "NO_CUTOVER_CONFIRMATION_REQUIRED", "必须确认本阶段不执行 cutover。")

    if payload.approval_stage != APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE:
        return error_response(400, "APPROVAL_STAGE_MISMATCH", "真实执行审批阶段不匹配。")
    if payload.transit_resource_id != APPROVED_TRANSIT_RESOURCE_ID:
        return error_response(400, "TRANSIT_RESOURCE_APPROVAL_MISMATCH", "中转资源与审批记录不一致。")
    if payload.landing_node_id != APPROVED_LANDING_NODE_ID:
        return error_response(400, "LANDING_NODE_APPROVAL_MISMATCH", "落地节点与审批记录不一致。")
    if payload.planned_listen_port != APPROVED_TRANSIT_LISTEN_PORT:
        return error_response(400, "LISTEN_PORT_APPROVAL_MISMATCH", "监听端口与审批记录不一致。")
    if payload.landing_target_host != APPROVED_LANDING_TARGET_HOST:
        return error_response(400, "LANDING_HOST_APPROVAL_MISMATCH", "落地目标 Host 与审批记录不一致。")
    if payload.landing_target_port != APPROVED_LANDING_TARGET_PORT:
        return error_response(400, "LANDING_PORT_APPROVAL_MISMATCH", "落地目标端口与审批记录不一致。")
    if payload.forwarding_method != APPROVED_TRANSIT_FORWARDING_METHOD:
        return error_response(400, "FORWARDING_METHOD_APPROVAL_MISMATCH", "转发方式与审批记录不一致。")
    if payload.route_name != APPROVED_TRANSIT_ROUTE_NAME:
        return error_response(400, "ROUTE_NAME_APPROVAL_MISMATCH", "线路名称与审批记录不一致。")
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
        return error_response(400, "TRANSIT_RESOURCE_TYPE_UNSUPPORTED", "只允许 server 类型中转资源执行真实创建。")
    if resource.status == "disabled":
        return error_response(400, "TRANSIT_RESOURCE_DISABLED", "已停用的中转资源不能执行真实创建。")

    node = db.get(Node, payload.landing_node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "LANDING_NODE_NOT_FOUND", "落地节点不存在。")
    if node.status != "active":
        return error_response(400, "LANDING_NODE_NOT_ACTIVE", "只允许 active 落地节点执行真实创建。")
    landing_host = node.vps.ip if node.vps else None
    if landing_host != payload.landing_target_host:
        return error_response(400, "LANDING_HOST_MISMATCH", "落地节点当前 IP 与审批目标不一致。")
    if node.xray_port != payload.landing_target_port:
        return error_response(400, "LANDING_TARGET_PORT_MISMATCH", "落地节点当前端口与审批目标不一致。")

    existing_route = db.scalar(
        select(TransitRoute).where(
            TransitRoute.transit_resource_id == resource.id,
            TransitRoute.listen_port == payload.planned_listen_port,
            TransitRoute.status.in_(("creating", "active")),
            TransitRoute.deleted_at.is_(None),
        )
    )
    if existing_route:
        return error_response(409, "TRANSIT_PORT_ALREADY_PLANNED", "该中转资源已有相同监听端口的 creating/active 线路记录。")

    if has_in_flight_transit_route_create_command(db, resource.id):
        return error_response(409, "TRANSIT_ROUTE_CREATE_COMMAND_IN_FLIGHT", "当前已有 pending/running/claimed 中转链路创建命令。")

    if not has_matching_successful_transit_readonly_preflight(
        db,
        transit_resource_id=resource.id,
        landing_node_id=node.id,
        planned_listen_port=payload.planned_listen_port,
        landing_target_host=payload.landing_target_host,
        landing_target_port=payload.landing_target_port,
        forwarding_method=payload.forwarding_method,
    ):
        return error_response(
            400,
            "READONLY_PREFLIGHT_REQUIRED",
            "未找到匹配的已成功远程只读预检记录，不能执行真实中转链路创建。",
        )

    try:
        target = resolve_command_target_worker(
            db,
            server_type="transit",
            server_id=resource.id,
            role="transit",
            requested_worker_id=APPROVED_TRANSIT_WORKER_ID,
            command_type=TRANSIT_ROUTE_CREATE_COMMAND,
        )
    except WorkerTargetError as exc:
        return error_response(400, exc.code, exc.message)

    target_worker = target.worker
    if target_worker.id != APPROVED_TRANSIT_WORKER_ID:
        return error_response(400, "WORKER_APPROVAL_MISMATCH", "目标 Worker 与审批记录不一致。")
    if target_worker.interface_name != APPROVED_TRANSIT_INTERFACE_NAME:
        return error_response(
            400,
            "WORKER_INTERFACE_MISMATCH",
            "目标 Worker interface_name 与审批记录不一致。",
        )
    if target_worker.role != "transit":
        return error_response(400, "WORKER_ROLE_MISMATCH", "只允许 transit role Worker 执行真实创建。")

    command_payload = {
        "transit_resource_id": resource.id,
        "transit_resource_name": resource.name,
        "landing_node_id": node.id,
        "landing_node_name": node.node_name,
        "planned_listen_port": payload.planned_listen_port,
        "landing_target_host": payload.landing_target_host,
        "landing_target_port": payload.landing_target_port,
        "forwarding_method": payload.forwarding_method,
        "purpose": payload.purpose,
        "approval_stage": payload.approval_stage,
        "dry_run": False,
        "approval_required": False,
        "execution_mode": "real_create",
        "approved_real_execution": True,
        "route_name": payload.route_name,
        "firewall_security_group_confirmed": True,
        "cloud_firewall_confirmed": True,
        "server_firewall_confirmed": True,
        "no_node_share_link_change_confirmed": True,
        "no_full_client_link_confirmed": True,
        "no_cutover_confirmed": True,
        "safety_boundary": TRANSIT_ROUTE_CREATE_REAL_BOUNDARY,
    }
    command = create_worker_command(db, target_worker, TRANSIT_ROUTE_CREATE_COMMAND, command_payload)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_transit_route_worker_create_execute",
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
            "minimum_supported_worker_version": minimum_worker_version_for_command(TRANSIT_ROUTE_CREATE_COMMAND),
            "execution_mode": "real_create",
            "approval_required": False,
            "safety_boundary": TRANSIT_ROUTE_CREATE_REAL_BOUNDARY,
        },
        "中转链路真实创建 Worker command 已创建；结果成功后才会写入 transit_routes，不读取或修改 nodes.share_link。",
    )
