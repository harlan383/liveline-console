from fastapi import Request
from sqlalchemy.orm import Session

from app.models.admin_session import AdminSession
from app.schemas.common import error_response
from app.services.auth_service import csrf_is_valid, get_session_from_request


def require_admin_session(db: Session, request: Request) -> AdminSession | None:
    return get_session_from_request(db, request)


def auth_error():
    return error_response(401, "ADMIN_INIT_REQUIRED", "请先登录管理员账号。")


def csrf_error():
    return error_response(403, "CSRF_TOKEN_INVALID", "请求安全校验失败，请刷新页面后重试。")


def csrf_valid(request: Request, session: AdminSession) -> bool:
    return csrf_is_valid(request, session)
