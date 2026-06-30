import unittest

from app.models.transit_route import TransitRoute
from app.models.worker_command import WorkerCommand
from app.schemas.transit_route import (
    HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
    haproxy_real_execution_confirmation_text,
)
from backend.tests.test_transit_haproxy_route_create_final_approval import (
    FakeSession as FinalApprovalFakeSession,
    call_final_approval,
    check_map as final_check_map,
    dry_run_payload as final_dry_run_payload,
    response_payload,
    valid_payload as final_valid_payload,
)
from backend.tests.test_transit_haproxy_route_create_real_execution import (
    FakeSession as RealExecutionFakeSession,
    call_real_execution,
    check_map as real_check_map,
    dry_run_payload as real_dry_run_payload,
    valid_payload as real_valid_payload,
)


PLANNED_LISTEN_PORT = 25867
LANDING_TARGET_PORT = 28917
ROUTE_NAME = "haproxy-tcp-25867"
SERVICE_NAME = "liveline-haproxy-25867.service"
LEGACY_23843_CONFIRMATION = "CONFIRM_REAL_HAPROXY_ROUTE_CREATE_23843"


def dynamic_dry_run_payload_for_final_approval():
    return final_dry_run_payload(
        planned_listen_port=PLANNED_LISTEN_PORT,
        approved_planned_listen_port=PLANNED_LISTEN_PORT,
        landing_target_port=LANDING_TARGET_PORT,
        approved_landing_target_port=LANDING_TARGET_PORT,
        route_name=ROUTE_NAME,
        planned_service_name=SERVICE_NAME,
    )


def dynamic_final_approval_payload():
    return final_valid_payload(
        planned_listen_port=PLANNED_LISTEN_PORT,
        landing_target_port=LANDING_TARGET_PORT,
        route_name=ROUTE_NAME,
        planned_service_name=SERVICE_NAME,
    )


def dynamic_dry_run_payload_for_real_execution():
    return real_dry_run_payload(
        planned_listen_port=PLANNED_LISTEN_PORT,
        approved_planned_listen_port=PLANNED_LISTEN_PORT,
        landing_target_port=LANDING_TARGET_PORT,
        approved_landing_target_port=LANDING_TARGET_PORT,
        route_name=ROUTE_NAME,
        planned_service_name=SERVICE_NAME,
    )


def dynamic_real_execution_payload(**overrides):
    return real_valid_payload(
        planned_listen_port=PLANNED_LISTEN_PORT,
        landing_target_port=LANDING_TARGET_PORT,
        route_name=ROUTE_NAME,
        **overrides,
    )


def assert_no_worker_command_or_route_created(test_case, db):
    test_case.assertEqual([item for item in db.added if isinstance(item, WorkerCommand)], [])
    test_case.assertEqual([item for item in db.added if isinstance(item, TransitRoute)], [])
    test_case.assertFalse(db.commit_called)


class Stage3419HaproxyProtectedSmokeValidationTests(unittest.TestCase):
    def test_dynamic_confirmation_text_helper_keeps_legacy_23843_and_supports_dynamic_port(self):
        self.assertEqual(
            haproxy_real_execution_confirmation_text(PLANNED_LISTEN_PORT),
            "CONFIRM_REAL_HAPROXY_ROUTE_CREATE_25867",
        )
        self.assertEqual(haproxy_real_execution_confirmation_text(23843), LEGACY_23843_CONFIRMATION)

    def test_final_approval_dynamic_port_is_read_only_and_returns_expected_real_execution_text(self):
        db = FinalApprovalFakeSession(
            command_payload=dynamic_dry_run_payload_for_final_approval(),
            node_port=LANDING_TARGET_PORT,
        )
        response = call_final_approval(dynamic_final_approval_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["ready_for_real_create"])
        self.assertFalse(data["data"]["blocked"])
        self.assertEqual(
            data["data"]["expected_real_execution_text"],
            haproxy_real_execution_confirmation_text(PLANNED_LISTEN_PORT),
        )
        self.assertEqual(data["data"]["final_approval_text"], HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT)
        self.assertFalse(data["data"]["worker_command_created"])
        self.assertFalse(data["data"]["real_execution_command_created"])
        self.assertFalse(data["data"]["route_created"])
        self.assertFalse(data["data"]["transit_route_active_record_created"])
        self.assertFalse(data["data"]["haproxy_installed"])
        self.assertFalse(data["data"]["listener_bound"])
        self.assertFalse(data["data"]["firewall_modified"])
        self.assertFalse(data["data"]["share_link_mutated"])
        self.assertFalse(data["data"]["cutover"])
        self.assertTrue(final_check_map(data)["worker_command_not_created"]["passed"])
        self.assertTrue(final_check_map(data)["haproxy_not_created"]["passed"])
        assert_no_worker_command_or_route_created(self, db)

    def test_real_execution_dynamic_port_rejects_legacy_23843_confirmation_without_creating_command(self):
        db = RealExecutionFakeSession(
            command_payload=dynamic_dry_run_payload_for_real_execution(),
            node_port=LANDING_TARGET_PORT,
        )
        response = call_real_execution(
            dynamic_real_execution_payload(real_execution_text=LEGACY_23843_CONFIRMATION),
            db,
        )
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["ready_for_real_execution"])
        self.assertTrue(data["data"]["blocked"])
        self.assertFalse(real_check_map(data)["real_execution_text_matches"]["passed"])
        self.assertEqual(
            data["data"]["expected_real_execution_text"],
            haproxy_real_execution_confirmation_text(PLANNED_LISTEN_PORT),
        )
        self.assertFalse(data["data"]["worker_command_created"])
        self.assertFalse(data["data"]["real_execution_command_created"])
        self.assertFalse(data["data"]["route_created"])
        self.assertFalse(data["data"]["transit_route_active_record_created"])
        self.assertFalse(data["data"]["listener_bound"])
        self.assertFalse(data["data"]["firewall_modified"])
        self.assertFalse(data["data"]["share_link_mutated"])
        self.assertFalse(data["data"]["cutover"])
        assert_no_worker_command_or_route_created(self, db)

    def test_real_execution_blocks_when_dry_run_has_not_succeeded(self):
        db = RealExecutionFakeSession(
            command_payload=dynamic_dry_run_payload_for_real_execution(),
            command_status="running",
            node_port=LANDING_TARGET_PORT,
        )
        response = call_real_execution(dynamic_real_execution_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["ready_for_real_execution"])
        self.assertTrue(data["data"]["blocked"])
        self.assertFalse(real_check_map(data)["dry_run_command_succeeded"]["passed"])
        self.assertFalse(data["data"]["worker_command_created"])
        self.assertFalse(data["data"]["route_created"])
        assert_no_worker_command_or_route_created(self, db)

    def test_real_execution_blocks_existing_active_haproxy_route_without_creating_command(self):
        db = RealExecutionFakeSession(
            command_payload=dynamic_dry_run_payload_for_real_execution(),
            node_port=LANDING_TARGET_PORT,
            existing_route=True,
        )
        if db.existing_route:
            db.existing_route.listen_port = PLANNED_LISTEN_PORT
            db.existing_route.service_name = SERVICE_NAME
        response = call_real_execution(dynamic_real_execution_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["ready_for_real_execution"])
        self.assertTrue(data["data"]["blocked"])
        self.assertFalse(real_check_map(data)["no_existing_haproxy_route_same_port"]["passed"])
        self.assertFalse(data["data"]["worker_command_created"])
        self.assertFalse(data["data"]["route_created"])
        assert_no_worker_command_or_route_created(self, db)


if __name__ == "__main__":
    unittest.main()
