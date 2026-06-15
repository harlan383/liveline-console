import shlex
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import FileResponse, PlainTextResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.core.config import get_settings
from app.core.security import hash_token, new_token, token_matches
from app.db.session import get_db
from app.models.worker import Worker, WorkerToken
from app.schemas.common import error_response, success_response
from app.schemas.workers import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    OFFLINE_THRESHOLD_SECONDS,
    WorkerHeartbeatRequest,
    WorkerRegisterRequest,
    WorkerTokenCreate,
)
from app.services.auth_service import record_audit

router = APIRouter()
setup_router = APIRouter()

SENSITIVE_METADATA_MARKERS = (
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
)
LOCAL_WORKER_INSTALL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def now_utc() -> datetime:
    return datetime.now(UTC)


def mask_token(token: str) -> str:
    if len(token) <= 16:
        return "[redacted]"
    return f"{token[:6]}...{token[-6:]}"


def clean_token(raw_token: str | None) -> str | None:
    if raw_token is None:
        return None
    cleaned = raw_token.strip()
    return cleaned or None


def token_is_expired(token: WorkerToken, current_time: datetime | None = None) -> bool:
    return token.expires_at <= (current_time or now_utc())


def worker_runtime_status(worker: Worker, current_time: datetime | None = None) -> str:
    if not worker.last_heartbeat_at:
        return "unknown"
    if worker.last_heartbeat_at <= (current_time or now_utc()) - timedelta(seconds=OFFLINE_THRESHOLD_SECONDS):
        return "offline"
    return "online"


def redact_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered_key = str(key).lower()
            if any(marker in lowered_key for marker in SENSITIVE_METADATA_MARKERS):
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = redact_metadata(item)
        return redacted
    if isinstance(value, list):
        return [redact_metadata(item) for item in value[:20]]
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...[truncated]"
    return value


def metadata_summary(worker: Worker) -> dict[str, Any]:
    metadata = redact_metadata(worker.metadata_json or {})
    if not isinstance(metadata, dict):
        return {}
    latest_status = metadata.get("latest_status")
    if isinstance(latest_status, dict):
        return {
            "received_at": metadata.get("received_at"),
            "uptime_seconds": latest_status.get("uptime_seconds"),
            "os": latest_status.get("os"),
            "kernel": latest_status.get("kernel"),
            "cpu": latest_status.get("cpu"),
            "memory": latest_status.get("memory"),
            "disk": latest_status.get("disk"),
            "services": latest_status.get("services"),
        }
    return metadata


def serialize_worker(worker: Worker) -> dict:
    status = worker_runtime_status(worker)
    return {
        "id": worker.id,
        "server_id": worker.server_id,
        "role": worker.role,
        "name": worker.name,
        "public_ip": worker.public_ip,
        "hostname": worker.hostname,
        "interface_name": worker.interface_name,
        "worker_version": worker.worker_version,
        "status": status,
        "last_heartbeat_at": worker.last_heartbeat_at.isoformat() if worker.last_heartbeat_at else None,
        "registered_at": worker.registered_at.isoformat() if worker.registered_at else None,
        "created_at": worker.created_at.isoformat() if worker.created_at else None,
        "updated_at": worker.updated_at.isoformat() if worker.updated_at else None,
        "metadata_summary": metadata_summary(worker),
    }


def find_token(db: Session, raw_token: str) -> WorkerToken | None:
    return db.scalar(select(WorkerToken).where(WorkerToken.token_hash == hash_token(raw_token)))


def worker_binary_candidates() -> list[Path]:
    return [
        Path("/app/worker-binaries/liveline-worker-linux-amd64"),
        Path(__file__).resolve().parents[3] / "worker-binaries" / "liveline-worker-linux-amd64",
        Path(__file__).resolve().parents[4] / "worker" / "bin" / "liveline-worker-linux-amd64",
    ]


def worker_binary_path() -> Path | None:
    for candidate in worker_binary_candidates():
        if candidate.is_file():
            return candidate
    return None


def worker_public_base_url() -> str:
    settings = get_settings()
    raw_value = (settings.worker_public_base_url or settings.public_console_url or "").strip().rstrip("/")
    if not raw_value:
        raise ValueError("WORKER_PUBLIC_URL_MISSING")

    parsed = urlparse(raw_value)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("WORKER_PUBLIC_URL_INVALID")
    if hostname in LOCAL_WORKER_INSTALL_HOSTS or hostname.startswith("127."):
        raise ValueError("WORKER_PUBLIC_URL_LOCALHOST")
    return raw_value


def worker_public_url_error(exc: ValueError):
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


def bash_quote(value: str) -> str:
    return shlex.quote(value)


