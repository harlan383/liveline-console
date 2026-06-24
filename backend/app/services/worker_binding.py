from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_token, new_token
from app.models.transit_resource import TransitResource
from app.models.vps_server import VpsServer
from app.models.worker import Worker, WorkerToken
from app.schemas.common import error_response
from app.schemas.workers import HEARTBEAT_STALE_THRESHOLD_SECONDS, OFFLINE_THRESHOLD_SECONDS

WORKER_PENDING_STATUS = "pending_worker"
WORKER_ONLINE_STATUS = "worker_online"
WORKER_OFFLINE_STATUS = "worker_offline"
LOCAL_WORKER_INSTALL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class WorkerPublicUrlError(ValueError):
    pass


def now_utc() -> datetime:
    return datetime.now(UTC)


def mask_token(token: str) -> str:
    if len(token) <= 16:
        return "[redacted]"
    return f"{token[:6]}...{token[-6:]}"


def worker_public_base_url() -> str:
    settings = get_settings()
    raw_value = (settings.worker_public_base_url or settings.public_console_url or "").strip().rstrip("/")
    if not raw_value:
        raise WorkerPublicUrlError("WORKER_PUBLIC_URL_MISSING")

    parsed = urlparse(raw_value)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise WorkerPublicUrlError("WORKER_PUBLIC_URL_INVALID")
    if hostname in LOCAL_WORKER_INSTALL_HOSTS or hostname.startswith("127."):
        raise WorkerPublicUrlError("WORKER_PUBLIC_URL_LOCALHOST")
    return raw_value


def worker_public_url_error_response(exc: ValueError):
    code = str(exc)
    if code == "WORKER_PUBLIC_URL_MISSING":
        return error_response(
            400,
            "WORKER_PUBLIC_CONSOLE_URL_REQUIRED",
            "主控公网地址未配置，远程 VPS 无法通过 localhost 访问安装脚本。",
        )
    if code == "WORKER_PUBLIC_URL_LOCALHOST":
        return error_response(
            400,
            "WORKER_PUBLIC_CONSOLE_URL_LOCALHOST_FORBIDDEN",
            "PUBLIC_CONSOLE_URL / WORKER_PUBLIC_BASE_URL 不能使用 localhost、127.0.0.1 或 0.0.0.0。",
        )
    return error_response(
        400,
        "WORKER_PUBLIC_CONSOLE_URL_INVALID",
        "PUBLIC_CONSOLE_URL / WORKER_PUBLIC_BASE_URL 必须是可从远程 VPS 访问的 http(s) URL。",
    )


def build_worker_install_command(raw_token: str, role: str, base_url: str | None = None) -> str:
    console_url = base_url or worker_public_base_url()
    setup_url = console_url + f"/worker_setup_script/{raw_token}"
    return f"curl -s {setup_url} | bash -s eth0 {role}"


def create_bound_worker_token(
    db: Session,
    *,
    role: str,
    name: str | None,
    server_id: str | None,
    admin_id: str | None,
    expires_in_minutes: int,
) -> tuple[WorkerToken, str, str]:
    base_url = worker_public_base_url()
    raw_token = new_token()
    token = WorkerToken(
        token_hash=hash_token(raw_token),
        role=role,
        status="active",
        name=name,
        expires_at=now_utc() + timedelta(minutes=expires_in_minutes),
        created_by=admin_id,
        server_id=server_id,
    )
    db.add(token)
    db.flush()
    return token, raw_token, build_worker_install_command(raw_token, role, base_url)


def serialize_worker_token_bootstrap(token: WorkerToken, raw_token: str, install_command: str) -> dict:
    return {
        "token_id": token.id,
        "role": token.role,
        "expires_at": token.expires_at.isoformat() if token.expires_at else None,
        "install_command": install_command,
        "masked_token": mask_token(raw_token),
        "status": token.status,
        "server_id": token.server_id,
    }


