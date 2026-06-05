import re
from datetime import UTC, datetime
from typing import Any, Callable

import paramiko

from app.models.vps_server import VpsServer
from app.worker.ssh_install import XRAY_CONFIG_PATH
from app.worker.ssh_prepare import parse_listening_ports
from app.worker.ssh_read import CommandResult, SSHReadError, connect_transport, run_read_only_command

XRAY_CONFIG_DIR = "/usr/local/etc/xray"
FAILED_BACKUP_FILENAME_RE = re.compile(r"^config\.json\.failed\.\d{14}$")
LIST_BACKUPS_COMMAND = (
    "find /usr/local/etc/xray -maxdepth 1 -type f -name 'config.json*' "
    "-printf '%f\\t%p\\t%s\\t%T@\\n'"
)
PREVIEW_CLEANUP_COMMAND = (
    "find /usr/local/etc/xray -maxdepth 1 -type f -name 'config.json*' "
    "-printf '%f|%p|%s|%T@\\n'"
)

BACKUP_SCAN_COMMANDS = {
    "config_dir_exists": f"test -d {XRAY_CONFIG_DIR}",
    "config_exists": f"test -e {XRAY_CONFIG_PATH}",
    "backup_files": LIST_BACKUPS_COMMAND,
    "cleanup_preview_files": PREVIEW_CLEANUP_COMMAND,
    "xray_active": "systemctl is-active xray",
    "listening_tcp": "ss -ltnH",
}

CommandLogger = Callable[[str, str, str], None]


def is_valid_failed_backup_filename(filename: str) -> bool:
    return bool(FAILED_BACKUP_FILENAME_RE.fullmatch(filename))


def backup_path_for_filename(filename: str) -> str:
    return f"{XRAY_CONFIG_DIR}/{filename}"


def validate_delete_candidate_request(filename: str, confirm: bool, confirm_filename: str) -> None:
    if not filename:
        raise SSHReadError(
            "VALIDATION_FAILED",
            "filename 不能为空。",
            delete_candidate_failure_result("validation_failed", "filename 不能为空。"),
        )
    if confirm is not True:
        raise SSHReadError(
            "VALIDATION_FAILED",
            "必须确认删除操作。",
            delete_candidate_failure_result("validation_failed", "必须确认删除操作。"),
        )
    if confirm_filename != filename:
        raise SSHReadError(
            "FILENAME_MISMATCH",
            "confirm_filename 与 filename 不一致。",
            delete_candidate_failure_result(
                "filename_mismatch",
                "confirm_filename 与 filename 不一致。",
                filename=filename,
            ),
        )
    if (
        "/" in filename
        or ".." in filename
        or any(char.isspace() for char in filename)
        or not is_valid_failed_backup_filename(filename)
    ):
        raise SSHReadError(
            "INVALID_FILENAME",
            "文件名不符合允许删除的 failed 备份格式。",
            delete_candidate_failure_result(
                "invalid_filename",
                "文件名不符合允许删除的 failed 备份格式。",
                filename=filename,
            ),
        )


def delete_candidate_failure_result(
    reason: str,
    message: str,
    *,
    filename: str | None = None,
    warnings: list[str] | None = None,
    failures: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "classification": "delete_xray_backup_candidate",
        "deleted": False,
        "message": message,
        "reason": reason,
        "file": {"name": filename} if filename else None,
        "verify": {
            "file_exists_after_delete": None,
            "remaining_file_count": None,
        },
        "warnings": warnings or [],
        "failures": failures or [reason],
    }


def backup_file_type(name: str) -> str:
    if name == "config.json":
        return "current"
    if name.startswith("config.json.bak."):
        return "backup"
    if name.startswith("config.json.disabled."):
        return "disabled"
    if name.startswith("config.json.failed."):
        return "failed"
    return "unknown"


def parse_modified_time(value: str) -> str | None:
    try:
        timestamp = float(value)
    except ValueError:
        return None
    return datetime.fromtimestamp(timestamp, UTC).isoformat()


