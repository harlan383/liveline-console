from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.vps_server import VpsServer
from app.models.worker_command import WorkerCommand


class BbrEnablePlanError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


SAFETY_BOUNDARY = [
    "readonly plan only",
    "no worker command created",
    "no remote execution",
    "no modprobe",
    "no sysctl write",
    "no sysctl reload",
    "no service restart",
    "no port/share_link/cutover changes",
]


def latest_landing_preflight_command(db: Session, server_id: str) -> WorkerCommand | None:
    return db.scalar(
        select(WorkerCommand)
        .where(
            WorkerCommand.server_type == "landing",
            WorkerCommand.server_id == server_id,
            WorkerCommand.command_type == "landing_preflight",
            WorkerCommand.status == "succeeded",
        )
        .order_by(WorkerCommand.completed_at.desc().nullslast(), WorkerCommand.created_at.desc())
        .limit(1)
    )


def _text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _bool(value: Any) -> bool:
    return value is True


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _available_control_contains_bbr(value: Any) -> bool:
    text = _text(value).lower()
    return "bbr" in {item.strip() for item in text.split()}


def _planned_action(step: str, *, command_preview: str | None = None, path_preview: str | None = None) -> dict:
    action = {"step": step, "executed": False}
    if command_preview:
        action["command_preview"] = command_preview
    if path_preview:
        action["path_preview"] = path_preview
    return action


def _persist_and_verify_actions() -> list[dict]:
    return [
        _planned_action(
            "persist_default_qdisc_fq",
            path_preview="/etc/sysctl.d/99-liveline-bbr.conf",
            command_preview="net.core.default_qdisc=fq",
        ),
        _planned_action(
            "persist_congestion_control_bbr",
            path_preview="/etc/sysctl.d/99-liveline-bbr.conf",
            command_preview="net.ipv4.tcp_congestion_control=bbr",
        ),
        _planned_action("reload_sysctl", command_preview="sysctl --system"),
        _planned_action("verify_available_congestion_control", command_preview="sysctl net.ipv4.tcp_available_congestion_control"),
        _planned_action("verify_current_congestion_control", command_preview="sysctl net.ipv4.tcp_congestion_control"),
    ]


def _blocked_plan(
    *,
    server_id: str,
    preflight: WorkerCommand | None,
    bbr: dict[str, Any] | None,
    recommendation: str,
    blocked_reasons: list[str],
) -> dict:
    preflight_at = None
    if preflight:
        timestamp = preflight.completed_at or preflight.created_at
        preflight_at = timestamp.isoformat() if timestamp else None
    return {
        "ready": False,
        "already_enabled": False,
        "server_id": server_id,
        "latest_preflight_id": preflight.id if preflight else None,
        "latest_preflight_at": preflight_at,
        "bbr": bbr or {},
        "recommendation": recommendation,
        "blocked_reasons": blocked_reasons,
        "warnings": [],
        "planned_actions": [],
        "required_confirmations": [],
        "safety_boundary": SAFETY_BOUNDARY,
    }


def build_bbr_enable_plan(db: Session, server_id: str) -> dict:
    server = db.get(VpsServer, server_id)
    if not server or server.status == "deleted":
        raise BbrEnablePlanError(404, "VPS_NOT_FOUND", "落地服务器记录不存在。")

    preflight = latest_landing_preflight_command(db, server_id)
    if not preflight:
        return _blocked_plan(
            server_id=server_id,
            preflight=None,
            bbr=None,
            recommendation="latest_landing_preflight_required",
            blocked_reasons=["latest_landing_preflight_required"],
        )

    preflight_at_value = preflight.completed_at or preflight.created_at
    preflight_at = preflight_at_value.isoformat() if preflight_at_value else None
    result_json = preflight.result_json if isinstance(preflight.result_json, dict) else {}
    bbr = result_json.get("bbr")
    if not isinstance(bbr, dict):
        return _blocked_plan(
            server_id=server_id,
            preflight=preflight,
            bbr=None,
            recommendation="bbr_readonly_result_required",
            blocked_reasons=["bbr_readonly_result_required"],
        )

    current_is_bbr = _bool(bbr.get("current_is_bbr")) or _text(bbr.get("current_congestion_control")).lower() == "bbr"
    if current_is_bbr:
        return {
            "ready": False,
            "already_enabled": True,
            "server_id": server_id,
            "latest_preflight_id": preflight.id,
            "latest_preflight_at": preflight_at,
            "bbr": bbr,
            "recommendation": "already_enabled",
            "blocked_reasons": [],
            "warnings": [],
            "planned_actions": [],
            "required_confirmations": [],
            "safety_boundary": SAFETY_BOUNDARY,
        }

    module_files = _text_list(bbr.get("module_files"))
    available_contains_bbr = _bool(bbr.get("available_contains_bbr")) or _available_control_contains_bbr(
        bbr.get("available_congestion_control")
    )
    module_available = (
        _bool(bbr.get("module_available"))
        or _bool(bbr.get("modinfo_available"))
        or _text(bbr.get("modinfo_status")).lower() == "available"
        or bool(module_files)
    )
    module_loaded = _bool(bbr.get("module_loaded")) or bbr.get("module_status") == "loaded"

    if available_contains_bbr:
        return {
            "ready": True,
            "already_enabled": False,
            "server_id": server_id,
            "latest_preflight_id": preflight.id,
            "latest_preflight_at": preflight_at,
            "bbr": bbr,
            "recommendation": "can_enable_with_approval",
            "blocked_reasons": [],
            "warnings": [],
            "planned_actions": _persist_and_verify_actions(),
            "required_confirmations": [
                "confirm_write_sysctl_config",
                "confirm_reload_sysctl",
                "confirm_no_network_restart_expected",
                "confirm_rollback_plan_understood",
            ],
            "safety_boundary": SAFETY_BOUNDARY,
        }

    if module_available and not module_loaded:
        return {
            "ready": True,
            "already_enabled": False,
            "server_id": server_id,
            "latest_preflight_id": preflight.id,
            "latest_preflight_at": preflight_at,
            "bbr": bbr,
            "recommendation": "module_available_needs_load_approval",
            "blocked_reasons": [],
            "warnings": ["tcp_bbr_module_not_loaded"],
            "planned_actions": [_planned_action("load_tcp_bbr_module", command_preview="modprobe tcp_bbr")]
            + _persist_and_verify_actions(),
            "required_confirmations": [
                "confirm_load_tcp_bbr_module",
                "confirm_write_sysctl_config",
                "confirm_reload_sysctl",
                "confirm_no_network_restart_expected",
                "confirm_rollback_plan_understood",
            ],
            "safety_boundary": SAFETY_BOUNDARY,
        }

    return _blocked_plan(
        server_id=server_id,
        preflight=preflight,
        bbr=bbr,
        recommendation="bbr_not_available",
        blocked_reasons=["bbr_not_available"],
    )
