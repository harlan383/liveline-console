from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.worker_command import WorkerCommand
from app.schemas.transit_route import (
    APPROVED_LANDING_NODE_ID,
    APPROVED_LANDING_TARGET_HOST,
    APPROVED_LANDING_TARGET_PORT,
    APPROVED_TRANSIT_FORWARDING_METHOD,
    APPROVED_TRANSIT_LISTEN_PORT,
    APPROVED_TRANSIT_RESOURCE_ID,
    APPROVED_TRANSIT_ROUTE_NAME,
    APPROVED_TRANSIT_SERVICE_NAME,
    APPROVED_TRANSIT_SERVICE_PATH,
    APPROVED_TRANSIT_WORKER_ID,
)
from app.services.worker_commands import normalize_worker_command_result

TRANSIT_ROUTE_CREATE_COMMAND = "transit_route_create"


class TransitRouteCreateResultError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _result_string(result: dict[str, Any], key: str) -> str | None:
    value = result.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _result_int(result: dict[str, Any], key: str) -> int | None:
    value = result.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _existing_route(db: Session) -> TransitRoute | None:
    return db.scalar(
        select(TransitRoute).where(
            TransitRoute.transit_resource_id == APPROVED_TRANSIT_RESOURCE_ID,
            TransitRoute.listen_port == APPROVED_TRANSIT_LISTEN_PORT,
            TransitRoute.status.in_(("creating", "active")),
            TransitRoute.deleted_at.is_(None),
        )
    )


def persist_successful_transit_route_create_result(
    *,
    db: Session,
    command: WorkerCommand,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    if command.command_type != TRANSIT_ROUTE_CREATE_COMMAND:
        return result or {}
    if not isinstance(result, dict):
        raise TransitRouteCreateResultError("INVALID_WORKER_RESULT", "Worker 返回结果格式不合法。")

    normalized = normalize_worker_command_result(TRANSIT_ROUTE_CREATE_COMMAND, result)
    if normalized.get("execution_mode") != "real_create" or normalized.get("real_execution") is not True:
        return normalized
    if normalized.get("status") != "succeeded":
        raise TransitRouteCreateResultError("INVALID_WORKER_RESULT_STATUS", "Worker 未返回真实创建成功状态。")
    if command.server_id != APPROVED_TRANSIT_RESOURCE_ID:
        raise TransitRouteCreateResultError("TRANSIT_RESOURCE_APPROVAL_MISMATCH", "Worker 命令不属于审批中转资源。")
    if command.worker_id != APPROVED_TRANSIT_WORKER_ID:
        raise TransitRouteCreateResultError("WORKER_APPROVAL_MISMATCH", "Worker 命令不属于审批 Worker。")

    checks = {
        "LISTEN_PORT_APPROVAL_MISMATCH": _result_int(normalized, "planned_listen_port")
        == APPROVED_TRANSIT_LISTEN_PORT,
        "LANDING_HOST_APPROVAL_MISMATCH": _result_string(normalized, "landing_target_host")
        == APPROVED_LANDING_TARGET_HOST,
        "LANDING_PORT_APPROVAL_MISMATCH": _result_int(normalized, "landing_target_port")
        == APPROVED_LANDING_TARGET_PORT,
        "FORWARDING_METHOD_APPROVAL_MISMATCH": _result_string(normalized, "forwarding_method")
        == APPROVED_TRANSIT_FORWARDING_METHOD,
        "ROUTE_NAME_APPROVAL_MISMATCH": _result_string(normalized, "route_name") == APPROVED_TRANSIT_ROUTE_NAME,
        "SERVICE_NAME_APPROVAL_MISMATCH": _result_string(normalized, "service_name")
        == APPROVED_TRANSIT_SERVICE_NAME,
        "SERVICE_PATH_APPROVAL_MISMATCH": _result_string(normalized, "service_path")
        == APPROVED_TRANSIT_SERVICE_PATH,
    }
    for code, passed in checks.items():
        if not passed:
            raise TransitRouteCreateResultError(code, "Worker 返回结果与审批参数不一致。")

    resource = db.get(TransitResource, APPROVED_TRANSIT_RESOURCE_ID)
    if not resource or resource.deleted_at is not None:
        raise TransitRouteCreateResultError("TRANSIT_RESOURCE_NOT_FOUND", "中转服务器记录不存在。")
    if resource.resource_type != "server" or resource.status == "disabled":
        raise TransitRouteCreateResultError("TRANSIT_RESOURCE_NOT_ELIGIBLE", "中转服务器状态不允许写入线路记录。")

    node = db.get(Node, APPROVED_LANDING_NODE_ID)
    if not node or node.deleted_at is not None:
        raise TransitRouteCreateResultError("LANDING_NODE_NOT_FOUND", "落地节点不存在。")
    if node.status != "active":
        raise TransitRouteCreateResultError("LANDING_NODE_NOT_ACTIVE", "落地节点不是 active 状态。")
    if node.xray_port != APPROVED_LANDING_TARGET_PORT:
        raise TransitRouteCreateResultError("LANDING_TARGET_PORT_MISMATCH", "落地节点端口与审批目标不一致。")

    existing = _existing_route(db)
    if existing:
        normalized["route_id"] = existing.id
        normalized["route_status"] = existing.status
        normalized["route_persisted"] = False
        normalized["route_duplicate_existing"] = True
        normalized["share_link_storage"] = "transit_route.share_link_null_not_generated"
        return normalized

    route = TransitRoute(
        name=APPROVED_TRANSIT_ROUTE_NAME,
        transit_resource_id=APPROVED_TRANSIT_RESOURCE_ID,
        node_id=APPROVED_LANDING_NODE_ID,
        landing_vps_id=node.vps_id,
        listen_port=APPROVED_TRANSIT_LISTEN_PORT,
        target_host=APPROVED_LANDING_TARGET_HOST,
        target_port=APPROVED_LANDING_TARGET_PORT,
        forwarding_method=APPROVED_TRANSIT_FORWARDING_METHOD,
        service_name=APPROVED_TRANSIT_SERVICE_NAME,
        service_path=APPROVED_TRANSIT_SERVICE_PATH,
        status="active",
        share_link=None,
    )
    db.add(route)
    db.flush()

    normalized["route_id"] = route.id
    normalized["route_status"] = route.status
    normalized["route_persisted"] = True
    normalized["share_link_storage"] = "transit_route.share_link_null_not_generated"
    return normalized
