import uuid
from contextlib import suppress
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.redis import get_redis_client
from app.models.node import Node
from app.models.task import Task
from app.models.transit_resource import TransitResource
from app.models.transit_route import TransitRoute
from app.models.vps_server import VpsServer
from app.services.credentials import (
    TempCredentialDecryptFailed,
    TempCredentialExpired,
    pop_temp_credential,
)
from app.services.task_logging import add_task_log, sanitize_log_text, update_task
from app.worker.ssh_create_direct import build_direct_node_params, create_direct_node_state
from app.worker.ssh_gost_install import install_gost_state
from app.worker.ssh_install import install_xray_state
from app.worker.ssh_node_delete import delete_node_state
from app.worker.ssh_node_manage import refresh_node_state, restart_xray_state
from app.worker.ssh_prepare import prepare_node_state
from app.worker.ssh_read import SSHReadError, check_vps_ssh_state, read_vps_state
from app.worker.ssh_socat_install import install_socat_state
from app.worker.ssh_socat_restart import restart_socat_route_state
from app.worker.ssh_socat_route import cleanup_socat_service, create_socat_route_state, route_summary
from app.worker.ssh_transit_diagnose import diagnose_transit_route_state
from app.worker.ssh_transit_read import read_transit_server_state
from app.worker.ssh_transit_route import cleanup_transit_service, create_transit_route_state
from app.worker.ssh_xray_backups import (
    delete_xray_backup_candidate_state,
    list_xray_backups_state,
    preview_xray_backup_cleanup_state,
)


def stage0_ping() -> str:
    return "pong"


def fail_task(
    db: Session,
    task: Task,
    *,
    error_code: str,
    error_message: str,
    result_data: dict | None = None,
) -> None:
    add_task_log(
        db,
        task.id,
        level="error",
        step=task.current_step or "failed",
        message=error_message,
    )
    update_task(
        db,
        task,
        status="failed",
        progress=100,
        error_code=error_code,
        error_message=error_message,
        result_data=result_data or {},
        finish=True,
    )
    db.commit()


