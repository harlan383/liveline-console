import json
import unittest
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import transit_routes


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/transit-routes/protected-resource-registration-approval-dry-run",
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


class FakeSession:
    def add(self, item):
        raise AssertionError("approval dry-run endpoint must not call db.add")

    def commit(self):
        raise AssertionError("approval dry-run endpoint must not call db.commit")

    def flush(self):
        raise AssertionError("approval dry-run endpoint must not call db.flush")

    def refresh(self, item):
        raise AssertionError("approval dry-run endpoint must not call db.refresh")


def valid_payload(**overrides):
    payload = {
        "stage": "3.4.28",
        "mode": "approval_dry_run",
        "source_registration_dry_run": {
            "dry_run": True,
            "ready_for_next_stage": True,
            "expected_approval_text": "CONFIRM_PROTECTED_RESOURCE_REGISTRATION_DRY_RUN_29833",
            "normalized_preview": {
                "source": {
                    "route_name": "haproxy-tcp-29833",
                    "planned_listen_port": 29833,
                }
            },
        },
        "approval_text": "CONFIRM_PROTECTED_RESOURCE_REGISTRATION_DRY_RUN_29833",
        "confirmations": {
            "registration_dry_run_passed": True,
            "approval_text_matches_expected": True,
            "no_real_resource_creation": True,
            "no_worker_command_creation": True,
            "no_transit_route_creation": True,
            "no_haproxy_route_creation": True,
            "no_ssh_or_remote_execution": True,
            "no_firewall_change": True,
            "no_cutover": True,
            "ordinary_product_ui_unchanged": True,
            "sensitive_fields_redacted": True,
        },
    }
    payload.update(overrides)
    return transit_routes.ProtectedResourceRegistrationApprovalDryRunRequest(**payload)


def call_approval_dry_run(payload, db=None):
    with (
        patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()),
        patch.object(transit_routes, "csrf_valid", return_value=True),
    ):
        return transit_routes.protected_resource_registration_approval_dry_run(
            payload,
            make_request(),
            db or FakeSession(),
        )


def check_map(data):
    return {check["id"]: check for check in data["data"]["checks"]}


class ProtectedResourceRegistrationApprovalDryRunTests(unittest.TestCase):
    def assert_blocked_by(self, check_id: str, payload=None):
        response = call_approval_dry_run(payload or valid_payload())
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["dry_run"], True)
        self.assertFalse(data["data"]["approved_for_next_stage"])
        self.assertFalse(data["data"]["ready_for_command_create_next_stage"])
        self.assertFalse(check_map(data)[check_id]["passed"])
        return data

    def test_valid_payload_returns_approved_for_next_stage(self):
        response = call_approval_dry_run(valid_payload())
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["dry_run"], True)
        self.assertTrue(data["data"]["approved_for_next_stage"])
        self.assertTrue(data["data"]["ready_for_command_create_next_stage"])
        self.assertEqual(data["data"]["blocked_reasons"], [])
        self.assertEqual(
            data["data"]["recommended_next_stage"],
            "Stage 3.4.29-protected-resource-registration-command-create",
        )

    def test_endpoint_does_not_call_db_write_methods(self):
        response = call_approval_dry_run(valid_payload(), FakeSession())
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["approved_for_next_stage"])

    def test_wrong_stage_blocked(self):
        self.assert_blocked_by("stage_is_expected", valid_payload(stage="Stage 3.4.27"))

    def test_wrong_mode_blocked(self):
        self.assert_blocked_by("mode_is_approval_dry_run", valid_payload(mode="preview_only"))

    def test_registration_dry_run_not_passed_blocked(self):
        payload = valid_payload(
            source_registration_dry_run={
                **valid_payload().source_registration_dry_run.model_dump(),
                "ready_for_next_stage": False,
            }
        )
        self.assert_blocked_by("source_registration_dry_run_ready", payload)

    def test_approval_text_mismatch_blocked(self):
        payload = valid_payload(approval_text="CONFIRM_WRONG_TEXT")
        self.assert_blocked_by("approval_text_matches_expected", payload)

    def test_missing_confirmation_blocked(self):
        payload = valid_payload(
            confirmations={
                **valid_payload().confirmations.model_dump(),
                "no_worker_command_creation": False,
            }
        )
        self.assert_blocked_by("all_approval_confirmations_present", payload)
        self.assert_blocked_by("no_worker_command_creation_confirmed", payload)

    def test_response_does_not_include_sensitive_values_or_fields(self):
        response = call_approval_dry_run(valid_payload())
        data = response_payload(response)
        body = json.dumps(data, ensure_ascii=False).lower()

        self.assertTrue(data["success"])
        self.assertNotIn("vless" + "://", body)
        self.assertNotIn("share" + "_link", body)
        self.assertNotIn("private" + "_key", body)
        self.assertNotIn("install" + "_command", body)
        self.assertNotIn("pass" + "word", body)
        self.assertNotIn("to" + "ken", body)

    def test_sensitive_input_blocks_next_stage_without_echoing_value(self):
        sensitive_value = "vless" + "://example-sensitive"
        payload = valid_payload(approval_text=sensitive_value)
        response = call_approval_dry_run(payload)
        data = response_payload(response)
        body = json.dumps(data, ensure_ascii=False)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["approved_for_next_stage"])
        self.assertFalse(check_map(data)["response_sensitive_content_absent"]["passed"])
        self.assertNotIn(sensitive_value, body)


if __name__ == "__main__":
    unittest.main()
