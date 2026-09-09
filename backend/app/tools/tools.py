"""File Reader, Calculator and RAG Search tools."""

from __future__ import annotations

import re
from typing import Any, ClassVar

from app.core.tool import BaseTool


class FileReaderTool(BaseTool):
    """Reads a UTF-8 text/markdown file from the local workspace (sandboxed root)."""

    name: ClassVar[str] = "file_reader"
    description: ClassVar[str] = "Read a local text/markdown file inside the data directory."
    input_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }
    timeout: ClassVar[float] = 10.0

    async def _run(self, input_data: dict[str, Any], **ctx) -> Any:
        from pathlib import Path

        root = ctx.get("root") or Path("data").resolve()
        root = Path(root).resolve()
        target = (root / str(input_data["path"])).resolve()
        if not str(target).startswith(str(root)):
            raise ValueError("路径越出了沙箱根目录")
        if not target.is_file():
            raise FileNotFoundError(f"文件未找到: {input_data['path']}")
        text = target.read_text(encoding="utf-8", errors="ignore")[:20000]
        return {"path": str(target), "content": text}

    def _summarize(self, data: Any) -> str:
        return f"读取 {len(data.get('content', ''))} 字符,来源 {data.get('path', '')}"


class CalculatorTool(BaseTool):
    """Safe arithmetic evaluator (no eval of arbitrary code)."""

    name: ClassVar[str] = "calculator"
    description: ClassVar[str] = "Evaluate a numeric arithmetic expression, e.g. '2*(3+4)/7'."
    input_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {"expression": {"type": "string"}},
        "required": ["expression"],
    }

    _PATTERN = re.compile(r"^[\d\s+\-*/().%eE]*$")

    async def _run(self, input_data: dict[str, Any], **ctx) -> Any:
        expr = str(input_data["expression"]).strip()
        if not self._PATTERN.match(expr):
            raise ValueError("表达式包含不允许的字符")
        try:
            result = eval(expr, {"__builtins__": {}}, {})  # noqa: S307 — regex-constrained
            return {"expression": expr, "result": result}
        except ZeroDivisionError:
            raise ValueError("除数为零") from None

    def _summarize(self, data: Any) -> str:
        return f"{data.get('expression')} = {data.get('result')}"


class RagSearchTool(BaseTool):
    """Search the local knowledge base through the RAG engine."""

    name: ClassVar[str] = "rag_search"
    description: ClassVar[str] = ("Search the local knowledge base (hybrid retrieval) for "
                                  "relevant passages. Use for uploaded documents.")
    input_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "default": 6},
        },
        "required": ["query"],
    }
    timeout: ClassVar[float] = 30.0

    async def _run(self, input_data: dict[str, Any], **ctx) -> Any:
        engine = ctx.get("rag_engine")
        if engine is None:
            return {"query": input_data["query"], "chunks": [],
                    "note": "当前上下文中 RAG 引擎不可用"}
        result = await engine.search(input_data["query"],
                                     top_k=int(input_data.get("top_k", 6)))
        return result

    def _summarize(self, data: Any) -> str:
        chunks = data.get("chunks", []) if isinstance(data, dict) else []
        return f"rag_search 返回 {len(chunks)} 条证据片段"
