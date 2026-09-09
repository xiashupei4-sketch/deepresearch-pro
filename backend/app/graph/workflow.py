"""LangGraph multi-agent research workflow.

Flow:
    initialize → planner → researcher ⇄ (critic fail → replan) → critic →
    (pass | max iterations) → writer → evaluator → finish
"""

from __future__ import annotations

import logging

from langgraph.graph import END, StateGraph

from app.agents.analyst import AnalystAgent
from app.agents.critic import CriticAgent
from app.agents.evaluator import EvaluatorAgent, citation_coverage, citation_validity
from app.agents.planner import PlannerAgent
from app.agents.retriever import RetrieverAgent
from app.agents.researcher import ResearcherAgent
from app.agents.writer import WriterAgent
from app.config import settings
from app.core.message import utcnow
from app.graph.scheduler import mark_task, run_parallel, select_runnable, snapshot_status_block
from app.graph.state import ResearchState
from app.observability.trace import TraceEvent

logger = logging.getLogger(__name__)

MAX_EVIDENCE_FOR_WRITER = 16


class ResearchWorkflow:
    """Wires agents into a LangGraph StateGraph and executes a research run."""

    def __init__(self, llm, session_index, kb_index, tool_registry, bus,
                 tool_ctx: dict | None = None):
        self.bus = bus
        planner = PlannerAgent(llm)
        researcher = ResearcherAgent(llm, tool_registry, tool_ctx=tool_ctx)
        retriever = RetrieverAgent(llm, session_index, kb_index)
        analyst = AnalystAgent(llm)
        critic = CriticAgent(llm)
        writer = WriterAgent(llm)
        evaluator = EvaluatorAgent(llm)

        graph = StateGraph(ResearchState)
        graph.add_node("initialize", self._mk_initialize())
        graph.add_node("planner", self._mk_planner(planner))
        graph.add_node("researcher", self._mk_researcher(researcher, retriever, analyst))
        graph.add_node("replan", self._mk_replan(planner))
        graph.add_node("critic", self._mk_critic(critic))
        graph.add_node("writer", self._mk_writer(writer))
        graph.add_node("evaluator", self._mk_evaluator_node())
        graph.add_node("finish", self._mk_finish())

        graph.set_entry_point("initialize")
        graph.add_edge("initialize", "planner")
        graph.add_edge("planner", "researcher")
        graph.add_edge("researcher", "critic")
        graph.add_conditional_edges(
            "critic",
            self._route_after_critic,
            {"replan": "replan", "writer": "writer", "finish": "finish",
             "researcher": "researcher"},
        )
        graph.add_edge("replan", "researcher")
        graph.add_edge("writer", "evaluator")
        graph.add_edge("evaluator", "finish")
        graph.add_edge("finish", END)

        self.agents = {"planner": planner, "researcher": researcher, "retriever": retriever,
                       "analyst": analyst, "critic": critic, "writer": writer,
                       "evaluator": evaluator}
        self.app = graph.compile()

    async def run(self, initial_state: ResearchState) -> ResearchState:
        final = await self.app.ainvoke(initial_state)
        return final

    # -- stage helper -----------------------------------------------------------

    async def _stage(self, state: ResearchState, stage: str) -> ResearchState:
        await self.bus.emit(TraceEvent(research_id=state["research_id"], agent="System",
                                       event_type="STAGE", output_summary=stage))
        return {**state, "stages": [stage]}

    # -- nodes --------------------------------------------------------------------

    def _mk_initialize(self):
        async def initialize(state: ResearchState) -> dict:
            await self._stage(state, "理解问题")
            return {"stages": ["initialize"],
                    "context": {"started_at": utcnow().isoformat()}, "iteration": 0}
        return initialize

    def _mk_planner(self, planner: PlannerAgent):
        async def planner_node(state: ResearchState) -> dict:
            await self._stage(state, "规划研究")
            ctx = self._ctx(state, "planner")
            try:
                plan = await planner.plan(ctx, state["query"])
            except Exception as exc:  # noqa: BLE001
                logger.exception("planner failed")
                return {"error": f"Planner failed: {exc}", "stages": ["planner"]}
            tasks = []
            for i, t in enumerate(plan.tasks):
                tasks.append({**t.model_dump(), "order_index": i})
            await self.bus.emit(TraceEvent(
                research_id=state["research_id"], agent="Planner", event_type="TASK_START",
                output_summary=f"研究计划已创建 · {len(tasks)} 个任务"))
            return {"plan": plan.model_dump(), "pending_tasks": tasks,
                    "objective": plan.objective, "stages": ["planner"]}
        return planner_node

    def _mk_researcher(self, researcher: ResearcherAgent, retriever: RetrieverAgent,
                       analyst: AnalystAgent):
        async def researcher_node(state: ResearchState) -> dict:
            await self._stage(state, "检索来源")
            ctx = self._ctx(state, "researcher")
            tasks = list(state.get("pending_tasks") or [])
            done_ids = {t["id"] for t in (state.get("completed_tasks") or [])}
            runnable = select_runnable(tasks, done_ids)
            if not runnable:
                # nothing runnable right now (deps unmet) — keep pending intact
                return {"stages": ["researcher"], "pending_tasks": tasks}

            async def execute_task(task: dict) -> dict:
                tctx = self._ctx(state, "researcher", task_id=task["id"])
                await self.bus.emit(TraceEvent(
                    research_id=state["research_id"], agent="Researcher",
                    event_type="TASK_START", task_id=task["id"],
                    input_summary=task["title"]))
                try:
                    result = await researcher.run(tctx, task["title"],
                                                  task.get("description", ""),
                                                  state["query"])
                    pages = _extract_pages(result["tool_results"])
                    # 索引/检索失败只降级为"无证据",不拖垮整个任务
                    # (ReAct 与分析师结论仍有效;具体异常会以 ERROR 轨迹可见)
                    try:
                        sources = await retriever.ingest_pages(tctx, pages)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("ingest failed for %s: %s", task["id"], exc)
                        await self.bus.emit(TraceEvent(
                            research_id=state["research_id"], agent="Retriever",
                            event_type="ERROR", status="error", task_id=task["id"],
                            output_summary=f"来源索引失败(已跳过):{exc}"))
                        sources = []
                    evidence = []
                    if sources or _has_kb_chunks(result["tool_results"]):
                        await self._stage(state, "分析证据")
                        try:
                            retrieved = await retriever.retrieve(tctx, task["title"])
                            evidence = retrieved["chunks"]
                        except Exception as exc:  # noqa: BLE001
                            logger.warning("retrieve failed for %s: %s", task["id"], exc)
                            await self.bus.emit(TraceEvent(
                                research_id=state["research_id"], agent="Retriever",
                                event_type="ERROR", status="error", task_id=task["id"],
                                output_summary=f"证据检索失败(已跳过):{exc}"))
                            evidence = []
                    evidence_block = _evidence_block(evidence)
                    analysis = await analyst.analyze(
                        self._ctx(state, "analyst", task_id=task["id"]),
                        state["query"], task["title"], evidence_block)
                    await self.bus.emit(TraceEvent(
                        research_id=state["research_id"], agent="Researcher",
                        event_type="TASK_END", task_id=task["id"],
                        output_summary=f"任务完成 · 收集 {len(evidence)} 条证据"))
                    return {"task": task, "status": "COMPLETED", "sources": sources,
                            "evidence": evidence, "analysis": analysis,
                            "tool_calls": len(result["tool_results"]),
                            "tool_results": result["tool_results"]}
                except Exception as exc:  # noqa: BLE001 — a failing task must not kill the run
                    logger.exception("task %s failed", task["id"])
                    await self.bus.emit(TraceEvent(
                        research_id=state["research_id"], agent="Researcher",
                        event_type="TASK_END", task_id=task["id"], status="error",
                        output_summary=f"任务失败:{exc}"))
                    return {"task": task, "status": "FAILED", "sources": [], "evidence": [],
                            "analysis": None, "tool_calls": 0, "tool_results": []}

            outcomes = await run_parallel(runnable, execute_task,
                                          max_concurrency=settings.max_concurrency)

            new_sources, new_evidence, completed, failed, tool_count = [], [], [], [], 0
            analysis_state = dict(state.get("analysis") or {})
            analysis_state.setdefault("findings", [])
            analysis_state.setdefault("missing_information", [])
            for out in outcomes:
                task = out["task"]
                mark_task(tasks, task["id"], status=out["status"])
                if out["status"] == "COMPLETED":
                    completed.append(task)
                    new_sources.extend(out["sources"])
                    for ev in out["evidence"]:
                        new_evidence.append(ev)
                    tool_count += out["tool_calls"]
                    analysis = out["analysis"]
                    if analysis is not None:
                        data = analysis.model_dump() if hasattr(analysis, "model_dump") \
                            else analysis
                        analysis_state["findings"].extend(data.get("findings", []))
                        analysis_state["missing_information"].extend(
                            data.get("missing_information", []))
                else:
                    failed.append(task)

            remaining = [t for t in tasks if t["status"] == "PENDING"]
            return {"pending_tasks": remaining,
                    "completed_tasks": completed, "failed_tasks": failed,
                    "sources": new_sources, "evidence": new_evidence,
                    "analysis": analysis_state,
                    "tool_call_count": state.get("tool_call_count", 0) + tool_count,
                    "stages": ["researcher"], "current_task": completed[-1] if completed else None}
        return researcher_node

    def _mk_replan(self, planner: PlannerAgent):
        async def replan_node(state: ResearchState) -> dict:
            await self._stage(state, "反思审查")
            ctx = self._ctx(state, "planner")
            critique = state.get("critique") or {}
            plan = state.get("plan") or {"tasks": []}
            from app.schemas.research import CriticResultSchema

            parsed = CriticResultSchema.model_validate(critique)
            new_tasks = await planner.replan(ctx, state["query"],
                                             _plan_schema(plan), parsed)
            tasks = list(state.get("pending_tasks") or []) + \
                    [t.model_dump() for t in new_tasks]
            for i, t in enumerate(tasks):
                t.setdefault("order_index", i)
            iteration = state.get("iteration", 0) + 1
            await self.bus.emit(TraceEvent(
                research_id=state["research_id"], agent="Planner", event_type="REPLAN",
                output_summary=f"新增 {len(new_tasks)} 个任务 · 第 {iteration} 轮迭代"))
            return {"pending_tasks": tasks, "iteration": iteration, "stages": ["replan"]}
        return replan_node

    def _mk_critic(self, critic: CriticAgent):
        async def critic_node(state: ResearchState) -> dict:
            await self._stage(state, "反思审查")
            ctx = self._ctx(state, "critic")
            evidence = state.get("evidence") or []
            analysis = state.get("analysis") or {"findings": []}
            all_tasks = list(state.get("pending_tasks") or []) + \
                list(state.get("completed_tasks") or []) + list(state.get("failed_tasks") or [])
            analysis_summary = "\n".join(
                f"- {f.get('claim', '')} ({', '.join(f.get('source_ids', []))})"
                for f in analysis.get("findings", [])[:12])
            try:
                result = await critic.critique(
                    ctx, state["query"], state.get("objective", ""),
                    snapshot_status_block(all_tasks), analysis_summary,
                    _evidence_block(evidence))
            except Exception as exc:  # noqa: BLE001
                logger.exception("critic failed — passing by default")
                result_dict = {"passed": bool(evidence), "score": 0.6,
                               "issues": [f"评审不可用:{exc}"],
                               "missing_information": [], "new_tasks": []}
            else:
                result_dict = result.model_dump()
            await self.bus.emit(TraceEvent(
                research_id=state["research_id"], agent="Critic", event_type="REFLECTION",
                output_summary=("质量通过" if result_dict["passed"] else
                                f"问题:{'; '.join(result_dict['issues'][:2])}")))
            return {"critique": result_dict, "stages": ["critic"]}
        return critic_node

    def _route_after_critic(self, state: ResearchState) -> str:
        critique = state.get("critique") or {}
        if state.get("error"):
            return "finish"
        pending = state.get("pending_tasks") or []
        done_ids = {t["id"] for t in (state.get("completed_tasks") or [])}
        runnable = select_runnable(pending, done_ids)
        iteration = state.get("iteration", 0)
        budget_left = iteration < settings.max_reflection_iterations
        # outstanding executable tasks — keep researching regardless of critic verdict
        if runnable and budget_left:
            return "researcher"
        if critique.get("passed"):
            return "writer"
        if not critique.get("new_tasks") and not pending:
            return "writer"  # cannot improve further
        if not budget_left:
            return "writer"
        return "replan"

    def _mk_writer(self, writer: WriterAgent):
        async def writer_node(state: ResearchState) -> dict:
            await self._stage(state, "撰写报告")
            ctx = self._ctx(state, "writer")
            evidence = (state.get("evidence") or [])[:MAX_EVIDENCE_FOR_WRITER]
            analysis = state.get("analysis") or {"findings": []}
            analysis_summary = "\n".join(
                f"- {f.get('claim', '')} (confidence {f.get('confidence', 0)})"
                for f in analysis.get("findings", [])[:15])
            try:
                report = await writer.write(ctx, state["query"], _evidence_block(evidence),
                                            analysis_summary)
            except Exception as exc:  # noqa: BLE001
                logger.exception("writer failed")
                report = (f"# 研究报告\n\n报告生成失败:{exc}\n\n"
                          f"已收集证据:\n{_evidence_block(evidence)[:2000]}")
            await self.bus.emit(TraceEvent(
                research_id=state["research_id"], agent="Writer",
                event_type="REPORT_GENERATED", output_summary=f"报告 {len(report)} 字符"))
            return {"report": report, "stages": ["writer"]}
        return writer_node

    def _mk_evaluator_node(self):
        async def evaluator_node(state: ResearchState) -> dict:
            await self._stage(state, "评估质量")
            from app.schemas.research import JudgeSchema

            evidence = state.get("evidence") or []
            report = state.get("report") or ""
            plan = state.get("plan") or {"tasks": []}
            all_tasks = list(state.get("completed_tasks") or []) + \
                list(state.get("failed_tasks") or []) + list(state.get("pending_tasks") or [])
            task_completion = (len(state.get("completed_tasks") or []) / len(all_tasks)
                               if all_tasks else 0.0)
            citation = citation_coverage(report, len(evidence))
            validity = citation_validity(report, len(evidence))
            judge = JudgeSchema(completeness=0.8, relevance=0.85, evidence_quality=0.75,
                                structure=0.85, issues=[])
            # LLM judge (mock provides deterministic values)
            agent = self.agents.get("evaluator")
            if agent is not None:
                try:
                    judge = await agent.judge(self._ctx(state, "evaluator"),
                                              state["query"], report[:6000])
                except Exception:  # noqa: BLE001
                    pass
            from app.agents.evaluator import overall_score

            judge_avg = (judge.completeness + judge.relevance + judge.evidence_quality
                         + judge.structure) / 4
            evaluation = {
                "task_completion": round(task_completion, 3),
                "citation_score": round(citation, 3),
                "citation_validity": round(validity, 3),
                "evidence_score": round(judge.evidence_quality, 3),
                "retrieval_score": None,
                "tool_success_rate": None,
                "judge": judge.model_dump(),
                "overall": None,
            }
            evaluation["overall"] = overall_score({
                "task_completion": task_completion, "citation": citation,
                "evidence": judge.evidence_quality, "judge": judge_avg,
                "retrieval": None,
            })
            await self.bus.emit(TraceEvent(
                research_id=state["research_id"], agent="Evaluator", event_type="EVALUATION",
                output_summary=f"综合评分 {evaluation['overall']}"))
            return {"evaluation": evaluation, "stages": ["evaluator"]}
        return evaluator_node

    def _mk_finish(self):
        async def finish_node(state: ResearchState) -> dict:
            return {"stages": ["finish"],
                    "context": {**(state.get("context") or {}),
                                "finished_at": utcnow().isoformat()}}
        return finish_node

    # -- helpers ---------------------------------------------------------------

    def _ctx(self, state: ResearchState, agent: str, task_id: str | None = None):
        from app.core.agent import AgentContext

        return AgentContext(research_id=state["research_id"], bus=self.bus, task_id=task_id)


