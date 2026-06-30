from datetime import UTC, datetime
from typing import Any

from redis import RedisError
from rq import Worker as RqWorker
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.redis import get_redis_client, get_rq_redis_client
from app.models.node import Node
from app.models.task import Task
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer
from app.services.redaction import redact_text
from app.services.worker_binding import latest_workers_by_server, worker_heartbeat_status

SAFETY_BOUNDARY = [
    "read-only overview aggregation",
    "no worker command created",
    "no remote execution",
    "no node or route mutation",
    "no share_link read or mutation",
    "no cutover",
]

FAILED_TASK_STATUSES = {"failed", "timeout", "error"}
RUNNING_TASK_STATUSES = {"pending", "running", "claimed"}
ABNORMAL_RESOURCE_STATUSES = {"failed", "failure", "error", "timeout"}
RISK_RESOURCE_STATUSES = {"creating", "deploying", "pending", "pending_worker", "worker_offline", "disabled", "unknown", "offline"}


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def aware_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def time_label(value: datetime | None, *, now: datetime) -> str:
    created_at = aware_datetime(value)
    if created_at is None:
        return "刚刚"
    if created_at > now:
        return "刚刚"
    if (now - created_at).total_seconds() < 300:
        return "刚刚"
    return created_at.strftime("%Y-%m-%d %H:%M")


def sort_timestamp(value: str | datetime | None) -> datetime:
    if isinstance(value, datetime):
        return aware_datetime(value) or datetime.min.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return aware_datetime(datetime.fromisoformat(value)) or datetime.min.replace(tzinfo=UTC)
        except ValueError:
            return datetime.min.replace(tzinfo=UTC)
    return datetime.min.replace(tzinfo=UTC)


def business_task_name(task_type: str | None) -> str:
    labels = {
        "landing_node_create": "创建直连节点",
        "transit_route_create": "创建中转线路",
        "cleanup_landing_node": "删除节点",
        "cleanup_landing_server": "清理落地服务器",
        "cleanup_transit_route": "清理中转线路",
        "cleanup_transit_resource": "清理中转服务器",
        "bbr_enable_dry_run": "网络加速试运行",
        "bbr_enable_real_execution": "启用网络加速",
        "landing_preflight": "创建前检查",
        "transit_readonly_preflight": "中转创建前检查",
        "collect_status": "读取服务器状态",
        "service_status": "读取服务状态",
    }
    return labels.get(task_type or "", "系统任务")


def _component(status: str, detail: str | None) -> dict[str, str | None]:
    return {"status": status, "detail": detail}


def build_health_summary(db: Session) -> dict[str, Any]:
    components = {
        "backend": _component("ok", "FastAPI is running"),
        "database": _component("unknown", None),
        "redis": _component("unknown", None),
        "worker": _component("unknown", None),
    }

    try:
        db.execute(text("select 1"))
        components["database"] = _component("ok", "PostgreSQL query succeeded")
    except SQLAlchemyError as exc:
        components["database"] = _component("error", exc.__class__.__name__)

    try:
        redis_client = get_redis_client()
        redis_client.ping()
        components["redis"] = _component("ok", "Redis ping succeeded")
        workers = RqWorker.all(connection=get_rq_redis_client())
        if workers:
            components["worker"] = _component("ok", f"{len(workers)} RQ worker(s) registered")
        else:
            components["worker"] = _component("missing", "No RQ worker registered")
    except RedisError as exc:
        components["redis"] = _component("error", exc.__class__.__name__)
        components["worker"] = _component("unknown", "Redis unavailable")

    ok = all(component["status"] == "ok" for component in components.values())
    danger = any(components[name]["status"] == "error" for name in ("backend", "database", "redis"))
    status = "ok" if ok else "danger" if danger else "warning"
    label = "系统运行正常" if ok else "系统需要关注" if status == "warning" else "系统组件异常"
    detail = "所有核心组件正常" if ok else "部分核心组件需要检查"

    return {
        "ok": ok,
        "status": status,
        "label": label,
        "detail": detail,
        "last_refreshed_label": "刚刚",
        "components": components,
    }


def _attention_item(
    *,
    item_id: str,
    summary: str,
    detail: str,
    tone: str,
    source_type: str,
    source_id: str | None = None,
    created_at: datetime | None = None,
    now: datetime,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "summary": summary,
        "detail": detail,
        "tone": tone,
        "source_type": source_type,
        "source_id": source_id,
        "created_at": iso_or_none(created_at),
        "time_label": time_label(created_at, now=now),
    }


