from datetime import UTC, datetime
from urllib.parse import quote, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.db.session import get_db
from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand
from app.schemas.common import error_response, success_response
from app.schemas.remote_cleanup import OFFLINE_LOCAL_REMOVE_CONFIRMATION, RemoteCleanupDeleteRequest
from app.schemas.transit_route import (
    APPROVED_LANDING_NODE_ID,
    APPROVED_LANDING_TARGET_HOST,
    APPROVED_LANDING_TARGET_PORT,
    APPROVED_TRANSIT_INTERFACE_NAME,
    APPROVED_TRANSIT_LISTEN_PORT,
    APPROVED_TRANSIT_CANDIDATE_NAME,
    APPROVED_TRANSIT_ROUTE_NAME,
    APPROVED_TRANSIT_RESOURCE_ID,
    APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE,
    APPROVED_TRANSIT_SERVICE_NAME,
    APPROVED_TRANSIT_ROUTE_CREATE_STAGE,
    FORWARDING_METHOD_HAPROXY_TCP,
    FORWARDING_METHOD_SOCAT,
    HAPROXY_ROUTE_CREATE_DRY_RUN_STAGE,
    HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_STAGE,
    HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
    HAPROXY_ROUTE_CREATE_REAL_EXECUTION_STAGE,
    HAPROXY_ROUTE_CREATE_REAL_EXECUTION_TEXT,
    PROTECTED_CREATE_PORT_MESSAGES,
    PROTECTED_CREATE_PORTS,
    ReadonlyPreflightPlanCheck,
    ReadonlyPreflightPlanRequest,
    ReadonlyPreflightPlanResponse,
    TransitHaproxyReadinessApprovalRequest,
    TransitHaproxyRouteCreateDryRunRequest,
    TransitHaproxyRouteCreateFinalApprovalRequest,
    TransitHaproxyRouteCreateRealExecutionRequest,
    TransitReadonlyPreflightCommandRequest,
    TransitRouteCandidateExportRequest,
    TransitRouteWorkerCreateExecuteRequest,
    TransitRouteWorkerCreatePlanRequest,
)
from app.services.auth_service import record_audit
from app.services.redaction import mask_share_link
from app.services.worker_commands import create_worker_command, serialize_worker_command
from app.services.remote_cleanup_delete import (
    RemoteCleanupError,
    create_transit_route_cleanup_command,
    offline_local_remove_transit_route,
    remote_cleanup_unavailable_offer,
)
from app.services.share_link_compat import ensure_vless_tcp_header_type_none
from app.services.worker_binding import worker_runtime_status
from app.services.worker_targeting import (
    WorkerTargetError,
    minimum_worker_version_for_command,
    minimum_worker_version_for_transit_forwarding_method,
    resolve_command_target_worker,
    worker_supports_transit_forwarding_method,
)

router = APIRouter()


TRANSIT_READONLY_PREFLIGHT_COMMAND = "transit_readonly_preflight"
TRANSIT_ROUTE_CREATE_COMMAND = "transit_route_create"
TRANSIT_ROUTE_CREATE_FORWARDING_METHODS = {
    FORWARDING_METHOD_SOCAT,
    FORWARDING_METHOD_HAPROXY_TCP,
}
TRANSIT_READONLY_PREFLIGHT_BOUNDARY = [
    "remote readonly preflight only",
    "no arbitrary shell accepted",
    "no real forwarding route created",
    "no socat/gost install, start, stop, or restart",
    "no real listening port added",
    "no firewall or cloud security group change",
    "no Xray modification",
    "no nodes.share_link read or modification",
    "no full client link export",
    "no cutover",
]
TRANSIT_ROUTE_CREATE_DRY_RUN_BOUNDARY = [
    "dry-run plan only",
    "approval required before real execution",
    "no arbitrary shell accepted",
    "no systemd unit content accepted from API",
    "fixed LiveLine-owned forwarding template only",
    "no real transit route created",
    "no socat/gost install, start, stop, or restart",
    "no listener binding",
    "no firewall or cloud security group change",
    "no Xray modification",
    "no nodes.share_link read or modification",
    "no full client link export",
    "no cutover",
]
TRANSIT_ROUTE_CREATE_REAL_BOUNDARY = [
    "protected real create only after matching active resources, online Worker, and successful readonly preflight",
    "no arbitrary shell accepted",
    "no systemd unit content accepted from API",
    "fixed LiveLine-owned forwarding template only",
    "no nodes.share_link read or modification",
    "no full client link export",
    "no Xray modification",
    "no landing node configuration modification",
    "no firewall or cloud security group change",
    "no cutover",
]
TRANSIT_RESOURCE_CREATE_STATUSES = {"active", "worker_online"}
READONLY_PREFLIGHT_SAFETY_BOUNDARY = [
    "readonly preflight plan only",
    "no SSH executed",
    "no remote commands executed",
    "no remote server connection",
    "no database write",
    "no task created",
    "no temp credential written",
    "no real forwarding created",
    "no real listening port added",
    "no node.share_link modification",
    "no cutover",
]
TRANSIT_CANDIDATE_EXPORT_BOUNDARY = [
    "transient candidate export only",
    "no database write",
    "no nodes.share_link mutation",
    "no transit_routes.share_link mutation",
    "no original direct node replacement",
    "no full link stored in audit logs",
    "no Worker command created",
    "no socat restart, stop, disable, or delete",
    "no Xray modification",
    "no firewall or cloud security group change",
    "no cutover",
]
HAPROXY_READINESS_RESERVED_PORTS = PROTECTED_CREATE_PORTS | {80, 443, 3200, 8200, 15432, 16379}
HAPROXY_READINESS_SAFETY_BOUNDARY = [
    "read-only HAProxy TCP route creation readiness approval only",
    "no Worker command created",
    "no HAProxy route created",
    "no HAProxy install, start, stop, or restart",
    "no listener binding",
    "no firewall, cloud firewall, or cloud security group mutation",
    "no socat service modification",
    "no Xray modification",
    "no nodes.share_link read or mutation",
    "no transit_routes.share_link write",
    "no full client link export",
    "no cutover",
]
HAPROXY_ROUTE_CREATE_DRY_RUN_BOUNDARY = [
    "HAProxy TCP route create dry-run only",
    "dry-run Worker command only",
    "approval required before real execution",
    "no real execution command created",
    "no HAProxy route created",
    "no TransitRoute active record created",
    "no HAProxy install, start, stop, or restart",
    "no listener binding",
    "no firewall, cloud firewall, or cloud security group mutation",
    "no socat service modification",
    "no Xray modification",
    "no nodes.share_link read or mutation",
    "no transit_routes.share_link write",
    "no full client link export",
    "no cutover",
]
HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_BOUNDARY = [
    "final approval package only",
    "read existing dry-run command summary only",
    "no Worker command created",
    "no real execution command created",
    "no HAProxy route created",
    "no TransitRoute active record created",
    "no HAProxy install, start, stop, or restart",
    "no listener binding",
    "no firewall, cloud firewall, or cloud security group mutation",
    "no SSH or remote execution",
    "no nodes.share_link read or mutation",
    "no transit_routes.share_link write",
    "no full client link export",
    "no cutover",
]
HAPROXY_ROUTE_CREATE_REAL_EXECUTION_BOUNDARY = [
    "protected HAProxy TCP real execution command creation only",
    "requires succeeded Stage 3.3.137 dry-run command",
    "requires Stage 3.3.138 final approval confirmation",
    "fixed HAProxy TCP route parameters only",
    "no arbitrary shell accepted",
    "no systemd unit content accepted from API",
    "no TransitRoute active record created by this request",
    "no nodes.share_link read or mutation",
    "no transit_routes.share_link write",
    "no full client link export",
    "no firewall, cloud firewall, or cloud security group mutation",
    "no Xray modification",
    "no cutover",
]


def redact_hint(value: str | None) -> str:
    if not value:
        return "Pending confirmation"
    cleaned = value.strip()
    lowered = cleaned.lower()
    if "://" in lowered or "begin " in lowered or "private key" in lowered:
        return "[redacted sensitive value]"
    if len(cleaned) > 80:
        return f"{cleaned[:40]}...{cleaned[-12:]}"
    return cleaned


def parse_optional_port(value: int | str | None) -> tuple[int | None, str | None]:
    if value is None:
        return None, "端口尚未填写。"
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None, "端口尚未填写。"
        if not stripped.isdigit():
            return None, "端口必须是 1-65535 之间的整数。"
        value = int(stripped)
    if not isinstance(value, int) or isinstance(value, bool):
        return None, "端口必须是 1-65535 之间的整数。"
    if value < 1 or value > 65535:
        return value, "端口必须是 1-65535 之间的整数。"
    return value, None


def make_preflight_check(
    *,
    check_id: str,
    label: str,
    category: str,
    passed: bool,
    message: str,
    next_action: str,
    status: str | None = None,
    evidence_summary: str | None = None,
) -> ReadonlyPreflightPlanCheck:
    resolved_status = status or ("passed" if passed else "blocked")
    return ReadonlyPreflightPlanCheck(
        id=check_id,
        label=label,
        category=category,
        status=resolved_status,
        passed=passed,
        message=message,
        evidence_summary=evidence_summary or message,
        next_action=next_action,
        sensitive_output_redacted=True,
    )


def make_haproxy_readiness_check(
    *,
    check_id: str,
    label: str,
    passed: bool,
    message: str,
    next_action: str,
    category: str = "readiness",
    evidence_summary: str | None = None,
) -> dict:
    return {
        "id": check_id,
        "label": label,
        "category": category,
        "status": "passed" if passed else "blocked",
        "passed": passed,
        "message": message,
        "evidence_summary": evidence_summary or ("confirmed" if passed else "missing_or_blocked"),
        "next_action": next_action,
        "sensitive_output_redacted": True,
    }


def latest_bound_worker(db: Session, *, server_id: str | None) -> Worker | None:
    if not server_id:
        return None
    workers = db.scalars(select(Worker).where(Worker.server_id == server_id)).all()
    if not workers:
        return None
    epoch = datetime.min.replace(tzinfo=UTC)
    return sorted(
        workers,
        key=lambda worker: (
            worker.last_heartbeat_at or epoch,
            worker.registered_at or epoch,
            worker.created_at or epoch,
        ),
        reverse=True,
    )[0]


