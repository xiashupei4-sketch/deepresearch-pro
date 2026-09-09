"""Test helpers: offline fake tool registry + workflow factory (no network)."""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ensure `app` imports work regardless of pytest invocation cwd
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.tool import ToolResult  # noqa: E402


@dataclass
class FakeRegistry:
    """Offline stand-in for ToolRegistry — returns canned results instantly."""

    calls: list[tuple[str, dict]] = field(default_factory=list)

    def has(self, name: str) -> bool:
        return name in {"web_search", "web_reader", "rag_search", "calculator"}

    async def execute(self, name: str, input_data: dict[str, Any], **ctx) -> ToolResult:
        self.calls.append((name, input_data))
        if name == "web_search":
            q = input_data.get("query", "")
            data: dict[str, Any] = {
                "results": [
                    {"title": f"Hybrid retrieval overview — {q}",
                     "url": "https://example.org/hybrid",
                     "snippet": "Hybrid retrieval combines BM25 keyword search with dense "
                                "vector retrieval to improve recall. Reciprocal rank fusion "
                                "merges both rankings into a single robust ordering."},
                    {"title": f"Reranking methods survey — {q}",
                     "url": "https://example.org/rerank",
                     "snippet": "Cross-encoder rerankers such as ColBERT and MonoT5 "
                                "substantially improve precision over first-stage retrieval "
                                "at the cost of additional inference latency."},
                ]
            }
        elif name == "web_reader":
            data = {"url": input_data.get("url", "https://example.org"),
                    "content": "<p>Dense retrieval uses bi-encoder embeddings. BM25 "
                               "remains a strong sparse baseline. Hybrid search with "
                               "RRF fusion and cross-encoder reranking is the dominant "
                               "production pattern in modern RAG pipelines.</p>"}
        elif name == "rag_search":
            engine = (ctx or {}).get("rag_engine")
            if engine is not None:
                res = await engine.search(input_data.get("query", ""), top_k=3)
                data = {"chunks": res["chunks"]}
            else:
                data = {"chunks": []}
        else:
            data = {"value": 42}
        return ToolResult(tool=name, ok=True, data=data, summary=f"ok: {name}",
                          error=None, duration_ms=1)


def mk_workflow(fake_registry: FakeRegistry, bus, rag_pair):
    """Build a ResearchWorkflow wired to offline fakes.

    必须强制使用 MockLLMProvider:get_llm_provider() 会读到 data/llm_settings.json
    中用户配置的真实 API,导致"离线"测试泄漏到真实 API(慢/烧配额/不稳定)。
    """
    from app.core.llm import MockLLMProvider
    from app.graph.workflow import ResearchWorkflow

    session_index, kb_index = rag_pair
    return ResearchWorkflow(
        llm=MockLLMProvider(), session_index=session_index, kb_index=kb_index,
        tool_registry=fake_registry, bus=bus,
        tool_ctx={"rag_engine": kb_index, "root": "."},
    )
