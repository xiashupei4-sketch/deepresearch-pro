"""Rerankers: heuristic keyword-overlap rerank (default) + optional LLM rerank."""

from __future__ import annotations

from app.rag.bm25 import tokenize


class HeuristicReranker:
    """Scores candidates by query term coverage + position. Deterministic, offline."""

    def rerank(self, query: str, candidates: list[dict], top_k: int = 8) -> list[dict]:
        if not candidates:
            return []
        q_terms = set(tokenize(query))
        if not q_terms:
            return candidates[:top_k]
        scored: list[tuple[float, dict]] = []
        for cand in candidates:
            text = (cand.get("text", "") or "").lower()
            tokens = tokenize(text)
            token_set = set(tokens)
            overlap = len(q_terms & token_set) / max(1, len(q_terms))
            # slight bonus for term density
            density = len(q_terms & token_set) / max(1, len(tokens) or 1)
            score = 0.8 * overlap + 0.2 * min(1.0, density * 5)
            item = dict(cand)
            item["rerank_score"] = round(score, 4)
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:top_k]]


class LLMReranker:
    """LLM-based relevance scoring; falls back to heuristic on failure."""

    def __init__(self, llm):
        self.llm = llm
        self.fallback = HeuristicReranker()

    async def rerank(self, query: str, candidates: list[dict], top_k: int = 8) -> list[dict]:
        if not candidates:
            return []
        try:
            payload = "\n\n".join(
                f"[{i}] {(c.get('text', '') or '')[:400]}" for i, c in enumerate(candidates[:12])
            )
            prompt = (f"Query: {query}\n\nRate each passage's relevance from 0.0 to 1.0.\n\n"
                      f"{payload}\n\nRespond with JSON: "
                      f'{{"scores": [{{"index": 0, "score": 0.9}}]}}')
            raw = await self.llm.chat([{"role": "user", "content": prompt}], temperature=0.0)
            import json
            import re

            data = json.loads(re.search(r"\{.*\}", raw, re.DOTALL).group(0))
            scores = {int(s["index"]): float(s["score"]) for s in data.get("scores", [])}
            out: list[dict] = []
            for i, cand in enumerate(candidates):
                item = dict(cand)
                item["rerank_score"] = scores.get(i, cand.get("fusion_score", 0.0))
                out.append(item)
            out.sort(key=lambda c: c.get("rerank_score", 0.0), reverse=True)
            return out[:top_k]
        except Exception:  # noqa: BLE001
            return self.fallback.rerank(query, candidates, top_k)
