from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import auth_error, csrf_error, csrf_valid, require_admin_session
from app.db.session import get_db
from app.models.node import Node
from app.schemas.common import error_response, success_response
from app.schemas.remote_cleanup import OFFLINE_LOCAL_REMOVE_CONFIRMATION, RemoteCleanupDeleteRequest
from app.services.auth_service import record_audit
from app.services.node_display import build_node_display_fields
from app.services.redaction import mask_identifier, mask_share_link
from app.services.remote_cleanup_delete import (
    RemoteCleanupError,
    create_landing_node_cleanup_command,
    offline_local_remove_node,
    remote_cleanup_unavailable_offer,
)
from app.services.share_link_compat import ensure_vless_tcp_header_type_none
from app.services.worker_commands import serialize_worker_command

router = APIRouter()


class NodeShareLinkExportRequest(BaseModel):
    confirm_export: bool = False
    reason: str | None = Field(default=None, max_length=120)


def serialize_node(node: Node, *, include_share_link: bool = False) -> dict:
    vps = node.vps
    has_share_link = bool(node.share_link)
    display_fields = build_node_display_fields(node.service_status, node.connectivity_status)
    data = {
        "id": node.id,
        "vps_id": node.vps_id,
        "vps_ip": vps.ip if vps else None,
        "vps_status": vps.status if vps else None,
        "node_name": node.node_name,
        "protocol": node.protocol,
        "transport": node.transport,
        "security": node.security,
        "port": node.xray_port,
        "status": node.status,
        "service_status": node.service_status,
        "connectivity_status": node.connectivity_status,
        **display_fields,
        "uuid": None,
        "uuid_present": bool(node.uuid),
        "masked_uuid": mask_identifier(node.uuid),
        "flow": node.flow,
        "reality_public_key": None,
        "reality_public_key_present": bool(node.reality_public_key),
        "masked_reality_public_key": mask_identifier(node.reality_public_key),
        "reality_short_id": None,
        "reality_short_id_present": bool(node.reality_short_id),
        "masked_reality_short_id": mask_identifier(node.reality_short_id),
        "reality_server_name": node.sni,
        "reality_dest": node.dest,
        "fingerprint": node.fingerprint,
        "has_share_link": has_share_link,
        "share_link_present": has_share_link,
        "share_link_length": len(node.share_link) if node.share_link else None,
        "masked_share_link": mask_share_link(node.share_link),
        "source": node.source,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
        "last_remote_check_at": node.last_remote_check_at.isoformat() if node.last_remote_check_at else None,
        "last_sync_status": node.last_sync_status,
    }
    if include_share_link:
        data["share_link"] = ensure_vless_tcp_header_type_none(node.share_link) if node.share_link else node.share_link
    return data


@router.get("")
@router.get("/")
def list_nodes(request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    nodes = db.scalars(
        select(Node)
        .where(Node.deleted_at.is_(None))
        .order_by(Node.created_at.desc())
    ).all()
    return success_response(
        {"nodes": [serialize_node(node, include_share_link=False) for node in nodes]},
        "ok",
    )


@router.get("/{node_id}")
def get_node(node_id: str, request: Request, db: Session = Depends(get_db)):
    if not require_admin_session(db, request):
        return auth_error()

    node = db.get(Node, node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "NODE_NOT_FOUND", "节点不存在。")

    return success_response(serialize_node(node, include_share_link=False), "ok")


@router.delete("/{node_id}")
def delete_node(
    node_id: str,
    request: Request,
    confirm: bool = False,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()
    if confirm is not True:
        return error_response(400, "CONFIRMATION_REQUIRED", "请确认删除节点记录。")

    node = db.get(Node, node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "NODE_NOT_FOUND", "节点不存在。")

    node.status = "deleted"
    node.service_status = "unknown"
    node.connectivity_status = "unknown"
    node.last_sync_status = "system_record_deleted"
    node.deleted_at = datetime.now(UTC)
    db.add(node)
    record_audit(
        db,
        admin_id=session.admin_id,
        action="delete_node_record",
        result="success",
        request=request,
        resource_type="node",
        resource_id=node.id,
    )
    db.commit()

    return success_response(
        {
            "id": node.id,
            "deleted": True,
            "delete_mode": "soft_delete",
            "remote_action_performed": False,
            "message": "系统记录已删除；未执行远程清理。",
        },
        "系统记录已删除；未执行远程清理。",
    )


@router.post("/{node_id}/remote-cleanup-delete")
def remote_cleanup_delete_node(
    node_id: str,
    payload: RemoteCleanupDeleteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()

    node = db.get(Node, node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "NODE_NOT_FOUND", "节点不存在。")

    if payload.confirm == OFFLINE_LOCAL_REMOVE_CONFIRMATION:
        try:
            result = offline_local_remove_node(db, node)
            record_audit(
                db,
                admin_id=session.admin_id,
                action="offline_local_remove_node",
                result="success",
                request=request,
                resource_type="node",
                resource_id=node.id,
            )
            db.commit()
        except RemoteCleanupError as exc:
            db.rollback()
            return error_response(exc.status_code, exc.code, exc.message)
        return success_response(result, result["message"])

    try:
        command, worker = create_landing_node_cleanup_command(db, node)
        record_audit(
            db,
            admin_id=session.admin_id,
            action="create_cleanup_landing_node_command",
            result="success",
            request=request,
            resource_type="node",
            resource_id=node.id,
        )
        db.commit()
        db.refresh(command)
    except RemoteCleanupError as exc:
        db.rollback()
        if offer := remote_cleanup_unavailable_offer(exc):
            return error_response(
                400,
                "REMOTE_CLEANUP_UNAVAILABLE",
                "Worker 离线，无法远程清理。可使用离线本地移除确认。",
                offer,
            )
        return error_response(exc.status_code, exc.code, exc.message)

    return success_response(
        {
            "command_id": command.id,
            "cleanup_type": "cleanup_landing_node",
            "status": "queued",
            "remote_cleanup_required": True,
            "system_record_delete_after_success": True,
            "command": serialize_worker_command(command, worker=worker),
            "message": "远程清理任务已创建，清理成功后将软删除系统记录。",
        },
        "远程清理任务已创建，清理成功后将软删除系统记录。",
    )


@router.post("/{node_id}/share-link/export")
def export_node_share_link(
    node_id: str,
    payload: NodeShareLinkExportRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    session = require_admin_session(db, request)
    if not session:
        return auth_error()
    if not csrf_valid(request, session):
        return csrf_error()
    if payload.confirm_export is not True:
        return error_response(400, "CONFIRM_EXPORT_REQUIRED", "导出完整节点链接前必须二次确认。")

    node = db.get(Node, node_id)
    if not node or node.deleted_at is not None:
        return error_response(404, "NODE_NOT_FOUND", "节点不存在。")
    if not node.share_link:
        return error_response(404, "SHARE_LINK_NOT_FOUND", "该节点没有可导出的分享链接。")

    record_audit(
        db,
        admin_id=session.admin_id,
        action="export_node_share_link",
        result="success",
        request=request,
        resource_type="node",
        resource_id=node.id,
    )
    db.commit()
    return success_response(
        {
            "node_id": node.id,
            "node_name": node.node_name,
            "share_link": ensure_vless_tcp_header_type_none(node.share_link),
            "warning": "share_link is sensitive; do not paste it into chats, logs, PRs, or documents.",
        },
        "节点链接已导出。本响应是唯一明文返回位置，请勿写入日志或文档。",
    )
