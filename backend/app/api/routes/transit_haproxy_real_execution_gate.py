from typing import Any

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.worker_command import WorkerCommand
from app.schemas.common import success_response
from app.schemas.transit_route import (
    APPROVED_LANDING_TARGET_HOST,
    APPROVED_LANDING_TARGET_PORT,
    APPROVED_TRANSIT_LISTEN_PORT,
    FORWARDING_METHOD_HAPROXY_TCP,
    TransitHaproxyRouteCreateRealExecutionRequest,
)

from . import transit_routes

APPROVED_HAPROXY_ROUTE_NAME = "haproxy-tcp-23843"
APPROVED_HAPROXY_SERVICE_NAME = "liveline-haproxy-23843.service"
HAPROXY_REAL_EXECUTION_FIXED_PARAMETER_BOUNDARY = [
    "backend fixed approved HAProxy parameter gate",
    "blocks before WorkerCommand creation when request or dry-run evidence is outside the approved route",
    "approved listen port only: 23843",
    "approved landing target only: 64.90.13.19:27939",
    "approved route name only: haproxy-tcp-23843",
    "approved service only: liveline-haproxy-23843.service",
    "no Worker command created when fixed-parameter gate blocks",
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
        "category": "fixed_parameter_gate",
        "status": "passed" if passed else "blocked",
        "passed": passed,
        "message": message,
        "evidence_summary": evidence_summary or ("confirmed" if passed else "missing_or_blocked"),
        "next_action": next_action,
        "sensitive_output_redacted": True,
    }


