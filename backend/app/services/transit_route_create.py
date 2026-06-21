from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.worker_command import WorkerCommand
from app.schemas.transit_route import (
    APPROVED_LANDING_TARGET_PORT,
    APPROVED_TRANSIT_FORWARDING_METHOD,
    APPROVED_TRANSIT_LISTEN_PORT,
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


def _payload_dict(command: WorkerCommand) -> dict[str, Any]:
    return command.payload_json if isinstance(command.payload_json, dict) else {}


def _expected_service_name(listen_port: int) -> str:
    return f"liveline-socat-{listen_port}.service"


def _expected_service_path(listen_port: int) -> str:
    return f"/etc/systemd/system/{_expected_service_name(listen_port)}"


def _existing_route(db: Session, transit_resource_id: str, listen_port: int) -> TransitRoute | None:
    return db.scalar(
        select(TransitRoute).where(
            TransitRoute.transit_resource_id == transit_resource_id,
            TransitRoute.listen_port == listen_port,
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

    payload = _payload_dict(command)
    transit_resource_id = _result_string(payload, "transit_resource_id") or command.server_id
    landing_node_id = _result_string(payload, "landing_node_id")
    route_name = _result_string(payload, "route_name")
    planned_listen_port = _result_int(payload, "planned_listen_port")
    landing_target_host = _result_string(payload, "landing_target_host")
    landing_target_port = _result_int(payload, "landing_target_port")
    forwarding_method = _result_string(payload, "forwarding_method")
    transit_worker_id = _result_string(payload, "transit_worker_id")

    if not transit_resource_id or command.server_id != transit_resource_id:
        raise TransitRouteCreateResultError("TRANSIT_RESOURCE_APPROVAL_MISMATCH", "Worker 命令不属于请求的中转资源。")
    if transit_worker_id and command.worker_id != transit_worker_id:
        raise TransitRouteCreateResultError("WORKER_APPROVAL_MISMATCH", "Worker 命令不属于请求的 Worker。")
    if not landing_node_id:
        raise TransitRouteCreateResultError("LANDING_NODE_APPROVAL_MISSING", "Worker 命令缺少落地节点审批参数。")
    if not route_name:
        raise TransitRouteCreateResultError("ROUTE_NAME_APPROVAL_MISSING", "Worker 命令缺少线路名称审批参数。")
    if planned_listen_port != APPROVED_TRANSIT_LISTEN_PORT:
        raise TransitRouteCreateResultError("LISTEN_PORT_APPROVAL_MISMATCH", "Worker 命令监听端口不在受保护审批范围。")
    if landing_target_port != APPROVED_LANDING_TARGET_PORT:
        raise TransitRouteCreateResultError("LANDING_PORT_APPROVAL_MISMATCH", "Worker 命令落地端口不在受保护审批范围。")
    if forwarding_method != APPROVED_TRANSIT_FORWARDING_METHOD:
        raise TransitRouteCreateResultError("FORWARDING_METHOD_APPROVAL_MISMATCH", "Worker 命令转发方式不在受保护审批范围。")

    expected_service_name = _expected_service_name(planned_listen_port)
    expected_service_path = _expected_service_path(planned_listen_port)

    checks = {
        "LISTEN_PORT_APPROVAL_MISMATCH": _result_int(normalized, "planned_listen_port")
        == planned_listen_port,
        "LANDING_HOST_APPROVAL_MISMATCH": _result_string(normalized, "landing_target_host")
        == landing_target_host,
        "LANDING_PORT_APPROVAL_MISMATCH": _result_int(normalized, "landing_target_port") == landing_target_port,
        "FORWARDING_METHOD_APPROVAL_MISMATCH": _result_string(normalized, "forwarding_method") == forwarding_method,
        "ROUTE_NAME_APPROVAL_MISMATCH": _result_string(normalized, "route_name") == route_name,
        "SERVICE_NAME_APPROVAL_MISMATCH": _result_string(normalized, "service_name") == expected_service_name,
        "SERVICE_PATH_APPROVAL_MISMATCH": _result_string(normalized, "service_path") == expected_service_path,
    }
    for code, passed in checks.items():
        if not passed:
            raise TransitRouteCreateResultError(code, "Worker 返回结果与审批参数不一致。")

    resource = db.get(TransitResource, transit_resource_id)
    if not resource or resource.deleted_at is not None:
        raise TransitRouteCreateResultError("TRANSIT_RESOURCE_NOT_FOUND", "中转服务器记录不存在。")
    if resource.resource_type != "server" or resource.status not in {"active", "worker_online"}:
        raise TransitRouteCreateResultError("TRANSIT_RESOURCE_NOT_ELIGIBLE", "中转服务器状态不允许写入线路记录。")
    if not resource.entry_host:
        raise TransitRouteCreateResultError("TRANSIT_RESOURCE_NOT_ELIGIBLE", "中转服务器缺少入口地址。")

    node = db.get(Node, landing_node_id)
    if not node or node.deleted_at is not None:
        raise TransitRouteCreateResultError("LANDING_NODE_NOT_FOUND", "落地节点不存在。")
    if node.status != "active":
        raise TransitRouteCreateResultError("LANDING_NODE_NOT_ACTIVE", "落地节点不是 active 状态。")
    if not node.share_link:
        raise TransitRouteCreateResultError("LANDING_NODE_SHARE_LINK_REQUIRED", "落地节点缺少已生成的 share_link。")
    if node.xray_port != landing_target_port:
        raise TransitRouteCreateResultError("LANDING_TARGET_PORT_MISMATCH", "落地节点端口与审批目标不一致。")
    landing_host = node.vps.ip if node.vps else None
    if landing_host != landing_target_host:
        raise TransitRouteCreateResultError("LANDING_TARGET_HOST_MISMATCH", "落地节点 IP 与审批目标不一致。")

    existing = _existing_route(db, transit_resource_id, planned_listen_port)
    if existing:
        normalized["route_id"] = existing.id
        normalized["route_status"] = existing.status
        normalized["route_persisted"] = False
        normalized["route_duplicate_existing"] = True
        normalized["share_link_storage"] = "transit_route.share_link_null_not_generated"
        return normalized

    route = TransitRoute(
        name=route_name,
        transit_resource_id=transit_resource_id,
        node_id=landing_node_id,
        landing_vps_id=node.vps_id,
        listen_port=planned_listen_port,
        target_host=landing_target_host,
        target_port=landing_target_port,
        forwarding_method=forwarding_method,
        service_name=expected_service_name,
        service_path=expected_service_path,
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
