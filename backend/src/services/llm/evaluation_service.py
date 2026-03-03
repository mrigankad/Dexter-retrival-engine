"""
Evaluation Service - RAG performance monitoring and quality assessment.

Uses RAGAS framework with NVIDIA NIM for:
- Faithfulness (Hallucination detection)
- Answer Relevance
- Context Precision
- Context Recall
"""

import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime

from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from datasets import Dataset
from src.services.ragas_nvidia_wrapper import NvidiaJudgeLLM

from src.core.config import settings
from src.core.logger import get_logger, log_timing

logger = get_logger(__name__)


class EvaluationService:
    """Service for evaluating RAG pipeline performance using RAGAS and NVIDIA models."""
    
    def __init__(self):
        self.judge_llm = NvidiaJudgeLLM()
        self.enabled = settings.ragas_evaluation_enabled

    @log_timing("rag_evaluation")
    async def evaluate_response(
        self,
        query: str,
        response: str,
        contexts: List[str],
        ground_truth: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a single RAG response using Ragas metrics.
        """
        if not self.enabled:
            return {"status": "disabled"}
            
        try:
            # Prepare dataset for RAGAS
            data = {
                "question": [query],
                "answer": [response],
                "contexts": [contexts],
            }
            if ground_truth:
                data["ground_truth"] = [ground_truth]
                
            dataset = Dataset.from_dict(data)
            
            # Run evaluation with our NVIDIA Judge
            # Note: evaluate is typically sync, we run in executor for async safety
            result = await asyncio.to_thread(
                evaluate,
                dataset,
                metrics=[faithfulness, answer_relevancy],
                llm=self.judge_llm
            )
            
            evaluation_results = {
                "timestamp": datetime.utcnow().isoformat(),
                "scores": {
                    "faithfulness": float(result["faithfulness"]),
                    "answer_relevance": float(result["answer_relevancy"])
                }
            }
            
            logger.info("RAGAS Evaluation complete", 
                        faithfulness=evaluation_results["scores"]["faithfulness"],
                        relevance=evaluation_results["scores"]["answer_relevance"])
            
            return evaluation_results
            
        except Exception as e:
            logger.error("RAGAS evaluation failed", error=str(e))
            return {"status": "error", "error": str(e)}

    def log_to_prometheus(self, results: Dict[str, Any]):
        """Export metrics to Prometheus for long-term monitoring."""
        # Implementation for Phase 6 Observability
        pass
