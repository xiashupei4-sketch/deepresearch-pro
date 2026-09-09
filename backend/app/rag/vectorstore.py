"""Vector store abstraction with an in-memory NumPy implementation (cosine).

Qdrant / FAISS can be plugged in behind the same interface later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class VectorRecord:
    id: str
    vector: list[float]
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class VectorHit:
    id: str
    score: float
    text: str
    metadata: dict


class VectorStore:
    async def upsert(self, records: list[VectorRecord]) -> None: ...
    async def delete(self, ids: list[str]) -> None: ...
    async def search(self, vector: list[float], top_k: int = 20,
                     filter_meta: dict | None = None) -> list[VectorHit]: ...
    async def count(self) -> int: ...


class InMemoryVectorStore(VectorStore):
    """NumPy cosine-similarity store. Sufficient for demo-scale corpora."""

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._vectors: np.ndarray | None = None
        self._texts: list[str] = []
        self._metas: list[dict] = []
        self._index: dict[str, int] = {}

    async def upsert(self, records: list[VectorRecord]) -> None:
        if not records:
            return
        fresh: list[VectorRecord] = []
        for rec in records:
            vec = np.asarray(rec.vector, dtype=np.float32)
            norm = np.linalg.norm(vec) or 1.0
            if rec.id in self._index:
                idx = self._index[rec.id]
                self._vectors[idx] = vec / norm
                self._texts[idx] = rec.text
                self._metas[idx] = rec.metadata
            else:
                fresh.append(rec)
        if fresh:
            new_vecs = np.zeros((len(fresh), len(fresh[0].vector)), dtype=np.float32)
            for i, rec in enumerate(fresh):
                vec = np.asarray(rec.vector, dtype=np.float32)
                norm = np.linalg.norm(vec) or 1.0
                new_vecs[i] = vec / norm
                self._index[rec.id] = len(self._ids)
                self._ids.append(rec.id)
                self._texts.append(rec.text)
                self._metas.append(rec.metadata)
            if self._vectors is None:
                self._vectors = new_vecs
            else:
                self._vectors = np.vstack([self._vectors, new_vecs])

    async def delete(self, ids: list[str]) -> None:
        keep = [i for i, doc_id in enumerate(self._ids) if doc_id not in set(ids)]
        old_texts = self._texts
        old_metas = self._metas
        self._ids = [self._ids[i] for i in keep]
        self._texts = [old_texts[i] for i in keep]
        self._metas = [old_metas[i] for i in keep]
        self._index = {doc_id: i for i, doc_id in enumerate(self._ids)}
        if self._vectors is not None:
            self._vectors = self._vectors[keep] if keep else None

    async def search(self, vector: list[float], top_k: int = 20,
                     filter_meta: dict | None = None) -> list[VectorHit]:
        if self._vectors is None or not self._ids:
            return []
        q = np.asarray(vector, dtype=np.float32)
        norm = np.linalg.norm(q) or 1.0
        q = q / norm
        scores = self._vectors @ q
        order = np.argsort(-scores)[: top_k * 3]
        hits: list[VectorHit] = []
        for idx in order:
            meta = self._metas[idx]
            if filter_meta:
                if any(meta.get(k) != v for k, v in filter_meta.items()):
                    continue
            hits.append(VectorHit(id=self._ids[idx], score=float(scores[idx]),
                                  text=self._texts[idx], metadata=meta))
            if len(hits) >= top_k:
                break
        return hits

    async def count(self) -> int:
        return len(self._ids)
