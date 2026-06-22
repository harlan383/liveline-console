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
    worker_public_base_url,
    worker_public_url_error_response,
    worker_runtime_status,
    worker_summary_fields,
)
from app.services.worker_commands import serialize_worker_command

router = APIRouter()


class TransitWorkerBootstrapRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    ip: str = Field(min_length=1, max_length=45)
    expires_in_minutes: int = Field(default=60, ge=1, le=10_080)

    @field_validator("name", "ip")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value cannot be empty")
        return cleaned


class TransitWorkerBootstrapRegenerateRequest(BaseModel):
    expires_in_minutes: int = Field(default=60, ge=1, le=10_080)


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
    if resource.status != WORKER_PENDING_STATUS:
        return error_response(
            400,
            "TRANSIT_RESOURCE_NOT_PENDING_WORKER",
            "只允许 pending_worker 中转服务器生成 Worker 安装命令。",
        )
    if not resource.entry_host:
        return error_response(400, "TRANSIT_RESOURCE_ENTRY_HOST_REQUIRED", "生成安装命令前必须填写中转 VPS 公网 IP 或域名。")

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
            "该中转服务器已有在线 Worker，不允许生成新的安装命令。",
        )

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
