from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.task_log import TaskLog

SENSITIVE_MARKERS = (
    "BEGIN OPENSSH PRIVATE KEY",
    "BEGIN RSA PRIVATE KEY",
    "BEGIN EC PRIVATE KEY",
    "BEGIN DSA PRIVATE KEY",
    "PRIVATE KEY",
    "PRIVATEKEY",
    "PASSPHRASE",
    "VLESS://",
    "VMESS://",
    "TROJAN://",
    "DATABASE_URL",
    "POSTGRESQL://",
    "POSTGRESQL+PSYCOPG://",
    "REDIS://",
    "COOKIE",
    "SESSION_SECRET",
)


def sanitize_log_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value
    upper = text.upper()
    if any(marker in upper for marker in SENSITIVE_MARKERS):
        return "[REDACTED]"
    if len(text) > 2000:
        return text[:2000] + "...[truncated]"
    return text


def add_task_log(
    db: Session,
    task_id: str,
    *,
    level: str,
    step: str,
    message: str,
    raw_output: str | None = None,
) -> None:
    db.add(
        TaskLog(
            task_id=task_id,
            level=level,
            step=step,
            message=sanitize_log_text(message) or "",
            raw_output=sanitize_log_text(raw_output),
        )
    )


def update_task(
    db: Session,
    task: Task,
    *,
    status: str | None = None,
    step: str | None = None,
    progress: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    result_data: dict[str, Any] | None = None,
    finish: bool = False,
) -> None:
    if status is not None:
        task.status = status
    if step is not None:
        task.current_step = step
    if progress is not None:
        task.progress = progress
    if error_code is not None:
        task.error_code = error_code
    if error_message is not None:
        task.error_message = sanitize_log_text(error_message)
    if result_data is not None:
        task.result_data = result_data
    if task.started_at is None and status == "running":
        task.started_at = datetime.now(UTC)
    if finish:
        task.finished_at = datetime.now(UTC)
    db.add(task)
