import hashlib
import io
import shlex
import tarfile
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from typing import Any, Callable

import paramiko

from app.core.config import get_settings
from app.models.transit_resource import TransitResource
from app.services.task_logging import sanitize_log_text
from app.worker.ssh_install import run_ssh_command
from app.worker.ssh_prepare import parse_listening_ports
from app.worker.ssh_read import (
    CommandResult,
    SSHReadError,
    parse_os_release,
    run_read_only_command,
)
from app.worker.ssh_transit_read import connect_transit_transport

GOST_VERSION = "3.2.6"
GOST_DOWNLOAD_URL = (
    "https://github.com/go-gost/gost/releases/download/v3.2.6/"
    "gost_3.2.6_linux_amd64.tar.gz"
)
GOST_DOWNLOAD_SHA256 = "b39037b0380ea001fb3c0c28441c2e10bfc694f90682739a65b53e55dce5238b"
GOST_INSTALL_PATH = "/usr/local/bin/gost"
SSH_RESERVED_PORT = 20575

INSTALL_PREFLIGHT_COMMANDS = {
    "os_release": "cat /etc/os-release",
    "architecture": "uname -m",
    "whoami": "whoami",
    "systemd_available": "test -d /run/systemd/system",
    "gost_path": "command -v gost",
    "usr_local_bin_exists": "test -d /usr/local/bin",
    "usr_local_bin_writable": "test -w /usr/local/bin",
    "listening_tcp": "ss -ltnH",
}

CommandLogger = Callable[[str, str, str, str | None], None]


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
    gost: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    failures: list[str] | None = None,
    failed_step: str | None = None,
    command_result: CommandResult | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "classification": "install_gost",
        "installed": installed,
        "already_installed": already_installed,
        "message": message,
        "gost": gost
        or {
            "path": GOST_INSTALL_PATH,
            "version": None,
            "download_url": GOST_DOWNLOAD_URL,
            "sha256_verified": False,
        },
        "system": system or {},
        "warnings": warnings or [],
        "failures": failures or [],
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


