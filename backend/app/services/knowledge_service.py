"""Knowledge Service — document upload, parsing, chunking, indexing, search."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.parser import SUPPORTED_TYPES, parse_document
from app.rag.vectorstore import VectorRecord
from app.config import DATA_DIR
from app.models.models import Document
from app.repositories import repositories as repo
from app.services.container import Container

logger = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


class KnowledgeService:
    def __init__(self, container: Container):
        self.container = container

    async def create_document(self, db: AsyncSession, filename: str, data: bytes) -> "Document":
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_TYPES:
            raise ValueError(f"不支持的文件类型 '{suffix}'。"
                             f"支持的类型:{', '.join(sorted(SUPPORTED_TYPES))}")
        if len(data) > MAX_UPLOAD_BYTES:
            raise ValueError("文件超过 20 MB 大小限制")
        doc = self._doc_model(filename, suffix, len(data))
        db.add(doc)
        await db.commit()
        await db.refresh(doc)
        return doc

    @staticmethod
    def _doc_model(filename: str, suffix: str, size: int):
        return Document(filename=filename,
                        file_type=suffix.lstrip("."), size_bytes=size, status="UPLOADING")

    async def process_document(self, document_id: str) -> None:
        """Background: parse → chunk → embed → index. Updates status progressively."""
        from app.db import AsyncSessionLocal

        def set_status(status: str, chunk_count: int | None = None,
                       error: str | None = None):
            async def _inner():
                async with AsyncSessionLocal() as db:
                    doc = await db.get(Document, document_id)
                    if doc is None:
                        return
                    doc.status = status
                    if chunk_count is not None:
                        doc.chunk_count = chunk_count
                    doc.error = error
                    await db.commit()
            return _inner()

        try:
            async with AsyncSessionLocal() as db:
                doc = await db.get(Document, document_id)
                if doc is None:
                    return
                # 必须用与上传路由一致的 DATA_DIR(绝对路径);
                # 相对路径会跟随进程工作目录,后端从 backend/ 启动时会指向不存在的 backend/data
                path = DATA_DIR / "uploads" / f"{doc.id}{Path(doc.filename).suffix}"
                data = path.read_bytes() if path.exists() else None
                filename = doc.filename
            if data is None:
                await set_status("FAILED", error="上传的文件在磁盘上丢失")
                return

            await set_status("PARSING")
            text = await asyncio.to_thread(parse_document, filename, data)
            if not text.strip():
                await set_status("FAILED", error="文档中无可提取的文本")
                return

            await set_status("CHUNKING")
            engine = self.container.kb_engine
            chunks = engine.chunker.split(text)
            if not chunks:
                await set_status("FAILED", error="文档未生成分块")
                return

            await set_status("EMBEDDING")
            count = await engine.ingest_text(
                document_id, text,
                metadata={"document_title": filename, "source_type": "local",
                          "domain": "local"})
            await set_status("INDEXED", chunk_count=count)
            await self.container.bus.emit(self._event(
                document_id, "DOCUMENT_INDEXED", f"indexed {count} chunks"))
        except Exception as exc:  # noqa: BLE001
            logger.exception("document %s processing failed", document_id)
            await set_status("FAILED", error=f"{type(exc).__name__}: {exc}")

    async def delete_document(self, db: AsyncSession, document_id: str) -> bool:
        doc = await db.get(Document, document_id)
        if doc is None:
            return False
        await self.container.kb_engine.delete_document(document_id)
        await db.delete(doc)
        await db.commit()
        return True

    async def search(self, query: str, top_k: int = 5) -> dict:
        result = await self.container.kb_engine.search(query, top_k=top_k)
        chunks = []
        for c in result["chunks"]:
            chunks.append({"id": c["id"], "text": c["text"], "score": c["score"],
                           "document_id": (c["metadata"] or {}).get("document_id"),
                           "document_title": (c["metadata"] or {}).get("document_title")})
        return {"query": query, "chunks": chunks, "total": len(chunks)}

    @staticmethod
    def _event(document_id: str, event_type: str, summary: str):
        from app.observability.trace import TraceEvent

        return TraceEvent(research_id=f"kb-{document_id}", agent="Knowledge",
                          event_type=event_type, output_summary=summary)
