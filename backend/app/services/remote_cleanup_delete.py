from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer
from app.models.worker import Worker, WorkerToken
from app.models.worker_command import WorkerCommand
from app.services.landing_node_create import (
    MANAGED_XRAY_CONFIG_PATH,
    MANAGED_XRAY_SERVICE_NAME,
    MANAGED_XRAY_SERVICE_PATH,
)
from app.services.worker_commands import create_worker_command, normalize_worker_command_result
from app.services.worker_targeting import WorkerTargetError, resolve_command_target_worker

CLEANUP_LANDING_NODE_COMMAND = "cleanup_landing_node"
CLEANUP_LANDING_SERVER_COMMAND = "cleanup_landing_server"
CLEANUP_TRANSIT_ROUTE_COMMAND = "cleanup_transit_route"
CLEANUP_TRANSIT_RESOURCE_COMMAND = "cleanup_transit_resource"
REMOTE_CLEANUP_COMMAND_TYPES = {
    CLEANUP_LANDING_NODE_COMMAND,
    CLEANUP_LANDING_SERVER_COMMAND,
    CLEANUP_TRANSIT_ROUTE_COMMAND,
    CLEANUP_TRANSIT_RESOURCE_COMMAND,
}
REMOTE_CLEANUP_RUNNING_STATUSES = ("pending", "claimed", "running")

REMOTE_CLEANUP_STAGE = "Stage 3.3.97-protected-remote-cleanup-delete-flow"
REMOTE_CLEANUP_CONFIRMATION = "CONFIRM_REMOTE_DELETE"
DEFAULT_WORKER_SERVICE_NAME = "liveline-worker.service"
DEFAULT_WORKER_SERVICE_PATH = "/etc/systemd/system/liveline-worker.service"
DEFAULT_WORKER_BINARY_PATH = "/usr/local/bin/liveline-worker"
DEFAULT_WORKER_CONFIG_PATH = "/etc/liveline-worker/config.yaml"
DEFAULT_WORKER_CONFIG_DIR = "/etc/liveline-worker"
REMOTE_CLEANUP_BOUNDARY = [
    "protected remote cleanup only",
    "fixed Worker allowlist only",
    "no arbitrary shell accepted from API",
    "no cloud firewall or security group mutation",
    "no nodes.share_link read or modification",
    "no full client link export",
    "no cutover",
    "system records are soft-deleted only after Worker success",
]


class RemoteCleanupError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def command_is_remote_cleanup(command_type: str | None) -> bool:
    return command_type in REMOTE_CLEANUP_COMMAND_TYPES


def _now() -> datetime:
    return datetime.now(UTC)


def _active_remote_cleanup_exists(db: Session, *, server_id: str | None) -> bool:
    if not server_id:
        return False
    return (
        db.scalar(
            select(WorkerCommand.id)
            .where(WorkerCommand.server_id == server_id)
            .where(WorkerCommand.command_type.in_(REMOTE_CLEANUP_COMMAND_TYPES))
            .where(WorkerCommand.status.in_(REMOTE_CLEANUP_RUNNING_STATUSES))
            .limit(1)
        )
        is not None
    )


def _node_xray_cleanup_plan(node: Node) -> dict[str, Any]:
    if not node.xray_port:
        raise RemoteCleanupError("NODE_XRAY_PORT_MISSING", "节点缺少 Xray 监听端口，不能创建远程清理任务。")
    service_candidates = [
        f"liveline-xray-{node.xray_port}.service",
        f"liveline-xray-{node.id.replace('-', '')[:12]}.service",
        MANAGED_XRAY_SERVICE_NAME,
    ]
    return {
        "node_id": node.id,
        "node_name": node.node_name,
        "vps_id": node.vps_id,
        "xray_port": node.xray_port,
        "service_candidates": service_candidates,
        "legacy_service_name": MANAGED_XRAY_SERVICE_NAME,
        "legacy_service_path": MANAGED_XRAY_SERVICE_PATH,
        "managed_config_path": MANAGED_XRAY_CONFIG_PATH,
        "delete_config_if_liveline_verified": True,
        "delete_binary": False,
    }