def worker_runtime_status(worker: Worker, current_time: datetime | None = None) -> str:
    if not worker.last_heartbeat_at:
        return "unknown"
    if worker.last_heartbeat_at <= (current_time or now_utc()) - timedelta(seconds=OFFLINE_THRESHOLD_SECONDS):
        return "offline"
    return "online"


def worker_heartbeat_age_seconds(worker: Worker | None, current_time: datetime | None = None) -> int | None:
    if not worker or not worker.last_heartbeat_at:
        return None
    reference_time = current_time or now_utc()
    heartbeat_at = worker.last_heartbeat_at
    if heartbeat_at.tzinfo is None and reference_time.tzinfo is not None:
        heartbeat_at = heartbeat_at.replace(tzinfo=reference_time.tzinfo)
    age_seconds = int((reference_time - heartbeat_at).total_seconds())
    return max(age_seconds, 0)


def worker_heartbeat_status(worker: Worker | None, current_time: datetime | None = None) -> str:
    if not worker:
        return "unknown"
    if worker.status == "deleted":
        return "deleted"
    age_seconds = worker_heartbeat_age_seconds(worker, current_time=current_time)
    if age_seconds is None:
        return "unknown"
    if worker.status == "online" and age_seconds <= HEARTBEAT_STALE_THRESHOLD_SECONDS:
        return "online"
    if age_seconds > HEARTBEAT_STALE_THRESHOLD_SECONDS or worker.status == "offline":
        return "stale"
    return "unknown"


def worker_heartbeat_summary_fields(worker: Worker | None, current_time: datetime | None = None) -> dict:
    if not worker:
        return {
            "worker_heartbeat_status": None,
            "worker_heartbeat_age_seconds": None,
            "worker_is_heartbeat_stale": False,
            "worker_display_status": None,
        }
    heartbeat_status = worker_heartbeat_status(worker, current_time=current_time)
    return {
        "worker_heartbeat_status": heartbeat_status,
        "worker_heartbeat_age_seconds": worker_heartbeat_age_seconds(worker, current_time=current_time),
        "worker_is_heartbeat_stale": heartbeat_status == "stale",
        "worker_display_status": heartbeat_status,
    }


def latest_worker_for_server(db: Session, *, role: str, server_id: str) -> Worker | None:
    return db.scalar(
        select(Worker)
        .where(Worker.role == role, Worker.server_id == server_id)
        .order_by(Worker.last_heartbeat_at.desc().nullslast(), Worker.created_at.desc())
        .limit(1)
    )


def latest_workers_by_server(db: Session, *, role: str, server_ids: list[str]) -> dict[str, Worker]:
    if not server_ids:
        return {}
    workers = db.scalars(select(Worker).where(Worker.role == role, Worker.server_id.in_(server_ids))).all()
    latest: dict[str, Worker] = {}
    for worker in workers:
        if not worker.server_id:
            continue
        current = latest.get(worker.server_id)
        current_time = current.last_heartbeat_at or current.created_at if current else None
        worker_time = worker.last_heartbeat_at or worker.created_at
        if current is None or (worker_time and current_time and worker_time > current_time) or current_time is None:
            latest[worker.server_id] = worker
    return latest


def worker_summary_fields(worker: Worker | None) -> dict:
    status = worker_runtime_status(worker) if worker else None
    heartbeat_fields = worker_heartbeat_summary_fields(worker)
    return {
        "worker_id": worker.id if worker else None,
        "worker_status": status,
        "worker_role": worker.role if worker else None,
        "worker_hostname": worker.hostname if worker else None,
        "worker_interface_name": worker.interface_name if worker else None,
        "worker_version": worker.worker_version if worker else None,
        "worker_last_heartbeat_at": worker.last_heartbeat_at.isoformat() if worker and worker.last_heartbeat_at else None,
        **heartbeat_fields,
        "worker_online": status == "online" and heartbeat_fields["worker_heartbeat_status"] == "online",
    }


