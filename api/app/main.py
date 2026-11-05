from contextlib import asynccontextmanager
from datetime import UTC, datetime
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import settings
from .db import Base, SessionLocal, engine
from .models import UserSession
from .routers import activity, auth, documents, exports, manual, reports, review, settings as settings_router, shipments
from .security import token_hash

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.is_local:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Customs-AI",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}
CSRF_EXEMPT = {"/api/auth/login"}


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if (
        request.method in MUTATING
        and request.url.path.startswith("/api")
        and request.url.path not in CSRF_EXEMPT
    ):
        sid = request.cookies.get("sid")
        cookie = request.cookies.get("csrf")
        header = request.headers.get("x-csrf-token")
        if not sid:
            return JSONResponse(
                {"type": "about:blank", "title": "Unauthorized", "status": 401,
                 "code": "not_authenticated", "detail": "Sign in to continue."},
                status_code=401,
            )
        with SessionLocal() as db:
            session = db.scalar(
                select(UserSession).where(UserSession.token_hash == token_hash(sid))
            )
        if (
            not session
            or session.revoked_at is not None
            or not cookie
            or not header
            or not secrets.compare_digest(cookie, header)
            or not secrets.compare_digest(cookie, session.csrf_secret)
        ):
            return JSONResponse(
                {"type": "about:blank", "title": "Forbidden", "status": 403,
                 "code": "csrf_failed", "detail": "Request could not be verified."},
                status_code=403,
            )

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["X-Frame-Options"] = "DENY"
    if not settings.is_local:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; connect-src 'self'; font-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        return JSONResponse(exc.detail, status_code=exc.status_code)
    return JSONResponse(
        {"type": "about:blank", "title": str(exc.detail), "status": exc.status_code,
         "code": "error", "detail": str(exc.detail)},
        status_code=exc.status_code,
    )


@app.get("/healthz")
def healthz() -> dict:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"ok": True, "env": settings.app_env, "time": datetime.now(UTC).isoformat()}


@app.get("/api/meta")
def meta() -> dict:
    from .extract import ai

    return {
        "app": "Customs-AI",
        "version": "0.1.0",
        "env": settings.app_env,
        "extractor": settings.ai_backend if ai.configured() else "fixture",
        "model": settings.vertex_model or settings.gemini_model,
        "region": settings.vertex_location if settings.ai_backend == "vertex" else "global",
    }


app.include_router(auth.router)
app.include_router(shipments.router)
app.include_router(documents.router)
app.include_router(manual.router)
app.include_router(review.router)
app.include_router(exports.router)
app.include_router(reports.router)
app.include_router(settings_router.router)
app.include_router(activity.router)


# Serve the built SPA when it exists (production image). In development Vite proxies /api.
if settings.static_dir.exists():
    app.mount("/assets", StaticFiles(directory=settings.static_dir / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith(("api/", "healthz", "health", "v1/")):
            return JSONResponse({"detail": "Not found"}, status_code=404)
        candidate = settings.static_dir / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        index = settings.static_dir / "index.html"
        if index.exists():
            return FileResponse(index)
        return JSONResponse({"detail": "Not found"}, status_code=404)
