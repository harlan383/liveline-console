from datetime import datetime
from decimal import Decimal
import re

from pydantic import BaseModel, Field, field_validator, model_validator

RESOURCE_TYPES = {"server", "iepl", "iplc", "other"}
PROTOCOL_HINTS = {"tcp", "udp", "tcp_udp", "unknown"}
RESOURCE_STATUSES = {"active", "disabled", "pending_worker", "worker_online", "worker_offline"}
HOST_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
SENSITIVE_NOTE_MARKERS = (
    "PRIVATE KEY",
    "BEGIN OPENSSH",
    "PASSWORD",
    "PASSWD",
    "PASSPHRASE",
    "SECRET",
    "TOKEN",
    "ACCESS KEY",
    "SSH KEY",
    "SSH_KEY",
    "SSHKEY",
    "后台账号",
    "后台密码",
    "密码",
    "私钥",
    "密钥",
)


def clean_optional_text(value: str | None, *, max_length: int) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise ValueError(f"不能超过 {max_length} 个字符")
    return cleaned


def validate_host(value: str | None) -> str | None:
    cleaned = clean_optional_text(value, max_length=255)
    if cleaned is None:
        return None
    if "://" in cleaned or "/" in cleaned or any(char.isspace() for char in cleaned):
        raise ValueError("host 不能包含协议、路径或空白字符")
    if not HOST_RE.fullmatch(cleaned):
        raise ValueError("host 只能包含字母、数字、点、下划线、短横线或冒号")
    return cleaned


class TransitResourceBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    resource_type: str
    provider: str | None = Field(default=None, max_length=120)
    entry_host: str | None = Field(default=None, max_length=255)
    entry_port: int | None = Field(default=None, ge=1, le=65535)
    entry_region: str | None = Field(default=None, max_length=120)
    exit_region: str | None = Field(default=None, max_length=120)
    bandwidth_mbps: int | None = Field(default=None, ge=0)
    traffic_limit_gb: Decimal | None = Field(default=None, ge=0)
    traffic_used_gb: Decimal | None = Field(default=None, ge=0)
    protocol_hint: str = "unknown"
    has_ssh: bool = False
    ssh_host: str | None = Field(default=None, max_length=255)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_username: str | None = Field(default=None, max_length=80)
    status: str = "active"
    expires_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("name 不能为空")
        return cleaned

    @field_validator("resource_type")
    @classmethod
    def validate_resource_type(cls, value: str) -> str:
        if value not in RESOURCE_TYPES:
            raise ValueError("resource_type 不合法")
        return value

    @field_validator("protocol_hint")
    @classmethod
    def validate_protocol_hint(cls, value: str) -> str:
        if value not in PROTOCOL_HINTS:
            raise ValueError("protocol_hint 不合法")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str) -> str:
        if value not in RESOURCE_STATUSES:
            raise ValueError("status 不合法")
        return value

    @field_validator("provider", "entry_region", "exit_region", "ssh_username", mode="before")
    @classmethod
    def clean_short_text(cls, value: str | None) -> str | None:
        return clean_optional_text(value, max_length=120)

    @field_validator("entry_host", "ssh_host", mode="before")
    @classmethod
    def clean_host(cls, value: str | None) -> str | None:
        return validate_host(value)

    @field_validator("notes", mode="before")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        cleaned = clean_optional_text(value, max_length=4000)
        if cleaned is None:
            return None
        upper = cleaned.upper()
        if any(marker in upper for marker in SENSITIVE_NOTE_MARKERS):
            raise ValueError("备注不能包含密码、私钥、后台账号或密钥等敏感凭据")
        return cleaned

    @model_validator(mode="after")
    def normalize_ssh_fields(self) -> "TransitResourceBase":
        if not self.has_ssh:
            self.ssh_host = None
            self.ssh_port = None
            self.ssh_username = None
        return self


class TransitResourceCreate(TransitResourceBase):
    pass


class TransitResourceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    resource_type: str | None = None
    provider: str | None = Field(default=None, max_length=120)
    entry_host: str | None = Field(default=None, max_length=255)
    entry_port: int | None = Field(default=None, ge=1, le=65535)
    entry_region: str | None = Field(default=None, max_length=120)
    exit_region: str | None = Field(default=None, max_length=120)
    bandwidth_mbps: int | None = Field(default=None, ge=0)
    traffic_limit_gb: Decimal | None = Field(default=None, ge=0)
    traffic_used_gb: Decimal | None = Field(default=None, ge=0)
    protocol_hint: str | None = None
    has_ssh: bool | None = None
    ssh_host: str | None = Field(default=None, max_length=255)
    ssh_port: int | None = Field(default=None, ge=1, le=65535)
    ssh_username: str | None = Field(default=None, max_length=80)
    status: str | None = None
    expires_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("name", mode="before")
    @classmethod
    def clean_name(cls, value: str | None) -> str | None:
        return clean_optional_text(value, max_length=120)

    @field_validator("resource_type")
    @classmethod
    def validate_resource_type(cls, value: str | None) -> str | None:
        if value is not None and value not in RESOURCE_TYPES:
            raise ValueError("resource_type 不合法")
        return value

    @field_validator("protocol_hint")
    @classmethod
    def validate_protocol_hint(cls, value: str | None) -> str | None:
        if value is not None and value not in PROTOCOL_HINTS:
            raise ValueError("protocol_hint 不合法")
        return value

    @field_validator("status")
    @classmethod
    def validate_status(cls, value: str | None) -> str | None:
        if value is not None and value not in RESOURCE_STATUSES:
            raise ValueError("status 不合法")
        return value

    @field_validator("provider", "entry_region", "exit_region", "ssh_username", mode="before")
    @classmethod
    def clean_short_text(cls, value: str | None) -> str | None:
        return clean_optional_text(value, max_length=120)

    @field_validator("entry_host", "ssh_host", mode="before")
    @classmethod
    def clean_host(cls, value: str | None) -> str | None:
        return validate_host(value)

    @field_validator("notes", mode="before")
    @classmethod
    def clean_notes(cls, value: str | None) -> str | None:
        cleaned = clean_optional_text(value, max_length=4000)
        if cleaned is None:
            return None
        upper = cleaned.upper()
        if any(marker in upper for marker in SENSITIVE_NOTE_MARKERS):
            raise ValueError("备注不能包含密码、私钥、后台账号或密钥等敏感凭据")
        return cleaned

    @model_validator(mode="after")
    def normalize_ssh_fields(self) -> "TransitResourceUpdate":
        if self.has_ssh is False:
            self.ssh_host = None
            self.ssh_port = None
            self.ssh_username = None
        return self
