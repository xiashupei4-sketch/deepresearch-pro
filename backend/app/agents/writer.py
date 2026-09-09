"""Writer Agent — citation-grounded report generation."""

from __future__ import annotations

from app.core.agent import BaseAgent, AgentContext
from app.core.prompt import system, user

WRITER_SYSTEM = """You are the Writer agent. Write the final research report in Markdown.

Hard rules:
- Use ONLY the provided evidence and analysis. Never invent facts.
- Every important claim must carry a citation marker like [1], [2] mapped to the
  evidence items numbered in the evidence block.
- ALWAYS write the report in Chinese (Simplified). Section headings must be Chinese,
  e.g. # 研究报告 / ## 摘要 / ## 研究问题 / ## 研究方法 / ## 关键发现 / ## 详细分析 /
  ## 对比分析 / ## 局限性 / ## 未来方向 / ## 结论 / ## 参考文献.
- In References, list [n] Source title — domain/URL. Keep source titles/URLs as-is.
- Be concise but complete; target 600-1200 words."""


class WriterAgent(BaseAgent):
    name = "Writer"
    system_prompt = WRITER_SYSTEM
    timeout = 180

    async def write(self, ctx: AgentContext, query: str, evidence_block: str,
                    analysis_summary: str, methodology_note: str = "") -> str:
        messages = [
            system(WRITER_SYSTEM),
            user(f"研究问题:{query}\n\n"
                 f"证据(编号 [E1]..[En],引用格式 [1]..[n]):\n{evidence_block}\n\n"
                 f"分析摘要:\n{analysis_summary[:4000]}\n\n"
                 f"方法说明:{methodology_note or '多智能体混合 RAG 研究。'}\n\n"
                 f"现在撰写报告。"),
        ]
        report = await self.llm.chat(self.messages_for(ctx, messages), temperature=0.3)
        await self.trace(ctx, "AGENT_END", output_summary=f"报告 {len(report)} 字符")
        return report