def _recent_item(
    *,
    item_id: str,
    name: str,
    item_type: str,
    type_label: str,
    status: str,
    created_at: datetime | None,
) -> dict[str, Any]:
    return {
        "id": item_id,
        "name": name,
        "type": item_type,
        "type_label": type_label,
        "status": status,
        "created_at": iso_or_none(created_at),
        "created_by": "admin",
    }


def build_product_overview(db: Session) -> dict[str, Any]:
    now = datetime.now(UTC)
    health = build_health_summary(db)

    servers = db.scalars(
        select(VpsServer)
        .where(VpsServer.status != "deleted")
        .order_by(VpsServer.created_at.desc())
    ).all()
    nodes = db.scalars(
        select(Node)
        .where(Node.deleted_at.is_(None))
        .order_by(Node.created_at.desc())
    ).all()
    resources = db.scalars(
        select(TransitResource)
        .where(TransitResource.deleted_at.is_(None))
        .order_by(TransitResource.created_at.desc())
    ).all()
    routes = db.scalars(
        select(TransitRoute)
        .where(TransitRoute.deleted_at.is_(None))
        .order_by(TransitRoute.created_at.desc())
    ).all()
    tasks = db.scalars(select(Task).order_by(Task.created_at.desc()).limit(30)).all()

    landing_workers = latest_workers_by_server(db, role="landing", server_ids=[server.id for server in servers])
    transit_workers = latest_workers_by_server(db, role="transit", server_ids=[resource.id for resource in resources])

    active_nodes = [node for node in nodes if node.status == "active"]
    active_routes = [route for route in routes if route.status == "active"]
    failed_tasks = [task for task in tasks if task.status in FAILED_TASK_STATUSES]
    running_tasks = [task for task in tasks if task.status in RUNNING_TASK_STATUSES]

    stale_servers = [
        server
        for server in servers
        if worker_heartbeat_status(landing_workers.get(server.id)) == "stale"
    ]
    stale_resources = [
        resource
        for resource in resources
        if worker_heartbeat_status(transit_workers.get(resource.id)) == "stale"
    ]

    abnormal_nodes = [node for node in nodes if node.status in ABNORMAL_RESOURCE_STATUSES]
    abnormal_routes = [route for route in routes if route.status in ABNORMAL_RESOURCE_STATUSES]
    abnormal_resources = [resource for resource in resources if resource.status in ABNORMAL_RESOURCE_STATUSES]
    risk_nodes = [node for node in nodes if node.status != "active" and node.status not in ABNORMAL_RESOURCE_STATUSES]
    risk_routes = [route for route in routes if route.status != "active" and route.status not in ABNORMAL_RESOURCE_STATUSES]
    risk_resources = [
        resource
        for resource in resources
        if resource.status in RISK_RESOURCE_STATUSES and resource.status not in ABNORMAL_RESOURCE_STATUSES
    ]
    risk_servers = [
        server
        for server in servers
        if server.status in RISK_RESOURCE_STATUSES or server.last_ssh_status in {"offline", "unknown"}
    ]

    stats = {
        "normal_lines": len(active_nodes) + len(active_routes),
        "risk_lines": len(stale_servers) + len(stale_resources) + len(risk_nodes) + len(risk_routes) + len(risk_resources) + len(risk_servers),
        "abnormal_lines": len(failed_tasks) + len(abnormal_nodes) + len(abnormal_routes) + len(abnormal_resources),
        "pending_items": len(running_tasks)
        + (0 if servers else 1)
        + (0 if active_nodes else 1 if servers else 0)
        + (1 if any(resource.resource_type == "server" for resource in resources) and not active_routes else 0),
    }

    attention_items: list[dict[str, Any]] = []
    if health["status"] != "ok":
        attention_items.append(
            _attention_item(
                item_id="health-status",
                summary=health["label"],
                detail=health["detail"],
                tone="danger" if health["status"] == "danger" else "warning",
                source_type="health",
                now=now,
            )
        )

    for task in failed_tasks[:2]:
        safe_error = redact_text(task.error_message) if task.error_message else None
        attention_items.append(
            _attention_item(
                item_id=f"task-{task.id}",
                summary=f"{business_task_name(task.task_type)}失败，请到任务记录查看处理建议。",
                detail=safe_error or task.error_code or "最近任务执行失败。",
                tone="danger",
                source_type="task",
                source_id=task.id,
                created_at=task.finished_at or task.updated_at or task.created_at,
                now=now,
            )
        )

    if stale_servers:
        server = stale_servers[0]
        attention_items.append(
            _attention_item(
                item_id=f"stale-vps-{server.id}",
                summary=f"{server.name or server.ip}：服务器助手心跳过期，建议检查助手状态。",
                detail="主控暂未收到该落地服务器的近期 heartbeat。",
                tone="warning",
                source_type="vps",
                source_id=server.id,
                created_at=server.updated_at or server.created_at,
                now=now,
            )
        )

    if stale_resources:
        resource = stale_resources[0]
        attention_items.append(
            _attention_item(
                item_id=f"stale-transit-resource-{resource.id}",
                summary=f"{resource.name}：中转助手心跳过期，建议检查助手状态。",
                detail="主控暂未收到该中转服务器的近期 heartbeat。",
                tone="warning",
                source_type="transit_resource",
                source_id=resource.id,
                created_at=resource.updated_at or resource.created_at,
                now=now,
            )
        )

    if abnormal_nodes:
        node = abnormal_nodes[0]
        attention_items.append(
            _attention_item(
                item_id=f"node-{node.id}",
                summary=f"{node.node_name}：直连节点状态异常。",
                detail=f"当前状态：{node.status}",
                tone="danger",
                source_type="node",
                source_id=node.id,
                created_at=node.updated_at or node.created_at,
                now=now,
            )
        )

    if abnormal_routes:
        route = abnormal_routes[0]
        attention_items.append(
            _attention_item(
                item_id=f"route-{route.id}",
                summary=f"{route.name}：中转线路状态异常。",
                detail=f"当前状态：{route.status}",
                tone="danger",
                source_type="transit_route",
                source_id=route.id,
                created_at=route.updated_at or route.created_at,
                now=now,
            )
        )

    if not servers:
        attention_items.append(
            _attention_item(
                item_id="no-landing-server",
                summary="暂无落地服务器，请先添加落地服务器。",
                detail="落地服务器是创建直连节点和中转目标的基础资源。",
                tone="info",
                source_type="system",
                now=now,
            )
        )
    elif not active_nodes:
        attention_items.append(
            _attention_item(
                item_id="no-active-node",
                summary="已有落地服务器，但还没有可用直连节点。",
                detail="可以在“线路搭建”中继续规划直连节点。",
                tone="info",
                source_type="node",
                now=now,
            )
        )

    has_transit_server = any(resource.resource_type == "server" for resource in resources)
    if not has_transit_server and not active_routes:
        attention_items.append(
            _attention_item(
                item_id="no-transit-server",
                summary="如需直播主线，可以继续添加中转服务器。",
                detail="中转服务器用于在客户入口和落地节点之间转发流量。",
                tone="info",
                source_type="transit_resource",
                now=now,
            )
        )

    if not attention_items:
        attention_items.append(
            _attention_item(
                item_id="overview-ok",
                summary="当前线路整体正常，没有需要立即处理的问题。",
                detail="建议定期查看任务记录和客户线路状态。",
                tone="success",
                source_type="system",
                now=now,
            )
        )

    recent_created = [
        *[
            _recent_item(
                item_id=server.id,
                name=server.name or server.ip,
                item_type="landing_server",
                type_label="落地服务器",
                status=server.status,
                created_at=server.created_at,
            )
            for server in servers
        ],
        *[
            _recent_item(
                item_id=node.id,
                name=node.node_name,
                item_type="direct_node",
                type_label="直连节点",
                status=node.status,
                created_at=node.created_at,
            )
            for node in nodes
        ],
        *[
            _recent_item(
                item_id=resource.id,
                name=resource.name,
                item_type="transit_resource",
                type_label="中转服务器" if resource.resource_type == "server" else "商家中转入口",
                status=resource.status,
                created_at=resource.created_at,
            )
            for resource in resources
        ],
        *[
            _recent_item(
                item_id=route.id,
                name=route.name,
                item_type="transit_route",
                type_label="中转线路",
                status=route.status,
                created_at=route.created_at,
            )
            for route in routes
        ],
    ]
    recent_created.sort(key=lambda item: sort_timestamp(item.get("created_at")), reverse=True)

    tips = [
        "通过“线路搭建”快速规划直连或中转线路。",
        "新增或变更客户连接端口后，请务必同步检查云服务器安全组、云防火墙、服务器防火墙是否放行。",
        "遇到问题时，先查看“任务记录”获取检测结果。",
    ]
    if servers and not active_nodes:
        tips.append("你已接入落地服务器，可以继续创建第一条直连节点。")
    if active_nodes and not active_routes:
        tips.append("已有直连节点，如需主线加速可继续规划中转线路。")

    return {
        "generated_at": now.isoformat(),
        "health": health,
        "stats": stats,
        "attention_items": attention_items[:6],
        "recent_created": recent_created[:5],
        "tips": tips,
        "safety_boundary": SAFETY_BOUNDARY,
    }