def safe_worker_error_message(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    return sanitize_log_text(text) or "任务执行失败。"


def latest_prepare_task(db: Session, vps_id: str) -> Task | None:
    return db.scalar(
        select(Task)
        .where(
            Task.vps_id == vps_id,
            Task.task_type == "prepare_node",
            Task.status == "success",
        )
        .order_by(Task.created_at.desc())
    )


def install_warnings_from_prepare(task: Task | None) -> list[str]:
    result_data = task.result_data if task else None
    if not isinstance(result_data, dict):
        return []
    warnings = result_data.get("warnings")
    if isinstance(warnings, list):
        return [item for item in warnings if isinstance(item, str)]
    failures = result_data.get("failures")
    if isinstance(failures, list):
        return [
            item
            for item in failures
            if isinstance(item, str) and item.startswith("常用端口被占用")
        ]
    return []


def vps_is_installed_pending_config(vps: VpsServer | None) -> bool:
    return bool(
        vps
        and vps.xray_installed
        and (
            not vps.xray_config_path
            or vps.status in {"xray_installed", "xray_installed_pending_config"}
        )
    )


def prepare_result_allows_install(
    task: Task | None,
    vps: VpsServer | None = None,
) -> tuple[bool, str, str]:
    result_data = task.result_data if task else None
    if not isinstance(result_data, dict):
        if vps_is_installed_pending_config(vps):
            return True, "", ""
        return False, "PREPARE_NODE_REQUIRED", "请先完成安装前检查。"

    system = result_data.get("system")
    xray = result_data.get("xray")
    if not isinstance(system, dict) or not isinstance(xray, dict):
        if vps_is_installed_pending_config(vps):
            return True, "", ""
        return False, "PREPARE_NODE_INVALID", "安装前检查结果不完整。"

    if system.get("whoami") != "root" or system.get("is_root") is not True:
        return False, "NO_ROOT_PERMISSION", "安装 Xray 需要 root 用户。"
    if system.get("systemd_available") is not True:
        return False, "SYSTEMD_UNAVAILABLE", "systemd 不可用，不能安装 Xray。"
    if system.get("supported") is not True:
        return False, "UNSUPPORTED_OS", "系统版本不支持安装。"

    if xray.get("installed") is True:
        return True, "", ""

    if result_data.get("passed") is not True:
        if vps_is_installed_pending_config(vps):
            return True, "", ""
        return False, "PREPARE_NODE_NOT_PASSED", "最近一次安装前检查未通过。"

    return True, "", ""


def update_vps_ssh_check(
    db: Session,
    vps: VpsServer,
    *,
    status: str,
    error: str | None = None,
) -> None:
    vps.last_ssh_status = status
    vps.last_ssh_check_at = datetime.now(UTC)
    vps.last_ssh_error = error
    db.add(vps)


def check_vps_ssh_job(task_id: str, vps_id: str, temp_credential_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        vps = db.get(VpsServer, vps_id)
        if not task or not vps:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            message = "临时 SSH Key 已过期，请重新提交。"
            update_vps_ssh_check(db, vps, status="offline", error=message)
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message=message,
                result_data={"message": message, "last_ssh_status": "offline"},
            )
            return
        except TempCredentialDecryptFailed:
            message = "临时 SSH Key 解密失败。"
            update_vps_ssh_check(db, vps, status="offline", error=message)
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message=message,
                result_data={"message": message, "last_ssh_status": "offline"},
            )
            return

        update_task(db, task, step="ssh_connect", progress=35)
        add_task_log(db, task.id, level="info", step="ssh_connect", message="开始 SSH 握手检测。")
        db.commit()

        try:
            result = check_vps_ssh_state(vps, private_key, passphrase)
        except SSHReadError as exc:
            safe_message = exc.message
            update_vps_ssh_check(db, vps, status="offline", error=safe_message)
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=safe_message,
                result_data={
                    "message": safe_message,
                    "last_ssh_status": "offline",
                    "failures": [safe_message],
                },
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=85)
        add_task_log(db, task.id, level="info", step="save_result", message="保存 SSH 握手结果。")

        vps.ssh_key_fingerprint = result["ssh"]["ssh_key_fingerprint"]
        if not vps.ssh_host_key_fingerprint:
            vps.ssh_host_key_fingerprint = result["ssh"]["host_key_fingerprint"]
        update_vps_ssh_check(db, vps, status="online", error=None)
        result["last_ssh_status"] = "online"

        add_task_log(
            db,
            task.id,
            level="info",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def read_node_job(task_id: str, vps_id: str, temp_credential_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        vps = db.get(VpsServer, vps_id)
        if not task or not vps:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="ssh_connect", progress=25)
        add_task_log(db, task.id, level="info", step="ssh_connect", message="开始 SSH 只读连接。")
        db.commit()

        try:
            result = read_vps_state(vps, private_key, passphrase)
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=85)
        add_task_log(db, task.id, level="info", step="save_result", message="保存读取结果。")

        vps.os_name = result["system"]["name"]
        vps.os_version = result["system"]["version_id"]
        vps.ssh_key_fingerprint = result["ssh"]["ssh_key_fingerprint"]
        if not vps.ssh_host_key_fingerprint:
            vps.ssh_host_key_fingerprint = result["ssh"]["host_key_fingerprint"]
        vps.xray_installed = result["xray"]["installed"]
        vps.xray_config_path = (
            result["xray"]["standard_config_path"]
            if result["xray"]["standard_config_exists"]
            else None
        )
        vps.status = (
            "configured"
            if result["xray"]["installed"] and result["xray"]["standard_config_exists"]
            else "unconfigured"
        )
        vps.last_synced_at = datetime.now(UTC)
        db.add(vps)

        add_task_log(
            db,
            task.id,
            level="info",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def install_xray_job(task_id: str, vps_id: str, temp_credential_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        vps = db.get(VpsServer, vps_id)
        if not task or not vps:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        prepare_task = latest_prepare_task(db, vps.id)
        allowed, error_code, error_message = prepare_result_allows_install(prepare_task, vps)
        warnings = install_warnings_from_prepare(prepare_task)
        if not allowed:
            private_key = ""
            passphrase = None
            fail_task(
                db,
                task,
                error_code=error_code,
                error_message=error_message,
                result_data={
                    "classification": "install_xray",
                    "installed": False,
                    "message": error_message,
                    "warnings": warnings,
                    "failures": [error_message],
                },
            )
            return

        update_task(db, task, step="preflight", progress=20)
        add_task_log(
            db,
            task.id,
            level="info",
            step="preflight",
            message="开始安装前最终校验。",
        )
        db.commit()

        def log_command(level: str, step: str, message: str, raw_output: str | None) -> None:
            add_task_log(db, task.id, level=level, step=step, message=message, raw_output=raw_output)
            db.commit()

        try:
            result = install_xray_state(
                vps,
                private_key,
                passphrase,
                warnings=warnings,
                logger=log_command,
            )
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=90)
        add_task_log(db, task.id, level="info", step="save_result", message="保存 Xray 安装结果。")

        vps.ssh_key_fingerprint = result["ssh"]["ssh_key_fingerprint"]
        if not vps.ssh_host_key_fingerprint:
            vps.ssh_host_key_fingerprint = result["ssh"]["host_key_fingerprint"]
        vps.xray_installed = result["installed"]
        vps.xray_config_path = (
            result["xray"]["config_path"] if result["xray"]["config_exists"] else None
        )
        if result["installed"] and result["xray"]["config_exists"]:
            vps.status = "xray_installed"
        elif result["installed"]:
            vps.status = "xray_installed_pending_config"
        vps.last_synced_at = datetime.now(UTC)
        db.add(vps)

        add_task_log(
            db,
            task.id,
            level="info",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def create_direct_node_job(
    task_id: str,
    vps_id: str,
    temp_credential_id: str,
    node_params: dict,
) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        vps = db.get(VpsServer, vps_id)
        if not task or not vps:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        active_node = db.scalar(
            select(Node).where(
                Node.vps_id == vps.id,
                Node.status == "active",
                Node.deleted_at.is_(None),
            )
        )
        if active_node:
            private_key = ""
            passphrase = None
            fail_task(
                db,
                task,
                error_code="ACTIVE_NODE_EXISTS",
                error_message="该 VPS 已存在 active 节点。",
                result_data={
                    "classification": "create_direct_node",
                    "created": False,
                    "message": "该 VPS 已存在 active 节点。",
                    "warnings": [],
                    "failures": ["该 VPS 已存在 active 节点"],
                },
            )
            return

        update_task(db, task, step="create_direct_node", progress=25)
        add_task_log(
            db,
            task.id,
            level="info",
            step="create_direct_node",
            message="开始创建直连 VLESS Reality 节点。",
        )
        db.commit()

        params = build_direct_node_params(**node_params)

        def log_command(level: str, step: str, message: str, raw_output: str | None) -> None:
            add_task_log(db, task.id, level=level, step=step, message=message, raw_output=raw_output)
            db.commit()

        try:
            result = create_direct_node_state(
                vps,
                private_key,
                passphrase,
                params,
                logger=log_command,
            )
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_node", progress=90)
        add_task_log(db, task.id, level="info", step="save_node", message="保存节点记录。")

        node_data = result["node"]
        node = Node(
            vps_id=vps.id,
            node_name=params.node_name,
            protocol="vless",
            transport="tcp",
            security="reality",
            flow=params.flow,
            xray_port=params.listen_port,
            uuid=params.client_uuid,
            reality_public_key=node_data["reality_public_key"],
            reality_short_id=params.reality_short_id,
            sni=params.reality_server_name,
            dest=params.reality_dest,
            share_link=node_data["share_link"],
            fingerprint=node_data["fingerprint"],
            service_status="active",
            connectivity_status="unknown",
            source="create_direct_node",
            status="active",
            last_remote_check_at=datetime.now(UTC),
            last_sync_status="created",
        )
        db.add(node)
        db.flush()

        task.node_id = node.id
        vps.status = "configured"
        vps.xray_installed = True
        vps.xray_config_path = result["xray"]["config_path"]
        vps.last_synced_at = datetime.now(UTC)
        db.add(vps)

        add_task_log(
            db,
            task.id,
            level="info",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def refresh_node_job(task_id: str, node_id: str, temp_credential_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        node = db.get(Node, node_id)
        vps = db.get(VpsServer, node.vps_id) if node else None
        if not task or not node or not vps:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            node.status = "error"
            db.add(node)
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            node.status = "error"
            db.add(node)
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="refresh_checks", progress=30)
        add_task_log(db, task.id, level="info", step="refresh_checks", message="开始刷新节点状态。")
        db.commit()

        try:
            result = refresh_node_state(vps, node, private_key, passphrase)
        except SSHReadError as exc:
            node.status = "error"
            node.service_status = "error"
            node.connectivity_status = "error"
            node.last_remote_check_at = datetime.now(UTC)
            node.last_sync_status = exc.error_code
            db.add(node)
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_status", progress=85)
        add_task_log(db, task.id, level="info", step="save_status", message="保存节点状态。")

        healthy = result["node"]["status"] == "active"
        node.status = "active" if healthy else "error"
        node.service_status = "active" if result["xray"]["service_active"] else "inactive"
        node.connectivity_status = "listening" if result["xray"]["listening"] else "not_listening"
        node.last_remote_check_at = datetime.now(UTC)
        node.last_sync_status = "ok" if healthy else "error"
        db.add(node)

        add_task_log(
            db,
            task.id,
            level="info" if healthy else "warning",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def restart_xray_job(task_id: str, node_id: str, temp_credential_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        node = db.get(Node, node_id)
        vps = db.get(VpsServer, node.vps_id) if node else None
        if not task or not node or not vps:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            node.status = "error"
            db.add(node)
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            node.status = "error"
            db.add(node)
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="restart_xray", progress=30)
        add_task_log(
            db,
            task.id,
            level="info",
            step="restart_xray",
            message="开始测试配置并重启 Xray。",
        )
        db.commit()

        try:
            result = restart_xray_state(vps, node, private_key, passphrase)
        except SSHReadError as exc:
            node.status = "error"
            node.service_status = "error"
            node.connectivity_status = "error"
            node.last_remote_check_at = datetime.now(UTC)
            node.last_sync_status = exc.error_code
            db.add(node)
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_status", progress=85)
        add_task_log(db, task.id, level="info", step="save_status", message="保存重启后的节点状态。")

        healthy = result["node"]["status"] == "active"
        node.status = "active" if healthy else "error"
        node.service_status = "active" if result["xray"]["service_active"] else "inactive"
        node.connectivity_status = "listening" if result["xray"]["listening"] else "not_listening"
        node.last_remote_check_at = datetime.now(UTC)
        node.last_sync_status = "ok" if healthy else "error"
        db.add(node)

        add_task_log(
            db,
            task.id,
            level="info" if healthy else "warning",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def delete_node_job(
    task_id: str,
    node_id: str,
    temp_credential_id: str,
    confirmation: dict | None = None,
) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        node = db.get(Node, node_id)
        vps = db.get(VpsServer, node.vps_id) if node else None
        if not task or not node or not vps:
            return

        if not confirmation or confirmation.get("confirm") is not True:
            fail_task(
                db,
                task,
                error_code="CONFIRMATION_REQUIRED",
                error_message="缺少删除确认字段。",
                result_data={
                    "classification": "delete_node",
                    "deleted": False,
                    "message": "缺少删除确认字段。",
                    "warnings": [],
                    "failures": ["缺少删除确认字段"],
                },
            )
            return

        if node.deleted_at is not None or node.status != "active":
            fail_task(
                db,
                task,
                error_code="NODE_NOT_ACTIVE",
                error_message="只能删除 active 节点。",
                result_data={
                    "classification": "delete_node",
                    "deleted": False,
                    "message": "只能删除 active 节点。",
                    "node": {
                        "id": node.id,
                        "name": node.node_name,
                        "status": node.status,
                    },
                    "warnings": [],
                    "failures": ["节点不是 active 状态"],
                },
            )
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="delete_node", progress=25)
        add_task_log(db, task.id, level="info", step="delete_node", message="开始软删除节点。")
        db.commit()

        def log_command(level: str, step: str, message: str, raw_output: str | None) -> None:
            add_task_log(db, task.id, level=level, step=step, message=message, raw_output=raw_output)
            db.commit()

        try:
            result = delete_node_state(
                vps,
                node,
                private_key,
                passphrase,
                logger=log_command,
            )
        except SSHReadError as exc:
            if exc.result_data.get("node", {}).get("status") == "error":
                node.status = "error"
                node.service_status = "error"
                node.connectivity_status = "error"
                node.last_remote_check_at = datetime.now(UTC)
                node.last_sync_status = exc.error_code
                db.add(node)
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=85)
        add_task_log(db, task.id, level="info", step="save_result", message="保存节点软删除结果。")

        deleted_at = datetime.now(UTC)
        result["node"]["deleted_at"] = deleted_at.isoformat()
        node.status = "deleted"
        node.deleted_at = deleted_at
        node.service_status = "inactive"
        node.connectivity_status = "not_listening"
        node.last_remote_check_at = deleted_at
        node.last_sync_status = "deleted"
        db.add(node)

        vps.status = "xray_installed_pending_config"
        vps.xray_installed = True
        vps.xray_config_path = None
        vps.last_synced_at = deleted_at
        db.add(vps)

        add_task_log(
            db,
            task.id,
            level="info",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            task = db.get(Task, task_id)
            node = db.get(Node, node_id)
            if task:
                result["warnings"].append(
                    "远端配置已停用，但数据库保存失败，请按 backup_path / disabled_path 手动核对。"
                )
                add_task_log(
                    db,
                    task.id,
                    level="error",
                    step="save_result",
                    message="严重不一致：远端配置已停用，但数据库保存失败。",
                )
                if node:
                    node.status = "error"
                    node.service_status = "error"
                    node.connectivity_status = "error"
                    node.last_sync_status = "DATABASE_SAVE_FAILED_AFTER_REMOTE_DELETE"
                    db.add(node)
                fail_task(
                    db,
                    task,
                    error_code="DATABASE_SAVE_FAILED_AFTER_REMOTE_DELETE",
                    error_message="远端配置已停用，但数据库保存失败，请手动核对。",
                    result_data=result,
                )
    finally:
        db.close()


def list_xray_backups_job(task_id: str, vps_id: str, temp_credential_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        vps = db.get(VpsServer, vps_id)
        if not task or not vps:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="list_xray_backups", progress=20)
        add_task_log(
            db,
            task.id,
            level="info",
            step="list_xray_backups",
            message="开始只读查看 Xray 备份文件。",
        )
        db.commit()

        def log_step(level: str, step: str, message: str) -> None:
            add_task_log(db, task.id, level=level, step=step, message=message)
            db.commit()

        try:
            result = list_xray_backups_state(
                vps,
                private_key,
                passphrase,
                logger=log_step,
            )
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=85)
        add_task_log(db, task.id, level="info", step="save_result", message="保存备份文件查看结果。")

        add_task_log(
            db,
            task.id,
            level="info",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def preview_xray_backup_cleanup_job(task_id: str, vps_id: str, temp_credential_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        vps = db.get(VpsServer, vps_id)
        if not task or not vps:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="preview_xray_backup_cleanup", progress=20)
        add_task_log(
            db,
            task.id,
            level="info",
            step="preview_xray_backup_cleanup",
            message="开始只读计算 Xray 备份清理预览。",
        )
        db.commit()

        def log_step(level: str, step: str, message: str) -> None:
            add_task_log(db, task.id, level=level, step=step, message=message)
            db.commit()

        try:
            result = preview_xray_backup_cleanup_state(
                vps,
                private_key,
                passphrase,
                logger=log_step,
            )
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=85)
        add_task_log(db, task.id, level="info", step="save_result", message="保存备份清理预览结果。")

        add_task_log(
            db,
            task.id,
            level="info",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def delete_xray_backup_candidate_job(
    task_id: str,
    vps_id: str,
    temp_credential_id: str,
    filename: str,
    confirm: bool,
    confirm_filename: str,
) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        vps = db.get(VpsServer, vps_id)
        if not task or not vps:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="delete_xray_backup_candidate", progress=20)
        add_task_log(
            db,
            task.id,
            level="info",
            step="delete_xray_backup_candidate",
            message="开始删除单个 failed 备份候选文件。",
        )
        db.commit()

        def log_step(level: str, step: str, message: str) -> None:
            add_task_log(db, task.id, level=level, step=step, message=message)
            db.commit()

        try:
            result = delete_xray_backup_candidate_state(
                vps,
                private_key,
                passphrase,
                filename=filename,
                confirm=confirm,
                confirm_filename=confirm_filename,
                logger=log_step,
            )
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=85)
        add_task_log(db, task.id, level="info", step="save_result", message="保存 failed 备份删除结果。")

        add_task_log(
            db,
            task.id,
            level="info",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def prepare_node_job(task_id: str, vps_id: str, temp_credential_id: str) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        vps = db.get(VpsServer, vps_id)
        if not task or not vps:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="prepare_checks", progress=25)
        add_task_log(
            db,
            task.id,
            level="info",
            step="prepare_checks",
            message="开始执行安装前只读检查。",
        )
        db.commit()

        try:
            result = prepare_node_state(vps, private_key, passphrase)
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=85)
        add_task_log(db, task.id, level="info", step="save_result", message="保存安装前检查结果。")

        vps.os_name = result["system"]["name"]
        vps.os_version = result["system"]["version_id"]
        vps.ssh_key_fingerprint = result["ssh"]["ssh_key_fingerprint"]
        if not vps.ssh_host_key_fingerprint:
            vps.ssh_host_key_fingerprint = result["ssh"]["host_key_fingerprint"]
        vps.xray_installed = result["xray"]["installed"]
        vps.status = "configured" if result["xray"]["installed"] else "unconfigured"
        vps.last_synced_at = datetime.now(UTC)
        db.add(vps)

        add_task_log(
            db,
            task.id,
            level="info" if result["passed"] else "warning",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def read_transit_server_job(
    task_id: str,
    transit_resource_id: str,
    temp_credential_id: str,
) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        resource = db.get(TransitResource, transit_resource_id)
        if not task or not resource:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="read_transit_server", progress=20)
        add_task_log(
            db,
            task.id,
            level="info",
            step="read_transit_server",
            message="开始执行中转服务器只读检查。",
        )
        update_task(db, task, step="ssh_connect", progress=30)
        add_task_log(db, task.id, level="info", step="ssh_connect", message="开始 SSH 只读连接。")
        db.commit()

        try:
            result = read_transit_server_state(resource, private_key, passphrase)
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        add_task_log(db, task.id, level="info", step="read_system", message="系统信息读取完成。")
        add_task_log(db, task.id, level="info", step="check_tools", message="转发工具状态只读检查完成。")
        add_task_log(db, task.id, level="info", step="check_ports", message="TCP 监听端口只读检查完成。")
        add_task_log(db, task.id, level="info", step="check_firewall", message="防火墙状态只读检查完成。")

        update_task(db, task, step="save_result", progress=85)
        add_task_log(db, task.id, level="info", step="save_result", message="保存中转服务器只读检查结果。")

        add_task_log(
            db,
            task.id,
            level="info" if not result["failures"] else "warning",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def install_gost_job(
    task_id: str,
    transit_resource_id: str,
    temp_credential_id: str,
) -> None:
    db = SessionLocal()
    try:
        task = db.get(Task, task_id)
        resource = db.get(TransitResource, transit_resource_id)
        if not task or not resource:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="install_gost", progress=20)
        add_task_log(
            db,
            task.id,
            level="info",
            step="install_gost",
            message="开始安装 gost binary。本阶段不创建转发规则。",
        )
        update_task(db, task, step="ssh_connect", progress=25)
        add_task_log(
            db,
            task.id,
            level="info",
            step="ssh_connect",
            message=(
                "开始 SSH 连接："
                f"host={resource.ssh_host or '-'}，"
                f"port={resource.ssh_port or '-'}，"
                f"username={resource.ssh_username or '-'}。"
            ),
        )
        db.commit()

        progress_map = {
            "preflight": 35,
            "check_existing_gost": 45,
            "download_gost": 55,
            "verify_download": 65,
            "install_binary": 75,
            "verify_gost": 85,
        }

        def log_command(level: str, step: str, message: str, raw_output: str | None) -> None:
            update_task(db, task, step=step, progress=progress_map.get(step, task.progress))
            add_task_log(db, task.id, level=level, step=step, message=message, raw_output=raw_output)
            db.commit()

        try:
            result = install_gost_state(
                resource,
                private_key,
                passphrase,
                logger=log_command,
            )
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=95)
        add_task_log(db, task.id, level="info", step="save_result", message="保存 gost 安装结果。")

        add_task_log(
            db,
            task.id,
            level="info" if not result["failures"] else "warning",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    finally:
        db.close()


def install_socat_job(
    task_id: str,
    transit_resource_id: str,
    temp_credential_id: str,
) -> None:
    db = SessionLocal()
    task: Task | None = None
    private_key = ""
    passphrase = None
    try:
        task = db.get(Task, task_id)
        resource = db.get(TransitResource, transit_resource_id)
        if not task or not resource:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="install_socat", progress=20)
        add_task_log(
            db,
            task.id,
            level="info",
            step="install_socat",
            message="开始安装/检查 socat。本阶段不创建转发规则。",
        )
        update_task(db, task, step="ssh_connect", progress=25)
        add_task_log(db, task.id, level="info", step="ssh_connect", message="开始 SSH 连接。")
        db.commit()

        progress_map = {
            "preflight": 35,
            "check_existing_socat": 50,
            "install_package": 70,
            "verify_socat": 85,
        }

        def log_command(level: str, step: str, message: str, raw_output: str | None) -> None:
            update_task(db, task, step=step, progress=progress_map.get(step, task.progress))
            add_task_log(db, task.id, level=level, step=step, message=message, raw_output=raw_output)
            db.commit()

        try:
            result = install_socat_state(
                resource,
                private_key,
                passphrase,
                logger=log_command,
            )
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return
        except Exception as exc:
            message = safe_worker_error_message(exc)
            failed_step = task.current_step or "install_socat"
            fail_task(
                db,
                task,
                error_code="INSTALL_SOCAT_FAILED",
                error_message=message,
                result_data={
                    "classification": "install_socat",
                    "ok": False,
                    "installed": False,
                    "already_installed": False,
                    "error_code": "INSTALL_SOCAT_FAILED",
                    "failed_step": failed_step,
                    "message": message,
                    "socat": {"path": None, "version": None},
                    "system": {},
                    "warnings": ["本阶段只安装/检查 socat，不创建转发规则"],
                    "failures": [message],
                    "checked_at": datetime.now(UTC).isoformat(),
                },
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=95)
        add_task_log(db, task.id, level="info", step="save_result", message="保存 socat 安装/检查结果。")

        add_task_log(
            db,
            task.id,
            level="info" if not result["failures"] else "warning",
            step="complete",
            message=result["message"],
        )
        update_task(
            db,
            task,
            status="success",
            step="complete",
            progress=100,
            result_data=result,
            finish=True,
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        if task is not None:
            message = safe_worker_error_message(exc)
            with suppress(Exception):
                fail_task(
                    db,
                    task,
                    error_code="INSTALL_SOCAT_JOB_FAILED",
                    error_message=message,
                    result_data={
                        "classification": "install_socat",
                        "ok": False,
                        "installed": False,
                        "already_installed": False,
                        "error_code": "INSTALL_SOCAT_JOB_FAILED",
                        "failed_step": task.current_step or "install_socat",
                        "message": message,
                        "socat": {"path": None, "version": None},
                        "system": {},
                        "warnings": ["本阶段只安装/检查 socat，不创建转发规则"],
                        "failures": [message],
                        "checked_at": datetime.now(UTC).isoformat(),
                    },
                )
        return
    finally:
        with suppress(Exception):
            get_redis_client().delete(f"temp_credential:{temp_credential_id}")
        private_key = ""
        passphrase = None
        db.close()


def create_transit_route_job(
    task_id: str,
    transit_resource_id: str,
    node_id: str,
    temp_credential_id: str,
    route_params: dict,
) -> None:
    db = SessionLocal()
    private_key = ""
    passphrase = None
    try:
        task = db.get(Task, task_id)
        resource = db.get(TransitResource, transit_resource_id)
        node = db.get(Node, node_id)
        vps = db.get(VpsServer, node.vps_id) if node else None
        if not task or not resource or not node or not vps:
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(
            db,
            task.id,
            level="info",
            step="load_credentials",
            message="读取临时 SSH 凭据。",
        )
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="create_transit_route", progress=18)
        add_task_log(
            db,
            task.id,
            level="info",
            step="create_transit_route",
            message="开始创建单条 gost TCP 中转规则。",
        )
        db.commit()

        route_name = str(route_params.get("route_name") or "").strip()
        forwarding_method = str(route_params.get("forwarding_method") or "")
        listen_port = int(route_params.get("listen_port") or 0)

        update_task(db, task, step="validate_inputs", progress=25)
        add_task_log(db, task.id, level="info", step="validate_inputs", message="开始校验中转规则输入。")

        if resource.resource_type != "server" or resource.status != "active" or not resource.has_ssh:
            fail_task(
                db,
                task,
                error_code="TRANSIT_RESOURCE_INVALID",
                error_message="中转资源必须是 active server 且启用 SSH 元数据。",
                result_data={
                    "classification": "create_transit_route",
                    "created": False,
                    "message": "中转资源不满足创建条件。",
                    "warnings": [],
                    "failures": ["中转资源必须是 active server 且启用 SSH 元数据"],
                },
            )
            return
        if node.status != "active" or node.deleted_at is not None or not node.share_link:
            fail_task(
                db,
                task,
                error_code="NODE_INVALID",
                error_message="节点必须是 active、未删除且存在分享链接。",
                result_data={
                    "classification": "create_transit_route",
                    "created": False,
                    "message": "节点不满足创建条件。",
                    "warnings": [],
                    "failures": ["节点必须是 active、未删除且存在分享链接"],
                },
            )
            return
        if not vps.ip:
            fail_task(
                db,
                task,
                error_code="LANDING_VPS_NOT_FOUND",
                error_message="落地 VPS 缺少 IP。",
                result_data={
                    "classification": "create_transit_route",
                    "created": False,
                    "message": "落地 VPS 缺少 IP。",
                    "warnings": [],
                    "failures": ["落地 VPS 缺少 IP"],
                },
            )
            return

        active_route = db.scalar(
            select(TransitRoute).where(
                TransitRoute.status == "active",
                TransitRoute.deleted_at.is_(None),
            )
        )
        if active_route:
            fail_task(
                db,
                task,
                error_code="TRANSIT_ROUTE_LIMIT_REACHED",
                error_message="Stage 3.3.3 只允许创建一条 active 中转规则。",
                result_data={
                    "classification": "create_transit_route",
                    "created": False,
                    "message": "Stage 3.3.3 只允许创建一条 active 中转规则。",
                    "warnings": [],
                    "failures": ["Stage 3.3.3 只允许创建一条 active 中转规则"],
                },
            )
            return

        db.commit()
        update_task(db, task, step="ssh_connect", progress=30)
        add_task_log(db, task.id, level="info", step="ssh_connect", message="开始连接香港中转服务器。")
        db.commit()

        progress_map = {
            "validate_inputs": 25,
            "ssh_connect": 30,
            "check_gost": 40,
            "check_port": 48,
            "write_service": 58,
            "daemon_reload": 66,
            "enable_service": 72,
            "start_service": 78,
            "verify_service": 84,
            "verify_port": 90,
            "rollback": 95,
        }

        def log_command(level: str, step: str, message: str, raw_output: str | None) -> None:
            update_task(db, task, step=step, progress=progress_map.get(step, task.progress))
            add_task_log(db, task.id, level=level, step=step, message=message, raw_output=raw_output)
            db.commit()

        route_id = str(uuid.uuid4())
        try:
            result = create_transit_route_state(
                resource=resource,
                node=node,
                vps=vps,
                private_key=private_key,
                passphrase=passphrase,
                route_id=route_id,
                route_name=route_name,
                listen_port=listen_port,
                forwarding_method=forwarding_method,
                logger=log_command,
            )
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data,
            )
            return

        route_data = result["route"]
        update_task(db, task, step="save_route", progress=95)
        add_task_log(db, task.id, level="info", step="save_route", message="保存中转规则记录。")
        route = TransitRoute(
            id=route_id,
            name=route_name,
            transit_resource_id=resource.id,
            node_id=node.id,
            landing_vps_id=vps.id,
            listen_port=listen_port,
            target_host=route_data["target_host"],
            target_port=route_data["target_port"],
            forwarding_method=forwarding_method,
            service_name=route_data["service_name"],
            service_path=route_data["service_path"],
            status="active",
            share_link=route_data["share_link"],
        )
        try:
            db.add(route)
            db.flush()
            result["route"]["created_at"] = route.created_at.isoformat() if route.created_at else None
            add_task_log(
                db,
                task.id,
                level="info",
                step="complete",
                message=result["message"],
            )
            update_task(
                db,
                task,
                status="success",
                step="complete",
                progress=100,
                result_data=result,
                finish=True,
            )
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            cleanup_ok = cleanup_transit_service(
                resource,
                private_key,
                passphrase,
                service_name=route_data["service_name"],
                service_path=route_data["service_path"],
                timeout_seconds=30,
            )
            fail_task(
                db,
                task,
                error_code="TRANSIT_ROUTE_DB_SAVE_FAILED",
                error_message="中转规则数据库保存失败，已尝试回滚远端 service。",
                result_data={
                    "classification": "create_transit_route",
                    "created": False,
                    "message": "中转规则数据库保存失败，已尝试回滚远端 service。",
                    "route": {
                        "id": route_id,
                        "service_name": route_data["service_name"],
                        "service_path": route_data["service_path"],
                    },
                    "manual_cleanup_required": not cleanup_ok,
                    "warnings": result.get("warnings", []),
                    "failures": ["中转规则数据库保存失败"],
                },
            )
    finally:
        private_key = ""
        passphrase = None
        db.close()


