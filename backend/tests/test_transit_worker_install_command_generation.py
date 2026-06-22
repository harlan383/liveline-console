import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import transit_resources
from app.models.transit_resource import TransitResource
from app.models.worker import WorkerToken
from app.schemas.transit_resource import (
    TRANSIT_WORKER_INSTALL_COMMAND_GENERATION_CONFIRMATION,
    TransitWorkerInstallCommandGenerationRequest,
)


class FakeAdminSession:
    admin_id = "admin-1"


def make_request(path: str = "/api/transit-resources/resource-1/worker-install-command") -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
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


class FakeScalarResult:
    def __init__(self, values):
        self.values = list(values)

    def all(self):
        return self.values


class FakeDb:
    def __init__(self, *, scalar_values=None, scalars_values=None):
        self.scalar_values = list(scalar_values or [])
        self.scalars_values = list(scalars_values or [])
        self.added: list[object] = []
        self.committed = False
        self.rolled_back = False

    def scalar(self, statement):
        if self.scalar_values:
            return self.scalar_values.pop(0)
        return None

    def scalars(self, statement):
        if self.scalars_values:
            return FakeScalarResult(self.scalars_values.pop(0))
        return FakeScalarResult([])

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def refresh(self, item):
        return None


def pending_resource(**overrides) -> TransitResource:
    data = {
        "id": "resource-1",
        "name": "new transit",
        "resource_type": "server",
        "entry_host": "203.0.113.10",
        "status": "pending_worker",
        "has_ssh": True,
        "ssh_host": "203.0.113.10",
        "ssh_port": 22,
        "ssh_username": "root",
    }
    data.update(overrides)
    return TransitResource(**data)


def valid_payload() -> TransitWorkerInstallCommandGenerationRequest:
    return TransitWorkerInstallCommandGenerationRequest(
        confirmation=TRANSIT_WORKER_INSTALL_COMMAND_GENERATION_CONFIRMATION,
        expires_in_minutes=60,
    )


class TransitWorkerInstallCommandGenerationTests(unittest.TestCase):
    def test_confirmation_mismatch_does_not_generate_token(self):
        db = FakeDb()
        payload = SimpleNamespace(confirmation="WRONG", expires_in_minutes=60)
        with patch.object(transit_resources, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_resources, "csrf_valid", return_value=True
        ), patch.object(transit_resources, "create_bound_worker_token") as create_token:
            response = transit_resources.generate_transit_resource_worker_install_command(
                "resource-1",
                payload,
                make_request(),
                db,
            )

        data = response_payload(response)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "CONFIRMATION_MISMATCH")
        create_token.assert_not_called()
        self.assertFalse(db.committed)

    def test_non_pending_resource_is_rejected(self):
        db = FakeDb(scalar_values=[pending_resource(status="active")])
        with patch.object(transit_resources, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_resources, "csrf_valid", return_value=True
        ), patch.object(transit_resources, "create_bound_worker_token") as create_token:
            response = transit_resources.generate_transit_resource_worker_install_command(
                "resource-1",
                valid_payload(),
                make_request(),
                db,
            )

        data = response_payload(response)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_RESOURCE_NOT_PENDING_WORKER")
        create_token.assert_not_called()

    def test_entry_host_is_required(self):
        db = FakeDb(scalar_values=[pending_resource(entry_host=None)])
        with patch.object(transit_resources, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_resources, "csrf_valid", return_value=True
        ), patch.object(transit_resources, "create_bound_worker_token") as create_token:
            response = transit_resources.generate_transit_resource_worker_install_command(
                "resource-1",
                valid_payload(),
                make_request(),
                db,
            )

        data = response_payload(response)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_RESOURCE_ENTRY_HOST_REQUIRED")
        create_token.assert_not_called()

    def test_success_generates_install_command_without_raw_token_field(self):
        resource = pending_resource(created_at=datetime.now(timezone.utc))
        old_token = WorkerToken(
            id="old-token",
            token_hash="hash",
            role="transit",
            status="active",
            name="old",
            server_id=resource.id,
            expires_at=datetime.now(timezone.utc),
        )
        new_token = WorkerToken(
            id="new-token",
            token_hash="new-hash",
            role="transit",
            status="active",
            name=resource.name,
            server_id=resource.id,
            expires_at=datetime.now(timezone.utc),
        )
        raw_token = "fixture-token-value"
        install_command = "curl -s http://example.invalid/setup-fixture | bash -s eth0 transit"
        db = FakeDb(scalar_values=[resource], scalars_values=[[], [old_token]])

        with patch.object(transit_resources, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_resources, "csrf_valid", return_value=True
        ), patch.object(
            transit_resources,
            "worker_public_base_url",
            return_value="http://my-con.golirong.xyz:8200",
        ), patch.object(
            transit_resources,
            "create_bound_worker_token",
            return_value=(new_token, raw_token, install_command),
        ):
            response = transit_resources.generate_transit_resource_worker_install_command(
                "resource-1",
                valid_payload(),
                make_request(),
                db,
            )

        data = response_payload(response)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["controller_url"], "http://my-con.golirong.xyz:8200")
        self.assertEqual(data["data"]["role"], "transit")
        self.assertEqual(data["data"]["install_command"], install_command)
        self.assertNotIn("worker_token", data["data"])
        self.assertNotIn("raw_token", data["data"])
        self.assertEqual(data["data"]["token"]["masked_token"], "fixtur...-value")
        self.assertEqual(old_token.status, "revoked")
        self.assertTrue(db.committed)


if __name__ == "__main__":
    unittest.main()
