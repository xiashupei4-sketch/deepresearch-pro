"""BaseAgent — every agent shares: system prompt, LLM provider, tool whitelist,
timeout, max tool calls, trace reporting and structured I/O schemas."""

from __future__ import annotations

import time
from abc import ABC
from typing import Any, ClassVar

from pydantic import BaseModel

from app.core.llm import LLMProvider, Message
from app.core.message import utcnow
from app.core.prompt import BASE_GUARDRAIL
from app.core.tool_registry import ToolRegistry
from app.observability.trace import TraceEvent, ResearchEventBus


class AgentContext:
    """Runtime context passed into every agent invocation."""

    def __init__(self, research_id: str, bus: ResearchEventBus,
                 task_id: str | None = None, extra: dict[str, Any] | None = None):
        self.research_id = research_id
        self.bus = bus
        self.task_id = task_id
        self.extra = extra or {}


class BaseAgent(ABC):
    name: ClassVar[str] = "agent"
    system_prompt: ClassVar[str] = ""
    tool_whitelist: ClassVar[list[str]] = []
    timeout: ClassVar[float] = 120.0
    max_tool_calls: ClassVar[int] = 10

    def __init__(self, llm: LLMProvider, tools: ToolRegistry | None = None,
                 max_tool_calls: int | None = None):
        self.llm = llm
        self.tools = tools
        self.max_tool_calls = max_tool_calls or self.max_tool_calls

    # -- tracing helpers ------------------------------------------------------

    async def trace(self, ctx: AgentContext, event_type: str, *,
                    input_summary: str | None = None, output_summary: str | None = None,
                    status: str = "ok", duration_ms: int | None = None) -> None:
        await ctx.bus.emit(TraceEvent(
            research_id=ctx.research_id, agent=self.name, event_type=event_type,
            status=status, task_id=ctx.task_id, input_summary=_clip(input_summary),
            output_summary=_clip(output_summary), duration_ms=duration_ms,
        ))

    def messages_for(self, ctx: AgentContext, messages: list[Message]) -> list[Message]:
        prompt = self.system_prompt.strip() + "\n" + BASE_GUARDRAIL
        return [{"role": "system", "content": prompt}, *messages]

    async def run_structured(self, ctx: AgentContext, messages: list[Message],
                             schema: type[BaseModel], **kw) -> BaseModel:
        start = time.monotonic()
        try:
            result = await self.llm.structured_output(
                self.messages_for(ctx, messages), schema, **kw)
            await self.trace(ctx, "AGENT_END",
                             output_summary=f"结构化输出:{schema.__name__}",
                             duration_ms=int((time.monotonic() - start) * 1000))
            return result
        except Exception as exc:
            await self.trace(ctx, "ERROR", status="error",
                             output_summary=f"{type(exc).__name__}: {exc}",
                             duration_ms=int((time.monotonic() - start) * 1000))
            raise


def _clip(text: str | None, limit: int = 400) -> str | None:
    if text is None:
        return None
    return text if len(text) <= limit else text[:limit] + "…"
