import unittest

from app.api.routes.transit_haproxy_real_execution_gate import (
    build_haproxy_real_execution_dynamic_approval_checks,
    dynamic_approval_gate_passed,
)
from app.schemas.transit_route import (
    FORWARDING_METHOD_HAPROXY_TCP,
    HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
    HAPROXY_ROUTE_CREATE_REAL_EXECUTION_STAGE,
    TransitHaproxyRouteCreateRealExecutionRequest,
    haproxy_real_execution_confirmation_text,
)

TRANSIT_WORKER_ID = "4072fcf0-dc40-473f-bf43-b785bf18a859"


def dynamic_payload(**overrides):
    payload = {
        "dry_run_command_id": "59c85e6f-b375-4022-98df-65687f22952f",
        "transit_resource_id": "80ec346d-3ac1-402e-ab09-33cb404ca81c",
        "landing_node_id": "d6404c5a-067a-48ad-8214-16631702e654",
        "planned_listen_port": 25867,
        "landing_target_host": "64.90.13.19",
        "landing_target_port": 28917,
        "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
        "route_name": "haproxy-tcp-25867",
        "approval_stage": HAPROXY_ROUTE_CREATE_REAL_EXECUTION_STAGE,
        "final_approval_text": HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
        "real_execution_text": haproxy_real_execution_confirmation_text(25867),
        "firewall_security_group_confirmed": True,
        "cloud_firewall_confirmed": True,
        "server_firewall_confirmed": True,
        "no_cutover_confirmed": True,
        "no_node_share_link_change_confirmed": True,
        "no_full_client_link_confirmed": True,
    }
    payload.update(overrides)
    if "planned_listen_port" in overrides and "real_execution_text" not in overrides:
        payload["real_execution_text"] = haproxy_real_execution_confirmation_text(payload["planned_listen_port"])
    return TransitHaproxyRouteCreateRealExecutionRequest(**payload)


def dynamic_dry_run_payload(**overrides):
    payload = {
        "command_intent": "haproxy_route_create_dry_run",
        "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
        "approval_stage": "Stage 3.3.137-new-transit-haproxy-route-create-dry-run",
        "dry_run": True,
        "approval_required": True,
        "real_execution": False,
        "planned_listen_port": 25867,
        "approved_planned_listen_port": 25867,
        "approved_firewall_confirmation": True,
        "landing_target_host": "64.90.13.19",
        "approved_landing_target_host": "64.90.13.19",
        "landing_target_port": 28917,
        "approved_landing_target_port": 28917,
        "route_name": "haproxy-tcp-25867",
        "planned_service_name": "liveline-haproxy-25867.service",
    }
    payload.update(overrides)
    return payload


def check_by_id(checks, check_id):
    return {check["id"]: check for check in checks}[check_id]


def dynamic_checks(payload=None, dry_run_payload=None, **metadata):
    return build_haproxy_real_execution_dynamic_approval_checks(
        payload or dynamic_payload(),
        dry_run_payload if dry_run_payload is not None else dynamic_dry_run_payload(),
        dry_run_status=metadata.get("dry_run_status", "succeeded"),
        dry_run_command_type=metadata.get("dry_run_command_type", "transit_route_create"),
        dry_run_worker_id=metadata.get("dry_run_worker_id", TRANSIT_WORKER_ID),
        current_worker_id=metadata.get("current_worker_id", TRANSIT_WORKER_ID),
    )


class TransitHaproxyRealExecutionDynamicApprovalGateTests(unittest.TestCase):
    def test_dynamic_request_and_dry_run_pass_gate(self):
        checks = dynamic_checks()

        self.assertTrue(all(check["passed"] for check in checks))
        self.assertTrue(
            dynamic_approval_gate_passed(
                dynamic_payload(),
                dynamic_dry_run_payload(),
                dry_run_worker_id=TRANSIT_WORKER_ID,
                current_worker_id=TRANSIT_WORKER_ID,
            )
        )

    def test_dynamic_port_and_landing_port_do_not_require_legacy_fixed_values(self):
        checks = dynamic_checks()

        self.assertTrue(check_by_id(checks, "planned_listen_port_matches_request")["passed"])
        self.assertTrue(check_by_id(checks, "approved_planned_listen_port_matches_request")["passed"])
        self.assertTrue(check_by_id(checks, "landing_target_port_matches_request")["passed"])
        self.assertTrue(check_by_id(checks, "approved_landing_target_port_matches_request")["passed"])
        self.assertEqual(dynamic_payload().planned_listen_port, 25867)
        self.assertEqual(dynamic_payload().landing_target_port, 28917)

    def test_missing_approved_planned_listen_port_blocks(self):
        dry_run_payload = dynamic_dry_run_payload()
        dry_run_payload.pop("approved_planned_listen_port")
        checks = dynamic_checks(dry_run_payload=dry_run_payload)

        self.assertFalse(check_by_id(checks, "approved_planned_listen_port_matches_request")["passed"])
        self.assertFalse(
            dynamic_approval_gate_passed(
                dynamic_payload(),
                dry_run_payload,
                dry_run_worker_id=TRANSIT_WORKER_ID,
                current_worker_id=TRANSIT_WORKER_ID,
            )
        )

    def test_approved_planned_listen_port_mismatch_blocks(self):
        checks = dynamic_checks(dry_run_payload=dynamic_dry_run_payload(approved_planned_listen_port=25868))

        self.assertFalse(check_by_id(checks, "approved_planned_listen_port_matches_request")["passed"])

    def test_approved_landing_target_port_mismatch_blocks(self):
        checks = dynamic_checks(dry_run_payload=dynamic_dry_run_payload(approved_landing_target_port=27939))

        self.assertFalse(check_by_id(checks, "approved_landing_target_port_matches_request")["passed"])

    def test_missing_approved_firewall_confirmation_blocks(self):
        checks = dynamic_checks(dry_run_payload=dynamic_dry_run_payload(approved_firewall_confirmation=False))

        self.assertFalse(check_by_id(checks, "approved_firewall_confirmation_present")["passed"])

    def test_dry_run_worker_mismatch_blocks(self):
        checks = dynamic_checks(dry_run_worker_id="older-worker", current_worker_id=TRANSIT_WORKER_ID)

        self.assertFalse(check_by_id(checks, "dry_run_worker_matches_current_transit_worker")["passed"])

    def test_dry_run_not_succeeded_blocks(self):
        checks = dynamic_checks(dry_run_status="failed")

        self.assertFalse(check_by_id(checks, "dry_run_command_succeeded")["passed"])

    def test_request_safety_confirmations_still_required(self):
        checks = dynamic_checks(payload=dynamic_payload(no_cutover_confirmed=False))

        self.assertFalse(check_by_id(checks, "request_safety_confirmations_present")["passed"])

    def test_request_confirmation_texts_still_required(self):
        checks = dynamic_checks(payload=dynamic_payload(real_execution_text="WRONG_CONFIRMATION"))

        self.assertFalse(check_by_id(checks, "request_real_execution_text_valid")["passed"])

    def test_legacy_23843_confirmation_text_does_not_approve_dynamic_port(self):
        checks = dynamic_checks(
            payload=dynamic_payload(real_execution_text=haproxy_real_execution_confirmation_text(23843))
        )

        self.assertFalse(check_by_id(checks, "request_real_execution_text_valid")["passed"])


if __name__ == "__main__":
    unittest.main()
