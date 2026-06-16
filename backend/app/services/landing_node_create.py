from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.node import Node
from app.models.vps_server import VpsServer
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand
from app.schemas.landing_node_plan import LandingNodeCreateRequest
from app.services.landing_node_plan import (
    APPROVED_FORMAL_LISTEN_PORT,
    latest_landing_preflight,
    service_installed,
    xray_existing_config_detected,
)
from app.services.worker_binding import worker_runtime_status
from app.services.worker_commands import create_worker_command
from app.services.worker_targeting import worker_supports_command_channel

APPROVED_FORMAL_SERVER_ID = "968519b3-9017-4b27-a9a0-d5731033f84f"
APPROVED_FORMAL_WORKER_ID = "ef421476-dcad-4380-8cea-40dc81e543fd"
APPROVED_FORMAL_SERVER_IP = "64.90.13.19"
APPROVED_FORMAL_INTERFACE = "ens17"
LANDING_NODE_CREATE_COMMAND = "landing_node_create"
DEFAULT_REALITY_SERVER_NAME = "www.microsoft.com"
DEFAULT_REALITY_DEST = "www.microsoft.com:443"
DEFAULT_REALITY_FLOW = "xtls-rprx-vision"
DEFAULT_FINGERPRINT = "chrome"
MANAGED_XRAY_CONFIG_PATH = "/usr/local/etc/liveline-xray/config.json"
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


def _preflight_has_blocking_xray(command: WorkerCommand | None) -> bool:
    if not command or not isinstance(command.result_json, dict):
        return True
    result = command.result_json
    return (
        service_installed(result, "xray")
        or service_installed(result, "x-ui")
        or service_installed(result, "3x-ui")
        or xray_existing_config_detected(result)
    )


def _active_node_on_port_exists(db: Session, server_id: str, port: int) -> bool:
    return (
        db.scalar(
            select(Node.id)
            .where(Node.vps_id == server_id)
            .where(Node.deleted_at.is_(None))
            .where(Node.xray_port == port)
            .limit(1)
        )
        is not None
    )


def _approved_worker(db: Session) -> Worker:
    worker = db.get(Worker, APPROVED_FORMAL_WORKER_ID)
    if not worker:
        raise LandingNodeCreateError("APPROVED_WORKER_NOT_FOUND", "审批锁定的 Worker 不存在。")
    if worker.server_id != APPROVED_FORMAL_SERVER_ID or worker.role != "landing":
        raise LandingNodeCreateError("APPROVED_WORKER_MISMATCH", "审批锁定的 Worker 与目标落地服务器不匹配。")
    if worker.interface_name != APPROVED_FORMAL_INTERFACE:
        raise LandingNodeCreateError("APPROVED_WORKER_INTERFACE_MISMATCH", "审批锁定的 Worker 网卡不是 ens17。")
    if worker_runtime_status(worker) != "online":
        raise LandingNodeCreateError("APPROVED_WORKER_OFFLINE", "审批锁定的 Worker 当前不在线。")
    if not worker_supports_command_channel(worker, LANDING_NODE_CREATE_COMMAND):
        raise LandingNodeCreateError(
            "APPROVED_WORKER_COMMAND_UNSUPPORTED",
            "审批锁定的 Worker 版本不支持正式创建命令，请先升级 liveline-worker。",
        )
    return worker


def validate_landing_node_create_request(
    *,
    db: Session,
    vps: VpsServer,
    payload: LandingNodeCreateRequest,
) -> Worker:
    if vps.id != APPROVED_FORMAL_SERVER_ID or vps.ip != APPROVED_FORMAL_SERVER_IP:
        raise LandingNodeCreateError("FORMAL_SERVER_NOT_APPROVED", "本阶段只允许审批锁定的落地服务器进入正式创建。")
    if payload.approved_port != APPROVED_FORMAL_LISTEN_PORT:
        raise LandingNodeCreateError("FORMAL_PORT_NOT_APPROVED", "本阶段只允许使用审批端口 27939/TCP。")

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

    if _active_node_on_port_exists(db, vps.id, APPROVED_FORMAL_LISTEN_PORT):
        raise LandingNodeCreateError("NODE_PORT_ALREADY_EXISTS", "系统中已有未删除节点使用审批端口。")

    preflight = latest_landing_preflight(db, vps.id)
    if not _preflight_clean(preflight):
        raise LandingNodeCreateError("LANDING_PREFLIGHT_REQUIRED", "正式创建前必须已有 warnings/errors 均为空的 landing_preflight。")
    if _preflight_has_blocking_xray(preflight):
        raise LandingNodeCreateError("XRAY_ALREADY_PRESENT", "最新 landing_preflight 显示 Xray 或已有配置存在，不能执行创建。")

    return _approved_worker(db)


def create_landing_node_create_command(
    *,
    db: Session,
    vps: VpsServer,
    payload: LandingNodeCreateRequest,
) -> tuple[WorkerCommand, Worker]:
    worker = validate_landing_node_create_request(db=db, vps=vps, payload=payload)
    command_payload = {
        "stage": "3.3.37",
        "server_id": vps.id,
        "server_ip": vps.ip,
        "worker_id": worker.id,
        "interface_name": APPROVED_FORMAL_INTERFACE,
        "listen_port": APPROVED_FORMAL_LISTEN_PORT,
        "protocol": "vless",
        "security": "reality",
        "flow": DEFAULT_REALITY_FLOW,
        "server_name": DEFAULT_REALITY_SERVER_NAME,
        "dest": DEFAULT_REALITY_DEST,
        "fingerprint": DEFAULT_FINGERPRINT,
        "node_name": f"liveline-reality-{APPROVED_FORMAL_LISTEN_PORT}",
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
    if command.server_id != APPROVED_FORMAL_SERVER_ID:
        raise LandingNodeCreateError("FORMAL_SERVER_NOT_APPROVED", "Worker 命令不属于审批锁定的服务器。")

    share_link = _result_string(result, "secure_share_link")
    if not share_link or not share_link.startswith("vless://"):
        raise LandingNodeCreateError("SHARE_LINK_MISSING", "Worker 未返回可写入的 VLESS 分享链接。")
    listen_port = _result_int(result, "listen_port")
    if listen_port != APPROVED_FORMAL_LISTEN_PORT:
        raise LandingNodeCreateError("FORMAL_PORT_NOT_APPROVED", "Worker 返回端口不是 27939/TCP。")
    if _active_node_on_port_exists(db, APPROVED_FORMAL_SERVER_ID, APPROVED_FORMAL_LISTEN_PORT):
        raise LandingNodeCreateError("NODE_PORT_ALREADY_EXISTS", "系统中已有未删除节点使用审批端口。")

    node = Node(
        vps_id=APPROVED_FORMAL_SERVER_ID,
        node_name=_result_string(result, "node_name") or f"liveline-reality-{APPROVED_FORMAL_LISTEN_PORT}",
        protocol="vless",
        transport="tcp",
        security="reality",
        flow=_result_string(result, "flow") or DEFAULT_REALITY_FLOW,
        xray_port=APPROVED_FORMAL_LISTEN_PORT,
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
    vps = db.get(VpsServer, APPROVED_FORMAL_SERVER_ID)
    if vps:
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

