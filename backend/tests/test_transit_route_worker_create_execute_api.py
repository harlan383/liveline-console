import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import transit_routes
from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand
from app.schemas.transit_route import APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE, TransitRouteWorkerCreateExecuteRequest

TRANSIT_RESOURCE_ID = "02d16c43-d20c-46e9-b84c-a367343b48ae"
TRANSIT_WORKER_ID = "9c359d1a-f018-4484-992b-d2ed840cb88f"
LANDING_NODE_ID = "7cf3ec9c-8e76-418e-97c1-5ee3ddb28e31"
LANDING_VPS_ID = "a3e4c4bf-2b4a-4705-bb45-65d9da9c1cbf"


def make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/transit-routes/worker-create-execute",
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


class FakeSession:
    def __init__(
        self,
        *,
        resource_status: str = "worker_online",
        resource_deleted: bool = False,
        resource_entry_host: str | None = "163.223.216.108",
        node_status: str = "active",
        node_deleted: bool = False,
        node_share_link: bool = True,
        worker_status: str = "online",
        worker_role: str = "transit",
        worker_server_id: str = TRANSIT_RESOURCE_ID,
        worker_interface: str | None = "eth0",
        preflight: bool = True,
        preflight_match: bool = True,
        preflight_interface: str | None = "eth0",
        existing_route: TransitRoute | None = None,
        in_flight_command: WorkerCommand | None = None,
    ) -> None:
        self.existing_route = existing_route
        self.in_flight_command = in_flight_command
        self.scalar_calls = 0
        self.scalars_calls = 0
        self.added: list[object] = []
        self.resource = TransitResource(
            id=TRANSIT_RESOURCE_ID,
            name="wepc香港中转",
            resource_type="server",
            status=resource_status,
            entry_host=resource_entry_host,
            entry_port=22,
        )
        if resource_deleted:
            self.resource.deleted_at = datetime.now(timezone.utc)
        self.node = Node(
            id=LANDING_NODE_ID,
            vps_id=LANDING_VPS_ID,
            node_name="liveline-reality-27939",
            xray_port=27939,
            status=node_status,
            share_link="redacted-share-link-present" if node_share_link else None,
        )
        if node_deleted:
            self.node.deleted_at = datetime.now(timezone.utc)
        self.node.vps = VpsServer(id=LANDING_VPS_ID, ip="64.90.13.19")
        self.worker = Worker(
            id=TRANSIT_WORKER_ID,
            server_id=worker_server_id,
            role=worker_role,
            status=worker_status,
            interface_name=worker_interface,
            worker_version="0.1.22-stage-3.3.107",
            worker_secret_hash="hash",
            last_heartbeat_at=datetime.now(timezone.utc),
        )
        self.preflight_commands = (
            [
                self._preflight_command(
                    matching=preflight_match,
                    interface_name=preflight_interface,
                )
            ]
            if preflight
            else []
        )

    def _preflight_command(self, *, matching: bool, interface_name: str | None) -> WorkerCommand:
        payload = {
            "transit_resource_id": TRANSIT_RESOURCE_ID,
            "landing_node_id": LANDING_NODE_ID if matching else "other-node",
            "planned_listen_port": 23843,
            "landing_target_host": "64.90.13.19",
            "landing_target_port": 27939,
            "forwarding_method": "socat",
        }
        result = {"status": "passed", "passed": True}
        if interface_name:
            result["interface_name"] = interface_name
        return WorkerCommand(
            id="preflight-command",
            worker_id=TRANSIT_WORKER_ID,
            server_type="transit",
            server_id=TRANSIT_RESOURCE_ID,
            command_type="transit_readonly_preflight",
            payload_json=payload,
            result_json=result,
            status="succeeded",
            attempts=1,
            completed_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )

    def get(self, model, key):
        if model is TransitResource and key == self.resource.id:
            return self.resource
        if model is Node and key == self.node.id:
            return self.node
        return None

    def scalar(self, statement):
        self.scalar_calls += 1
        if self.scalar_calls == 1:
            return self.existing_route
        if self.scalar_calls == 2:
            return self.in_flight_command
        return None

    def scalars(self, statement):
        self.scalars_calls += 1
        if self.scalars_calls <= 2:
            return FakeScalarResult(self.preflight_commands)
        workers = [self.worker] if self.worker.server_id == TRANSIT_RESOURCE_ID and self.worker.role == "transit" else []
        return FakeScalarResult(workers)

    def add(self, item):
        self.added.append(item)

    def flush(self):
        for item in self.added:
            if isinstance(item, WorkerCommand) and not item.id:
                item.id = "created-command"

    def commit(self):
        return None

    def refresh(self, item):
        return None


def valid_payload(**overrides):
    payload = {
        "transit_resource_id": TRANSIT_RESOURCE_ID,
        "landing_node_id": LANDING_NODE_ID,
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
    payload.update(overrides)
    return TransitRouteWorkerCreateExecuteRequest(**payload)


def call_execute(payload, db):
    with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
        transit_routes, "csrf_valid", return_value=True
    ):
        return transit_routes.create_transit_route_worker_create_execute(
            payload,
            make_request(),
            db,
        )