def download_and_verify_gost() -> bytes:
    request = urllib.request.Request(
        GOST_DOWNLOAD_URL,
        headers={"User-Agent": "LiveLine-Console/Stage-3.3.2"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            archive_bytes = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SSHReadError(
            "GOST_DOWNLOAD_FAILED",
            "下载 gost 官方 release 失败。",
            result_payload(
                installed=False,
                already_installed=False,
                message="下载 gost 官方 release 失败。",
                warnings=[],
                failures=["下载 gost 官方 release 失败"],
                failed_step="download_gost",
            ),
        ) from exc

    digest = hashlib.sha256(archive_bytes).hexdigest()
    if digest != GOST_DOWNLOAD_SHA256:
        raise SSHReadError(
            "GOST_SHA256_MISMATCH",
            "gost release sha256 校验失败。",
            result_payload(
                installed=False,
                already_installed=False,
                message="gost release sha256 校验失败。",
                warnings=[],
                failures=["gost release sha256 校验失败"],
                failed_step="verify_download",
                gost={
                    "path": GOST_INSTALL_PATH,
                    "version": None,
                    "download_url": GOST_DOWNLOAD_URL,
                    "sha256_verified": False,
                },
            ),
        )

    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            for member in archive.getmembers():
                if member.isfile() and member.name.rsplit("/", 1)[-1] == "gost":
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        break
                    return extracted.read()
    except tarfile.TarError as exc:
        raise SSHReadError(
            "GOST_ARCHIVE_INVALID",
            "gost release 压缩包无法解析。",
            result_payload(
                installed=False,
                already_installed=False,
                message="gost release 压缩包无法解析。",
                warnings=[],
                failures=["gost release 压缩包无法解析"],
                failed_step="verify_download",
            ),
        ) from exc

    raise SSHReadError(
        "GOST_BINARY_NOT_FOUND_IN_ARCHIVE",
        "gost release 中未找到 gost binary。",
        result_payload(
            installed=False,
            already_installed=False,
            message="gost release 中未找到 gost binary。",
            warnings=[],
            failures=["gost release 中未找到 gost binary"],
            failed_step="verify_download",
        ),
    )


def upload_temp_binary(transport: paramiko.Transport, binary: bytes) -> str:
    remote_path = f"/tmp/liveline-gost-{uuid.uuid4().hex}"
    sftp = paramiko.SFTPClient.from_transport(transport)
    try:
        with sftp.open(remote_path, "wb") as remote_file:
            remote_file.write(binary)
    finally:
        sftp.close()
    return remote_path


def remove_remote_temp(transport: paramiko.Transport, remote_path: str | None) -> None:
    if not remote_path:
        return
    sftp = paramiko.SFTPClient.from_transport(transport)
    try:
        sftp.remove(remote_path)
    except OSError:
        pass
    finally:
        sftp.close()


def install_gost_state(
    resource: TransitResource,
    private_key: str,
    passphrase: str | None,
    *,
    logger: CommandLogger | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    warnings: list[str] = []
    transport, _, _ = connect_transit_transport(
        resource,
        private_key,
        passphrase,
    )
    remote_temp_path: str | None = None
    try:
        preflight = {
            key: run_read_only_command(transport, command)
            for key, command in INSTALL_PREFLIGHT_COMMANDS.items()
        }
        log_step(logger, level="info", step="preflight", message="gost 安装前检查完成。")

        if preflight["os_release"].exit_code != 0:
            raise command_failure(
                error_code="UNSUPPORTED_OS",
                message="无法读取系统版本。",
                step="preflight",
                warnings=warnings,
                result=preflight["os_release"],
            )

        os_release = parse_os_release(preflight["os_release"].stdout)
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
                message="安装 gost binary 需要 root 用户。",
                step="preflight",
                warnings=warnings,
                system=system_info,
                result=preflight["whoami"],
            )
        if architecture != "x86_64":
            raise command_failure(
                error_code="UNSUPPORTED_ARCHITECTURE",
                message="Stage 3.3.2 仅支持 x86_64 中转服务器。",
                step="preflight",
                warnings=warnings,
                system=system_info,
                result=preflight["architecture"],
            )
        if not systemd_available:
            raise command_failure(
                error_code="SYSTEMD_UNAVAILABLE",
                message="systemd 不可用。",
                step="preflight",
                warnings=warnings,
                system=system_info,
                result=preflight["systemd_available"],
            )
        if preflight["usr_local_bin_exists"].exit_code != 0:
            raise command_failure(
                error_code="GOST_INSTALL_DIR_MISSING",
                message="/usr/local/bin 不存在。",
                step="preflight",
                warnings=warnings,
                system=system_info,
                result=preflight["usr_local_bin_exists"],
            )
        if preflight["usr_local_bin_writable"].exit_code != 0:
            raise command_failure(
                error_code="GOST_INSTALL_DIR_NOT_WRITABLE",
                message="/usr/local/bin 不可写。",
                step="preflight",
                warnings=warnings,
                system=system_info,
                result=preflight["usr_local_bin_writable"],
            )

        existing_path = preflight["gost_path"].stdout.strip()
        log_step(
            logger,
            level="info",
            step="check_existing_gost",
            message="已检查 gost 是否存在。",
            result=preflight["gost_path"],
        )
        if existing_path:
            version_result = run_read_only_command(transport, f"{shlex.quote(existing_path)} -V")
            log_step(
                logger,
                level="info" if version_result.exit_code == 0 else "error",
                step="verify_gost",
                message="已读取现有 gost 版本。" if version_result.exit_code == 0 else "读取现有 gost 版本失败。",
                result=version_result,
            )
            if version_result.exit_code != 0:
                raise command_failure(
                    error_code="GOST_VERSION_FAILED",
                    message="读取现有 gost 版本失败。",
                    step="verify_gost",
                    warnings=warnings,
                    system=system_info,
                    result=version_result,
                )
            return result_payload(
                installed=True,
                already_installed=True,
                message="gost 已安装，已跳过安装。",
                system=system_info,
                gost={
                    "path": existing_path,
                    "version": version_from_result(version_result),
                    "download_url": GOST_DOWNLOAD_URL,
                    "sha256_verified": None,
                },
                warnings=warnings,
                failures=[],
            )

        log_step(logger, level="info", step="download_gost", message="开始下载固定版本 gost release。")
        binary = download_and_verify_gost()
        log_step(logger, level="info", step="verify_download", message="gost release sha256 校验通过。")

        remote_temp_path = upload_temp_binary(transport, binary)
        install_result = run_ssh_command(
            transport,
            f"install -m 0755 {shlex.quote(remote_temp_path)} {GOST_INSTALL_PATH}",
            timeout_seconds=settings.ssh_command_timeout_seconds,
        )
        log_step(
            logger,
            level="info" if install_result.exit_code == 0 else "error",
            step="install_binary",
            message="gost binary 已安装到 /usr/local/bin/gost。"
            if install_result.exit_code == 0
            else "安装 gost binary 失败。",
            result=install_result,
        )
        if install_result.exit_code != 0:
            raise command_failure(
                error_code="GOST_INSTALL_FAILED",
                message="安装 gost binary 失败。",
                step="install_binary",
                warnings=warnings,
                system=system_info,
                result=install_result,
            )

        executable_result = run_read_only_command(transport, f"test -x {GOST_INSTALL_PATH}")
        if executable_result.exit_code != 0:
            log_step(
                logger,
                level="error",
                step="verify_gost",
                message="gost binary 不可执行。",
                result=executable_result,
            )
            raise command_failure(
                error_code="GOST_NOT_EXECUTABLE",
                message="gost binary 不可执行。",
                step="verify_gost",
                warnings=warnings,
                system=system_info,
                result=executable_result,
            )

        version_result = run_read_only_command(transport, f"{GOST_INSTALL_PATH} -V")
        log_step(
            logger,
            level="info" if version_result.exit_code == 0 else "error",
            step="verify_gost",
            message="gost version 检查通过。" if version_result.exit_code == 0 else "gost version 检查失败。",
            result=version_result,
        )
        if version_result.exit_code != 0:
            raise command_failure(
                error_code="GOST_VERSION_FAILED",
                message="gost version 检查失败。",
                step="verify_gost",
                warnings=warnings,
                system=system_info,
                result=version_result,
            )

        return result_payload(
            installed=True,
            already_installed=False,
            message="gost binary 安装完成",
            system=system_info,
            gost={
                "path": GOST_INSTALL_PATH,
                "version": version_from_result(version_result),
                "download_url": GOST_DOWNLOAD_URL,
                "sha256_verified": True,
                "sha256": GOST_DOWNLOAD_SHA256,
            },
            warnings=warnings,
            failures=[],
        )
    finally:
        try:
            remove_remote_temp(transport, remote_temp_path)
        finally:
            transport.close()
