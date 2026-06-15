from typing import Any

from pydantic import BaseModel, Field, field_validator

WORKER_COMMAND_TYPES = {"ping", "collect_status", "service_status"}
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

    @field_validator("command_type")
    @classmethod
    def validate_command_type(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in WORKER_COMMAND_TYPES:
            raise ValueError("command_type must be ping, collect_status, or service_status")
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
