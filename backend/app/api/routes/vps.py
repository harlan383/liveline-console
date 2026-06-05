from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

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
    delete_xray_backup_candidate_job,
    list_xray_backups_job,
    preview_xray_backup_cleanup_job,
)
from app.worker.ssh_xray_backups import is_valid_failed_backup_filename

router = APIRouter()

BACKUP_SCAN_BLOCKING_TASK_TYPES = (
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
