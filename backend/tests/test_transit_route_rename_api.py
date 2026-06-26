import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.requests import Request

from app.api.routes import transit_routes
from app.models.audit_log import AuditLog
from app.models.transit_route import TransitRoute
from app.schemas.transit_route import TransitRouteRenameRequest


class FakeAdminSession:
    admin_id = "admin-1"


def make_request(path: str, method: str = "PATCH") -> Request:
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
    def __init__(self, *, route: TransitRoute | None = None) -> None:
        self.route = route
        self.added: list[object] = []
        self.committed = False

    def scalar(self, statement):
        return self.route

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True


def make_route(*, deleted: bool = False) -> TransitRoute:
    return TransitRoute(
        id="route-1",
        name="haproxy-tcp-29833",
        transit_resource_id="resource-1",
        node_id="node-1",
        landing_vps_id="landing-vps-1",
        listen_port=29833,
        target_host="64.90.13.19",
        target_port=28917,
        forwarding_method="haproxy_tcp",
        service_name="liveline-haproxy-29833.service",
        service_path="/etc/systemd/system/liveline-haproxy-29833.service",
        status="deleted" if deleted else "active",
        share_link="stored-transit-link-redacted",
        updated_at=datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc),
        deleted_at=datetime(2026, 6, 26, 13, 0, tzinfo=timezone.utc) if deleted else None,
    )


class TransitRouteRenameApiTests(unittest.TestCase):
    def test_rename_active_route_only_updates_display_name_and_updated_at(self):
        route = make_route()
        original = {
            "listen_port": route.listen_port,
            "target_host": route.target_host,
            "target_port": route.target_port,
            "forwarding_method": route.forwarding_method,
            "service_name": route.service_name,
            "service_path": route.service_path,
            "share_link": route.share_link,
        }
        old_updated_at = route.updated_at
        db = FakeDb(route=route)

        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.rename_transit_route(
                route.id,
                TransitRouteRenameRequest(name="mk香港落地15m"),
                make_request(f"/api/transit-routes/{route.id}/name"),
                db,
            )

        data = response_payload(response)
        self.assertTrue(data["success"])
        self.assertEqual(route.name, "mk香港落地15m")
        self.assertGreater(route.updated_at, old_updated_at)
        self.assertEqual(route.listen_port, original["listen_port"])
        self.assertEqual(route.target_host, original["target_host"])
        self.assertEqual(route.target_port, original["target_port"])
        self.assertEqual(route.forwarding_method, original["forwarding_method"])
        self.assertEqual(route.service_name, original["service_name"])
        self.assertEqual(route.service_path, original["service_path"])
        self.assertEqual(route.share_link, original["share_link"])
        self.assertEqual(data["data"]["name"], "mk香港落地15m")
        self.assertNotIn("share_link", data["data"])
        self.assertTrue(data["data"]["share_link_present"])
        self.assertTrue(db.committed)
        self.assertEqual([item.action for item in db.added if isinstance(item, AuditLog)], ["rename_transit_route"])

    def test_rename_request_rejects_empty_or_sensitive_names(self):
        for value in (" ", "vless" + "://example", "raw token value", "admin password", "private key material"):
            with self.subTest(value=value), self.assertRaises(ValidationError):
                TransitRouteRenameRequest(name=value)
        with self.assertRaises(ValidationError):
            TransitRouteRenameRequest(name="x" * 121)

    def test_rename_deleted_route_is_not_found(self):
        db = FakeDb(route=None)
        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.rename_transit_route(
                "deleted-route",
                TransitRouteRenameRequest(name="mk香港落地15m"),
                make_request("/api/transit-routes/deleted-route/name"),
                db,
            )

        data = response_payload(response)
        self.assertEqual(response.status_code, 404)
        self.assertEqual(data["error_code"], "TRANSIT_ROUTE_NOT_FOUND")
        self.assertFalse(db.committed)

    def test_rename_requires_login(self):
        db = FakeDb(route=make_route())
        with patch.object(transit_routes, "require_admin_session", return_value=None):
            response = transit_routes.rename_transit_route(
                "route-1",
                TransitRouteRenameRequest(name="mk香港落地15m"),
                make_request("/api/transit-routes/route-1/name"),
                db,
            )

        data = response_payload(response)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(db.committed)
        self.assertIn("error_code", data)

    def test_rename_requires_valid_csrf(self):
        db = FakeDb(route=make_route())
        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=False
        ):
            response = transit_routes.rename_transit_route(
                "route-1",
                TransitRouteRenameRequest(name="mk香港落地15m"),
                make_request("/api/transit-routes/route-1/name"),
                db,
            )

        data = response_payload(response)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(db.committed)
        self.assertIn("error_code", data)


if __name__ == "__main__":
    unittest.main()
