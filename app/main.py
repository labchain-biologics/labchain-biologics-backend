"""LabChain Biologics FastAPI application entrypoint."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.services import run_lifecycle
from app.services.s3 import s3_service

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("labchain")


async def _prepare_local_bucket() -> None:
    """
    Local development only (S3_ENDPOINT_URL set): create the bucket and allow the web origins
    in CORS_ORIGINS to upload through presigned URLs. On real AWS the bucket and its CORS
    policy are infrastructure, managed outside the application.
    """
    try:
        await asyncio.to_thread(s3_service.ensure_bucket)
        await asyncio.to_thread(s3_service.apply_cors, settings.cors_origins)
    except (BotoCoreError, ClientError) as exc:
        logger.warning("Local S3 bucket setup skipped: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    logger.info(
        "Starting %s (env=%s, debug=%s)",
        settings.app_name,
        settings.app_env,
        settings.debug,
    )
    if settings.is_localstack:
        await _prepare_local_bucket()
    monitor: asyncio.Task[None] | None = None
    if settings.aws_batch_enabled:
        monitor = asyncio.create_task(run_lifecycle.run_monitor(AsyncSessionLocal))
        logger.info("Run monitor started (every %ss)", settings.run_monitor_interval_seconds)
    yield
    if monitor is not None:
        monitor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor
    await engine.dispose()
    logger.info("Shutdown complete — async engine disposed")


def operation_id(route: APIRoute) -> str:
    """
    OpenAPI ``operationId`` = the endpoint function name (``list_samples``, ``launch_run``).
    Stable and readable for generated clients; FastAPI's default appends path and method.
    """
    return route.name


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Regulated multi-omics LIMS and Nextflow orchestration API "
        "for LabChain Biologics (21 CFR Part 11 audit trail)."
    ),
    lifespan=lifespan,
    generate_unique_id_function=operation_id,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-LabChain-Workspace"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
    }
