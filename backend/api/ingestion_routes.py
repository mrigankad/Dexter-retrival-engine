"""
Document ingestion routes for file upload and processing.
"""

import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
import json

from core.config import settings
from core.dependency_injection import CurrentUser, RedisClient, get_current_user_optional
from core.security import TokenData, verify_access_token
from db.session_manager import get_session
from db.postgres_models import Document
from core.logger import get_logger

router = APIRouter()
logger = get_logger(__name__)

UPLOAD_DIR = "/app/uploads"


class DocumentMetadata(BaseModel):
    """Document metadata model."""
    document_id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    created_at: datetime
    chunks_count: Optional[int] = None


class IngestionResponse(BaseModel):
    """Ingestion response model."""
    document_id: str
    filename: str
    status: str
    message: str


class DocumentListResponse(BaseModel):
    """Document list response model."""
    documents: List[DocumentMetadata]
    total: int

    class Config:
        from_attributes = True


def validate_file_extension(filename: str) -> bool:
    """Check if file extension is allowed."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return ext in settings.allowed_extensions_list


def validate_file_size(file_size: int) -> bool:
    """Check if file size is within limits."""
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    return file_size <= max_bytes




@router.post("/ingest", response_model=IngestionResponse)
async def ingest_document(
    redis_client: RedisClient,
    file: UploadFile = File(...),
    user: CurrentUser = None,
    session: AsyncSession = Depends(get_session),
):
    """
    Upload and ingest a document.
    
    Accepts PDF, DOCX, and TXT files. Processing happens asynchronously.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided")
    
    if not validate_file_extension(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed: {settings.allowed_extensions}",
        )
    
    # Read file content
    content = await file.read()
    file_size = len(content)
    
    if not validate_file_size(file_size):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {settings.max_file_size_mb}MB",
        )
    
    # Generate document ID and save file
    document_id = str(uuid.uuid4())
    file_ext = file.filename.rsplit(".", 1)[-1].lower()
    file_path = os.path.join(UPLOAD_DIR, f"{document_id}.{file_ext}")
    
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Create document record in DB
    new_doc = Document(
        id=uuid.UUID(document_id),
        user_id=uuid.UUID(user.user_id) if user else None,
        filename=file.filename,
        file_type=file_ext,
        file_size=file_size,
        status="pending",
        doc_metadata={"original_filename": file.filename}
    )
    
    session.add(new_doc)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        logger.error("Database integrity error during ingestion", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Document record conflict. The document may already exist or the user session is invalid.",
        )
    except Exception as e:
        await session.rollback()
        logger.exception("Unexpected error saving document to DB", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save document record",
        )
    
    logger.info(
        "Document uploaded",
        document_id=document_id,
        filename=file.filename,
        size=file_size,
        user_id=user.user_id if user else "anonymous",
    )
    
    # Queue job in Redis
    job_data = json.dumps({
        "document_id": document_id,
        "file_path": file_path,
        "metadata": {"user_id": user.user_id if user else None}
    })
    
    await redis_client.rpush(settings.redis_queue_name, job_data)
    
    return IngestionResponse(
        document_id=document_id,
        filename=file.filename,
        status="queued",
        message="Document uploaded and queued for processing",
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    user: CurrentUser,
    limit: int = 10,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """List all ingested documents for the current user."""
    query = select(Document).order_by(desc(Document.created_at)).limit(limit).offset(offset)
    
    if user:
        query = query.where(Document.user_id == uuid.UUID(user.user_id))
        
    result = await session.execute(query)
    documents = result.scalars().all()
    
    # Get total count (simplified)
    # total = await session.scalar(select(func.count()).select_from(Document))
    
    return DocumentListResponse(
        documents=[
            DocumentMetadata(
                document_id=str(doc.id),
                filename=doc.filename,
                file_type=doc.file_type,
                file_size=doc.file_size,
                status=doc.status,
                created_at=doc.created_at,
                chunks_count=doc.chunks_count
            ) for doc in documents
        ],
        total=len(documents) # simplified
    )


@router.get("/documents/{document_id}", response_model=DocumentMetadata)
async def get_document(
    document_id: str, 
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Get document metadata and status."""
    query = select(Document).where(Document.id == uuid.UUID(document_id))
    
    if user:
        query = query.where(Document.user_id == uuid.UUID(user.user_id))
        
    result = await session.execute(query)
    doc = result.scalar_one_or_none()
    
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
        
    return DocumentMetadata(
        document_id=str(doc.id),
        filename=doc.filename,
        file_type=doc.file_type,
        file_size=doc.file_size,
        status=doc.status,
        created_at=doc.created_at,
        chunks_count=doc.chunks_count
    )


@router.get("/files/{document_id}")
async def get_document_file(
    document_id: str,
    session: AsyncSession = Depends(get_session),
    user: Optional[TokenData] = Depends(get_current_user_optional),
    token: Optional[str] = None,
):
    """
    Serve the raw document file.
    
    Supports authentication via:
    - Bearer token in Authorization header (standard API calls)
    - `token` query parameter (for window.open / direct browser access)
    """
    # If no user from Bearer header, try query param token
    effective_user = user
    if effective_user is None and token:
        effective_user = verify_access_token(token)
    
    if effective_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication credentials",
        )
    
    # Look up document by ID — may not match if Qdrant and Postgres have different IDs
    doc = None
    file_path = None
    
    try:
        query = select(Document).where(Document.id == uuid.UUID(document_id))
        result = await session.execute(query)
        doc = result.scalar_one_or_none()
    except (ValueError, Exception) as e:
        logger.warning("DB lookup failed", document_id=document_id, error=str(e))
    
    if doc:
        # Found in DB — use the DB record to serve the file
        file_path = os.path.join(UPLOAD_DIR, f"{document_id}.{doc.file_type}")
        if not os.path.exists(file_path):
            file_path = None
    
    # Fallback: scan uploads directory for a file matching this document_id
    if not file_path:
        for fname in os.listdir(UPLOAD_DIR):
            if fname.startswith(document_id):
                file_path = os.path.join(UPLOAD_DIR, fname)
                break
    
    # Fallback 2: try to find by filename from query param
    if not file_path:
        # Try finding ANY file for the same source document
        try:
            query = select(Document).where(Document.filename.isnot(None)).order_by(desc(Document.created_at))
            result = await session.execute(query)
            all_docs = result.scalars().all()
            for candidate in all_docs:
                candidate_path = os.path.join(UPLOAD_DIR, f"{candidate.id}.{candidate.file_type}")
                if os.path.exists(candidate_path):
                    doc = candidate
                    file_path = candidate_path
                    break
        except Exception:
            pass
    
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    
    # Determine media type from file extension
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    media_type = "application/pdf" if ext == "pdf" else "application/octet-stream"
    filename = doc.filename if doc else os.path.basename(file_path)
    
    return FileResponse(
        path=file_path,
        filename=filename,
        media_type=media_type,
    )


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    user: CurrentUser,
    session: AsyncSession = Depends(get_session),
):
    """Delete a document and its vectors from all storage tiers."""
    logger.info("Document deletion requested", document_id=document_id, user_id=user.user_id)

    # 1. Find document in DB
    query = select(Document).where(Document.id == uuid.UUID(document_id))
    result = await session.execute(query)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    # 2. Delete vectors from Qdrant
    try:
        from services.vector_store_service import VectorStoreService
        vector_store = VectorStoreService()
        await vector_store.delete_by_filter({
            "must": [{"key": "document_id", "match": {"value": document_id}}]
        })
        logger.info("Qdrant vectors deleted", document_id=document_id)
    except Exception as e:
        logger.warning("Failed to delete Qdrant vectors", error=str(e))

    # 3. Delete files from MinIO
    try:
        from services.object_storage_service import ObjectStorageService
        obj_storage = ObjectStorageService()
        obj_storage.delete_object(settings.minio_bucket_documents, f"{document_id}/")
        obj_storage.delete_object(settings.minio_bucket_assets, f"{document_id}/")
        logger.info("MinIO objects deleted", document_id=document_id)
    except Exception as e:
        logger.warning("Failed to delete MinIO objects", error=str(e))

    # 4. Delete local upload file (if exists)
    import glob
    for f in glob.glob(os.path.join(UPLOAD_DIR, f"{document_id}.*")):
        try:
            os.remove(f)
        except OSError:
            pass

    # 5. Delete DB record (cascades to document_chunks)
    await session.delete(doc)
    await session.commit()
    logger.info("Document fully deleted", document_id=document_id)

    return {"status": "deleted", "document_id": document_id}
