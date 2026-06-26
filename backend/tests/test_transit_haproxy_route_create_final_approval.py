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
from app.schemas.transit_route import (
    HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
    TransitHaproxyRouteCreateFinalApprovalRequest,
)

TRANSIT_RESOURCE_ID = "80ec346d-3ac1-402e-ab09-33cb404ca81c"
TRANSIT_WORKER_ID = "f2e16197-e953-46dd-90af-66f64759a2a9"
LANDING_NODE_ID = "a71472c6-f62c-43b5-a223-9f5f070ae4ef"
LANDING_VPS_ID = "968519b3-9017-4b27-a9a0-d5731033f84f"
DRY_RUN_COMMAND_ID = "ecfcf03a-8549-4b4a-9214-abebf6eee7f"


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/transit-routes/haproxy-route-create-final-approval",
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


def dry_run_payload(**overrides):
    payload = {
        "command_intent": "haproxy_route_create_dry_run",
        "transit_resource_id": TRANSIT_RESOURCE_ID,
        "transit_resource_name": "mkiepl广港",
        "transit_entry_host": "109.244.79.147",
        "landing_node_id": LANDING_NODE_ID,
        "landing_node_name": "liveline-reality-27939",
        "planned_listen_port": 23843,
        "approved_planned_listen_port": 23843,
        "approved_firewall_confirmation": True,
        "landing_target_host": "64.90.13.19",
        "approved_landing_target_host": "64.90.13.19",
        "landing_target_port": 27939,
        "approved_landing_target_port": 27939,
        "forwarding_method": "haproxy_tcp",
        "purpose": "直播",
        "approval_stage": "Stage 3.3.137-new-transit-haproxy-route-create-dry-run",
        "readiness_approval_confirmed": True,
        "dry_run": True,
        "approval_required": True,
        "user_approved_real_execution": False,
        "real_execution": False,
        "route_created": False,
        "haproxy_installed": False,
        "listener_bound": False,
        "firewall_modified": False,
        "share_link_mutated": False,
        "cutover": False,
        "route_name": "haproxy-tcp-23843",
        "route_display_name": "mk香港落地15m",
        "planned_service_name": "liveline-haproxy-23843.service",
    }
    payload.update(overrides)
    return payload


class FakeSession:
    def __init__(
        self,
        *,
        command_present: bool = True,
        command_payload: dict | None = None,
        command_type: str = "transit_route_create",
        command_status: str = "succeeded",
        command_worker_id: str = TRANSIT_WORKER_ID,
        resource_present: bool = True,
        resource_deleted: bool = False,
        node_present: bool = True,
        node_deleted: bool = False,
        node_has_vps: bool = True,
        node_port: int | None = 27939,
        worker_present: bool = True,
        worker_status: str = "online",
        worker_role: str = "transit",
        worker_version: str | None = "0.1.36-stage-3.3.188-transit-port-approval",
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
        self.command = (
            WorkerCommand(
                id=DRY_RUN_COMMAND_ID,
                worker_id=command_worker_id,
                server_type="transit",
                server_id=TRANSIT_RESOURCE_ID,
                command_type=command_type,
                payload_json=command_payload if command_payload is not None else dry_run_payload(),
                status=command_status,
                attempts=1,
            )
            if command_present
            else None
        )

    def get(self, model, key):
        if model is WorkerCommand and self.command and key == self.command.id:
            return self.command
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
        "dry_run_command_id": DRY_RUN_COMMAND_ID,
        "transit_resource_id": TRANSIT_RESOURCE_ID,
        "landing_node_id": LANDING_NODE_ID,
        "planned_listen_port": 23843,
        "landing_target_host": "64.90.13.19",
        "landing_target_port": 27939,
        "forwarding_method": "haproxy_tcp",
        "route_name": "haproxy-tcp-23843",
        "route_display_name": "mk香港落地15m",
        "planned_service_name": "liveline-haproxy-23843.service",
        "dry_run_verified": True,
        "firewall_security_group_confirmed": True,
        "cloud_firewall_confirmed": True,
        "server_firewall_confirmed": True,
        "no_cutover_confirmed": True,
        "no_node_share_link_change_confirmed": True,
        "no_full_client_link_confirmed": True,
        "final_approval_text": HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
    }
    payload.update(overrides)
    return TransitHaproxyRouteCreateFinalApprovalRequest(**payload)


