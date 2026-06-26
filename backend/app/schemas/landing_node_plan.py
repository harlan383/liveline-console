import ipaddress
import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


DEFAULT_REALITY_SNI = "dash.cloudflare.com"
DEFAULT_REALITY_DEST = "dash.cloudflare.com:443"
DEFAULT_REALITY_FINGERPRINT = "chrome"
DEFAULT_REALITY_FLOW = "xtls-rprx-vision"
DEFAULT_REALITY_SECURITY = "reality"
DEFAULT_REALITY_TRANSPORT = "tcp"
DEFAULT_LANDING_NODE_LISTEN_PORT = 27939
LANDING_NODE_LISTEN_PORT_MIN = 10000
LANDING_NODE_LISTEN_PORT_MAX = 30000
BLOCKED_LANDING_NODE_LISTEN_PORTS = {
    22,
    80,
    443,
    8080,
    8443,
    18443,
    3000,
    3200,
    8000,
    8200,
    5432,
    6379,
    15432,
    16379,
    10000,
    27017,
}

DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


def _normalize_reality_aliases(values: Any) -> Any:
    if not isinstance(values, dict):
        return values
    normalized = dict(values)
    if "reality_sni" in normalized and "server_name" not in normalized:
        normalized["server_name"] = normalized["reality_sni"]
    if "reality_dest" in normalized and "dest" not in normalized:
        normalized["dest"] = normalized["reality_dest"]
    return normalized


