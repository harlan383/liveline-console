from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.db.session import get_db
from app.models.vps_server import VpsServer
from app.schemas.common import error_response, success_response
from app.schemas.landing_node_plan import LandingNodeCreateRequest, LandingNodePlanRequest
from app.schemas.remote_cleanup import RemoteCleanupDeleteRequest
from app.services.auth_service import record_audit
from app.services.landing_node_create import (
    APPROVED_FORMAL_LISTEN_PORT,
    LandingNodeCreateError,
    create_landing_node_create_command,
)
from app.services.landing_node_plan import build_landing_node_plan
from app.services.worker_binding import (
    WORKER_PENDING_STATUS,
    WorkerPublicUrlError,
    connection_mode_for_vps,
    create_bound_worker_token,
    latest_worker_for_server,
    latest_workers_by_server,
    serialize_worker_token_bootstrap,
    vps_display_status,
    worker_public_url_error_response,
    worker_summary_fields,
)
from app.services.worker_commands import serialize_worker_command
from app.services.remote_cleanup_delete import RemoteCleanupError, create_landing_server_cleanup_command

router = APIRouter()

SENSITIVE_NOTE_MARKERS = (
    "PRIVATE KEY",
    "BEGIN OPENSSH",
    "PASSWORD",
    "PASSWD",
    "PASSPHRASE",
    "TOKEN",
    "SESSION_SECRET",
    "VLESS://",
    "VMESS://",
    "SS://",
)


class VpsCreateRequest(BaseModel):
    name: str | None = None
    ip: str
    ssh_port: int = 22
    ssh_user: str = "root"
    notes: str | None = None


class VpsUpdateRequest(BaseModel):
    name: str | None = None
    ip: str | None = None
    ssh_port: int | None = None
    ssh_user: str | None = None
    notes: str | None = None


class VpsWorkerBootstrapRequest(BaseModel):
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


