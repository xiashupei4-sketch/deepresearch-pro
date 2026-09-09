"""Analyst Agent — evidence analysis only (no searching)."""

from __future__ import annotations

from app.core.agent import BaseAgent, AgentContext
from app.core.prompt import system, user
from app.schemas.research import EvidenceAnalysisSchema

ANALYST_SYSTEM = """You are the Analyst agent. You analyze collected evidence only — you
never search. Compare sources, aggregate common conclusions, flag conflicts,
estimate claim confidence and list information gaps that block answering the question."""


class AnalystAgent(BaseAgent):
    name = "Analyst"
    system_prompt = ANALYST_SYSTEM
    timeout = 90

    async def analyze(self, ctx: AgentContext, query: str, task_title: str,
                      evidence_block: str) -> EvidenceAnalysisSchema:
        messages = [
            system(ANALYST_SYSTEM),
            user(f"Research question: {query}\nCurrent task: {task_title}\n\n"
                 f"Evidence collected:\n{evidence_block or '(no evidence)'}\n\n"
                 f"Analyze the evidence: extract claims with source ids ([E1], [E2], ...), "
                 f"confidence, conflicts, and list missing information."),
        ]
        return await self.run_structured(ctx, messages, EvidenceAnalysisSchema, temperature=0.2)
