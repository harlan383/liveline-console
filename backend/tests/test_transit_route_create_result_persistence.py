import unittest
from datetime import datetime, timezone

from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.worker_command import WorkerCommand
from app.schemas.transit_route import (
    APPROVED_LANDING_NODE_ID,
    APPROVED_LANDING_TARGET_HOST,
    APPROVED_LANDING_TARGET_PORT,
    APPROVED_TRANSIT_FORWARDING_METHOD,
    APPROVED_TRANSIT_LISTEN_PORT,
    APPROVED_TRANSIT_RESOURCE_ID,
    APPROVED_TRANSIT_ROUTE_NAME,
    APPROVED_TRANSIT_SERVICE_NAME,
    APPROVED_TRANSIT_SERVICE_PATH,
    APPROVED_TRANSIT_WORKER_ID,
)
from app.services.transit_route_create import persist_successful_transit_route_create_result


class FakeSession:
    def __init__(self, duplicate_route: TransitRoute | None = None) -> None:
        self.resource = TransitResource(
            id=APPROVED_TRANSIT_RESOURCE_ID,
            name="香港中转服务器",
            resource_type="server",
            status="active",
        )
        self.node = Node(
            id=APPROVED_LANDING_NODE_ID,
            vps_id="landing-vps",
            node_name="liveline-reality-27939",
            xray_port=APPROVED_LANDING_TARGET_PORT,
            status="active",
        )
        self.duplicate_route = duplicate_route
        self.added: list[object] = []

    def get(self, model, key):
        if model is TransitResource and key == APPROVED_TRANSIT_RESOURCE_ID:
            return self.resource
        if model is Node and key == APPROVED_LANDING_NODE_ID:
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


def successful_result() -> dict:
    return {
        "execution_mode": "real_create",
        "real_execution": True,
        "status": "succeeded",
        "summary": "Approved socat transit route created.",
        "worker_version": "0.1.19-stage-3.3.73",
        "hostname": "WEPC202605221223335",
        "role": "transit",
        "interface_name": "eth0",
        "planned_listen_port": APPROVED_TRANSIT_LISTEN_PORT,
        "landing_target_host": APPROVED_LANDING_TARGET_HOST,
        "landing_target_port": APPROVED_LANDING_TARGET_PORT,
        "forwarding_method": APPROVED_TRANSIT_FORWARDING_METHOD,
        "route_name": APPROVED_TRANSIT_ROUTE_NAME,
        "service_name": APPROVED_TRANSIT_SERVICE_NAME,
        "service_path": APPROVED_TRANSIT_SERVICE_PATH,
        "safety_boundary": ["no nodes.share_link read or modification", "no cutover"],
        "checks": [{"name": "listener_verified", "passed": True}],
    }


def command() -> WorkerCommand:
    return WorkerCommand(
        id="command-1",
        worker_id=APPROVED_TRANSIT_WORKER_ID,
        server_type="transit",
        server_id=APPROVED_TRANSIT_RESOURCE_ID,
        command_type="transit_route_create",
        status="running",
        attempts=1,
        created_at=datetime.now(timezone.utc),
    )


class TransitRouteCreateResultPersistenceTests(unittest.TestCase):
    def test_real_create_result_creates_transit_route_without_share_link(self):
        db = FakeSession()
        normalized = persist_successful_transit_route_create_result(
            db=db,
            command=command(),
            result=successful_result(),
        )

        routes = [item for item in db.added if isinstance(item, TransitRoute)]
        self.assertEqual(len(routes), 1)
        route = routes[0]
        self.assertEqual(route.name, APPROVED_TRANSIT_ROUTE_NAME)
        self.assertEqual(route.listen_port, APPROVED_TRANSIT_LISTEN_PORT)
        self.assertEqual(route.target_host, APPROVED_LANDING_TARGET_HOST)
        self.assertEqual(route.target_port, APPROVED_LANDING_TARGET_PORT)
        self.assertEqual(route.forwarding_method, APPROVED_TRANSIT_FORWARDING_METHOD)
        self.assertEqual(route.service_name, APPROVED_TRANSIT_SERVICE_NAME)
        self.assertEqual(route.service_path, APPROVED_TRANSIT_SERVICE_PATH)
        self.assertEqual(route.status, "active")
        self.assertIsNone(route.share_link)
        self.assertTrue(normalized["route_persisted"])
        self.assertEqual(normalized["share_link_storage"], "transit_route.share_link_null_not_generated")

    def test_real_create_result_is_idempotent_when_route_exists(self):
        existing = TransitRoute(
            id="existing-route",
            name=APPROVED_TRANSIT_ROUTE_NAME,
            transit_resource_id=APPROVED_TRANSIT_RESOURCE_ID,
            node_id=APPROVED_LANDING_NODE_ID,
            listen_port=APPROVED_TRANSIT_LISTEN_PORT,
            target_host=APPROVED_LANDING_TARGET_HOST,
            target_port=APPROVED_LANDING_TARGET_PORT,
            forwarding_method=APPROVED_TRANSIT_FORWARDING_METHOD,
            service_name=APPROVED_TRANSIT_SERVICE_NAME,
            service_path=APPROVED_TRANSIT_SERVICE_PATH,
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


if __name__ == "__main__":
    unittest.main()
