"""
API routes for multi-agent RAG system.

Endpoints for:
- Query the complete RAG pipeline
- Get agent statistics
- Monitor workflow execution
- Stream responses in real-time
"""

from fastapi import APIRouter, HTTPException, Query, Path
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from src.agents.coordinator.coordinator_agent import CoordinatorAgent

logger = logging.getLogger(__name__)


class _LazyCoordinator:
    """Instantiate the multi-agent coordinator on first use (keeps app startup cheap)."""

    _instance = None

    def __getattr__(self, item):
        if _LazyCoordinator._instance is None:
            _LazyCoordinator._instance = CoordinatorAgent()
        return getattr(_LazyCoordinator._instance, item)


coordinator = _LazyCoordinator()

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ── Request/Response Models ────────────────────────────────────────────────────

class QueryRequest(BaseModel):
    """Request to answer a query using the multi-agent RAG pipeline."""
    query: str = Field(..., description="User question or query", min_length=1, max_length=1000)
    top_k: int = Field(default=12, description="Number of top documents to retrieve", ge=1, le=50)

    class Config:
        json_schema_extra = {
            "example": {
                "query": "What are the latest developments in AI?",
                "top_k": 12
            }
        }


class SourceDocument(BaseModel):
    """Source document with relevance information."""
    id: str = Field(..., description="Document ID")
    title: str = Field(..., description="Document title")
    relevance: float = Field(..., description="Relevance score (0-1)", ge=0, le=1)
    url: Optional[str] = Field(None, description="Document URL")


class PipelineStepResult(BaseModel):
    """Result from a single pipeline step."""
    documents_found: Optional[int] = Field(None, description="Number of documents found (search)")
    findings_count: Optional[int] = Field(None, description="Number of findings extracted (analysis)")
    verified: Optional[bool] = Field(None, description="Whether findings are verified (verification)")
    confidence: Optional[float] = Field(None, description="Confidence score (verification)")
    execution_time: float = Field(..., description="Time taken for this step (seconds)")


class QueryResponse(BaseModel):
    """Response from the multi-agent RAG pipeline."""
    status: str = Field(..., description="Success or error status")
    query: str = Field(..., description="Original query")
    response: str = Field(..., description="Final answer from synthesis agent")
    confidence_score: float = Field(..., description="Overall confidence score (0-1)", ge=0, le=1)
    sources: List[SourceDocument] = Field(..., description="Source documents cited")
    reasoning_trace: List[str] = Field(..., description="Step-by-step reasoning trace")
    limitations: List[str] = Field(..., description="Identified limitations or caveats")

    pipeline_results: Dict[str, PipelineStepResult] = Field(
        ...,
        description="Results from each pipeline step (search, analysis, verification, synthesis)"
    )

    execution_time: float = Field(..., description="Total execution time (seconds)")

    metadata: Dict[str, Any] = Field(..., description="Additional metadata")

    class Config:
        json_schema_extra = {
            "example": {
                "status": "success",
                "query": "What is AI?",
                "response": "Artificial Intelligence (AI) is the simulation of human intelligence...",
                "confidence_score": 0.87,
                "sources": [
                    {
                        "id": "doc_1",
                        "title": "Introduction to AI",
                        "relevance": 0.95,
                        "url": "https://example.com/ai-intro"
                    }
                ],
                "reasoning_trace": [
                    "Retrieved 12 documents about AI",
                    "Extracted 5 key findings",
                    "Verified findings against sources",
                    "Generated comprehensive response"
                ],
                "limitations": ["Limited to training data from 2024"],
                "pipeline_results": {
                    "search": {
                        "documents_found": 12,
                        "execution_time": 1.2
                    }
                },
                "execution_time": 5.34,
                "metadata": {
                    "pipeline": "search->analysis->verification->synthesis",
                    "agents_used": 4
                }
            }
        }


class AgentStats(BaseModel):
    """Statistics for a single agent."""
    total_tasks: int = Field(..., description="Total tasks executed")
    successful_tasks: int = Field(..., description="Successfully completed tasks")
    success_rate: float = Field(..., description="Success rate (0-1)")


class PipelineStats(BaseModel):
    """Statistics for the complete pipeline."""
    total_workflows: int = Field(..., description="Total workflows executed")
    successful_workflows: int = Field(..., description="Successfully completed workflows")
    failed_workflows: int = Field(..., description="Failed workflows")
    avg_workflow_time: float = Field(..., description="Average workflow execution time (seconds)")
    success_rate: float = Field(..., description="Overall success rate (0-1)")
    agent_performance: Dict[str, AgentStats] = Field(..., description="Performance of each agent")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Service status")
    agents_ready: bool = Field(..., description="Whether all agents are initialized")
    timestamp: str = Field(..., description="Timestamp of check")


# ── API Endpoints ──────────────────────────────────────────────────────────────

