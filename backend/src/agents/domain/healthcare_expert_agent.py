"""
HealthcareExpertAgent - Healthcare Domain Specialist

Responsible for providing healthcare domain expertise:
- Medical knowledge and best practices
- Healthcare regulations and compliance (HIPAA, etc.)
- Clinical decision support
- Healthcare technology assessment
"""

from typing import Dict, Any, List
import time
import logging
from datetime import datetime

from src.agents.base.base_agent import Agent

logger = logging.getLogger(__name__)


class HealthcareExpertAgent(Agent):
    """
    Provides expertise on healthcare and medical topics.

    Specializes in:
    1. Clinical knowledge and best practices
    2. Healthcare regulations and compliance
    3. Medical terminology and concepts
    4. Healthcare technology and systems
    5. Patient safety and quality standards
    6. Healthcare policy and economics
    """

    def __init__(self):
        super().__init__(
            name="HealthcareExpertAgent",
            role="Healthcare Domain Specialist"
        )

        self.domain = "healthcare"
        self.expertise_areas = [
            "clinical best practices",
            "healthcare regulations",
            "medical technology",
            "patient safety",
            "quality standards",
            "healthcare administration",
            "medical informatics",
            "healthcare policy",
        ]

        self.tools = {
            "assess_clinical_validity": None,
            "check_regulatory_compliance": None,
            "evaluate_healthcare_technology": None,
            "assess_patient_safety": None,
        }

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute healthcare domain expertise task.

        Args:
            task: {
                "task": "provide_expertise",
                "domain_question": "What are best practices for EHR implementation?",
                "context": {...},
                "expertise_type": "clinical|regulatory|technology|quality"
            }

        Returns:
            {
                "status": "success",
                "expertise": "healthcare analysis",
                "recommendations": [...],
                "compliance_notes": [...],
                "confidence_score": 0.85,
                "execution_time": 2.5
            }
        """
        if task.get("task") != "provide_expertise":
            raise ValueError(f"HealthcareExpertAgent only handles 'provide_expertise' task")

        domain_question = task.get("domain_question", "")
        if not domain_question:
            raise ValueError("No domain question provided")

        expertise_type = task.get("expertise_type", "general")
        context = task.get("context", "")

        logger.info(f"HealthcareExpertAgent: Analyzing {expertise_type} question: {domain_question[:100]}...")

        start_time = time.time()

        try:
            from src.services.llm.nvidia_llm_service import NvidiaLLMService

            llm_service = NvidiaLLMService()

            prompt = self._create_expertise_prompt(domain_question, expertise_type, context)

            expertise_response = await llm_service.generate(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.6  # Lower temperature for healthcare safety
            )

            expertise_data = self._parse_expertise(expertise_response)

            duration = time.time() - start_time

            await self.observe({
                "type": "expertise_execution",
                "domain": self.domain,
                "expertise_type": expertise_type,
                "confidence_score": expertise_data.get("confidence_score", 0.7),
                "duration": duration,
                "importance": 0.9,  # Higher importance for healthcare
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
                "compliance_notes": expertise_data.get("compliance_notes", []),
                "patient_safety_considerations": expertise_data.get("patient_safety_considerations", []),
                "confidence_score": expertise_data.get("confidence_score", 0.7),
                "execution_time": round(duration, 3),
                "metadata": {
                    "domain": self.domain,
                    "expertise_type": expertise_type,
                    "timestamp": datetime.now().isoformat(),
                    "safety_critical": True,
                }
            }

        except Exception as exc:
            logger.error(f"HealthcareExpertAgent failed: {exc}")
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
        """Determine healthcare analysis strategy."""
        return {
            "provide_detailed_analysis": True,
            "include_regulatory_guidance": True,
            "include_safety_considerations": True,
            "include_best_practices": True,
            "safety_critical": True,
            "depth_level": "comprehensive",
        }

    def _create_expertise_prompt(self, domain_question: str, expertise_type: str, context: str) -> str:
        """Create healthcare expertise prompt."""
        expertise_guide = {
            "clinical": "Provide clinical best practices and evidence-based guidance.",
            "regulatory": "Address healthcare regulations including HIPAA, CMS, and quality standards.",
            "technology": "Evaluate healthcare technology systems and implementation practices.",
            "quality": "Assess patient safety, quality metrics, and quality improvement.",
            "general": "Provide comprehensive healthcare expertise and guidance.",
        }

        guide_text = expertise_guide.get(expertise_type, expertise_guide["general"])
        context_text = f"\nAdditional Context:\n{context}" if context else ""

        return f"""You are a healthcare domain expert with knowledge of clinical practices, healthcare
regulations, medical technology, and patient safety standards.

IMPORTANT: Provide accurate, evidence-based guidance. Include relevant compliance and safety considerations.

{guide_text}

Question: {domain_question}{context_text}

Please provide:
1. Detailed healthcare expertise and analysis
2. Key recommendations
3. Relevant regulations and compliance requirements
4. Patient safety considerations
5. Best practices and quality standards

Format as JSON with keys:
- "expertise": analysis
- "recommendations": list
- "compliance_notes": regulatory guidance
- "patient_safety_considerations": safety factors
- "confidence_score": 0-1
"""

    def _parse_expertise(self, response: str) -> Dict[str, Any]:
        """Parse healthcare expertise response."""
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
            "compliance_notes": [],
            "patient_safety_considerations": [],
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
            "safety_critical": True,
        }
