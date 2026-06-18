import json
import unittest
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import transit_routes
from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer
from app.schemas.transit_route import APPROVED_TRANSIT_ROUTE_REAL_CREATE_STAGE, TransitRouteWorkerCreateExecuteRequest


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


class FakeSession:
    def __init__(self, existing_route: TransitRoute | None = None) -> None:
        self.existing_route = existing_route
        self.resource = TransitResource(
            id="1e222459-9fa2-4c62-800f-a3b35edb7df8",
            name="香港中转服务器",
            resource_type="server",
            status="active",
        )
        self.node = Node(
            id="a71472c6-f62c-43b5-a223-9f5f070ae4ef",
            vps_id="landing-vps",
            node_name="liveline-reality-27939",
            xray_port=27939,
            status="active",
        )
        self.node.vps = VpsServer(id="landing-vps", ip="64.90.13.19")

    def get(self, model, key):
        if model is TransitResource and key == self.resource.id:
            return self.resource
        if model is Node and key == self.node.id:
            return self.node
        return None

    def scalar(self, statement):
        return self.existing_route


def valid_payload(**overrides):
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
    payload.update(overrides)
    return TransitRouteWorkerCreateExecuteRequest(**payload)


class TransitRouteWorkerCreateExecuteApiTests(unittest.TestCase):
    def test_execute_endpoint_rejects_dry_run_true(self):
        payload = valid_payload(dry_run=True)
        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.create_transit_route_worker_create_execute(
                payload,
                make_request(),
                FakeSession(),
            )
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_ROUTE_REAL_CREATE_REQUIRED")

    def test_execute_endpoint_rejects_missing_firewall_confirmation(self):
        payload = valid_payload(firewall_security_group_confirmed=False)
        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.create_transit_route_worker_create_execute(
                payload,
                make_request(),
                FakeSession(),
            )
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "SECURITY_GROUP_CONFIRMATION_REQUIRED")

    def test_execute_endpoint_rejects_missing_share_link_confirmation(self):
        payload = valid_payload(no_node_share_link_change_confirmed=False)
        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.create_transit_route_worker_create_execute(
                payload,
                make_request(),
                FakeSession(),
            )
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "NODE_SHARE_LINK_BOUNDARY_REQUIRED")

    def test_execute_endpoint_rejects_missing_no_cutover_confirmation(self):
        payload = valid_payload(no_cutover_confirmed=False)
        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.create_transit_route_worker_create_execute(
                payload,
                make_request(),
                FakeSession(),
            )
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "NO_CUTOVER_CONFIRMATION_REQUIRED")

    def test_execute_endpoint_rejects_duplicate_route(self):
        payload = valid_payload()
        existing = TransitRoute(
            id="existing-route",
            transit_resource_id="1e222459-9fa2-4c62-800f-a3b35edb7df8",
            node_id="a71472c6-f62c-43b5-a223-9f5f070ae4ef",
            listen_port=23843,
            target_host="64.90.13.19",
            target_port=27939,
            forwarding_method="socat",
            service_name="liveline-socat-23843.service",
            service_path="/etc/systemd/system/liveline-socat-23843.service",
            status="active",
        )
        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.create_transit_route_worker_create_execute(
                payload,
                make_request(),
                FakeSession(existing_route=existing),
            )
        data = response_payload(response)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["error_code"], "TRANSIT_PORT_ALREADY_PLANNED")


if __name__ == "__main__":
    unittest.main()
