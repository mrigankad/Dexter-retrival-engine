#!/usr/bin/env python3
"""
Re-ingest documents already registered in the database (e.g. after changing
the chunker, embedding model or vector size).

Usage (from the repo root, with backend/ on the path and the same env as the API):
    python scripts/reingest_documents.py --all
    python scripts/reingest_documents.py --document-id <uuid>
    python scripts/reingest_documents.py --all --dry-run

Original files must still exist in UPLOAD_DIR (they are kept after ingestion).
"""

from __future__ import annotations

import argparse
import asyncio
import glob
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-id")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.document_id and not args.all:
        parser.error("pass --document-id <id> or --all")

    from sqlalchemy import select
    from src.contracts import IngestionJob
    from src.core.config import settings
    from src.infrastructure.database import Document, init_db, session_scope
    from src.ingestion import get_ingestion_pipeline

    await init_db(seed_admin=False)
    async with session_scope() as s:
        q = select(Document)
        if args.document_id:
            q = q.where(Document.id == uuid.UUID(args.document_id))
        docs = (await s.execute(q)).scalars().all()
        targets = [(str(d.id), d.filename, str(d.user_id) if d.user_id else None, d.tenant_id) for d in docs]

    pipeline = get_ingestion_pipeline()
    done = skipped = 0
    for doc_id, filename, user_id, tenant_id in targets:
        matches = glob.glob(os.path.join(settings.upload_dir, f"{doc_id}.*"))
        if not matches:
            print(f"SKIP {doc_id} {filename}: original file not found in {settings.upload_dir}")
            skipped += 1
            continue
        print(f"{'DRY ' if args.dry_run else ''}REINGEST {doc_id} {filename}")
        if args.dry_run:
            continue
        await pipeline.delete_document(doc_id)
        result = await pipeline.process(IngestionJob(document_id=doc_id, file_path=matches[0], filename=filename,
                                                     user_id=user_id, tenant_id=tenant_id))
        print(f"   -> {result.status} chunks={result.chunks_count} {result.error or ''}")
        done += 1
    print(f"done={done} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
