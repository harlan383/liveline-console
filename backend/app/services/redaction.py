from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any


LINK_RE = re.compile(r"\b(vless|vmess|ss)://[^\s\"'<>]+", re.IGNORECASE)
ASSIGNMENT_SECRET_RE = re.compile(
    r"(?i)\b(password|passphrase|token|session_secret|admin_password_hash|private[_-]?key)\s*=\s*[^\s\"']+"
)

SENSITIVE_VALUE_KEYS = {
    "share_link",
    "secure_share_link",
    "client_link",
    "exported_share_link",
    "reality_private_key",
    "private_key",
    "ssh_private_key",
    "ssh_key",
    "passphrase",
    "password",
    "token",
    "worker_token",
    "session_secret",
    "admin_password_hash",
    "cookie",
    "session",
}

NODE_MATERIAL_KEYS = {
    "uuid",
    "client_uuid",
    "reality_public_key",
    "public_key",
    "reality_short_id",
    "short_id",
}


def mask_share_link(share_link: str | None) -> str | None:
    if not share_link:
        return None
    if "://" in share_link:
        scheme = share_link.split("://", 1)[0]
        return f"{scheme}://[redacted]"
    return "[redacted]"


def mask_identifier(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "[redacted]"
    return f"{value[:4]}...[redacted]...{value[-4:]} ({len(value)} chars)"


def redact_text(value: str) -> str:
    redacted = LINK_RE.sub(lambda match: f"{match.group(1)}://[redacted]", value)
    return ASSIGNMENT_SECRET_RE.sub(lambda match: f"{match.group(1)}=[redacted]", redacted)


def redact_sensitive_payload(value: Any, *, key: str | None = None) -> Any:
    key_name = (key or "").lower()
    if isinstance(value, str):
        if key_name in SENSITIVE_VALUE_KEYS:
            return mask_share_link(value) if "link" in key_name else "[redacted]"
        if key_name in NODE_MATERIAL_KEYS:
            return mask_identifier(value)
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            item_key: redact_sensitive_payload(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [redact_sensitive_payload(item) for item in value]
    return value
