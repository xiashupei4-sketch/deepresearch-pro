"""Researcher Agent — ReAct loop with tool calling."""

from __future__ import annotations

import json

from app.core.agent import BaseAgent, AgentContext
from app.core.llm import Message
from app.core.prompt import BASE_GUARDRAIL, tool_msg, user
from app.core.tool_registry import ToolRegistry
from app.schemas.research import AgentDecisionSchema

RESEARCHER_SYSTEM = """You are the Researcher agent, a ReAct agent for web research.

Available tools: {tool_list}. Use ONLY these exact tool names.

Use the loop:
1. Decide the next action (a tool call or 'finish').
2. Observe the tool result.
3. Repeat until the task goal is satisfied, then 'finish' with a concise summary.

Rules:
- Prefer precise, information-dense queries.
- After collecting enough observations (usually 1-3 tool calls), finish.
- The final answer must summarize the findings, not the reasoning process.
- ALWAYS write 'thought' and 'final_answer' in Chinese (Simplified).
"""

# 模型常把工具名写成近义词,归一化到白名单,避免"未知工具"导致任务中断
_TOOL_ALIASES = {
    "search": "web_search",
    "websearch": "web_search",
    "web-search": "web_search",
    "read": "web_reader",
    "reader": "web_reader",
    "web_read": "web_reader",
    "rag": "rag_search",
    "retrieval": "rag_search",
    "retrieve": "rag_search",
    "knowledge_base": "rag_search",
    "calc": "calculator",
}


class ResearcherAgent(BaseAgent):
    name = "Researcher"
    system_prompt = RESEARCHER_SYSTEM
    tool_whitelist = ["web_search", "web_reader", "rag_search", "file_reader", "calculator",
                      "mcp_tool"]
    timeout = 120.0
    max_tool_calls = 6

    def __init__(self, llm, tools: ToolRegistry, *, max_tool_calls: int | None = None,
                 tool_ctx: dict | None = None):
        super().__init__(llm, tools, max_tool_calls=max_tool_calls)
        self.tool_ctx = tool_ctx or {}

    def messages_for(self, ctx: AgentContext, messages: list[Message]) -> list[Message]:
        """把真实工具白名单注入系统提示词,模型才能返回正确的工具名。"""
        prompt = (RESEARCHER_SYSTEM.replace("{tool_list}", ", ".join(self.tool_whitelist))
                  + "\n" + BASE_GUARDRAIL)
        return [{"role": "system", "content": prompt}, *messages]

    async def run(self, ctx: AgentContext, task_title: str, task_description: str,
                  query: str) -> dict:
        """Runs the ReAct loop for one research task.

        Returns {"final_answer": str, "tool_results": [ToolResult...], "steps": int}
        """
        goal = (f"Research question: {query}\n\n"
                f"Current task: {task_title}\n"
                f"Task details: {task_description or task_title}\n\n"
                f"Start by deciding your first action.")
        messages: list[dict[str, str]] = [user(goal)]
        tool_results: list = []
        await self.trace(ctx, "AGENT_START", input_summary=task_title)

        for step in range(self.max_tool_calls):
            decision: AgentDecisionSchema = await self.run_structured(
                ctx, self.messages_for(ctx, messages), AgentDecisionSchema, temperature=0.1)
            if decision.action == "finish" or not decision.action:
                await self.trace(ctx, "AGENT_END", output_summary="ReAct 循环完成")
                return {"final_answer": decision.final_answer or "未获得发现。",
                        "tool_results": tool_results, "steps": step}
            action = _TOOL_ALIASES.get(decision.action.strip().lower(), decision.action.strip())
            if self.tools is None or not self.tools.has(action):
                await self.trace(ctx, "ERROR", status="error",
                                 output_summary=f"未知工具 {action}")
                break
            try:
                tool_input = json.loads(decision.action_input) if decision.action_input else {}
            except json.JSONDecodeError:
                tool_input = {"query": decision.action_input}
            if action == "web_search" and "query" not in tool_input:
                tool_input = {"query": task_title}
            await self.trace(ctx, "TOOL_CALL",
                             input_summary=f"{action} {json.dumps(tool_input,
                                                                  ensure_ascii=False)[:200]}")
            result = await self.tools.execute(action, tool_input, **self.tool_ctx)
            tool_results.append(result)
            await self.trace(ctx, "TOOL_RESULT", status="ok" if result.ok else "error",
                             output_summary=result.summary,
                             duration_ms=result.duration_ms)
            messages.append(tool_msg(decision.action, result.summary or str(result.error)))

        await self.trace(ctx, "AGENT_END", output_summary="达到最大工具调用次数")
        summary = " | ".join(r.summary for r in tool_results[:3]) or "无工具结果。"
        return {"final_answer": summary, "tool_results": tool_results,
                "steps": len(tool_results)}
