"""
Context Compression Agent - Evidence Compression and Deduplication.

Compresses retrieved evidence to fit within token budgets while
preserving factual accuracy, citations, and key data points.

Features:
- Per-sub-query compression to token limit
- Cross-query deduplication index
- Preserves numerical data, citations, and page references
- Extractive + abstractive hybrid compression
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import hashlib
import re

from core.config import settings
from core.logger import get_logger, log_timing

logger = get_logger(__name__)


@dataclass
class CompressedEvidence:
    """Output of the compression agent."""
    sub_query: str
    compressed_text: str
    token_count: int
    original_token_count: int
    compression_ratio: float
    preserved_citations: List[str]
    preserved_numbers: List[str]
    chunk_ids_used: List[str]
    dedup_removed: int = 0


@dataclass
class DeduplicationIndex:
    """Cross-query chunk deduplication tracker."""
    seen_hashes: Set[str] = field(default_factory=set)
    seen_pages: Dict[str, Set[int]] = field(default_factory=dict)  # doc_id -> set of pages seen
    fact_hashes: Set[str] = field(default_factory=set)

    def is_duplicate_chunk(self, content: str, threshold: int = 200) -> bool:
        """Check if a chunk is a near-duplicate of previously seen content."""
        # Use first N chars as fingerprint
        fingerprint = hashlib.md5(content[:threshold].encode()).hexdigest()
        if fingerprint in self.seen_hashes:
            return True
        self.seen_hashes.add(fingerprint)
        return False

    def is_duplicate_page(self, doc_id: str, page: int) -> bool:
        """Check if we've already seen significant content from this page."""
        if doc_id not in self.seen_pages:
            self.seen_pages[doc_id] = set()
        if page in self.seen_pages[doc_id]:
            return True
        self.seen_pages[doc_id].add(page)
        return False

    def register_fact(self, fact_text: str) -> bool:
        """Register a key fact. Returns True if it's new."""
        fact_hash = hashlib.md5(fact_text.strip().lower().encode()).hexdigest()
        if fact_hash in self.fact_hashes:
            return False
        self.fact_hashes.add(fact_hash)
        return True

    def reset(self):
        """Reset the dedup index for a new query plan."""
        self.seen_hashes.clear()
        self.seen_pages.clear()
        self.fact_hashes.clear()


# ── Compression Prompts ───────────────────────────────────────

COMPRESSION_SYSTEM_PROMPT = """You are a High-Precision Data Distiller for enterprise document analysis.
Your ONLY job is to compress evidence while preserving factual accuracy."""

COMPRESSION_PROMPT = """TASK: Compress the following evidence for the question: "{sub_query}"

CONSTRAINTS:
1. ONLY keep data points, specific dates, exact figures, and cited page numbers.
2. Remove preambles, marketing language, boilerplate text, and verbose explanations.
3. Limit output to {max_tokens} tokens maximum.
4. Format as a bulleted list of FACTS only.
5. If chunks contain contradictory data, state BOTH with their page citations.
6. PRESERVE: All [Page X] citations, percentages, currency values, and metric names.
7. DISCARD: Filler phrases, repeated context, and non-specific statements.

INPUT EVIDENCE:
{evidence}

COMPRESSED FACTS (bulleted list):"""


