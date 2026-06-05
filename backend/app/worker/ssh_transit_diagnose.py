import shlex
from datetime import UTC, datetime
from typing import Any

from app.models.transit_route import TransitRoute
from app.services.task_logging import sanitize_log_text
from app.worker.ssh_read import CommandResult, SSHReadError, run_read_only_command
from app.worker.ssh_transit_read import connect_transit_transport

DIAGNOSE_ROUTE_TASK_TYPE = "diagnose_transit_route"
MAX_OUTPUT_CHARS = 4000


def compact_output(result: CommandResult) -> str:
    parts: list[str] = []
    if result.stdout:
        parts.append("stdout:\n" + result.stdout)
    if result.stderr:
        parts.append("stderr:\n" + result.stderr)
    if not parts:
        parts.append("(no output)")
    clean = sanitize_log_text("\n\n".join(parts)) or ""
    return clean[:MAX_OUTPUT_CHARS]


def route_summary(route: TransitRoute) -> dict[str, Any]:
    return {
        "id": route.id,
        "name": route.name,
        "transit_resource_id": route.transit_resource_id,
        "listen_port": route.listen_port,
        "target_host": route.target_host,
        "target_port": route.target_port,
        "forwarding_method": route.forwarding_method,
        "service_name": route.service_name,
        "status": route.status,
    }


def process_command_for(route: TransitRoute) -> str:
    if route.forwarding_method == "socat":
        return "ps -ef | grep '[s]ocat'"
    if route.forwarding_method == "gost":
        return "ps -ef | grep '[g]ost'"
    raise SSHReadError(
        "UNSUPPORTED_FORWARDING_METHOD",
        "只支持 gost / socat 中转线路只读诊断。",
    )


def diagnostic_commands_for(route: TransitRoute) -> dict[str, str]:
    listen_port = int(route.listen_port)
    target_port = int(route.target_port)
    target_host = shlex.quote(route.target_host)
    service_name = shlex.quote(route.service_name)
    return {
        "listen_check": f"ss -lntp | grep {listen_port}",
        "service_status": f"systemctl status {service_name} --no-pager",
        "target_connectivity": f"nc -vz {target_host} {target_port}",
        "process_check": process_command_for(route),
    }


def run_diagnostic_command(transport, key: str, command: str) -> dict[str, Any]:
    result = run_read_only_command(transport, command)
    return {
        "key": key,
        "command": command,
        "exit_code": result.exit_code,
        "ok": result.exit_code == 0,
        "stdout": sanitize_log_text(result.stdout) or "",
        "stderr": sanitize_log_text(result.stderr) or "",
        "raw_output": compact_output(result),
    }


def diagnose_transit_route_state(
    route: TransitRoute,
    private_key: str,
    passphrase: str | None,
) -> dict[str, Any]:
    resource = route.transit_resource
    if resource is None:
        raise SSHReadError("TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")

    commands = diagnostic_commands_for(route)
    transport, host_fingerprint, ssh_key_fingerprint = connect_transit_transport(
        resource,
        private_key,
        passphrase,
    )
    try:
        checks = {
            key: run_diagnostic_command(transport, key, command)
            for key, command in commands.items()
        }
    finally:
        transport.close()

    hints: list[str] = [
        f"本地 nc timeout：优先检查云安全组/云防火墙 TCP {route.listen_port} 是否放行。",
        "本机开代理客户端时，nc/curl 测试路径可能被代理规则污染。",
    ]
    if not checks["listen_check"]["ok"]:
        hints.append("监听不存在：转发服务可能未启动或已退出。")
    if not checks["target_connectivity"]["ok"]:
        hints.append("target nc 不通：中转机到落地机不通。")

    all_ok = all(check["ok"] for check in checks.values())
    return {
        "classification": "diagnose_transit_route",
        "diagnosed": True,
        "passed": all_ok,
        "message": "中转线路只读诊断完成" if all_ok else "中转线路只读诊断发现问题",
        "route": route_summary(route),
        "ssh": {
            "username": resource.ssh_username,
            "ssh_key_fingerprint": ssh_key_fingerprint,
            "host_key_fingerprint": host_fingerprint,
        },
        "checks": checks,
        "raw_output": {key: value["raw_output"] for key, value in checks.items()},
        "hints": hints,
        "warnings": [
            "本任务只执行白名单只读诊断命令，不停止、不删除、不重启、不创建线路。",
            f"请确认云服务器安全组/云防火墙已放行 TCP {route.listen_port}。",
        ],
        "failures": [] if all_ok else [hint for hint in hints if "不存在" in hint or "不通" in hint],
        "checked_at": datetime.now(UTC).isoformat(),
    }
