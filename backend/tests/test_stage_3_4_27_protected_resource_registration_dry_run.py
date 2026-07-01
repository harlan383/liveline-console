import json
import unittest
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import transit_routes
from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.vps_server import VpsServer
from app.models.worker_command import WorkerCommand


DRY_RUN_COMMAND_ID = "ecfcf03a-8549-4b4a-9214-abebf6eee7f"
TRANSIT_WORKER_ID = "f2e16197-e953-46dd-90af-66f64759a2a9"


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/transit-routes/protected-resource-registration-dry-run",
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
        "planned_listen_port": 29833,
        "approved_planned_listen_port": 29833,
        "approved_firewall_confirmation": True,
        "landing_target_host": "64.90.13.19",
        "approved_landing_target_host": "64.90.13.19",
        "landing_target_port": 28917,
        "approved_landing_target_port": 28917,
        "forwarding_method": "haproxy_tcp",
        "dry_run": True,
        "approval_required": True,
        "real_execution": False,
        "user_approved_real_execution": False,
        "approved_real_execution": False,
        "route_created": False,
        "listener_bound": False,
        "firewall_modified": False,
        "share_link_mutated": False,
        "cutover": False,
        "route_name": "haproxy-tcp-29833",
        "route_display_name": "mk香港落地15m",
        "planned_service_name": "liveline-haproxy-29833.service",
    }
    payload.update(overrides)
    return payload


def valid_payload(**overrides):
    payload = {
        "stage": "Stage 3.4.26-advanced-debug-protected-resource-registration-ui",
        "mode": "preview_only",
        "source": {
            "dry_run_command_id": DRY_RUN_COMMAND_ID,
            "route_name": "haproxy-tcp-29833",
            "planned_listen_port": 29833,
            "landing_target_host": "64.90.13.19",
            "landing_target_port": 28917,
            "candidate_integrity_ready": False,
        },
        "transit_resource_registration": {
            "name": "广州IEPL-香港出口01",
            "resource_type": "server",
            "entry_host": "109.244.79.147",
            "entry_port": 22,
            "entry_region": "广州",
            "exit_region": "香港",
            "expected_status": "worker_online",
            "worker_role": "transit",
            "worker_binding_required": True,
        },
        "landing_node_registration": {
            "node_name": "香港直连15m",
            "vps_ip": "64.90.13.19",
            "xray_port": 28917,
            "expected_status": "active",
            "share_link_handling": "do_not_export_or_modify_full_share_link",
        },
        "confirmations": {
            "manual_confirm_transit_host": True,
            "manual_confirm_worker_binding": True,
            "manual_confirm_landing_host": True,
            "manual_confirm_landing_port": True,
            "manual_confirm_no_share_link_export": True,
            "manual_confirm_no_remote_execution": True,
            "manual_confirm_no_firewall_change": True,
            "manual_confirm_no_cutover": True,
        },
        "safety_boundary": list(transit_routes.PROTECTED_RESOURCE_REGISTRATION_REQUIRED_BOUNDARY),
    }
    payload.update(overrides)
    return transit_routes.ProtectedResourceRegistrationDryRunRequest(**payload)


class FakeSession:
    def __init__(
        self,
        *,
        command_present: bool = True,
        command_status: str = "succeeded",
        command_payload: dict | None = None,
        duplicate_transit_name: bool = False,
        duplicate_transit_entry_host: bool = False,
        duplicate_landing_node: bool = False,
    ) -> None:
        self.scalars_calls = 0
        self.command = (
            WorkerCommand(
                id=DRY_RUN_COMMAND_ID,
                worker_id=TRANSIT_WORKER_ID,
                server_type="transit",
                server_id="80ec346d-3ac1-402e-ab09-33cb404ca81c",
                command_type="transit_route_create",
                payload_json=command_payload if command_payload is not None else dry_run_payload(),
                status=command_status,
                attempts=1,
            )
            if command_present
            else None
        )
        self.duplicate_name_resource = (
            TransitResource(
                id="duplicate-name-resource",
                name="广州IEPL-香港出口01",
                resource_type="server",
                entry_host="203.0.113.10",
                entry_port=22,
                status="worker_online",
            )
            if duplicate_transit_name
            else None
        )
        self.duplicate_entry_host_resource = (
            TransitResource(
                id="duplicate-entry-host-resource",
                name="另一条中转资源",
                resource_type="server",
                entry_host="109.244.79.147",
                entry_port=22,
                status="active",
            )
            if duplicate_transit_entry_host
            else None
        )
        self.duplicate_landing_node = (
            Node(
                id="duplicate-landing-node",
                vps_id="vps-1",
                node_name="香港直连15m",
                xray_port=28917,
                status="active",
            )
            if duplicate_landing_node
            else None
        )
        if self.duplicate_landing_node:
            self.duplicate_landing_node.vps = VpsServer(id="vps-1", ip="64.90.13.19")

    def get(self, model, key):
        if model is WorkerCommand and self.command and key == self.command.id:
            return self.command
        return None

    def scalars(self, statement):
        self.scalars_calls += 1
        if self.scalars_calls == 1:
            return FakeScalarResult([self.duplicate_name_resource] if self.duplicate_name_resource else [])
        if self.scalars_calls == 2:
            return FakeScalarResult([self.duplicate_entry_host_resource] if self.duplicate_entry_host_resource else [])
        return FakeScalarResult([self.duplicate_landing_node] if self.duplicate_landing_node else [])

    def add(self, item):
        raise AssertionError("dry-run endpoint must not call db.add")

    def commit(self):
        raise AssertionError("dry-run endpoint must not call db.commit")

    def flush(self):
        raise AssertionError("dry-run endpoint must not call db.flush")

    def refresh(self, item):
        raise AssertionError("dry-run endpoint must not call db.refresh")


