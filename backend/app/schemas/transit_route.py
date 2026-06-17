from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class ReadonlyPreflightPlanRequest(BaseModel):
    transit_resource_id: str | None = None
    transit_resource_name: str | None = None
    transit_host_hint: str | None = None
    landing_node_id: str | None = None
    landing_node_name: str | None = None
    landing_host_hint: str | None = None
    landing_target_port: int | str | None = None
    planned_listen_port: int | str | None = None
    route_purpose: str | None = None
    firewall_security_group_confirmed: bool = False
    cloud_firewall_confirmed: bool = False
    server_firewall_confirmed: bool = False
    local_backup_confirmed: bool = False
    user_approved_readonly_preflight: bool = False
    workbuddy_authorized: bool = False
    no_cutover_confirmed: bool = False
    no_node_share_link_change_confirmed: bool = False


class ReadonlyPreflightPlanCheck(BaseModel):
    id: str
    label: str
    category: str
    status: str
    passed: bool
    message: str
    evidence_summary: str
    next_action: str
    sensitive_output_redacted: bool = True


class ReadonlyPreflightPlanResponse(BaseModel):
    ready: bool
    blocked: bool
    status: str
    summary: str
    next_action: str
    checks: list[ReadonlyPreflightPlanCheck]
    safety_boundary: list[str]
    redacted_summary: str


class TransitReadonlyPreflightCommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transit_resource_id: str = Field(min_length=1, max_length=36)
    landing_node_id: str = Field(min_length=1, max_length=36)
    planned_listen_port: int = Field(ge=1, le=65535)
    landing_target_port: int = Field(ge=1, le=65535)
    forwarding_method: str = "socat"
    purpose: str | None = Field(default=None, max_length=120)
    readonly: bool = False

    @field_validator("forwarding_method")
    @classmethod
    def validate_preflight_forwarding_method(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned not in FORWARDING_METHODS:
            raise ValueError("forwarding_method 不支持")
        return cleaned

    @field_validator("purpose")
    @classmethod
    def clean_preflight_purpose(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        lowered = cleaned.lower()
        if "://" in lowered or "private key" in lowered or "token" in lowered or "password" in lowered:
            raise ValueError("purpose 不能包含链接、token、密码或私钥内容")
        return cleaned or None
