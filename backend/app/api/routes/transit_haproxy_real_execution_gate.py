from typing import Any

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.db.session import get_db
from app.models.worker_command import WorkerCommand
from app.schemas.common import success_response
from app.schemas.transit_route import (
    FORWARDING_METHOD_HAPROXY_TCP,
    HAPROXY_ROUTE_CREATE_DRY_RUN_STAGE,
    HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
    TransitHaproxyRouteCreateRealExecutionRequest,
    haproxy_real_execution_confirmation_text,
)

from . import transit_routes

HAPROXY_REAL_EXECUTION_DYNAMIC_APPROVAL_BOUNDARY = [
    "backend dynamic HAProxy approval gate",
    "requires a succeeded HAProxy TCP dry-run command before real_create",
    "requires dry-run Worker to match the current online transit Worker",
    "requires planned_listen_port to match approved_planned_listen_port",
    "requires landing_target_host to match approved_landing_target_host",
    "requires landing_target_port to match approved_landing_target_port",
    "requires approved_firewall_confirmation=true",
    "no Worker command created when dynamic approval gate blocks",
    "no HAProxy route created by this request",
    "no listener binding",
    "no firewall, cloud firewall, or cloud security group mutation",
    "no nodes.share_link read or mutation",
    "no transit_routes.share_link write",
    "no full client link export",
    "no cutover",
]

_original_real_execution_handler = transit_routes.create_haproxy_route_create_real_execution
_installed = False


def _planned_service_name(port: int) -> str:
    return f"liveline-haproxy-{port}.service"


def _check_item(*, check_id: str, label: str, passed: bool, message: str, next_action: str, evidence_summary: str | None = None) -> dict[str, Any]:
    return {
        "id": check_id,
        "label": label,
        "category": "dynamic_approval_gate",
        "status": "passed" if passed else "blocked",
        "passed": passed,
        "message": message,
        "evidence_summary": evidence_summary or ("confirmed" if passed else "missing_or_blocked"),
        "next_action": next_action,
        "sensitive_output_redacted": True,
    }


