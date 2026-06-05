from datetime import UTC, datetime
from contextlib import suppress
from typing import Any, Callable

from app.models.transit_resource import TransitResource
from app.services.task_logging import sanitize_log_text
from app.worker.ssh_gost_install import SSH_RESERVED_PORT
from app.worker.ssh_install import run_ssh_command
from app.worker.ssh_prepare import parse_listening_ports
from app.worker.ssh_read import CommandResult, SSHReadError, parse_os_release, run_read_only_command
from app.worker.ssh_transit_read import connect_transit_transport

SOCAT_PACKAGE_NAME = "socat"
SOCAT_INSTALL_COMMANDS = {
    "apt_update": "DEBIAN_FRONTEND=noninteractive apt-get update",
    "apt_install": "DEBIAN_FRONTEND=noninteractive apt-get install -y socat",
}
SOCAT_PREFLIGHT_COMMANDS = {
    "os_release": "cat /etc/os-release",
    "architecture": "uname -m",
    "whoami": "whoami",
    "systemd_available": "test -d /run/systemd/system",
    "socat_path": "command -v socat",
    "apt_get_path": "command -v apt-get",
    "listening_tcp": "ss -ltnH",
}
SUPPORTED_PACKAGE_OS = {"debian", "ubuntu"}
WARNING_NO_ROUTE = "本阶段只安装/检查 socat，不创建转发规则"

CommandLogger = Callable[[str, str, str, str | None], None]


def safe_exception_message(exc: Exception) -> str:
    messages: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        text = str(current).strip()
        if text and text not in messages:
            messages.append(text)
        current = current.__cause__ or current.__context__
    return sanitize_log_text(messages[-1] if messages else exc.__class__.__name__) or "SSH 连接失败。"


def compact_command_output(result: CommandResult | None) -> str | None:
    if result is None:
        return None
    parts: list[str] = []
    if result.stdout:
        parts.append("stdout:\n" + result.stdout)
    if result.stderr:
        parts.append("stderr:\n" + result.stderr)
    if not parts:
        parts.append("(no output)")
    return sanitize_log_text("\n\n".join(parts))


def log_step(
    logger: CommandLogger | None,
    *,
    level: str,
    step: str,
    message: str,
    result: CommandResult | None = None,
) -> None:
    if logger is None:
        return
    logger(level, step, message, compact_command_output(result))


def result_payload(
    *,
    installed: bool,
    already_installed: bool,
    message: str,
    system: dict[str, Any] | None = None,
    socat: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    failures: list[str] | None = None,
    failed_step: str | None = None,
    command_result: CommandResult | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "classification": "install_socat",
        "installed": installed,
        "already_installed": already_installed,
        "message": message,
        "socat": socat or {"path": None, "version": None},
        "system": system or {},
        "warnings": warnings or [WARNING_NO_ROUTE],
        "failures": failures or [],
        "checked_at": datetime.now(UTC).isoformat(),
    }
    if failed_step:
        payload["failed_step"] = failed_step
    if command_result is not None:
        payload["command_exit_code"] = command_result.exit_code
        payload["command_output"] = compact_command_output(command_result)
    return payload


def command_failure(
    *,
    error_code: str,
    message: str,
    step: str,
    warnings: list[str],
    system: dict[str, Any] | None = None,
    result: CommandResult | None = None,
) -> SSHReadError:
    return SSHReadError(
        error_code,
        message,
        result_payload(
            installed=False,
            already_installed=False,
            message=message,
            system=system,
            warnings=warnings,
            failures=[message],
            failed_step=step,
            command_result=result,
        ),
    )


def build_system_info(
    *,
    os_release: dict[str, str],
    architecture: str,
    whoami: str,
    systemd_available: bool,
) -> dict[str, Any]:
    return {
        "id": os_release.get("ID"),
        "name": os_release.get("PRETTY_NAME") or os_release.get("NAME"),
        "version_id": os_release.get("VERSION_ID"),
        "architecture": architecture,
        "whoami": whoami,
        "is_root": whoami == "root",
        "systemd_available": systemd_available,
    }


def version_from_result(result: CommandResult) -> str | None:
    output = result.stdout.strip() or result.stderr.strip()
    if not output:
        return None
    return output.splitlines()[0][:200]


def verify_socat(
    transport,
    *,
    path: str,
    logger: CommandLogger | None,
) -> CommandResult:
    version_result = run_read_only_command(transport, f"{path} -V")
    log_step(
        logger,
        level="info" if version_result.exit_code == 0 else "error",
        step="verify_socat",
        message="socat version 检查通过。" if version_result.exit_code == 0 else "socat version 检查失败。",
        result=version_result,
    )
    return version_result


