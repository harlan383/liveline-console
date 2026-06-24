import unittest
from datetime import datetime, timezone

from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer
from app.models.worker_command import WorkerCommand
from app.schemas.transit_route import (
    APPROVED_LANDING_TARGET_PORT,
    APPROVED_TRANSIT_FORWARDING_METHOD,
    APPROVED_TRANSIT_LISTEN_PORT,
    FORWARDING_METHOD_HAPROXY_TCP,
)
from app.services.transit_route_create import persist_successful_transit_route_create_result

TRANSIT_RESOURCE_ID = "02d16c43-d20c-46e9-b84c-a367343b48ae"
TRANSIT_WORKER_ID = "9c359d1a-f018-4484-992b-d2ed840cb88f"
LANDING_NODE_ID = "7cf3ec9c-8e76-418e-97c1-5ee3ddb28e31"
LANDING_VPS_ID = "a3e4c4bf-2b4a-4705-bb45-65d9da9c1cbf"
ROUTE_NAME = "wepc-socat-live-23843"
SERVICE_NAME = "liveline-socat-23843.service"
SERVICE_PATH = "/etc/systemd/system/liveline-socat-23843.service"
HAPROXY_ROUTE_NAME = "mkiepl-haproxy-live-23843"
HAPROXY_SERVICE_NAME = "liveline-haproxy-23843.service"
HAPROXY_SERVICE_PATH = "/etc/systemd/system/liveline-haproxy-23843.service"
HAPROXY_CONFIG_PATH = "/etc/haproxy/liveline/routes/liveline-haproxy-23843.cfg"


class FakeSession:
    def __init__(
        self,
        *,
        duplicate_route: TransitRoute | None = None,
        resource_status: str = "worker_online",
        node_share_link: bool = True,
    ) -> None:
        self.resource = TransitResource(
            id=TRANSIT_RESOURCE_ID,
            name="wepc香港中转",
            resource_type="server",
            status=resource_status,
            entry_host="163.223.216.108",
            entry_port=22,
        )
        self.node = Node(
            id=LANDING_NODE_ID,
            vps_id=LANDING_VPS_ID,
            node_name="liveline-reality-27939",
            xray_port=APPROVED_LANDING_TARGET_PORT,
            status="active",
            share_link="redacted-share-link-present" if node_share_link else None,
        )
        self.node.vps = VpsServer(id=LANDING_VPS_ID, ip="64.90.13.19")
        self.duplicate_route = duplicate_route
        self.added: list[object] = []

    def get(self, model, key):
        if model is TransitResource and key == TRANSIT_RESOURCE_ID:
            return self.resource
        if model is Node and key == LANDING_NODE_ID:
            return self.node
        return None

    def scalar(self, statement):
        return self.duplicate_route

    def add(self, item):
        self.added.append(item)

    def flush(self):
        for item in self.added:
            if isinstance(item, TransitRoute) and not item.id:
                item.id = "created-route"


def command(**payload_overrides) -> WorkerCommand:
    payload = {
        "transit_resource_id": TRANSIT_RESOURCE_ID,
        "transit_worker_id": TRANSIT_WORKER_ID,
        "landing_node_id": LANDING_NODE_ID,
        "planned_listen_port": APPROVED_TRANSIT_LISTEN_PORT,
        "landing_target_host": "64.90.13.19",
        "landing_target_port": APPROVED_LANDING_TARGET_PORT,
        "forwarding_method": APPROVED_TRANSIT_FORWARDING_METHOD,
        "route_name": ROUTE_NAME,
    }
    payload.update(payload_overrides)
    return WorkerCommand(
        id="command-1",
        worker_id=TRANSIT_WORKER_ID,
        server_type="transit",
        server_id=TRANSIT_RESOURCE_ID,
        command_type="transit_route_create",
        payload_json=payload,
        status="running",
        attempts=1,
        created_at=datetime.now(timezone.utc),
    )


def successful_result(**overrides) -> dict:
    result = {
        "execution_mode": "real_create",
        "real_execution": True,
        "status": "succeeded",
        "summary": "Approved socat transit route created.",
        "worker_version": "0.1.22-stage-3.3.107",
        "hostname": "WEPC202605221223335",
        "role": "transit",
        "interface_name": "eth0",
        "planned_listen_port": APPROVED_TRANSIT_LISTEN_PORT,
        "landing_target_host": "64.90.13.19",
        "landing_target_port": APPROVED_LANDING_TARGET_PORT,
        "forwarding_method": APPROVED_TRANSIT_FORWARDING_METHOD,
        "route_name": ROUTE_NAME,
        "service_name": SERVICE_NAME,
        "service_path": SERVICE_PATH,
        "safety_boundary": ["no nodes.share_link read or modification", "no cutover"],
        "checks": [{"name": "listener_verified", "passed": True}],
    }
    result.update(overrides)
    return result


