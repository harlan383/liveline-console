from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.node import Node
from app.models.vps_server import VpsServer
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand
from app.schemas.landing_node_plan import (
    DEFAULT_LANDING_NODE_LISTEN_PORT,
    DEFAULT_REALITY_DEST,
    DEFAULT_REALITY_FINGERPRINT,
    DEFAULT_REALITY_FLOW,
    DEFAULT_REALITY_SECURITY,
    DEFAULT_REALITY_SNI,
    DEFAULT_REALITY_TRANSPORT,
    LandingNodeCreateRequest,
    validate_landing_node_listen_port,
)
from app.services.landing_node_plan import (
    active_node_on_port_exists,
    active_transit_target_on_port_exists,
    APPROVED_FORMAL_LISTEN_PORT,
    latest_landing_preflight,
    service_installed,
    xray_existing_config_detected,
)
from app.services.worker_binding import worker_runtime_status
from app.services.worker_commands import create_worker_command
from app.services.share_link_compat import ensure_vless_tcp_header_type_none, is_vless_share_link
from app.services.worker_targeting import (
    minimum_worker_version_for_command,
    worker_sort_key,
    worker_supports_command_channel,
)

LANDING_NODE_CREATE_COMMAND = "landing_node_create"
DEFAULT_REALITY_SERVER_NAME = DEFAULT_REALITY_SNI
DEFAULT_FINGERPRINT = DEFAULT_REALITY_FINGERPRINT
MANAGED_XRAY_CONFIG_PATH = "/opt/liveline-xray/config/config.json"
MANAGED_XRAY_SERVICE_NAME = "liveline-xray.service"
MANAGED_XRAY_SERVICE_PATH = "/etc/systemd/system/liveline-xray.service"


class LandingNodeCreateError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _preflight_clean(command: WorkerCommand | None) -> bool:
    if not command or command.status != "succeeded" or not isinstance(command.result_json, dict):
        return False
    warnings = command.result_json.get("warnings")
    errors = command.result_json.get("errors")
    warning_count = len(warnings) if isinstance(warnings, list) else 0
    error_count = len(errors) if isinstance(errors, list) else 0
    return warning_count == 0 and error_count == 0


def _preflight_result(command: WorkerCommand | None) -> dict[str, Any]:
    if command and isinstance(command.result_json, dict):
        return command.result_json
    return {}


def _preflight_text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _preflight_default_interface(command: WorkerCommand | None) -> str | None:
    result = _preflight_result(command)
    network = result.get("network") if isinstance(result.get("network"), dict) else {}
    system = result.get("system") if isinstance(result.get("system"), dict) else {}
    return (
        _preflight_text(network.get("default_route_interface"))
        or _preflight_text(network.get("detected_default_interface"))
        or _preflight_text(result.get("default_route_interface"))
        or _preflight_text(result.get("detected_default_interface"))
        or _preflight_text(system.get("default_route_interface"))
    )


def _preflight_has_interface_mismatch(command: WorkerCommand | None) -> bool:
    result = _preflight_result(command)
    network = result.get("network") if isinstance(result.get("network"), dict) else {}
    system = result.get("system") if isinstance(result.get("system"), dict) else {}
    if result.get("interface_mismatch") is True or network.get("interface_mismatch") is True or system.get("interface_mismatch") is True:
        return True

    warnings = result.get("warnings")
    if isinstance(warnings, list):
        for item in warnings:
            if isinstance(item, str) and "interface_mismatch" in item:
                return True
            if isinstance(item, dict) and item.get("code") == "interface_mismatch":
                return True
    return False


def _preflight_has_blocking_xray(command: WorkerCommand | None) -> bool:
    if not command or not isinstance(command.result_json, dict):
        return True
    result = command.result_json
    return (
        service_installed(result, "x-ui")
        or service_installed(result, "3x-ui")
        or xray_existing_config_detected(result)
    )


def _vps_is_available_for_create(vps: VpsServer) -> bool:
    return bool(vps.id and vps.ip and vps.status != "deleted")


def _active_node_on_port_exists(db: Session, server_id: str, port: int) -> bool:
    return active_node_on_port_exists(db, server_id, port)


