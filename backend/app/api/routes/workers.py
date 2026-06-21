import logging
import json
import shlex
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from json import JSONDecodeError
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.core.config import get_settings
from app.core.security import hash_token, new_token, token_matches
from app.db.session import get_db
from app.models.worker import Worker, WorkerToken
from app.models.worker_command import WorkerCommand
from app.schemas.common import error_response, success_response
from app.schemas.worker_commands import WorkerCommandCreate
from app.schemas.workers import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    OFFLINE_THRESHOLD_SECONDS,
    WorkerHeartbeatRequest,
    WorkerRegisterRequest,
    WorkerTokenCreate,
)
from app.services.auth_service import record_audit
from app.services.worker_binding import (
    sync_worker_bound_resource_status,
    try_bind_worker_by_public_ip,
    validate_worker_token_binding_target,
)
from app.services.worker_commands import (
    DEFAULT_NEXT_POLL_SECONDS,
    claim_next_worker_command,
    command_type_allowed,
    complete_worker_command,
    create_worker_command,
    fail_worker_command,
    normalize_worker_command_result,
    serialize_worker_command,
    serialize_worker_command_for_worker,
)
from app.services.landing_node_create import (
    LandingNodeCreateError,
    persist_successful_landing_node_result,
)
from app.services.transit_route_create import (
    TransitRouteCreateResultError,
    persist_successful_transit_route_create_result,
)
from app.services.remote_cleanup_delete import (
    RemoteCleanupError,
    command_is_remote_cleanup,
    persist_successful_remote_cleanup_result,
)
from app.services.worker_targeting import (
    WorkerTargetError,
    minimum_worker_version_for_command,
    resolve_command_target_worker,
)

router = APIRouter()
setup_router = APIRouter()
logger = logging.getLogger(__name__)

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
WORKER_COMMAND_TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "expired", "completed"}
WORKER_RESULT_BODY_LIMIT_BYTES = 128 * 1024
WORKER_CLEANUP_EXPECTED_OFFLINE = "cleanup_expected_offline"
WORKER_COMMAND_READ_SENSITIVE_MARKERS = (
    "share_link",
    "secure_share_link",
    "candidate_link",
    "client_link",
    "vless_link",
    "uuid",
    "privatekey",
    "private_key",
    "short_id",
    "shortid",
)


def now_utc() -> datetime:
    return datetime.now(UTC)