def call_dry_run(payload, db):
    with (
        patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()),
        patch.object(transit_routes, "csrf_valid", return_value=True),
    ):
        return transit_routes.protected_resource_registration_dry_run(payload, make_request(), db)


def check_map(data):
    return {check["id"]: check for check in data["data"]["checks"]}


class ProtectedResourceRegistrationDryRunTests(unittest.TestCase):
    def assert_blocked_by(self, db: FakeSession, check_id: str, payload=None):
        response = call_dry_run(payload or valid_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["ready_for_next_stage"])
        self.assertFalse(check_map(data)[check_id]["passed"])
        self.assertEqual(data["data"]["dry_run"], True)
        return data

    def test_valid_payload_returns_ready(self):
        response = call_dry_run(valid_payload(), FakeSession())
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["ready_for_next_stage"])
        self.assertEqual(data["data"]["blocked_reasons"], [])
        self.assertEqual(
            data["data"]["expected_approval_text"],
            "CONFIRM_PROTECTED_RESOURCE_REGISTRATION_DRY_RUN_29833",
        )
        self.assertEqual(
            data["data"]["recommended_next_stage"],
            "Stage 3.4.28-advanced-debug-protected-resource-registration-approval",
        )

    def test_endpoint_does_not_call_db_write_methods(self):
        response = call_dry_run(valid_payload(), FakeSession())
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["ready_for_next_stage"])

    def test_invalid_stage_blocked(self):
        self.assert_blocked_by(FakeSession(), "stage_is_expected", valid_payload(stage="wrong-stage"))

    def test_mode_not_preview_only_blocked(self):
        self.assert_blocked_by(FakeSession(), "mode_is_preview_only", valid_payload(mode="real_create"))

    def test_missing_manual_confirmations_blocked(self):
        payload = valid_payload(
            confirmations={
                "manual_confirm_transit_host": True,
                "manual_confirm_worker_binding": True,
                "manual_confirm_landing_host": False,
                "manual_confirm_landing_port": True,
                "manual_confirm_no_share_link_export": True,
                "manual_confirm_no_remote_execution": True,
                "manual_confirm_no_firewall_change": True,
                "manual_confirm_no_cutover": True,
            }
        )
        self.assert_blocked_by(FakeSession(), "all_manual_confirmations_present", payload)

    def test_invalid_transit_entry_port_blocked(self):
        payload = valid_payload(
            transit_resource_registration={
                **valid_payload().transit_resource_registration.model_dump(),
                "entry_port": 70000,
            }
        )
        self.assert_blocked_by(FakeSession(), "transit_entry_port_valid", payload)

    def test_invalid_landing_xray_port_blocked(self):
        payload = valid_payload(
            landing_node_registration={
                **valid_payload().landing_node_registration.model_dump(),
                "xray_port": 0,
            }
        )
        self.assert_blocked_by(FakeSession(), "landing_xray_port_valid", payload)

    def test_source_dry_run_missing_blocked(self):
        self.assert_blocked_by(FakeSession(command_present=False), "source_dry_run_command_exists")

    def test_source_dry_run_not_succeeded_blocked(self):
        self.assert_blocked_by(FakeSession(command_status="failed"), "source_dry_run_status_succeeded")

    def test_source_payload_mismatch_blocked(self):
        self.assert_blocked_by(
            FakeSession(command_payload=dry_run_payload(planned_listen_port=25963)),
            "source_planned_listen_port_matches",
        )

    def test_duplicate_active_transit_resource_blocked(self):
        self.assert_blocked_by(
            FakeSession(duplicate_transit_name=True),
            "transit_no_active_duplicate_by_name",
        )

    def test_duplicate_active_landing_node_by_vps_ip_port_blocked(self):
        self.assert_blocked_by(
            FakeSession(duplicate_landing_node=True),
            "landing_no_active_duplicate_by_vps_ip_port",
        )

    def test_response_redacts_sensitive_input_and_blocks(self):
        sensitive_value = "vless" + "://example-sensitive"
        payload = valid_payload(
            transit_resource_registration={
                **valid_payload().transit_resource_registration.model_dump(),
                "name": sensitive_value,
            }
        )
        response = call_dry_run(payload, FakeSession())
        data = response_payload(response)
        body = json.dumps(data, ensure_ascii=False)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["ready_for_next_stage"])
        self.assertFalse(check_map(data)["response_sensitive_content_absent"]["passed"])
        self.assertNotIn(sensitive_value, body)
        self.assertIn("[redacted sensitive value]", body)

    def test_integrity_ready_candidate_allowed_as_warning(self):
        payload = valid_payload(
            source={
                **valid_payload().source.model_dump(),
                "candidate_integrity_ready": True,
            }
        )
        response = call_dry_run(payload, FakeSession())
        data = response_payload(response)
        warning = check_map(data)["candidate_already_integrity_ready"]

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["ready_for_next_stage"])
        self.assertTrue(warning["passed"])
        self.assertEqual(warning["severity"], "warning")


if __name__ == "__main__":
    unittest.main()
