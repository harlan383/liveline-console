import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import nodes, transit_resources, transit_routes, vps
from app.models.audit_log import AuditLog
from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer


class FakeAdminSession:
    admin_id = "admin-1"


def make_request(path: str, method: str = "DELETE") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
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


class FakeDb:
    def __init__(self, *, objects=None, scalar_values=None) -> None:
        self.objects = objects or {}
        self.scalar_values = list(scalar_values or [])
        self.added: list[object] = []
        self.committed = False

    def get(self, model, key):
        return self.objects.get((model, key))

    def scalar(self, statement):
        if self.scalar_values:
            return self.scalar_values.pop(0)
        return None

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True


def route() -> TransitRoute:
    return TransitRoute(
        id="route-1",
        name="hk-socat-live-23843",
        transit_resource_id="resource-1",
        node_id="node-1",
        listen_port=23843,
        target_host="64.90.13.19",
        target_port=27939,
        forwarding_method="socat",
        service_name="liveline-socat-23843.service",
        service_path="/etc/systemd/system/liveline-socat-23843.service",
        status="active",
        share_link=None,
    )


class ResourceSafeDeleteTests(unittest.TestCase):
    def test_vps_delete_requires_confirm(self):
        db = FakeDb()
        with patch.object(vps, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            vps, "csrf_valid", return_value=True
        ):
            response = vps.delete_vps("vps-1", make_request("/api/vps/vps-1"), confirm=False, db=db)

        data = response_payload(response)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "CONFIRMATION_REQUIRED")

    def test_vps_delete_rejects_active_nodes_without_cascade(self):
        server = VpsServer(id="vps-1", name="landing", ip="64.90.13.19", status="active")
        node = Node(id="node-1", vps_id="vps-1", node_name="direct", status="active")
        server.nodes = [node]
        db = FakeDb(objects={(VpsServer, "vps-1"): server})

        with patch.object(vps, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            vps, "csrf_valid", return_value=True
        ):
            response = vps.delete_vps("vps-1", make_request("/api/vps/vps-1"), confirm=True, db=db)

        data = response_payload(response)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["error_code"], "VPS_HAS_ACTIVE_NODES")
        self.assertEqual(server.status, "active")
        self.assertIsNone(node.deleted_at)
        self.assertFalse(db.committed)

    def test_node_delete_soft_deletes_without_share_link_mutation(self):
        node = Node(
            id="node-1",
            vps_id="vps-1",
            node_name="direct",
            status="active",
            share_link="vless" + "://fake-redacted-example",
        )
        db = FakeDb(objects={(Node, "node-1"): node})

        with patch.object(nodes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            nodes, "csrf_valid", return_value=True
        ):
            response = nodes.delete_node("node-1", make_request("/api/nodes/node-1"), confirm=True, db=db)

        data = response_payload(response)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["delete_mode"], "soft_delete")
        self.assertFalse(data["data"]["remote_action_performed"])
        self.assertEqual(node.status, "deleted")
        self.assertIsNotNone(node.deleted_at)
        self.assertEqual(node.share_link, "vless" + "://fake-redacted-example")
        self.assertTrue(db.committed)
        self.assertEqual([item.action for item in db.added if isinstance(item, AuditLog)], ["delete_node_record"])

    def test_transit_resource_delete_rejects_active_routes(self):
        resource = TransitResource(id="resource-1", name="hk", resource_type="server", status="active")
        db = FakeDb(scalar_values=[resource, route()])

        with patch.object(transit_resources, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_resources, "csrf_valid", return_value=True
        ):
            response = transit_resources.delete_transit_resource(
                "resource-1",
                make_request("/api/transit-resources/resource-1"),
                confirm=True,
                db=db,
            )

        data = response_payload(response)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["error_code"], "TRANSIT_RESOURCE_HAS_ACTIVE_ROUTES")
        self.assertIsNone(resource.deleted_at)
        self.assertFalse(db.committed)

    def test_transit_route_delete_rejects_cutover_like_share_link(self):
        existing = route()
        existing.share_link = "vless" + "://fake-redacted-example"
        db = FakeDb(scalar_values=[existing])

        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.delete_transit_route(
                existing.id,
                make_request(f"/api/transit-routes/{existing.id}"),
                confirm=True,
                db=db,
            )

        data = response_payload(response)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["error_code"], "TRANSIT_ROUTE_CUTOVER_BLOCKED")
        self.assertIsNone(existing.deleted_at)
        self.assertFalse(db.committed)

    def test_transit_route_delete_soft_deletes_without_remote_action(self):
        existing = route()
        existing.created_at = datetime.now(timezone.utc)
        db = FakeDb(scalar_values=[existing])

        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.delete_transit_route(
                existing.id,
                make_request(f"/api/transit-routes/{existing.id}"),
                confirm=True,
                db=db,
            )

        data = response_payload(response)
        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["delete_mode"], "soft_delete")
        self.assertFalse(data["data"]["remote_action_performed"])
        self.assertEqual(existing.status, "deleted")
        self.assertIsNotNone(existing.deleted_at)
        self.assertTrue(db.committed)
        self.assertEqual([item.action for item in db.added if isinstance(item, AuditLog)], ["delete_transit_route_record"])


if __name__ == "__main__":
    unittest.main()
