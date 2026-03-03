"""
BusinessExpertAgent - Business Domain Specialist

Responsible for providing business and finance domain expertise:
- Business strategy and planning
- Financial analysis and forecasting
- Market analysis and competitive positioning
- ROI and business case evaluation
"""

from typing import Dict, Any, List
import time
import logging
from datetime import datetime

from src.agents.base.base_agent import Agent

logger = logging.getLogger(__name__)


class BusinessExpertAgent(Agent):
    """
    Provides expertise on business and finance topics.

    Specializes in:
    1. Business strategy and planning
    2. Financial analysis and metrics
    3. Market research and competitive analysis
    4. ROI and business case development
    5. Risk assessment and mitigation
    6. Organizational dynamics
    """

    def __init__(self):
        super().__init__(
            name="BusinessExpertAgent",
            role="Business Domain Specialist"
        )

        self.domain = "business"
        self.expertise_areas = [
            "business strategy",
            "financial analysis",
            "market research",
            "competitive analysis",
            "roi calculation",
            "business case development",
            "risk assessment",
            "organizational structure",
        ]

        self.tools = {
            "analyze_business_case": None,
            "calculate_roi": None,
            "assess_market_opportunity": None,
            "evaluate_competitive_position": None,
        }

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute business domain expertise task.

        Args:
            task: {
                "task": "provide_expertise",
                "domain_question": "What's the market opportunity for this product?",
                "context": {...},
                "expertise_type": "market|financial|strategy|risk"
            }

        Returns:
            {
                "status": "success",
                "expertise": "business analysis",
                "recommendations": [...],
                "confidence_score": 0.85,
                "execution_time": 2.5
            }
        """
        if task.get("task") != "provide_expertise":
            raise ValueError(f"BusinessExpertAgent only handles 'provide_expertise' task")

        domain_question = task.get("domain_question", "")
        if not domain_question:
            raise ValueError("No domain question provided")

        expertise_type = task.get("expertise_type", "general")
        context = task.get("context", "")

        logger.info(f"BusinessExpertAgent: Analyzing {expertise_type} question: {domain_question[:100]}...")

        start_time = time.time()

        try:
            from src.services.llm.nvidia_llm_service import NvidiaLLMService

            llm_service = NvidiaLLMService()

            prompt = self._create_expertise_prompt(domain_question, expertise_type, context)

            expertise_response = await llm_service.generate(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.7
            )

            expertise_data = self._parse_expertise(expertise_response)

            duration = time.time() - start_time

            await self.observe({
                "type": "expertise_execution",
                "domain": self.domain,
                "expertise_type": expertise_type,
                "confidence_score": expertise_data.get("confidence_score", 0.7),
                "duration": duration,
                "importance": 0.8,
            })

            self.record_execution(
                task_name="provide_expertise",
                status="success",
                duration=duration,
                metadata={"expertise_type": expertise_type, "domain": self.domain}
            )

            self.update_performance(
                success=True,
                quality_score=expertise_data.get("confidence_score", 0.7),
                response_time=duration
            )

            return {
                "status": "success",
                "expertise": expertise_data.get("expertise", ""),
                "recommendations": expertise_data.get("recommendations", []),
                "financial_metrics": expertise_data.get("financial_metrics", {}),
                "confidence_score": expertise_data.get("confidence_score", 0.7),
                "risks": expertise_data.get("risks", []),
                "execution_time": round(duration, 3),
                "metadata": {
                    "domain": self.domain,
                    "expertise_type": expertise_type,
                    "timestamp": datetime.now().isoformat(),
                }
            }

        except Exception as exc:
            logger.error(f"BusinessExpertAgent failed: {exc}")
            duration = time.time() - start_time
            self.record_execution(
                task_name="provide_expertise",
                status="error",
                duration=duration,
                metadata={"error": str(exc)}
            )
            self.update_performance(success=False, quality_score=0.0, response_time=duration)
            raise

    async def think(self, domain_question: str, expertise_type: str) -> Dict[str, Any]:
        """Determine business analysis strategy."""
        return {
            "provide_detailed_analysis": True,
            "include_financial_metrics": True,
            "include_risk_assessment": True,
            "include_market_context": True,
            "depth_level": "comprehensive",
        }

    def _create_expertise_prompt(self, domain_question: str, expertise_type: str, context: str) -> str:
        """Create business expertise prompt."""
        expertise_guide = {
            "market": "Analyze market opportunity, size, growth, and competitive landscape.",
            "financial": "Provide financial analysis including ROI, payback period, and financial metrics.",
            "strategy": "Develop business strategy recommendations and action plans.",
            "risk": "Identify and assess business risks with mitigation strategies.",
            "general": "Provide comprehensive business expertise and analysis.",
        }

        guide_text = expertise_guide.get(expertise_type, expertise_guide["general"])
        context_text = f"\nAdditional Context:\n{context}" if context else ""

        return f"""You are a business domain expert with expertise in strategy, finance, market analysis,
and organizational dynamics.

{guide_text}

Question: {domain_question}{context_text}

Please provide:
1. Detailed business analysis
2. Key recommendations
3. Financial projections or metrics (if applicable)
4. Risk factors and mitigation
5. Market or competitive insights

Format as JSON with keys:
- "expertise": analysis
- "recommendations": list
- "financial_metrics": metrics
- "risks": risk assessment
- "confidence_score": 0-1
"""

    def _parse_expertise(self, response: str) -> Dict[str, Any]:
        """Parse business expertise response."""
        try:
            import json
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(response[start:end])
        except (json.JSONDecodeError, ValueError):
            pass

        return {
            "expertise": response[:500],
            "recommendations": [],
            "financial_metrics": {},
            "risks": [],
            "confidence_score": 0.6,
        }

    def get_expertise_stats(self) -> Dict[str, Any]:
        """Return domain expertise statistics."""
        history = self.get_execution_history()
        successful = sum(1 for h in history if h["status"] == "success")

        return {
            "total_expertise_queries": self.performance_metrics["total_tasks"],
            "successful_queries": successful,
            "failed_queries": self.performance_metrics["failed_tasks"],
            "avg_expertise_time": self.performance_metrics["avg_response_time"],
            "success_rate": self.performance_metrics["success_rate"],
            "domain": self.domain,
            "expertise_areas": self.expertise_areas,
        }
