#!/usr/bin/env python3
"""
Re-ingestion Script for RAG Documents.

This script re-processes all existing documents with the improved chunking strategy
for better handling of financial/tabular data.

Usage:
    python scripts/reingest_documents.py [--document-id <id>]

Options:
    --document-id <id>  Re-ingest a specific document only
    --all               Re-ingest all completed documents
    --dry-run           Show what would be done without making changes
"""

import asyncio
import argparse
import os
import sys

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from typing import List, Optional
import uuid


async def get_all_documents(session) -> List[dict]:
    """Fetch all completed documents from database."""
    from sqlalchemy import select
    from db.postgres_models import Document
    
    query = select(Document).where(Document.status == "completed")
    result = await session.execute(query)
    documents = result.scalars().all()
    
    return [
        {
            "id": str(doc.id),
            "filename": doc.filename,
            "file_type": doc.file_type,
            "chunks_count": doc.chunks_count,
            "created_at": doc.created_at,
        }
        for doc in documents
    ]


async def clear_document_vectors(document_id: str, vector_store) -> int:
    """Delete all vectors for a document from Qdrant."""
    from qdrant_client.http import models
    
    try:
        # Delete by document_id filter
        vector_store.client.delete(
            collection_name=vector_store.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id)
                        )
                    ]
                )
            )
        )
        return 1
    except Exception as e:
        print(f"  Warning: Could not delete vectors: {e}")
        return 0


async def reingest_document(
    document_id: str,
    file_path: str,
    filename: str,
    pipeline,
    session,
) -> dict:
    """Re-ingest a single document."""
    from sqlalchemy import update
    from db.postgres_models import Document
    from datetime import datetime
    
    print(f"  Processing: {filename}")
    
    # Update status to processing
    await session.execute(
        update(Document)
        .where(Document.id == uuid.UUID(document_id))
        .values(status="processing")
    )
    await session.commit()
    
    try:
        # Run the embedding pipeline
        result = await pipeline.process_document(
            document_id=document_id,
            file_path=file_path,
            metadata={"reingested": True}
        )
        
        # Update status to completed
        await session.execute(
            update(Document)
            .where(Document.id == uuid.UUID(document_id))
            .values(
                status="completed",
                processed_at=datetime.utcnow(),
                chunks_count=result.get("chunks_count", 0),
                doc_metadata=result
            )
        )
        await session.commit()
        
        return result
        
    except Exception as e:
        # Update status to failed
        await session.execute(
            update(Document)
            .where(Document.id == uuid.UUID(document_id))
            .values(
                status="failed",
                error_message=str(e)
            )
        )
        await session.commit()
        raise


async def main():
    parser = argparse.ArgumentParser(description="Re-ingest documents with improved chunking")
    parser.add_argument("--document-id", type=str, help="Re-ingest specific document by ID")
    parser.add_argument("--all", action="store_true", help="Re-ingest all completed documents")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done")
    args = parser.parse_args()
    
    if not args.document_id and not args.all:
        print("Error: Please specify --document-id <id> or --all")
        print("Run with --help for more options")
        sys.exit(1)
    
    # Import after path setup
    from core.config import settings
    from core.logger import setup_logging, get_logger
    from db.session_manager import async_session_factory
    from ingestion.embedding_pipeline import EmbeddingPipeline
    from services.vector_store_service import VectorStoreService
    
    setup_logging(log_level="INFO")
    logger = get_logger(__name__)
    
    print("=" * 60)
    print("RAG Document Re-ingestion Script")
    print("=" * 60)
    print(f"\nConfiguration:")
    print(f"  Chunk size: {settings.chunk_size} tokens")
    print(f"  Chunk overlap: {settings.chunk_overlap} tokens")
    print(f"  Top-k retrieval: {settings.top_k_retrieval}")
    print(f"  Hybrid search: {settings.hybrid_search_enabled}")
    print(f"  Reranking: {settings.enable_reranking}")
    print()
    
    # Upload directory (adjust for local vs Docker)
    upload_dirs = [
        "/app/uploads",  # Docker
        os.path.join(os.path.dirname(__file__), '..', 'uploads'),  # Local
        os.path.join(os.path.dirname(__file__), '..', 'backend', 'uploads'),  # Local alt
    ]
    
    upload_dir = None
    for d in upload_dirs:
        if os.path.exists(d):
            upload_dir = d
            break
    
    if not upload_dir:
        print("Warning: Upload directory not found. Creating local uploads folder.")
        upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
    
    print(f"Upload directory: {upload_dir}")
    
    # Initialize services
    pipeline = EmbeddingPipeline()
    vector_store = VectorStoreService()
    
    async with async_session_factory() as session:
        # Get documents to process
        if args.document_id:
            # Specific document
            from sqlalchemy import select
            from db.postgres_models import Document
            
            query = select(Document).where(Document.id == uuid.UUID(args.document_id))
            result = await session.execute(query)
            doc = result.scalar_one_or_none()
            
            if not doc:
                print(f"Error: Document {args.document_id} not found")
                sys.exit(1)
            
            documents = [{
                "id": str(doc.id),
                "filename": doc.filename,
                "file_type": doc.file_type,
                "chunks_count": doc.chunks_count,
            }]
        else:
            # All documents
            documents = await get_all_documents(session)
        
        if not documents:
            print("No documents found to re-ingest.")
            sys.exit(0)
        
        print(f"\nFound {len(documents)} document(s) to re-ingest:")
        for doc in documents:
            print(f"  - {doc['filename']} (ID: {doc['id'][:8]}..., {doc['chunks_count']} chunks)")
        
        if args.dry_run:
            print("\n[DRY RUN] No changes made.")
            sys.exit(0)
        
        print("\n" + "-" * 60)
        print("Starting re-ingestion...")
        print("-" * 60)
        
        success_count = 0
        error_count = 0
        
        for doc in documents:
            doc_id = doc["id"]
            filename = doc["filename"]
            file_type = doc.get("file_type", filename.rsplit(".", 1)[-1])
            
            # Find the file
            file_path = os.path.join(upload_dir, f"{doc_id}.{file_type}")
            
            if not os.path.exists(file_path):
                print(f"\n[SKIP] {filename} - File not found at {file_path}")
                error_count += 1
                continue
            
            print(f"\n[{success_count + error_count + 1}/{len(documents)}] {filename}")
            
            try:
                # Step 1: Clear existing vectors
                print("  Clearing existing vectors...")
                await clear_document_vectors(doc_id, vector_store)
                
                # Step 2: Re-ingest with new chunking
                print("  Re-processing with improved chunking...")
                result = await reingest_document(
                    document_id=doc_id,
                    file_path=file_path,
                    filename=filename,
                    pipeline=pipeline,
                    session=session,
                )
                
                new_chunks = result.get("chunks_count", 0)
                old_chunks = doc.get("chunks_count", 0)
                
                print(f"  ✓ Success: {old_chunks} chunks → {new_chunks} chunks")
                if result.get("total_pages"):
                    print(f"    Pages: {result.get('total_pages')}")
                
                success_count += 1
                
            except Exception as e:
                print(f"  ✗ Error: {e}")
                error_count += 1
        
        print("\n" + "=" * 60)
        print("Re-ingestion Complete")
        print("=" * 60)
        print(f"  Successful: {success_count}")
        print(f"  Failed: {error_count}")
        print(f"  Total: {len(documents)}")
        
        if success_count > 0:
            print("\n✓ Documents are now indexed with improved chunking for better")
            print("  financial/tabular data retrieval. Try your queries again!")


if __name__ == "__main__":
    asyncio.run(main())
