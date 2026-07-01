import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import quote, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.db.session import get_db
from app.models.node import Node
from app.models.task import Task
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer
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
    TransitRouteRenameRequest,
    TransitRouteWorkerCreateExecuteRequest,
    TransitRouteWorkerCreatePlanRequest,
    haproxy_real_execution_confirmation_text,
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
PROTECTED_RESOURCE_REGISTRATION_UI_STAGE = "Stage 3.4.26-advanced-debug-protected-resource-registration-ui"
PROTECTED_RESOURCE_REGISTRATION_DRY_RUN_STAGE = "Stage 3.4.27-advanced-debug-protected-resource-registration-dry-run"
PROTECTED_RESOURCE_REGISTRATION_APPROVAL_STAGE = "Stage 3.4.28-advanced-debug-protected-resource-registration-approval"
PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_STAGE = "3.4.28"
PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_MODE = "approval_dry_run"
PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_NEXT_STAGE = (
    "Stage 3.4.29-protected-resource-registration-command-create"
)
PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_STAGE = "3.4.29"
PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_MODE = "command_create"
PROTECTED_RESOURCE_REGISTRATION_COMMAND_TASK_TYPE = "protected_resource_registration_command"
PROTECTED_RESOURCE_REGISTRATION_COMMAND_STATUS = "pending_protected_registration_execution"
PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_NEXT_STAGE = (
    "Stage 3.4.30-protected-resource-registration-execution-verify"
)
PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_STAGE = "3.4.30"
PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_MODE = "execution_verify"
PROTECTED_RESOURCE_REGISTRATION_EXECUTED_STATUS = "executed_verified"
PROTECTED_RESOURCE_REGISTRATION_HAPROXY_DRY_RUN_NEXT_STAGE = "Stage 3.4.31-regenerate-haproxy-dry-run"
PROTECTED_RESOURCE_REGISTRATION_REQUIRED_BOUNDARY = [
    "preview_only",
    "不提交后端",
    "不创建 transit_resource",
    "不创建 landing_node",
    "不创建 WorkerCommand",
    "不创建 TransitRoute",
    "不 SSH / 不远程执行",
    "不修改防火墙 / 云安全组 / 云防火墙",
    "不读取、不输出、不修改完整 share_link",
    "不 cutover",
]


class ProtectedRegistrationSource(BaseModel):
    dry_run_command_id: str = Field(default="", max_length=80)
    route_name: str = Field(default="", max_length=160)
    planned_listen_port: int | None = None
    landing_target_host: str = Field(default="", max_length=255)
    landing_target_port: int | None = None
    candidate_integrity_ready: bool = False


class ProtectedRegistrationTransitResource(BaseModel):
    name: str = Field(default="", max_length=120)
    resource_type: str = Field(default="")
    entry_host: str = Field(default="", max_length=255)
    entry_port: int | None = None
    entry_region: str = Field(default="", max_length=120)
    exit_region: str = Field(default="", max_length=120)
    expected_status: str = Field(default="")
    worker_role: str = Field(default="")
    worker_binding_required: bool = False


class ProtectedRegistrationLandingNode(BaseModel):
    node_name: str = Field(default="", max_length=120)
    vps_ip: str = Field(default="", max_length=45)
    xray_port: int | None = None
    expected_status: str = Field(default="")
    share_link_handling: str = Field(default="", max_length=120)


class ProtectedRegistrationConfirmations(BaseModel):
    manual_confirm_transit_host: bool = False
    manual_confirm_worker_binding: bool = False
    manual_confirm_landing_host: bool = False
    manual_confirm_landing_port: bool = False
    manual_confirm_no_share_link_export: bool = False
    manual_confirm_no_remote_execution: bool = False
    manual_confirm_no_firewall_change: bool = False
    manual_confirm_no_cutover: bool = False


class ProtectedResourceRegistrationDryRunRequest(BaseModel):
    stage: str = Field(default="", max_length=120)
    mode: str = Field(default="", max_length=40)
    source: ProtectedRegistrationSource = Field(default_factory=ProtectedRegistrationSource)
    transit_resource_registration: ProtectedRegistrationTransitResource = Field(
        default_factory=ProtectedRegistrationTransitResource,
    )
    landing_node_registration: ProtectedRegistrationLandingNode = Field(default_factory=ProtectedRegistrationLandingNode)
    confirmations: ProtectedRegistrationConfirmations = Field(default_factory=ProtectedRegistrationConfirmations)
    safety_boundary: list[str] = Field(default_factory=list, max_length=80)


class ProtectedRegistrationApprovalSourceDryRun(BaseModel):
    dry_run: bool = False
    ready_for_next_stage: bool = False
    expected_approval_text: str = Field(default="", max_length=200)
    normalized_preview: dict[str, object] = Field(default_factory=dict)


class ProtectedRegistrationApprovalConfirmations(BaseModel):
    registration_dry_run_passed: bool = False
    approval_text_matches_expected: bool = False
    no_real_resource_creation: bool = False
    no_worker_command_creation: bool = False
    no_transit_route_creation: bool = False
    no_haproxy_route_creation: bool = False
    no_ssh_or_remote_execution: bool = False
    no_firewall_change: bool = False
    no_cutover: bool = False
    ordinary_product_ui_unchanged: bool = False
    sensitive_fields_redacted: bool = False


class ProtectedResourceRegistrationApprovalDryRunRequest(BaseModel):
    stage: str = Field(default="", max_length=40)
    mode: str = Field(default="", max_length=40)
    source_registration_dry_run: ProtectedRegistrationApprovalSourceDryRun = Field(
        default_factory=ProtectedRegistrationApprovalSourceDryRun,
    )
    approval_text: str = Field(default="", max_length=200)
    confirmations: ProtectedRegistrationApprovalConfirmations = Field(
        default_factory=ProtectedRegistrationApprovalConfirmations,
    )


class ProtectedRegistrationCommandSourceApprovalDryRun(BaseModel):
    dry_run: bool = False
    stage: str = Field(default="", max_length=40)
    mode: str = Field(default="", max_length=40)
    approved_for_next_stage: bool = False
    ready_for_command_create_next_stage: bool = False
    normalized_approval_preview: dict[str, object] = Field(default_factory=dict)
    safety_boundary: dict[str, object] = Field(default_factory=dict)


class ProtectedRegistrationCommandConfirmations(BaseModel):
    approval_dry_run_passed: bool = False
    create_local_pending_command_only: bool = False
    no_real_resource_creation: bool = False
    no_transit_resource_creation: bool = False
    no_landing_node_creation: bool = False
    no_worker_remote_execution: bool = False
    no_transit_route_creation: bool = False
    no_haproxy_route_creation: bool = False
    no_listening_port_change: bool = False
    no_ssh_or_remote_execution: bool = False
    no_firewall_change: bool = False
    no_cutover: bool = False
    ordinary_product_ui_unchanged: bool = False
    sensitive_fields_redacted: bool = False


class ProtectedResourceRegistrationCommandCreateRequest(BaseModel):
    stage: str = Field(default="", max_length=40)
    mode: str = Field(default="", max_length=40)
    source_approval_dry_run: ProtectedRegistrationCommandSourceApprovalDryRun = Field(
        default_factory=ProtectedRegistrationCommandSourceApprovalDryRun,
    )
    confirmations: ProtectedRegistrationCommandConfirmations = Field(
        default_factory=ProtectedRegistrationCommandConfirmations,
    )


class ProtectedRegistrationExecutionConfirmations(BaseModel):
    command_was_created_by_stage_3_4_29: bool = False
    command_is_pending: bool = False
    approval_dry_run_passed: bool = False
    execute_local_db_registration_only: bool = False
    allow_create_transit_resource_record: bool = False
    allow_create_landing_node_record: bool = False
    no_worker_command_creation: bool = False
    no_transit_route_creation: bool = False
    no_haproxy_route_creation: bool = False
    no_haproxy_config_generation: bool = False
    no_listening_port_change: bool = False
    no_ssh_or_remote_execution: bool = False
    no_firewall_change: bool = False
    no_cutover: bool = False
    ordinary_product_ui_unchanged: bool = False
    sensitive_fields_redacted: bool = False


class ProtectedResourceRegistrationExecutionVerifyRequest(BaseModel):
    stage: str = Field(default="", max_length=40)
    mode: str = Field(default="", max_length=40)
    command_id: str = Field(default="", max_length=80)
    execution_approval_text: str = Field(default="", max_length=180)
    confirmations: ProtectedRegistrationExecutionConfirmations = Field(
        default_factory=ProtectedRegistrationExecutionConfirmations,
    )


ProtectedRegistrationSeverity = Literal["info", "warning", "danger"]


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
HAPROXY_ROUTE_REAL_EXECUTION_READINESS_BOUNDARY = [
    "advanced-debug readiness only",
    "no Worker command created",
    "no real execution command created",
    "no HAProxy route created",
    "no TransitRoute active record created",
    "no HAProxy install, start, stop, or restart",
    "no listener binding",
    "no firewall, cloud firewall, or cloud security group mutation",
    "no SSH",
    "no remote execution",
    "no arbitrary shell accepted",
    "no arbitrary systemd or HAProxy config accepted from API",
    "no nodes.share_link read or mutation",
    "no transit_routes.share_link write",
    "no full client link export",
    "no cutover",
]
HAPROXY_RUNTIME_DEBUG_CONTEXT_BOUNDARY = [
    "advanced-debug context autofill only",
    "read local control-plane records only",
    "no Worker command created",
    "no TransitRoute created",
    "no SSH",
    "no remote execution",
    "no listener binding",
    "no firewall, cloud firewall, or cloud security group mutation",
    "no share_link export",
    "no full client link export",
    "no cutover",
]


def isoformat_or_none(value) -> str | None:
    return value.isoformat() if value else None


def optional_int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def current_worker_by_server(workers: list[Worker]) -> dict[str, Worker]:
    epoch = datetime.min.replace(tzinfo=UTC)
    sorted_workers = sorted(
        workers,
        key=lambda worker: (
            worker.last_heartbeat_at or epoch,
            worker.registered_at or epoch,
            worker.created_at or epoch,
        ),
        reverse=True,
    )
    by_server: dict[str, Worker] = {}
    for worker in sorted_workers:
        if worker.server_id and worker.server_id not in by_server:
            by_server[worker.server_id] = worker
    return by_server


def serialize_haproxy_runtime_debug_transit_resource(
    resource: TransitResource,
    worker: Worker | None,
) -> dict:
    runtime_status = worker_runtime_status(worker) if worker else "missing"
    return {
        "id": resource.id,
        "name": resource.name,
        "resource_type": resource.resource_type,
        "entry_host": resource.entry_host,
        "entry_port": resource.entry_port,
        "entry_region": resource.entry_region,
        "exit_region": resource.exit_region,
        "status": resource.status,
        "deleted_at": isoformat_or_none(resource.deleted_at),
        "worker_id": worker.id if worker else None,
        "worker_status": worker.status if worker else None,
        "worker_runtime_status": runtime_status,
        "worker_online": bool(worker and worker.status == "online" and runtime_status == "online"),
        "worker_version": worker.worker_version if worker else None,
        "worker_hostname": worker.hostname if worker else None,
        "worker_interface_name": worker.interface_name if worker else None,
        "worker_last_heartbeat_at": isoformat_or_none(worker.last_heartbeat_at) if worker else None,
    }


def serialize_haproxy_runtime_debug_landing_node(node: Node) -> dict:
    vps = node.vps
    return {
        "id": node.id,
        "node_name": node.node_name,
        "vps_id": node.vps_id,
        "vps_ip": vps.ip if vps else None,
        "xray_port": node.xray_port,
        "target_host": vps.ip if vps else None,
        "target_port": node.xray_port,
        "status": node.status,
        "service_status": node.service_status,
        "share_link_present": bool(node.share_link),
        "masked_share_link": "[REDACTED_SHARE_LINK]" if node.share_link else None,
        "deleted_at": isoformat_or_none(node.deleted_at),
        "created_at": isoformat_or_none(node.created_at),
    }


def haproxy_dry_run_candidate_from_command(command: WorkerCommand) -> dict | None:
    payload = command.payload_json if isinstance(command.payload_json, dict) else {}
    if command.command_type != TRANSIT_ROUTE_CREATE_COMMAND:
        return None
    if command.status not in {"created", "pending", "running", "succeeded", "failed"}:
        return None
    if payload.get("command_intent") != "haproxy_route_create_dry_run":
        return None
    if payload.get("forwarding_method") != FORWARDING_METHOD_HAPROXY_TCP:
        return None
    if payload.get("dry_run") is not True:
        return None
    if payload.get("real_execution") is not False:
        return None

    planned_listen_port = optional_int(payload.get("planned_listen_port"))
    approved_planned_listen_port = optional_int(payload.get("approved_planned_listen_port"))
    landing_target_port = optional_int(payload.get("landing_target_port"))
    approved_landing_target_port = optional_int(payload.get("approved_landing_target_port"))
    return {
        "id": command.id,
        "status": command.status,
        "created_at": isoformat_or_none(command.created_at),
        "updated_at": isoformat_or_none(command.updated_at),
        "worker_id": command.worker_id,
        "target_worker_id": payload.get("transit_worker_id") or command.worker_id,
        "transit_resource_id": payload.get("transit_resource_id"),
        "landing_node_id": payload.get("landing_node_id"),
        "planned_listen_port": planned_listen_port,
        "approved_planned_listen_port": approved_planned_listen_port,
        "landing_target_host": payload.get("landing_target_host"),
        "approved_landing_target_host": payload.get("approved_landing_target_host"),
        "landing_target_port": landing_target_port,
        "approved_landing_target_port": approved_landing_target_port,
        "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
        "route_name": payload.get("route_name"),
        "route_display_name": payload.get("route_display_name"),
        "planned_service_name": payload.get("planned_service_name"),
        "command_intent": payload.get("command_intent"),
        "approval_stage": payload.get("approval_stage"),
        "dry_run": payload.get("dry_run"),
        "approval_required": payload.get("approval_required"),
        "real_execution": payload.get("real_execution"),
        "user_approved_real_execution": payload.get("user_approved_real_execution"),
        "approved_firewall_confirmation": payload.get("approved_firewall_confirmation"),
    }


