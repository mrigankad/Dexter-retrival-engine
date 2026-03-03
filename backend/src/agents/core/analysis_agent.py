"""
AnalysisAgent - Data Analysis Specialist

Responsible for analyzing documents and extracting:
- Key findings
- Important patterns
- Data insights
- Relationships between information
"""

from typing import Dict, Any, List
import time
import logging
from datetime import datetime

from src.agents.base.base_agent import Agent

logger = logging.getLogger(__name__)


class AnalysisAgent(Agent):
    """
    Analyzes documents using LLM to extract insights.

    Takes documents from SearchAgent and produces structured analysis:
    1. Identify key findings
    2. Extract patterns
    3. Summarize insights
    4. Determine relationships
    """

    def __init__(self):
        super().__init__(
            name="AnalysisAgent",
            role="Data Analysis Specialist"
        )
        self.tools = {
            "extract_findings": None,
            "identify_patterns": None,
            "summarize_insights": None,
        }

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute analysis task.

        Args:
            task: {
                "task": "analyze_documents",
                "previous_results": {
                    "documents": [...],
                    "scores": [...]
                },
                "query": "original query",
                ...
            }

        Returns:
            {
                "status": "success",
                "analysis": {...},
                "key_findings": ["Finding 1", "Finding 2"],
                "patterns": ["Pattern 1", "Pattern 2"],
                "insights": [...],
                "execution_time": 1.23
            }
        """
        if task.get("task") != "analyze_documents":
            raise ValueError(f"AnalysisAgent only handles 'analyze_documents' task")

        previous_results = task.get("previous_results", {})
        documents = previous_results.get("documents", [])
        query = task.get("query", "")

        if not documents:
            raise ValueError("No documents provided for analysis")

        logger.info(
            f"AnalysisAgent: Analyzing {len(documents)} documents"
        )

        start_time = time.time()

        try:
            # Import locally to avoid circular dependencies
            from src.services.llm.nvidia_llm_service import NvidiaLLMService

            llm_service = NvidiaLLMService()

            # Prepare documents for analysis
            doc_text = self._prepare_documents(documents)

            # Create analysis prompt
            prompt = self._create_analysis_prompt(doc_text, query)

            # Call LLM for analysis
            analysis_response = await llm_service.generate(
                prompt=prompt,
                max_tokens=800,
                temperature=0.7
            )

            # Parse structured results
            analysis_data = self._parse_analysis(analysis_response)

            duration = time.time() - start_time

            # Store in memory
            await self.observe({
                "type": "analysis_execution",
                "query": query,
                "documents_analyzed": len(documents),
                "findings_count": len(analysis_data.get("key_findings", [])),
                "duration": duration,
                "importance": 0.7,
            })

            # Record execution
            self.record_execution(
                task_name="analyze_documents",
                status="success",
                duration=duration,
                metadata={
                    "documents_count": len(documents),
                    "query": query
                }
            )

            # Update performance
            self.update_performance(
                success=True,
                quality_score=0.85,
                response_time=duration
            )

            return {
                "status": "success",
                "analysis": analysis_data,
                "key_findings": analysis_data.get("key_findings", []),
                "patterns": analysis_data.get("patterns", []),
                "insights": analysis_data.get("insights", []),
                "summary": analysis_data.get("summary", ""),
                "execution_time": round(duration, 3),
                "metadata": {
                    "documents_analyzed": len(documents),
                    "analysis_method": "llm_based",
                    "timestamp": datetime.now().isoformat(),
                }
            }

        except Exception as exc:
            logger.error(f"AnalysisAgent failed: {exc}")

            duration = time.time() - start_time

            # Record failure
            self.record_execution(
                task_name="analyze_documents",
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

    async def think(self, documents: List[Dict], query: str) -> Dict[str, Any]:
        """
        Determine analysis strategy for documents.

        Args:
            documents: List of document dicts
            query: Original user query

        Returns:
            Analysis strategy dict
        """
        strategy = {
            "extract_key_findings": True,
            "identify_patterns": True,
            "extract_relationships": True,
            "summarize_insights": True,
            "depth_level": "standard",
            "max_findings": 5,
        }

        # Adjust strategy based on document count
        if len(documents) > 10:
            strategy["depth_level"] = "shallow"
            strategy["max_findings"] = 3
        elif len(documents) < 3:
            strategy["depth_level"] = "deep"
            strategy["max_findings"] = 10

        return strategy

    def _prepare_documents(self, documents: List[Dict]) -> str:
        """
        Prepare documents for LLM analysis.

        Args:
            documents: List of document dicts

        Returns:
            Formatted text for LLM
        """
        text_parts = []

        for i, doc in enumerate(documents, 1):
            content = doc.get("content", "")
            score = doc.get("score", 0.0)

            text_parts.append(f"[Document {i} (relevance: {score:.2f})]")
            text_parts.append(content[:500])  # Limit to first 500 chars
            text_parts.append("")

        return "\n".join(text_parts)

    def _create_analysis_prompt(self, doc_text: str, query: str) -> str:
        """
        Create analysis prompt for LLM.

        Args:
            doc_text: Prepared document text
            query: Original query

        Returns:
            Prompt string
        """
        return f"""You are a data analysis specialist. Analyze the following documents
related to the query: "{query}"

Documents:
{doc_text}

Provide a structured analysis with:
1. Key Findings (2-5 bullet points of the most important information)
2. Patterns (recurring themes or relationships)
3. Insights (deeper interpretations)
4. Summary (1-2 sentences overall summary)

Format your response as JSON with keys: "key_findings", "patterns", "insights", "summary"
"""

    def _parse_analysis(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM analysis response.

        Args:
            response: Raw LLM response

        Returns:
            Structured analysis dict
        """
        # Try to parse as JSON
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

        # Fallback: simple parsing
        lines = response.split("\n")
        return {
            "key_findings": [l.strip("- ") for l in lines if l.strip().startswith("-")][:5],
            "patterns": [],
            "insights": [response[:100]],
            "summary": response[:200],
        }

    def get_analysis_stats(self) -> Dict[str, Any]:
        """Return analysis-specific statistics."""
        history = self.get_execution_history()
        successful = sum(1 for h in history if h["status"] == "success")

        return {
            "total_analyses": self.performance_metrics["total_tasks"],
            "successful_analyses": successful,
            "failed_analyses": self.performance_metrics["failed_tasks"],
            "avg_analysis_time": self.performance_metrics["avg_response_time"],
            "success_rate": self.performance_metrics["success_rate"],
        }
