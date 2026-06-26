import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

FORWARDING_METHOD_SOCAT = "socat"
FORWARDING_METHOD_GOST = "gost"
FORWARDING_METHOD_HAPROXY_TCP = "haproxy_tcp"
FORWARDING_METHODS = {FORWARDING_METHOD_GOST, FORWARDING_METHOD_SOCAT, FORWARDING_METHOD_HAPROXY_TCP}
FORWARDING_METHOD_LABELS = {
    FORWARDING_METHOD_SOCAT: "socat TCP transparent forwarding",
    FORWARDING_METHOD_GOST: "gost TCP forwarding",
    FORWARDING_METHOD_HAPROXY_TCP: "HAProxy TCP mode / Layer 4 forwarding",
}
TRANSIT_ROUTE_STATUSES = {"creating", "active", "disabled", "error"}
SSH_RESERVED_PORT = 20575
PROTECTED_CREATE_PORTS = {22, 8443, 18443, 20575}
APPROVED_TRANSIT_ROUTE_CREATE_STAGE = "Stage 3.3.71-transit-route-worker-create-path"
APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE = "Stage 3.3.73d-transit-route-real-create-code-path"
HAPROXY_ROUTE_CREATE_DRY_RUN_STAGE = "Stage 3.3.137-new-transit-haproxy-route-create-dry-run"
HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_STAGE = "Stage 3.3.138-new-transit-haproxy-route-create-final-approval"
HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT = "CONFIRM_HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_ONLY"
HAPROXY_ROUTE_CREATE_REAL_EXECUTION_STAGE = "Stage 3.3.139-new-transit-haproxy-route-create-real-execution"
HAPROXY_ROUTE_CREATE_REAL_EXECUTION_TEXT = "CONFIRM_REAL_HAPROXY_ROUTE_CREATE_23843"
APPROVED_TRANSIT_RESOURCE_ID = "1e222459-9fa2-4c62-800f-a3b35edb7df8"
APPROVED_TRANSIT_WORKER_ID = "f2e16197-e953-46dd-90af-66f64759a2a9"
APPROVED_LANDING_NODE_ID = "a71472c6-f62c-43b5-a223-9f5f070ae4ef"
APPROVED_TRANSIT_LISTEN_PORT = 23843
APPROVED_TRANSIT_INTERFACE_NAME = "eth0"
APPROVED_LANDING_TARGET_HOST = "64.90.13.19"
APPROVED_LANDING_TARGET_PORT = 27939
APPROVED_TRANSIT_FORWARDING_METHOD = FORWARDING_METHOD_SOCAT
APPROVED_TRANSIT_ROUTE_NAME = "hk-socat-live-23843"
APPROVED_TRANSIT_ROUTE_ID = "d10d3dcc-679f-4f85-ae37-9e5dfa37e6af"
APPROVED_TRANSIT_CANDIDATE_NAME = "hk-socat-live-23843-test"
APPROVED_TRANSIT_SERVICE_NAME = "liveline-socat-23843.service"
APPROVED_TRANSIT_SERVICE_PATH = "/etc/systemd/system/liveline-socat-23843.service"
TRANSIT_ROUTE_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$")
PROTECTED_CREATE_PORT_MESSAGES = {
    22: "22 是 SSH 端口，不能作为中转监听端口。",
    8443: "8443 当前保留给 gost 回退链路，不能作为新转发端口。",
    18443: "18443 当前为 socat 正式链路，不能被新转发覆盖或复用。",
    20575: "20575 是历史问题端口，不能作为中转监听端口。",
}
SOCAT_RESERVED_PORTS = PROTECTED_CREATE_PORTS


def normalize_forwarding_method(value: str) -> str:
    cleaned = value.strip().lower().replace("-", "_")
    if cleaned == "haproxy":
        cleaned = FORWARDING_METHOD_HAPROXY_TCP
    if cleaned not in FORWARDING_METHODS:
        raise ValueError("forwarding_method 不支持")
    return cleaned


