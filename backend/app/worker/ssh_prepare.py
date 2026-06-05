from datetime import UTC, datetime
from typing import Any

from app.models.vps_server import VpsServer
from app.worker.ssh_read import (
    SSHReadError,
    connect_transport,
    ensure_supported_os,
    parse_os_release,
    run_read_only_command,
)

PREPARE_COMMANDS = {
    "os_release": "cat /etc/os-release",
    "architecture": "uname -m",
    "whoami": "whoami",
    "systemd_available": "test -d /run/systemd/system",
    "xray_path": "command -v xray",
    "xray_service_exists": "systemctl list-unit-files xray.service --no-pager --no-legend",
    "xray_active": "systemctl is-active xray",
    "listening_tcp": "ss -ltnH",
    "ufw_status": "ufw status",
    "iptables_status": "iptables -S",
    "firewalld_status": "firewall-cmd --state",
    "curl_path": "command -v curl",
    "wget_path": "command -v wget",
    "unzip_path": "command -v unzip",
    "tar_path": "command -v tar",
}

COMMON_PORTS = (443, 8443, 2053, 2083)


def parse_listening_ports(output: str) -> list[int]:
    ports: set[int] = set()
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        local_address = parts[3]
        try:
            port_text = local_address.rsplit(":", 1)[1]
            ports.add(int(port_text))
        except (IndexError, ValueError):
            continue
    return sorted(ports)


def package_tool_result(stdout: str, exit_code: int) -> dict[str, Any]:
    return {
        "available": exit_code == 0 and bool(stdout.strip()),
        "path": stdout.strip() if exit_code == 0 and stdout.strip() else None,
    }


def prepare_node_state(vps: VpsServer, private_key: str, passphrase: str | None) -> dict[str, Any]:
    transport, host_fingerprint, ssh_key_fingerprint = connect_transport(
        vps,
        private_key,
        passphrase,
    )
    try:
        results = {
            key: run_read_only_command(transport, command)
            for key, command in PREPARE_COMMANDS.items()
        }
    finally:
        transport.close()

    if results["os_release"].exit_code != 0:
        raise SSHReadError("UNSUPPORTED_OS", "无法读取系统版本。")

    os_release = parse_os_release(results["os_release"].stdout)
    ensure_supported_os(os_release)

    whoami = results["whoami"].stdout.strip()
    if whoami != "root":
        raise SSHReadError("NO_ROOT_PERMISSION", "第 2.1 阶段只支持 root 权限检查。")

    architecture = results["architecture"].stdout.strip()
    systemd_available = results["systemd_available"].exit_code == 0
    xray_installed = results["xray_path"].exit_code == 0 and bool(results["xray_path"].stdout)
    xray_service_exists = results["xray_service_exists"].exit_code == 0 and bool(
        results["xray_service_exists"].stdout.strip()
    )
    xray_active = (
        results["xray_active"].exit_code == 0
        and results["xray_active"].stdout.strip() == "active"
    )

    listening_ports = parse_listening_ports(results["listening_tcp"].stdout)
    common_ports = [
        {
            "port": port,
            "occupied": port in listening_ports,
        }
        for port in COMMON_PORTS
    ]

    tools = {
        "curl": package_tool_result(results["curl_path"].stdout, results["curl_path"].exit_code),
        "wget": package_tool_result(results["wget_path"].stdout, results["wget_path"].exit_code),
        "unzip": package_tool_result(results["unzip_path"].stdout, results["unzip_path"].exit_code),
        "tar": package_tool_result(results["tar_path"].stdout, results["tar_path"].exit_code),
    }
    missing_tools = [name for name, item in tools.items() if not item["available"]]
    occupied_common_ports = [item["port"] for item in common_ports if item["occupied"]]

    warnings: list[str] = []
    failures: list[str] = []
    if not systemd_available:
        failures.append("systemd 不可用")
    if xray_installed:
        failures.append("Xray 已安装")
    if xray_service_exists:
        failures.append("xray.service 已存在")
    if results["listening_tcp"].exit_code != 0:
        failures.append("无法检查 TCP 端口占用")
    if missing_tools:
        failures.append("缺少工具：" + ", ".join(missing_tools))
    if occupied_common_ports:
        warnings.append("常用端口被占用：" + ", ".join(str(port) for port in occupied_common_ports))

    passed = not failures

    return {
        "classification": "prepare_node",
        "message": "可以进入安装 Xray" if passed else "安装前检查未通过",
        "passed": passed,
        "warnings": warnings,
        "failures": failures,
        "ssh": {
            "username": vps.ssh_username,
            "host_key_fingerprint": host_fingerprint,
            "ssh_key_fingerprint": ssh_key_fingerprint,
        },
        "system": {
            "id": os_release.get("ID"),
            "name": os_release.get("PRETTY_NAME") or os_release.get("NAME"),
            "version_id": os_release.get("VERSION_ID"),
            "architecture": architecture,
            "whoami": whoami,
            "is_root": whoami == "root",
            "supported": True,
            "systemd_available": systemd_available,
        },
        "xray": {
            "installed": xray_installed,
            "binary_path": results["xray_path"].stdout if xray_installed else None,
            "service_exists": xray_service_exists,
            "service_active": xray_active,
        },
        "ports": {
            "listening_tcp": listening_ports,
            "common": common_ports,
        },
        "firewall": {
            "ufw": {
                "available": results["ufw_status"].exit_code == 0,
                "summary": results["ufw_status"].stdout.splitlines()[:6],
            },
            "iptables": {
                "available": results["iptables_status"].exit_code == 0,
                "summary": results["iptables_status"].stdout.splitlines()[:12],
            },
            "firewalld": {
                "available": results["firewalld_status"].exit_code == 0,
                "state": results["firewalld_status"].stdout or None,
            },
        },
        "tools": tools,
        "checked_at": datetime.now(UTC).isoformat(),
    }
