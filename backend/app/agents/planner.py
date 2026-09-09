"""Planner Agent — Plan-and-Solve + dynamic replanning."""

from __future__ import annotations

from app.core.agent import BaseAgent, AgentContext
from app.core.prompt import system, user
from app.schemas.research import CriticResultSchema, ResearchPlanSchema, ResearchTaskSchema

PLANNER_SYSTEM = """You are the Planner agent of an autonomous deep-research system.
Your job is to decompose a complex research question into a small, executable task DAG.

Rules:
- Produce 3-8 focused tasks; never one giant task.
- Order tasks so dependencies make sense (search before analysis, analysis before synthesis).
- Each task id must be unique in the form task-N (N = 0..).
- dependencies reference earlier task ids.
- task_type is one of: search | analyze | synthesize | fetch.
- priority: 1 (critical) .. 5 (optional).
- ALWAYS write task titles, descriptions and objective in Chinese (Simplified).
"""


class PlannerAgent(BaseAgent):
    name = "Planner"
    system_prompt = PLANNER_SYSTEM
    timeout = 90

    async def plan(self, ctx: AgentContext, query: str) -> ResearchPlanSchema:
        messages = [system(PLANNER_SYSTEM),
                    user(f"Research question:\n{query}\n\nCreate the research plan.")]
        plan: ResearchPlanSchema = await self.run_structured(ctx, messages, ResearchPlanSchema,
                                                             temperature=0.2)
        plan.tasks = _validate_dag(plan.tasks)
        await self.trace(ctx, "AGENT_END",
                         output_summary=f"已创建 {len(plan.tasks)} 个任务")
        return plan

    async def replan(self, ctx: AgentContext, query: str, plan: ResearchPlanSchema,
                     critique: CriticResultSchema) -> list[ResearchTaskSchema]:
        if not critique.new_tasks:
            critique.new_tasks = [
                ResearchTaskSchema(
                    id=f"task-x{len(plan.tasks) + i}",
                    title=t or "填补证据空白",
                    description="为支撑薄弱的结论收集补充证据。",
                    task_type="search", priority=1)
                for i, t in enumerate(critique.missing_information[:3]) or []
            ]
            if not critique.new_tasks:
                critique.new_tasks = [ResearchTaskSchema(
                    id=f"task-x{len(plan.tasks)}",
                    title="深化证据收集",
                    description="检索更多权威来源以支撑关键论断。",
                    task_type="search", priority=1)]
        for t in critique.new_tasks:
            t.dependencies = []
        return critique.new_tasks


def _validate_dag(tasks: list[ResearchTaskSchema]) -> list[ResearchTaskSchema]:
    """Ensure ids are unique and dependency ids exist (drop dangling deps)."""
    ids = {t.id for t in tasks}
    seen: set[str] = set()
    for i, t in enumerate(tasks):
        if t.id in seen:
            t.id = f"task-{i}"
            ids.add(t.id)
        seen.add(t.id)
    for t in tasks:
        t.dependencies = [d for d in t.dependencies if d in ids and d != t.id]
    return tasks
