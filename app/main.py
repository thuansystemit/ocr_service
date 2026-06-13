"""FastAPI application factory + lifespan (C-01).

Sprint 1 wires logging, the health/metrics router, and clean engine disposal on
shutdown. Auth, tenant-context, and rate-limit middleware (Sprint 2) and the
ingest/schema/review/admin routers (Sprint 3+) attach here as they land.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app import __version__
from app.api.routers import audit, dlq, extract, health, me, review, schemas
from app.config import get_settings
from app.db.session import dispose_engine
from app.observability.logging import configure_logging, get_logger


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    log = get_logger(__name__)
    log.info("app.startup", env=settings.env.value, version=__version__)
    try:
        yield
    finally:
        await dispose_engine()
        log.info("app.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="OCR Service",
        version=__version__,
        description="Enterprise OCR / document-extraction platform.",
        docs_url="/docs",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(me.router)
    app.include_router(schemas.router)
    app.include_router(extract.router)
    app.include_router(review.router)
    app.include_router(dlq.router)
    app.include_router(audit.router)
    # Routers/middleware for later sprints register here.
    _ = settings  # reserved for CORS / rate-limit config wiring
    return app


app = create_app()
