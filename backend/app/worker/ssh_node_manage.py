from datetime import UTC, datetime
from typing import Any

from app.models.node import Node
from app.models.vps_server import VpsServer
from app.worker.ssh_create_direct import run_ssh_command
from app.worker.ssh_install import XRAY_CONFIG_PATH
from app.worker.ssh_prepare import parse_listening_ports
from app.worker.ssh_read import CommandResult, SSHReadError, connect_transport, run_read_only_command

NODE_STATUS_COMMANDS = {
    "xray_path": "command -v xray",
    "xray_version": "xray version",
    "config_exists": f"test -e {XRAY_CONFIG_PATH}",
    "config_test": f"xray run -test -config {XRAY_CONFIG_PATH}",
    "xray_active": "systemctl is-active xray",
    "listening_tcp": "ss -ltnH",
}


def command_summary(result: CommandResult) -> dict[str, Any]:
    return {
        "exit_code": result.exit_code,
        "stdout": result.stdout[:500] if result.stdout else "",
        "stderr": result.stderr[:500] if result.stderr else "",
    }


def evaluate_node_checks(node: Node, results: dict[str, CommandResult]) -> dict[str, Any]:
    failures: list[str] = []
    binary_path = results["xray_path"].stdout.strip()
    config_exists = results["config_exists"].exit_code == 0
    config_test_passed = results["config_test"].exit_code == 0
    service_active = (
        results["xray_active"].exit_code == 0 and results["xray_active"].stdout.strip() == "active"
    )
    listening_ports = parse_listening_ports(results["listening_tcp"].stdout)
    listening = bool(node.xray_port and node.xray_port in listening_ports)

    if not binary_path:
        failures.append("未找到 xray binary")
    if results["xray_version"].exit_code != 0:
        failures.append("xray version 执行失败")
    if not config_exists:
        failures.append("Xray 配置文件不存在")
    if not config_test_passed:
        failures.append("xray run -test 未通过")
    if not service_active:
        failures.append("xray.service 未处于 active 状态")
    if not listening:
        failures.append(f"端口 {node.xray_port} 未监听")

    healthy = not failures
    return {
        "healthy": healthy,
        "failures": failures,
        "xray": {
            "binary_path": binary_path or None,
            "version": results["xray_version"].stdout if results["xray_version"].exit_code == 0 else None,
            "config_path": XRAY_CONFIG_PATH,
            "config_exists": config_exists,
            "config_test_passed": config_test_passed,
            "service_active": service_active,
            "listening": listening,
            "port": node.xray_port,
        },
    }


def refresh_node_state(
    vps: VpsServer,
    node: Node,
    private_key: str,
    passphrase: str | None,
) -> dict[str, Any]:
    transport, _, _ = connect_transport(vps, private_key, passphrase)
    try:
        results = {
            key: run_read_only_command(transport, command)
            for key, command in NODE_STATUS_COMMANDS.items()
        }
    finally:
        transport.close()

    evaluated = evaluate_node_checks(node, results)
    return {
        "classification": "refresh_node",
        "refreshed": True,
        "message": "节点状态正常" if evaluated["healthy"] else "节点状态异常",
        "node": {
            "id": node.id,
            "name": node.node_name,
            "status": "active" if evaluated["healthy"] else "error",
            "protocol": node.protocol,
            "port": node.xray_port,
        },
        "xray": evaluated["xray"],
        "warnings": [],
        "failures": evaluated["failures"],
        "checked_at": datetime.now(UTC).isoformat(),
    }


def restart_xray_state(
    vps: VpsServer,
    node: Node,
    private_key: str,
    passphrase: str | None,
) -> dict[str, Any]:
    transport, _, _ = connect_transport(vps, private_key, passphrase)
    try:
        config_test = run_ssh_command(
            transport,
            f"xray run -test -config {XRAY_CONFIG_PATH}",
            timeout_seconds=30,
        )
        if config_test.exit_code != 0:
            raise SSHReadError(
                "XRAY_CONFIG_TEST_FAILED",
                "xray run -test 未通过，未重启服务。",
                {
                    "classification": "restart_xray",
                    "restarted": False,
                    "message": "xray run -test 未通过，未重启服务。",
                    "xray": {
                        "config_path": XRAY_CONFIG_PATH,
                        "config_test_passed": False,
                    },
                    "warnings": [],
                    "failures": ["xray run -test 未通过"],
                },
            )

        restart = run_ssh_command(transport, "systemctl restart xray", timeout_seconds=30)
        if restart.exit_code != 0:
            raise SSHReadError(
                "XRAY_SERVICE_RESTART_FAILED",
                "重启 xray.service 失败。",
                {
                    "classification": "restart_xray",
                    "restarted": False,
                    "message": "重启 xray.service 失败。",
                    "xray": {
                        "config_path": XRAY_CONFIG_PATH,
                        "config_test_passed": True,
                    },
                    "warnings": [],
                    "failures": ["重启 xray.service 失败"],
                },
            )

        results = {
            key: run_read_only_command(transport, command)
            for key, command in NODE_STATUS_COMMANDS.items()
        }
    finally:
        transport.close()

    evaluated = evaluate_node_checks(node, results)
    return {
        "classification": "restart_xray",
        "restarted": evaluated["healthy"],
        "message": "Xray 已重启，节点状态正常" if evaluated["healthy"] else "Xray 已重启，但节点状态异常",
        "node": {
            "id": node.id,
            "name": node.node_name,
            "status": "active" if evaluated["healthy"] else "error",
            "protocol": node.protocol,
            "port": node.xray_port,
        },
        "xray": evaluated["xray"],
        "warnings": [],
        "failures": evaluated["failures"],
        "restarted_at": datetime.now(UTC).isoformat(),
    }
