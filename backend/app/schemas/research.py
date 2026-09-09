"""Pydantic schemas — shared structured I/O contracts for agents and API."""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator, model_validator


# --- Planner ---------------------------------------------------------------

class ResearchTaskSchema(BaseModel):
    id: str = Field(description="Unique task id, e.g. task-0")
    title: str
    description: str = ""
    task_type: str = Field(default="search", description="search|analyze|synthesize|fetch")
    priority: int = Field(default=1, description="1 (highest) .. 5")
    dependencies: list[str] = Field(default_factory=list)
    status: str = Field(default="PENDING", description="PENDING|RUNNING|COMPLETED|FAILED|SKIPPED")


class ResearchPlanSchema(BaseModel):
    objective: str
    tasks: list[ResearchTaskSchema] = Field(description="3-8 tasks forming a small DAG")
    expected_output: list[str] = Field(default_factory=list)


def _coerce_confidence(value) -> float:
    """把模型返回的宽松 confidence 表达式解析为 [0,1] 浮点数。

    兼容 "0.8" / "85%" / "8/10" / "high" / "N/A (...)" 等写法。
    """
    if isinstance(value, (int, float)):
        return min(max(float(value), 0.0), 1.0)
    if isinstance(value, str):
        t = value.strip()
        pct = "%" in t
        m = re.search(r"\d+(?:\.\d+)?", t)
        if m:
            v = float(m.group())
            if pct:
                v /= 100
            elif v > 10:
                v /= 100
            elif v > 1:
                v /= 10
            return min(max(v, 0.0), 1.0)
    return 0.5


def _coerce_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


# --- Evidence / Analyst -----------------------------------------------------

class EvidenceItem(BaseModel):
    claim: str
    source_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    conflicts: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _lenient_fields(cls, data):
        """宽容解析:真实模型常返回 source_id/content 别名、字符串置信度、null 列表。"""
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if not d.get("claim"):
            for k in ("content", "text", "evidence", "summary", "statement", "observation"):
                if d.get(k):
                    d["claim"] = str(d[k])[:600]
                    break
            else:
                d["claim"] = "(模型未返回论断内容)"
        for key in ("source_ids", "source_id", "sources"):
            if key in d and key != "source_ids":
                if d[key] and not d.get("source_ids"):
                    d["source_ids"] = d[key]
                d.pop(key, None)
        d["source_ids"] = _coerce_str_list(d.get("source_ids"))
        d["conflicts"] = _coerce_str_list(d.get("conflicts"))
        d["confidence"] = _coerce_confidence(d.get("confidence"))
        return d


class EvidenceAnalysisSchema(BaseModel):
    findings: list[EvidenceItem] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    @field_validator("missing_information", mode="before")
    @classmethod
    def _lenient_missing(cls, v):
        return _coerce_str_list(v)


# --- Critic -----------------------------------------------------------------

class CriticResultSchema(BaseModel):
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    new_tasks: list[ResearchTaskSchema] = Field(default_factory=list)

    @field_validator("score", mode="before")
    @classmethod
    def _clamp_score(cls, v):
        return _coerce_confidence(v)

    @field_validator("issues", "missing_information", mode="before")
    @classmethod
    def _lenient_lists(cls, v):
        return _coerce_str_list(v)


# --- ReAct researcher decision ----------------------------------------------

class AgentDecisionSchema(BaseModel):
    thought: str = ""
    action: str = Field(description="One of the whitelisted tool names, or 'finish'")
    action_input: str = Field(default="{}", description="JSON object string of tool args")
    final_answer: str = ""


# --- Evaluator / LLM-as-a-Judge ----------------------------------------------

class JudgeSchema(BaseModel):
    completeness: float = Field(ge=0.0, le=1.0, default=0.0)
    relevance: float = Field(ge=0.0, le=1.0, default=0.0)
    evidence_quality: float = Field(ge=0.0, le=1.0, default=0.0)
    structure: float = Field(ge=0.0, le=1.0, default=0.0)
    issues: list[str] = Field(default_factory=list)

    @field_validator("completeness", "relevance", "evidence_quality", "structure",
                     mode="before")
    @classmethod
    def _clamp_scores(cls, v):
        return _coerce_confidence(v)

    @field_validator("issues", mode="before")
    @classmethod
    def _lenient_issues(cls, v):
        return _coerce_str_list(v)


# --- API ----------------------------------------------------------------------

class CreateResearchRequest(BaseModel):
    query: str = Field(min_length=8, max_length=4000)
    config: dict = Field(default_factory=dict)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=50)


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    llm_provider: str
    database: str
