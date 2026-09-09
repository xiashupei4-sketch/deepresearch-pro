"""Global dependency container — one instance per app process."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.config import CONFIG_YAML_PATH, settings
from app.core.llm import EmbeddingProvider, LLMProvider, get_embedding_provider, get_llm_provider
from app.core.tool_registry import ToolRegistry
from app.mcp.manager import MCPManager, McpToolAdapter
from app.observability.trace import ResearchEventBus
from app.rag.engine import RAGEngine
from app.tools.tools import CalculatorTool, FileReaderTool, RagSearchTool
from app.tools.web_search import WebReaderTool, WebSearchTool

logger = logging.getLogger(__name__)


@dataclass
class Container:
    llm: LLMProvider
    embedding: EmbeddingProvider
    kb_engine: RAGEngine
    tools: ToolRegistry
    bus: ResearchEventBus
    mcp_manager: MCPManager | None = None
    skills: dict = field(default_factory=dict)


def load_mcp_server_configs() -> dict[str, dict]:
    if not CONFIG_YAML_PATH.exists():
        return {}
    try:
        import yaml

        data = yaml.safe_load(CONFIG_YAML_PATH.read_text(encoding="utf-8")) or {}
        servers = (data.get("mcp") or {}).get("servers") or {}
        return {name: cfg for name, cfg in servers.items() if cfg.get("enabled")}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load config.yaml: %s", exc)
        return {}


def build_container(persist_trace=None) -> Container:
    llm = get_llm_provider()
    embedding = get_embedding_provider()

    kb_engine = RAGEngine(
        embedding, llm,
        chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap,
        vector_top_k=settings.vector_top_k, bm25_top_k=settings.bm25_top_k,
        rerank_top_k=settings.rerank_top_k)

    tools = ToolRegistry()
    tools.register(WebSearchTool())
    tools.register(WebReaderTool())
    tools.register(FileReaderTool())
    tools.register(CalculatorTool())
    tools.register(RagSearchTool())

    bus = ResearchEventBus(persist=persist_trace)

    mcp_cfg = load_mcp_server_configs()
    mcp_manager = MCPManager(mcp_cfg) if mcp_cfg else None
    if mcp_manager is not None:
        tools.register(McpToolAdapter(mcp_manager), replace=True)

    return Container(llm=llm, embedding=embedding, kb_engine=kb_engine, tools=tools, bus=bus,
                     mcp_manager=mcp_manager)
