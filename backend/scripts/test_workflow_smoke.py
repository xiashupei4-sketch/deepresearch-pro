"""Quick in-process validation of the full research workflow (mock mode)."""

from __future__ import annotations

import asyncio
import sys


async def main() -> None:
    from app.core.llm import get_llm_provider
    from app.observability.trace import ResearchEventBus, TraceEvent
    from app.graph.workflow import ResearchWorkflow
    from app.rag.engine import RAGEngine
    from app.core.llm import get_embedding_provider
    from app.services.container import build_container
    from app.config import settings

    container = build_container()
    session_index = RAGEngine(get_embedding_provider(), get_llm_provider())
    seen = []

    async def persist(e: TraceEvent) -> None:
        seen.append(f"{e.agent}:{e.event_type}:{e.output_summary}")

    bus = ResearchEventBus(persist=persist)
    wf = ResearchWorkflow(llm=container.llm, session_index=session_index,
                          kb_index=container.kb_engine, tool_registry=container.tools,
                          bus=bus, tool_ctx={"rag_engine": container.kb_engine})
    state = await wf.run({
        "research_id": "test-123",
        "query": "Research the main technical routes of Hybrid Retrieval and Reranking in RAG",
        "iteration": 0, "pending_tasks": [], "completed_tasks": [], "failed_tasks": [],
        "sources": [], "evidence": [], "tool_call_count": 0,
    })
    print("completed:", len(state.get("completed_tasks", [])),
          "pending:", len(state.get("pending_tasks", [])),
          "failed:", len(state.get("failed_tasks", [])))
    print("sources:", len(state.get("sources", [])),
          "evidence:", len(state.get("evidence", [])))
    ev = state.get("evaluation") or {}
    print("eval overall:", ev.get("overall"), "task_completion:", ev.get("task_completion"),
          "citation:", ev.get("citation_score"))
    report = state.get("report") or ""
    print("report chars:", len(report))
    print("findings:", len((state.get("analysis") or {}).get("findings", [])))
    for line in seen[:14]:
        print(" ", line)
    sys.exit(0 if len(state.get("evidence", [])) > 0 and len(report) > 500 else 1)


asyncio.run(main())
