"""
TechExpertAgent - Technology Domain Specialist

Responsible for providing technology and software domain expertise:
- Technical architecture analysis
- Code and algorithm explanation
- Technology stack recommendations
- Software best practices assessment
"""

from typing import Dict, Any, List
import time
import logging
from datetime import datetime

from src.agents.base.base_agent import Agent

logger = logging.getLogger(__name__)


class TechExpertAgent(Agent):
    """
    Provides expertise on technology and software topics.

    Specializes in:
    1. Technical architecture and design patterns
    2. Programming languages and frameworks
    3. Software development best practices
    4. Technology recommendations and evaluations
    5. Code quality and performance analysis
    """

    def __init__(self):
        super().__init__(
            name="TechExpertAgent",
            role="Technology Domain Specialist"
        )

        self.domain = "technology"
        self.expertise_areas = [
            "software architecture",
            "programming languages",
            "frameworks and libraries",
            "databases and storage",
            "cloud platforms",
            "devops and deployment",
            "security practices",
            "performance optimization",
        ]

        self.tools = {
            "analyze_architecture": None,
            "recommend_tech_stack": None,
            "assess_code_quality": None,
            "evaluate_frameworks": None,
        }

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute domain expertise task.

        Args:
            task: {
                "task": "provide_expertise",
                "domain_question": "How to design a scalable API?",
                "context": {...},
                "expertise_type": "architecture|recommendation|evaluation|best_practices"
            }

        Returns:
            {
                "status": "success",
                "expertise": "detailed domain knowledge",
                "recommendations": [...],
                "confidence_score": 0.85,
                "references": [...],
                "execution_time": 2.5
            }
        """
        if task.get("task") != "provide_expertise":
            raise ValueError(f"TechExpertAgent only handles 'provide_expertise' task")

        domain_question = task.get("domain_question", "")
        if not domain_question:
            raise ValueError("No domain question provided")

        expertise_type = task.get("expertise_type", "general")
        context = task.get("context", "")

        logger.info(f"TechExpertAgent: Analyzing {expertise_type} question: {domain_question[:100]}...")

        start_time = time.time()

        try:
            from src.services.llm.nvidia_llm_service import NvidiaLLMService

            llm_service = NvidiaLLMService()

            # Build expertise prompt
            prompt = self._create_expertise_prompt(domain_question, expertise_type, context)

            # Get expertise from LLM
            expertise_response = await llm_service.generate(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.7
            )

            # Parse and structure expertise
            expertise_data = self._parse_expertise(expertise_response)

            duration = time.time() - start_time

            # Store in memory
            await self.observe({
                "type": "expertise_execution",
                "domain": self.domain,
                "expertise_type": expertise_type,
                "confidence_score": expertise_data.get("confidence_score", 0.7),
                "duration": duration,
                "importance": 0.8,
            })

            # Record execution
            self.record_execution(
                task_name="provide_expertise",
                status="success",
                duration=duration,
                metadata={
                    "expertise_type": expertise_type,
                    "domain": self.domain,
                }
            )

            # Update performance
            self.update_performance(
                success=True,
                quality_score=expertise_data.get("confidence_score", 0.7),
                response_time=duration
            )

            return {
                "status": "success",
                "expertise": expertise_data.get("expertise", ""),
                "recommendations": expertise_data.get("recommendations", []),
                "best_practices": expertise_data.get("best_practices", []),
                "confidence_score": expertise_data.get("confidence_score", 0.7),
                "references": expertise_data.get("references", []),
                "execution_time": round(duration, 3),
                "metadata": {
                    "domain": self.domain,
                    "expertise_type": expertise_type,
                    "timestamp": datetime.now().isoformat(),
                }
            }

        except Exception as exc:
            logger.error(f"TechExpertAgent failed: {exc}")

            duration = time.time() - start_time

            self.record_execution(
                task_name="provide_expertise",
                status="error",
                duration=duration,
                metadata={"error": str(exc)}
            )

            self.update_performance(
                success=False,
                quality_score=0.0,
                response_time=duration
            )

            raise

    async def think(self, domain_question: str, expertise_type: str) -> Dict[str, Any]:
        """
        Determine expertise analysis strategy.

        Args:
            domain_question: Question about technology
            expertise_type: Type of expertise (architecture, recommendation, etc.)

        Returns:
            Strategy dict
        """
        strategy = {
            "provide_detailed_analysis": True,
            "include_best_practices": True,
            "include_trade_offs": True,
            "reference_standards": True,
            "depth_level": "comprehensive",
        }

        # Adjust based on expertise type
        if expertise_type == "quick_recommendation":
            strategy["depth_level"] = "quick"
        elif expertise_type == "evaluation":
            strategy["include_trade_offs"] = True
            strategy["include_comparison"] = True

        return strategy

    def _create_expertise_prompt(self, domain_question: str, expertise_type: str, context: str) -> str:
        """
        Create expertise analysis prompt.

        Args:
            domain_question: The question about technology
            expertise_type: Type of expertise needed
            context: Additional context

        Returns:
            Prompt string
        """
        expertise_guide = {
            "architecture": "Provide architectural guidance including design patterns, scalability considerations, and trade-offs.",
            "recommendation": "Recommend appropriate technologies, frameworks, and tools for the described use case.",
            "evaluation": "Compare and evaluate different technology options, discussing pros/cons of each.",
            "best_practices": "Explain industry best practices and how to implement them.",
            "general": "Provide comprehensive technology expertise and guidance.",
        }

        guide_text = expertise_guide.get(expertise_type, expertise_guide["general"])

        context_text = f"\nAdditional Context:\n{context}" if context else ""

        return f"""You are a technology domain expert with deep knowledge of software architecture,
programming languages, frameworks, databases, cloud platforms, and software development practices.

{guide_text}

Question: {domain_question}{context_text}

Please provide:
1. Detailed expertise and analysis
2. Key recommendations
3. Best practices to follow
4. Important trade-offs or considerations
5. References or industry standards

Format your response as JSON with keys:
- "expertise": detailed analysis
- "recommendations": list of specific recommendations
- "best_practices": list of best practices
- "confidence_score": 0-1 confidence in advice
- "references": relevant standards or resources
"""

    def _parse_expertise(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM expertise response.

        Args:
            response: Raw LLM response

        Returns:
            Structured expertise dict
        """
        try:
            import json
            start = response.find("{")
            end = response.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = response[start:end]
                return json.loads(json_str)
        except (json.JSONDecodeError, ValueError):
            pass

        # Fallback parsing
        return {
            "expertise": response[:500],
            "recommendations": [],
            "best_practices": [],
            "confidence_score": 0.6,
            "references": [],
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
