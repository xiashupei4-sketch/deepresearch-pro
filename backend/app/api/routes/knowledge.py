"""Knowledge Base API — upload / list / delete / search."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import DATA_DIR
from app.db import get_db
from app.repositories import repositories as repo
from app.schemas.research import KnowledgeSearchRequest
from app.services.knowledge_service import KnowledgeService

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post("/documents")
async def upload_document(file: UploadFile, background: BackgroundTasks, request: Request,
                          db: AsyncSession = Depends(get_db)) -> dict:
    service: KnowledgeService = request.app.state.knowledge
    data = await file.read()
    try:
        doc = await service.create_document(db, file.filename or "upload.txt", data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    # persist raw file for the background processor
    suffix = Path(doc.filename).suffix.lower()
    path = UPLOAD_DIR / f"{doc.id}{suffix}"
    path.write_bytes(data)
    background.add_task(service.process_document, doc.id)
    return _doc_dict(doc)


@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)) -> list[dict]:
    docs = await repo.list_documents(db)
    return [_doc_dict(d) for d in docs]


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, request: Request,
                          db: AsyncSession = Depends(get_db)) -> dict:
    service: KnowledgeService = request.app.state.knowledge
    ok = await service.delete_document(db, document_id)
    if not ok:
        raise HTTPException(404, "文档不存在")
    return {"deleted": document_id}


@router.post("/search")
async def search(body: KnowledgeSearchRequest, request: Request) -> dict:
    service: KnowledgeService = request.app.state.knowledge
    return await service.search(body.query, top_k=body.top_k)


def _doc_dict(d) -> dict:
    return {
        "id": d.id, "filename": d.filename, "file_type": d.file_type,
        "size_bytes": d.size_bytes, "status": d.status, "chunk_count": d.chunk_count,
        "error": d.error,
        "created_at": d.created_at.isoformat() if d.created_at else None,
    }
