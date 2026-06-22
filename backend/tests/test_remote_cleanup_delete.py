import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError

from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer
from app.models.worker import Worker, WorkerToken
from app.models.worker_command import WorkerCommand
from app.schemas.remote_cleanup import RemoteCleanupDeleteRequest
from app.services import remote_cleanup_delete as cleanup
from app.services.worker_targeting import WorkerTargetError


class ScalarResult:
    def __init__(self, values):
        self.values = list(values)

    def all(self):
        return self.values


class FakeDb:
    def __init__(self, *, objects=None, scalars=None, scalar_values=None, commands=None):
        self.objects = objects or {}
        self.scalars_queue = list(scalars or [])
        self.scalar_queue = list(scalar_values or [])
        self.commands = list(commands) if commands is not None else None
        self.added = []
        self.flushed = False

    def get(self, model, key):
        return self.objects.get((model, key))

    def scalars(self, statement):
        values = self.scalars_queue.pop(0) if self.scalars_queue else []
        return ScalarResult(values)

    def scalar(self, statement):
        if self.commands is not None:
            for command in self.commands:
                if (
                    command.server_id
                    and command.command_type in cleanup.REMOTE_CLEANUP_COMMAND_TYPES
                    and command.status in cleanup.REMOTE_CLEANUP_RUNNING_STATUSES
                ):
                    return command.id
            return None
        if self.scalar_queue:
            return self.scalar_queue.pop(0)
        return None

    def add(self, item):
        self.added.append(item)

    def flush(self):
        self.flushed = True


def worker(role="landing", server_id="server-1"):
    return Worker(
        id=f"{role}-worker-1",
        role=role,
        server_id=server_id,
        status="online",
        worker_version="0.1.21-stage-3.3.97",
        worker_secret_hash="hash",
    )


def online_worker(role="landing", server_id="server-1"):
    item = worker(role, server_id)
    item.last_heartbeat_at = cleanup._now()
    return item


def node(node_id="node-1", vps_id="server-1"):
    return Node(
        id=node_id,
        vps_id=vps_id,
        node_name="liveline-reality-27939",
        status="active",
        xray_port=27939,
        share_link="vless" + "://fake-redacted-example",
    )


def route(route_id="route-1", resource_id="resource-1"):
    return TransitRoute(
        id=route_id,
        name="hk-socat-live-23843",
        transit_resource_id=resource_id,
        node_id="node-1",
        listen_port=23843,
        target_host="64.90.13.19",
        target_port=27939,
        forwarding_method="socat",
        service_name="liveline-socat-23843.service",
        service_path="/etc/systemd/system/liveline-socat-23843.service",
        status="active",
    )


def worker_command(command_type, status, server_id="server-1"):
    return WorkerCommand(
        id=f"{command_type}-{status}",
        worker_id="worker-1",
        server_id=server_id,
        server_type="landing" if server_id.startswith("server") else "transit",
        command_type=command_type,
        status=status,
        payload_json={},
    )


