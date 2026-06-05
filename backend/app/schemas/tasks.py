from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TaskResponse(BaseModel):
    id: str
    vps_id: str | None
    node_id: str | None
    task_type: str
    status: str
    current_step: str | None
    progress: int
    error_code: str | None
    error_message: str | None
    result_data: dict[str, Any] | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class TaskLogResponse(BaseModel):
    id: str
    task_id: str
    level: str
    step: str | None
    message: str
    raw_output: str | None
    created_at: datetime | None
