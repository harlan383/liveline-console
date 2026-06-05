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
from app.schemas.transit_route import SSH_RESERVED_PORT, SOCAT_RESERVED_PORTS, TransitRouteCreateFields
from app.services.auth_service import record_audit
from app.services.credentials import store_temp_credential
from app.services.task_logging import add_task_log
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

    if fields.forwarding_method == "gost" and fields.listen_port == SSH_RESERVED_PORT:
        return error_response(400, "TRANSIT_PORT_RESERVED", "20575 是 SSH 端口，不能作为中转监听端口。")
    if fields.forwarding_method == "socat" and fields.listen_port in SOCAT_RESERVED_PORTS:
        return error_response(
            400,
            "SOCAT_PORT_RESERVED",
            "socat 测试转发禁止使用 22、8443、20575 作为监听端口。",
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