def parse_backup_files(output: str) -> list[dict[str, Any]]:
    files: list[dict[str, Any]] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        delimiter = "\t" if "\t" in line else "|"
        parts = line.split(delimiter)
        if len(parts) != 4:
            continue
        name, path, size_text, modified_text = parts
        try:
            size_bytes = int(size_text)
        except ValueError:
            size_bytes = None
        files.append(
            {
                "name": name,
                "path": path,
                "type": backup_file_type(name),
                "size_bytes": size_bytes,
                "modified_at": parse_modified_time(modified_text),
            }
        )
    return sorted(files, key=lambda item: (item["type"], item["name"]))


def risk_level(file_type: str) -> str:
    if file_type == "failed":
        return "low"
    if file_type == "disabled":
        return "medium"
    if file_type == "backup":
        return "high"
    return "protected"


def retained_reason(file_type: str) -> str:
    if file_type == "current":
        return "current_config"
    if file_type == "unknown":
        return "unknown_type"
    return "within_keep_latest_3"


def with_cleanup_reason(file: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        **file,
        "reason": reason,
        "risk_level": risk_level(str(file.get("type") or "unknown")),
    }


def preview_cleanup(files: list[dict[str, Any]], keep_latest_per_type: int = 3) -> dict[str, Any]:
    retained_files: list[dict[str, Any]] = []
    candidate_files: list[dict[str, Any]] = []
    cleanable_types = ("backup", "disabled", "failed")

    for file in files:
        file_type = str(file.get("type") or "unknown")
        if file_type not in cleanable_types:
            retained_files.append(with_cleanup_reason(file, retained_reason(file_type)))

    for file_type in cleanable_types:
        typed_files = [file for file in files if file.get("type") == file_type]
        typed_files.sort(key=lambda item: str(item.get("modified_at") or ""), reverse=True)
        for index, file in enumerate(typed_files):
            if index < keep_latest_per_type:
                retained_files.append(with_cleanup_reason(file, "within_keep_latest_3"))
            else:
                candidate_files.append(with_cleanup_reason(file, "older_than_keep_latest_3"))

    retained_files.sort(key=lambda item: (str(item.get("type")), str(item.get("name"))))
    candidate_files.sort(key=lambda item: (str(item.get("type")), str(item.get("name"))))
    candidate_size = sum(
        item["size_bytes"] for item in candidate_files if isinstance(item.get("size_bytes"), int)
    )
    total_size = sum(item["size_bytes"] for item in files if isinstance(item.get("size_bytes"), int))

    return {
        "summary": {
            "total_files": len(files),
            "total_size_bytes": total_size,
            "candidate_count": len(candidate_files),
            "candidate_size_bytes": candidate_size,
            "estimated_reclaim_bytes": candidate_size,
            "retained_count": len(retained_files),
        },
        "candidate_files": candidate_files,
        "retained_files": retained_files,
    }


def find_file_by_name(files: list[dict[str, Any]], filename: str) -> dict[str, Any] | None:
    for file in files:
        if file.get("name") == filename:
            return file
    return None


def scan_cleanup_preview(
    transport: paramiko.Transport,
    *,
    logger: CommandLogger | None = None,
    log_status_checks: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any], CommandResult, CommandResult]:
    if logger:
        logger("info", "scan_backup_files", "扫描 Xray 配置备份文件元数据。")
    files_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["cleanup_preview_files"])
    if files_result.exit_code != 0:
        raise SSHReadError(
            "XRAY_BACKUP_SCAN_FAILED",
            "读取 Xray 备份文件列表失败。",
            delete_candidate_failure_result(
                "validation_failed",
                "读取 Xray 备份文件列表失败。",
            ),
        )

    files = parse_backup_files(files_result.stdout)
    if logger:
        logger("info", "calculate_cleanup_candidates", "计算备份清理候选文件。")
    preview = preview_cleanup(files)
    if logger and log_status_checks:
        logger("info", "check_service", "检查 xray.service 当前状态。")
    service_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["xray_active"])
    if logger and log_status_checks:
        logger("info", "check_port", "检查 443 端口监听状态。")
    ports_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["listening_tcp"])
    return files, preview, service_result, ports_result


