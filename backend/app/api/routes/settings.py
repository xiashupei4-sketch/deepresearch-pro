"""Runtime settings API — LLM provider configuration.

前端“API 配置”弹窗的后端:支持在运行时把 Mock 提供者切换为任意
OpenAI 兼容端点(或重置回默认)。配置同时写入 DATA_DIR/llm_settings.json,
进程重启后自动恢复,优先级:运行时 > 持久化文件 > 环境变量/.env。
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import settings
from app.core.llm import (
    DEFAULT_OPENAI_BASE_URL,
    DEFAULT_OPENAI_MODEL,
    LLMError,
    OpenAICompatibleEmbeddingProvider,
    OpenAICompatibleProvider,
    _pick_embedding_model,
    clear_llm_override,
    get_embedding_provider,
    get_llm_provider,
    load_llm_override,
    save_llm_override,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])

# 运行时覆盖值(进程内存)
_runtime: dict[str, str | None] = {"api_key": None, "base_url": None, "model": None}


class LlmSettingsBody(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
    reset: bool = False


def _resolved() -> tuple[str, str, str]:
    """按优先级(运行时 > 持久化文件 > 环境变量)解析当前生效配置。"""
    override = load_llm_override()
    api_key = _runtime["api_key"] or override.get("api_key") or settings.llm_api_key or ""
    base_url = (_runtime["base_url"] or override.get("base_url")
                or settings.llm_base_url or DEFAULT_OPENAI_BASE_URL)
    model = _runtime["model"] or override.get("model") or settings.llm_model \
        or DEFAULT_OPENAI_MODEL
    return api_key, base_url, model


def _status() -> dict:
    api_key, base_url, model = _resolved()
    if api_key:
        return {"mode": "openai-compatible", "base_url": base_url, "model": model,
                "has_api_key": True}
    return {"mode": "mock", "base_url": "", "model": "", "has_api_key": False}


@router.get("/llm")
async def get_llm_settings() -> dict:
    return _status()


@router.post("/llm")
async def update_llm_settings(body: LlmSettingsBody, request: Request) -> dict:
    container = request.app.state.container
    if body.reset:
        _runtime.update({"api_key": None, "base_url": None, "model": None})
        clear_llm_override()
        container.llm = get_llm_provider()
        container.embedding = get_embedding_provider()
        container.kb_engine.embedding = container.embedding
        container.kb_engine.llm = container.llm
        logger.info("LLM provider reset to default (env/mock)")
        return _status()

    api_key, base_url, model = _resolved()
    api_key = (body.api_key or "").strip() or api_key
    if not api_key:
        raise HTTPException(400, "请填写 API Key,或选择重置为默认(Mock)模式")
    base_url = (body.base_url or "").strip() or base_url
    model = (body.model or "").strip() or model

    container.llm = OpenAICompatibleProvider(api_key=api_key, base_url=base_url,
                                             model=model)
    container.embedding = OpenAICompatibleEmbeddingProvider(
        api_key=api_key, base_url=base_url, model=_pick_embedding_model(base_url))
    container.kb_engine.embedding = container.embedding
    container.kb_engine.llm = container.llm

    _runtime.update({"api_key": api_key, "base_url": base_url, "model": model})
    save_llm_override(api_key, base_url, model)
    logger.info("LLM provider switched: %s @ %s", model, base_url)
    return _status()


class LlmTestBody(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None


@router.post("/llm/test")
async def test_llm_settings(body: LlmTestBody) -> dict:
    """连通性测试:用表单值(缺省回退到已保存配置)发一次最小 chat + embedding 请求。

    不改动运行时配置;不重试、短超时,失败时把常见错误转成可读提示。
    """
    saved_key, saved_base, saved_model = _resolved()
    api_key = (body.api_key or "").strip() or saved_key
    base_url = (body.base_url or "").strip() or saved_base
    model = (body.model or "").strip() or saved_model
    if not api_key:
        raise HTTPException(400, "请先填写 API Key")

    provider = OpenAICompatibleProvider(api_key=api_key, base_url=base_url, model=model,
                                        timeout=30.0, max_retries=0)
    start = time.perf_counter()
    try:
        reply = await provider.chat(
            [{"role": "user", "content": "请只回复两个字母:OK"}],
            temperature=0, max_tokens=8)
    except LLMError as exc:
        return {"ok": False, "error": _friendly_error(str(exc))}
    except Exception as exc:  # noqa: BLE001 — 兜底,保证前端总能拿到结果
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    latency_ms = int((time.perf_counter() - start) * 1000)

    # embedding 同步体检(知识库与会话内检索依赖它)
    embedding_client = OpenAICompatibleEmbeddingProvider(
        api_key=api_key, base_url=base_url, model=_pick_embedding_model(base_url))
    embedding_ok = True
    embedding_error: str | None = None
    try:
        await embedding_client.embed(["连通性测试"])
    except Exception as exc:  # noqa: BLE001
        embedding_ok = False
        embedding_error = _friendly_error(str(exc))

    return {"ok": True, "latency_ms": latency_ms, "model": model,
            "reply": (reply or "").strip()[:80],
            "embedding_ok": embedding_ok, "embedding_error": embedding_error}


def _friendly_error(message: str) -> str:
    """把 httpx/LLM 错误串映射为用户可读的中文提示。"""
    lowered = message.lower()
    if "401" in lowered or "unauthorized" in lowered or "invalid api key" in lowered:
        return "认证失败(401):API Key 无效或已过期"
    if "403" in lowered or "forbidden" in lowered:
        return "访问被拒绝(403):请检查 Key 权限或账户状态"
    if "404" in lowered:
        return "端点或模型不存在(404):请检查 Base URL 与模型名称"
    if "429" in lowered:
        return "请求过于频繁(429):触发限流,请稍后重试"
    if "502" in lowered or "bad gateway" in lowered:
        return "网关错误(502):代理或端点不可达,请检查网络与 Base URL"
    if "503" in lowered:
        return "服务暂不可用(503):端点过载或维护中,请稍后重试"
    if "500" in lowered:
        return "端点内部错误(500):请检查模型名称是否正确"
    if "timed out" in lowered or "timeout" in lowered:
        return "连接超时:网络不通或端点响应过慢"
    if "connect" in lowered and ("refused" in lowered or "error" in lowered):
        return "无法建立连接:请检查 Base URL 是否正确、网络是否可达"
    return message[:200]
