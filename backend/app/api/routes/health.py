"""Health & readiness."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.research import HealthResponse

router = APIRouter()


@router.get("/api/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    container = request.app.state.container
    return HealthResponse(
        status="ok",
        app=request.app.state.settings.app_name,
        version="0.1.0",
        llm_provider=container.llm.name,
        database="sqlite" if "sqlite" in request.app.state.settings.database_url else "postgres",
    )