def make_haproxy_context_integrity_check(
    *,
    check_id: str,
    label: str,
    passed: bool,
    message: str,
    next_action: str,
    evidence_summary: str | None = None,
    failure_severity: str = "danger",
) -> dict:
    return {
        "id": check_id,
        "label": label,
        "passed": passed,
        "severity": "success" if passed else failure_severity,
        "message": message,
        "next_action": next_action,
        "evidence_summary": evidence_summary,
    }


def attach_haproxy_dry_run_candidate_integrity(
    candidate: dict,
    *,
    resources_by_id: dict[str, TransitResource],
    nodes_by_id: dict[str, Node],
    workers_by_id: dict[str, Worker],
) -> dict:
    transit_resource_id = candidate.get("transit_resource_id")
    landing_node_id = candidate.get("landing_node_id")
    worker_id = candidate.get("target_worker_id") or candidate.get("worker_id")
    resource = resources_by_id.get(transit_resource_id) if transit_resource_id else None
    node = nodes_by_id.get(landing_node_id) if landing_node_id else None
    worker = workers_by_id.get(worker_id) if worker_id else None
    worker_status = worker_runtime_status(worker) if worker else "missing"
    node_vps_ip = node.vps.ip if node and node.vps else None
    node_port = node.xray_port if node else None
    candidate_landing_host = candidate.get("landing_target_host")
    candidate_landing_port = candidate.get("landing_target_port")

    checks = [
        make_haproxy_context_integrity_check(
            check_id="transit_resource_record_exists",
            label="中转资源记录存在",
            passed=resource is not None,
            message="candidate 引用的中转资源记录存在。" if resource else "candidate 引用的中转资源记录不存在。",
            next_action="重新选择存在的中转资源并重新生成 HAProxy dry-run。" if not resource else "继续检查。",
            evidence_summary=resource.name if resource else str(transit_resource_id or "missing"),
        ),
        make_haproxy_context_integrity_check(
            check_id="transit_resource_not_deleted",
            label="中转资源未删除",
            passed=bool(resource and resource.deleted_at is None),
            message="中转资源未删除。" if resource and resource.deleted_at is None else "中转资源已删除或不可用。",
            next_action="选择未删除的中转资源并重新生成 dry-run。" if not resource or resource.deleted_at is not None else "继续检查。",
            evidence_summary=resource.status if resource else None,
        ),
        make_haproxy_context_integrity_check(
            check_id="transit_resource_status_supported",
            label="中转资源状态支持创建",
            passed=bool(resource and resource.status in TRANSIT_RESOURCE_CREATE_STATUSES),
            message="中转资源状态允许 HAProxy 创建流程。" if resource and resource.status in TRANSIT_RESOURCE_CREATE_STATUSES else "中转资源状态不允许 HAProxy 创建流程。",
            next_action="等待中转资源恢复 active / worker_online 后重新生成 dry-run。" if not resource or resource.status not in TRANSIT_RESOURCE_CREATE_STATUSES else "继续检查。",
            evidence_summary=resource.status if resource else None,
        ),
        make_haproxy_context_integrity_check(
            check_id="transit_worker_record_exists",
            label="Transit Worker 记录存在",
            passed=worker is not None,
            message="candidate 引用的 Transit Worker 记录存在。" if worker else "candidate 引用的 Transit Worker 记录不存在。",
            next_action="重新安装 / 升级中转 Worker，等待心跳后重新生成 dry-run。" if not worker else "继续检查。",
            evidence_summary=worker.id if worker else str(worker_id or "missing"),
        ),
        make_haproxy_context_integrity_check(
            check_id="transit_worker_online",
            label="Transit Worker 在线",
            passed=bool(worker and worker.status == "online" and worker_status == "online"),
            message="Transit Worker 在线且心跳有效。" if worker and worker.status == "online" and worker_status == "online" else "Transit Worker 不在线或心跳过期。",
            next_action="等待 Transit Worker 恢复 online 后重新生成 dry-run。" if not worker or worker.status != "online" or worker_status != "online" else "继续检查。",
            evidence_summary=worker_status,
        ),
        make_haproxy_context_integrity_check(
            check_id="transit_worker_role_is_transit",
            label="Worker role 为 transit",
            passed=bool(worker and worker.role == "transit"),
            message="Worker role 正确。" if worker and worker.role == "transit" else "Worker role 不是 transit。",
            next_action="使用 transit role Worker 重新生成 dry-run。" if not worker or worker.role != "transit" else "继续检查。",
            evidence_summary=worker.role if worker else None,
        ),
        make_haproxy_context_integrity_check(
            check_id="transit_worker_interface_detected",
            label="Worker 已上报网卡",
            passed=bool(worker and worker.interface_name),
            message="Worker 已上报 interface_name。" if worker and worker.interface_name else "Worker 未上报 interface_name。",
            next_action="等待 Worker heartbeat 上报 interface_name 后重新生成 dry-run。" if not worker or not worker.interface_name else "继续检查。",
            evidence_summary=worker.interface_name if worker else None,
        ),
        make_haproxy_context_integrity_check(
            check_id="landing_node_record_exists",
            label="落地节点记录存在",
            passed=node is not None,
            message="candidate 引用的落地节点记录存在。" if node else "candidate 引用的落地节点记录不存在。",
            next_action="选择存在的 active 落地节点并重新生成 dry-run。" if not node else "继续检查。",
            evidence_summary=node.node_name if node else str(landing_node_id or "missing"),
        ),
        make_haproxy_context_integrity_check(
            check_id="landing_node_not_deleted",
            label="落地节点未删除",
            passed=bool(node and node.deleted_at is None),
            message="落地节点未删除。" if node and node.deleted_at is None else "落地节点已删除或不可用。",
            next_action="选择未删除的落地节点并重新生成 dry-run。" if not node or node.deleted_at is not None else "继续检查。",
            evidence_summary=node.status if node else None,
        ),
        make_haproxy_context_integrity_check(
            check_id="landing_node_active",
            label="落地节点 active",
            passed=bool(node and node.status == "active"),
            message="落地节点处于 active 状态。" if node and node.status == "active" else "落地节点不是 active 状态。",
            next_action="选择 active 落地节点并重新生成 dry-run。" if not node or node.status != "active" else "继续检查。",
            evidence_summary=node.status if node else None,
        ),
        make_haproxy_context_integrity_check(
            check_id="landing_node_has_vps_ip",
            label="落地节点有 VPS IP",
            passed=bool(node_vps_ip),
            message="落地节点绑定的 VPS IP 可用。" if node_vps_ip else "落地节点缺少 VPS IP。",
            next_action="检查落地服务器记录是否存在 IP，再重新生成 dry-run。" if not node_vps_ip else "继续检查。",
            evidence_summary=node_vps_ip,
        ),
        make_haproxy_context_integrity_check(
            check_id="landing_node_xray_port_present",
            label="落地节点有 Xray 端口",
            passed=bool(node_port),
            message="落地节点 xray_port 可用。" if node_port else "落地节点缺少 xray_port。",
            next_action="选择已创建直连节点的落地记录并重新生成 dry-run。" if not node_port else "继续检查。",
            evidence_summary=str(node_port) if node_port else None,
        ),
        make_haproxy_context_integrity_check(
            check_id="candidate_landing_host_matches_node_vps_ip",
            label="candidate host 匹配落地 VPS IP",
            passed=bool(node_vps_ip and candidate_landing_host == node_vps_ip),
            message="candidate landing_target_host 与正式落地节点 VPS IP 一致。" if node_vps_ip and candidate_landing_host == node_vps_ip else "candidate landing_target_host 与正式落地节点 VPS IP 不一致。",
            next_action="使用当前正式落地节点重新生成 dry-run。" if not node_vps_ip or candidate_landing_host != node_vps_ip else "继续检查。",
            evidence_summary=f"candidate={candidate_landing_host or '-'} / node={node_vps_ip or '-'}",
        ),
        make_haproxy_context_integrity_check(
            check_id="candidate_landing_port_matches_node_xray_port",
            label="candidate port 匹配落地 Xray 端口",
            passed=bool(node_port and candidate_landing_port == node_port),
            message="candidate landing_target_port 与正式落地节点 xray_port 一致。" if node_port and candidate_landing_port == node_port else "candidate landing_target_port 与正式落地节点 xray_port 不一致。",
            next_action="使用当前正式落地节点重新生成 dry-run。" if not node_port or candidate_landing_port != node_port else "继续检查。",
            evidence_summary=f"candidate={candidate_landing_port or '-'} / node={node_port or '-'}",
        ),
        make_haproxy_context_integrity_check(
            check_id="candidate_forwarding_method_is_haproxy_tcp",
            label="candidate forwarding_method 为 haproxy_tcp",
            passed=candidate.get("forwarding_method") == FORWARDING_METHOD_HAPROXY_TCP,
            message="candidate 是 HAProxy TCP dry-run。" if candidate.get("forwarding_method") == FORWARDING_METHOD_HAPROXY_TCP else "candidate 不是 HAProxy TCP。",
            next_action="选择 HAProxy TCP dry-run candidate。" if candidate.get("forwarding_method") != FORWARDING_METHOD_HAPROXY_TCP else "继续检查。",
            evidence_summary=str(candidate.get("forwarding_method") or "missing"),
        ),
        make_haproxy_context_integrity_check(
            check_id="candidate_is_dry_run",
            label="candidate 是 dry-run",
            passed=candidate.get("dry_run") is True,
            message="candidate 标记为 dry-run。" if candidate.get("dry_run") is True else "candidate 未标记为 dry-run。",
            next_action="选择 dry_run=true 的 HAProxy candidate。" if candidate.get("dry_run") is not True else "继续检查。",
            evidence_summary=str(candidate.get("dry_run")),
        ),
        make_haproxy_context_integrity_check(
            check_id="candidate_is_not_real_execution",
            label="candidate 不是 real execution",
            passed=candidate.get("real_execution") is False,
            message="candidate 未执行真实创建。" if candidate.get("real_execution") is False else "candidate 已是 real execution 或字段缺失。",
            next_action="选择 real_execution=false 的 dry-run candidate。" if candidate.get("real_execution") is not False else "继续检查。",
            evidence_summary=str(candidate.get("real_execution")),
        ),
        make_haproxy_context_integrity_check(
            check_id="candidate_status_succeeded",
            label="candidate status 为 succeeded",
            passed=candidate.get("status") == "succeeded",
            message="dry-run command 已 succeeded。" if candidate.get("status") == "succeeded" else "dry-run command 尚未 succeeded。",
            next_action="等待 dry-run succeeded，或重新生成成功的 dry-run 后再继续。" if candidate.get("status") != "succeeded" else "继续检查。",
            evidence_summary=str(candidate.get("status") or "missing"),
        ),
    ]
    blocking_checks = [check for check in checks if not check["passed"] and check["severity"] == "danger"]
    integrity_ready = not blocking_checks
    return {
        **candidate,
        "integrity_ready": integrity_ready,
        "integrity_blocked": not integrity_ready,
        "integrity_summary": (
            "上下文完整，可继续 readiness。"
            if integrity_ready
            else "上下文不完整，不能继续 readiness / real execution。"
        ),
        "integrity_next_action": (
            "人工确认端口放行与安全项后运行 readiness。"
            if integrity_ready
            else blocking_checks[0]["next_action"]
        ),
        "integrity_checks": checks,
    }


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


def protected_registration_port_valid(value: int | None) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 65535


def protected_registration_text(value: str | None) -> str:
    return (value or "").strip()


def protected_registration_sensitive_terms() -> tuple[str, ...]:
    return (
        "vless" + "://",
        "begin " + "openssh",
        "begin " + "rsa",
        "private" + "_key",
        "private key",
        "install" + "_command",
        "to" + "ken",
        "pass" + "word",
    )


def protected_registration_contains_sensitive_value(value: object) -> bool:
    if isinstance(value, dict):
        return any(protected_registration_contains_sensitive_value(item) for item in value.values())
    if isinstance(value, list):
        return any(protected_registration_contains_sensitive_value(item) for item in value)
    if not isinstance(value, str):
        return False
    lowered = value.lower()
    return any(term in lowered for term in protected_registration_sensitive_terms())


def protected_registration_sanitize_text(value: str | None) -> str:
    cleaned = protected_registration_text(value)
    if protected_registration_contains_sensitive_value(cleaned):
        return "[redacted sensitive value]"
    return cleaned


