from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import AuditEvent, Role, User, UserSession
from .security import token_hash


def problem(status_code: int, code: str, detail: str, title: str | None = None) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title or code, "status": status_code,
                "code": code, "detail": detail},
    )


def current_session(request: Request, db: Session) -> tuple[User, UserSession]:
    raw = request.cookies.get("sid")
    if not raw:
        raise problem(401, "not_authenticated", "Sign in to continue.")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(raw)))
    if not session or session.revoked_at is not None:
        raise problem(401, "not_authenticated", "Session is no longer valid.")
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    if expires < datetime.now(UTC):
        raise problem(401, "session_expired", "Session expired. Sign in again.")
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise problem(401, "not_authenticated", "Account is not active.")
    return user, session


def current_user(request: Request, db: Annotated[Session, Depends(get_db)]) -> User:
    user, _ = current_session(request, db)
    return user


CurrentUser = Annotated[User, Depends(current_user)]
DbSession = Annotated[Session, Depends(get_db)]


def require_role(*roles: Role):
    def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise problem(403, "role_required", "You do not have permission for this action.")
        return user

    return dependency


ManagerUser = Annotated[User, Depends(require_role(Role.MANAGER))]


def audit(
    db: Session,
    *,
    org_id: str,
    actor_id: str | None,
    action: str,
    entity: str,
    entity_id: str | None,
    meta: dict | None = None,
    ip: str | None = None,
) -> None:
    db.add(
        AuditEvent(
            org_id=org_id,
            actor_id=actor_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            meta=meta or {},
            ip=ip,
        )
    )
