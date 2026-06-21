import json
import unittest
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import workers as worker_routes
from app.models.worker import Worker
from app.schemas.workers import WorkerHeartbeatRequest


def make_request(path: str = "/api/workers/heartbeat") -> Request:
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


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.commits = 0

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commits += 1


def worker(status: str = "online", cleanup_expected: bool = False) -> Worker:
    metadata = {"cleanup_status": "cleanup_expected_offline"} if cleanup_expected else {"registered_at": "now"}
    return Worker(
        id="worker-1",
        role="transit",
        server_id="resource-1",
        status=status,
        worker_version="0.1.21-stage-3.3.97",
        worker_secret_hash="hash",
        metadata_json=metadata,
    )


class WorkerHeartbeatCleanupStateTests(unittest.TestCase):
    def heartbeat(self, target: Worker):
        payload = WorkerHeartbeatRequest(
            worker_version="0.1.21-stage-3.3.97",
            hostname="WEPC202605221223335",
            interface_name="eth0",
            services={"liveline_worker": {"systemd_active": "active"}},
        )
        db = FakeSession()
        with (
            patch.object(worker_routes, "authenticate_worker", return_value=(target, None)),
            patch.object(worker_routes, "sync_worker_bound_resource_status") as sync_resource,
            patch.object(worker_routes, "try_bind_worker_by_public_ip") as try_bind,
        ):
            response = worker_routes.worker_heartbeat(payload, make_request(), "worker-1", "secret", db)
        return response_payload(response), db, sync_resource, try_bind

    def test_deleted_worker_heartbeat_does_not_revive_online(self):
        target = worker(status="deleted", cleanup_expected=True)

        payload, db, sync_resource, try_bind = self.heartbeat(target)

        self.assertTrue(payload["success"])
        self.assertEqual(target.status, "deleted")
        self.assertIsNotNone(target.last_heartbeat_at)
        self.assertTrue(target.metadata_json["unexpected_heartbeat_after_cleanup"])
        self.assertIn("unexpected_heartbeat_at", target.metadata_json)
        self.assertEqual(
            target.metadata_json["latest_status"]["services"]["liveline_worker"]["systemd_active"],
            "active",
        )
        sync_resource.assert_not_called()
        try_bind.assert_not_called()
        self.assertEqual(db.commits, 1)

    def test_cleanup_expected_worker_heartbeat_does_not_become_online(self):
        target = worker(status="cleanup_pending", cleanup_expected=True)

        payload, _, sync_resource, try_bind = self.heartbeat(target)

        self.assertTrue(payload["success"])
        self.assertEqual(target.status, "cleanup_pending")
        self.assertTrue(target.metadata_json["unexpected_heartbeat_after_cleanup"])
        sync_resource.assert_not_called()
        try_bind.assert_not_called()

    def test_normal_worker_heartbeat_still_sets_online_and_syncs_resource(self):
        target = worker(status="offline", cleanup_expected=False)

        payload, _, sync_resource, try_bind = self.heartbeat(target)

        self.assertTrue(payload["success"])
        self.assertEqual(target.status, "online")
        self.assertIsNotNone(target.last_heartbeat_at)
        self.assertEqual(target.metadata_json["latest_status"]["hostname"], "WEPC202605221223335")
        sync_resource.assert_called_once()
        try_bind.assert_not_called()


if __name__ == "__main__":
    unittest.main()