def build_haproxy_real_execution_dynamic_approval_checks(
    payload: TransitHaproxyRouteCreateRealExecutionRequest,
    dry_run_payload: dict[str, Any] | None,
    *,
    dry_run_status: str | None = "succeeded",
    dry_run_command_type: str | None = "transit_route_create",
    dry_run_worker_id: str | None = None,
    current_worker_id: str | None = None,
) -> list[dict[str, Any]]:
    command_payload = dry_run_payload if isinstance(dry_run_payload, dict) else {}
    approved_planned_listen_port = command_payload.get("approved_planned_listen_port")
    approved_landing_target_host = command_payload.get("approved_landing_target_host")
    approved_landing_target_port = command_payload.get("approved_landing_target_port")
    expected_real_execution_text = haproxy_real_execution_confirmation_text(payload.planned_listen_port)

    checks = [
        _check_item(
            check_id="dry_run_command_succeeded",
            label="dry-run command 已成功",
            passed=dry_run_status == "succeeded",
            message="dry-run command 已 succeeded。" if dry_run_status == "succeeded" else f"dry-run command 必须为 succeeded，当前状态为 {dry_run_status or 'missing'}。",
            next_action="重新生成 HAProxy TCP dry-run，直到 command succeeded。" if dry_run_status != "succeeded" else "继续检查。",
            evidence_summary=dry_run_status,
        ),
        _check_item(
            check_id="dry_run_command_type_valid",
            label="dry-run command 类型合法",
            passed=dry_run_command_type == "transit_route_create",
            message="dry-run command type 是 transit_route_create。" if dry_run_command_type == "transit_route_create" else "dry-run command type 不是 transit_route_create。",
            next_action="使用 HAProxy TCP 创建流程重新生成 dry-run。" if dry_run_command_type != "transit_route_create" else "继续检查。",
            evidence_summary=dry_run_command_type,
        ),
        _check_item(
            check_id="dry_run_command_intent_valid",
            label="dry-run command intent 合法",
            passed=command_payload.get("command_intent") == "haproxy_route_create_dry_run",
            message="dry-run command intent 是 haproxy_route_create_dry_run。" if command_payload.get("command_intent") == "haproxy_route_create_dry_run" else "dry-run command intent 不匹配。",
            next_action="使用 Stage 3.3.137 重新生成 HAProxy TCP dry-run。" if command_payload.get("command_intent") != "haproxy_route_create_dry_run" else "继续检查。",
            evidence_summary=str(command_payload.get("command_intent")),
        ),
        _check_item(
            check_id="dry_run_forwarding_method_valid",
            label="dry-run 转发方式为 HAProxy TCP",
            passed=command_payload.get("forwarding_method") == FORWARDING_METHOD_HAPROXY_TCP,
            message="dry-run 转发方式为 haproxy_tcp。" if command_payload.get("forwarding_method") == FORWARDING_METHOD_HAPROXY_TCP else "dry-run 转发方式不是 haproxy_tcp。",
            next_action="重新生成 HAProxy TCP dry-run。" if command_payload.get("forwarding_method") != FORWARDING_METHOD_HAPROXY_TCP else "继续检查。",
            evidence_summary=str(command_payload.get("forwarding_method")),
        ),
        _check_item(
            check_id="dry_run_mode_valid",
            label="dry-run execution flags 合法",
            passed=command_payload.get("dry_run") is True and command_payload.get("approval_required") is True and command_payload.get("real_execution") is False,
            message="dry-run flags 合法。" if command_payload.get("dry_run") is True and command_payload.get("approval_required") is True and command_payload.get("real_execution") is False else "dry-run flags 不合法。",
            next_action="重新生成 approval_required 的 HAProxy TCP dry-run。" if not (command_payload.get("dry_run") is True and command_payload.get("approval_required") is True and command_payload.get("real_execution") is False) else "继续检查。",
            evidence_summary=f"dry_run={command_payload.get('dry_run')}, approval_required={command_payload.get('approval_required')}, real_execution={command_payload.get('real_execution')}",
        ),
        _check_item(
            check_id="dry_run_approval_stage_valid",
            label="dry-run approval stage 合法",
            passed=command_payload.get("approval_stage") == HAPROXY_ROUTE_CREATE_DRY_RUN_STAGE,
            message="dry-run approval_stage 合法。" if command_payload.get("approval_stage") == HAPROXY_ROUTE_CREATE_DRY_RUN_STAGE else "dry-run approval_stage 不匹配。",
            next_action="重新生成当前 HAProxy TCP dry-run 阶段的 command。" if command_payload.get("approval_stage") != HAPROXY_ROUTE_CREATE_DRY_RUN_STAGE else "继续检查。",
            evidence_summary=str(command_payload.get("approval_stage")),
        ),
        _check_item(
            check_id="dry_run_worker_matches_current_transit_worker",
            label="dry-run Worker 匹配当前 Transit Worker",
            passed=bool(dry_run_worker_id and current_worker_id and dry_run_worker_id == current_worker_id),
            message="dry-run command 来自当前 Transit Worker。" if dry_run_worker_id and current_worker_id and dry_run_worker_id == current_worker_id else "dry-run command 不是当前 Transit Worker 创建的。",
            next_action="使用当前在线 Transit Worker 重新生成 HAProxy TCP dry-run。" if not (dry_run_worker_id and current_worker_id and dry_run_worker_id == current_worker_id) else "继续检查。",
            evidence_summary=dry_run_worker_id,
        ),
        _check_item(
            check_id="planned_listen_port_matches_request",
            label="dry-run 监听端口匹配 request",
            passed=command_payload.get("planned_listen_port") == payload.planned_listen_port,
            message="dry-run planned_listen_port 与 request 一致。" if command_payload.get("planned_listen_port") == payload.planned_listen_port else "dry-run planned_listen_port 与 request 不一致。",
            next_action="使用 dry-run 返回的计划监听端口发起 real_create。" if command_payload.get("planned_listen_port") != payload.planned_listen_port else "继续检查。",
            evidence_summary=str(command_payload.get("planned_listen_port")),
        ),
        _check_item(
            check_id="approved_planned_listen_port_matches_request",
            label="approved planned listen port 匹配",
            passed=approved_planned_listen_port == payload.planned_listen_port,
            message="approved_planned_listen_port 与 planned_listen_port 一致。" if approved_planned_listen_port == payload.planned_listen_port else "approved_planned_listen_port 缺失或与 planned_listen_port 不一致。",
            next_action="重新生成包含 approved_planned_listen_port 的 dry-run。" if approved_planned_listen_port != payload.planned_listen_port else "继续检查。",
            evidence_summary=str(approved_planned_listen_port),
        ),
        _check_item(
            check_id="approved_firewall_confirmation_present",
            label="approved firewall confirmation 存在",
            passed=command_payload.get("approved_firewall_confirmation") is True,
            message="dry-run 已记录 approved_firewall_confirmation=true。" if command_payload.get("approved_firewall_confirmation") is True else "dry-run 未记录 approved_firewall_confirmation=true。",
            next_action="重新确认端口放行后生成 dry-run。" if command_payload.get("approved_firewall_confirmation") is not True else "继续检查。",
            evidence_summary=str(command_payload.get("approved_firewall_confirmation")),
        ),
        _check_item(
            check_id="landing_target_host_matches_request",
            label="dry-run 落地 Host 匹配 request",
            passed=command_payload.get("landing_target_host") == payload.landing_target_host,
            message="dry-run landing_target_host 与 request 一致。" if command_payload.get("landing_target_host") == payload.landing_target_host else "dry-run landing_target_host 与 request 不一致。",
            next_action="使用 dry-run 返回的落地目标 Host 发起 real_create。" if command_payload.get("landing_target_host") != payload.landing_target_host else "继续检查。",
            evidence_summary=str(command_payload.get("landing_target_host")),
        ),
        _check_item(
            check_id="approved_landing_target_host_matches_request",
            label="approved landing target Host 匹配",
            passed=approved_landing_target_host == payload.landing_target_host,
            message="approved_landing_target_host 与 landing_target_host 一致。" if approved_landing_target_host == payload.landing_target_host else "approved_landing_target_host 缺失或与 landing_target_host 不一致。",
            next_action="重新生成包含 approved_landing_target_host 的 dry-run。" if approved_landing_target_host != payload.landing_target_host else "继续检查。",
            evidence_summary=str(approved_landing_target_host),
        ),
        _check_item(
            check_id="landing_target_port_matches_request",
            label="dry-run 落地端口匹配 request",
            passed=command_payload.get("landing_target_port") == payload.landing_target_port,
            message="dry-run landing_target_port 与 request 一致。" if command_payload.get("landing_target_port") == payload.landing_target_port else "dry-run landing_target_port 与 request 不一致。",
            next_action="使用 dry-run 返回的落地目标端口发起 real_create。" if command_payload.get("landing_target_port") != payload.landing_target_port else "继续检查。",
            evidence_summary=str(command_payload.get("landing_target_port")),
        ),
        _check_item(
            check_id="approved_landing_target_port_matches_request",
            label="approved landing target port 匹配",
            passed=approved_landing_target_port == payload.landing_target_port,
            message="approved_landing_target_port 与 landing_target_port 一致。" if approved_landing_target_port == payload.landing_target_port else "approved_landing_target_port 缺失或与 landing_target_port 不一致。",
            next_action="重新生成包含 approved_landing_target_port 的 dry-run。" if approved_landing_target_port != payload.landing_target_port else "继续检查。",
            evidence_summary=str(approved_landing_target_port),
        ),
        _check_item(
            check_id="request_forwarding_method_valid",
            label="request 转发方式为 HAProxy TCP",
            passed=payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP,
            message="request 转发方式为 haproxy_tcp。" if payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP else "request 转发方式不是 haproxy_tcp。",
            next_action="选择 HAProxy TCP mode。" if payload.forwarding_method != FORWARDING_METHOD_HAPROXY_TCP else "继续检查。",
            evidence_summary=payload.forwarding_method,
        ),
        _check_item(
            check_id="request_final_approval_text_valid",
            label="request final approval 文本正确",
            passed=payload.final_approval_text.strip() == HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
            message="request final approval 文本正确。" if payload.final_approval_text.strip() == HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT else "request final approval 文本不正确。",
            next_action="输入正确的 final approval 确认文本。" if payload.final_approval_text.strip() != HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT else "继续检查。",
            evidence_summary="typed_confirmation",
        ),
        _check_item(
            check_id="request_real_execution_text_valid",
            label="request real execution 文本正确",
            passed=payload.real_execution_text.strip() == expected_real_execution_text,
            message="request real execution 文本正确。" if payload.real_execution_text.strip() == expected_real_execution_text else "request real execution 文本不正确。",
            next_action=f"输入 {expected_real_execution_text}。" if payload.real_execution_text.strip() != expected_real_execution_text else "继续检查。",
            evidence_summary="typed_confirmation",
        ),
        _check_item(
            check_id="request_firewall_confirmations_present",
            label="request 防火墙确认齐全",
            passed=payload.firewall_security_group_confirmed and payload.cloud_firewall_confirmed and payload.server_firewall_confirmed,
            message="request 防火墙确认齐全。" if payload.firewall_security_group_confirmed and payload.cloud_firewall_confirmed and payload.server_firewall_confirmed else "request 缺少防火墙确认。",
            next_action="确认云安全组、云防火墙和服务器本机防火墙均已放行。" if not (payload.firewall_security_group_confirmed and payload.cloud_firewall_confirmed and payload.server_firewall_confirmed) else "继续检查。",
        ),
        _check_item(
            check_id="request_safety_confirmations_present",
            label="request 安全边界确认齐全",
            passed=payload.no_cutover_confirmed and payload.no_node_share_link_change_confirmed and payload.no_full_client_link_confirmed,
            message="request 安全边界确认齐全。" if payload.no_cutover_confirmed and payload.no_node_share_link_change_confirmed and payload.no_full_client_link_confirmed else "request 缺少安全边界确认。",
            next_action="确认不 cutover、不修改 nodes.share_link、不输出完整客户端链接。" if not (payload.no_cutover_confirmed and payload.no_node_share_link_change_confirmed and payload.no_full_client_link_confirmed) else "继续检查。",
        ),
    ]
    return checks


