import ipaddress
import shlex
import time
from contextlib import suppress
from datetime import UTC, datetime
from typing import Any, Callable

import paramiko

from app.models.transit_route import TransitRoute
from app.services.task_logging import sanitize_log_text
from app.worker.ssh_install import run_ssh_command
from app.worker.ssh_prepare import parse_listening_ports
from app.worker.ssh_read import CommandResult, SSHReadError, run_read_only_command
from app.worker.ssh_transit_read import connect_transit_transport

ACCEPTED_SOCAT_RESOURCE_ID = "6d67c275-8ac9-4775-9519-c89b50718157"
SOCAT_PATH = "/usr/bin/socat"
SOCAT_FORWARDING_METHOD = "socat"
SOCAT_SERVICE_PREFIX = "liveline-socat"
SYSTEMD_DIR = "/etc/systemd/system"
SOCAT_RESERVED_PORTS = {22, 8443, 20575}
VERIFY_PORT_ATTEMPTS = 5
VERIFY_PORT_INTERVAL_SECONDS = 1

CommandLogger = Callable[[str, str, str, str | None], None]


def service_name_for(route_id: str) -> str:
    return f"{SOCAT_SERVICE_PREFIX}-{route_id.replace('-', '')}.service"


def service_path_for(service_name: str) -> str:
    return f"{SYSTEMD_DIR}/{service_name}"


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


def base_warnings() -> list[str]:
    return [
        "Stage 3.3.3-fix-b1 只创建 socat 测试转发，不替换现有 gost 8443",
        "本系统未自动开放云安全组，请确认测试监听端口已在云厂商后台放行",
    ]


def route_summary(route: TransitRoute) -> dict[str, Any]:
    return {
        "id": route.id,
        "name": route.name,
        "transit_resource_id": route.transit_resource_id,
        "node_id": route.node_id,
        "listen_port": route.listen_port,
        "target_host": route.target_host,
        "target_port": route.target_port,
        "forwarding_method": route.forwarding_method,
        "service_name": route.service_name,
        "service_path": route.service_path,
        "status": route.status,
    }


def fail_result(
    *,
    message: str,
    failures: list[str],
    route: TransitRoute,
    step: str | None = None,
    command_result: CommandResult | None = None,
    manual_cleanup_required: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "classification": "create_socat_route",
        "created": False,
        "message": message,
        "route": route_summary(route),
        "warnings": base_warnings(),
        "failures": failures,
        "manual_cleanup_required": manual_cleanup_required,
        "checked_at": datetime.now(UTC).isoformat(),
    }
    if step:
        payload["failed_step"] = step
    if command_result is not None:
        payload["command_exit_code"] = command_result.exit_code
        payload["command_output"] = compact_command_output(command_result)
    return payload


def success_result(
    *,
    route: TransitRoute,
    socat_version: str,
    service_active: bool,
    listening: bool,
) -> dict[str, Any]:
    return {
        "classification": "create_socat_route",
        "created": True,
        "message": "单条 socat TCP 测试转发创建成功",
        "route": route_summary(route) | {"status": "active"},
        "socat": {
            "path": SOCAT_PATH,
            "version": socat_version,
        },
        "verify": {
            "service_active": service_active,
            "listening": listening,
        },
        "warnings": base_warnings(),
        "failures": [],
        "checked_at": datetime.now(UTC).isoformat(),
    }


def validate_ipv4(value: str, *, field: str, route: TransitRoute) -> str:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        message = f"{field} 不是合法 IP 地址。"
        raise SSHReadError(
            f"INVALID_{field.upper()}",
            message,
            fail_result(message=message, failures=[message], route=route, step="validate_inputs"),
        ) from exc


def validate_port(value: int, *, field: str, route: TransitRoute) -> int:
    if value < 1 or value > 65535:
        message = f"{field} 必须在 1-65535 之间。"
        raise SSHReadError(
            f"INVALID_{field.upper()}",
            message,
            fail_result(message=message, failures=[message], route=route, step="validate_inputs"),
        )
    if field == "listen_port" and value in SOCAT_RESERVED_PORTS:
        message = "socat 测试转发禁止使用 22、8443、20575 作为监听端口。"
        raise SSHReadError(
            "SOCAT_PORT_RESERVED",
            message,
            fail_result(message=message, failures=[message], route=route, step="validate_inputs"),
        )
    return value


def build_socat_command(*, listen_port: int, target_host: str, target_port: int) -> str:
    return f"{SOCAT_PATH} TCP-LISTEN:{listen_port},fork,reuseaddr TCP:{target_host}:{target_port}"


def build_service_file(route: TransitRoute) -> str:
    command = build_socat_command(
        listen_port=route.listen_port,
        target_host=route.target_host,
        target_port=route.target_port,
    )
    return "\n".join(
        [
            "[Unit]",
            f"Description=LiveLine Socat Transit Route {route.id}",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            "User=root",
            f"ExecStart={command}",
            "Restart=always",
            "RestartSec=3",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


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
        with suppress(FileNotFoundError):
            sftp.remove(service_path)
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
    route: TransitRoute,
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
                route=route,
                step=step,
                command_result=result,
            ),
        )
    log_step(logger, level="info", step=step, message=success_message, result=result)
    return result