def _approved_worker_for_vps(db: Session, *, vps: VpsServer, preflight: WorkerCommand) -> Worker:
    workers = db.scalars(
        select(Worker)
        .where(Worker.server_id == vps.id)
        .where(Worker.role == "landing")
        .where(Worker.status == "online")
    ).all()
    if not workers:
        raise LandingNodeCreateError(
            "APPROVED_WORKER_NOT_FOUND",
            "没有找到绑定到当前落地服务器、角色为 landing 的在线 Worker。",
        )

    online_workers = [
        worker
        for worker in workers
        if worker.server_id == vps.id and worker.role == "landing" and worker_runtime_status(worker) == "online"
    ]
    if not online_workers:
        raise LandingNodeCreateError(
            "APPROVED_WORKER_OFFLINE",
            "当前落地服务器上的 landing Worker 心跳已过期或不在线。",
        )

    capable_workers = [
        worker for worker in online_workers if worker_supports_command_channel(worker, LANDING_NODE_CREATE_COMMAND)
    ]
    if not capable_workers:
        minimum_version = minimum_worker_version_for_command(LANDING_NODE_CREATE_COMMAND)
        raise LandingNodeCreateError(
            "APPROVED_WORKER_COMMAND_UNSUPPORTED",
            f"当前落地服务器上的在线 Worker 版本不支持正式创建命令，请先升级到 {minimum_version} 或更高版本。",
        )

    default_interface = _preflight_default_interface(preflight)
    if not default_interface:
        raise LandingNodeCreateError(
            "FORMAL_PREFLIGHT_INTERFACE_UNKNOWN",
            "最新 landing_preflight 未返回默认公网网卡，不能进入正式创建。",
        )

    matched_workers = [worker for worker in capable_workers if worker.interface_name == default_interface]
    if not matched_workers:
        raise LandingNodeCreateError(
            "FORMAL_WORKER_INTERFACE_MISMATCH",
            "当前 landing Worker 绑定网卡与最新 landing_preflight 默认公网网卡不一致，不能进入正式创建。",
        )

    return sorted(matched_workers, key=worker_sort_key, reverse=True)[0]


def validate_landing_node_create_request(
    *,
    db: Session,
    vps: VpsServer,
    payload: LandingNodeCreateRequest,
) -> Worker:
    if not _vps_is_available_for_create(vps):
        raise LandingNodeCreateError("FORMAL_SERVER_NOT_APPROVED", "当前落地服务器记录不可用于正式创建。")
    try:
        validate_landing_node_listen_port(payload.approved_port)
    except ValueError as exc:
        raise LandingNodeCreateError("FORMAL_PORT_NOT_APPROVED", str(exc)) from exc

    confirmations = {
        "CONFIRM_FIREWALL_OPEN_REQUIRED": payload.confirm_firewall_open,
        "CONFIRM_GENERATE_SHARE_LINK_REQUIRED": payload.confirm_generate_share_link,
        "CONFIRM_WRITE_SHARE_LINK_REQUIRED": payload.confirm_write_share_link_after_success,
        "CONFIRM_NO_EXISTING_XRAY_REQUIRED": payload.confirm_no_existing_xray,
        "CONFIRM_ROLLBACK_SCOPE_REQUIRED": payload.confirm_rollback_new_artifacts_only,
    }
    missing = [code for code, confirmed in confirmations.items() if not confirmed]
    if missing:
        raise LandingNodeCreateError(missing[0], "正式创建前必须完成所有二次确认。")

    if _active_node_on_port_exists(db, vps.id, payload.approved_port):
        raise LandingNodeCreateError("NODE_PORT_ALREADY_EXISTS", "系统中已有未删除节点使用该监听端口。")
    if active_transit_target_on_port_exists(db, vps.id, payload.approved_port):
        raise LandingNodeCreateError("TRANSIT_TARGET_PORT_ALREADY_EXISTS", "系统中已有未删除中转链路使用该端口作为落地目标。")

    preflight = latest_landing_preflight(db, vps.id)
    if _preflight_has_interface_mismatch(preflight):
        raise LandingNodeCreateError("FORMAL_PREFLIGHT_INTERFACE_MISMATCH", "最新 landing_preflight 显示 Worker 网卡与默认公网网卡不一致。")
    if not _preflight_clean(preflight):
        raise LandingNodeCreateError("LANDING_PREFLIGHT_REQUIRED", "正式创建前必须已有 warnings/errors 均为空的 landing_preflight。")
    if _preflight_has_blocking_xray(preflight):
        raise LandingNodeCreateError("XRAY_ALREADY_PRESENT", "最新 landing_preflight 显示 Xray 或已有配置存在，不能执行创建。")

    return _approved_worker_for_vps(db, vps=vps, preflight=preflight)


