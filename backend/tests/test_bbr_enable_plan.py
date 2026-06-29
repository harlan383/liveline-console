from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from app.models.vps_server import VpsServer
from app.models.worker_command import WorkerCommand
from app.services.bbr_enable_plan import build_bbr_enable_plan


SERVER_ID = "landing-1"


class FakeDb:
    def __init__(self, server: VpsServer | None = None) -> None:
        self.server = server or VpsServer(id=SERVER_ID, name="landing", ip="198.51.100.19", status="active")
        self.added: list[object] = []

    def get(self, model, item_id):
        if model is VpsServer and self.server and item_id == self.server.id:
            return self.server
        return None

    def add(self, item):
        self.added.append(item)


def preflight_with_bbr(bbr: dict | None) -> WorkerCommand:
    result_json = {"bbr": bbr} if bbr is not None else {"system": {"hostname": "landing"}}
    return WorkerCommand(
        id="preflight-1",
        worker_id="worker-1",
        server_type="landing",
        server_id=SERVER_ID,
        command_type="landing_preflight",
        status="succeeded",
        result_json=result_json,
        completed_at=datetime(2026, 6, 29, 8, 0, 0, tzinfo=timezone.utc),
    )


class BbrEnablePlanTests(unittest.TestCase):
    def build_with_preflight(self, command: WorkerCommand | None) -> dict:
        with patch("app.services.bbr_enable_plan.latest_landing_preflight_command", return_value=command):
            return build_bbr_enable_plan(FakeDb(), SERVER_ID)

    def test_no_landing_preflight_blocks_plan(self):
        plan = self.build_with_preflight(None)

        self.assertFalse(plan["ready"])
        self.assertEqual(plan["blocked_reasons"], ["latest_landing_preflight_required"])
        self.assertEqual(plan["planned_actions"], [])

    def test_missing_bbr_result_blocks_plan(self):
        plan = self.build_with_preflight(preflight_with_bbr(None))

        self.assertFalse(plan["ready"])
        self.assertEqual(plan["blocked_reasons"], ["bbr_readonly_result_required"])
        self.assertEqual(plan["latest_preflight_id"], "preflight-1")

    def test_current_bbr_reports_already_enabled(self):
        plan = self.build_with_preflight(
            preflight_with_bbr(
                {
                    "current_congestion_control": "bbr",
                    "available_congestion_control": "reno cubic bbr",
                }
            )
        )

        self.assertFalse(plan["ready"])
        self.assertTrue(plan["already_enabled"])
        self.assertEqual(plan["recommendation"], "already_enabled")
        self.assertEqual(plan["planned_actions"], [])

    def test_available_bbr_can_enable_with_approval(self):
        plan = self.build_with_preflight(
            preflight_with_bbr(
                {
                    "current_congestion_control": "cubic",
                    "available_congestion_control": "reno cubic bbr",
                    "default_qdisc": "fq_codel",
                }
            )
        )

        self.assertTrue(plan["ready"])
        self.assertEqual(plan["recommendation"], "can_enable_with_approval")
        self.assertNotIn("confirm_load_tcp_bbr_module", plan["required_confirmations"])
        self.assertIn("confirm_write_sysctl_config", plan["required_confirmations"])
        self.assertTrue(any(action["step"] == "persist_congestion_control_bbr" for action in plan["planned_actions"]))

    def test_module_available_requires_load_approval(self):
        plan = self.build_with_preflight(
            preflight_with_bbr(
                {
                    "current_congestion_control": "cubic",
                    "available_congestion_control": "reno cubic",
                    "module_status": "not_loaded",
                    "modinfo_status": "available",
                    "module_files": ["/lib/modules/example/kernel/net/ipv4/tcp_bbr.ko"],
                    "kernel_config_bbr": "CONFIG_TCP_CONG_BBR=m",
                }
            )
        )

        self.assertTrue(plan["ready"])
        self.assertEqual(plan["recommendation"], "module_available_needs_load_approval")
        self.assertIn("confirm_load_tcp_bbr_module", plan["required_confirmations"])
        self.assertEqual(plan["planned_actions"][0]["step"], "load_tcp_bbr_module")

    def test_bbr_not_available_blocks_plan(self):
        plan = self.build_with_preflight(
            preflight_with_bbr(
                {
                    "current_congestion_control": "cubic",
                    "available_congestion_control": "reno cubic",
                    "module_status": "not_found",
                    "modinfo_status": "not_found",
                    "module_files": [],
                }
            )
        )

        self.assertFalse(plan["ready"])
        self.assertEqual(plan["recommendation"], "bbr_not_available")
        self.assertEqual(plan["blocked_reasons"], ["bbr_not_available"])


if __name__ == "__main__":
    unittest.main()
