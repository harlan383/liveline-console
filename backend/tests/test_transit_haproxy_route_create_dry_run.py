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
from app.schemas.transit_route import TransitHaproxyRouteCreateDryRunRequest

TRANSIT_RESOURCE_ID = "80ec346d-3ac1-402e-ab09-33cb404ca81c"
TRANSIT_WORKER_ID = "f2e16197-e953-46dd-90af-66f64759a2a9"
LANDING_NODE_ID = "a71472c6-f62c-43b5-a223-9f5f070ae4ef"
LANDING_VPS_ID = "968519b3-9017-4b27-a9a0-d5731033f84f"


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/transit-routes/haproxy-route-create-dry-run",
            "headers": [(b"x-csrf-token", b"test")],
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
        worker_version: str | None = "0.1.30-stage-3.3.175-hotfix-1-haproxy-install-runner",
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

    def flush(self):
        for item in self.added:
            if isinstance(item, WorkerCommand) and not item.id:
                item.id = "dry-run-command"

    def commit(self):
        self.commit_called = True

    def refresh(self, item):
        return None


def valid_payload(**overrides):
    payload = {
        "transit_resource_id": TRANSIT_RESOURCE_ID,
        "landing_node_id": LANDING_NODE_ID,
        "planned_listen_port": 12081,
        "landing_target_host": "64.90.13.19",
        "landing_target_port": 27939,
        "forwarding_method": "haproxy_tcp",
        "purpose": "直播",
        "route_name": "haproxy-tcp-12081",
        "readiness_approval_confirmed": True,
        "dry_run": True,
        "approval_required": True,
        "firewall_security_group_confirmed": True,
        "cloud_firewall_confirmed": True,
        "server_firewall_confirmed": True,
        "no_cutover_confirmed": True,
        "no_node_share_link_change_confirmed": True,
        "no_full_client_link_confirmed": True,
    }
    payload.update(overrides)
    return TransitHaproxyRouteCreateDryRunRequest(**payload)


def call_dry_run(payload, db):
    with (
        patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()),
        patch.object(transit_routes, "csrf_valid", return_value=True),
    ):
        return transit_routes.create_haproxy_route_create_dry_run(payload, make_request(), db)


