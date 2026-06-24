import json
import unittest
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import transit_routes
from app.models.audit_log import AuditLog
from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer
from app.schemas.transit_route import (
    APPROVED_LANDING_NODE_ID,
    APPROVED_LANDING_TARGET_HOST,
    APPROVED_LANDING_TARGET_PORT,
    APPROVED_TRANSIT_FORWARDING_METHOD,
    APPROVED_TRANSIT_LISTEN_PORT,
    APPROVED_TRANSIT_RESOURCE_ID,
    APPROVED_TRANSIT_ROUTE_ID,
    APPROVED_TRANSIT_ROUTE_NAME,
    APPROVED_TRANSIT_SERVICE_NAME,
    APPROVED_TRANSIT_SERVICE_PATH,
    TransitRouteCandidateExportRequest,
)


class FakeAdminSession:
    admin_id = "admin-1"


def make_request(path: str, method: str = "POST") -> Request:
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


class FakeSession:
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


def make_candidate_route(*, status: str = "active", route_id: str = APPROVED_TRANSIT_ROUTE_ID) -> TransitRoute:
    resource = TransitResource(
        id=APPROVED_TRANSIT_RESOURCE_ID,
        name="香港中转服务器",
        resource_type="server",
        entry_host="163.223.216.108",
        status="active",
    )
    node = Node(
        id=APPROVED_LANDING_NODE_ID,
        vps_id="landing-vps",
        node_name="liveline-reality-27939",
        protocol="vless",
        transport="tcp",
        security="reality",
        flow="xtls-rprx-vision",
        xray_port=APPROVED_LANDING_TARGET_PORT,
        uuid="11111111-2222-3333-4444-555555555555",
        reality_public_key="fake-public-key-for-test",
        reality_short_id="fake-short-id",
        sni="www.example.com",
        fingerprint="chrome",
        share_link=(
            "vless"
            + "://11111111-2222-3333-4444-555555555555@64.90.13.19:27939"
            "?encryption=none&flow=xtls-rprx-vision&security=reality&sni=www.example.com"
            "&fp=chrome&pbk=fake-public-key-for-test&sid=fake-short-id&type=tcp#liveline-reality-27939"
        ),
        status="active",
    )
    vps = VpsServer(id="landing-vps", ip=APPROVED_LANDING_TARGET_HOST)
    node.vps = vps
    route = TransitRoute(
        id=route_id,
        name=APPROVED_TRANSIT_ROUTE_NAME,
        transit_resource_id=APPROVED_TRANSIT_RESOURCE_ID,
        node_id=APPROVED_LANDING_NODE_ID,
        landing_vps_id="landing-vps",
        listen_port=APPROVED_TRANSIT_LISTEN_PORT,
        target_host=APPROVED_LANDING_TARGET_HOST,
        target_port=APPROVED_LANDING_TARGET_PORT,
        forwarding_method=APPROVED_TRANSIT_FORWARDING_METHOD,
        service_name=APPROVED_TRANSIT_SERVICE_NAME,
        service_path=APPROVED_TRANSIT_SERVICE_PATH,
        status=status,
        share_link=None,
    )
    route.transit_resource = resource
    route.node = node
    route.landing_vps = vps
    return route


def valid_export_payload(**overrides):
    payload = {
        "confirm_transient_export": True,
        "confirm_no_database_write": True,
        "confirm_no_share_link_mutation": True,
        "confirm_no_cutover": True,
        "reason": "client_candidate_test",
    }
    payload.update(overrides)
    return TransitRouteCandidateExportRequest(**payload)