def create_landing_node_create_command(
    *,
    db: Session,
    vps: VpsServer,
    payload: LandingNodeCreateRequest,
) -> tuple[WorkerCommand, Worker]:
    worker = validate_landing_node_create_request(db=db, vps=vps, payload=payload)
    reality_sni = payload.server_name or DEFAULT_REALITY_SERVER_NAME
    reality_dest = payload.dest or DEFAULT_REALITY_DEST
    fingerprint = payload.fingerprint or DEFAULT_FINGERPRINT
    command_payload = {
        "stage": "3.3.37",
        "server_id": vps.id,
        "server_ip": vps.ip,
        "worker_id": worker.id,
        "interface_name": worker.interface_name,
        "listen_port": payload.approved_port,
        "protocol": "vless",
        "security": DEFAULT_REALITY_SECURITY,
        "flow": DEFAULT_REALITY_FLOW,
        "server_name": reality_sni,
        "sni": reality_sni,
        "reality_sni": reality_sni,
        "dest": reality_dest,
        "reality_dest": reality_dest,
        "fingerprint": fingerprint,
        "transport": DEFAULT_REALITY_TRANSPORT,
        "node_name": payload.node_name or f"liveline-reality-{payload.approved_port}",
        "managed_config_path": MANAGED_XRAY_CONFIG_PATH,
        "managed_service_name": MANAGED_XRAY_SERVICE_NAME,
        "managed_service_path": MANAGED_XRAY_SERVICE_PATH,
        "rollback_scope": "current_run_artifacts_only",
        "share_link_write_policy": "backend_writes_after_worker_success_only",
    }
    command = create_worker_command(db, worker, LANDING_NODE_CREATE_COMMAND, command_payload)
    return command, worker


def _result_string(result: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _result_int(result: dict[str, Any], key: str) -> int | None:
    value = result.get(key)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def mask_share_link(share_link: str) -> str:
    if len(share_link) <= 40:
        return "[redacted-link]"
    return f"{share_link[:18]}...{share_link[-10:]}"


def persist_successful_landing_node_result(
    *,
    db: Session,
    command: WorkerCommand,
    result: dict[str, Any] | None,
) -> dict[str, Any]:
    if command.command_type != LANDING_NODE_CREATE_COMMAND:
        return result or {}
    if not isinstance(result, dict):
        raise LandingNodeCreateError("INVALID_WORKER_RESULT", "Worker 返回结果格式不合法。")
    if result.get("status") != "succeeded":
        raise LandingNodeCreateError("INVALID_WORKER_RESULT_STATUS", "Worker 未返回成功状态，不能写入 node.share_link。")
    if not command.server_id:
        raise LandingNodeCreateError("FORMAL_SERVER_NOT_APPROVED", "Worker 命令缺少绑定落地服务器。")

    share_link = _result_string(result, "secure_share_link")
    if not is_vless_share_link(share_link):
        raise LandingNodeCreateError("SHARE_LINK_MISSING", "Worker 未返回可写入的 VLESS 分享链接。")
    share_link = ensure_vless_tcp_header_type_none(share_link)
    listen_port = _result_int(result, "listen_port")
    command_port = _result_int(command.payload_json or {}, "listen_port") if isinstance(command.payload_json, dict) else None
    expected_port = command_port or DEFAULT_LANDING_NODE_LISTEN_PORT
    if listen_port != expected_port:
        raise LandingNodeCreateError("FORMAL_PORT_NOT_APPROVED", "Worker 返回端口与创建命令审批端口不一致。")
    if _active_node_on_port_exists(db, command.server_id, expected_port):
        raise LandingNodeCreateError("NODE_PORT_ALREADY_EXISTS", "系统中已有未删除节点使用该监听端口。")

    vps = db.get(VpsServer, command.server_id)
    if not vps or not _vps_is_available_for_create(vps):
        raise LandingNodeCreateError("FORMAL_SERVER_NOT_APPROVED", "Worker 命令绑定的落地服务器记录不可用。")

    node = Node(
        vps_id=command.server_id,
        node_name=_result_string(result, "node_name") or f"liveline-reality-{expected_port}",
        protocol="vless",
        transport=_result_string(result, "transport") or DEFAULT_REALITY_TRANSPORT,
        security=_result_string(result, "security") or DEFAULT_REALITY_SECURITY,
        flow=_result_string(result, "flow") or DEFAULT_REALITY_FLOW,
        xray_port=expected_port,
        uuid=_result_string(result, "uuid"),
        reality_public_key=_result_string(result, "reality_public_key"),
        reality_short_id=_result_string(result, "reality_short_id"),
        sni=_result_string(result, "server_name", "sni") or DEFAULT_REALITY_SERVER_NAME,
        dest=_result_string(result, "dest") or DEFAULT_REALITY_DEST,
        share_link=share_link,
        fingerprint=_result_string(result, "fingerprint") or DEFAULT_FINGERPRINT,
        service_status="active",
        connectivity_status="not_checked",
        source="worker_landing_node_create",
        status="active",
        last_remote_check_at=datetime.now(UTC),
        last_sync_status="created_by_liveline_worker",
    )
    db.add(node)
    vps.xray_installed = True
    vps.xray_config_path = MANAGED_XRAY_CONFIG_PATH
    vps.status = "active"
    db.add(vps)
    db.flush()

    sanitized = dict(result)
    sanitized.pop("secure_share_link", None)
    sanitized["node_id"] = node.id
    sanitized["share_link_present"] = True
    sanitized["masked_share_link"] = mask_share_link(share_link)
    sanitized["share_link_storage"] = "node.share_link_written_after_success"
    return sanitized
