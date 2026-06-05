from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.admin_user import AdminUser
from app.schemas.auth import LoginRequest
from app.schemas.common import error_response, success_response
from app.services.auth_service import (
    SESSION_COOKIE_NAME,
    create_session,
    csrf_is_valid,
    find_active_admin,
    get_session_from_request,
    record_audit,
    revoke_session,
    rotate_csrf_token,
    verify_admin_password,
)

router = APIRouter()


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    admin = find_active_admin(db, payload.username)

    if not admin or not verify_admin_password(admin, payload.password):
        record_audit(
            db,
            admin_id=admin.id if admin else None,
            action="login",
            result="failed",
            request=request,
            resource_type="admin",
        )
        db.commit()
        return error_response(401, "AUTH_FAILED", "用户名或密码错误。")

    session, raw_session_token = create_session(db, admin, request)
    admin.last_login_at = datetime.now(UTC)
    db.add(admin)
    db.flush()
    record_audit(
        db,
        admin_id=admin.id,
        action="login",
        result="success",
        request=request,
        resource_type="admin",
        resource_id=admin.id,
    )
    db.commit()

    response.set_cookie(
        SESSION_COOKIE_NAME,
        raw_session_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return success_response({"admin_id": admin.id, "username": admin.username}, "登录成功")


@router.get("/csrf")
def get_csrf(request: Request, db: Session = Depends(get_db)):
    session = get_session_from_request(db, request)
    if not session:
        return error_response(401, "ADMIN_INIT_REQUIRED", "请先登录管理员账号。")

    raw_csrf_token = rotate_csrf_token(db, session)
    db.commit()
    return success_response({"csrf_token": raw_csrf_token}, "ok")


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    session = get_session_from_request(db, request)
    if not session:
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return success_response({}, "已退出")

    if not csrf_is_valid(request, session):
        return error_response(403, "CSRF_TOKEN_INVALID", "请求安全校验失败，请刷新页面后重试。")

    admin: AdminUser | None = db.get(AdminUser, session.admin_id)
    revoke_session(db, session)
    record_audit(
        db,
        admin_id=admin.id if admin else session.admin_id,
        action="logout",
        result="success",
        request=request,
        resource_type="admin",
        resource_id=admin.id if admin else session.admin_id,
    )
    db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return success_response({}, "退出成功")
