"""ResearchState — LangGraph state contract."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict


def merge_lists(existing: list | None, updates: list | None) -> list:
    base = list(existing or [])
    for item in updates or []:
        base.append(item)
    return base


class ResearchState(TypedDict, total=False):
    research_id: str
    query: str
    objective: str
    plan: dict
    current_task: dict | None
    completed_tasks: Annotated[list, merge_lists]
    pending_tasks: list          # mutated wholesale each step
    failed_tasks: Annotated[list, merge_lists]
    sources: Annotated[list, merge_lists]
    evidence: Annotated[list, merge_lists]
    analysis: dict
    critique: dict | None
    report: str | None
    evaluation: dict | None
    iteration: int
    tool_call_count: int
    messages: Annotated[list, merge_lists]
    context: dict
    error: str | None
    stages: Annotated[list, merge_lists]
