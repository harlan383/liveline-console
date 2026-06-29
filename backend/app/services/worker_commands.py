from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.worker import Worker
from app.models.worker_command import WorkerCommand
from app.schemas.worker_commands import WORKER_COMMAND_TYPES

COMMAND_LEASE_SECONDS = 90
DEFAULT_NEXT_POLL_SECONDS = 20
RECENT_COMMAND_LIMIT = 20
MAX_RESULT_STRING_LENGTH = 1000
MAX_TRANSIT_PREFLIGHT_CHECKS = 50
SENSITIVE_MARKERS = (
    "secret",
    "token",
    "password",
    "passwd",
    "passphrase",
    "private_key",
    "ssh_key",
    "session",
    "cookie",
    "share_link",
    "vless://",
    "vmess://",
    "ss://",
)
SAFE_SENSITIVE_NAMED_CONFIRMATION_KEYS = {
    "no_node_share_link_change_confirmed",
}
REMOTE_CLEANUP_COMMAND_TYPES = {
    "cleanup_landing_node",
    "cleanup_landing_server",
    "cleanup_transit_route",
    "cleanup_transit_resource",
}
REMOTE_CLEANUP_SERVER_COMMAND_TYPES = {
    "cleanup_landing_server",
    "cleanup_transit_resource",
}


def now_utc() -> datetime:
    return datetime.now(UTC)


def command_type_allowed(command_type: str) -> bool:
    return command_type in WORKER_COMMAND_TYPES


def sanitize_command_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    return sanitize_value(payload)


def sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered_key = key_text.lower()
            if any(marker in lowered_key for marker in SENSITIVE_MARKERS):
                if lowered_key in SAFE_SENSITIVE_NAMED_CONFIRMATION_KEYS and isinstance(item, bool):
                    result[key_text] = item
                    continue
                result[key_text] = "[redacted]"
                continue
            result[key_text] = sanitize_value(item)
        return result
    if isinstance(value, list):
        return [sanitize_value(item) for item in value[:50]]
    if isinstance(value, str):
        value = value.replace("\x00", "")
        lowered_value = value.lower()
        if any(marker in lowered_value for marker in ("vless://", "vmess://", "ss://")):
            return "[redacted-link]"
        if len(value) > MAX_RESULT_STRING_LENGTH:
            return value[:MAX_RESULT_STRING_LENGTH] + "...[truncated]"
    return value


def normalize_worker_command_result(command_type: str, result: Any) -> dict[str, Any]:
    if result is None:
        return {}
    if not isinstance(result, dict):
        raise ValueError("Worker command result must be a JSON object.")
    if command_type == "transit_readonly_preflight":
        return normalize_transit_readonly_preflight_result(result)
    if command_type == "landing_node_create":
        return normalize_landing_node_create_result(result)
    if command_type == "transit_route_create":
        return normalize_transit_route_create_result(result)
    if command_type in REMOTE_CLEANUP_COMMAND_TYPES:
        return normalize_remote_cleanup_result(command_type, result)
    normalized = sanitize_value(result)
    if not isinstance(normalized, dict):
        raise ValueError("Worker command result normalization returned a non-object.")
    return normalized


def normalize_transit_readonly_preflight_result(result: dict[str, Any]) -> dict[str, Any]:
    checks = _normalize_transit_preflight_checks(result.get("checks"))
    passed = result.get("passed")
    if not isinstance(passed, bool):
        passed = all(bool(check.get("passed")) for check in checks) if checks else False

    status = _safe_result_text(result.get("status")) or ("passed" if passed else "blocked")
    summary = _safe_result_text(result.get("summary")) or (
        "Remote readonly preflight passed." if passed else "Remote readonly preflight returned blockers."
    )

    normalized: dict[str, Any] = {
        "passed": passed,
        "status": status,
        "summary": summary,
        "checks": checks,
        "worker_version": _safe_result_text(result.get("worker_version")),
        "hostname": _safe_result_text(result.get("hostname")),
        "role": _safe_result_text(result.get("role")),
        "interface_name": _safe_result_text(result.get("interface_name")),
        "planned_listen_port": _safe_result_int(result.get("planned_listen_port")),
        "landing_target_port": _safe_result_int(result.get("landing_target_port")),
        "forwarding_method": _safe_result_text(result.get("forwarding_method")),
        "redacted_summary": _safe_result_text(result.get("redacted_summary")) or summary,
        "safety_boundary": _normalize_text_list(result.get("safety_boundary")),
    }

    extra: dict[str, Any] = {}
    for key, value in result.items():
        if key in normalized:
            continue
        if key == "checks":
            continue
        extra[str(key)] = sanitize_value(value)
    if extra:
        normalized["extra"] = extra
    return sanitize_value(normalized)