def rollback_socat_service(
    transport: paramiko.Transport,
    *,
    service_name: str,
    service_path: str,
    timeout_seconds: int,
    logger: CommandLogger | None = None,
) -> bool:
    ok = True
    for command in (
        f"systemctl stop {shlex.quote(service_name)}",
        f"systemctl disable {shlex.quote(service_name)}",
    ):
        result = run_ssh_command(transport, command, timeout_seconds=timeout_seconds)
        if result.exit_code not in (0, 1):
            ok = False
            log_step(
                logger,
                level="warning",
                step="rollback",
                message="回滚 socat systemd service 时出现问题。",
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


def cleanup_socat_service(
    route: TransitRoute,
    private_key: str,
    passphrase: str | None,
    *,
    timeout_seconds: int,
) -> bool:
    resource = route.transit_resource
    if resource is None:
        return False
    transport, _, _ = connect_transit_transport(resource, private_key, passphrase)
    try:
        return rollback_socat_service(
            transport,
            service_name=route.service_name,
            service_path=route.service_path,
            timeout_seconds=timeout_seconds,
        )
    finally:
        transport.close()


def wait_for_listening_port(
    transport: paramiko.Transport,
    *,
    listen_port: int,
    logger: CommandLogger | None,
    attempts: int = VERIFY_PORT_ATTEMPTS,
    interval_seconds: int = VERIFY_PORT_INTERVAL_SECONDS,
) -> tuple[bool, CommandResult | None]:
    log_step(logger, level="info", step="verify_port", message="等待 socat 测试端口监听。")
    last_result: CommandResult | None = None
    for attempt in range(1, attempts + 1):
        log_step(logger, level="info", step="verify_port", message=f"第 {attempt} 次检查 socat 端口监听状态。")
        last_result = run_read_only_command(transport, "ss -ltnH")
        listening_ports = parse_listening_ports(last_result.stdout) if last_result.exit_code == 0 else set()
        if listen_port in listening_ports:
            log_step(logger, level="info", step="verify_port", message="socat 测试监听端口已进入 LISTEN 状态。")
            return True, last_result
        if attempt < attempts:
            time.sleep(interval_seconds)
    return False, last_result


def create_socat_route_state(
    *,
    route: TransitRoute,
    private_key: str,
    passphrase: str | None,
    logger: CommandLogger | None = None,
) -> dict[str, Any]:
    resource = route.transit_resource
    if resource is None:
        message = "中转资源不存在。"
        raise SSHReadError(
            "TRANSIT_RESOURCE_NOT_FOUND",
            message,
            fail_result(message=message, failures=[message], route=route, step="validate_inputs"),
        )
    if resource.id != ACCEPTED_SOCAT_RESOURCE_ID:
        message = "Stage 3.3.3-fix-b1 只允许正式香港中转资源创建 socat 测试转发。"
        raise SSHReadError(
            "SOCAT_RESOURCE_NOT_ACCEPTED",
            message,
            fail_result(message=message, failures=[message], route=route, step="validate_inputs"),
        )
    if route.forwarding_method != SOCAT_FORWARDING_METHOD:
        message = "Stage 3.3.3-fix-b1 只支持 socat 转发方式。"
        raise SSHReadError(
            "UNSUPPORTED_FORWARDING_METHOD",
            message,
            fail_result(message=message, failures=[message], route=route, step="validate_inputs"),
        )

    validate_port(route.listen_port, field="listen_port", route=route)
    validate_ipv4(route.target_host, field="target_host", route=route)
    validate_port(route.target_port, field="target_port", route=route)

    timeout_seconds = 30
    transport: paramiko.Transport | None = None
    service_written = False
    try:
        transport, _, _ = connect_transit_transport(resource, private_key, passphrase)
        log_step(logger, level="info", step="ssh_connect", message="香港中转服务器 SSH 连接成功。")

        whoami = run_read_only_command(transport, "whoami")
        systemd = run_read_only_command(transport, "test -d /run/systemd/system")
        if whoami.stdout.strip() != "root":
            message = "创建 socat systemd 转发服务需要 root 用户。"
            raise SSHReadError(
                "NO_ROOT_PERMISSION",
                message,
                fail_result(message=message, failures=[message], route=route, step="validate_inputs", command_result=whoami),
            )
        if systemd.exit_code != 0:
            message = "systemd 不可用，不能创建 socat 转发服务。"
            raise SSHReadError(
                "SYSTEMD_UNAVAILABLE",
                message,
                fail_result(message=message, failures=[message], route=route, step="validate_inputs", command_result=systemd),
            )
        log_step(logger, level="info", step="validate_inputs", message="socat 测试转发基础条件校验通过。")

        socat_path = run_read_only_command(transport, "command -v socat")
        if socat_path.exit_code != 0 or socat_path.stdout.strip() != SOCAT_PATH:
            message = "未检测到 /usr/bin/socat，请先完成 Stage 3.3.3-fix-a。"
            raise SSHReadError(
                "SOCAT_NOT_INSTALLED",
                message,
                fail_result(message=message, failures=[message], route=route, step="check_socat", command_result=socat_path),
            )
        socat_version_result = run_read_only_command(transport, f"{SOCAT_PATH} -V")
        if socat_version_result.exit_code != 0:
            message = "socat 版本读取失败。"
            raise SSHReadError(
                "SOCAT_VERSION_FAILED",
                message,
                fail_result(
                    message=message,
                    failures=[message],
                    route=route,
                    step="check_socat",
                    command_result=socat_version_result,
                ),
            )
        socat_version = (socat_version_result.stdout or socat_version_result.stderr).splitlines()[0][:200]
        log_step(logger, level="info", step="check_socat", message="socat binary 校验通过。")

        port_result = run_read_only_command(transport, "ss -ltnH")
        if port_result.exit_code != 0:
            message = "无法检查中转服务器监听端口。"
            raise SSHReadError(
                "PORT_CHECK_FAILED",
                message,
                fail_result(message=message, failures=[message], route=route, step="check_port", command_result=port_result),
            )
        if route.listen_port in parse_listening_ports(port_result.stdout):
            message = "socat 测试监听端口已被占用。"
            raise SSHReadError(
                "SOCAT_PORT_IN_USE",
                message,
                fail_result(message=message, failures=[message], route=route, step="check_port", command_result=port_result),
            )
        log_step(logger, level="info", step="check_port", message="socat 测试监听端口未被占用。")

        service_exists = run_read_only_command(transport, f"test -e {shlex.quote(route.service_path)}")
        if service_exists.exit_code == 0:
            message = "检测到同名 liveline-socat service，已拒绝覆盖。"
            raise SSHReadError(
                "SOCAT_SERVICE_ALREADY_EXISTS",
                message,
                fail_result(message=message, failures=[message], route=route, step="write_service"),
            )

        write_service_file(transport, service_path=route.service_path, content=build_service_file(route))
        service_written = True
        log_step(logger, level="info", step="write_service", message="socat systemd service 文件已写入。")

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
                route=route,
            )
            run_checked(
                transport,
                command=f"systemctl enable {shlex.quote(route.service_name)}",
                step="enable_service",
                timeout_seconds=timeout_seconds,
                logger=logger,
                success_message="socat service 已 enable。",
                error_code="SOCAT_SERVICE_ENABLE_FAILED",
                error_message="socat service enable 失败。",
                route=route,
            )
            run_checked(
                transport,
                command=f"systemctl start {shlex.quote(route.service_name)}",
                step="start_service",
                timeout_seconds=timeout_seconds,
                logger=logger,
                success_message="socat service 已 start。",
                error_code="SOCAT_SERVICE_START_FAILED",
                error_message="socat service start 失败。",
                route=route,
            )
            active_result = run_checked(
                transport,
                command=f"systemctl is-active {shlex.quote(route.service_name)}",
                step="verify_service",
                timeout_seconds=timeout_seconds,
                logger=logger,
                success_message="socat service 当前为 active。",
                error_code="SOCAT_SERVICE_NOT_ACTIVE",
                error_message="socat service 未 active。",
                route=route,
            )
            port_is_listening, _ = wait_for_listening_port(transport, listen_port=route.listen_port, logger=logger)
            if not port_is_listening:
                message = "socat 测试监听端口未进入 LISTEN 状态。"
                log_step(logger, level="error", step="verify_port", message=message)
                raise SSHReadError(
                    "SOCAT_PORT_NOT_LISTENING",
                    message,
                    fail_result(message=message, failures=[message], route=route, step="verify_port"),
                )
        except SSHReadError as exc:
            rollback_ok = rollback_socat_service(
                transport,
                service_name=route.service_name,
                service_path=route.service_path,
                timeout_seconds=timeout_seconds,
                logger=logger,
            )
            if exc.result_data is not None:
                exc.result_data["manual_cleanup_required"] = not rollback_ok
            raise

        return success_result(
            route=route,
            socat_version=socat_version,
            service_active=active_result.stdout.strip() == "active",
            listening=True,
        )
    except OSError as exc:
        rollback_ok = True
        if service_written and transport is not None:
            rollback_ok = rollback_socat_service(
                transport,
                service_name=route.service_name,
                service_path=route.service_path,
                timeout_seconds=timeout_seconds,
                logger=logger,
            )
        message = "写入 socat systemd service 文件失败。"
        raise SSHReadError(
            "SOCAT_SERVICE_WRITE_FAILED",
            message,
            fail_result(
                message=message,
                failures=[message],
                route=route,
                step="write_service",
                manual_cleanup_required=not rollback_ok,
            ),
        ) from exc
    finally:
        if transport is not None:
            with suppress(Exception):
                transport.close()
