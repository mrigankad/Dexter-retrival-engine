"""
Comprehensive RAG Query Test Script.

Runs a battery of questions against the ingested document and saves results.
Usage (from backend directory):
    python scripts/query_test.py
"""

import asyncio
import os
import sys
import time
import json
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

os.environ["QDRANT_HOST"] = "localhost"
os.environ["REDIS_HOST"] = "localhost"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["MINIO_ENDPOINT"] = "localhost:9000"

# ── Load .env ────────────────────────────────────────────────
env_path = os.path.join(BACKEND_DIR, "..", ".env")
env_vars = {}
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                env_vars[key.strip()] = val.strip()
                if key.strip() not in os.environ:
                    os.environ[key.strip()] = val.strip()

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
EMBED_MODEL = os.environ.get("NVIDIA_EMBED_MODEL", "nvidia/nv-embedqa-e5-v5")
LLM_MODEL = os.environ.get("NVIDIA_LLM_MODEL", "meta/llama-3.1-70b-instruct")
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"  # Local open-source reranker
COLLECTION = os.environ.get("QDRANT_COLLECTION", "documents")

# ── Questions ────────────────────────────────────────────────
SECTIONS = {
    "Section 1: Vision & Strategy": [
        "Explain JSW Steel's Vision 2030: Zero Harm as a strategic framework rather than a single target. How does the document describe this transformation?",
        "How does JSW Steel transition from reactive safety measures to a predictive, data-led safety system under Vision 2030?",
        "What role does digital innovation play in achieving Vision 2030: Zero Harm, and which specific platforms or initiatives are highlighted?",
        "How does Vision 2030 integrate employee well-being with operational excellence and safety outcomes?",
    ],
    "Section 2: Embedding Safety into Culture": [
        "How is a safety-first culture institutionalised across JSW Steel's operations, according to the document?",
        "What leadership-driven initiatives are mentioned that reinforce safety accountability and behavioural change?",
        "How does JSW Steel ensure that safety remains a non-negotiable value across all levels of the organisation?",
        "In what ways does the document describe inclusivity and intuition as part of JSW Steel's safety culture?",
    ],
    "Section 3: Leadership, Capability & Workforce": [
        "How does JSW Steel build and strengthen safety leadership capabilities within the organisation?",
        "What competency frameworks or leadership programmes are referenced in relation to health and safety?",
        "How are future-fit leaders identified and developed, and how does this connect to safety and sustainability goals?",
        "How does workforce diversity and inclusion intersect with safety and well-being initiatives in the document?",
    ],
    "Section 4: Digital & Flagship Initiatives": [
        "Describe the purpose and impact of Project Rakshak as outlined in the document.",
        "How do AI-driven tools and digital platforms contribute to industrial safety transformation at JSW Steel?",
        "What evidence does the document provide to show increased safety engagement and observation across the workforce?",
    ],
    "Section 5: Governance, Oversight & CSR": [
        "How does JSW Steel link its health and safety strategy with broader sustainability and governance discussions?",
        "What role do audits, cross-functional reviews, or corporate-level discussions play in reinforcing safety strategy?",
        "How do CSR initiatives complement JSW Steel's Vision 2030 and Zero Harm objectives?",
    ],
    "Section 6: Evidence-based / Validation": [
        "What measurable outcomes or indicators are cited in the document to demonstrate progress toward Zero Harm?",
        "Does the document mention any challenges or areas of ongoing improvement related to health and safety? If so, explain them.",
        "How does the document connect safety performance with employee well-being and community impact?",
        "According to the document, how is safety performance reviewed and monitored at an organisational level?",
    ],
    "Section 7: Trick / Control Questions": [
        "Does the document specify any external regulatory penalties faced by JSW Steel due to safety incidents?",
        "Is there any mention of specific accident rates or fatality numbers in the document?",
        "Does the document compare JSW Steel's safety performance directly with competitors?",
    ],
}

# ── RAG System Prompt ────────────────────────────────────────
SYSTEM_PROMPT = """You are a financial and corporate document analyst assistant with access to JSW Steel's corporate report.
Your task is to provide accurate, well-structured answers based ONLY on the provided context.

CRITICAL Guidelines:
1. ONLY use information from the provided context. Do NOT make up or assume any information.
2. Quote specific passages, data points, page numbers, and figures from the context.
3. If information is NOT found in the context, clearly state: "This information is not present in the provided context."
4. For numerical data, quote exact figures with units.
5. Structure your answers with clear paragraphs.
6. Cite page numbers where possible (e.g., "As stated on Page X...").
7. For trick/control questions, be honest if the information is absent — do NOT fabricate an answer.
8. Provide comprehensive answers that synthesize information from multiple pages when relevant."""


