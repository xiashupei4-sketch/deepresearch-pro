"""Prompt template utilities."""

from __future__ import annotations

from textwrap import dedent

from app.core.llm import Message


def system(*blocks: str) -> Message:
    return {"role": "system", "content": "\n\n".join(b.strip() for b in blocks)}


def user(*blocks: str) -> Message:
    return {"role": "user", "content": "\n\n".join(b.strip() for b in blocks)}


def assistant(content: str) -> Message:
    return {"role": "assistant", "content": content}


def tool_msg(name: str, content: str) -> Message:
    return {"role": "tool", "content": f"[tool:{name}]\n{content}"}


BASE_GUARDRAIL = dedent(
    """
    General rules:
    - Never reveal hidden chain-of-thought. Provide concise reasoning summaries only.
    - Ground every factual claim in the provided evidence or tool results.
    - Be precise, neutral and structured.
    """
)
