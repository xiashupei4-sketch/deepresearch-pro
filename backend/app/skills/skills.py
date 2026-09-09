"""Skill system — composite workflows built on top of atomic tools.

* academic_research : deep plan → search → retrieve → summarize with citations
* paper_summary     : fetch + summarize a single paper/document
* fact_check        : cross-verify a claim against multiple sources
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class SkillResult(BaseModel):
    skill: str
    ok: bool
    summary: str
    data: dict = {}


class BaseSkill(ABC):
    name: str = "skill"
    description: str = ""

    @abstractmethod
    async def run(self, query: str, **ctx) -> SkillResult: ...


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, BaseSkill] = {}

    def register(self, skill: BaseSkill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> BaseSkill:
        if name not in self._skills:
            raise KeyError(f"Unknown skill: {name}")
        return self._skills[name]

    def names(self) -> list[str]:
        return list(self._skills)


def _tool_call(tools, name: str, args: dict):
    import asyncio

    return asyncio.ensure_future(tools.execute(name, args))


class AcademicResearchSkill(BaseSkill):
    """Runs a focused search → read → summarize loop with citations."""

    name = "academic_research"
    description = "Focused academic-style research on a topic with cited summary."

    def __init__(self, llm, tools, retriever=None):
        self.llm = llm
        self.tools = tools
        self.retriever = retriever

    async def run(self, query: str, **ctx) -> SkillResult:
        steps: list[dict] = []
        search = await self.tools.execute("web_search", {"query": query, "max_results": 6})
        steps.append({"tool": "web_search", "ok": search.ok,
                      "summary": search.summary})
        evidence_texts: list[str] = []
        if search.ok and isinstance(search.data, dict):
            for r in search.data.get("results", [])[:3]:
                read = await self.tools.execute("web_reader", {"url": r["url"]})
                if read.ok:
                    evidence_texts.append(read.data.get("content", "")[:1500])
                else:
                    evidence_texts.append(r.get("snippet", ""))
        summary = await self.llm.chat(
            [{"role": "system",
              "content": "Summarize findings with [n] citations mapped to sources."},
             {"role": "user", "content": f"Query: {query}\n\nEvidence:\n" +
              "\n\n".join(f"[{i+1}] {t}" for i, t in enumerate(evidence_texts))}],
            temperature=0.3)
        return SkillResult(skill=self.name, ok=True, summary=summary[:400],
                           data={"summary": summary, "sources": evidence_texts, "steps": steps})


class PaperSummarySkill(BaseSkill):
    name = "paper_summary"
    description = "Summarize a paper or document by URL."

    def __init__(self, llm, tools):
        self.llm = llm
        self.tools = tools

    async def run(self, query: str, **ctx) -> SkillResult:
        url = query if query.startswith("http") else (ctx.get("url") or "")
        if not url:
            return SkillResult(skill=self.name, ok=False, summary="A URL is required")
        read = await self.tools.execute("web_reader", {"url": url})
        if not read.ok:
            return SkillResult(skill=self.name, ok=False, summary=read.summary)
        content = read.data.get("content", "")[:6000]
        summary = await self.llm.chat(
            [{"role": "system",
              "content": ("Summarize the document: problem, method, data, results, "
                          "limitations. Markdown, concise.")},
             {"role": "user", "content": content}], temperature=0.3)
        return SkillResult(skill=self.name, ok=True, summary=summary[:400],
                           data={"summary": summary, "url": url})


class FactCheckSkill(BaseSkill):
    name = "fact_check"
    description = "Cross-verify a factual claim against multiple search results."

    def __init__(self, llm, tools):
        self.llm = llm
        self.tools = tools

    async def run(self, query: str, **ctx) -> SkillResult:
        search = await self.tools.execute("web_search", {"query": query, "max_results": 8})
        snippets: list[str] = []
        verdicts = []
        if search.ok and isinstance(search.data, dict):
            for r in search.data.get("results", []):
                snippets.append(f"{r.get('title', '')}: {r.get('snippet', '')}")
        evidence = "\n".join(f"[{i+1}] {s}" for i, s in enumerate(snippets))
        judgment = await self.llm.chat(
            [{"role": "system",
              "content": ("You are a fact-checker. For the given claim, compare the "
                          "evidence and answer SUPPORTED / CONTRADICTED / UNCLEAR with a "
                          "one-paragraph justification and cite [n].")},
             {"role": "user", "content": f"Claim: {query}\n\nEvidence:\n{evidence}"}],
            temperature=0.1)
        verdicts.append(judgment)
        return SkillResult(skill=self.name, ok=True, summary=judgment[:400],
                           data={"verdict": judgment, "evidence_count": len(snippets)})


def build_default_skills(llm, tools) -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(AcademicResearchSkill(llm, tools))
    registry.register(PaperSummarySkill(llm, tools))
    registry.register(FactCheckSkill(llm, tools))
    return registry