@router.post(
    "/query",
    response_model=QueryResponse,
    summary="Query the multi-agent RAG system",
    description="Submit a query to the multi-agent RAG pipeline. The system will search for relevant documents, analyze them, verify the findings, and synthesize a comprehensive response.",
    responses={
        200: {"description": "Successful query execution"},
        400: {"description": "Invalid request (missing query, invalid parameters)"},
        500: {"description": "Server error during pipeline execution"}
    }
)
async def query_rag_system(request: QueryRequest) -> QueryResponse:
    """
    Query the complete RAG pipeline.

    The pipeline executes the following steps:
    1. **SearchAgent** - Retrieves relevant documents from vector store
    2. **AnalysisAgent** - Extracts key findings and patterns from documents
    3. **VerificationAgent** - Verifies findings against source documents
    4. **SynthesisAgent** - Generates final response with citations

    Args:
        request: Query request with user question and parameters

    Returns:
        QueryResponse with comprehensive answer and pipeline metadata

    Raises:
        HTTPException: If pipeline execution fails
    """
    try:
        logger.info(f"Received query: {request.query[:100]}...")

        # Execute the pipeline
        result = await coordinator.execute({
            "task": "answer_query",
            "query": request.query,
            "top_k": request.top_k,
        })

        if result["status"] != "success":
            logger.error(f"Pipeline failed: {result}")
            raise HTTPException(
                status_code=500,
                detail=f"Pipeline execution failed: {result.get('error', 'Unknown error')}"
            )

        # Transform result to response model
        response = QueryResponse(
            status=result["status"],
            query=result["query"],
            response=result["response"],
            confidence_score=result["confidence_score"],
            sources=result["sources"],
            reasoning_trace=result["reasoning_trace"],
            limitations=result["limitations"],
            pipeline_results={
                step: PipelineStepResult(**result["pipeline_results"][step])
                for step in result["pipeline_results"]
            },
            execution_time=result["execution_time"],
            metadata=result["metadata"]
        )

        logger.info(f"Query completed successfully in {result['execution_time']:.2f}s")
        return response

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Query execution failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Query execution failed: {str(exc)}"
        )


@router.get(
    "/statistics",
    response_model=PipelineStats,
    summary="Get pipeline statistics",
    description="Retrieve statistics about the multi-agent pipeline performance, including success rates and execution times for each agent."
)
async def get_statistics() -> PipelineStats:
    """
    Get statistics about the multi-agent pipeline.

    Returns:
        PipelineStats with performance metrics for the coordinator and all sub-agents
    """
    try:
        stats = coordinator.get_pipeline_stats()

        response = PipelineStats(
            total_workflows=stats["total_workflows"],
            successful_workflows=stats["successful_workflows"],
            failed_workflows=stats["failed_workflows"],
            avg_workflow_time=stats["avg_workflow_time"],
            success_rate=stats["success_rate"],
            agent_performance={
                agent_name: AgentStats(**agent_stats)
                for agent_name, agent_stats in stats["agent_performance"].items()
            }
        )

        return response

    except Exception as exc:
        logger.error(f"Failed to retrieve statistics: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve statistics: {str(exc)}"
        )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check the health status of the multi-agent system."
)
async def health_check() -> HealthResponse:
    """
    Check the health status of the multi-agent system.

    Returns:
        HealthResponse indicating service status and agent readiness
    """
    try:
        from datetime import datetime

        # Check if agents are initialized
        agents_ready = (
            coordinator.search_agent is not None and
            coordinator.analysis_agent is not None and
            coordinator.verification_agent is not None and
            coordinator.synthesis_agent is not None
        )

        return HealthResponse(
            status="healthy" if agents_ready else "degraded",
            agents_ready=agents_ready,
            timestamp=datetime.now().isoformat()
        )

    except Exception as exc:
        logger.error(f"Health check failed: {exc}", exc_info=True)
        return HealthResponse(
            status="unhealthy",
            agents_ready=False,
            timestamp="unknown"
        )


@router.get(
    "/agents/list",
    summary="List available agents",
    description="Get information about all agents in the system."
)
async def list_agents() -> Dict[str, Dict[str, Any]]:
    """
    Get information about all agents in the system.

    Returns:
        Dictionary with information about each agent
    """
    try:
        return {
            "coordinator": {
                "name": coordinator.name,
                "role": coordinator.role,
                "type": "orchestrator"
            },
            "search": {
                "name": coordinator.search_agent.name,
                "role": coordinator.search_agent.role,
                "type": "specialized"
            },
            "analysis": {
                "name": coordinator.analysis_agent.name,
                "role": coordinator.analysis_agent.role,
                "type": "specialized"
            },
            "verification": {
                "name": coordinator.verification_agent.name,
                "role": coordinator.verification_agent.role,
                "type": "specialized"
            },
            "synthesis": {
                "name": coordinator.synthesis_agent.name,
                "role": coordinator.synthesis_agent.role,
                "type": "specialized"
            }
        }

    except Exception as exc:
        logger.error(f"Failed to list agents: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list agents: {str(exc)}"
        )


@router.get(
    "/agents/{agent_name}/stats",
    summary="Get agent statistics",
    description="Get performance statistics for a specific agent."
)
async def get_agent_stats(agent_name: str = Path(..., description="Name of the agent (search, analysis, verification, synthesis)")) -> Dict[str, Any]:
    """
    Get performance statistics for a specific agent.

    Args:
        agent_name: Name of the agent (search, analysis, verification, synthesis)

    Returns:
        Agent performance statistics
    """
    try:
        agent_map = {
            "search": coordinator.search_agent,
            "analysis": coordinator.analysis_agent,
            "verification": coordinator.verification_agent,
            "synthesis": coordinator.synthesis_agent,
        }

        if agent_name not in agent_map:
            raise HTTPException(
                status_code=404,
                detail=f"Agent '{agent_name}' not found. Available: {list(agent_map.keys())}"
            )

        agent = agent_map[agent_name]
        metrics = agent.performance_metrics

        return {
            "agent": agent_name,
            "name": agent.name,
            "role": agent.role,
            "performance": {
                "total_tasks": metrics["total_tasks"],
                "successful_tasks": metrics["successful_tasks"],
                "failed_tasks": metrics["failed_tasks"],
                "success_rate": metrics["success_rate"],
                "avg_response_time": metrics["avg_response_time"],
                "total_response_time": metrics["total_response_time"],
                "avg_quality_score": metrics["avg_quality_score"]
            }
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get agent stats: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get agent stats: {str(exc)}"
        )