def clean_route_display_name(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    lowered = cleaned.lower()
    if not cleaned:
        return None
    if "://" in lowered or "private key" in lowered or "token" in lowered or "password" in lowered:
        raise ValueError("route_display_name 不能包含链接、token、密码或私钥内容")
    return cleaned


class TransitRouteCreateFields(BaseModel):
    transit_resource_id: str = Field(min_length=1, max_length=36)
    node_id: str = Field(min_length=1, max_length=36)
    listen_port: int = Field(ge=1, le=65535)
    forwarding_method: str = FORWARDING_METHOD_GOST
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
        return normalize_forwarding_method(value)


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


class TransitRouteCandidateSummary(BaseModel):
    route_id: str
    route_name: str
    transit_resource_id: str
    transit_resource_name: str | None = None
    entry_host: str
    listen_port: int
    target_host: str
    target_port: int
    forwarding_method: str
    service_name: str
    service_path: str
    status: str
    landing_node_id: str
    landing_node_name: str | None = None
    landing_vps_ip: str | None = None
    route_share_link_present: bool = False
    share_link_present: bool = False
    recommended_candidate: bool = True
    cutover_status: str = "not_cutover"
    safety_boundary: list[str]


class TransitRouteCandidateExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm_transient_export: bool = False
    confirm_no_database_write: bool = False
    confirm_no_share_link_mutation: bool = False
    confirm_no_cutover: bool = False
    reason: str = Field(default="client_candidate_test", min_length=1, max_length=120)

    @field_validator("reason")
    @classmethod
    def clean_candidate_export_reason(cls, value: str) -> str:
        cleaned = value.strip()
        lowered = cleaned.lower()
        if "://" in lowered or "private key" in lowered or "token" in lowered or "password" in lowered:
            raise ValueError("reason 不能包含链接、token、密码或私钥内容")
        return cleaned or "client_candidate_test"


class TransitRouteCandidateExportResult(BaseModel):
    route_id: str
    route_name: str
    candidate_name: str
    server: str
    port: int
    protocol: str
    security: str
    network: str
    flow: str | None = None
    sni: str | None = None
    fingerprint: str | None = None
    reality_public_key_present: bool
    reality_short_id_present: bool
    uuid_present: bool
    masked_candidate_link: str
    candidate_link: str
    warning: str
    cutover_status: str = "not_cutover"
    database_write_performed: bool = False
    nodes_share_link_mutated: bool = False
    transit_route_share_link_mutated: bool = False
    safety_boundary: list[str]


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
    forwarding_method: str = FORWARDING_METHOD_SOCAT
    purpose: str | None = Field(default=None, max_length=120)
    readonly: bool = False

    @field_validator("forwarding_method")
    @classmethod
    def validate_preflight_forwarding_method(cls, value: str) -> str:
        return normalize_forwarding_method(value)

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


class TransitHaproxyReadinessApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transit_resource_id: str = Field(min_length=1, max_length=36)
    landing_node_id: str = Field(min_length=1, max_length=36)
    planned_listen_port: int = Field(ge=1, le=65535)
    landing_target_port: int = Field(ge=1, le=65535)
    forwarding_method: str = FORWARDING_METHOD_HAPROXY_TCP
    purpose: str | None = Field(default=None, max_length=120)
    firewall_security_group_confirmed: bool = False
    cloud_firewall_confirmed: bool = False
    server_firewall_confirmed: bool = False
    no_cutover_confirmed: bool = False
    no_node_share_link_change_confirmed: bool = False
    no_full_client_link_confirmed: bool = False

    @field_validator("forwarding_method")
    @classmethod
    def validate_haproxy_readiness_forwarding_method(cls, value: str) -> str:
        return normalize_forwarding_method(value)

    @field_validator("purpose")
    @classmethod
    def clean_haproxy_readiness_purpose(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        lowered = cleaned.lower()
        if "://" in lowered or "private key" in lowered or "token" in lowered or "password" in lowered:
            raise ValueError("purpose 不能包含链接、token、密码或私钥内容")
        return cleaned or None


class TransitHaproxyRouteCreateDryRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transit_resource_id: str = Field(min_length=1, max_length=36)
    landing_node_id: str = Field(min_length=1, max_length=36)
    planned_listen_port: int = Field(ge=1, le=65535)
    landing_target_host: str = Field(min_length=1, max_length=255)
    landing_target_port: int = Field(ge=1, le=65535)
    forwarding_method: str = FORWARDING_METHOD_HAPROXY_TCP
    purpose: str | None = Field(default=None, max_length=120)
    route_name: str = Field(min_length=1, max_length=120)
    route_display_name: str | None = Field(default=None, max_length=120)
    approval_stage: str = HAPROXY_ROUTE_CREATE_DRY_RUN_STAGE
    readiness_approval_confirmed: bool = False
    dry_run: bool = True
    approval_required: bool = True
    firewall_security_group_confirmed: bool = False
    cloud_firewall_confirmed: bool = False
    server_firewall_confirmed: bool = False
    no_cutover_confirmed: bool = False
    no_node_share_link_change_confirmed: bool = False
    no_full_client_link_confirmed: bool = False

    @field_validator("forwarding_method")
    @classmethod
    def validate_haproxy_dry_run_forwarding_method(cls, value: str) -> str:
        return normalize_forwarding_method(value)

    @field_validator("purpose")
    @classmethod
    def clean_haproxy_dry_run_purpose(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        lowered = cleaned.lower()
        if "://" in lowered or "private key" in lowered or "token" in lowered or "password" in lowered:
            raise ValueError("purpose 不能包含链接、token、密码或私钥内容")
        return cleaned or None

    @field_validator("route_name")
    @classmethod
    def validate_haproxy_dry_run_route_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not TRANSIT_ROUTE_SAFE_NAME_RE.match(cleaned):
            raise ValueError("route_name 只能包含字母、数字、点、下划线和短横线，并且必须以字母或数字开头")
        return cleaned

    @field_validator("route_display_name")
    @classmethod
    def validate_haproxy_dry_run_display_name(cls, value: str | None) -> str | None:
        return clean_route_display_name(value)

    @field_validator("approval_stage")
    @classmethod
    def validate_haproxy_dry_run_approval_stage(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned != HAPROXY_ROUTE_CREATE_DRY_RUN_STAGE:
            raise ValueError("approval_stage 不匹配当前 dry-run 阶段")
        return cleaned


class TransitHaproxyRouteCreateFinalApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run_command_id: str = Field(min_length=1, max_length=36)
    transit_resource_id: str = Field(min_length=1, max_length=36)
    landing_node_id: str = Field(min_length=1, max_length=36)
    planned_listen_port: int = Field(ge=1, le=65535)
    landing_target_host: str = Field(min_length=1, max_length=255)
    landing_target_port: int = Field(ge=1, le=65535)
    forwarding_method: str = FORWARDING_METHOD_HAPROXY_TCP
    route_name: str = Field(min_length=1, max_length=120)
    route_display_name: str | None = Field(default=None, max_length=120)
    planned_service_name: str = Field(min_length=1, max_length=160)
    approval_stage: str = HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_STAGE
    dry_run_verified: bool = False
    firewall_security_group_confirmed: bool = False
    cloud_firewall_confirmed: bool = False
    server_firewall_confirmed: bool = False
    no_cutover_confirmed: bool = False
    no_node_share_link_change_confirmed: bool = False
    no_full_client_link_confirmed: bool = False
    final_approval_text: str = Field(min_length=1, max_length=120)

    @field_validator("forwarding_method")
    @classmethod
    def validate_haproxy_final_forwarding_method(cls, value: str) -> str:
        return normalize_forwarding_method(value)

    @field_validator("route_name")
    @classmethod
    def validate_haproxy_final_route_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not TRANSIT_ROUTE_SAFE_NAME_RE.match(cleaned):
            raise ValueError("route_name 只能包含字母、数字、点、下划线和短横线，并且必须以字母或数字开头")
        return cleaned

    @field_validator("route_display_name")
    @classmethod
    def validate_haproxy_final_display_name(cls, value: str | None) -> str | None:
        return clean_route_display_name(value)

    @field_validator("planned_service_name")
    @classmethod
    def validate_haproxy_final_service_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not re.match(r"^liveline-haproxy-[0-9]{1,5}\.service$", cleaned):
            raise ValueError("planned_service_name 必须是 liveline-haproxy-<port>.service")
        return cleaned

    @field_validator("approval_stage")
    @classmethod
    def validate_haproxy_final_approval_stage(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned != HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_STAGE:
            raise ValueError("approval_stage 不匹配当前 final approval 阶段")
        return cleaned


class TransitHaproxyRouteCreateRealExecutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run_command_id: str = Field(min_length=1, max_length=36)
    transit_resource_id: str = Field(min_length=1, max_length=36)
    landing_node_id: str = Field(min_length=1, max_length=36)
    planned_listen_port: int = Field(ge=1, le=65535)
    landing_target_host: str = Field(min_length=1, max_length=255)
    landing_target_port: int = Field(ge=1, le=65535)
    forwarding_method: str = FORWARDING_METHOD_HAPROXY_TCP
    route_name: str = Field(min_length=1, max_length=120)
    route_display_name: str | None = Field(default=None, max_length=120)
    approval_stage: str = HAPROXY_ROUTE_CREATE_REAL_EXECUTION_STAGE
    final_approval_text: str = Field(min_length=1, max_length=120)
    real_execution_text: str = Field(min_length=1, max_length=120)
    firewall_security_group_confirmed: bool = False
    cloud_firewall_confirmed: bool = False
    server_firewall_confirmed: bool = False
    no_cutover_confirmed: bool = False
    no_node_share_link_change_confirmed: bool = False
    no_full_client_link_confirmed: bool = False

    @field_validator("forwarding_method")
    @classmethod
    def validate_haproxy_real_forwarding_method(cls, value: str) -> str:
        return normalize_forwarding_method(value)

    @field_validator("route_name")
    @classmethod
    def validate_haproxy_real_route_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not TRANSIT_ROUTE_SAFE_NAME_RE.match(cleaned):
            raise ValueError("route_name 只能包含字母、数字、点、下划线和短横线，并且必须以字母或数字开头")
        return cleaned

    @field_validator("route_display_name")
    @classmethod
    def validate_haproxy_real_display_name(cls, value: str | None) -> str | None:
        return clean_route_display_name(value)

    @field_validator("approval_stage")
    @classmethod
    def validate_haproxy_real_approval_stage(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned != HAPROXY_ROUTE_CREATE_REAL_EXECUTION_STAGE:
            raise ValueError("approval_stage 不匹配当前 real execution 阶段")
        return cleaned

class TransitRouteWorkerCreatePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transit_resource_id: str = Field(min_length=1, max_length=36)
    landing_node_id: str = Field(min_length=1, max_length=36)
    planned_listen_port: int = Field(ge=1, le=65535)
    landing_target_host: str = Field(min_length=1, max_length=255)
    landing_target_port: int = Field(ge=1, le=65535)
    forwarding_method: str = FORWARDING_METHOD_SOCAT
    purpose: str | None = Field(default=None, max_length=120)
    approval_stage: str = APPROVED_TRANSIT_ROUTE_CREATE_STAGE
    dry_run: bool = True
    approval_required: bool = True
    user_approved_execution_boundary: bool = False
    no_node_share_link_change_confirmed: bool = False
    no_cutover_confirmed: bool = False

    @field_validator("forwarding_method")
    @classmethod
    def validate_worker_create_forwarding_method(cls, value: str) -> str:
        return normalize_forwarding_method(value)

    @field_validator("purpose")
    @classmethod
    def clean_worker_create_purpose(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        lowered = cleaned.lower()
        if "://" in lowered or "private key" in lowered or "token" in lowered or "password" in lowered:
            raise ValueError("purpose 不能包含链接、token、密码或私钥内容")
        return cleaned or None

    @field_validator("approval_stage")
    @classmethod
    def validate_approval_stage(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned != APPROVED_TRANSIT_ROUTE_CREATE_STAGE:
            raise ValueError("approval_stage 不匹配当前审批阶段")
        return cleaned


class TransitRouteWorkerCreateExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transit_resource_id: str = Field(min_length=1, max_length=36)
    landing_node_id: str = Field(min_length=1, max_length=36)
    planned_listen_port: int = Field(ge=1, le=65535)
    landing_target_host: str = Field(min_length=1, max_length=255)
    landing_target_port: int = Field(ge=1, le=65535)
    forwarding_method: str = FORWARDING_METHOD_SOCAT
    purpose: str | None = Field(default=None, max_length=120)
    route_name: str = APPROVED_TRANSIT_ROUTE_NAME
    approval_stage: str = APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE
    dry_run: bool = False
    approval_required: bool = False
    user_approved_real_execution: bool = False
    firewall_security_group_confirmed: bool = False
    cloud_firewall_confirmed: bool = False
    server_firewall_confirmed: bool = False
    no_node_share_link_change_confirmed: bool = False
    no_full_client_link_confirmed: bool = False
    no_cutover_confirmed: bool = False

    @field_validator("forwarding_method")
    @classmethod
    def validate_execute_forwarding_method(cls, value: str) -> str:
        return normalize_forwarding_method(value)

    @field_validator("purpose")
    @classmethod
    def clean_execute_purpose(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        lowered = cleaned.lower()
        if "://" in lowered or "private key" in lowered or "token" in lowered or "password" in lowered:
            raise ValueError("purpose 不能包含链接、token、密码或私钥内容")
        return cleaned or None

    @field_validator("route_name")
    @classmethod
    def validate_execute_route_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not TRANSIT_ROUTE_SAFE_NAME_RE.match(cleaned):
            raise ValueError("route_name 只能包含字母、数字、点、下划线和短横线，并且必须以字母或数字开头")
        return cleaned

    @field_validator("approval_stage")
    @classmethod
    def validate_execute_approval_stage(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned != APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE:
            raise ValueError("approval_stage 不匹配当前真实执行审批阶段")
        return cleaned