class TransitCandidateExportApiTests(unittest.TestCase):
    def test_summary_does_not_return_full_node_share_link(self):
        route = make_candidate_route()
        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()):
            response = transit_routes.get_transit_route_candidate_summary(
                route.id,
                make_request(f"/api/transit-routes/{route.id}/candidate-summary", method="GET"),
                FakeSession(route=route),
            )
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertEqual(data["data"]["route_id"], APPROVED_TRANSIT_ROUTE_ID)
        self.assertFalse(data["data"]["route_share_link_present"])
        self.assertNotIn("candidate_link", data["data"])
        self.assertNotIn("share_link", data["data"])

    def test_export_requires_all_confirmations(self):
        payload = valid_export_payload(confirm_no_cutover=False)
        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.export_transit_route_candidate(
                APPROVED_TRANSIT_ROUTE_ID,
                payload,
                make_request(f"/api/transit-routes/{APPROVED_TRANSIT_ROUTE_ID}/candidate-export"),
                FakeSession(route=make_candidate_route()),
            )
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "NO_CUTOVER_CONFIRMATION_REQUIRED")

    def test_export_returns_404_when_route_missing(self):
        payload = valid_export_payload()
        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.export_transit_route_candidate(
                APPROVED_TRANSIT_ROUTE_ID,
                payload,
                make_request(f"/api/transit-routes/{APPROVED_TRANSIT_ROUTE_ID}/candidate-export"),
                FakeSession(route=None),
            )
        data = response_payload(response)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(data["error_code"], "TRANSIT_ROUTE_NOT_FOUND")

    def test_export_rejects_non_active_route(self):
        payload = valid_export_payload()
        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.export_transit_route_candidate(
                APPROVED_TRANSIT_ROUTE_ID,
                payload,
                make_request(f"/api/transit-routes/{APPROVED_TRANSIT_ROUTE_ID}/candidate-export"),
                FakeSession(route=make_candidate_route(status="disabled")),
            )
        data = response_payload(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(data["error_code"], "TRANSIT_ROUTE_NOT_ACTIVE")

    def test_export_builds_transient_candidate_without_mutating_share_links(self):
        route = make_candidate_route()
        original_node_share_link = route.node.share_link
        db = FakeSession(route=route)
        payload = valid_export_payload()

        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.export_transit_route_candidate(
                route.id,
                payload,
                make_request(f"/api/transit-routes/{route.id}/candidate-export"),
                db,
            )
        data = response_payload(response)

        self.assertTrue(data["success"])
        exported = data["data"]
        self.assertEqual(exported["server"], "163.223.216.108")
        self.assertEqual(exported["port"], APPROVED_TRANSIT_LISTEN_PORT)
        self.assertTrue(exported["uuid_present"])
        self.assertTrue(exported["reality_public_key_present"])
        self.assertTrue(exported["reality_short_id_present"])
        self.assertEqual(exported["cutover_status"], "not_cutover")
        self.assertEqual(exported["export_mode"], "transient")
        self.assertEqual(exported["persistence"], "not_saved")
        self.assertFalse(exported["database_write_performed"])
        self.assertFalse(exported["nodes_share_link_mutated"])
        self.assertFalse(exported["transit_route_share_link_mutated"])
        self.assertTrue(exported["candidate_link"].startswith("vless" + "://"))
        self.assertIn("@163.223.216.108:23843", exported["candidate_link"])
        self.assertIn("pbk=fake-public-key-for-test", exported["candidate_link"])
        self.assertIn("sid=fake-short-id", exported["candidate_link"])
        self.assertIn("sni=www.example.com", exported["candidate_link"])
        self.assertIn("flow=xtls-rprx-vision", exported["candidate_link"])
        self.assertTrue(exported["candidate_link"].endswith("#hk-socat-live-23843"))
        self.assertNotEqual(exported["candidate_link"], original_node_share_link)
        self.assertEqual(route.node.share_link, original_node_share_link)
        self.assertIsNone(route.share_link)

        audit_logs = [item for item in db.added if isinstance(item, AuditLog)]
        self.assertEqual(len(audit_logs), 1)
        self.assertEqual(audit_logs[0].action, "export_transit_route_candidate")
        self.assertEqual(audit_logs[0].resource_id, route.id)
        self.assertNotIn(exported["candidate_link"], str(audit_logs[0].__dict__))

    def test_export_rejects_missing_landing_node_share_link(self):
        route = make_candidate_route()
        route.node.share_link = None
        payload = valid_export_payload()

        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.export_transit_route_candidate(
                route.id,
                payload,
                make_request(f"/api/transit-routes/{route.id}/candidate-export"),
                FakeSession(route=route),
            )
        data = response_payload(response)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["error_code"], "CANDIDATE_LINK_MATERIAL_INCOMPLETE")

    def test_export_allows_active_non_cutover_route_without_fixed_route_id(self):
        route = make_candidate_route(route_id="custom-route-1")
        route.name = "custom-socat-route"
        route.listen_port = 24001
        payload = valid_export_payload()

        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.export_transit_route_candidate(
                route.id,
                payload,
                make_request(f"/api/transit-routes/{route.id}/candidate-export"),
                FakeSession(route=route),
            )
        data = response_payload(response)

        self.assertTrue(data["success"])
        self.assertIn("@163.223.216.108:24001", data["data"]["candidate_link"])
        self.assertTrue(data["data"]["candidate_link"].endswith("#custom-socat-route"))

    def test_export_rejects_cutover_route(self):
        route = make_candidate_route()
        route.share_link = "stored-transit-link-redacted"
        payload = valid_export_payload()

        with patch.object(transit_routes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            transit_routes, "csrf_valid", return_value=True
        ):
            response = transit_routes.export_transit_route_candidate(
                route.id,
                payload,
                make_request(f"/api/transit-routes/{route.id}/candidate-export"),
                FakeSession(route=route),
            )
        data = response_payload(response)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(data["error_code"], "TRANSIT_ROUTE_CUTOVER_BLOCKED")


if __name__ == "__main__":
    unittest.main()