class TransitHaproxyRouteCreateDryRunTests(unittest.TestCase):
    def assert_rejected_without_command(self, db: FakeSession, payload, expected_code: str):
        response = call_dry_run(payload, db)
        data = response_payload(response)

        self.assertFalse(data["success"])
        self.assertEqual(data["error_code"], expected_code)
        self.assertEqual([item for item in db.added if isinstance(item, WorkerCommand)], [])
        self.assertEqual([item for item in db.added if isinstance(item, TransitRoute)], [])
        self.assertFalse(db.commit_called)

    def test_resource_missing_rejected(self):
        self.assert_rejected_without_command(
            FakeSession(resource_present=False),
            valid_payload(),
            "HAPROXY_READINESS_NOT_READY",
        )

    def test_worker_missing_rejected(self):
        self.assert_rejected_without_command(
            FakeSession(worker_present=False),
            valid_payload(),
            "HAPROXY_READINESS_NOT_READY",
        )

    def test_worker_offline_rejected(self):
        self.assert_rejected_without_command(
            FakeSession(worker_heartbeat_recent=False),
            valid_payload(),
            "HAPROXY_READINESS_NOT_READY",
        )

    def test_worker_wrong_role_rejected(self):
        self.assert_rejected_without_command(
            FakeSession(worker_role="landing"),
            valid_payload(),
            "HAPROXY_READINESS_NOT_READY",
        )

    def test_worker_version_unsupported_rejected(self):
        self.assert_rejected_without_command(
            FakeSession(worker_version="0.1.23-stage-3.3.117"),
            valid_payload(),
            "HAPROXY_READINESS_NOT_READY",
        )

    def test_worker_interface_missing_rejected(self):
        self.assert_rejected_without_command(
            FakeSession(worker_interface=None),
            valid_payload(),
            "HAPROXY_READINESS_NOT_READY",
        )

    def test_landing_node_missing_rejected(self):
        self.assert_rejected_without_command(
            FakeSession(node_present=False),
            valid_payload(),
            "HAPROXY_READINESS_NOT_READY",
        )

    def test_invalid_schema_port_rejected_before_endpoint(self):
        with self.assertRaises(Exception):
            valid_payload(planned_listen_port=0)

    def test_reserved_listen_port_rejected(self):
        self.assert_rejected_without_command(
            FakeSession(),
            valid_payload(planned_listen_port=22),
            "HAPROXY_READINESS_NOT_READY",
        )

    def test_missing_firewall_confirmations_rejected(self):
        self.assert_rejected_without_command(
            FakeSession(),
            valid_payload(firewall_security_group_confirmed=False),
            "SECURITY_GROUP_CONFIRMATION_REQUIRED",
        )
        self.assert_rejected_without_command(
            FakeSession(),
            valid_payload(cloud_firewall_confirmed=False),
            "CLOUD_FIREWALL_CONFIRMATION_REQUIRED",
        )
        self.assert_rejected_without_command(
            FakeSession(),
            valid_payload(server_firewall_confirmed=False),
            "SERVER_FIREWALL_CONFIRMATION_REQUIRED",
        )

    def test_missing_safety_confirmations_rejected(self):
        self.assert_rejected_without_command(
            FakeSession(),
            valid_payload(no_cutover_confirmed=False),
            "NO_CUTOVER_CONFIRMATION_REQUIRED",
        )
        self.assert_rejected_without_command(
            FakeSession(),
            valid_payload(no_node_share_link_change_confirmed=False),
            "NODE_SHARE_LINK_BOUNDARY_REQUIRED",
        )
        self.assert_rejected_without_command(
            FakeSession(),
            valid_payload(no_full_client_link_confirmed=False),
            "NO_FULL_CLIENT_LINK_CONFIRMATION_REQUIRED",
        )

    def test_success_creates_only_dry_run_worker_command(self):
        db = FakeSession()
        original_share_link = db.node.share_link if db.node else None
        response = call_dry_run(valid_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["dry_run"])
        self.assertTrue(data["data"]["approval_required"])
        self.assertFalse(data["data"]["real_execution"])
        self.assertFalse(data["data"]["route_created"])
        self.assertFalse(data["data"]["haproxy_installed"])
        self.assertFalse(data["data"]["listener_bound"])
        self.assertFalse(data["data"]["firewall_modified"])
        self.assertFalse(data["data"]["share_link_mutated"])
        self.assertFalse(data["data"]["cutover"])
        self.assertEqual(data["data"]["command"]["command_type"], "transit_route_create")
        self.assertEqual(data["data"]["command"]["payload"]["command_intent"], "haproxy_route_create_dry_run")
        self.assertTrue(data["data"]["command"]["payload"]["dry_run"])
        self.assertFalse(data["data"]["command"]["payload"]["real_execution"])
        self.assertFalse(data["data"]["command"]["payload"]["user_approved_real_execution"])
        self.assertEqual(data["data"]["forwarding_method"], "haproxy_tcp")
        self.assertEqual(data["data"]["planned_service_name"], "liveline-haproxy-12081.service")
        command_payload = data["data"]["command"]["payload"]
        haproxy_config_plan = command_payload["haproxy_config_plan"]
        self.assertEqual(command_payload["planned_service_name"], "liveline-haproxy-12081.service")
        self.assertEqual(haproxy_config_plan["mode"], "tcp")
        self.assertEqual(haproxy_config_plan["frontend_bind"], "*:12081")
        self.assertEqual(haproxy_config_plan["backend_target"], "64.90.13.19:27939")
        self.assertNotIn("service_name", haproxy_config_plan)
        self.assertEqual(data["data"]["next_stage"], "Stage 3.3.138-new-transit-haproxy-route-create-final-approval")
        self.assertEqual(db.node.share_link if db.node else None, original_share_link)
        self.assertEqual(len([item for item in db.added if isinstance(item, WorkerCommand)]), 1)
        self.assertEqual([item for item in db.added if isinstance(item, TransitRoute)], [])
        self.assertFalse(
            any(
                isinstance(item, WorkerCommand) and item.payload_json and item.payload_json.get("dry_run") is False
                for item in db.added
            )
        )
        self.assertTrue(db.commit_called)


if __name__ == "__main__":
    unittest.main()