def list_xray_backups_state(
    vps: VpsServer,
    private_key: str,
    passphrase: str | None,
    *,
    logger: CommandLogger | None = None,
) -> dict[str, Any]:
    transport, _, _ = connect_transport(vps, private_key, passphrase)
    try:
        if logger:
            logger("info", "check_config_dir", "检查 Xray 配置目录是否存在。")
        dir_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["config_dir_exists"])
        if dir_result.exit_code != 0:
            raise SSHReadError(
                "XRAY_CONFIG_DIR_NOT_FOUND",
                "Xray 配置目录不存在。",
                {
                    "classification": "list_xray_backups",
                    "listed": False,
                    "message": "Xray 配置目录不存在。",
                    "xray": {
                        "config_dir": XRAY_CONFIG_DIR,
                        "config_exists": False,
                        "service_active": False,
                        "port_443_listening": False,
                    },
                    "files": [],
                    "warnings": [],
                    "failures": ["Xray 配置目录不存在"],
                },
            )

        if logger:
            logger("info", "scan_backup_files", "扫描 Xray 配置备份文件元数据。")
        config_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["config_exists"])
        files_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["backup_files"])
        if logger:
            logger("info", "check_service", "检查 xray.service 当前状态。")
        service_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["xray_active"])
        if logger:
            logger("info", "check_port", "检查 443 端口监听状态。")
        ports_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["listening_tcp"])
    finally:
        transport.close()

    if files_result.exit_code != 0:
        raise SSHReadError(
            "XRAY_BACKUP_SCAN_FAILED",
            "读取 Xray 备份文件列表失败。",
            {
                "classification": "list_xray_backups",
                "listed": False,
                "message": "读取 Xray 备份文件列表失败。",
                "xray": {
                    "config_dir": XRAY_CONFIG_DIR,
                    "config_exists": config_result.exit_code == 0,
                    "service_active": service_result.exit_code == 0
                    and service_result.stdout.strip() == "active",
                    "port_443_listening": 443 in parse_listening_ports(ports_result.stdout),
                },
                "files": [],
                "warnings": [],
                "failures": ["读取 Xray 备份文件列表失败"],
            },
        )

    return {
        "classification": "list_xray_backups",
        "listed": True,
        "message": "Xray 备份文件列表读取完成",
        "xray": {
            "config_dir": XRAY_CONFIG_DIR,
            "config_exists": config_result.exit_code == 0,
            "service_active": service_result.exit_code == 0
            and service_result.stdout.strip() == "active",
            "port_443_listening": 443 in parse_listening_ports(ports_result.stdout),
        },
        "files": parse_backup_files(files_result.stdout),
        "warnings": [],
        "failures": [],
        "listed_at": datetime.now(UTC).isoformat(),
    }


