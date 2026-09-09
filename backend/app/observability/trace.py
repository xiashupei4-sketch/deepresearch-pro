"""Observability: TraceEvent schema, event bus and SSE queue plumbing."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict

from pydantic import BaseModel, Field

from app.core.message import utcnow


class TraceEvent(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    research_id: str
    agent: str
    event_type: str  # AGENT_START|AGENT_END|TOOL_CALL|TOOL_RESULT|TASK_START|TASK_END|REFLECTION|REPLAN|ERROR|REPORT_GENERATED|EVALUATION|STAGE
    status: str = "ok"
    task_id: str | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    duration_ms: int | None = None
    created_at: str = Field(default_factory=lambda: utcnow().isoformat())

    def to_sse_dict(self) -> dict:
        return self.model_dump(mode="json")


def sse_format(data: dict, event: str = "trace") -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


class ResearchEventBus:
    """Per-research fan-out bus.

    * ``emit`` persists the event (fire-and-forget) and pushes to all SSE queues.
    * SSE endpoints register a queue via ``subscribe``.
    """

    def __init__(self, persist=None):
        # persist: async fn(TraceEvent) -> None
        self._queues: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._persist = persist

    def subscribe(self, research_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=512)
        self._queues[research_id].append(q)
        return q

    def unsubscribe(self, research_id: str, q: asyncio.Queue | None = None) -> None:
        if q is not None:
            if q in self._queues.get(research_id, []):
                self._queues[research_id].remove(q)
            return
        # 未指定队列时清理该会话的全部订阅(如会话被删除)
        self._queues.pop(research_id, None)

    async def emit(self, event: TraceEvent) -> None:
        if self._persist is not None:
            try:
                await self._persist(event)
            except Exception:  # noqa: BLE001 — persistence failure must not break the run
                pass
        for q in list(self._queues.get(event.research_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def emit_nowait(self, event: TraceEvent) -> None:
        """Fire-and-forget emit from sync contexts."""
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.emit(event))
        except RuntimeError:
            pass
