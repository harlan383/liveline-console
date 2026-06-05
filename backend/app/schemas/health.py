from pydantic import BaseModel


class ComponentStatus(BaseModel):
    status: str
    detail: str | None = None


class HealthData(BaseModel):
    backend: ComponentStatus
    database: ComponentStatus
    redis: ComponentStatus
    worker: ComponentStatus
