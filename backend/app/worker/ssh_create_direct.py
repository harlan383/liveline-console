import json
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import quote, urlencode

import paramiko

from app.core.config import get_settings
from app.models.vps_server import VpsServer
from app.services.task_logging import sanitize_log_text
from app.worker.ssh_install import XRAY_CONFIG_PATH
from app.worker.ssh_prepare import parse_listening_ports
from app.worker.ssh_read import CommandResult, SSHReadError, connect_transport, run_read_only_command

DEFAULT_FLOW = "xtls-rprx-vision"
DEFAULT_FINGERPRINT = "chrome"
CREATE_DIRECT_CHECKS = {
    "xray_path": "command -v xray",
    "xray_version": "xray version",
    "xray_service_exists": "systemctl list-unit-files xray.service --no-pager --no-legend",
    "config_exists": f"test -e {XRAY_CONFIG_PATH}",
    "listening_tcp": "ss -ltnH",
}

CommandLogger = Callable[[str, str, str, str | None], None]


@dataclass
class DirectNodeParams:
    node_name: str
    listen_port: int
    reality_dest: str
    reality_server_name: str
    reality_short_id: str
    client_uuid: str
    flow: str


def compact_command_output(result: CommandResult) -> str:
    parts: list[str] = []
    if result.stdout:
        parts.append("stdout:\n" + result.stdout)
    if result.stderr:
        parts.append("stderr:\n" + result.stderr)
    if not parts:
        parts.append("(no output)")
    return sanitize_log_text("\n\n".join(parts)) or ""


def run_ssh_command(
    transport: paramiko.Transport,
    command: str,
    *,
    timeout_seconds: int,
) -> CommandResult:
    deadline = time.monotonic() + timeout_seconds
    channel = transport.open_session(timeout=timeout_seconds)
    channel.settimeout(timeout_seconds)
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


def log_command_result(
    logger: CommandLogger | None,
    *,
    level: str,
    step: str,
    message: str,
    result: CommandResult | None = None,
) -> None:
    if logger is None:
        return
    logger(level, step, message, compact_command_output(result) if result else None)


def fail_result(
    *,
    message: str,
    failures: list[str],
    warnings: list[str] | None = None,
    step: str | None = None,
    command_result: CommandResult | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "classification": "create_direct_node",
        "created": False,
        "message": message,
        "warnings": warnings or [],
        "failures": failures,
    }
    if step:
        result["failed_step"] = step
    if command_result is not None:
        result["command_exit_code"] = command_result.exit_code
        result["command_output"] = compact_command_output(command_result)
    return result


def config_exists_fail_result() -> dict[str, Any]:
    return {
        "classification": "create_direct_node",
        "created": False,
        "message": "检测到已有 Xray 配置文件，已拒绝覆盖",
        "failures": [
            "标准 config.json 已存在，为避免覆盖现有配置，本次未创建节点",
        ],
        "xray": {
            "config_path": XRAY_CONFIG_PATH,
            "config_exists": True,
        },
        "warnings": [],
    }


def parse_x25519(output: str) -> tuple[str, str]:
    private_match = re.search(r"private\s*key\s*:\s*(\S+)", output, re.IGNORECASE)
    public_match = re.search(r"public\s*key\)?\s*:\s*(\S+)", output, re.IGNORECASE)
    if not private_match or not public_match:
        raise SSHReadError(
            "XRAY_X25519_PARSE_FAILED",
            "无法解析 xray x25519 输出。",
            fail_result(
                message="无法解析 xray x25519 输出。",
                failures=["无法解析 Reality 密钥输出"],
                step="generate_reality_keys",
            ),
        )
    return private_match.group(1), public_match.group(1)


def build_xray_config(params: DirectNodeParams, reality_private_key: str) -> str:
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "direct-vless-reality",
                "listen": "0.0.0.0",
                "port": params.listen_port,
                "protocol": "vless",
                "settings": {
                    "clients": [
                        {
                            "id": params.client_uuid,
                            "flow": params.flow,
                        }
                    ],
                    "decryption": "none",
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": params.reality_dest,
                        "xver": 0,
                        "serverNames": [params.reality_server_name],
                        "privateKey": reality_private_key,
                        "shortIds": [params.reality_short_id],
                    },
                },
                "sniffing": {
                    "enabled": True,
                    "destOverride": ["http", "tls", "quic"],
                },
            }
        ],
        "outbounds": [
            {
                "tag": "direct",
                "protocol": "freedom",
            }
        ],
    }
    return json.dumps(config, ensure_ascii=False, indent=2)


