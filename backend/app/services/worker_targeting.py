import re
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.worker import Worker
from app.services.worker_binding import worker_runtime_status

MIN_COMMAND_CHANNEL_VERSION = "0.1.1-stage-3.3.28"
MIN_COMMAND_CHANNEL_VERSION_KEY = (0, 1, 1, 3, 3, 28)
MIN_LANDING_PREFLIGHT_VERSION = "0.1.3-stage-3.3.33"
MIN_LANDING_PREFLIGHT_VERSION_KEY = (0, 1, 3, 3, 3, 33)
MIN_LANDING_NODE_CREATE_VERSION = "0.1.5-stage-3.3.37"
MIN_LANDING_NODE_CREATE_VERSION_KEY = (0, 1, 5, 3, 3, 37)
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-stage-(\d+)\.(\d+)\.(\d+))?$")


@dataclass(frozen=True)
class WorkerTargetResolution:
    worker: Worker
    changed: bool
    requested_worker_id: str | None


class WorkerTargetError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def parse_worker_version(version: str | None) -> tuple[int, int, int, int, int, int] | None:
    if not version:
        return None
    match = VERSION_RE.match(version.strip())
    if not match:
        return None
    major, minor, patch, stage_major, stage_minor, stage_patch = match.groups()
    stage_values = (stage_major, stage_minor, stage_patch)
    if any(value is None for value in stage_values):
        return (int(major), int(minor), int(patch), 0, 0, 0)
    return (
        int(major),
        int(minor),
        int(patch),
        int(stage_major or 0),
        int(stage_minor or 0),
        int(stage_patch or 0),
    )


def worker_supports_min_version(worker: Worker | None, min_version_key: tuple[int, int, int, int, int, int]) -> bool:
    if not worker:
        return False
    parsed = parse_worker_version(worker.worker_version)
    if not parsed:
        return False
    return parsed >= min_version_key


def minimum_worker_version_for_command(command_type: str | None) -> str:
    if command_type == "landing_node_create":
        return MIN_LANDING_NODE_CREATE_VERSION
    if command_type == "landing_preflight":
        return MIN_LANDING_PREFLIGHT_VERSION
    return MIN_COMMAND_CHANNEL_VERSION


def minimum_worker_version_key_for_command(command_type: str | None) -> tuple[int, int, int, int, int, int]:
    if command_type == "landing_node_create":
        return MIN_LANDING_NODE_CREATE_VERSION_KEY
    if command_type == "landing_preflight":
        return MIN_LANDING_PREFLIGHT_VERSION_KEY
    return MIN_COMMAND_CHANNEL_VERSION_KEY


def worker_supports_command_channel(worker: Worker | None, command_type: str | None = None) -> bool:
    return worker_supports_min_version(worker, minimum_worker_version_key_for_command(command_type))


def worker_sort_key(worker: Worker) -> tuple[datetime, datetime, datetime]:
    epoch = datetime.min.replace(tzinfo=UTC)
    return (
        worker.last_heartbeat_at or epoch,
        worker.registered_at or epoch,
        worker.created_at or epoch,
    )


def resolve_command_target_worker(
    db: Session,
    *,
    server_type: str | None,
    server_id: str | None,
    role: str | None = None,
    requested_worker_id: str | None = None,
    command_type: str | None = None,
) -> WorkerTargetResolution:
    target_role = (role or server_type or "").strip()
    if target_role not in {"landing", "transit"}:
        raise WorkerTargetError("WORKER_NOT_BOUND", "Worker 未绑定到可识别的服务器角色。")
    if not server_id:
        raise WorkerTargetError("WORKER_NOT_BOUND", "Worker 未绑定到服务器记录，不能创建检查命令。")

    workers = db.scalars(
        select(Worker)
        .where(Worker.server_id == server_id)
        .where(Worker.role == target_role)
    ).all()
    if not workers:
        raise WorkerTargetError("WORKER_NOT_BOUND", "该服务器没有绑定 Worker，不能创建检查命令。")

    online_workers = [
        worker
        for worker in workers
        if worker.status == "online" and worker_runtime_status(worker) == "online"
    ]
    if not online_workers:
        raise WorkerTargetError("WORKER_OFFLINE", "当前没有在线 Worker，不能创建检查命令。")

    command_capable_workers = [
        worker for worker in online_workers if worker_supports_command_channel(worker, command_type)
    ]
    if not command_capable_workers:
        raise WorkerTargetError(
            "WORKER_COMMAND_UNSUPPORTED",
            "当前在线 Worker 不支持检查命令，请重新安装或升级 liveline-worker。",
        )

    target = sorted(command_capable_workers, key=worker_sort_key, reverse=True)[0]
    return WorkerTargetResolution(
        worker=target,
        changed=bool(requested_worker_id and target.id != requested_worker_id),
        requested_worker_id=requested_worker_id,
    )
