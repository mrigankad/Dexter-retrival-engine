"""Document upload, listing, status, download, deletion and reprocessing."""

from __future__ import annotations

import glob
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from src.contracts import IngestionJob
from src.core.access import acl_for_document, column_to_groups, document_visibility_clause, groups_to_column
from src.core.auth import verify_bearer
from src.core.config import settings
from src.core.dependency_injection import CurrentUser, DbSession, OptionalUser
from src.core.logger import get_logger
from src.infrastructure.database import Document
from src.ingestion import enqueue_ingestion, get_ingestion_pipeline

router = APIRouter()
logger = get_logger(__name__)


class DocumentMetadata(BaseModel):
    document_id: str
    id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    created_at: datetime
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    chunks_count: Optional[int] = None
    total_pages: Optional[int] = None
    error_message: Optional[str] = None
    visibility: str = "tenant"
    shared_groups: List[str] = []
    owner_id: Optional[str] = None
    metadata: dict = {}


class IngestionResponse(BaseModel):
    document_id: str
    filename: str
    status: str
    message: str


class DocumentListResponse(BaseModel):
    documents: List[DocumentMetadata]
    total: int


def _to_meta(doc: Document) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=str(doc.id), id=str(doc.id), filename=doc.filename, file_type=doc.file_type, file_size=doc.file_size,
        status=doc.status, created_at=doc.created_at, uploaded_at=doc.created_at, processed_at=doc.processed_at,
        chunks_count=doc.chunks_count, total_pages=doc.total_pages, error_message=doc.error_message,
        visibility=doc.visibility or "tenant", shared_groups=column_to_groups(doc.shared_groups),
        owner_id=str(doc.user_id) if doc.user_id else None, metadata=doc.doc_metadata or {},
    )


def _ext_ok(filename: str) -> Optional[str]:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext if ext in settings.allowed_extensions_list else None


def _visible_query(user, base):
    """Documents the caller may see: own, public, tenant-shared, or shared with one of their groups."""
    return document_visibility_clause(base, user)


def _can_modify(user, doc: Document) -> bool:
    if (user.role or "").lower() == "admin":
        return True
    return doc.user_id is not None and str(doc.user_id) == user.user_id


def _job_for(doc: Document, path: str, user) -> IngestionJob:
    return IngestionJob(
        document_id=str(doc.id), file_path=path, filename=doc.filename, user_id=str(doc.user_id) if doc.user_id else None,
        tenant_id=doc.tenant_id, visibility=doc.visibility or "tenant",
        acl=acl_for_document(str(doc.user_id) if doc.user_id else None, doc.tenant_id, doc.visibility or "tenant",
                             column_to_groups(doc.shared_groups)),
        metadata={"uploaded_by": user.username},
    )


@router.post("/ingest", response_model=IngestionResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_document(
    db: DbSession, user: CurrentUser, file: UploadFile = File(...),
    visibility: Optional[str] = Form(default=None, description="private | tenant | public"),
    groups: Optional[str] = Form(default=None, description="Comma separated groups that may read this document"),
):
    visibility = (visibility or settings.default_document_visibility).lower()
    if visibility not in ("private", "tenant", "public"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "visibility must be private, tenant or public")
    shared = [g.strip() for g in (groups or "").split(",") if g.strip()]
    if not file.filename:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No filename provided")
    ext = _ext_ok(file.filename)
    if ext is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File type not allowed. Allowed: {settings.allowed_extensions}")
    content = await file.read()
    if len(content) > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"File too large. Maximum size: {settings.max_file_size_mb}MB")
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty file")

    document_id = uuid.uuid4()
    os.makedirs(settings.upload_dir, exist_ok=True)
    path = os.path.join(settings.upload_dir, f"{document_id}.{ext}")
    with open(path, "wb") as f:
        f.write(content)

    try:
        owner_uuid: Optional[uuid.UUID] = uuid.UUID(user.user_id)
    except ValueError:
        owner_uuid = None   # external (Entra) identities are not rows in users
    tenant_id = user.tenant_id or settings.default_tenant_id
    doc = Document(id=document_id, user_id=owner_uuid, tenant_id=tenant_id, filename=file.filename, file_type=ext,
                   file_size=len(content), status="pending", visibility=visibility, shared_groups=groups_to_column(shared),
                   doc_metadata={"original_filename": file.filename, "owner": user.user_id})
    db.add(doc)
    await db.commit()

    job = IngestionJob(
        document_id=str(document_id), file_path=path, filename=file.filename, user_id=user.user_id, tenant_id=tenant_id,
        visibility=visibility, acl=acl_for_document(user.user_id, tenant_id, visibility, shared),
        metadata={"uploaded_by": user.username},
    )
    mode = await enqueue_ingestion(job)
    logger.info("Document uploaded", document_id=str(document_id), filename=file.filename, mode=mode)
    return IngestionResponse(document_id=str(document_id), filename=file.filename, status="queued" if mode == "queued" else "processing",
                             message="Document uploaded and queued for processing" if mode == "queued" else "Document uploaded; processing started")


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(db: DbSession, user: CurrentUser, limit: int = 100, offset: int = 0, status_filter: Optional[str] = None):
    q = _visible_query(user, select(Document)).order_by(desc(Document.created_at))
    if status_filter:
        q = q.where(Document.status == status_filter)
    total = await db.scalar(_visible_query(user, select(func.count(Document.id)))) or 0
    rows = (await db.execute(q.limit(limit).offset(offset))).scalars().all()
    return DocumentListResponse(documents=[_to_meta(d) for d in rows], total=int(total))


