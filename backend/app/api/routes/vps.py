from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.db.redis import get_rq_redis_client
from app.db.session import get_db
from app.models.task import Task
from app.models.vps_server import VpsServer
from app.schemas.common import error_response, success_response
from app.schemas.read_node import ConfirmHostKeyRequest
from app.services.auth_service import record_audit
from app.services.credentials import store_temp_credential
from app.services.task_logging import add_task_log
from app.worker.jobs import (
    check_vps_ssh_job,
    delete_xray_backup_candidate_job,
    list_xray_backups_job,
    preview_xray_backup_cleanup_job,
)
from app.worker.ssh_xray_backups import is_valid_failed_backup_filename

router = APIRouter()

BACKUP_SCAN_BLOCKING_TASK_TYPES = (
    "check_vps_ssh",
    "prepare_node",
    "install_xray",
    "create_direct_node",
    "refresh_node",
    "restart_xray",
    "delete_node",
    "list_xray_backups",
    "preview_xray_backup_cleanup",
    "delete_xray_backup_candidate",
)

VPS_MANAGEMENT_TASK_TYPES = (
    "check_vps_ssh",
    "read_node",
    "prepare_node",
    "install_xray",
    "create_direct_node",
    "refresh_node",
    "restart_xray",
    "delete_node",
)

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


class VpsUpdateRequest(BaseModel):
    name: str | None = None
    ip: str | None = None
    ssh_port: int | None = None
    ssh_user: str | None = None
    notes: str | None = None


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


def serialize_vps(vps: VpsServer) -> dict:
    nodes = [
        serialize_vps_node(node, vps_ip=vps.ip)
        for node in sorted(
            vps.nodes,
            key=lambda item: item.created_at.isoformat() if item.created_at else "",
            reverse=True,
        )
        if node.deleted_at is None
    ]
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
        "created_at": vps.created_at.isoformat() if vps.created_at else None,
        "updated_at": vps.updated_at.isoformat() if vps.updated_at else None,
        "nodes": nodes,
    }


def find_running_vps_management_task(db: Session, vps_id: str) -> Task | None:
    return db.scalar(
        select(Task).where(
            Task.vps_id == vps_id,
            Task.task_type.in_(VPS_MANAGEMENT_TASK_TYPES),
            Task.status.in_(("pending", "running")),
        )
    )


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


