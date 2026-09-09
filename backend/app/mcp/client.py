"""Minimal MCP (Model Context Protocol) client over stdio JSON-RPC 2.0.

Implements: initialize handshake → tools/list → tools/call.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field

from app.core.errors import MCPError


@dataclass
class McpToolInfo:
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)


class McpStdioClient:
    """Speaks line-delimited JSON-RPC 2.0 with an MCP server subprocess."""

    def __init__(self, name: str, command: list[str], *, timeout: float = 30.0):
        self.name = name
        self.command = command
        self.timeout = timeout
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int | str, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._proc is not None:
            return
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *self.command, stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        except OSError as exc:
            raise MCPError(f"MCP server '{self.name}' failed to start: {exc}") from exc
        self._reader_task = asyncio.create_task(self._read_loop())
        await self._request("initialize", {
            "protocolVersion": "2024-11-05", "capabilities": {},
            "clientInfo": {"name": "deepresearch-pro", "version": "0.1.0"},
        })
        await self._notify("notifications/initialized", {})

    async def disconnect(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=3)
            except (ProcessLookupError, asyncio.TimeoutError):
                pass
            self._proc = None
        if self._reader_task is not None:
            self._reader_task.cancel()
            self._reader_task = None

    async def discover_tools(self) -> list[McpToolInfo]:
        result = await self._request("tools/list", {})
        tools = []
        for t in result.get("tools", []):
            tools.append(McpToolInfo(name=t.get("name", ""), description=t.get("description", ""),
                                     input_schema=t.get("inputSchema", {})))
        return tools

    async def call_tool(self, tool_name: str, arguments: dict) -> str:
        result = await self._request("tools/call", {"name": tool_name, "arguments": arguments})
        parts = result.get("content", [])
        texts = [p.get("text", "") for p in parts if p.get("type") == "text"]
        return "\n".join(texts) or json.dumps(result, ensure_ascii=False)

    # -- plumbing -----------------------------------------------------------------

    async def _request(self, method: str, params: dict) -> dict:
        async with self._lock:
            if self._proc is None or self._proc.stdin is None:
                raise MCPError(f"MCP server '{self.name}' is not connected")
            rid = self._next_id
            self._next_id += 1
            payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
            fut: asyncio.Future = asyncio.get_running_loop().create_future()
            self._pending[rid] = fut
            try:
                line = json.dumps(payload, ensure_ascii=False) + "\n"
                self._proc.stdin.write(line.encode("utf-8"))
                await self._proc.stdin.drain()
                return await asyncio.wait_for(fut, timeout=self.timeout)
            except asyncio.TimeoutError:
                raise MCPError(f"MCP request '{method}' timed out") from None
            finally:
                self._pending.pop(rid, None)

    async def _notify(self, method: str, params: dict) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        payload = {"jsonrpc": "2.0", "method": method, "params": params}
        self._proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
        await self._proc.stdin.drain()

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            while True:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                try:
                    message = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                rid = message.get("id")
                if rid is not None and rid in self._pending:
                    fut = self._pending.pop(rid)
                    if "error" in message:
                        err = message["error"]
                        fut.set_exception(MCPError(f"MCP error: {err}"))
                    else:
                        fut.set_result(message.get("result", {}))
        except asyncio.CancelledError:
            pass