def install_socat_state(
    resource: TransitResource,
    private_key: str,
    passphrase: str | None,
    *,
    logger: CommandLogger | None = None,
) -> dict[str, Any]:
    warnings = [WARNING_NO_ROUTE]
    transport = None
    try:
        try:
            transport, _, _ = connect_transit_transport(resource, private_key, passphrase)
        except SSHReadError as exc:
            message = safe_exception_message(exc)
            raise SSHReadError(
                "SSH_CONNECT_FAILED",
                message,
                result_payload(
                    installed=False,
                    already_installed=False,
                    message=message,
                    warnings=warnings,
                    failures=[message],
                    failed_step="ssh_connect",
                )
                | {
                    "ok": False,
                    "error_code": "SSH_CONNECT_FAILED",
                },
            ) from exc
        except Exception as exc:
            message = safe_exception_message(exc)
            raise SSHReadError(
                "SSH_CONNECT_FAILED",
                message,
                result_payload(
                    installed=False,
                    already_installed=False,
                    message=message,
                    warnings=warnings,
                    failures=[message],
                    failed_step="ssh_connect",
                )
                | {
                    "ok": False,
                    "error_code": "SSH_CONNECT_FAILED",
                },
            ) from exc

        preflight = {
            key: run_read_only_command(transport, command)
            for key, command in SOCAT_PREFLIGHT_COMMANDS.items()
        }
        log_step(logger, level="info", step="preflight", message="socat 安装前检查完成。")

        if preflight["os_release"].exit_code != 0:
            raise command_failure(
                error_code="UNSUPPORTED_OS",
                message="无法读取系统版本。",
                step="preflight",
                warnings=warnings,
                result=preflight["os_release"],
            )

        os_release = parse_os_release(preflight["os_release"].stdout)
        os_id = (os_release.get("ID") or "").lower()
        architecture = preflight["architecture"].stdout.strip()
        whoami = preflight["whoami"].stdout.strip()
        systemd_available = preflight["systemd_available"].exit_code == 0
        system_info = build_system_info(
            os_release=os_release,
            architecture=architecture,
            whoami=whoami,
            systemd_available=systemd_available,
        )

        listening_ports = parse_listening_ports(preflight["listening_tcp"].stdout)
        if resource.ssh_port == SSH_RESERVED_PORT or SSH_RESERVED_PORT in listening_ports:
            warnings.append("20575 当前为 SSH 端口，后续不得作为中转监听端口")

        if whoami != "root":
            raise command_failure(
                error_code="NO_ROOT_PERMISSION",
                message="安装 socat 需要 root 用户。",
                step="preflight",
                warnings=warnings,
                system=system_info,
                result=preflight["whoami"],
            )
        if os_id not in SUPPORTED_PACKAGE_OS:
            raise command_failure(
                error_code="UNSUPPORTED_OS",
                message="Stage 3.3.3-fix-a 仅支持 Debian / Ubuntu 使用 apt-get 安装 socat。",
                step="preflight",
                warnings=warnings,
                system=system_info,
                result=preflight["os_release"],
            )
        if preflight["apt_get_path"].exit_code != 0:
            raise command_failure(
                error_code="APT_GET_NOT_FOUND",
                message="未检测到 apt-get，不能安装 socat。",
                step="preflight",
                warnings=warnings,
                system=system_info,
                result=preflight["apt_get_path"],
            )

        existing_path = preflight["socat_path"].stdout.strip()
        log_step(
            logger,
            level="info",
            step="check_existing_socat",
            message="已检查 socat 是否存在。",
            result=preflight["socat_path"],
        )
        if existing_path:
            version_result = verify_socat(transport, path=existing_path, logger=logger)
            if version_result.exit_code != 0:
                raise command_failure(
                    error_code="SOCAT_VERSION_FAILED",
                    message="读取现有 socat 版本失败。",
                    step="verify_socat",
                    warnings=warnings,
                    system=system_info,
                    result=version_result,
                )
            return result_payload(
                installed=True,
                already_installed=True,
                message="socat 已安装，已跳过安装。",
                system=system_info,
                socat={
                    "path": existing_path,
                    "version": version_from_result(version_result),
                },
                warnings=warnings,
                failures=[],
            )

        update_result = run_ssh_command(
            transport,
            SOCAT_INSTALL_COMMANDS["apt_update"],
            timeout_seconds=120,
        )
        log_step(
            logger,
            level="info" if update_result.exit_code == 0 else "error",
            step="install_package",
            message="apt-get update 完成。" if update_result.exit_code == 0 else "apt-get update 失败。",
            result=update_result,
        )
        if update_result.exit_code != 0:
            raise command_failure(
                error_code="APT_UPDATE_FAILED",
                message="apt-get update 失败。",
                step="install_package",
                warnings=warnings,
                system=system_info,
                result=update_result,
            )

        install_result = run_ssh_command(
            transport,
            SOCAT_INSTALL_COMMANDS["apt_install"],
            timeout_seconds=120,
        )
        log_step(
            logger,
            level="info" if install_result.exit_code == 0 else "error",
            step="install_package",
            message="socat package 安装完成。" if install_result.exit_code == 0 else "socat package 安装失败。",
            result=install_result,
        )
        if install_result.exit_code != 0:
            raise command_failure(
                error_code="SOCAT_INSTALL_FAILED",
                message="socat package 安装失败。",
                step="install_package",
                warnings=warnings,
                system=system_info,
                result=install_result,
            )

        installed_path_result = run_read_only_command(transport, "command -v socat")
        installed_path = installed_path_result.stdout.strip()
        if installed_path_result.exit_code != 0 or not installed_path:
            raise command_failure(
                error_code="SOCAT_NOT_FOUND_AFTER_INSTALL",
                message="安装后未检测到 socat。",
                step="verify_socat",
                warnings=warnings,
                system=system_info,
                result=installed_path_result,
            )
        version_result = verify_socat(transport, path=installed_path, logger=logger)
        if version_result.exit_code != 0:
            raise command_failure(
                error_code="SOCAT_VERSION_FAILED",
                message="socat version 检查失败。",
                step="verify_socat",
                warnings=warnings,
                system=system_info,
                result=version_result,
            )

        return result_payload(
            installed=True,
            already_installed=False,
            message="socat 安装完成",
            system=system_info,
            socat={
                "path": installed_path,
                "version": version_from_result(version_result),
            },
            warnings=warnings,
            failures=[],
        )
    finally:
        if transport is not None:
            with suppress(Exception):
                transport.close()
