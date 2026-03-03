"""
SynthesisAgent - Response Synthesis Specialist

Responsible for synthesizing final responses:
- Integrate findings from all prior agents
- Generate comprehensive responses with citations
- Provide confidence scores and reasoning traces
- Ensure factual accuracy through verification results
"""

from typing import Dict, Any, List
import time
import logging
from datetime import datetime

from src.agents.base.base_agent import Agent

logger = logging.getLogger(__name__)


class SynthesisAgent(Agent):
    """
    Synthesizes comprehensive responses from prior agent results.

    Takes outputs from SearchAgent, AnalysisAgent, and VerificationAgent
    to produce final response with:
    1. Comprehensive answer to user query
    2. Citations to source documents
    3. Confidence assessment
    4. Reasoning trace
    5. Identified limitations
    """

    def __init__(self):
        super().__init__(
            name="SynthesisAgent",
            role="Response Synthesis Specialist"
        )
        self.tools = {
            "integrate_findings": None,
            "generate_citations": None,
            "assess_confidence": None,
        }

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute synthesis task.

        Args:
            task: {
                "task": "synthesize_response",
                "query": "original user query",
                "previous_results": {
                    "search_results": {...},
                    "analysis_results": {...},
                    "verification_results": {...}
                }
            }

        Returns:
            {
                "status": "success",
                "response": "comprehensive answer",
                "confidence_score": 0.87,
                "sources": [{"title": "...", "id": "...", "relevance": 0.95}],
                "reasoning_trace": [...],
                "limitations": [...],
                "execution_time": 1.23
            }
        """
        if task.get("task") != "synthesize_response":
            raise ValueError(f"SynthesisAgent only handles 'synthesize_response' task")

        query = task.get("query", "")
        previous_results = task.get("previous_results", {})

        if not query:
            raise ValueError("No query provided for synthesis")

        if not previous_results:
            raise ValueError("No previous results provided for synthesis")

        # Extract results from prior agents
        search_results = previous_results.get("search_results", {})
        analysis_results = previous_results.get("analysis_results", {})
        verification_results = previous_results.get("verification_results", {})

        if not search_results:
            raise ValueError("No search results provided for synthesis")

        logger.info(f"SynthesisAgent: Synthesizing response for query: {query}")

        start_time = time.time()

        try:
            # Import locally to avoid circular dependencies
            from src.services.llm.nvidia_llm_service import NvidiaLLMService

            llm_service = NvidiaLLMService()

            # Prepare synthesis context
            synthesis_context = self._prepare_synthesis_context(
                query,
                search_results,
                analysis_results,
                verification_results
            )

            # Create synthesis prompt
            prompt = self._create_synthesis_prompt(query, synthesis_context)

            # Call LLM for synthesis
            synthesis_response = await llm_service.generate(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.6  # Balanced for coherence and accuracy
            )

            # Parse synthesis results
            synthesis_data = self._parse_synthesis(synthesis_response)

            # Extract sources from search results
            sources = self._extract_sources(search_results)

            # Generate reasoning trace
            reasoning_trace = self._generate_reasoning_trace(
                query,
                search_results,
                analysis_results,
                verification_results
            )

            duration = time.time() - start_time

            # Calculate overall confidence
            confidence_score = self._calculate_confidence(
                verification_results,
                synthesis_data
            )

            # Store in memory
            await self.observe({
                "type": "synthesis_execution",
                "query": query,
                "confidence_score": confidence_score,
                "sources_count": len(sources),
                "duration": duration,
                "importance": 0.9,  # High importance for final synthesis
            })

            # Record execution
            self.record_execution(
                task_name="synthesize_response",
                status="success",
                duration=duration,
                metadata={
                    "query": query,
                    "sources_count": len(sources),
                    "confidence_score": confidence_score
                }
            )

            # Update performance
            self.update_performance(
                success=True,
                quality_score=confidence_score,
                response_time=duration
            )

            return {
                "status": "success",
                "response": synthesis_data.get("response", ""),
                "confidence_score": confidence_score,
                "sources": sources,
                "reasoning_trace": reasoning_trace,
                "limitations": synthesis_data.get("limitations", []),
                "execution_time": round(duration, 3),
                "metadata": {
                    "synthesis_method": "llm_integrated",
                    "sources_used": len(sources),
                    "verification_included": bool(verification_results),
                    "timestamp": datetime.now().isoformat(),
                }
            }

        except Exception as exc:
            logger.error(f"SynthesisAgent failed: {exc}")

            duration = time.time() - start_time

            # Record failure
            self.record_execution(
                task_name="synthesize_response",
                status="error",
                duration=duration,
                metadata={"error": str(exc)}
            )

            # Update performance
            self.update_performance(
                success=False,
                quality_score=0.0,
                response_time=duration
            )

            raise

    async def think(
        self,
        query: str,
        search_results: Dict,
        analysis_results: Dict,
        verification_results: Dict
    ) -> Dict[str, Any]:
        """
        Determine synthesis strategy.

        Args:
            query: User query
            search_results: Results from SearchAgent
            analysis_results: Results from AnalysisAgent
            verification_results: Results from VerificationAgent

        Returns:
            Synthesis strategy dict
        """
        strategy = {
            "integrate_all_sources": True,
            "prioritize_verified": True,
            "include_reasoning": True,
            "cite_sources": True,
            "depth_level": "comprehensive",
            "confidence_threshold": 0.6,
        }

        # Adjust based on verification confidence
        if verification_results and verification_results.get("verification"):
            verif_confidence = verification_results.get("verification", {}).get(
                "confidence_score", 0.5
            )
            if verif_confidence < 0.5:
                strategy["confidence_threshold"] = 0.5
                strategy["depth_level"] = "cautious"

        # Adjust based on available data
        if not analysis_results:
            strategy["depth_level"] = "shallow"

        return strategy

    def _prepare_synthesis_context(
        self,
        query: str,
        search_results: Dict,
        analysis_results: Dict,
        verification_results: Dict
    ) -> str:
        """
        Prepare comprehensive context for synthesis.

        Args:
            query: User query
            search_results: Search results dict
            analysis_results: Analysis results dict
            verification_results: Verification results dict

        Returns:
            Formatted context string
        """
        context_parts = [
            "=== USER QUERY ===",
            query,
            "",
        ]

        # Add search context
        if search_results and search_results.get("documents"):
            context_parts.append("=== SEARCH RESULTS ===")
            for i, doc in enumerate(search_results["documents"][:3], 1):
                content = doc.get("content", "")[:300]
                score = doc.get("score", 0.0)
                context_parts.append(f"[Source {i} (relevance: {score:.2f})]")
                context_parts.append(content)
                context_parts.append("")

        # Add analysis context
        if analysis_results and analysis_results.get("key_findings"):
            context_parts.append("=== KEY FINDINGS ===")
            for finding in analysis_results.get("key_findings", [])[:5]:
                context_parts.append(f"- {finding}")
            context_parts.append("")

        # Add verification context
        if verification_results and verification_results.get("verification"):
            context_parts.append("=== VERIFICATION STATUS ===")
            verif = verification_results.get("verification", {})
            context_parts.append(
                f"Verified: {verif.get('verified', False)}"
            )
            context_parts.append(
                f"Confidence: {verif.get('confidence_score', 0.5):.2f}"
            )
            if verif.get("issues"):
                context_parts.append("Issues:")
                for issue in verif["issues"][:3]:
                    context_parts.append(f"  - {issue}")
            context_parts.append("")

        return "\n".join(context_parts)

    def _create_synthesis_prompt(self, query: str, context: str) -> str:
        """
        Create synthesis prompt for LLM.

        Args:
            query: User query
            context: Prepared synthesis context

        Returns:
            Prompt string
        """
        return f"""You are a response synthesis specialist. Using the provided context,
