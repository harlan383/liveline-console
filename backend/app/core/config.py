from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

WEAK_PRODUCTION_MARKERS = (
    "change-me",
    "changeme",
    "example",
    "placeholder",
    "replace-with",
    "default",
    "secret",
    "dev",
    "test",
    "local",
)


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
    auth_login_max_attempts: int = Field(default=5, alias="AUTH_LOGIN_MAX_ATTEMPTS")
    auth_login_window_seconds: int = Field(default=600, alias="AUTH_LOGIN_WINDOW_SECONDS")
    auth_login_lock_seconds: int = Field(default=900, alias="AUTH_LOGIN_LOCK_SECONDS")
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
    public_console_url: str = Field(default="", alias="PUBLIC_CONSOLE_URL")
    worker_public_base_url: str = Field(default="", alias="WORKER_PUBLIC_BASE_URL")

    model_config = SettingsConfigDict(case_sensitive=False, hide_input_in_errors=True)

    @field_validator("app_env")
    @classmethod
    def normalize_app_env(cls, value: str):
        return value.strip().lower()

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

    @field_validator(
        "session_ttl_seconds",
        "auth_login_max_attempts",
        "auth_login_window_seconds",
        "auth_login_lock_seconds",
    )
    @classmethod
    def positive_auth_limit(cls, value: int, info):
        if value < 1:
            env_name = info.field_name.upper()
            raise ValueError(f"{env_name} must be greater than 0")
        return value

    @model_validator(mode="after")
    def production_auth_guardrails(self):
        if self.app_env != "production":
            return self

        errors = []
        if not _looks_like_strong_production_secret(self.session_secret):
            errors.append(
                "SESSION_SECRET must be a strong non-placeholder value of at least 32 characters in production"
            )
        if not _looks_like_secure_password_hash(self.admin_password_hash):
            errors.append(
                "ADMIN_PASSWORD_HASH must be configured as a secure password hash in production"
            )
        if not self.cookie_secure:
            errors.append("COOKIE_SECURE must be true in production")
        if self.cookie_samesite not in {"lax", "strict", "none"}:
            errors.append("COOKIE_SAMESITE must be lax, strict, or none in production")

        if errors:
            raise ValueError("PRODUCTION_CONFIG_INVALID: " + "; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _contains_weak_marker(value: str) -> bool:
    lowered = value.strip().lower()
    return any(marker in lowered for marker in WEAK_PRODUCTION_MARKERS)


def _looks_like_strong_production_secret(value: str) -> bool:
    stripped = value.strip()
    return len(stripped) >= 32 and not _contains_weak_marker(stripped)


def _looks_like_secure_password_hash(value: str) -> bool:
    stripped = value.strip()
    if not stripped or _contains_weak_marker(stripped):
        return False

    try:
        algorithm, iterations_text, salt, digest = stripped.split("$", 3)
        iterations = int(iterations_text)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256" or iterations < 100_000:
        return False
    if len(salt) < 16 or len(digest) < 64:
        return False
    return all(character in "0123456789abcdefABCDEF" for character in salt + digest)
