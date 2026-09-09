"""Unit tests — MockLLMProvider structured outputs + evaluation metrics."""

import asyncio

from app.core.llm import MockLLMProvider
from app.schemas.research import (
    AgentDecisionSchema,
    CriticResultSchema,
    EvidenceAnalysisSchema,
    JudgeSchema,
    ResearchPlanSchema,
)
from app.agents.evaluator import citation_coverage, citation_validity, overall_score


def _mock() -> MockLLMProvider:
    return MockLLMProvider()


def _structured(schema, system_keyword: str, user: str):
    m = _mock()
    return asyncio.run(m.structured_output(
        [{"role": "system", "content": f"You are the {system_keyword} agent."},
         {"role": "user", "content": user}],
        schema,
    ))


def test_mock_plan_shape_and_dependency_chain():
    plan = _structured(ResearchPlanSchema, "Planner", "Research question: hybrid RAG")
    assert plan.objective.startswith("研究:")
    assert len(plan.tasks) == 6
    ids = {t.id for t in plan.tasks}
    for t in plan.tasks:
        assert t.status == "PENDING"
        for dep in t.dependencies:
            assert dep in ids, "dependencies must reference known task ids"


def test_mock_analysis_extracts_findings_from_evidence_block():
    analysis = _structured(
        EvidenceAnalysisSchema, "Analyst",
        "Evidence:\n[E1] Hybrid retrieval improves recall substantially. It combines "
        "BM25 with dense vectors.\n\n[E2] Rerankers improve precision.\n\n"
        "[E3] RRF is parameter-free and robust.\n\n",
    )
    assert len(analysis.findings) >= 3
    assert all(f.source_ids for f in analysis.findings)
    assert all(0.0 <= f.confidence <= 1.0 for f in analysis.findings)


def test_mock_critic_fails_with_low_evidence_then_passes():
    fail = _structured(
        CriticResultSchema, "Critic",
        "Evidence (ids [E1]..[En]):\n[E1] only one snippet\n\nTask status:\n"
        "- [COMPLETED] task-0: a\n- [PENDING] task-1: b\n",
    )
    assert fail.passed is False
    assert fail.new_tasks, "critic should propose a task when evidence is thin"

    ok = _structured(
        CriticResultSchema, "Critic",
        "Evidence (ids [E1]..[En]):\n" + "\n".join(f"[E{i}] chunk {i}" for i in range(1, 7))
        + "\n\nTask status:\n" + "\n".join(
            f"- [COMPLETED] task-{i}: t" for i in range(4)),
    )
    assert ok.passed is True


def test_mock_judge_scores_in_range():
    judge = _structured(JudgeSchema, "Evaluator", "Report:\n# Report\n\nAll good.")
    for v in (judge.completeness, judge.relevance, judge.evidence_quality, judge.structure):
        assert 0.0 <= v <= 1.0


def test_mock_decision_search_then_finish():
    decision = _structured(AgentDecisionSchema, "Researcher",
                           "Research question: q\n\nCurrent task: t")
    assert decision.action == "web_search"

    m = _mock()
    decision2 = asyncio.run(m.structured_output(
        [{"role": "system", "content": "You are the Researcher agent. ReAct"},
         {"role": "user", "content": "goal"},
         {"role": "tool", "content": "observation"}],
        AgentDecisionSchema,
    ))
    assert decision2.action == "finish"


def test_mock_report_contains_citations():
    m = _mock()
    report = asyncio.run(m.chat([
        {"role": "system", "content": "You are the Writer agent."},
        {"role": "user", "content": "研究问题:hybrid RAG\n\n"
         "证据:\n[E1] Hybrid retrieval combines BM25 and dense vectors.\n\n"
         "[E2] Rerankers refine candidates.\n"},
    ]))
    assert report.startswith("# 研究报告")
    assert "[1]" in report and "[2]" in report


def test_citation_metrics():
    report = "Claim one [1] and claim two [2]. Repeat [1]."
    assert citation_coverage(report, evidence_count=2) == 1.0
    assert citation_coverage(report, evidence_count=5) == 0.4
    assert citation_validity(report, evidence_count=2) == 1.0
    # out-of-range citation harms validity
    assert citation_validity("x [7]", evidence_count=2) == 0.0
    assert citation_validity("no citations", evidence_count=3) == 0.0
    assert citation_coverage("nothing", evidence_count=0) == 0.0


def test_overall_score_weighted_and_scaled_to_100():
    score = overall_score({"task_completion": 1.0, "citation": 0.5,
                           "evidence": 0.8, "judge": 0.7, "retrieval": None})
    expected = (1.0 * 0.25 + 0.5 * 0.2 + 0.8 * 0.25 + 0.7 * 0.2) / 0.9
    assert abs(score - round(expected * 100, 1)) < 0.01
