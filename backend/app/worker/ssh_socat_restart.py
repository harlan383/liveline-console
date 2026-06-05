import shlex
from datetime import UTC, datetime
from typing import Any

from app.models.transit_route import TransitRoute
from app.worker.ssh_install import run_ssh_command
from app.worker.ssh_read import SSHReadError, run_read_only_command
from app.worker.ssh_transit_diagnose import compact_output, route_summary, run_diagnostic_command
from app.worker.ssh_transit_read import connect_transit_transport

RESTART_SOCAT_ROUTE_TASK_TYPE = "restart_socat_route"
SOCAT_TEST_LISTEN_PORT = 18443


def validate_restart_route(route: TransitRoute) -> None:
    if route.forwarding_method != "socat":
        raise SSHReadError(
            "SOCAT_ROUTE_REQUIRED",
            "只允许重启 socat 测试链路，禁止操作 gost 正式链路。",
        )
    if route.listen_port != SOCAT_TEST_LISTEN_PORT:
        raise SSHReadError(
            "SOCAT_TEST_PORT_REQUIRED",
            "只允许重启 18443 socat 测试链路。",
        )
    if not route.service_name:
        raise SSHReadError("SOCAT_SERVICE_MISSING", "socat 测试链路缺少 systemd service 名称。")


def restart_commands_for(route: TransitRoute) -> dict[str, str]:
    service_name = shlex.quote(route.service_name)
    target_host = shlex.quote(route.target_host)
    return {
        "restart_result": f"systemctl restart {service_name}",
        "service_status": f"systemctl status {service_name} --no-pager",
        "listen_check": f"ss -lntp | grep {int(route.listen_port)}",
        "target_connectivity": f"nc -vz {target_host} {int(route.target_port)}",
    }


def restart_socat_route_state(
    route: TransitRoute,
    private_key: str,
    passphrase: str | None,
) -> dict[str, Any]:
    validate_restart_route(route)
    resource = route.transit_resource
    if resource is None:
        raise SSHReadError("TRANSIT_RESOURCE_NOT_FOUND", "中转资源不存在。")

    commands = restart_commands_for(route)
    transport, host_fingerprint, ssh_key_fingerprint = connect_transit_transport(
        resource,
        private_key,
        passphrase,
    )
    try:
        restart_result_raw = run_ssh_command(transport, commands["restart_result"], timeout_seconds=30)
        restart_result = {
            "key": "restart_result",
            "command": commands["restart_result"],
            "exit_code": restart_result_raw.exit_code,
            "ok": restart_result_raw.exit_code == 0,
            "stdout": restart_result_raw.stdout,
            "stderr": restart_result_raw.stderr,
            "raw_output": compact_output(restart_result_raw),
        }
        checks = {
            "restart_result": restart_result,
            "service_status": run_diagnostic_command(transport, "service_status", commands["service_status"]),
            "listen_check": run_diagnostic_command(transport, "listen_check", commands["listen_check"]),
            "target_connectivity": run_diagnostic_command(
                transport,
                "target_connectivity",
                commands["target_connectivity"],
            ),
        }
    finally:
        transport.close()

    hints: list[str] = [
        f"本地 nc timeout：优先检查云安全组/云防火墙 TCP {route.listen_port} 是否放行。",
        "本机开代理客户端时，nc/curl 测试路径可能被代理规则污染。",
    ]
    if not checks["restart_result"]["ok"]:
        hints.append("restart_result 失败：socat 测试 service 重启失败。")
    if not checks["listen_check"]["ok"]:
        hints.append("监听不存在：转发服务可能未启动或已退出。")
    if not checks["target_connectivity"]["ok"]:
        hints.append("target nc 不通：中转机到落地机不通。")

    all_ok = all(check["ok"] for check in checks.values())
    return {
        "classification": "restart_socat_route",
        "restarted": all_ok,
        "passed": all_ok,
        "message": "socat 测试链路重启完成" if all_ok else "socat 测试链路重启后发现问题",
        "route": route_summary(route),
        "ssh": {
            "username": resource.ssh_username,
            "ssh_key_fingerprint": ssh_key_fingerprint,
            "host_key_fingerprint": host_fingerprint,
        },
        "checks": checks,
        "restart_result": checks["restart_result"],
        "service_status": checks["service_status"],
        "listen_check": checks["listen_check"],
        "target_connectivity": checks["target_connectivity"],
        "raw_output": {key: value["raw_output"] for key, value in checks.items()},
        "hints": hints,
        "warnings": [
            "本任务只重启 socat 18443 测试链路，不操作 gost 8443 正式链路。",
            f"请确认云服务器安全组/云防火墙已放行 TCP {route.listen_port}。",
        ],
        "failures": [] if all_ok else [hint for hint in hints if "失败" in hint or "不存在" in hint or "不通" in hint],
        "checked_at": datetime.now(UTC).isoformat(),
    }
