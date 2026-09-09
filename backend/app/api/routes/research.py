"""Research API — create, inspect, stream (SSE)."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.models import EvaluationResult, ResearchSession
from app.observability.trace import sse_format
from app.repositories import repositories as repo
from app.schemas.research import CreateResearchRequest
from app.services.research_service import ResearchService

router = APIRouter(prefix="/api/research", tags=["research"])


def _session_dict(session: ResearchSession, tasks_count: int | None = None) -> dict:
    return {
        "id": session.id, "query": session.query, "status": session.status,
        "objective": session.objective, "iteration": session.iteration,
        "pinned": bool(session.pinned),
        "report": session.report, "error": session.error,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "finished_at": session.finished_at.isoformat() if session.finished_at else None,
        "tasks_count": tasks_count,
    }


@router.post("")
async def create_research(body: CreateResearchRequest, background: BackgroundTasks,
                          request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    service = ResearchService(request.app.state.container)
    session = await service.create_research(db, body.query.strip(), body.config)
    background.add_task(service.run_research, session.id)
    return _session_dict(session, 0)


@router.get("")
async def list_research(limit: int = 30, db: AsyncSession = Depends(get_db)) -> list[dict]:
    sessions = await repo.list_sessions(db, limit=limit)
    return [_session_dict(s) for s in sessions]


class PinBody(BaseModel):
    pinned: bool


@router.patch("/{research_id}/pin")
async def pin_research(research_id: str, body: PinBody,
                       db: AsyncSession = Depends(get_db)) -> dict:
    session = await repo.set_pinned(db, research_id, body.pinned)
    if session is None:
        raise HTTPException(404, "研究会话不存在")
    return _session_dict(session)


@router.delete("/{research_id}")
async def delete_research(research_id: str, request: Request,
                          db: AsyncSession = Depends(get_db)) -> dict:
    # 若删除的是正在运行的会话,先从事件总线清理订阅
    request.app.state.container.bus.unsubscribe(research_id)
    deleted = await repo.delete_session(db, research_id)
    if not deleted:
        raise HTTPException(404, "研究会话不存在")
    return {"deleted": research_id}


@router.get("/{research_id}")
async def get_research(research_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    session = await repo.get_session(db, research_id)
    if session is None:
        raise HTTPException(404, "研究会话不存在")
    tasks = await repo.session_tasks(db, research_id)
    data = _session_dict(session, len(tasks))
    data["tasks"] = [{
        "id": t.id, "title": t.title, "description": t.description,
        "task_type": t.task_type, "priority": t.priority,
        "dependencies": t.dependencies, "status": t.status, "order_index": t.order_index,
    } for t in tasks]
    return data


@router.get("/{research_id}/plan")
async def get_plan(research_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    session = await repo.get_session(db, research_id)
    if session is None:
        raise HTTPException(404, "研究会话不存在")
    tasks = await repo.session_tasks(db, research_id)
    return {"objective": session.objective, "tasks": [{
        "id": t.id, "title": t.title, "description": t.description,
        "task_type": t.task_type, "priority": t.priority,
        "dependencies": t.dependencies, "status": t.status, "order_index": t.order_index,
    } for t in tasks]}


@router.get("/{research_id}/tasks")
async def get_tasks(research_id: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    tasks = await repo.session_tasks(db, research_id)
    return [{"id": t.id, "title": t.title, "status": t.status, "task_type": t.task_type,
             "dependencies": t.dependencies, "order_index": t.order_index} for t in tasks]


@router.get("/{research_id}/sources")
async def get_sources(research_id: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    sources = await repo.session_sources(db, research_id)
    evidence = await repo.session_evidence(db, research_id)
    used: dict[str, int] = {}
    for ev in evidence:
        used[ev.source_id] = used.get(ev.source_id, 0) + 1
    return [{
        "id": s.id, "title": s.title, "url": s.url, "author": s.author,
        "published_at": s.published_at, "source_type": s.source_type, "domain": s.domain,
        "claims_used": used.get(s.id, 0),
        "created_at": s.created_at.isoformat() if s.created_at else None,
    } for s in sources]


@router.get("/{research_id}/evidence")
async def get_evidence(research_id: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    evidence = await repo.session_evidence(db, research_id)
    return [{
        "id": ev.id, "source_id": ev.source_id, "content": ev.content[:800],
        "relevance_score": ev.relevance_score,
    } for ev in evidence]


@router.get("/{research_id}/trace")
async def get_trace(research_id: str, db: AsyncSession = Depends(get_db)) -> list[dict]:
    events = await repo.session_traces(db, research_id)
    return [{
        "id": e.id, "agent": e.agent, "event_type": e.event_type, "status": e.status,
        "task_id": e.task_id, "input_summary": e.input_summary,
        "output_summary": e.output_summary, "duration_ms": e.duration_ms,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    } for e in events]


@router.get("/{research_id}/report")
async def get_report(research_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    session = await repo.get_session(db, research_id)
    if session is None:
        raise HTTPException(404, "研究会话不存在")
    return {"id": session.id, "report": session.report, "status": session.status,
            "error": session.error}


@router.get("/{research_id}/evaluation")
async def get_evaluation(research_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    result = await repo.get_evaluation(db, research_id)
    if result is None:
        raise HTTPException(404, "评估尚未生成")
    return {
        "overall_score": result.overall_score,
        "task_completion": result.task_completion,
        "citation_score": result.citation_score,
        "evidence_score": result.evidence_score,
        "retrieval_score": result.retrieval_score,
        "tool_success_rate": result.tool_success_rate,
        "latency_ms": result.latency_ms,
        "judge": result.judge,
        "issues": result.issues,
        "strengths": result.strengths,
        "recommendations": result.recommendations,
    }


@router.get("/{research_id}/events")
async def stream_events(research_id: str, request: Request,
                        db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    session = await repo.get_session(db, research_id)
    if session is None:
        raise HTTPException(404, "研究会话不存在")

    bus = request.app.state.container.bus
    queue = bus.subscribe(research_id)

    # replay persisted history first
    history = await repo.session_traces(db, research_id)

    async def event_stream():
        try:
            for e in history:
                payload = {
                    "id": e.id, "agent": e.agent, "event_type": e.event_type,
                    "status": e.status, "task_id": e.task_id,
                    "input_summary": e.input_summary, "output_summary": e.output_summary,
                    "duration_ms": e.duration_ms,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                }
                yield sse_format(payload, event="trace")
            if session.status in ("COMPLETED", "FAILED"):
                yield sse_format({"type": "done", "status": session.status}, event="done")
                return
            idle = 0
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    idle = 0
                    yield sse_format(event.to_sse_dict(), event="trace")
                    if (event.agent == "System" and event.event_type == "AGENT_END"):
                        yield sse_format({"type": "done", "status": event.status},
                                         event="done")
                        return
                except asyncio.TimeoutError:
                    idle += 1
                    yield ": keep-alive\n\n"
                    if idle > 80:  # ~20 min without events
                        yield sse_format({"type": "timeout"}, event="done")
                        return
        finally:
            bus.unsubscribe(research_id, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })
