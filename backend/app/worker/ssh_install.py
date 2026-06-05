import time
from datetime import UTC, datetime
from typing import Any, Callable

import paramiko

from app.core.config import get_settings
from app.models.vps_server import VpsServer
from app.services.task_logging import sanitize_log_text
from app.worker.ssh_read import (
    CommandResult,
    SSHReadError,
    connect_transport,
    ensure_supported_os,
    parse_os_release,
    run_read_only_command,
)

XRAY_INSTALL_SCRIPT_URL = "https://github.com/XTLS/Xray-install/raw/main/install-release.sh"
XRAY_CONFIG_DIR = "/usr/local/etc/xray"
XRAY_CONFIG_PATH = "/usr/local/etc/xray/config.json"
XRAY_INSTALL_COMMAND = (
    'bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" '
    "@ install"
)

PRE_INSTALL_CHECKS = {
    "os_release": "cat /etc/os-release",
    "whoami": "whoami",
    "systemd_available": "test -d /run/systemd/system",
    "xray_path": "command -v xray",
    "xray_service_exists": "systemctl list-unit-files xray.service --no-pager --no-legend",
    "xray_config_dir_exists": f"test -d {XRAY_CONFIG_DIR}",
    "xray_config_exists": f"test -e {XRAY_CONFIG_PATH}",
}

POST_INSTALL_CHECKS = {
    "xray_path": "command -v xray",
    "xray_version": "xray version",
    "xray_service_exists": "systemctl list-unit-files xray.service --no-pager --no-legend",
    "xray_enabled": "systemctl is-enabled xray",
    "xray_active": "systemctl is-active xray",
    "xray_status": "systemctl status xray --no-pager",
    "xray_config_dir_exists": f"test -d {XRAY_CONFIG_DIR}",
    "xray_config_exists": f"test -f {XRAY_CONFIG_PATH}",
}

CommandLogger = Callable[[str, str, str, str | None], None]


def append_warning_once(warnings: list[str], message: str) -> None:
    if message not in warnings:
        warnings.append(message)


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


def command_failed_result(
    *,
    step: str,
    message: str,
    result: CommandResult | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "classification": "install_xray",
        "installed": False,
        "message": message,
        "warnings": warnings or [],
        "failures": [message],
        "failed_step": step,
    }
    if result is not None:
        payload["command_exit_code"] = result.exit_code
        payload["command_output"] = compact_command_output(result)
    return payload


def log_result(
    logger: CommandLogger | None,
    *,
    step: str,
    message: str,
    result: CommandResult,
    level: str = "info",
) -> None:
    if logger is None:
        return
    logger(level, step, message, compact_command_output(result))


def run_install_step(
    transport: paramiko.Transport,
    *,
    step: str,
    command: str,
    timeout_seconds: int,
    logger: CommandLogger | None,
    success_message: str,
    error_code: str,
    error_message: str,
    warnings: list[str],
) -> CommandResult:
    result = run_ssh_command(transport, command, timeout_seconds=timeout_seconds)
    if result.exit_code != 0:
        log_result(logger, step=step, message=error_message, result=result, level="error")
        raise SSHReadError(
            error_code,
            error_message,
            command_failed_result(
                step=step,
                message=error_message,
                result=result,
                warnings=warnings,
            ),
        )
    log_result(logger, step=step, message=success_message, result=result)
    return result


def preflight_install_state(
    transport: paramiko.Transport,
    warnings: list[str],
) -> dict[str, CommandResult]:
    results = {
        key: run_read_only_command(transport, command)
        for key, command in PRE_INSTALL_CHECKS.items()
    }

    if results["os_release"].exit_code != 0:
        raise SSHReadError(
            "UNSUPPORTED_OS",
            "无法读取系统版本。",
            command_failed_result(
                step="preflight",
                message="无法读取系统版本。",
                result=results["os_release"],
                warnings=warnings,
            ),
        )

    os_release = parse_os_release(results["os_release"].stdout)
    try:
        ensure_supported_os(os_release)
    except SSHReadError as exc:
        exc.result_data = command_failed_result(
            step="preflight",
            message=exc.message,
            warnings=warnings,
        )
        raise

    if results["whoami"].stdout.strip() != "root":
        raise SSHReadError(
            "NO_ROOT_PERMISSION",
            "安装 Xray 需要 root 用户。",
            command_failed_result(
                step="preflight",
                message="安装 Xray 需要 root 用户。",
                result=results["whoami"],
                warnings=warnings,
            ),
        )

    if results["systemd_available"].exit_code != 0:
        raise SSHReadError(
            "SYSTEMD_UNAVAILABLE",
            "systemd 不可用，不能安装并启动 xray.service。",
            command_failed_result(
                step="preflight",
                message="systemd 不可用，不能安装并启动 xray.service。",
                result=results["systemd_available"],
                warnings=warnings,
            ),
        )

    return results