def normalize_transit_route_create_result(result: dict[str, Any]) -> dict[str, Any]:
    status = _safe_result_text(result.get("status")) or "approval_required"
    execution_mode = _safe_result_text(result.get("execution_mode"))
    if not execution_mode:
        execution_mode = "real_create" if result.get("real_execution") is True else "dry_run"
    summary = _safe_result_text(result.get("summary"))
    if not summary:
        summary = (
            "Transit route create real execution returned a result."
            if execution_mode == "real_create"
            else "Transit route create dry-run returned a result."
        )
    checks = _normalize_transit_route_create_checks(result.get("checks"))

    normalized: dict[str, Any] = {
        "execution_mode": execution_mode,
        "real_execution": result.get("real_execution") is True,
        "status": status,
        "summary": summary,
        "redacted_error": _safe_result_text(result.get("redacted_error")),
        "worker_version": _safe_result_text(result.get("worker_version")),
        "hostname": _safe_result_text(result.get("hostname")),
        "role": _safe_result_text(result.get("role")),
        "interface_name": _safe_result_text(result.get("interface_name")),
        "planned_listen_port": _safe_result_int(result.get("planned_listen_port")),
        "landing_target_host": _safe_result_text(result.get("landing_target_host")),
        "landing_target_port": _safe_result_int(result.get("landing_target_port")),
        "forwarding_method": _safe_result_text(result.get("forwarding_method")),
        "route_name": _safe_result_text(result.get("route_name")),
        "planned_service_name": _safe_result_text(result.get("planned_service_name")),
        "service_name": _safe_result_text(result.get("service_name")),
        "service_path": _safe_result_text(result.get("service_path")),
        "checks_count": _safe_result_int(result.get("checks_count")) or len(checks),
        "planned_actions_count": _safe_result_int(result.get("planned_actions_count")),
        "listen_attempts_count": _safe_result_int(result.get("listen_attempts_count")),
        "rollback_attempted": result.get("rollback_attempted") is True,
        "safety_boundary": _normalize_text_list(result.get("safety_boundary"))[:5],
    }
    if checks:
        normalized["checks"] = checks

    diagnostics = _normalize_transit_route_create_diagnostics(result.get("diagnostics"))
    if diagnostics:
        normalized["diagnostics"] = diagnostics

    listen_attempts = _normalize_transit_route_listen_attempts(result.get("listen_verification_attempts"))
    if listen_attempts:
        normalized["listen_verification_attempts"] = listen_attempts

    last_listen_attempt = _normalize_transit_route_listen_attempt(result.get("last_listen_attempt"))
    if last_listen_attempt:
        normalized["last_listen_attempt"] = last_listen_attempt

    failed_names = _normalize_text_list(result.get("failed_check_names"))[:MAX_TRANSIT_PREFLIGHT_CHECKS]
    if failed_names:
        normalized["failed_check_names"] = failed_names

    return sanitize_value(normalized)


