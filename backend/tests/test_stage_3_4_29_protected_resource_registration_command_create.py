import json
import unittest
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import transit_routes
from app.models.node import Node
from app.models.task import Task
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.worker_command import WorkerCommand


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/transit-routes/protected-resource-registration-command-create",
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
    def __init__(self, existing_tasks: list[Task] | None = None) -> None:
        self.existing_tasks = existing_tasks or []
        self.added: list[object] = []
        self.commit_calls = 0

    def scalars(self, statement):
        return FakeScalarResult(self.existing_tasks)

    def add(self, item):
        forbidden_models = (TransitResource, Node, TransitRoute, WorkerCommand)
        if isinstance(item, forbidden_models):
            raise AssertionError(f"command-create must not create {type(item).__name__}")
        if not isinstance(item, Task):
            raise AssertionError(f"command-create may add only Task records, got {type(item).__name__}")
        self.added.append(item)

    def commit(self):
        self.commit_calls += 1

    def flush(self):
        raise AssertionError("command-create endpoint must not call db.flush")

    def refresh(self, item):
        raise AssertionError("command-create endpoint must not call db.refresh")


class NoWriteSession(FakeSession):
    def add(self, item):
        raise AssertionError("blocked command-create must not call db.add")

    def commit(self):
        raise AssertionError("blocked command-create must not call db.commit")


def valid_payload(**overrides):
    payload = {
        "stage": "3.4.29",
        "mode": "command_create",
        "source_approval_dry_run": {
            "dry_run": True,
            "stage": "3.4.28",
            "mode": "approval_dry_run",
            "approved_for_next_stage": True,
            "ready_for_command_create_next_stage": True,
            "normalized_approval_preview": {
                "stage": "3.4.28",
                "mode": "approval_dry_run",
                "source_registration_dry_run": {
                    "dry_run": True,
                    "ready_for_next_stage": True,
                    "normalized_preview_present": True,
                    "normalized_preview_key_count": 4,
                },
            },
            "safety_boundary": {
                "no_real_resource_creation": True,
                "no_worker_command_creation": True,
                "no_transit_route_creation": True,
                "no_haproxy_route_creation": True,
                "no_ssh_or_remote_execution": True,
                "no_firewall_change": True,
                "no_cutover": True,
                "ordinary_product_ui_unchanged": True,
            },
        },
        "confirmations": {
            "approval_dry_run_passed": True,
            "create_local_pending_command_only": True,
            "no_real_resource_creation": True,
            "no_transit_resource_creation": True,
            "no_landing_node_creation": True,
            "no_worker_remote_execution": True,
            "no_transit_route_creation": True,
            "no_haproxy_route_creation": True,
            "no_listening_port_change": True,
            "no_ssh_or_remote_execution": True,
            "no_firewall_change": True,
            "no_cutover": True,
            "ordinary_product_ui_unchanged": True,
            "sensitive_fields_redacted": True,
        },
    }
    payload.update(overrides)
    return transit_routes.ProtectedResourceRegistrationCommandCreateRequest(**payload)


def call_command_create(payload, db=None):
    with (
        patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()),
        patch.object(transit_routes, "csrf_valid", return_value=True),
    ):
        return transit_routes.protected_resource_registration_command_create(
            payload,
            make_request(),
            db or FakeSession(),
        )


def check_map(data):
    return {check["id"]: check for check in data["data"]["checks"]}