def create_socat_route_job(
    task_id: str,
    transit_route_id: str,
    temp_credential_id: str,
) -> None:
    db = SessionLocal()
    task: Task | None = None
    route: TransitRoute | None = None
    private_key = ""
    passphrase = None
    try:
        task = db.get(Task, task_id)
        route = db.get(TransitRoute, transit_route_id)
        if not task or not route:
            return

        resource = route.transit_resource
        if resource is None:
            fail_task(
                db,
                task,
                error_code="TRANSIT_RESOURCE_NOT_FOUND",
                error_message="中转资源不存在。",
                result_data={
                    "classification": "create_socat_route",
                    "created": False,
                    "message": "中转资源不存在。",
                    "failures": ["中转资源不存在"],
                    "warnings": [],
                },
            )
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(db, task.id, level="info", step="load_credentials", message="读取临时 SSH 凭据。")
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            route.status = "error"
            db.add(route)
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            route.status = "error"
            db.add(route)
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="create_socat_route", progress=18)
        add_task_log(
            db,
            task.id,
            level="info",
            step="create_socat_route",
            message=(
                "开始创建单条 socat TCP 测试转发。"
                f" route_id={route.id}，host={resource.ssh_host or '-'}，"
                f"ssh_port={resource.ssh_port or '-'}，username={resource.ssh_username or '-'}，"
                f"listen_port={route.listen_port}，target={route.target_host}:{route.target_port}。"
            ),
        )
        db.commit()

        progress_map = {
            "validate_inputs": 25,
            "ssh_connect": 30,
            "check_socat": 42,
            "check_port": 50,
            "write_service": 60,
            "daemon_reload": 68,
            "enable_service": 74,
            "start_service": 80,
            "verify_service": 86,
            "verify_port": 92,
            "rollback": 95,
        }

        def log_command(level: str, step: str, message: str, raw_output: str | None) -> None:
            update_task(db, task, step=step, progress=progress_map.get(step, task.progress))
            add_task_log(db, task.id, level=level, step=step, message=message, raw_output=raw_output)
            db.commit()

        try:
            result = create_socat_route_state(route=route, private_key=private_key, passphrase=passphrase, logger=log_command)
        except SSHReadError as exc:
            route.status = "error"
            db.add(route)
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data
                or {
                    "classification": "create_socat_route",
                    "created": False,
                    "error_code": exc.error_code,
                    "failed_step": task.current_step or "create_socat_route",
                    "message": exc.message,
                    "route": route_summary(route),
                    "warnings": ["Stage 3.3.3-fix-b1 只创建 socat 测试转发，不替换现有 gost 8443"],
                    "failures": [exc.message],
                },
            )
            return
        except Exception as exc:
            message = safe_worker_error_message(exc)
            route.status = "error"
            db.add(route)
            fail_task(
                db,
                task,
                error_code="CREATE_SOCAT_ROUTE_FAILED",
                error_message=message,
                result_data={
                    "classification": "create_socat_route",
                    "created": False,
                    "message": message,
                    "route": route_summary(route),
                    "warnings": ["Stage 3.3.3-fix-b1 只创建 socat 测试转发，不替换现有 gost 8443"],
                    "failures": [message],
                    "failed_step": task.current_step or "create_socat_route",
                },
            )
            return

        try:
            route.status = "active"
            route.share_link = None
            db.add(route)
            update_task(db, task, step="save_route", progress=96)
            add_task_log(db, task.id, level="info", step="save_route", message="保存 socat 测试转发规则记录。")
            add_task_log(db, task.id, level="info", step="complete", message=result["message"])
            update_task(db, task, status="success", step="complete", progress=100, result_data=result, finish=True)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            cleanup_ok = cleanup_socat_service(route, private_key, passphrase, timeout_seconds=30)
            task = db.get(Task, task_id)
            route = db.get(TransitRoute, transit_route_id)
            if route is not None:
                route.status = "error"
                db.add(route)
            if task is not None:
                fail_task(
                    db,
                    task,
                    error_code="SOCAT_ROUTE_DB_SAVE_FAILED",
                    error_message="socat 测试转发数据库保存失败，已尝试回滚远端 service。",
                    result_data={
                        "classification": "create_socat_route",
                        "created": False,
                        "message": "socat 测试转发数据库保存失败，已尝试回滚远端 service。",
                        "route": {
                            "id": transit_route_id,
                            "service_name": route.service_name if route else None,
                            "service_path": route.service_path if route else None,
                        },
                        "manual_cleanup_required": not cleanup_ok,
                        "warnings": result.get("warnings", []),
                        "failures": ["socat 测试转发数据库保存失败"],
                    },
                )
    except Exception as exc:
        db.rollback()
        if task is not None:
            message = safe_worker_error_message(exc)
            if route is not None:
                with suppress(Exception):
                    route.status = "error"
                    db.add(route)
            with suppress(Exception):
                fail_task(
                    db,
                    task,
                    error_code="CREATE_SOCAT_ROUTE_JOB_FAILED",
                    error_message=message,
                    result_data={
                        "classification": "create_socat_route",
                        "created": False,
                        "message": message,
                        "route": route_summary(route) if route is not None else {},
                        "warnings": ["Stage 3.3.3-fix-b1 只创建 socat 测试转发，不替换现有 gost 8443"],
                        "failures": [message],
                        "failed_step": task.current_step or "create_socat_route",
                    },
                )
        return
    finally:
        with suppress(Exception):
            get_redis_client().delete(f"temp_credential:{temp_credential_id}")
        private_key = ""
        passphrase = None
        db.close()