class WorkerReportBodyError(Exception):
    def __init__(self, code: str, message: str, body_size: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.body_size = body_size


def worker_remote_addr(request: Request) -> str:
    client = request.client
    if not client:
        return "unknown"
    return client.host or "unknown"


def request_content_length(request: Request) -> str:
    return request.headers.get("content-length") or "unknown"


def worker_command_status_is_terminal(status: str | None) -> bool:
    return status in WORKER_COMMAND_TERMINAL_STATUSES


def redact_worker_command_read_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered_key = key_text.lower()
            if any(marker in lowered_key for marker in WORKER_COMMAND_READ_SENSITIVE_MARKERS):
                redacted[key_text] = "[redacted]"
                continue
            redacted[key_text] = redact_worker_command_read_value(item)
        return redacted
    if isinstance(value, list):
        return [redact_worker_command_read_value(item) for item in value[:50]]
    if isinstance(value, str):
        lowered_value = value.lower()
        if any(marker in lowered_value for marker in ("vless://", "vmess://", "trojan://", "ss://")):
            return "[redacted-link]"
    return value


def serialize_admin_worker_command_read(command: WorkerCommand, worker: Worker | None = None) -> dict[str, Any]:
    data = serialize_worker_command(command, worker=worker)
    data["result_json"] = redact_worker_command_read_value(data.get("result_json") or {})
    return data


def elapsed_ms_since(started_perf: float) -> float:
    return (perf_counter() - started_perf) * 1000


def format_timings(timings: dict[str, float] | None) -> str:
    if not timings:
        return "-"
    return " ".join(f"{key}={value:.2f}" for key, value in timings.items())


def worker_cleanup_expected_offline(worker: Worker) -> bool:
    metadata = worker.metadata_json if isinstance(worker.metadata_json, dict) else {}
    return worker.status == "deleted" or metadata.get("cleanup_status") == WORKER_CLEANUP_EXPECTED_OFFLINE


def log_worker_result_endpoint(
    *,
    endpoint: str,
    phase: str,
    command_id: str,
    command_type: str | None,
    worker_id: str | None,
    body_size: int | None,
    request: Request,
    started_at: datetime,
    started_perf: float,
    outcome: str | None = None,
    timings: dict[str, float] | None = None,
) -> None:
    logger.info(
        "worker command %s %s command_id=%s command_type=%s worker_id=%s method=%s path=%s content_length=%s body_size=%s remote_addr=%s begin=%s end=%s elapsed_ms=%.2f outcome=%s timings=%s",
        endpoint,
        phase,
        command_id,
        command_type or "-",
        worker_id or "-",
        request.method,
        request.url.path,
        request_content_length(request),
        body_size if body_size is not None else "-",
        worker_remote_addr(request),
        started_at.isoformat(),
        now_utc().isoformat(),
        elapsed_ms_since(started_perf),
        outcome or "-",
        format_timings(timings),
    )


def log_worker_auth_event(
    *,
    phase: str,
    request: Request | None,
    worker_id: str | None,
    has_worker_id_header: bool,
    has_worker_secret_header: bool,
    started_perf: float,
    outcome: str | None = None,
) -> None:
    logger.info(
        "worker auth %s method=%s path=%s remote_addr=%s has_worker_id_header=%s has_worker_secret_header=%s worker_id=%s elapsed_ms=%.2f outcome=%s",
        phase,
        request.method if request else "-",
        request.url.path if request else "-",
        worker_remote_addr(request) if request else "unknown",
        has_worker_id_header,
        has_worker_secret_header,
        worker_id or "-",
        elapsed_ms_since(started_perf),
        outcome or "-",
    )


def decode_worker_command_report_body(
    raw_body: bytes,
    body_size: int,
    limit_bytes: int = WORKER_RESULT_BODY_LIMIT_BYTES,
) -> dict[str, Any]:
    if body_size > limit_bytes:
        raise WorkerReportBodyError(
            "WORKER_RESULT_BODY_TOO_LARGE",
            f"Worker command report body exceeds {limit_bytes} bytes.",
            body_size,
        )
    cleaned_body = raw_body.replace(b"\x00", b"")
    if not cleaned_body.strip():
        raise WorkerReportBodyError(
            "WORKER_RESULT_EMPTY_BODY",
            "Worker command report body is empty.",
            body_size,
        )
    try:
        payload = json.loads(cleaned_body.decode("utf-8"))
    except UnicodeDecodeError:
        raise WorkerReportBodyError(
            "WORKER_RESULT_BODY_ENCODING_ERROR",
            "Worker command report body must be UTF-8 JSON.",
            body_size,
        )
    except JSONDecodeError:
        raise WorkerReportBodyError(
            "WORKER_RESULT_PARSE_ERROR",
            "Worker command report body is not valid JSON.",
            body_size,
        )
    if not isinstance(payload, dict):
        raise WorkerReportBodyError(
            "WORKER_RESULT_INVALID_PAYLOAD",
            "Worker command report payload must be a JSON object.",
            body_size,
        )
    return payload


async def read_limited_worker_command_report_body(
    request: Request,
    limit_bytes: int = WORKER_RESULT_BODY_LIMIT_BYTES,
) -> tuple[bytes, int]:
    body = bytearray()
    body_size = 0
    async for chunk in request.stream():
        if not chunk:
            continue
        body_size += len(chunk)
        if body_size > limit_bytes:
            raise WorkerReportBodyError(
                "WORKER_RESULT_BODY_TOO_LARGE",
                f"Worker command report body exceeds {limit_bytes} bytes.",
                body_size,
            )
        body.extend(chunk)

    return bytes(body), body_size


async def parse_worker_command_report_request(
    request: Request,
    timings: dict[str, float],
) -> tuple[dict[str, Any], int]:
    body_started = perf_counter()
    raw_body, body_size = await read_limited_worker_command_report_body(request)
    timings["body_read_ms"] = elapsed_ms_since(body_started)
    parse_started = perf_counter()
    payload = decode_worker_command_report_body(raw_body, body_size)
    timings["json_parse_ms"] = elapsed_ms_since(parse_started)
    return payload, body_size


def apply_worker_result_statement_timeout(db: Session) -> None:
    db.execute(text("SET LOCAL statement_timeout = '3000ms'"))


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


def authenticate_worker(
    db: Session,
    x_worker_id: str | None,
    x_worker_secret: str | None,
    request: Request | None = None,
):
    started_perf = perf_counter()
    worker_id = clean_token(x_worker_id)
    worker_secret = clean_token(x_worker_secret)
    log_worker_auth_event(
        phase="begin",
        request=request,
        worker_id=worker_id,
        has_worker_id_header=bool(worker_id),
        has_worker_secret_header=bool(worker_secret),
        started_perf=started_perf,
    )
    if not worker_id or not worker_secret:
        log_worker_auth_event(
            phase="end",
            request=request,
            worker_id=worker_id,
            has_worker_id_header=bool(worker_id),
            has_worker_secret_header=bool(worker_secret),
            started_perf=started_perf,
            outcome="missing_header",
        )
        return None, error_response(401, "WORKER_AUTH_REQUIRED", "Worker 认证信息缺失。")

    if request and request.url.path.startswith("/api/workers/commands/"):
        try:
            apply_worker_result_statement_timeout(db)
        except Exception as exc:
            logger.warning(
                "worker auth statement_timeout setup failed path=%s worker_id=%s error=%s",
                request.url.path,
                worker_id,
                type(exc).__name__,
            )
            db.rollback()

    worker = db.get(Worker, worker_id)
    if not worker or not token_matches(worker_secret, worker.worker_secret_hash):
        log_worker_auth_event(
            phase="end",
            request=request,
            worker_id=worker_id,
            has_worker_id_header=True,
            has_worker_secret_header=True,
            started_perf=started_perf,
            outcome="invalid",
        )
        return None, error_response(401, "WORKER_AUTH_INVALID", "Worker 认证失败。")
    log_worker_auth_event(
        phase="end",
        request=request,
        worker_id=worker_id,
        has_worker_id_header=True,
        has_worker_secret_header=True,
        started_perf=started_perf,
        outcome="success",
    )
    return worker, None


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

echo "LiveLine Worker install: preparing Worker sandbox writable directory /opt/liveline-xray."
mkdir -p /opt/liveline-xray
chmod 755 /opt/liveline-xray

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
ReadWritePaths=/opt/liveline-xray /etc/systemd/system /run/systemd

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
        server_id=payload.server_id,
    )
    binding_error = validate_worker_token_binding_target(db, token)
    if binding_error:
        return error_response(400, binding_error[0], binding_error[1])
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
            "server_id": token.server_id,
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
    binding_error = validate_worker_token_binding_target(db, token_record)
    if binding_error:
        return error_response(400, binding_error[0], binding_error[1])

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
    sync_worker_bound_resource_status(db, worker)
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
    request: Request,
    x_worker_id: str | None = Header(None, alias="X-Worker-Id"),
    x_worker_secret: str | None = Header(None, alias="X-Worker-Secret"),
    db: Session = Depends(get_db),
):
    worker, auth_response = authenticate_worker(db, x_worker_id, x_worker_secret, request=request)
    if auth_response:
        return auth_response
    assert worker is not None

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

    cleanup_expected_offline = worker_cleanup_expected_offline(worker)
    previous_metadata = dict(worker.metadata_json or {})
    redacted_heartbeat = redact_metadata(heartbeat_data)

    if cleanup_expected_offline:
        previous_metadata.update(
            {
                "received_at": current_time.isoformat(),
                "latest_status": redacted_heartbeat,
                "unexpected_heartbeat_after_cleanup": True,
                "unexpected_heartbeat_at": current_time.isoformat(),
            }
        )
        worker.metadata_json = previous_metadata
    else:
        worker.status = "online"
        worker.metadata_json = {
            "received_at": current_time.isoformat(),
            "latest_status": redacted_heartbeat,
        }
    worker.last_heartbeat_at = current_time
    db.add(worker)
    if not cleanup_expected_offline:
        if worker.server_id:
            sync_worker_bound_resource_status(db, worker)
        else:
            try_bind_worker_by_public_ip(db, worker)
    db.commit()

    return success_response(
        {
            "ok": True,
            "server_time": current_time.isoformat(),
            "next_heartbeat_seconds": DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
        },
        "ok",
    )


