"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, knowledge, research
from app.api.routes import settings as settings_routes
from app.config import settings
from app.db import init_db
from app.services.container import build_container
from app.services.knowledge_service import KnowledgeService
from app.services.research_service import _persist_trace

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    container = build_container(persist_trace=_persist_trace)
    if container.mcp_manager is not None:
        try:
            await container.mcp_manager.connect_all()
            if container.mcp_manager.clients:
                logging.getLogger(__name__).info(
                    "MCP servers connected: %s", container.mcp_manager.available_tools())
        except Exception as exc:  # noqa: BLE001
            logging.getLogger(__name__).warning("MCP connect failed: %s", exc)
    app.state.container = container
    app.state.knowledge = KnowledgeService(container)
    app.state.settings = settings
    yield


app = FastAPI(title=settings.app_name, version="0.1.1", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(research.router)
app.include_router(knowledge.router)
app.include_router(settings_routes.router)
