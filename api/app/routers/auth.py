from datetime import UTC, datetime
from threading import Lock

from fastapi import APIRouter, Request, Response
from sqlalchemy import func, select

from ..config import settings
from ..deps import CurrentUser, DbSession, audit, current_session, problem
from ..models import User, UserSession
from ..schemas import LoginIn, MeOut, UserOut
from ..security import (
    hash_password,
    new_token,
    session_expiry,
    token_hash,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_attempts: dict[str, list[datetime]] = {}
_lock = Lock()


def _rate_limited(key: str) -> bool:
    now = datetime.now(UTC)
    with _lock:
        recent = [t for t in _attempts.get(key, []) if (now - t).total_seconds() < 900]
        _attempts[key] = recent
        return len(recent) >= 5


def _record_attempt(key: str) -> None:
    with _lock:
        _attempts.setdefault(key, []).append(datetime.now(UTC))


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        org_id=user.org_id,
        org_name=user.org.name,
    )


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: DbSession) -> MeOut:
    ip = request.client.host if request.client else "unknown"
    key = f"{ip}:{body.email}"
    if _rate_limited(key):
        raise problem(429, "rate_limited", "Too many attempts. Try again in 15 minutes.")

    user = db.scalar(select(User).where(func.lower(User.email) == body.email))
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        _record_attempt(key)
        raise problem(401, "invalid_credentials", "Invalid email or password.")

    _attempts.pop(key, None)
    raw = new_token()
    csrf = new_token()
    session = UserSession(
        user_id=user.id,
        token_hash=token_hash(raw),
        csrf_secret=csrf,
        ip=ip,
        user_agent=request.headers.get("user-agent", "")[:400],
        expires_at=session_expiry(),
    )
    user.last_login_at = datetime.now(UTC)
    db.add(session)
    audit(db, org_id=user.org_id, actor_id=user.id, action="auth.login", entity="user",
          entity_id=user.id, ip=ip)
    db.commit()
    db.refresh(user)

    secure = not settings.is_local
    max_age = settings.session_ttl_hours * 3600
    response.set_cookie("sid", raw, httponly=True, secure=secure, samesite="lax",
                        max_age=max_age, path="/")
    response.set_cookie("csrf", csrf, httponly=False, secure=secure, samesite="lax",
                        max_age=max_age, path="/")
    return MeOut(user=_user_out(user), csrf_token=csrf)


@router.post("/logout")
def logout(request: Request, response: Response, db: DbSession) -> dict:
    raw = request.cookies.get("sid")
    if raw:
        session = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash(raw)))
        if session:
            session.revoked_at = datetime.now(UTC)
            db.commit()
    response.delete_cookie("sid", path="/")
    response.delete_cookie("csrf", path="/")
    return {"ok": True}


@router.get("/me", response_model=MeOut)
def me(request: Request, db: DbSession) -> MeOut:
    user, session = current_session(request, db)
    return MeOut(user=_user_out(user), csrf_token=session.csrf_secret)


@router.get("/demo-hash")
def demo_hash() -> dict:
    """Local-only helper used by the seed script to verify Argon2 is available."""
    if not settings.is_local:
        raise problem(404, "not_found", "Not available.")
    return {"hash": hash_password("demo")}
