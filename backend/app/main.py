"""SmartPOS AI backend application."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware

logger = logging.getLogger("smartpos")


def create_app() -> FastAPI:
    settings = get_settings()  # Validates configuration; fails fast on bad production settings.
    configure_logging(settings.log_level, settings.log_format)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "SmartPOS AI backend starting", extra={"env": settings.app_env, "ai_assistant": settings.llm_configured}
        )
        yield

    app = FastAPI(
        title="SmartPOS AI API",
        version=settings.app_version,
        description=(
            "Cloud-based point-of-sale and restaurant management API with AI-assisted inventory "
            "forecasting. Restaurant-scoped endpoints require the `X-Restaurant-ID` header."
        ),
        openapi_url="/api/v1/openapi.json" if settings.show_api_docs else None,
        docs_url="/api/docs" if settings.show_api_docs else None,
        redoc_url="/api/redoc" if settings.show_api_docs else None,
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-CSRF-Token",
            "X-Restaurant-ID",
            "X-Request-ID",
            "Idempotency-Key",
        ],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )
    app.add_middleware(RequestContextMiddleware)
    app.include_router(api_router, prefix="/api/v1")
    return app


app = create_app()
