from pydantic import BaseModel


class ReadNodeResponse(BaseModel):
    task_id: str
    vps_id: str


class ConfirmHostKeyRequest(BaseModel):
    ssh_host_key_fingerprint: str