def create_check_vps_ssh_task(
    *,
    db: Session,
    request: Request,
    admin_id: str,
    vps: VpsServer,
    temp_credential_id: str,
    action: str,
) -> Task:
    task = Task(
        vps_id=vps.id,
        node_id=None,
        task_type="check_vps_ssh",
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
        message="服务器 SSH 握手检测任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=admin_id,
        action=action,
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(check_vps_ssh_job, task.id, vps.id, temp_credential_id)
    return task


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
    return success_response({"servers": [serialize_vps(vps) for vps in servers]}, "ok")


@router.post("")
@router.post("/")
async def create_vps(
    request: Request,
    name: str | None = Form(None),
    ip: str = Form(...),
    ssh_port: int = Form(22),
    ssh_user: str = Form("root"),
    notes: str | None = Form(None),
    private_key_text: str | None = Form(None),
    private_key_passphrase: str | None = Form(None),
    ssh_key_passphrase: str | None = Form(None),
    private_key_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    payload, validation_error = validate_vps_payload(
        name=name,
        ip=ip,
        ssh_port=ssh_port,
        ssh_user=ssh_user,
        notes=notes,
    )
    if validation_error:
        return error_response(*validation_error)
    assert payload is not None

    existing = db.scalar(
        select(VpsServer).where(
            VpsServer.ip == payload["ip"],
            VpsServer.ssh_port == payload["ssh_port"],
            VpsServer.ssh_username == payload["ssh_user"],
            VpsServer.status != "deleted",
        )
    )
    if existing:
        return error_response(409, "VPS_ALREADY_EXISTS", "该服务器记录已存在，请编辑或重新检测。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    passphrase = private_key_passphrase if private_key_passphrase is not None else ssh_key_passphrase
    temp_credential_id = store_temp_credential(private_key, passphrase)
    private_key = ""
    passphrase = None
    ssh_key_passphrase = None

    vps = VpsServer(
        name=payload["name"],
        ip=payload["ip"],
        ssh_port=payload["ssh_port"],
        ssh_username=payload["ssh_user"],
        notes=payload["notes"],
        status="unconfigured",
        last_ssh_status="unchecked",
        last_ssh_error=None,
    )
    db.add(vps)
    db.flush()
    task = create_check_vps_ssh_task(
        db=db,
        request=request,
        admin_id=session.admin_id,
        vps=vps,
        temp_credential_id=temp_credential_id,
        action="create_vps",
    )
    db.commit()

    return success_response(
        {"task_id": task.id, "vps_id": vps.id, "server": serialize_vps(vps)},
        "服务器记录已保存，SSH 握手检测任务已创建。",
    )


@router.post("/{vps_id}/recheck")
async def recheck_vps_ssh(
    vps_id: str,
    request: Request,
    ssh_port: int | None = Form(None),
    ssh_user: str | None = Form(None),
    private_key_text: str | None = Form(None),
    private_key_passphrase: str | None = Form(None),
    ssh_key_passphrase: str | None = Form(None),
    private_key_file: UploadFile | None = File(None),
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

    next_port = ssh_port if ssh_port is not None else vps.ssh_port
    next_user = clean_optional_text(ssh_user, max_length=80) or vps.ssh_username
    payload, validation_error = validate_vps_payload(
        name=vps.name,
        ip=vps.ip,
        ssh_port=next_port,
        ssh_user=next_user,
        notes=vps.notes,
    )
    if validation_error:
        return error_response(*validation_error)
    assert payload is not None

    running_task = find_running_vps_management_task(db, vps.id)
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前服务器正在执行任务。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    if vps.ssh_port != payload["ssh_port"] or vps.ssh_username != payload["ssh_user"]:
        vps.ssh_port = payload["ssh_port"]
        vps.ssh_username = payload["ssh_user"]
        vps.last_ssh_status = "unchecked"
        vps.last_ssh_check_at = None
        vps.last_ssh_error = None
        db.add(vps)
        db.flush()

    passphrase = private_key_passphrase if private_key_passphrase is not None else ssh_key_passphrase
    temp_credential_id = store_temp_credential(private_key, passphrase)
    private_key = ""
    passphrase = None
    ssh_key_passphrase = None
    task = create_check_vps_ssh_task(
        db=db,
        request=request,
        admin_id=session.admin_id,
        vps=vps,
        temp_credential_id=temp_credential_id,
        action="recheck_vps_ssh",
    )
    db.commit()

    return success_response(
        {"task_id": task.id, "vps_id": vps.id, "server": serialize_vps(vps)},
        "服务器 SSH 重新检测任务已创建。",
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
        "服务器信息已更新。" if not connection_changed else "服务器信息已更新，请重新检测 SSH 连接。",
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

    running_task = find_running_vps_management_task(db, vps.id)
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前服务器正在执行任务。")

    from datetime import UTC, datetime

    deleted_at = datetime.now(UTC)
    affected_nodes = 0
    for node in vps.nodes:
        if node.deleted_at is None:
            node.status = "deleted"
            node.service_status = "unknown"
            node.connectivity_status = "unknown"
            node.last_sync_status = "server_record_deleted"
            node.deleted_at = deleted_at
            db.add(node)
            affected_nodes += 1

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
            "deleted_server_id": vps.id,
            "affected_nodes": affected_nodes,
            "system_record_only": True,
            "remote_cleanup_performed": False,
            "message": "仅删除本系统记录；未 SSH 登录远程服务器清理 Xray 或节点配置。",
        },
        "服务器系统记录已删除。",
    )


@router.post("/{vps_id}/confirm-host-key")
def confirm_host_key(
    vps_id: str,
    payload: ConfirmHostKeyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    vps = db.get(VpsServer, vps_id)
    if not vps:
        return error_response(404, "VPS_NOT_FOUND", "VPS 记录不存在。")

    vps.ssh_host_key_fingerprint = payload.ssh_host_key_fingerprint
    db.add(vps)
    db.commit()

    return success_response(
        {"vps_id": vps.id, "ssh_host_key_fingerprint": vps.ssh_host_key_fingerprint},
        "SSH Host Key 指纹已确认，请重新触发读取任务。",
    )


@router.post("/{vps_id}/xray-backups")
async def list_xray_backups(
    vps_id: str,
    request: Request,
    private_key_text: str | None = Form(None),
    ssh_key_passphrase: str | None = Form(None),
    private_key_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    vps = db.get(VpsServer, vps_id)
    if not vps:
        return error_response(404, "VPS_NOT_FOUND", "VPS 记录不存在。")

    running_task = db.scalar(
        select(Task).where(
            Task.vps_id == vps.id,
            Task.task_type.in_(BACKUP_SCAN_BLOCKING_TASK_TYPES),
            Task.status.in_(("pending", "running")),
        )
    )
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前 VPS 正在执行任务。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None

    task = Task(
        vps_id=vps.id,
        node_id=None,
        task_type="list_xray_backups",
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
        message="Xray 备份文件只读查看任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="list_xray_backups",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(list_xray_backups_job, task.id, vps.id, temp_credential_id)

    return success_response({"task_id": task.id, "vps_id": vps.id}, "Xray 备份文件查看任务已创建")


@router.post("/{vps_id}/xray-backups/cleanup-preview")
async def preview_xray_backup_cleanup(
    vps_id: str,
    request: Request,
    private_key_text: str | None = Form(None),
    ssh_key_passphrase: str | None = Form(None),
    private_key_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    vps = db.get(VpsServer, vps_id)
    if not vps:
        return error_response(404, "VPS_NOT_FOUND", "VPS 记录不存在。")

    running_task = db.scalar(
        select(Task).where(
            Task.vps_id == vps.id,
            Task.task_type.in_(BACKUP_SCAN_BLOCKING_TASK_TYPES),
            Task.status.in_(("pending", "running")),
        )
    )
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前 VPS 正在执行任务。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None

    task = Task(
        vps_id=vps.id,
        node_id=None,
        task_type="preview_xray_backup_cleanup",
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
        message="Xray 备份清理预览任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="preview_xray_backup_cleanup",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(preview_xray_backup_cleanup_job, task.id, vps.id, temp_credential_id)

    return success_response({"task_id": task.id, "vps_id": vps.id}, "Xray 备份清理预览任务已创建")


@router.post("/{vps_id}/xray-backups/delete-candidate")
async def delete_xray_backup_candidate(
    vps_id: str,
    request: Request,
    filename: str | None = Form(None),
    confirm: str | None = Form(None),
    confirm_filename: str | None = Form(None),
    private_key_text: str | None = Form(None),
    ssh_key_passphrase: str | None = Form(None),
    private_key_file: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    vps = db.get(VpsServer, vps_id)
    if not vps:
        return error_response(404, "VPS_NOT_FOUND", "VPS 记录不存在。")

    clean_filename = (filename or "").strip()
    if not clean_filename:
        return error_response(400, "VALIDATION_FAILED", "filename 不能为空。")
    if confirm != "true":
        return error_response(400, "VALIDATION_FAILED", "必须确认删除操作。")
    if confirm_filename != clean_filename:
        return error_response(400, "FILENAME_MISMATCH", "confirm_filename 与 filename 不一致。")
    if not is_valid_failed_backup_filename(clean_filename):
        return error_response(400, "INVALID_FILENAME", "仅允许删除 failed 类型候选文件。")

    running_task = db.scalar(
        select(Task).where(
            Task.vps_id == vps.id,
            Task.task_type.in_(BACKUP_SCAN_BLOCKING_TASK_TYPES),
            Task.status.in_(("pending", "running")),
        )
    )
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前 VPS 正在执行任务。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None

    task = Task(
        vps_id=vps.id,
        node_id=None,
        task_type="delete_xray_backup_candidate",
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
        message="failed 备份候选文件删除任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="delete_xray_backup_candidate",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(
        delete_xray_backup_candidate_job,
        task.id,
        vps.id,
        temp_credential_id,
        clean_filename,
        True,
        clean_filename,
    )

    return success_response(
        {"task_id": task.id, "vps_id": vps.id},
        "failed 备份候选文件删除任务已创建",
    )
