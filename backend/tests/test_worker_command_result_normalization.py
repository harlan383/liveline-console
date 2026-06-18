import unittest

from app.api.routes.workers import (
    WORKER_RESULT_BODY_LIMIT_BYTES,
    WorkerReportBodyError,
    decode_worker_command_report_body,
    worker_command_status_is_terminal,
)
from app.services.worker_commands import normalize_worker_command_result


class WorkerCommandResultNormalizationTests(unittest.TestCase):
    def test_transit_readonly_preflight_result_is_normalized_and_redacted(self):
        result = normalize_worker_command_result(
            "transit_readonly_preflight",
            {
                "passed": False,
                "status": "blocked",
                "summary": "x" * 1200,
                "checks": [
                    {
                        "id": "planned_port_free",
                        "label": "Planned port",
                        "status": "failed",
                        "passed": False,
                        "detail": "port occupied",
                        "worker_token": "fake-token-that-must-not-survive",
                    }
                ],
                "worker_token": "fake-token-that-must-not-survive",
                "notes": "safe\x00text",
            },
        )

        self.assertFalse(result["passed"])
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(str(result["summary"]).endswith("...[truncated]"))
        self.assertEqual(result["checks"][0]["id"], "planned_port_free")
        self.assertFalse(result["checks"][0]["passed"])
        self.assertEqual(result["checks"][0]["sensitive_output_redacted"], True)
        self.assertEqual(result["extra"]["worker_token"], "[redacted]")
        self.assertEqual(result["extra"]["notes"], "safetext")

    def test_transit_readonly_preflight_rejects_non_object_result(self):
        with self.assertRaises(ValueError):
            normalize_worker_command_result("transit_readonly_preflight", ["not", "an", "object"])

    def test_worker_report_body_rejects_invalid_json(self):
        with self.assertRaises(WorkerReportBodyError) as context:
            decode_worker_command_report_body(b"{not-json", len(b"{not-json"))

        self.assertEqual(context.exception.code, "WORKER_RESULT_PARSE_ERROR")

    def test_worker_report_body_rejects_non_object_json(self):
        with self.assertRaises(WorkerReportBodyError) as context:
            decode_worker_command_report_body(b"[]", len(b"[]"))

        self.assertEqual(context.exception.code, "WORKER_RESULT_INVALID_PAYLOAD")

    def test_worker_report_body_strips_nul_characters(self):
        payload = decode_worker_command_report_body(
            b'{"result":\x00{"summary":"safe"}}',
            len(b'{"result":\x00{"summary":"safe"}}'),
        )

        self.assertEqual(payload["result"]["summary"], "safe")

    def test_worker_report_body_limit_constant_is_bounded(self):
        self.assertLessEqual(WORKER_RESULT_BODY_LIMIT_BYTES, 128 * 1024)

    def test_worker_report_body_rejects_oversized_payload(self):
        with self.assertRaises(WorkerReportBodyError) as context:
            decode_worker_command_report_body(
                b'{"result":{}}',
                WORKER_RESULT_BODY_LIMIT_BYTES + 1,
            )

        self.assertEqual(context.exception.code, "WORKER_RESULT_BODY_TOO_LARGE")

    def test_worker_command_terminal_status_helper(self):
        self.assertTrue(worker_command_status_is_terminal("succeeded"))
        self.assertTrue(worker_command_status_is_terminal("failed"))
        self.assertTrue(worker_command_status_is_terminal("completed"))
        self.assertFalse(worker_command_status_is_terminal("running"))
        self.assertFalse(worker_command_status_is_terminal(None))


if __name__ == "__main__":
    unittest.main()