@router.post("/workers/commands/next")
def next_worker_command(
    request: Request,
    x_worker_id: str | None = Header(None, alias="X-Worker-Id"),
    x_worker_secret: str | None = Header(None, alias="X-Worker-Secret"),
    db: Session = Depends(get_db),
):
    worker, auth_response = authenticate_worker(db, x_worker_id, x_worker_secret, request=request)
    if auth_response:
        return auth_response
    assert worker is not None

    command = claim_next_worker_command(db, worker)
    db.commit()
    if not command:
        return success_response(
            {
                "ok": True,
                "command": None,
                "next_poll_seconds": DEFAULT_NEXT_POLL_SECONDS,
            },
            "ok",
        )
    db.refresh(command)
    return success_response(
        {
            "ok": True,
            "command": serialize_worker_command_for_worker(command),
            "next_poll_seconds": DEFAULT_NEXT_POLL_SECONDS,
        },
        "ok",
    )


def fail_worker_command_result_ingest(
    db: Session,
    command: WorkerCommand,
    worker: Worker,
    code: str,
    message: str,
    status_code: int = 200,
    timings: dict[str, float] | None = None,
) -> dict | JSONResponse:
    db_update_started = perf_counter()
    try:
        fail_worker_command(db, command, message, {"code": code, "summary": message})
        db.commit()
        db.refresh(command)
        if timings is not None:
            timings["db_update_ms"] = elapsed_ms_since(db_update_started)
    except Exception as exc:
        if timings is not None:
            timings["db_update_ms"] = elapsed_ms_since(db_update_started)
        logger.exception(
            "Worker command failed-state persistence failed command_id=%s command_type=%s worker_id=%s error_code=%s",
            command.id,
            command.command_type,
            worker.id,
            code,
        )
        db.rollback()
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error_code": "WORKER_RESULT_FAILED_STATE_PERSIST_FAILED",
                "message": f"Worker 命令失败状态落库失败：{type(exc).__name__}",
            },
        )
    payload = {
        "success": status_code < 400,
        "data": {
            "command": serialize_worker_command(command, worker=worker),
            "accepted_failure": True,
            "error_code": code,
        },
        "message": "Worker 命令结果无法接收，已标记失败。",
    }
    if status_code >= 400:
        payload["error_code"] = code
    if status_code == 200:
        return payload
    return JSONResponse(status_code=status_code, content=payload)


