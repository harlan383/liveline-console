from typing import Any

from pydantic import BaseModel, Field, field_validator

WORKER_COMMAND_TYPES = {
    "ping",
    "collect_status",
    "service_status",
    "landing_preflight",
    "landing_node_create",
    "transit_readonly_preflight",
}
WORKER_COMMAND_STATUSES = {
    "pending",
    "claimed",
    "running",
    "succeeded",
    "failed",
    "expired",
    "cancelled",
}


class WorkerCommandCreate(BaseModel):
    command_type: str
    payload: dict[str, Any] | None = Field(default=None)
    server_id: str | None = Field(default=None)
    server_type: str | None = Field(default=None)

    @field_validator("command_type")
    @classmethod
    def validate_command_type(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in WORKER_COMMAND_TYPES:
            raise ValueError(
                "command_type must be ping, collect_status, service_status, landing_preflight, landing_node_create, or transit_readonly_preflight"
            )
        return cleaned

    @field_validator("server_type")
    @classmethod
    def validate_server_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned not in {"landing", "transit"}:
            raise ValueError("server_type must be landing or transit")
        return cleaned


class WorkerCommandResult(BaseModel):
    result: dict[str, Any] | None = Field(default=None)


class WorkerCommandFailure(BaseModel):
    error_message: str = Field(min_length=1, max_length=1000)
    result: dict[str, Any] | None = Field(default=None)

    @field_validator("error_message")
    @classmethod
    def clean_error_message(cls, value: str) -> str:
        return value.strip()[:1000]