def normalize_landing_node_create_result(result: dict[str, Any]) -> dict[str, Any]:
    status = _safe_result_text(result.get("status")) or "failed"
    summary = _safe_result_text(result.get("summary")) or "Landing node create returned a result."
    normalized: dict[str, Any] = {
        "command_type": "landing_node_create",
        "status": status,
        "summary": summary,
        "redacted_error": _safe_result_text(result.get("redacted_error")),
        "worker_version": _safe_result_text(result.get("worker_version")),
        "node_name": _safe_result_text(result.get("node_name")),
        "listen_port": _safe_result_int(result.get("listen_port")),
        "xray_service_active": _safe_result_text(result.get("xray_service_active")),
        "xray_service_enabled": _safe_result_text(result.get("xray_service_enabled")),
        "xray_config_exists": result.get("xray_config_exists") is True,
        "xray_binary_exists": result.get("xray_binary_exists") is True,
        "xray_config_test_ok": result.get("xray_config_test_ok") is True,
        "xray_config_inbounds_summary": _normalize_landing_xray_inbounds(
            result.get("xray_config_inbounds_summary")
        ),
        "listen_check_attempts": _normalize_landing_listen_attempts(result.get("listen_check_attempts")),
        "ss_listen_summary": _normalize_text_list(result.get("ss_listen_summary"))[:30],
        "systemd_status_summary": _safe_result_text(result.get("systemd_status_summary")),
        "journal_tail_summary": _safe_result_text(result.get("journal_tail_summary")),
        "rollback_performed": result.get("rollback_performed") is True,
        "rollback_summary": _normalize_landing_rollback_summary(result.get("rollback_summary")),
        "phases": _normalize_landing_create_phases(result.get("phases")),
        "safety_boundary": _normalize_text_list(result.get("safety_boundary"))[:10],
    }
    return sanitize_value(normalized)


