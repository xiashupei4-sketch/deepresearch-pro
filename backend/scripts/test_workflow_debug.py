"""Detailed workflow debug run (mock mode)."""

from __future__ import annotations

import asyncio


async def main() -> None:
    from app.observability.trace import ResearchEventBus, TraceEvent
    from app.graph.workflow import ResearchWorkflow
    from app.core.llm import get_embedding_provider, get_llm_provider
    from app.rag.engine import RAGEngine
    from app.services.container import build_container

    container = build_container()
    session_index = RAGEngine(get_embedding_provider(), get_llm_provider())
    events: list[TraceEvent] = []

    async def persist(e: TraceEvent) -> None:
        events.append(e)

    bus = ResearchEventBus(persist=persist)
    wf = ResearchWorkflow(llm=container.llm, session_index=session_index,
                          kb_index=container.kb_engine, tool_registry=container.tools,
                          bus=bus, tool_ctx={"rag_engine": container.kb_engine})
    state = await wf.run({
        "research_id": "dbg-1",
        "query": "Research the main technical routes of Hybrid Retrieval and Reranking in RAG",
        "iteration": 0, "pending_tasks": [], "completed_tasks": [], "failed_tasks": [],
        "sources": [], "evidence": [], "tool_call_count": 0,
    })
    print("=== tasks ===")
    for t in (state.get("completed_tasks") + state.get("failed_tasks")
              + state.get("pending_tasks")):
        print(f"  {t['id']:>10} {t['status']:>10} {t['title'][:50]}")
    print("evidence:", len(state.get("evidence", [])))
    analysis = state.get("analysis") or {}
    print("findings:", len(analysis.get("findings", [])),
          "missing:", analysis.get("missing_information"))
    print("critique:", state.get("critique"))
    print("evaluation:", state.get("evaluation"))
    print("stages:", state.get("stages"))
    print("=== key events ===")
    for e in events:
        if e.event_type in ("REFLECTION", "REPLAN", "TASK_START", "TASK_END", "EVALUATION",
                            "REPORT_GENERATED", "ERROR"):
            tid = f" [{e.task_id}]" if e.task_id else ""
            print(f"  {e.agent:>10} {e.event_type:<12} {e.status:<6}{tid} "
                  f"{str(e.output_summary)[:70]}")


asyncio.run(main())
