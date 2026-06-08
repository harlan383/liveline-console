from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field(default="local", alias="APP_ENV")
    database_url: str = Field(alias="DATABASE_URL")
    redis_url: str = Field(alias="REDIS_URL")
    encryption_key: str = Field(default="", alias="ENCRYPTION_KEY")
    session_secret: str = Field(default="", alias="SESSION_SECRET")
    init_token: str = Field(default="", alias="INIT_TOKEN")
    admin_username: str = Field(default="", alias="ADMIN_USERNAME")
    admin_password_hash: str = Field(default="", alias="ADMIN_PASSWORD_HASH")
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")
    cookie_samesite: str = Field(default="lax", alias="COOKIE_SAMESITE")
    session_ttl_seconds: int = Field(default=86400, alias="SESSION_TTL_SECONDS")
    temp_credential_ttl_seconds: int = Field(
        default=1800,
        alias="TEMP_CREDENTIAL_TTL_SECONDS",
    )
    ssh_connect_timeout_seconds: int = Field(default=15, alias="SSH_CONNECT_TIMEOUT_SECONDS")
    ssh_command_timeout_seconds: int = Field(default=10, alias="SSH_COMMAND_TIMEOUT_SECONDS")
    ssh_install_timeout_seconds: int = Field(default=300, alias="SSH_INSTALL_TIMEOUT_SECONDS")
    frontend_origin: str = Field(
        default="http://localhost:3000",
        alias="FRONTEND_ORIGIN",
    )

    model_config = SettingsConfigDict(case_sensitive=False)

    @field_validator("encryption_key", "session_secret")
    @classmethod
    def required_secret(cls, value: str, info):
        if not value or not value.strip():
            env_name = info.field_name.upper()
            raise ValueError(f"ENV_REQUIRED_MISSING: {env_name} is required")
        return value

    @field_validator("cookie_samesite")
    @classmethod
    def valid_samesite(cls, value: str):
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("COOKIE_SAMESITE must be lax, strict, or none")
        return normalized


@lru_cache
def get_settings() -> Settings:
    return Settings()
