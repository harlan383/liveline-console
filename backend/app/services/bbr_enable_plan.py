from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.vps_server import VpsServer
from app.models.worker import Worker
from app.models.worker_command import WorkerCommand
from app.services.worker_commands import create_worker_command
from app.services.worker_targeting import WorkerTargetResolution, resolve_command_target_worker


BBR_ENABLE_DRY_RUN_COMMAND = "bbr_enable_dry_run"
BBR_ENABLE_DRY_RUN_STAGE = "Stage 3.3.204-bbr-enable-protected-execution-dry-run"
BBR_ENABLE_REAL_EXECUTION_COMMAND = "bbr_enable_real_execution"
BBR_ENABLE_REAL_EXECUTION_STAGE = "Stage 3.3.205-bbr-enable-protected-real-execution"
BBR_ENABLE_REAL_EXECUTION_CONFIRMATION = "CONFIRM_ENABLE_BBR_ON_LANDING_VPS"
DANGEROUS_BBR_DRY_RUN_PAYLOAD_FIELDS = {
    "shell",
    "command",
    "commands",
    "args",
    "argv",
    "script",
    "exec",
    "exec_start",
    "systemd_unit",
    "unit_content",
    "service_content",
    "modprobe",
    "sysctl_write",
    "sysctl_reload",
    "write_file",
    "rm_rf",
}
DANGEROUS_BBR_REAL_EXECUTION_PAYLOAD_FIELDS = {
    "shell",
    "command",
    "commands",
    "args",
    "argv",
    "script",
    "exec",
    "exec_start",
    "systemd_unit",
    "unit_content",
    "service_content",
    "write_file",
    "rm_rf",
    "arbitrary_command",
    "arbitrary_script",
    "path",
    "content",
}


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