def build_haproxy_real_execution_fixed_parameter_checks(
    payload: TransitHaproxyRouteCreateRealExecutionRequest,
    dry_run_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    command_payload = dry_run_payload if isinstance(dry_run_payload, dict) else {}
    request_service_name = _planned_service_name(payload.planned_listen_port)

    checks = [
        _check_item(
            check_id="approved_request_listen_port",
            label="请求监听端口为批准端口",
            passed=payload.planned_listen_port == APPROVED_TRANSIT_LISTEN_PORT,
            message="请求监听端口是批准端口 23843。" if payload.planned_listen_port == APPROVED_TRANSIT_LISTEN_PORT else "请求监听端口不是批准端口 23843。",
            next_action="重新使用批准的 HAProxy route dry-run 参数。",
            evidence_summary=str(payload.planned_listen_port),
        ),
        _check_item(
            check_id="approved_request_landing_host",
            label="请求落地 Host 为批准目标",
            passed=payload.landing_target_host == APPROVED_LANDING_TARGET_HOST,
            message="请求落地 Host 是批准目标。" if payload.landing_target_host == APPROVED_LANDING_TARGET_HOST else "请求落地 Host 不是批准目标。",
            next_action="重新使用批准的落地目标 64.90.13.19。",
            evidence_summary=payload.landing_target_host,
        ),
        _check_item(
            check_id="approved_request_landing_port",
            label="请求落地端口为批准目标端口",
            passed=payload.landing_target_port == APPROVED_LANDING_TARGET_PORT,
            message="请求落地端口是批准目标端口 27939。" if payload.landing_target_port == APPROVED_LANDING_TARGET_PORT else "请求落地端口不是批准目标端口 27939。",
            next_action="重新使用批准的落地目标端口 27939。",
            evidence_summary=str(payload.landing_target_port),
        ),
        _check_item(
            check_id="approved_request_route_name",
            label="请求 route_name 为批准名称",
            passed=payload.route_name == APPROVED_HAPROXY_ROUTE_NAME,
            message="请求 route_name 是批准名称。" if payload.route_name == APPROVED_HAPROXY_ROUTE_NAME else "请求 route_name 不是批准名称。",
            next_action="重新使用批准的 route_name=haproxy-tcp-23843。",
            evidence_summary=payload.route_name,
        ),
        _check_item(
            check_id="approved_request_service_name",
            label="请求派生 service_name 为批准名称",
            passed=request_service_name == APPROVED_HAPROXY_SERVICE_NAME,
            message="请求派生 service_name 是批准名称。" if request_service_name == APPROVED_HAPROXY_SERVICE_NAME else "请求派生 service_name 不是批准名称。",
            next_action="重新使用批准的监听端口 23843。",
            evidence_summary=request_service_name,
        ),
        _check_item(
            check_id="approved_request_forwarding_method",
            label="请求转发方式为 HAProxy TCP",
            passed=payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP,
            message="请求转发方式为 haproxy_tcp。" if payload.forwarding_method == FORWARDING_METHOD_HAPROXY_TCP else "请求转发方式不是 haproxy_tcp。",
            next_action="重新选择 HAProxy TCP mode。",
            evidence_summary=payload.forwarding_method,
        ),
        _check_item(
            check_id="approved_dry_run_listen_port",
            label="dry-run 监听端口为批准端口",
            passed=command_payload.get("planned_listen_port") == APPROVED_TRANSIT_LISTEN_PORT,
            message="dry-run 监听端口是批准端口 23843。" if command_payload.get("planned_listen_port") == APPROVED_TRANSIT_LISTEN_PORT else "dry-run 监听端口不是批准端口 23843。",
            next_action="重新生成批准参数的 Stage 3.3.137 HAProxy dry-run。",
            evidence_summary=str(command_payload.get("planned_listen_port")),
        ),
        _check_item(
            check_id="approved_dry_run_landing_host",
            label="dry-run 落地 Host 为批准目标",
            passed=command_payload.get("landing_target_host") == APPROVED_LANDING_TARGET_HOST,
            message="dry-run 落地 Host 是批准目标。" if command_payload.get("landing_target_host") == APPROVED_LANDING_TARGET_HOST else "dry-run 落地 Host 不是批准目标。",
            next_action="重新生成批准目标的 Stage 3.3.137 HAProxy dry-run。",
            evidence_summary=str(command_payload.get("landing_target_host")),
        ),
        _check_item(
            check_id="approved_dry_run_landing_port",
            label="dry-run 落地端口为批准目标端口",
            passed=command_payload.get("landing_target_port") == APPROVED_LANDING_TARGET_PORT,
            message="dry-run 落地端口是批准目标端口 27939。" if command_payload.get("landing_target_port") == APPROVED_LANDING_TARGET_PORT else "dry-run 落地端口不是批准目标端口 27939。",
            next_action="重新生成批准目标端口的 Stage 3.3.137 HAProxy dry-run。",
            evidence_summary=str(command_payload.get("landing_target_port")),
        ),
        _check_item(
            check_id="approved_dry_run_route_name",
            label="dry-run route_name 为批准名称",
            passed=command_payload.get("route_name") == APPROVED_HAPROXY_ROUTE_NAME,
            message="dry-run route_name 是批准名称。" if command_payload.get("route_name") == APPROVED_HAPROXY_ROUTE_NAME else "dry-run route_name 不是批准名称。",
            next_action="重新生成批准 route_name 的 Stage 3.3.137 HAProxy dry-run。",
            evidence_summary=str(command_payload.get("route_name")),
        ),
        _check_item(
            check_id="approved_dry_run_service_name",
            label="dry-run service_name 为批准名称",
            passed=command_payload.get("planned_service_name") == APPROVED_HAPROXY_SERVICE_NAME,
            message="dry-run service_name 是批准名称。" if command_payload.get("planned_service_name") == APPROVED_HAPROXY_SERVICE_NAME else "dry-run service_name 不是批准名称。",
            next_action="重新生成批准 service_name 的 Stage 3.3.137 HAProxy dry-run。",
            evidence_summary=str(command_payload.get("planned_service_name")),
        ),
        _check_item(
            check_id="approved_dry_run_forwarding_method",
            label="dry-run 转发方式为 HAProxy TCP",
            passed=command_payload.get("forwarding_method") == FORWARDING_METHOD_HAPROXY_TCP,
            message="dry-run 转发方式为 haproxy_tcp。" if command_payload.get("forwarding_method") == FORWARDING_METHOD_HAPROXY_TCP else "dry-run 转发方式不是 haproxy_tcp。",
            next_action="重新生成 HAProxy TCP dry-run。",
            evidence_summary=str(command_payload.get("forwarding_method")),
        ),
    ]
    return checks


def fixed_parameter_gate_passed(
    payload: TransitHaproxyRouteCreateRealExecutionRequest,
    dry_run_payload: dict[str, Any] | None,
) -> bool:
    return all(check["passed"] for check in build_haproxy_real_execution_fixed_parameter_checks(payload, dry_run_payload))


def blocked_fixed_parameter_response(
    payload: TransitHaproxyRouteCreateRealExecutionRequest,
    checks: list[dict[str, Any]],
):
    return success_response(
        {
            "ready_for_real_execution": False,
            "blocked": True,
            "summary": "HAProxy TCP route real execution blocked by fixed approved parameter gate",
            "next_action": "重新生成并使用批准参数的 Stage 3.3.137 dry-run；不会创建 Worker command、HAProxy route 或监听端口。",
            "dry_run_command_id": payload.dry_run_command_id,
            "planned_service_name": _planned_service_name(payload.planned_listen_port),
            "planned_listen_port": payload.planned_listen_port,
            "landing_target_host": payload.landing_target_host,
            "landing_target_port": payload.landing_target_port,
            "forwarding_method": payload.forwarding_method,
            "route_name": payload.route_name,
            "approved_parameters": {
                "planned_service_name": APPROVED_HAPROXY_SERVICE_NAME,
                "planned_listen_port": APPROVED_TRANSIT_LISTEN_PORT,
                "landing_target_host": APPROVED_LANDING_TARGET_HOST,
                "landing_target_port": APPROVED_LANDING_TARGET_PORT,
                "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
                "route_name": APPROVED_HAPROXY_ROUTE_NAME,
            },
            "checks": checks,
            "safety_boundary": HAPROXY_REAL_EXECUTION_FIXED_PARAMETER_BOUNDARY,
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
        "HAProxy route 真实创建被固定批准参数门禁阻塞；未创建 Worker command、HAProxy route 或监听端口。",
    )


def create_haproxy_route_create_real_execution(
    payload: TransitHaproxyRouteCreateRealExecutionRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    command = db.get(WorkerCommand, payload.dry_run_command_id)
    command_payload = command.payload_json if command and isinstance(command.payload_json, dict) else None
    if command_payload is not None:
        checks = build_haproxy_real_execution_fixed_parameter_checks(payload, command_payload)
        if not all(check["passed"] for check in checks):
            return blocked_fixed_parameter_response(payload, checks)
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