async def _get_owned(db, user, document_id: str) -> Document:
    try:
        doc_uuid = uuid.UUID(document_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    doc = await db.scalar(_visible_query(user, select(Document).where(Document.id == doc_uuid)))
    if doc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.get("/documents/{document_id}", response_model=DocumentMetadata)
async def get_document(document_id: str, db: DbSession, user: CurrentUser):
    return _to_meta(await _get_owned(db, user, document_id))


@router.get("/documents/{document_id}/chunks")
async def get_document_chunks(document_id: str, db: DbSession, user: CurrentUser, limit: int = 200):
    await _get_owned(db, user, document_id)
    from src.infrastructure.vector_store import get_qdrant_store
    chunks = await get_qdrant_store().get_document_chunks(document_id, limit=limit)
    return {"document_id": document_id, "chunks": [c.model_dump() for c in chunks]}


@router.post("/documents/{document_id}/reprocess", response_model=IngestionResponse)
async def reprocess_document(document_id: str, db: DbSession, user: CurrentUser):
    doc = await _get_owned(db, user, document_id)
    if not _can_modify(user, doc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner or an admin can reprocess this document")
    matches = glob.glob(os.path.join(settings.upload_dir, f"{document_id}.*"))
    if not matches:
        raise HTTPException(status.HTTP_409_CONFLICT, "Original file no longer available; upload again")
    await get_ingestion_pipeline().delete_document(document_id)
    doc.status = "pending"
    await db.commit()
    mode = await enqueue_ingestion(_job_for(doc, matches[0], user))
    return IngestionResponse(document_id=document_id, filename=doc.filename, status="queued" if mode == "queued" else "processing", message="Reprocessing")


class ShareRequest(BaseModel):
    visibility: Optional[str] = None
    groups: Optional[List[str]] = None


@router.put("/documents/{document_id}/sharing", response_model=DocumentMetadata)
async def update_sharing(document_id: str, body: ShareRequest, db: DbSession, user: CurrentUser):
    """Change who can see a document; re-indexes its chunks with the new ACL."""
    doc = await _get_owned(db, user, document_id)
    if not _can_modify(user, doc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner or an admin can change sharing")
    if body.visibility is not None:
        if body.visibility not in ("private", "tenant", "public"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "visibility must be private, tenant or public")
        doc.visibility = body.visibility
    if body.groups is not None:
        doc.shared_groups = groups_to_column(body.groups)
    await db.commit()
    matches = glob.glob(os.path.join(settings.upload_dir, f"{document_id}.*"))
    if matches and doc.status == "completed":
        await get_ingestion_pipeline().delete_document(document_id)
        await enqueue_ingestion(_job_for(doc, matches[0], user))
    return _to_meta(doc)


@router.get("/files/{document_id}")
async def get_document_file(document_id: str, db: DbSession, user: OptionalUser, token: Optional[str] = None):
    effective = user or (verify_bearer(token) if token else None)
    if effective is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or invalid authentication credentials")
    doc = await _get_owned(db, effective, document_id)
    path = os.path.join(settings.upload_dir, f"{document_id}.{doc.file_type}")
    if not os.path.exists(path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found on disk")
    media = {"pdf": "application/pdf", "txt": "text/plain", "md": "text/markdown", "html": "text/html", "csv": "text/csv",
             "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}.get(doc.file_type, "application/octet-stream")
    return FileResponse(path=path, filename=doc.filename, media_type=media)


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str, db: DbSession, user: CurrentUser):
    doc = await _get_owned(db, user, document_id)
    if not _can_modify(user, doc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only the owner or an admin can delete this document")
    try:
        await get_ingestion_pipeline().delete_document(document_id)
    except Exception as exc:
        logger.warning("Vector deletion failed", document_id=document_id, error=str(exc))
    for f in glob.glob(os.path.join(settings.upload_dir, f"{document_id}.*")):
        try:
            os.remove(f)
        except OSError:
            pass
    await db.delete(doc)
    await db.commit()
    logger.info("Document deleted", document_id=document_id)
    return {"status": "deleted", "document_id": document_id}
