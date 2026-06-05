import ipaddress
import shlex
import time
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import quote, urlencode

import paramiko

from app.models.node import Node
from app.models.transit_resource import TransitResource
from app.models.vps_server import VpsServer
from app.services.task_logging import sanitize_log_text
from app.worker.ssh_gost_install import GOST_INSTALL_PATH, SSH_RESERVED_PORT
from app.worker.ssh_install import run_ssh_command
from app.worker.ssh_prepare import parse_listening_ports
from app.worker.ssh_read import CommandResult, SSHReadError, run_read_only_command
from app.worker.ssh_transit_read import connect_transit_transport

SERVICE_PREFIX = "liveline-transit"
SYSTEMD_DIR = "/etc/systemd/system"
FORWARDING_METHOD = "gost"
DEFAULT_FINGERPRINT = "chrome"
VERIFY_PORT_ATTEMPTS = 5
VERIFY_PORT_INTERVAL_SECONDS = 1

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


def validate_ipv4(value: str, *, field: str) -> str:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise SSHReadError(
            f"INVALID_{field.upper()}",
            f"{field} 不是合法 IP 地址。",
            fail_result(
                message=f"{field} 不是合法 IP 地址。",
                failures=[f"{field} 不是合法 IP 地址"],
                step="validate_inputs",
            ),
        ) from exc


def validate_port(value: int, *, field: str) -> int:
    if value < 1 or value > 65535:
        raise SSHReadError(
            f"INVALID_{field.upper()}",
            f"{field} 必须在 1-65535 之间。",
            fail_result(
                message=f"{field} 必须在 1-65535 之间。",
                failures=[f"{field} 必须在 1-65535 之间"],
                step="validate_inputs",
            ),
        )
    if field == "listen_port" and value == SSH_RESERVED_PORT:
        raise SSHReadError(
            "TRANSIT_PORT_RESERVED",
            "20575 是 SSH 端口，不能作为中转监听端口。",
            fail_result(
                message="20575 是 SSH 端口，不能作为中转监听端口。",
                failures=["20575 是 SSH 端口，不能作为中转监听端口"],
                step="validate_inputs",
            ),
        )
    return value


def service_name_for(route_id: str) -> str:
    safe_id = route_id.replace("-", "")
    return f"{SERVICE_PREFIX}-{safe_id}.service"


def service_path_for(service_name: str) -> str:
    return f"{SYSTEMD_DIR}/{service_name}"


def build_gost_command(*, listen_port: int, target_host: str, target_port: int) -> str:
    # GOST v3.2.6 CLI uses -L tcp://:listen/target:port for TCP port forwarding.
    # Reference: https://v3.gost.run/en/reference/configuration/cmd/
    return f"{GOST_INSTALL_PATH} -L=tcp://0.0.0.0:{listen_port}/{target_host}:{target_port}"