def preview_xray_backup_cleanup_state(
    vps: VpsServer,
    private_key: str,
    passphrase: str | None,
    *,
    logger: CommandLogger | None = None,
) -> dict[str, Any]:
    transport, _, _ = connect_transport(vps, private_key, passphrase)
    try:
        if logger:
            logger("info", "check_config_dir", "检查 Xray 配置目录是否存在。")
        dir_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["config_dir_exists"])
        if dir_result.exit_code != 0:
            raise SSHReadError(
                "XRAY_CONFIG_DIR_NOT_FOUND",
                "Xray 配置目录不存在。",
                {
                    "classification": "preview_xray_backup_cleanup",
                    "previewed": False,
                    "message": "Xray 配置目录不存在。",
                    "policy": {
                        "keep_latest_per_type": 3,
                        "dry_run": True,
                        "delete_enabled": False,
                    },
                    "summary": {
                        "total_files": 0,
                        "total_size_bytes": 0,
                        "candidate_count": 0,
                        "candidate_size_bytes": 0,
                        "estimated_reclaim_bytes": 0,
                        "retained_count": 0,
                    },
                    "candidate_files": [],
                    "retained_files": [],
                    "xray": {
                        "config_dir": XRAY_CONFIG_DIR,
                        "service_active": False,
                        "port_443_listening": False,
                    },
                    "warnings": ["本阶段仅预览，不会删除任何文件"],
                    "failures": ["Xray 配置目录不存在"],
                },
            )

        if logger:
            logger("info", "scan_backup_files", "扫描 Xray 配置备份文件元数据。")
        files_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["cleanup_preview_files"])
        if logger:
            logger("info", "calculate_cleanup_candidates", "计算备份清理候选文件。")
        files = parse_backup_files(files_result.stdout) if files_result.exit_code == 0 else []
        preview = preview_cleanup(files)
        if logger:
            logger("info", "check_service", "检查 xray.service 当前状态。")
        service_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["xray_active"])
        if logger:
            logger("info", "check_port", "检查 443 端口监听状态。")
        ports_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["listening_tcp"])
    finally:
        transport.close()

    if files_result.exit_code != 0:
        raise SSHReadError(
            "XRAY_BACKUP_SCAN_FAILED",
            "读取 Xray 备份文件列表失败。",
            {
                "classification": "preview_xray_backup_cleanup",
                "previewed": False,
                "message": "读取 Xray 备份文件列表失败。",
                "policy": {
                    "keep_latest_per_type": 3,
                    "dry_run": True,
                    "delete_enabled": False,
                },
                "summary": {
                    "total_files": 0,
                    "total_size_bytes": 0,
                    "candidate_count": 0,
                    "candidate_size_bytes": 0,
                    "estimated_reclaim_bytes": 0,
                    "retained_count": 0,
                },
                "candidate_files": [],
                "retained_files": [],
                "xray": {
                    "config_dir": XRAY_CONFIG_DIR,
                    "service_active": service_result.exit_code == 0
                    and service_result.stdout.strip() == "active",
                    "port_443_listening": 443 in parse_listening_ports(ports_result.stdout),
                },
                "warnings": ["本阶段仅预览，不会删除任何文件"],
                "failures": ["读取 Xray 备份文件列表失败"],
            },
        )

    return {
        "classification": "preview_xray_backup_cleanup",
        "previewed": True,
        "message": "Xray 备份清理预览完成，本阶段未删除任何文件",
        "policy": {
            "keep_latest_per_type": 3,
            "dry_run": True,
            "delete_enabled": False,
        },
        "summary": preview["summary"],
        "candidate_files": preview["candidate_files"],
        "retained_files": preview["retained_files"],
        "xray": {
            "config_dir": XRAY_CONFIG_DIR,
            "service_active": service_result.exit_code == 0
            and service_result.stdout.strip() == "active",
            "port_443_listening": 443 in parse_listening_ports(ports_result.stdout),
        },
        "warnings": ["本阶段仅预览，不会删除任何文件"],
        "failures": [],
        "previewed_at": datetime.now(UTC).isoformat(),
    }


