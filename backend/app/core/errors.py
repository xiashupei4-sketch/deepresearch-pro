"""Unified exception hierarchy — tools/agents must never crash the whole graph."""

from __future__ import annotations


class DeepResearchError(Exception):
    """Base error for the platform."""

    def __init__(self, message: str, *, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.detail = detail


class ToolError(DeepResearchError):
    pass


class AgentError(DeepResearchError):
    pass


class LLMError(DeepResearchError):
    pass


class RetrievalError(DeepResearchError):
    pass


class MCPError(DeepResearchError):
    pass


class StorageError(DeepResearchError):
    pass
