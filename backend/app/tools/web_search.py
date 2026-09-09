"""Web Search tool.

Primary provider: DuckDuckGo HTML (no API key needed).
Fallback: built-in offline seed corpus so the research workflow keeps working
in sandboxed/offline environments (results are clearly labelled).
"""

from __future__ import annotations

import json
import re
from typing import Any, ClassVar

import httpx

from app.core.tool import BaseTool, ToolResult

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# Small offline corpus used when no network is available (labelled clearly).
_SEED_RESULTS: dict[str, list[dict[str, str]]] = {
    "default": [
        {"title": "研究主题概述(离线种子语料)",
         "url": "https://example.org/offline/overview",
         "snippet": "离线种子结果。沙箱环境中无法访问实时网络,因此使用该确定性语料"
                    "对完整研究工作流进行端到端演练。"},
        {"title": "方法学综述(离线种子语料)",
         "url": "https://example.org/offline/methodology",
         "snippet": "综述型种子文档,描述与研究问题相关的常见方法、数据集与评估协议。"},
        {"title": "开放挑战与未来方向(离线种子语料)",
         "url": "https://example.org/offline/future",
         "snippet": "种子内容,列举文献中讨论的典型开放挑战、局限性与未来研究方向。"},
    ],
}


def _parse_ddg(html: str, limit: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    for m in re.finditer(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html, re.DOTALL):
        url = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        # DDG redirect links: //duckduckgo.com/l/?uddg=<encoded>
        if "uddg=" in url:
            from urllib.parse import parse_qs, urlparse

            try:
                q = parse_qs(urlparse("https:" + url if url.startswith("//") else url).query)
                url = q.get("uddg", [url])[0]
            except Exception:  # noqa: BLE001
                pass
        results.append({"title": title, "url": url, "snippet": ""})
        if len(results) >= limit:
            break
    # snippets
    snips = re.findall(r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', html, re.DOTALL)
    for i, s in enumerate(snips[:len(results)]):
        results[i]["snippet"] = re.sub(r"<[^>]+>", "", s).strip()
    return [r for r in results if r["title"]]


class WebSearchTool(BaseTool):
    name: ClassVar[str] = "web_search"
    description: ClassVar[str] = "Search the public web for a query. Returns a list of results."
    input_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "max_results": {"type": "integer", "description": "1-10", "default": 6},
        },
        "required": ["query"],
    }
    timeout: ClassVar[float] = 20.0
    max_retries: ClassVar[int] = 1

    async def _run(self, input_data: dict[str, Any], **ctx) -> Any:
        query = str(input_data["query"]).strip()[:400]
        max_results = min(int(input_data.get("max_results", 6)), 10)
        try:
            async with httpx.AsyncClient(headers={"User-Agent": _UA}, timeout=12.0,
                                         follow_redirects=True) as client:
                resp = await client.post("https://html.duckduckgo.com/html/",
                                         data={"q": query})
                resp.raise_for_status()
                results = _parse_ddg(resp.text, max_results)
                if results:
                    return {"query": query, "provider": "duckduckgo", "results": results,
                            "offline": False}
        except Exception:  # noqa: BLE001 — fall through to offline seeds
            pass
        return {"query": query, "provider": "offline_seed", "results": _SEED_RESULTS["default"],
                "offline": True,
                "note": "实时网络搜索不可用,已使用确定性离线语料。"}

    def _summarize(self, data: Any) -> str:
        rs = data.get("results", []) if isinstance(data, dict) else []
        return f"{len(rs)} 条结果({data.get('provider', '?')})" if rs else "无结果"


class WebReaderTool(BaseTool):
    """Reads a URL and returns cleaned text. SSRF-protected."""

    name: ClassVar[str] = "web_reader"
    description: ClassVar[str] = "Fetch a web page and return its main text content."
    input_schema: ClassVar[dict] = {
        "type": "object",
        "properties": {"url": {"type": "string"}},
        "required": ["url"],
    }
    timeout: ClassVar[float] = 25.0
    max_retries: ClassVar[int] = 1

    async def _run(self, input_data: dict[str, Any], **ctx) -> Any:
        url = str(input_data["url"]).strip()
        _assert_safe_url(url)
        async with httpx.AsyncClient(headers={"User-Agent": _UA}, timeout=15.0,
                                     follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return {"url": url, "content": "", "note": f"unsupported content-type {ctype}"}
            text = _strip_html(resp.text)
            return {"url": url, "content": text[:8000]}

    def _summarize(self, data: Any) -> str:
        content = data.get("content", "") if isinstance(data, dict) else ""
        return f"读取 {len(content)} 字符,来源 {data.get('url', '')}"


def _strip_html(html: str) -> str:
    html = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"&nbsp;?", " ", html)
    html = re.sub(r"&amp;", "&", html)
    html = re.sub(r"&lt;", "<", html)
    html = re.sub(r"&gt;", ">", html)
    html = re.sub(r"[ \t\r\f]+", " ", html)
    return re.sub(r"\n\s*\n+", "\n\n", html).strip()


_ALLOWED_HOSTS_SUFFIX = ("localhost",)


def _assert_safe_url(url: str) -> None:
    """Basic SSRF guard: only http(s), no private/loopback targets."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"已拦截非 http/https 协议: {parsed.scheme}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("已拦截无主机名的 URL")
    if host in _ALLOWED_HOSTS_SUFFIX:
        raise ValueError("已拦截本地主机访问")
    import ipaddress

    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise ValueError("已拦截私有/回环 IP 访问")
    except ValueError as exc:
        if "已拦截" in str(exc):
            raise
        # hostname, fine
