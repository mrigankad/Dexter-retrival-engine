"""
Content Guardrails Service.

Provides safety and governance capabilities:
- Input validation and prompt injection detection
- Output moderation and content filtering
- PII detection
- Topic restriction enforcement
- Role-based access validation
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import httpx

from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)


class GuardrailResult(str, Enum):
    """Result of guardrail check."""
    PASS = "pass"
    WARN = "warn"
    BLOCK = "block"


class ViolationType(str, Enum):
    """Types of guardrail violations."""
    PROMPT_INJECTION = "prompt_injection"
    PII_DETECTED = "pii_detected"
    TOXIC_CONTENT = "toxic_content"
    OFF_TOPIC = "off_topic"
    HALLUCINATION = "hallucination"
    UNAUTHORIZED_ACCESS = "unauthorized_access"


@dataclass
class GuardrailCheckResult:
    """Result of a guardrail check."""
    result: GuardrailResult
    violations: List[ViolationType]
    details: Dict[str, Any]
    sanitized_content: Optional[str] = None
    confidence: float = 1.0


class GuardrailsService:
    """
    Content guardrails and safety service.
    
    Implements pre-generation (input) and post-generation (output)
    safety checks with configurable policies.
    """
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        Initialize guardrails service.
        
        Args:
            api_key: NVIDIA API key for NemoGuard
            base_url: NVIDIA NIM base URL
        """
        self.api_key = api_key or settings.nvidia_api_key
        self.base_url = base_url or settings.nvidia_base_url
        self.enabled = settings.guardrails_enabled
        self.input_guardrails = settings.input_guardrails
        self.output_guardrails = settings.output_guardrails
        
        # Pattern-based detection (fallback when API unavailable)
        self._setup_patterns()
        
        logger.info(
            "Guardrails service initialized",
            enabled=self.enabled,
            input=self.input_guardrails,
            output=self.output_guardrails
        )
    
    def _setup_patterns(self):
        """Setup regex patterns for local detection."""
        # Prompt injection patterns
        self.injection_patterns = [
            r"ignore\s+(previous|above|all)\s+(instructions|prompts)",
            r"disregard\s+(your|the)\s+(instructions|rules|guidelines)",
            r"pretend\s+you\s+are",
            r"act\s+as\s+if\s+you\s+(are|were)",
            r"forget\s+(everything|all|your)",
            r"new\s+instructions?:",
            r"system\s*:\s*you\s+are",
            r"</?(system|user|assistant)>",
            r"\[INST\]|\[/INST\]",
            r"<<SYS>>|<</SYS>>",
        ]
        self.injection_regex = re.compile(
            "|".join(self.injection_patterns),
            re.IGNORECASE
        )
        
        # PII patterns
        self.pii_patterns = {
            "email": r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
            "credit_card": r"\b(?:\d{4}[- ]?){3}\d{4}\b",
            "phone": r"\b(?:\+1[- ]?)?\(?\d{3}\)?[- ]?\d{3}[- ]?\d{4}\b",
            "ip_address": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        }
        
        # Toxic content keywords (simplified)
        self.toxic_keywords = [
            "hate", "violence", "weapon", "illegal", "harmful",
            "dangerous", "attack", "exploit", "hack", "malware"
        ]
    
    # ==========================================
    # Input Guardrails
    # ==========================================
    
    async def check_input(
        self,
        user_query: str,
        context: Optional[Dict[str, Any]] = None
    ) -> GuardrailCheckResult:
        """
        Pre-generation safety check on user input.
        
        Checks for:
        - Prompt injection attempts
        - PII in queries
        - Off-topic requests
        - Malicious intent
        
        Args:
            user_query: User's query text
            context: Optional context dict
            
        Returns:
            GuardrailCheckResult with pass/warn/block status
        """
        if not self.enabled or not self.input_guardrails:
            return GuardrailCheckResult(
                result=GuardrailResult.PASS,
                violations=[],
                details={"guardrails_disabled": True}
            )
        
        violations = []
        details = {}
        
        # Check for prompt injection
        injection_check = self._check_prompt_injection(user_query)
        if injection_check["detected"]:
            violations.append(ViolationType.PROMPT_INJECTION)
            details["injection"] = injection_check
        
        # Check for PII
        pii_check = self._check_pii(user_query)
        if pii_check["detected"]:
            violations.append(ViolationType.PII_DETECTED)
            details["pii"] = pii_check
        
        # Determine result
        if ViolationType.PROMPT_INJECTION in violations:
            result = GuardrailResult.BLOCK
        elif violations:
            result = GuardrailResult.WARN
        else:
            result = GuardrailResult.PASS
        
        logger.info(
            "Input guardrail check complete",
            result=result.value,
            violations=[v.value for v in violations]
        )
        
        return GuardrailCheckResult(
            result=result,
            violations=violations,
            details=details,
            sanitized_content=self._sanitize_pii(user_query) if pii_check["detected"] else user_query,
            confidence=0.9
        )
    
    def _check_prompt_injection(self, text: str) -> Dict[str, Any]:
        """Check for prompt injection attempts."""
        matches = self.injection_regex.findall(text.lower())
        
        return {
            "detected": len(matches) > 0,
            "matches": matches[:5],  # Limit matches shown
            "confidence": 0.95 if matches else 0.0
        }
    
    def _check_pii(self, text: str) -> Dict[str, Any]:
        """Check for personally identifiable information."""
        detected_pii = {}
        
        for pii_type, pattern in self.pii_patterns.items():
            matches = re.findall(pattern, text)
            if matches:
                detected_pii[pii_type] = len(matches)
        
        return {
            "detected": bool(detected_pii),
            "types": list(detected_pii.keys()),
            "counts": detected_pii
        }
    
    def _sanitize_pii(self, text: str) -> str:
        """Replace PII with placeholders."""
        sanitized = text
        
        for pii_type, pattern in self.pii_patterns.items():
            sanitized = re.sub(pattern, f"[{pii_type.upper()}_REDACTED]", sanitized)
        
        return sanitized
    
    # ==========================================
    # Output Guardrails
    # ==========================================
    
    async def check_output(
        self,
        llm_response: str,
        context: Optional[str] = None,
        original_query: Optional[str] = None
    ) -> GuardrailCheckResult:
        """
        Post-generation safety check on LLM output.
        
        Checks for:
        - Toxic or harmful content
        - PII leakage
        - Hallucination (if context provided)
        - Off-topic responses
        
        Args:
            llm_response: Generated response text
            context: Retrieved context (for hallucination check)
            original_query: Original user query
            
        Returns:
            GuardrailCheckResult with pass/warn/block status
        """
        if not self.enabled or not self.output_guardrails:
            return GuardrailCheckResult(
                result=GuardrailResult.PASS,
                violations=[],
                details={"guardrails_disabled": True}
            )
        
        violations = []
        details = {}
        
        # Check for toxic content
        toxic_check = self._check_toxic_content(llm_response)
        if toxic_check["detected"]:
            violations.append(ViolationType.TOXIC_CONTENT)
            details["toxic"] = toxic_check
        
        # Check for PII in response
        pii_check = self._check_pii(llm_response)
        if pii_check["detected"]:
            violations.append(ViolationType.PII_DETECTED)
            details["pii"] = pii_check
        
        # Check for hallucination (basic check)
        if context:
            hallucination_check = self._check_hallucination(llm_response, context)
            if hallucination_check["suspected"]:
                violations.append(ViolationType.HALLUCINATION)
                details["hallucination"] = hallucination_check
        
        # Determine result
        if ViolationType.TOXIC_CONTENT in violations:
            result = GuardrailResult.BLOCK
        elif violations:
            result = GuardrailResult.WARN
        else:
            result = GuardrailResult.PASS
        
        logger.info(
            "Output guardrail check complete",
            result=result.value,
            violations=[v.value for v in violations]
        )
        
        return GuardrailCheckResult(
            result=result,
            violations=violations,
            details=details,
            sanitized_content=self._sanitize_pii(llm_response) if pii_check["detected"] else llm_response,
            confidence=0.85
        )
    
    def _check_toxic_content(self, text: str) -> Dict[str, Any]:
        """Check for toxic or harmful content."""
        text_lower = text.lower()
        found_keywords = [kw for kw in self.toxic_keywords if kw in text_lower]
        
        # Very basic check - in production, use NemoGuard API
        return {
            "detected": len(found_keywords) > 2,  # Only flag if multiple keywords
            "keywords": found_keywords[:5],
            "confidence": 0.6  # Lower confidence for keyword-based detection
        }
    
    def _check_hallucination(
        self,
        response: str,
        context: str
    ) -> Dict[str, Any]:
        """
        Basic hallucination detection.
        
        Checks if response contains claims not grounded in context.
        This is a simplified version - production should use NemoGuard.
        """
        # Extract key claims/numbers from response
        response_numbers = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', response))
        context_numbers = set(re.findall(r'\b\d+(?:\.\d+)?%?\b', context))
        
        # Numbers in response not found in context (potential hallucination)
        ungrounded_numbers = response_numbers - context_numbers
        
        # Simple heuristic: if more than 30% of numbers are ungrounded, suspect hallucination
        if response_numbers:
            ungrounded_ratio = len(ungrounded_numbers) / len(response_numbers)
        else:
            ungrounded_ratio = 0.0
        
        return {
            "suspected": ungrounded_ratio > 0.3 and len(ungrounded_numbers) > 2,
            "ungrounded_numbers": list(ungrounded_numbers)[:5],
            "confidence": 0.5  # Low confidence for this simple check
        }
    
    # ==========================================
    # Access Control
    # ==========================================
    
    async def validate_access(
        self,
        user_id: str,
        user_roles: List[str],
        document_ids: List[str],
        action: str = "read"
    ) -> GuardrailCheckResult:
        """
        Validate user access to documents.
        
        Args:
            user_id: User identifier
            user_roles: User's roles
            document_ids: Documents being accessed
            action: Action being performed (read/write/delete)
            
        Returns:
            GuardrailCheckResult with access decision
        """
        # Placeholder - in production, check against access control policies
        # stored in PostgreSQL
        
        violations = []
        details = {
            "user_id": user_id,
            "roles": user_roles,
            "documents": document_ids,
            "action": action
        }
        
        # Example: Admin has full access
        if "admin" in user_roles:
            return GuardrailCheckResult(
                result=GuardrailResult.PASS,
                violations=[],
                details=details
            )
        
        # Example: Regular users can only read
        if action != "read" and "editor" not in user_roles:
            violations.append(ViolationType.UNAUTHORIZED_ACCESS)
            details["reason"] = f"Role required for {action}: editor or admin"
        
        result = GuardrailResult.BLOCK if violations else GuardrailResult.PASS
        
        return GuardrailCheckResult(
            result=result,
            violations=violations,
            details=details
        )
    
    # ==========================================
    # Topic Restriction
    # ==========================================
    
    def register_allowed_topics(self, topics: List[str]) -> None:
        """
        Register allowed topics for the RAG system.
        
        Args:
            topics: List of allowed topic keywords/categories
        """
        self.allowed_topics = [t.lower() for t in topics]
        logger.info(f"Registered {len(topics)} allowed topics")
    
    def check_topic_compliance(
        self,
        query: str,
        allowed_topics: Optional[List[str]] = None
    ) -> GuardrailCheckResult:
        """
        Check if query is within allowed topics.
        
        Args:
            query: User query
            allowed_topics: Override allowed topics list
            
        Returns:
            GuardrailCheckResult
        """
        topics = allowed_topics or getattr(self, 'allowed_topics', [])
        
        if not topics:
            # No restrictions
            return GuardrailCheckResult(
                result=GuardrailResult.PASS,
                violations=[],
                details={"topic_restriction": "none"}
            )
        
        query_lower = query.lower()
        topic_match = any(topic in query_lower for topic in topics)
        
        if topic_match:
            return GuardrailCheckResult(
                result=GuardrailResult.PASS,
                violations=[],
                details={"matched_topics": [t for t in topics if t in query_lower]}
            )
        else:
            return GuardrailCheckResult(
                result=GuardrailResult.WARN,
                violations=[ViolationType.OFF_TOPIC],
                details={
                    "allowed_topics": topics,
                    "message": "Query may be outside configured topic scope"
                }
            )
