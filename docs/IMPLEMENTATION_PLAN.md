# DeepResearch Pro — Implementation Plan

> Multi-Agent + RAG + MCP + Context Engineering 自主深度研究与知识工作平台

## 阶段计划（P0 → P1 → P2）

| Phase | 内容 | 优先级 | 状态 |
|-------|------|--------|------|
| 0 | Bootstrap：仓库结构 / FastAPI / Vite / config / SQLite / health | P0 | ✅ |
| 1 | LLM Core：LLMProvider 抽象、OpenAICompatible、Mock、structured output、streaming | P0 | ✅ |
| 2 | Agent Core：BaseAgent / BaseTool / ToolRegistry / Runtime / AgentMessage / ReAct | P0 | ✅ |
| 3 | Planner：ResearchPlan / ResearchTask / plan() / replan() | P0 | ✅ |
| 4 | Tools：web_search / web_reader / file_reader / calculator + retry/timeout | P0 | ✅ |
| 5 | RAG：parser / cleaner / chunker / embedding / vector store / BM25 / hybrid / RRF / rerank | P0 | ✅ |
| 6 | Multi-Agent：Researcher / Retriever / Analyst / Critic / Writer / Evaluator | P0 | ✅ |
| 7 | LangGraph：ResearchState / nodes / conditional routing / reflection loop | P0 | ✅ |
| 8 | Memory：working / short-term / long-term + extractor | P1 | ✅ |
| 9 | Context Engineering：token counter / selector / compressor / builder / budget | P1 | ✅ |
| 10 | MCP + Skills：MCPManager、MCP tool adapter、3 skills | P1 | ✅ |
| 11 | Observability：TraceEvent / event bus / SSE / persistence | P1 | ✅ |
| 12 | Evaluation：deterministic metrics + LLM-as-a-Judge | P1 | ✅ |
| 13 | Frontend：Design System / App Shell / Home / Workspace / Report / Evaluation / Knowledge | P0 | ✅ |
| 14 | Testing & Hardening：unit / integration / browser verification | P1 | ✅ |
| 15 | Delivery：Docker / README / docs / demo data / final acceptance | P2 | ✅ |

## 关键设计决策

1. **LLM Provider Abstraction**：`LLMProvider` 抽象基类；`OpenAICompatibleProvider`（httpx 直连，无 SDK 锁定）+ `MockLLMProvider`（无 Key 也能全流程演示）。业务代码只依赖抽象。
2. **Mock 优先策略**：无 API Key 时 Mock LLM 返回确定性结构化输出（计划/分析/评审/报告模板），Web Search fallback 为 DuckDuckGo HTML + 内置 seed 语料，保证 RAG/Workflow 可测试。
3. **Hybrid RAG**：BM25 自实现（无外部重型依赖）、向量检索优先 FAISS fallback 内存实现、RRF 融合、reranker 支持规则/LLM 两种。
4. **LangGraph 编排**：initialize → planner → researcher → retriever → analyst → critic →(cond) writer/…，critic FAIL 且未超次数时 replan 回 researcher。
5. **Context Engineering**：token budget（chars/4 估算 + tiktoken 可选），selector 按优先级（system > goal > task > evidence > memory > messages）装配，超预算时压缩/裁剪。
6. **Observability**：TraceEvent 持久化 SQLite/PG，经 Event Bus 广播到 SSE `/api/research/{id}/events`。
7. **前端**：React + TS + Vite + Tailwind + Zustand，Linear/Vercel 式中性设计系统，CSS variables design tokens，Light/Dark，三栏 Workspace，SSE 实时 Trace Timeline。
8. **数据库**：SQLAlchemy 2.x + Alembic，开发 SQLite，compose 提供 PostgreSQL。

## 第一版明确不做

支付、RBAC、K8s、微服务拆分、跨机器 A2A、SFT/GRPO、分布式任务队列。