def call_final_approval(payload, db):
    with (
        patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()),
        patch.object(transit_routes, "csrf_valid", return_value=True),
    ):
        return transit_routes.haproxy_route_create_final_approval(payload, make_request(), db)


def check_map(data):
    return {check["id"]: check for check in data["data"]["checks"]}


class TransitHaproxyRouteCreateFinalApprovalTests(unittest.TestCase):
    def assert_blocked_by(self, db: FakeSession, check_id: str, payload=None):
        response = call_final_approval(payload or valid_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["ready_for_real_create"])
        self.assertTrue(data["data"]["blocked"])
        self.assertFalse(check_map(data)[check_id]["passed"])
        self.assertEqual([item for item in db.added if isinstance(item, WorkerCommand)], [])
        self.assertEqual([item for item in db.added if isinstance(item, TransitRoute)], [])
        self.assertFalse(db.commit_called)
        return data

    def test_dry_run_command_missing_blocks_approval(self):
        self.assert_blocked_by(FakeSession(command_present=False), "dry_run_command_exists")

    def test_dry_run_command_not_dry_run_blocks_approval(self):
        self.assert_blocked_by(
            FakeSession(command_payload=dry_run_payload(dry_run=False)),
            "dry_run_command_shape_valid",
        )

    def test_failed_dry_run_command_blocks_approval(self):
        data = self.assert_blocked_by(
            FakeSession(command_status="failed"),
            "dry_run_command_succeeded",
        )

        self.assertEqual(data["data"]["summary"], "HAProxy route final approval blocked")
        self.assertEqual(
            data["data"]["next_action"],
            "请先重新生成并完成 Stage 3.3.137 HAProxy route dry-run，直到 dry-run command succeeded。",
        )
        self.assertFalse(data["data"]["worker_command_created"])
        self.assertFalse(data["data"]["route_created"])
        self.assertFalse(data["data"]["transit_route_active_record_created"])
        self.assertFalse(data["data"]["share_link_mutated"])

    def test_running_dry_run_command_blocks_approval(self):
        data = self.assert_blocked_by(
            FakeSession(command_status="running"),
            "dry_run_command_succeeded",
        )

        self.assertEqual(data["data"]["summary"], "HAProxy route final approval blocked")
        self.assertFalse(data["data"]["ready_for_real_create"])
        self.assertTrue(data["data"]["blocked"])
        self.assertFalse(data["data"]["worker_command_created"])
        self.assertFalse(data["data"]["route_created"])
        self.assertFalse(data["data"]["transit_route_active_record_created"])
        self.assertFalse(data["data"]["share_link_mutated"])

    def test_dry_run_payload_mismatch_blocks_approval(self):
        self.assert_blocked_by(
            FakeSession(command_payload=dry_run_payload(planned_listen_port=12081)),
            "dry_run_payload_matches_final_request",
        )

    def test_dry_run_worker_mismatch_blocks_approval(self):
        self.assert_blocked_by(
            FakeSession(command_worker_id="older-transit-worker"),
            "dry_run_worker_matches_current_transit_worker",
        )

    def test_final_approval_text_mismatch_blocks_approval(self):
        self.assert_blocked_by(
            FakeSession(),
            "final_approval_text_matches",
            valid_payload(final_approval_text="WRONG_CONFIRMATION"),
        )

    def test_transit_resource_missing_blocks_approval(self):
        self.assert_blocked_by(FakeSession(resource_present=False), "transit_resource_exists")

    def test_transit_worker_offline_blocks_approval(self):
        self.assert_blocked_by(FakeSession(worker_heartbeat_recent=False), "transit_worker_online")

    def test_landing_node_mismatch_blocks_approval(self):
        self.assert_blocked_by(
            FakeSession(node_port=28000),
            "landing_target_port_matches_current_node",
        )

    def test_planned_listen_port_mismatch_blocks_approval(self):
        self.assert_blocked_by(
            FakeSession(),
            "dry_run_payload_matches_final_request",
            valid_payload(planned_listen_port=12081, planned_service_name="liveline-haproxy-12081.service"),
        )

    def test_missing_approved_planned_listen_port_blocks_approval(self):
        command_payload = dry_run_payload()
        command_payload.pop("approved_planned_listen_port")

        self.assert_blocked_by(
            FakeSession(command_payload=command_payload),
            "dry_run_command_shape_valid",
        )

    def test_approved_planned_listen_port_mismatch_blocks_approval(self):
        self.assert_blocked_by(
            FakeSession(command_payload=dry_run_payload(approved_planned_listen_port=24731)),
            "dry_run_command_shape_valid",
        )

    def test_missing_approved_firewall_confirmation_blocks_approval(self):
        command_payload = dry_run_payload()
        command_payload.pop("approved_firewall_confirmation")

        self.assert_blocked_by(
            FakeSession(command_payload=command_payload),
            "dry_run_command_shape_valid",
        )

    def test_missing_firewall_confirmations_block_approval(self):
        self.assert_blocked_by(
            FakeSession(),
            "security_group_confirmation_present",
            valid_payload(firewall_security_group_confirmed=False),
        )
        self.assert_blocked_by(
            FakeSession(),
            "cloud_firewall_confirmation_present",
            valid_payload(cloud_firewall_confirmed=False),
        )
        self.assert_blocked_by(
            FakeSession(),
            "server_firewall_confirmation_present",
            valid_payload(server_firewall_confirmed=False),
        )

    def test_missing_safety_confirmations_block_approval(self):
        self.assert_blocked_by(
            FakeSession(),
            "no_cutover_confirmed",
            valid_payload(no_cutover_confirmed=False),
        )
        self.assert_blocked_by(
            FakeSession(),
            "no_share_link_mutation_confirmed",
            valid_payload(no_node_share_link_change_confirmed=False),
        )
        self.assert_blocked_by(
            FakeSession(),
            "no_full_client_link_confirmed",
            valid_payload(no_full_client_link_confirmed=False),
        )

    def test_ready_success_is_read_only_and_does_not_mutate_links_or_create_records(self):
        db = FakeSession()
        original_share_link = db.node.share_link if db.node else None
        response = call_final_approval(valid_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["ready_for_real_create"])
        self.assertFalse(data["data"]["blocked"])
        self.assertEqual(data["data"]["dry_run_command_id"], DRY_RUN_COMMAND_ID)
        self.assertEqual(data["data"]["planned_service_name"], "liveline-haproxy-23843.service")
        self.assertEqual(data["data"]["route_display_name"], "mk香港落地15m")
        self.assertEqual(data["data"]["next_stage"], "Stage 3.3.139-new-transit-haproxy-route-create-real-execution")
        self.assertFalse(data["data"]["worker_command_created"])
        self.assertFalse(data["data"]["real_execution_command_created"])
        self.assertFalse(data["data"]["route_created"])
        self.assertFalse(data["data"]["transit_route_active_record_created"])
        self.assertFalse(data["data"]["haproxy_installed"])
        self.assertFalse(data["data"]["listener_bound"])
        self.assertFalse(data["data"]["firewall_modified"])
        self.assertFalse(data["data"]["share_link_mutated"])
        self.assertFalse(data["data"]["cutover"])
        self.assertTrue(check_map(data)["dry_run_command_succeeded"]["passed"])
        self.assertTrue(check_map(data)["dry_run_worker_matches_current_transit_worker"]["passed"])
        self.assertTrue(check_map(data)["worker_command_not_created"]["passed"])
        self.assertTrue(check_map(data)["haproxy_not_created"]["passed"])
        self.assertTrue(check_map(data)["firewall_not_modified"]["passed"])
        self.assertEqual(db.node.share_link if db.node else None, original_share_link)
        self.assertEqual([item for item in db.added if isinstance(item, WorkerCommand)], [])
        self.assertEqual([item for item in db.added if isinstance(item, TransitRoute)], [])
        self.assertFalse(db.commit_called)


if __name__ == "__main__":
    unittest.main()
