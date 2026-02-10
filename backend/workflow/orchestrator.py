"""
Workflow Orchestrator - Main entry point for query processing.

Coordinates routing, pipeline execution, and response handling.
"""

from typing import AsyncGenerator, Dict, List, Optional, Any

from core.config import settings
from core.logger import get_logger, log_timing
from services.nvidia_llm_service import NvidiaLLMService
from services.memory_service import MemoryService
from .query_router import QueryRouter, RouteType
from .rag_pipeline import RAGPipeline
from .tool_pipeline import ToolPipeline

logger = get_logger(__name__)


class WorkflowOrchestrator:
    """Main orchestrator for query processing workflows."""
    
    def __init__(self):
        self.llm = NvidiaLLMService()
        self.router = QueryRouter(self.llm)
        self.rag_pipeline = RAGPipeline(llm_service=self.llm)
        self.tool_pipeline = ToolPipeline()
        self.memory = MemoryService()
    
    @log_timing("orchestrator_execute")
    async def execute(
        self,
        query: str,
        use_rag: bool = True,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
        document_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Execute workflow for a query (non-streaming).
        
        Args:
            query: User query
            use_rag: Whether to enable RAG retrieval
            session_id: Session ID for history
            user_id: User ID for personalization
            chat_history: Previous messages
            document_ids: List of document IDs to scope search to
            
        Returns:
            Dict with response, route, sources, and metadata
        """
        # Get chat history if session provided
        if session_id and not chat_history:
            chat_history = await self.memory.get_context_messages(session_id)
        
        # Route the query
        if use_rag:
            route, confidence, reason = await self.router.route(query)
        else:
            route = RouteType.DIRECT_LLM
            confidence = 1.0
            reason = "RAG disabled"
        
        logger.info(
            "Query routed",
            route=route.value,
            confidence=confidence,
            session_id=session_id,
        )
        
        # Execute appropriate pipeline
        if route == RouteType.RAG_PIPELINE:
            result = await self.rag_pipeline.execute(query, chat_history, document_ids=document_ids)
            response = result["response"]
            sources = result.get("sources", [])
        else:
            # Direct LLM response
            response = await self.llm.generate(
                prompt=query,
                max_tokens=1024,
            )
            sources = []
        
        # Store in memory
        if session_id:
            await self.memory.add_message(session_id, "user", query, user_id)
            await self.memory.add_message(session_id, "assistant", response, user_id)
        
        return {
            "response": response,
            "route": route.value,
            "confidence": confidence,
            "sources": sources,
            "usage": {},  # TODO: Track token usage
        }
    
    async def execute_stream(
        self,
        query: str,
        use_rag: bool = True,
        session_id: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
        user_id: Optional[str] = None,
        document_ids: Optional[List[str]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Execute workflow with streaming response and trigger Ragas evaluation.
        """
        # Store user message
        if session_id:
            await self.memory.add_message(session_id, "user", query, user_id)

        # Route the query (quick decision)
        if use_rag:
            route = await self.router.route_simple(query)
        else:
            route = RouteType.DIRECT_LLM
        
        logger.info("Streaming query", route=route.value, session_id=session_id, document_ids=document_ids)
        
        full_response = ""
        last_context = ""
        last_sources = []

        # Execute with streaming
        if route == RouteType.RAG_PIPELINE:
            async for event in self.rag_pipeline.execute_stream(query, chat_history, document_ids=document_ids):
                if event["type"] == "token":
                    full_response += event["data"]
                elif event["type"] == "context":
                    last_context = event["data"]
                elif event["type"] == "sources":
                    last_sources = event["data"]
                
                yield event
        else:
            async for token in self.llm.generate_stream(query, chat_history=chat_history):
                full_response += token
                yield {"type": "token", "data": token}

        # Finalize
        if session_id:
            assistant_msg_id = await self.memory.add_message(
                session_id, "assistant", full_response, user_id, 
                metadata={"sources": last_sources}
            )
            
            # Yield metadata for frontend to know the real message ID
            yield {"type": "metadata", "data": {"message_id": assistant_msg_id}}

            # Trigger Ragas Evaluation Asynchronously
            if use_rag and last_context:
                import asyncio
                from workers.evaluation_worker import evaluate_and_store
                
                asyncio.create_task(
                    evaluate_and_store(
                        query=query,
                        response=full_response,
                        contexts=[last_context],
                        message_id=assistant_msg_id,
                        session_id=session_id
                    )
                )
                logger.debug("Evaluation task queued", message_id=assistant_msg_id)