def _extract_pages(tool_results: list) -> list[dict]:
    pages: list[dict] = []
    for result in tool_results:
        if not getattr(result, "ok", False) or result.tool == "calculator":
            continue
        data = result.data if isinstance(result.data, dict) else {}
        if result.tool == "web_search":
            for r in data.get("results", [])[:5]:
                pages.append({"title": r.get("title", "无标题"), "url": r.get("url"),
                              "content": r.get("snippet", ""), "source_type": "web"})
        elif result.tool == "web_reader":
            pages.append({"title": data.get("url", "网页"), "url": data.get("url"),
                          "content": data.get("content", ""), "source_type": "web"})
        elif result.tool == "file_reader":
            pages.append({"title": data.get("path", "文件"), "url": None,
                          "content": data.get("content", ""), "source_type": "local"})
    return pages


def _has_kb_chunks(tool_results: list) -> bool:
    return any(getattr(r, "ok", False) and getattr(r, "tool", "") == "rag_search"
               for r in tool_results)


def _evidence_block(evidence: list[dict]) -> str:
    parts = []
    for i, ev in enumerate(evidence, start=1):
        meta = ev.get("metadata") or {}
        header = f"[E{i}] {ev.get('text', '')}"
        if meta.get("source_title"):
            header += f"\n(source: {meta['source_title']} · {meta.get('url') or 'local'})"
        parts.append(header)
    return "\n\n".join(parts)


def _plan_schema(plan: dict):
    from app.schemas.research import ResearchPlanSchema

    return ResearchPlanSchema.model_validate(plan)