class ContextCompressor:
    """
    AI agent that compresses retrieved evidence per sub-query.
    
    Pipeline:
    1. Deduplicate chunks across sub-queries
    2. Extract key facts, numbers, and citations
    3. LLM-based abstractive compression
    4. Token budget enforcement
    5. Cross-validate preserved data
    """

    def __init__(self, llm_service=None):
        self.llm = llm_service
        self.dedup_index = DeduplicationIndex()
        self._number_pattern = re.compile(
            r"[\$₹€£]?\s*\d[\d,]*(?:\.\d+)?\s*(?:%|cr|mn|bn|million|billion|crore|lakh|/dmt|/tonne)?",
            re.IGNORECASE,
        )
        self._citation_pattern = re.compile(
            r"\[(?:Page|Source|Ref)\s*[\d/,\s]+\]",
            re.IGNORECASE,
        )

    def reset_dedup(self):
        """Reset deduplication index for a new query plan execution."""
        self.dedup_index.reset()

    @log_timing("context_compress")
    async def compress(
        self,
        sub_query: str,
        retrieved_docs: List[Dict[str, Any]],
        max_tokens: int = 300,
        use_llm: bool = True,
    ) -> CompressedEvidence:
        """
        Compress retrieved evidence for a single sub-query.
        
        Args:
            sub_query: The sub-query this evidence answers
            retrieved_docs: List of retrieved document chunks
            max_tokens: Maximum token budget for compressed output
            use_llm: Whether to use LLM for compression
            
        Returns:
            CompressedEvidence with compressed text and metadata
        """
        if not retrieved_docs:
            return CompressedEvidence(
                sub_query=sub_query,
                compressed_text="No evidence found.",
                token_count=3,
                original_token_count=0,
                compression_ratio=0.0,
                preserved_citations=[],
                preserved_numbers=[],
                chunk_ids_used=[],
            )

        # Step 1: Deduplicate chunks
        deduped_docs, dedup_removed = self._deduplicate(retrieved_docs)

        # Step 2: Extract and preserve key data
        preserved_numbers = []
        preserved_citations = []
        chunk_ids = []

        evidence_parts = []
        for doc in deduped_docs:
            payload = doc.get("payload", {})
            content = payload.get("content", "")
            page = payload.get("page", "N/A")
            source = payload.get("source", "Unknown")
            chunk_id = payload.get("chunk_index", "")

            # Track citations and numbers
            numbers = self._number_pattern.findall(content)
            preserved_numbers.extend(numbers)

            citations = self._citation_pattern.findall(content)
            preserved_citations.extend(citations)

            chunk_ids.append(str(chunk_id))

            # Format with page citation
            evidence_parts.append(f"[Page {page}] {content}")

        raw_evidence = "\n\n".join(evidence_parts)
        original_tokens = len(raw_evidence) // 4

        # Step 3: Compress
        if use_llm and self.llm and original_tokens > max_tokens * 1.5:
            compressed_text = await self._llm_compress(
                sub_query, raw_evidence, max_tokens
            )
        else:
            compressed_text = self._extractive_compress(
                raw_evidence, max_tokens, preserved_numbers, preserved_citations
            )

        # Step 4: Validate compression preserved key data
        compressed_text = self._validate_preservation(
            compressed_text, preserved_numbers[:10], preserved_citations[:10]
        )

        compressed_tokens = len(compressed_text) // 4
        ratio = 1 - (compressed_tokens / max(original_tokens, 1))

        return CompressedEvidence(
            sub_query=sub_query,
            compressed_text=compressed_text,
            token_count=compressed_tokens,
            original_token_count=original_tokens,
            compression_ratio=round(ratio, 2),
            preserved_citations=list(set(preserved_citations)),
            preserved_numbers=list(set(preserved_numbers[:20])),
            chunk_ids_used=chunk_ids,
            dedup_removed=dedup_removed,
        )

    async def compress_multi(
        self,
        sub_queries_with_docs: List[Tuple[str, List[Dict[str, Any]]]],
        max_tokens_per_query: int = 300,
    ) -> List[CompressedEvidence]:
        """
        Compress evidence for multiple sub-queries with cross-query dedup.
        
        Args:
            sub_queries_with_docs: List of (sub_query, retrieved_docs) tuples
            max_tokens_per_query: Token budget per sub-query
            
        Returns:
            List of CompressedEvidence for each sub-query
        """
        self.reset_dedup()
        results = []

        for sub_query, docs in sub_queries_with_docs:
            compressed = await self.compress(
                sub_query=sub_query,
                retrieved_docs=docs,
                max_tokens=max_tokens_per_query,
            )
            results.append(compressed)

        total_original = sum(r.original_token_count for r in results)
        total_compressed = sum(r.token_count for r in results)
        total_dedup = sum(r.dedup_removed for r in results)

        logger.info(
            "Multi-query compression complete",
            queries=len(results),
            original_tokens=total_original,
            compressed_tokens=total_compressed,
            total_dedup_removed=total_dedup,
        )

        return results

    # ── Internal Methods ───────────────────────────────────────

    def _deduplicate(
        self, docs: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Remove duplicate chunks across sub-queries."""
        deduped = []
        removed = 0

        for doc in docs:
            payload = doc.get("payload", {})
            content = payload.get("content", "")

            if self.dedup_index.is_duplicate_chunk(content):
                removed += 1
                continue

            deduped.append(doc)

        if removed > 0:
            logger.debug(f"Deduplication removed {removed} chunks")

        return deduped, removed

    async def _llm_compress(
        self, sub_query: str, evidence: str, max_tokens: int
    ) -> str:
        """Use LLM for abstractive compression."""
        try:
            prompt = COMPRESSION_PROMPT.format(
                sub_query=sub_query,
                max_tokens=max_tokens,
                evidence=evidence[:8000],  # Cap input to avoid token limits
            )

            response = await self.llm.generate(
                prompt=prompt,
                system_prompt=COMPRESSION_SYSTEM_PROMPT,
                max_tokens=max_tokens + 100,  # Small buffer
                temperature=0.1,
            )

            return response.strip()

        except Exception as e:
            logger.warning("LLM compression failed, using extractive", error=str(e))
            return self._extractive_compress(evidence, max_tokens, [], [])

    def _extractive_compress(
        self,
        evidence: str,
        max_tokens: int,
        priority_numbers: List[str],
        priority_citations: List[str],
    ) -> str:
        """
        Extractive compression: select most information-dense sentences.
        
        Prioritizes:
        1. Sentences with numbers
        2. Sentences with citations
        3. Shorter, fact-dense sentences
        """
        # Split into sentences
        sentences = re.split(r"(?<=[.!?])\s+|\n+", evidence)
        if not sentences:
            return evidence[:max_tokens * 4]

        # Score each sentence
        scored = []
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 10:
                continue

            score = 0.0

            # Boost for numbers
            num_count = len(self._number_pattern.findall(sent))
            score += num_count * 2.0

            # Boost for citations
            cit_count = len(self._citation_pattern.findall(sent))
            score += cit_count * 1.5

            # Boost for priority numbers
            for num in priority_numbers[:5]:
                if num in sent:
                    score += 3.0

            # Penalty for length (prefer concise)
            word_count = len(sent.split())
            if word_count > 50:
                score -= 1.0

            # Penalty for vague language
            vague_terms = ["generally", "typically", "usually", "approximately",
                          "various", "several", "many", "some", "certain"]
            for term in vague_terms:
                if term in sent.lower():
                    score -= 0.5

            scored.append((sent, score))

        # Sort by score (descending)
        scored.sort(key=lambda x: x[1], reverse=True)

        # Select sentences within token budget
        selected = []
        current_tokens = 0
        for sent, score in scored:
            sent_tokens = len(sent) // 4
            if current_tokens + sent_tokens > max_tokens:
                break
            selected.append(sent)
            current_tokens += sent_tokens

        return "\n".join(selected) if selected else evidence[:max_tokens * 4]

    def _validate_preservation(
        self,
        compressed: str,
        key_numbers: List[str],
        key_citations: List[str],
    ) -> str:
        """
        Validate that key data was preserved in compression.
        If critical numbers are missing, append them.
        """
        missing_data = []

        # Check if key numbers survived compression
        for num in key_numbers[:5]:
            cleaned = num.strip()
            if cleaned and cleaned not in compressed:
                missing_data.append(f"• Data point: {cleaned}")

        # Append at most 3 missing data points
        if missing_data:
            compressed += "\n\n[Additional preserved data:]"
            for item in missing_data[:3]:
                compressed += f"\n{item}"

        return compressed