def build_haproxy_readiness_approval(
    db: Session,
    payload: TransitHaproxyReadinessApprovalRequest,
) -> dict:
    resource = db.get(TransitResource, payload.transit_resource_id)
    node = db.get(Node, payload.landing_node_id)
    worker = latest_bound_worker(db, server_id=resource.id if resource else None)
    landing_host = node.vps.ip if node and node.vps else None
    worker_status = worker_runtime_status(worker) if worker else "missing"
    forwarding_method_ok = payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP
    listen_port_allowed = payload.planned_listen_port not in HAPROXY_READINESS_RESERVED_PORTS
    landing_target_port_matches = bool(node and node.xray_port and node.xray_port == payload.landing_target_port)
    worker_version_supported = worker_supports_transit_forwarding_method(worker, FORWARDING_METHOD_HAPROXY_TCP)

    checks = [
        make_haproxy_readiness_check(
            check_id="transit_resource_exists",
            label="中转资源存在",
            passed=resource is not None,
            message="中转资源记录存在。" if resource else "中转资源记录不存在。",
            next_action="选择已登记的中转服务器。" if not resource else "继续检查。",
            evidence_summary=resource.name if resource else None,
        ),
        make_haproxy_readiness_check(
            check_id="transit_resource_not_deleted",
            label="中转资源未删除",
            passed=bool(resource and resource.deleted_at is None),
            message="中转资源未删除。" if resource and resource.deleted_at is None else "中转资源已删除或不可用。",
            next_action="选择未删除的中转服务器。" if not resource or resource.deleted_at is not None else "继续检查。",
            evidence_summary=resource.status if resource else None,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_found",
            label="找到绑定 Worker",
            passed=worker is not None,
            message="已找到绑定 Worker。" if worker else "该中转资源尚未绑定 Worker。",
            next_action="完成 Worker 安装并等待心跳。" if not worker else "继续检查。",
            evidence_summary=worker.id if worker else None,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_online",
            label="Worker 在线",
            passed=bool(worker and worker.status == "online" and worker_status == "online"),
            message="Worker 在线。" if worker and worker.status == "online" and worker_status == "online" else "Worker 不在线或心跳过期。",
            next_action="等待 Worker heartbeat 恢复 online。" if not worker or worker_status != "online" else "继续检查。",
            evidence_summary=worker_status,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_role_is_transit",
            label="Worker role 为 transit",
            passed=bool(worker and worker.role == "transit"),
            message="Worker role 正确。" if worker and worker.role == "transit" else "Worker role 不是 transit。",
            next_action="使用 transit role Worker。" if not worker or worker.role != "transit" else "继续检查。",
            evidence_summary=worker.role if worker else None,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_version_supported",
            label="Worker 版本支持 HAProxy TCP",
            passed=worker_version_supported,
            message="Worker 版本支持 HAProxy TCP。" if worker_version_supported else "Worker 版本不支持 HAProxy TCP。",
            next_action=(
                f"升级 Worker 到 {minimum_worker_version_for_transit_forwarding_method(FORWARDING_METHOD_HAPROXY_TCP)} 或更高版本。"
                if not worker_version_supported
                else "继续检查。"
            ),
            evidence_summary=worker.worker_version if worker else None,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_interface_detected",
            label="Worker 已上报网卡",
            passed=bool(worker and worker.interface_name),
            message="Worker 已上报 interface_name。" if worker and worker.interface_name else "Worker 未上报 interface_name。",
            next_action="等待 Worker heartbeat 上报 interface_name。" if not worker or not worker.interface_name else "继续检查。",
            evidence_summary=worker.interface_name if worker else None,
        ),
        make_haproxy_readiness_check(
            check_id="landing_node_exists",
            label="落地节点存在",
            passed=bool(node and node.deleted_at is None),
            message="落地节点存在且未删除。" if node and node.deleted_at is None else "落地节点不存在或已删除。",
            next_action="选择 active 的落地节点。" if not node or node.deleted_at is not None else "继续检查。",
            evidence_summary=node.node_name if node else None,
        ),
        make_haproxy_readiness_check(
            check_id="landing_node_has_target_host",
            label="落地节点有目标地址",
            passed=bool(landing_host),
            message="落地节点有目标地址。" if landing_host else "落地节点缺少 VPS IP。",
            next_action="确认落地服务器 IP 已登记。" if not landing_host else "继续检查。",
            evidence_summary=landing_host,
        ),
        make_haproxy_readiness_check(
            check_id="landing_target_port_valid",
            label="落地目标端口有效",
            passed=landing_target_port_matches,
            message="落地目标端口与节点端口一致。" if landing_target_port_matches else "落地目标端口无效或与节点端口不一致。",
            next_action="使用当前落地节点的 Xray 端口。" if not landing_target_port_matches else "继续检查。",
            evidence_summary=str(node.xray_port) if node and node.xray_port else None,
        ),
        make_haproxy_readiness_check(
            check_id="planned_listen_port_valid",
            label="计划监听端口有效",
            passed=listen_port_allowed,
            message="计划监听端口可进入审批。" if listen_port_allowed else "计划监听端口属于保留端口，不能进入审批。",
            next_action="更换非保留监听端口。" if not listen_port_allowed else "继续检查。",
            evidence_summary=str(payload.planned_listen_port),
        ),
        make_haproxy_readiness_check(
            check_id="forwarding_method_is_haproxy_tcp",
            label="转发方式为 HAProxy TCP",
            passed=forwarding_method_ok,
            message="转发方式为 haproxy_tcp。" if forwarding_method_ok else "转发方式不是 haproxy_tcp。",
            next_action="选择 HAProxy TCP mode。" if not forwarding_method_ok else "继续检查。",
            evidence_summary=payload.forwarding_method,
        ),
        make_haproxy_readiness_check(
            check_id="security_group_confirmation_present",
            label="云安全组确认",
            passed=payload.firewall_security_group_confirmed,
            message="已确认云安全组放行。" if payload.firewall_security_group_confirmed else "尚未确认云安全组放行。",
            next_action="人工确认云安全组已放行监听 TCP 端口。" if not payload.firewall_security_group_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="cloud_firewall_confirmation_present",
            label="云防火墙确认",
            passed=payload.cloud_firewall_confirmed,
            message="已确认云防火墙放行。" if payload.cloud_firewall_confirmed else "尚未确认云防火墙放行。",
            next_action="人工确认云防火墙已放行监听 TCP 端口。" if not payload.cloud_firewall_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="server_firewall_confirmation_present",
            label="服务器本机防火墙确认",
            passed=payload.server_firewall_confirmed,
            message="已确认服务器本机防火墙放行。" if payload.server_firewall_confirmed else "尚未确认服务器本机防火墙放行。",
            next_action="人工确认服务器本机防火墙已放行监听 TCP 端口。" if not payload.server_firewall_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="no_cutover_confirmed",
            label="不 cutover 确认",
            passed=payload.no_cutover_confirmed,
            message="已确认不 cutover。" if payload.no_cutover_confirmed else "尚未确认不 cutover。",
            next_action="确认本阶段不切换默认入口。" if not payload.no_cutover_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="no_share_link_mutation_confirmed",
            label="不修改 share_link 确认",
            passed=payload.no_node_share_link_change_confirmed,
            message="已确认不修改 nodes.share_link。" if payload.no_node_share_link_change_confirmed else "尚未确认不修改 nodes.share_link。",
            next_action="确认本阶段不读取或修改 nodes.share_link。" if not payload.no_node_share_link_change_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="no_full_client_link_confirmed",
            label="不导出完整客户端链接确认",
            passed=payload.no_full_client_link_confirmed,
            message="已确认不导出完整客户端链接。" if payload.no_full_client_link_confirmed else "尚未确认不导出完整客户端链接。",
            next_action="确认本阶段不生成或展示完整客户端链接。" if not payload.no_full_client_link_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="worker_command_not_created",
            label="未创建 Worker command",
            passed=True,
            message="本接口只读，不创建 Worker command。",
            next_action="后续真实创建必须另行审批。",
            category="safety_boundary",
            evidence_summary="no db write",
        ),
        make_haproxy_readiness_check(
            check_id="haproxy_not_created",
            label="未创建 HAProxy route",
            passed=True,
            message="本接口不会创建 HAProxy route 或监听端口。",
            next_action="后续真实创建必须另行审批。",
            category="safety_boundary",
            evidence_summary="readiness only",
        ),
        make_haproxy_readiness_check(
            check_id="firewall_not_modified",
            label="未修改防火墙",
            passed=True,
            message="本接口不会修改云安全组、云防火墙或服务器防火墙。",
            next_action="端口放行仍由用户人工确认。",
            category="safety_boundary",
            evidence_summary="readiness only",
        ),
    ]
    ready = all(check["passed"] for check in checks)
    route_name = f"haproxy-tcp-{payload.planned_listen_port}"
    return {
        "ready": ready,
        "blocked": not ready,
        "status": "ready" if ready else "blocked",
        "summary": (
            "HAProxy TCP route 创建审批包已满足只读 readiness 条件。"
            if ready
            else "HAProxy TCP route 创建审批包仍有阻塞项。"
        ),
        "next_action": (
            "可以进入下一阶段，由用户再次明确授权后创建 HAProxy TCP route。"
            if ready
            else "先处理 blocked 检查项；本阶段不会创建 Worker command 或 HAProxy route。"
        ),
        "transit_resource": {
            "id": resource.id if resource else payload.transit_resource_id,
            "name": resource.name if resource else None,
            "entry_host": resource.entry_host if resource else None,
            "status": resource.status if resource else "missing",
            "deleted": bool(resource and resource.deleted_at is not None),
        },
        "transit_worker": {
            "id": worker.id if worker else None,
            "role": worker.role if worker else None,
            "status": worker_status,
            "worker_version": worker.worker_version if worker else None,
            "interface_name": worker.interface_name if worker else None,
            "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(
                FORWARDING_METHOD_HAPROXY_TCP
            ),
        },
        "landing_node": {
            "id": node.id if node else payload.landing_node_id,
            "name": node.node_name if node else None,
            "target_host": landing_host,
            "target_port": node.xray_port if node else None,
            "status": node.status if node else "missing",
        },
        "planned_route": {
            "route_name": route_name,
            "planned_listen_port": payload.planned_listen_port,
            "landing_target_host": landing_host,
            "landing_target_port": payload.landing_target_port,
            "forwarding_method": payload.forwarding_method,
            "purpose": payload.purpose,
            "service_name": f"liveline-haproxy-{payload.planned_listen_port}.service",
            "dry_readiness_only": True,
        },
        "checks": checks,
        "safety_boundary": HAPROXY_READINESS_SAFETY_BOUNDARY,
    }