def latest_bbr_enable_dry_run_command(db: Session, server_id: str) -> WorkerCommand | None:
    return db.scalar(
        select(WorkerCommand)
        .where(
            WorkerCommand.server_type == "landing",
            WorkerCommand.server_id == server_id,
            WorkerCommand.command_type == BBR_ENABLE_DRY_RUN_COMMAND,
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


def build_bbr_enable_dry_run_payload(plan: dict) -> dict:
    payload = {
        "stage": BBR_ENABLE_DRY_RUN_STAGE,
        "server_id": plan["server_id"],
        "preflight_id": plan["latest_preflight_id"],
        "recommendation": plan["recommendation"],
        "confirm_dry_run_only": True,
        "confirm_no_modprobe": True,
        "confirm_no_sysctl_write": True,
        "confirm_no_sysctl_reload": True,
        "confirm_no_network_restart": True,
    }
    unexpected = DANGEROUS_BBR_DRY_RUN_PAYLOAD_FIELDS.intersection(payload)
    if unexpected:
        raise BbrEnablePlanError(500, "BBR_DRY_RUN_PAYLOAD_UNSAFE", "BBR dry-run payload contains unsafe fields.")
    return payload


def build_bbr_enable_real_execution_payload(plan: dict, dry_run_command: WorkerCommand, confirmation_text: str) -> dict:
    if confirmation_text != BBR_ENABLE_REAL_EXECUTION_CONFIRMATION:
        raise BbrEnablePlanError(
            400,
            "BBR_ENABLE_CONFIRMATION_REQUIRED",
            "请输入完整确认文本后才能创建 BBR 真实开启命令。",
        )
    payload = {
        "stage": BBR_ENABLE_REAL_EXECUTION_STAGE,
        "server_id": plan["server_id"],
        "preflight_id": plan["latest_preflight_id"],
        "dry_run_command_id": dry_run_command.id,
        "recommendation": plan["recommendation"],
        "confirm_enable_bbr_real_execution": True,
        "confirm_load_tcp_bbr_module": True,
        "confirm_write_sysctl_config": True,
        "confirm_reload_sysctl": True,
        "confirm_no_network_restart_expected": True,
        "confirm_rollback_plan_understood": True,
        "confirmation_text": BBR_ENABLE_REAL_EXECUTION_CONFIRMATION,
    }
    unexpected = DANGEROUS_BBR_REAL_EXECUTION_PAYLOAD_FIELDS.intersection(payload)
    if unexpected:
        raise BbrEnablePlanError(
            500,
            "BBR_REAL_EXECUTION_PAYLOAD_UNSAFE",
            "BBR real execution payload contains unsafe fields.",
        )
    return payload


def _validate_latest_bbr_enable_dry_run(dry_run: WorkerCommand | None, server_id: str) -> WorkerCommand:
    if not dry_run:
        raise BbrEnablePlanError(400, "BBR_ENABLE_DRY_RUN_REQUIRED", "需要先完成 BBR dry-run。")
    if dry_run.server_id != server_id or dry_run.server_type != "landing":
        raise BbrEnablePlanError(400, "BBR_ENABLE_DRY_RUN_REQUIRED", "最新 BBR dry-run 不属于当前落地服务器。")
    if dry_run.status != "succeeded":
        raise BbrEnablePlanError(
            400,
            "BBR_ENABLE_DRY_RUN_NOT_SUCCESSFUL",
            "最新 BBR dry-run 未成功，不能创建真实开启命令。",
        )
    result_json = dry_run.result_json if isinstance(dry_run.result_json, dict) else {}
    if result_json.get("status") != "succeeded":
        raise BbrEnablePlanError(
            400,
            "BBR_ENABLE_DRY_RUN_NOT_SUCCESSFUL",
            "最新 BBR dry-run 结果未通过，不能创建真实开启命令。",
        )
    blocked_reasons = result_json.get("blocked_reasons")
    if isinstance(blocked_reasons, list) and blocked_reasons:
        raise BbrEnablePlanError(
            400,
            "BBR_ENABLE_DRY_RUN_NOT_SUCCESSFUL",
            "最新 BBR dry-run 仍有阻塞项，不能创建真实开启命令。",
        )
    payload = dry_run.payload_json if isinstance(dry_run.payload_json, dict) else {}
    if payload.get("confirm_dry_run_only") is not True:
        raise BbrEnablePlanError(
            400,
            "BBR_ENABLE_DRY_RUN_NOT_SUCCESSFUL",
            "最新 BBR dry-run payload 不完整，不能创建真实开启命令。",
        )
    return dry_run


def create_bbr_enable_dry_run_command(db: Session, server_id: str) -> tuple[WorkerCommand, Worker, dict, WorkerTargetResolution]:
    plan = build_bbr_enable_plan(db, server_id)
    if plan.get("already_enabled") or not plan.get("ready"):
        raise BbrEnablePlanError(400, "BBR_ENABLE_PLAN_NOT_READY", "BBR 开启方案未就绪，不能创建 dry-run 命令。")

    target = resolve_command_target_worker(
        db,
        server_type="landing",
        server_id=server_id,
        role="landing",
        command_type=BBR_ENABLE_DRY_RUN_COMMAND,
    )
    payload = build_bbr_enable_dry_run_payload(plan)
    command = create_worker_command(db, target.worker, BBR_ENABLE_DRY_RUN_COMMAND, payload)
    return command, target.worker, plan, target


def create_bbr_enable_real_execution_command(
    db: Session,
    server_id: str,
    confirmation_text: str,
) -> tuple[WorkerCommand, Worker, dict, WorkerTargetResolution, WorkerCommand]:
    plan = build_bbr_enable_plan(db, server_id)
    if plan.get("already_enabled") or not plan.get("ready"):
        raise BbrEnablePlanError(400, "BBR_ENABLE_PLAN_NOT_READY", "BBR 开启方案未就绪，不能创建真实执行命令。")

    dry_run = _validate_latest_bbr_enable_dry_run(latest_bbr_enable_dry_run_command(db, server_id), server_id)
    target = resolve_command_target_worker(
        db,
        server_type="landing",
        server_id=server_id,
        role="landing",
        command_type=BBR_ENABLE_REAL_EXECUTION_COMMAND,
    )
    if dry_run.worker_id != target.worker.id:
        raise BbrEnablePlanError(
            400,
            "BBR_ENABLE_DRY_RUN_REQUIRED",
            "最新 BBR dry-run 不是由当前目标 Worker 执行，不能创建真实开启命令。",
        )
    payload = build_bbr_enable_real_execution_payload(plan, dry_run, confirmation_text)
    command = create_worker_command(db, target.worker, BBR_ENABLE_REAL_EXECUTION_COMMAND, payload)
    return command, target.worker, plan, target, dry_run
