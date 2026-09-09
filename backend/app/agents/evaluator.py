"""Evaluator Agent — deterministic metrics + LLM-as-a-Judge."""

from __future__ import annotations

import re
import time

from app.core.agent import BaseAgent, AgentContext
from app.core.prompt import system, user
from app.schemas.research import JudgeSchema

JUDGE_SYSTEM = """You are the Evaluator agent acting as an LLM-as-a-Judge.
Score the research report on completeness, relevance, evidence_quality and structure
(each 0.0-1.0) and list concrete issues. Be fair and slightly strict.
ALWAYS write the issues list in Chinese (Simplified)."""


class EvaluatorAgent(BaseAgent):
    name = "Evaluator"
    system_prompt = JUDGE_SYSTEM
    timeout = 90

    async def judge(self, ctx: AgentContext, query: str, report: str) -> JudgeSchema:
        messages = [
            system(JUDGE_SYSTEM),
            user(f"Research question: {query}\n\nReport:\n{report[:6000]}\n\n"
                 f"Respond with the judge JSON."),
        ]
        return await self.run_structured(ctx, messages, JudgeSchema, temperature=0.1)


def citation_coverage(report: str, evidence_count: int) -> float:
    """Fraction of evidence items cited at least once as [n]."""
    if evidence_count == 0:
        return 0.0
    cited = set()
    for m in re.finditer(r"\[(\d+)\]", report):
        cited.add(int(m.group(1)))
    valid = {n for n in cited if 1 <= n <= evidence_count}
    return min(1.0, len(valid) / evidence_count)


def citation_validity(report: str, evidence_count: int) -> float:
    """Fraction of citation markers that map to an existing evidence item."""
    markers = list(re.finditer(r"\[(\d+)\]", report))
    if not markers:
        return 0.0
    ok = sum(1 for m in markers if 1 <= int(m.group(1)) <= evidence_count)
    return ok / len(markers)


def task_completion_rate(tasks: list[dict]) -> float:
    if not tasks:
        return 0.0
    done = sum(1 for t in tasks if t.get("status") in ("COMPLETED",))
    return done / len(tasks)


def tool_success_rate(tool_results: list) -> float:
    if not tool_results:
        return None
    ok = sum(1 for r in tool_results if getattr(r, "ok", False))
    return ok / len(tool_results)


def overall_score(parts: dict) -> float:
    weights = {"task_completion": 0.25, "citation": 0.2, "evidence": 0.25,
               "retrieval": 0.1, "judge": 0.2}
    total = 0.0
    wsum = 0.0
    for key, w in weights.items():
        v = parts.get(key)
        if v is not None:
            total += v * w
            wsum += w
    return round(total / wsum * 100, 1) if wsum else 0.0


class Stopwatch:
    def __init__(self) -> None:
        self.start = time.monotonic()

    def ms(self) -> int:
        return int((time.monotonic() - self.start) * 1000)
