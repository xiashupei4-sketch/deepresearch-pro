"""Self-contained BM25 (Okapi) over jieba-aware tokens."""

from __future__ import annotations

import math
from dataclasses import dataclass

import jieba

jieba.setLogLevel(60)  # silence


def tokenize(text: str) -> list[str]:
    tokens = [t.strip() for t in jieba.lcut(text.lower()) if t.strip()]
    # also index alphanumeric runs (english terms stay whole)
    return tokens


@dataclass
class _Doc:
    doc_id: str
    tf: dict[str, int]
    length: int


class BM25Index:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.docs: dict[str, _Doc] = {}
        self.df: dict[str, int] = {}
        self.total_len = 0

    def add(self, doc_id: str, text: str) -> None:
        tokens = tokenize(text)
        tf: dict[str, int] = {}
        for tok in tokens:
            tf[tok] = tf.get(tok, 0) + 1
        self.docs[doc_id] = _Doc(doc_id=doc_id, tf=tf, length=len(tokens) or 1)
        self.total_len += len(tokens) or 1
        for tok in tf:
            self.df[tok] = self.df.get(tok, 0) + 1

    def remove(self, doc_id: str) -> None:
        doc = self.docs.pop(doc_id, None)
        if doc is None:
            return
        self.total_len -= doc.length
        for tok in doc.tf:
            self.df[tok] = max(0, self.df.get(tok, 0) - 1)
            if self.df[tok] == 0:
                del self.df[tok]

    def _idf(self, term: str) -> float:
        n = len(self.docs)
        df = self.df.get(term, 0)
        if df == 0 or n == 0:
            return 0.0
        return math.log((n - df + 0.5) / (df + 0.5) + 1.0)

    def search(self, query: str, top_k: int = 20) -> list[tuple[str, float]]:
        if not self.docs:
            return []
        avg_len = self.total_len / len(self.docs)
        q_tokens = set(tokenize(query))
        scores: dict[str, float] = {}
        for doc in self.docs.values():
            score = 0.0
            for term in q_tokens:
                f = doc.tf.get(term, 0)
                if f == 0:
                    continue
                idf = self._idf(term)
                denom = f + self.k1 * (1 - self.b + self.b * doc.length / avg_len)
                score += idf * (f * (self.k1 + 1)) / denom
            if score > 0:
                scores[doc.doc_id] = score
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return ranked
