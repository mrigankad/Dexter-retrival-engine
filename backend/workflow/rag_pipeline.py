"""
RAG Pipeline - Production-Grade Retrieval Reasoning Engine.

Implements the Planner-Driven Multi-Hop Retrieval + Evidence Reasoning workflow:

  Query → Classifier → Planner → [Parallel Sub-Query Executor]
                                       ↓
                                 Context Compressor (dedup)
                                       ↓
                                 Feedback Loop (if missing)
                                       ↓
                                 Synthesis Engine → Final Answer

Simple queries bypass the planner and use direct retrieval.
"""

from typing import AsyncGenerator, Dict, List, Optional, Any, Tuple
import json
import re
import time

from core.config import settings
from core.logger import get_logger, log_timing
from core.telemetry import get_rag_metrics, Timer

from services.nvidia_llm_service import NvidiaLLMService
from services.embedding_service import EmbeddingService
from services.retrieval_service import RetrievalService
from services.object_storage_service import ObjectStorageService
from services.guardrails_service import GuardrailsService
from services.evaluation_service import EvaluationService
from services.planner_service import PlannerService, QueryPlan, SubQuery
from services.query_classifier import QueryClassifier, QueryType
from services.context_compressor import ContextCompressor
from services.plan_cache_service import PlanCacheService

from workflow.multi_hop_executor import MultiHopExecutor
from workflow.synthesis_engine import SynthesisEngine
from workflow.feedback_loop import FeedbackLoop

logger = get_logger(__name__)


# ── Pattern Detectors ─────────────────────────────────────────

PAGE_NUMBER_PATTERN = re.compile(
    r'\b(?:page|pg|p\.?)\s*(?:number|no\.?|#)?\s*(\d+)\b',
    re.IGNORECASE
)

FINANCIAL_PATTERNS = [
    r'\b(?:price|cost|rate|value|amount|revenue|profit|margin|sales|income)\b',
    r'\b(?:average|mean|median|total|sum|growth|decline|change|movement|trend)\b',
    r'\b(?:year[\s-]?(?:on|over)[\s-]?year|yoy|quarterly|annual|monthly)\b',
    r'\b(?:percentage|percent|%|\$|₹|rs\.?|inr|usd)\b',
    r'\b(?:benchmark|index|indicator|metric|kpi)\b',
    r'\b(?:iron\s*ore|steel|coal|raw\s*material|commodity)\b',
    r'\b(?:forecast|projection|estimate|budget|target)\b',
    r'\b\d+(?:\.\d+)?(?:\s*(?:million|billion|crore|lakh|mn|bn|cr|lac))?\b',
]

FINANCIAL_QUERY_PATTERN = re.compile(
    '|'.join(FINANCIAL_PATTERNS),
    re.IGNORECASE
)


def extract_page_number(query: str) -> Optional[int]:
    """Extract page number from query if asking about a specific page."""
    match = PAGE_NUMBER_PATTERN.search(query)
    if match:
        return int(match.group(1))
    return None


def is_financial_query(query: str) -> bool:
    """Check if query is financial/numerical in nature."""
    matches = FINANCIAL_QUERY_PATTERN.findall(query)
    return len(matches) >= 2


def extract_keywords(query: str) -> List[str]:
    """Extract important keywords for hybrid search."""
    stop_words = {
        'what', 'is', 'the', 'a', 'an', 'are', 'was', 'were', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'must', 'can', 'could', 'for', 'of', 'to',
        'in', 'on', 'at', 'by', 'with', 'about', 'into', 'through', 'during',
        'before', 'after', 'above', 'below', 'from', 'up', 'down', 'out', 'off',
        'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there',
        'when', 'where', 'why', 'how', 'all', 'each', 'few', 'more', 'most',
        'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same',
        'so', 'than', 'too', 'very', 'just', 'and', 'but', 'if', 'or', 'because',
        'as', 'until', 'while', 'please', 'tell', 'me', 'show', 'give', 'find',
    }

    query_lower = query.lower()

    multi_word_terms = [
        'iron ore', 'year on year', 'year over year', 'raw material',
        'steel price', 'benchmark price', 'average price', 'profit margin',
        'operating margin', 'net profit', 'gross profit', 'total revenue',
    ]

    keywords = []
    for term in multi_word_terms:
        if term in query_lower:
            keywords.append(term)
            query_lower = query_lower.replace(term, '')

    words = re.findall(r'\b[a-zA-Z0-9]+\b', query_lower)
    for word in words:
        if word not in stop_words and len(word) > 2:
            keywords.append(word)

    return list(set(keywords))