def delete_xray_backup_candidate_state(
    vps: VpsServer,
    private_key: str,
    passphrase: str | None,
    *,
    filename: str,
    confirm: bool,
    confirm_filename: str,
    logger: CommandLogger | None = None,
) -> dict[str, Any]:
    if logger:
        logger("info", "validate_request", "校验单个 failed 备份候选文件删除请求。")
    validate_delete_candidate_request(filename, confirm, confirm_filename)

    transport, _, _ = connect_transport(vps, private_key, passphrase)
    try:
        dir_result = run_read_only_command(transport, BACKUP_SCAN_COMMANDS["config_dir_exists"])
        if dir_result.exit_code != 0:
            raise SSHReadError(
                "XRAY_CONFIG_DIR_NOT_FOUND",
                "Xray 配置目录不存在。",
                delete_candidate_failure_result(
                    "validation_failed",
                    "Xray 配置目录不存在。",
                    filename=filename,
                ),
            )

        files, preview, service_result, ports_result = scan_cleanup_preview(
            transport,
            logger=logger,
            log_status_checks=False,
        )

        if logger:
            logger("info", "validate_candidate", "确认文件仍是 failed 类型 dry-run 候选。")
        current_file = find_file_by_name(files, filename)
        if current_file is None:
            raise SSHReadError(
                "FILE_MISSING",
                "目标备份文件不存在。",
                delete_candidate_failure_result(
                    "file_missing",
                    "目标备份文件不存在。",
                    filename=filename,
                ),
            )

        expected_path = backup_path_for_filename(filename)
        if current_file.get("path") != expected_path:
            raise SSHReadError(
                "INVALID_FILENAME",
                "目标文件路径不在允许目录中。",
                delete_candidate_failure_result(
                    "invalid_filename",
                    "目标文件路径不在允许目录中。",
                    filename=filename,
                ),
            )

        if current_file.get("type") != "failed":
            raise SSHReadError(
                "UNSUPPORTED_TYPE",
                "本阶段只允许删除 failed 类型候选文件。",
                delete_candidate_failure_result(
                    "unsupported_type",
                    "本阶段只允许删除 failed 类型候选文件。",
                    filename=filename,
                ),
            )

        candidate = find_file_by_name(preview["candidate_files"], filename)
        if candidate is None:
            retained = find_file_by_name(preview["retained_files"], filename)
            reason = "retained_file" if retained else "not_candidate"
            message = "目标文件不是 dry-run 候选文件。"
            if retained:
                message = "目标文件属于 retained_files，本阶段禁止删除。"
            raise SSHReadError(
                "NOT_CANDIDATE",
                message,
                delete_candidate_failure_result(
                    reason,
                    message,
                    filename=filename,
                ),
            )

        if logger:
            logger("info", "delete_file", "删除单个 failed 备份候选文件。")
        try:
            sftp = paramiko.SFTPClient.from_transport(transport)
            try:
                sftp.remove(expected_path)
            finally:
                sftp.close()
        except (OSError, paramiko.SSHException) as exc:
            raise SSHReadError(
                "REMOTE_DELETE_FAILED",
                "远端删除 failed 备份候选文件失败。",
                delete_candidate_failure_result(
                    "remote_delete_failed",
                    "远端删除 failed 备份候选文件失败。",
                    filename=filename,
                ),
            ) from exc

        if logger:
            logger("info", "verify_deleted", "重新扫描并验证目标文件已不存在。")
        verify_result = run_read_only_command(
            transport,
            BACKUP_SCAN_COMMANDS["cleanup_preview_files"],
        )
        if verify_result.exit_code != 0:
            raise SSHReadError(
                "XRAY_BACKUP_SCAN_FAILED",
                "删除后重新扫描备份文件失败。",
                delete_candidate_failure_result(
                    "remote_delete_failed",
                    "删除后重新扫描备份文件失败。",
                    filename=filename,
                ),
            )
        remaining_files = parse_backup_files(verify_result.stdout)
        file_exists_after_delete = find_file_by_name(remaining_files, filename) is not None
        if file_exists_after_delete:
            raise SSHReadError(
                "REMOTE_DELETE_FAILED",
                "删除后目标文件仍然存在。",
                delete_candidate_failure_result(
                    "remote_delete_failed",
                    "删除后目标文件仍然存在。",
                    filename=filename,
                ),
            )
    finally:
        transport.close()

    return {
        "classification": "delete_xray_backup_candidate",
        "deleted": True,
        "message": "备份候选文件已删除",
        "file": candidate,
        "verify": {
            "file_exists_after_delete": False,
            "remaining_file_count": len(remaining_files),
        },
        "xray": {
            "config_dir": XRAY_CONFIG_DIR,
            "service_active": service_result.exit_code == 0
            and service_result.stdout.strip() == "active",
            "port_443_listening": 443 in parse_listening_ports(ports_result.stdout),
        },
        "warnings": [],
        "failures": [],
        "deleted_at": datetime.now(UTC).isoformat(),
    }