def _payload_int(payload: dict | None, key: str) -> int | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _payload_text(payload: dict | None, key: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if value is None:
        return None
    return str(value).strip()


def has_matching_successful_transit_readonly_preflight(
    db: Session,
    *,
    transit_resource_id: str,
    landing_node_id: str,
    planned_listen_port: int,
    landing_target_host: str,
    landing_target_port: int,
    forwarding_method: str,
) -> bool:
    return (
        find_matching_successful_transit_readonly_preflight(
            db,
            transit_resource_id=transit_resource_id,
            landing_node_id=landing_node_id,
            planned_listen_port=planned_listen_port,
            landing_target_host=landing_target_host,
            landing_target_port=landing_target_port,
            forwarding_method=forwarding_method,
        )
        is not None
    )


def recent_successful_transit_readonly_preflights(db: Session, transit_resource_id: str) -> list[WorkerCommand]:
    commands = db.scalars(
        select(WorkerCommand)
        .where(WorkerCommand.command_type == TRANSIT_READONLY_PREFLIGHT_COMMAND)
        .where(WorkerCommand.status == "succeeded")
        .where(WorkerCommand.server_type == "transit")
        .where(WorkerCommand.server_id == transit_resource_id)
        .order_by(WorkerCommand.completed_at.desc().nullslast(), WorkerCommand.created_at.desc())
        .limit(20)
    ).all()
    return list(commands)


def find_matching_successful_transit_readonly_preflight(
    db: Session,
    *,
    transit_resource_id: str,
    landing_node_id: str,
    planned_listen_port: int,
    landing_target_host: str,
    landing_target_port: int,
    forwarding_method: str,
) -> WorkerCommand | None:
    commands = recent_successful_transit_readonly_preflights(db, transit_resource_id)
    for command in commands:
        payload = command.payload_json if isinstance(command.payload_json, dict) else {}
        result = command.result_json if isinstance(command.result_json, dict) else {}
        if _payload_text(payload, "transit_resource_id") != transit_resource_id:
            continue
        if _payload_text(payload, "landing_node_id") != landing_node_id:
            continue
        if _payload_int(payload, "planned_listen_port") != planned_listen_port:
            continue
        if _payload_text(payload, "landing_target_host") != landing_target_host:
            continue
        if _payload_int(payload, "landing_target_port") != landing_target_port:
            continue
        if _payload_text(payload, "forwarding_method") != forwarding_method:
            continue
        if result.get("passed") is True or result.get("status") == "passed":
            return command
    return None


def preflight_interface_name(command: WorkerCommand | None) -> str | None:
    if command is None or not isinstance(command.result_json, dict):
        return None
    result = command.result_json
    nested_sources = [
        result,
        result.get("network") if isinstance(result.get("network"), dict) else {},
        result.get("system") if isinstance(result.get("system"), dict) else {},
    ]
    for source in nested_sources:
        if not isinstance(source, dict):
            continue
        for key in (
            "interface_name",
            "worker_config_interface",
            "default_route_interface",
            "primary_interface",
        ):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def has_in_flight_transit_route_create_command(db: Session, transit_resource_id: str) -> bool:
    command = db.scalar(
        select(WorkerCommand)
        .where(WorkerCommand.command_type == TRANSIT_ROUTE_CREATE_COMMAND)
        .where(WorkerCommand.server_type == "transit")
        .where(WorkerCommand.server_id == transit_resource_id)
        .where(WorkerCommand.status.in_(("pending", "running", "claimed")))
        .order_by(WorkerCommand.created_at.desc())
    )
    return command is not None


def future_preflight_check(check_id: str, label: str, category: str) -> ReadonlyPreflightPlanCheck:
    return make_preflight_check(
        check_id=check_id,
        label=label,
        category=category,
        passed=False,
        status="skipped",
        message="future check / not executed in this stage",
        evidence_summary="No remote evidence collected.",
        next_action="Enter a separately authorized Workbuddy read-only preflight stage before executing this check.",
    )


def build_readonly_preflight_plan(payload: ReadonlyPreflightPlanRequest) -> ReadonlyPreflightPlanResponse:
    planned_port, planned_port_error = parse_optional_port(payload.planned_listen_port)
    landing_port, landing_port_error = parse_optional_port(payload.landing_target_port)
    protected_port_message = PROTECTED_CREATE_PORT_MESSAGES.get(planned_port or 0)
    planned_port_valid = planned_port is not None and planned_port_error is None
    planned_port_not_reserved = planned_port_valid and planned_port not in PROTECTED_CREATE_PORTS
    firewall_confirmations_present = (
        payload.firewall_security_group_confirmed
        and payload.cloud_firewall_confirmed
        and payload.server_firewall_confirmed
    )

    checks = [
        make_preflight_check(
            check_id="transit_resource_selected",
            label="Transit resource selected",
            category="local_input",
            passed=bool(payload.transit_resource_id),
            message="Transit resource is selected." if payload.transit_resource_id else "Transit resource is missing.",
            next_action="Select a transit resource before requesting read-only preflight.",
        ),
        make_preflight_check(
            check_id="landing_node_selected",
            label="Landing node selected",
            category="local_input",
            passed=bool(payload.landing_node_id),
            message="Landing node is selected." if payload.landing_node_id else "Landing node is missing.",
            next_action="Select an active landing node before requesting read-only preflight.",
        ),
        make_preflight_check(
            check_id="planned_port_valid",
            label="Planned listen port is valid",
            category="port_safety",
            passed=planned_port_valid,
            message="Planned listen port is a valid TCP port." if planned_port_valid else (planned_port_error or "Planned listen port is invalid."),
            next_action="Use an integer TCP port from 1 to 65535.",
        ),
        make_preflight_check(
            check_id="planned_port_not_reserved",
            label="Planned listen port is not reserved",
            category="port_safety",
            passed=planned_port_not_reserved,
            message=(
                "Planned listen port is not reserved."
                if planned_port_not_reserved
                else protected_port_message or "Planned listen port must avoid protected ports."
            ),
            next_action="Avoid 22, 8443, 18443, and 20575.",
        ),
        make_preflight_check(
            check_id="landing_target_port_valid",
            label="Landing target port is valid",
            category="port_safety",
            passed=landing_port is not None and landing_port_error is None,
            message="Landing target port is valid." if landing_port is not None and landing_port_error is None else (landing_port_error or "Landing target port is invalid."),
            next_action="Use an integer TCP port from 1 to 65535.",
        ),
        make_preflight_check(
            check_id="firewall_confirmations_present",
            label="Firewall confirmations are present",
            category="firewall",
            passed=firewall_confirmations_present,
            message="Cloud security group, cloud firewall, and server firewall are confirmed." if firewall_confirmations_present else "Firewall confirmations are incomplete.",
            next_action="Confirm cloud security group, cloud firewall, and server firewall allow the planned TCP port.",
        ),
        make_preflight_check(
            check_id="local_backup_confirmed",
            label="Local database backup confirmed",
            category="local_safety",
            passed=payload.local_backup_confirmed,
            message="Local database backup is confirmed." if payload.local_backup_confirmed else "Local database backup is not confirmed.",
            next_action="Run and verify a local database backup before requesting read-only preflight.",
        ),
        make_preflight_check(
            check_id="user_approved_readonly_preflight",
            label="User approved read-only preflight",
            category="authorization",
            passed=payload.user_approved_readonly_preflight,
            message="User approval for read-only preflight is present." if payload.user_approved_readonly_preflight else "User approval for read-only preflight is missing.",
            next_action="Confirm that the request is only for read-only preflight.",
        ),
        make_preflight_check(
            check_id="no_cutover_confirmed",
            label="No cutover confirmed",
            category="authorization",
            passed=payload.no_cutover_confirmed,
            message="No-cutover boundary is confirmed." if payload.no_cutover_confirmed else "No-cutover boundary is not confirmed.",
            next_action="Confirm that this request will not perform cutover.",
        ),
        make_preflight_check(
            check_id="no_node_share_link_change_confirmed",
            label="No node.share_link change confirmed",
            category="authorization",
            passed=payload.no_node_share_link_change_confirmed,
            message="No node.share_link change boundary is confirmed." if payload.no_node_share_link_change_confirmed else "No node.share_link change boundary is not confirmed.",
            next_action="Confirm that node.share_link will not be read or modified.",
        ),
        make_preflight_check(
            check_id="workbuddy_authorization_status",
            label="Workbuddy authorization status",
            category="authorization",
            passed=payload.workbuddy_authorized,
            message="Workbuddy read-only preflight authorization is present." if payload.workbuddy_authorized else "Workbuddy read-only preflight authorization is missing.",
            next_action="Obtain explicit Workbuddy authorization before any future remote read-only execution.",
        ),
        future_preflight_check("future_transit_reachable", "Transit server reachable", "future_remote"),
        future_preflight_check("future_planned_port_available", "Planned port available", "future_remote"),
        future_preflight_check("future_formal_socat_18443_preserved", "Formal socat 18443 preserved", "future_route_safety"),
        future_preflight_check("future_fallback_gost_8443_preserved", "Fallback gost 8443 preserved", "future_route_safety"),
        future_preflight_check("future_transit_to_landing_tcp_connectivity", "Transit to landing TCP connectivity", "future_remote"),
    ]

    required_checks = [check for check in checks if not check.id.startswith("future_")]
    ready = all(check.passed for check in required_checks)
    structural_blocked = any(
        not check.passed
        for check in checks
        if check.id in {
            "transit_resource_selected",
            "landing_node_selected",
            "planned_port_valid",
            "planned_port_not_reserved",
            "landing_target_port_valid",
        }
    )
    status = "ready" if ready else ("blocked" if structural_blocked else "no_go")
    summary = (
        "Ready for readonly preflight approval / execution stage. This does not authorize real forwarding."
        if ready
        else "Readonly preflight plan is No-Go. No remote execution is authorized."
    )
    next_action = (
        "Proceed only to a separately authorized read-only preflight execution stage."
        if ready
        else "Resolve blocked or No-Go checks before requesting read-only preflight execution approval."
    )
    redacted_summary = "\n".join(
        [
            "LiveLine readonly preflight no-op plan",
            f"Status: {status}",
            f"Transit resource: {redact_hint(payload.transit_resource_name)}",
            f"Transit host hint: {redact_hint(payload.transit_host_hint)}",
            f"Landing node: {redact_hint(payload.landing_node_name)}",
            f"Landing host hint: {redact_hint(payload.landing_host_hint)}",
            f"Planned listen port: {planned_port if planned_port is not None else 'Pending confirmation'}",
            f"Landing target port: {landing_port if landing_port is not None else 'Pending confirmation'}",
            f"Purpose: {redact_hint(payload.route_purpose)}",
            "Remote execution: not performed by this API",
            "Real forwarding creation: not authorized",
            "node.share_link modification: not authorized",
            "Cutover: not authorized",
        ]
    )

    return ReadonlyPreflightPlanResponse(
        ready=ready,
        blocked=not ready,
        status=status,
        summary=summary,
        next_action=next_action,
        checks=checks,
        safety_boundary=READONLY_PREFLIGHT_SAFETY_BOUNDARY,
        redacted_summary=redacted_summary,
    )


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


def route_entry_host(route: TransitRoute) -> str | None:
    resource = route.transit_resource
    return resource.entry_host if resource and resource.entry_host else None


def is_exportable_candidate_route(route: TransitRoute) -> bool:
    return (
        route.deleted_at is None
        and route.status == "active"
        and route.forwarding_method in TRANSIT_ROUTE_CREATE_FORWARDING_METHODS
        and bool(route_entry_host(route))
        and route.listen_port > 0
        and route.target_port > 0
        and not bool(route.share_link)
    )


def candidate_summary_payload(route: TransitRoute) -> dict:
    resource = route.transit_resource
    node = route.node
    vps = route.landing_vps
    entry_host = route_entry_host(route) or ""
    return {
        "route_id": route.id,
        "route_name": route.name,
        "transit_resource_id": route.transit_resource_id,
        "transit_resource_name": resource.name if resource else None,
        "entry_host": entry_host,
        "listen_port": route.listen_port,
        "target_host": route.target_host,
        "target_port": route.target_port,
        "forwarding_method": route.forwarding_method,
        "service_name": route.service_name,
        "service_path": route.service_path,
        "status": route.status,
        "landing_node_id": route.node_id,
        "landing_node_name": node.node_name if node else None,
        "landing_vps_ip": vps.ip if vps else None,
        "route_share_link_present": bool(route.share_link),
        "share_link_present": bool(route.share_link),
        "recommended_candidate": True,
        "cutover_status": "not_cutover",
        "safety_boundary": TRANSIT_CANDIDATE_EXPORT_BOUNDARY,
    }


def build_transient_candidate_link(route: TransitRoute, node: Node) -> tuple[str | None, str | None]:
    entry_host = route_entry_host(route)
    if not entry_host:
        return None, "中转入口 IP 缺失，不能生成临时候选配置。"
    if not node.share_link:
        return None, "落地节点缺少已生成的客户端链接，不能临时导出中转配置。"

    parsed = urlsplit(node.share_link)
    if parsed.scheme.lower() != "vless" or "@" not in parsed.netloc or not parsed.query:
        return None, "落地节点客户端链接格式不完整，不能生成中转测试配置。"

    userinfo = parsed.netloc.rsplit("@", 1)[0]
    if not userinfo:
        return None, "落地节点客户端链接缺少 UUID，不能生成中转测试配置。"

    host = entry_host.strip()
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{userinfo}@{host}:{route.listen_port}"
    fragment = quote(route.name or APPROVED_TRANSIT_CANDIDATE_NAME, safe="")
    link = ensure_vless_tcp_header_type_none(urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, fragment)))
    return link, None


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


@router.delete("/{route_id}")
def delete_transit_route(
    route_id: str,
    request: Request,
    confirm: bool = False,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()
    if confirm is not True:
        return error_response(400, "CONFIRMATION_REQUIRED", "请确认删除中转链路记录。")

    route = get_route_or_error(db, route_id)
    if not route:
        return error_response(404, "TRANSIT_ROUTE_NOT_FOUND", "中转规则不存在。")
    if route.share_link:
        return error_response(
            409,
            "TRANSIT_ROUTE_CUTOVER_BLOCKED",
            "该中转链路处于 cutover 状态，本阶段不允许删除。",
        )

    route.status = "deleted"
    route.deleted_at = datetime.now(UTC)
    db.add(route)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="delete_transit_route_record",
        result="success",
        request=request,
        resource_type="transit_route",
        resource_id=route.id,
    )
    db.commit()

    return success_response(
        {
            "id": route.id,
            "deleted": True,
            "delete_mode": "soft_delete",
            "remote_action_performed": False,
            "message": "系统记录已删除；未执行远程清理。",
        },
        "系统记录已删除；未执行远程清理。",
    )


