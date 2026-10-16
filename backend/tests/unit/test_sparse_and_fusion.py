from src.contracts import RetrievedChunk
from src.infrastructure.vector_store.sparse_encoder import SparseEncoder, tokenize
from src.retrieval.fusion import dedupe_chunks, reciprocal_rank_fusion


def test_tokenize_strips_stopwords_and_stems():
    toks = tokenize("The prices of iron ore increased sharply in FY2024")
    assert "the" not in toks and "of" not in toks
    assert "price" in toks and "fy2024" in toks and "increas" in toks


def test_sparse_encoder_query_matches_document():
    enc = SparseEncoder()
    doc = enc.encode_document("Iron ore prices increased 12% year on year")
    query = enc.encode_query("iron ore price increase")
    assert set(query.indices) & set(doc.indices)
    assert all(v == 1.0 for v in query.values)
    assert all(0 < v <= 2.2 for v in doc.values)
    assert enc.encode_document("").is_empty()


def _chunk(cid: str, text: str = "x", score: float = 0.5) -> RetrievedChunk:
    return RetrievedChunk(id=cid, content=text, score=score, source="s")


def test_rrf_prefers_items_ranked_high_in_multiple_lists():
    a = [_chunk("1", "one"), _chunk("2", "two"), _chunk("3", "three")]
    b = [_chunk("3", "three"), _chunk("1", "one"), _chunk("4", "four")]
    fused = reciprocal_rank_fusion([a, b], k=60)
    ids = [c.id for c in fused]
    assert ids[0] in ("1", "3") and ids[1] in ("1", "3")
    assert set(ids) == {"1", "2", "3", "4"}
    assert fused[0].metadata["pre_fusion_score"] == 0.5


def test_dedupe_removes_duplicate_ids_and_near_duplicate_text():
    chunks = [_chunk("1", "Same leading text here"), _chunk("2", "same   leading TEXT here"), _chunk("1", "dup id")]
    assert [c.id for c in dedupe_chunks(chunks)] == ["1"]