def build_service_file(
    *,
    route_id: str,
    listen_port: int,
    target_host: str,
    target_port: int,
) -> str:
    gost_command = build_gost_command(
        listen_port=listen_port,
        target_host=target_host,
        target_port=target_port,
    )
    return "\n".join(
        [
            "[Unit]",
            f"Description=LiveLine Transit Route {route_id}",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            "User=root",
            f"ExecStart={gost_command}",
            "Restart=always",
            "RestartSec=3",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def build_transit_share_link(
    *,
    route_name: str,
    transit_host: str,
    listen_port: int,
    node: Node,
) -> str:
    if not node.uuid or not node.reality_public_key or not node.reality_short_id or not node.sni:
        raise SSHReadError(
            "NODE_REALITY_FIELDS_MISSING",
            "节点 Reality 参数不完整，不能生成中转链接。",
            fail_result(
                message="节点 Reality 参数不完整，不能生成中转链接。",
                failures=["节点 Reality 参数不完整"],
                step="validate_inputs",
            ),
        )

    query = urlencode(
        {
            "type": "tcp",
            "security": "reality",
            "encryption": "none",
            "flow": node.flow or "xtls-rprx-vision",
            "sni": node.sni,
            "fp": node.fingerprint or DEFAULT_FINGERPRINT,
            "pbk": node.reality_public_key,
            "sid": node.reality_short_id,
        }
    )
    name = quote(route_name, safe="")
    return f"vless://{node.uuid}@{transit_host}:{listen_port}?{query}#{name}"


def base_warnings() -> list[str]:
    return [
        "本系统未自动开放云安全组，请确认监听端口已在云厂商后台放行",
        "本阶段暂不提供删除转发功能，删除功能将在后续阶段实现",
    ]


def fail_result(
    *,
    message: str,
    failures: list[str],
    warnings: list[str] | None = None,
    step: str | None = None,
    command_result: CommandResult | None = None,
    route: dict[str, Any] | None = None,
    manual_cleanup_required: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "classification": "create_transit_route",
        "created": False,
        "message": message,
        "warnings": warnings if warnings is not None else base_warnings(),
        "failures": failures,
        "manual_cleanup_required": manual_cleanup_required,
    }
    if route is not None:
        payload["route"] = route
    if step:
        payload["failed_step"] = step
    if command_result is not None:
        payload["command_exit_code"] = command_result.exit_code
        payload["command_output"] = compact_command_output(command_result)
    return payload


def success_result(
    *,
    route: dict[str, Any],
    gost_version: str,
    service_active: bool,
    listening: bool,
) -> dict[str, Any]:
    return {
        "classification": "create_transit_route",
        "created": True,
        "message": "单条 gost TCP 中转规则创建成功",
        "route": route,
        "gost": {
            "path": GOST_INSTALL_PATH,
            "version": gost_version,
        },
        "verify": {
            "service_active": service_active,
            "listening": listening,
        },
        "warnings": base_warnings(),
        "failures": [],
    }


def write_service_file(
    transport: paramiko.Transport,
    *,
    service_path: str,
    content: str,
) -> None:
    sftp = paramiko.SFTPClient.from_transport(transport)
    try:
        with sftp.open(service_path, "w") as remote_file:
            remote_file.write(content)
    finally:
        sftp.close()


def remove_service_file(transport: paramiko.Transport, service_path: str) -> None:
    sftp = paramiko.SFTPClient.from_transport(transport)
    try:
        try:
            sftp.remove(service_path)
        except FileNotFoundError:
            return
    finally:
        sftp.close()


def run_checked(
    transport: paramiko.Transport,
    *,
    command: str,
    step: str,
    timeout_seconds: int,
    logger: CommandLogger | None,
    success_message: str,
    error_code: str,
    error_message: str,
    route: dict[str, Any],
) -> CommandResult:
    result = run_ssh_command(transport, command, timeout_seconds=timeout_seconds)
    if result.exit_code != 0:
        log_step(logger, level="error", step=step, message=error_message, result=result)
        raise SSHReadError(
            error_code,
            error_message,
            fail_result(
                message=error_message,
                failures=[error_message],
                step=step,
                command_result=result,
                route=route,
            ),
        )
    log_step(logger, level="info", step=step, message=success_message, result=result)
    return result


def rollback_remote_service(
    transport: paramiko.Transport,
    *,
    service_name: str,
    service_path: str,
    timeout_seconds: int,
    logger: CommandLogger | None = None,
) -> bool:
    ok = True
    commands = (
        f"systemctl stop {shlex.quote(service_name)}",
        f"systemctl disable {shlex.quote(service_name)}",
    )
    for command in commands:
        result = run_ssh_command(transport, command, timeout_seconds=timeout_seconds)
        if result.exit_code not in (0, 1):
            ok = False
            log_step(
                logger,
                level="warning",
                step="rollback",
                message="回滚 systemd service 时出现问题。",
                result=result,
            )
    try:
        remove_service_file(transport, service_path)
    except OSError:
        ok = False
    reload_result = run_ssh_command(transport, "systemctl daemon-reload", timeout_seconds=timeout_seconds)
    if reload_result.exit_code != 0:
        ok = False
        log_step(
            logger,
            level="warning",
            step="rollback",
            message="回滚后 daemon-reload 失败。",
            result=reload_result,
        )
    return ok


def wait_for_listening_port(
    transport: paramiko.Transport,
    *,
    listen_port: int,
    logger: CommandLogger | None,
    attempts: int = VERIFY_PORT_ATTEMPTS,
    interval_seconds: int = VERIFY_PORT_INTERVAL_SECONDS,
) -> tuple[bool, CommandResult | None]:
    log_step(
        logger,
        level="info",
        step="verify_port",
        message="等待中转端口监听。",
    )
    last_result: CommandResult | None = None
    for attempt in range(1, attempts + 1):
        log_step(
            logger,
            level="info",
            step="verify_port",
            message=f"第 {attempt} 次检查中转端口监听状态。",
        )
        last_result = run_read_only_command(transport, "ss -ltnH")
        listening_ports = parse_listening_ports(last_result.stdout) if last_result.exit_code == 0 else set()
        if listen_port in listening_ports:
            log_step(
                logger,
                level="info",
                step="verify_port",
                message="中转监听端口已进入 LISTEN 状态。",
            )
            return True, last_result
        if attempt < attempts:
            time.sleep(interval_seconds)
    return False, last_result


def cleanup_transit_service(
    resource: TransitResource,
    private_key: str,
    passphrase: str | None,
    *,
    service_name: str,
    service_path: str,
    timeout_seconds: int,
) -> bool:
    transport, _, _ = connect_transit_transport(resource, private_key, passphrase)
    try:
        return rollback_remote_service(
            transport,
            service_name=service_name,
            service_path=service_path,
            timeout_seconds=timeout_seconds,
        )
    finally:
        transport.close()


def create_transit_route_state(
    *,
    resource: TransitResource,
    node: Node,
    vps: VpsServer,
    private_key: str,
    passphrase: str | None,
    route_id: str,
    route_name: str,
    listen_port: int,
    forwarding_method: str,
    logger: CommandLogger | None = None,
) -> dict[str, Any]:
    validate_port(listen_port, field="listen_port")
    target_host = validate_ipv4(vps.ip, field="target_host")
    target_port = validate_port(node.xray_port or 0, field="target_port")
    if forwarding_method != FORWARDING_METHOD:
        raise SSHReadError(
            "UNSUPPORTED_FORWARDING_METHOD",
            "Stage 3.3.3 只支持 gost。",
            fail_result(
                message="Stage 3.3.3 只支持 gost。",
                failures=["Stage 3.3.3 只支持 gost"],
                step="validate_inputs",
            ),
        )
    if not resource.entry_host:
        raise SSHReadError(
            "TRANSIT_ENTRY_HOST_REQUIRED",
            "中转资源缺少入口 Host，无法生成中转链接。",
            fail_result(
                message="中转资源缺少入口 Host，无法生成中转链接。",
                failures=["中转资源缺少入口 Host"],
                step="validate_inputs",
            ),
        )

    service_name = service_name_for(route_id)
    service_path = service_path_for(service_name)
    share_link = build_transit_share_link(
        route_name=route_name,
        transit_host=resource.entry_host,
        listen_port=listen_port,
        node=node,
    )
    route_summary: dict[str, Any] = {
        "id": route_id,
        "name": route_name,
        "transit_resource_id": resource.id,
        "node_id": node.id,
        "listen_port": listen_port,
        "target_host": target_host,
        "target_port": target_port,
        "forwarding_method": forwarding_method,
        "service_name": service_name,
        "service_path": service_path,
        "status": "active",
        "share_link": share_link,
    }

    timeout_seconds = 30
    transport: paramiko.Transport | None = None
    service_written = False
    try:
        transport, _, _ = connect_transit_transport(resource, private_key, passphrase)
        log_step(logger, level="info", step="ssh_connect", message="香港中转服务器 SSH 连接成功。")

        whoami = run_read_only_command(transport, "whoami")
        systemd = run_read_only_command(transport, "test -d /run/systemd/system")
        if whoami.stdout.strip() != "root":
            raise SSHReadError(
                "NO_ROOT_PERMISSION",
                "创建 systemd 转发服务需要 root 用户。",
                fail_result(
                    message="创建 systemd 转发服务需要 root 用户。",
                    failures=["创建 systemd 转发服务需要 root 用户"],
                    step="validate_inputs",
                    command_result=whoami,
                    route=route_summary,
                ),
            )
        if systemd.exit_code != 0:
            raise SSHReadError(
                "SYSTEMD_UNAVAILABLE",
                "systemd 不可用，不能创建中转转发服务。",
                fail_result(
                    message="systemd 不可用，不能创建中转转发服务。",
                    failures=["systemd 不可用"],
                    step="validate_inputs",
                    command_result=systemd,
                    route=route_summary,
                ),
            )
        log_step(logger, level="info", step="validate_inputs", message="本地与远端基础条件校验通过。")

        gost_path = run_read_only_command(transport, "command -v gost")
        if gost_path.exit_code != 0 or gost_path.stdout.strip() != GOST_INSTALL_PATH:
            raise SSHReadError(
                "GOST_NOT_INSTALLED",
                "未检测到 /usr/local/bin/gost，请先完成 Stage 3.3.2。",
                fail_result(
                    message="未检测到 /usr/local/bin/gost，请先完成 Stage 3.3.2。",
                    failures=["未检测到 /usr/local/bin/gost"],
                    step="check_gost",
                    command_result=gost_path,
                    route=route_summary,
                ),
            )
        gost_version_result = run_read_only_command(transport, f"{GOST_INSTALL_PATH} -V")
        if gost_version_result.exit_code != 0:
            raise SSHReadError(
                "GOST_VERSION_FAILED",
                "gost 版本读取失败。",
                fail_result(
                    message="gost 版本读取失败。",
                    failures=["gost 版本读取失败"],
                    step="check_gost",
                    command_result=gost_version_result,
                    route=route_summary,
                ),
            )
        gost_version = (gost_version_result.stdout or gost_version_result.stderr).splitlines()[0]
        log_step(logger, level="info", step="check_gost", message="gost binary 校验通过。")

        port_result = run_read_only_command(transport, "ss -ltnH")
        if port_result.exit_code != 0:
            raise SSHReadError(
                "PORT_CHECK_FAILED",
                "无法检查中转服务器监听端口。",
                fail_result(
                    message="无法检查中转服务器监听端口。",
                    failures=["无法检查中转服务器监听端口"],
                    step="check_port",
                    command_result=port_result,
                    route=route_summary,
                ),
            )
        listening_ports = parse_listening_ports(port_result.stdout)
        if listen_port in listening_ports:
            raise SSHReadError(
                "TRANSIT_PORT_IN_USE",
                "中转监听端口已被占用。",
                fail_result(
                    message="中转监听端口已被占用。",
                    failures=[f"中转监听端口 {listen_port} 已被占用"],
                    step="check_port",
                    command_result=port_result,
                    route=route_summary,
                ),
            )
        log_step(logger, level="info", step="check_port", message="中转监听端口未被占用。")

        service_exists = run_read_only_command(transport, f"test -e {shlex.quote(service_path)}")
        if service_exists.exit_code == 0:
            raise SSHReadError(
                "TRANSIT_SERVICE_ALREADY_EXISTS",
                "检测到同名 liveline-transit service，已拒绝覆盖。",
                fail_result(
                    message="检测到同名 liveline-transit service，已拒绝覆盖。",
                    failures=["检测到同名 liveline-transit service"],
                    step="write_service",
                    route=route_summary,
                ),
            )
        write_service_file(
            transport,
            service_path=service_path,
            content=build_service_file(
                route_id=route_id,
                listen_port=listen_port,
                target_host=target_host,
                target_port=target_port,
            ),
        )
        service_written = True
        log_step(logger, level="info", step="write_service", message="systemd service 文件已写入。")

        try:
            run_checked(
                transport,
                command="systemctl daemon-reload",
                step="daemon_reload",
                timeout_seconds=timeout_seconds,
                logger=logger,
                success_message="systemd daemon-reload 完成。",
                error_code="SYSTEMD_DAEMON_RELOAD_FAILED",
                error_message="systemd daemon-reload 失败。",
                route=route_summary,
            )
            run_checked(
                transport,
                command=f"systemctl enable {shlex.quote(service_name)}",
                step="enable_service",
                timeout_seconds=timeout_seconds,
                logger=logger,
                success_message="中转 service 已 enable。",
                error_code="TRANSIT_SERVICE_ENABLE_FAILED",
                error_message="中转 service enable 失败。",
                route=route_summary,
            )
            run_checked(
                transport,
                command=f"systemctl start {shlex.quote(service_name)}",
                step="start_service",
                timeout_seconds=timeout_seconds,
                logger=logger,
                success_message="中转 service 已 start。",
                error_code="TRANSIT_SERVICE_START_FAILED",
                error_message="中转 service start 失败。",
                route=route_summary,
            )
            active_result = run_checked(
                transport,
                command=f"systemctl is-active {shlex.quote(service_name)}",
                step="verify_service",
                timeout_seconds=timeout_seconds,
                logger=logger,
                success_message="中转 service 当前为 active。",
                error_code="TRANSIT_SERVICE_NOT_ACTIVE",
                error_message="中转 service 未 active。",
                route=route_summary,
            )
            port_is_listening, verify_port_result = wait_for_listening_port(
                transport,
                listen_port=listen_port,
                logger=logger,
            )
            if not port_is_listening:
                log_step(
                    logger,
                    level="error",
                    step="verify_port",
                    message="中转监听端口未进入 LISTEN 状态。",
                )
                raise SSHReadError(
                    "TRANSIT_PORT_NOT_LISTENING",
                    "中转监听端口未进入 LISTEN 状态。",
                    fail_result(
                        message="中转监听端口未进入 LISTEN 状态。",
                        failures=["中转监听端口未进入 LISTEN 状态"],
                        step="verify_port",
                        route=route_summary,
                    ),
                )
        except SSHReadError as exc:
            rollback_ok = rollback_remote_service(
                transport,
                service_name=service_name,
                service_path=service_path,
                timeout_seconds=timeout_seconds,
                logger=logger,
            )
            if exc.result_data is not None:
                exc.result_data["manual_cleanup_required"] = not rollback_ok
            raise

        route_summary["created_at"] = datetime.now(UTC).isoformat()
        return success_result(
            route=route_summary,
            gost_version=gost_version[:200],
            service_active=active_result.stdout.strip() == "active",
            listening=True,
        )
    except OSError as exc:
        rollback_ok = True
        if service_written and transport is not None:
            rollback_ok = rollback_remote_service(
                transport,
                service_name=service_name,
                service_path=service_path,
                timeout_seconds=timeout_seconds,
                logger=logger,
            )
        raise SSHReadError(
            "TRANSIT_SERVICE_WRITE_FAILED",
            "写入 systemd service 文件失败。",
            fail_result(
                message="写入 systemd service 文件失败。",
                failures=["写入 systemd service 文件失败"],
                step="write_service",
                route=route_summary,
                manual_cleanup_required=not rollback_ok,
            ),
        ) from exc
    finally:
        if transport is not None:
            transport.close()
        time.sleep(0)
