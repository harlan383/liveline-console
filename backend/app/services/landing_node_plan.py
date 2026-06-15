import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.vps_server import VpsServer
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand
from app.schemas.landing_node_plan import LandingNodePlanRequest
from app.services.worker_binding import worker_runtime_status
from app.services.worker_targeting import worker_supports_command_channel

DEFAULT_NEXT_STAGE = "Stage 3.3.33-worker-preflight-interface-normalization 或 Stage 3.3.33-formal-landing-node-create-approval"
SAFE_PORT_MIN = 1
SAFE_PORT_MAX = 65535
BLOCKED_MANAGEMENT_PORTS = {22, 20575}


def latest_landing_preflight(db: Session, server_id: str) -> WorkerCommand | None:
    return db.scalar(
        select(WorkerCommand)
        .where(
            WorkerCommand.server_id == server_id,
            WorkerCommand.server_type == "landing",
            WorkerCommand.command_type == "landing_preflight",
            WorkerCommand.status == "succeeded",
        )
        .order_by(WorkerCommand.completed_at.desc().nullslast(), WorkerCommand.created_at.desc())
        .limit(1)
    )


def default_route_interface(ip_route: str | None) -> str | None:
    if not ip_route:
        return None
    match = re.search(r"(?:^|\s)default\s+.*?\bdev\s+([A-Za-z0-9_.:-]+)", ip_route)
    return match.group(1) if match else None


def text_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def first_text(*values: Any) -> str | None:
    for value in values:
        text = text_or_none(value)
        if text:
            return text
    return None


def bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def local_ip_for_interface(local_ips: Any, interface_name: str | None) -> str | None:
    if not interface_name or not isinstance(local_ips, list):
        return None
    for item in local_ips:
        if not isinstance(item, dict):
            continue
        if item.get("interface") != interface_name:
            continue
        ip = text_or_none(item.get("ip"))
        if ip and ":" not in ip:
            return ip
    return None


def important_port_status(preflight: dict[str, Any], listen_port: int) -> str | None:
    ports = preflight.get("ports")
    if not isinstance(ports, dict):
        return None
    important_ports = ports.get("important_ports")
    if not isinstance(important_ports, dict):
        return None
    item = important_ports.get(str(listen_port))
    if isinstance(item, dict):
        status = item.get("status")
        return status if isinstance(status, str) else None
    return None


def xray_existing_config_detected(preflight: dict[str, Any]) -> bool:
    discovery = preflight.get("xray_discovery")
    if not isinstance(discovery, dict):
        return False
    paths = discovery.get("paths")
    if not isinstance(paths, list):
        return False
    config_paths = {"/usr/local/etc/xray/config.json", "/etc/xray/config.json"}
    for item in paths:
        if not isinstance(item, dict):
            continue
        if item.get("path") in config_paths and item.get("exists") is True:
            return True
    return False


def service_installed(preflight: dict[str, Any], name: str) -> bool:
    services = preflight.get("services")
    if isinstance(services, list):
        for item in services:
            if isinstance(item, dict) and item.get("name") == name and item.get("exists") is True:
                return True
    binaries = preflight.get("binaries")
    if isinstance(binaries, list):
        for item in binaries:
            if isinstance(item, dict) and item.get("name") == name and item.get("present") is True:
                return True
    return False


def preflight_summary(
    *,
    vps: VpsServer,
    worker: Worker | None,
    command: WorkerCommand | None,
) -> dict[str, Any]:
    result = command.result_json if command and isinstance(command.result_json, dict) else {}
    system = result.get("system") if isinstance(result.get("system"), dict) else {}
    network = result.get("network") if isinstance(result.get("network"), dict) else {}
    ports = result.get("ports") if isinstance(result.get("ports"), dict) else {}
    ip_route = text_or_none(network.get("ip_route")) if isinstance(network, dict) else None
    network_worker_interface = text_or_none(network.get("worker_config_interface")) if isinstance(network, dict) else None
    system_worker_interface = first_text(system.get("worker_config_interface"), system.get("interface_name")) if isinstance(system, dict) else None
    worker_bound_interface = worker.interface_name if worker else None
    configured_interface = first_text(network_worker_interface, system_worker_interface, worker_bound_interface)
    default_interface = first_text(
        network.get("default_route_interface") if isinstance(network, dict) else None,
        default_route_interface(ip_route),
    )
    primary_interface = first_text(network.get("primary_interface") if isinstance(network, dict) else None, default_interface)
    primary_interface_ip = first_text(
        network.get("primary_interface_ip") if isinstance(network, dict) else None,
        local_ip_for_interface(network.get("local_ips") if isinstance(network, dict) else None, primary_interface),
    )
    mismatch = bool_or_none(network.get("interface_mismatch") if isinstance(network, dict) else None)
    if mismatch is None:
        mismatch = bool(configured_interface and default_interface and configured_interface != default_interface)

    return {
        "server_name": vps.name or vps.ip,
        "server_ip": vps.ip,
        "worker_id": worker.id if worker else None,
        "worker_version": worker.worker_version if worker else None,
        "worker_status": worker_runtime_status(worker) if worker else "missing",
        "preflight_command_id": command.id if command else None,
        "preflight_status": command.status if command else "missing",
        "preflight_completed_at": command.completed_at.isoformat() if command and command.completed_at else None,
        "os_release": system.get("os_release") if isinstance(system, dict) else None,
        "architecture": system.get("architecture") if isinstance(system, dict) else None,
        "worker_running_user": system.get("worker_running_user") if isinstance(system, dict) else None,
        "configured_interface": configured_interface,
        "worker_config_interface": configured_interface,
        "detected_default_interface": default_interface,
        "default_route_interface": default_interface,
        "default_route_gateway": network.get("default_route_gateway") if isinstance(network, dict) else None,
        "primary_interface": primary_interface,
        "primary_interface_ip": primary_interface_ip,
        "interface_mismatch": mismatch,
        "listening_summary": ports.get("listening_summary") if isinstance(ports, dict) else None,
        "listening_count": ports.get("listening_count") if isinstance(ports, dict) else None,
        "important_ports": ports.get("important_ports") if isinstance(ports, dict) else None,
        "xray_installed": service_installed(result, "xray"),
        "xray_existing_config_detected": xray_existing_config_detected(result),
    }


