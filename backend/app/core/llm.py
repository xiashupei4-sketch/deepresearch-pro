"""LLM Provider abstraction.

Business code must depend on ``LLMProvider`` only — never on a concrete vendor.

Providers
---------
* ``OpenAICompatibleProvider`` — talks to any OpenAI-compatible endpoint via httpx.
* ``MockLLMProvider`` — deterministic offline provider; without an API key the
  whole research workflow stays runnable and testable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator

from pydantic import BaseModel, ValidationError

from app.core.errors import LLMError

logger = logging.getLogger(__name__)

Message = dict[str, str]  # {"role": "system"|"user"|"assistant"|"tool", "content": str}


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def chat(self, messages: list[Message], *, temperature: float = 0.2,
                   max_tokens: int | None = None) -> str: ...

    @abstractmethod
    def stream(self, messages: list[Message], *, temperature: float = 0.2,
               max_tokens: int | None = None) -> AsyncIterator[str]: ...

    @abstractmethod
    async def structured_output(self, messages: list[Message], schema: type[BaseModel],
                                *, temperature: float = 0.2) -> BaseModel: ...


def _close_brackets(text: str) -> str:
    """补全未闭合的字符串与括号(模型输出常被 max_tokens 截断)。"""
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    if in_str:
        text += '"'
    return text + "".join("}" if c == "{" else "]" for c in reversed(stack))


def _repair_json_text(text: str) -> str:
    """修复真实模型 JSON 输出中最常见的语法错误。"""
    # 全角引号 → 半角(中文模型偶发)
    text = text.replace("“", '"').replace("”", '"')
    # 去掉尾随逗号
    text = re.sub(r",\s*([}\]])", r"\1", text)
    # 补上换行处缺失的逗号: 值结束(" 或数字或 }/]/true/false/null)后,
    # 下一行直接以 " 开头(JSON 字符串内不允许裸换行,因此这是安全的)
    text = re.sub(r'((?:true|false|null|["\d}\]])[ \t]*)\n([ \t]*")', r'\1,\n\2', text)
    return _close_brackets(text)


def _extract_json(text: str) -> dict[str, Any]:
    """Robustly extract a JSON object from an LLM response."""
    text = text.strip()
    # strip markdown fences if present
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    def _balanced_blocks(src: str) -> list[str]:
        blocks: list[str] = []
        start = src.find("{")
        depth = 0
        if start != -1:
            for i in range(start, len(src)):
                if src[i] == "{":
                    depth += 1
                elif src[i] == "}":
                    depth -= 1
                    if depth == 0:
                        blocks.append(src[start : i + 1])
                        break
        return blocks

    candidates = [text, *_balanced_blocks(text)]
    for cand in candidates:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue

    # 修复后重试(原文与首个平衡块)
    repaired = _repair_json_text(text)
    for cand in [repaired, *_balanced_blocks(repaired)]:
        try:
            return json.loads(cand)
        except json.JSONDecodeError:
            continue

    raise LLMError("Failed to parse JSON from LLM response: invalid syntax")


def schema_to_json_instruction(schema: type[BaseModel]) -> str:
    props = {}
    for name, field in schema.model_fields.items():
        props[name] = {
            "type": str(field.annotation) if field.annotation else "string",
            "description": field.description or "",
        }
    return (
        "You MUST respond with a single valid JSON object and nothing else.\n"
        f"JSON schema (fields): {json.dumps(props, ensure_ascii=False, default=str)}"
    )


def _client_trust_env(base_url: str) -> bool:
    """判断 httpx 是否应读取环境/系统代理。

    Windows 系统代理会连 localhost/内网请求一并拦截(返回 502),
    因此本机与内网端点强制直连;公网端点保持默认(机器可能需要代理出网)。
    """
    from urllib.parse import urlparse

    host = (urlparse(base_url).hostname or "").lower()
    if host in ("localhost",) or host.endswith(".local"):
        return False
    if host.startswith(("127.", "10.", "192.168.")):
        return False
    parts = host.split(".")
    if len(parts) == 4 and parts[0] == "172" and parts[1].isdigit() \
            and 16 <= int(parts[1]) <= 31:
        return False
    return True


_QUOTA_HINTS = {
    "AllocationQuota.FreeTierOnly":
        "该模型的免费额度已用完:请在阿里云百炼控制台充值或关闭「仅使用免费额度」模式,"
        "或更换仍有免费额度的模型(如 qwen-flash / qwen-plus)。",
    "Arrears": "账户欠费,请充值后重试。",
    "InvalidApiKey": "API Key 无效,请检查配置。",
    "AccessDenied": "没有该模型的访问权限,请确认已开通。",
}


def _api_error_detail(resp: Any) -> str:
    """从 API 错误响应体中提取可读信息(OpenAI/DashScope 两种结构都兼容)。"""
    code = ""
    message = ""
    try:
        data = resp.json()
        err = data.get("error") or data
        code = str(err.get("code") or "")
        message = str(err.get("message") or "")
    except Exception:  # noqa: BLE001 — body may not be JSON
        message = (resp.text or "")[:300]
    hint = _QUOTA_HINTS.get(code, "")
    parts = [p for p in (f"[{code}]" if code else "", message, hint) if p]
    return " ".join(parts) if parts else f"HTTP {resp.status_code}"


class OpenAICompatibleProvider(LLMProvider):
    """Provider for OpenAI-compatible /chat/completions APIs (OpenAI, vLLM, Ollama, etc.)."""

    name = "openai-compatible"

    def __init__(self, api_key: str, base_url: str, model: str, *, timeout: float = 120.0,
                 max_retries: int = 2):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self._trust_env = _client_trust_env(self.base_url)
        self._client: Any = None

    def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
                trust_env=self._trust_env,
            )
        return self._client

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        import httpx

        client = self._get_client()
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = await client.post("/chat/completions", json=payload)
            except httpx.HTTPError as exc:  # transport error — retryable
                last_exc = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                continue
            if resp.status_code < 400:
                return resp.json()
            detail = _api_error_detail(resp)
            # 429/5xx 可重试;4xx(鉴权/额度/参数)重试无意义,直接失败并携带原因
            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = LLMError(f"LLM endpoint returned {resp.status_code}: {detail}")
                if attempt < self.max_retries:
                    await asyncio.sleep(0.5 * (2**attempt))
                continue
            raise LLMError(f"LLM request failed: HTTP {resp.status_code}: {detail}")
        raise LLMError(
            f"LLM request failed after retries: {type(last_exc).__name__}: {last_exc}"
        ) from last_exc

    async def chat(self, messages: list[Message], *, temperature: float = 0.2,
                   max_tokens: int | None = None) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        data = await self._request(payload)
        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected LLM response shape: {data}") from exc

    async def stream(self, messages: list[Message], *, temperature: float = 0.2,
                     max_tokens: int | None = None) -> AsyncIterator[str]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        client = self._get_client()
        try:
            async with client.stream("POST", "/chat/completions", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        data = json.loads(chunk)
                        delta = data["choices"][0].get("delta", {})
                        content = delta.get("content")
                        if content:
                            yield content
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except Exception as exc:
            raise LLMError(f"LLM streaming failed: {exc}") from exc

    async def structured_output(self, messages: list[Message], schema: type[BaseModel],
                                *, temperature: float = 0.2) -> BaseModel:
        msgs = list(messages)
        instruction = schema_to_json_instruction(schema)
        if msgs and msgs[0]["role"] == "system":
            msgs[0] = {"role": "system", "content": msgs[0]["content"] + "\n\n" + instruction}
        else:
            msgs.insert(0, {"role": "system", "content": instruction})
        last_error: Exception | None = None
        retry_msgs: list[Message] | None = None
        raw = ""
        # 真实模型常输出不合 schema 或语法损坏的 JSON(缺逗号/字符串数字/null 列表)。
        # 两类错误都把具体问题发回给模型,要求修正后重试一次。
        for attempt in range(2):
            raw = await self.chat(retry_msgs or msgs, temperature=temperature)
            try:
                return schema.model_validate(_extract_json(raw))
            except ValidationError as exc:
                last_error = exc
                errors = "; ".join(
                    f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}"
                    for e in exc.errors()[:6])
                feedback = (
                    f"你返回的 JSON 未通过 Schema 校验:{errors}。\n"
                    "请严格按 Schema 返回修正后的完整 JSON 对象:字段名与类型必须一致,"
                    "数字字段用数字而非字符串,列表字段不要输出 null。只输出 JSON,不要其他文字。")
            except LLMError as exc:
                last_error = exc
                feedback = (
                    f"你返回的内容不是合法 JSON(解析错误:{exc})。\n"
                    "请重新输出完整、语法正确的 JSON 对象:字段之间用逗号分隔,"
                    "字符串内的引号必须转义,不要有多余文字或注释。只输出 JSON。")
            retry_msgs = msgs + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": feedback},
            ]
        raise LLMError(
            f"Structured output failed for {schema.__name__} after retry: {last_error}"
        ) from last_error


# ---------------------------------------------------------------------------
# Mock provider — deterministic, offline, drives the entire workflow
# ---------------------------------------------------------------------------

def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。！？])\s+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) > 12][:3]


class MockLLMProvider(LLMProvider):
    """Deterministic provider used when no API key is configured (and in tests)."""

    name = "mock"

    async def chat(self, messages: list[Message], *, temperature: float = 0.2,
                   max_tokens: int | None = None) -> str:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if "Writer" in system:
            return self._mock_report(user, messages)
        return self._mock_answer(user, system)

    async def stream(self, messages: list[Message], *, temperature: float = 0.2,
                     max_tokens: int | None = None) -> AsyncIterator[str]:
        text = await self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        for i in range(0, len(text), 24):
            yield text[i : i + 24]
            await asyncio.sleep(0.005)

    async def structured_output(self, messages: list[Message], schema: type[BaseModel],
                                *, temperature: float = 0.2) -> BaseModel:
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        schema_name = schema.__name__
        try:
            if "Planner" in system:
                return self._mock_plan(schema, user)
            if "Analyst" in system:
                return self._mock_analysis(schema, user)
            if "Critic" in system:
                return self._mock_critic(schema, user)
            if "Evaluator" in system or "Judge" in system:
                return schema.model_validate(self._mock_judge())
            if "ReAct" in system or "Researcher" in system:
                return self._mock_decision(schema, messages, user)
            return schema.model_validate({})
        except LLMError:
            raise
        except Exception as exc:  # validation errors etc.
            raise LLMError(f"Mock structured output failed for {schema_name}: {exc}") from exc

    # -- mock implementations ------------------------------------------------

    def _mock_answer(self, user: str, system: str) -> str:
        return (
            f"(Mock)基于已收集的证据,以下是对该问题的简要回答:"
            f"{user[:160]}……完整报告包含带引用的结构化发现。"
        )

    def _mock_plan(self, schema: type[BaseModel], user: str) -> BaseModel:
        topic = user.strip().splitlines()[0][:80] if user.strip() else "研究问题"
        task_defs = [
            ("了解基线研究现状", "survey", 1,
             "梳理背景、核心定义与当前研究前沿。"),
            ("检索代表性论文与来源", "search", 1,
             "收集与该问题相关的关键论文、文章与数据集。"),
            ("分析主要技术路线", "analyze", 2,
             "比较代表性方法、架构及其权衡。"),
            ("对比数据集与评估设置", "analyze", 2,
             "识别来源中使用的基准、指标与实验设置。"),
            ("识别局限性与开放挑战", "analyze", 3,
             "提取来源中声明的局限性、来源之间的冲突与研究空白。"),
            ("总结未来研究方向", "synthesize", 3,
             "基于已收集的证据推导有前景的研究方向。"),
        ]
        tasks: list[dict[str, Any]] = []
        for i, (title, ttype, prio, desc) in enumerate(task_defs):
            deps = []
            if i == 1:
                deps = [f"task-{0}"]
            elif i >= 2:
                deps = [f"task-{1}"]
            tasks.append({
                "id": f"task-{i}",
                "title": f"{title}",
                "description": desc,
                "task_type": ttype,
                "priority": prio,
                "dependencies": deps,
                "status": "PENDING",
            })
        return schema.model_validate({
            "objective": f"研究:{topic}",
            "tasks": tasks,
            "expected_output": [
                "一份带引用的研究报告",
                "代表性方法的对比",
                "未来研究方向",
            ],
        })

    def _mock_analysis(self, schema: type[BaseModel], evidence_block: str) -> BaseModel:
        findings: list[dict[str, Any]] = []
        missing: list[str] = []
        entries = re.findall(r"\[E(\d+)\]\s*([^\[]+)", evidence_block)
        for idx, (eid, content) in enumerate(entries[:6]):
            sents = _sentences(content)
            claim = sents[0] if sents else content.strip()[:140]
            findings.append({
                "claim": claim,
                "source_ids": [f"E{eid}"],
                "confidence": round(0.65 + 0.05 * (idx % 5), 2),
                "conflicts": [],
            })
        if len(entries) < 3:
            missing.append("需要更多独立来源对关键论断进行交叉验证。")
        if not findings:
            findings.append({
                "claim": "本任务收集到的证据不足。",
                "source_ids": [],
                "confidence": 0.3,
                "conflicts": [],
            })
            missing.append("当前子任务未检索到可用证据。")
        return schema.model_validate({"findings": findings, "missing_information": missing})

    def _mock_critic(self, schema: type[BaseModel], user: str) -> BaseModel:
        evidence_count = len(re.findall(r"\[E\d+\]", user))
        tasks_done = len(re.findall(r"COMPLETED", user))
        score = min(0.9, 0.35 + 0.05 * evidence_count + 0.05 * tasks_done)
        passed = evidence_count >= 4 and tasks_done >= 3
        issues: list[str] = []
        missing: list[str] = []
        new_tasks: list[dict[str, Any]] = []
        if evidence_count < 4:
            issues.append("支撑主要结论的引用证据不足。")
            missing.append("需要针对核心问题补充权威来源。")
            new_tasks.append({
                "id": f"task-extra-{int(time.time()) % 10000}",
                "title": "为支撑薄弱的论断补充证据",
                "description": "检索更多权威来源以填补证据空白。",
                "task_type": "search",
                "priority": 1,
                "dependencies": [],
                "status": "PENDING",
            })
        if tasks_done < 3:
            issues.append("部分规划的研究任务尚未完成。")
        if not passed and not issues:
            issues.append("整体质量低于阈值。")
        return schema.model_validate({
            "passed": passed,
            "score": round(score, 2),
            "issues": issues,
            "missing_information": missing,
            "new_tasks": new_tasks,
        })

    def _mock_judge(self) -> dict[str, Any]:
        return {
            "completeness": 0.82,
            "relevance": 0.9,
            "evidence_quality": 0.78,
            "structure": 0.88,
            "issues": ["部分章节依赖的来源数量较少(Mock 评估)。"],
        }

    def _mock_decision(self, schema: type[BaseModel], messages: list[Message],
                       user: str) -> BaseModel:
        tool_results = [m for m in messages if m.get("role") == "tool"]
        if not tool_results:
            query = user.strip().splitlines()[0][:100] if user.strip() else "研究主题"
            return schema.model_validate({
                "thought": "需要先从外部来源收集证据。",
                "action": "web_search",
                "action_input": json.dumps({"query": query}, ensure_ascii=False),
                "final_answer": "",
            })
        return schema.model_validate({
            "thought": "已收集的观察结果足以完成本任务。",
            "action": "finish",
            "action_input": "{}",
            "final_answer": (
                "已为本任务收集到相关证据,从搜索结果中提取了关键要点并传递给分析师。"
            ),
        })

    def _mock_report(self, user: str, messages: list[Message]) -> str:
        entries = re.findall(r"\[E(\d+)\]\s*([^\[]+)", user)
        context = next((m["content"] for m in reversed(messages)
                        if m["role"] == "user" and "证据" in m["content"]), user)
        lines: list[str] = ["# 研究报告", "", "## 摘要", ""]
        lines.append(
            "本报告总结了自主多智能体研究过程的发现,"
            "所有关键论断均以工作流中收集的引用证据为依据。"
        )
        lines += ["", "## 研究问题", "",
                  (user.split("研究问题:")[1].splitlines()[0][:400]
                   if "研究问题:" in user else "无"), ""]
        lines += ["## 研究方法", "",
                  "系统采用规划器 → 研究员 → 检索器 → 分析师 → 评审 → 写作者的流水线,"
                  "结合混合检索(BM25 + 向量 + RRF 融合 + 重排序)与反思驱动的重规划。", ""]
        lines.append("## 关键发现")
        lines.append("")
        for i, (eid, content) in enumerate(entries[:8], start=1):
            sents = _sentences(content)
            claim = sents[0] if sents else content.strip()[:150]
            lines.append(f"{i}. {claim} [{i}]")
        lines += ["", "## 详细分析", "", context[:2000], ""]
        lines += ["## 对比分析", "", "| 维度 | 观察 |", "| --- | --- |",
                  "| 来源 | 对比了多个独立来源 |",
                  "| 一致性 | 尽可能对论断进行了交叉验证 |", ""]
        lines += ["## 局限性", "",
                  "- 证据仅限于可检索到的来源。",
                  "- 部分论断依赖的来源数量较少。", ""]
        lines += ["## 未来方向", "",
                  "- 接入更专业的学术检索索引以扩展检索能力。",
                  "- 增加反思迭代轮数以获得更深入的验证。", ""]
        lines += ["## 结论", "",
                  "研究问题已得到回答,所有发现均严格来源于收集到的证据并附有引用。", ""]
        lines.append("## 参考文献")
        lines.append("")
        for i, (eid, content) in enumerate(entries[:8], start=1):
            title = content.strip().splitlines()[0][:90] if content.strip() else f"来源 {eid}"
            lines.append(f"[{i}] {title}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Embedding provider (kept alongside LLM provider for symmetry)
# ---------------------------------------------------------------------------

class EmbeddingProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]: ...

    @property
    @abstractmethod
    def dim(self) -> int: ...


class HashingEmbeddingProvider(EmbeddingProvider):
    """Deterministic feature-hashing embedding — offline fallback, no API needed.

    Uses character n-gram hashing + fixed random projection. Good enough for
    semantic-ish similarity in demo mode; swap with a real model via env config.
    """

    name = "hashing"

    def __init__(self, dim: int = 256):
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import hashlib

        out: list[list[float]] = []
        for text in texts:
            vec = [0.0] * self._dim
            t = text.lower()
            for n in (1, 2, 3):
                grams = [t[i : i + n] for i in range(0, max(1, len(t) - n + 1), max(1, n - 1))]
                for g in grams:
                    h = int(hashlib.md5(g.encode("utf-8")).hexdigest(), 16)
                    idx = h % self._dim
                    sign = 1.0 if (h >> 128) % 2 == 0 else -1.0
                    vec[idx] += sign
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out


class OpenAICompatibleEmbeddingProvider(EmbeddingProvider):
    name = "openai-compatible"

    def __init__(self, api_key: str, base_url: str, model: str, *, dim: int = 256):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._dim = dim
        self._trust_env = _client_trust_env(self.base_url)
        self._client: Any = None

    @property
    def dim(self) -> int:
        return self._dim

    def _get_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=60.0,
                trust_env=self._trust_env,
            )
        return self._client

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._get_client()
        out: list[list[float]] = []
        # 百炼等端点对单请求批量有上限(如 text-embedding-v3 为 10 条),分批发送
        for i in range(0, len(texts), 10):
            resp = await client.post("/embeddings",
                                     json={"model": self.model, "input": texts[i:i + 10]})
            resp.raise_for_status()
            data = resp.json()["data"]
            out.extend(d["embedding"] for d in data)
        return out


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


def _pick_embedding_model(base_url: str) -> str:
    """按端点选择兼容的 embedding 模型名。

    阿里云百炼(DashScope) OpenAI 兼容模式没有 OpenAI 的
    text-embedding-3-small,需使用其自有模型 text-embedding-v3。
    """
    if "dashscope.aliyuncs.com" in base_url:
        return "text-embedding-v3"
    return "text-embedding-3-small"


# ---------------------------------------------------------------------------
# Runtime LLM settings persistence — survives process restarts (JSON in DATA_DIR)
# ---------------------------------------------------------------------------

def _llm_settings_file():
    from pathlib import Path

    from app.config import DATA_DIR

    return Path(DATA_DIR) / "llm_settings.json"


def load_llm_override() -> dict:
    p = _llm_settings_file()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:  # noqa: BLE001 — corrupted file falls back to env
            pass
    return {}


def save_llm_override(api_key: str, base_url: str, model: str) -> None:
    p = _llm_settings_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"api_key": api_key, "base_url": base_url, "model": model},
                            ensure_ascii=False), encoding="utf-8")


def clear_llm_override() -> None:
    p = _llm_settings_file()
    if p.exists():
        p.unlink()


def get_llm_provider() -> LLMProvider:
    from app.config import settings

    override = load_llm_override()
    api_key = override.get("api_key") or settings.llm_api_key
    base_url = override.get("base_url") or settings.llm_base_url
    model = override.get("model") or settings.llm_model
    if api_key:
        return OpenAICompatibleProvider(
            api_key=api_key,
            base_url=base_url or DEFAULT_OPENAI_BASE_URL,
            model=model or DEFAULT_OPENAI_MODEL,
        )
    logger.info("No LLM_API_KEY configured — using MockLLMProvider (offline mode)")
    return MockLLMProvider()


def get_embedding_provider() -> EmbeddingProvider:
    from app.config import settings

    override = load_llm_override()
    api_key = override.get("api_key") or settings.llm_api_key
    base_url = override.get("base_url") or settings.llm_base_url or DEFAULT_OPENAI_BASE_URL
    if api_key:
        return OpenAICompatibleEmbeddingProvider(
            api_key=api_key,
            base_url=base_url,
            model=_pick_embedding_model(base_url),
        )
    return HashingEmbeddingProvider()
