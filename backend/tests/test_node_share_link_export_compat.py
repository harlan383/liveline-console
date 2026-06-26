import json
import unittest
from unittest.mock import patch

from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.routes import nodes
from app.models.node import Node


class FakeAdminSession:
    admin_id = "admin-1"


class FakeSession:
    def __init__(self, node: Node | None) -> None:
        self.node = node
        self.committed = False
        self.added: list[object] = []

    def get(self, model, item_id):
        if model is Node and self.node and item_id == self.node.id:
            return self.node
        return None

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True


def make_request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )


def response_payload(response):
    if isinstance(response, JSONResponse):
        return json.loads(response.body)
    return response


class NodeShareLinkExportCompatTests(unittest.TestCase):
    def test_export_adds_header_type_none_without_mutating_stored_share_link(self):
        stored_link = (
            "vless"
            + "://11111111-2222-3333-4444-555555555555@64.90.13.19:27939"
            "?encryption=none&flow=xtls-rprx-vision&security=reality&sni=dash.cloudflare.com"
            "&fp=chrome&pbk=fake-public-key&sid=fake-short-id&type=tcp#liveline-reality-27939"
        )
        node = Node(
            id="node-1",
            vps_id="server-1",
            node_name="liveline-reality-27939",
            protocol="vless",
            transport="tcp",
            security="reality",
            flow="xtls-rprx-vision",
            xray_port=27939,
            share_link=stored_link,
            status="active",
        )

        with patch.object(nodes, "require_admin_session", return_value=FakeAdminSession()), patch.object(
            nodes, "csrf_valid", return_value=True
        ):
            response = nodes.export_node_share_link(
                node.id,
                nodes.NodeShareLinkExportRequest(confirm_export=True),
                make_request(f"/api/nodes/{node.id}/share-link/export"),
                FakeSession(node),
            )

        data = response_payload(response)
        self.assertTrue(data["success"])
        self.assertIn("headerType=none", data["data"]["share_link"])
        self.assertIn("spx=%2F", data["data"]["share_link"])
        self.assertEqual(node.share_link, stored_link)


if __name__ == "__main__":
    unittest.main()