def haproxy_command(**payload_overrides) -> WorkerCommand:
    return command(
        forwarding_method=FORWARDING_METHOD_HAPROXY_TCP,
        route_name=HAPROXY_ROUTE_NAME,
        **payload_overrides,
    )


def haproxy_successful_result(**overrides) -> dict:
    result = successful_result(
        summary="Approved HAProxy TCP transit route created.",
        forwarding_method=FORWARDING_METHOD_HAPROXY_TCP,
        route_name=HAPROXY_ROUTE_NAME,
        service_name=HAPROXY_SERVICE_NAME,
        service_path=HAPROXY_SERVICE_PATH,
        config_path=HAPROXY_CONFIG_PATH,
    )
    result.update(overrides)
    return result


class TransitRouteCreateResultPersistenceTests(unittest.TestCase):
    def test_real_create_result_creates_dynamic_transit_route_without_share_link(self):
        db = FakeSession()
        normalized = persist_successful_transit_route_create_result(
            db=db,
            command=command(),
            result=successful_result(),
        )

        routes = [item for item in db.added if isinstance(item, TransitRoute)]
        self.assertEqual(len(routes), 1)
        route = routes[0]
        self.assertEqual(route.name, ROUTE_NAME)
        self.assertEqual(route.transit_resource_id, TRANSIT_RESOURCE_ID)
        self.assertEqual(route.node_id, LANDING_NODE_ID)
        self.assertEqual(route.listen_port, APPROVED_TRANSIT_LISTEN_PORT)
        self.assertEqual(route.target_host, "64.90.13.19")
        self.assertEqual(route.target_port, APPROVED_LANDING_TARGET_PORT)
        self.assertEqual(route.forwarding_method, APPROVED_TRANSIT_FORWARDING_METHOD)
        self.assertEqual(route.service_name, SERVICE_NAME)
        self.assertEqual(route.service_path, SERVICE_PATH)
        self.assertEqual(route.status, "active")
        self.assertIsNone(route.share_link)
        self.assertTrue(normalized["route_persisted"])
        self.assertEqual(normalized["share_link_storage"], "transit_route.share_link_null_not_generated")

    def test_haproxy_real_create_result_creates_active_transit_route_without_share_link(self):
        db = FakeSession()
        normalized = persist_successful_transit_route_create_result(
            db=db,
            command=haproxy_command(),
            result=haproxy_successful_result(),
        )

        routes = [item for item in db.added if isinstance(item, TransitRoute)]
        self.assertEqual(len(routes), 1)
        route = routes[0]
        self.assertEqual(route.name, HAPROXY_ROUTE_NAME)
        self.assertEqual(route.transit_resource_id, TRANSIT_RESOURCE_ID)
        self.assertEqual(route.node_id, LANDING_NODE_ID)
        self.assertEqual(route.listen_port, APPROVED_TRANSIT_LISTEN_PORT)
        self.assertEqual(route.target_host, "64.90.13.19")
        self.assertEqual(route.target_port, APPROVED_LANDING_TARGET_PORT)
        self.assertEqual(route.forwarding_method, FORWARDING_METHOD_HAPROXY_TCP)
        self.assertEqual(route.service_name, HAPROXY_SERVICE_NAME)
        self.assertEqual(route.service_path, HAPROXY_SERVICE_PATH)
        self.assertEqual(route.status, "active")
        self.assertIsNone(route.share_link)
        self.assertTrue(normalized["route_persisted"])
        self.assertEqual(normalized["share_link_storage"], "transit_route.share_link_null_not_generated")

    def test_real_create_result_is_idempotent_when_route_exists(self):
        existing = TransitRoute(
            id="existing-route",
            name=ROUTE_NAME,
            transit_resource_id=TRANSIT_RESOURCE_ID,
            node_id=LANDING_NODE_ID,
            listen_port=APPROVED_TRANSIT_LISTEN_PORT,
            target_host="64.90.13.19",
            target_port=APPROVED_LANDING_TARGET_PORT,
            forwarding_method=APPROVED_TRANSIT_FORWARDING_METHOD,
            service_name=SERVICE_NAME,
            service_path=SERVICE_PATH,
            status="active",
        )
        db = FakeSession(duplicate_route=existing)

        normalized = persist_successful_transit_route_create_result(
            db=db,
            command=command(),
            result=successful_result(),
        )

        self.assertFalse([item for item in db.added if isinstance(item, TransitRoute)])
        self.assertFalse(normalized["route_persisted"])
        self.assertTrue(normalized["route_duplicate_existing"])
        self.assertEqual(normalized["route_id"], "existing-route")

    def test_haproxy_real_create_result_is_idempotent_when_route_exists(self):
        existing = TransitRoute(
            id="existing-haproxy-route",
            name=HAPROXY_ROUTE_NAME,
            transit_resource_id=TRANSIT_RESOURCE_ID,
            node_id=LANDING_NODE_ID,
            listen_port=APPROVED_TRANSIT_LISTEN_PORT,
            target_host="64.90.13.19",
            target_port=APPROVED_LANDING_TARGET_PORT,
            forwarding_method=FORWARDING_METHOD_HAPROXY_TCP,
            service_name=HAPROXY_SERVICE_NAME,
            service_path=HAPROXY_SERVICE_PATH,
            status="active",
            share_link=None,
        )
        db = FakeSession(duplicate_route=existing)

        normalized = persist_successful_transit_route_create_result(
            db=db,
            command=haproxy_command(),
            result=haproxy_successful_result(),
        )

        self.assertFalse([item for item in db.added if isinstance(item, TransitRoute)])
        self.assertFalse(normalized["route_persisted"])
        self.assertTrue(normalized["route_duplicate_existing"])
        self.assertEqual(normalized["route_id"], "existing-haproxy-route")

    def test_real_create_result_rejects_missing_landing_share_link(self):
        with self.assertRaises(Exception) as context:
            persist_successful_transit_route_create_result(
                db=FakeSession(node_share_link=False),
                command=command(),
                result=successful_result(),
            )

        self.assertEqual(context.exception.code, "LANDING_NODE_SHARE_LINK_REQUIRED")

    def test_real_create_result_rejects_non_approved_port(self):
        with self.assertRaises(Exception) as context:
            persist_successful_transit_route_create_result(
                db=FakeSession(),
                command=command(planned_listen_port=25000),
                result=successful_result(planned_listen_port=25000, service_name="liveline-socat-25000.service"),
            )

        self.assertEqual(context.exception.code, "LISTEN_PORT_APPROVAL_MISMATCH")

    def test_real_create_result_rejects_mismatched_result_target(self):
        with self.assertRaises(Exception) as context:
            persist_successful_transit_route_create_result(
                db=FakeSession(),
                command=command(),
                result=successful_result(landing_target_host="203.0.113.10"),
            )

        self.assertEqual(context.exception.code, "LANDING_HOST_APPROVAL_MISMATCH")

    def test_haproxy_real_create_result_rejects_mismatched_service_name(self):
        with self.assertRaises(Exception) as context:
            persist_successful_transit_route_create_result(
                db=FakeSession(),
                command=haproxy_command(),
                result=haproxy_successful_result(service_name="liveline-haproxy-wrong.service"),
            )

        self.assertEqual(context.exception.code, "SERVICE_NAME_APPROVAL_MISMATCH")

    def test_haproxy_real_create_result_rejects_mismatched_service_path(self):
        with self.assertRaises(Exception) as context:
            persist_successful_transit_route_create_result(
                db=FakeSession(),
                command=haproxy_command(),
                result=haproxy_successful_result(
                    service_path="/etc/systemd/system/liveline-haproxy-wrong.service",
                ),
            )

        self.assertEqual(context.exception.code, "SERVICE_PATH_APPROVAL_MISMATCH")

    def test_haproxy_real_create_result_rejects_mismatched_config_path_when_returned(self):
        with self.assertRaises(Exception) as context:
            persist_successful_transit_route_create_result(
                db=FakeSession(),
                command=haproxy_command(),
                result=haproxy_successful_result(
                    config_path="/etc/haproxy/liveline/routes/liveline-haproxy-wrong.cfg",
                ),
            )

        self.assertEqual(context.exception.code, "CONFIG_PATH_APPROVAL_MISMATCH")


if __name__ == "__main__":
    unittest.main()