def worker_command_already_completed_response(command: WorkerCommand, worker: Worker) -> dict:
    return success_response(
        {
            "command": serialize_worker_command(command, worker=worker),
            "already_completed": True,
        },
        "Worker 命令已结束，重复提交已忽略。",
    )


@router.post("/workers/commands/{command_id}/result")
async def worker_command_result(
    command_id: str,
    request: Request,
    x_worker_id: str | None = Header(None, alias="X-Worker-Id"),
    x_worker_secret: str | None = Header(None, alias="X-Worker-Secret"),
    db: Session = Depends(get_db),
):
    started_at = now_utc()
    started_perf = perf_counter()
    body_size: int | None = None
    timings: dict[str, float] = {}
    log_worker_result_endpoint(
        endpoint="result",
        phase="begin",
        command_id=command_id,
        command_type=None,
        worker_id=clean_token(x_worker_id),
        body_size=None,
        request=request,
        started_at=started_at,
        started_perf=started_perf,
        timings=timings,
    )
    auth_started = perf_counter()
    worker, auth_response = authenticate_worker(db, x_worker_id, x_worker_secret, request=request)
    timings["auth_ms"] = elapsed_ms_since(auth_started)
    if auth_response:
        log_worker_result_endpoint(
            endpoint="result",
            phase="end",
            command_id=command_id,
            command_type=None,
            worker_id=clean_token(x_worker_id),
            body_size=None,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome="auth_failed",
            timings=timings,
        )
        return auth_response
    assert worker is not None

    timeout_started = perf_counter()
    try:
        apply_worker_result_statement_timeout(db)
    except Exception as exc:
        logger.warning(
            "worker command result statement_timeout setup failed command_id=%s worker_id=%s error=%s",
            command_id,
            worker.id,
            type(exc).__name__,
        )
        db.rollback()
    timings["statement_timeout_ms"] = elapsed_ms_since(timeout_started)

    lookup_started = perf_counter()
    command = db.get(WorkerCommand, command_id)
    timings["command_lookup_ms"] = elapsed_ms_since(lookup_started)
    if not command or command.worker_id != worker.id:
        log_worker_result_endpoint(
            endpoint="result",
            phase="end",
            command_id=command_id,
            command_type=command.command_type if command else None,
            worker_id=worker.id,
            body_size=None,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome="not_found",
            timings=timings,
        )
        return error_response(404, "WORKER_COMMAND_NOT_FOUND", "Worker 命令不存在或不属于当前 Worker。")
    try:
        payload, body_size = await parse_worker_command_report_request(request, timings)
    except WorkerReportBodyError as exc:
        logger.warning(
            "worker command result body rejected command_id=%s command_type=%s worker_id=%s error_code=%s body_size=%s",
            command.id,
            command.command_type,
            worker.id,
            exc.code,
            exc.body_size,
        )
        if worker_command_status_is_terminal(command.status):
            response = worker_command_already_completed_response(command, worker)
            log_worker_result_endpoint(
                endpoint="result",
                phase="end",
                command_id=command.id,
                command_type=command.command_type,
                worker_id=worker.id,
                body_size=exc.body_size,
                request=request,
                started_at=started_at,
                started_perf=started_perf,
                outcome="already_completed",
                timings=timings,
            )
            return response
        response = fail_worker_command_result_ingest(
            db,
            command,
            worker,
            exc.code,
            exc.message,
            status_code=413 if exc.code == "WORKER_RESULT_BODY_TOO_LARGE" else 200,
            timings=timings,
        )
        log_worker_result_endpoint(
            endpoint="result",
            phase="end",
            command_id=command.id,
            command_type=command.command_type,
            worker_id=worker.id,
            body_size=exc.body_size,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome=f"failed_{exc.code}",
            timings=timings,
        )
        return response

    if worker_command_status_is_terminal(command.status):
        response = worker_command_already_completed_response(command, worker)
        log_worker_result_endpoint(
            endpoint="result",
            phase="end",
            command_id=command.id,
            command_type=command.command_type,
            worker_id=worker.id,
            body_size=body_size,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome="already_completed",
            timings=timings,
        )
        return response

    raw_result = payload.get("result")
    result_payload: dict[str, Any] | None = raw_result if isinstance(raw_result, dict) else None
    if raw_result is not None and not isinstance(raw_result, dict):
        response = fail_worker_command_result_ingest(
            db,
            command,
            worker,
            "WORKER_RESULT_INVALID_RESULT",
            "Worker 命令 result 字段必须是 JSON object。",
            timings=timings,
        )
        log_worker_result_endpoint(
            endpoint="result",
            phase="end",
            command_id=command.id,
            command_type=command.command_type,
            worker_id=worker.id,
            body_size=body_size,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome="failed_WORKER_RESULT_INVALID_RESULT",
            timings=timings,
        )
        return response

    normalize_started = perf_counter()
    try:
        if command.command_type == "landing_node_create":
            result_payload = persist_successful_landing_node_result(db=db, command=command, result=result_payload)
        elif command.command_type == "transit_route_create":
            result_payload = persist_successful_transit_route_create_result(db=db, command=command, result=result_payload)
        elif command_is_remote_cleanup(command.command_type):
            result_payload = persist_successful_remote_cleanup_result(db=db, command=command, result=result_payload)
        else:
            result_payload = normalize_worker_command_result(command.command_type, result_payload)
        timings["normalize_ms"] = elapsed_ms_since(normalize_started)
    except (LandingNodeCreateError, TransitRouteCreateResultError, RemoteCleanupError) as exc:
        timings["normalize_ms"] = elapsed_ms_since(normalize_started)
        response = fail_worker_command_result_ingest(db, command, worker, exc.code, exc.message, timings=timings)
        log_worker_result_endpoint(
            endpoint="result",
            phase="end",
            command_id=command.id,
            command_type=command.command_type,
            worker_id=worker.id,
            body_size=body_size,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome=f"failed_{exc.code}",
            timings=timings,
        )
        return response
    except ValueError as exc:
        timings["normalize_ms"] = elapsed_ms_since(normalize_started)
        response = fail_worker_command_result_ingest(
            db,
            command,
            worker,
            "WORKER_RESULT_SCHEMA_ERROR",
            str(exc)[:1000],
            timings=timings,
        )
        log_worker_result_endpoint(
            endpoint="result",
            phase="end",
            command_id=command.id,
            command_type=command.command_type,
            worker_id=worker.id,
            body_size=body_size,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome="failed_WORKER_RESULT_SCHEMA_ERROR",
            timings=timings,
        )
        return response
    except Exception as exc:
        timings["normalize_ms"] = elapsed_ms_since(normalize_started)
        logger.exception(
            "Worker command result normalization failed command_id=%s command_type=%s worker_id=%s",
            command.id,
            command.command_type,
            worker.id,
        )
        response = fail_worker_command_result_ingest(
            db,
            command,
            worker,
            "WORKER_RESULT_NORMALIZE_FAILED",
            f"Worker 命令结果规范化失败，已标记失败：{type(exc).__name__}",
            timings=timings,
        )
        log_worker_result_endpoint(
            endpoint="result",
            phase="end",
            command_id=command.id,
            command_type=command.command_type,
            worker_id=worker.id,
            body_size=body_size,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome="failed_WORKER_RESULT_NORMALIZE_FAILED",
            timings=timings,
        )
        return response

    db_update_started = perf_counter()
    try:
        complete_worker_command(db, command, result_payload)
        db.commit()
        timings["db_update_ms"] = elapsed_ms_since(db_update_started)
    except Exception as exc:
        timings["db_update_ms"] = elapsed_ms_since(db_update_started)
        logger.exception(
            "Worker command result persistence failed command_id=%s command_type=%s worker_id=%s",
            command.id,
            command.command_type,
            worker.id,
        )
        db.rollback()
        command = db.get(WorkerCommand, command_id)
        if not command:
            return error_response(404, "WORKER_COMMAND_NOT_FOUND", "Worker 命令不存在。")
        if not worker_command_status_is_terminal(command.status):
            response = fail_worker_command_result_ingest(
                db,
                command,
                worker,
                "WORKER_RESULT_PERSIST_FAILED",
                f"Worker 命令结果落库失败，已标记失败：{type(exc).__name__}",
                timings=timings,
            )
            log_worker_result_endpoint(
                endpoint="result",
                phase="end",
                command_id=command.id,
                command_type=command.command_type,
                worker_id=worker.id,
                body_size=body_size,
                request=request,
                started_at=started_at,
                started_perf=started_perf,
                outcome="failed_WORKER_RESULT_PERSIST_FAILED",
                timings=timings,
            )
            return response
        return error_response(500, "WORKER_RESULT_PERSIST_FAILED", "Worker 命令结果落库失败。")

    db.refresh(command)
    response = success_response(
        {"command": serialize_worker_command(command, worker=worker)},
        "Worker 命令结果已记录。",
    )
    log_worker_result_endpoint(
        endpoint="result",
        phase="end",
        command_id=command.id,
        command_type=command.command_type,
        worker_id=worker.id,
        body_size=body_size,
        request=request,
        started_at=started_at,
        started_perf=started_perf,
        outcome="succeeded",
        timings=timings,
    )
    return response


