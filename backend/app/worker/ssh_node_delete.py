from datetime import UTC, datetime
from typing import Any, Callable

import paramiko

from app.core.config import get_settings
from app.models.node import Node
from app.models.vps_server import VpsServer
from app.worker.ssh_create_direct import compact_command_output, run_ssh_command
from app.worker.ssh_install import XRAY_CONFIG_PATH
from app.worker.ssh_prepare import parse_listening_ports
from app.worker.ssh_read import CommandResult, SSHReadError, connect_transport, run_read_only_command

CommandLogger = Callable[[str, str, str, str | None], None]

DELETE_PREFLIGHT_COMMANDS = {
    "xray_path": "command -v xray",
    "xray_version": "xray version",
    "config_exists": f"test -e {XRAY_CONFIG_PATH}",
    "config_test": f"xray run -test -config {XRAY_CONFIG_PATH}",
    "xray_active": "systemctl is-active xray",
    "listening_tcp": "ss -ltnH",
}


def delete_fail_result(
    *,
    message: str,
    failures: list[str],
    warnings: list[str] | None = None,
    backup_path: str | None = None,
    disabled_path: str | None = None,
    step: str | None = None,
    command_result: CommandResult | None = None,
    node_status: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "classification": "delete_node",
        "deleted": False,
        "message": message,
        "xray": {
            "config_path": XRAY_CONFIG_PATH,
            "backup_path": backup_path,
            "disabled_path": disabled_path,
        },
        "warnings": warnings or [],
        "failures": failures,
    }
    if node_status:
        result["node"] = {"status": node_status}
    if step:
        result["failed_step"] = step
    if command_result is not None:
        result["command_exit_code"] = command_result.exit_code
        result["command_output"] = compact_command_output(command_result)
    return result