def install_script_for_role(role: str, raw_token: str, console_url: str, binary_url: str) -> str:
    return f"""#!/usr/bin/env bash
set -euo pipefail

INTERFACE_NAME="${{1:-}}"
ROLE="${{2:-}}"
EXPECTED_ROLE={bash_quote(role)}
CONSOLE_URL={bash_quote(console_url)}
BINARY_URL={bash_quote(binary_url)}
TOKEN={bash_quote(raw_token)}
CONFIG_DIR="/etc/liveline-worker"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
SERVICE_FILE="/etc/systemd/system/liveline-worker.service"
BINARY_PATH="/usr/local/bin/liveline-worker"

if [[ -z "$INTERFACE_NAME" ]]; then
  echo "LiveLine Worker install: missing interface_name, for example eth0, ens3, ens5, or enp1s0." >&2
  exit 1
fi

if [[ "$ROLE" != "$EXPECTED_ROLE" ]]; then
  echo "LiveLine Worker install: role must be $EXPECTED_ROLE for this token." >&2
  exit 1
fi

if ! [[ "$INTERFACE_NAME" =~ ^[A-Za-z0-9_.:-]+$ ]]; then
  echo "LiveLine Worker install: interface_name contains unsupported characters." >&2
  exit 1
fi

if [[ "$(id -u)" != "0" ]]; then
  echo "LiveLine Worker install: please run as root because /usr/local/bin, /etc, and systemd are required." >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "LiveLine Worker install: curl is required." >&2
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1 || [[ ! -d /run/systemd/system ]]; then
  echo "LiveLine Worker install: systemd is required." >&2
  exit 1
fi

echo "LiveLine Worker install: installing liveline-worker for role=$ROLE interface=$INTERFACE_NAME"
echo "LiveLine Worker install: this installs only the worker binary and systemd service."
echo "LiveLine Worker install: it does not install Xray, socat, or gost; does not open ports; does not modify firewall rules."

install -d -m 700 "$CONFIG_DIR"
TMP_BINARY="$(mktemp)"
cleanup() {{
  rm -f "$TMP_BINARY"
}}
trap cleanup EXIT

curl -fsSL "$BINARY_URL" -o "$TMP_BINARY"
install -m 755 "$TMP_BINARY" "$BINARY_PATH"

"$BINARY_PATH" register \\
  --config "$CONFIG_FILE" \\
  --console-url "$CONSOLE_URL" \\
  --token "$TOKEN" \\
  --role "$ROLE" \\
  --interface "$INTERFACE_NAME"

chmod 600 "$CONFIG_FILE"

cat > "$SERVICE_FILE" <<'LIVELINE_WORKER_SYSTEMD'
[Unit]
Description=LiveLine Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/liveline-worker run --config /etc/liveline-worker/config.yaml
Restart=always
RestartSec=10
User=root
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true

[Install]
WantedBy=multi-user.target
LIVELINE_WORKER_SYSTEMD

chmod 644 "$SERVICE_FILE"
systemctl daemon-reload
systemctl enable liveline-worker
systemctl restart liveline-worker

echo "LiveLine Worker install: completed."
echo "LiveLine Worker install: config file is $CONFIG_FILE with mode 600."
echo "LiveLine Worker install: view logs with: journalctl -u liveline-worker -f"
"""


@router.post("/worker-tokens")
def create_worker_token(
    payload: WorkerTokenCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    try:
        base_url = worker_public_base_url()
    except ValueError as exc:
        return worker_public_url_error(exc)

    raw_token = new_token()
    expires_at = now_utc() + timedelta(minutes=payload.expires_in_minutes)
    token = WorkerToken(
        token_hash=hash_token(raw_token),
        role=payload.role,
        status="active",
        name=payload.name,
        expires_at=expires_at,
        created_by=session.admin_id,
        server_id=None,
    )
    db.add(token)
    db.flush()
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_worker_token",
        result="success",
        request=request,
        resource_type="worker_token",
        resource_id=token.id,
    )
    db.commit()
    db.refresh(token)

    setup_url = base_url + f"/worker_setup_script/{raw_token}"
    install_command = f"curl -s {setup_url} | bash -s eth0 {token.role}"
    return success_response(
        {
            "token_id": token.id,
            "role": token.role,
            "expires_at": token.expires_at.isoformat() if token.expires_at else None,
            "install_command": install_command,
            "masked_token": mask_token(raw_token),
            "status": token.status,
        },
        "Worker 安装 token 已生成。明文 token 只在本次响应中返回。",
    )


@setup_router.get("/worker_setup_script/{token}")
def worker_setup_script(token: str, request: Request, db: Session = Depends(get_db)):
    raw_token = clean_token(token)
    if not raw_token:
        return error_response(404, "WORKER_TOKEN_NOT_FOUND", "Worker token 不存在。")

    token_record = find_token(db, raw_token)
    if not token_record:
        return error_response(404, "WORKER_TOKEN_NOT_FOUND", "Worker token 不存在。")
    if token_record.status != "active":
        return error_response(400, "WORKER_TOKEN_NOT_ACTIVE", "Worker token 不可用。")
    if token_is_expired(token_record):
        return error_response(400, "WORKER_TOKEN_EXPIRED", "Worker token 已过期。")

    try:
        base_url = worker_public_base_url()
    except ValueError as exc:
        return worker_public_url_error(exc)

    binary_url = base_url + "/worker_binary/liveline-worker-linux-amd64"
    return PlainTextResponse(
        install_script_for_role(
            token_record.role,
            raw_token,
            base_url,
            binary_url,
        ),
        media_type="text/x-shellscript",
    )


