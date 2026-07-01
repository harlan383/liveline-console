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
from app.models.vps_server import VpsServer
from app.models.worker_command import WorkerCommand


COMMAND_ID = "protected-command-1"
IDEMPOTENCY_KEY = "stage-3-4-30-idempotency-key"
TRANSIT_RESOURCE_ID = "transit-resource-created-1"
LANDING_NODE_ID = "landing-node-created-1"
VPS_ID = "vps-existing-1"
DEFAULT_COMMAND = object()
DEFAULT_VPS = object()


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/transit-routes/protected-resource-registration-execution-verify",
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


def registration_source_preview(**overrides):
    preview = {
        "source": {
            "dry_run_command_id": "dry-run-1",
            "route_name": "haproxy-tcp-29833",
            "planned_listen_port": 29833,
            "landing_target_host": "64.90.13.19",
            "landing_target_port": 28917,
            "candidate_integrity_ready": True,
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
        },
    }
    preview.update(overrides)
    return preview


def command_result_data(**overrides):
    data = {
        "stage": "3.4.29",
        "mode": "command_create",
        "command_status": "pending_protected_registration_execution",
        "idempotency_key": IDEMPOTENCY_KEY,
        "registration_source_preview": registration_source_preview(),
        "normalized_command_preview": {
            "stage": "3.4.29",
            "mode": "command_create",
            "command_type": "protected_resource_registration_command",
            "command_status": "pending_protected_registration_execution",
            "idempotency_key": IDEMPOTENCY_KEY,
            "source_approval_dry_run": {
                "dry_run": True,
                "stage": "3.4.28",
                "mode": "approval_dry_run",
                "approved_for_next_stage": True,
                "ready_for_command_create_next_stage": True,
                "registration_source_preview_present": True,
                "registration_source_ready": True,
            },
            "safety_boundary": {
                "local_pending_command_only": True,
                "no_real_resource_creation": True,
                "no_worker_remote_execution": True,
                "no_transit_route_creation": True,
                "no_haproxy_route_creation": True,
                "no_listening_port_change": True,
                "no_ssh_or_remote_execution": True,
                "no_firewall_change": True,
                "no_cutover": True,
                "ordinary_product_ui_unchanged": True,
            },
        },
        "safety_boundary": {
            "local_pending_command_only": True,
            "no_worker_remote_execution": True,
        },
    }
    data.update(overrides)
    return data


def make_command(**overrides):
    fields = {
        "id": COMMAND_ID,
        "task_type": "protected_resource_registration_command",
        "status": "pending_protected_registration_execution",
        "current_step": "awaiting_stage_3_4_30_execution_verify",
        "progress": 0,
        "result_data": command_result_data(),
    }
    fields.update(overrides)
    return Task(**fields)


def valid_payload(**overrides):
    payload = {
        "stage": "3.4.30",
        "mode": "execution_verify",
        "command_id": COMMAND_ID,
        "execution_approval_text": f"EXECUTE_PROTECTED_RESOURCE_REGISTRATION:{COMMAND_ID}",
        "confirmations": {
            "command_was_created_by_stage_3_4_29": True,
            "command_is_pending": True,
            "approval_dry_run_passed": True,
            "execute_local_db_registration_only": True,
            "allow_create_transit_resource_record": True,
            "allow_create_landing_node_record": True,
            "no_worker_command_creation": True,
            "no_transit_route_creation": True,
            "no_haproxy_route_creation": True,
            "no_haproxy_config_generation": True,
            "no_listening_port_change": True,
            "no_ssh_or_remote_execution": True,
            "no_firewall_change": True,
            "no_cutover": True,
            "ordinary_product_ui_unchanged": True,
            "sensitive_fields_redacted": True,
        },
    }
    payload.update(overrides)
    return transit_routes.ProtectedResourceRegistrationExecutionVerifyRequest(**payload)


