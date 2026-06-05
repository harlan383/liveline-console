from datetime import UTC, datetime
from contextlib import suppress
import socket
from typing import Any

import paramiko

from app.core.config import get_settings
from app.models.transit_resource import TransitResource
from app.services.task_logging import sanitize_log_text
from app.worker.ssh_prepare import COMMON_PORTS, parse_listening_ports
from app.worker.ssh_read import (
    CommandResult,
    SSHReadError,
    host_key_fingerprint,
    load_private_key,
    parse_os_release,
    public_key_fingerprint,
    run_read_only_command,
)

TRANSIT_READ_COMMANDS = {
    "os_release": "cat /etc/os-release",
    "architecture": "uname -m",
    "whoami": "whoami",
    "systemd_available": "test -d /run/systemd/system",
    "gost_path": "command -v gost",
    "nginx_path": "command -v nginx",
    "socat_path": "command -v socat",
    "xray_path": "command -v xray",
    "listening_tcp": "ss -ltnH",
    "ufw_status": "ufw status",
    "iptables_status": "iptables -S",
    "firewalld_status": "firewall-cmd --state",
}


def connect_transit_transport(
    resource: TransitResource,
    private_key: str,
    passphrase: str | None,
) -> tuple[paramiko.Transport, str, str]:
    settings = get_settings()
    if not resource.ssh_host or not resource.ssh_port or not resource.ssh_username:
        raise SSHReadError("TRANSIT_SSH_METADATA_MISSING", "中转资源缺少 SSH 元数据。")

    transport: paramiko.Transport | None = None
    try:
        sock = socket.create_connection(
            (resource.ssh_host, resource.ssh_port),
            timeout=settings.ssh_connect_timeout_seconds,
        )
        transport = paramiko.Transport(sock)
        transport.banner_timeout = max(settings.ssh_connect_timeout_seconds, 30)
        transport.auth_timeout = max(settings.ssh_connect_timeout_seconds, 30)
        transport.start_client(timeout=settings.ssh_connect_timeout_seconds)
        transport_exception = transport.get_exception()
        if transport_exception is not None:
            raise transport_exception
        if not transport.is_active():
            raise paramiko.SSHException("SSH session is not active")
        host_key = transport.get_remote_server_key()
    except (socket.timeout, TimeoutError, OSError, paramiko.SSHException) as exc:
        if transport is not None:
            transport_exception = transport.get_exception()
            if transport_exception is not None:
                exc = transport_exception
            with suppress(Exception):
                transport.close()
        message = str(exc).strip() or "SSH 连接超时或无法建立连接。"
        raise SSHReadError("SSH_CONNECT_FAILED", message) from exc

    presented_host_fingerprint = host_key_fingerprint(host_key)
    try:
        pkey = load_private_key(private_key, passphrase)
    except Exception:
        transport.close()
        raise

    try:
        transport.auth_publickey(resource.ssh_username, pkey)
    except (paramiko.AuthenticationException, paramiko.SSHException) as exc:
        transport.close()
        raise SSHReadError("SSH_AUTH_FAILED", "SSH Key 认证失败。") from exc

    if not transport.is_authenticated():
        transport.close()
        raise SSHReadError("SSH_AUTH_FAILED", "SSH Key 认证失败。")

    return transport, presented_host_fingerprint, public_key_fingerprint(pkey)


def tool_result(result: CommandResult) -> dict[str, Any]:
    available = result.exit_code == 0 and bool(result.stdout.strip())
    return {
        "available": available,
        "path": result.stdout.strip() if available else None,
    }


def firewall_summary(result: CommandResult, *, max_lines: int) -> list[str]:
    output = result.stdout if result.exit_code == 0 else result.stderr
    clean_output = sanitize_log_text(output) or ""
    return clean_output.splitlines()[:max_lines]


def read_transit_server_state(
    resource: TransitResource,
    private_key: str,
    passphrase: str | None,
) -> dict[str, Any]:
    transport, host_fingerprint, ssh_key_fingerprint = connect_transit_transport(
        resource,
        private_key,
        passphrase,
    )
    try:
        results = {
            key: run_read_only_command(transport, command)
            for key, command in TRANSIT_READ_COMMANDS.items()
        }
    finally:
        transport.close()

    if results["os_release"].exit_code != 0:
        raise SSHReadError("UNSUPPORTED_OS", "无法读取系统版本。")

    os_release = parse_os_release(results["os_release"].stdout)
    architecture = results["architecture"].stdout.strip()
    whoami = results["whoami"].stdout.strip()
    systemd_available = results["systemd_available"].exit_code == 0
    listening_ports = parse_listening_ports(results["listening_tcp"].stdout)
    common_ports = [
        {
            "port": port,
            "occupied": port in listening_ports,
        }
        for port in COMMON_PORTS
    ]

    tools = {
        "gost": tool_result(results["gost_path"]),
        "nginx": tool_result(results["nginx_path"]),
        "socat": tool_result(results["socat_path"]),
        "xray": tool_result(results["xray_path"]),
    }

    warnings: list[str] = []
    failures: list[str] = []
    if whoami != "root":
        failures.append("中转服务器后续安装和配置需要 root 用户")
    if not systemd_available:
        failures.append("systemd 不可用")
    if results["listening_tcp"].exit_code != 0:
        failures.append("无法检查 TCP 监听端口")
    occupied_common_ports = [item["port"] for item in common_ports if item["occupied"]]
    if occupied_common_ports:
        warnings.append("常用端口被占用：" + ", ".join(str(port) for port in occupied_common_ports))

    passed = not failures

    return {
        "classification": "read_transit_server",
        "checked": True,
        "passed": passed,
        "message": "中转服务器只读检查完成" if passed else "中转服务器只读检查发现问题",
        "ssh": {
            "username": resource.ssh_username,
            "ssh_key_fingerprint": ssh_key_fingerprint,
            "host_key_fingerprint": host_fingerprint,
        },
        "system": {
            "id": os_release.get("ID"),
            "name": os_release.get("PRETTY_NAME") or os_release.get("NAME"),
            "version_id": os_release.get("VERSION_ID"),
            "architecture": architecture,
            "whoami": whoami,
            "is_root": whoami == "root",
            "systemd_available": systemd_available,
        },
        "tools": tools,
        "ports": {
            "listening_tcp": listening_ports,
            "common": common_ports,
        },
        "firewall": {
            "ufw": {
                "available": results["ufw_status"].exit_code == 0,
                "summary": firewall_summary(results["ufw_status"], max_lines=6),
            },
            "iptables": {
                "available": results["iptables_status"].exit_code == 0,
                "summary": firewall_summary(results["iptables_status"], max_lines=12),
            },
            "firewalld": {
                "available": results["firewalld_status"].exit_code == 0,
                "state": results["firewalld_status"].stdout.strip() or None,
            },
        },
        "warnings": warnings,
        "failures": failures,
        "checked_at": datetime.now(UTC).isoformat(),
    }
