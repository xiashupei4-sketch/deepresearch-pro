"""MCPManager + ToolRegistry adapter."""

from __future__ import annotations

import json
from typing import Any, ClassVar

from app.core.errors import MCPError
from app.core.tool import BaseTool
from app.mcp.client import McpStdioClient, McpToolInfo


class MCPManager:
    def __init__(self, server_configs: dict[str, dict]):
        self.clients: dict[str, McpStdioClient] = {}
        self.tools: dict[str, dict[str, McpToolInfo]] = {}  # server -> tools
        self.server_configs = server_configs

    async def connect(self, server_name: str) -> None:
        cfg = self.server_configs.get(server_name)
        if not cfg:
            raise MCPError(f"Unknown MCP server: {server_name}")
        client = McpStdioClient(server_name, cfg["command"], timeout=cfg.get("timeout", 30.0))
        await client.connect()
        self.clients[server_name] = client
        self.tools[server_name] = {t.name: t for t in await client.discover_tools()}

    async def connect_all(self) -> None:
        for name in self.server_configs:
            try:
                await self.connect(name)
            except MCPError:
                continue  # unavailable servers are skipped; adapter still testable

    async def disconnect_all(self) -> None:
        for client in self.clients.values():
            await client.disconnect()
        self.clients.clear()
        self.tools.clear()

    def available_tools(self) -> dict[str, list[str]]:
        return {server: list(tools) for server, tools in self.tools.items()}

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict) -> str:
        if server_name not in self.clients:
            try:
                await self.connect(server_name)
            except MCPError as exc:
                raise MCPError(f"MCP server '{server_name}' unavailable: {exc}") from exc
        return await self.clients[server_name].call_tool(tool_name, arguments)


class McpToolAdapter(BaseTool):
    """Wraps all MCP tools behind one registered tool:

    input: {"server": "demo", "tool": "echo", "arguments": {...}}
    """

    name: ClassVar[str] = "mcp_tool"
    description: ClassVar[str] = ("Call a tool exposed by a connected MCP server. "
                                  "Input: {server, tool, arguments}.")
    input_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "server": {"type": "string"},
            "tool": {"type": "string"},
            "arguments": {"type": "object", "default": {}},
        },
        "required": ["server", "tool"],
    }
    timeout: ClassVar[float] = 30.0
    max_retries: ClassVar[int] = 1

    def __init__(self, manager: MCPManager):
        self.manager = manager

    async def _run(self, input_data: dict[str, Any], **ctx) -> Any:
        server = str(input_data["server"])
        tool = str(input_data["tool"])
        arguments = input_data.get("arguments") or {}
        text = await self.manager.call_tool(server, tool, arguments)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}