def _route_socat_cleanup_plan(route: TransitRoute) -> dict[str, Any]:
    if route.forwarding_method != "socat":
        raise RemoteCleanupError("TRANSIT_ROUTE_METHOD_UNSUPPORTED", "本阶段只允许清理 socat 中转链路。")
    if not route.listen_port:
        raise RemoteCleanupError("TRANSIT_ROUTE_LISTEN_PORT_MISSING", "中转链路缺少监听端口，不能创建远程清理任务。")
    expected_name = f"liveline-socat-{route.listen_port}.service"
    expected_path = f"/etc/systemd/system/{expected_name}"
    if route.service_name != expected_name or route.service_path != expected_path:
        raise RemoteCleanupError(
            "TRANSIT_ROUTE_SERVICE_NOT_LIVELINE",
            "中转链路 service 不符合 LiveLine socat 命名，不能自动远程清理。",
        )
    return {
        "route_id": route.id,
        "route_name": route.name,
        "transit_resource_id": route.transit_resource_id,
        "listen_port": route.listen_port,
        "target_host": route.target_host,
        "target_port": route.target_port,
        "forwarding_method": route.forwarding_method,
        "service_name": route.service_name,
        "service_path": route.service_path,
    }


def _worker_self_cleanup_plan(worker: Worker) -> dict[str, Any]:
    return {
        "worker_id": worker.id,
        "role": worker.role,
        "service_candidates": [
            DEFAULT_WORKER_SERVICE_NAME,
            f"liveline-worker-{worker.role}.service",
            f"liveline-worker-{worker.id.replace('-', '')[:12]}.service",
        ],
        "default_service_name": DEFAULT_WORKER_SERVICE_NAME,
        "default_service_path": DEFAULT_WORKER_SERVICE_PATH,
        "default_binary_path": DEFAULT_WORKER_BINARY_PATH,
        "default_config_path": DEFAULT_WORKER_CONFIG_PATH,
        "default_config_dir": DEFAULT_WORKER_CONFIG_DIR,
        "delete_binary_if_liveline_verified": True,
        "delete_config_if_liveline_verified": True,
        "delay_seconds": 5,
    }


def _cleanup_command_payload(
    *,
    cleanup_type: str,
    target_id: str,
    plans: list[dict[str, Any]],
    cleanup_worker: bool = False,
    worker_cleanup: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "stage": REMOTE_CLEANUP_STAGE,
        "cleanup_type": cleanup_type,
        "target_id": target_id,
        "plans": plans,
        "cleanup_worker": cleanup_worker,
        "worker_cleanup": worker_cleanup,
        "remote_cleanup_required": True,
        "system_record_delete_after_success": True,
        "confirmation": REMOTE_CLEANUP_CONFIRMATION,
        "safety_boundary": REMOTE_CLEANUP_BOUNDARY,
    }
    return payload


def _resolve_worker(
    db: Session,
    *,
    server_type: str,
    server_id: str,
    command_type: str,
) -> Worker:
    try:
        return resolve_command_target_worker(
            db,
            server_type=server_type,
            server_id=server_id,
            role=server_type,
            command_type=command_type,
        ).worker
    except WorkerTargetError as exc:
        raise RemoteCleanupError(exc.code, exc.message, 400) from exc


def create_landing_node_cleanup_command(db: Session, node: Node) -> tuple[WorkerCommand, Worker]:
    if node.deleted_at is not None:
        raise RemoteCleanupError("NODE_NOT_FOUND", "节点不存在。", 404)
    worker = _resolve_worker(
        db,
        server_type="landing",
        server_id=node.vps_id,
        command_type=CLEANUP_LANDING_NODE_COMMAND,
    )
    if _active_remote_cleanup_exists(db, server_id=node.vps_id):
        raise RemoteCleanupError("REMOTE_CLEANUP_COMMAND_IN_FLIGHT", "当前已有该服务器的远程清理任务在执行。", 409)
    payload = _cleanup_command_payload(
        cleanup_type=CLEANUP_LANDING_NODE_COMMAND,
        target_id=node.id,
        plans=[_node_xray_cleanup_plan(node)],
    )
    command = create_worker_command(db, worker, CLEANUP_LANDING_NODE_COMMAND, payload)
    return command, worker


