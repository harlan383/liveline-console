from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.auth import AdminInitRequest
from app.schemas.common import error_response, success_response
from app.services.auth_service import admin_count, create_admin, record_audit

router = APIRouter()


@router.post("/init")
def init_admin(payload: AdminInitRequest, request: Request, db: Session = Depends(get_db)):
    settings = get_settings()

    if admin_count(db) > 0:
        return error_response(
            409,
            "ADMIN_ALREADY_INITIALIZED",
            "管理员已经初始化，不能重复初始化。",
        )

    if settings.app_env == "production" or settings.init_token:
        if not payload.init_token or payload.init_token != settings.init_token:
            return error_response(403, "INIT_TOKEN_INVALID", "初始化 token 错误。")

    try:
        admin = create_admin(db, payload.username, payload.password)
        db.flush()
        record_audit(
            db,
            admin_id=admin.id,
            action="admin_init",
            result="success",
            request=request,
            resource_type="admin",
            resource_id=admin.id,
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        return error_response(409, "ADMIN_ALREADY_INITIALIZED", "管理员已经初始化。")

    return success_response(
        {"admin_id": admin.id, "username": admin.username},
        "管理员初始化完成",
    )