def build_landing_node_plan(
    *,
    db: Session,
    vps: VpsServer,
    worker: Worker | None,
    payload: LandingNodePlanRequest,
) -> dict[str, Any]:
    command = latest_landing_preflight(db, vps.id)
    summary = preflight_summary(vps=vps, worker=worker, command=command)
    blocked_reasons: list[str] = []
    warnings: list[str] = []
    confirmations: list[str] = []

    if not worker:
        blocked_reasons.append("worker_offline")
    else:
        if worker_runtime_status(worker) != "online":
            blocked_reasons.append("worker_offline")
        if not worker_supports_command_channel(worker, "landing_preflight"):
            blocked_reasons.append("worker_not_command_capable")

    if payload.require_preflight_success and not command:
        blocked_reasons.append("preflight_missing")

    configured_interface = summary.get("configured_interface")
    detected_interface = summary.get("detected_default_interface")
    primary_interface_ip = summary.get("primary_interface_ip")
    if summary.get("interface_mismatch"):
        blocked_reasons.append("interface_mismatch")
        warnings.append(
            f"检测到 Worker 配置网卡 {configured_interface or '未知'} 与系统默认公网网卡 {detected_interface or '未知'} 不一致。正式创建节点前需修复网卡识别或重新安装 Worker 时选择正确网卡。"
        )
    elif configured_interface and not primary_interface_ip:
        warnings.append("Worker 未返回 primary_interface_ip，正式创建前需确认公网网卡识别正确。")

    if payload.listen_port < SAFE_PORT_MIN or payload.listen_port > SAFE_PORT_MAX or payload.listen_port in BLOCKED_MANAGEMENT_PORTS:
        blocked_reasons.append("unsafe_port")
    elif payload.listen_port in {443, 8443, 18443}:
        warnings.append(f"端口 {payload.listen_port} 可作为候选端口，但正式使用前必须单独确认云安全组 / 云防火墙 / 服务器防火墙。")

    if command:
        port_status = important_port_status(command.result_json or {}, payload.listen_port)
        if port_status == "listening":
            blocked_reasons.append("port_already_listening")

    if summary.get("xray_existing_config_detected") and not payload.allow_overwrite_existing_config:
        blocked_reasons.append("xray_existing_config_detected")

    if payload.require_manual_cloud_firewall_confirmation:
        if not payload.cloud_security_group_confirmed or not payload.cloud_firewall_confirmed or not payload.server_firewall_confirmed:
            blocked_reasons.append("missing_cloud_firewall_confirmation")
        confirmations.extend(
            [
                "已确认云服务器安全组放行计划 TCP 端口",
                "已确认云防火墙放行计划 TCP 端口",
                "已确认服务器本机防火墙放行计划 TCP 端口",
            ]
        )

    if not payload.allow_install_xray:
        confirmations.append("正式执行前需人工批准安装 Xray-core")
    if not payload.allow_generate_share_link:
        blocked_reasons.append("share_link_generation_not_approved")
        confirmations.append("正式执行前需人工批准生成分享链接")
    if not payload.allow_modify_firewall:
        confirmations.append("正式执行前需人工批准是否修改服务器本机防火墙")
    if not payload.allow_overwrite_existing_config:
        confirmations.append("正式执行前需确认不覆盖已有 Xray 配置；如需覆盖必须单独审批")

    blocked_reasons = sorted(set(blocked_reasons))
    warnings = sorted(set(warnings))

    return {
        "plan_id": f"dryrun-{uuid.uuid4()}",
        "server_id": vps.id,
        "mode": "dry_run",
        "ready": len(blocked_reasons) == 0,
        "will_install_xray": bool(payload.allow_install_xray),
        "will_create_config": False,
        "will_open_local_firewall": bool(payload.allow_modify_firewall),
        "will_modify_cloud_security_group": False,
        "listen_port": payload.listen_port,
        "protocol": payload.protocol,
        "security": payload.security,
        "flow": payload.flow,
        "server_name": payload.server_name,
        "dest": payload.dest,
        "key_generation_strategy": {
            "uuid": "future_worker_generates_at_execution_time",
            "reality_private_key": "future_worker_generates_at_execution_time_and_never_returns_private_key",
            "reality_public_key": "future_worker_returns_public_key_only_after_approved_execution",
            "short_id": "future_worker_generates_random_hex_short_id_at_execution_time",
        },
        "required_user_confirmations": confirmations,
        "preflight_summary": summary,
        "warnings": warnings,
        "blocked_reasons": blocked_reasons,
        "next_stage_required": DEFAULT_NEXT_STAGE,
        "safety_boundary": [
            "本阶段只生成 dry-run 计划",
            "不安装 Xray",
            "不写入 Xray 配置",
            "不创建节点",
            "不新增监听端口",
            "不修改服务器防火墙",
            "不修改云服务器安全组",
            "不修改 node.share_link",
            "不生成真实可用节点链接",
            "不执行 cutover",
        ],
    }