def dynamic_approval_gate_passed(
    payload: TransitHaproxyRouteCreateRealExecutionRequest,
    dry_run_payload: dict[str, Any] | None,
    *,
    dry_run_status: str | None = "succeeded",
    dry_run_command_type: str | None = "transit_route_create",
    dry_run_worker_id: str | None = None,
    current_worker_id: str | None = None,
) -> bool:
    return all(
        check["passed"]
        for check in build_haproxy_real_execution_dynamic_approval_checks(
            payload,
            dry_run_payload,
            dry_run_status=dry_run_status,
            dry_run_command_type=dry_run_command_type,
            dry_run_worker_id=dry_run_worker_id,
            current_worker_id=current_worker_id,
        )
    )


def blocked_dynamic_approval_response(
    payload: TransitHaproxyRouteCreateRealExecutionRequest,
    checks: list[dict[str, Any]],
):
    return success_response(
        {
            "ready_for_real_execution": False,
            "blocked": True,
            "summary": "HAProxy TCP real execution blocked by dynamic approval gate",
            "next_action": "重新生成并使用同一组动态审批参数的 HAProxy TCP dry-run；不会创建 Worker command、HAProxy route 或监听端口。",
            "dry_run_command_id": payload.dry_run_command_id,
            "planned_service_name": _planned_service_name(payload.planned_listen_port),
            "planned_listen_port": payload.planned_listen_port,
            "landing_target_host": payload.landing_target_host,
            "landing_target_port": payload.landing_target_port,
            "forwarding_method": payload.forwarding_method,
            "route_name": payload.route_name,
            "checks": checks,
            "safety_boundary": HAPROXY_REAL_EXECUTION_DYNAMIC_APPROVAL_BOUNDARY,
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
        "HAProxy route 真实创建被动态审批门禁阻塞；未创建 Worker command、HAProxy route 或监听端口。",
    )


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
    command_payload = command.payload_json if command and isinstance(command.payload_json, dict) else None
    target_worker = transit_routes.latest_bound_worker(db, server_id=payload.transit_resource_id)
    checks = build_haproxy_real_execution_dynamic_approval_checks(
        payload,
        command_payload,
        dry_run_status=command.status if command else None,
        dry_run_command_type=command.command_type if command else None,
        dry_run_worker_id=command.worker_id if command else None,
        current_worker_id=target_worker.id if target_worker else None,
    )
    if not all(check["passed"] for check in checks):
        return blocked_dynamic_approval_response(payload, checks)
    return _original_real_execution_handler(payload, request, db)


def install() -> None:
    global _installed
    if _installed:
        return

    transit_routes.create_haproxy_route_create_real_execution = create_haproxy_route_create_real_execution
    transit_routes.router.routes = [
        route
        for route in transit_routes.router.routes
        if not (
            getattr(route, "path", None) == "/haproxy-route-create-real-execution"
            and "POST" in (getattr(route, "methods", set()) or set())
        )
    ]
    transit_routes.router.post("/haproxy-route-create-real-execution")(create_haproxy_route_create_real_execution)
    _installed = True
