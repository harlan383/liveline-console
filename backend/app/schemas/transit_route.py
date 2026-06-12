from pydantic import BaseModel, Field, field_validator

FORWARDING_METHODS = {"gost", "socat"}
TRANSIT_ROUTE_STATUSES = {"creating", "active", "disabled", "error"}
SSH_RESERVED_PORT = 20575
PROTECTED_CREATE_PORTS = {22, 8443, 18443, 20575}
PROTECTED_CREATE_PORT_MESSAGES = {
    22: "22 是 SSH 端口，不能作为中转监听端口。",
    8443: "8443 当前保留给 gost 回退链路，不能作为新转发端口。",
    18443: "18443 当前为 socat 正式链路，不能被新转发覆盖或复用。",
    20575: "20575 是历史问题端口，不能作为中转监听端口。",
}
SOCAT_RESERVED_PORTS = PROTECTED_CREATE_PORTS


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