def install_xray_state(
    vps: VpsServer,
    private_key: str,
    passphrase: str | None,
    *,
    warnings: list[str] | None = None,
    logger: CommandLogger | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    install_warnings = warnings or []
    transport, host_fingerprint, ssh_key_fingerprint = connect_transport(
        vps,
        private_key,
        passphrase,
    )
    already_installed = False
    try:
        preflight = preflight_install_state(transport, install_warnings)
        already_installed = (
            preflight["xray_path"].exit_code == 0 and bool(preflight["xray_path"].stdout.strip())
        )

        if already_installed:
            if logger is not None:
                logger(
                    "info",
                    "install_xray",
                    "检测到 Xray 已安装，跳过官方安装脚本。",
                    preflight["xray_path"].stdout,
                )
        else:
            run_install_step(
                transport,
                step="install_xray",
                command=XRAY_INSTALL_COMMAND,
                timeout_seconds=settings.ssh_install_timeout_seconds,
                logger=logger,
                success_message="官方 Xray 安装脚本执行完成。",
                error_code="XRAY_INSTALL_FAILED",
                error_message="Xray 官方安装脚本执行失败。",
                warnings=install_warnings,
            )
        run_install_step(
            transport,
            step="enable_service",
            command="systemctl enable xray",
            timeout_seconds=settings.ssh_command_timeout_seconds,
            logger=logger,
            success_message="xray.service 已启用。",
            error_code="XRAY_SERVICE_ENABLE_FAILED",
            error_message="启用 xray.service 失败。",
            warnings=install_warnings,
        )

        checks = {
            key: run_read_only_command(transport, command)
            for key, command in POST_INSTALL_CHECKS.items()
        }
        config_exists_before_start = checks["xray_config_exists"].exit_code == 0
        if config_exists_before_start:
            start_result = run_ssh_command(
                transport,
                "systemctl start xray",
                timeout_seconds=settings.ssh_command_timeout_seconds,
            )
            if start_result.exit_code == 0:
                log_result(
                    logger,
                    step="start_service",
                    message="xray.service 启动命令已执行。",
                    result=start_result,
                )
            else:
                append_warning_once(
                    install_warnings,
                    "xray.service 当前未运行，等待 Stage 2.3 写入配置后启动",
                )
                log_result(
                    logger,
                    step="start_service",
                    message="xray.service 启动失败，等待 Stage 2.3 写入配置后启动。",
                    result=start_result,
                    level="warning",
                )
        else:
            append_warning_once(
                install_warnings,
                "标准 Xray 配置文件不存在，等待 Stage 2.3 创建业务配置",
            )
            append_warning_once(
                install_warnings,
                "xray.service 当前未运行，等待 Stage 2.3 写入配置后启动",
            )
            if logger is not None:
                logger(
                    "warning",
                    "start_service",
                    "未发现标准 Xray 配置文件，跳过启动，等待 Stage 2.3 写入配置。",
                    None,
                )

        checks = {
            key: run_read_only_command(transport, command)
            for key, command in POST_INSTALL_CHECKS.items()
        }
    finally:
        transport.close()

    failures: list[str] = []
    binary_path = checks["xray_path"].stdout.strip()
    service_exists = checks["xray_service_exists"].exit_code == 0 and bool(
        checks["xray_service_exists"].stdout.strip()
    )
    service_active = (
        checks["xray_active"].exit_code == 0 and checks["xray_active"].stdout.strip() == "active"
    )
    service_enabled = (
        checks["xray_enabled"].exit_code == 0
        and checks["xray_enabled"].stdout.strip() == "enabled"
    )
    config_dir_exists = checks["xray_config_dir_exists"].exit_code == 0
    config_exists = checks["xray_config_exists"].exit_code == 0

    if not binary_path:
        failures.append("安装后未找到 xray binary")
    if checks["xray_version"].exit_code != 0:
        failures.append("xray version 执行失败")
    if not service_exists:
        failures.append("xray.service 不存在")
    if not service_enabled:
        failures.append("xray.service 未 enabled")
    if not config_dir_exists:
        append_warning_once(install_warnings, "标准 Xray 配置目录不存在")
    if not config_exists:
        append_warning_once(
            install_warnings,
            "标准 Xray 配置文件不存在，等待 Stage 2.3 创建业务配置",
        )
    if not service_active:
        append_warning_once(
            install_warnings,
            "xray.service 当前未运行，等待 Stage 2.3 写入配置后启动",
        )

    installed = not failures
    message = "Xray 已安装，等待创建节点配置" if installed else "Xray 安装后验证失败"

    result = {
        "classification": "install_xray",
        "installed": installed,
        "already_installed": already_installed,
        "message": message,
        "xray": {
            "binary_path": binary_path or None,
            "version": checks["xray_version"].stdout if checks["xray_version"].exit_code == 0 else None,
            "service_exists": service_exists,
            "service_enabled": service_enabled,
            "service_active": service_active,
            "service_status": checks["xray_status"].stdout.splitlines()[:14],
            "config_dir": XRAY_CONFIG_DIR,
            "config_dir_exists": config_dir_exists,
            "config_path": XRAY_CONFIG_PATH,
            "config_exists": config_exists,
        },
        "ssh": {
            "username": vps.ssh_username,
            "host_key_fingerprint": host_fingerprint,
            "ssh_key_fingerprint": ssh_key_fingerprint,
        },
        "warnings": install_warnings,
        "failures": failures,
        "installed_at": datetime.now(UTC).isoformat(),
    }

    if failures:
        raise SSHReadError("XRAY_INSTALL_VERIFY_FAILED", message, result)

    return result