def build_share_link(
    *,
    vps_ip: str,
    params: DirectNodeParams,
    reality_public_key: str,
) -> str:
    query = urlencode(
        {
            "type": "tcp",
            "security": "reality",
            "encryption": "none",
            "flow": params.flow,
            "sni": params.reality_server_name,
            "fp": DEFAULT_FINGERPRINT,
            "pbk": reality_public_key,
            "sid": params.reality_short_id,
        }
    )
    name = quote(params.node_name, safe="")
    return f"vless://{params.client_uuid}@{vps_ip}:{params.listen_port}?{query}#{name}"


def write_remote_config(transport: paramiko.Transport, config_text: str) -> None:
    sftp = paramiko.SFTPClient.from_transport(transport)
    try:
        with sftp.open(XRAY_CONFIG_PATH, "w") as remote_file:
            remote_file.write(config_text)
    finally:
        sftp.close()


def create_direct_node_state(
    vps: VpsServer,
    private_key: str,
    passphrase: str | None,
    params: DirectNodeParams,
    *,
    logger: CommandLogger | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    warnings: list[str] = []
    transport, _, _ = connect_transport(vps, private_key, passphrase)
    reality_private_key = ""
    try:
        checks = {
            key: run_read_only_command(transport, command)
            for key, command in CREATE_DIRECT_CHECKS.items()
        }

        binary_path = checks["xray_path"].stdout.strip()
        service_exists = checks["xray_service_exists"].exit_code == 0 and bool(
            checks["xray_service_exists"].stdout.strip()
        )
        occupied_ports = parse_listening_ports(checks["listening_tcp"].stdout)

        if not binary_path:
            raise SSHReadError(
                "XRAY_BINARY_NOT_FOUND",
                "未找到 Xray binary。",
                fail_result(
                    message="未找到 Xray binary。",
                    failures=["未找到 Xray binary"],
                    step="post_install_check",
                    command_result=checks["xray_path"],
                ),
            )
        if checks["xray_version"].exit_code != 0:
            raise SSHReadError(
                "XRAY_VERSION_FAILED",
                "xray version 执行失败。",
                fail_result(
                    message="xray version 执行失败。",
                    failures=["xray version 执行失败"],
                    step="post_install_check",
                    command_result=checks["xray_version"],
                ),
            )
        if not service_exists:
            raise SSHReadError(
                "XRAY_SERVICE_NOT_FOUND",
                "xray.service 不存在。",
                fail_result(
                    message="xray.service 不存在。",
                    failures=["xray.service 不存在"],
                    step="post_install_check",
                    command_result=checks["xray_service_exists"],
                ),
            )
        if checks["config_exists"].exit_code == 0:
            raise SSHReadError(
                "XRAY_CONFIG_ALREADY_EXISTS",
                "检测到已有 Xray 配置文件，已拒绝覆盖。",
                config_exists_fail_result(),
            )
        if params.listen_port in occupied_ports:
            raise SSHReadError(
                "PORT_IN_USE",
                "监听端口已被占用，未写入配置。",
                fail_result(
                    message="监听端口已被占用，未写入配置。",
                    failures=[f"端口 {params.listen_port} 已被占用"],
                    step="check_port",
                    command_result=checks["listening_tcp"],
                ),
            )

        log_command_result(
            logger,
            level="info",
            step="post_install_check",
            message="Xray 安装状态与端口占用检查通过。",
        )

        x25519_result = run_ssh_command(
            transport,
            "xray x25519",
            timeout_seconds=settings.ssh_command_timeout_seconds,
        )
        if x25519_result.exit_code != 0:
            raise SSHReadError(
                "XRAY_X25519_FAILED",
                "生成 Reality 密钥失败。",
                fail_result(
                    message="生成 Reality 密钥失败。",
                    failures=["xray x25519 执行失败"],
                    step="generate_reality_keys",
                    command_result=x25519_result,
                ),
            )
        reality_private_key, reality_public_key = parse_x25519(x25519_result.stdout)
        log_command_result(
            logger,
            level="info",
            step="generate_reality_keys",
            message="Reality 公私钥已生成，私钥不会写入日志或数据库。",
        )

        config_text = build_xray_config(params, reality_private_key)
        try:
            write_remote_config(transport, config_text)
        except OSError as exc:
            raise SSHReadError(
                "XRAY_CONFIG_WRITE_FAILED",
                "写入 Xray 配置失败。",
                fail_result(
                    message="写入 Xray 配置失败。",
                    failures=[str(exc)],
                    step="write_config",
                ),
            ) from exc
        finally:
            reality_private_key = ""
            config_text = ""

        log_command_result(
            logger,
            level="info",
            step="write_config",
            message="Xray 配置已写入标准路径。",
        )

        test_result = run_ssh_command(
            transport,
            f"xray run -test -config {XRAY_CONFIG_PATH}",
            timeout_seconds=settings.ssh_command_timeout_seconds,
        )
        if test_result.exit_code != 0:
            raise SSHReadError(
                "XRAY_CONFIG_TEST_FAILED",
                "xray test 未通过，未重启服务。",
                fail_result(
                    message="xray test 未通过，未重启服务。",
                    failures=["xray test 未通过"],
                    step="test_config",
                    command_result=test_result,
                ),
            )
        log_command_result(
            logger,
            level="info",
            step="test_config",
            message="xray test 通过。",
            result=test_result,
        )

        restart_result = run_ssh_command(
            transport,
            "systemctl restart xray",
            timeout_seconds=settings.ssh_command_timeout_seconds,
        )
        if restart_result.exit_code != 0:
            raise SSHReadError(
                "XRAY_SERVICE_RESTART_FAILED",
                "重启 xray.service 失败。",
                fail_result(
                    message="重启 xray.service 失败。",
                    failures=["重启 xray.service 失败"],
                    step="restart_service",
                    command_result=restart_result,
                ),
            )
        log_command_result(
            logger,
            level="info",
            step="restart_service",
            message="xray.service 已重启。",
            result=restart_result,
        )

        active_result = run_read_only_command(transport, "systemctl is-active xray")
        listening_result = run_read_only_command(transport, "ss -ltnH")
        listening_ports = parse_listening_ports(listening_result.stdout)
        service_active = active_result.exit_code == 0 and active_result.stdout.strip() == "active"
        listening = params.listen_port in listening_ports

        if not service_active:
            raise SSHReadError(
                "XRAY_SERVICE_INACTIVE",
                "xray.service 未处于 active 状态。",
                fail_result(
                    message="xray.service 未处于 active 状态。",
                    failures=["xray.service 未处于 active 状态"],
                    step="verify_service",
                    command_result=active_result,
                ),
            )
        if not listening:
            raise SSHReadError(
                "XRAY_PORT_NOT_LISTENING",
                "Xray 未监听指定端口。",
                fail_result(
                    message="Xray 未监听指定端口。",
                    failures=[f"端口 {params.listen_port} 未监听"],
                    step="verify_listening",
                    command_result=listening_result,
                ),
            )

        share_link = build_share_link(
            vps_ip=vps.ip,
            params=params,
            reality_public_key=reality_public_key,
        )

        return {
            "classification": "create_direct_node",
            "created": True,
            "message": "直连 VLESS Reality 节点创建成功",
            "node": {
                "name": params.node_name,
                "protocol": "vless",
                "port": params.listen_port,
                "uuid": params.client_uuid,
                "flow": params.flow,
                "reality_server_name": params.reality_server_name,
                "reality_dest": params.reality_dest,
                "reality_public_key": reality_public_key,
                "reality_short_id": params.reality_short_id,
                "fingerprint": DEFAULT_FINGERPRINT,
                "share_link": share_link,
            },
            "xray": {
                "binary_path": binary_path,
                "version": checks["xray_version"].stdout,
                "config_path": XRAY_CONFIG_PATH,
                "config_test_passed": True,
                "service_active": service_active,
                "listening": listening,
            },
            "warnings": warnings,
            "failures": [],
            "created_at": datetime.now(UTC).isoformat(),
        }
    finally:
        reality_private_key = ""
        transport.close()


def build_direct_node_params(
    *,
    node_name: str,
    listen_port: int,
    reality_dest: str,
    reality_server_name: str,
    reality_short_id: str | None = None,
    client_uuid: str | None = None,
    flow: str = DEFAULT_FLOW,
) -> DirectNodeParams:
    return DirectNodeParams(
        node_name=node_name,
        listen_port=listen_port,
        reality_dest=reality_dest,
        reality_server_name=reality_server_name,
        reality_short_id=reality_short_id or secrets.token_hex(8),
        client_uuid=client_uuid or str(uuid.uuid4()),
        flow=flow,
    )