def clean_optional_text(value: str | None, *, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if max_length is not None and len(cleaned) > max_length:
        return cleaned[:max_length]
    return cleaned


def notes_has_sensitive_text(notes: str | None) -> bool:
    if not notes:
        return False
    upper = notes.upper()
    return any(marker in upper for marker in SENSITIVE_NOTE_MARKERS)


def serialize_vps_node(node, *, vps_ip: str) -> dict:
    return {
        "id": node.id,
        "name": node.node_name,
        "address": vps_ip,
        "ip": vps_ip,
        "port": node.xray_port,
        "protocol": f"{node.protocol.upper()} {node.security.capitalize()}".strip(),
        "status": node.status,
        "share_link_present": bool(node.share_link),
        "created_at": node.created_at.isoformat() if node.created_at else None,
    }


def serialize_vps(vps: VpsServer, *, worker=None) -> dict:
    nodes = [
        serialize_vps_node(node, vps_ip=vps.ip)
        for node in sorted(
            vps.nodes,
            key=lambda item: item.created_at.isoformat() if item.created_at else "",
            reverse=True,
        )
        if node.deleted_at is None
    ]
    worker_fields = worker_summary_fields(worker)
    return {
        "id": vps.id,
        "name": vps.name or vps.ip,
        "ip": vps.ip,
        "ssh_port": vps.ssh_port,
        "ssh_user": vps.ssh_username,
        "ssh_username": vps.ssh_username,
        "notes": vps.notes,
        "status": vps.status,
        "last_ssh_status": vps.last_ssh_status,
        "last_ssh_check_at": vps.last_ssh_check_at.isoformat() if vps.last_ssh_check_at else None,
        "last_ssh_error": vps.last_ssh_error,
        "connection_mode": connection_mode_for_vps(vps, worker),
        "display_status": vps_display_status(vps, worker),
        **worker_fields,
        "created_at": vps.created_at.isoformat() if vps.created_at else None,
        "updated_at": vps.updated_at.isoformat() if vps.updated_at else None,
        "nodes": nodes,
    }


def validate_vps_payload(
    *,
    name: str | None,
    ip: str | None,
    ssh_port: int | None,
    ssh_user: str | None,
    notes: str | None,
) -> tuple[dict | None, tuple[int, str, str] | None]:
    clean_name = clean_optional_text(name, max_length=120)
    clean_ip = clean_optional_text(ip)
    clean_user = clean_optional_text(ssh_user, max_length=80)
    clean_notes = clean_optional_text(notes)

    if not clean_ip:
        return None, (400, "INVALID_IP", "服务器 IP 不能为空。")

    from app.services.vps_validation import validate_public_ipv4, validate_ssh_port

    host_error = validate_public_ipv4(clean_ip)
    if host_error:
        return None, (400, host_error, "服务器 IP 格式不合法，只允许公网 IPv4。")
    port_error = validate_ssh_port(ssh_port or 0)
    if port_error:
        return None, (400, port_error, "SSH 端口不合法。")
    if not clean_user:
        return None, (400, "INVALID_SSH_USER", "SSH 用户名不能为空。")
    if notes_has_sensitive_text(clean_notes):
        return None, (400, "SENSITIVE_NOTES_REJECTED", "备注不能包含密码、私钥、token 或完整节点链接。")

    return (
        {
            "name": clean_name,
            "ip": clean_ip,
            "ssh_port": ssh_port,
            "ssh_user": clean_user,
            "notes": clean_notes,
        },
        None,
    )


@router.get("")
@router.get("/")
def list_vps(request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    servers = db.scalars(
        select(VpsServer)
        .options(selectinload(VpsServer.nodes))
        .where(VpsServer.status != "deleted")
        .order_by(VpsServer.created_at.desc())
    ).all()
    workers = latest_workers_by_server(db, role="landing", server_ids=[vps.id for vps in servers])
    return success_response(
        {"servers": [serialize_vps(vps, worker=workers.get(vps.id)) for vps in servers]},
        "ok",
    )


@router.post("")
@router.post("/")
def create_vps(
    payload: VpsCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    data, validation_error = validate_vps_payload(
        name=payload.name,
        ip=payload.ip,
        ssh_port=payload.ssh_port,
        ssh_user=payload.ssh_user,
        notes=payload.notes,
    )
    if validation_error:
        return error_response(*validation_error)
    assert data is not None

    existing = db.scalar(
        select(VpsServer).where(
            VpsServer.ip == data["ip"],
            VpsServer.status != "deleted",
        )
    )
    if existing:
        return error_response(409, "VPS_ALREADY_EXISTS", "该服务器记录已存在，请编辑现有记录。")

    vps = VpsServer(
        name=data["name"],
        ip=data["ip"],
        ssh_port=data["ssh_port"],
        ssh_username=data["ssh_user"],
        notes=data["notes"],
        status="unconfigured",
        last_ssh_status="unchecked",
        last_ssh_error=None,
    )
    db.add(vps)
    db.flush()
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_vps_record",
        result="success",
        request=request,
        resource_type="vps",
        resource_id=vps.id,
    )
    db.commit()
    db.refresh(vps)

    return success_response(
        {"server": serialize_vps(vps), "system_record_only": True},
        "服务器记录已保存；未执行 SSH 或远程检测。",
    )


@router.post("/worker-bootstrap")
def create_vps_worker_bootstrap(
    payload: VpsWorkerBootstrapRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    data, validation_error = validate_vps_payload(
        name=payload.name,
        ip=payload.ip,
        ssh_port=22,
        ssh_user="root",
        notes=None,
    )
    if validation_error:
        return error_response(*validation_error)
    assert data is not None

    existing = db.scalar(
        select(VpsServer).where(
            VpsServer.ip == data["ip"],
            VpsServer.status != "deleted",
        )
    )
    if existing:
        return error_response(409, "VPS_ALREADY_EXISTS", "该落地服务器记录已存在，请编辑现有记录或删除后重试。")

    try:
        vps = VpsServer(
            name=data["name"],
            ip=data["ip"],
            ssh_port=22,
            ssh_username="root",
            notes=None,
            status=WORKER_PENDING_STATUS,
            last_ssh_status="unchecked",
            last_ssh_error=None,
        )
        db.add(vps)
        db.flush()
        token, raw_token, install_command = create_bound_worker_token(
            db,
            role="landing",
            name=vps.name,
            server_id=vps.id,
            admin_id=session.admin_id,
            expires_in_minutes=payload.expires_in_minutes,
        )
        record_audit(
            db,
            admin_id=session.admin_id,
            action="create_vps_worker_bootstrap",
            result="success",
            request=request,
            resource_type="vps",
            resource_id=vps.id,
        )
        db.commit()
        db.refresh(vps)
        db.refresh(token)
    except WorkerPublicUrlError as exc:
        db.rollback()
        return worker_public_url_error_response(exc)

    return success_response(
        {
            "server": serialize_vps(vps),
            "token": serialize_worker_token_bootstrap(token, raw_token, install_command),
            "install_command": install_command,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        },
        "落地服务器记录已创建，Worker 安装命令已生成。",
    )


@router.post("/{vps_id}/landing-node-plan")
def create_landing_node_plan(
    vps_id: str,
    payload: LandingNodePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    vps = db.get(VpsServer, vps_id)
    if not vps or vps.status == "deleted":
        return error_response(404, "VPS_NOT_FOUND", "落地服务器记录不存在。")

    worker = latest_worker_for_server(db, role="landing", server_id=vps.id)
    plan = build_landing_node_plan(db=db, vps=vps, worker=worker, payload=payload)

    return success_response(plan, "落地节点创建 dry-run 计划已生成；未执行任何远程操作。")


@router.post("/{vps_id}/landing-node-create")
def create_landing_node(
    vps_id: str,
    payload: LandingNodeCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    vps = db.get(VpsServer, vps_id)
    if not vps or vps.status == "deleted":
        return error_response(404, "VPS_NOT_FOUND", "落地服务器记录不存在。")

    try:
        command, worker = create_landing_node_create_command(db=db, vps=vps, payload=payload)
    except LandingNodeCreateError as exc:
        return error_response(400, exc.code, exc.message)

    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_landing_node",
        result="success",
        request=request,
        resource_type="worker_command",
        resource_id=command.id,
    )
    db.commit()
    db.refresh(command)
    return success_response(
        {
            "command_id": command.id,
            "command": serialize_worker_command(command, include_payload=True, worker=worker),
            "target_worker_id": worker.id,
            "target_worker_version": worker.worker_version,
            "server_id": vps.id,
            "approved_port": APPROVED_FORMAL_LISTEN_PORT,
            "status": command.status,
            "next_action": "等待 liveline-worker 轮询执行 landing_node_create；真实链接不会写入命令结果或日志。",
            "safety_boundary": [
                "正式执行会先由 Worker 重新运行本机预检",
                "只有 Worker 成功安装 Xray、写入 LiveLine 管理配置、启动服务并验证 27939/TCP 监听后，backend 才写入 node.share_link",
                "真实 vless:// 链接不会写入 README、阶段文档、终端日志、Worker 日志或聊天记录",
                "失败回滚只允许清理本次新增内容",
            ],
        },
        "正式创建命令已创建；将由当前落地服务器绑定的 Worker 执行。",
    )


@router.patch("/{vps_id}")
def update_vps(
    vps_id: str,
    payload: VpsUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    vps = db.get(VpsServer, vps_id)
    if not vps or vps.status == "deleted":
        return error_response(404, "VPS_NOT_FOUND", "服务器记录不存在。")

    next_name = payload.name if payload.name is not None else vps.name
    next_ip = payload.ip if payload.ip is not None else vps.ip
    next_port = payload.ssh_port if payload.ssh_port is not None else vps.ssh_port
    next_user = payload.ssh_user if payload.ssh_user is not None else vps.ssh_username
    next_notes = payload.notes if payload.notes is not None else vps.notes
    data, validation_error = validate_vps_payload(
        name=next_name,
        ip=next_ip,
        ssh_port=next_port,
        ssh_user=next_user,
        notes=next_notes,
    )
    if validation_error:
        return error_response(*validation_error)
    assert data is not None

    connection_changed = (
        vps.ip != data["ip"]
        or vps.ssh_port != data["ssh_port"]
        or vps.ssh_username != data["ssh_user"]
    )
    vps.name = data["name"]
    vps.ip = data["ip"]
    vps.ssh_port = data["ssh_port"]
    vps.ssh_username = data["ssh_user"]
    vps.notes = data["notes"]
    if connection_changed:
        vps.last_ssh_status = "unchecked"
        vps.last_ssh_check_at = None
        vps.last_ssh_error = None
    db.add(vps)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="update_vps",
        result="success",
        request=request,
        resource_type="vps",
        resource_id=vps.id,
    )
    db.commit()
    db.refresh(vps)

    return success_response(
        {"server": serialize_vps(vps), "ssh_status_reset": connection_changed},
        "服务器信息已更新。" if not connection_changed else "服务器信息已更新；Worker 状态需由注册心跳刷新。",
    )


@router.delete("/{vps_id}")
def delete_vps(
    vps_id: str,
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
        return error_response(400, "CONFIRMATION_REQUIRED", "请确认删除服务器。")

    vps = db.get(VpsServer, vps_id)
    if not vps or vps.status == "deleted":
        return error_response(404, "VPS_NOT_FOUND", "服务器记录不存在。")

    active_nodes = [node for node in vps.nodes if node.deleted_at is None]
    if active_nodes:
        return error_response(
            409,
            "VPS_HAS_ACTIVE_NODES",
            "该落地服务器下仍有直连节点，请先删除节点记录。",
        )

    vps.status = "deleted"
    vps.last_ssh_status = "unchecked"
    vps.last_ssh_error = None
    db.add(vps)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="delete_vps",
        result="success",
        request=request,
        resource_type="vps",
        resource_id=vps.id,
    )
    db.commit()

    return success_response(
        {
            "id": vps.id,
            "deleted": True,
            "delete_mode": "soft_delete",
            "remote_action_performed": False,
            "message": "系统记录已删除；未执行远程清理。",
        },
        "系统记录已删除；未执行远程清理。",
    )


@router.post("/{vps_id}/remote-cleanup-delete")
def remote_cleanup_delete_vps(
    vps_id: str,
    payload: RemoteCleanupDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    vps = db.get(VpsServer, vps_id)
    if not vps or vps.status == "deleted":
        return error_response(404, "VPS_NOT_FOUND", "服务器记录不存在。")

    try:
        command, worker = create_landing_server_cleanup_command(db, vps)
        record_audit(
            db,
            admin_id=session.admin_id,
            action="create_cleanup_landing_server_command",
            result="success",
            request=request,
            resource_type="vps",
            resource_id=vps.id,
        )
        db.commit()
        db.refresh(command)
    except RemoteCleanupError as exc:
        db.rollback()
        return error_response(exc.status_code, exc.code, exc.message)

    return success_response(
        {
            "command_id": command.id,
            "cleanup_type": "cleanup_landing_server",
            "status": "queued",
            "remote_cleanup_required": True,
            "system_record_delete_after_success": True,
            "command": serialize_worker_command(command, worker=worker),
            "message": "远程清理任务已创建，清理成功后将软删除系统记录。",
        },
        "远程清理任务已创建，清理成功后将软删除系统记录。",
    )
