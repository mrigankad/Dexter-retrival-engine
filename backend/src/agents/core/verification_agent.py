"""
VerificationAgent - Fact Verification Specialist

Responsible for verifying claims and detecting hallucinations:
- Check factual accuracy against sources
- Measure source credibility
- Detect contradictions
- Assign confidence scores
"""

from typing import Dict, Any, List
import time
import logging
from datetime import datetime

from src.agents.base.base_agent import Agent

logger = logging.getLogger(__name__)


class VerificationAgent(Agent):
    """
    Verifies claims and facts using LLM and source analysis.

    Takes analysis findings and verifies them against:
    1. Original documents
    2. Internal consistency
    3. Source credibility
    4. Logical coherence
    """

    def __init__(self):
        super().__init__(
            name="VerificationAgent",
            role="Fact Verification Specialist"
        )
        self.tools = {
            "check_consistency": None,
            "verify_sources": None,
            "measure_confidence": None,
        }

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute verification task.

        Args:
            task: {
                "task": "verify_findings",
                "previous_results": {
                    "key_findings": [...],
                    "documents": [...]
                },
                ...
            }

        Returns:
            {
                "status": "success",
                "verification": {...},
                "verified": bool,
                "confidence_score": 0.87,
                "issues": ["issue 1"],
                "execution_time": 1.23
            }
        """
        if task.get("task") != "verify_findings":
            raise ValueError(f"VerificationAgent only handles 'verify_findings' task")

        previous_results = task.get("previous_results", {})
        findings = previous_results.get("key_findings", [])
        documents = previous_results.get("documents", [])

        if not findings:
            raise ValueError("No findings provided for verification")

        if not documents:
            raise ValueError("No documents provided for verification")

        logger.info(f"VerificationAgent: Verifying {len(findings)} findings")

        start_time = time.time()

        try:
            # Import locally to avoid circular dependencies
            from src.services.llm.nvidia_llm_service import NvidiaLLMService

            llm_service = NvidiaLLMService()

            # Prepare verification prompt
            doc_text = self._prepare_documents(documents)
            prompt = self._create_verification_prompt(findings, doc_text)

            # Call LLM for verification
            verification_response = await llm_service.generate(
                prompt=prompt,
                max_tokens=600,
                temperature=0.5  # Lower temp for consistent factuality
            )

            # Parse verification results
            verification_data = self._parse_verification(verification_response)

            duration = time.time() - start_time

            # Store in memory
            await self.observe({
                "type": "verification_execution",
                "findings_count": len(findings),
                "confidence_score": verification_data.get("confidence_score", 0.5),
                "duration": duration,
                "importance": 0.8,  # High importance for verification
            })

            # Record execution
            self.record_execution(
                task_name="verify_findings",
                status="success",
                duration=duration,
                metadata={
                    "findings_count": len(findings),
                    "documents_count": len(documents)
                }
            )

            # Update performance
            confidence = verification_data.get("confidence_score", 0.5)
            self.update_performance(
                success=True,
                quality_score=confidence,
                response_time=duration
            )

            return {
                "status": "success",
                "verification": verification_data,
                "verified": verification_data.get("verified", False),
                "confidence_score": confidence,
                "issues": verification_data.get("issues", []),
                "evidence_strength": verification_data.get("evidence_strength", 0.5),
                "execution_time": round(duration, 3),
                "metadata": {
                    "verification_method": "llm_based",
                    "findings_verified": len(findings),
                    "timestamp": datetime.now().isoformat(),
                }
            }

        except Exception as exc:
            logger.error(f"VerificationAgent failed: {exc}")

            duration = time.time() - start_time

            # Record failure
            self.record_execution(
                task_name="verify_findings",
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

    async def think(self, findings: List[str], documents: List[Dict]) -> Dict[str, Any]:
        """
        Determine verification strategy.

        Args:
            findings: Claims to verify
            documents: Source documents

        Returns:
            Verification strategy dict
        """
        strategy = {
            "check_factuality": True,
            "check_consistency": True,
            "assess_source_credibility": True,
            "detect_hallucinations": True,
            "confidence_threshold": 0.7,
        }

        # Adjust based on document quality
        if len(documents) < 2:
            strategy["confidence_threshold"] = 0.5

        return strategy

    def _prepare_documents(self, documents: List[Dict]) -> str:
        """
        Prepare documents for verification.

        Args:
            documents: List of document dicts

        Returns:
            Formatted text for LLM
        """
        text_parts = []

        for i, doc in enumerate(documents, 1):
            content = doc.get("content", "")
            score = doc.get("score", 0.0)

            text_parts.append(f"[Source {i} (relevance: {score:.2f})]")
            text_parts.append(content[:400])
            text_parts.append("")

        return "\n".join(text_parts)

    def _create_verification_prompt(self, findings: List[str], doc_text: str) -> str:
        """
        Create verification prompt for LLM.

        Args:
            findings: Claims to verify
            doc_text: Source documents

        Returns:
            Prompt string
        """
        findings_str = "\n".join([f"- {f}" for f in findings])

        return f"""You are a fact-checking specialist. Verify the following findings against
the provided source documents.

Findings to verify:
{findings_str}

Source Documents:
{doc_text}

For each finding, assess:
1. Is it supported by the sources? (yes/no)
2. How strong is the evidence? (weak/moderate/strong)
3. Are there any contradictions?
4. Overall confidence score (0-1)

Also identify any:
- Hallucinations (claims not in sources)
- Contradictions (conflicting information)
- Unsupported inferences

Return a JSON response with:
{{
    "verified": bool,
    "confidence_score": float (0-1),
    "evidence_strength": float (0-1),
    "issues": ["issue1", "issue2"],
    "summary": "brief summary"
}}
"""

    def _parse_verification(self, response: str) -> Dict[str, Any]:
        """
        Parse LLM verification response.

        Args:
            response: Raw LLM response

        Returns:
            Structured verification dict
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
            "verified": "verified" in response.lower(),
            "confidence_score": 0.5,
            "evidence_strength": 0.5,
            "issues": [],
            "summary": response[:200],
        }

    def get_verification_stats(self) -> Dict[str, Any]:
        """Return verification-specific statistics."""
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
            "total_verifications": self.performance_metrics["total_tasks"],
            "successful_verifications": successful,
            "failed_verifications": self.performance_metrics["failed_tasks"],
            "avg_verification_time": self.performance_metrics["avg_response_time"],
            "avg_confidence_score": round(avg_confidence, 3),
            "success_rate": self.performance_metrics["success_rate"],
        }