def diagnose_transit_route_job(
    task_id: str,
    transit_route_id: str,
    temp_credential_id: str,
) -> None:
    db = SessionLocal()
    task: Task | None = None
    route: TransitRoute | None = None
    private_key = ""
    passphrase = None
    try:
        task = db.get(Task, task_id)
        route = db.get(TransitRoute, transit_route_id)
        if not task or not route:
            return

        resource = route.transit_resource
        if resource is None:
            fail_task(
                db,
                task,
                error_code="TRANSIT_RESOURCE_NOT_FOUND",
                error_message="中转资源不存在。",
                result_data={
                    "classification": "diagnose_transit_route",
                    "diagnosed": False,
                    "message": "中转资源不存在。",
                    "route": {"id": transit_route_id},
                    "warnings": [],
                    "failures": ["中转资源不存在"],
                },
            )
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(db, task.id, level="info", step="load_credentials", message="读取临时 SSH 凭据。")
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="diagnose_transit_route", progress=20)
        add_task_log(
            db,
            task.id,
            level="info",
            step="diagnose_transit_route",
            message=(
                "开始中转线路只读诊断。"
                f" route_id={route.id}，host={resource.ssh_host or '-'}，"
                f"ssh_port={resource.ssh_port or '-'}，username={resource.ssh_username or '-'}，"
                f"method={route.forwarding_method}，listen_port={route.listen_port}，"
                f"target={route.target_host}:{route.target_port}。"
            ),
        )
        db.commit()

        try:
            result = diagnose_transit_route_state(route, private_key, passphrase)
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data
                or {
                    "classification": "diagnose_transit_route",
                    "diagnosed": False,
                    "message": exc.message,
                    "route": {"id": route.id},
                    "warnings": ["本任务只执行白名单只读诊断命令。"],
                    "failures": [exc.message],
                    "failed_step": task.current_step or "diagnose_transit_route",
                },
            )
            return
        except Exception as exc:
            message = safe_worker_error_message(exc)
            fail_task(
                db,
                task,
                error_code="DIAGNOSE_TRANSIT_ROUTE_FAILED",
                error_message=message,
                result_data={
                    "classification": "diagnose_transit_route",
                    "diagnosed": False,
                    "message": message,
                    "route": {"id": route.id},
                    "warnings": ["本任务只执行白名单只读诊断命令。"],
                    "failures": [message],
                    "failed_step": task.current_step or "diagnose_transit_route",
                },
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=85)
        add_task_log(db, task.id, level="info", step="save_result", message="保存中转线路只读诊断结果。")
        add_task_log(db, task.id, level="info", step="complete", message=result["message"])
        update_task(db, task, status="success", step="complete", progress=100, result_data=result, finish=True)
        db.commit()
    except Exception as exc:
        db.rollback()
        if task is not None:
            message = safe_worker_error_message(exc)
            with suppress(Exception):
                fail_task(
                    db,
                    task,
                    error_code="DIAGNOSE_TRANSIT_ROUTE_JOB_FAILED",
                    error_message=message,
                    result_data={
                        "classification": "diagnose_transit_route",
                        "diagnosed": False,
                        "message": message,
                        "route": {"id": transit_route_id},
                        "warnings": ["本任务只执行白名单只读诊断命令。"],
                        "failures": [message],
                        "failed_step": task.current_step or "diagnose_transit_route",
                    },
                )
        return
    finally:
        with suppress(Exception):
            get_redis_client().delete(f"temp_credential:{temp_credential_id}")
        private_key = ""
        passphrase = None
        db.close()


