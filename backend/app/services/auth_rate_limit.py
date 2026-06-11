import hashlib
import hmac
from dataclasses import dataclass

from fastapi import Request
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.db.redis import get_redis_client
from app.services.auth_service import client_ip

RATE_LIMIT_PREFIX = "auth_login_rate"


@dataclass(frozen=True)
class LoginRateLimitResult:
    limited: bool
    retry_after_seconds: int | None = None


def _rate_limit_key(request: Request, username: str) -> str:
    settings = get_settings()
    ip_address = client_ip(request) or "unknown"
    normalized_username = username.strip().lower()[:160]
    raw_identifier = f"{ip_address}\0{normalized_username}"
    digest = hmac.new(
        settings.session_secret.encode("utf-8"),
        raw_identifier.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{RATE_LIMIT_PREFIX}:{digest}"


def check_login_rate_limit(request: Request, username: str) -> LoginRateLimitResult:
    base_key = _rate_limit_key(request, username)
    lock_key = f"{base_key}:lock"

    try:
        redis = get_redis_client()
        is_locked = redis.exists(lock_key)
        if not is_locked:
            return LoginRateLimitResult(limited=False)

        ttl = redis.ttl(lock_key)
        retry_after = ttl if ttl and ttl > 0 else None
        return LoginRateLimitResult(limited=True, retry_after_seconds=retry_after)
    except RedisError:
        return LoginRateLimitResult(limited=False)


def record_login_failure(request: Request, username: str) -> LoginRateLimitResult:
    settings = get_settings()
    base_key = _rate_limit_key(request, username)
    attempts_key = f"{base_key}:attempts"
    lock_key = f"{base_key}:lock"

    try:
        redis = get_redis_client()
        attempts = redis.incr(attempts_key)
        if attempts == 1:
            redis.expire(attempts_key, settings.auth_login_window_seconds)

        if attempts >= settings.auth_login_max_attempts:
            redis.set(lock_key, "1", ex=settings.auth_login_lock_seconds)
            redis.delete(attempts_key)
            return LoginRateLimitResult(
                limited=True,
                retry_after_seconds=settings.auth_login_lock_seconds,
            )
    except RedisError:
        return LoginRateLimitResult(limited=False)

    return LoginRateLimitResult(limited=False)


def clear_login_failures(request: Request, username: str) -> None:
    base_key = _rate_limit_key(request, username)
    try:
        redis = get_redis_client()
        redis.delete(f"{base_key}:attempts", f"{base_key}:lock")
    except RedisError:
        return
