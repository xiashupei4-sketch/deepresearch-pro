"""Text chunker with configurable size / overlap and heading-aware separators."""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    text: str
    index: int
    metadata: dict = field(default_factory=dict)


_PARA_SPLIT = re.compile(r"\n\s*\n")


def clean_text(text: str) -> str:
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


class Chunker:
    def __init__(self, chunk_size: int = 700, chunk_overlap: int = 120):
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split(self, text: str, metadata: dict | None = None) -> list[Chunk]:
        text = clean_text(text)
        if not text:
            return []
        paragraphs = [p.strip() for p in _PARA_SPLIT.split(text) if p.strip()]
        # greedy paragraph packing, then hard-split oversized paragraphs
        units: list[str] = []
        for para in paragraphs:
            if len(para) <= self.chunk_size:
                units.append(para)
            else:
                for i in range(0, len(para), self.chunk_size - self.chunk_overlap):
                    units.append(para[i : i + self.chunk_size])
        chunks: list[Chunk] = []
        buf = ""
        for unit in units:
            candidate = f"{buf}\n\n{unit}" if buf else unit
            if len(candidate) > self.chunk_size and buf:
                chunks.append(Chunk(text=buf, index=len(chunks)))
                # start next buffer with tail overlap for continuity
                tail = buf[-self.chunk_overlap:] if self.chunk_overlap > 0 else ""
                buf = (tail + "\n\n" + unit).strip()
                if len(buf) > self.chunk_size:
                    chunks.append(Chunk(text=buf[: self.chunk_size], index=len(chunks)))
                    buf = buf[self.chunk_size - self.chunk_overlap:]
            else:
                buf = candidate
        if buf.strip():
            chunks.append(Chunk(text=buf.strip(), index=len(chunks)))
        if metadata:
            for c in chunks:
                c.metadata = dict(metadata)
        return chunks
