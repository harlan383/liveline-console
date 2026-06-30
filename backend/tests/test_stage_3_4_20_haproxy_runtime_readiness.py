import json
import unittest
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import transit_routes
from app.models.transit_route import TransitRoute
from app.models.worker_command import WorkerCommand
from app.schemas.transit_route import (
    HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
    haproxy_real_execution_confirmation_text,
)
from backend.tests.test_stage_3_4_19_haproxy_protected_smoke_validation import (
    LANDING_TARGET_PORT,
    LEGACY_23843_CONFIRMATION,
    PLANNED_LISTEN_PORT,
    ROUTE_NAME,
    SERVICE_NAME,
    dynamic_dry_run_payload_for_real_execution,
    dynamic_real_execution_payload,
)
from backend.tests.test_transit_haproxy_route_create_real_execution import (
    FakeAdminSession,
    FakeSession,
    call_real_execution,
)


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/transit-routes/haproxy-route-real-execution-readiness",
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


def call_runtime_readiness(payload, db):
    with (
        patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()),
        patch.object(transit_routes, "csrf_valid", return_value=True),
    ):
        return transit_routes.haproxy_route_real_execution_readiness(payload, make_request(), db)


def check_map(data):
    return {check["id"]: check for check in data["data"]["checks"]}


def assert_no_worker_command_or_route_created(test_case, db):
    test_case.assertEqual([item for item in db.added if isinstance(item, WorkerCommand)], [])
    test_case.assertEqual([item for item in db.added if isinstance(item, TransitRoute)], [])
    test_case.assertFalse(db.commit_called)


class Stage3420HaproxyRuntimeReadinessTests(unittest.TestCase):
    def test_readiness_success_for_dynamic_port_is_read_only(self):
        db = FakeSession(
            command_payload=dynamic_dry_run_payload_for_real_execution(),
            node_port=LANDING_TARGET_PORT,
        )
        response = call_runtime_readiness(dynamic_real_execution_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["ready_for_real_execution"])
        self.assertFalse(data["data"]["blocked"])
        self.assertEqual(
            data["data"]["expected_real_execution_text"],
            haproxy_real_execution_confirmation_text(PLANNED_LISTEN_PORT),
        )
        self.assertEqual(data["data"]["final_approval_text"], HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT)
        self.assertEqual(data["data"]["planned_service_name"], SERVICE_NAME)
        self.assertEqual(data["data"]["planned_listen_port"], PLANNED_LISTEN_PORT)
        self.assertEqual(data["data"]["landing_target_port"], LANDING_TARGET_PORT)
        self.assertEqual(data["data"]["route_name"], ROUTE_NAME)
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
        self.assertTrue(check_map(data)["planned_listen_port_not_reserved"]["passed"])
        self.assertTrue(check_map(data)["landing_node_active"]["passed"])
        assert_no_worker_command_or_route_created(self, db)

    def test_readiness_blocks_legacy_23843_confirmation_for_dynamic_port(self):
        db = FakeSession(
            command_payload=dynamic_dry_run_payload_for_real_execution(),
            node_port=LANDING_TARGET_PORT,
        )
        response = call_runtime_readiness(
            dynamic_real_execution_payload(real_execution_text=LEGACY_23843_CONFIRMATION),
            db,
        )
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["ready_for_real_execution"])
        self.assertTrue(data["data"]["blocked"])
        self.assertFalse(check_map(data)["real_execution_text_matches"]["passed"])
        self.assertEqual(
            data["data"]["expected_real_execution_text"],
            haproxy_real_execution_confirmation_text(PLANNED_LISTEN_PORT),
        )
        self.assertFalse(data["data"]["worker_command_created"])
        self.assertFalse(data["data"]["real_execution_command_created"])
        self.assertFalse(data["data"]["route_created"])
        assert_no_worker_command_or_route_created(self, db)

    def test_readiness_blocks_dry_run_not_succeeded(self):
        db = FakeSession(
            command_payload=dynamic_dry_run_payload_for_real_execution(),
            command_status="running",
            node_port=LANDING_TARGET_PORT,
        )
        response = call_runtime_readiness(dynamic_real_execution_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["ready_for_real_execution"])
        self.assertTrue(data["data"]["blocked"])
        self.assertFalse(check_map(data)["dry_run_command_succeeded"]["passed"])
        self.assertFalse(data["data"]["worker_command_created"])
        self.assertFalse(data["data"]["route_created"])
        assert_no_worker_command_or_route_created(self, db)

    def test_readiness_blocks_existing_active_route(self):
        db = FakeSession(
            command_payload=dynamic_dry_run_payload_for_real_execution(),
            node_port=LANDING_TARGET_PORT,
            existing_route=True,
        )
        if db.existing_route:
            db.existing_route.listen_port = PLANNED_LISTEN_PORT
            db.existing_route.service_name = SERVICE_NAME
        response = call_runtime_readiness(dynamic_real_execution_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["ready_for_real_execution"])
        self.assertTrue(data["data"]["blocked"])
        self.assertFalse(check_map(data)["no_existing_haproxy_route_same_port"]["passed"])
        self.assertFalse(data["data"]["worker_command_created"])
        self.assertFalse(data["data"]["route_created"])
        assert_no_worker_command_or_route_created(self, db)

    def test_real_execution_still_creates_one_command_only_when_readiness_is_ready(self):
        db = FakeSession(
            command_payload=dynamic_dry_run_payload_for_real_execution(),
            node_port=LANDING_TARGET_PORT,
        )
        response = call_real_execution(dynamic_real_execution_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["ready_for_real_execution"])
        self.assertFalse(data["data"]["blocked"])
        self.assertTrue(data["data"]["worker_command_created"])
        self.assertTrue(data["data"]["real_execution_command_created"])
        self.assertFalse(data["data"]["route_created"])
        self.assertFalse(data["data"]["transit_route_active_record_created"])
        self.assertFalse(data["data"]["share_link_mutated"])
        self.assertFalse(data["data"]["cutover"])

        commands = [item for item in db.added if isinstance(item, WorkerCommand)]
        routes = [item for item in db.added if isinstance(item, TransitRoute)]
        self.assertEqual(len(commands), 1)
        self.assertEqual(routes, [])
        self.assertTrue(db.commit_called)
        self.assertEqual(commands[0].payload_json["planned_listen_port"], PLANNED_LISTEN_PORT)
        self.assertEqual(commands[0].payload_json["approved_planned_listen_port"], PLANNED_LISTEN_PORT)


if __name__ == "__main__":
    unittest.main()