def _normalize_landing_xray_inbounds(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    inbounds: list[dict[str, Any]] = []
    for item in value[:10]:
        if not isinstance(item, dict):
            continue
        inbounds.append(
            {
                "tag": _safe_result_text(item.get("tag")),
                "listen": _safe_result_text(item.get("listen")),
                "port": _safe_result_int(item.get("port")),
                "protocol": _safe_result_text(item.get("protocol")),
            }
        )
    return inbounds


def _normalize_landing_listen_attempts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    attempts: list[dict[str, Any]] = []
    for item in value[:10]:
        if not isinstance(item, dict):
            continue
        attempts.append(
            {
                "attempt": _safe_result_int(item.get("attempt")),
                "xray_service_active": _safe_result_text(item.get("xray_service_active")),
                "port_listening": item.get("port_listening") is True,
                "ss_matching_lines": _normalize_text_list(item.get("ss_matching_lines"))[:5],
            }
        )
    return attempts


def _normalize_landing_rollback_summary(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    summary: list[dict[str, Any]] = []
    for item in value[:20]:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {
            "action": _safe_result_text(item.get("action")),
            "target": _safe_result_text(item.get("target")),
            "ok": item.get("ok") is True,
        }
        if error := _safe_result_text(item.get("error")):
            entry["error"] = error
        summary.append(entry)
    return summary


def _normalize_landing_create_phases(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    phases: list[dict[str, Any]] = []
    for item in value[:20]:
        if not isinstance(item, dict):
            continue
        phases.append(
            {
                "name": _safe_result_text(item.get("name")),
                "status": _safe_result_text(item.get("status")),
                "summary": _safe_result_text(item.get("summary")),
            }
        )
    return phases


def normalize_remote_cleanup_result(command_type: str, result: dict[str, Any]) -> dict[str, Any]:
    status = _safe_result_text(result.get("status")) or "failed"
    cleanup_type = _safe_result_text(result.get("cleanup_type")) or command_type
    summary = _safe_result_text(result.get("summary")) or "Protected remote cleanup returned a result."
    plans_count = _safe_result_int(result.get("plans_count"))
    if plans_count is None:
        plans_count = len(result.get("cleanup_items", [])) if isinstance(result.get("cleanup_items"), list) else None
    worker_self_cleanup = _normalize_remote_cleanup_worker(result.get("worker_self_cleanup"))
    normalized: dict[str, Any] = {
        "cleanup_type": cleanup_type,
        "status": status,
        "summary": summary,
        "remote_cleanup_performed": result.get("remote_cleanup_performed") is True,
        "system_record_delete_after_success": result.get("system_record_delete_after_success") is True,
        "worker_version": _safe_result_text(result.get("worker_version")),
        "hostname": _safe_result_text(result.get("hostname")),
        "role": _safe_result_text(result.get("role")),
        "interface_name": _safe_result_text(result.get("interface_name")),
        "plans_count": plans_count,
        "cleanup_items": _normalize_remote_cleanup_items(result.get("cleanup_items")),
        "worker_self_cleanup": worker_self_cleanup,
        "safety_boundary": _normalize_text_list(result.get("safety_boundary"))[:10],
    }
    if command_type in REMOTE_CLEANUP_SERVER_COMMAND_TYPES:
        worker_cleanup_status = _remote_cleanup_worker_status(worker_self_cleanup)
        normalized["worker_cleanup_status"] = worker_cleanup_status
        normalized["worker_self_cleanup_status"] = worker_cleanup_status
    if redacted_error := _safe_result_text(result.get("redacted_error")):
        normalized["redacted_error"] = redacted_error
    return sanitize_value(normalized)


def _normalize_remote_cleanup_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    items: list[dict[str, Any]] = []
    for item in value[:MAX_TRANSIT_PREFLIGHT_CHECKS]:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "type": _safe_result_text(item.get("type")),
                "id": _safe_result_text(item.get("id")),
                "service_name": _safe_result_text(item.get("service_name")),
                "port": _safe_result_int(item.get("port")),
                "status": _safe_result_text(item.get("status")),
                "service_removed": item.get("service_removed") is True,
                "port_stopped": item.get("port_stopped") is True,
                "config_removed": item.get("config_removed") is True,
                "detail": _safe_result_text(item.get("detail")),
            }
        )
    return items


def _normalize_remote_cleanup_worker(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "requested": value.get("requested") is True,
        "scheduled": value.get("scheduled") is True,
        "service_name": _safe_result_text(value.get("service_name")),
        "binary_cleanup_scheduled": value.get("binary_cleanup_scheduled") is True,
        "config_cleanup_scheduled": value.get("config_cleanup_scheduled") is True,
        "delay_seconds": _safe_result_int(value.get("delay_seconds")),
        "detail": _safe_result_text(value.get("detail")),
    }


def _remote_cleanup_worker_status(worker_self_cleanup: dict[str, Any]) -> str:
    if not worker_self_cleanup:
        return "missing"
    if worker_self_cleanup.get("scheduled") is True:
        return "scheduled"
    if worker_self_cleanup.get("requested") is True:
        return "requested"
    return "missing"


def _normalize_transit_route_create_diagnostics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    diagnostics: dict[str, Any] = {}
    for key in ("systemctl_is_active", "systemctl_status", "journal", "listen_socket"):
        item = value.get(key)
        if isinstance(item, dict):
            diagnostics[key] = {
                "status": _safe_result_text(item.get("status")),
                "detail": _safe_result_text(item.get("detail")),
                "error": _safe_result_text(item.get("error")),
            }
    service_file = value.get("service_file")
    if isinstance(service_file, dict):
        diagnostics["service_file"] = {
            "exists": service_file.get("exists") is True,
            "size_bytes": _safe_result_int(service_file.get("size_bytes")),
            "contains_fixed_exec": service_file.get("contains_fixed_exec") is True,
            "contains_approved_name": service_file.get("contains_approved_name") is True,
            "error": _safe_result_text(service_file.get("error")),
        }
    return diagnostics


def _normalize_transit_route_listen_attempts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    attempts: list[dict[str, Any]] = []
    for item in value[:10]:
        if not isinstance(item, dict):
            continue
        attempts.append(
            {
                "attempt": _safe_result_int(item.get("attempt")),
                "service_active": _safe_result_text(item.get("service_active")),
                "listener_detected": item.get("listener_detected") is True,
            }
        )
    return attempts


def _normalize_transit_route_listen_attempt(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "attempt": _safe_result_int(value.get("attempt")),
        "service_active": _safe_result_text(value.get("service_active")),
        "listener_detected": value.get("listener_detected") is True,
    }


def _normalize_transit_route_create_checks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    checks: list[dict[str, Any]] = []
    for index, item in enumerate(value[:MAX_TRANSIT_PREFLIGHT_CHECKS]):
        if not isinstance(item, dict):
            checks.append(
                {
                    "name": f"check_{index + 1}",
                    "passed": False,
                    "detail": _safe_result_text(item) or "Malformed check item.",
                }
            )
            continue
        passed = item.get("passed")
        if not isinstance(passed, bool):
            status = _safe_result_text(item.get("status"))
            passed = status in {"passed", "ok", "success"}
        check = {
            "name": _safe_result_text(item.get("name") or item.get("label") or item.get("id"))
            or f"check_{index + 1}",
            "passed": passed,
        }
        detail = _safe_result_text(item.get("detail") or item.get("summary") or item.get("message"))
        if detail:
            check["detail"] = detail
        checks.append(check)
    return checks


def _normalize_transit_preflight_checks(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    checks: list[dict[str, Any]] = []
    for index, item in enumerate(value[:MAX_TRANSIT_PREFLIGHT_CHECKS]):
        if not isinstance(item, dict):
            checks.append(
                {
                    "id": f"check_{index + 1}",
                    "label": f"Check {index + 1}",
                    "status": "unknown",
                    "passed": False,
                    "detail": _safe_result_text(item) or "Malformed check item.",
                }
            )
            continue
        passed = item.get("passed")
        status = _safe_result_text(item.get("status"))
        if not isinstance(passed, bool):
            passed = status in {"passed", "ok", "success"}
        checks.append(
            {
                "id": _safe_result_text(item.get("id")) or f"check_{index + 1}",
                "label": _safe_result_text(item.get("label")) or f"Check {index + 1}",
                "status": status or ("passed" if passed else "failed"),
                "passed": passed,
                "detail": _safe_result_text(item.get("detail") or item.get("message") or item.get("summary")),
                "category": _safe_result_text(item.get("category")),
                "evidence_summary": _safe_result_text(item.get("evidence_summary")),
                "next_action": _safe_result_text(item.get("next_action")),
                "sensitive_output_redacted": True,
            }
        )
    return checks


def _safe_result_text(value: Any) -> str | None:
    if value is None:
        return None
    sanitized = sanitize_value(str(value))
    if not isinstance(sanitized, str):
        return "[redacted]"
    return sanitized


def _safe_result_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.isdigit():
            return int(cleaned)
    return None


def _normalize_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value[:MAX_TRANSIT_PREFLIGHT_CHECKS]:
        text = _safe_result_text(item)
        if text:
            result.append(text)
    return result


def create_worker_command(
    db: Session,
    worker: Worker,
    command_type: str,
    payload: dict[str, Any] | None = None,
) -> WorkerCommand:
    command = WorkerCommand(
        worker_id=worker.id,
        server_type=worker.role,
        server_id=worker.server_id,
        command_type=command_type,
        payload_json=sanitize_command_payload(payload),
        status="pending",
        attempts=0,
    )
    db.add(command)
    db.flush()
    return command


def claim_next_worker_command(db: Session, worker: Worker) -> WorkerCommand | None:
    current_time = now_utc()
    command = db.scalar(
        select(WorkerCommand)
        .where(WorkerCommand.worker_id == worker.id)
        .where(
            or_(
                WorkerCommand.status == "pending",
                WorkerCommand.status == "claimed",
                WorkerCommand.status == "running",
            )
        )
        .where(or_(WorkerCommand.lease_until.is_(None), WorkerCommand.lease_until <= current_time))
        .order_by(WorkerCommand.created_at.asc())
        .with_for_update(skip_locked=True)
    )
    if not command:
        return None

    command.status = "running"
    command.claimed_at = command.claimed_at or current_time
    command.lease_until = current_time + timedelta(seconds=COMMAND_LEASE_SECONDS)
    command.attempts = (command.attempts or 0) + 1
    db.add(command)
    db.flush()
    return command


def complete_worker_command(
    db: Session,
    command: WorkerCommand,
    result: dict[str, Any] | None,
) -> WorkerCommand:
    command.status = "succeeded"
    command.result_json = sanitize_value(result or {})
    command.error_message = None
    command.completed_at = now_utc()
    command.lease_until = None
    db.add(command)
    db.flush()
    return command


def fail_worker_command(
    db: Session,
    command: WorkerCommand,
    error_message: str,
    result: dict[str, Any] | None = None,
) -> WorkerCommand:
    command.status = "failed"
    command.error_message = sanitize_error_message(error_message)
    command.result_json = sanitize_value(result or {}) if result else None
    command.completed_at = now_utc()
    command.lease_until = None
    db.add(command)
    db.flush()
    return command


def sanitize_error_message(error_message: str) -> str:
    sanitized = sanitize_value(error_message.strip())
    if not isinstance(sanitized, str):
        return "[redacted]"
    return sanitized[:1000]


def result_summary(command: WorkerCommand) -> str | None:
    if command.status == "failed":
        return command.error_message
    result = command.result_json or {}
    if not isinstance(result, dict) or not result:
        return None
    if command.command_type == "ping":
        pong = result.get("pong")
        hostname = result.get("hostname")
        version = result.get("worker_version")
        return f"pong={pong} hostname={hostname or '-'} version={version or '-'}"
    if command.command_type == "collect_status":
        hostname = result.get("hostname")
        os_name = result.get("os")
        uptime = result.get("uptime_seconds")
        return f"hostname={hostname or '-'} os={os_name or '-'} uptime={uptime or '-'}"
    if command.command_type == "service_status":
        services = result.get("services")
        if isinstance(services, dict):
            return ", ".join(f"{key}={value}" for key, value in list(services.items())[:6])
    if command.command_type == "landing_preflight":
        warnings = result.get("warnings")
        warning_count = len(warnings) if isinstance(warnings, list) else 0
        ports = result.get("ports")
        listening_count = "-"
        important_ports = "-"
        if isinstance(ports, dict):
            listening_count = str(ports.get("listening_count", "-"))
            checks = ports.get("important_ports")
            if isinstance(checks, dict):
                important_ports = ",".join(
                    f"{port}:{check.get('status', '-')}"
                    for port, check in checks.items()
                    if isinstance(check, dict)
                )
        return f"landing_preflight listening_count={listening_count} important_ports={important_ports} warnings={warning_count}"
    if command.command_type == "bbr_enable_dry_run":
        status = result.get("status") or "-"
        bbr = result.get("bbr")
        recommendation = "-"
        if isinstance(bbr, dict):
            recommendation = bbr.get("recommendation") or "-"
        blocked_reasons = result.get("blocked_reasons")
        blocked_count = len(blocked_reasons) if isinstance(blocked_reasons, list) else 0
        return f"bbr_enable_dry_run status={status} recommendation={recommendation} blocked={blocked_count}"
    if command.command_type == "landing_node_create":
        node_id = result.get("node_id") or "-"
        listen_port = result.get("listen_port") or "-"
        masked_link = result.get("masked_share_link") or "-"
        return f"landing_node_create node_id={node_id} listen_port={listen_port} share_link={masked_link}"
    if command.command_type == "transit_readonly_preflight":
        status = result.get("status") or "-"
        checks = result.get("checks")
        check_count = len(checks) if isinstance(checks, list) else 0
        summary = result.get("summary") or "remote readonly preflight returned"
        return f"transit_readonly_preflight status={status} checks={check_count} summary={summary}"
    if command.command_type == "transit_route_create":
        mode = result.get("execution_mode") or "-"
        status = result.get("status") or "-"
        listen_port = result.get("planned_listen_port") or "-"
        target_port = result.get("landing_target_port") or "-"
        return f"transit_route_create mode={mode} status={status} listen_port={listen_port} target_port={target_port}"
    if command.command_type in REMOTE_CLEANUP_COMMAND_TYPES:
        cleanup_type = result.get("cleanup_type") or command.command_type
        status = result.get("status") or "-"
        plans_count = result.get("plans_count")
        return f"{cleanup_type} status={status} cleanup_items={plans_count or '-'}"
    return "命令已返回脱敏结果。"


def serialize_worker_command(
    command: WorkerCommand,
    include_payload: bool = False,
    worker: Worker | None = None,
) -> dict[str, Any]:
    data = {
        "id": command.id,
        "worker_id": command.worker_id,
        "target_worker_id": command.worker_id,
        "target_worker_version": worker.worker_version if worker else None,
        "server_type": command.server_type,
        "server_id": command.server_id,
        "command_type": command.command_type,
        "status": command.status,
        "lease_until": command.lease_until.isoformat() if command.lease_until else None,
        "claimed_at": command.claimed_at.isoformat() if command.claimed_at else None,
        "completed_at": command.completed_at.isoformat() if command.completed_at else None,
        "result_json": sanitize_value(command.result_json or {}),
        "result_summary": result_summary(command),
        "error_message": command.error_message,
        "attempts": command.attempts,
        "created_at": command.created_at.isoformat() if command.created_at else None,
        "updated_at": command.updated_at.isoformat() if command.updated_at else None,
    }
    if include_payload:
        data["payload"] = sanitize_value(command.payload_json or {})
    return data


def serialize_worker_command_for_worker(command: WorkerCommand) -> dict[str, Any]:
    return {
        "id": command.id,
        "command_type": command.command_type,
        "payload": sanitize_value(command.payload_json or {}),
    }
