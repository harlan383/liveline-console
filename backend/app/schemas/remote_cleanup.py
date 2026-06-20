from pydantic import BaseModel, Field, field_validator


REMOTE_CLEANUP_CONFIRMATION = "CONFIRM_REMOTE_DELETE"


class RemoteCleanupDeleteRequest(BaseModel):
    confirm: str = Field(min_length=1, max_length=64)

    @field_validator("confirm")
    @classmethod
    def require_remote_cleanup_confirmation(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned != REMOTE_CLEANUP_CONFIRMATION:
            raise ValueError("confirm must be CONFIRM_REMOTE_DELETE")
        return cleaned