def vps_display_status(vps: VpsServer, worker: Worker | None) -> str:
    if worker:
        heartbeat_status = worker_heartbeat_status(worker)
        if heartbeat_status == "online":
            return "online"
        if heartbeat_status in {"stale", "deleted"}:
            return heartbeat_status
    if vps.status == WORKER_PENDING_STATUS:
        return WORKER_PENDING_STATUS
    if vps.status == WORKER_ONLINE_STATUS:
        return "online"
    if vps.status == WORKER_OFFLINE_STATUS:
        return "offline"
    if vps.last_ssh_status in {"online", "offline"}:
        return vps.last_ssh_status
    return "unchecked"


def transit_display_status(resource: TransitResource, worker: Worker | None) -> str:
    if worker:
        heartbeat_status = worker_heartbeat_status(worker)
        if heartbeat_status == "online":
            return "online"
        if heartbeat_status in {"stale", "deleted"}:
            return heartbeat_status
    if resource.status == WORKER_PENDING_STATUS:
        return WORKER_PENDING_STATUS
    if resource.status == WORKER_ONLINE_STATUS:
        return "online"
    if resource.status == WORKER_OFFLINE_STATUS:
        return "offline"
    if resource.status == "disabled":
        return "disabled"
    return "unchecked"


def connection_mode_for_vps(vps: VpsServer, worker: Worker | None) -> str:
    if worker or vps.status in {WORKER_PENDING_STATUS, WORKER_ONLINE_STATUS, WORKER_OFFLINE_STATUS}:
        return "worker"
    if vps.ssh_username:
        return "ssh"
    return "unknown"


def connection_mode_for_transit(resource: TransitResource, worker: Worker | None) -> str:
    if worker or resource.status in {WORKER_PENDING_STATUS, WORKER_ONLINE_STATUS, WORKER_OFFLINE_STATUS}:
        return "worker"
    if resource.has_ssh:
        return "ssh"
    return "unknown"


def validate_worker_token_binding_target(db: Session, token: WorkerToken) -> tuple[str, str] | None:
    if not token.server_id:
        return None
    if token.role == "landing":
        vps = db.get(VpsServer, token.server_id)
        if not vps or vps.status == "deleted":
            return ("WORKER_SERVER_BINDING_NOT_FOUND", "Worker token 绑定的落地服务器记录不存在。")
        return None
    if token.role == "transit":
        resource = db.get(TransitResource, token.server_id)
        if not resource or resource.deleted_at is not None:
            return ("WORKER_SERVER_BINDING_NOT_FOUND", "Worker token 绑定的中转服务器记录不存在。")
        return None
    return ("WORKER_ROLE_INVALID", "Worker role 不合法。")


def sync_worker_bound_resource_status(db: Session, worker: Worker) -> None:
    if not worker.server_id:
        return
    status = worker_runtime_status(worker)
    next_status = WORKER_ONLINE_STATUS if status == "online" else WORKER_OFFLINE_STATUS
    if worker.role == "landing":
        vps = db.get(VpsServer, worker.server_id)
        if vps and vps.status != "deleted":
            vps.status = next_status
            db.add(vps)
        return
    if worker.role == "transit":
        resource = db.get(TransitResource, worker.server_id)
        if resource and resource.deleted_at is None:
            resource.status = next_status
            db.add(resource)


def try_bind_worker_by_public_ip(db: Session, worker: Worker) -> bool:
    if worker.server_id or not worker.public_ip:
        return False
    public_ip = worker.public_ip.strip()
    if not public_ip:
        return False

    if worker.role == "landing":
        candidates = db.scalars(
            select(VpsServer).where(VpsServer.ip == public_ip, VpsServer.status != "deleted")
        ).all()
        if len(candidates) == 1:
            worker.server_id = candidates[0].id
            db.add(worker)
            sync_worker_bound_resource_status(db, worker)
            return True
        return False

    if worker.role == "transit":
        candidates = db.scalars(
            select(TransitResource).where(
                TransitResource.deleted_at.is_(None),
                or_(TransitResource.entry_host == public_ip, TransitResource.ssh_host == public_ip),
            )
        ).all()
        if len(candidates) == 1:
            worker.server_id = candidates[0].id
            db.add(worker)
            sync_worker_bound_resource_status(db, worker)
            return True
    return False