def restart_socat_route_job(
    task_id: str,
    transit_route_id: str,
    temp_credential_id: str,
) -> None:
    db = SessionLocal()
    task: Task | None = None
    route: TransitRoute | None = None
    private_key = ""
    passphrase = None
    try:
        task = db.get(Task, task_id)
        route = db.get(TransitRoute, transit_route_id)
        if not task or not route:
            return

        resource = route.transit_resource
        if resource is None:
            fail_task(
                db,
                task,
                error_code="TRANSIT_RESOURCE_NOT_FOUND",
                error_message="中转资源不存在。",
                result_data={
                    "classification": "restart_socat_route",
                    "restarted": False,
                    "message": "中转资源不存在。",
                    "route": {"id": transit_route_id},
                    "warnings": [],
                    "failures": ["中转资源不存在"],
                },
            )
            return

        update_task(db, task, status="running", step="load_credentials", progress=10)
        add_task_log(db, task.id, level="info", step="load_credentials", message="读取临时 SSH 凭据。")
        db.commit()

        try:
            private_key, passphrase = pop_temp_credential(temp_credential_id)
        except TempCredentialExpired:
            fail_task(
                db,
                task,
                error_code="SSH_KEY_EXPIRED",
                error_message="临时 SSH Key 已过期，请重新提交。",
            )
            return
        except TempCredentialDecryptFailed:
            fail_task(
                db,
                task,
                error_code="SSH_AUTH_FAILED",
                error_message="临时 SSH Key 解密失败。",
            )
            return

        update_task(db, task, step="restart_socat_route", progress=20)
        add_task_log(
            db,
            task.id,
            level="info",
            step="restart_socat_route",
            message=(
                "开始重启 socat 18443 测试链路。"
                f" route_id={route.id}，host={resource.ssh_host or '-'}，"
                f"ssh_port={resource.ssh_port or '-'}，username={resource.ssh_username or '-'}，"
                f"method={route.forwarding_method}，listen_port={route.listen_port}，"
                f"target={route.target_host}:{route.target_port}。"
            ),
        )
        db.commit()

        try:
            result = restart_socat_route_state(route, private_key, passphrase)
        except SSHReadError as exc:
            fail_task(
                db,
                task,
                error_code=exc.error_code,
                error_message=exc.message,
                result_data=exc.result_data
                or {
                    "classification": "restart_socat_route",
                    "restarted": False,
                    "message": exc.message,
                    "route": {"id": route.id},
                    "warnings": ["本任务只允许重启 socat 18443 测试链路。"],
                    "failures": [exc.message],
                    "failed_step": task.current_step or "restart_socat_route",
                },
            )
            return
        except Exception as exc:
            message = safe_worker_error_message(exc)
            fail_task(
                db,
                task,
                error_code="RESTART_SOCAT_ROUTE_FAILED",
                error_message=message,
                result_data={
                    "classification": "restart_socat_route",
                    "restarted": False,
                    "message": message,
                    "route": {"id": route.id},
                    "warnings": ["本任务只允许重启 socat 18443 测试链路。"],
                    "failures": [message],
                    "failed_step": task.current_step or "restart_socat_route",
                },
            )
            return
        finally:
            private_key = ""
            passphrase = None

        update_task(db, task, step="save_result", progress=85)
        add_task_log(db, task.id, level="info", step="save_result", message="保存 socat 测试链路重启结果。")
        add_task_log(db, task.id, level="info", step="complete", message=result["message"])
        update_task(db, task, status="success", step="complete", progress=100, result_data=result, finish=True)
        db.commit()
    except Exception as exc:
        db.rollback()
        if task is not None:
            message = safe_worker_error_message(exc)
            with suppress(Exception):
                fail_task(
                    db,
                    task,
                    error_code="RESTART_SOCAT_ROUTE_JOB_FAILED",
                    error_message=message,
                    result_data={
                        "classification": "restart_socat_route",
                        "restarted": False,
                        "message": message,
                        "route": {"id": transit_route_id},
                        "warnings": ["本任务只允许重启 socat 18443 测试链路。"],
                        "failures": [message],
                        "failed_step": task.current_step or "restart_socat_route",
                    },
                )
        return
    finally:
        with suppress(Exception):
            get_redis_client().delete(f"temp_credential:{temp_credential_id}")
        private_key = ""
        passphrase = None
        db.close()
