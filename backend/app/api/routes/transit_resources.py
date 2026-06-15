from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import BaseModel, Field, field_validator
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.db.redis import get_rq_redis_client
from app.db.session import get_db
from app.models.task import Task
from app.models.transit_resource import TransitResource
from app.schemas.common import error_response, success_response
from app.schemas.transit_resource import (
    PROTOCOL_HINTS,
    RESOURCE_STATUSES,
    RESOURCE_TYPES,
    TransitResourceCreate,
    TransitResourceUpdate,
)
from app.services.auth_service import record_audit
from app.services.credentials import store_temp_credential
from app.services.task_logging import add_task_log
from app.services.worker_binding import (
    WORKER_PENDING_STATUS,
    WorkerPublicUrlError,
    connection_mode_for_transit,
    create_bound_worker_token,
    latest_workers_by_server,
    serialize_worker_token_bootstrap,
    transit_display_status,
    worker_public_url_error_response,
    worker_summary_fields,
)
from app.worker.jobs import install_gost_job, install_socat_job, read_transit_server_job

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


@router.post("/{resource_id}/read-server")
async def read_transit_server(
    resource_id: str,
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

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_NOT_SERVER", "只允许读取 server 类型中转资源。")
    if resource.status != "active":
        return error_response(400, "TRANSIT_RESOURCE_NOT_ACTIVE", "只允许读取 active 中转资源。")
    if not resource.has_ssh:
        return error_response(400, "TRANSIT_RESOURCE_SSH_REQUIRED", "该中转资源未启用 SSH 元数据。")
    if not resource.ssh_host or not resource.ssh_port or not resource.ssh_username:
        return error_response(400, "TRANSIT_SSH_METADATA_MISSING", "中转资源缺少 SSH 元数据。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None

    task = Task(
        vps_id=None,
        node_id=None,
        task_type="read_transit_server",
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
        message="中转服务器只读检查任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="read_transit_server",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(read_transit_server_job, task.id, resource.id, temp_credential_id)

    return success_response(
        {"task_id": task.id, "transit_resource_id": resource.id},
        "中转服务器只读检查任务已创建",
    )


@router.post("/{resource_id}/install-gost")
async def install_gost(
    resource_id: str,
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

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_NOT_SERVER", "只允许给 server 类型中转资源安装 gost。")
    if resource.status != "active":
        return error_response(400, "TRANSIT_RESOURCE_NOT_ACTIVE", "只允许给 active 中转资源安装 gost。")
    if not resource.has_ssh:
        return error_response(400, "TRANSIT_RESOURCE_SSH_REQUIRED", "该中转资源未启用 SSH 元数据。")
    if not resource.ssh_host or not resource.ssh_port or not resource.ssh_username:
        return error_response(400, "TRANSIT_SSH_METADATA_MISSING", "中转资源缺少 SSH 元数据。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None

    task = Task(
        vps_id=None,
        node_id=None,
        task_type="install_gost",
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
        message="gost binary 安装任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="install_gost",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(install_gost_job, task.id, resource.id, temp_credential_id)

    return success_response(
        {"task_id": task.id, "transit_resource_id": resource.id},
        "gost binary 安装任务已创建",
    )


@router.post("/{resource_id}/install-socat")
async def install_socat(
    resource_id: str,
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

    resource = get_transit_resource_or_error(db, resource_id)
    if not resource:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_NOT_SERVER", "只允许给 server 类型中转资源安装 socat。")
    if resource.status != "active":
        return error_response(400, "TRANSIT_RESOURCE_NOT_ACTIVE", "只允许给 active 中转资源安装 socat。")
    if not resource.has_ssh:
        return error_response(400, "TRANSIT_RESOURCE_SSH_REQUIRED", "该中转资源未启用 SSH 元数据。")
    if not resource.ssh_host or not resource.ssh_port or not resource.ssh_username:
        return error_response(400, "TRANSIT_SSH_METADATA_MISSING", "中转资源缺少 SSH 元数据。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None

    task = Task(
        vps_id=None,
        node_id=None,
        task_type="install_socat",
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
        message="socat 安装/检查任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="install_socat",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(install_socat_job, task.id, resource.id, temp_credential_id)

    return success_response(
        {"task_id": task.id, "transit_resource_id": resource.id},
        "socat 安装/检查任务已创建",
    )


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
