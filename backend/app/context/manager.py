"""Context Engineering — token budgeting, prioritized selection, compression.

Priority order when the budget is tight:
    1. System instructions
    2. Current goal
    3. Current task
    4. Evidence
    5. Relevant memory
    6. Recent messages
    7. Tool result summaries
"""

from __future__ import annotations


class TokenCounter:
    """chars/4 heuristic (tiktoken-compatible estimate); good enough for budgeting."""

    def __init__(self, chars_per_token: float = 4.0):
        self.chars_per_token = chars_per_token

    def count(self, text: str) -> int:
        return max(1, int(len(text) / self.chars_per_token))

    def count_messages(self, messages: list[dict]) -> int:
        return sum(self.count(m.get("content", "")) for m in messages)


def dedupe(texts: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for t in texts:
        key = t.strip()[:120]
        if key and key not in seen:
            seen.add(key)
            out.append(t)
    return out


def compress_text(text: str, max_chars: int) -> str:
    """Keeps head + tail, drops the middle — cheap deterministic compression."""
    if len(text) <= max_chars:
        return text
    head = text[: int(max_chars * 0.65)]
    tail = text[-int(max_chars * 0.3):]
    return f"{head}\n…[compressed]…\n{tail}"


class ContextManager:
    def __init__(self, max_tokens: int = 16000, reserve_output_tokens: int = 3000):
        self.counter = TokenCounter()
        self.max_tokens = max_tokens
        self.reserve_output_tokens = reserve_output_tokens

    @property
    def input_budget(self) -> int:
        return max(1000, self.max_tokens - self.reserve_output_tokens)

    def build_evidence_block(self, evidence: list[dict], *, budget_tokens: int = 3000) -> str:
        """Prioritized, deduplicated, budget-bounded evidence block [E1]..[En]."""
        parts: list[str] = []
        used = 0
        budget_chars = budget_tokens * self.counter.chars_per_token
        for i, ev in enumerate(evidence, start=1):
            text = compress_text(ev.get("text", ""), 900)
            header = f"[E{i}] {text}"
            meta = ev.get("metadata") or {}
            if meta.get("source_title"):
                header += f"\n(source: {meta['source_title']})"
            if used + len(header) > budget_chars and parts:
                break
            parts.append(header)
            used += len(header)
        return "\n\n".join(dedupe(parts))

    def trim_messages(self, messages: list[dict]) -> list[dict]:
        """Drop oldest middle messages while over budget (keep first & last few)."""
        msgs = list(messages)
        while msgs and self.counter.count_messages(msgs) > self.input_budget:
            if len(msgs) <= 3:
                for m in msgs:
                    m["content"] = compress_text(m.get("content", ""), 2000)
                break
            # remove the second message (after system/goal)
            del msgs[1]
        return msgs

    def stats(self, messages: list[dict]) -> dict:
        used = self.counter.count_messages(messages)
        return {"used_tokens": used, "budget_tokens": self.input_budget,
                "utilization": round(used / self.input_budget, 2)}
