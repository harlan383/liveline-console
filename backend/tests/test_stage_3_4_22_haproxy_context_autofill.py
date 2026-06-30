import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import transit_routes
from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.vps_server import VpsServer
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand

TRANSIT_RESOURCE_ID = "80ec346d-3ac1-402e-ab09-33cb404ca81c"
TRANSIT_WORKER_ID = "f2e16197-e953-46dd-90af-66f64759a2a9"
LANDING_NODE_ID = "a71472c6-f62c-43b5-a223-9f5f070ae4ef"
LANDING_VPS_ID = "968519b3-9017-4b27-a9a0-d5731033f84f"
DRY_RUN_COMMAND_ID = "ecfcf03a-8549-4b4a-9214-abebf6eee7f"
SENSITIVE_LINK_PREFIX = "vl" + "ess://"


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/transit-routes/haproxy-runtime-debug-context",
            "headers": [],
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
        "transit_worker_id": TRANSIT_WORKER_ID,
        "landing_node_id": LANDING_NODE_ID,
        "landing_node_name": "liveline-reality-28917",
        "planned_listen_port": 29833,
        "approved_planned_listen_port": 29833,
        "approved_firewall_confirmation": True,
        "landing_target_host": "64.90.13.19",
        "approved_landing_target_host": "64.90.13.19",
        "landing_target_port": 28917,
        "approved_landing_target_port": 28917,
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
        "route_name": "haproxy-tcp-29833",
        "route_display_name": "mk香港落地15m",
        "planned_service_name": "liveline-haproxy-29833.service",
        "payload_json": {"must": "not leak"},
        "install_command": "curl example.invalid/install.sh",
        "token": "secret-token",
        "private_key": "secret-private-key",
        "candidate_link": f"{SENSITIVE_LINK_PREFIX}secret.example",
    }
    payload.update(overrides)
    return payload


class FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_called = False
        self.flush_called = False
        self.refresh_called = False
        now = datetime(2026, 6, 30, 8, 0, 0, tzinfo=timezone.utc)
        self.resource = TransitResource(
            id=TRANSIT_RESOURCE_ID,
            name="mkiepl广港",
            resource_type="server",
            status="worker_online",
            entry_host="109.244.79.147",
            entry_port=22,
            entry_region="广州",
            exit_region="香港",
        )
        self.resource.created_at = now
        self.node = Node(
            id=LANDING_NODE_ID,
            vps_id=LANDING_VPS_ID,
            node_name="香港直连15m",
            xray_port=28917,
            status="active",
            service_status="active",
            protocol="vless",
            security="reality",
            transport="tcp",
            share_link=f"{SENSITIVE_LINK_PREFIX}uuid@example.invalid:28917?x=redacted#leak",
        )
        self.node.created_at = now
        self.node.vps = VpsServer(id=LANDING_VPS_ID, ip="64.90.13.19")
        self.worker = Worker(
            id=TRANSIT_WORKER_ID,
            server_id=TRANSIT_RESOURCE_ID,
            role="transit",
            status="online",
            interface_name="eth0",
            hostname="MKiepl",
            worker_version="0.1.41-stage-3.3.206-bbr-sysctl-sandbox-fix",
            worker_secret_hash="hash",
            last_heartbeat_at=now,
        )
        self.worker.created_at = now
        self.worker.registered_at = now
        self.good_command = WorkerCommand(
            id=DRY_RUN_COMMAND_ID,
            worker_id=TRANSIT_WORKER_ID,
            server_type="transit",
            server_id=TRANSIT_RESOURCE_ID,
            command_type="transit_route_create",
            payload_json=dry_run_payload(),
            status="succeeded",
            attempts=1,
            created_at=now,
            updated_at=now,
        )
        self.non_haproxy_command = WorkerCommand(
            id="non-haproxy",
            worker_id=TRANSIT_WORKER_ID,
            server_type="transit",
            server_id=TRANSIT_RESOURCE_ID,
            command_type="transit_route_create",
            payload_json=dry_run_payload(forwarding_method="socat"),
            status="succeeded",
            attempts=1,
            created_at=now,
            updated_at=now,
        )
        self.real_execution_command = WorkerCommand(
            id="real-execution",
            worker_id=TRANSIT_WORKER_ID,
            server_type="transit",
            server_id=TRANSIT_RESOURCE_ID,
            command_type="transit_route_create",
            payload_json=dry_run_payload(
                command_intent="haproxy_route_create_real_execution",
                dry_run=False,
                approval_required=False,
                real_execution=True,
                user_approved_real_execution=True,
            ),
            status="pending",
            attempts=0,
            created_at=now,
            updated_at=now,
        )

    def scalars(self, statement):
        text = str(statement)
        if "FROM workers" in text:
            return FakeScalarResult([self.worker])
        if "FROM transit_resources" in text:
            return FakeScalarResult([self.resource])
        if "FROM nodes" in text:
            return FakeScalarResult([self.node])
        if "FROM worker_commands" in text:
            return FakeScalarResult([self.good_command, self.non_haproxy_command, self.real_execution_command])
        return FakeScalarResult([])

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.commit_called = True

    def flush(self):
        self.flush_called = True

    def refresh(self, _item):
        self.refresh_called = True