@router.post("/{route_id}/remote-cleanup-delete")
def remote_cleanup_delete_transit_route(
    route_id: str,
    payload: RemoteCleanupDeleteRequest,
    request: Request,
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

    if payload.confirm == OFFLINE_LOCAL_REMOVE_CONFIRMATION:
        try:
            result = offline_local_remove_transit_route(db, route)
            record_audit(
                db,
                admin_id=session.admin_id,
                action="offline_local_remove_transit_route",
                result="success",
                request=request,
                resource_type="transit_route",
                resource_id=route.id,
            )
            db.commit()
        except RemoteCleanupError as exc:
            db.rollback()
            return error_response(exc.status_code, exc.code, exc.message)
        return success_response(result, result["message"])

    try:
        command, worker = create_transit_route_cleanup_command(db, route)
        record_audit(
            db,
            admin_id=session.admin_id,
            action="create_cleanup_transit_route_command",
            result="success",
            request=request,
            resource_type="transit_route",
            resource_id=route.id,
        )
        db.commit()
        db.refresh(command)
    except RemoteCleanupError as exc:
        db.rollback()
        if offer := remote_cleanup_unavailable_offer(exc):
            return error_response(
                400,
                "REMOTE_CLEANUP_UNAVAILABLE",
                "Worker 离线，无法远程清理。可使用离线本地移除确认。",
                offer,
            )
        return error_response(exc.status_code, exc.code, exc.message)

    return success_response(
        {
            "command_id": command.id,
            "cleanup_type": "cleanup_transit_route",
            "status": "queued",
            "remote_cleanup_required": True,
            "system_record_delete_after_success": True,
            "command": serialize_worker_command(command, worker=worker),
            "message": "远程清理任务已创建，清理成功后将软删除系统记录。",
        },
        "远程清理任务已创建，清理成功后将软删除系统记录。",
    )


@router.get("/{route_id}/candidate-summary")
def get_transit_route_candidate_summary(
    route_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    if not require_admin_session(db, request):
        return auth_error()

    route = get_route_or_error(db, route_id)
    if not route:
        return error_response(404, "TRANSIT_ROUTE_NOT_FOUND", "中转规则不存在。")
    if route.status != "active":
        return error_response(400, "TRANSIT_ROUTE_NOT_ACTIVE", "只有 active 候选链路可以查看候选摘要。")
    if route.share_link:
        return error_response(409, "TRANSIT_ROUTE_CUTOVER_BLOCKED", "该中转链路已经写入分享链接，本接口只用于未 cutover 的临时导出。")

    return success_response(candidate_summary_payload(route), "candidate summary generated")


@router.post("/{route_id}/candidate-export")
def export_transit_route_candidate(
    route_id: str,
    payload: TransitRouteCandidateExportRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    if not payload.confirm_transient_export:
        return error_response(400, "TRANSIENT_EXPORT_CONFIRMATION_REQUIRED", "必须确认这是临时导出。")
    if not payload.confirm_no_database_write:
        return error_response(400, "NO_DATABASE_WRITE_CONFIRMATION_REQUIRED", "必须确认本次导出不写入数据库。")
    if not payload.confirm_no_share_link_mutation:
        return error_response(400, "NO_SHARE_LINK_MUTATION_CONFIRMATION_REQUIRED", "必须确认不修改 nodes.share_link。")
    if not payload.confirm_no_cutover:
        return error_response(400, "NO_CUTOVER_CONFIRMATION_REQUIRED", "必须确认本次导出不执行 cutover。")

    route = get_route_or_error(db, route_id)
    if not route:
        return error_response(404, "TRANSIT_ROUTE_NOT_FOUND", "中转规则不存在。")
    if route.status != "active":
        return error_response(400, "TRANSIT_ROUTE_NOT_ACTIVE", "只有 active 候选链路可以临时导出测试配置。")
    if route.share_link:
        return error_response(409, "TRANSIT_ROUTE_CUTOVER_BLOCKED", "该中转链路已经写入分享链接，本接口只用于未 cutover 的临时导出。")
    if not is_exportable_candidate_route(route):
        return error_response(400, "TRANSIT_ROUTE_NOT_EXPORTABLE", "该中转链路缺少临时导出所需的入口、端口或转发方式。")

    node = route.node
    if not node or node.deleted_at is not None:
        return error_response(404, "LANDING_NODE_NOT_FOUND", "候选链路关联的落地节点不存在。")
    if node.status != "active":
        return error_response(400, "LANDING_NODE_NOT_ACTIVE", "只有 active 落地节点可以临时导出测试配置。")
    if node.xray_port != route.target_port:
        return error_response(400, "LANDING_TARGET_PORT_MISMATCH", "落地节点端口与候选链路目标端口不一致。")

    candidate_link, link_error = build_transient_candidate_link(route, node)
    if not candidate_link:
        return error_response(409, "CANDIDATE_LINK_MATERIAL_INCOMPLETE", link_error or "候选配置参数不完整。")

    record_audit(
        db,
        admin_id=session.admin_id,
        action="export_transit_route_candidate",
        result="success",
        request=request,
        resource_type="transit_route",
        resource_id=route.id,
    )
    db.commit()

    return success_response(
        {
            "route_id": route.id,
            "route_name": route.name,
            "candidate_name": route.name,
            "server": route_entry_host(route),
            "port": route.listen_port,
            "protocol": node.protocol,
            "security": node.security,
            "network": node.transport or "tcp",
            "flow": node.flow,
            "sni": node.sni,
            "fingerprint": node.fingerprint,
            "reality_public_key_present": bool(node.reality_public_key),
            "reality_short_id_present": bool(node.reality_short_id),
            "uuid_present": bool(node.uuid),
            "masked_candidate_link": mask_share_link(candidate_link),
            "candidate_link": candidate_link,
            "export_mode": "transient",
            "persistence": "not_saved",
            "warning": "这是临时客户端链接，仅用于复制测试；不会写入数据库、覆盖原节点链接或执行 cutover。",
            "cutover_status": "not_cutover",
            "database_write_performed": False,
            "nodes_share_link_mutated": False,
            "transit_route_share_link_mutated": False,
            "safety_boundary": TRANSIT_CANDIDATE_EXPORT_BOUNDARY,
        },
        "候选测试配置已临时导出。本响应是唯一明文返回位置，请勿写入日志、文档或 PR。",
    )


@router.post("/readonly-preflight-plan")
def readonly_preflight_plan(
    payload: ReadonlyPreflightPlanRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if not require_admin_session(db, request):
        return auth_error()

    plan = build_readonly_preflight_plan(payload)
    return success_response(plan.model_dump(), "readonly preflight plan generated locally")


@router.post("/haproxy-readiness-approval")
def haproxy_readiness_approval(
    payload: TransitHaproxyReadinessApprovalRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    if not require_admin_session(db, request):
        return auth_error()

    result = build_haproxy_readiness_approval(db, payload)
    return success_response(
        result,
        "HAProxy TCP route 创建审批包已生成；本接口只读，未创建 Worker command、HAProxy route 或监听端口。",
    )


@router.post("/haproxy-route-create-dry-run")
def create_haproxy_route_create_dry_run(
    payload: TransitHaproxyRouteCreateDryRunRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    if not payload.readiness_approval_confirmed:
        return error_response(
            400,
            "HAPROXY_READINESS_APPROVAL_REQUIRED",
            "必须先确认 Stage 3.3.136 HAProxy readiness 审批包已通过。",
        )
    if not payload.dry_run:
        return error_response(400, "HAPROXY_ROUTE_DRY_RUN_REQUIRED", "本阶段只允许 dry_run=true。")
    if not payload.approval_required:
        return error_response(
            400,
            "HAPROXY_ROUTE_APPROVAL_REQUIRED",
            "本阶段仍需要下一阶段再次审批，approval_required 必须为 true。",
        )
    if payload.approval_stage != HAPROXY_ROUTE_CREATE_DRY_RUN_STAGE:
        return error_response(
            400,
            "HAPROXY_ROUTE_DRY_RUN_STAGE_MISMATCH",
            "approval_stage 不匹配 Stage 3.3.137 dry-run 阶段。",
        )
    if payload.forwarding_method != FORWARDING_METHOD_HAPROXY_TCP:
        return error_response(400, "HAPROXY_FORWARDING_METHOD_REQUIRED", "本阶段只允许 haproxy_tcp。")
    if not payload.firewall_security_group_confirmed:
        return error_response(
            400,
            "SECURITY_GROUP_CONFIRMATION_REQUIRED",
            f"必须确认云安全组已放行 {payload.planned_listen_port}/TCP。",
        )
    if not payload.cloud_firewall_confirmed:
        return error_response(
            400,
            "CLOUD_FIREWALL_CONFIRMATION_REQUIRED",
            f"必须确认云防火墙已放行 {payload.planned_listen_port}/TCP。",
        )
    if not payload.server_firewall_confirmed:
        return error_response(
            400,
            "SERVER_FIREWALL_CONFIRMATION_REQUIRED",
            f"必须确认服务器本机防火墙已放行 {payload.planned_listen_port}/TCP。",
        )
    if not payload.no_cutover_confirmed:
        return error_response(400, "NO_CUTOVER_CONFIRMATION_REQUIRED", "必须确认本阶段不执行 cutover。")
    if not payload.no_node_share_link_change_confirmed:
        return error_response(
            400,
            "NODE_SHARE_LINK_BOUNDARY_REQUIRED",
            "必须确认本阶段不读取或修改 nodes.share_link。",
        )
    if not payload.no_full_client_link_confirmed:
        return error_response(
            400,
            "NO_FULL_CLIENT_LINK_CONFIRMATION_REQUIRED",
            "必须确认本阶段不生成或展示完整客户端链接。",
        )

    readiness_payload = TransitHaproxyReadinessApprovalRequest(
        transit_resource_id=payload.transit_resource_id,
        landing_node_id=payload.landing_node_id,
        planned_listen_port=payload.planned_listen_port,
        landing_target_port=payload.landing_target_port,
        forwarding_method=payload.forwarding_method,
        purpose=payload.purpose,
        firewall_security_group_confirmed=payload.firewall_security_group_confirmed,
        cloud_firewall_confirmed=payload.cloud_firewall_confirmed,
        server_firewall_confirmed=payload.server_firewall_confirmed,
        no_cutover_confirmed=payload.no_cutover_confirmed,
        no_node_share_link_change_confirmed=payload.no_node_share_link_change_confirmed,
        no_full_client_link_confirmed=payload.no_full_client_link_confirmed,
    )
    readiness = build_haproxy_readiness_approval(db, readiness_payload)
    if not readiness["ready"]:
        return error_response(
            400,
            "HAPROXY_READINESS_NOT_READY",
            "HAProxy TCP route 创建 readiness 仍有阻塞项，不能创建 dry-run Worker command。",
            {"readiness": readiness},
        )

    resource = db.get(TransitResource, payload.transit_resource_id)
    node = db.get(Node, payload.landing_node_id)
    target_worker = latest_bound_worker(db, server_id=resource.id if resource else None)
    landing_host = node.vps.ip if node and node.vps else None
    if not resource or resource.deleted_at is not None:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转服务器记录不存在。")
    if not node or node.deleted_at is not None:
        return error_response(404, "LANDING_NODE_NOT_FOUND", "落地节点不存在。")
    if landing_host != payload.landing_target_host:
        return error_response(400, "LANDING_HOST_MISMATCH", "落地节点当前 IP 与 dry-run 目标不一致。")
    if node.xray_port != payload.landing_target_port:
        return error_response(400, "LANDING_TARGET_PORT_MISMATCH", "落地节点当前端口与 dry-run 目标不一致。")
    if not target_worker:
        return error_response(400, "WORKER_NOT_FOUND", "该中转资源尚未绑定 Worker。")
    if target_worker.status != "online" or worker_runtime_status(target_worker) != "online":
        return error_response(400, "WORKER_OFFLINE", "目标 transit Worker 不在线。")
    if target_worker.role != "transit":
        return error_response(400, "WORKER_ROLE_MISMATCH", "只允许 transit role Worker 创建 HAProxy route dry-run。")
    if not target_worker.interface_name:
        return error_response(400, "WORKER_INTERFACE_MISSING", "目标 Worker 尚未上报 interface_name。")
    if not worker_supports_transit_forwarding_method(target_worker, FORWARDING_METHOD_HAPROXY_TCP):
        return error_response(
            400,
            "WORKER_FORWARDING_METHOD_UNSUPPORTED",
            "当前在线 Worker 版本不支持 HAProxy TCP，请先升级中转 Worker。",
            {
                "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(
                    FORWARDING_METHOD_HAPROXY_TCP
                ),
                "target_worker_version": target_worker.worker_version,
                "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
            },
        )

    planned_service_name = f"liveline-haproxy-{payload.planned_listen_port}.service"
    command_payload = {
        "command_intent": "haproxy_route_create_dry_run",
        "transit_resource_id": resource.id,
        "transit_resource_name": resource.name,
        "transit_entry_host": resource.entry_host,
        "landing_node_id": node.id,
        "landing_node_name": node.node_name,
        "planned_listen_port": payload.planned_listen_port,
        "approved_planned_listen_port": payload.planned_listen_port,
        "approved_firewall_confirmation": True,
        "landing_target_host": payload.landing_target_host,
        "approved_landing_target_host": payload.landing_target_host,
        "landing_target_port": payload.landing_target_port,
        "approved_landing_target_port": payload.landing_target_port,
        "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
        "purpose": payload.purpose,
        "approval_stage": payload.approval_stage,
        "readiness_approval_confirmed": True,
        "dry_run": True,
        "approval_required": True,
        "user_approved_real_execution": False,
        "real_execution": False,
        "route_created": False,
        "haproxy_installed": False,
        "listener_bound": False,
        "firewall_modified": False,
        "share_link_mutated": False,
        "cutover": False,
        "route_name": payload.route_name,
        "planned_service_name": planned_service_name,
        "haproxy_config_plan": {
            "mode": "tcp",
            "frontend_bind": f"*:{payload.planned_listen_port}",
            "backend_target": f"{payload.landing_target_host}:{payload.landing_target_port}",
        },
        "firewall_security_group_confirmed": True,
        "cloud_firewall_confirmed": True,
        "server_firewall_confirmed": True,
        "no_cutover_confirmed": True,
        "no_node_share_link_change_confirmed": True,
        "no_full_client_link_confirmed": True,
        "safety_boundary": HAPROXY_ROUTE_CREATE_DRY_RUN_BOUNDARY,
    }
    command = create_worker_command(db, target_worker, TRANSIT_ROUTE_CREATE_COMMAND, command_payload)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_haproxy_route_create_dry_run",
        result="success",
        request=request,
        resource_type="worker_command",
        resource_id=command.id,
    )
    db.commit()
    db.refresh(command)

    return success_response(
        {
            "command": serialize_worker_command(command, include_payload=True, worker=target_worker),
            "target_worker_id": target_worker.id,
            "target_worker_version": target_worker.worker_version,
            "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(
                FORWARDING_METHOD_HAPROXY_TCP
            ),
            "dry_run": True,
            "approval_required": True,
            "real_execution": False,
            "route_created": False,
            "haproxy_installed": False,
            "listener_bound": False,
            "firewall_modified": False,
            "share_link_mutated": False,
            "cutover": False,
            "planned_service_name": planned_service_name,
            "planned_listen_port": payload.planned_listen_port,
            "landing_target_host": payload.landing_target_host,
            "landing_target_port": payload.landing_target_port,
            "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
            "route_name": payload.route_name,
            "readiness_summary": readiness["summary"],
            "checks": readiness["checks"],
            "safety_boundary": HAPROXY_ROUTE_CREATE_DRY_RUN_BOUNDARY,
            "next_stage": "Stage 3.3.138-new-transit-haproxy-route-create-final-approval",
        },
        "HAProxy route dry-run Worker command 已创建；不会真实创建 HAProxy route、监听端口或客户端链接。",
    )


@router.post("/haproxy-route-create-final-approval")
def haproxy_route_create_final_approval(
    payload: TransitHaproxyRouteCreateFinalApprovalRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    command = db.get(WorkerCommand, payload.dry_run_command_id)
    command_payload = command.payload_json if command and isinstance(command.payload_json, dict) else {}
    resource = db.get(TransitResource, payload.transit_resource_id)
    node = db.get(Node, payload.landing_node_id)
    target_worker = latest_bound_worker(db, server_id=resource.id if resource else None)
    landing_host = node.vps.ip if node and node.vps else None
    worker_status = worker_runtime_status(target_worker) if target_worker else "missing"

    payload_match_fields = {
        "transit_resource_id": payload.transit_resource_id,
        "landing_node_id": payload.landing_node_id,
        "planned_listen_port": payload.planned_listen_port,
        "approved_planned_listen_port": payload.planned_listen_port,
        "approved_firewall_confirmation": True,
        "landing_target_host": payload.landing_target_host,
        "approved_landing_target_host": payload.landing_target_host,
        "landing_target_port": payload.landing_target_port,
        "approved_landing_target_port": payload.landing_target_port,
        "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
        "route_name": payload.route_name,
        "planned_service_name": payload.planned_service_name,
    }
    payload_matches = bool(command_payload) and all(
        command_payload.get(key) == value for key, value in payload_match_fields.items()
    )
    dry_run_shape_ok = bool(
        command
        and command.command_type == TRANSIT_ROUTE_CREATE_COMMAND
        and command_payload.get("command_intent") == "haproxy_route_create_dry_run"
        and command_payload.get("dry_run") is True
        and command_payload.get("real_execution") is False
        and command_payload.get("user_approved_real_execution") is False
        and command_payload.get("approved_planned_listen_port") == payload.planned_listen_port
        and command_payload.get("approved_firewall_confirmation") is True
        and command_payload.get("approved_landing_target_host") == payload.landing_target_host
        and command_payload.get("approved_landing_target_port") == payload.landing_target_port
        and command_payload.get("route_created", False) is False
        and command_payload.get("listener_bound", False) is False
        and command_payload.get("forwarding_method") == FORWARDING_METHOD_HAPROXY_TCP
    )
    dry_run_succeeded = bool(command and command.status == "succeeded")
    final_text_ok = payload.final_approval_text.strip() == HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT
    worker_version_supported = worker_supports_transit_forwarding_method(
        target_worker,
        FORWARDING_METHOD_HAPROXY_TCP,
    )

    checks = [
        make_haproxy_readiness_check(
            check_id="dry_run_command_exists",
            label="dry-run command 存在",
            passed=command is not None,
            message="已找到 dry-run command。" if command else "dry-run command 不存在。",
            next_action="选择 Stage 3.3.137 成功生成的 dry-run command。" if not command else "继续检查。",
            evidence_summary=payload.dry_run_command_id,
        ),
        make_haproxy_readiness_check(
            check_id="dry_run_command_succeeded",
            label="dry-run command 已成功",
            passed=dry_run_succeeded,
            message=(
                "dry-run command 已 succeeded。"
                if dry_run_succeeded
                else f"dry-run command 必须为 succeeded，当前状态为 {command.status if command and command.status else 'missing'}。"
            ),
            next_action=(
                "重新生成 HAProxy route dry-run，并确认 dry-run command succeeded 后再进入最终审批。"
                if not dry_run_succeeded
                else "继续检查。"
            ),
            evidence_summary=command.status if command else None,
        ),
        make_haproxy_readiness_check(
            check_id="dry_run_command_shape_valid",
            label="dry-run command payload 合法",
            passed=dry_run_shape_ok,
            message="dry-run command payload 是 HAProxy route create dry-run。" if dry_run_shape_ok else "dry-run command payload 不是合法 HAProxy dry-run。",
            next_action="重新生成 HAProxy route create dry-run。" if not dry_run_shape_ok else "继续检查。",
            evidence_summary=command_payload.get("command_intent") if command_payload else None,
        ),
        make_haproxy_readiness_check(
            check_id="dry_run_verified",
            label="dry-run 已人工核验",
            passed=payload.dry_run_verified,
            message="已确认 dry-run 结果。" if payload.dry_run_verified else "尚未确认 dry-run 结果。",
            next_action="先核验 Stage 3.3.137 dry-run command 与计划摘要。" if not payload.dry_run_verified else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="dry_run_payload_matches_final_request",
            label="final approval 参数与 dry-run 一致",
            passed=payload_matches,
            message="final approval 参数与 dry-run payload 一致。" if payload_matches else "final approval 参数与 dry-run payload 不一致。",
            next_action="使用 dry-run 返回的 service、端口、目标和 route name。" if not payload_matches else "继续检查。",
            evidence_summary=payload.planned_service_name,
        ),
        make_haproxy_readiness_check(
            check_id="transit_resource_exists",
            label="中转资源存在",
            passed=resource is not None and (resource.deleted_at is None),
            message="中转资源存在且未删除。" if resource and resource.deleted_at is None else "中转资源不存在或已删除。",
            next_action="选择未删除的中转服务器。" if not resource or resource.deleted_at is not None else "继续检查。",
            evidence_summary=resource.name if resource else None,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_online",
            label="Transit Worker 在线",
            passed=bool(target_worker and target_worker.status == "online" and worker_status == "online"),
            message="Transit Worker 在线。" if target_worker and target_worker.status == "online" and worker_status == "online" else "Transit Worker 不在线。",
            next_action="等待 Worker heartbeat 恢复 online。" if not target_worker or worker_status != "online" else "继续检查。",
            evidence_summary=worker_status,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_role_is_transit",
            label="Worker role 为 transit",
            passed=bool(target_worker and target_worker.role == "transit"),
            message="Worker role 正确。" if target_worker and target_worker.role == "transit" else "Worker role 不是 transit。",
            next_action="使用 transit role Worker。" if not target_worker or target_worker.role != "transit" else "继续检查。",
            evidence_summary=target_worker.role if target_worker else None,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_version_supported",
            label="Worker 版本支持 HAProxy TCP",
            passed=worker_version_supported,
            message="Worker 版本支持 HAProxy TCP。" if worker_version_supported else "Worker 版本不支持 HAProxy TCP。",
            next_action=(
                f"升级 Worker 到 {minimum_worker_version_for_transit_forwarding_method(FORWARDING_METHOD_HAPROXY_TCP)} 或更高版本。"
                if not worker_version_supported
                else "继续检查。"
            ),
            evidence_summary=target_worker.worker_version if target_worker else None,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_interface_detected",
            label="Worker 已上报网卡",
            passed=bool(target_worker and target_worker.interface_name),
            message="Worker 已上报 interface_name。" if target_worker and target_worker.interface_name else "Worker 未上报 interface_name。",
            next_action="等待 Worker heartbeat 上报 interface_name。" if not target_worker or not target_worker.interface_name else "继续检查。",
            evidence_summary=target_worker.interface_name if target_worker else None,
        ),
        make_haproxy_readiness_check(
            check_id="landing_node_exists",
            label="落地节点存在",
            passed=bool(node and node.deleted_at is None),
            message="落地节点存在且未删除。" if node and node.deleted_at is None else "落地节点不存在或已删除。",
            next_action="选择 active 的落地节点。" if not node or node.deleted_at is not None else "继续检查。",
            evidence_summary=node.node_name if node else None,
        ),
        make_haproxy_readiness_check(
            check_id="landing_target_host_matches_current_node",
            label="落地目标 Host 匹配",
            passed=bool(landing_host and landing_host == payload.landing_target_host),
            message="落地目标 Host 与当前节点一致。" if landing_host == payload.landing_target_host else "落地目标 Host 与当前节点不一致。",
            next_action="使用当前落地节点 VPS IP。" if landing_host != payload.landing_target_host else "继续检查。",
            evidence_summary=landing_host,
        ),
        make_haproxy_readiness_check(
            check_id="landing_target_port_matches_current_node",
            label="落地目标端口匹配",
            passed=bool(node and node.xray_port == payload.landing_target_port),
            message="落地目标端口与当前节点一致。" if node and node.xray_port == payload.landing_target_port else "落地目标端口与当前节点不一致。",
            next_action="使用当前落地节点 Xray 端口。" if not node or node.xray_port != payload.landing_target_port else "继续检查。",
            evidence_summary=str(node.xray_port) if node and node.xray_port else None,
        ),
        make_haproxy_readiness_check(
            check_id="forwarding_method_is_haproxy_tcp",
            label="转发方式为 HAProxy TCP",
            passed=payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP,
            message="转发方式为 haproxy_tcp。" if payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP else "转发方式不是 haproxy_tcp。",
            next_action="选择 HAProxy TCP mode。" if payload.forwarding_method != FORWARDING_METHOD_HAPROXY_TCP else "继续检查。",
            evidence_summary=payload.forwarding_method,
        ),
        make_haproxy_readiness_check(
            check_id="security_group_confirmation_present",
            label="云安全组确认",
            passed=payload.firewall_security_group_confirmed,
            message="已确认云安全组放行。" if payload.firewall_security_group_confirmed else "尚未确认云安全组放行。",
            next_action="人工确认云安全组已放行监听 TCP 端口。" if not payload.firewall_security_group_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="cloud_firewall_confirmation_present",
            label="云防火墙确认",
            passed=payload.cloud_firewall_confirmed,
            message="已确认云防火墙放行。" if payload.cloud_firewall_confirmed else "尚未确认云防火墙放行。",
            next_action="人工确认云防火墙已放行监听 TCP 端口。" if not payload.cloud_firewall_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="server_firewall_confirmation_present",
            label="服务器本机防火墙确认",
            passed=payload.server_firewall_confirmed,
            message="已确认服务器本机防火墙放行。" if payload.server_firewall_confirmed else "尚未确认服务器本机防火墙放行。",
            next_action="人工确认服务器本机防火墙已放行监听 TCP 端口。" if not payload.server_firewall_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="no_cutover_confirmed",
            label="不 cutover 确认",
            passed=payload.no_cutover_confirmed,
            message="已确认不 cutover。" if payload.no_cutover_confirmed else "尚未确认不 cutover。",
            next_action="确认本阶段不切换默认入口。" if not payload.no_cutover_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="no_share_link_mutation_confirmed",
            label="不修改 share_link 确认",
            passed=payload.no_node_share_link_change_confirmed,
            message="已确认不修改 nodes.share_link。" if payload.no_node_share_link_change_confirmed else "尚未确认不修改 nodes.share_link。",
            next_action="确认本阶段不读取或修改 nodes.share_link。" if not payload.no_node_share_link_change_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="no_full_client_link_confirmed",
            label="不导出完整客户端链接确认",
            passed=payload.no_full_client_link_confirmed,
            message="已确认不导出完整客户端链接。" if payload.no_full_client_link_confirmed else "尚未确认不导出完整客户端链接。",
            next_action="确认本阶段不生成或展示完整客户端链接。" if not payload.no_full_client_link_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="final_approval_text_matches",
            label="最终确认文本匹配",
            passed=final_text_ok,
            message="最终确认文本匹配。" if final_text_ok else "最终确认文本不匹配。",
            next_action=f"输入 {HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT}。" if not final_text_ok else "继续检查。",
            evidence_summary="typed_confirmation",
        ),
        make_haproxy_readiness_check(
            check_id="worker_command_not_created",
            label="未创建 Worker command",
            passed=True,
            message="本接口只读，不创建 Worker command。",
            next_action="下一阶段必须另行审批真实执行。",
            category="safety_boundary",
            evidence_summary="no db write",
        ),
        make_haproxy_readiness_check(
            check_id="haproxy_not_created",
            label="未创建 HAProxy route",
            passed=True,
            message="本接口不会创建 HAProxy route、service 或监听端口。",
            next_action="下一阶段必须另行审批真实执行。",
            category="safety_boundary",
            evidence_summary="final approval only",
        ),
        make_haproxy_readiness_check(
            check_id="firewall_not_modified",
            label="未修改防火墙",
            passed=True,
            message="本接口不会修改云安全组、云防火墙或服务器防火墙。",
            next_action="端口放行仍由用户人工确认。",
            category="safety_boundary",
            evidence_summary="final approval only",
        ),
    ]

    ready = all(check["passed"] for check in checks)
    return success_response(
        {
            "ready_for_real_create": ready,
            "blocked": not ready,
            "summary": (
                "HAProxy TCP route 创建最终审批包已满足 Go 条件。"
                if ready
                else (
                    "HAProxy route final approval blocked"
                    if not dry_run_succeeded
                    else "HAProxy TCP route 创建最终审批包仍有 No-Go / blocked 检查项。"
                )
            ),
            "next_action": (
                "可以进入 Stage 3.3.139，由用户再次明确授权后创建真实 HAProxy TCP route。"
                if ready
                else (
                    "请先重新生成并完成 Stage 3.3.137 HAProxy route dry-run，直到 dry-run command succeeded。"
                    if not dry_run_succeeded
                    else "先处理 blocked 检查项；本阶段不会创建 Worker command 或 HAProxy route。"
                )
            ),
            "dry_run_command_id": payload.dry_run_command_id,
            "planned_service_name": payload.planned_service_name,
            "planned_listen_port": payload.planned_listen_port,
            "landing_target_host": payload.landing_target_host,
            "landing_target_port": payload.landing_target_port,
            "forwarding_method": payload.forwarding_method,
            "route_name": payload.route_name,
            "target_worker_id": target_worker.id if target_worker else None,
            "target_worker_version": target_worker.worker_version if target_worker else None,
            "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(
                FORWARDING_METHOD_HAPROXY_TCP
            ),
            "checks": checks,
            "safety_boundary": HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_BOUNDARY,
            "next_stage": "Stage 3.3.139-new-transit-haproxy-route-create-real-execution",
            "worker_command_created": False,
            "real_execution_command_created": False,
            "route_created": False,
            "transit_route_active_record_created": False,
            "haproxy_installed": False,
            "listener_bound": False,
            "firewall_modified": False,
            "share_link_mutated": False,
            "cutover": False,
        },
        "HAProxy route 最终审批包已生成；本接口只读，不创建 Worker command、HAProxy route 或监听端口。",
    )


def find_existing_haproxy_real_execution_command(
    db: Session,
    *,
    transit_resource_id: str,
    landing_node_id: str,
    planned_listen_port: int,
    landing_target_host: str,
    landing_target_port: int,
    route_name: str,
) -> WorkerCommand | None:
    commands = db.scalars(
        select(WorkerCommand).where(
            WorkerCommand.server_type == "transit",
            WorkerCommand.server_id == transit_resource_id,
            WorkerCommand.command_type == TRANSIT_ROUTE_CREATE_COMMAND,
            WorkerCommand.status.in_(("created", "pending", "running", "claimed", "succeeded")),
        )
    ).all()
    for command in commands:
        command_payload = command.payload_json if isinstance(command.payload_json, dict) else {}
        if command_payload.get("command_intent") != "haproxy_route_create_real_execution":
            continue
        if command_payload.get("transit_resource_id") != transit_resource_id:
            continue
        if command_payload.get("landing_node_id") != landing_node_id:
            continue
        if command_payload.get("planned_listen_port") != planned_listen_port:
            continue
        if command_payload.get("landing_target_host") != landing_target_host:
            continue
        if command_payload.get("landing_target_port") != landing_target_port:
            continue
        if command_payload.get("forwarding_method") != FORWARDING_METHOD_HAPROXY_TCP:
            continue
        if command_payload.get("route_name") != route_name:
            continue
        return command
    return None


@router.post("/haproxy-route-create-real-execution")
def create_haproxy_route_create_real_execution(
    payload: TransitHaproxyRouteCreateRealExecutionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    command = db.get(WorkerCommand, payload.dry_run_command_id)
    command_payload = command.payload_json if command and isinstance(command.payload_json, dict) else {}
    resource = db.get(TransitResource, payload.transit_resource_id)
    node = db.get(Node, payload.landing_node_id)
    target_worker = latest_bound_worker(db, server_id=resource.id if resource else None)
    landing_host = node.vps.ip if node and node.vps else None
    worker_status = worker_runtime_status(target_worker) if target_worker else "missing"
    planned_service_name = f"liveline-haproxy-{payload.planned_listen_port}.service"

    payload_match_fields = {
        "transit_resource_id": payload.transit_resource_id,
        "landing_node_id": payload.landing_node_id,
        "planned_listen_port": payload.planned_listen_port,
        "approved_planned_listen_port": payload.planned_listen_port,
        "approved_firewall_confirmation": True,
        "landing_target_host": payload.landing_target_host,
        "approved_landing_target_host": payload.landing_target_host,
        "landing_target_port": payload.landing_target_port,
        "approved_landing_target_port": payload.landing_target_port,
        "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
        "route_name": payload.route_name,
        "planned_service_name": planned_service_name,
    }
    payload_matches = bool(command_payload) and all(
        command_payload.get(key) == value for key, value in payload_match_fields.items()
    )
    dry_run_shape_ok = bool(
        command
        and command.command_type == TRANSIT_ROUTE_CREATE_COMMAND
        and command.server_type == "transit"
        and command.server_id == payload.transit_resource_id
        and command_payload.get("command_intent") == "haproxy_route_create_dry_run"
        and command_payload.get("approval_stage") == HAPROXY_ROUTE_CREATE_DRY_RUN_STAGE
        and command_payload.get("dry_run") is True
        and command_payload.get("approval_required") is True
        and command_payload.get("real_execution") is False
        and command_payload.get("user_approved_real_execution") is False
        and command_payload.get("approved_planned_listen_port") == payload.planned_listen_port
        and command_payload.get("approved_firewall_confirmation") is True
        and command_payload.get("approved_landing_target_host") == payload.landing_target_host
        and command_payload.get("approved_landing_target_port") == payload.landing_target_port
        and command_payload.get("route_created", False) is False
        and command_payload.get("listener_bound", False) is False
        and command_payload.get("forwarding_method") == FORWARDING_METHOD_HAPROXY_TCP
    )
    dry_run_succeeded = bool(command and command.status == "succeeded")
    final_text_ok = payload.final_approval_text.strip() == HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT
    real_execution_text_ok = payload.real_execution_text.strip() == HAPROXY_ROUTE_CREATE_REAL_EXECUTION_TEXT
    worker_version_supported = worker_supports_transit_forwarding_method(
        target_worker,
        FORWARDING_METHOD_HAPROXY_TCP,
    )
    active_route = db.scalar(
        select(TransitRoute).where(
            TransitRoute.transit_resource_id == payload.transit_resource_id,
            TransitRoute.listen_port == payload.planned_listen_port,
            TransitRoute.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP,
            TransitRoute.status.in_(("creating", "active")),
            TransitRoute.deleted_at.is_(None),
        )
    )
    duplicate_command = find_existing_haproxy_real_execution_command(
        db,
        transit_resource_id=payload.transit_resource_id,
        landing_node_id=payload.landing_node_id,
        planned_listen_port=payload.planned_listen_port,
        landing_target_host=payload.landing_target_host,
        landing_target_port=payload.landing_target_port,
        route_name=payload.route_name,
    )
    unsafe_payload_keys_absent = True

    checks = [
        make_haproxy_readiness_check(
            check_id="dry_run_command_exists",
            label="dry-run command 存在",
            passed=command is not None,
            message="已找到 dry-run command。" if command else "dry-run command 不存在。",
            next_action="重新生成 Stage 3.3.137 HAProxy route dry-run。" if not command else "继续检查。",
            evidence_summary=payload.dry_run_command_id,
        ),
        make_haproxy_readiness_check(
            check_id="dry_run_command_succeeded",
            label="dry-run command 已成功",
            passed=dry_run_succeeded,
            message=(
                "dry-run command 已 succeeded。"
                if dry_run_succeeded
                else f"dry-run command 必须为 succeeded，当前状态为 {command.status if command and command.status else 'missing'}。"
            ),
            next_action=(
                "先重新生成并完成 Stage 3.3.137 HAProxy route dry-run，直到 command succeeded。"
                if not dry_run_succeeded
                else "继续检查。"
            ),
            evidence_summary=command.status if command else None,
        ),
        make_haproxy_readiness_check(
            check_id="dry_run_command_shape_valid",
            label="dry-run command payload 合法",
            passed=dry_run_shape_ok,
            message="dry-run payload 是 HAProxy TCP dry-run。" if dry_run_shape_ok else "dry-run payload 不是合法 HAProxy TCP dry-run。",
            next_action="使用 Stage 3.3.137 重新生成 HAProxy route dry-run。" if not dry_run_shape_ok else "继续检查。",
            evidence_summary=command_payload.get("command_intent") if command_payload else None,
        ),
        make_haproxy_readiness_check(
            check_id="dry_run_payload_matches_real_request",
            label="真实执行参数与 dry-run 一致",
            passed=payload_matches,
            message="真实执行参数与 dry-run payload 一致。" if payload_matches else "真实执行参数与 dry-run payload 不一致。",
            next_action="使用 dry-run 返回的 service、端口、目标和 route name。" if not payload_matches else "继续检查。",
            evidence_summary=planned_service_name,
        ),
        make_haproxy_readiness_check(
            check_id="final_approval_text_matches",
            label="最终审批确认文本匹配",
            passed=final_text_ok,
            message="最终审批确认文本匹配。" if final_text_ok else "最终审批确认文本不匹配。",
            next_action=f"先输入 {HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT}。" if not final_text_ok else "继续检查。",
            evidence_summary="typed_confirmation",
        ),
        make_haproxy_readiness_check(
            check_id="real_execution_text_matches",
            label="真实执行确认文本匹配",
            passed=real_execution_text_ok,
            message="真实执行确认文本匹配。" if real_execution_text_ok else "真实执行确认文本不匹配。",
            next_action=f"输入 {HAPROXY_ROUTE_CREATE_REAL_EXECUTION_TEXT}。" if not real_execution_text_ok else "继续检查。",
            evidence_summary="typed_confirmation",
        ),
        make_haproxy_readiness_check(
            check_id="transit_resource_exists",
            label="中转资源存在",
            passed=resource is not None and (resource.deleted_at is None),
            message="中转资源存在且未删除。" if resource and resource.deleted_at is None else "中转资源不存在或已删除。",
            next_action="选择未删除的中转服务器。" if not resource or resource.deleted_at is not None else "继续检查。",
            evidence_summary=resource.name if resource else None,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_online",
            label="Transit Worker 在线",
            passed=bool(target_worker and target_worker.status == "online" and worker_status == "online"),
            message="Transit Worker 在线。" if target_worker and target_worker.status == "online" and worker_status == "online" else "Transit Worker 不在线。",
            next_action="等待 Worker heartbeat 恢复 online。" if not target_worker or worker_status != "online" else "继续检查。",
            evidence_summary=worker_status,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_role_is_transit",
            label="Worker role 为 transit",
            passed=bool(target_worker and target_worker.role == "transit"),
            message="Worker role 正确。" if target_worker and target_worker.role == "transit" else "Worker role 不是 transit。",
            next_action="使用 transit role Worker。" if not target_worker or target_worker.role != "transit" else "继续检查。",
            evidence_summary=target_worker.role if target_worker else None,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_version_supported",
            label="Worker 版本支持 HAProxy TCP",
            passed=worker_version_supported,
            message="Worker 版本支持 HAProxy TCP。" if worker_version_supported else "Worker 版本不支持 HAProxy TCP。",
            next_action=(
                f"升级 Worker 到 {minimum_worker_version_for_transit_forwarding_method(FORWARDING_METHOD_HAPROXY_TCP)} 或更高版本。"
                if not worker_version_supported
                else "继续检查。"
            ),
            evidence_summary=target_worker.worker_version if target_worker else None,
        ),
        make_haproxy_readiness_check(
            check_id="transit_worker_interface_detected",
            label="Worker 已上报网卡",
            passed=bool(target_worker and target_worker.interface_name),
            message="Worker 已上报 interface_name。" if target_worker and target_worker.interface_name else "Worker 未上报 interface_name。",
            next_action="等待 Worker heartbeat 上报 interface_name。" if not target_worker or not target_worker.interface_name else "继续检查。",
            evidence_summary=target_worker.interface_name if target_worker else None,
        ),
        make_haproxy_readiness_check(
            check_id="landing_node_exists",
            label="落地节点存在",
            passed=bool(node and node.deleted_at is None),
            message="落地节点存在且未删除。" if node and node.deleted_at is None else "落地节点不存在或已删除。",
            next_action="选择 active 的落地节点。" if not node or node.deleted_at is not None else "继续检查。",
            evidence_summary=node.node_name if node else None,
        ),
        make_haproxy_readiness_check(
            check_id="landing_target_host_matches_current_node",
            label="落地目标 Host 匹配",
            passed=bool(landing_host and landing_host == payload.landing_target_host),
            message="落地目标 Host 与当前节点一致。" if landing_host == payload.landing_target_host else "落地目标 Host 与当前节点不一致。",
            next_action="使用当前落地节点 VPS IP。" if landing_host != payload.landing_target_host else "继续检查。",
            evidence_summary=landing_host,
        ),
        make_haproxy_readiness_check(
            check_id="landing_target_port_matches_current_node",
            label="落地目标端口匹配",
            passed=bool(node and node.xray_port == payload.landing_target_port),
            message="落地目标端口与当前节点一致。" if node and node.xray_port == payload.landing_target_port else "落地目标端口与当前节点不一致。",
            next_action="使用当前落地节点 Xray 端口。" if not node or node.xray_port != payload.landing_target_port else "继续检查。",
            evidence_summary=str(node.xray_port) if node and node.xray_port else None,
        ),
        make_haproxy_readiness_check(
            check_id="forwarding_method_is_haproxy_tcp",
            label="转发方式为 HAProxy TCP",
            passed=payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP,
            message="转发方式为 haproxy_tcp。" if payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP else "转发方式不是 haproxy_tcp。",
            next_action="选择 HAProxy TCP mode。" if payload.forwarding_method != FORWARDING_METHOD_HAPROXY_TCP else "继续检查。",
            evidence_summary=payload.forwarding_method,
        ),
        make_haproxy_readiness_check(
            check_id="security_group_confirmation_present",
            label="云安全组确认",
            passed=payload.firewall_security_group_confirmed,
            message="已确认云安全组放行。" if payload.firewall_security_group_confirmed else "尚未确认云安全组放行。",
            next_action="人工确认云安全组已放行监听 TCP 端口。" if not payload.firewall_security_group_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="cloud_firewall_confirmation_present",
            label="云防火墙确认",
            passed=payload.cloud_firewall_confirmed,
            message="已确认云防火墙放行。" if payload.cloud_firewall_confirmed else "尚未确认云防火墙放行。",
            next_action="人工确认云防火墙已放行监听 TCP 端口。" if not payload.cloud_firewall_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="server_firewall_confirmation_present",
            label="服务器本机防火墙确认",
            passed=payload.server_firewall_confirmed,
            message="已确认服务器本机防火墙放行。" if payload.server_firewall_confirmed else "尚未确认服务器本机防火墙放行。",
            next_action="人工确认服务器本机防火墙已放行监听 TCP 端口。" if not payload.server_firewall_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="no_cutover_confirmed",
            label="不 cutover 确认",
            passed=payload.no_cutover_confirmed,
            message="已确认不 cutover。" if payload.no_cutover_confirmed else "尚未确认不 cutover。",
            next_action="确认本阶段不切换默认入口。" if not payload.no_cutover_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="no_share_link_mutation_confirmed",
            label="不修改 share_link 确认",
            passed=payload.no_node_share_link_change_confirmed,
            message="已确认不修改 nodes.share_link。" if payload.no_node_share_link_change_confirmed else "尚未确认不修改 nodes.share_link。",
            next_action="确认本阶段不读取或修改 nodes.share_link。" if not payload.no_node_share_link_change_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="no_full_client_link_confirmed",
            label="不导出完整客户端链接确认",
            passed=payload.no_full_client_link_confirmed,
            message="已确认不导出完整客户端链接。" if payload.no_full_client_link_confirmed else "尚未确认不导出完整客户端链接。",
            next_action="确认本阶段不生成或展示完整客户端链接。" if not payload.no_full_client_link_confirmed else "继续检查。",
        ),
        make_haproxy_readiness_check(
            check_id="no_existing_haproxy_route_same_port",
            label="不存在同端口 active HAProxy route",
            passed=active_route is None,
            message="未发现同端口 active HAProxy route。" if not active_route else "已有同端口 creating/active HAProxy route。",
            next_action="先处理已有 HAProxy route 记录。" if active_route else "继续检查。",
            evidence_summary=active_route.id if active_route else None,
        ),
        make_haproxy_readiness_check(
            check_id="no_duplicate_real_execution_command",
            label="不存在重复真实执行 command",
            passed=duplicate_command is None,
            message="未发现重复真实执行 command。" if not duplicate_command else "已有相同 route 的真实执行 command。",
            next_action="等待已有真实执行 command 完成或处理后再重试。" if duplicate_command else "继续检查。",
            evidence_summary=duplicate_command.id if duplicate_command else None,
        ),
        make_haproxy_readiness_check(
            check_id="unsafe_payload_keys_absent",
            label="命令 payload 不包含任意执行字段",
            passed=unsafe_payload_keys_absent,
            message="将创建的 payload 只包含固定 HAProxy TCP 字段。",
            next_action="继续检查。",
            category="safety_boundary",
        ),
    ]

    ready = all(check["passed"] for check in checks)
    blocked_response = {
        "ready_for_real_execution": ready,
        "blocked": not ready,
        "summary": "HAProxy TCP route 真实创建条件已满足。" if ready else "HAProxy TCP route real execution blocked",
        "next_action": (
            "可以创建受控真实执行 Worker command。"
            if ready
            else "先处理 blocked 检查项；不会创建 Worker command、HAProxy route 或监听端口。"
        ),
        "dry_run_command_id": payload.dry_run_command_id,
        "planned_service_name": planned_service_name,
        "planned_listen_port": payload.planned_listen_port,
        "landing_target_host": payload.landing_target_host,
        "landing_target_port": payload.landing_target_port,
        "forwarding_method": payload.forwarding_method,
        "route_name": payload.route_name,
        "target_worker_id": target_worker.id if target_worker else None,
        "target_worker_version": target_worker.worker_version if target_worker else None,
        "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(
            FORWARDING_METHOD_HAPROXY_TCP
        ),
        "checks": checks,
        "safety_boundary": HAPROXY_ROUTE_CREATE_REAL_EXECUTION_BOUNDARY,
        "worker_command_created": False,
        "real_execution_command_created": False,
        "route_created": False,
        "transit_route_active_record_created": False,
        "haproxy_installed": False,
        "listener_bound": False,
        "firewall_modified": False,
        "share_link_mutated": False,
        "cutover": False,
    }
    if not ready:
        return success_response(
            blocked_response,
            "HAProxy route 真实创建被阻塞；未创建 Worker command、HAProxy route 或监听端口。",
        )

    command_payload = {
        "command_intent": "haproxy_route_create_real_execution",
        "source_dry_run_command_id": payload.dry_run_command_id,
        "source_final_approval": HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_STAGE,
        "transit_resource_id": resource.id,
        "transit_resource_name": resource.name,
        "transit_entry_host": resource.entry_host,
        "transit_worker_id": target_worker.id,
        "interface_name": target_worker.interface_name,
        "landing_node_id": node.id,
        "landing_node_name": node.node_name,
        "planned_listen_port": payload.planned_listen_port,
        "approved_planned_listen_port": payload.planned_listen_port,
        "approved_firewall_confirmation": True,
        "landing_target_host": payload.landing_target_host,
        "approved_landing_target_host": payload.landing_target_host,
        "landing_target_port": payload.landing_target_port,
        "approved_landing_target_port": payload.landing_target_port,
        "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
        "purpose": "HAProxy TCP protected route create",
        "approval_stage": HAPROXY_ROUTE_CREATE_REAL_EXECUTION_STAGE,
        "dry_run": False,
        "approval_required": False,
        "execution_mode": "real_create",
        "approved_real_execution": True,
        "user_approved_real_execution": True,
        "route_name": payload.route_name,
        "planned_service_name": planned_service_name,
        "firewall_security_group_confirmed": True,
        "cloud_firewall_confirmed": True,
        "server_firewall_confirmed": True,
        "no_cutover_confirmed": True,
        "no_node_share_link_change_confirmed": True,
        "no_full_client_link_confirmed": True,
        "cutover": False,
        "safety_boundary": HAPROXY_ROUTE_CREATE_REAL_EXECUTION_BOUNDARY,
    }
    real_command = create_worker_command(db, target_worker, TRANSIT_ROUTE_CREATE_COMMAND, command_payload)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_haproxy_route_create_real_execution",
        result="success",
        request=request,
        resource_type="worker_command",
        resource_id=real_command.id,
    )
    db.commit()
    db.refresh(real_command)

    response_data = {
        **blocked_response,
        "ready_for_real_execution": True,
        "blocked": False,
        "summary": "HAProxy TCP route 真实创建 Worker command 已创建。",
        "next_action": "等待 transit Worker 执行并回传结果；成功后才会由 result ingest 写入 TransitRoute active record。",
        "command": serialize_worker_command(real_command, include_payload=True, worker=target_worker),
        "worker_command_created": True,
        "real_execution_command_created": True,
    }
    return success_response(
        response_data,
        "HAProxy TCP route 真实创建 Worker command 已创建；本请求未直接创建 TransitRoute、未写 share_link、未 cutover。",
    )


@router.post("/readonly-preflight-command")
def create_transit_readonly_preflight_command(
    payload: TransitReadonlyPreflightCommandRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    if not payload.readonly:
        return error_response(
            400,
            "READONLY_CONFIRMATION_REQUIRED",
            "必须明确确认 readonly=true，才允许创建远程只读预检命令。",
        )
    if payload.planned_listen_port in PROTECTED_CREATE_PORTS:
        return error_response(
            400,
            "PROTECTED_LISTEN_PORT",
            PROTECTED_CREATE_PORT_MESSAGES[payload.planned_listen_port],
        )

    resource = db.get(TransitResource, payload.transit_resource_id)
    if not resource or resource.deleted_at is not None:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转服务器记录不存在。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_TYPE_UNSUPPORTED", "只允许 server 类型中转资源执行只读预检。")
    if resource.status == "disabled":
        return error_response(400, "TRANSIT_RESOURCE_DISABLED", "已停用的中转资源不能执行只读预检。")

    node = db.get(Node, payload.landing_node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "LANDING_NODE_NOT_FOUND", "落地节点不存在。")
    if node.status != "active":
        return error_response(400, "LANDING_NODE_NOT_ACTIVE", "只允许 active 落地节点执行只读预检。")
    landing_host = node.vps.ip if node.vps else None
    if not landing_host:
        return error_response(400, "LANDING_HOST_MISSING", "落地节点缺少目标 IP，不能执行只读预检。")
    if node.xray_port and payload.landing_target_port != node.xray_port:
        return error_response(
            400,
            "LANDING_TARGET_PORT_MISMATCH",
            "落地目标端口必须与当前 active 节点端口一致。",
        )

    try:
        target = resolve_command_target_worker(
            db,
            server_type="transit",
            server_id=resource.id,
            role="transit",
            command_type=TRANSIT_READONLY_PREFLIGHT_COMMAND,
        )
    except WorkerTargetError as exc:
        return error_response(400, exc.code, exc.message)

    target_worker = target.worker
    if target_worker.role != "transit":
        return error_response(400, "WORKER_ROLE_MISMATCH", "只允许 transit role Worker 执行中转只读预检。")

    command_payload = {
        "transit_resource_id": resource.id,
        "transit_resource_name": resource.name,
        "landing_node_id": node.id,
        "landing_node_name": node.node_name,
        "planned_listen_port": payload.planned_listen_port,
        "landing_target_host": landing_host,
        "landing_target_port": payload.landing_target_port,
        "forwarding_method": payload.forwarding_method,
        "purpose": payload.purpose,
        "readonly": True,
        "safety_boundary": TRANSIT_READONLY_PREFLIGHT_BOUNDARY,
    }
    command = create_worker_command(db, target_worker, TRANSIT_READONLY_PREFLIGHT_COMMAND, command_payload)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_transit_readonly_preflight_command",
        result="success",
        request=request,
        resource_type="worker_command",
        resource_id=command.id,
    )
    db.commit()
    db.refresh(command)
    return success_response(
        {
            "command": serialize_worker_command(command, include_payload=True, worker=target_worker),
            "target_worker_id": target_worker.id,
            "target_worker_version": target_worker.worker_version,
            "minimum_supported_worker_version": minimum_worker_version_for_command(TRANSIT_READONLY_PREFLIGHT_COMMAND),
            "safety_boundary": TRANSIT_READONLY_PREFLIGHT_BOUNDARY,
        },
        "远程只读预检 Worker command 已创建；不会创建真实转发。",
    )


@router.post("/worker-create-plan")
def create_transit_route_worker_create_plan(
    payload: TransitRouteWorkerCreatePlanRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    if not payload.dry_run:
        return error_response(
            400,
            "TRANSIT_ROUTE_CREATE_DRY_RUN_REQUIRED",
            "Stage 3.3.71 只允许 dry_run=true 的中转链路创建计划。",
        )
    if not payload.approval_required:
        return error_response(
            400,
            "TRANSIT_ROUTE_CREATE_APPROVAL_REQUIRED",
            "Stage 3.3.71 仍需要下一阶段再次审批，approval_required 必须为 true。",
        )
    if not payload.user_approved_execution_boundary:
        return error_response(
            400,
            "EXECUTION_BOUNDARY_CONFIRMATION_REQUIRED",
            "必须确认本阶段只创建 dry-run 计划，不执行真实中转链路创建。",
        )
    if not payload.no_node_share_link_change_confirmed:
        return error_response(
            400,
            "NODE_SHARE_LINK_BOUNDARY_REQUIRED",
            "必须确认本阶段不读取或修改 nodes.share_link。",
        )
    if not payload.no_cutover_confirmed:
        return error_response(400, "NO_CUTOVER_CONFIRMATION_REQUIRED", "必须确认本阶段不执行 cutover。")

    if payload.transit_resource_id != APPROVED_TRANSIT_RESOURCE_ID:
        return error_response(400, "TRANSIT_RESOURCE_APPROVAL_MISMATCH", "中转资源与 Stage 3.3.70 审批记录不一致。")
    if payload.landing_node_id != APPROVED_LANDING_NODE_ID:
        return error_response(400, "LANDING_NODE_APPROVAL_MISMATCH", "落地节点与 Stage 3.3.70 审批记录不一致。")
    if payload.planned_listen_port != APPROVED_TRANSIT_LISTEN_PORT:
        return error_response(400, "LISTEN_PORT_APPROVAL_MISMATCH", "监听端口与 Stage 3.3.70 审批记录不一致。")
    if payload.landing_target_host != APPROVED_LANDING_TARGET_HOST:
        return error_response(400, "LANDING_HOST_APPROVAL_MISMATCH", "落地目标 Host 与 Stage 3.3.70 审批记录不一致。")
    if payload.landing_target_port != APPROVED_LANDING_TARGET_PORT:
        return error_response(400, "LANDING_PORT_APPROVAL_MISMATCH", "落地目标端口与 Stage 3.3.70 审批记录不一致。")
    if payload.forwarding_method not in TRANSIT_ROUTE_CREATE_FORWARDING_METHODS:
        return error_response(400, "TRANSIT_METHOD_NOT_SUPPORTED", "当前只允许 socat 或 HAProxy TCP mode。")
    if payload.planned_listen_port in PROTECTED_CREATE_PORTS:
        return error_response(
            400,
            "PROTECTED_LISTEN_PORT",
            PROTECTED_CREATE_PORT_MESSAGES[payload.planned_listen_port],
        )

    resource = db.get(TransitResource, payload.transit_resource_id)
    if not resource or resource.deleted_at is not None:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转服务器记录不存在。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_TYPE_UNSUPPORTED", "只允许 server 类型中转资源进入创建计划。")
    if resource.status == "disabled":
        return error_response(400, "TRANSIT_RESOURCE_DISABLED", "已停用的中转资源不能进入创建计划。")

    node = db.get(Node, payload.landing_node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "LANDING_NODE_NOT_FOUND", "落地节点不存在。")
    if node.status != "active":
        return error_response(400, "LANDING_NODE_NOT_ACTIVE", "只允许 active 落地节点进入创建计划。")
    landing_host = node.vps.ip if node.vps else None
    if landing_host != payload.landing_target_host:
        return error_response(400, "LANDING_HOST_MISMATCH", "落地节点当前 IP 与审批目标不一致。")
    if node.xray_port != payload.landing_target_port:
        return error_response(400, "LANDING_TARGET_PORT_MISMATCH", "落地节点当前端口与审批目标不一致。")

    existing_route = db.scalar(
        select(TransitRoute).where(
            TransitRoute.transit_resource_id == resource.id,
            TransitRoute.listen_port == payload.planned_listen_port,
            TransitRoute.status.in_(("creating", "active")),
            TransitRoute.deleted_at.is_(None),
        )
    )
    if existing_route:
        return error_response(409, "TRANSIT_PORT_ALREADY_PLANNED", "该中转资源已有相同监听端口的 creating/active 线路记录。")

    if not has_matching_successful_transit_readonly_preflight(
        db,
        transit_resource_id=resource.id,
        landing_node_id=node.id,
        planned_listen_port=payload.planned_listen_port,
        landing_target_host=payload.landing_target_host,
        landing_target_port=payload.landing_target_port,
        forwarding_method=payload.forwarding_method,
    ):
        return error_response(
            400,
            "READONLY_PREFLIGHT_REQUIRED",
            "未找到匹配的已成功远程只读预检记录，不能创建中转链路 dry-run 计划。",
        )

    try:
        target = resolve_command_target_worker(
            db,
            server_type="transit",
            server_id=resource.id,
            role="transit",
            command_type=TRANSIT_ROUTE_CREATE_COMMAND,
        )
    except WorkerTargetError as exc:
        return error_response(400, exc.code, exc.message)

    target_worker = target.worker
    if target_worker.interface_name != APPROVED_TRANSIT_INTERFACE_NAME:
        return error_response(
            400,
            "WORKER_INTERFACE_MISMATCH",
            "目标 Worker interface_name 与 Stage 3.3.70 审批记录不一致。",
        )
    if not worker_supports_transit_forwarding_method(target_worker, payload.forwarding_method):
        return error_response(
            400,
            "WORKER_FORWARDING_METHOD_UNSUPPORTED",
            "当前在线 Worker 版本不支持所选转发方式，请先升级中转 Worker。",
            {
                "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(
                    payload.forwarding_method
                ),
                "target_worker_version": target_worker.worker_version,
                "forwarding_method": payload.forwarding_method,
            },
        )
    route_name = (
        f"hk-haproxy-live-{payload.planned_listen_port}"
        if payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP
        else APPROVED_TRANSIT_ROUTE_NAME
    )
    command_payload = {
        "transit_resource_id": resource.id,
        "transit_resource_name": resource.name,
        "landing_node_id": node.id,
        "landing_node_name": node.node_name,
        "planned_listen_port": payload.planned_listen_port,
        "landing_target_host": payload.landing_target_host,
        "landing_target_port": payload.landing_target_port,
        "forwarding_method": payload.forwarding_method,
        "purpose": payload.purpose,
        "approval_stage": payload.approval_stage,
        "dry_run": True,
        "approval_required": True,
        "route_name": route_name,
        "safety_boundary": TRANSIT_ROUTE_CREATE_DRY_RUN_BOUNDARY,
    }
    if payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP:
        command_payload.update(
            {
                "approved_planned_listen_port": payload.planned_listen_port,
                "approved_firewall_confirmation": True,
                "approved_landing_target_host": payload.landing_target_host,
                "approved_landing_target_port": payload.landing_target_port,
            }
        )
    command = create_worker_command(db, target_worker, TRANSIT_ROUTE_CREATE_COMMAND, command_payload)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_transit_route_worker_create_plan",
        result="success",
        request=request,
        resource_type="worker_command",
        resource_id=command.id,
    )
    db.commit()
    db.refresh(command)

    return success_response(
        {
            "command": serialize_worker_command(command, include_payload=True, worker=target_worker),
            "target_worker_id": target_worker.id,
            "target_worker_version": target_worker.worker_version,
            "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(
                payload.forwarding_method
            ),
            "execution_mode": "dry_run",
            "approval_required": True,
            "safety_boundary": TRANSIT_ROUTE_CREATE_DRY_RUN_BOUNDARY,
        },
        "中转链路 Worker 创建路径 dry-run command 已创建；不会创建真实转发。",
    )