@setup_router.get("/worker_binary/liveline-worker-linux-amd64")
def download_worker_binary():
    binary_path = worker_binary_path()
    if not binary_path:
        return error_response(
            404,
            "WORKER_BINARY_NOT_FOUND",
            "liveline-worker binary is not available in this console build.",
        )
    return FileResponse(
        binary_path,
        media_type="application/octet-stream",
        filename="liveline-worker-linux-amd64",
    )


@router.post("/workers/register")
def register_worker(payload: WorkerRegisterRequest, db: Session = Depends(get_db)):
    raw_token = clean_token(payload.token)
    if not raw_token:
        return error_response(401, "WORKER_TOKEN_INVALID", "Worker token 无效。")

    token_record = find_token(db, raw_token)
    if not token_record:
        return error_response(401, "WORKER_TOKEN_INVALID", "Worker token 无效。")
    if token_record.status != "active":
        return error_response(400, "WORKER_TOKEN_NOT_ACTIVE", "Worker token 不可用。")
    if token_is_expired(token_record):
        token_record.status = "expired"
        db.add(token_record)
        db.commit()
        return error_response(400, "WORKER_TOKEN_EXPIRED", "Worker token 已过期。")
    if token_record.role != payload.role:
        return error_response(400, "WORKER_ROLE_MISMATCH", "Worker role 与 token 不一致。")

    current_time = now_utc()
    raw_worker_secret = new_token()
    worker = Worker(
        server_id=token_record.server_id,
        role=payload.role,
        name=token_record.name,
        public_ip=payload.public_ip,
        hostname=payload.hostname,
        interface_name=payload.interface_name,
        worker_version=payload.worker_version,
        status="online",
        last_heartbeat_at=current_time,
        worker_secret_hash=hash_token(raw_worker_secret),
        metadata_json={
            "registered_system_info": redact_metadata(payload.system_info or {}),
            "registered_at": current_time.isoformat(),
        },
    )
    token_record.status = "used"
    token_record.used_at = current_time
    db.add(worker)
    db.add(token_record)
    db.commit()
    db.refresh(worker)

    return success_response(
        {
            "worker_id": worker.id,
            "server_id": worker.server_id,
            "role": worker.role,
            "worker_secret": raw_worker_secret,
            "heartbeat_interval_seconds": DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
            "server_time": current_time.isoformat(),
        },
        "Worker 注册成功。worker_secret 只在本次响应中返回。",
    )


@router.post("/workers/heartbeat")
def worker_heartbeat(
    payload: WorkerHeartbeatRequest,
    x_worker_id: str | None = Header(None, alias="X-Worker-Id"),
    x_worker_secret: str | None = Header(None, alias="X-Worker-Secret"),
    db: Session = Depends(get_db),
):
    worker_id = clean_token(x_worker_id)
    worker_secret = clean_token(x_worker_secret)
    if not worker_id or not worker_secret:
        return error_response(401, "WORKER_AUTH_REQUIRED", "Worker 认证信息缺失。")

    worker = db.get(Worker, worker_id)
    if not worker or not token_matches(worker_secret, worker.worker_secret_hash):
        return error_response(401, "WORKER_AUTH_INVALID", "Worker 认证失败。")

    current_time = now_utc()
    heartbeat_data = payload.model_dump(exclude_none=True)
    if payload.worker_version:
        worker.worker_version = payload.worker_version
    if payload.interface_name:
        worker.interface_name = payload.interface_name
    if payload.public_ip:
        worker.public_ip = payload.public_ip
    if payload.hostname:
        worker.hostname = payload.hostname

    worker.status = "online"
    worker.last_heartbeat_at = current_time
    worker.metadata_json = {
        "received_at": current_time.isoformat(),
        "latest_status": redact_metadata(heartbeat_data),
    }
    db.add(worker)
    db.commit()

    return success_response(
        {
            "ok": True,
            "server_time": current_time.isoformat(),
            "next_heartbeat_seconds": DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        },
        "ok",
    )


@router.get("/workers")
@router.get("/workers/")
def list_workers(request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    workers = db.scalars(select(Worker).order_by(Worker.created_at.desc())).all()
    return success_response({"workers": [serialize_worker(worker) for worker in workers]}, "ok")


@router.get("/workers/{worker_id}")
def get_worker(worker_id: str, request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    worker = db.get(Worker, worker_id)
    if not worker:
        return error_response(404, "WORKER_NOT_FOUND", "Worker 不存在。")

    return success_response(serialize_worker(worker), "ok")
