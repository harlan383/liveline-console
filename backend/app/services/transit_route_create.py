from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.worker_command import WorkerCommand
from app.schemas.transit_route import (
    APPROVED_TRANSIT_FORWARDING_METHOD,
    FORWARDING_METHOD_HAPROXY_TCP,
    normalize_forwarding_method,
)
from app.services.worker_commands import normalize_worker_command_result

TRANSIT_ROUTE_CREATE_COMMAND = "transit_route_create"
HAPROXY_ROUTE_CREATE_REAL_EXECUTION_INTENT = "haproxy_route_create_real_execution"
SUPPORTED_PERSIST_FORWARDING_METHODS = {APPROVED_TRANSIT_FORWARDING_METHOD, FORWARDING_METHOD_HAPROXY_TCP}


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


def _result_bool(result: dict[str, Any], key: str) -> bool | None:
    value = result.get(key)
    if isinstance(value, bool):
        return value
    return None


def _payload_dict(command: WorkerCommand) -> dict[str, Any]:
    return command.payload_json if isinstance(command.payload_json, dict) else {}


def _normalized_forwarding_method(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return normalize_forwarding_method(value)
    except ValueError:
        return value.strip().lower().replace("-", "_")


def _expected_service_name(listen_port: int, forwarding_method: str) -> str:
    if forwarding_method == FORWARDING_METHOD_HAPROXY_TCP:
        return f"liveline-haproxy-{listen_port}.service"
    return f"liveline-socat-{listen_port}.service"


def _expected_service_path(listen_port: int, forwarding_method: str) -> str:
    return f"/etc/systemd/system/{_expected_service_name(listen_port, forwarding_method)}"


def _expected_config_path(listen_port: int, forwarding_method: str) -> str | None:
    if forwarding_method == FORWARDING_METHOD_HAPROXY_TCP:
        return f"/etc/haproxy/liveline/routes/liveline-haproxy-{listen_port}.cfg"
    return None


def _existing_route(db: Session, transit_resource_id: str, listen_port: int) -> TransitRoute | None:
    return db.scalar(
        select(TransitRoute).where(
            TransitRoute.transit_resource_id == transit_resource_id,
            TransitRoute.listen_port == listen_port,
            TransitRoute.status.in_(("creating", "active")),
            TransitRoute.deleted_at.is_(None),
        )
    )


def _require_tcp_port(value: int | None, code: str, message: str) -> int:
    if value is None or value < 1 or value > 65535:
        raise TransitRouteCreateResultError(code, message)
    return value


def _validate_haproxy_dynamic_real_create_approval(
    *,
    payload: dict[str, Any],
    planned_listen_port: int,
    landing_target_host: str | None,
    landing_target_port: int,
) -> None:
    if _result_string(payload, "command_intent") != HAPROXY_ROUTE_CREATE_REAL_EXECUTION_INTENT:
        raise TransitRouteCreateResultError(
            "COMMAND_INTENT_APPROVAL_MISMATCH",
            "HAProxy TCP real_create 命令缺少真实创建审批 intent。",
        )
    if _result_string(payload, "execution_mode") != "real_create":
        raise TransitRouteCreateResultError(
            "EXECUTION_MODE_APPROVAL_MISMATCH",
            "HAProxy TCP real_create 命令 execution_mode 必须为 real_create。",
        )
    if _result_bool(payload, "dry_run") is not False:
        raise TransitRouteCreateResultError(
            "DRY_RUN_APPROVAL_MISMATCH",
            "HAProxy TCP real_create 命令 dry_run 必须为 false。",
        )
    if _result_bool(payload, "real_execution") is not True:
        raise TransitRouteCreateResultError(
            "REAL_EXECUTION_APPROVAL_MISMATCH",
            "HAProxy TCP real_create 命令 real_execution 必须为 true。",
        )
    if _result_bool(payload, "approved_real_execution") is not True:
        raise TransitRouteCreateResultError(
            "REAL_EXECUTION_APPROVAL_MISSING",
            "HAProxy TCP real_create 命令缺少 approved_real_execution 确认。",
        )
    if _result_int(payload, "approved_planned_listen_port") != planned_listen_port:
        raise TransitRouteCreateResultError(
            "LISTEN_PORT_APPROVAL_MISMATCH",
            "approved_planned_listen_port 与 planned_listen_port 不一致。",
        )
    if _result_string(payload, "approved_landing_target_host") != landing_target_host:
        raise TransitRouteCreateResultError(
            "LANDING_HOST_APPROVAL_MISMATCH",
            "approved_landing_target_host 与 landing_target_host 不一致。",
        )
    if _result_int(payload, "approved_landing_target_port") != landing_target_port:
        raise TransitRouteCreateResultError(
            "LANDING_PORT_APPROVAL_MISMATCH",
            "approved_landing_target_port 与 landing_target_port 不一致。",
        )
    if _result_bool(payload, "approved_firewall_confirmation") is not True:
        raise TransitRouteCreateResultError(
            "FIREWALL_CONFIRMATION_MISSING",
            "approved_firewall_confirmation 缺失或不是 true。",
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
    forwarding_method = _normalized_forwarding_method(_result_string(payload, "forwarding_method"))
    transit_worker_id = _result_string(payload, "transit_worker_id")

    if not transit_resource_id or command.server_id != transit_resource_id:
        raise TransitRouteCreateResultError("TRANSIT_RESOURCE_APPROVAL_MISMATCH", "Worker 命令不属于请求的中转资源。")
    if transit_worker_id and command.worker_id != transit_worker_id:
        raise TransitRouteCreateResultError("WORKER_APPROVAL_MISMATCH", "Worker 命令不属于请求的 Worker。")
    if not landing_node_id:
        raise TransitRouteCreateResultError("LANDING_NODE_APPROVAL_MISSING", "Worker 命令缺少落地节点审批参数。")
    if not route_name:
        raise TransitRouteCreateResultError("ROUTE_NAME_APPROVAL_MISSING", "Worker 命令缺少线路名称审批参数。")
    if not landing_target_host:
        raise TransitRouteCreateResultError("LANDING_HOST_APPROVAL_MISSING", "Worker 命令缺少落地目标 host 审批参数。")
    planned_listen_port = _require_tcp_port(
        planned_listen_port,
        "LISTEN_PORT_APPROVAL_MISSING",
        "Worker 命令缺少合法 planned_listen_port 审批参数。",
    )
    landing_target_port = _require_tcp_port(
        landing_target_port,
        "LANDING_PORT_APPROVAL_MISSING",
        "Worker 命令缺少合法 landing_target_port 审批参数。",
    )
    if forwarding_method not in SUPPORTED_PERSIST_FORWARDING_METHODS:
        raise TransitRouteCreateResultError("FORWARDING_METHOD_APPROVAL_MISMATCH", "Worker 命令转发方式不在受保护审批范围。")
    if forwarding_method == FORWARDING_METHOD_HAPROXY_TCP:
        _validate_haproxy_dynamic_real_create_approval(
            payload=payload,
            planned_listen_port=planned_listen_port,
            landing_target_host=landing_target_host,
            landing_target_port=landing_target_port,
        )

    expected_service_name = _expected_service_name(planned_listen_port, forwarding_method)
    expected_service_path = _expected_service_path(planned_listen_port, forwarding_method)
    expected_config_path = _expected_config_path(planned_listen_port, forwarding_method)

    result_planned_listen_port = _result_int(normalized, "planned_listen_port")
    result_raw_listen_port = _result_int(result, "listen_port")
    result_landing_target_port = _result_int(normalized, "landing_target_port")
    result_raw_target_port = _result_int(result, "target_port")
    result_effective_listen_port = result_planned_listen_port or result_raw_listen_port
    result_effective_target_port = result_landing_target_port or result_raw_target_port
    checks = {
        "LISTEN_PORT_APPROVAL_MISMATCH": result_effective_listen_port == planned_listen_port,
        "RESULT_LISTEN_PORT_APPROVAL_MISMATCH": result_raw_listen_port in {None, planned_listen_port},
        "LANDING_HOST_APPROVAL_MISMATCH": _result_string(normalized, "landing_target_host")
        == landing_target_host,
        "LANDING_PORT_APPROVAL_MISMATCH": result_effective_target_port == landing_target_port,
        "RESULT_TARGET_PORT_APPROVAL_MISMATCH": result_raw_target_port in {None, landing_target_port},
        "FORWARDING_METHOD_APPROVAL_MISMATCH": _normalized_forwarding_method(
            _result_string(normalized, "forwarding_method")
        )
        == forwarding_method,
        "ROUTE_NAME_APPROVAL_MISMATCH": _result_string(normalized, "route_name") == route_name,
        "SERVICE_NAME_APPROVAL_MISMATCH": _result_string(normalized, "service_name") == expected_service_name,
        "SERVICE_PATH_APPROVAL_MISMATCH": _result_string(normalized, "service_path") == expected_service_path,
    }
    check_messages = {
        "LISTEN_PORT_APPROVAL_MISMATCH": "Worker 返回监听端口与 command planned_listen_port 不一致。",
        "RESULT_LISTEN_PORT_APPROVAL_MISMATCH": "Worker 返回 listen_port 与 command planned_listen_port 不一致。",
        "LANDING_HOST_APPROVAL_MISMATCH": "Worker 返回落地目标 host 与 command landing_target_host 不一致。",
        "LANDING_PORT_APPROVAL_MISMATCH": "Worker 返回落地目标端口与 command landing_target_port 不一致。",
        "RESULT_TARGET_PORT_APPROVAL_MISMATCH": "Worker 返回 target_port 与 command landing_target_port 不一致。",
        "FORWARDING_METHOD_APPROVAL_MISMATCH": "Worker 返回 forwarding_method 与 command forwarding_method 不一致。",
        "ROUTE_NAME_APPROVAL_MISMATCH": "Worker 返回 route_name 与 command route_name 不一致。",
        "SERVICE_NAME_APPROVAL_MISMATCH": "Worker 返回 service_name 与 LiveLine 管理服务名不一致。",
        "SERVICE_PATH_APPROVAL_MISMATCH": "Worker 返回 service_path 与 LiveLine 管理服务路径不一致。",
    }
    for code, passed in checks.items():
        if not passed:
            raise TransitRouteCreateResultError(code, check_messages[code])
    result_config_path = _result_string(normalized, "config_path") or _result_string(result, "config_path")
    if expected_config_path and result_config_path and result_config_path != expected_config_path:
        raise TransitRouteCreateResultError("CONFIG_PATH_APPROVAL_MISMATCH", "Worker 返回 HAProxy 配置路径与审批参数不一致。")

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
