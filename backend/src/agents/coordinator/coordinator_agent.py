"""
CoordinatorAgent - Workflow Orchestration Specialist

Responsible for orchestrating the multi-agent workflow:
- Route tasks to appropriate specialized agents
- Manage inter-agent communication
- Handle workflow execution and error recovery
- Aggregate and present final results
"""

from typing import Dict, Any, List
import time
import logging
from datetime import datetime

from src.agents.base.base_agent import Agent
from src.agents.core.search_agent import SearchAgent
from src.agents.core.analysis_agent import AnalysisAgent
from src.agents.core.verification_agent import VerificationAgent
from src.agents.core.synthesis_agent import SynthesisAgent

logger = logging.getLogger(__name__)


class CoordinatorAgent(Agent):
    """
    Orchestrates the multi-agent RAG workflow.

    Manages the complete pipeline:
    1. SearchAgent - Find relevant documents
    2. AnalysisAgent - Extract insights from documents
    3. VerificationAgent - Verify findings against sources
    4. SynthesisAgent - Generate final response with citations

    Handles:
    - Workflow orchestration and sequencing
    - Inter-agent communication and result passing
    - Error handling and recovery
    - Performance monitoring across pipeline
    """

    def __init__(self):
        super().__init__(
            name="CoordinatorAgent",
            role="Workflow Orchestration Specialist"
        )

        # Initialize specialized agents
        self.search_agent = SearchAgent()
        self.analysis_agent = AnalysisAgent()
        self.verification_agent = VerificationAgent()
        self.synthesis_agent = SynthesisAgent()

        self.agents = {
            "search": self.search_agent,
            "analysis": self.analysis_agent,
            "verification": self.verification_agent,
            "synthesis": self.synthesis_agent,
        }

        self.tools = {
            "route_to_agents": None,
            "manage_workflow": None,
            "aggregate_results": None,
        }

    async def initialize(self):
        """Initialize all child agents."""
        await self.initialize_memory()
        for agent in self.agents.values():
            await agent.initialize_memory()

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute complete RAG workflow.

        Args:
            task: {
                "task": "answer_query",
                "query": "user question",
                "top_k": 12,  # optional
                ...
            }

        Returns:
            {
                "status": "success",
                "query": "original query",
                "response": "final answer",
                "confidence_score": 0.87,
                "sources": [...],
                "pipeline_results": {
                    "search": {...},
                    "analysis": {...},
                    "verification": {...},
                    "synthesis": {...}
                },
                "execution_time": 12.34
            }
        """
        if task.get("task") != "answer_query":
            raise ValueError(f"CoordinatorAgent only handles 'answer_query' task")

        query = task.get("query", "")
        if not query:
            raise ValueError("No query provided")

        logger.info(f"CoordinatorAgent: Starting workflow for query: {query}")

        start_time = time.time()
        pipeline_results = {}

        try:
            # Step 1: Search
            logger.info("Step 1/4: SearchAgent - Retrieving documents")
            search_result = await self.search_agent.execute({
                "task": "retrieve_documents",
                "query": query,
                "top_k": task.get("top_k", 12),
            })
            pipeline_results["search"] = search_result

            if search_result["status"] != "success":
                raise RuntimeError(f"Search failed: {search_result}")

            # Step 2: Analysis
            logger.info("Step 2/4: AnalysisAgent - Analyzing documents")
            analysis_result = await self.analysis_agent.execute({
                "task": "analyze_documents",
                "query": query,
                "previous_results": {
                    "documents": search_result.get("documents", []),
                    "scores": search_result.get("scores", []),
                },
            })
            pipeline_results["analysis"] = analysis_result

            if analysis_result["status"] != "success":
                raise RuntimeError(f"Analysis failed: {analysis_result}")

            # Step 3: Verification
            logger.info("Step 3/4: VerificationAgent - Verifying findings")
            verification_result = await self.verification_agent.execute({
                "task": "verify_findings",
                "previous_results": {
                    "key_findings": analysis_result.get("key_findings", []),
                    "documents": search_result.get("documents", []),
                },
            })
            pipeline_results["verification"] = verification_result

            if verification_result["status"] != "success":
                raise RuntimeError(f"Verification failed: {verification_result}")

            # Step 4: Synthesis
            logger.info("Step 4/4: SynthesisAgent - Synthesizing response")
            synthesis_result = await self.synthesis_agent.execute({
                "task": "synthesize_response",
                "query": query,
                "previous_results": {
                    "search_results": {
                        "documents": search_result.get("documents", []),
                    },
                    "analysis_results": {
                        "key_findings": analysis_result.get("key_findings", []),
                        "patterns": analysis_result.get("patterns", []),
                        "insights": analysis_result.get("insights", []),
                    },
                    "verification_results": {
                        "verification": verification_result.get("verification", {}),
                    },
                },
            })
            pipeline_results["synthesis"] = synthesis_result

            if synthesis_result["status"] != "success":
                raise RuntimeError(f"Synthesis failed: {synthesis_result}")

            duration = time.time() - start_time

            # Store in memory
            await self.observe({
                "type": "coordination_execution",
                "query": query,
                "confidence_score": synthesis_result.get("confidence_score", 0.5),
                "duration": duration,
                "importance": 0.95,  # Very high importance for complete workflows
            })

            # Record execution
            self.record_execution(
                task_name="answer_query",
                status="success",
                duration=duration,
                metadata={
                    "query": query,
                    "sources_count": len(search_result.get("documents", [])),
                    "findings_count": len(analysis_result.get("key_findings", [])),
                }
            )

            # Update performance
            self.update_performance(
                success=True,
                quality_score=synthesis_result.get("confidence_score", 0.5),
                response_time=duration
            )

            # Aggregate sub-agent performance
            self._aggregate_agent_performance()

            return {
                "status": "success",
                "query": query,
                "response": synthesis_result.get("response", ""),
                "confidence_score": synthesis_result.get("confidence_score", 0.5),
                "sources": synthesis_result.get("sources", []),
                "reasoning_trace": synthesis_result.get("reasoning_trace", []),
                "limitations": synthesis_result.get("limitations", []),
                "pipeline_results": {
                    "search": {
                        "documents_found": len(search_result.get("documents", [])),
                        "execution_time": search_result.get("execution_time", 0),
                    },
                    "analysis": {
                        "findings_count": len(analysis_result.get("key_findings", [])),
                        "execution_time": analysis_result.get("execution_time", 0),
                    },
                    "verification": {
                        "verified": verification_result.get("verified", False),
                        "confidence": verification_result.get("confidence_score", 0),
                        "execution_time": verification_result.get("execution_time", 0),
                    },
                    "synthesis": {
                        "execution_time": synthesis_result.get("execution_time", 0),
                    },
                },
                "execution_time": round(duration, 3),
                "metadata": {
                    "pipeline": "search->analysis->verification->synthesis",
                    "timestamp": datetime.now().isoformat(),
                    "agents_used": 4,
                }
            }

        except Exception as exc:
            logger.error(f"CoordinatorAgent workflow failed: {exc}")

            duration = time.time() - start_time

            # Record failure
            self.record_execution(
                task_name="answer_query",
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

    async def think(self, query: str) -> Dict[str, Any]:
        """
        Determine optimal workflow strategy.

        Args:
            query: User query

        Returns:
            Workflow strategy dict
        """
        strategy = {
            "execute_full_pipeline": True,
            "agents_to_use": ["search", "analysis", "verification", "synthesis"],
            "fallback_strategy": "return_search_results",
            "error_recovery": "skip_failed_step",
        }

        # Adjust based on query characteristics
        query_length = len(query.split())
        if query_length < 3:
            strategy["error_recovery"] = "abort_pipeline"

        return strategy

    def _aggregate_agent_performance(self):
        """Aggregate performance metrics from all sub-agents."""
        total_time = 0
        total_tasks = 0
        successful_tasks = 0

        for agent in self.agents.values():
            metrics = agent.performance_metrics
            total_time += metrics.get("total_response_time", 0)
            total_tasks += metrics.get("total_tasks", 0)
            successful_tasks += metrics.get("successful_tasks", 0)

        if total_tasks > 0:
            logger.info(
                f"Pipeline performance: {successful_tasks}/{total_tasks} tasks successful, "
                f"avg time: {total_time/total_tasks:.2f}s"
            )

    def get_pipeline_stats(self) -> Dict[str, Any]:
        """Return pipeline-level statistics."""
        history = self.get_execution_history()
        successful = sum(1 for h in history if h["status"] == "success")

        agent_stats = {}
        for name, agent in self.agents.items():
            agent_stats[name] = agent.get_execution_history()

        return {
            "total_workflows": self.performance_metrics["total_tasks"],
            "successful_workflows": successful,
            "failed_workflows": self.performance_metrics["failed_tasks"],
            "avg_workflow_time": self.performance_metrics["avg_response_time"],
            "success_rate": self.performance_metrics["success_rate"],
            "agent_performance": {
                name: {
                    "total_tasks": agent.performance_metrics["total_tasks"],
                    "successful_tasks": agent.performance_metrics["successful_tasks"],
                    "success_rate": agent.performance_metrics["success_rate"],
                }
                for name, agent in self.agents.items()
            }
        }
