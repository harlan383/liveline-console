from pydantic import BaseModel, Field, field_validator

FORWARDING_METHODS = {"gost", "socat"}
TRANSIT_ROUTE_STATUSES = {"creating", "active", "disabled", "error"}
SSH_RESERVED_PORT = 20575
SOCAT_RESERVED_PORTS = {22, 8443, 20575}


class TransitRouteCreateFields(BaseModel):
    transit_resource_id: str = Field(min_length=1, max_length=36)
    node_id: str = Field(min_length=1, max_length=36)
    listen_port: int = Field(ge=1, le=65535)
    forwarding_method: str = "gost"
    route_name: str = Field(min_length=1, max_length=120)
    confirm: bool = False

    @field_validator("route_name")
    @classmethod
    def clean_route_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("route_name 不能为空")
        return cleaned

    @field_validator("forwarding_method")
    @classmethod
    def validate_forwarding_method(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in FORWARDING_METHODS:
            raise ValueError("forwarding_method 不支持")
        return cleaned


class TransitRouteData(BaseModel):
    id: str
    name: str
    transit_resource_id: str
    transit_resource_name: str | None = None
    node_id: str
    node_name: str | None = None
    landing_vps_id: str | None = None
    landing_vps_ip: str | None = None
    listen_port: int
    target_host: str
    target_port: int
    forwarding_method: str
    service_name: str
    service_path: str
    status: str
    share_link: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None


class TransitRouteListResult(BaseModel):
    routes: list[TransitRouteData]
