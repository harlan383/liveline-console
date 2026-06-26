from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.models.node import Node
from app.models.vps_server import VpsServer
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand
from app.schemas.landing_node_plan import LandingNodeCreateRequest
from app.services.landing_node_create import (
    APPROVED_FORMAL_LISTEN_PORT,
    LANDING_NODE_CREATE_COMMAND,
    LandingNodeCreateError,
    create_landing_node_create_command,
    persist_successful_landing_node_result,
    validate_landing_node_create_request,
)


SERVER_ID = "a3e4c4bf-2b4a-4705-bb45-65d9da9c1cbf"
SERVER_IP = "198.51.100.19"
WORKER_ID = "bf7f9a90-e010-490b-8927-b2341d16485a"


class FakeScalarResult:
    def __init__(self, items):
        self.items = items

    def all(self):
        return list(self.items)


class FakeSession:
    def __init__(self, *, workers=None, vps=None) -> None:
        self.added = []
        self.flushed = False
        self.workers = workers or []
        self.vps = vps or approved_vps()

    def scalar(self, *_args, **_kwargs):
        return None

    def scalars(self, *_args, **_kwargs):
        return FakeScalarResult(self.workers)

    def get(self, model, item_id):
        if model is VpsServer and item_id == self.vps.id:
            return self.vps
        return None

    def add(self, item):
        self.added.append(item)

    def flush(self):
        self.flushed = True


def approved_vps(**overrides) -> VpsServer:
    data = {"id": SERVER_ID, "ip": SERVER_IP, "status": "active", "name": "landing-test"}
    data.update(overrides)
    return VpsServer(**data)


def landing_worker(**overrides) -> Worker:
    data = {
        "id": WORKER_ID,
        "server_id": SERVER_ID,
        "role": "landing",
        "status": "online",
        "interface_name": "ens17",
        "worker_version": "0.1.32-stage-3.3.179-reality-dest-sni-template",
        "worker_secret_hash": "hash",
        "last_heartbeat_at": datetime.now(timezone.utc),
    }
    data.update(overrides)
    return Worker(**data)


