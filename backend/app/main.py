"""FastAPI application factory."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    actions,
    alerts,
    auth,
    chr_nodes,
    ip_pools,
    mail_config,
    monitoring,
    ws,
)
from app.config import settings
from app.services.bootstrap import bootstrap_admin_user

logger = logging.getLogger("xiguard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.log_level)
    logger.info("Xiguard API starting")
    await bootstrap_admin_user()
    yield
    logger.info("Xiguard API shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Xiguard",
        version="0.1.0",
        description="MikroTik CHR DDoS monitoring panel",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
    app.include_router(chr_nodes.router, prefix="/api/chr-nodes", tags=["chr-nodes"])
    app.include_router(ip_pools.router, prefix="/api/ip-pools", tags=["ip-pools"])
    app.include_router(monitoring.router, prefix="/api/monitoring", tags=["monitoring"])
    app.include_router(alerts.router, prefix="/api/alerts", tags=["alerts"])
    app.include_router(actions.router, prefix="/api/actions", tags=["actions"])
    app.include_router(mail_config.router, prefix="/api/settings", tags=["settings"])
    app.include_router(ws.router, prefix="/api", tags=["ws"])

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
