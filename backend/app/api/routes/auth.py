from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import verify_password
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


def env_admin_password_is_valid(
    admin: AdminUser | None,
    username: str,
    password: str,
) -> bool:
    if not admin:
        return False

    settings = get_settings()
    if not settings.admin_username or not settings.admin_password_hash:
        return False
    if username != settings.admin_username:
        return False

    return verify_password(password, settings.admin_password_hash)


@router.post("/login")
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    settings = get_settings()
    admin = find_active_admin(db, payload.username)

    password_valid = bool(admin and verify_admin_password(admin, payload.password))
    password_valid = password_valid or env_admin_password_is_valid(
        admin,
        payload.username,
        payload.password,
    )

    if not admin or not password_valid:
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


@router.get("/me")
def me(request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    session = get_session_from_request(db, request)
    if not session:
        return error_response(401, "AUTH_REQUIRED", "请先登录管理员账号。")

    admin: AdminUser | None = db.get(AdminUser, session.admin_id)
    if not admin or admin.status != "active":
        revoke_session(db, session)
        db.commit()
        response.delete_cookie(SESSION_COOKIE_NAME, path="/")
        return error_response(401, "AUTH_REQUIRED", "登录状态已失效，请重新登录。")

    response.set_cookie(
        SESSION_COOKIE_NAME,
        request.cookies.get(SESSION_COOKIE_NAME, ""),
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    return success_response({"admin_id": admin.id, "username": admin.username}, "已登录")


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
