import base64
import hashlib
import io
import socket
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import paramiko

from app.core.config import get_settings
from app.models.vps_server import VpsServer

READ_ONLY_COMMANDS = {
    "os_release": "cat /etc/os-release",
    "whoami": "whoami",
    "xray_path": "command -v xray",
    "xray_config_exists": "test -f /usr/local/etc/xray/config.json",
    "xray_active": "systemctl is-active xray",
}

SSH_CHECK_COMMANDS = {
    "os_release": "cat /etc/os-release",
    "uname_arch": "uname -m",
    "whoami": "whoami",
    "systemd_available": "test -d /run/systemd/system",
}


class SSHReadError(Exception):
    def __init__(
        self,
        error_code: str,
        message: str,
        result_data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.result_data = result_data or {}


@dataclass
class CommandResult:
    exit_code: int
    stdout: str
    stderr: str


def host_key_fingerprint(host_key: paramiko.PKey) -> str:
    digest = hashlib.sha256(host_key.asbytes()).digest()
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


def public_key_fingerprint(private_key: paramiko.PKey) -> str:
    digest = hashlib.sha256(private_key.asbytes()).digest()
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{encoded}"


def load_private_key(private_key: str, passphrase: str | None) -> paramiko.PKey:
    encrypted_hint = "ENCRYPTED" in private_key.upper()
    key_errors: list[str] = []
    for key_cls in (
        paramiko.Ed25519Key,
        paramiko.ECDSAKey,
        paramiko.RSAKey,
        paramiko.DSSKey,
    ):
        try:
            return key_cls.from_private_key(io.StringIO(private_key), password=passphrase)
        except paramiko.PasswordRequiredException as exc:
            raise SSHReadError(
                "SSH_KEY_PASSPHRASE_FAILED",
                "SSH Key 需要 Passphrase 或 Passphrase 不正确。",
            ) from exc
        except paramiko.SSHException as exc:
            key_errors.append(str(exc))

    if encrypted_hint or passphrase:
        raise SSHReadError(
            "SSH_KEY_PASSPHRASE_FAILED",
            "SSH Key Passphrase 错误或私钥无法解密。",
        )

    raise SSHReadError("SSH_AUTH_FAILED", "SSH Key 无法解析或认证失败。", {"errors": key_errors[:2]})


def connect_transport(
    vps: VpsServer,
    private_key: str,
    passphrase: str | None,
) -> tuple[paramiko.Transport, str, str]:
    settings = get_settings()
    try:
        sock = socket.create_connection(
            (vps.ip, vps.ssh_port),
            timeout=settings.ssh_connect_timeout_seconds,
        )
        transport = paramiko.Transport(sock)
        transport.start_client(timeout=settings.ssh_connect_timeout_seconds)
    except (socket.timeout, TimeoutError, OSError, paramiko.SSHException) as exc:
        raise SSHReadError("SSH_TIMEOUT", "SSH 连接超时或无法建立连接。") from exc

    host_key = transport.get_remote_server_key()
    fingerprint = host_key_fingerprint(host_key)
    if vps.ssh_host_key_fingerprint and vps.ssh_host_key_fingerprint != fingerprint:
        transport.close()
        raise SSHReadError(
            "SSH_HOST_KEY_CHANGED",
            "检测到 VPS SSH Host Key 发生变化，请确认后再继续。",
            {
                "expected_host_key_fingerprint": vps.ssh_host_key_fingerprint,
                "presented_host_key_fingerprint": fingerprint,
            },
        )

    pkey = load_private_key(private_key, passphrase)
    try:
        transport.auth_publickey(vps.ssh_username, pkey)
    except paramiko.AuthenticationException as exc:
        transport.close()
        raise SSHReadError("SSH_AUTH_FAILED", "SSH Key 认证失败。") from exc
    except paramiko.SSHException as exc:
        transport.close()
        raise SSHReadError("SSH_AUTH_FAILED", "SSH Key 认证失败。") from exc

    if not transport.is_authenticated():
        transport.close()
        raise SSHReadError("SSH_AUTH_FAILED", "SSH Key 认证失败。")

    return transport, fingerprint, public_key_fingerprint(pkey)


def run_read_only_command(transport: paramiko.Transport, command: str) -> CommandResult:
    settings = get_settings()
    deadline = time.monotonic() + settings.ssh_command_timeout_seconds
    channel = transport.open_session(timeout=settings.ssh_command_timeout_seconds)
    channel.settimeout(settings.ssh_command_timeout_seconds)
    channel.exec_command(command)

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []

    try:
        while not channel.exit_status_ready():
            if time.monotonic() > deadline:
                channel.close()
                raise SSHReadError("SSH_TIMEOUT", "SSH 命令执行超时。")
            if channel.recv_ready():
                stdout_chunks.append(channel.recv(4096))
            if channel.recv_stderr_ready():
                stderr_chunks.append(channel.recv_stderr(4096))
            time.sleep(0.05)

        while channel.recv_ready():
            stdout_chunks.append(channel.recv(4096))
        while channel.recv_stderr_ready():
            stderr_chunks.append(channel.recv_stderr(4096))

        exit_code = channel.recv_exit_status()
    finally:
        channel.close()

    return CommandResult(
        exit_code=exit_code,
        stdout=b"".join(stdout_chunks).decode("utf-8", errors="replace").strip(),
        stderr=b"".join(stderr_chunks).decode("utf-8", errors="replace").strip(),
    )


def parse_os_release(content: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in content.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value.strip().strip('"')
    return data


def ensure_supported_os(os_release: dict[str, str]) -> None:
    os_id = os_release.get("ID", "").lower()
    version_id = os_release.get("VERSION_ID", "")
    if os_id == "debian" and version_id.startswith("12"):
        return
    if os_id == "ubuntu" and version_id.startswith("22.04"):
        return
    raise SSHReadError(
        "UNSUPPORTED_OS",
        "第 1 阶段仅支持 Debian 12 / Ubuntu 22.04。",
        {
            "os_id": os_id,
            "version_id": version_id,
        },
    )


def read_vps_state(vps: VpsServer, private_key: str, passphrase: str | None) -> dict[str, Any]:
    transport, host_fingerprint, ssh_key_fingerprint = connect_transport(
        vps,
        private_key,
        passphrase,
    )
    command_results: dict[str, CommandResult] = {}
    try:
        for key, command in READ_ONLY_COMMANDS.items():
            command_results[key] = run_read_only_command(transport, command)
    finally:
        transport.close()

    os_release_result = command_results["os_release"]
    if os_release_result.exit_code != 0:
        raise SSHReadError("UNSUPPORTED_OS", "无法读取系统版本。")

    os_release = parse_os_release(os_release_result.stdout)
    ensure_supported_os(os_release)

    whoami = command_results["whoami"].stdout.strip()
    if whoami != "root":
        raise SSHReadError("NO_ROOT_PERMISSION", "第 1 阶段只支持 root 权限读取。")

    xray_path_result = command_results["xray_path"]
    xray_installed = xray_path_result.exit_code == 0 and bool(xray_path_result.stdout)
    xray_config_exists = command_results["xray_config_exists"].exit_code == 0
    xray_active_result = command_results["xray_active"]
    xray_active = xray_active_result.exit_code == 0 and xray_active_result.stdout == "active"

    if not xray_installed or not xray_config_exists:
        classification = "blank_vps"
        message = "未发现节点，可以新建"
    else:
        classification = "xray_config_present_stage1_readonly"
        message = "检测到标准 Xray 配置路径存在，第 1 阶段只读记录，不接管、不修改。"

    return {
        "classification": classification,
        "message": message,
        "ssh": {
            "username": vps.ssh_username,
            "host_key_fingerprint": host_fingerprint,
            "ssh_key_fingerprint": ssh_key_fingerprint,
        },
        "system": {
            "id": os_release.get("ID"),
            "name": os_release.get("PRETTY_NAME") or os_release.get("NAME"),
            "version_id": os_release.get("VERSION_ID"),
            "whoami": whoami,
            "supported": True,
        },
        "xray": {
            "installed": xray_installed,
            "binary_path": xray_path_result.stdout if xray_installed else None,
            "standard_config_path": "/usr/local/etc/xray/config.json",
            "standard_config_exists": xray_config_exists,
            "service_active": xray_active,
        },
        "read_at": datetime.now(UTC).isoformat(),
    }


def check_vps_ssh_state(vps: VpsServer, private_key: str, passphrase: str | None) -> dict[str, Any]:
    transport, host_fingerprint, ssh_key_fingerprint = connect_transport(
        vps,
        private_key,
        passphrase,
    )
    command_results: dict[str, CommandResult] = {}
    try:
        for key, command in SSH_CHECK_COMMANDS.items():
            command_results[key] = run_read_only_command(transport, command)
    finally:
        transport.close()

    os_release: dict[str, str] = {}
    if command_results["os_release"].exit_code == 0:
        os_release = parse_os_release(command_results["os_release"].stdout)

    return {
        "message": "SSH 握手成功，服务器可通讯。",
        "ssh": {
            "username": vps.ssh_username,
            "host_key_fingerprint": host_fingerprint,
            "ssh_key_fingerprint": ssh_key_fingerprint,
        },
        "system": {
            "id": os_release.get("ID"),
            "name": os_release.get("PRETTY_NAME") or os_release.get("NAME"),
            "version_id": os_release.get("VERSION_ID"),
            "arch": command_results["uname_arch"].stdout.strip() or None,
            "whoami": command_results["whoami"].stdout.strip() or None,
            "systemd_available": command_results["systemd_available"].exit_code == 0,
        },
        "checked_at": datetime.now(UTC).isoformat(),
    }