# ── Prompt Templates ──────────────────────────────────────────

QUERY_REWRITE_PROMPT = """Rewrite the following query to be more suitable for semantic search in a document retrieval system.
Make it clear, specific, and focused on the key concepts.
IMPORTANT: Preserve all specific terms like numbers, prices, percentages, company names, and technical terms.
Only output the rewritten query, nothing else.

Original query: {query}

Rewritten query:"""

FINANCIAL_QUERY_REWRITE_PROMPT = """Rewrite this financial/numerical query for document retrieval.
CRITICAL: Keep ALL specific terms like:
- Numbers, prices, percentages
- Time periods (year on year, quarterly, annual, FY2024, etc.)
- Financial terms (revenue, profit, margin, price, cost)
- Company/product names
- Units (million, crore, $/dmt, etc.)

Original query: {query}

Rewritten query (keep all specifics):"""

RAG_SYSTEM_PROMPT = """
You are a professional Enterprise RAG Assistant. Your goal is to provide accurate, evidence-based answers using the provided context.

### MANDATORY FORMATTING RULES:
1. **Always use Markdown**: Treat every response as a structured Markdown document.
2. **Tables**: Use GFM tables (`| head |`) only. Always include the separator row (`|---|`).
3. **Lists**: Use standard dashes (`- `) for unordered lists and (`1. `) for ordered lists. Avoid jamming list items into paragraphs.
4. **Code Blocks**: Always wrap code, terminal commands, or structured data in triple backticks with the appropriate language tag.
5. **Citations**: Always cite your sources using [Page X] or [Source ID] based on the context provided.
6. **No Speculation**: If the answer is not in the context, state that clearly.

Answer the user query based ONLY on the provided context evidence.
"""

FINANCIAL_SYSTEM_PROMPT = """You are a financial analyst assistant with access to company documents.
Your task is to find and present specific numerical data from the provided context.

CRITICAL Guidelines for financial/numerical questions:
1. SEARCH the entire context carefully for relevant numbers, prices, percentages
2. Look for data in tables, bullet points, and paragraph text
3. Quote exact figures with their units (e.g., "$85/dmt", "₹5,234 crores", "12.5%")
4. Include the time period or year for any data point
5. Cite the page number for each piece of data
6. If multiple related figures exist, present them in a table
7. If the EXACT data isn't found, state what related data IS available
8. Never make up numbers - only use what's in the context"""


