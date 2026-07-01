import json
import unittest

from backend.tests.test_stage_3_4_22_haproxy_context_autofill import (
    SENSITIVE_LINK_PREFIX,
    FakeScalarResult,
    FakeSession,
    call_context,
    response_payload,
)


def integrity_checks(candidate):
    return {check["id"]: check for check in candidate["integrity_checks"]}


class IntegrityFakeSession(FakeSession):
    def __init__(
        self,
        *,
        include_resource: bool = True,
        include_node: bool = True,
        include_worker: bool = True,
        command_status: str = "succeeded",
        node_ip: str = "64.90.13.19",
        node_port: int = 28917,
    ) -> None:
        super().__init__()
        self.include_resource = include_resource
        self.include_node = include_node
        self.include_worker = include_worker
        self.good_command.status = command_status
        self.node.vps.ip = node_ip
        self.node.xray_port = node_port

    def scalars(self, statement):
        text = str(statement)
        if "FROM workers" in text:
            return FakeScalarResult([self.worker] if self.include_worker else [])
        if "FROM transit_resources" in text:
            return FakeScalarResult([self.resource] if self.include_resource else [])
        if "FROM nodes" in text:
            return FakeScalarResult([self.node] if self.include_node else [])
        if "FROM worker_commands" in text:
            return FakeScalarResult([self.good_command, self.non_haproxy_command, self.real_execution_command])
        return FakeScalarResult([])


class Stage3423HaproxyContextIntegrityTest(unittest.TestCase):
    def candidate_from(self, db):
        payload = response_payload(call_context(db))
        return payload["data"]["haproxy_dry_run_commands"][0], payload

    def assert_no_writes(self, db):
        self.assertFalse(db.added)
        self.assertFalse(db.commit_called)
        self.assertFalse(db.flush_called)
        self.assertFalse(db.refresh_called)

    def test_candidate_integrity_ready_success(self):
        db = IntegrityFakeSession()
        candidate, _payload = self.candidate_from(db)
        checks = integrity_checks(candidate)

        self.assertIs(candidate["integrity_ready"], True)
        self.assertIs(candidate["integrity_blocked"], False)
        self.assertTrue(all(check["passed"] for check in checks.values()))
        self.assertTrue(checks["transit_resource_record_exists"]["passed"])
        self.assertTrue(checks["transit_worker_online"]["passed"])
        self.assertTrue(checks["landing_node_active"]["passed"])
        self.assertTrue(checks["candidate_landing_host_matches_node_vps_ip"]["passed"])
        self.assertTrue(checks["candidate_landing_port_matches_node_xray_port"]["passed"])
        self.assertTrue(checks["candidate_status_succeeded"]["passed"])
        self.assert_no_writes(db)

    def test_missing_transit_resource_blocks_integrity(self):
        db = IntegrityFakeSession(include_resource=False)
        candidate, _payload = self.candidate_from(db)
        checks = integrity_checks(candidate)

        self.assertIs(candidate["integrity_ready"], False)
        self.assertIs(candidate["integrity_blocked"], True)
        self.assertFalse(checks["transit_resource_record_exists"]["passed"])
        self.assertEqual("danger", checks["transit_resource_record_exists"]["severity"])
        self.assert_no_writes(db)

    def test_missing_landing_node_blocks_integrity(self):
        db = IntegrityFakeSession(include_node=False)
        candidate, _payload = self.candidate_from(db)
        checks = integrity_checks(candidate)

        self.assertIs(candidate["integrity_ready"], False)
        self.assertFalse(checks["landing_node_record_exists"]["passed"])
        self.assertEqual("danger", checks["landing_node_record_exists"]["severity"])
        self.assert_no_writes(db)

    def test_landing_host_mismatch_blocks_integrity(self):
        db = IntegrityFakeSession(node_ip="203.0.113.99")
        candidate, _payload = self.candidate_from(db)
        checks = integrity_checks(candidate)

        self.assertIs(candidate["integrity_ready"], False)
        self.assertFalse(checks["candidate_landing_host_matches_node_vps_ip"]["passed"])
        self.assertIn("candidate=64.90.13.19", checks["candidate_landing_host_matches_node_vps_ip"]["evidence_summary"])
        self.assert_no_writes(db)

    def test_landing_port_mismatch_blocks_integrity(self):
        db = IntegrityFakeSession(node_port=29999)
        candidate, _payload = self.candidate_from(db)
        checks = integrity_checks(candidate)

        self.assertIs(candidate["integrity_ready"], False)
        self.assertFalse(checks["candidate_landing_port_matches_node_xray_port"]["passed"])
        self.assertIn("candidate=28917", checks["candidate_landing_port_matches_node_xray_port"]["evidence_summary"])
        self.assert_no_writes(db)

    def test_non_succeeded_dry_run_blocks_integrity(self):
        db = IntegrityFakeSession(command_status="running")
        candidate, _payload = self.candidate_from(db)
        checks = integrity_checks(candidate)

        self.assertIs(candidate["integrity_ready"], False)
        self.assertFalse(checks["candidate_status_succeeded"]["passed"])
        self.assertEqual("running", checks["candidate_status_succeeded"]["evidence_summary"])
        self.assert_no_writes(db)

    def test_sensitive_data_still_not_leaked(self):
        db = IntegrityFakeSession()
        candidate, payload = self.candidate_from(db)
        dumped = json.dumps(payload, ensure_ascii=False)

        self.assertNotIn("payload_json", candidate)
        self.assertNotIn("candidate_link", dumped)
        self.assertNotIn("install_command", dumped)
        self.assertNotIn("secret-token", dumped)
        self.assertNotIn("secret-private-key", dumped)
        self.assertNotIn(SENSITIVE_LINK_PREFIX, dumped)
        self.assertNotIn("uuid@example.invalid", dumped)
        self.assert_no_writes(db)


if __name__ == "__main__":
    unittest.main()
