from pydantic import BaseModel, Field, field_validator


REMOTE_CLEANUP_CONFIRMATION = "CONFIRM_REMOTE_DELETE"
OFFLINE_LOCAL_REMOVE_CONFIRMATION = "CONFIRM_OFFLINE_LOCAL_REMOVE"


class RemoteCleanupDeleteRequest(BaseModel):
    confirm: str = Field(min_length=1, max_length=64)

    @field_validator("confirm")
    @classmethod
    def require_remote_cleanup_confirmation(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned not in {REMOTE_CLEANUP_CONFIRMATION, OFFLINE_LOCAL_REMOVE_CONFIRMATION}:
            raise ValueError("confirm must be CONFIRM_REMOTE_DELETE or CONFIRM_OFFLINE_LOCAL_REMOVE")
        return cleaned
