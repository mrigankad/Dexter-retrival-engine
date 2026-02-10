"""
Ingestion Schemas - Request and response models for document ingestion.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field


class IngestionRequest(BaseModel):
    """Document ingestion request (for JSON API, not file upload)."""
    document_url: Optional[str] = Field(None, description="URL to fetch document from")
    metadata: Optional[Dict[str, Any]] = Field(default={}, description="Document metadata")


class IngestionResponse(BaseModel):
    """Ingestion response schema."""
    document_id: str = Field(..., description="Unique document ID")
    filename: str = Field(..., description="Original filename")
    status: str = Field(..., description="Processing status")
    message: str = Field(..., description="Status message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "document_id": "abc123-def456",
                "filename": "report.pdf",
                "status": "processing",
                "message": "Document queued for processing",
            }
        }


class DocumentMetadata(BaseModel):
    """Document metadata schema."""
    document_id: str
    filename: str
    file_type: str
    file_size: int
    status: str
    created_at: datetime
    processed_at: Optional[datetime] = None
    chunks_count: Optional[int] = None
    error_message: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Document list response schema."""
    documents: List[DocumentMetadata]
    total: int
    page: int = 1
    page_size: int = 10


class DocumentDetailResponse(BaseModel):
    """Detailed document response schema."""
    document: DocumentMetadata
    chunks: Optional[List[Dict[str, Any]]] = None


class DocumentDeleteResponse(BaseModel):
    """Document deletion response schema."""
    document_id: str
    status: str
    message: str
