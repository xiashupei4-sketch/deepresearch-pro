"""Integration tests — full multi-agent workflow, fully offline.

Regression coverage for the pipeline bugs fixed during development:
* task dependency scheduling across reflection iterations
* accumulated analysis findings reaching the critic/writer
* routing that keeps researching while runnable tasks remain
* evaluator judge scoring (not zeroed out by critic-schema mismatch)
"""

from __future__ import annotations

import asyncio

from app.graph.workflow import _evidence_block
from tests.helpers import mk_workflow


def _initial_state(query: str) -> dict:
    return {"research_id": "it-1", "query": query, "iteration": 0,
            "pending_tasks": [], "completed_tasks": [], "failed_tasks": [],
            "sources": [], "evidence": [], "tool_call_count": 0}


def test_full_workflow_completes_all_tasks(fake_registry, bus, rag_pair):
    wf = mk_workflow(fake_registry, bus, rag_pair)
    state = asyncio.run(wf.run(_initial_state(
        "Research the main technical routes of Hybrid Retrieval and Reranking in RAG")))

    tasks = (state.get("completed_tasks") + state.get("failed_tasks")
             + state.get("pending_tasks"))
    assert len(tasks) == 6, "planner should create the standard 6-task plan"
    assert not state.get("pending_tasks"), "no tasks may be left pending"
    assert not state.get("failed_tasks"), f"failed: {[t['id'] for t in state.get('failed_tasks')]}"
    assert {t["status"] for t in state.get("completed_tasks")} == {"COMPLETED"}


def test_workflow_produces_report_and_evaluation(fake_registry, bus, rag_pair):
    wf = mk_workflow(fake_registry, bus, rag_pair)
    state = asyncio.run(wf.run(_initial_state("Compare hybrid retrieval vs reranking")))

    report = state.get("report") or ""
    assert len(report) > 500, "report must be substantial"
    assert report.startswith("# 研究报告")
    assert "[1]" in report, "report must cite evidence"

    evaluation = state.get("evaluation") or {}
    assert evaluation.get("overall", 0) > 50, \
        f"overall score too low: {evaluation.get('overall')}"
    assert evaluation.get("task_completion") == 1.0
    judge = evaluation.get("judge") or {}
    assert judge.get("evidence_quality", 0) > 0, "judge must not be zeroed out"


def test_workflow_accumulates_findings_and_evidence(fake_registry, bus, rag_pair):
    """Regression: per-task analysis used to be dropped (findings: 0)."""
    wf = mk_workflow(fake_registry, bus, rag_pair)
    state = asyncio.run(wf.run(_initial_state("Survey hybrid retrieval techniques")))

    analysis = state.get("analysis") or {}
    assert len(analysis.get("findings", [])) >= 3, \
        "findings from every task must accumulate in state"
    assert len(state.get("evidence", [])) >= 3, "evidence must accumulate across tasks"
    assert state.get("tool_call_count", 0) > 0


def test_workflow_emits_lifecycle_events(fake_registry, bus, rag_pair):
    seen: list[str] = []
    bus2 = type(bus)(persist=None)

    original = bus2.emit

    async def capture(event):
        seen.append(event.event_type)
        await original(event)

    bus2.emit = capture  # type: ignore[method-assign]
    wf = mk_workflow(fake_registry, bus2, rag_pair)
    asyncio.run(wf.run(_initial_state("Research RAG evaluation")))

    for expected in ("TASK_START", "TASK_END", "REFLECTION", "REPORT_GENERATED",
                     "EVALUATION"):
        assert expected in seen, f"missing lifecycle event {expected}"


def test_task_failure_does_not_crash_run(fake_registry, bus, rag_pair):
    """A tool that always fails must degrade that task, not the whole run."""
    import app.core.tool as tool_mod
    from app.core.tool import ToolResult

    class BrokenRegistry(fake_registry.__class__):
        async def execute(self, name, input_data, **ctx):
            if name == "web_search":
                return ToolResult(tool=name, ok=False, error="network down",
                                  summary="failed", duration_ms=1)
            return await super().execute(name, input_data, **ctx)

    broken = BrokenRegistry(calls=fake_registry.calls)
    wf = mk_workflow(broken, bus, rag_pair)
    state = asyncio.run(wf.run(_initial_state("Research rerankers offline")))

    # the run finishes regardless; report exists (possibly thin) and no crash
    assert (state.get("report") or "") != ""
    assert state.get("failed_tasks") or state.get("completed_tasks")


def test_evidence_block_formatting():
    block = _evidence_block([
        {"text": "claim text", "metadata": {"source_title": "Paper X"}},
        {"text": "second", "metadata": {}},
    ])
    assert block.startswith("[E1] claim text")
    assert "(source: Paper X" in block
    assert "[E2] second" in block