class RemoteCleanupDeleteTests(unittest.TestCase):
    def test_remote_cleanup_request_requires_confirm_phrase(self):
        with self.assertRaises(ValidationError):
            RemoteCleanupDeleteRequest(confirm="DELETE")
        payload = RemoteCleanupDeleteRequest(confirm="CONFIRM_REMOTE_DELETE")
        self.assertEqual(payload.confirm, "CONFIRM_REMOTE_DELETE")
        offline_payload = RemoteCleanupDeleteRequest(confirm="CONFIRM_OFFLINE_LOCAL_REMOVE")
        self.assertEqual(offline_payload.confirm, "CONFIRM_OFFLINE_LOCAL_REMOVE")

    def test_create_landing_node_cleanup_command_without_share_link_payload(self):
        target_worker = worker("landing", "server-1")
        db = FakeDb()
        target = SimpleNamespace(worker=target_worker)
        with patch.object(cleanup, "resolve_command_target_worker", return_value=target):
            command, returned_worker = cleanup.create_landing_node_cleanup_command(db, node())

        self.assertEqual(returned_worker.id, target_worker.id)
        self.assertEqual(command.command_type, "cleanup_landing_node")
        self.assertEqual(command.payload_json["cleanup_type"], "cleanup_landing_node")
        self.assertNotIn("fake-redacted-example", json.dumps(command.payload_json))

    def test_create_landing_server_cleanup_command_includes_all_nodes(self):
        target_worker = worker("landing", "server-1")
        server = VpsServer(id="server-1", ip="64.90.13.19", status="active")
        db = FakeDb(scalars=[[node("node-1"), node("node-2")]])
        target = SimpleNamespace(worker=target_worker)
        with patch.object(cleanup, "resolve_command_target_worker", return_value=target):
            command, _ = cleanup.create_landing_server_cleanup_command(db, server)

        self.assertEqual(command.command_type, "cleanup_landing_server")
        self.assertEqual(len(command.payload_json["plans"]), 2)
        self.assertTrue(command.payload_json["cleanup_worker"])
        self.assertEqual(target_worker.status, "cleanup_pending")

    def test_create_transit_route_cleanup_command(self):
        target_worker = worker("transit", "resource-1")
        db = FakeDb()
        target = SimpleNamespace(worker=target_worker)
        with patch.object(cleanup, "resolve_command_target_worker", return_value=target):
            command, _ = cleanup.create_transit_route_cleanup_command(db, route())

        self.assertEqual(command.command_type, "cleanup_transit_route")
        self.assertEqual(command.payload_json["plans"][0]["service_name"], "liveline-socat-23843.service")

    def test_create_transit_resource_cleanup_command_includes_routes(self):
        target_worker = worker("transit", "resource-1")
        resource = TransitResource(id="resource-1", name="hk", resource_type="server", status="active")
        db = FakeDb(scalars=[[route("route-1"), route("route-2")]])
        target = SimpleNamespace(worker=target_worker)
        with patch.object(cleanup, "resolve_command_target_worker", return_value=target):
            command, _ = cleanup.create_transit_resource_cleanup_command(db, resource)

        self.assertEqual(command.command_type, "cleanup_transit_resource")
        self.assertEqual(len(command.payload_json["plans"]), 2)
        self.assertTrue(command.payload_json["cleanup_worker"])
        self.assertEqual(target_worker.status, "cleanup_pending")

    def test_create_cleanup_rejects_missing_worker(self):
        db = FakeDb()
        with patch.object(
            cleanup,
            "resolve_command_target_worker",
            side_effect=WorkerTargetError("WORKER_OFFLINE", "offline"),
        ):
            with self.assertRaises(cleanup.RemoteCleanupError) as raised:
                cleanup.create_landing_node_cleanup_command(db, node())
        self.assertEqual(raised.exception.code, "WORKER_OFFLINE")

    def test_remote_cleanup_unavailable_offer_includes_offline_confirmation(self):
        exc = cleanup.RemoteCleanupError("WORKER_OFFLINE", "offline")
        offer = cleanup.remote_cleanup_unavailable_offer(exc)
        self.assertIsNotNone(offer)
        self.assertTrue(offer["offline_local_remove_available"])
        self.assertEqual(offer["required_confirm_text"], "CONFIRM_OFFLINE_LOCAL_REMOVE")

    def test_offline_local_remove_node_soft_deletes_without_share_link_mutation_or_command(self):
        existing = node()
        original_share_link = existing.share_link
        related_route = route()
        db = FakeDb(scalars=[[worker("landing", "server-1")], [related_route]])

        result = cleanup.offline_local_remove_node(db, existing)

        self.assertEqual(result["delete_mode"], "offline_local_remove")
        self.assertFalse(result["worker_command_created"])
        self.assertFalse(result["remote_cleanup_executed"])
        self.assertEqual(existing.status, "deleted")
        self.assertEqual(existing.last_sync_status, "offline_local_remove")
        self.assertEqual(existing.share_link, original_share_link)
        self.assertEqual(related_route.status, "deleted")
        self.assertFalse(any(isinstance(item, WorkerCommand) for item in db.added))

    def test_offline_local_remove_node_rejects_online_worker(self):
        existing = node()
        db = FakeDb(scalars=[[online_worker("landing", "server-1")]])

        with self.assertRaises(cleanup.RemoteCleanupError) as raised:
            cleanup.offline_local_remove_node(db, existing)

        self.assertEqual(raised.exception.code, "RESOURCE_HAS_ONLINE_WORKER_USE_NORMAL_DELETE")
        self.assertEqual(existing.status, "active")

    def test_offline_local_remove_landing_server_soft_deletes_nodes_routes_and_worker(self):
        server = VpsServer(id="server-1", ip="64.90.13.19", status="active")
        existing_node = node()
        related_route = route()
        stale_worker = worker("landing", "server-1")
        token = WorkerToken(
            id="token-1",
            role="landing",
            server_id="server-1",
            status="active",
            token_hash="hash",
            expires_at=cleanup._now(),
        )
        db = FakeDb(scalars=[[stale_worker], [existing_node], [related_route], [stale_worker], [token]])

        result = cleanup.offline_local_remove_landing_server(db, server)

        self.assertEqual(result["nodes_marked_deleted"], 1)
        self.assertEqual(result["routes_marked_deleted"], 1)
        self.assertEqual(result["workers_marked_deleted"], 1)
        self.assertEqual(server.status, "deleted")
        self.assertEqual(existing_node.status, "deleted")
        self.assertEqual(related_route.status, "deleted")
        self.assertEqual(stale_worker.status, "deleted")
        self.assertEqual(token.status, "expired")
        self.assertFalse(any(isinstance(item, WorkerCommand) for item in db.added))

    def test_offline_local_remove_transit_route_soft_deletes_without_share_link_write(self):
        existing_route = route()
        self.assertIsNone(existing_route.share_link)
        db = FakeDb(scalars=[[worker("transit", "resource-1")]])

        result = cleanup.offline_local_remove_transit_route(db, existing_route)

        self.assertEqual(result["delete_mode"], "offline_local_remove")
        self.assertTrue(result["route_marked_deleted"])
        self.assertEqual(existing_route.status, "deleted")
        self.assertIsNone(existing_route.share_link)
        self.assertFalse(any(isinstance(item, WorkerCommand) for item in db.added))

    def test_offline_local_remove_transit_resource_soft_deletes_routes_and_worker(self):
        resource = TransitResource(id="resource-1", name="hk", resource_type="server", status="active")
        existing_route = route()
        stale_worker = worker("transit", "resource-1")
        token = WorkerToken(
            id="token-1",
            role="transit",
            server_id="resource-1",
            status="active",
            token_hash="hash",
            expires_at=cleanup._now(),
        )
        db = FakeDb(scalars=[[stale_worker], [existing_route], [stale_worker], [token]])

        result = cleanup.offline_local_remove_transit_resource(db, resource)

        self.assertEqual(result["routes_marked_deleted"], 1)
        self.assertEqual(result["workers_marked_deleted"], 1)
        self.assertEqual(resource.status, "deleted")
        self.assertIsNotNone(resource.deleted_at)
        self.assertEqual(existing_route.status, "deleted")
        self.assertEqual(stale_worker.status, "deleted")
        self.assertFalse(any(isinstance(item, WorkerCommand) for item in db.added))

    def test_transit_route_cleanup_rejects_non_liveline_service_name(self):
        target_worker = worker("transit", "resource-1")
        bad_route = route()
        bad_route.service_name = "socat.service"
        bad_route.service_path = "/etc/systemd/system/socat.service"
        db = FakeDb()
        target = SimpleNamespace(worker=target_worker)
        with patch.object(cleanup, "resolve_command_target_worker", return_value=target):
            with self.assertRaises(cleanup.RemoteCleanupError) as raised:
                cleanup.create_transit_route_cleanup_command(db, bad_route)
        self.assertEqual(raised.exception.code, "TRANSIT_ROUTE_SERVICE_NOT_LIVELINE")

    def test_pending_landing_node_cleanup_blocks_landing_server_cleanup(self):
        target_worker = worker("landing", "server-1")
        server = VpsServer(id="server-1", ip="64.90.13.19", status="active")
        db = FakeDb(commands=[worker_command("cleanup_landing_node", "pending", "server-1")])
        target = SimpleNamespace(worker=target_worker)
        with patch.object(cleanup, "resolve_command_target_worker", return_value=target):
            with self.assertRaises(cleanup.RemoteCleanupError) as raised:
                cleanup.create_landing_server_cleanup_command(db, server)
        self.assertEqual(raised.exception.code, "REMOTE_CLEANUP_COMMAND_IN_FLIGHT")

    def test_running_landing_server_cleanup_blocks_landing_node_cleanup(self):
        target_worker = worker("landing", "server-1")
        db = FakeDb(commands=[worker_command("cleanup_landing_server", "running", "server-1")])
        target = SimpleNamespace(worker=target_worker)
        with patch.object(cleanup, "resolve_command_target_worker", return_value=target):
            with self.assertRaises(cleanup.RemoteCleanupError) as raised:
                cleanup.create_landing_node_cleanup_command(db, node())
        self.assertEqual(raised.exception.code, "REMOTE_CLEANUP_COMMAND_IN_FLIGHT")

    def test_claimed_transit_route_cleanup_blocks_transit_resource_cleanup(self):
        target_worker = worker("transit", "resource-1")
        resource = TransitResource(id="resource-1", name="hk", resource_type="server", status="active")
        db = FakeDb(commands=[worker_command("cleanup_transit_route", "claimed", "resource-1")])
        target = SimpleNamespace(worker=target_worker)
        with patch.object(cleanup, "resolve_command_target_worker", return_value=target):
            with self.assertRaises(cleanup.RemoteCleanupError) as raised:
                cleanup.create_transit_resource_cleanup_command(db, resource)
        self.assertEqual(raised.exception.code, "REMOTE_CLEANUP_COMMAND_IN_FLIGHT")

    def test_pending_transit_resource_cleanup_blocks_transit_route_cleanup(self):
        target_worker = worker("transit", "resource-1")
        db = FakeDb(commands=[worker_command("cleanup_transit_resource", "pending", "resource-1")])
        target = SimpleNamespace(worker=target_worker)
        with patch.object(cleanup, "resolve_command_target_worker", return_value=target):
            with self.assertRaises(cleanup.RemoteCleanupError) as raised:
                cleanup.create_transit_route_cleanup_command(db, route())
        self.assertEqual(raised.exception.code, "REMOTE_CLEANUP_COMMAND_IN_FLIGHT")

    def test_non_cleanup_command_does_not_block_remote_cleanup(self):
        target_worker = worker("landing", "server-1")
        db = FakeDb(commands=[worker_command("collect_status", "pending", "server-1")])
        target = SimpleNamespace(worker=target_worker)
        with patch.object(cleanup, "resolve_command_target_worker", return_value=target):
            command, _ = cleanup.create_landing_node_cleanup_command(db, node())
        self.assertEqual(command.command_type, "cleanup_landing_node")

    def test_completed_cleanup_commands_do_not_block_remote_cleanup(self):
        target_worker = worker("landing", "server-1")
        db = FakeDb(
            commands=[
                worker_command("cleanup_landing_node", "succeeded", "server-1"),
                worker_command("cleanup_landing_server", "failed", "server-1"),
            ]
        )
        target = SimpleNamespace(worker=target_worker)
        with patch.object(cleanup, "resolve_command_target_worker", return_value=target):
            command, _ = cleanup.create_landing_node_cleanup_command(db, node())
        self.assertEqual(command.command_type, "cleanup_landing_node")

    def test_failed_result_does_not_soft_delete_node(self):
        existing = node()
        command = WorkerCommand(
            id="command-1",
            worker_id="landing-worker-1",
            server_id="server-1",
            server_type="landing",
            command_type="cleanup_landing_node",
            payload_json={"target_id": existing.id},
        )
        db = FakeDb(objects={(Node, existing.id): existing})
        with self.assertRaises(cleanup.RemoteCleanupError):
            cleanup.persist_successful_remote_cleanup_result(
                db=db,
                command=command,
                result={"cleanup_type": "cleanup_landing_node", "status": "failed"},
            )
        self.assertEqual(existing.status, "active")
        self.assertIsNone(existing.deleted_at)

    def test_successful_node_cleanup_soft_deletes_node(self):
        existing = node()
        command = WorkerCommand(
            id="command-1",
            worker_id="landing-worker-1",
            server_id="server-1",
            server_type="landing",
            command_type="cleanup_landing_node",
            payload_json={"target_id": existing.id},
        )
        db = FakeDb(objects={(Node, existing.id): existing})
        result = cleanup.persist_successful_remote_cleanup_result(
            db=db,
            command=command,
            result={
                "cleanup_type": "cleanup_landing_node",
                "status": "succeeded",
                "remote_cleanup_performed": True,
                "system_record_delete_after_success": True,
            },
        )
        self.assertTrue(result["system_record_deleted"])
        self.assertEqual(existing.status, "deleted")
        self.assertEqual(existing.last_sync_status, "remote_cleanup_completed")
        self.assertIsNotNone(existing.deleted_at)

    def test_successful_landing_server_cleanup_marks_worker_deleted_and_token_expired(self):
        existing_node = node()
        existing_worker = worker("landing", "server-1")
        token = WorkerToken(
            id="token-1",
            role="landing",
            server_id="server-1",
            status="active",
            token_hash="hash",
            expires_at=cleanup._now(),
        )
        server = VpsServer(id="server-1", ip="64.90.13.19", status="active")
        command = WorkerCommand(
            id="command-1",
            worker_id=existing_worker.id,
            server_id="server-1",
            server_type="landing",
            command_type="cleanup_landing_server",
            payload_json={"target_id": server.id},
        )
        db = FakeDb(
            objects={(VpsServer, server.id): server, (Worker, existing_worker.id): existing_worker},
            scalars=[[existing_node], [token]],
        )
        result = cleanup.persist_successful_remote_cleanup_result(
            db=db,
            command=command,
            result={
                "cleanup_type": "cleanup_landing_server",
                "status": "succeeded",
                "remote_cleanup_performed": True,
                "system_record_delete_after_success": True,
            },
        )

        self.assertTrue(result["system_record_deleted"])
        self.assertEqual(server.status, "deleted")
        self.assertEqual(existing_node.status, "deleted")
        self.assertEqual(existing_worker.status, "deleted")
        self.assertEqual(existing_worker.metadata_json["cleanup_status"], "cleanup_expected_offline")
        self.assertEqual(result["worker_cleanup_status"], "missing")
        self.assertEqual(result["worker_self_cleanup_status"], "missing")
        self.assertEqual(token.status, "expired")


if __name__ == "__main__":
    unittest.main()
