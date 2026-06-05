import re
import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from rq import Queue
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.db.redis import get_rq_redis_client
from app.db.session import get_db
from app.models.node import Node
from app.models.task import Task
from app.models.vps_server import VpsServer
from app.schemas.common import error_response, success_response
from app.services.auth_service import record_audit
from app.services.credentials import store_temp_credential
from app.services.task_logging import add_task_log
from app.services.vps_validation import validate_public_ipv4, validate_ssh_port
from app.worker.jobs import (
    create_direct_node_job,
    delete_node_job,
    install_xray_job,
    latest_prepare_task,
    prepare_node_job,
    prepare_result_allows_install,
    read_node_job,
    refresh_node_job,
    restart_xray_job,
)

router = APIRouter()

DEFAULT_REALITY_DEST = "www.microsoft.com:443"
DEFAULT_REALITY_SERVER_NAME = "www.microsoft.com"
DEFAULT_DIRECT_FLOW = "xtls-rprx-vision"
HOSTNAME_RE = re.compile(r"^[A-Za-z0-9.-]+$")
DEST_RE = re.compile(r"^[A-Za-z0-9.-]+:[0-9]{1,5}$")
SHORT_ID_RE = re.compile(r"^[0-9a-fA-F]{2,16}$")
MUTATING_TASK_TYPES = (
    "prepare_node",
    "install_xray",
    "create_direct_node",
    "refresh_node",
    "restart_xray",
    "delete_node",
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


def validate_direct_node_params(
    *,
    node_name: str,
    listen_port: int,
    reality_dest: str,
    reality_server_name: str,
    reality_short_id: str | None,
    client_uuid: str | None,
    flow: str,
) -> tuple[dict | None, tuple[int, str, str] | None]:
    node_name = node_name.strip()
    reality_dest = reality_dest.strip()
    reality_server_name = reality_server_name.strip()
    flow = flow.strip()
    reality_short_id = reality_short_id.strip() if reality_short_id else None
    client_uuid = client_uuid.strip() if client_uuid else None

    if not node_name or len(node_name) > 120:
        return None, (400, "INVALID_NODE_NAME", "节点名称不能为空，且不能超过 120 个字符。")
    if listen_port < 1 or listen_port > 65535:
        return None, (400, "INVALID_PORT", "监听端口必须在 1-65535 之间。")
    if not DEST_RE.match(reality_dest):
        return None, (400, "INVALID_REALITY_DEST", "Reality dest 必须是 host:port 格式。")
    dest_port = int(reality_dest.rsplit(":", 1)[1])
    if dest_port < 1 or dest_port > 65535:
        return None, (400, "INVALID_REALITY_DEST", "Reality dest 端口不合法。")
    if not HOSTNAME_RE.match(reality_server_name):
        return None, (400, "INVALID_REALITY_SERVER_NAME", "Reality serverName 格式不合法。")
    if reality_short_id and not SHORT_ID_RE.match(reality_short_id):
        return None, (400, "INVALID_REALITY_SHORT_ID", "Reality shortId 必须是 2-16 位十六进制。")
    if client_uuid:
        try:
            client_uuid = str(uuid.UUID(client_uuid))
        except ValueError:
            return None, (400, "INVALID_CLIENT_UUID", "client_uuid 格式不合法。")
    if flow != DEFAULT_DIRECT_FLOW:
        return None, (400, "INVALID_FLOW", "Stage 2.3 仅支持 xtls-rprx-vision。")

    return (
        {
            "node_name": node_name,
            "listen_port": listen_port,
            "reality_dest": reality_dest,
            "reality_server_name": reality_server_name,
            "reality_short_id": reality_short_id,
            "client_uuid": client_uuid,
            "flow": flow,
        },
        None,
    )


def serialize_node(node: Node, *, include_share_link: bool = True) -> dict:
    vps = node.vps
    data = {
        "id": node.id,
        "vps_id": node.vps_id,
        "vps_ip": vps.ip if vps else None,
        "vps_status": vps.status if vps else None,
        "node_name": node.node_name,
        "protocol": node.protocol,
        "transport": node.transport,
        "security": node.security,
        "port": node.xray_port,
        "status": node.status,
        "service_status": node.service_status,
        "connectivity_status": node.connectivity_status,
        "uuid": node.uuid,
        "flow": node.flow,
        "reality_public_key": node.reality_public_key,
        "reality_short_id": node.reality_short_id,
        "reality_server_name": node.sni,
        "reality_dest": node.dest,
        "fingerprint": node.fingerprint,
        "source": node.source,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
        "last_remote_check_at": (
            node.last_remote_check_at.isoformat() if node.last_remote_check_at else None
        ),
        "last_sync_status": node.last_sync_status,
    }
    if include_share_link:
        data["share_link"] = node.share_link
    return data


def running_mutating_task(db: Session, *, vps_id: str, node_id: str | None = None) -> Task | None:
    conditions = [
        Task.vps_id == vps_id,
        Task.task_type.in_(MUTATING_TASK_TYPES),
        Task.status.in_(("pending", "running")),
    ]
    if node_id:
        conditions.append((Task.node_id == node_id) | (Task.node_id.is_(None)))
    return db.scalar(select(Task).where(*conditions))


@router.get("")
@router.get("/")
def list_nodes(request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    nodes = db.scalars(
        select(Node)
        .where(Node.deleted_at.is_(None))
        .order_by(Node.created_at.desc())
    ).all()
    return success_response({"nodes": [serialize_node(node, include_share_link=False) for node in nodes]}, "ok")


@router.post("/read")
async def read_node(
    request: Request,
    vps_ip: str = Form(...),
    ssh_port: int = Form(22),
    ssh_username: str = Form("root"),
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

    vps_ip = vps_ip.strip()
    ssh_username = ssh_username.strip()

    host_error = validate_public_ipv4(vps_ip)
    if host_error:
        return error_response(400, host_error, "VPS 地址格式不合法，只允许公网 IPv4。")

    port_error = validate_ssh_port(ssh_port)
    if port_error:
        return error_response(400, port_error, "SSH 端口不合法。")

    if ssh_username != "root":
        return error_response(400, "NO_ROOT_PERMISSION", "第 1 阶段只支持 root 用户。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    vps = db.scalar(
        select(VpsServer).where(
            VpsServer.ip == vps_ip,
            VpsServer.ssh_port == ssh_port,
            VpsServer.ssh_username == ssh_username,
        )
    )
    if not vps:
        vps = VpsServer(
            ip=vps_ip,
            ssh_port=ssh_port,
            ssh_username=ssh_username,
            status="unconfigured",
        )
        db.add(vps)
        db.flush()

    running_task = db.scalar(
        select(Task).where(
            Task.vps_id == vps.id,
            Task.task_type == "read_node",
            Task.status.in_(("pending", "running")),
        )
    )
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前 VPS 正在执行读取任务。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None
    task = Task(
        vps_id=vps.id,
        node_id=None,
        task_type="read_node",
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
        message="读取任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="read_node",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(read_node_job, task.id, vps.id, temp_credential_id)

    return success_response({"task_id": task.id, "vps_id": vps.id}, "读取任务已创建")


@router.post("/prepare")
async def prepare_node(
    request: Request,
    vps_id: str = Form(...),
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

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    running_task = db.scalar(
        select(Task).where(
            Task.vps_id == vps.id,
            Task.task_type.in_(MUTATING_TASK_TYPES),
            Task.status.in_(("pending", "running")),
        )
    )
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前 VPS 正在执行安装前检查、安装或创建节点任务。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None
    task = Task(
        vps_id=vps.id,
        node_id=None,
        task_type="prepare_node",
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
        message="安装前检查任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="prepare_node",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(prepare_node_job, task.id, vps.id, temp_credential_id)

    return success_response({"task_id": task.id, "vps_id": vps.id}, "安装前检查任务已创建")


@router.post("/install-xray")
async def install_xray(
    request: Request,
    vps_id: str = Form(...),
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
            Task.task_type.in_(MUTATING_TASK_TYPES),
            Task.status.in_(("pending", "running")),
        )
    )
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前 VPS 正在执行安装前检查、安装或创建节点任务。")

    prepare_task = latest_prepare_task(db, vps.id)
    allowed, error_code, error_message = prepare_result_allows_install(prepare_task, vps)
    if not allowed:
        return error_response(400, error_code, error_message)

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None
    task = Task(
        vps_id=vps.id,
        node_id=None,
        task_type="install_xray",
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
        message="Xray 安装任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="install_xray",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(install_xray_job, task.id, vps.id, temp_credential_id)

    return success_response({"task_id": task.id, "vps_id": vps.id}, "Xray 安装任务已创建")


@router.post("/create-direct")
async def create_direct_node(
    request: Request,
    vps_id: str = Form(...),
    node_name: str = Form(...),
    listen_port: int = Form(443),
    reality_dest: str = Form(DEFAULT_REALITY_DEST),
    reality_server_name: str = Form(DEFAULT_REALITY_SERVER_NAME),
    reality_short_id: str | None = Form(None),
    client_uuid: str | None = Form(None),
    flow: str = Form(DEFAULT_DIRECT_FLOW),
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
    if vps.status not in {"xray_installed_pending_config", "xray_installed"}:
        return error_response(400, "VPS_NOT_READY", "VPS 必须先完成 Xray 安装。")
    if not vps.xray_installed:
        return error_response(400, "XRAY_NOT_INSTALLED", "Xray 尚未安装。")

    params, params_error = validate_direct_node_params(
        node_name=node_name,
        listen_port=listen_port,
        reality_dest=reality_dest,
        reality_server_name=reality_server_name,
        reality_short_id=reality_short_id,
        client_uuid=client_uuid,
        flow=flow,
    )
    if params_error:
        return error_response(*params_error)
    assert params is not None

    active_node = db.scalar(
        select(Node).where(
            Node.vps_id == vps.id,
            Node.status == "active",
            Node.deleted_at.is_(None),
        )
    )
    if active_node:
        return error_response(409, "ACTIVE_NODE_EXISTS", "该 VPS 已存在 active 节点。")

    running_task = db.scalar(
        select(Task).where(
            Task.vps_id == vps.id,
            Task.task_type.in_(MUTATING_TASK_TYPES),
            Task.status.in_(("pending", "running")),
        )
    )
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前 VPS 正在执行安装前检查、安装或创建节点任务。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None
    task = Task(
        vps_id=vps.id,
        node_id=None,
        task_type="create_direct_node",
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
        message="直连 VLESS Reality 节点创建任务已创建，等待 Worker 执行。",
    )
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_direct_node",
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(create_direct_node_job, task.id, vps.id, temp_credential_id, params)

    return success_response({"task_id": task.id, "vps_id": vps.id}, "直连节点创建任务已创建")


@router.get("/{node_id}")
def get_node(node_id: str, request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    node = db.get(Node, node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "NODE_NOT_FOUND", "节点不存在。")

    return success_response(serialize_node(node), "ok")


def create_node_action_task(
    *,
    db: Session,
    request: Request,
    session_admin_id: str,
    node: Node,
    task_type: str,
    queued_message: str,
    action: str,
) -> Task:
    task = Task(
        vps_id=node.vps_id,
        node_id=node.id,
        task_type=task_type,
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
        message=queued_message,
    )
    record_audit(
        db,
        admin_id=session_admin_id,
        action=action,
        result="success",
        request=request,
        resource_type="task",
        resource_id=task.id,
    )
    return task


@router.post("/{node_id}/refresh")
async def refresh_node(
    node_id: str,
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

    node = db.get(Node, node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "NODE_NOT_FOUND", "节点不存在。")
    if not node.vps:
        return error_response(404, "VPS_NOT_FOUND", "节点所属 VPS 不存在。")

    running_task = running_mutating_task(db, vps_id=node.vps_id, node_id=node.id)
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前节点或 VPS 正在执行任务。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None
    task = create_node_action_task(
        db=db,
        request=request,
        session_admin_id=session.admin_id,
        node=node,
        task_type="refresh_node",
        queued_message="刷新节点状态任务已创建，等待 Worker 执行。",
        action="refresh_node",
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(refresh_node_job, task.id, node.id, temp_credential_id)

    return success_response({"task_id": task.id, "node_id": node.id}, "刷新节点状态任务已创建")


@router.post("/{node_id}/restart")
async def restart_xray(
    node_id: str,
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

    node = db.get(Node, node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "NODE_NOT_FOUND", "节点不存在。")
    if not node.vps:
        return error_response(404, "VPS_NOT_FOUND", "节点所属 VPS 不存在。")

    running_task = running_mutating_task(db, vps_id=node.vps_id, node_id=node.id)
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前节点或 VPS 正在执行任务。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None
    task = create_node_action_task(
        db=db,
        request=request,
        session_admin_id=session.admin_id,
        node=node,
        task_type="restart_xray",
        queued_message="重启 Xray 任务已创建，等待 Worker 执行。",
        action="restart_xray",
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(restart_xray_job, task.id, node.id, temp_credential_id)

    return success_response({"task_id": task.id, "node_id": node.id}, "重启 Xray 任务已创建")


@router.post("/{node_id}/delete")
async def delete_node(
    node_id: str,
    request: Request,
    confirm: bool = Form(False),
    confirm_node_name: str = Form(""),
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

    node = db.get(Node, node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "NODE_NOT_FOUND", "节点不存在。")
    if not node.vps:
        return error_response(404, "VPS_NOT_FOUND", "节点所属 VPS 不存在。")
    if node.status != "active":
        return error_response(400, "NODE_NOT_ACTIVE", "只能删除 active 节点。")
    if confirm is not True:
        return error_response(400, "CONFIRMATION_REQUIRED", "请确认删除操作。")
    if confirm_node_name.strip() != node.node_name:
        return error_response(400, "CONFIRM_NODE_NAME_MISMATCH", "确认节点名称不匹配。")

    running_task = running_mutating_task(db, vps_id=node.vps_id, node_id=node.id)
    if running_task:
        return error_response(409, "TASK_ALREADY_RUNNING", "当前节点或 VPS 正在执行任务。")

    private_key = await read_private_key_payload(private_key_text, private_key_file)
    if not private_key:
        return error_response(400, "SSH_AUTH_FAILED", "请上传或粘贴 SSH 私钥。")

    temp_credential_id = store_temp_credential(private_key, ssh_key_passphrase)
    private_key = ""
    ssh_key_passphrase = None
    task = create_node_action_task(
        db=db,
        request=request,
        session_admin_id=session.admin_id,
        node=node,
        task_type="delete_node",
        queued_message="节点软删除任务已创建，等待 Worker 执行。",
        action="delete_node",
    )
    db.commit()

    queue = Queue("default", connection=get_rq_redis_client())
    queue.enqueue(delete_node_job, task.id, node.id, temp_credential_id, {"confirm": True})

    return success_response({"task_id": task.id, "node_id": node.id}, "节点软删除任务已创建")