async def embed_query(client, query: str) -> list[float]:
    """Embed a query using NVIDIA API."""
    resp = await client.post(
        f"{NVIDIA_BASE_URL}/embeddings",
        headers={
            "Authorization": f"Bearer {NVIDIA_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": EMBED_MODEL,
            "input": [query],
            "input_type": "query",
            "encoding_format": "float",
            "truncate": "END",
        },
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


# ── Local CrossEncoder Reranker ──────────────────────────────
_cross_encoder = None

def get_cross_encoder():
    """Lazy-load the CrossEncoder model (singleton)."""
    global _cross_encoder
    if _cross_encoder is None:
        from sentence_transformers import CrossEncoder
        print(f"      [Loading reranker: {RERANK_MODEL}...]", flush=True)
        _cross_encoder = CrossEncoder(RERANK_MODEL)
        print(f"      [Reranker loaded ✓]")
    return _cross_encoder


def rerank_docs(query: str, documents: list[dict], top_k: int = 8) -> list[dict]:
    """Rerank documents using local CrossEncoder."""
    if not documents:
        return []

    model = get_cross_encoder()
    texts = [d["payload"]["content"] for d in documents]

    # Score query-document pairs
    pairs = [(query, text) for text in texts]
    scores = model.predict(pairs).tolist()

    # Attach scores and sort
    scored = []
    for doc, score in zip(documents, scores):
        d = doc.copy()
        d["rerank_score"] = float(score)
        scored.append(d)

    scored.sort(key=lambda x: x["rerank_score"], reverse=True)
    return scored[:top_k]


async def generate_answer(client, query: str, context: str, retries: int = 3) -> str:
    """Generate answer using NVIDIA LLM with retry logic."""
    prompt = f"""Based on the following context from a JSW Steel corporate document, answer the question comprehensively.

CONTEXT:
{context}

QUESTION: {query}

ANSWER:"""

    for attempt in range(retries):
        try:
            resp = await client.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {NVIDIA_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500,
                },
                timeout=90.0,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            if attempt < retries - 1:
                print(f"[retry {attempt+1}]", end=" ", flush=True)
                import asyncio
                await asyncio.sleep(2)
            else:
                raise e
    return "ERROR: Failed after retries"


async def main():
    import httpx
    from qdrant_client import QdrantClient

    qdrant = QdrantClient(host="localhost", port=6333)

    # Verify collection
    info = qdrant.get_collection(COLLECTION)
    print(f"\n{'='*70}")
    print(f"  RAG Query Test Suite")
    print(f"  Collection: {COLLECTION} ({info.points_count} points)")
    print(f"  LLM: {LLM_MODEL}")
    print(f"  Embeddings: {EMBED_MODEL}")
    print(f"  Reranker: {RERANK_MODEL}")
    print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    total_questions = sum(len(qs) for qs in SECTIONS.values())
    print(f"  Total questions: {total_questions}\n")

    results = []
    q_num = 0
    overall_start = time.time()

    async with httpx.AsyncClient(timeout=120.0) as client:
        for section_name, questions in SECTIONS.items():
            print(f"\n{'─'*70}")
            print(f"  📋 {section_name}")
            print(f"{'─'*70}")

            for question in questions:
                q_num += 1
                q_start = time.time()
                
                print(f"\n  Q{q_num}/{total_questions}: {question[:80]}...")

                try:
                    # Step 1: Embed query
                    print(f"      → Embedding query...", end=" ", flush=True)
                    query_vector = await embed_query(client, question)
                    print("✓")

                    # Step 2: Search Qdrant (retrieve top 20 for reranking)
                    print(f"      → Searching Qdrant...", end=" ", flush=True)
                    search_results = qdrant.query_points(
                        collection_name=COLLECTION,
                        query=query_vector,
                        limit=20,
                        with_payload=True,
                    )
                    
                    docs = [
                        {"id": str(hit.id), "score": hit.score, "payload": hit.payload}
                        for hit in search_results.points
                    ]
                    print(f"✓ ({len(docs)} results)")

                    # Step 3: Rerank with local CrossEncoder
                    print(f"      → Reranking (local)...", end=" ", flush=True)
                    reranked = rerank_docs(question, docs, top_k=8)
                    top_rerank = reranked[0]['rerank_score'] if reranked else 0
                    print(f"✓ (top {len(reranked)}, best={top_rerank:.3f})")

                    # Step 4: Assemble context
                    context_parts = []
                    source_pages = []
                    for i, doc in enumerate(reranked, 1):
                        p = doc["payload"]
                        page = p.get("page", "N/A")
                        source = p.get("source", "Unknown")
                        content = p.get("content", "")
                        score = doc.get("rerank_score", doc.get("score", 0))
                        
                        context_parts.append(
                            f"[Source {i} | {source}, Page {page} | Score: {score:.3f}]\n{content}"
                        )
                        if page != "N/A":
                            source_pages.append(page)

                    context = "\n\n---\n\n".join(context_parts)

                    # Step 5: Generate answer
                    print(f"      → Generating answer...", end=" ", flush=True)
                    answer = await generate_answer(client, question, context)
                    print(f"✓ ({len(answer)} chars)")

                    elapsed = time.time() - q_start

                    results.append({
                        "section": section_name,
                        "question_number": q_num,
                        "question": question,
                        "answer": answer,
                        "source_pages": sorted(set(source_pages)),
                        "num_sources": len(reranked),
                        "top_score": reranked[0].get("rerank_score", reranked[0].get("score", 0)) if reranked else 0,
                        "latency_seconds": round(elapsed, 2),
                        "status": "success",
                    })

                    print(f"      ✓ Done in {elapsed:.1f}s | Pages: {sorted(set(source_pages))[:8]}")

                except Exception as e:
                    elapsed = time.time() - q_start
                    print(f"      ✗ Error: {e}")
                    results.append({
                        "section": section_name,
                        "question_number": q_num,
                        "question": question,
                        "answer": f"ERROR: {str(e)}",
                        "source_pages": [],
                        "num_sources": 0,
                        "latency_seconds": round(elapsed, 2),
                        "status": "error",
                    })

    total_elapsed = time.time() - overall_start

    # ── Write Results ────────────────────────────────────────
    output_dir = os.path.join(BACKEND_DIR, "..")
    
    # 1. Write formatted text report
    report_path = os.path.join(output_dir, "query_results.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("  JSW Steel - RAG Query Test Results\n")
        f.write(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  Total Questions: {total_questions}\n")
        f.write(f"  Total Time: {total_elapsed:.1f}s\n")
        f.write(f"  Avg per Question: {total_elapsed / total_questions:.1f}s\n")
        f.write(f"  LLM: {LLM_MODEL}\n")
        f.write(f"  Embeddings: {EMBED_MODEL}\n")
        f.write(f"  Reranker: {RERANK_MODEL}\n")
        f.write("=" * 80 + "\n\n")

        current_section = ""
        for r in results:
            if r["section"] != current_section:
                current_section = r["section"]
                f.write("\n" + "━" * 80 + "\n")
                f.write(f"  🔹 {current_section}\n")
                f.write("━" * 80 + "\n\n")

            f.write(f"Q{r['question_number']}: {r['question']}\n")
            f.write(f"[Sources: Pages {r['source_pages']} | {r['latency_seconds']}s | Status: {r['status']}]\n\n")
            f.write(f"{r['answer']}\n\n")
            f.write("─" * 80 + "\n\n")

    # 2. Write JSON for programmatic access
    json_path = os.path.join(output_dir, "query_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "metadata": {
                "generated_at": datetime.now().isoformat(),
                "total_questions": total_questions,
                "total_time_seconds": round(total_elapsed, 2),
                "models": {
                    "llm": LLM_MODEL,
                    "embed": EMBED_MODEL,
                    "rerank": RERANK_MODEL,
                },
            },
            "results": results,
        }, f, indent=2, ensure_ascii=False)

    # ── Final Summary ────────────────────────────────────────
    successes = sum(1 for r in results if r["status"] == "success")
    errors = sum(1 for r in results if r["status"] == "error")
    avg_latency = sum(r["latency_seconds"] for r in results) / len(results) if results else 0

    print(f"\n\n{'='*70}")
    print(f"  ✅ Query Test Complete!")
    print(f"  Successful: {successes}/{total_questions}")
    print(f"  Errors: {errors}")
    print(f"  Total Time: {total_elapsed:.1f}s")
    print(f"  Avg Latency: {avg_latency:.1f}s per question")
    print(f"  Results: {report_path}")
    print(f"  JSON: {json_path}")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    asyncio.run(main())
