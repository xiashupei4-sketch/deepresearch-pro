"""BaseTool + tool result model. All tools share timeout / retry / trace semantics."""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from app.core.errors import ToolError
from app.core.message import utcnow


class ToolResult(BaseModel):
    tool: str
    ok: bool
    data: Any = None
    summary: str = ""
    error: str | None = None
    duration_ms: int = 0


class BaseTool(ABC):
    """A tool is an atomic capability with a typed contract."""

    name: ClassVar[str] = "tool"
    description: ClassVar[str] = ""
    input_schema: ClassVar[dict] = {"type": "object", "properties": {}, "required": []}
    timeout: ClassVar[float] = 30.0
    max_retries: ClassVar[int] = 2

    async def execute(self, input_data: dict[str, Any], **ctx) -> ToolResult:
        """Public entry: applies timeout + retry with exponential backoff."""
        start = time.monotonic()
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                self._validate(input_data)
                data = await asyncio.wait_for(self._run(input_data, **ctx), timeout=self.timeout)
                dur = int((time.monotonic() - start) * 1000)
                summary = self._summarize(data)
                return ToolResult(tool=self.name, ok=True, data=data, summary=summary,
                                  duration_ms=dur)
            except (ToolError, asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.4 * (2**attempt))
        dur = int((time.monotonic() - start) * 1000)
        return ToolResult(
            tool=self.name, ok=False, error=f"{type(last_exc).__name__}: {last_exc}",
            summary=f"Tool {self.name} failed: {last_exc}", duration_ms=dur,
        )

    def _validate(self, input_data: dict[str, Any]) -> None:
        if not isinstance(input_data, dict):
            raise ToolError(f"{self.name}: input must be an object")
        required = self.input_schema.get("required", [])
        for key in required:
            if key not in input_data:
                raise ToolError(f"{self.name}: missing required field '{key}'")

    @abstractmethod
    async def _run(self, input_data: dict[str, Any], **ctx) -> Any: ...

    def _summarize(self, data: Any) -> str:
        try:
            text = json.dumps(data, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001
            text = str(data)
        return text[:200]

    def to_openai_spec(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
