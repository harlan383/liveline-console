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
                result[key_text] = "[redacted]"
                continue
            result[key_text] = sanitize_value(item)
        return result
    if isinstance(value, list):
        return [sanitize_value(item) for item in value[:50]]
    if isinstance(value, str):
        lowered_value = value.lower()
        if any(marker in lowered_value for marker in ("vless://", "vmess://", "ss://")):
            return "[redacted-link]"
        if len(value) > 1000:
            return value[:1000] + "...[truncated]"
    return value


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
