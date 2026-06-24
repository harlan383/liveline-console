import unittest

from app.services.node_display import build_node_display_fields


class NodeDisplayFieldsTest(unittest.TestCase):
    def test_active_service_not_checked_connectivity_is_neutral(self):
        fields = build_node_display_fields("active", "not_checked")

        self.assertEqual(fields["service_display_label"], "服务运行中")
        self.assertEqual(fields["connectivity_display_status"], "not_checked")
        self.assertEqual(fields["connectivity_display_label"], "服务运行中，连接未检测")
        self.assertEqual(fields["node_health_summary"], "服务运行中，连接未检测")

    def test_failed_connectivity_keeps_failed_semantics(self):
        fields = build_node_display_fields("active", "failed")

        self.assertEqual(fields["connectivity_display_status"], "failed")
        self.assertEqual(fields["connectivity_display_label"], "连接检测失败")

    def test_connected_connectivity_keeps_success_semantics(self):
        fields = build_node_display_fields("active", "success")

        self.assertEqual(fields["connectivity_display_status"], "connected")
        self.assertEqual(fields["connectivity_display_label"], "连接检测正常")


if __name__ == "__main__":
    unittest.main()