def create_landing_server_cleanup_command(db: Session, vps: VpsServer) -> tuple[WorkerCommand, Worker]:
    if vps.status == "deleted":
        raise RemoteCleanupError("VPS_NOT_FOUND", "落地服务器记录不存在。", 404)
    worker = _resolve_worker(
        db,
        server_type="landing",
        server_id=vps.id,
        command_type=CLEANUP_LANDING_SERVER_COMMAND,
    )
    if _active_remote_cleanup_exists(db, server_id=vps.id):
        raise RemoteCleanupError("REMOTE_CLEANUP_COMMAND_IN_FLIGHT", "当前已有该服务器的远程清理任务在执行。", 409)
    nodes = db.scalars(
        select(Node)
        .where(Node.vps_id == vps.id)
        .where(Node.deleted_at.is_(None))
        .order_by(Node.created_at.asc())
    ).all()
    plans = [_node_xray_cleanup_plan(node) for node in nodes]
    payload = _cleanup_command_payload(
        cleanup_type=CLEANUP_LANDING_SERVER_COMMAND,
        target_id=vps.id,
        plans=plans,
        cleanup_worker=True,
        worker_cleanup=_worker_self_cleanup_plan(worker),
    )
    command = create_worker_command(db, worker, CLEANUP_LANDING_SERVER_COMMAND, payload)
    worker.status = "cleanup_pending"
    db.add(worker)
    return command, worker


def create_transit_route_cleanup_command(db: Session, route: TransitRoute) -> tuple[WorkerCommand, Worker]:
    if route.deleted_at is not None:
        raise RemoteCleanupError("TRANSIT_ROUTE_NOT_FOUND", "中转链路不存在。", 404)
    if route.share_link:
        raise RemoteCleanupError("TRANSIT_ROUTE_CUTOVER_BLOCKED", "该中转链路处于 cutover 状态，本阶段不允许删除。", 409)
    worker = _resolve_worker(
        db,
        server_type="transit",
        server_id=route.transit_resource_id,
        command_type=CLEANUP_TRANSIT_ROUTE_COMMAND,
    )
    if _active_remote_cleanup_exists(db, server_id=route.transit_resource_id):
        raise RemoteCleanupError("REMOTE_CLEANUP_COMMAND_IN_FLIGHT", "当前已有该服务器的远程清理任务在执行。", 409)
    payload = _cleanup_command_payload(
        cleanup_type=CLEANUP_TRANSIT_ROUTE_COMMAND,
        target_id=route.id,
        plans=[_route_socat_cleanup_plan(route)],
    )
    command = create_worker_command(db, worker, CLEANUP_TRANSIT_ROUTE_COMMAND, payload)
    return command, worker


def create_transit_resource_cleanup_command(db: Session, resource: TransitResource) -> tuple[WorkerCommand, Worker]:
    if resource.deleted_at is not None:
        raise RemoteCleanupError("TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。", 404)
    if resource.resource_type != "server":
        raise RemoteCleanupError("TRANSIT_RESOURCE_NOT_SERVER", "只允许 server 类型中转资源执行远程清理。")
    worker = _resolve_worker(
        db,
        server_type="transit",
        server_id=resource.id,
        command_type=CLEANUP_TRANSIT_RESOURCE_COMMAND,
    )
    if _active_remote_cleanup_exists(db, server_id=resource.id):
        raise RemoteCleanupError("REMOTE_CLEANUP_COMMAND_IN_FLIGHT", "当前已有该服务器的远程清理任务在执行。", 409)
    routes = db.scalars(
        select(TransitRoute)
        .where(TransitRoute.transit_resource_id == resource.id)
        .where(TransitRoute.deleted_at.is_(None))
        .order_by(TransitRoute.created_at.asc())
    ).all()
    plans = [_route_socat_cleanup_plan(route) for route in routes]
    payload = _cleanup_command_payload(
        cleanup_type=CLEANUP_TRANSIT_RESOURCE_COMMAND,
        target_id=resource.id,
        plans=plans,
        cleanup_worker=True,
        worker_cleanup=_worker_self_cleanup_plan(worker),
    )
    command = create_worker_command(db, worker, CLEANUP_TRANSIT_RESOURCE_COMMAND, payload)
    worker.status = "cleanup_pending"
    db.add(worker)
    return command, worker


def _mark_node_deleted(node: Node) -> None:
    node.status = "deleted"
    node.service_status = "unknown"
    node.connectivity_status = "unknown"
    node.last_sync_status = "remote_cleanup_completed"
    node.deleted_at = node.deleted_at or _now()


def _mark_route_deleted(route: TransitRoute) -> None:
    route.status = "deleted"
    route.deleted_at = route.deleted_at or _now()


