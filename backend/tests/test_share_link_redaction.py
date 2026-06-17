import unittest

from app.services.redaction import mask_identifier, mask_share_link, redact_sensitive_payload


class ShareLinkRedactionTests(unittest.TestCase):
    def test_share_link_mask_keeps_only_scheme(self):
        link = "vless" + "://fake-redacted-example"

        self.assertEqual(mask_share_link(link), "vless://[redacted]")

    def test_identifier_mask_does_not_return_full_value(self):
        value = "12345678-abcd-efgh-ijkl-123456789000"

        masked = mask_identifier(value)

        self.assertIsNotNone(masked)
        self.assertNotEqual(masked, value)
        self.assertIn("[redacted]", masked or "")

    def test_nested_payload_redacts_links_and_node_material(self):
        link = "vless" + "://fake-redacted-example"
        payload = {
            "node": {
                "share_link": link,
                "uuid": "12345678-abcd-efgh-ijkl-123456789000",
                "nested": [{"reality_short_id": "abcdef123456"}],
            }
        }

        redacted = redact_sensitive_payload(payload)

        self.assertEqual(redacted["node"]["share_link"], "vless://[redacted]")
        self.assertIn("[redacted]", redacted["node"]["uuid"])
        self.assertIn("[redacted]", redacted["node"]["nested"][0]["reality_short_id"])


if __name__ == "__main__":
    unittest.main()