class RAGPipeline:
    """
    Production-grade RAG pipeline with planner-driven multi-hop retrieval.
    
    Architecture:
    ┌─────────────────────────────────────────────────────┐
    │  Query → Classifier → [Simple: Direct RAG]          │
    │              │                                       │
    │         [Complex]                                    │
    │              ▼                                       │
    │    Plan Cache → Planner (LLM) → Query Plan          │
    │              ▼                                       │
    │    Multi-Hop Executor (Parallel + Compress)          │
    │              ▼                                       │
    │    Feedback Loop (if evidence missing)               │
    │              ▼                                       │
    │    Synthesis Engine (Strategy-aware)                  │
    │              ▼                                       │
    │    Guardrails → Final Response                       │
    └─────────────────────────────────────────────────────┘
    """

    def __init__(
        self,
        llm_service: Optional[NvidiaLLMService] = None,
        embedding_service: Optional[EmbeddingService] = None,
        retrieval_service: Optional[RetrievalService] = None,
    ):
        self.llm = llm_service or NvidiaLLMService()
        self.embedding = embedding_service or EmbeddingService()
        self.retrieval = retrieval_service or RetrievalService()
        self.object_storage = ObjectStorageService()
        self.guardrails = GuardrailsService()
        self.evaluation = EvaluationService()
        self.metrics = get_rag_metrics()

        # ── New Production Components ──
        self.classifier = QueryClassifier(llm_service=self.llm)
        self.planner = PlannerService(self.llm)
        self.plan_cache = PlanCacheService()
        self.multi_hop = MultiHopExecutor(
            retrieval_service=self.retrieval,
            llm_service=self.llm,
            max_concurrent=5,
            tokens_per_sub_query=300,
        )
        self.synthesizer = SynthesisEngine(llm_service=self.llm)
        self.feedback = FeedbackLoop(
            retrieval_service=self.retrieval,
            llm_service=self.llm,
            max_retries=3,
        )

    # ── Query Rewriting ───────────────────────────────────────

    @log_timing("query_rewrite")
    async def rewrite_query(self, query: str) -> str:
        """Rewrite query for better retrieval."""
        try:
            prompt = QUERY_REWRITE_PROMPT.format(query=query)
            rewritten = await self.llm.generate(
                prompt=prompt, max_tokens=100, temperature=0.3,
            )
            logger.debug("Query rewritten", original=query, rewritten=rewritten.strip())
            return rewritten.strip()
        except Exception as e:
            logger.warning("Query rewrite failed, using original", error=str(e))
            return query

    # ── Multimodal Context Assembly ───────────────────────────

    async def _fetch_multimodal_asset(self, asset_path: str) -> Optional[Dict[str, Any]]:
        """Fetch a multimodal asset (table/chart data) from object storage."""
        try:
            return self.object_storage.get_json(
                bucket_name=settings.minio_bucket_assets,
                object_name=asset_path
            )
        except Exception as e:
            logger.warning("Failed to fetch asset", path=asset_path, error=str(e))
            return None

    async def _assemble_rich_context(
        self, retrieved_docs: List[Dict[str, Any]], max_tokens: int = 4096
    ) -> str:
        """Assemble context with text chunks and multimodal assets."""
        context_parts = []
        current_tokens = 0
        seen_assets = set()

        for i, doc in enumerate(retrieved_docs, 1):
            payload = doc.get("payload", {})
            content = payload.get("content", "")
            content_type = payload.get("content_type", "text")
            page = payload.get("page", "N/A")
            source = payload.get("source", "Unknown")

            header = f"[Source {i}: {source}, Page {page}]"
            context_parts.append(f"{header}\n{content}")
            current_tokens += len(content) // 4

            # Fetch detailed asset data if available
            asset_path = payload.get("asset_path")
            if asset_path and asset_path not in seen_assets:
                asset_data = await self._fetch_multimodal_asset(asset_path)
                if asset_data:
                    asset_type = asset_data.get("type", "asset").upper()
                    if asset_type == "TABLE":
                        table_content = asset_data.get("content", "")
                        formatted = f"\n[DETAILED TABLE DATA FROM SOURCE {i}]\n{table_content}"
                        context_parts.append(formatted)
                        current_tokens += len(formatted) // 4
                    elif asset_type == "GRAPHIC":
                        analysis = asset_data.get("analysis", "")
                        formatted = f"\n[CHART ANALYSIS FROM SOURCE {i}]\n{analysis}"
                        context_parts.append(formatted)
                        current_tokens += len(formatted) // 4
                    seen_assets.add(asset_path)

            if current_tokens > max_tokens:
                break

        return "\n\n---\n\n".join(context_parts)

    # ── Complex Plan Execution (NEW: uses modular components) ─

    async def _execute_complex_plan(
        self, plan: QueryPlan
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Execute a multi-hop plan using the production components.
        
        Pipeline:
        1. Multi-hop executor (parallel retrieval + compression)
        2. Feedback loop for missing evidence
        3. Return assembled context + sources
        """
        # Phase 1: Parallel sub-query execution with compression
        context, sources, results = await self.multi_hop.execute_plan(
            plan=plan,
            top_k_per_query=settings.top_k_retrieval,
            compress=True,
        )

        # Phase 2: Feedback loop for failed sub-queries
        failed_queries = [
            r.sub_query.question
            for r in results
            if not r.success or not r.evidence_text
        ]

        if failed_queries:
            logger.info(
                f"Triggering feedback loop for {len(failed_queries)} failed sub-queries"
            )
            additional_context, additional_sources = await self.feedback.retry_missing_evidence(
                original_query=plan.sub_queries[0].question if plan.sub_queries else "",
                failed_sub_queries=failed_queries,
                original_context=context,
            )

            if additional_context:
                context += "\n\n" + additional_context
                sources.extend(additional_sources)

        return context, sources

    # ── Non-Streaming Execution ───────────────────────────────

    @log_timing("rag_execute")
    async def execute(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        rewrite_query: bool = True,
        document_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute full RAG pipeline with reasoning (non-streaming)."""
        start_time = time.time()

        # Step 1: Classify query
        classification = await self.classifier.classify(query)

        # Step 2: Plan (with cache)
        plan = None
        if classification.needs_planning:
            cached_plan = self.plan_cache.get_plan(query)
            if cached_plan:
                plan = QueryPlan(**cached_plan)
                logger.info("Using cached plan")
            else:
                plan = await self.planner.plan_query(query)
                self.plan_cache.store_plan(query, plan.model_dump())

        # Step 3: Execute
        if plan and (plan.query_type != "lookup" or len(plan.sub_queries) > 1):
            # Pass document_ids to complex plan (future enhancement for planner)
            context, sources = await self._execute_complex_plan(plan)

            # Step 4: Synthesis
            synthesis_result = await self.synthesizer.synthesize(
                query=query,
                evidence_context=context,
                synthesis_strategy=plan.synthesis_strategy,
                plan_reasoning=plan.reasoning,
                max_tokens=2048,
            )

            elapsed_ms = (time.time() - start_time) * 1000

            return {
                "response": synthesis_result["response"],
                "sources": sources,
                "context_used": True,
                "plan": plan.model_dump(),
                "classification": classification.to_dict(),
                "confidence": synthesis_result.get("confidence", 0.5),
                "citations": synthesis_result.get("citations", []),
                "missing_info": synthesis_result.get("missing_info", []),
                "latency_ms": round(elapsed_ms),
            }

        # Fallback: simple RAG
        return await self._execute_simple(query, chat_history, rewrite_query, document_ids)

    async def _execute_simple(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        rewrite_query: bool = True,
        document_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Execute simple single-hop RAG."""
        requested_page = extract_page_number(query)
        is_financial = is_financial_query(query)
        keywords = extract_keywords(query) if settings.hybrid_search_enabled else []

        # Rewrite
        if requested_page:
            search_query = query
        elif is_financial and rewrite_query:
            try:
                prompt = FINANCIAL_QUERY_REWRITE_PROMPT.format(query=query)
                search_query = await self.llm.generate(prompt=prompt, max_tokens=150, temperature=0.2)
                search_query = search_query.strip()
            except Exception:
                search_query = query
        elif rewrite_query:
            search_query = await self.rewrite_query(query)
        else:
            search_query = query

        # Retrieve
        top_k = settings.top_k_retrieval
        if is_financial:
            top_k = int(top_k * 1.5)

        filter_conds = {}
        if requested_page:
            filter_conds["page"] = requested_page
        if document_ids:
            filter_conds["document_id"] = document_ids

        retrieved_docs = await self.retrieval.retrieve(
            query=search_query,
            top_k=top_k,
            rerank=settings.enable_reranking,
            filter_conditions=filter_conds if filter_conds else None,
            keywords=keywords if settings.hybrid_search_enabled else None,
        )

        # Context
        context = await self._assemble_rich_context(retrieved_docs, max_tokens=settings.max_context_tokens)

        # Generate
        sys_prompt = FINANCIAL_SYSTEM_PROMPT if is_financial else RAG_SYSTEM_PROMPT
        if requested_page:
            prompt = f"Summarize page {requested_page} using this content:\n\n{context}\n\nQuestion: {query}"
        elif is_financial:
            prompt = f"Extract all financial data from this context:\n\n{context}\n\nQuestion: {query}"
        else:
            prompt = f"Context:\n\n{context}\n\nQuestion: {query}"

        if context:
            response = await self.llm.generate(
                prompt=prompt,
                chat_history=chat_history,
                system_prompt=sys_prompt,
                max_tokens=1500 if is_financial else 1024,
                temperature=0.3 if is_financial else 0.7,
            )
        else:
            response = await self.llm.generate(prompt=query, chat_history=chat_history)

        # Sources
        sources = []
        for doc in retrieved_docs:
            payload = doc.get("payload", {})
            sources.append({
                "source": payload.get("source", "Unknown"),
                "page": payload.get("page", "N/A"),
                "total_pages": payload.get("total_pages", "N/A"),
                "chunk_index": payload.get("chunk_index", 0),
                "document_id": payload.get("document_id"),
                "score": doc.get("score", 0),
                "content_type": payload.get("content_type", "text"),
            })

        return {
            "response": response,
            "sources": sources,
            "context_used": bool(context),
        }

    # ── Streaming Execution ───────────────────────────────────

    async def execute_stream(
        self,
        query: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
        rewrite_query: bool = True,
        document_ids: Optional[List[str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute RAG pipeline with streaming and reasoning-grade synthesis."""

        # Step 1: Classify query
        classification = await self.classifier.classify(query)

        # Step 2: Plan (with cache)
        plan = None
        if classification.needs_planning:
            cached_plan = self.plan_cache.get_plan(query)
            if cached_plan:
                plan = QueryPlan(**cached_plan)
            else:
                plan = await self.planner.plan_query(query)
                self.plan_cache.store_plan(query, plan.model_dump())

        # ── Complex Multi-Hop Path ────────────────────────────
        if plan and (plan.query_type != "lookup" or len(plan.sub_queries) > 1):
            # Yield classification metadata
            yield {
                "type": "metadata",
                "data": {
                    "classification": classification.to_dict(),
                    "plan": plan.model_dump(),
                },
            }

            # Execute plan (needs document_ids update in multi_hop executor for full production parity)
            context, sources = await self._execute_complex_plan(plan)
            yield {"type": "sources", "data": sources}

            # Streaming synthesis
            async for token in self.synthesizer.synthesize_stream(
                query=query,
                evidence_context=context,
                synthesis_strategy=plan.synthesis_strategy,
                plan_reasoning=plan.reasoning,
                max_tokens=2048,
            ):
                yield {"type": "token", "data": token}

            return

        # ── Simple Query Path ─────────────────────────────────
        requested_page = extract_page_number(query)
        is_financial = is_financial_query(query)
        keywords = extract_keywords(query) if settings.hybrid_search_enabled else []

        # Build search query
        if requested_page:
            search_query = query
        elif is_financial and rewrite_query:
            try:
                prompt = FINANCIAL_QUERY_REWRITE_PROMPT.format(query=query)
                search_query = await self.llm.generate(prompt=prompt, max_tokens=150, temperature=0.2)
                search_query = search_query.strip()
            except Exception:
                search_query = query
        elif rewrite_query:
            search_query = await self.rewrite_query(query)
        else:
            search_query = query

        # Retrieve
        initial_top_k = settings.top_k_retrieval
        if is_financial:
            initial_top_k = int(initial_top_k * 1.5)

        filter_conds = {}
        if requested_page:
            filter_conds["page"] = requested_page
        if document_ids:
            filter_conds["document_id"] = document_ids

        retrieved_docs = await self.retrieval.retrieve(
            query=search_query,
            top_k=initial_top_k,
            rerank=settings.enable_reranking,
            filter_conditions=filter_conds if filter_conds else None,
            keywords=keywords if settings.hybrid_search_enabled else None,
        )

        # Yield sources
        sources = []
        for doc in retrieved_docs:
            payload = doc.get("payload", {})
            sources.append({
                "source": payload.get("source", "Unknown"),
                "page": payload.get("page", "N/A"),
                "total_pages": payload.get("total_pages", "N/A"),
                "chunk_index": payload.get("chunk_index", 0),
                "document_id": payload.get("document_id"),
                "score": doc.get("score", 0),
                "rerank_score": doc.get("rerank_score"),
                "content_type": payload.get("content_type", "text"),
            })
        yield {"type": "sources", "data": sources}

        # Graph Retrieval
        graph_context = ""
        try:
            from services.knowledge_graph_service import KnowledgeGraphService
            graph_service = KnowledgeGraphService()
            # Simple entity lookup from query
            related_nodes = graph_service.search_entities(query, document_ids=document_ids)
            graph_triplets = []
            for node in related_nodes:
                triplets = graph_service.get_related_entities(node, depth=1, document_ids=document_ids)
                for t in triplets:
                    graph_triplets.append(f"({t['source']})-[{t['relationship']}]->({t['target']})")
            
            if graph_triplets:
                graph_context = "\nKNOWLEDGE GRAPH CONTEXT (Connected Facts):\n" + "\n".join(set(graph_triplets[:15]))
                logger.info("GraphRAG context added", triplets=len(set(graph_triplets)))
        except Exception as e:
            logger.error("Graph retrieval failed", error=str(e))

        # Context
        context = await self._assemble_rich_context(
            retrieved_docs, max_tokens=settings.max_context_tokens
        )
        
        # Yield context for evaluation
        yield {"type": "context", "data": context}

        # Merge contexts
        if graph_context:
            context = f"{graph_context}\n\nVECTOR SEARCH EVIDENCE:\n{context}"

        # Generate Stream
        if requested_page:
            sys_prompt = RAG_SYSTEM_PROMPT
            prompt = f"Summarize page {requested_page} using this content:\n\n{context}\n\nQuestion: {query}"
        elif is_financial:
            sys_prompt = FINANCIAL_SYSTEM_PROMPT
            prompt = f"Extract all financial data from this context:\n\n{context}\n\nQuestion: {query}"
        else:
            sys_prompt = RAG_SYSTEM_PROMPT
            prompt = f"Combine the Knowledge Graph facts and Vector search evidence to answer accurately.\n\nContext:\n\n{context}\n\nQuestion: {query}"

        if context:
            full_response = ""
            async for token in self.llm.generate_stream(
                prompt=prompt,
                chat_history=chat_history,
                system_prompt=sys_prompt,
                max_tokens=1500 if is_financial else 1024,
                temperature=0.3 if is_financial else 0.7,
            ):
                full_response += token
                yield {"type": "token", "data": token}

            # Guardrails check
            if settings.guardrails_enabled:
                og_result = await self.guardrails.validate_output(full_response)
                if not og_result["safe"]:
                    yield {
                        "type": "token",
                        "data": f"\n\n[Warning: Flagged by safety guardrails: {og_result['reason']}]",
                    }
        else:
            async for token in self.llm.generate_stream(prompt=query, chat_history=chat_history):
                yield {"type": "token", "data": token}

