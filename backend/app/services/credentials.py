import base64
import hashlib
import json
import uuid

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.db.redis import get_redis_client


class TempCredentialExpired(Exception):
    pass


class TempCredentialDecryptFailed(Exception):
    pass


def _fernet() -> Fernet:
    settings = get_settings()
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.encryption_key.encode("utf-8")).digest()
    )
    return Fernet(key)


def store_temp_credential(private_key: str, passphrase: str | None) -> str:
    settings = get_settings()
    credential_id = str(uuid.uuid4())
    payload = json.dumps(
        {
            "private_key": private_key,
            "passphrase": passphrase or "",
        }
    ).encode("utf-8")
    encrypted = _fernet().encrypt(payload).decode("utf-8")
    redis_client = get_redis_client()
    redis_client.setex(
        f"temp_credential:{credential_id}",
        settings.temp_credential_ttl_seconds,
        encrypted,
    )
    return credential_id


def pop_temp_credential(credential_id: str) -> tuple[str, str | None]:
    redis_client = get_redis_client()
    key = f"temp_credential:{credential_id}"
    pipe = redis_client.pipeline()
    pipe.get(key)
    pipe.delete(key)
    encrypted, _ = pipe.execute()
    if not encrypted:
        raise TempCredentialExpired()

    try:
        payload = json.loads(_fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8"))
    except (InvalidToken, json.JSONDecodeError) as exc:
        raise TempCredentialDecryptFailed() from exc

    private_key = payload.get("private_key")
    if not private_key:
        raise TempCredentialDecryptFailed()

    passphrase = payload.get("passphrase") or None
    return private_key, passphrase