class ProtectedResourceRegistrationCommandCreateTests(unittest.TestCase):
    def assert_blocked_by(self, check_id: str, payload=None):
        response = call_command_create(payload or valid_payload(), NoWriteSession())
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["created"])
        self.assertFalse(data["data"]["ready_for_execution_next_stage"])
        self.assertFalse(check_map(data)[check_id]["passed"])
        return data

    def test_valid_payload_creates_local_pending_task_record(self):
        db = FakeSession()
        response = call_command_create(valid_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["created"])
        self.assertEqual(data["data"]["mode"], "command_create")
        self.assertEqual(data["data"]["command_status"], "pending_protected_registration_execution")
        self.assertTrue(data["data"]["ready_for_execution_next_stage"])
        self.assertFalse(data["data"]["idempotent_reuse"])
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.commit_calls, 1)
        command_task = db.added[0]
        self.assertIsInstance(command_task, Task)
        self.assertEqual(command_task.task_type, "protected_resource_registration_command")
        self.assertEqual(command_task.status, "pending_protected_registration_execution")
        self.assertEqual(command_task.current_step, "awaiting_stage_3_4_30_execution_verify")
        self.assertEqual(command_task.result_data["idempotency_key"], data["data"]["idempotency_key"])

    def test_command_preview_is_sanitized_and_boundary_explicit(self):
        response = call_command_create(valid_payload())
        data = response_payload(response)
        preview = data["data"]["normalized_command_preview"]
        body = json.dumps(data, ensure_ascii=False).lower()

        self.assertTrue(data["success"])
        self.assertEqual(preview["command_type"], "protected_resource_registration_command")
        self.assertEqual(preview["command_status"], "pending_protected_registration_execution")
        self.assertTrue(data["data"]["safety_boundary"]["local_pending_command_only"])
        self.assertTrue(data["data"]["safety_boundary"]["no_worker_remote_execution"])
        self.assertTrue(data["data"]["safety_boundary"]["ordinary_product_ui_unchanged"])
        self.assertNotIn("vless" + "://", body)
        self.assertNotIn("share" + "_link", body)
        self.assertNotIn("private" + "_key", body)
        self.assertNotIn("install" + "_command", body)
        self.assertNotIn("pass" + "word", body)
        self.assertNotIn("to" + "ken", body)

    def test_wrong_stage_blocked(self):
        self.assert_blocked_by("stage_is_expected", valid_payload(stage="3.4.28"))

    def test_wrong_mode_blocked(self):
        self.assert_blocked_by("mode_is_command_create", valid_payload(mode="approval_dry_run"))

    def test_source_approval_dry_run_not_passed_blocked(self):
        payload = valid_payload(
            source_approval_dry_run={
                **valid_payload().source_approval_dry_run.model_dump(),
                "approved_for_next_stage": False,
            }
        )
        self.assert_blocked_by("source_approval_approved_for_next_stage", payload)

    def test_source_approval_stage_and_mode_must_match(self):
        stage_payload = valid_payload(
            source_approval_dry_run={**valid_payload().source_approval_dry_run.model_dump(), "stage": "3.4.27"}
        )
        mode_payload = valid_payload(
            source_approval_dry_run={**valid_payload().source_approval_dry_run.model_dump(), "mode": "command_create"}
        )

        self.assert_blocked_by("source_approval_stage_is_expected", stage_payload)
        self.assert_blocked_by("source_approval_mode_is_expected", mode_payload)

    def test_missing_confirmation_blocked(self):
        payload = valid_payload(
            confirmations={
                **valid_payload().confirmations.model_dump(),
                "no_worker_remote_execution": False,
            }
        )
        self.assert_blocked_by("all_command_create_confirmations_present", payload)
        self.assert_blocked_by("no_worker_remote_execution_confirmed", payload)

    def test_sensitive_input_blocks_without_echoing_value(self):
        sensitive_value = "vless" + "://example-sensitive"
        payload = valid_payload(
            source_approval_dry_run={
                **valid_payload().source_approval_dry_run.model_dump(),
                "normalized_approval_preview": {"note": sensitive_value},
            }
        )
        response = call_command_create(payload, NoWriteSession())
        data = response_payload(response)
        body = json.dumps(data, ensure_ascii=False)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["created"])
        self.assertFalse(check_map(data)["response_sensitive_content_absent"]["passed"])
        self.assertNotIn(sensitive_value, body)

    def test_idempotent_reuse_returns_existing_pending_task(self):
        payload = valid_payload()
        idempotency_key = transit_routes.protected_registration_command_create_idempotency_key(payload)
        existing_task = Task(
            id="existing-command-1",
            task_type="protected_resource_registration_command",
            status="pending_protected_registration_execution",
            current_step="awaiting_stage_3_4_30_execution_verify",
            progress=0,
            result_data={"idempotency_key": idempotency_key},
        )
        db = FakeSession(existing_tasks=[existing_task])
        response = call_command_create(payload, db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["created"])
        self.assertTrue(data["data"]["idempotent_reuse"])
        self.assertEqual(data["data"]["command_id"], "existing-command-1")
        self.assertEqual(data["data"]["command_status"], "pending_protected_registration_execution")
        self.assertEqual(db.added, [])
        self.assertEqual(db.commit_calls, 0)


if __name__ == "__main__":
    unittest.main()