def protected_registration_preview_record(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def protected_registration_record_text(record: dict, key: str) -> str:
    value = record.get(key)
    if value is None:
        return ""
    return protected_registration_sanitize_text(str(value))


def protected_registration_safe_source_preview(normalized_preview: dict[str, object] | None) -> dict:
    preview = protected_registration_preview_record(normalized_preview)
    if protected_registration_contains_sensitive_value(preview):
        return {}
    source = protected_registration_preview_record(preview.get("source"))
    transit = protected_registration_preview_record(preview.get("transit_resource_registration"))
    landing = protected_registration_preview_record(preview.get("landing_node_registration"))
    safe_preview = {
        "source": {
            "dry_run_command_id": protected_registration_record_text(source, "dry_run_command_id"),
            "route_name": protected_registration_record_text(source, "route_name"),
            "planned_listen_port": _payload_int(source, "planned_listen_port"),
            "landing_target_host": protected_registration_record_text(source, "landing_target_host"),
            "landing_target_port": _payload_int(source, "landing_target_port"),
            "candidate_integrity_ready": source.get("candidate_integrity_ready") is True,
        },
        "transit_resource_registration": {
            "name": protected_registration_record_text(transit, "name"),
            "resource_type": protected_registration_record_text(transit, "resource_type"),
            "entry_host": protected_registration_record_text(transit, "entry_host"),
            "entry_port": _payload_int(transit, "entry_port"),
            "entry_region": protected_registration_record_text(transit, "entry_region"),
            "exit_region": protected_registration_record_text(transit, "exit_region"),
            "expected_status": protected_registration_record_text(transit, "expected_status"),
            "worker_role": protected_registration_record_text(transit, "worker_role"),
            "worker_binding_required": transit.get("worker_binding_required") is True,
        },
        "landing_node_registration": {
            "node_name": protected_registration_record_text(landing, "node_name"),
            "vps_ip": protected_registration_record_text(landing, "vps_ip"),
            "xray_port": _payload_int(landing, "xray_port"),
            "expected_status": protected_registration_record_text(landing, "expected_status"),
        },
    }
    if protected_registration_contains_sensitive_value(safe_preview):
        return {}
    return safe_preview


def protected_registration_preview_complete(registration_source: dict | None) -> bool:
    source = protected_registration_preview_record((registration_source or {}).get("source"))
    transit = protected_registration_preview_record((registration_source or {}).get("transit_resource_registration"))
    landing = protected_registration_preview_record((registration_source or {}).get("landing_node_registration"))
    return all(
        [
            bool(protected_registration_record_text(source, "dry_run_command_id")),
            bool(protected_registration_record_text(source, "route_name")),
            protected_registration_port_valid(_payload_int(source, "planned_listen_port")),
            bool(protected_registration_record_text(transit, "name")),
            bool(protected_registration_record_text(transit, "entry_host")),
            protected_registration_port_valid(_payload_int(transit, "entry_port")),
            bool(protected_registration_record_text(landing, "node_name")),
            bool(protected_registration_record_text(landing, "vps_ip")),
            protected_registration_port_valid(_payload_int(landing, "xray_port")),
        ]
    )


def make_protected_registration_check(
    *,
    check_id: str,
    label: str,
    passed: bool,
    message: str,
    next_action: str,
    severity: ProtectedRegistrationSeverity | None = None,
    evidence_summary: str | None = None,
) -> dict:
    return {
        "id": check_id,
        "label": label,
        "passed": passed,
        "severity": severity or ("info" if passed else "danger"),
        "message": message,
        "next_action": next_action,
        "evidence_summary": evidence_summary,
    }


def protected_registration_active_transit_resource_duplicates(
    db: Session,
    *,
    field_name: str,
    value: str,
) -> list[TransitResource]:
    if not value:
        return []
    field = TransitResource.name if field_name == "name" else TransitResource.entry_host
    return db.scalars(
        select(TransitResource)
        .where(TransitResource.deleted_at.is_(None))
        .where(TransitResource.status.in_(("active", "worker_online")))
        .where(field == value)
    ).all()


def protected_registration_active_landing_node_duplicates(
    db: Session,
    *,
    vps_ip: str,
    xray_port: int | None,
) -> list[Node]:
    if not vps_ip or not protected_registration_port_valid(xray_port):
        return []
    nodes = db.scalars(
        select(Node)
        .where(Node.deleted_at.is_(None))
        .where(Node.status == "active")
        .where(Node.xray_port == xray_port)
    ).all()
    return [node for node in nodes if node.vps and node.vps.ip == vps_ip]


def build_protected_resource_registration_dry_run(
    db: Session,
    payload: ProtectedResourceRegistrationDryRunRequest,
) -> dict:
    source = payload.source
    transit = payload.transit_resource_registration
    landing = payload.landing_node_registration
    confirmations = payload.confirmations
    source_command = db.get(WorkerCommand, source.dry_run_command_id) if source.dry_run_command_id else None
    source_payload = source_command.payload_json if source_command and isinstance(source_command.payload_json, dict) else {}
    command_landing_host = protected_registration_text(_payload_text(source_payload, "landing_target_host"))
    command_route_name = protected_registration_text(_payload_text(source_payload, "route_name"))
    command_planned_listen_port = _payload_int(source_payload, "planned_listen_port")
    command_landing_port = _payload_int(source_payload, "landing_target_port")
    normalized_preview = {
        "source": {
            "dry_run_command_id": protected_registration_sanitize_text(source.dry_run_command_id),
            "route_name": protected_registration_sanitize_text(source.route_name),
            "planned_listen_port": source.planned_listen_port,
            "landing_target_host": protected_registration_sanitize_text(source.landing_target_host),
            "landing_target_port": source.landing_target_port,
            "candidate_integrity_ready": source.candidate_integrity_ready,
        },
        "transit_resource_registration": {
            "name": protected_registration_sanitize_text(transit.name),
            "resource_type": protected_registration_sanitize_text(transit.resource_type),
            "entry_host": protected_registration_sanitize_text(transit.entry_host),
            "entry_port": transit.entry_port,
            "entry_region": protected_registration_sanitize_text(transit.entry_region),
            "exit_region": protected_registration_sanitize_text(transit.exit_region),
            "expected_status": protected_registration_sanitize_text(transit.expected_status),
            "worker_role": protected_registration_sanitize_text(transit.worker_role),
            "worker_binding_required": transit.worker_binding_required,
        },
        "landing_node_registration": {
            "node_name": protected_registration_sanitize_text(landing.node_name),
            "vps_ip": protected_registration_sanitize_text(landing.vps_ip),
            "xray_port": landing.xray_port,
            "expected_status": protected_registration_sanitize_text(landing.expected_status),
            "share_link_handling": protected_registration_sanitize_text(landing.share_link_handling),
        },
        "confirmations": confirmations.model_dump(),
        "safety_boundary": [protected_registration_sanitize_text(item) for item in payload.safety_boundary],
    }
    required_boundary_set = set(PROTECTED_RESOURCE_REGISTRATION_REQUIRED_BOUNDARY)
    safety_boundary_set = set(payload.safety_boundary)
    confirmation_values = confirmations.model_dump()
    transit_name = protected_registration_text(transit.name)
    transit_entry_host = protected_registration_text(transit.entry_host)
    landing_vps_ip = protected_registration_text(landing.vps_ip)
    checks: list[dict] = [
        make_protected_registration_check(
            check_id="stage_is_expected",
            label="Stage 来源正确",
            passed=payload.stage == PROTECTED_RESOURCE_REGISTRATION_UI_STAGE,
            message="Payload 来自 Stage 3.4.26 准备 UI。" if payload.stage == PROTECTED_RESOURCE_REGISTRATION_UI_STAGE else "Payload stage 不匹配。",
            next_action="使用 Stage 3.4.26 生成的登记 payload。" if payload.stage != PROTECTED_RESOURCE_REGISTRATION_UI_STAGE else "继续检查。",
            evidence_summary=payload.stage,
        ),
        make_protected_registration_check(
            check_id="mode_is_preview_only",
            label="Mode 为 preview_only",
            passed=payload.mode == "preview_only",
            message="Payload 保持 preview_only。" if payload.mode == "preview_only" else "Payload mode 不是 preview_only。",
            next_action="将 mode 设置为 preview_only 后重新 dry-run。" if payload.mode != "preview_only" else "继续检查。",
            evidence_summary=payload.mode,
        ),
        make_protected_registration_check(
            check_id="safety_boundary_present",
            label="安全边界完整",
            passed=required_boundary_set.issubset(safety_boundary_set),
            message="安全边界包含所有必需项。" if required_boundary_set.issubset(safety_boundary_set) else "安全边界缺少必需项。",
            next_action="重新复制 Stage 3.4.26 登记 payload，确保 safety_boundary 完整。",
            evidence_summary=f"{len(required_boundary_set.intersection(safety_boundary_set))}/{len(required_boundary_set)}",
        ),
        make_protected_registration_check(
            check_id="no_share_link_export_confirmed",
            label="确认不处理完整客户端配置",
            passed=confirmations.manual_confirm_no_share_link_export,
            message="已确认不读取、不输出、不修改完整客户端配置。" if confirmations.manual_confirm_no_share_link_export else "尚未确认不处理完整客户端配置。",
            next_action="勾选不读取、不输出、不修改完整客户端配置确认项。",
        ),
        make_protected_registration_check(
            check_id="no_remote_execution_confirmed",
            label="确认不远程执行",
            passed=confirmations.manual_confirm_no_remote_execution,
            message="已确认不 SSH、不远程执行。" if confirmations.manual_confirm_no_remote_execution else "尚未确认不 SSH、不远程执行。",
            next_action="勾选不 SSH、不远程执行确认项。",
        ),
        make_protected_registration_check(
            check_id="no_firewall_change_confirmed",
            label="确认不修改防火墙",
            passed=confirmations.manual_confirm_no_firewall_change,
            message="已确认不修改防火墙 / 云安全组 / 云防火墙。" if confirmations.manual_confirm_no_firewall_change else "尚未确认不修改防火墙。",
            next_action="勾选不修改防火墙确认项。",
        ),
        make_protected_registration_check(
            check_id="no_cutover_confirmed",
            label="确认不 cutover",
            passed=confirmations.manual_confirm_no_cutover,
            message="已确认不 cutover。" if confirmations.manual_confirm_no_cutover else "尚未确认不 cutover。",
            next_action="勾选不 cutover 确认项。",
        ),
        make_protected_registration_check(
            check_id="all_manual_confirmations_present",
            label="人工确认完整",
            passed=all(bool(value) for value in confirmation_values.values()),
            message="所有人工确认项已勾选。" if all(bool(value) for value in confirmation_values.values()) else "仍有人工确认项未勾选。",
            next_action="补齐所有人工确认项后重新 dry-run。",
            evidence_summary=f"{sum(1 for value in confirmation_values.values() if value)}/{len(confirmation_values)}",
        ),
    ]
    checks.extend(
        [
            make_protected_registration_check(
                check_id="source_dry_run_command_exists",
                label="来源 dry-run command 存在",
                passed=source_command is not None,
                message="来源 dry-run command 存在。" if source_command else "来源 dry-run command 不存在。",
                next_action="选择存在的 HAProxy TCP dry-run command。",
                evidence_summary=source.dry_run_command_id or "missing",
            ),
            make_protected_registration_check(
                check_id="source_dry_run_status_succeeded",
                label="来源 dry-run 已成功",
                passed=bool(source_command and source_command.status == "succeeded"),
                message="来源 dry-run command 已 succeeded。" if source_command and source_command.status == "succeeded" else "来源 dry-run command 未成功。",
                next_action="等待 dry-run succeeded 或重新生成 dry-run。",
                evidence_summary=source_command.status if source_command else None,
            ),
            make_protected_registration_check(
                check_id="source_dry_run_is_haproxy_tcp",
                label="来源是 HAProxy TCP",
                passed=source_payload.get("forwarding_method") == FORWARDING_METHOD_HAPROXY_TCP,
                message="来源 forwarding_method 为 haproxy_tcp。" if source_payload.get("forwarding_method") == FORWARDING_METHOD_HAPROXY_TCP else "来源 forwarding_method 不是 haproxy_tcp。",
                next_action="选择 HAProxy TCP dry-run command。",
                evidence_summary=str(source_payload.get("forwarding_method") or "missing"),
            ),
            make_protected_registration_check(
                check_id="source_dry_run_is_dry_run",
                label="来源是 dry-run",
                passed=source_payload.get("dry_run") is True,
                message="来源 command 标记为 dry_run。" if source_payload.get("dry_run") is True else "来源 command 未标记为 dry_run。",
                next_action="选择 dry_run=true 的 command。",
                evidence_summary=str(source_payload.get("dry_run")),
            ),
            make_protected_registration_check(
                check_id="source_dry_run_is_not_real_execution",
                label="来源不是真实执行",
                passed=source_payload.get("real_execution") is False and source_payload.get("approved_real_execution") is not True,
                message="来源 command 未执行真实创建。" if source_payload.get("real_execution") is False and source_payload.get("approved_real_execution") is not True else "来源 command 是 real execution 或已审批真实执行。",
                next_action="选择 real_execution=false 的 dry-run command。",
                evidence_summary=f"real_execution={source_payload.get('real_execution')}",
            ),
            make_protected_registration_check(
                check_id="source_route_name_matches",
                label="route_name 匹配",
                passed=bool(command_route_name and command_route_name == protected_registration_text(source.route_name)),
                message="route_name 与来源 payload 一致。" if command_route_name and command_route_name == protected_registration_text(source.route_name) else "route_name 与来源 payload 不一致。",
                next_action="使用 dry-run candidate 中的 route_name。",
                evidence_summary=f"request={source.route_name or '-'} / source={command_route_name or '-'}",
            ),
            make_protected_registration_check(
                check_id="source_planned_listen_port_matches",
                label="监听端口匹配",
                passed=bool(command_planned_listen_port and command_planned_listen_port == source.planned_listen_port),
                message="planned_listen_port 与来源 payload 一致。" if command_planned_listen_port and command_planned_listen_port == source.planned_listen_port else "planned_listen_port 与来源 payload 不一致。",
                next_action="使用 dry-run candidate 中的 planned_listen_port。",
                evidence_summary=f"request={source.planned_listen_port or '-'} / source={command_planned_listen_port or '-'}",
            ),
            make_protected_registration_check(
                check_id="source_landing_host_matches",
                label="落地 host 匹配",
                passed=bool(command_landing_host and command_landing_host == protected_registration_text(source.landing_target_host)),
                message="landing_target_host 与来源 payload 一致。" if command_landing_host and command_landing_host == protected_registration_text(source.landing_target_host) else "landing_target_host 与来源 payload 不一致。",
                next_action="使用 dry-run candidate 中的 landing_target_host。",
                evidence_summary=f"request={source.landing_target_host or '-'} / source={command_landing_host or '-'}",
            ),
            make_protected_registration_check(
                check_id="source_landing_port_matches",
                label="落地 port 匹配",
                passed=bool(command_landing_port and command_landing_port == source.landing_target_port),
                message="landing_target_port 与来源 payload 一致。" if command_landing_port and command_landing_port == source.landing_target_port else "landing_target_port 与来源 payload 不一致。",
                next_action="使用 dry-run candidate 中的 landing_target_port。",
                evidence_summary=f"request={source.landing_target_port or '-'} / source={command_landing_port or '-'}",
            ),
            make_protected_registration_check(
                check_id="candidate_already_integrity_ready",
                label="candidate 已完整",
                passed=True,
                severity="warning" if source.candidate_integrity_ready else "info",
                message=(
                    "当前 candidate 已经 integrity_ready，通常不需要登记新资源；本 dry-run 仍保持只读。"
                    if source.candidate_integrity_ready
                    else "candidate integrity 未 ready 也允许进行登记 dry-run。"
                ),
                next_action="如无需补资源，停止在当前阶段；如确需登记，进入下一阶段审批。" if source.candidate_integrity_ready else "继续 dry-run 检查。",
                evidence_summary=str(source.candidate_integrity_ready),
            ),
        ],
    )
    duplicate_name = protected_registration_active_transit_resource_duplicates(db, field_name="name", value=transit_name)
    duplicate_entry_host = protected_registration_active_transit_resource_duplicates(
        db,
        field_name="entry_host",
        value=transit_entry_host,
    )
    checks.extend(
        [
            make_protected_registration_check(
                check_id="transit_resource_name_present",
                label="中转资源名称已填写",
                passed=bool(transit_name),
                message="中转资源名称已填写。" if transit_name else "中转资源名称为空。",
                next_action="填写中转资源名称。",
            ),
            make_protected_registration_check(
                check_id="transit_entry_host_present",
                label="中转入口 host 已填写",
                passed=bool(transit_entry_host),
                message="中转入口 host 已填写。" if transit_entry_host else "中转入口 host 为空。",
                next_action="填写中转入口 host。",
            ),
            make_protected_registration_check(
                check_id="transit_entry_port_valid",
                label="中转入口端口有效",
                passed=protected_registration_port_valid(transit.entry_port),
                message="中转入口端口有效。" if protected_registration_port_valid(transit.entry_port) else "中转入口端口无效。",
                next_action="填写 1-65535 的中转入口端口。",
                evidence_summary=str(transit.entry_port),
            ),
            make_protected_registration_check(
                check_id="transit_entry_region_present",
                label="入口地区已填写",
                passed=bool(protected_registration_text(transit.entry_region)),
                message="入口地区已填写。" if protected_registration_text(transit.entry_region) else "入口地区为空。",
                next_action="填写入口地区。",
            ),
            make_protected_registration_check(
                check_id="transit_exit_region_present",
                label="出口地区已填写",
                passed=bool(protected_registration_text(transit.exit_region)),
                message="出口地区已填写。" if protected_registration_text(transit.exit_region) else "出口地区为空。",
                next_action="填写出口地区。",
            ),
            make_protected_registration_check(
                check_id="transit_resource_type_is_server",
                label="中转资源类型为 server",
                passed=transit.resource_type == "server",
                message="中转资源类型为 server。" if transit.resource_type == "server" else "中转资源类型不是 server。",
                next_action="将 resource_type 设置为 server。",
                evidence_summary=transit.resource_type,
            ),
            make_protected_registration_check(
                check_id="transit_expected_status_supported",
                label="中转期望状态受支持",
                passed=transit.expected_status in {"active", "worker_online"},
                message="中转期望状态受支持。" if transit.expected_status in {"active", "worker_online"} else "中转期望状态不受支持。",
                next_action="将 expected_status 设置为 active 或 worker_online。",
                evidence_summary=transit.expected_status,
            ),
            make_protected_registration_check(
                check_id="transit_worker_role_is_transit",
                label="Worker role 为 transit",
                passed=transit.worker_role == "transit",
                message="Worker role 为 transit。" if transit.worker_role == "transit" else "Worker role 不是 transit。",
                next_action="将 worker_role 设置为 transit。",
                evidence_summary=transit.worker_role,
            ),
            make_protected_registration_check(
                check_id="transit_worker_binding_required",
                label="需要 Worker 绑定",
                passed=transit.worker_binding_required,
                message="已要求绑定 transit Worker。" if transit.worker_binding_required else "未要求绑定 transit Worker。",
                next_action="确认后续登记必须绑定在线 transit Worker。",
            ),
            make_protected_registration_check(
                check_id="transit_no_active_duplicate_by_name",
                label="无同名 active 中转资源",
                passed=not duplicate_name,
                message="未发现同名 active / worker_online 中转资源。" if not duplicate_name else "发现同名 active / worker_online 中转资源。",
                next_action="复用现有资源或修改拟登记资源名称。",
                evidence_summary=", ".join(resource.id for resource in duplicate_name) if duplicate_name else None,
            ),
            make_protected_registration_check(
                check_id="transit_no_active_duplicate_by_entry_host",
                label="无同入口 host 中转资源",
                passed=not duplicate_entry_host,
                message="未发现同入口 host 的 active / worker_online 中转资源。" if not duplicate_entry_host else "发现同入口 host 的 active / worker_online 中转资源。",
                next_action="复用现有资源或人工确认入口 host 是否重复。",
                evidence_summary=", ".join(resource.id for resource in duplicate_entry_host) if duplicate_entry_host else None,
            ),
        ],
    )
    duplicate_nodes = protected_registration_active_landing_node_duplicates(
        db,
        vps_ip=landing_vps_ip,
        xray_port=landing.xray_port,
    )
    landing_host_matches_source = bool(landing_vps_ip and landing_vps_ip == protected_registration_text(source.landing_target_host))
    landing_port_matches_source = bool(landing.xray_port and landing.xray_port == source.landing_target_port)
    checks.extend(
        [
            make_protected_registration_check(
                check_id="landing_node_name_present",
                label="落地节点名称已填写",
                passed=bool(protected_registration_text(landing.node_name)),
                message="落地节点名称已填写。" if protected_registration_text(landing.node_name) else "落地节点名称为空。",
                next_action="填写落地节点名称。",
            ),
            make_protected_registration_check(
                check_id="landing_vps_ip_present",
                label="落地 VPS IP 已填写",
                passed=bool(landing_vps_ip),
                message="落地 VPS IP 已填写。" if landing_vps_ip else "落地 VPS IP 为空。",
                next_action="填写落地 VPS IP。",
            ),
            make_protected_registration_check(
                check_id="landing_xray_port_valid",
                label="落地 Xray 端口有效",
                passed=protected_registration_port_valid(landing.xray_port),
                message="落地 Xray 端口有效。" if protected_registration_port_valid(landing.xray_port) else "落地 Xray 端口无效。",
                next_action="填写 1-65535 的落地 Xray 端口。",
                evidence_summary=str(landing.xray_port),
            ),
            make_protected_registration_check(
                check_id="landing_expected_status_is_active",
                label="落地期望状态 active",
                passed=landing.expected_status == "active",
                message="落地期望状态为 active。" if landing.expected_status == "active" else "落地期望状态不是 active。",
                next_action="将落地 expected_status 设置为 active。",
                evidence_summary=landing.expected_status,
            ),
            make_protected_registration_check(
                check_id="landing_share_link_handling_safe",
                label="客户端配置处理策略安全",
                passed=landing.share_link_handling == "do_not_export_or_modify_full_share_link",
                message="客户端配置处理策略为不导出、不修改。" if landing.share_link_handling == "do_not_export_or_modify_full_share_link" else "客户端配置处理策略不安全。",
                next_action="将 share_link_handling 设置为 do_not_export_or_modify_full_share_link。",
                evidence_summary=landing.share_link_handling,
            ),
            make_protected_registration_check(
                check_id="landing_no_active_duplicate_by_vps_ip_port",
                label="无同 IP + 端口 active 节点",
                passed=not duplicate_nodes,
                message="未发现同 VPS IP + 端口的 active 节点。" if not duplicate_nodes else "发现同 VPS IP + 端口的 active 节点。",
                next_action="复用现有节点或人工确认是否重复登记。",
                evidence_summary=", ".join(node.id for node in duplicate_nodes) if duplicate_nodes else None,
            ),
            make_protected_registration_check(
                check_id="landing_host_matches_source_or_manual_override_warning",
                label="落地 host 与来源一致",
                passed=landing_host_matches_source,
                severity="warning" if not landing_host_matches_source else "info",
                message="落地 VPS IP 与来源 candidate 一致。" if landing_host_matches_source else "落地 VPS IP 与来源 candidate 不一致，允许人工 override 但需复核。",
                next_action="复核落地 VPS IP 是否为当前正式节点。" if not landing_host_matches_source else "继续检查。",
                evidence_summary=f"draft={landing_vps_ip or '-'} / source={source.landing_target_host or '-'}",
            ),
            make_protected_registration_check(
                check_id="landing_port_matches_source_or_manual_override_warning",
                label="落地端口与来源一致",
                passed=landing_port_matches_source,
                severity="warning" if not landing_port_matches_source else "info",
                message="落地 Xray 端口与来源 candidate 一致。" if landing_port_matches_source else "落地 Xray 端口与来源 candidate 不一致，允许人工 override 但需复核。",
                next_action="复核落地 Xray 端口是否为当前正式节点。" if not landing_port_matches_source else "继续检查。",
                evidence_summary=f"draft={landing.xray_port or '-'} / source={source.landing_target_port or '-'}",
            ),
        ],
    )
    original_payload_has_sensitive_value = protected_registration_contains_sensitive_value(payload.model_dump())
    checks.append(
        make_protected_registration_check(
            check_id="response_sensitive_content_absent",
            label="响应不包含敏感值",
            passed=not original_payload_has_sensitive_value,
            message="响应预览未包含完整客户端链接或凭证类敏感值。" if not original_payload_has_sensitive_value else "响应预览包含疑似敏感值，已脱敏但不能进入下一阶段。",
            next_action="移除 payload 中的完整客户端链接、密钥、命令或凭证后重新 dry-run。",
            evidence_summary="redacted" if original_payload_has_sensitive_value else "clean",
        ),
    )
    danger_failures = [check for check in checks if check["severity"] == "danger" and not check["passed"]]
    expected_suffix = str(source.planned_listen_port) if protected_registration_port_valid(source.planned_listen_port) else "MANUAL"
    return {
        "dry_run": True,
        "ready_for_next_stage": not danger_failures,
        "stage": PROTECTED_RESOURCE_REGISTRATION_DRY_RUN_STAGE,
        "recommended_next_stage": PROTECTED_RESOURCE_REGISTRATION_APPROVAL_STAGE,
        "checks": checks,
        "blocked_reasons": [check["message"] for check in danger_failures],
        "normalized_preview": normalized_preview,
        "expected_approval_text": f"CONFIRM_PROTECTED_RESOURCE_REGISTRATION_DRY_RUN_{expected_suffix}",
    }


def build_protected_resource_registration_approval_dry_run(
    payload: ProtectedResourceRegistrationApprovalDryRunRequest,
) -> dict:
    source = payload.source_registration_dry_run
    confirmations = payload.confirmations
    confirmation_values = confirmations.model_dump()
    expected_approval_text = protected_registration_text(source.expected_approval_text)
    approval_text = protected_registration_text(payload.approval_text)
    approval_text_matches = bool(expected_approval_text and approval_text == expected_approval_text)
    all_confirmations = all(bool(value) for value in confirmation_values.values())
    payload_has_sensitive_value = protected_registration_contains_sensitive_value(payload.model_dump())
    normalized_preview = source.normalized_preview if isinstance(source.normalized_preview, dict) else {}
    registration_source_preview = protected_registration_safe_source_preview(normalized_preview)
    normalized_approval_preview = {
        "stage": PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_STAGE,
        "mode": PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_MODE,
        "source_registration_dry_run": {
            "dry_run": source.dry_run,
            "ready_for_next_stage": source.ready_for_next_stage,
            "expected_approval_text_present": bool(expected_approval_text),
            "normalized_preview_present": bool(normalized_preview),
            "normalized_preview_key_count": len(normalized_preview),
        },
        "registration_source_preview": registration_source_preview,
        "registration_source_ready": protected_registration_preview_complete(registration_source_preview),
        "approval_text_present": bool(approval_text),
        "approval_text_matches_expected": approval_text_matches,
        "confirmations": confirmation_values,
    }
    safety_boundary = {
        "no_real_resource_creation": confirmations.no_real_resource_creation,
        "no_worker_command_creation": confirmations.no_worker_command_creation,
        "no_transit_route_creation": confirmations.no_transit_route_creation,
        "no_haproxy_route_creation": confirmations.no_haproxy_route_creation,
        "no_ssh_or_remote_execution": confirmations.no_ssh_or_remote_execution,
        "no_firewall_change": confirmations.no_firewall_change,
        "no_cutover": confirmations.no_cutover,
        "ordinary_product_ui_unchanged": confirmations.ordinary_product_ui_unchanged,
    }
    checks: list[dict] = [
        make_protected_registration_check(
            check_id="stage_is_expected",
            label="Stage 正确",
            passed=payload.stage == PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_STAGE,
            message="Approval payload stage 为 3.4.28。" if payload.stage == PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_STAGE else "Approval payload stage 不匹配。",
            next_action="使用 Stage 3.4.28 生成的 approval payload。" if payload.stage != PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_STAGE else "继续检查。",
            evidence_summary=payload.stage,
        ),
        make_protected_registration_check(
            check_id="mode_is_approval_dry_run",
            label="Mode 为 approval_dry_run",
            passed=payload.mode == PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_MODE,
            message="Approval payload 保持 approval_dry_run。" if payload.mode == PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_MODE else "Approval payload mode 不匹配。",
            next_action="将 mode 设置为 approval_dry_run。",
            evidence_summary=payload.mode,
        ),
        make_protected_registration_check(
            check_id="source_registration_dry_run_is_dry_run",
            label="来源 registration dry-run",
            passed=source.dry_run is True,
            message="来源结果标记 dry_run=true。" if source.dry_run is True else "来源结果不是 dry_run。",
            next_action="粘贴或读取 Stage 3.4.27 registration dry-run 结果。",
            evidence_summary=str(source.dry_run),
        ),
        make_protected_registration_check(
            check_id="source_registration_dry_run_ready",
            label="来源 ready_for_next_stage",
            passed=source.ready_for_next_stage is True,
            message="来源 registration dry-run 已 ready。" if source.ready_for_next_stage is True else "来源 registration dry-run 未 ready。",
            next_action="先让 Stage 3.4.27 registration dry-run 通过。",
            evidence_summary=str(source.ready_for_next_stage),
        ),
        make_protected_registration_check(
            check_id="expected_approval_text_present",
            label="审批文本存在",
            passed=bool(expected_approval_text),
            message="来源提供 expected_approval_text。" if expected_approval_text else "来源缺少 expected_approval_text。",
            next_action="重新复制 Stage 3.4.27 registration dry-run 结果。",
        ),
        make_protected_registration_check(
            check_id="approval_text_matches_expected",
            label="审批文本完全匹配",
            passed=approval_text_matches and confirmations.approval_text_matches_expected,
            message="人工输入的 approval text 与 expected 完全一致。" if approval_text_matches and confirmations.approval_text_matches_expected else "人工输入的 approval text 未完全匹配。",
            next_action="逐字符复制 expected_approval_text 后重新运行 approval dry-run。",
            evidence_summary="matched" if approval_text_matches else "mismatch",
        ),
        make_protected_registration_check(
            check_id="all_approval_confirmations_present",
            label="审批确认完整",
            passed=all_confirmations,
            message="所有 approval 安全确认项已勾选。" if all_confirmations else "仍有 approval 安全确认项未勾选。",
            next_action="补齐所有安全确认项。",
            evidence_summary=f"{sum(1 for value in confirmation_values.values() if value)}/{len(confirmation_values)}",
        ),
        make_protected_registration_check(
            check_id="registration_dry_run_passed_confirmed",
            label="确认 registration dry-run 已通过",
            passed=confirmations.registration_dry_run_passed,
            message="已确认 Stage 3.4.27 dry-run 通过。" if confirmations.registration_dry_run_passed else "尚未确认 Stage 3.4.27 dry-run 通过。",
            next_action="勾选 registration dry-run passed 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_real_resource_creation_confirmed",
            label="确认不创建真实资源",
            passed=confirmations.no_real_resource_creation,
            message="已确认本阶段不创建真实资源。" if confirmations.no_real_resource_creation else "尚未确认不创建真实资源。",
            next_action="勾选 no real resource creation 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_worker_command_creation_confirmed",
            label="确认不创建 WorkerCommand",
            passed=confirmations.no_worker_command_creation,
            message="已确认本阶段不创建 WorkerCommand。" if confirmations.no_worker_command_creation else "尚未确认不创建 WorkerCommand。",
            next_action="勾选 no WorkerCommand creation 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_transit_route_creation_confirmed",
            label="确认不创建 TransitRoute",
            passed=confirmations.no_transit_route_creation,
            message="已确认本阶段不创建 TransitRoute。" if confirmations.no_transit_route_creation else "尚未确认不创建 TransitRoute。",
            next_action="勾选 no TransitRoute creation 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_haproxy_route_creation_confirmed",
            label="确认不创建 HAProxy route",
            passed=confirmations.no_haproxy_route_creation,
            message="已确认本阶段不创建 HAProxy route。" if confirmations.no_haproxy_route_creation else "尚未确认不创建 HAProxy route。",
            next_action="勾选 no HAProxy route creation 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_ssh_or_remote_execution_confirmed",
            label="确认不 SSH / 不远程执行",
            passed=confirmations.no_ssh_or_remote_execution,
            message="已确认本阶段不 SSH、不远程执行。" if confirmations.no_ssh_or_remote_execution else "尚未确认不 SSH、不远程执行。",
            next_action="勾选 no SSH or remote execution 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_firewall_change_confirmed",
            label="确认不改防火墙",
            passed=confirmations.no_firewall_change,
            message="已确认本阶段不修改防火墙。" if confirmations.no_firewall_change else "尚未确认不修改防火墙。",
            next_action="勾选 no firewall change 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_cutover_confirmed",
            label="确认不 cutover",
            passed=confirmations.no_cutover,
            message="已确认本阶段不 cutover。" if confirmations.no_cutover else "尚未确认不 cutover。",
            next_action="勾选 no cutover 确认项。",
        ),
        make_protected_registration_check(
            check_id="ordinary_product_ui_unchanged_confirmed",
            label="确认普通产品 UI 不变",
            passed=confirmations.ordinary_product_ui_unchanged,
            message="已确认普通产品 UI 不改。" if confirmations.ordinary_product_ui_unchanged else "尚未确认普通产品 UI 不改。",
            next_action="勾选 ordinary product UI unchanged 确认项。",
        ),
        make_protected_registration_check(
            check_id="sensitive_fields_redacted_confirmed",
            label="确认敏感字段已脱敏",
            passed=confirmations.sensitive_fields_redacted,
            message="已确认输入与响应不包含完整敏感值。" if confirmations.sensitive_fields_redacted else "尚未确认敏感字段脱敏。",
            next_action="确认没有完整客户端配置、凭证、命令或密钥后勾选。",
        ),
        make_protected_registration_check(
            check_id="response_sensitive_content_absent",
            label="响应不包含敏感值",
            passed=not payload_has_sensitive_value,
            message="Approval dry-run 响应未回显完整客户端链接或凭证类敏感值。" if not payload_has_sensitive_value else "Approval payload 包含疑似敏感值，已阻止进入下一阶段。",
            next_action="移除 payload 中的完整客户端链接、密钥、命令或凭证后重新 dry-run。",
            evidence_summary="clean" if not payload_has_sensitive_value else "redacted",
        ),
    ]
    danger_failures = [check for check in checks if check["severity"] == "danger" and not check["passed"]]
    approved = not danger_failures
    return {
        "dry_run": True,
        "stage": PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_STAGE,
        "mode": PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_MODE,
        "approved_for_next_stage": approved,
        "ready_for_command_create_next_stage": approved,
        "checks": checks,
        "blocked_reasons": [check["message"] for check in danger_failures],
        "normalized_approval_preview": normalized_approval_preview,
        "safety_boundary": safety_boundary,
        "recommended_next_stage": PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_NEXT_STAGE,
    }


def protected_registration_command_create_idempotency_key(
    payload: ProtectedResourceRegistrationCommandCreateRequest,
) -> str:
    source = payload.source_approval_dry_run
    key_material = {
        "stage": payload.stage,
        "mode": payload.mode,
        "source_stage": source.stage,
        "source_mode": source.mode,
        "approved_for_next_stage": source.approved_for_next_stage,
        "ready_for_command_create_next_stage": source.ready_for_command_create_next_stage,
        "normalized_approval_preview": source.normalized_approval_preview,
        "safety_boundary": source.safety_boundary,
    }
    encoded = json.dumps(key_material, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def protected_registration_existing_command_by_idempotency_key(db: Session, idempotency_key: str) -> Task | None:
    if not idempotency_key:
        return None
    tasks = db.scalars(
        select(Task)
        .where(Task.task_type == PROTECTED_RESOURCE_REGISTRATION_COMMAND_TASK_TYPE)
        .order_by(Task.created_at.desc())
        .limit(50)
    ).all()
    for task in tasks:
        result_data = task.result_data if isinstance(task.result_data, dict) else {}
        if result_data.get("idempotency_key") == idempotency_key:
            return task
    return None


def build_protected_registration_command_preview(
    payload: ProtectedResourceRegistrationCommandCreateRequest,
    *,
    idempotency_key: str,
) -> dict:
    source = payload.source_approval_dry_run
    approval_preview = source.normalized_approval_preview if isinstance(source.normalized_approval_preview, dict) else {}
    registration_source_preview = protected_registration_safe_source_preview(
        protected_registration_preview_record(approval_preview.get("registration_source_preview"))
    )
    safety_boundary = source.safety_boundary if isinstance(source.safety_boundary, dict) else {}
    return {
        "stage": PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_STAGE,
        "mode": PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_MODE,
        "command_type": PROTECTED_RESOURCE_REGISTRATION_COMMAND_TASK_TYPE,
        "command_status": PROTECTED_RESOURCE_REGISTRATION_COMMAND_STATUS,
        "idempotency_key": idempotency_key,
        "source_approval_dry_run": {
            "dry_run": source.dry_run,
            "stage": source.stage,
            "mode": source.mode,
            "approved_for_next_stage": source.approved_for_next_stage,
            "ready_for_command_create_next_stage": source.ready_for_command_create_next_stage,
            "normalized_approval_preview_present": bool(approval_preview),
            "normalized_approval_preview_key_count": len(approval_preview),
            "registration_source_preview_present": bool(registration_source_preview),
            "registration_source_ready": protected_registration_preview_complete(registration_source_preview),
            "safety_boundary_key_count": len(safety_boundary),
        },
        "safety_boundary": {
            "local_pending_command_only": payload.confirmations.create_local_pending_command_only,
            "no_real_resource_creation": payload.confirmations.no_real_resource_creation,
            "no_transit_resource_creation": payload.confirmations.no_transit_resource_creation,
            "no_landing_node_creation": payload.confirmations.no_landing_node_creation,
            "no_worker_remote_execution": payload.confirmations.no_worker_remote_execution,
            "no_transit_route_creation": payload.confirmations.no_transit_route_creation,
            "no_haproxy_route_creation": payload.confirmations.no_haproxy_route_creation,
            "no_listening_port_change": payload.confirmations.no_listening_port_change,
            "no_ssh_or_remote_execution": payload.confirmations.no_ssh_or_remote_execution,
            "no_firewall_change": payload.confirmations.no_firewall_change,
            "no_cutover": payload.confirmations.no_cutover,
            "ordinary_product_ui_unchanged": payload.confirmations.ordinary_product_ui_unchanged,
        },
        "recommended_next_stage": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_NEXT_STAGE,
    }


def build_protected_resource_registration_command_create(
    db: Session,
    payload: ProtectedResourceRegistrationCommandCreateRequest,
) -> dict:
    source = payload.source_approval_dry_run
    confirmations = payload.confirmations
    confirmation_values = confirmations.model_dump()
    idempotency_key = protected_registration_command_create_idempotency_key(payload)
    payload_has_sensitive_value = protected_registration_contains_sensitive_value(payload.model_dump())
    normalized_command_preview = build_protected_registration_command_preview(
        payload,
        idempotency_key=idempotency_key,
    )
    registration_source_preview = protected_registration_safe_source_preview(
        protected_registration_preview_record(source.normalized_approval_preview.get("registration_source_preview"))
    )
    checks: list[dict] = [
        make_protected_registration_check(
            check_id="stage_is_expected",
            label="Stage 正确",
            passed=payload.stage == PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_STAGE,
            message="Command-create payload stage 为 3.4.29。" if payload.stage == PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_STAGE else "Command-create payload stage 不匹配。",
            next_action="使用 Stage 3.4.29 生成的 command-create payload。" if payload.stage != PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_STAGE else "继续检查。",
            evidence_summary=payload.stage,
        ),
        make_protected_registration_check(
            check_id="mode_is_command_create",
            label="Mode 为 command_create",
            passed=payload.mode == PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_MODE,
            message="Command-create payload mode 正确。" if payload.mode == PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_MODE else "Command-create payload mode 不匹配。",
            next_action="将 mode 设置为 command_create。",
            evidence_summary=payload.mode,
        ),
        make_protected_registration_check(
            check_id="source_approval_dry_run_is_dry_run",
            label="来源 approval dry-run",
            passed=source.dry_run is True,
            message="来源 approval 结果标记 dry_run=true。" if source.dry_run is True else "来源 approval 结果不是 dry-run。",
            next_action="粘贴或读取 Stage 3.4.28 approval dry-run 结果。",
            evidence_summary=str(source.dry_run),
        ),
        make_protected_registration_check(
            check_id="source_approval_stage_is_expected",
            label="来源 stage 为 3.4.28",
            passed=source.stage == PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_STAGE,
            message="来源 approval dry-run stage 正确。" if source.stage == PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_STAGE else "来源 approval dry-run stage 不匹配。",
            next_action="使用 Stage 3.4.28 approval dry-run 结果。",
            evidence_summary=source.stage,
        ),
        make_protected_registration_check(
            check_id="source_approval_mode_is_expected",
            label="来源 mode 为 approval_dry_run",
            passed=source.mode == PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_MODE,
            message="来源 approval dry-run mode 正确。" if source.mode == PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_MODE else "来源 approval dry-run mode 不匹配。",
            next_action="使用 approval_dry_run 结果。",
            evidence_summary=source.mode,
        ),
        make_protected_registration_check(
            check_id="source_approval_approved_for_next_stage",
            label="来源已批准下一阶段",
            passed=source.approved_for_next_stage is True,
            message="来源 approval dry-run 已 approved_for_next_stage。" if source.approved_for_next_stage is True else "来源 approval dry-run 未 approved_for_next_stage。",
            next_action="先让 Stage 3.4.28 approval dry-run 通过。",
            evidence_summary=str(source.approved_for_next_stage),
        ),
        make_protected_registration_check(
            check_id="source_ready_for_command_create_next_stage",
            label="来源 ready_for_command_create_next_stage",
            passed=source.ready_for_command_create_next_stage is True,
            message="来源已允许 command-create 阶段。" if source.ready_for_command_create_next_stage is True else "来源未允许 command-create 阶段。",
            next_action="先让 Stage 3.4.28 approval dry-run 通过。",
            evidence_summary=str(source.ready_for_command_create_next_stage),
        ),
        make_protected_registration_check(
            check_id="all_command_create_confirmations_present",
            label="命令创建确认完整",
            passed=all(bool(value) for value in confirmation_values.values()),
            message="所有 command-create 安全确认项已勾选。" if all(bool(value) for value in confirmation_values.values()) else "仍有 command-create 安全确认项未勾选。",
            next_action="补齐所有安全确认项。",
            evidence_summary=f"{sum(1 for value in confirmation_values.values() if value)}/{len(confirmation_values)}",
        ),
        make_protected_registration_check(
            check_id="create_local_pending_command_only_confirmed",
            label="确认只创建本地 pending command",
            passed=confirmations.create_local_pending_command_only,
            message="已确认只创建本地 pending command 记录。" if confirmations.create_local_pending_command_only else "尚未确认只创建本地 pending command 记录。",
            next_action="勾选 create local pending command only 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_real_resource_creation_confirmed",
            label="确认不创建真实资源",
            passed=confirmations.no_real_resource_creation,
            message="已确认不创建真实资源。" if confirmations.no_real_resource_creation else "尚未确认不创建真实资源。",
            next_action="勾选 no real resource creation 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_transit_resource_creation_confirmed",
            label="确认不创建 transit_resource",
            passed=confirmations.no_transit_resource_creation,
            message="已确认不创建 transit_resource。" if confirmations.no_transit_resource_creation else "尚未确认不创建 transit_resource。",
            next_action="勾选 no transit_resource creation 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_landing_node_creation_confirmed",
            label="确认不创建 landing_node",
            passed=confirmations.no_landing_node_creation,
            message="已确认不创建 landing_node。" if confirmations.no_landing_node_creation else "尚未确认不创建 landing_node。",
            next_action="勾选 no landing_node creation 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_worker_remote_execution_confirmed",
            label="确认不触发 Worker 远程执行",
            passed=confirmations.no_worker_remote_execution,
            message="已确认不触发 Worker 远程执行。" if confirmations.no_worker_remote_execution else "尚未确认不触发 Worker 远程执行。",
            next_action="勾选 no worker remote execution 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_transit_route_creation_confirmed",
            label="确认不创建 TransitRoute",
            passed=confirmations.no_transit_route_creation,
            message="已确认不创建 TransitRoute。" if confirmations.no_transit_route_creation else "尚未确认不创建 TransitRoute。",
            next_action="勾选 no TransitRoute creation 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_haproxy_route_creation_confirmed",
            label="确认不创建 HAProxy route",
            passed=confirmations.no_haproxy_route_creation,
            message="已确认不创建 HAProxy route。" if confirmations.no_haproxy_route_creation else "尚未确认不创建 HAProxy route。",
            next_action="勾选 no HAProxy route creation 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_listening_port_change_confirmed",
            label="确认不新增/变更监听端口",
            passed=confirmations.no_listening_port_change,
            message="已确认不新增或变更监听端口。" if confirmations.no_listening_port_change else "尚未确认不新增或变更监听端口。",
            next_action="勾选 no listening port change 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_ssh_or_remote_execution_confirmed",
            label="确认不 SSH / 不远程执行",
            passed=confirmations.no_ssh_or_remote_execution,
            message="已确认不 SSH、不远程执行。" if confirmations.no_ssh_or_remote_execution else "尚未确认不 SSH、不远程执行。",
            next_action="勾选 no SSH or remote execution 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_firewall_change_confirmed",
            label="确认不改防火墙",
            passed=confirmations.no_firewall_change,
            message="已确认不修改防火墙。" if confirmations.no_firewall_change else "尚未确认不修改防火墙。",
            next_action="勾选 no firewall change 确认项。",
        ),
        make_protected_registration_check(
            check_id="no_cutover_confirmed",
            label="确认不 cutover",
            passed=confirmations.no_cutover,
            message="已确认不 cutover。" if confirmations.no_cutover else "尚未确认不 cutover。",
            next_action="勾选 no cutover 确认项。",
        ),
        make_protected_registration_check(
            check_id="ordinary_product_ui_unchanged_confirmed",
            label="确认普通产品 UI 不变",
            passed=confirmations.ordinary_product_ui_unchanged,
            message="已确认普通产品 UI 不改。" if confirmations.ordinary_product_ui_unchanged else "尚未确认普通产品 UI 不改。",
            next_action="勾选 ordinary product UI unchanged 确认项。",
        ),
        make_protected_registration_check(
            check_id="sensitive_fields_redacted_confirmed",
            label="确认敏感字段已脱敏",
            passed=confirmations.sensitive_fields_redacted,
            message="已确认输入与响应不包含完整敏感值。" if confirmations.sensitive_fields_redacted else "尚未确认敏感字段脱敏。",
            next_action="确认没有完整客户端配置、凭证、命令或密钥后勾选。",
        ),
        make_protected_registration_check(
            check_id="response_sensitive_content_absent",
            label="响应不包含敏感值",
            passed=not payload_has_sensitive_value,
            message="Command-create 响应未回显完整客户端链接或凭证类敏感值。" if not payload_has_sensitive_value else "Command-create payload 包含疑似敏感值，已阻止创建 pending command。",
            next_action="移除 payload 中的完整客户端链接、密钥、命令或凭证后重新提交。",
            evidence_summary="clean" if not payload_has_sensitive_value else "redacted",
        ),
    ]
    danger_failures = [check for check in checks if check["severity"] == "danger" and not check["passed"]]
    if danger_failures:
        return {
            "created": False,
            "stage": PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_STAGE,
            "mode": PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_MODE,
            "dry_run": False,
            "command_id": None,
            "task_id": None,
            "registration_command_id": None,
            "command_status": None,
            "ready_for_execution_next_stage": False,
            "idempotency_key": idempotency_key,
            "idempotent_reuse": False,
            "checks": checks,
            "blocked_reasons": [check["message"] for check in danger_failures],
            "normalized_command_preview": normalized_command_preview,
            "safety_boundary": normalized_command_preview["safety_boundary"],
            "recommended_next_stage": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_NEXT_STAGE,
        }

    existing_command = protected_registration_existing_command_by_idempotency_key(db, idempotency_key)
    if existing_command:
        return {
            "created": True,
            "stage": PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_STAGE,
            "mode": PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_MODE,
            "dry_run": False,
            "command_id": existing_command.id,
            "task_id": existing_command.id,
            "registration_command_id": existing_command.id,
            "command_status": existing_command.status,
            "ready_for_execution_next_stage": existing_command.status == PROTECTED_RESOURCE_REGISTRATION_COMMAND_STATUS,
            "idempotency_key": idempotency_key,
            "idempotent_reuse": True,
            "checks": checks,
            "blocked_reasons": [],
            "normalized_command_preview": normalized_command_preview,
            "safety_boundary": normalized_command_preview["safety_boundary"],
            "recommended_next_stage": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_NEXT_STAGE,
        }

    command_id = str(uuid.uuid4())
    command_task = Task(
        id=command_id,
        task_type=PROTECTED_RESOURCE_REGISTRATION_COMMAND_TASK_TYPE,
        status=PROTECTED_RESOURCE_REGISTRATION_COMMAND_STATUS,
        current_step="awaiting_stage_3_4_30_execution_verify",
        progress=0,
        result_data={
            "stage": PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_STAGE,
            "mode": PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_MODE,
            "command_status": PROTECTED_RESOURCE_REGISTRATION_COMMAND_STATUS,
            "idempotency_key": idempotency_key,
            "normalized_command_preview": normalized_command_preview,
            "registration_source_preview": registration_source_preview,
            "safety_boundary": normalized_command_preview["safety_boundary"],
            "recommended_next_stage": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_NEXT_STAGE,
        },
    )
    db.add(command_task)
    db.commit()
    return {
        "created": True,
        "stage": PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_STAGE,
        "mode": PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_MODE,
        "dry_run": False,
        "command_id": command_task.id,
        "task_id": command_task.id,
        "registration_command_id": command_task.id,
        "command_status": command_task.status,
        "ready_for_execution_next_stage": True,
        "idempotency_key": idempotency_key,
        "idempotent_reuse": False,
        "checks": checks,
        "blocked_reasons": [],
        "normalized_command_preview": normalized_command_preview,
        "safety_boundary": normalized_command_preview["safety_boundary"],
        "recommended_next_stage": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_NEXT_STAGE,
    }


def protected_registration_execution_expected_text(command_id: str) -> str:
    return f"EXECUTE_PROTECTED_RESOURCE_REGISTRATION:{command_id}"


def protected_registration_execution_fingerprint(command_id: str, idempotency_key: str, registration_source: dict) -> str:
    material = {
        "command_id": command_id,
        "idempotency_key": idempotency_key,
        "registration_source": registration_source,
    }
    encoded = json.dumps(material, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def protected_registration_execution_safety_boundary(
    confirmations: ProtectedRegistrationExecutionConfirmations,
) -> dict:
    return {
        "local_db_registration_only": confirmations.execute_local_db_registration_only,
        "no_worker_command_creation": confirmations.no_worker_command_creation,
        "no_transit_route_creation": confirmations.no_transit_route_creation,
        "no_haproxy_route_creation": confirmations.no_haproxy_route_creation,
        "no_haproxy_config_generation": confirmations.no_haproxy_config_generation,
        "no_listening_port_change": confirmations.no_listening_port_change,
        "no_ssh_or_remote_execution": confirmations.no_ssh_or_remote_execution,
        "no_firewall_change": confirmations.no_firewall_change,
        "no_cutover": confirmations.no_cutover,
        "ordinary_product_ui_unchanged": confirmations.ordinary_product_ui_unchanged,
    }


def protected_registration_execution_empty_response(
    *,
    payload: ProtectedResourceRegistrationExecutionVerifyRequest,
    command_status: str | None = None,
    checks: list[dict] | None = None,
    blocked_reasons: list[str] | None = None,
    idempotency_key: str = "",
    idempotent_reuse: bool = False,
    created: dict | None = None,
    verification: dict | None = None,
    normalized_execution_preview: dict | None = None,
) -> dict:
    return {
        "executed": False,
        "stage": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_STAGE,
        "mode": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_MODE,
        "command_id": payload.command_id or None,
        "command_status": command_status,
        "idempotency_key": idempotency_key,
        "idempotent_reuse": idempotent_reuse,
        "created": created
        or {
            "transit_resource_id": None,
            "landing_node_id": None,
        },
        "verification": verification
        or {
            "transit_resource_exists": False,
            "landing_node_exists": False,
            "worker_command_created": False,
            "transit_route_created": False,
            "haproxy_route_created": False,
            "listening_port_changed": False,
            "remote_execution_triggered": False,
            "firewall_changed": False,
            "cutover_done": False,
        },
        "checks": checks or [],
        "blocked_reasons": blocked_reasons or [],
        "normalized_execution_preview": normalized_execution_preview or {},
        "safety_boundary": protected_registration_execution_safety_boundary(payload.confirmations),
        "ready_for_haproxy_dry_run_next_stage": False,
        "recommended_next_stage": PROTECTED_RESOURCE_REGISTRATION_HAPROXY_DRY_RUN_NEXT_STAGE,
    }


def protected_registration_command_execution_data(command: Task) -> dict:
    result_data = command.result_data if isinstance(command.result_data, dict) else {}
    execution = result_data.get("execution")
    return execution if isinstance(execution, dict) else {}


def protected_registration_command_result_data(command: Task | None) -> dict:
    if not command or not isinstance(command.result_data, dict):
        return {}
    return command.result_data


def protected_registration_command_source_approved(result_data: dict) -> bool:
    preview = protected_registration_preview_record(result_data.get("normalized_command_preview"))
    source = protected_registration_preview_record(preview.get("source_approval_dry_run"))
    return (
        source.get("dry_run") is True
        and source.get("stage") == PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_STAGE
        and source.get("mode") == PROTECTED_RESOURCE_REGISTRATION_APPROVAL_DRY_RUN_MODE
        and source.get("approved_for_next_stage") is True
        and source.get("ready_for_command_create_next_stage") is True
    )


def protected_registration_command_registration_source(result_data: dict) -> dict:
    registration_source = protected_registration_preview_record(result_data.get("registration_source_preview"))
    if registration_source:
        return protected_registration_safe_source_preview(registration_source)
    preview = protected_registration_preview_record(result_data.get("normalized_command_preview"))
    source = protected_registration_preview_record(preview.get("registration_source_preview"))
    return protected_registration_safe_source_preview(source)


def protected_registration_select_first(db: Session, statement):
    return db.scalars(statement.limit(20)).all()


def protected_registration_find_transit_resource(
    db: Session,
    *,
    name: str,
    entry_host: str,
    entry_port: int,
) -> tuple[TransitResource | None, str | None]:
    resources = protected_registration_select_first(
        db,
        select(TransitResource)
        .where(TransitResource.deleted_at.is_(None))
        .where(TransitResource.entry_host == entry_host)
        .where(TransitResource.entry_port == entry_port),
    )
    exact = next((resource for resource in resources if resource.name == name), None)
    if exact:
        return exact, None
    if resources:
        return None, "发现相同 entry_host / entry_port 的其它中转资源，不能自动复用。"
    name_matches = protected_registration_select_first(
        db,
        select(TransitResource)
        .where(TransitResource.deleted_at.is_(None))
        .where(TransitResource.name == name),
    )
    if name_matches:
        return None, "发现同名中转资源但入口信息不同，不能自动复用。"
    return None, None


def protected_registration_find_vps_by_ip(db: Session, ip: str) -> VpsServer | None:
    matches = protected_registration_select_first(db, select(VpsServer).where(VpsServer.ip == ip))
    return matches[0] if matches else None


def protected_registration_find_landing_node(
    db: Session,
    *,
    vps_id: str,
    node_name: str,
    xray_port: int,
) -> tuple[Node | None, str | None]:
    nodes = protected_registration_select_first(
        db,
        select(Node)
        .where(Node.vps_id == vps_id)
        .where(Node.deleted_at.is_(None))
        .where(Node.xray_port == xray_port),
    )
    exact = next((node for node in nodes if node.node_name == node_name), None)
    if exact:
        return exact, None
    if nodes:
        return None, "发现相同 VPS / Xray 端口的其它节点，不能自动复用。"
    name_matches = protected_registration_select_first(
        db,
        select(Node)
        .where(Node.vps_id == vps_id)
        .where(Node.deleted_at.is_(None))
        .where(Node.node_name == node_name),
    )
    if name_matches:
        return None, "发现同名落地节点但端口不同，不能自动复用。"
    return None, None


def build_protected_resource_registration_execution_verify(
    db: Session,
    payload: ProtectedResourceRegistrationExecutionVerifyRequest,
) -> dict:
    command = db.get(Task, payload.command_id) if payload.command_id else None
    result_data = protected_registration_command_result_data(command)
    registration_source = protected_registration_command_registration_source(result_data)
    command_execution = protected_registration_command_execution_data(command) if command else {}
    confirmation_values = payload.confirmations.model_dump()
    expected_text = protected_registration_execution_expected_text(payload.command_id)
    text_matches = payload.execution_approval_text == expected_text
    idempotency_key = protected_registration_text(str(result_data.get("idempotency_key") or ""))
    source = protected_registration_preview_record(registration_source.get("source"))
    transit = protected_registration_preview_record(registration_source.get("transit_resource_registration"))
    landing = protected_registration_preview_record(registration_source.get("landing_node_registration"))
    transit_name = protected_registration_record_text(transit, "name")
    transit_entry_host = protected_registration_record_text(transit, "entry_host")
    transit_entry_port = _payload_int(transit, "entry_port")
    transit_status = protected_registration_record_text(transit, "expected_status") or "active"
    landing_name = protected_registration_record_text(landing, "node_name")
    landing_vps_ip = protected_registration_record_text(landing, "vps_ip")
    landing_xray_port = _payload_int(landing, "xray_port")
    landing_status = protected_registration_record_text(landing, "expected_status") or "active"
    registration_complete = protected_registration_preview_complete(registration_source)
    payload_has_sensitive_value = protected_registration_contains_sensitive_value(payload.model_dump())
    command_has_sensitive_value = protected_registration_contains_sensitive_value(registration_source)
    normalized_execution_preview = {
        "stage": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_STAGE,
        "mode": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_MODE,
        "command_id_present": bool(payload.command_id),
        "command_type": command.task_type if command else None,
        "command_status_before": command.status if command else "missing",
        "idempotency_key_present": bool(idempotency_key),
        "source": {
            "dry_run_command_id": protected_registration_record_text(source, "dry_run_command_id"),
            "route_name": protected_registration_record_text(source, "route_name"),
            "planned_listen_port": _payload_int(source, "planned_listen_port"),
            "landing_target_port": _payload_int(source, "landing_target_port"),
        },
        "transit_resource_registration": {
            "name": transit_name,
            "resource_type": protected_registration_record_text(transit, "resource_type"),
            "entry_host": transit_entry_host,
            "entry_port": transit_entry_port,
            "expected_status": transit_status,
        },
        "landing_node_registration": {
            "node_name": landing_name,
            "vps_ip": landing_vps_ip,
            "xray_port": landing_xray_port,
            "expected_status": landing_status,
        },
    }
    checks: list[dict] = [
        make_protected_registration_check(
            check_id="stage_is_expected",
            label="Stage 正确",
            passed=payload.stage == PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_STAGE,
            message="Execution payload stage 为 3.4.30。" if payload.stage == PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_STAGE else "Execution payload stage 不匹配。",
            next_action="使用 Stage 3.4.30 生成的 execution verify payload。" if payload.stage != PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_STAGE else "继续检查。",
            evidence_summary=payload.stage,
        ),
        make_protected_registration_check(
            check_id="mode_is_execution_verify",
            label="Mode 为 execution_verify",
            passed=payload.mode == PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_MODE,
            message="Execution payload mode 正确。" if payload.mode == PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_MODE else "Execution payload mode 不匹配。",
            next_action="将 mode 设置为 execution_verify。",
            evidence_summary=payload.mode,
        ),
        make_protected_registration_check(
            check_id="command_exists",
            label="command_id 存在",
            passed=command is not None,
            message="已找到 pending command 记录。" if command else "未找到 command_id 对应的本地 task 记录。",
            next_action="确认使用 Stage 3.4.29 返回的 command_id。",
            evidence_summary=payload.command_id,
        ),
        make_protected_registration_check(
            check_id="command_type_is_protected_registration",
            label="command 类型正确",
            passed=bool(command and command.task_type == PROTECTED_RESOURCE_REGISTRATION_COMMAND_TASK_TYPE),
            message="command type 为 protected_resource_registration_command。" if command and command.task_type == PROTECTED_RESOURCE_REGISTRATION_COMMAND_TASK_TYPE else "command type 不匹配。",
            next_action="只能执行 Stage 3.4.29 创建的 protected registration command。",
            evidence_summary=command.task_type if command else "missing",
        ),
        make_protected_registration_check(
            check_id="command_stage_is_stage_3_4_29",
            label="command 来源阶段正确",
            passed=result_data.get("stage") == PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_STAGE,
            message="command 由 Stage 3.4.29 创建。" if result_data.get("stage") == PROTECTED_RESOURCE_REGISTRATION_COMMAND_CREATE_STAGE else "command 不是 Stage 3.4.29 command-create 结果。",
            next_action="重新使用 Stage 3.4.29 command-create endpoint 创建 pending command。",
            evidence_summary=str(result_data.get("stage") or ""),
        ),
        make_protected_registration_check(
            check_id="command_pending_or_already_verified",
            label="command 状态可执行或可复用",
            passed=bool(
                command
                and command.status in {PROTECTED_RESOURCE_REGISTRATION_COMMAND_STATUS, PROTECTED_RESOURCE_REGISTRATION_EXECUTED_STATUS}
            ),
            message="command 仍处于 pending 或已验证可幂等复用。" if command and command.status in {PROTECTED_RESOURCE_REGISTRATION_COMMAND_STATUS, PROTECTED_RESOURCE_REGISTRATION_EXECUTED_STATUS} else "command 状态不允许执行。",
            next_action="仅允许 pending command 或已执行成功 command 幂等复用。",
            evidence_summary=command.status if command else "missing",
        ),
        make_protected_registration_check(
            check_id="approval_text_matches_expected",
            label="最终执行审批文本匹配",
            passed=text_matches,
            message="execution approval text 完全匹配。" if text_matches else "execution approval text 不匹配。",
            next_action=f"逐字符输入 {expected_text}",
            evidence_summary="matched" if text_matches else "mismatch",
        ),
        make_protected_registration_check(
            check_id="source_approval_dry_run_passed",
            label="来源 approval dry-run 已通过",
            passed=protected_registration_command_source_approved(result_data),
            message="command 记录显示 Stage 3.4.28 approval dry-run 已通过。" if protected_registration_command_source_approved(result_data) else "command 记录未证明 approval dry-run 已通过。",
            next_action="重新运行 approval dry-run 和 command-create。",
        ),
        make_protected_registration_check(
            check_id="registration_source_preview_present",
            label="登记源摘要存在",
            passed=registration_complete,
            message="command 包含可用于本地登记的非敏感资源摘要。" if registration_complete else "command 缺少可安全登记的资源摘要。",
            next_action="重新运行 Stage 3.4.27/3.4.28/3.4.29，确保 command 包含 registration_source_preview。",
            evidence_summary="ready" if registration_complete else "missing",
        ),
        make_protected_registration_check(
            check_id="all_execution_confirmations_present",
            label="执行确认完整",
            passed=all(bool(value) for value in confirmation_values.values()),
            message="所有 execution 安全确认项已勾选。" if all(bool(value) for value in confirmation_values.values()) else "仍有 execution 安全确认项未勾选。",
            next_action="补齐所有安全确认项。",
            evidence_summary=f"{sum(1 for value in confirmation_values.values() if value)}/{len(confirmation_values)}",
        ),
        make_protected_registration_check(
            check_id="response_sensitive_content_absent",
            label="响应不包含敏感值",
            passed=not payload_has_sensitive_value and not command_has_sensitive_value,
            message="Execution verify 响应未回显完整客户端链接或凭证类敏感值。" if not payload_has_sensitive_value and not command_has_sensitive_value else "Execution payload 或 command 摘要包含疑似敏感值，已阻止执行。",
            next_action="移除完整客户端链接、密钥、命令或凭证后重新走审批链路。",
            evidence_summary="clean" if not payload_has_sensitive_value and not command_has_sensitive_value else "redacted",
        ),
    ]
    for key, value in confirmation_values.items():
        checks.append(
            make_protected_registration_check(
                check_id=f"{key}_confirmed",
                label=f"确认 {key}",
                passed=bool(value),
                message=f"已确认 {key}。" if value else f"尚未确认 {key}。",
                next_action=f"勾选 {key} 确认项。",
            )
        )
    danger_failures = [check for check in checks if check["severity"] == "danger" and not check["passed"]]
    if danger_failures or not command:
        return protected_registration_execution_empty_response(
            payload=payload,
            command_status=command.status if command else None,
            checks=checks,
            blocked_reasons=[check["message"] for check in danger_failures],
            idempotency_key=idempotency_key,
            normalized_execution_preview=normalized_execution_preview,
        )

    if command.status == PROTECTED_RESOURCE_REGISTRATION_EXECUTED_STATUS and command_execution:
        created = command_execution.get("created") if isinstance(command_execution.get("created"), dict) else {}
        verification = command_execution.get("verification") if isinstance(command_execution.get("verification"), dict) else {}
        return {
            "executed": True,
            "stage": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_STAGE,
            "mode": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_MODE,
            "command_id": command.id,
            "command_status": command.status,
            "idempotency_key": idempotency_key,
            "idempotent_reuse": True,
            "created": {
                "transit_resource_id": created.get("transit_resource_id"),
                "landing_node_id": created.get("landing_node_id"),
            },
            "verification": verification,
            "checks": checks,
            "blocked_reasons": [],
            "normalized_execution_preview": normalized_execution_preview,
            "safety_boundary": protected_registration_execution_safety_boundary(payload.confirmations),
            "ready_for_haproxy_dry_run_next_stage": True,
            "recommended_next_stage": PROTECTED_RESOURCE_REGISTRATION_HAPROXY_DRY_RUN_NEXT_STAGE,
        }

    transit_resource, transit_conflict = protected_registration_find_transit_resource(
        db,
        name=transit_name,
        entry_host=transit_entry_host,
        entry_port=transit_entry_port or 0,
    )
    landing_vps = protected_registration_find_vps_by_ip(db, landing_vps_ip)
    landing_node = None
    landing_conflict = None
    if landing_vps and landing_xray_port:
        landing_node, landing_conflict = protected_registration_find_landing_node(
            db,
            vps_id=landing_vps.id,
            node_name=landing_name,
            xray_port=landing_xray_port,
        )
    conflict_checks = [
        make_protected_registration_check(
            check_id="transit_resource_conflict_absent",
            label="中转资源无冲突",
            passed=transit_conflict is None,
            message="未发现中转资源冲突。" if transit_conflict is None else transit_conflict,
            next_action="人工核对现有 transit_resources 后再执行。",
        ),
        make_protected_registration_check(
            check_id="landing_vps_exists",
            label="落地 VPS 已存在",
            passed=landing_vps is not None,
            message="已找到匹配 landing VPS，可创建或复用 node。" if landing_vps else "未找到匹配 vps_servers.ip，无法安全创建 node。",
            next_action="先通过受保护流程登记落地服务器，或选择已有 VPS。",
            evidence_summary=landing_vps_ip,
        ),
        make_protected_registration_check(
            check_id="landing_node_conflict_absent",
            label="落地节点无冲突",
            passed=landing_conflict is None,
            message="未发现落地节点冲突。" if landing_conflict is None else landing_conflict,
            next_action="人工核对现有 nodes 后再执行。",
        ),
    ]
    checks.extend(conflict_checks)
    conflict_failures = [check for check in conflict_checks if not check["passed"]]
    if conflict_failures:
        return protected_registration_execution_empty_response(
            payload=payload,
            command_status=command.status,
            checks=checks,
            blocked_reasons=[check["message"] for check in conflict_failures],
            idempotency_key=idempotency_key,
            normalized_execution_preview=normalized_execution_preview,
        )

    if not transit_resource:
        transit_resource = TransitResource(
            id=str(uuid.uuid4()),
            name=transit_name,
            resource_type="server",
            entry_host=transit_entry_host,
            entry_port=transit_entry_port,
            entry_region=protected_registration_record_text(transit, "entry_region") or None,
            exit_region=protected_registration_record_text(transit, "exit_region") or None,
            protocol_hint="haproxy_tcp",
            has_ssh=False,
            status=transit_status if transit_status in {"active", "worker_online", "worker_offline", "pending_worker"} else "active",
            notes=f"Stage 3.4.30 protected local registration; command_id={command.id}",
        )
        db.add(transit_resource)
    if not landing_node:
        landing_node = Node(
            id=str(uuid.uuid4()),
            vps_id=landing_vps.id,
            node_name=landing_name,
            country=protected_registration_record_text(transit, "exit_region") or None,
            protocol="vless",
            transport="tcp",
            security="reality",
            flow="xtls-rprx-vision",
            xray_port=landing_xray_port,
            share_link=None,
            service_status="not_checked",
            connectivity_status=None,
            source="protected_resource_registration",
            status=landing_status if landing_status else "active",
        )
        db.add(landing_node)
    created = {
        "transit_resource_id": transit_resource.id,
        "landing_node_id": landing_node.id,
    }
    verification = {
        "transit_resource_exists": bool(transit_resource.id),
        "landing_node_exists": bool(landing_node.id),
        "worker_command_created": False,
        "transit_route_created": False,
        "haproxy_route_created": False,
        "listening_port_changed": False,
        "remote_execution_triggered": False,
        "firewall_changed": False,
        "cutover_done": False,
    }
    fingerprint = protected_registration_execution_fingerprint(command.id, idempotency_key, registration_source)
    now = datetime.now(UTC)
    command.status = PROTECTED_RESOURCE_REGISTRATION_EXECUTED_STATUS
    command.current_step = "ready_for_stage_3_4_31_haproxy_dry_run"
    command.progress = 100
    command.finished_at = now
    command.result_data = {
        **result_data,
        "command_status": PROTECTED_RESOURCE_REGISTRATION_EXECUTED_STATUS,
        "execution": {
            "stage": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_STAGE,
            "mode": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_MODE,
            "executed_at": now.isoformat(),
            "created": created,
            "verification": verification,
            "fingerprint": fingerprint,
            "idempotency_key": idempotency_key,
            "recommended_next_stage": PROTECTED_RESOURCE_REGISTRATION_HAPROXY_DRY_RUN_NEXT_STAGE,
        },
    }
    db.commit()
    return {
        "executed": True,
        "stage": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_STAGE,
        "mode": PROTECTED_RESOURCE_REGISTRATION_EXECUTION_VERIFY_MODE,
        "command_id": command.id,
        "command_status": command.status,
        "idempotency_key": idempotency_key,
        "idempotent_reuse": False,
        "created": created,
        "verification": verification,
        "checks": checks,
        "blocked_reasons": [],
        "normalized_execution_preview": normalized_execution_preview,
        "safety_boundary": protected_registration_execution_safety_boundary(payload.confirmations),
        "ready_for_haproxy_dry_run_next_stage": True,
        "recommended_next_stage": PROTECTED_RESOURCE_REGISTRATION_HAPROXY_DRY_RUN_NEXT_STAGE,
    }


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


@router.get("/haproxy-runtime-debug-context")
def get_haproxy_runtime_debug_context(request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    workers = db.scalars(select(Worker)).all()
    workers_by_server = current_worker_by_server(workers)
    workers_by_id = {worker.id: worker for worker in workers}
    all_resources = db.scalars(
        select(TransitResource)
        .order_by(TransitResource.created_at.desc())
    ).all()
    resources = [resource for resource in all_resources if resource.deleted_at is None]
    resources_by_id = {resource.id: resource for resource in all_resources}
    all_nodes = db.scalars(
        select(Node)
        .order_by(Node.created_at.desc())
    ).all()
    nodes = [node for node in all_nodes if node.deleted_at is None]
    nodes_by_id = {node.id: node for node in all_nodes}
    commands = db.scalars(
        select(WorkerCommand)
        .where(WorkerCommand.command_type == TRANSIT_ROUTE_CREATE_COMMAND)
        .where(WorkerCommand.status.in_(("created", "pending", "running", "succeeded", "failed")))
        .order_by(WorkerCommand.created_at.desc())
        .limit(50)
    ).all()

    dry_run_candidates: list[dict] = []
    for command in commands:
        candidate = haproxy_dry_run_candidate_from_command(command)
        if candidate:
            dry_run_candidates.append(
                attach_haproxy_dry_run_candidate_integrity(
                    candidate,
                    resources_by_id=resources_by_id,
                    nodes_by_id=nodes_by_id,
                    workers_by_id=workers_by_id,
                )
            )
        if len(dry_run_candidates) >= 30:
            break

    return success_response(
        {
            "transit_resources": [
                serialize_haproxy_runtime_debug_transit_resource(
                    resource,
                    workers_by_server.get(resource.id),
                )
                for resource in resources
            ],
            "landing_nodes": [serialize_haproxy_runtime_debug_landing_node(node) for node in nodes],
            "haproxy_dry_run_commands": dry_run_candidates,
            "generated_at": datetime.now(UTC).isoformat(),
            "safety_boundary": HAPROXY_RUNTIME_DEBUG_CONTEXT_BOUNDARY,
        },
        "HAProxy runtime debug context loaded; read-only.",
    )


@router.post("/protected-resource-registration-dry-run")
def protected_resource_registration_dry_run(
    payload: ProtectedResourceRegistrationDryRunRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    result = build_protected_resource_registration_dry_run(db, payload)
    return success_response(result, "protected resource registration dry-run completed")


@router.post("/protected-resource-registration-approval-dry-run")
def protected_resource_registration_approval_dry_run(
    payload: ProtectedResourceRegistrationApprovalDryRunRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    result = build_protected_resource_registration_approval_dry_run(payload)
    return success_response(result, "protected resource registration approval dry-run completed")


@router.post("/protected-resource-registration-command-create")
def protected_resource_registration_command_create(
    payload: ProtectedResourceRegistrationCommandCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    result = build_protected_resource_registration_command_create(db, payload)
    return success_response(result, "protected resource registration command-create completed")


@router.post("/protected-resource-registration-execution-verify")
def protected_resource_registration_execution_verify(
    payload: ProtectedResourceRegistrationExecutionVerifyRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    result = build_protected_resource_registration_execution_verify(db, payload)
    return success_response(result, "protected resource registration execution verify completed")


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


@router.patch("/{route_id}/name")
def rename_transit_route(
    route_id: str,
    payload: TransitRouteRenameRequest,
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
        return error_response(404, "TRANSIT_ROUTE_NOT_FOUND", "中转链路不存在。")

    route.name = payload.name
    route.updated_at = datetime.now(UTC)
    db.add(route)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="rename_transit_route",
        result="success",
        request=request,
        resource_type="transit_route",
        resource_id=route.id,
    )
    db.commit()

    return success_response(
        {
            "id": route.id,
            "name": route.name,
            "listen_port": route.listen_port,
            "target_host": route.target_host,
            "target_port": route.target_port,
            "forwarding_method": route.forwarding_method,
            "status": route.status,
            "updated_at": route.updated_at.isoformat() if route.updated_at else None,
            "share_link_present": bool(route.share_link),
        },
        "中转链路名称已更新。",
    )


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
        "route_display_name": payload.route_display_name,
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
            "route_display_name": payload.route_display_name,
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
    if command_payload.get("route_display_name") or payload.route_display_name:
        payload_match_fields["route_display_name"] = payload.route_display_name
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
    dry_run_worker_matches_target = bool(command and target_worker and command.worker_id == target_worker.id)
    final_text_ok = payload.final_approval_text.strip() == HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT
    expected_real_execution_text = haproxy_real_execution_confirmation_text(payload.planned_listen_port)
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
            check_id="dry_run_worker_matches_current_transit_worker",
            label="dry-run Worker 匹配当前 Transit Worker",
            passed=dry_run_worker_matches_target,
            message="dry-run command 来自当前 Transit Worker。" if dry_run_worker_matches_target else "dry-run command 不是当前 Transit Worker 创建的。",
            next_action="使用当前在线 Transit Worker 重新生成 HAProxy route dry-run。" if not dry_run_worker_matches_target else "继续检查。",
            evidence_summary=command.worker_id if command else None,
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
            "route_display_name": payload.route_display_name,
            "final_approval_text": HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
            "expected_real_execution_text": expected_real_execution_text,
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


def build_haproxy_route_real_execution_readiness(
    db: Session,
    payload: TransitHaproxyRouteCreateRealExecutionRequest,
    *,
    safety_boundary: list[str] | None = None,
) -> dict:
    command = db.get(WorkerCommand, payload.dry_run_command_id)
    command_payload = command.payload_json if command and isinstance(command.payload_json, dict) else {}
    resource = db.get(TransitResource, payload.transit_resource_id)
    node = db.get(Node, payload.landing_node_id)
    target_worker = latest_bound_worker(db, server_id=resource.id if resource else None)
    landing_host = node.vps.ip if node and node.vps else None
    worker_status = worker_runtime_status(target_worker) if target_worker else "missing"
    planned_service_name = f"liveline-haproxy-{payload.planned_listen_port}.service"
    expected_real_execution_text = haproxy_real_execution_confirmation_text(payload.planned_listen_port)

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
    if command_payload.get("route_display_name") or payload.route_display_name:
        payload_match_fields["route_display_name"] = payload.route_display_name
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
        and command_payload.get("planned_service_name") == planned_service_name
        and command_payload.get("route_created", False) is False
        and command_payload.get("listener_bound", False) is False
        and command_payload.get("forwarding_method") == FORWARDING_METHOD_HAPROXY_TCP
    )
    dry_run_succeeded = bool(command and command.status == "succeeded")
    dry_run_worker_matches_target = bool(command and target_worker and command.worker_id == target_worker.id)
    final_text_ok = payload.final_approval_text.strip() == HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT
    real_execution_text_ok = payload.real_execution_text.strip() == expected_real_execution_text
    worker_version_supported = worker_supports_transit_forwarding_method(
        target_worker,
        FORWARDING_METHOD_HAPROXY_TCP,
    )
    listen_port_allowed = payload.planned_listen_port not in HAPROXY_READINESS_RESERVED_PORTS
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
            check_id="dry_run_worker_matches_current_transit_worker",
            label="dry-run Worker 匹配当前 Transit Worker",
            passed=dry_run_worker_matches_target,
            message="dry-run command 来自当前 Transit Worker。" if dry_run_worker_matches_target else "dry-run command 不是当前 Transit Worker 创建的。",
            next_action="使用当前在线 Transit Worker 重新生成 HAProxy route dry-run。" if not dry_run_worker_matches_target else "继续检查。",
            evidence_summary=command.worker_id if command else None,
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
            next_action=f"输入 {expected_real_execution_text}。" if not real_execution_text_ok else "继续检查。",
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
            check_id="landing_node_active",
            label="落地节点 active",
            passed=bool(node and node.deleted_at is None and node.status == "active"),
            message="落地节点为 active。" if node and node.deleted_at is None and node.status == "active" else "落地节点不是 active。",
            next_action="选择 active 的落地节点。" if not node or node.deleted_at is not None or node.status != "active" else "继续检查。",
            evidence_summary=node.status if node else None,
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
            check_id="planned_listen_port_not_reserved",
            label="计划监听端口未保留",
            passed=listen_port_allowed,
            message="计划监听端口未命中保留端口。" if listen_port_allowed else "计划监听端口是保留端口。",
            next_action="换用未保留且已人工放行的监听端口。" if not listen_port_allowed else "继续检查。",
            evidence_summary=str(payload.planned_listen_port),
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
    response = {
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
        "route_display_name": payload.route_display_name,
        "final_approval_text": HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
        "expected_real_execution_text": expected_real_execution_text,
        "target_worker_id": target_worker.id if target_worker else None,
        "target_worker_version": target_worker.worker_version if target_worker else None,
        "minimum_supported_worker_version": minimum_worker_version_for_transit_forwarding_method(
            FORWARDING_METHOD_HAPROXY_TCP
        ),
        "checks": checks,
        "safety_boundary": safety_boundary or HAPROXY_ROUTE_REAL_EXECUTION_READINESS_BOUNDARY,
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
    return {
        "ready": ready,
        "response": response,
        "resource": resource,
        "node": node,
        "target_worker": target_worker,
        "planned_service_name": planned_service_name,
    }


@router.post("/haproxy-route-real-execution-readiness")
def haproxy_route_real_execution_readiness(
    payload: TransitHaproxyRouteCreateRealExecutionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    readiness = build_haproxy_route_real_execution_readiness(
        db,
        payload,
        safety_boundary=HAPROXY_ROUTE_REAL_EXECUTION_READINESS_BOUNDARY,
    )
    return success_response(
        readiness["response"],
        (
            "HAProxy TCP route 真实创建运行时条件已满足；本接口只读，未创建 Worker command。"
            if readiness["ready"]
            else "HAProxy TCP route 真实创建运行时条件未满足；本接口只读，未创建 Worker command。"
        ),
    )


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

    readiness = build_haproxy_route_real_execution_readiness(
        db,
        payload,
        safety_boundary=HAPROXY_ROUTE_CREATE_REAL_EXECUTION_BOUNDARY,
    )
    blocked_response = readiness["response"]
    if not readiness["ready"]:
        return success_response(
            blocked_response,
            "HAProxy route 真实创建被阻塞；未创建 Worker command、HAProxy route 或监听端口。",
        )
    resource = readiness["resource"]
    node = readiness["node"]
    target_worker = readiness["target_worker"]
    planned_service_name = readiness["planned_service_name"]

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
        "real_execution": True,
        "approved_real_execution": True,
        "user_approved_real_execution": True,
        "route_name": payload.route_name,
        "route_display_name": payload.route_display_name,
        "planned_service_name": planned_service_name,
        "route_created": False,
        "haproxy_installed": False,
        "listener_bound": False,
        "firewall_modified": False,
        "share_link_mutated": False,
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