generate a comprehensive response to the user's query.

{context}

Please provide a well-structured response that:
1. Directly answers the user query
2. Cites specific sources for claims
3. Acknowledges confidence levels
4. Identifies any limitations or uncertainties
5. Summarizes key points clearly

Format your response as JSON with keys:
- "response": the comprehensive answer
- "limitations": array of any limitations or uncertainties
- "summary": one sentence summary

Ensure the response is factual and well-supported by the provided sources."""

    def _parse_synthesis(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM synthesis response.

        Args:
            response: Raw LLM response

        Returns:
            Structured synthesis dict
        """
        try:
            import json
            # Look for JSON in response
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback parsing
        return {
            "response": response[:500],
            "limitations": ["Response not fully parsed"],
            "summary": response[:100],
        }

    def _extract_sources(self, search_results: Dict) -> List[Dict[str, Any]]:
        """
        Extract and format sources from search results.

        Args:
            search_results: Search results dict

        Returns:
            List of formatted source dicts
        """
        sources = []

        if search_results and search_results.get("documents"):
            for doc in search_results["documents"][:5]:
                sources.append({
                    "title": doc.get("title", doc.get("id", "Unknown")),
                    "id": doc.get("id", ""),
                    "relevance": doc.get("score", 0.0),
                    "url": doc.get("url", ""),
                })

        return sources

    def _generate_reasoning_trace(
        self,
        query: str,
        search_results: Dict,
        analysis_results: Dict,
        verification_results: Dict
    ) -> List[str]:
        """
        Generate reasoning trace showing agent workflow.

        Args:
            query: User query
            search_results: Search results
            analysis_results: Analysis results
            verification_results: Verification results

        Returns:
            List of reasoning trace steps
        """
        trace = [
            f"Query received: {query[:80]}..."
        ]

        if search_results:
            doc_count = len(search_results.get("documents", []))
            trace.append(f"SearchAgent found {doc_count} relevant documents")

        if analysis_results:
            findings_count = len(analysis_results.get("key_findings", []))
            trace.append(f"AnalysisAgent extracted {findings_count} key findings")

        if verification_results:
            verified = verification_results.get("verification", {}).get("verified", False)
            conf = verification_results.get("verification", {}).get("confidence_score", 0.0)
            status = "verified" if verified else "unverified"
            trace.append(f"VerificationAgent: findings {status} (confidence: {conf:.2f})")

        trace.append("SynthesisAgent: generating comprehensive response")

        return trace

    def _calculate_confidence(
        self,
        verification_results: Dict,
        synthesis_data: Dict
    ) -> float:
        """
        Calculate overall confidence score for synthesis.

        Args:
            verification_results: Verification agent results
            synthesis_data: Parsed synthesis data

        Returns:
            Confidence score (0-1)
        """
        base_confidence = 0.7

        # Adjust based on verification if available
        if verification_results and verification_results.get("verification"):
            verif_conf = verification_results.get("verification", {}).get(
                "confidence_score", 0.5
            )
            base_confidence = (base_confidence + verif_conf) / 2

        # If synthesis indicates limitations, lower confidence
        if synthesis_data.get("limitations"):
            base_confidence *= 0.9

        return round(base_confidence, 3)

    def get_synthesis_stats(self) -> Dict[str, Any]:
        """Return synthesis-specific statistics."""
        history = self.get_execution_history()
        successful = sum(1 for h in history if h["status"] == "success")

        # Calculate avg confidence from memory
        avg_confidence = 0.0
        if self.memory and self.memory.short_term:
            confidences = [
                m.get("confidence_score", 0.5)
                for m in self.memory.short_term
                if "confidence_score" in m
            ]
            if confidences:
                avg_confidence = sum(confidences) / len(confidences)

        return {
            "total_syntheses": self.performance_metrics["total_tasks"],
            "successful_syntheses": successful,
            "failed_syntheses": self.performance_metrics["failed_tasks"],
            "avg_synthesis_time": self.performance_metrics["avg_response_time"],
            "avg_confidence_score": round(avg_confidence, 3),
            "success_rate": self.performance_metrics["success_rate"],
        }
