import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import transit_resources
from app.models.transit_resource import TransitResource
from app.models.worker import Worker


class FakeAdminSession:
    admin_id = "admin-1"


def make_request(path: str = "/api/transit-resources/resource-1/worker-acceptance") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
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


class FakeDb:
    def __init__(self, scalar_values=None):
        self.scalar_values = list(scalar_values or [])
        self.added: list[object] = []
        self.committed = False
        self.rolled_back = False

    def scalar(self, statement):
        if self.scalar_values:
            return self.scalar_values.pop(0)
        return None

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def transit_resource(**overrides) -> TransitResource:
    data = {
        "id": "resource-1",
        "name": "new transit",
        "resource_type": "server",
        "entry_host": "203.0.113.10",
        "status": "pending_worker",
    }
    data.update(overrides)
    return TransitResource(**data)


def transit_worker(**overrides) -> Worker:
    data = {
        "id": "worker-1",
        "server_id": "resource-1",
        "role": "transit",
        "status": "online",
        "hostname": "transit-host",
        "interface_name": "eth0",
        "worker_version": transit_resources.EXPECTED_TRANSIT_WORKER_ACCEPTANCE_VERSION,
        "worker_secret_hash": "hash",
        "last_heartbeat_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return Worker(**data)


class TransitWorkerAcceptanceTests(unittest.TestCase):
    def call_endpoint(self, db):
        with patch.object(transit_resources, "require_admin_session", return_value=FakeAdminSession()):
            return transit_resources.get_transit_resource_worker_acceptance(
                "resource-1",
                make_request(),
                db,
            )

    def test_resource_not_found(self):
        db = FakeDb()
        response = self.call_endpoint(db)
        data = response_payload(response)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(data["error_code"], "TRANSIT_RESOURCE_NOT_FOUND")
        self.assertEqual(db.added, [])
        self.assertFalse(db.committed)

    def test_no_worker_found(self):
        db = FakeDb([transit_resource(), None])
        response = self.call_endpoint(db)
        data = response_payload(response)
        result = data["data"]
        self.assertTrue(data["success"])
        self.assertFalse(result["worker_found"])
        self.assertFalse(result["accepted"])
        self.assertTrue(result["blocked"])
        self.assertIn("手动执行安装命令", result["next_action"])
        self.assertEqual(db.added, [])
        self.assertFalse(db.committed)

    def test_worker_bound_but_offline(self):
        old_heartbeat = datetime.now(timezone.utc) - timedelta(hours=1)
        db = FakeDb([transit_resource(), transit_worker(last_heartbeat_at=old_heartbeat)])
        response = self.call_endpoint(db)
        result = response_payload(response)["data"]
        self.assertTrue(result["worker_found"])
        self.assertFalse(result["heartbeat_ok"])
        self.assertFalse(result["accepted"])
        self.assertIn("未在线", result["next_action"])
        self.assertEqual(db.added, [])
        self.assertFalse(db.committed)

    def test_worker_role_mismatch(self):
        db = FakeDb([transit_resource(), transit_worker(role="landing")])
        response = self.call_endpoint(db)
        result = response_payload(response)["data"]
        self.assertFalse(result["role_ok"])
        self.assertFalse(result["accepted"])
        self.assertIn("role 不正确", result["next_action"])
        self.assertEqual(db.added, [])
        self.assertFalse(db.committed)

    def test_worker_version_mismatch(self):
        db = FakeDb([transit_resource(), transit_worker(worker_version="0.1.23-stage-3.3.117")])
        response = self.call_endpoint(db)
        result = response_payload(response)["data"]
        self.assertFalse(result["version_ok"])
        self.assertFalse(result["accepted"])
        self.assertIn("版本不满足", result["next_action"])
        self.assertEqual(db.added, [])
        self.assertFalse(db.committed)

    def test_accepted_success(self):
        db = FakeDb([transit_resource(status="worker_online"), transit_worker()])
        response = self.call_endpoint(db)
        data = response_payload(response)
        result = data["data"]
        self.assertTrue(data["success"])
        self.assertTrue(result["worker_found"])
        self.assertTrue(result["server_binding_ok"])
        self.assertTrue(result["role_ok"])
        self.assertTrue(result["heartbeat_ok"])
        self.assertTrue(result["version_ok"])
        self.assertTrue(result["accepted"])
        self.assertFalse(result["blocked"])
        self.assertIn("acceptance passed", result["next_action"])
        self.assertTrue(any(check["id"] == "worker_command_not_created" and check["passed"] for check in result["checks"]))
        self.assertTrue(any(check["id"] == "token_not_exposed" and check["passed"] for check in result["checks"]))
        self.assertEqual(db.added, [])
        self.assertFalse(db.committed)


class TransitWorkerUpgradeAcceptanceTests(unittest.TestCase):
    def call_endpoint(self, db):
        with patch.object(transit_resources, "require_admin_session", return_value=FakeAdminSession()):
            return transit_resources.get_transit_resource_worker_upgrade_acceptance(
                "resource-1",
                make_request("/api/transit-resources/resource-1/worker-upgrade-acceptance"),
                db,
            )

    def assert_read_only(self, db):
        self.assertEqual(db.added, [])
        self.assertFalse(db.committed)
        self.assertFalse(db.rolled_back)

    def test_old_worker_version_requires_upgrade(self):
        db = FakeDb([transit_resource(status="worker_online"), transit_worker(worker_version="0.1.24-stage-3.3.122")])
        response = self.call_endpoint(db)
        result = response_payload(response)["data"]

        self.assertTrue(result["worker_found"])
        self.assertFalse(result["version_ok"])
        self.assertTrue(result["upgrade_required"])
        self.assertFalse(result["acceptance_passed"])
        self.assertTrue(result["blocked"])
        self.assertEqual(result["blocked_reason"], "Transit Worker must be upgraded before HAProxy TCP dry-run.")
        self.assertIn("手动升级", result["next_action"])
        self.assertFalse(result["worker_command_created"])
        self.assertFalse(result["transit_route_created"])
        self.assertFalse(result["share_link_read_or_written"])
        self.assertTrue(any(check["id"] == "worker_command_not_created" and check["passed"] for check in result["checks"]))
        self.assertTrue(any(check["id"] == "transit_route_not_created" and check["passed"] for check in result["checks"]))
        self.assertTrue(any(check["id"] == "share_link_not_read_or_written" and check["passed"] for check in result["checks"]))
        self.assert_read_only(db)

    def test_required_worker_version_passes_acceptance(self):
        db = FakeDb([transit_resource(status="worker_online"), transit_worker(worker_version="0.1.31-stage-3.3.175-hotfix-2-haproxy-systemd-run")])
        response = self.call_endpoint(db)
        result = response_payload(response)["data"]

        self.assertTrue(result["version_ok"])
        self.assertFalse(result["upgrade_required"])
        self.assertTrue(result["acceptance_passed"])
        self.assertFalse(result["blocked"])
        self.assertIsNone(result["blocked_reason"])
        self.assertIn("重新生成 HAProxy route dry-run", result["next_action"])
        self.assertFalse(result["worker_command_created"])
        self.assertFalse(result["transit_route_created"])
        self.assertFalse(result["share_link_read_or_written"])
        self.assert_read_only(db)

    def test_worker_offline_blocks_acceptance(self):
        old_heartbeat = datetime.now(timezone.utc) - timedelta(hours=1)
        db = FakeDb([transit_resource(status="worker_online"), transit_worker(last_heartbeat_at=old_heartbeat)])
        response = self.call_endpoint(db)
        result = response_payload(response)["data"]

        self.assertFalse(result["heartbeat_ok"])
        self.assertFalse(result["acceptance_passed"])
        self.assertTrue(result["blocked"])
        self.assertEqual(result["blocked_reason"], "Transit Worker must be online before HAProxy TCP dry-run.")
        self.assert_read_only(db)

    def test_non_transit_role_blocks_acceptance(self):
        db = FakeDb([transit_resource(status="worker_online"), transit_worker(role="landing")])
        response = self.call_endpoint(db)
        result = response_payload(response)["data"]

        self.assertFalse(result["role_ok"])
        self.assertFalse(result["acceptance_passed"])
        self.assertTrue(result["blocked"])
        self.assertEqual(result["blocked_reason"], "Transit Worker role must be transit.")
        self.assert_read_only(db)

    def test_missing_worker_version_blocks_acceptance(self):
        db = FakeDb([transit_resource(status="worker_online"), transit_worker(worker_version=None)])
        response = self.call_endpoint(db)
        result = response_payload(response)["data"]

        self.assertFalse(result["version_present"])
        self.assertFalse(result["version_ok"])
        self.assertFalse(result["acceptance_passed"])
        self.assertTrue(result["blocked"])
        self.assertEqual(result["blocked_reason"], "Transit Worker version is missing.")
        self.assert_read_only(db)


if __name__ == "__main__":
    unittest.main()
