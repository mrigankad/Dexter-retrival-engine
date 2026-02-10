"""
Re-ingestion Script: Clear Qdrant + Re-ingest a document.

Usage (from backend directory):
    python scripts/reingest.py <file_path>

Example:
    python scripts/reingest.py ../documents/Test1.pdf
"""

import asyncio
import os
import sys
import uuid
import time
import re

# Add backend root to path
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

# Override hosts to localhost if running outside Docker
os.environ["QDRANT_HOST"] = "localhost"
os.environ["REDIS_HOST"] = "localhost"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["MINIO_ENDPOINT"] = "localhost:9000"


def smart_chunk_text(text: str, chunk_size: int = 768, chunk_overlap: int = 100, min_words: int = 15) -> list[str]:
    """
    Smart chunking strategy: split by paragraphs, then combine or split as needed.
    Produces overlapping chunks for better retrieval.
    """
    if not text or not text.strip():
        return []
    
    # Split into paragraphs (double newline or single newline with indent)
    paragraphs = re.split(r'\n\s*\n|\n(?=[A-Z•●\-\d])', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        # If adding this paragraph exceeds chunk_size, finalize current chunk
        if current_chunk and len(current_chunk) + len(para) + 2 > chunk_size:
            if len(current_chunk.split()) >= min_words:
                chunks.append(current_chunk)
            
            # Start new chunk with overlap from the end of the previous
            overlap_text = ""
            if chunk_overlap > 0 and current_chunk:
                # Take the last chunk_overlap characters
                overlap_text = current_chunk[-chunk_overlap:].strip()
                # Try to start at a sentence boundary
                last_period = overlap_text.rfind(". ")
                if last_period > 0:
                    overlap_text = overlap_text[last_period + 2:]
            
            current_chunk = (overlap_text + "\n\n" + para).strip() if overlap_text else para
        else:
            current_chunk = (current_chunk + "\n\n" + para).strip() if current_chunk else para
    
    # Don't forget the last chunk
    if current_chunk and len(current_chunk.split()) >= min_words:
        chunks.append(current_chunk)
    
    # If a single chunk is still very large, split it further
    final_chunks = []
    for chunk in chunks:
        if len(chunk) > chunk_size * 1.5:
            # Split by sentences
            sentences = re.split(r'(?<=[.!?])\s+', chunk)
            sub_chunk = ""
            for sent in sentences:
                if len(sub_chunk) + len(sent) + 1 > chunk_size:
                    if len(sub_chunk.split()) >= min_words:
                        final_chunks.append(sub_chunk.strip())
                    sub_chunk = sent
                else:
                    sub_chunk = (sub_chunk + " " + sent).strip() if sub_chunk else sent
            if sub_chunk and len(sub_chunk.split()) >= min_words:
                final_chunks.append(sub_chunk.strip())
        else:
            final_chunks.append(chunk)
    
    return final_chunks


def detect_content_type(text: str) -> str:
    """Detect if text contains financial data, tables, or general text."""
    financial_patterns = [
        r'\b\d+(?:\.\d+)?(?:\s*(?:million|billion|crore|lakh|mn|bn|cr|lac|%))\b',
        r'(?:revenue|profit|loss|income|expense|margin|ebitda|capex)',
        r'(?:FY\s*\d{2,4}|Q[1-4]\s*FY)',
    ]
    
    table_patterns = [
        r'(?:\|[^\|]+\|){2,}',  # Markdown-style table
        r'(?:\d+\s+\d+\s+\d+)',  # Columns of numbers
    ]
    
    text_lower = text.lower()
    
    if any(re.search(p, text_lower) for p in table_patterns):
        return "table"
    
    financial_matches = sum(1 for p in financial_patterns if re.search(p, text_lower))
    if financial_matches >= 2:
        return "financial"
    
    return "text"


async def main():
    file_path = sys.argv[1] if len(sys.argv) > 1 else None

    if not file_path:
        print("Usage: python scripts/reingest.py <file_path>")
        sys.exit(1)

    # Resolve to absolute path
    if not os.path.isabs(file_path):
        file_path = os.path.abspath(file_path)

    if not os.path.exists(file_path):
        print(f"ERROR: File not found: {file_path}")
        sys.exit(1)

    filename = os.path.basename(file_path)
    file_size_kb = os.path.getsize(file_path) / 1024

    print(f"\n{'='*60}")
    print(f"  RAG Re-Ingestion Pipeline")
    print(f"  File: {filename}")
    print(f"  Path: {file_path}")
    print(f"  Size: {file_size_kb:.1f} KB")
    print(f"{'='*60}\n")

    # ── Step 1: Clear Qdrant Collection ──────────────────────
    print("[1/4] Clearing Qdrant collection...")

    from qdrant_client import QdrantClient
    from qdrant_client.http import models

    qdrant_host = os.environ.get("QDRANT_HOST", "localhost")
    qdrant_port = int(os.environ.get("QDRANT_PORT", "6333"))
    collection_name = os.environ.get("QDRANT_COLLECTION", "documents")
    vector_size = int(os.environ.get("QDRANT_VECTOR_SIZE", "1024"))

    qdrant = QdrantClient(host=qdrant_host, port=qdrant_port)

    try:
        info = qdrant.get_collection(collection_name)
        existing_points = info.points_count
        print(f"      Found {existing_points} existing points in '{collection_name}'")

        # Delete and recreate
        qdrant.delete_collection(collection_name)
        print(f"      ✓ Collection '{collection_name}' deleted")
    except Exception as e:
        print(f"      Collection doesn't exist or error: {e}")

    # Recreate collection
    qdrant.create_collection(
        collection_name=collection_name,
        vectors_config=models.VectorParams(
            size=vector_size,
            distance=models.Distance.COSINE,
        ),
    )
    print(f"      ✓ Collection '{collection_name}' recreated (vector_size={vector_size})")

    # ── Step 2: Parse Document ───────────────────────────────
    print("\n[2/4] Parsing document...")

    from pypdf import PdfReader

    reader = PdfReader(file_path)
    total_pages = len(reader.pages)
    
    pages = []
    for page_num, page in enumerate(reader.pages, 1):
        text = page.extract_text()
        if text and text.strip():
            pages.append({
                "page": page_num,
                "content": text.strip(),
                "total_pages": total_pages,
            })

    print(f"      ✓ Parsed {len(pages)} pages (of {total_pages} total)")

    # ── Step 3: Chunk Document ───────────────────────────────
    print("\n[3/4] Chunking document...")

    document_id = str(uuid.uuid4())
    
    # Settings
    chunk_size = int(os.environ.get("CHUNK_SIZE", "768"))
    chunk_overlap = int(os.environ.get("CHUNK_OVERLAP", "100"))
    
    all_chunks = []
    chunk_index = 0

    for page_data in pages:
        page_num = page_data["page"]
        raw_text = page_data["content"]

        if not raw_text:
            continue

        page_chunks = smart_chunk_text(raw_text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

        for chunk_text in page_chunks:
            content_type = detect_content_type(chunk_text)
            all_chunks.append({
                "content": chunk_text,
                "document_id": document_id,
                "source": filename,
                "page": page_num,
                "total_pages": total_pages,
                "content_type": content_type,
                "chunk_level": "paragraph",
                "chunk_index": chunk_index,
            })
            chunk_index += 1

    print(f"      ✓ Created {len(all_chunks)} chunks from {len(pages)} pages")
    print(f"      Avg chunks/page: {len(all_chunks) / max(len(pages), 1):.1f}")

    if not all_chunks:
        print("\nERROR: No chunks generated from document!")
        sys.exit(1)

    # Content type distribution
    type_dist = {}
    for c in all_chunks:
        ct = c["content_type"]
        type_dist[ct] = type_dist.get(ct, 0) + 1
    print(f"      Content types: {type_dist}")

    # Page distribution sample
    page_dist = {}
    for c in all_chunks:
        page_dist[c["page"]] = page_dist.get(c["page"], 0) + 1

    sample_pages = dict(sorted(page_dist.items())[:10])
    suffix = f"... ({len(page_dist)} pages total)" if len(page_dist) > 10 else ""
    print(f"      Chunks per page (sample): {sample_pages}{suffix}")

    # ── Step 4: Embed & Upsert ───────────────────────────────
    print(f"\n[4/4] Embedding and upserting to Qdrant ({len(all_chunks)} chunks)...")

    import httpx

    nvidia_api_key = os.environ.get("NVIDIA_API_KEY", "")
    embed_model = os.environ.get("NVIDIA_EMBED_MODEL", "nvidia/nv-embedqa-e5-v5")
    nvidia_base_url = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")

    if not nvidia_api_key:
        # Try loading from .env
        env_path = os.path.join(BACKEND_DIR, "..", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("NVIDIA_API_KEY="):
                        nvidia_api_key = line.split("=", 1)[1]
                    elif line.startswith("NVIDIA_EMBED_MODEL="):
                        embed_model = line.split("=", 1)[1]
                    elif line.startswith("NVIDIA_BASE_URL="):
                        nvidia_base_url = line.split("=", 1)[1]

    if not nvidia_api_key:
        print("ERROR: NVIDIA_API_KEY not found!")
        sys.exit(1)

    print(f"      Using model: {embed_model}")

    headers = {
        "Authorization": f"Bearer {nvidia_api_key}",
        "Content-Type": "application/json",
    }

    embed_url = f"{nvidia_base_url}/embeddings"

    batch_size = 16
    total_upserted = 0
    total_batches = (len(all_chunks) + batch_size - 1) // batch_size
    start_time = time.time()
    errors = 0

    async with httpx.AsyncClient(timeout=60.0) as client:
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i:i + batch_size]
            texts = [c["content"] for c in batch]
            batch_num = i // batch_size + 1

            print(f"      Batch {batch_num}/{total_batches} ({len(texts)} chunks)...", end=" ", flush=True)

            try:
                # Call NVIDIA embedding API
                payload = {
                    "model": embed_model,
                    "input": texts,
                    "input_type": "passage",
                    "encoding_format": "float",
                    "truncate": "END",
                }

                resp = await client.post(embed_url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()

                embeddings = [item["embedding"] for item in data["data"]]

                # Build Qdrant points
                points = []
                for chunk, embedding in zip(batch, embeddings):
                    point_id = str(uuid.uuid4())
                    pt_payload = {
                        "document_id": chunk["document_id"],
                        "source": chunk["source"],
                        "content": chunk["content"],
                        "page": chunk["page"],
                        "total_pages": chunk["total_pages"],
                        "content_type": chunk["content_type"],
                        "chunk_level": chunk.get("chunk_level", "paragraph"),
                        "chunk_index": chunk.get("chunk_index", 0),
                    }
                    points.append(
                        models.PointStruct(id=point_id, vector=embedding, payload=pt_payload)
                    )

                qdrant.upsert(collection_name=collection_name, points=points)
                total_upserted += len(points)
                print("✓")

            except httpx.HTTPStatusError as e:
                errors += 1
                print(f"✗ HTTP Error: {e.response.status_code} - {e.response.text[:200]}")
                continue
            except Exception as e:
                errors += 1
                print(f"✗ Error: {e}")
                continue

    elapsed = time.time() - start_time

    # ── Summary ──────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  ✓ Ingestion Complete!")
    print(f"  Document ID : {document_id}")
    print(f"  File        : {filename}")
    print(f"  Pages       : {total_pages}")
    print(f"  Chunks      : {total_upserted}")
    print(f"  Errors      : {errors}")
    print(f"  Time        : {elapsed:.1f}s")
    print(f"  Avg/batch   : {elapsed / max(total_batches, 1):.2f}s")
    print(f"{'='*60}\n")

    # Verify
    info = qdrant.get_collection(collection_name)
    print(f"  Qdrant status : {info.status}")
    print(f"  Points count  : {info.points_count}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
