"""Critic Agent — reflection / quality gate with replan trigger."""

from __future__ import annotations

from app.core.agent import BaseAgent, AgentContext
from app.core.prompt import system, user
from app.schemas.research import CriticResultSchema

CRITIC_SYSTEM = """You are the Critic agent performing reflection on a research run.

Check:
1. Is the user question actually answered by the evidence and analysis?
2. Are the planned tasks completed?
3. Are there unsupported claims?
4. Is citation coverage sufficient (>= 4 distinct evidence ids)?
5. Do sources conflict?
6. Are key research directions missing?

Set passed=false when quality is clearly insufficient, and propose concrete
new_tasks (with unique ids like task-xN) that fix the gaps. Be conservative:
do not fail a decent run.
ALWAYS write issues, missing_information and new task titles/descriptions in
Chinese (Simplified)."""


class CriticAgent(BaseAgent):
    name = "Critic"
    system_prompt = CRITIC_SYSTEM
    timeout = 90

    async def critique(self, ctx: AgentContext, query: str, objective: str,
                       tasks_status_block: str, analysis_summary: str,
                       evidence_block: str) -> CriticResultSchema:
        messages = [
            system(CRITIC_SYSTEM),
            user(f"Research question: {query}\nObjective: {objective}\n\n"
                 f"Task status:\n{tasks_status_block}\n\n"
                 f"Analysis summary:\n{analysis_summary[:3000]}\n\n"
                 f"Evidence (ids [E1]..[En]):\n{evidence_block[:4000]}\n\n"
                 f"Evaluate and respond with the CriticResult JSON."),
        ]
        return await self.run_structured(ctx, messages, CriticResultSchema, temperature=0.1)