class FakeSession:
    def __init__(
        self,
        *,
        command: Task | None | object = DEFAULT_COMMAND,
        transit_resources_by_entry: list[TransitResource] | None = None,
        transit_resources_by_name: list[TransitResource] | None = None,
        vps: VpsServer | None | object = DEFAULT_VPS,
        nodes_by_port: list[Node] | None = None,
        nodes_by_name: list[Node] | None = None,
    ) -> None:
        self.command = make_command() if command is DEFAULT_COMMAND else command
        self.transit_resources_by_entry = transit_resources_by_entry or []
        self.transit_resources_by_name = transit_resources_by_name or []
        self.vps = VpsServer(id=VPS_ID, name="香港落地", ip="64.90.13.19") if vps is DEFAULT_VPS else vps
        self.nodes_by_port = nodes_by_port or []
        self.nodes_by_name = nodes_by_name or []
        self.scalars_calls = 0
        self.added: list[object] = []
        self.commit_calls = 0

    def get(self, model, key):
        if model is Task and self.command and key == self.command.id:
            return self.command
        return None

    def scalars(self, statement):
        self.scalars_calls += 1
        if self.scalars_calls == 1:
            return FakeScalarResult(self.transit_resources_by_entry)
        if self.scalars_calls == 2:
            return FakeScalarResult(self.transit_resources_by_name)
        if self.scalars_calls == 3:
            return FakeScalarResult([self.vps] if self.vps else [])
        if self.scalars_calls == 4:
            return FakeScalarResult(self.nodes_by_port)
        return FakeScalarResult(self.nodes_by_name)

    def add(self, item):
        if isinstance(item, (WorkerCommand, TransitRoute)):
            raise AssertionError(f"execution verify must not create {type(item).__name__}")
        if not isinstance(item, (TransitResource, Node)):
            raise AssertionError(f"execution verify may add only TransitResource or Node, got {type(item).__name__}")
        self.added.append(item)

    def commit(self):
        self.commit_calls += 1

    def flush(self):
        raise AssertionError("execution verify endpoint must not call db.flush")

    def refresh(self, item):
        raise AssertionError("execution verify endpoint must not call db.refresh")


class NoWriteSession(FakeSession):
    def add(self, item):
        raise AssertionError("blocked execution verify must not call db.add")

    def commit(self):
        raise AssertionError("blocked execution verify must not call db.commit")


def call_execution_verify(payload, db=None):
    with (
        patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()),
        patch.object(transit_routes, "csrf_valid", return_value=True),
    ):
        return transit_routes.protected_resource_registration_execution_verify(
            payload,
            make_request(),
            db or FakeSession(),
        )


def check_map(data):
    return {check["id"]: check for check in data["data"]["checks"]}