class TransitRouteWorkerCreateExecuteApiTests(unittest.TestCase):
    def test_execute_endpoint_rejects_dry_run_true(self):
        response = call_execute(valid_payload(dry_run=True), FakeSession())
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_ROUTE_REAL_CREATE_REQUIRED")

    def test_execute_endpoint_rejects_missing_firewall_confirmation(self):
        response = call_execute(valid_payload(firewall_security_group_confirmed=False), FakeSession())
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "SECURITY_GROUP_CONFIRMATION_REQUIRED")

    def test_execute_endpoint_rejects_missing_share_link_confirmation(self):
        response = call_execute(valid_payload(no_node_share_link_change_confirmed=False), FakeSession())
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "NODE_SHARE_LINK_BOUNDARY_REQUIRED")

    def test_execute_endpoint_rejects_missing_no_cutover_confirmation(self):
        response = call_execute(valid_payload(no_cutover_confirmed=False), FakeSession())
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "NO_CUTOVER_CONFIRMATION_REQUIRED")

    def test_execute_endpoint_accepts_worker_online_resource_and_creates_command(self):
        db = FakeSession(resource_status="worker_online")
        response = call_execute(valid_payload(), db)
        data = response_payload(response)

        self.assertTrue(data["success"])
        commands = [item for item in db.added if isinstance(item, WorkerCommand)]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].command_type, "transit_route_create")
        self.assertEqual(commands[0].payload_json["transit_resource_id"], TRANSIT_RESOURCE_ID)
        self.assertEqual(commands[0].payload_json["landing_node_id"], LANDING_NODE_ID)
        self.assertEqual(commands[0].payload_json["transit_worker_id"], TRANSIT_WORKER_ID)
        self.assertEqual(data["data"]["target_worker_id"], TRANSIT_WORKER_ID)

    def test_execute_endpoint_accepts_active_resource(self):
        response = call_execute(valid_payload(), FakeSession(resource_status="active"))
        data = response_payload(response)

        self.assertTrue(data["success"])

    def test_execute_endpoint_rejects_deleted_resource(self):
        response = call_execute(valid_payload(), FakeSession(resource_deleted=True))
        data = response_payload(response)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(data["error_code"], "TRANSIT_RESOURCE_NOT_FOUND")

    def test_execute_endpoint_rejects_resource_without_entry_host(self):
        response = call_execute(valid_payload(), FakeSession(resource_entry_host=None))
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_RESOURCE_NOT_USABLE")

    def test_execute_endpoint_rejects_non_approved_listen_port(self):
        response = call_execute(valid_payload(planned_listen_port=25000), FakeSession())
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_PORT_NOT_APPROVED")

    def test_execute_endpoint_rejects_non_socat_method(self):
        response = call_execute(valid_payload(forwarding_method="gost"), FakeSession())
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_METHOD_NOT_APPROVED")

    def test_execute_endpoint_rejects_missing_landing_share_link(self):
        response = call_execute(valid_payload(), FakeSession(node_share_link=False))
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_LANDING_NODE_SHARE_LINK_REQUIRED")

    def test_execute_endpoint_rejects_inactive_landing_node(self):
        response = call_execute(valid_payload(), FakeSession(node_status="disabled"))
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_LANDING_NODE_NOT_ACTIVE")

    def test_execute_endpoint_rejects_duplicate_route(self):
        existing = TransitRoute(
            id="existing-route",
            transit_resource_id=TRANSIT_RESOURCE_ID,
            node_id=LANDING_NODE_ID,
            listen_port=23843,
            target_host="64.90.13.19",
            target_port=27939,
            forwarding_method="socat",
            service_name="liveline-socat-23843.service",
            service_path="/etc/systemd/system/liveline-socat-23843.service",
            status="active",
        )
        response = call_execute(valid_payload(), FakeSession(existing_route=existing))
        data = response_payload(response)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["error_code"], "TRANSIT_PORT_ALREADY_EXISTS")

    def test_execute_endpoint_rejects_missing_preflight(self):
        response = call_execute(valid_payload(), FakeSession(preflight=False))
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_PREFLIGHT_REQUIRED")

    def test_execute_endpoint_rejects_mismatched_preflight(self):
        response = call_execute(valid_payload(), FakeSession(preflight_match=False))
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_PREFLIGHT_TARGET_MISMATCH")

    def test_execute_endpoint_rejects_preflight_without_interface(self):
        response = call_execute(valid_payload(), FakeSession(preflight_interface=None))
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_PREFLIGHT_TARGET_MISMATCH")

    def test_execute_endpoint_rejects_worker_interface_mismatch(self):
        response = call_execute(valid_payload(), FakeSession(worker_interface="ens17"))
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_WORKER_INTERFACE_MISMATCH")

    def test_execute_endpoint_rejects_wrong_worker_role(self):
        response = call_execute(valid_payload(), FakeSession(worker_role="landing"))
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_WORKER_NOT_ONLINE")

    def test_execute_endpoint_rejects_offline_worker(self):
        response = call_execute(valid_payload(), FakeSession(worker_status="offline"))
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_WORKER_NOT_ONLINE")


if __name__ == "__main__":
    unittest.main()
