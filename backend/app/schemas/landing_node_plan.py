from typing import Any

from pydantic import BaseModel, Field, field_validator


class LandingNodePlanRequest(BaseModel):
    listen_port: int = Field(ge=1, le=65535)
    protocol: str = Field(default="vless", max_length=40)
    security: str = Field(default="reality", max_length=40)
    flow: str = Field(default="xtls-rprx-vision", max_length=80)
    server_name: str = Field(default="www.microsoft.com", max_length=255)
    dest: str = Field(default="www.microsoft.com:443", max_length=255)
    remark: str | None = Field(default=None, max_length=200)
    allow_install_xray: bool = False
    allow_modify_firewall: bool = False
    allow_generate_share_link: bool = False
    allow_overwrite_existing_config: bool = False
    cloud_security_group_confirmed: bool = False
    cloud_firewall_confirmed: bool = False
    server_firewall_confirmed: bool = False
    require_manual_cloud_firewall_confirmation: bool = True
    require_preflight_success: bool = True

    @field_validator("protocol", "security", "flow", "server_name", "dest")
    @classmethod
    def clean_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value cannot be empty")
        return cleaned

    @field_validator("remark")
    @classmethod
    def clean_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class LandingNodePlanResponse(BaseModel):
    plan_id: str
    server_id: str
    mode: str
    ready: bool
    will_install_xray: bool
    will_create_config: bool
    will_open_local_firewall: bool
    will_modify_cloud_security_group: bool
    listen_port: int
    protocol: str
    security: str
    flow: str
    server_name: str
    dest: str
    key_generation_strategy: dict[str, str]
    required_user_confirmations: list[str]
    preflight_summary: dict[str, Any]
    warnings: list[str]
    blocked_reasons: list[str]
    next_stage_required: str
    execution_guard: list[str]
    safety_boundary: list[str]