def log_delete_command(
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


def run_delete_command(transport: paramiko.Transport, command: str) -> CommandResult:
    settings = get_settings()
    return run_ssh_command(
        transport,
        command,
        timeout_seconds=settings.ssh_command_timeout_seconds,
    )


def service_is_active(result: CommandResult) -> bool:
    return result.exit_code == 0 and result.stdout.strip() == "active"


def port_is_listening(result: CommandResult, port: int | None) -> bool:
    if port is None:
        return False
    return port in parse_listening_ports(result.stdout)


def attempt_restore_service(
    transport: paramiko.Transport,
    *,
    backup_path: str,
    disabled_path: str,
    node_port: int | None,
    logger: CommandLogger | None,
) -> bool:
    restore_command = (
        f"if test -e {disabled_path}; then mv {disabled_path} {XRAY_CONFIG_PATH}; "
        f"elif test ! -e {XRAY_CONFIG_PATH} && test -e {backup_path}; "
        f"then cp {backup_path} {XRAY_CONFIG_PATH}; fi"
    )
    restore_result = run_delete_command(transport, restore_command)
    log_delete_command(
        logger,
        level="warning" if restore_result.exit_code == 0 else "error",
        step="rollback_restore_config",
        message="尝试恢复原 Xray 配置。",
        result=restore_result,
    )
    if restore_result.exit_code != 0:
        return False

    restart_result = run_delete_command(transport, "systemctl restart xray")
    log_delete_command(
        logger,
        level="warning" if restart_result.exit_code == 0 else "error",
        step="rollback_restart_service",
        message="尝试重启原 Xray 服务。",
        result=restart_result,
    )
    if restart_result.exit_code != 0:
        return False

    active_result = run_read_only_command(transport, "systemctl is-active xray")
    listening_result = run_read_only_command(transport, "ss -ltnH")
    return service_is_active(active_result) and port_is_listening(listening_result, node_port)


def ensure_delete_preflight(
    *,
    results: dict[str, CommandResult],
    node: Node,
    warnings: list[str],
) -> None:
    binary_path = results["xray_path"].stdout.strip()
    config_exists = results["config_exists"].exit_code == 0
    config_test_passed = results["config_test"].exit_code == 0
    active = service_is_active(results["xray_active"])
    listening = port_is_listening(results["listening_tcp"], node.xray_port)

    if not binary_path:
        raise SSHReadError(
            "XRAY_BINARY_NOT_FOUND",
            "未找到 xray binary，未执行删除。",
            delete_fail_result(
                message="未找到 xray binary，未执行删除。",
                failures=["未找到 xray binary"],
                step="preflight",
                command_result=results["xray_path"],
            ),
        )
    if results["xray_version"].exit_code != 0:
        raise SSHReadError(
            "XRAY_VERSION_FAILED",
            "xray version 执行失败，未执行删除。",
            delete_fail_result(
                message="xray version 执行失败，未执行删除。",
                failures=["xray version 执行失败"],
                step="preflight",
                command_result=results["xray_version"],
            ),
        )
    if not config_exists:
        raise SSHReadError(
            "XRAY_CONFIG_NOT_FOUND",
            "Xray 配置文件不存在，未修改数据库。",
            delete_fail_result(
                message="Xray 配置文件不存在，未修改数据库。",
                failures=["Xray 配置文件不存在"],
                step="preflight",
                command_result=results["config_exists"],
            ),
        )
    if not config_test_passed:
        raise SSHReadError(
            "XRAY_CONFIG_TEST_FAILED",
            "xray run -test 未通过，未执行删除。",
            delete_fail_result(
                message="xray run -test 未通过，未执行删除。",
                failures=["xray run -test 未通过"],
                step="preflight",
                command_result=results["config_test"],
            ),
        )
    if not active:
        warnings.append("删除前 xray.service 已不是 active 状态。")
    if not listening:
        warnings.append(f"删除前端口 {node.xray_port} 未处于监听状态。")


def delete_node_state(
    vps: VpsServer,
    node: Node,
    private_key: str,
    passphrase: str | None,
    *,
    logger: CommandLogger | None = None,
) -> dict[str, Any]:
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
    backup_path = f"{XRAY_CONFIG_PATH}.bak.{timestamp}"
    disabled_path = f"{XRAY_CONFIG_PATH}.disabled.{timestamp}"
    warnings: list[str] = []

    transport, _, _ = connect_transport(vps, private_key, passphrase)
    try:
        preflight_results = {
            key: run_read_only_command(transport, command)
            for key, command in DELETE_PREFLIGHT_COMMANDS.items()
        }
        ensure_delete_preflight(results=preflight_results, node=node, warnings=warnings)
        log_delete_command(
            logger,
            level="info",
            step="preflight",
            message="删除前检查通过。",
        )

        backup_result = run_delete_command(transport, f"cp {XRAY_CONFIG_PATH} {backup_path}")
        log_delete_command(
            logger,
            level="info" if backup_result.exit_code == 0 else "error",
            step="backup_config",
            message="备份 Xray 配置。",
            result=backup_result,
        )
        if backup_result.exit_code != 0:
            raise SSHReadError(
                "XRAY_CONFIG_BACKUP_FAILED",
                "备份 Xray 配置失败，未停止服务。",
                delete_fail_result(
                    message="备份 Xray 配置失败，未停止服务。",
                    failures=["备份 Xray 配置失败"],
                    backup_path=backup_path,
                    disabled_path=disabled_path,
                    step="backup_config",
                    command_result=backup_result,
                ),
            )

        backup_check = run_read_only_command(transport, f"test -e {backup_path}")
        if backup_check.exit_code != 0:
            raise SSHReadError(
                "XRAY_CONFIG_BACKUP_VERIFY_FAILED",
                "备份文件验证失败，未停止服务。",
                delete_fail_result(
                    message="备份文件验证失败，未停止服务。",
                    failures=["备份文件验证失败"],
                    backup_path=backup_path,
                    disabled_path=disabled_path,
                    step="backup_config",
                    command_result=backup_check,
                ),
            )

        stop_result = run_delete_command(transport, "systemctl stop xray")
        log_delete_command(
            logger,
            level="info" if stop_result.exit_code == 0 else "error",
            step="stop_service",
            message="停止 xray.service。",
            result=stop_result,
        )
        if stop_result.exit_code != 0:
            raise SSHReadError(
                "XRAY_SERVICE_STOP_FAILED",
                "停止 xray.service 失败，未移动配置。",
                delete_fail_result(
                    message="停止 xray.service 失败，未移动配置。",
                    failures=["停止 xray.service 失败"],
                    backup_path=backup_path,
                    disabled_path=disabled_path,
                    step="stop_service",
                    command_result=stop_result,
                ),
            )

        move_result = run_delete_command(transport, f"mv {XRAY_CONFIG_PATH} {disabled_path}")
        log_delete_command(
            logger,
            level="info" if move_result.exit_code == 0 else "error",
            step="move_config",
            message="移走正式 Xray 配置。",
            result=move_result,
        )
        if move_result.exit_code != 0:
            restored = attempt_restore_service(
                transport,
                backup_path=backup_path,
                disabled_path=disabled_path,
                node_port=node.xray_port,
                logger=logger,
            )
            raise SSHReadError(
                "XRAY_CONFIG_MOVE_FAILED",
                "移走 Xray 配置失败，已尝试恢复原服务。",
                delete_fail_result(
                    message="移走 Xray 配置失败，已尝试恢复原服务。",
                    failures=["移走 Xray 配置失败"],
                    warnings=(["原服务已恢复。"] if restored else ["原服务恢复失败，请手动检查。"]),
                    backup_path=backup_path,
                    disabled_path=disabled_path,
                    step="move_config",
                    command_result=move_result,
                    node_status=None if restored else "error",
                ),
            )

        disabled_check = run_read_only_command(transport, f"test -e {disabled_path}")
        if disabled_check.exit_code != 0:
            restored = attempt_restore_service(
                transport,
                backup_path=backup_path,
                disabled_path=disabled_path,
                node_port=node.xray_port,
                logger=logger,
            )
            raise SSHReadError(
                "XRAY_DISABLED_CONFIG_VERIFY_FAILED",
                "停用配置文件验证失败，已尝试恢复原服务。",
                delete_fail_result(
                    message="停用配置文件验证失败，已尝试恢复原服务。",
                    failures=["停用配置文件验证失败"],
                    warnings=(["原服务已恢复。"] if restored else ["原服务恢复失败，请手动检查。"]),
                    backup_path=backup_path,
                    disabled_path=disabled_path,
                    step="move_config",
                    command_result=disabled_check,
                    node_status=None if restored else "error",
                ),
            )

        active_result = run_read_only_command(transport, "systemctl is-active xray")
        listening_result = run_read_only_command(transport, "ss -ltnH")
        service_active = service_is_active(active_result)
        listening = port_is_listening(listening_result, node.xray_port)
        log_delete_command(
            logger,
            level="info" if not service_active and not listening else "error",
            step="verify_stopped",
            message="验证 Xray 已停止且节点端口不再监听。",
            result=listening_result,
        )

        if service_active or listening:
            restored = attempt_restore_service(
                transport,
                backup_path=backup_path,
                disabled_path=disabled_path,
                node_port=node.xray_port,
                logger=logger,
            )
            raise SSHReadError(
                "XRAY_DELETE_VERIFY_FAILED",
                "节点停用验证失败，已尝试恢复原服务。",
                delete_fail_result(
                    message="节点停用验证失败，已尝试恢复原服务。",
                    failures=["xray.service 仍为 active" if service_active else f"端口 {node.xray_port} 仍在监听"],
                    warnings=(["原服务已恢复。"] if restored else ["原服务恢复失败，请手动检查。"]),
                    backup_path=backup_path,
                    disabled_path=disabled_path,
                    step="verify_stopped",
                    command_result=active_result if service_active else listening_result,
                    node_status=None if restored else "error",
                ),
            )

        return {
            "classification": "delete_node",
            "deleted": True,
            "message": "节点已软删除，旧链接已失效",
            "node": {
                "id": node.id,
                "name": node.node_name,
                "status": "deleted",
                "port": node.xray_port,
                "deleted_at": datetime.now(UTC).isoformat(),
            },
            "xray": {
                "config_path": XRAY_CONFIG_PATH,
                "backup_path": backup_path,
                "disabled_path": disabled_path,
                "service_active": service_active,
                "listening": listening,
            },
            "warnings": warnings,
            "failures": [],
        }
    finally:
        transport.close()