@router.post("/worker-create-execute")
def create_transit_route_worker_create_execute(
    payload: TransitRouteWorkerCreateExecuteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    if payload.dry_run:
        return error_response(400, "TRANSIT_ROUTE_REAL_CREATE_REQUIRED", "真实执行入口必须 dry_run=false。")
    if payload.approval_required:
        return error_response(
            400,
            "TRANSIT_ROUTE_APPROVAL_ALREADY_REQUIRED",
            "Stage 3.3.73d 需要显式真实执行授权，approval_required 必须为 false。",
        )
    if not payload.user_approved_real_execution:
        return error_response(400, "REAL_EXECUTION_APPROVAL_REQUIRED", "必须确认允许真实创建本次固定中转链路。")
    if not payload.firewall_security_group_confirmed:
        return error_response(
            400,
            "SECURITY_GROUP_CONFIRMATION_REQUIRED",
            f"必须确认云安全组已放行 {payload.planned_listen_port}/TCP。",
        )
    if not payload.cloud_firewall_confirmed:
        return error_response(
            400,
            "CLOUD_FIREWALL_CONFIRMATION_REQUIRED",
            f"必须确认云防火墙已放行 {payload.planned_listen_port}/TCP。",
        )
    if not payload.server_firewall_confirmed:
        return error_response(400, "SERVER_FIREWALL_CONFIRMATION_REQUIRED", "必须确认服务器防火墙已放行或无阻断。")
    if not payload.no_node_share_link_change_confirmed:
        return error_response(
            400,
            "NODE_SHARE_LINK_BOUNDARY_REQUIRED",
            "必须确认本阶段不读取或修改 nodes.share_link。",
        )
    if not payload.no_full_client_link_confirmed:
        return error_response(400, "NO_FULL_CLIENT_LINK_CONFIRMATION_REQUIRED", "必须确认不生成或展示完整节点链接。")
    if not payload.no_cutover_confirmed:
        return error_response(400, "NO_CUTOVER_CONFIRMATION_REQUIRED", "必须确认本阶段不执行 cutover。")

    if payload.approval_stage != APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE:
        return error_response(400, "APPROVAL_STAGE_MISMATCH", "真实执行审批阶段不匹配。")
    if payload.planned_listen_port != APPROVED_TRANSIT_LISTEN_PORT:
        return error_response(
            400,
            "TRANSIT_PORT_NOT_APPROVED",
            "当前受保护创建入口只允许已审批的 23843/TCP 中转监听端口。",
        )
    if payload.landing_target_port != APPROVED_LANDING_TARGET_PORT:
        return error_response(400, "LANDING_TARGET_PORT_MISMATCH", "当前受保护创建入口只允许落地目标端口 27939。")
    if payload.forwarding_method not in TRANSIT_ROUTE_CREATE_FORWARDING_METHODS:
        return error_response(400, "TRANSIT_METHOD_NOT_SUPPORTED", "当前只允许 socat 或 HAProxy TCP mode。")
    if payload.planned_listen_port in PROTECTED_CREATE_PORTS:
        return error_response(
            400,
            "PROTECTED_LISTEN_PORT",
            PROTECTED_CREATE_PORT_MESSAGES[payload.planned_listen_port],
        )

    resource = db.get(TransitResource, payload.transit_resource_id)
    if not resource or resource.deleted_at is not None:
        return error_response(404, "TRANSIT_RESOURCE_NOT_FOUND", "中转服务器记录不存在或已删除。")
    if resource.resource_type != "server":
        return error_response(400, "TRANSIT_RESOURCE_NOT_USABLE", "只允许 server 类型中转资源执行受保护创建。")
    if resource.status not in TRANSIT_RESOURCE_CREATE_STATUSES:
        return error_response(
            400,
            "TRANSIT_RESOURCE_NOT_USABLE",
            "只允许 active 或 worker_online 状态的中转服务器执行受保护创建。",
        )
    if not resource.entry_host:
        return error_response(400, "TRANSIT_RESOURCE_NOT_USABLE", "中转服务器缺少入口地址，不能执行受保护创建。")

    node = db.get(Node, payload.landing_node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "TRANSIT_LANDING_NODE_NOT_ACTIVE", "落地节点不存在或已删除。")
    if node.status != "active":
        return error_response(400, "TRANSIT_LANDING_NODE_NOT_ACTIVE", "只允许 active 落地节点执行受保护创建。")
    if not node.share_link:
        return error_response(
            400,
            "TRANSIT_LANDING_NODE_SHARE_LINK_REQUIRED",
            "落地直连节点缺少已生成的 share_link，不能生成中转客户端候选链接。",
        )
    landing_host = node.vps.ip if node.vps else None
    if landing_host != payload.landing_target_host:
        return error_response(400, "TRANSIT_PREFLIGHT_TARGET_MISMATCH", "落地节点当前 IP 与请求目标不一致。")
    if node.xray_port != payload.landing_target_port:
        return error_response(400, "LANDING_TARGET_PORT_MISMATCH", "落地节点当前端口与请求目标不一致。")

    existing_route = db.scalar(
        select(TransitRoute).where(
            TransitRoute.transit_resource_id == resource.id,
            TransitRoute.listen_port == payload.planned_listen_port,
            TransitRoute.status.in_(("creating", "active")),
            TransitRoute.deleted_at.is_(None),
        )
    )
    if existing_route:
        return error_response(409, "TRANSIT_PORT_ALREADY_EXISTS", "该中转资源已有相同监听端口的 creating/active 线路记录。")

    if has_in_flight_transit_route_create_command(db, resource.id):
        return error_response(409, "TRANSIT_ROUTE_CREATE_COMMAND_IN_FLIGHT", "当前已有 pending/running/claimed 中转链路创建命令。")

    recent_preflights = recent_successful_transit_readonly_preflights(db, resource.id)
    matching_preflight = find_matching_successful_transit_readonly_preflight(
        db,
        transit_resource_id=resource.id,
        landing_node_id=node.id,
        planned_listen_port=payload.planned_listen_port,
        landing_target_host=payload.landing_target_host,
        landing_target_port=payload.landing_target_port,
        forwarding_method=payload.forwarding_method,
    )
    if not matching_preflight:
        code = "TRANSIT_PREFLIGHT_TARGET_MISMATCH" if recent_preflights else "TRANSIT_PREFLIGHT_REQUIRED"
        return error_response(
            400,
            code,
            "未找到与当前中转服务器、落地节点、监听端口和目标端口完全匹配的成功只读预检记录。",
        )
    preflight_interface = preflight_interface_name(matching_preflight)
    if not preflight_interface:
        return error_response(
            400,
            "TRANSIT_PREFLIGHT_TARGET_MISMATCH",
            "匹配的只读预检结果缺少网卡信息，不能执行受保护创建。",
        )

    try:
        target = resolve_command_target_worker(
            db,
            server_type="transit",
            server_id=resource.id,
            role="transit",
            command_type=TRANSIT_ROUTE_CREATE_COMMAND,
        )
    except WorkerTargetError as exc:
        mapped_code = "TRANSIT_WORKER_NOT_ONLINE" if exc.code in {"WORKER_NOT_BOUND", "WORKER_OFFLINE"} else exc.code
        return error_response(400, mapped_code, exc.message)

    target_worker = target.worker
    if target_worker.server_id != resource.id:
        return error_response(400, "TRANSIT_WORKER_SERVER_MISMATCH", "目标 Worker 未绑定到当前中转服务器。")
    if target_worker.role != "transit":
        return error_response(400, "TRANSIT_WORKER_NOT_ONLINE", "只允许 transit role Worker 执行受保护创建。")
    if target_worker.interface_name != preflight_interface:
        return error_response(
            400,
            "TRANSIT_WORKER_INTERFACE_MISMATCH",
            "目标 Worker interface_name 与最近成功只读预检结果不一致。",
        )
    if not worker_supports_transit_forwarding_method(target_worker, payload.forwarding_method):
        return error_response(
            400,
            "WORKER_FORWARDING_METHOD_UNSUPPORTED",
            "当前在线 Worker 版本不支持所选转发方式，请先升级中转 Worker。",
            {
                "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(
                    payload.forwarding_method
                ),
                "target_worker_version": target_worker.worker_version,
                "forwarding_method": payload.forwarding_method,
            },
        )

    command_payload = {
        "transit_resource_id": resource.id,
        "transit_resource_name": resource.name,
        "transit_worker_id": target_worker.id,
        "interface_name": target_worker.interface_name,
        "landing_node_id": node.id,
        "landing_node_name": node.node_name,
        "planned_listen_port": payload.planned_listen_port,
        "landing_target_host": payload.landing_target_host,
        "landing_target_port": payload.landing_target_port,
        "forwarding_method": payload.forwarding_method,
        "purpose": payload.purpose,
        "approval_stage": payload.approval_stage,
        "dry_run": False,
        "approval_required": False,
        "execution_mode": "real_create",
        "approved_real_execution": True,
        "route_name": payload.route_name,
        "firewall_security_group_confirmed": True,
        "cloud_firewall_confirmed": True,
        "server_firewall_confirmed": True,
        "no_node_share_link_change_confirmed": True,
        "no_full_client_link_confirmed": True,
        "no_cutover_confirmed": True,
        "safety_boundary": TRANSIT_ROUTE_CREATE_REAL_BOUNDARY,
    }
    if payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP:
        command_payload.update(
            {
                "approved_planned_listen_port": payload.planned_listen_port,
                "approved_firewall_confirmation": True,
                "approved_landing_target_host": payload.landing_target_host,
                "approved_landing_target_port": payload.landing_target_port,
            }
        )
    command = create_worker_command(db, target_worker, TRANSIT_ROUTE_CREATE_COMMAND, command_payload)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_transit_route_worker_create_execute",
        result="success",
        request=request,
        resource_type="worker_command",
        resource_id=command.id,
    )
    db.commit()
    db.refresh(command)

    return success_response(
        {
            "command": serialize_worker_command(command, include_payload=True, worker=target_worker),
            "target_worker_id": target_worker.id,
            "target_worker_version": target_worker.worker_version,
            "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(
                payload.forwarding_method
            ),
            "execution_mode": "real_create",
            "approval_required": False,
            "safety_boundary": TRANSIT_ROUTE_CREATE_REAL_BOUNDARY,
        },
        "中转链路真实创建 Worker command 已创建；结果成功后才会写入 transit_routes，不读取或修改 nodes.share_link。",
    )