class ProtectedResourceRegistrationExecutionVerifyTests(unittest.TestCase):
    def assert_blocked_by(self, check_id: str, payload=None, db=None):
        response = call_execution_verify(payload or valid_payload(), db or NoWriteSession())
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["executed"])
        self.assertFalse(data["data"]["ready_for_haproxy_dry_run_next_stage"])
        self.assertFalse(check_map(data)[check_id]["passed"])
        return data

    def test_valid_payload_creates_transit_resource_and_landing_node(self):
        db = FakeSession()
        response = call_execution_verify(valid_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["executed"])
        self.assertFalse(data["data"]["idempotent_reuse"])
        self.assertEqual(data["data"]["command_status"], "executed_verified")
        self.assertTrue(data["data"]["ready_for_haproxy_dry_run_next_stage"])
        self.assertTrue(data["data"]["created"]["transit_resource_id"])
        self.assertTrue(data["data"]["created"]["landing_node_id"])
        self.assertEqual(len(db.added), 2)
        self.assertIsInstance(db.added[0], TransitResource)
        self.assertIsInstance(db.added[1], Node)
        self.assertIsNone(db.added[1].share_link)
        self.assertEqual(db.command.status, "executed_verified")
        self.assertEqual(db.command.result_data["execution"]["created"], data["data"]["created"])
        self.assertEqual(db.commit_calls, 1)

    def test_valid_payload_reuses_existing_records_without_duplicate_create(self):
        existing_resource = TransitResource(
            id=TRANSIT_RESOURCE_ID,
            name="广州IEPL-香港出口01",
            resource_type="server",
            entry_host="109.244.79.147",
            entry_port=22,
            status="worker_online",
        )
        existing_node = Node(
            id=LANDING_NODE_ID,
            vps_id=VPS_ID,
            node_name="香港直连15m",
            xray_port=28917,
            status="active",
        )
        db = FakeSession(
            transit_resources_by_entry=[existing_resource],
            nodes_by_port=[existing_node],
        )
        response = call_execution_verify(valid_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["executed"])
        self.assertEqual(data["data"]["created"]["transit_resource_id"], TRANSIT_RESOURCE_ID)
        self.assertEqual(data["data"]["created"]["landing_node_id"], LANDING_NODE_ID)
        self.assertEqual(db.added, [])
        self.assertEqual(db.commit_calls, 1)

    def test_repeated_execution_reuses_command_result(self):
        command = make_command(
            status="executed_verified",
            result_data=command_result_data(
                command_status="executed_verified",
                execution={
                    "stage": "3.4.30",
                    "mode": "execution_verify",
                    "created": {
                        "transit_resource_id": TRANSIT_RESOURCE_ID,
                        "landing_node_id": LANDING_NODE_ID,
                    },
                    "verification": {
                        "transit_resource_exists": True,
                        "landing_node_exists": True,
                        "worker_command_created": False,
                        "transit_route_created": False,
                        "haproxy_route_created": False,
                        "listening_port_changed": False,
                        "remote_execution_triggered": False,
                        "firewall_changed": False,
                        "cutover_done": False,
                    },
                },
            ),
        )
        db = NoWriteSession(command=command)
        response = call_execution_verify(valid_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertTrue(data["data"]["executed"])
        self.assertTrue(data["data"]["idempotent_reuse"])
        self.assertEqual(data["data"]["created"]["transit_resource_id"], TRANSIT_RESOURCE_ID)
        self.assertEqual(data["data"]["created"]["landing_node_id"], LANDING_NODE_ID)

    def test_wrong_stage_blocked(self):
        self.assert_blocked_by("stage_is_expected", valid_payload(stage="3.4.29"))

    def test_wrong_mode_blocked(self):
        self.assert_blocked_by("mode_is_execution_verify", valid_payload(mode="command_create"))

    def test_command_id_missing_blocked(self):
        self.assert_blocked_by("command_exists", valid_payload(command_id="missing"), NoWriteSession(command=None))

    def test_wrong_command_type_blocked(self):
        command = make_command(task_type="transit_route_create")
        self.assert_blocked_by("command_type_is_protected_registration", valid_payload(), NoWriteSession(command=command))

    def test_command_without_approval_dry_run_blocked(self):
        bad_data = command_result_data(
            normalized_command_preview={
                **command_result_data()["normalized_command_preview"],
                "source_approval_dry_run": {
                    **command_result_data()["normalized_command_preview"]["source_approval_dry_run"],
                    "approved_for_next_stage": False,
                },
            }
        )
        command = make_command(result_data=bad_data)
        self.assert_blocked_by("source_approval_dry_run_passed", valid_payload(), NoWriteSession(command=command))

    def test_execution_approval_text_mismatch_blocked(self):
        self.assert_blocked_by(
            "approval_text_matches_expected",
            valid_payload(execution_approval_text="EXECUTE_PROTECTED_RESOURCE_REGISTRATION:wrong"),
        )

    def test_missing_confirmation_blocked(self):
        payload = valid_payload(
            confirmations={
                **valid_payload().confirmations.model_dump(),
                "no_worker_command_creation": False,
            }
        )
        self.assert_blocked_by("all_execution_confirmations_present", payload)
        self.assert_blocked_by("no_worker_command_creation_confirmed", payload)

    def test_missing_landing_vps_blocks_node_creation(self):
        db = NoWriteSession(vps=None)
        data = self.assert_blocked_by("landing_vps_exists", valid_payload(), db)

        self.assertFalse(data["data"]["verification"]["landing_node_exists"])

    def test_conflict_resource_blocks_execution(self):
        conflict = TransitResource(
            id="conflict-resource",
            name="另一个中转资源",
            resource_type="server",
            entry_host="109.244.79.147",
            entry_port=22,
            status="active",
        )
        db = NoWriteSession(transit_resources_by_entry=[conflict])
        self.assert_blocked_by("transit_resource_conflict_absent", valid_payload(), db)

    def test_sensitive_input_blocks_without_echoing_value(self):
        sensitive_value = "vless" + "://example-sensitive"
        command = make_command(
            result_data=command_result_data(
                registration_source_preview=registration_source_preview(
                    transit_resource_registration={
                        **registration_source_preview()["transit_resource_registration"],
                        "name": sensitive_value,
                    }
                )
            )
        )
        response = call_execution_verify(valid_payload(), NoWriteSession(command=command))
        data = response_payload(response)
        body = json.dumps(data, ensure_ascii=False)

        self.assertTrue(data["success"])
        self.assertFalse(data["data"]["executed"])
        self.assertFalse(check_map(data)["registration_source_preview_present"]["passed"])
        self.assertNotIn(sensitive_value, body)

    def test_response_does_not_include_sensitive_keywords(self):
        response = call_execution_verify(valid_payload(), FakeSession())
        data = response_payload(response)
        body = json.dumps(data, ensure_ascii=False).lower()

        self.assertTrue(data["success"])
        self.assertNotIn("vless" + "://", body)
        self.assertNotIn("share" + "_link", body)
        self.assertNotIn("private" + "_key", body)
        self.assertNotIn("install" + "_command", body)
        self.assertNotIn("pass" + "word", body)
        self.assertNotIn("to" + "ken", body)
        self.assertFalse(data["data"]["verification"]["worker_command_created"])
        self.assertFalse(data["data"]["verification"]["transit_route_created"])
        self.assertFalse(data["data"]["verification"]["haproxy_route_created"])
        self.assertFalse(data["data"]["verification"]["listening_port_changed"])
        self.assertFalse(data["data"]["verification"]["remote_execution_triggered"])
        self.assertFalse(data["data"]["verification"]["firewall_changed"])
        self.assertFalse(data["data"]["verification"]["cutover_done"])


if __name__ == "__main__":
    unittest.main()
