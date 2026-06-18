import unittest

from app.api.routes.workers import (
    WORKER_RESULT_BODY_LIMIT_BYTES,
    WorkerReportBodyError,
    decode_worker_command_report_body,
    worker_command_status_is_terminal,
)
from app.services.worker_commands import normalize_worker_command_result, sanitize_command_payload
from app.schemas.transit_route import (
    APPROVED_TRANSIT_ROUTE_CREATE_STAGE,
    APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE,
    TransitRouteWorkerCreateExecuteRequest,
    TransitRouteWorkerCreatePlanRequest,
)
from app.schemas.worker_commands import WorkerCommandCreate
from app.services.worker_targeting import minimum_worker_version_for_command, minimum_worker_version_key_for_command


class WorkerCommandResultNormalizationTests(unittest.TestCase):
    def test_transit_readonly_preflight_result_is_normalized_and_redacted(self):
        result = normalize_worker_command_result(
            "transit_readonly_preflight",
            {
                "passed": False,
                "status": "blocked",
                "summary": "x" * 1200,
                "checks": [
                    {
                        "id": "planned_port_free",
                        "label": "Planned port",
                        "status": "failed",
                        "passed": False,
                        "detail": "port occupied",
                        "worker_token": "fake-token-that-must-not-survive",
                    }
                ],
                "worker_token": "fake-token-that-must-not-survive",
                "notes": "safe\x00text",
            },
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(str(result["summary"]).endswith("...[truncated]"))
        self.assertEqual(result["checks"][0]["id"], "planned_port_free")
        self.assertFalse(result["checks"][0]["passed"])
        self.assertEqual(result["checks"][0]["sensitive_output_redacted"], True)
        self.assertEqual(result["extra"]["worker_token"], "[redacted]")
        self.assertEqual(result["extra"]["notes"], "safetext")

    def test_transit_readonly_preflight_rejects_non_object_result(self):
        with self.assertRaises(ValueError):
            normalize_worker_command_result("transit_readonly_preflight", ["not", "an", "object"])

    def test_worker_report_body_rejects_invalid_json(self):
        with self.assertRaises(WorkerReportBodyError) as context:
            decode_worker_command_report_body(b"{not-json", len(b"{not-json"))

        self.assertEqual(context.exception.code, "WORKER_RESULT_PARSE_ERROR")

    def test_worker_report_body_rejects_non_object_json(self):
        with self.assertRaises(WorkerReportBodyError) as context:
            decode_worker_command_report_body(b"[]", len(b"[]"))

        self.assertEqual(context.exception.code, "WORKER_RESULT_INVALID_PAYLOAD")

    def test_worker_report_body_strips_nul_characters(self):
        payload = decode_worker_command_report_body(
            b'{"result":\x00{"summary":"safe"}}',
            len(b'{"result":\x00{"summary":"safe"}}'),
        )

        self.assertEqual(payload["result"]["summary"], "safe")

    def test_worker_report_body_limit_constant_is_bounded(self):
        self.assertLessEqual(WORKER_RESULT_BODY_LIMIT_BYTES, 128 * 1024)

    def test_worker_report_body_rejects_oversized_payload(self):
        with self.assertRaises(WorkerReportBodyError) as context:
            decode_worker_command_report_body(
                b'{"result":{}}',
                WORKER_RESULT_BODY_LIMIT_BYTES + 1,
            )

        self.assertEqual(context.exception.code, "WORKER_RESULT_BODY_TOO_LARGE")

    def test_worker_command_terminal_status_helper(self):
        self.assertTrue(worker_command_status_is_terminal("succeeded"))
        self.assertTrue(worker_command_status_is_terminal("failed"))
        self.assertTrue(worker_command_status_is_terminal("completed"))
        self.assertFalse(worker_command_status_is_terminal("running"))
        self.assertFalse(worker_command_status_is_terminal(None))

    def test_transit_route_create_command_type_is_registered(self):
        command = WorkerCommandCreate(command_type="transit_route_create", payload={"dry_run": True})
        self.assertEqual(command.command_type, "transit_route_create")
        self.assertEqual(
            minimum_worker_version_for_command("transit_route_create"),
            "0.1.20-stage-3.3.73",
        )
        self.assertEqual(
            minimum_worker_version_key_for_command("transit_route_create"),
            (0, 1, 20, 3, 3, 73),
        )

    def test_sanitize_command_payload_preserves_share_link_confirmation_boolean_only(self):
        payload = sanitize_command_payload(
            {
                "no_node_share_link_change_confirmed": True,
                "share_link": "vless://fake-redacted-example",
            }
        )

        self.assertEqual(payload["no_node_share_link_change_confirmed"], True)
        self.assertEqual(payload["share_link"], "[redacted]")

    def test_transit_route_create_result_is_normalized_as_compact_dry_run(self):
        result = normalize_worker_command_result(
            "transit_route_create",
            {
                "execution_mode": "dry_run",
                "real_execution": False,
                "status": "approval_required",
                "summary": "x" * 1200,
                "worker_version": "0.1.20-stage-3.3.73",
                "hostname": "WEPC202605221223335",
                "role": "transit",
                "interface_name": "eth0",
                "planned_listen_port": 23843,
                "landing_target_host": "64.90.13.19",
                "landing_target_port": 27939,
                "forwarding_method": "socat",
                "route_name": "hk-socat-live-23843",
                "planned_service_name": "liveline-socat-safe.service",
                "checks_count": 2,
                "planned_actions_count": 4,
                "checks": [
                    {"name": "dry_run_required", "passed": True, "detail": "safe dry-run"},
                    {"name": "no_listener_created", "passed": True},
                ],
                "planned_service": {
                    "exec_start": "this long service template must not be kept",
                },
                "worker_token": "fake-token-that-must-not-survive",
            },
        )

        self.assertEqual(result["execution_mode"], "dry_run")
        self.assertFalse(result["real_execution"])
        self.assertEqual(result["planned_listen_port"], 23843)
        self.assertEqual(result["landing_target_port"], 27939)
        self.assertEqual(result["forwarding_method"], "socat")
        self.assertEqual(result["checks_count"], 2)
        self.assertNotIn("planned_service", result)
        self.assertNotIn("worker_token", result)
        self.assertEqual(result["checks"][0]["name"], "dry_run_required")
        self.assertTrue(str(result["summary"]).endswith("...[truncated]"))

    def test_transit_route_create_real_failed_result_preserves_diagnostics(self):
        result = normalize_worker_command_result(
            "transit_route_create",
            {
                "execution_mode": "real_create",
                "real_execution": True,
                "status": "failed",
                "summary": "Approved socat transit route creation failed.",
                "redacted_error": "approved TCP port 23843 is not listening after socat start retries",
                "worker_version": "0.1.20-stage-3.3.73",
                "hostname": "WEPC202605221223335",
                "role": "transit",
                "interface_name": "eth0",
                "planned_listen_port": 23843,
                "landing_target_host": "64.90.13.19",
                "landing_target_port": 27939,
                "forwarding_method": "socat",
                "route_name": "hk-socat-live-23843",
                "service_name": "liveline-socat-23843.service",
                "service_path": "/etc/systemd/system/liveline-socat-23843.service",
                "listen_verification_attempts": [
                    {"attempt": 1, "service_active": "active", "listener_detected": False},
                    {"attempt": 2, "service_active": "active", "listener_detected": True},
                ],
                "last_listen_attempt": {"attempt": 2, "service_active": "active", "listener_detected": True},
                "diagnostics": {
                    "systemctl_is_active": {"status": "ok", "detail": "active", "error": ""},
                    "journal": {"status": "ok", "detail": "Started LiveLine", "error": ""},
                    "service_file": {
                        "exists": True,
                        "size_bytes": 280,
                        "contains_fixed_exec": True,
                        "contains_approved_name": True,
                    },
                },
                "rollback_attempted": True,
            },
        )

        self.assertEqual(result["execution_mode"], "real_create")
        self.assertTrue(result["real_execution"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["planned_listen_port"], 23843)
        self.assertEqual(result["service_name"], "liveline-socat-23843.service")
        self.assertTrue(result["rollback_attempted"])
        self.assertEqual(result["listen_verification_attempts"][0]["service_active"], "active")
        self.assertEqual(result["last_listen_attempt"]["attempt"], 2)
        self.assertEqual(result["diagnostics"]["journal"]["detail"], "Started LiveLine")
        self.assertTrue(result["diagnostics"]["service_file"]["contains_fixed_exec"])

    def test_transit_route_worker_create_plan_schema_requires_current_stage(self):
        payload = {
            "transit_resource_id": "1e222459-9fa2-4c62-800f-a3b35edb7df8",
            "landing_node_id": "a71472c6-f62c-43b5-a223-9f5f070ae4ef",
            "planned_listen_port": 23843,
            "landing_target_host": "64.90.13.19",
            "landing_target_port": 27939,
            "forwarding_method": "socat",
            "approval_stage": APPROVED_TRANSIT_ROUTE_CREATE_STAGE,
            "dry_run": True,
            "approval_required": True,
            "user_approved_execution_boundary": True,
            "no_node_share_link_change_confirmed": True,
            "no_cutover_confirmed": True,
        }
        parsed = TransitRouteWorkerCreatePlanRequest(**payload)
        self.assertTrue(parsed.dry_run)
        self.assertEqual(parsed.forwarding_method, "socat")

    def test_transit_route_worker_create_plan_schema_rejects_extra_shell(self):
        payload = {
            "transit_resource_id": "1e222459-9fa2-4c62-800f-a3b35edb7df8",
            "landing_node_id": "a71472c6-f62c-43b5-a223-9f5f070ae4ef",
            "planned_listen_port": 23843,
            "landing_target_host": "64.90.13.19",
            "landing_target_port": 27939,
            "forwarding_method": "socat",
            "approval_stage": APPROVED_TRANSIT_ROUTE_CREATE_STAGE,
            "dry_run": True,
            "approval_required": True,
            "user_approved_execution_boundary": True,
            "no_node_share_link_change_confirmed": True,
            "no_cutover_confirmed": True,
            "shell": "systemctl start anything",
        }
        with self.assertRaises(Exception):
            TransitRouteWorkerCreatePlanRequest(**payload)

    def test_transit_route_worker_create_execute_schema_accepts_confirmed_request(self):
        payload = {
            "transit_resource_id": "1e222459-9fa2-4c62-800f-a3b35edb7df8",
            "landing_node_id": "a71472c6-f62c-43b5-a223-9f5f070ae4ef",
            "planned_listen_port": 23843,
            "landing_target_host": "64.90.13.19",
            "landing_target_port": 27939,
            "forwarding_method": "socat",
            "route_name": "hk-socat-live-23843",
            "approval_stage": APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE,
            "dry_run": False,
            "approval_required": False,
            "user_approved_real_execution": True,
            "firewall_security_group_confirmed": True,
            "cloud_firewall_confirmed": True,
            "server_firewall_confirmed": True,
            "no_node_share_link_change_confirmed": True,
            "no_full_client_link_confirmed": True,
            "no_cutover_confirmed": True,
        }
        parsed = TransitRouteWorkerCreateExecuteRequest(**payload)
        self.assertFalse(parsed.dry_run)
        self.assertEqual(parsed.route_name, "hk-socat-live-23843")

    def test_transit_route_worker_create_execute_schema_rejects_extra_systemd_unit(self):
        payload = {
            "transit_resource_id": "1e222459-9fa2-4c62-800f-a3b35edb7df8",
            "landing_node_id": "a71472c6-f62c-43b5-a223-9f5f070ae4ef",
            "planned_listen_port": 23843,
            "landing_target_host": "64.90.13.19",
            "landing_target_port": 27939,
            "forwarding_method": "socat",
            "route_name": "hk-socat-live-23843",
            "approval_stage": APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE,
            "dry_run": False,
            "approval_required": False,
            "user_approved_real_execution": True,
            "firewall_security_group_confirmed": True,
            "cloud_firewall_confirmed": True,
            "server_firewall_confirmed": True,
            "no_node_share_link_change_confirmed": True,
            "no_full_client_link_confirmed": True,
            "no_cutover_confirmed": True,
            "systemd_unit": "[Service]\nExecStart=/bin/true",
        }
        with self.assertRaises(Exception):
            TransitRouteWorkerCreateExecuteRequest(**payload)


if __name__ == "__main__":
    unittest.main()
