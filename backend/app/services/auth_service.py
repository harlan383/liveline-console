from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_password, hash_token, new_token, token_matches, verify_password
from app.models.admin_session import AdminSession
from app.models.admin_user import AdminUser
from app.models.audit_log import AuditLog

SESSION_COOKIE_NAME = "livelines_session"
CSRF_HEADER_NAME = "X-CSRF-Token"


def client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()
    if request.client:
        return request.client.host
    return None


def user_agent(request: Request) -> str | None:
    return request.headers.get("user-agent")


def record_audit(
    db: Session,
    *,
    admin_id: str | None,
    action: str,
    result: str,
    request: Request,
    resource_type: str | None = None,
    resource_id: str | None = None,
) -> None:
    db.add(
        AuditLog(
            admin_id=admin_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            ip_address=client_ip(request),
            user_agent=user_agent(request),
            result=result,
        )
    )


def admin_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(AdminUser)) or 0


def create_admin(db: Session, username: str, password: str) -> AdminUser:
    admin = AdminUser(
        username=username,
        password_hash=hash_password(password),
        status="active",
    )
    db.add(admin)
    return admin


def find_active_admin(db: Session, username: str) -> AdminUser | None:
    stmt: Select[tuple[AdminUser]] = select(AdminUser).where(
        AdminUser.username == username,
        AdminUser.status == "active",
    )
    return db.scalar(stmt)


def verify_admin_password(admin: AdminUser, password: str) -> bool:
    return verify_password(password, admin.password_hash)


def create_session(db: Session, admin: AdminUser, request: Request) -> tuple[AdminSession, str]:
    settings = get_settings()
    raw_session_token = new_token()
    session = AdminSession(
        admin_id=admin.id,
        session_token_hash=hash_token(raw_session_token),
        expires_at=datetime.now(UTC) + timedelta(seconds=settings.session_ttl_seconds),
        ip_address=client_ip(request),
        user_agent=user_agent(request),
    )
    db.add(session)
    return session, raw_session_token


def get_session_from_request(db: Session, request: Request) -> AdminSession | None:
    raw_session_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_session_token:
        return None

    stmt = select(AdminSession).where(
        AdminSession.session_token_hash == hash_token(raw_session_token),
        AdminSession.revoked_at.is_(None),
        AdminSession.expires_at > datetime.now(UTC),
    )
    return db.scalar(stmt)


def rotate_csrf_token(db: Session, session: AdminSession) -> str:
    raw_csrf_token = new_token()
    session.csrf_token_hash = hash_token(raw_csrf_token)
    db.add(session)
    return raw_csrf_token


def csrf_is_valid(request: Request, session: AdminSession) -> bool:
    raw_csrf_token = request.headers.get(CSRF_HEADER_NAME)
    if not raw_csrf_token or not session.csrf_token_hash:
        return False
    return token_matches(raw_csrf_token, session.csrf_token_hash)


def revoke_session(db: Session, session: AdminSession) -> None:
    session.revoked_at = datetime.now(UTC)
    db.add(session)
