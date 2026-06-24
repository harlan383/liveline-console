from typing import Any

from pydantic import BaseModel, Field, field_validator

WORKER_ROLES = {"landing", "transit"}
WORKER_TOKEN_STATUSES = {"active", "used", "expired", "revoked"}
WORKER_STATUSES = {"online", "offline", "unknown"}
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 60
OFFLINE_THRESHOLD_SECONDS = DEFAULT_HEARTBEAT_INTERVAL_SECONDS * 5
HEARTBEAT_STALE_THRESHOLD_SECONDS = OFFLINE_THRESHOLD_SECONDS


def clean_optional(value: str | None, max_length: int | None = None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if max_length is not None:
        return cleaned[:max_length]
    return cleaned


class WorkerTokenCreate(BaseModel):
    role: str
    name: str | None = Field(default=None, max_length=120)
    server_id: str | None = Field(default=None, max_length=36)
    expires_in_minutes: int = Field(default=60, ge=1, le=10_080)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in WORKER_ROLES:
            raise ValueError("role must be landing or transit")
        return cleaned

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return clean_optional(value, max_length=120)

    @field_validator("server_id")
    @classmethod
    def clean_server_id(cls, value: str | None) -> str | None:
        return clean_optional(value, max_length=36)


class WorkerRegisterRequest(BaseModel):
    token: str
    role: str
    interface_name: str = Field(min_length=1, max_length=80)
    hostname: str = Field(min_length=1, max_length=255)
    public_ip: str | None = Field(default=None, max_length=45)
    worker_version: str | None = Field(default=None, max_length=80)
    system_info: dict[str, Any] | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in WORKER_ROLES:
            raise ValueError("role must be landing or transit")
        return cleaned

    @field_validator("interface_name", "hostname")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = clean_optional(value)
        if not cleaned:
            raise ValueError("value cannot be empty")
        return cleaned

    @field_validator("public_ip", "worker_version")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        return clean_optional(value)


class WorkerHeartbeatRequest(BaseModel):
    worker_version: str | None = Field(default=None, max_length=80)
    role: str | None = Field(default=None, max_length=16)
    interface_name: str | None = Field(default=None, max_length=80)
    public_ip: str | None = Field(default=None, max_length=45)
    hostname: str | None = Field(default=None, max_length=255)
    uptime_seconds: int | None = Field(default=None, ge=0)
    os: str | None = Field(default=None, max_length=160)
    kernel: str | None = Field(default=None, max_length=160)
    cpu: dict[str, Any] | str | None = None
    memory: dict[str, Any] | str | None = None
    disk: dict[str, Any] | str | None = None
    services: dict[str, Any] | None = None

    @field_validator("worker_version", "interface_name", "public_ip", "hostname", "os", "kernel")
    @classmethod
    def clean_text(cls, value: str | None) -> str | None:
        return clean_optional(value)

    @field_validator("role")
    @classmethod
    def clean_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if not cleaned:
            return None
        if cleaned not in WORKER_ROLES:
            raise ValueError("role must be landing or transit")
        return cleaned
