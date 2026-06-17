import unittest

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


if __name__ == "__main__":
    unittest.main()
