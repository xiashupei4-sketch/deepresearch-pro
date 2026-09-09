"""Research Service — orchestrates a full research run end to end."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DATA_DIR, settings
from app.core.message import utcnow
from app.db import AsyncSessionLocal
from app.graph.workflow import ResearchWorkflow
from app.memory.memory import MemoryService
from app.models.models import (
    EvaluationResult,
    Evidence,
    ResearchSession,
    ResearchTask,
    Source,
    TraceEvent,
)
from app.observability.trace import TraceEvent as TraceEventModel
from app.rag.engine import RAGEngine
from app.repositories import repositories as repo
from app.services.container import Container

logger = logging.getLogger(__name__)


async def _persist_trace(event: TraceEventModel) -> None:
    # pydantic 事件的 created_at 是 ISO 字符串,ORM 列是 DateTime,需显式解析
    try:
        created = datetime.fromisoformat(event.created_at)
    except (ValueError, TypeError):
        created = utcnow()
    async with AsyncSessionLocal() as db:
        db.add(TraceEvent(
            id=event.id, session_id=event.research_id, agent=event.agent,
            event_type=event.event_type, status=event.status, task_id=event.task_id,
            input_summary=event.input_summary, output_summary=event.output_summary,
            duration_ms=event.duration_ms,
            created_at=created,
        ))
        await db.commit()


class ResearchService:
    def __init__(self, container: Container):
        self.container = container
        self.memory = MemoryService(container.embedding)

    async def create_research(self, db: AsyncSession, query: str,
                              config: dict | None = None) -> ResearchSession:
        session = ResearchSession(query=query, status="PENDING",
                                  config=config or {},
                                  started_at=None)
        db.add(session)
        await db.commit()
        await db.refresh(session)
        await self.container.bus.emit(TraceEventModel(
            research_id=session.id, agent="System", event_type="AGENT_START",
            output_summary="研究任务已创建"))
        return session

    async def run_research(self, research_id: str) -> None:
        """Executed as a background task after creation."""
        start = time.monotonic()
        async with AsyncSessionLocal() as db:
            session = await repo.get_session(db, research_id)
            if session is None:
                return
            session.status = "RUNNING"
            session.started_at = utcnow()
            await db.commit()
            query = session.query

        # per-session ephemeral index (fresh vector/bm25 per research)
        session_index = RAGEngine(
            self.container.embedding, self.container.llm,
            chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap,
            vector_top_k=settings.vector_top_k, bm25_top_k=settings.bm25_top_k,
            rerank_top_k=settings.rerank_top_k)

        workflow = ResearchWorkflow(
            llm=self.container.llm, session_index=session_index,
            kb_index=self.container.kb_engine, tool_registry=self.container.tools,
            bus=self.container.bus,
            tool_ctx={"rag_engine": self.container.kb_engine, "root": str(DATA_DIR)})

        initial_state = {
            "research_id": research_id, "query": query, "iteration": 0,
            "pending_tasks": [], "completed_tasks": [], "failed_tasks": [],
            "sources": [], "evidence": [], "tool_call_count": 0,
        }
        status = "COMPLETED"
        error_msg = None
        try:
            final_state = await workflow.run(initial_state)
        except Exception as exc:  # noqa: BLE001
            logger.exception("research %s crashed", research_id)
            final_state = {}
            status = "FAILED"
            error_msg = f"{type(exc).__name__}: {exc}"
            await self.container.bus.emit(TraceEventModel(
                research_id=research_id, agent="System", event_type="ERROR",
                status="error", output_summary=error_msg))

        try:
            await self._persist_results(research_id, query, final_state, status, error_msg,
                                        int((time.monotonic() - start) * 1000))
        except Exception:  # noqa: BLE001 — persistence must never strand a session in RUNNING
            logger.exception("failed to persist results for %s", research_id)
            try:
                async with AsyncSessionLocal() as db:
                    session = await repo.get_session(db, research_id)
                    if session is not None:
                        session.status = status
                        session.error = error_msg or "结果持久化失败"
                        session.report = final_state.get("report")
                        session.finished_at = utcnow()
                        await db.commit()
            except Exception:
                logger.exception("failed to persist fallback status for %s", research_id)

    # -- persistence -------------------------------------------------------------

    async def _persist_results(self, research_id: str, query: str, state: dict,
                               status: str, error_msg: str | None, latency_ms: int) -> None:
        async with AsyncSessionLocal() as db:
            session = await repo.get_session(db, research_id)
            if session is None:
                return
            session.status = status
            session.error = error_msg
            session.report = state.get("report")
            session.iteration = state.get("iteration", 0)
            session.finished_at = utcnow()

            # clear previous rows (reflection replans may re-run persistence);
            # bulk DELETE statements run immediately — avoids insert-before-delete
            # ordering hazards when the same rows are re-inserted in one transaction
            await db.execute(delete(Evidence).where(Evidence.session_id == research_id))
            await db.execute(delete(Source).where(Source.session_id == research_id))
            await db.execute(delete(ResearchTask).where(ResearchTask.session_id == research_id))

            plan = state.get("plan") or {}
            all_tasks = list(state.get("completed_tasks") or []) + \
                list(state.get("failed_tasks") or []) + list(state.get("pending_tasks") or [])
            if not all_tasks and plan.get("tasks"):
                all_tasks = plan["tasks"]
            for i, t in enumerate(all_tasks):
                db.add(ResearchTask(
                    session_id=research_id, id=t["id"], title=t.get("title", ""),
                    description=t.get("description", ""), task_type=t.get("task_type", "search"),
                    priority=t.get("priority", 1), dependencies=t.get("dependencies", []),
                    status=t.get("status", "PENDING"), order_index=i))

            # sources — web/local pages collected during the run.
            # Workflow-level source ids (URL hashes / document ids) are only unique
            # within a session, so DB rows get fresh uuids and workflow ids are
            # mapped to them for evidence linkage.
            sid_map: dict[str, str] = {}

            def _register_source(wsid: str, **fields) -> None:
                if wsid and wsid not in sid_map:
                    db_sid = uuid.uuid4().hex
                    sid_map[wsid] = db_sid
                    db.add(Source(id=db_sid, session_id=research_id, **fields))

            for s in state.get("sources") or []:
                _register_source(s["id"], title=s.get("title", ""), url=s.get("url"),
                                 source_type=s.get("source_type", "web"),
                                 domain=s.get("domain"))
            # KB document sources referenced by evidence
            for ev in state.get("evidence") or []:
                meta = ev.get("metadata") or {}
                sid = meta.get("source_id") or meta.get("document_id")
                if sid:
                    _register_source(
                        sid,
                        title=(meta.get("document_title") or meta.get("source_title")
                               or "Document"),
                        url=meta.get("url"), source_type=meta.get("source_type", "local"),
                        domain=meta.get("domain", "local"))

            for i, ev in enumerate(state.get("evidence") or [], start=1):
                meta = ev.get("metadata") or {}
                sid = meta.get("source_id") or meta.get("document_id")
                if not sid or sid not in sid_map:
                    # guarantee FK integrity: create a source row for orphan evidence
                    sid = f"src-ev-{research_id[:8]}-{i}"
                    _register_source(
                        sid, title=meta.get("source_title") or "已收集证据",
                        url=meta.get("url"), source_type=meta.get("source_type", "web"),
                        domain=meta.get("domain", "web"))
                db.add(Evidence(session_id=research_id, source_id=sid_map[sid],
                                content=ev.get("text", ""),
                                relevance_score=ev.get("score", 0.0)))

            evaluation = state.get("evaluation")
            if evaluation and status == "COMPLETED":
                tool_events = await repo.session_traces(db, research_id)
                tool_results = [e for e in tool_events if e.event_type == "TOOL_RESULT"]
                tool_success = (sum(1 for e in tool_results if e.status == "ok")
                                / len(tool_results)) if tool_results else None
                judge = evaluation.get("judge", {})
                db.add(EvaluationResult(
                    session_id=research_id,
                    overall_score=evaluation.get("overall", 0.0),
                    task_completion=evaluation.get("task_completion", 0.0),
                    citation_score=evaluation.get("citation_score", 0.0),
                    evidence_score=evaluation.get("evidence_score", 0.0),
                    retrieval_score=None,
                    tool_success_rate=tool_success,
                    latency_ms=latency_ms,
                    judge=judge,
                    issues=judge.get("issues", []),
                    strengths=["多智能体工作流在反思循环下顺利完成"]
                    if status == "COMPLETED" else [],
                    recommendations=["可调大 max_reflection_iterations 以获得更深入的验证"],
                ))

            await db.commit()

            # long-term memory extraction (fire and forget values, best-effort)
            if status == "COMPLETED" and state.get("report"):
                try:
                    candidates = MemoryService.extract_memory_candidates(
                        query, state["report"])
                    for content, importance in candidates:
                        await self.memory.remember(db, content, research_id=research_id,
                                                   type="fact", importance=importance)
                    await db.commit()
                except Exception:  # noqa: BLE001
                    pass

            status_zh = {"COMPLETED": "完成", "FAILED": "失败"}.get(status, status)
            await self.container.bus.emit(TraceEventModel(
                research_id=research_id, agent="System", event_type="AGENT_END",
                status=status.lower(), output_summary=f"研究{status_zh}"))


def _doc_source_id(chunk_id: str) -> str:
    """For kb:: chunks, derive a stable source id from the document part."""
    doc_part = chunk_id.split("::", 1)[-1].split("::")[0]
    return doc_part or "src-unknown"