def successful_preflight(**overrides) -> WorkerCommand:
    result = {
        "warnings": [],
        "errors": [],
        "network": {
            "worker_config_interface": "ens17",
            "default_route_interface": "ens17",
            "interface_mismatch": False,
        },
        "services": [],
        "binaries": [],
        "xray_discovery": {"paths": []},
    }
    result.update(overrides.pop("result_json", {}))
    data = {
        "id": "preflight-1",
        "worker_id": WORKER_ID,
        "server_id": SERVER_ID,
        "server_type": "landing",
        "command_type": "landing_preflight",
        "status": "succeeded",
        "result_json": result,
    }
    data.update(overrides)
    return WorkerCommand(**data)


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
    def test_active_server_with_matching_worker_and_clean_preflight_is_allowed(self):
        worker = landing_worker()

        with patch("app.services.landing_node_create.latest_landing_preflight", return_value=successful_preflight()):
            selected = validate_landing_node_create_request(
                db=FakeSession(workers=[worker]),
                vps=approved_vps(),
                payload=approved_payload(),
            )

        self.assertIs(selected, worker)

    def test_non_approved_port_is_still_rejected(self):
        payload = approved_payload(approved_port=APPROVED_FORMAL_LISTEN_PORT + 1)

        with self.assertRaises(LandingNodeCreateError) as ctx:
            validate_landing_node_create_request(db=FakeSession(), vps=approved_vps(), payload=payload)

        self.assertEqual(ctx.exception.code, "FORMAL_PORT_NOT_APPROVED")

    def test_deleted_server_is_rejected(self):
        with self.assertRaises(LandingNodeCreateError) as ctx:
            validate_landing_node_create_request(
                db=FakeSession(workers=[landing_worker()]),
                vps=approved_vps(status="deleted"),
                payload=approved_payload(),
            )

        self.assertEqual(ctx.exception.code, "FORMAL_SERVER_NOT_APPROVED")

    def test_worker_bound_to_different_server_is_rejected(self):
        worker = landing_worker(server_id="other-server")

        with patch("app.services.landing_node_create.latest_landing_preflight", return_value=successful_preflight()):
            with self.assertRaises(LandingNodeCreateError) as ctx:
                validate_landing_node_create_request(
                    db=FakeSession(workers=[worker]),
                    vps=approved_vps(),
                    payload=approved_payload(),
                )

        self.assertEqual(ctx.exception.code, "APPROVED_WORKER_OFFLINE")

    def test_worker_interface_must_match_preflight_default_interface(self):
        worker = landing_worker(interface_name="eth0")

        with patch("app.services.landing_node_create.latest_landing_preflight", return_value=successful_preflight()):
            with self.assertRaises(LandingNodeCreateError) as ctx:
                validate_landing_node_create_request(
                    db=FakeSession(workers=[worker]),
                    vps=approved_vps(),
                    payload=approved_payload(),
                )

        self.assertEqual(ctx.exception.code, "FORMAL_WORKER_INTERFACE_MISMATCH")

    def test_preflight_interface_mismatch_warning_is_rejected(self):
        preflight = successful_preflight(
            result_json={
                "warnings": [{"code": "interface_mismatch"}],
                "network": {
                    "worker_config_interface": "eth0",
                    "default_route_interface": "ens17",
                    "interface_mismatch": True,
                },
            }
        )

        with patch("app.services.landing_node_create.latest_landing_preflight", return_value=preflight):
            with self.assertRaises(LandingNodeCreateError) as ctx:
                validate_landing_node_create_request(
                    db=FakeSession(workers=[landing_worker()]),
                    vps=approved_vps(),
                    payload=approved_payload(),
                )

        self.assertEqual(ctx.exception.code, "FORMAL_PREFLIGHT_INTERFACE_MISMATCH")

    def test_missing_successful_preflight_is_rejected(self):
        with patch("app.services.landing_node_create.latest_landing_preflight", return_value=None):
            with self.assertRaises(LandingNodeCreateError) as ctx:
                validate_landing_node_create_request(
                    db=FakeSession(workers=[landing_worker()]),
                    vps=approved_vps(),
                    payload=approved_payload(),
                )

        self.assertEqual(ctx.exception.code, "LANDING_PREFLIGHT_REQUIRED")

    def test_create_payload_passes_node_name_and_reality_fields(self):
        worker = landing_worker()
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
                db=FakeSession(workers=[worker]),
                vps=approved_vps(),
                payload=payload,
            )

        self.assertIs(returned_command, command)
        self.assertIs(returned_worker, worker)
        self.assertEqual(captured_payload["server_id"], SERVER_ID)
        self.assertEqual(captured_payload["node_name"], "custom-reality-node")
        self.assertEqual(captured_payload["server_name"], "example.com")
        self.assertEqual(captured_payload["sni"], "example.com")
        self.assertEqual(captured_payload["reality_sni"], "example.com")
        self.assertEqual(captured_payload["dest"], "example.com:443")
        self.assertEqual(captured_payload["reality_dest"], "example.com:443")
        self.assertEqual(captured_payload["fingerprint"], "chrome")
        self.assertEqual(captured_payload["interface_name"], "ens17")
        self.assertEqual(captured_payload["listen_port"], APPROVED_FORMAL_LISTEN_PORT)

    def test_create_payload_defaults_to_cloudflare_reality_template(self):
        worker = landing_worker()
        captured_payload = {}
        command = WorkerCommand(id="command-1", worker_id=worker.id, command_type=LANDING_NODE_CREATE_COMMAND)

        def fake_create_worker_command(_db, _worker, _command_type, payload):
            captured_payload.update(payload)
            return command

        with (
            patch("app.services.landing_node_create.validate_landing_node_create_request", return_value=worker),
            patch("app.services.landing_node_create.create_worker_command", side_effect=fake_create_worker_command),
        ):
            create_landing_node_create_command(
                db=FakeSession(workers=[worker]),
                vps=approved_vps(),
                payload=approved_payload(),
            )

        self.assertEqual(captured_payload["server_name"], "dash.cloudflare.com")
        self.assertEqual(captured_payload["dest"], "dash.cloudflare.com:443")
        self.assertEqual(captured_payload["fingerprint"], "chrome")
        self.assertEqual(captured_payload["flow"], "xtls-rprx-vision")
        self.assertEqual(captured_payload["security"], "reality")
        self.assertEqual(captured_payload["transport"], "tcp")

    def test_create_payload_rejects_invalid_reality_sni_and_dest(self):
        invalid_cases = [
            {"server_name": "https://dash.cloudflare.com"},
            {"server_name": "dash.cloudflare.com/"},
            {"server_name": "dash.cloudflare.com:443"},
            {"dest": "dash.cloudflare.com:abc"},
            {"dest": "https://dash.cloudflare.com:443"},
        ]
        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValidationError):
                    approved_payload(**overrides)

    def test_success_result_sanitizes_full_share_link_from_command_result(self):
        db = FakeSession(vps=approved_vps(status="unconfigured"))
        command = WorkerCommand(
            id="command-1",
            worker_id=WORKER_ID,
            server_id=SERVER_ID,
            command_type=LANDING_NODE_CREATE_COMMAND,
        )
        full_link = "vless" + "://fake-redacted-example"
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
        self.assertEqual(created_nodes[0].vps_id, SERVER_ID)
        self.assertEqual(created_nodes[0].share_link, full_link)
        self.assertEqual(db.vps.status, "active")


if __name__ == "__main__":
    unittest.main()
