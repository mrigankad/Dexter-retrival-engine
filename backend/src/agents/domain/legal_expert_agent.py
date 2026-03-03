"""
LegalExpertAgent - Legal Domain Specialist

Responsible for providing legal domain expertise:
- Legal analysis and case assessment
- Regulatory compliance and requirements
- Contract analysis and negotiation
- Risk assessment and mitigation
"""

from typing import Dict, Any, List
import time
import logging
from datetime import datetime

from src.agents.base.base_agent import Agent

logger = logging.getLogger(__name__)


class LegalExpertAgent(Agent):
    """
    Provides expertise on legal and regulatory topics.

    Specializes in:
    1. Legal analysis and interpretation
    2. Regulatory compliance and requirements
    3. Contract analysis and negotiation
    4. Risk assessment and mitigation
    5. Intellectual property
    6. Employment law and labor regulations
    7. Data privacy and security regulations
    8. Industry-specific legal requirements
    """

    def __init__(self):
        super().__init__(
            name="LegalExpertAgent",
            role="Legal Domain Specialist"
        )

        self.domain = "legal"
        self.expertise_areas = [
            "legal analysis",
            "regulatory compliance",
            "contract law",
            "intellectual property",
            "employment law",
            "data privacy",
            "regulatory requirements",
            "legal risk assessment",
        ]

        self.tools = {
            "analyze_legal_question": None,
            "assess_compliance": None,
            "analyze_contract": None,
            "assess_legal_risk": None,
        }

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute legal domain expertise task.

        Args:
            task: {
                "task": "provide_expertise",
                "domain_question": "What are GDPR requirements for data processing?",
                "context": {...},
                "expertise_type": "compliance|contract|risk|regulatory"
            }

        Returns:
            {
                "status": "success",
                "expertise": "legal analysis",
                "recommendations": [...],
                "legal_considerations": [...],
                "compliance_requirements": [...],
                "confidence_score": 0.85,
                "execution_time": 2.5
            }
        """
        if task.get("task") != "provide_expertise":
            raise ValueError(f"LegalExpertAgent only handles 'provide_expertise' task")

        domain_question = task.get("domain_question", "")
        if not domain_question:
            raise ValueError("No domain question provided")

        expertise_type = task.get("expertise_type", "general")
        context = task.get("context", "")

        logger.info(f"LegalExpertAgent: Analyzing {expertise_type} question: {domain_question[:100]}...")

        start_time = time.time()

        try:
            from src.services.llm.nvidia_llm_service import NvidiaLLMService

            llm_service = NvidiaLLMService()

            prompt = self._create_expertise_prompt(domain_question, expertise_type, context)

            expertise_response = await llm_service.generate(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.6  # Lower temperature for legal accuracy
            )

            expertise_data = self._parse_expertise(expertise_response)

            duration = time.time() - start_time

            await self.observe({
                "type": "expertise_execution",
                "domain": self.domain,
                "expertise_type": expertise_type,
                "confidence_score": expertise_data.get("confidence_score", 0.7),
                "duration": duration,
                "importance": 0.9,  # Higher importance for legal matters
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
                "legal_considerations": expertise_data.get("legal_considerations", []),
                "compliance_requirements": expertise_data.get("compliance_requirements", []),
                "risk_factors": expertise_data.get("risk_factors", []),
                "confidence_score": expertise_data.get("confidence_score", 0.7),
                "disclaimer": "This is not legal advice. Consult qualified legal counsel.",
                "execution_time": round(duration, 3),
                "metadata": {
                    "domain": self.domain,
                    "expertise_type": expertise_type,
                    "timestamp": datetime.now().isoformat(),
                    "requires_legal_review": True,
                }
            }

        except Exception as exc:
            logger.error(f"LegalExpertAgent failed: {exc}")
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
        """Determine legal analysis strategy."""
        return {
            "provide_detailed_analysis": True,
            "include_regulatory_requirements": True,
            "include_risk_assessment": True,
            "include_compliance_checklist": True,
            "requires_legal_review": True,
            "depth_level": "comprehensive",
        }

    def _create_expertise_prompt(self, domain_question: str, expertise_type: str, context: str) -> str:
        """Create legal expertise prompt."""
        expertise_guide = {
            "compliance": "Assess regulatory compliance requirements and obligations.",
            "contract": "Analyze contract terms, conditions, and potential risks.",
            "risk": "Identify legal risks and recommend mitigation strategies.",
            "regulatory": "Explain relevant regulations and legal requirements.",
            "general": "Provide comprehensive legal expertise and guidance.",
        }

        guide_text = expertise_guide.get(expertise_type, expertise_guide["general"])
        context_text = f"\nAdditional Context:\n{context}" if context else ""

        return f"""You are a legal domain expert with expertise in regulatory compliance, contracts,
intellectual property, employment law, data privacy, and risk assessment.

IMPORTANT: Provide accurate legal guidance but include a disclaimer that this is not legal advice.

{guide_text}

Question: {domain_question}{context_text}

Please provide:
1. Detailed legal analysis
2. Key recommendations
3. Relevant laws and regulations
4. Compliance requirements
5. Risk factors and mitigation

Format as JSON with keys:
- "expertise": analysis
- "recommendations": list
- "legal_considerations": key considerations
- "compliance_requirements": requirements
- "risk_factors": identified risks
- "confidence_score": 0-1
"""

    def _parse_expertise(self, response: str) -> Dict[str, Any]:
        """Parse legal expertise response."""
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
            "legal_considerations": [],
            "compliance_requirements": [],
            "risk_factors": [],
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
            "requires_legal_review": True,
        }