def call_context(db):
    with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()):
        return transit_routes.get_haproxy_runtime_debug_context(make_request(), db)


class Stage3422HaproxyContextAutofillTest(unittest.TestCase):
    def test_context_endpoint_readonly_success(self):
        db = FakeSession()
        payload = response_payload(call_context(db))

        self.assertTrue(payload["success"])
        data = payload["data"]
        self.assertEqual(1, len(data["transit_resources"]))
        self.assertEqual(1, len(data["landing_nodes"]))
        self.assertEqual(1, len(data["haproxy_dry_run_commands"]))
        self.assertFalse(db.added)
        self.assertFalse(db.commit_called)
        self.assertFalse(db.flush_called)
        self.assertFalse(db.refresh_called)
        self.assertIn("no Worker command created", data["safety_boundary"])
        self.assertIn("no TransitRoute created", data["safety_boundary"])

    def test_dry_run_candidate_is_sanitized(self):
        payload = response_payload(call_context(FakeSession()))
        dumped = json.dumps(payload, ensure_ascii=False)
        candidate = payload["data"]["haproxy_dry_run_commands"][0]

        self.assertNotIn("payload_json", candidate)
        self.assertNotIn("candidate_link", dumped)
        self.assertNotIn("install_command", dumped)
        self.assertNotIn("secret-token", dumped)
        self.assertNotIn("secret-private-key", dumped)
        self.assertNotIn(SENSITIVE_LINK_PREFIX, dumped)
        self.assertNotIn("uuid@example.invalid", dumped)

    def test_only_haproxy_dry_run_candidates_are_included(self):
        payload = response_payload(call_context(FakeSession()))
        candidates = payload["data"]["haproxy_dry_run_commands"]

        self.assertEqual([DRY_RUN_COMMAND_ID], [candidate["id"] for candidate in candidates])
        self.assertEqual("haproxy_route_create_dry_run", candidates[0]["command_intent"])
        self.assertEqual("haproxy_tcp", candidates[0]["forwarding_method"])
        self.assertIs(candidates[0]["dry_run"], True)
        self.assertIs(candidates[0]["real_execution"], False)

    def test_candidate_fields_can_build_readiness_payload(self):
        payload = response_payload(call_context(FakeSession()))
        candidate = payload["data"]["haproxy_dry_run_commands"][0]

        readiness_payload = {
            "dry_run_command_id": candidate["id"],
            "transit_resource_id": candidate["transit_resource_id"],
            "landing_node_id": candidate["landing_node_id"],
            "planned_listen_port": candidate["planned_listen_port"],
            "landing_target_host": candidate["landing_target_host"],
            "landing_target_port": candidate["landing_target_port"],
            "forwarding_method": candidate["forwarding_method"],
            "route_name": candidate["route_name"],
            "route_display_name": candidate["route_display_name"],
            "planned_service_name": candidate["planned_service_name"],
        }
        self.assertEqual(29833, readiness_payload["planned_listen_port"])
        self.assertEqual("64.90.13.19", readiness_payload["landing_target_host"])
        self.assertEqual(28917, readiness_payload["landing_target_port"])
        self.assertEqual("haproxy-tcp-29833", readiness_payload["route_name"])
        self.assertEqual("liveline-haproxy-29833.service", readiness_payload["planned_service_name"])


if __name__ == "__main__":
    unittest.main()
