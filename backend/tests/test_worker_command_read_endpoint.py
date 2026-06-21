import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import workers
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand


def make_request(command_id: str = "command-1") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": f"/api/workers/commands/{command_id}",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )


def response_payload(response):
    if isinstance(response, JSONResponse):
        return json.loads(response.body)
    return response


class FakeAdminSession:
    admin_id = "admin-1"


class FakeSession:
    def __init__(self, command: WorkerCommand | None) -> None:
        self.command = command
        self.worker = Worker(
            id="worker-1",
            server_id="server-1",
            role="transit",
            status="online",
            worker_version="0.1.22-stage-3.3.107",
            worker_secret_hash="hash",
            last_heartbeat_at=datetime.now(timezone.utc),
        )

    def get(self, model, key):
        if model is WorkerCommand and self.command and key == self.command.id:
            return self.command
        if model is Worker and key == self.worker.id:
            return self.worker
        return None


def command(status: str, result_json: dict | None = None) -> WorkerCommand:
    return WorkerCommand(
        id=f"{status}-command",
        worker_id="worker-1",
        server_type="transit",
        server_id="server-1",
        command_type="transit_readonly_preflight",
        status=status,
        result_json=result_json or {},
        error_message=None,
        attempts=1,
        created_at=datetime.now(timezone.utc),
        claimed_at=datetime.now(timezone.utc) if status != "pending" else None,
        completed_at=datetime.now(timezone.utc) if status == "succeeded" else None,
    )


def call_get(command_id: str, db: FakeSession):
    with patch.object(workers, "require_admin_session", return_value=FakeAdminSession()):
        return workers.get_admin_worker_command(command_id, make_request(command_id), db)


class WorkerCommandReadEndpointTests(unittest.TestCase):
    def test_get_worker_command_reads_pending_command(self):
        db = FakeSession(command("pending"))
        response = call_get("pending-command", db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["id"], "pending-command")
        self.assertEqual(data["data"]["status"], "pending")
        self.assertEqual(data["data"]["target_worker_version"], "0.1.22-stage-3.3.107")

    def test_get_worker_command_reads_succeeded_command(self):
        db = FakeSession(command("succeeded", {"status": "passed", "summary": "ok"}))
        response = call_get("succeeded-command", db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["id"], "succeeded-command")
        self.assertEqual(data["data"]["status"], "succeeded")
        self.assertEqual(data["data"]["result_json"]["status"], "passed")

    def test_get_worker_command_missing_returns_404(self):
        response = call_get("missing", FakeSession(None))
        data = response_payload(response)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], "WORKER_COMMAND_NOT_FOUND")

    def test_get_worker_command_redacts_sensitive_result_fields(self):
        result = {
            "share_link": "redacted-share-link-placeholder",
            "secure_share_link": "redacted-share-link-placeholder",
            "candidate_link": "redacted-share-link-placeholder",
            "client_link": "redacted-share-link-placeholder",
            "vless_link": "redacted-share-link-placeholder",
            "uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "privateKey": "private-key-value",
            "shortId": "short-id-value",
            "safe_summary": "ok",
        }
        response = call_get("succeeded-command", FakeSession(command("succeeded", result)))
        data = response_payload(response)
        serialized = data["data"]["result_json"]

        self.assertEqual(serialized["share_link"], "[redacted]")
        self.assertEqual(serialized["secure_share_link"], "[redacted]")
        self.assertEqual(serialized["candidate_link"], "[redacted]")
        self.assertEqual(serialized["client_link"], "[redacted]")
        self.assertEqual(serialized["vless_link"], "[redacted]")
        self.assertEqual(serialized["uuid"], "[redacted]")
        self.assertEqual(serialized["privateKey"], "[redacted]")
        self.assertEqual(serialized["shortId"], "[redacted]")
        self.assertEqual(serialized["safe_summary"], "ok")
        self.assertNotIn("vless://", json.dumps(serialized))


if __name__ == "__main__":
    unittest.main()
