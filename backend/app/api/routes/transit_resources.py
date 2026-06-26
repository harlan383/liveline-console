from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.db.session import get_db
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.worker import Worker, WorkerToken
from app.schemas.common import error_response, success_response
from app.schemas.remote_cleanup import OFFLINE_LOCAL_REMOVE_CONFIRMATION, RemoteCleanupDeleteRequest
from app.schemas.transit_resource import (
    PROTOCOL_HINTS,
    RESOURCE_STATUSES,
    RESOURCE_TYPES,
    TRANSIT_WORKER_INSTALL_COMMAND_GENERATION_CONFIRMATION,
    TransitResourceCreate,
    TransitResourceUpdate,
    TransitWorkerInstallCommandGenerationRequest,
)
from app.services.auth_service import record_audit
from app.services.remote_cleanup_delete import (
    RemoteCleanupError,
    create_transit_resource_cleanup_command,
    offline_local_remove_transit_resource,
    remote_cleanup_unavailable_offer,
)
from app.services.worker_binding import (
    WORKER_PENDING_STATUS,
    WorkerPublicUrlError,
    connection_mode_for_transit,
    create_bound_worker_token,
    latest_workers_by_server,
    serialize_worker_token_bootstrap,
    transit_display_status,
    validate_worker_interface_name,
    worker_public_base_url,
    worker_public_url_error_response,
    worker_runtime_status,
    worker_summary_fields,
)
from app.services.worker_commands import serialize_worker_command
from app.services.worker_targeting import (
    minimum_worker_version_for_transit_forwarding_method,
    worker_supports_transit_forwarding_method,
)

router = APIRouter()
EXPECTED_TRANSIT_WORKER_ACCEPTANCE_VERSION = "0.1.33-stage-3.3.180-dynamic-landing-create-port"
TRANSIT_WORKER_UPGRADE_ACCEPTANCE_FORWARDING_METHOD = "haproxy_tcp"
TRANSIT_WORKER_UPGRADE_ACCEPTANCE_CHECKSUM = "385ffcf6e8da9bc0a5a613286f9831be7165d5c0b1f6d053cc9f64598928d040"
TRANSIT_WORKER_ACCEPTANCE_RESOURCE_STATUSES = {"pending_worker", "worker_online", "worker_offline"}
WORKER_INSTALL_COMMAND_ALLOWED_STATUSES = {"pending_worker", "worker_online", "worker_offline", "online"}


class TransitWorkerBootstrapRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    ip: str = Field(min_length=1, max_length=45)
    expires_in_minutes: int = Field(default=60, ge=1, le=10_080)
    interface_name: str = Field(default="eth0", min_length=1, max_length=80)

    @field_validator("name", "ip")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value cannot be empty")
        return cleaned

    @field_validator("interface_name")
    @classmethod
    def clean_interface_name(cls, value: str) -> str:
        return validate_worker_interface_name(value)


class TransitWorkerBootstrapRegenerateRequest(BaseModel):
    expires_in_minutes: int = Field(default=60, ge=1, le=10_080)
    interface_name: str = Field(default="eth0", min_length=1, max_length=80)

    @field_validator("interface_name")
    @classmethod
    def clean_interface_name(cls, value: str) -> str:
        return validate_worker_interface_name(value)


