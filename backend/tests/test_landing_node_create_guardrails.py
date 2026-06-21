import unittest
from unittest.mock import patch

from app.models.node import Node
from app.models.vps_server import VpsServer
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand
from app.schemas.landing_node_plan import LandingNodeCreateRequest
from app.services.landing_node_create import (
    APPROVED_FORMAL_LISTEN_PORT,
    APPROVED_FORMAL_SERVER_ID,
    APPROVED_FORMAL_SERVER_IP,
    LANDING_NODE_CREATE_COMMAND,
    LandingNodeCreateError,
    create_landing_node_create_command,
    persist_successful_landing_node_result,
    validate_landing_node_create_request,
)


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.flushed = False

    def scalar(self, *_args, **_kwargs):
        return None

    def get(self, _model, _id):
        return VpsServer(id=APPROVED_FORMAL_SERVER_ID, ip=APPROVED_FORMAL_SERVER_IP, status="active")

    def add(self, item):
        self.added.append(item)

    def flush(self):
        self.flushed = True


def approved_vps() -> VpsServer:
    return VpsServer(id=APPROVED_FORMAL_SERVER_ID, ip=APPROVED_FORMAL_SERVER_IP, status="active")


def approved_payload(**overrides) -> LandingNodeCreateRequest:
    data = {
        "approved_port": APPROVED_FORMAL_LISTEN_PORT,
        "confirm_firewall_open": True,
        "confirm_generate_share_link": True,
        "confirm_write_share_link_after_success": True,
        "confirm_no_existing_xray": True,
        "confirm_rollback_new_artifacts_only": True,
    }
    data.update(overrides)
    return LandingNodeCreateRequest(**data)


class LandingNodeCreateGuardrailTests(unittest.TestCase):
    def test_non_approved_port_is_still_rejected(self):
        payload = approved_payload(approved_port=APPROVED_FORMAL_LISTEN_PORT + 1)

        with self.assertRaises(LandingNodeCreateError) as ctx:
            validate_landing_node_create_request(db=FakeSession(), vps=approved_vps(), payload=payload)

        self.assertEqual(ctx.exception.code, "FORMAL_PORT_NOT_APPROVED")

    def test_create_payload_passes_node_name_and_reality_fields(self):
        worker = Worker(
            id="worker-1",
            server_id=APPROVED_FORMAL_SERVER_ID,
            role="landing",
            status="online",
            interface_name="ens17",
            worker_version="0.1.21-stage-3.3.97",
            worker_secret_hash="hash",
        )
        captured_payload = {}
        command = WorkerCommand(id="command-1", worker_id=worker.id, command_type=LANDING_NODE_CREATE_COMMAND)

        def fake_create_worker_command(_db, _worker, _command_type, payload):
            captured_payload.update(payload)
            return command

        payload = approved_payload(
            node_name="custom-reality-node",
            server_name="example.com",
            dest="example.com:443",
        )

        with (
            patch("app.services.landing_node_create.validate_landing_node_create_request", return_value=worker),
            patch("app.services.landing_node_create.create_worker_command", side_effect=fake_create_worker_command),
        ):
            returned_command, returned_worker = create_landing_node_create_command(
                db=FakeSession(),
                vps=approved_vps(),
                payload=payload,
            )

        self.assertIs(returned_command, command)
        self.assertIs(returned_worker, worker)
        self.assertEqual(captured_payload["node_name"], "custom-reality-node")
        self.assertEqual(captured_payload["server_name"], "example.com")
        self.assertEqual(captured_payload["dest"], "example.com:443")
        self.assertEqual(captured_payload["listen_port"], APPROVED_FORMAL_LISTEN_PORT)

    def test_success_result_sanitizes_full_share_link_from_command_result(self):
        db = FakeSession()
        command = WorkerCommand(
            id="command-1",
            worker_id="worker-1",
            server_id=APPROVED_FORMAL_SERVER_ID,
            command_type=LANDING_NODE_CREATE_COMMAND,
        )
        full_link = "vless://fake-redacted-example"
        result = {
            "status": "succeeded",
            "node_name": "custom-reality-node",
            "listen_port": APPROVED_FORMAL_LISTEN_PORT,
            "flow": "xtls-rprx-vision",
            "uuid": "fake-uuid",
            "reality_public_key": "fake-public-key",
            "reality_short_id": "fake-short-id",
            "server_name": "example.com",
            "dest": "example.com:443",
            "fingerprint": "chrome",
            "secure_share_link": full_link,
        }

        sanitized = persist_successful_landing_node_result(db=db, command=command, result=result)

        self.assertNotIn("secure_share_link", sanitized)
        self.assertTrue(sanitized["share_link_present"])
        self.assertEqual(sanitized["share_link_storage"], "node.share_link_written_after_success")
        self.assertTrue(db.flushed)
        created_nodes = [item for item in db.added if isinstance(item, Node)]
        self.assertEqual(len(created_nodes), 1)
        self.assertEqual(created_nodes[0].share_link, full_link)


if __name__ == "__main__":
    unittest.main()