@router.post("/workers/commands/{command_id}/fail")
async def worker_command_fail(
    command_id: str,
    request: Request,
    x_worker_id: str | None = Header(None, alias="X-Worker-Id"),
    x_worker_secret: str | None = Header(None, alias="X-Worker-Secret"),
    db: Session = Depends(get_db),
):
    started_at = now_utc()
    started_perf = perf_counter()
    body_size: int | None = None
    timings: dict[str, float] = {}
    log_worker_result_endpoint(
        endpoint="fail",
        phase="begin",
        command_id=command_id,
        command_type=None,
        worker_id=clean_token(x_worker_id),
        body_size=None,
        request=request,
        started_at=started_at,
        started_perf=started_perf,
        timings=timings,
    )
    auth_started = perf_counter()
    worker, auth_response = authenticate_worker(db, x_worker_id, x_worker_secret, request=request)
    timings["auth_ms"] = elapsed_ms_since(auth_started)
    if auth_response:
        log_worker_result_endpoint(
            endpoint="fail",
            phase="end",
            command_id=command_id,
            command_type=None,
            worker_id=clean_token(x_worker_id),
            body_size=None,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome="auth_failed",
            timings=timings,
        )
        return auth_response
    assert worker is not None

    timeout_started = perf_counter()
    try:
        apply_worker_result_statement_timeout(db)
    except Exception as exc:
        logger.warning(
            "worker command failure statement_timeout setup failed command_id=%s worker_id=%s error=%s",
            command_id,
            worker.id,
            type(exc).__name__,
        )
        db.rollback()
    timings["statement_timeout_ms"] = elapsed_ms_since(timeout_started)

    lookup_started = perf_counter()
    command = db.get(WorkerCommand, command_id)
    timings["command_lookup_ms"] = elapsed_ms_since(lookup_started)
    if not command or command.worker_id != worker.id:
        log_worker_result_endpoint(
            endpoint="fail",
            phase="end",
            command_id=command_id,
            command_type=command.command_type if command else None,
            worker_id=worker.id,
            body_size=None,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome="not_found",
            timings=timings,
        )
        return error_response(404, "WORKER_COMMAND_NOT_FOUND", "Worker 命令不存在或不属于当前 Worker。")

    try:
        payload, body_size = await parse_worker_command_report_request(request, timings)
    except WorkerReportBodyError as exc:
        logger.warning(
            "worker command failure body rejected command_id=%s command_type=%s worker_id=%s error_code=%s body_size=%s",
            command.id,
            command.command_type,
            worker.id,
            exc.code,
            exc.body_size,
        )
        if worker_command_status_is_terminal(command.status):
            response = worker_command_already_completed_response(command, worker)
            log_worker_result_endpoint(
                endpoint="fail",
                phase="end",
                command_id=command.id,
                command_type=command.command_type,
                worker_id=worker.id,
                body_size=exc.body_size,
                request=request,
                started_at=started_at,
                started_perf=started_perf,
                outcome="already_completed",
                timings=timings,
            )
            return response
        response = fail_worker_command_result_ingest(
            db,
            command,
            worker,
            exc.code,
            exc.message,
            status_code=413 if exc.code == "WORKER_RESULT_BODY_TOO_LARGE" else 200,
            timings=timings,
        )
        log_worker_result_endpoint(
            endpoint="fail",
            phase="end",
            command_id=command.id,
            command_type=command.command_type,
            worker_id=worker.id,
            body_size=exc.body_size,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome=f"failed_{exc.code}",
            timings=timings,
        )
        return response

    if worker_command_status_is_terminal(command.status):
        response = worker_command_already_completed_response(command, worker)
        log_worker_result_endpoint(
            endpoint="fail",
            phase="end",
            command_id=command.id,
            command_type=command.command_type,
            worker_id=worker.id,
            body_size=body_size,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome="already_completed",
            timings=timings,
        )
        return response

    raw_error_message = payload.get("error_message") or payload.get("message") or payload.get("error")
    error_message = str(raw_error_message).strip()[:1000] if raw_error_message else "Worker reported command failure."
    raw_result = payload.get("result")
    if raw_result is None:
        raw_result = {
            "status": "failed",
            "summary": error_message,
            "redacted_summary": error_message,
            "safety_boundary": [
                "Worker failure report is redacted.",
                "No sensitive client link, token, SSH key, or database password is included.",
            ],
        }
    result_payload: dict[str, Any] | None
    if isinstance(raw_result, dict):
        normalize_started = perf_counter()
        try:
            result_payload = normalize_worker_command_result(command.command_type, raw_result)
            timings["normalize_ms"] = elapsed_ms_since(normalize_started)
        except ValueError:
            timings["normalize_ms"] = elapsed_ms_since(normalize_started)
            result_payload = {
                "code": "WORKER_FAILURE_RESULT_SCHEMA_ERROR",
                "summary": "Worker failure result could not be normalized.",
            }
        except Exception as exc:
            timings["normalize_ms"] = elapsed_ms_since(normalize_started)
            logger.exception(
                "Worker command failure result normalization failed command_id=%s command_type=%s worker_id=%s",
                command.id,
                command.command_type,
                worker.id,
            )
            result_payload = {
                "code": "WORKER_FAILURE_RESULT_NORMALIZE_FAILED",
                "summary": f"Worker failure result normalization failed: {type(exc).__name__}",
            }
    else:
        result_payload = {
            "code": "WORKER_FAILURE_RESULT_INVALID",
            "summary": "Worker failure result was not a JSON object.",
        }

    db_update_started = perf_counter()
    try:
        fail_worker_command(db, command, error_message, result_payload)
        db.commit()
        timings["db_update_ms"] = elapsed_ms_since(db_update_started)
    except Exception as exc:
        timings["db_update_ms"] = elapsed_ms_since(db_update_started)
        logger.exception(
            "Worker command failure persistence failed command_id=%s command_type=%s worker_id=%s",
            command.id,
            command.command_type,
            worker.id,
        )
        db.rollback()
        log_worker_result_endpoint(
            endpoint="fail",
            phase="end",
            command_id=command.id,
            command_type=command.command_type,
            worker_id=worker.id,
            body_size=body_size,
            request=request,
            started_at=started_at,
            started_perf=started_perf,
            outcome="failed_WORKER_FAILURE_PERSIST_FAILED",
            timings=timings,
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error_code": "WORKER_FAILURE_PERSIST_FAILED",
                "message": f"Worker 命令失败结果落库失败：{type(exc).__name__}",
            },
        )
    db.refresh(command)
    response = success_response(
        {"command": serialize_worker_command(command, worker=worker)},
        "Worker 命令失败结果已记录。",
    )
    log_worker_result_endpoint(
        endpoint="fail",
        phase="end",
        command_id=command.id,
        command_type=command.command_type,
        worker_id=worker.id,
        body_size=body_size,
        request=request,
        started_at=started_at,
        started_perf=started_perf,
        outcome="failed_recorded",
        timings=timings,
    )
    return response


