"""Tool Registry — single place to register, discover and execute tools.

MCP tools are wrapped into the same interface at startup.
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ToolError
from app.core.tool import BaseTool, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool, *, replace: bool = False) -> None:
        if tool.name in self._tools and not replace:
            raise ToolError(f"Tool '{tool.name}' already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise ToolError(f"Unknown tool: {name}")
        return self._tools[name]

    def has(self, name: str) -> bool:
        return name in self._tools

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def all(self) -> dict[str, BaseTool]:
        return dict(self._tools)

    def openai_specs(self, whitelist: list[str] | None = None) -> list[dict]:
        tools = [self._tools[n] for n in whitelist if self.has(n)] if whitelist \
            else list(self._tools.values())
        return [t.to_openai_spec() for t in tools]

    async def execute(self, name: str, input_data: dict[str, Any], **ctx) -> ToolResult:
        return await self.get(name).execute(input_data, **ctx)