def _validate_reality_sni(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        raise ValueError("reality sni cannot be empty")
    if "://" in cleaned or "/" in cleaned or ":" in cleaned or any(char.isspace() for char in cleaned):
        raise ValueError("reality sni must be a domain without protocol, slash, colon, or whitespace")
    if not DOMAIN_RE.match(cleaned):
        raise ValueError("reality sni must be a valid domain")
    return cleaned


def _valid_dest_host(host: str) -> bool:
    if DOMAIN_RE.match(host):
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _validate_reality_dest(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        raise ValueError("reality dest cannot be empty")
    if "://" in cleaned or "/" in cleaned or any(char.isspace() for char in cleaned):
        raise ValueError("reality dest must be host:port without protocol, slash, or whitespace")

    if ":" not in cleaned:
        cleaned = f"{cleaned}:443"
    host, port_text = cleaned.rsplit(":", 1)
    if not host or not _valid_dest_host(host):
        raise ValueError("reality dest host must be a valid domain or IP")
    if not port_text.isdigit():
        raise ValueError("reality dest port must be numeric")
    port = int(port_text)
    if port < 1 or port > 65535:
        raise ValueError("reality dest port must be between 1 and 65535")
    return f"{host}:{port}"


def _validate_reality_fingerprint(value: str) -> str:
    cleaned = value.strip().lower()
    if not cleaned:
        raise ValueError("fingerprint cannot be empty")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", cleaned):
        raise ValueError("fingerprint contains unsupported characters")
    return cleaned


def validate_landing_node_listen_port(value: int) -> int:
    if value < LANDING_NODE_LISTEN_PORT_MIN or value > LANDING_NODE_LISTEN_PORT_MAX:
        raise ValueError(
            f"listen port must be between {LANDING_NODE_LISTEN_PORT_MIN} and {LANDING_NODE_LISTEN_PORT_MAX}"
        )
    if value in BLOCKED_LANDING_NODE_LISTEN_PORTS:
        raise ValueError("listen port is reserved and cannot be used for a direct node")
    return value


class LandingNodePlanRequest(BaseModel):
    listen_port: int = Field(
        default=DEFAULT_LANDING_NODE_LISTEN_PORT,
        ge=LANDING_NODE_LISTEN_PORT_MIN,
        le=LANDING_NODE_LISTEN_PORT_MAX,
    )
    protocol: str = Field(default="vless", max_length=40)
    security: str = Field(default=DEFAULT_REALITY_SECURITY, max_length=40)
    flow: str = Field(default=DEFAULT_REALITY_FLOW, max_length=80)
    server_name: str = Field(default=DEFAULT_REALITY_SNI, max_length=255)
    dest: str = Field(default=DEFAULT_REALITY_DEST, max_length=255)
    fingerprint: str = Field(default=DEFAULT_REALITY_FINGERPRINT, max_length=80)
    remark: str | None = Field(default=None, max_length=200)
    allow_install_xray: bool = False
    allow_modify_firewall: bool = False
    allow_generate_share_link: bool = False
    allow_overwrite_existing_config: bool = False
    cloud_security_group_confirmed: bool = False
    cloud_firewall_confirmed: bool = False
    server_firewall_confirmed: bool = False
    require_manual_cloud_firewall_confirmation: bool = True
    require_preflight_success: bool = True

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, values: Any) -> Any:
        return _normalize_reality_aliases(values)

    @field_validator("protocol", "security", "flow")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value cannot be empty")
        return cleaned

    @field_validator("listen_port")
    @classmethod
    def clean_listen_port(cls, value: int) -> int:
        return validate_landing_node_listen_port(value)

    @field_validator("server_name")
    @classmethod
    def clean_server_name(cls, value: str) -> str:
        return _validate_reality_sni(value)

    @field_validator("dest")
    @classmethod
    def clean_dest(cls, value: str) -> str:
        return _validate_reality_dest(value)

    @field_validator("fingerprint")
    @classmethod
    def clean_fingerprint(cls, value: str) -> str:
        return _validate_reality_fingerprint(value)

    @field_validator("remark")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class LandingNodePlanResponse(BaseModel):
    plan_id: str
    server_id: str
    mode: str
    ready: bool
    will_install_xray: bool
    will_create_config: bool
    will_open_local_firewall: bool
    will_modify_cloud_security_group: bool
    listen_port: int
    protocol: str
    security: str
    flow: str
    server_name: str
    dest: str
    fingerprint: str
    key_generation_strategy: dict[str, str]
    required_user_confirmations: list[str]
    preflight_summary: dict[str, Any]
    warnings: list[str]
    blocked_reasons: list[str]
    next_stage_required: str
    execution_guard: list[str]
    safety_boundary: list[str]


class LandingNodeCreateRequest(BaseModel):
    approved_port: int = Field(
        default=DEFAULT_LANDING_NODE_LISTEN_PORT,
        ge=LANDING_NODE_LISTEN_PORT_MIN,
        le=LANDING_NODE_LISTEN_PORT_MAX,
    )
    node_name: str | None = Field(default=None, max_length=120)
    server_name: str = Field(default=DEFAULT_REALITY_SNI, max_length=255)
    dest: str = Field(default=DEFAULT_REALITY_DEST, max_length=255)
    fingerprint: str = Field(default=DEFAULT_REALITY_FINGERPRINT, max_length=80)
    confirm_firewall_open: bool = False
    confirm_generate_share_link: bool = False
    confirm_write_share_link_after_success: bool = False
    confirm_no_existing_xray: bool = False
    confirm_rollback_new_artifacts_only: bool = False

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, values: Any) -> Any:
        return _normalize_reality_aliases(values)

    @field_validator("node_name")
    @classmethod
    def clean_optional_node_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("approved_port")
    @classmethod
    def clean_approved_port(cls, value: int) -> int:
        return validate_landing_node_listen_port(value)

    @field_validator("server_name")
    @classmethod
    def clean_create_server_name(cls, value: str) -> str:
        return _validate_reality_sni(value)

    @field_validator("dest")
    @classmethod
    def clean_create_dest(cls, value: str) -> str:
        return _validate_reality_dest(value)

    @field_validator("fingerprint")
    @classmethod
    def clean_create_fingerprint(cls, value: str) -> str:
        return _validate_reality_fingerprint(value)


class LandingNodeCreateResponse(BaseModel):
    command_id: str
    target_worker_id: str
    target_worker_version: str | None = None
    server_id: str
    approved_port: int
    status: str
    next_action: str
    safety_boundary: list[str]