def _mark_worker_deleted(db: Session, worker: Worker) -> None:
    worker.status = "deleted"
    metadata = dict(worker.metadata_json or {})
    metadata["cleanup_status"] = "cleanup_expected_offline"
    metadata["cleanup_completed_at"] = _now().isoformat()
    worker.metadata_json = metadata
    db.add(worker)
    tokens = db.scalars(
        select(WorkerToken).where(
            WorkerToken.server_id == worker.server_id,
            WorkerToken.role == worker.role,
            WorkerToken.status == "active",
        )
    ).all()
    for token in tokens:
        token.status = "expired"
        db.add(token)


def _assert_cleanup_success(command: WorkerCommand, result: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(result, dict):
        raise RemoteCleanupError("INVALID_WORKER_RESULT", "Worker 返回结果格式不合法。")
    normalized = normalize_worker_command_result(command.command_type, result)
    if normalized.get("status") != "succeeded":
        raise RemoteCleanupError("REMOTE_CLEANUP_FAILED", "远程清理未返回成功状态。")
    if normalized.get("cleanup_type") != command.command_type:
        raise RemoteCleanupError("REMOTE_CLEANUP_TYPE_MISMATCH", "远程清理结果类型与命令不一致。")
    return normalized


def persist_successful_remote_cleanup_result(
    *,
    db: Session,
    command: WorkerCommand,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    if not command_is_remote_cleanup(command.command_type):
        return result or {}
    normalized = _assert_cleanup_success(command, result)
    payload = command.payload_json or {}
    target_id = str(payload.get("target_id") or "")

    if command.command_type == CLEANUP_LANDING_NODE_COMMAND:
        node = db.get(Node, target_id)
        if not node or node.deleted_at is not None:
            raise RemoteCleanupError("NODE_NOT_FOUND", "节点不存在。", 404)
        _mark_node_deleted(node)
        db.add(node)
        normalized["system_record_deleted"] = True
        normalized["deleted_node_ids"] = [node.id]
    elif command.command_type == CLEANUP_LANDING_SERVER_COMMAND:
        vps = db.get(VpsServer, target_id)
        if not vps or vps.status == "deleted":
            raise RemoteCleanupError("VPS_NOT_FOUND", "落地服务器记录不存在。", 404)
        nodes = db.scalars(
            select(Node)
            .where(Node.vps_id == vps.id)
            .where(Node.deleted_at.is_(None))
        ).all()
        deleted_node_ids: list[str] = []
        for node in nodes:
            _mark_node_deleted(node)
            db.add(node)
            deleted_node_ids.append(node.id)
        worker = db.get(Worker, command.worker_id)
        if worker:
            _mark_worker_deleted(db, worker)
        vps.status = "deleted"
        vps.last_ssh_status = "unchecked"
        vps.last_ssh_error = None
        db.add(vps)
        normalized["system_record_deleted"] = True
        normalized["deleted_node_ids"] = deleted_node_ids
        normalized["deleted_vps_id"] = vps.id
        normalized["worker_record_status"] = "deleted"
    elif command.command_type == CLEANUP_TRANSIT_ROUTE_COMMAND:
        route = db.get(TransitRoute, target_id)
        if not route or route.deleted_at is not None:
            raise RemoteCleanupError("TRANSIT_ROUTE_NOT_FOUND", "中转链路不存在。", 404)
        _mark_route_deleted(route)
        db.add(route)
        normalized["system_record_deleted"] = True
        normalized["deleted_route_ids"] = [route.id]
    elif command.command_type == CLEANUP_TRANSIT_RESOURCE_COMMAND:
        resource = db.get(TransitResource, target_id)
        if not resource or resource.deleted_at is not None:
            raise RemoteCleanupError("TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。", 404)
        routes = db.scalars(
            select(TransitRoute)
            .where(TransitRoute.transit_resource_id == resource.id)
            .where(TransitRoute.deleted_at.is_(None))
        ).all()
        deleted_route_ids: list[str] = []
        for route in routes:
            _mark_route_deleted(route)
            db.add(route)
            deleted_route_ids.append(route.id)
        worker = db.get(Worker, command.worker_id)
        if worker:
            _mark_worker_deleted(db, worker)
        resource.status = "deleted"
        resource.deleted_at = resource.deleted_at or _now()
        db.add(resource)
        normalized["system_record_deleted"] = True
        normalized["deleted_route_ids"] = deleted_route_ids
        normalized["deleted_transit_resource_id"] = resource.id
        normalized["worker_record_status"] = "deleted"
    return normalized
