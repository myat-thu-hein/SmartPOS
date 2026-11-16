"""Health and readiness probes."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.db.session import check_database

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
def health() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "service": "smartpos-backend", "version": settings.app_version}


@router.get("/health/ready", summary="Readiness probe (checks the database)")
def ready() -> JSONResponse:
    database_ok = check_database()
    body = {
        "status": "ready" if database_ok else "not_ready",
        "checks": {"database": "ok" if database_ok else "unavailable"},
        "ai_assistant": "configured" if get_settings().llm_configured else "not_configured",
    }
    return JSONResponse(status_code=200 if database_ok else 503, content=body)
