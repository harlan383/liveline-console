import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import transit_routes
from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand
from app.schemas.transit_route import TransitHaproxyReadinessApprovalRequest

TRANSIT_RESOURCE_ID = "80ec346d-3ac1-402e-ab09-33cb404ca81c"
TRANSIT_WORKER_ID = "f2e16197-e953-46dd-90af-66f64759a2a9"
LANDING_NODE_ID = "a71472c6-f62c-43b5-a223-9f5f070ae4ef"
LANDING_VPS_ID = "968519b3-9017-4b27-a9a0-d5731033f84f"


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/transit-routes/haproxy-readiness-approval",
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


class FakeScalarResult:
    def __init__(self, items: list[object]) -> None:
        self.items = items

    def all(self):
        return self.items


class FakeSession:
    def __init__(
        self,
        *,
        resource_present: bool = True,
        resource_deleted: bool = False,
        node_present: bool = True,
        node_deleted: bool = False,
        node_has_vps: bool = True,
        node_port: int | None = 27939,
        worker_present: bool = True,
        worker_status: str = "online",
        worker_role: str = "transit",
        worker_version: str | None = "0.1.29-stage-3.3.175-haproxy-auto-install",
        worker_interface: str | None = "eth0",
        worker_heartbeat_recent: bool = True,
    ) -> None:
        self.added: list[object] = []
        self.commit_called = False
        self.resource = (
            TransitResource(
                id=TRANSIT_RESOURCE_ID,
                name="mkiepl广港",
                resource_type="server",
                status="worker_online",
                entry_host="109.244.79.147",
                entry_port=22,
            )
            if resource_present
            else None
        )
        if self.resource and resource_deleted:
            self.resource.deleted_at = datetime.now(timezone.utc)
        self.node = (
            Node(
                id=LANDING_NODE_ID,
                vps_id=LANDING_VPS_ID,
                node_name="liveline-reality-27939",
                xray_port=node_port,
                status="active",
                share_link="redacted-share-link-present",
            )
            if node_present
            else None
        )
        if self.node and node_deleted:
            self.node.deleted_at = datetime.now(timezone.utc)
        if self.node and node_has_vps:
            self.node.vps = VpsServer(id=LANDING_VPS_ID, ip="64.90.13.19")
        self.worker = (
            Worker(
                id=TRANSIT_WORKER_ID,
                server_id=TRANSIT_RESOURCE_ID,
                role=worker_role,
                status=worker_status,
                interface_name=worker_interface,
                worker_version=worker_version,
                worker_secret_hash="hash",
                last_heartbeat_at=(
                    datetime.now(timezone.utc)
                    if worker_heartbeat_recent
                    else datetime.now(timezone.utc) - timedelta(hours=1)
                ),
            )
            if worker_present
            else None
        )

    def get(self, model, key):
        if model is TransitResource and self.resource and key == self.resource.id:
            return self.resource
        if model is Node and self.node and key == self.node.id:
            return self.node
        return None

    def scalars(self, statement):
        return FakeScalarResult([self.worker] if self.worker else [])

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commit_called = True


def valid_payload(**overrides):
    payload = {
        "transit_resource_id": TRANSIT_RESOURCE_ID,
        "landing_node_id": LANDING_NODE_ID,
        "planned_listen_port": 12081,
        "landing_target_port": 27939,
        "forwarding_method": "haproxy_tcp",
        "purpose": "直播",
        "firewall_security_group_confirmed": True,
        "cloud_firewall_confirmed": True,
        "server_firewall_confirmed": True,
        "no_cutover_confirmed": True,
        "no_node_share_link_change_confirmed": True,
        "no_full_client_link_confirmed": True,
    }
    payload.update(overrides)
    return TransitHaproxyReadinessApprovalRequest(**payload)


def call_readiness(payload, db):
    with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()):
        return transit_routes.haproxy_readiness_approval(payload, make_request(), db)


def check_map(data):
    return {check["id"]: check for check in data["data"]["checks"]}


class TransitHaproxyReadinessApprovalTests(unittest.TestCase):
    def assert_readiness_blocked_by(self, db: FakeSession, check_id: str, payload=None):
        response = call_readiness(payload or valid_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["ready"])
        self.assertTrue(data["data"]["blocked"])
        self.assertFalse(check_map(data)[check_id]["passed"])
        self.assertEqual(db.added, [])
        self.assertFalse(db.commit_called)
        return data

    def test_resource_not_found_blocks_readiness(self):
        self.assert_readiness_blocked_by(FakeSession(resource_present=False), "transit_resource_exists")

    def test_worker_missing_blocks_readiness(self):
        self.assert_readiness_blocked_by(FakeSession(worker_present=False), "transit_worker_found")

    def test_worker_offline_blocks_readiness(self):
        self.assert_readiness_blocked_by(FakeSession(worker_heartbeat_recent=False), "transit_worker_online")

    def test_worker_wrong_role_blocks_readiness(self):
        self.assert_readiness_blocked_by(FakeSession(worker_role="landing"), "transit_worker_role_is_transit")

    def test_worker_version_unsupported_blocks_readiness(self):
        self.assert_readiness_blocked_by(
            FakeSession(worker_version="0.1.23-stage-3.3.117"),
            "transit_worker_version_supported",
        )

    def test_worker_interface_missing_blocks_readiness(self):
        self.assert_readiness_blocked_by(FakeSession(worker_interface=None), "transit_worker_interface_detected")

    def test_landing_node_missing_blocks_readiness(self):
        self.assert_readiness_blocked_by(FakeSession(node_present=False), "landing_node_exists")

    def test_invalid_listen_port_blocks_readiness(self):
        self.assert_readiness_blocked_by(FakeSession(), "planned_listen_port_valid", valid_payload(planned_listen_port=22))

    def test_missing_firewall_confirmation_blocks_readiness(self):
        self.assert_readiness_blocked_by(
            FakeSession(),
            "security_group_confirmation_present",
            valid_payload(firewall_security_group_confirmed=False),
        )

    def test_ready_success_is_read_only_and_does_not_mutate_links_or_create_records(self):
        db = FakeSession()
        original_share_link = db.node.share_link if db.node else None
        response = call_readiness(valid_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["ready"])
        self.assertFalse(data["data"]["blocked"])
        self.assertEqual(data["data"]["planned_route"]["forwarding_method"], "haproxy_tcp")
        self.assertTrue(check_map(data)["worker_command_not_created"]["passed"])
        self.assertTrue(check_map(data)["haproxy_not_created"]["passed"])
        self.assertTrue(check_map(data)["firewall_not_modified"]["passed"])
        self.assertEqual(db.node.share_link if db.node else None, original_share_link)
        self.assertEqual([item for item in db.added if isinstance(item, WorkerCommand)], [])
        self.assertEqual([item for item in db.added if isinstance(item, TransitRoute)], [])
        self.assertFalse(db.commit_called)


if __name__ == "__main__":
    unittest.main()
