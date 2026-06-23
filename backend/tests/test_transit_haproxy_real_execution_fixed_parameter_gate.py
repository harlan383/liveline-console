import unittest

from app.api.routes.transit_haproxy_real_execution_gate import (
    APPROVED_HAPROXY_ROUTE_NAME,
    APPROVED_HAPROXY_SERVICE_NAME,
    build_haproxy_real_execution_fixed_parameter_checks,
    fixed_parameter_gate_passed,
)
from app.schemas.transit_route import (
    APPROVED_LANDING_TARGET_HOST,
    APPROVED_LANDING_TARGET_PORT,
    APPROVED_TRANSIT_LISTEN_PORT,
    FORWARDING_METHOD_HAPROXY_TCP,
    HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
    HAPROXY_ROUTE_CREATE_REAL_EXECUTION_STAGE,
    HAPROXY_ROUTE_CREATE_REAL_EXECUTION_TEXT,
    TransitHaproxyRouteCreateRealExecutionRequest,
)


def approved_payload(**overrides):
    payload = {
        "dry_run_command_id": "ecfcf03a-8549-4b4a-9214-abebf6eee7f",
        "transit_resource_id": "80ec346d-3ac1-402e-ab09-33cb404ca81c",
        "landing_node_id": "a71472c6-f62c-43b5-a223-9f5f070ae4ef",
        "planned_listen_port": APPROVED_TRANSIT_LISTEN_PORT,
        "landing_target_host": APPROVED_LANDING_TARGET_HOST,
        "landing_target_port": APPROVED_LANDING_TARGET_PORT,
        "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
        "route_name": APPROVED_HAPROXY_ROUTE_NAME,
        "approval_stage": HAPROXY_ROUTE_CREATE_REAL_EXECUTION_STAGE,
        "final_approval_text": HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_TEXT,
        "real_execution_text": HAPROXY_ROUTE_CREATE_REAL_EXECUTION_TEXT,
        "firewall_security_group_confirmed": True,
        "cloud_firewall_confirmed": True,
        "server_firewall_confirmed": True,
        "no_cutover_confirmed": True,
        "no_node_share_link_change_confirmed": True,
        "no_full_client_link_confirmed": True,
    }
    payload.update(overrides)
    return TransitHaproxyRouteCreateRealExecutionRequest(**payload)


def approved_dry_run_payload(**overrides):
    payload = {
        "command_intent": "haproxy_route_create_dry_run",
        "planned_listen_port": APPROVED_TRANSIT_LISTEN_PORT,
        "landing_target_host": APPROVED_LANDING_TARGET_HOST,
        "landing_target_port": APPROVED_LANDING_TARGET_PORT,
        "forwarding_method": FORWARDING_METHOD_HAPROXY_TCP,
        "route_name": APPROVED_HAPROXY_ROUTE_NAME,
        "planned_service_name": APPROVED_HAPROXY_SERVICE_NAME,
    }
    payload.update(overrides)
    return payload


def check_by_id(checks, check_id):
    return {check["id"]: check for check in checks}[check_id]


class TransitHaproxyRealExecutionFixedParameterGateTests(unittest.TestCase):
    def test_approved_request_and_dry_run_pass_gate(self):
        checks = build_haproxy_real_execution_fixed_parameter_checks(
            approved_payload(),
            approved_dry_run_payload(),
        )

        self.assertTrue(all(check["passed"] for check in checks))
        self.assertTrue(fixed_parameter_gate_passed(approved_payload(), approved_dry_run_payload()))

    def test_non_approved_request_port_blocks_before_worker_command(self):
        checks = build_haproxy_real_execution_fixed_parameter_checks(
            approved_payload(planned_listen_port=24731),
            approved_dry_run_payload(),
        )

        self.assertFalse(check_by_id(checks, "approved_request_listen_port")["passed"])
        self.assertFalse(check_by_id(checks, "approved_request_service_name")["passed"])
        self.assertFalse(fixed_parameter_gate_passed(approved_payload(planned_listen_port=24731), approved_dry_run_payload()))

    def test_non_approved_request_target_blocks_before_worker_command(self):
        checks = build_haproxy_real_execution_fixed_parameter_checks(
            approved_payload(landing_target_host="203.0.113.10"),
            approved_dry_run_payload(),
        )

        self.assertFalse(check_by_id(checks, "approved_request_landing_host")["passed"])

    def test_non_approved_dry_run_port_blocks_even_when_request_is_approved(self):
        checks = build_haproxy_real_execution_fixed_parameter_checks(
            approved_payload(),
            approved_dry_run_payload(planned_listen_port=24731, planned_service_name="liveline-haproxy-24731.service"),
        )

        self.assertFalse(check_by_id(checks, "approved_dry_run_listen_port")["passed"])
        self.assertFalse(check_by_id(checks, "approved_dry_run_service_name")["passed"])
        self.assertFalse(fixed_parameter_gate_passed(approved_payload(), approved_dry_run_payload(planned_listen_port=24731)))

    def test_non_approved_dry_run_route_name_blocks_even_when_request_is_approved(self):
        checks = build_haproxy_real_execution_fixed_parameter_checks(
            approved_payload(),
            approved_dry_run_payload(route_name="haproxy-tcp-24731"),
        )

        self.assertFalse(check_by_id(checks, "approved_dry_run_route_name")["passed"])


if __name__ == "__main__":
    unittest.main()