@router.post("/workers/{worker_id}/commands")
def create_admin_worker_command(
    worker_id: str,
    payload: WorkerCommandCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    worker = db.get(Worker, worker_id)
    if not worker:
        return error_response(404, "WORKER_NOT_FOUND", "Worker 不存在。")
    if not command_type_allowed(payload.command_type):
        return error_response(
            400,
            "WORKER_COMMAND_NOT_ALLOWED",
            "只允许 ping、collect_status、service_status、landing_preflight、landing_node_create、transit_readonly_preflight、transit_route_create。",
        )
    if payload.command_type == "landing_node_create":
        return error_response(
            400,
            "LANDING_NODE_CREATE_ENDPOINT_REQUIRED",
            "正式创建落地节点必须通过 /api/vps/{id}/landing-node-create 并完成二次确认。",
        )
    if payload.command_type == "transit_readonly_preflight":
        return error_response(
            400,
            "TRANSIT_READONLY_PREFLIGHT_ENDPOINT_REQUIRED",
            "中转远程只读预检必须通过 /api/transit-routes/readonly-preflight-command 创建，不能传入任意 payload。",
        )
    if payload.command_type == "transit_route_create":
        return error_response(
            400,
            "TRANSIT_ROUTE_CREATE_PLAN_ENDPOINT_REQUIRED",
            "中转链路 Worker 创建路径必须通过 /api/transit-routes/worker-create-plan 创建，不能传入任意 payload。",
        )

    server_id = payload.server_id or worker.server_id
    server_type = payload.server_type or worker.role
    try:
        target = resolve_command_target_worker(
            db,
            server_type=server_type,
            server_id=server_id,
            role=server_type,
            requested_worker_id=worker.id,
            command_type=payload.command_type,
        )
    except WorkerTargetError as exc:
        return error_response(400, exc.code, exc.message)

    target_worker = target.worker
    command = create_worker_command(db, target_worker, payload.command_type, payload.payload)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="create_worker_command",
        result="success",
        request=request,
        resource_type="worker_command",
        resource_id=command.id,
    )
    db.commit()
    db.refresh(command)
    message = "Worker 检查命令已创建。"
    if target.changed:
        message = "已自动选择最新支持命令的 Worker，Worker 检查命令已创建。"
    return success_response(
        {
            "command": serialize_worker_command(command, include_payload=True, worker=target_worker),
            "requested_worker_id": target.requested_worker_id,
            "target_worker_id": target_worker.id,
            "target_worker_version": target_worker.worker_version,
            "target_worker_changed": target.changed,
            "minimum_supported_worker_version": minimum_worker_version_for_command(payload.command_type),
        },
        message,
    )


@router.get("/workers/commands/{command_id}")
def get_admin_worker_command(command_id: str, request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    command = db.get(WorkerCommand, command_id)
    if not command:
        return error_response(404, "WORKER_COMMAND_NOT_FOUND", "Worker 命令不存在。")
    worker = db.get(Worker, command.worker_id)
    return success_response(
        serialize_admin_worker_command_read(command, worker=worker),
        "ok",
    )


@router.get("/workers/{worker_id}/commands")
def list_admin_worker_commands(worker_id: str, request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    worker = db.get(Worker, worker_id)
    if not worker:
        return error_response(404, "WORKER_NOT_FOUND", "Worker 不存在。")

    commands = db.scalars(
        select(WorkerCommand)
        .where(WorkerCommand.worker_id == worker.id)
        .order_by(WorkerCommand.created_at.desc())
        .limit(20)
    ).all()
    return success_response(
        {"commands": [serialize_worker_command(command, worker=worker) for command in commands]},
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
