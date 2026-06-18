import asyncio
import unittest
import json
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import workers as worker_routes
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand


def make_request(path: str, body: bytes | None = None, headers: dict[str, str] | None = None) -> Request:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    if body is not None and "content-length" not in {key.decode(): value.decode() for key, value in raw_headers}:
        raw_headers.append((b"content-length", str(len(body)).encode()))

    sent = False

    async def receive():
        nonlocal sent
        if body is None:
            raise AssertionError("request body should not be read")
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": raw_headers,
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "server": ("testserver", 80),
        },
        receive,
    )


def response_payload(response):
    if isinstance(response, JSONResponse):
        return json.loads(response.body)
    return response


class FakeSession:
    def __init__(self, command: WorkerCommand | None = None) -> None:
        self.command = command
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def get(self, model, key):
        if model is WorkerCommand and self.command and self.command.id == key:
            return self.command
        return None

    def add(self, item):
        self.added.append(item)

    def flush(self):
        return None

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def refresh(self, item):
        return None


def fake_worker() -> Worker:
    return Worker(
        id="worker-1",
        role="transit",
        status="online",
        worker_version="0.1.18-stage-3.3.72",
        worker_secret_hash="hash",
    )


def running_transit_route_command() -> WorkerCommand:
    return WorkerCommand(
        id="11111111-2222-3333-4444-555555555555",
        worker_id="worker-1",
        server_type="transit",
        server_id="1e222459-9fa2-4c62-800f-a3b35edb7df8",
        command_type="transit_route_create",
        status="running",
        attempts=1,
        created_at=datetime.now(timezone.utc),
    )


class WorkerCommandResultRouteTests(unittest.TestCase):
    def test_large_result_without_worker_auth_returns_401_without_reading_body(self):
        request = make_request(
            "/api/workers/commands/missing/result",
            body=None,
            headers={"content-length": str(256 * 1024)},
        )

        response = asyncio.run(worker_routes.worker_command_result("missing", request, None, None, FakeSession()))
        payload = response_payload(response)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(payload["error_code"], "WORKER_AUTH_REQUIRED")

    def test_large_result_for_missing_command_returns_404_without_reading_body(self):
        request = make_request(
            "/api/workers/commands/missing/result",
            body=None,
            headers={"content-length": str(256 * 1024), "x-worker-id": "worker-1", "x-worker-secret": "secret"},
        )

        with (
            patch.object(worker_routes, "authenticate_worker", return_value=(fake_worker(), None)),
            patch.object(worker_routes, "apply_worker_result_statement_timeout", return_value=None),
        ):
            response = asyncio.run(
                worker_routes.worker_command_result(
                    "missing",
                    request,
                    "worker-1",
                    "secret",
                    FakeSession(),
                )
            )
        payload = response_payload(response)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(payload["error_code"], "WORKER_COMMAND_NOT_FOUND")

    def test_transit_route_create_dry_run_result_completes_without_route_creation(self):
        command = running_transit_route_command()
        db = FakeSession(command)
        body = json.dumps(
            {
                "result": {
                    "execution_mode": "dry_run",
                    "real_execution": False,
                    "status": "approval_required",
                    "summary": "Transit route create dry-run accepted.",
                    "worker_version": "0.1.18-stage-3.3.72",
                    "hostname": "WEPC202605221223335",
                    "role": "transit",
                    "interface_name": "eth0",
                    "planned_listen_port": 23843,
                    "landing_target_host": "64.90.13.19",
                    "landing_target_port": 27939,
                    "forwarding_method": "socat",
                    "route_name": "hk-socat-live-23843",
                    "checks_count": 5,
                    "checks": [{"name": "dry_run_required", "passed": True}],
                    "planned_service": {"exec_start": "must not survive normalization"},
                }
            }
        ).encode()
        request = make_request(
            f"/api/workers/commands/{command.id}/result",
            body=body,
            headers={"x-worker-id": "worker-1", "x-worker-secret": "secret"},
        )

        with (
            patch.object(worker_routes, "authenticate_worker", return_value=(fake_worker(), None)),
            patch.object(worker_routes, "apply_worker_result_statement_timeout", return_value=None),
        ):
            response = asyncio.run(
                worker_routes.worker_command_result(command.id, request, "worker-1", "secret", db)
            )
        payload = response_payload(response)

        self.assertTrue(payload["success"])
        self.assertEqual(command.status, "succeeded")
        self.assertEqual(command.result_json["execution_mode"], "dry_run")
        self.assertFalse(command.result_json["real_execution"])
        self.assertNotIn("planned_service", command.result_json)
        self.assertFalse(any(type(item).__name__ == "TransitRoute" for item in db.added))

    def test_large_failure_payload_marks_command_failed(self):
        command = running_transit_route_command()
        db = FakeSession(command)
        body = json.dumps(
            {
                "error_message": "x" * 5000,
                "result": {
                    "command_type": "transit_route_create",
                    "summary": "x" * 5000,
                    "checks": [{"name": "dry_run_required", "passed": True, "detail": "x" * 5000}],
                    "safety_boundary": ["no listener", "no firewall", "no cutover"],
                },
            }
        ).encode()
        request = make_request(
            f"/api/workers/commands/{command.id}/fail",
            body=body,
            headers={"x-worker-id": "worker-1", "x-worker-secret": "secret"},
        )

        with (
            patch.object(worker_routes, "authenticate_worker", return_value=(fake_worker(), None)),
            patch.object(worker_routes, "apply_worker_result_statement_timeout", return_value=None),
        ):
            response = asyncio.run(
                worker_routes.worker_command_fail(command.id, request, "worker-1", "secret", db)
            )
        payload = response_payload(response)

        self.assertTrue(payload["success"])
        self.assertEqual(command.status, "failed")
        self.assertIsNotNone(command.result_json)
        self.assertNotEqual(command.status, "running")
        self.assertFalse(any(type(item).__name__ == "TransitRoute" for item in db.added))


if __name__ == "__main__":
    unittest.main()