def numeric_value(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def serialize_transit_resource(resource: TransitResource, *, worker=None) -> dict:
    worker_fields = worker_summary_fields(worker)
    return {
        "id": resource.id,
        "name": resource.name,
        "resource_type": resource.resource_type,
        "provider": resource.provider,
        "entry_host": resource.entry_host,
        "entry_port": resource.entry_port,
        "entry_region": resource.entry_region,
        "exit_region": resource.exit_region,
        "bandwidth_mbps": resource.bandwidth_mbps,
        "traffic_limit_gb": numeric_value(resource.traffic_limit_gb),
        "traffic_used_gb": numeric_value(resource.traffic_used_gb),
        "protocol_hint": resource.protocol_hint,
        "has_ssh": resource.has_ssh,
        "ssh_host": resource.ssh_host,
        "ssh_port": resource.ssh_port,
        "ssh_username": resource.ssh_username,
        "status": resource.status,
        "connection_mode": connection_mode_for_transit(resource, worker),
        "display_status": transit_display_status(resource, worker),
        **worker_fields,
        "expires_at": resource.expires_at.isoformat() if resource.expires_at else None,
        "notes": resource.notes,
        "created_at": resource.created_at.isoformat() if resource.created_at else None,
        "updated_at": resource.updated_at.isoformat() if resource.updated_at else None,
        "deleted_at": resource.deleted_at.isoformat() if resource.deleted_at else None,
    }


def worker_acceptance_check(check_id: str, label: str, passed: bool, detail: str) -> dict:
    return {
        "id": check_id,
        "label": label,
        "passed": passed,
        "status": "passed" if passed else "pending",
        "detail": detail,
    }


def transit_worker_acceptance_next_action(*, worker_found: bool, role_ok: bool, heartbeat_ok: bool, version_ok: bool, accepted: bool) -> str:
    if accepted:
        return "Worker manual install acceptance passed. 下一阶段可进入 HAProxy readiness / route creation approval。"
    if not worker_found:
        return "请确认已在真实测试中转 VPS 手动执行安装命令，并等待 10-30 秒后刷新。"
    if not heartbeat_ok:
        return "Worker 记录已存在但未在线，请检查真实测试 VPS 上 liveline-worker 服务状态。"
    if not role_ok:
        return "Worker role 不正确，必须是 transit。"
    if not version_ok:
        return "Worker 版本不满足要求，需要使用 Stage 3.3.134 生成的新安装命令重新安装或升级。"
    return "请检查 Worker 绑定信息后刷新验收状态。"


def serialize_transit_worker_acceptance(resource: TransitResource, worker: Worker | None) -> dict:
    runtime_status = worker_runtime_status(worker) if worker else None
    worker_found = worker is not None
    server_binding_ok = bool(worker and worker.server_id == resource.id)
    role_ok = bool(worker and worker.role == "transit")
    heartbeat_ok = runtime_status == "online"
    version_ok = bool(worker and worker.worker_version == EXPECTED_TRANSIT_WORKER_ACCEPTANCE_VERSION)
    interface_detected = bool(worker and worker.interface_name)
    accepted = worker_found and server_binding_ok and role_ok and heartbeat_ok and version_ok
    next_action = transit_worker_acceptance_next_action(
        worker_found=worker_found,
        role_ok=role_ok,
        heartbeat_ok=heartbeat_ok,
        version_ok=version_ok,
        accepted=accepted,
    )
    checks = [
        worker_acceptance_check(
            "manual_install_command_was_user_executed",
            "用户已手动执行安装命令",
            worker_found,
            "系统不验证命令内容，只通过 Worker heartbeat 与绑定状态判断人工安装结果。",
        ),
        worker_acceptance_check(
            "worker_record_found",
            "找到绑定当前资源的 Worker",
            worker_found,
            "查询当前 transit resource 绑定的最新 Worker 记录。",
        ),
        worker_acceptance_check(
            "server_binding_ok",
            "Worker server_id 绑定正确",
            server_binding_ok,
            "Worker.server_id 必须等于当前 transit resource id。",
        ),
        worker_acceptance_check(
            "role_ok",
            "Worker role 正确",
            role_ok,
            "Worker.role 必须是 transit。",
        ),
        worker_acceptance_check(
            "heartbeat_ok",
            "Worker heartbeat 在线",
            heartbeat_ok,
            "worker_runtime_status(worker) 必须是 online。",
        ),
        worker_acceptance_check(
            "version_ok",
            "Worker version 满足要求",
            version_ok,
            f"当前采用精确版本比较，目标版本为 {EXPECTED_TRANSIT_WORKER_ACCEPTANCE_VERSION}。",
        ),
        worker_acceptance_check(
            "interface_detected",
            "Worker 上报 interface_name",
            interface_detected,
            "interface_name 用于后续 HAProxy / route readiness 审批参考。",
        ),
        worker_acceptance_check("token_not_exposed", "不输出 token", True, "本接口不返回 Worker token 或 install command。"),
        worker_acceptance_check("remote_execution_not_performed", "未执行远程命令", True, "本接口只读，不 SSH，不安装 Worker。"),
        worker_acceptance_check("worker_command_not_created", "未创建 Worker command", True, "本接口不会创建 Worker command。"),
        worker_acceptance_check("haproxy_not_created", "未创建 HAProxy route", True, "本接口不会安装 HAProxy 或创建 HAProxy route。"),
    ]
    return {
        "resource_id": resource.id,
        "resource_name": resource.name,
        "resource_status": resource.status,
        "expected_role": "transit",
        "expected_worker_version": EXPECTED_TRANSIT_WORKER_ACCEPTANCE_VERSION,
        "worker_found": worker_found,
        "worker_id": worker.id if worker else None,
        "worker_role": worker.role if worker else None,
        "worker_status": runtime_status,
        "worker_online": heartbeat_ok,
        "worker_version": worker.worker_version if worker else None,
        "worker_hostname": worker.hostname if worker else None,
        "worker_interface_name": worker.interface_name if worker else None,
        "worker_last_heartbeat_at": worker.last_heartbeat_at.isoformat() if worker and worker.last_heartbeat_at else None,
        "server_binding_ok": server_binding_ok,
        "role_ok": role_ok,
        "version_ok": version_ok,
        "heartbeat_ok": heartbeat_ok,
        "interface_detected": interface_detected,
        "accepted": accepted,
        "blocked": not accepted,
        "summary": (
            "Worker 手动安装验收通过：role / binding / version / heartbeat 均满足要求。"
            if accepted
            else "Worker 手动安装验收未完成，请按下一步建议处理后刷新。"
        ),
        "next_action": next_action,
        "checks": checks,
        "safety_boundary": [
            "本接口不返回安装命令。",
            "本接口不返回 Worker token。",
            "本接口不执行 SSH 或远程命令。",
            "本接口不安装 Worker。",
            "本接口不创建 Worker command。",
            "本接口不创建 HAProxy route。",
            "本接口不修改 firewall / security group / cloud firewall。",
            "本接口不读取或修改 nodes.share_link。",
            "本接口不写 transit_routes.share_link。",
            "本接口不 cutover。",
        ],
    }


def transit_worker_upgrade_blocked_reason(
    *,
    worker_found: bool,
    server_binding_ok: bool,
    role_ok: bool,
    heartbeat_ok: bool,
    version_present: bool,
    version_ok: bool,
) -> str | None:
    if not worker_found:
        return "Transit Worker record is missing."
    if not server_binding_ok:
        return "Transit Worker is not bound to this transit resource."
    if not role_ok:
        return "Transit Worker role must be transit."
    if not heartbeat_ok:
        return "Transit Worker must be online before HAProxy TCP dry-run."
    if not version_present:
        return "Transit Worker version is missing."
    if not version_ok:
        return "Transit Worker must be upgraded before HAProxy TCP dry-run."
    return None


def serialize_transit_worker_upgrade_acceptance(resource: TransitResource, worker: Worker | None) -> dict:
    runtime_status = worker_runtime_status(worker) if worker else None
    required_worker_version = minimum_worker_version_for_transit_forwarding_method(
        TRANSIT_WORKER_UPGRADE_ACCEPTANCE_FORWARDING_METHOD
    )
    worker_found = worker is not None
    server_binding_ok = bool(worker and worker.server_id == resource.id)
    role_ok = bool(worker and worker.role == "transit")
    heartbeat_ok = runtime_status == "online"
    version_present = bool(worker and worker.worker_version)
    version_ok = worker_supports_transit_forwarding_method(
        worker,
        TRANSIT_WORKER_UPGRADE_ACCEPTANCE_FORWARDING_METHOD,
    )
    acceptance_passed = worker_found and server_binding_ok and role_ok and heartbeat_ok and version_ok
    upgrade_required = worker_found and version_present and not version_ok
    blocked_reason = transit_worker_upgrade_blocked_reason(
        worker_found=worker_found,
        server_binding_ok=server_binding_ok,
        role_ok=role_ok,
        heartbeat_ok=heartbeat_ok,
        version_present=version_present,
        version_ok=version_ok,
    )
    if acceptance_passed:
        summary = "Transit Worker upgrade acceptance passed"
        next_action = "可以回到 Stage 3.3.137 重新生成 HAProxy route dry-run。"
    elif upgrade_required:
        summary = "Transit Worker upgrade acceptance blocked"
        next_action = "手动升级 transit Worker 后刷新验收。"
    else:
        summary = "Transit Worker upgrade acceptance blocked"
        next_action = "请先恢复 transit Worker online / role / binding / version 状态后刷新验收。"

    current_status = worker.worker_version if worker and worker.worker_version else "missing"
    checks = [
        worker_acceptance_check(
            "worker_record_found",
            "找到绑定当前资源的 Worker",
            worker_found,
            "查询当前 transit resource 绑定的最新 Worker 记录。",
        ),
        worker_acceptance_check(
            "server_binding_ok",
            "Worker server_id 绑定正确",
            server_binding_ok,
            "Worker.server_id 必须等于当前 transit resource id。",
        ),
        worker_acceptance_check(
            "role_ok",
            "Worker role 为 transit",
            role_ok,
            "只有 transit Worker 可以进入 HAProxy TCP dry-run。",
        ),
        worker_acceptance_check(
            "heartbeat_online",
            "Worker heartbeat 在线",
            heartbeat_ok,
            "worker_runtime_status(worker) 必须是 online。",
        ),
        worker_acceptance_check(
            "worker_version_present",
            "Worker version 已上报",
            version_present,
            "Worker 必须上报 worker_version 才能做升级验收。",
        ),
        worker_acceptance_check(
            "worker_version_supported",
            "Worker version 满足 HAProxy TCP dry-run 最低版本",
            version_ok,
            f"要求版本 {required_worker_version} 或更高；当前版本为 {current_status}。",
        ),
        worker_acceptance_check(
            "worker_command_not_created",
            "未创建 Worker command",
            True,
            "本接口只读，不创建 dry-run、real execution 或任何 Worker command。",
        ),
        worker_acceptance_check(
            "transit_route_not_created",
            "未创建 TransitRoute",
            True,
            "本接口只读，不创建 HAProxy route 或 TransitRoute active record。",
        ),
        worker_acceptance_check(
            "share_link_not_read_or_written",
            "未读取或写入 share_link",
            True,
            "本接口不访问 nodes.share_link，也不写 transit_routes.share_link。",
        ),
        worker_acceptance_check(
            "remote_execution_not_performed",
            "未执行远程命令",
            True,
            "本接口不 SSH、不安装 Worker、不重启 Worker、不安装 HAProxy、不绑定监听端口。",
        ),
    ]
    return {
        "resource_id": resource.id,
        "resource_name": resource.name,
        "role": "transit",
        "worker_id": worker.id if worker else None,
        "worker_status": runtime_status,
        "worker_online": heartbeat_ok,
        "current_worker_version": worker.worker_version if worker else None,
        "required_worker_version": required_worker_version,
        "required_worker_checksum": TRANSIT_WORKER_UPGRADE_ACCEPTANCE_CHECKSUM,
        "worker_hostname": worker.hostname if worker else None,
        "worker_interface_name": worker.interface_name if worker else None,
        "worker_last_heartbeat_at": worker.last_heartbeat_at.isoformat() if worker and worker.last_heartbeat_at else None,
        "worker_found": worker_found,
        "server_binding_ok": server_binding_ok,
        "role_ok": role_ok,
        "heartbeat_ok": heartbeat_ok,
        "version_present": version_present,
        "version_ok": version_ok,
        "upgrade_required": upgrade_required,
        "acceptance_passed": acceptance_passed,
        "blocked": not acceptance_passed,
        "blocked_reason": blocked_reason,
        "summary": summary,
        "next_action": next_action,
        "checks": checks,
        "worker_command_created": False,
        "transit_route_created": False,
        "share_link_read_or_written": False,
        "safety_boundary": [
            "本接口不生成 Worker token。",
            "本接口不生成 Worker install command。",
            "本接口不执行 SSH 或远程命令。",
            "本接口不安装或重启 Worker。",
            "本接口不创建 Worker command。",
            "本接口不创建真实 execution command。",
            "本接口不创建 HAProxy route 或 TransitRoute active record。",
            "本接口不安装 HAProxy 或绑定监听端口。",
            "本接口不修改 firewall / security group / cloud firewall。",
            "本接口不读取或修改 nodes.share_link。",
            "本接口不写 transit_routes.share_link。",
            "本接口不 cutover。",
        ],
    }


def get_transit_resource_or_error(
    db: Session,
    resource_id: str,
) -> TransitResource | None:
    return db.scalar(
        select(TransitResource).where(
            TransitResource.id == resource_id,
            TransitResource.deleted_at.is_(None),
        )
    )


def apply_payload(resource: TransitResource, payload: dict) -> None:
    for key, value in payload.items():
        setattr(resource, key, value)
    if not resource.has_ssh:
        resource.ssh_host = None
        resource.ssh_port = None
        resource.ssh_username = None


@router.get("")
@router.get("/")
def list_transit_resources(
    request: Request,
    status: str | None = None,
    resource_type: str | None = None,
    db: Session = Depends(get_db),
):
    if not require_admin_session(db, request):
        return auth_error()

    if status and status not in RESOURCE_STATUSES:
        return error_response(400, "INVALID_STATUS", "中转资源状态不合法。")
    if resource_type and resource_type not in RESOURCE_TYPES:
        return error_response(400, "INVALID_RESOURCE_TYPE", "中转资源类型不合法。")

    conditions = [TransitResource.deleted_at.is_(None)]
    if status:
        conditions.append(TransitResource.status == status)
    if resource_type:
        conditions.append(TransitResource.resource_type == resource_type)

    resources = db.scalars(
        select(TransitResource)
        .where(*conditions)
        .order_by(TransitResource.created_at.desc())
    ).all()
    workers = latest_workers_by_server(db, role="transit", server_ids=[resource.id for resource in resources])

    return success_response(
        {"resources": [serialize_transit_resource(resource, worker=workers.get(resource.id)) for resource in resources]},
        "ok",
    )


@router.post("")
@router.post("/")
def create_transit_resource(
    payload: TransitResourceCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    resource = TransitResource(**payload.model_dump())
    if not resource.has_ssh:
        resource.ssh_host = None
        resource.ssh_port = None
        resource.ssh_username = None
    db.add(resource)
    db.flush()
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_transit_resource",
        result="success",
        request=request,
        resource_type="transit_resource",
        resource_id=resource.id,
    )
    db.commit()
    db.refresh(resource)

    return success_response(
        serialize_transit_resource(resource),
        "中转资源已创建。本阶段只保存资源信息，不会连接远端。",
    )


@router.post("/worker-bootstrap")
def create_transit_resource_worker_bootstrap(
    payload: TransitWorkerBootstrapRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    from app.services.vps_validation import validate_public_ipv4

    host_error = validate_public_ipv4(payload.ip)
    if host_error:
        return error_response(400, host_error, "中转服务器 IP 格式不合法，只允许公网 IPv4。")

    existing = db.scalar(
        select(TransitResource).where(
            TransitResource.deleted_at.is_(None),
            TransitResource.resource_type == "server",
            TransitResource.entry_host == payload.ip,
        )
    )
    if existing:
        return error_response(409, "TRANSIT_RESOURCE_ALREADY_EXISTS", "该中转服务器记录已存在，请编辑现有记录。")

    try:
        resource = TransitResource(
            name=payload.name,
            resource_type="server",
            provider=None,
            entry_host=payload.ip,
            entry_port=22,
            protocol_hint="tcp",
            has_ssh=False,
            ssh_host=None,
            ssh_port=None,
            ssh_username=None,
            status=WORKER_PENDING_STATUS,
            notes=None,
        )
        db.add(resource)
        db.flush()
        token, raw_token, install_command = create_bound_worker_token(
            db,
            role="transit",
            name=resource.name,
            server_id=resource.id,
            admin_id=session.admin_id,
            expires_in_minutes=payload.expires_in_minutes,
            interface_name=payload.interface_name,
        )
        record_audit(
            db,
            admin_id=session.admin_id,
            action="create_transit_resource_worker_bootstrap",
            result="success",
            request=request,
            resource_type="transit_resource",
            resource_id=resource.id,
        )
        db.commit()
        db.refresh(resource)
        db.refresh(token)
    except WorkerPublicUrlError as exc:
        db.rollback()
        return worker_public_url_error_response(exc)

    return success_response(
        {
            "resource": serialize_transit_resource(resource),
            "token": serialize_worker_token_bootstrap(token, raw_token, install_command),
            "install_command": install_command,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        },
        "中转服务器记录已创建，Worker 安装命令已生成。",
    )


@router.post("/{resource_id}/worker-bootstrap/regenerate")
def regenerate_transit_resource_worker_bootstrap(
    resource_id: str,
    payload: TransitWorkerBootstrapRegenerateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_NOT_SERVER", "只允许 server 类型中转资源重新生成 Worker 安装命令。")
    if resource.status != WORKER_PENDING_STATUS:
        return error_response(
            400,
            "TRANSIT_RESOURCE_NOT_PENDING_WORKER",
            "只允许 pending_worker 且 Worker 未注册的中转服务器重新生成安装命令。",
        )

    bound_workers = db.scalars(
        select(Worker).where(
            Worker.role == "transit",
            Worker.server_id == resource.id,
        )
    ).all()
    online_workers = [worker for worker in bound_workers if worker_runtime_status(worker) == "online"]
    if online_workers:
        return error_response(
            409,
            "TRANSIT_RESOURCE_WORKER_ALREADY_ONLINE",
            "该中转服务器已有在线 Worker，不允许重新生成安装命令。",
        )

    try:
        old_tokens = db.scalars(
            select(WorkerToken).where(
                WorkerToken.server_id == resource.id,
                WorkerToken.role == "transit",
                WorkerToken.status == "active",
            )
        ).all()
        for old_token in old_tokens:
            old_token.status = "revoked"
            db.add(old_token)

        token, raw_token, install_command = create_bound_worker_token(
            db,
            role="transit",
            name=resource.name,
            server_id=resource.id,
            admin_id=session.admin_id,
            expires_in_minutes=payload.expires_in_minutes,
            interface_name=payload.interface_name,
        )
        record_audit(
            db,
            admin_id=session.admin_id,
            action="regenerate_transit_resource_worker_bootstrap",
            result="success",
            request=request,
            resource_type="transit_resource",
            resource_id=resource.id,
        )
        db.commit()
        db.refresh(resource)
        db.refresh(token)
    except WorkerPublicUrlError as exc:
        db.rollback()
        return worker_public_url_error_response(exc)

    return success_response(
        {
            "resource": serialize_transit_resource(resource),
            "token": serialize_worker_token_bootstrap(token, raw_token, install_command),
            "install_command": install_command,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        },
        "新的 Worker 安装命令已生成，请立即复制并妥善保存。",
    )


@router.post("/{resource_id}/worker-install-command")
def generate_transit_resource_worker_install_command(
    resource_id: str,
    payload: TransitWorkerInstallCommandGenerationRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    if payload.confirmation != TRANSIT_WORKER_INSTALL_COMMAND_GENERATION_CONFIRMATION:
        return error_response(400, "CONFIRMATION_MISMATCH", "真实生成命令审批确认文本不匹配。")

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_NOT_SERVER", "只允许 server 类型中转资源生成 Worker 安装命令。")
    if resource.status not in WORKER_INSTALL_COMMAND_ALLOWED_STATUSES:
        return error_response(
            400,
            "TRANSIT_RESOURCE_STATUS_NOT_ALLOWED",
            "当前中转服务器状态不允许生成 Worker 安装命令。",
        )
    if not resource.entry_host:
        return error_response(400, "TRANSIT_RESOURCE_ENTRY_HOST_REQUIRED", "生成安装命令前必须填写中转 VPS 公网 IP 或域名。")

    try:
        controller_url = worker_public_base_url()
        old_tokens = db.scalars(
            select(WorkerToken).where(
                WorkerToken.server_id == resource.id,
                WorkerToken.role == "transit",
                WorkerToken.status == "active",
            )
        ).all()
        for old_token in old_tokens:
            old_token.status = "revoked"
            db.add(old_token)

        token, raw_token, install_command = create_bound_worker_token(
            db,
            role="transit",
            name=resource.name,
            server_id=resource.id,
            admin_id=session.admin_id,
            expires_in_minutes=payload.expires_in_minutes,
            interface_name=payload.interface_name,
        )
        record_audit(
            db,
            admin_id=session.admin_id,
            action="generate_transit_resource_worker_install_command",
            result="success",
            request=request,
            resource_type="transit_resource",
            resource_id=resource.id,
        )
        db.commit()
        db.refresh(resource)
        db.refresh(token)
    except WorkerPublicUrlError as exc:
        db.rollback()
        return worker_public_url_error_response(exc)

    return success_response(
        {
            "resource": serialize_transit_resource(resource),
            "token": serialize_worker_token_bootstrap(token, raw_token, install_command),
            "install_command": install_command,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
            "controller_url": controller_url,
            "role": "transit",
            "token_expires_in_minutes": payload.expires_in_minutes,
            "safety_notice": [
                "该命令只用于用户手动复制到真实测试 VPS 执行。",
                "本阶段不会自动 SSH。",
                "本阶段不会安装 Worker。",
                "不要把命令或 token 发到 README/docs/PR/chat/logs。",
            ],
        },
        "一次性 Worker 安装命令已生成。明文 token 只在本次响应的安装命令中出现，请立即复制并妥善保存。",
    )


@router.get("/{resource_id}/worker-acceptance")
def get_transit_resource_worker_acceptance(
    resource_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not require_admin_session(db, request):
        return auth_error()

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_NOT_SERVER", "只允许 server 类型中转资源执行 Worker 手动安装验收。")
    if resource.status not in TRANSIT_WORKER_ACCEPTANCE_RESOURCE_STATUSES:
        return error_response(
            400,
            "TRANSIT_RESOURCE_STATUS_NOT_ACCEPTABLE",
            "只允许 pending_worker / worker_online / worker_offline 中转资源执行 Worker 手动安装验收。",
        )

    worker = db.scalar(
        select(Worker)
        .where(Worker.server_id == resource.id)
        .order_by(Worker.last_heartbeat_at.desc().nullslast(), Worker.created_at.desc())
        .limit(1)
    )
    return success_response(
        serialize_transit_worker_acceptance(resource, worker),
        "Worker 手动安装与心跳验收状态已读取。",
    )


@router.get("/{resource_id}/worker-upgrade-acceptance")
def get_transit_resource_worker_upgrade_acceptance(
    resource_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not require_admin_session(db, request):
        return auth_error()

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_NOT_SERVER", "只允许 server 类型中转资源执行 Worker 升级验收。")

    worker = db.scalar(
        select(Worker)
        .where(Worker.server_id == resource.id)
        .order_by(Worker.last_heartbeat_at.desc().nullslast(), Worker.created_at.desc())
        .limit(1)
    )
    return success_response(
        serialize_transit_worker_upgrade_acceptance(resource, worker),
        "Transit Worker 升级验收状态已读取。",
    )


@router.get("/{resource_id}")
def get_transit_resource(
    resource_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not require_admin_session(db, request):
        return auth_error()

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")

    return success_response(serialize_transit_resource(resource), "ok")


@router.patch("/{resource_id}")
def update_transit_resource(
    resource_id: str,
    payload: TransitResourceUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")

    apply_payload(resource, payload.model_dump(exclude_unset=True))
    db.add(resource)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="update_transit_resource",
        result="success",
        request=request,
        resource_type="transit_resource",
        resource_id=resource.id,
    )
    db.commit()
    db.refresh(resource)

    return success_response(
        serialize_transit_resource(resource),
        "中转资源已更新。本阶段不会连接远端或配置中转。",
    )


@router.post("/{resource_id}/disable")
def disable_transit_resource(
    resource_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")

    resource.status = "disabled"
    db.add(resource)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="disable_transit_resource",
        result="success",
        request=request,
        resource_type="transit_resource",
        resource_id=resource.id,
    )
    db.commit()
    db.refresh(resource)

    return success_response(serialize_transit_resource(resource), "中转资源已禁用。")


@router.post("/{resource_id}/enable")
def enable_transit_resource(
    resource_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")

    resource.status = "active"
    db.add(resource)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="enable_transit_resource",
        result="success",
        request=request,
        resource_type="transit_resource",
        resource_id=resource.id,
    )
    db.commit()
    db.refresh(resource)

    return success_response(serialize_transit_resource(resource), "中转资源已启用。")


@router.delete("/{resource_id}")
def delete_transit_resource(
    resource_id: str,
    request: Request,
    confirm: bool = False,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()
    if confirm is not True:
        return error_response(400, "CONFIRMATION_REQUIRED", "请确认删除中转服务器记录。")

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")

    active_route = db.scalar(
        select(TransitRoute).where(
            TransitRoute.transit_resource_id == resource.id,
            TransitRoute.deleted_at.is_(None),
        )
    )
    if active_route:
        return error_response(
            409,
            "TRANSIT_RESOURCE_HAS_ACTIVE_ROUTES",
            "该中转服务器下仍有中转链路，请先删除链路记录。",
        )

    resource.deleted_at = datetime.now(UTC)
    resource.status = "deleted"
    db.add(resource)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="delete_transit_resource_record",
        result="success",
        request=request,
        resource_type="transit_resource",
        resource_id=resource.id,
    )
    db.commit()

    return success_response(
        {
            "id": resource.id,
            "deleted": True,
            "delete_mode": "soft_delete",
            "remote_action_performed": False,
            "message": "系统记录已删除；未执行远程清理。",
        },
        "系统记录已删除；未执行远程清理。",
    )


@router.post("/{resource_id}/remote-cleanup-delete")
def remote_cleanup_delete_transit_resource(
    resource_id: str,
    payload: RemoteCleanupDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")

    if payload.confirm == OFFLINE_LOCAL_REMOVE_CONFIRMATION:
        try:
            result = offline_local_remove_transit_resource(db, resource)
            record_audit(
                db,
                admin_id=session.admin_id,
                action="offline_local_remove_transit_resource",
                result="success",
                request=request,
                resource_type="transit_resource",
                resource_id=resource.id,
            )
            db.commit()
        except RemoteCleanupError as exc:
            db.rollback()
            return error_response(exc.status_code, exc.code, exc.message)
        return success_response(result, result["message"])

    try:
        command, worker = create_transit_resource_cleanup_command(db, resource)
        record_audit(
            db,
            admin_id=session.admin_id,
            action="create_cleanup_transit_resource_command",
            result="success",
            request=request,
            resource_type="transit_resource",
            resource_id=resource.id,
        )
        db.commit()
        db.refresh(command)
    except RemoteCleanupError as exc:
        db.rollback()
        if offer := remote_cleanup_unavailable_offer(exc):
            return error_response(
                400,
                "REMOTE_CLEANUP_UNAVAILABLE",
                "Worker 离线，无法远程清理。可使用离线本地移除确认。",
                offer,
            )
        return error_response(exc.status_code, exc.code, exc.message)

    return success_response(
        {
            "command_id": command.id,
            "cleanup_type": "cleanup_transit_resource",
            "status": "queued",
            "remote_cleanup_required": True,
            "system_record_delete_after_success": True,
            "command": serialize_worker_command(command, worker=worker),
            "message": "远程清理任务已创建，清理成功后将软删除系统记录。",
        },
        "远程清理任务已创建，清理成功后将软删除系统记录。",
    )
