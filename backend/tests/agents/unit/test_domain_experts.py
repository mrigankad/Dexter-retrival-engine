"""Unit tests for Domain Expert Agents"""

import pytest
from unittest.mock import AsyncMock, patch
from src.agents.domain.tech_expert_agent import TechExpertAgent
from src.agents.domain.business_expert_agent import BusinessExpertAgent
from src.agents.domain.healthcare_expert_agent import HealthcareExpertAgent
from src.agents.domain.legal_expert_agent import LegalExpertAgent


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def tech_expert():
    return TechExpertAgent()


@pytest.fixture
def business_expert():
    return BusinessExpertAgent()


@pytest.fixture
def healthcare_expert():
    return HealthcareExpertAgent()


@pytest.fixture
def legal_expert():
    return LegalExpertAgent()


@pytest.fixture
async def initialized_tech_expert(tech_expert):
    await tech_expert.initialize_memory()
    return tech_expert


@pytest.fixture
async def initialized_business_expert(business_expert):
    await business_expert.initialize_memory()
    return business_expert


@pytest.fixture
async def initialized_healthcare_expert(healthcare_expert):
    await healthcare_expert.initialize_memory()
    return healthcare_expert


@pytest.fixture
async def initialized_legal_expert(legal_expert):
    await legal_expert.initialize_memory()
    return legal_expert


# ── TechExpertAgent Tests ──────────────────────────────────────────────────────

class TestTechExpertAgent:
    """Tests for TechExpertAgent"""

    def test_tech_expert_initialization(self, tech_expert):
        assert tech_expert.name == "TechExpertAgent"
        assert tech_expert.role == "Technology Domain Specialist"
        assert tech_expert.domain == "technology"
        assert len(tech_expert.expertise_areas) > 0

    def test_tech_expert_inherits_from_agent(self, tech_expert):
        assert hasattr(tech_expert, "memory")
        assert hasattr(tech_expert, "execute")
        assert hasattr(tech_expert, "performance_metrics")

    @pytest.mark.asyncio
    async def test_tech_expert_execute_success(self, initialized_tech_expert):
        with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate = AsyncMock(return_value='{"expertise": "test", "recommendations": [], "best_practices": [], "confidence_score": 0.85}')
            MockLLM.return_value = mock_instance

            result = await initialized_tech_expert.execute({
                "task": "provide_expertise",
                "domain_question": "How to design scalable microservices?",
                "expertise_type": "architecture",
            })

            assert result["status"] == "success"
            assert "expertise" in result
            assert "recommendations" in result
            assert "confidence_score" in result

    @pytest.mark.asyncio
    async def test_tech_expert_think(self, tech_expert):
        strategy = await tech_expert.think("design question", "architecture")
        assert strategy["depth_level"] == "comprehensive"
        assert strategy["provide_detailed_analysis"] is True


# ── BusinessExpertAgent Tests ──────────────────────────────────────────────────

class TestBusinessExpertAgent:
    """Tests for BusinessExpertAgent"""

    def test_business_expert_initialization(self, business_expert):
        assert business_expert.name == "BusinessExpertAgent"
        assert business_expert.role == "Business Domain Specialist"
        assert business_expert.domain == "business"

    @pytest.mark.asyncio
    async def test_business_expert_execute_success(self, initialized_business_expert):
        with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate = AsyncMock(return_value='{"expertise": "market analysis", "recommendations": [], "financial_metrics": {}, "confidence_score": 0.8}')
            MockLLM.return_value = mock_instance

            result = await initialized_business_expert.execute({
                "task": "provide_expertise",
                "domain_question": "What's the market for AI consulting?",
                "expertise_type": "market",
            })

            assert result["status"] == "success"
            assert "expertise" in result
            assert "financial_metrics" in result
            assert "risks" in result


# ── HealthcareExpertAgent Tests ────────────────────────────────────────────────

class TestHealthcareExpertAgent:
    """Tests for HealthcareExpertAgent"""

    def test_healthcare_expert_initialization(self, healthcare_expert):
        assert healthcare_expert.name == "HealthcareExpertAgent"
        assert healthcare_expert.role == "Healthcare Domain Specialist"
        assert healthcare_expert.domain == "healthcare"

    @pytest.mark.asyncio
    async def test_healthcare_expert_safety_critical(self, initialized_healthcare_expert):
        with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate = AsyncMock(return_value='{"expertise": "clinical guidance", "recommendations": [], "compliance_notes": [], "patient_safety_considerations": [], "confidence_score": 0.85}')
            MockLLM.return_value = mock_instance

            result = await initialized_healthcare_expert.execute({
                "task": "provide_expertise",
                "domain_question": "Best practices for EHR implementation?",
                "expertise_type": "technology",
            })

            assert result["status"] == "success"
            assert result["metadata"]["safety_critical"] is True
            assert "compliance_notes" in result
            assert "patient_safety_considerations" in result


# ── LegalExpertAgent Tests ─────────────────────────────────────────────────────

class TestLegalExpertAgent:
    """Tests for LegalExpertAgent"""

    def test_legal_expert_initialization(self, legal_expert):
        assert legal_expert.name == "LegalExpertAgent"
        assert legal_expert.role == "Legal Domain Specialist"
        assert legal_expert.domain == "legal"

    @pytest.mark.asyncio
    async def test_legal_expert_includes_disclaimer(self, initialized_legal_expert):
        with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate = AsyncMock(return_value='{"expertise": "compliance guidance", "recommendations": [], "legal_considerations": [], "compliance_requirements": [], "risk_factors": [], "confidence_score": 0.82}')
            MockLLM.return_value = mock_instance

            result = await initialized_legal_expert.execute({
                "task": "provide_expertise",
                "domain_question": "What are GDPR requirements?",
                "expertise_type": "compliance",
            })

            assert result["status"] == "success"
            assert "disclaimer" in result
            assert result["metadata"]["requires_legal_review"] is True
            assert "compliance_requirements" in result


# ── Shared Tests ───────────────────────────────────────────────────────────────

class TestDomainExpertShared:
    """Shared tests for all domain experts"""

    @pytest.mark.asyncio
    async def test_all_experts_reject_wrong_task(self, initialized_tech_expert, initialized_business_expert, initialized_healthcare_expert, initialized_legal_expert):
        experts = [initialized_tech_expert, initialized_business_expert, initialized_healthcare_expert, initialized_legal_expert]

        for expert in experts:
            with pytest.raises(ValueError, match="only handles 'provide_expertise'"):
                await expert.execute({
                    "task": "wrong_task",
                    "domain_question": "test",
                })

    @pytest.mark.asyncio
    async def test_all_experts_require_question(self, initialized_tech_expert, initialized_business_expert, initialized_healthcare_expert, initialized_legal_expert):
        experts = [initialized_tech_expert, initialized_business_expert, initialized_healthcare_expert, initialized_legal_expert]

        for expert in experts:
            with pytest.raises(ValueError, match="No domain question provided"):
                await expert.execute({
                    "task": "provide_expertise",
                    "domain_question": "",
                })

    @pytest.mark.asyncio
    async def test_all_experts_update_performance(self, initialized_tech_expert, initialized_business_expert, initialized_healthcare_expert, initialized_legal_expert):
        experts = [initialized_tech_expert, initialized_business_expert, initialized_healthcare_expert, initialized_legal_expert]

        for expert in experts:
            with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLM:
                mock_instance = AsyncMock()
                mock_instance.generate = AsyncMock(return_value='{"expertise": "test", "recommendations": [], "confidence_score": 0.8}')
                MockLLM.return_value = mock_instance

                assert expert.performance_metrics["total_tasks"] == 0

                await expert.execute({
                    "task": "provide_expertise",
                    "domain_question": "test question",
                })

                assert expert.performance_metrics["total_tasks"] == 1
                assert expert.performance_metrics["successful_tasks"] == 1

    @pytest.mark.asyncio
    async def test_all_experts_store_in_memory(self, initialized_tech_expert, initialized_business_expert, initialized_healthcare_expert, initialized_legal_expert):
        experts = [initialized_tech_expert, initialized_business_expert, initialized_healthcare_expert, initialized_legal_expert]

        for expert in experts:
            with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLM:
                mock_instance = AsyncMock()
                mock_instance.generate = AsyncMock(return_value='{"expertise": "test", "recommendations": [], "confidence_score": 0.8}')
                MockLLM.return_value = mock_instance

                await expert.execute({
                    "task": "provide_expertise",
                    "domain_question": "test question",
                })

                assert len(expert.memory.short_term) > 0
                entry = expert.memory.short_term[0]
                assert entry["type"] == "expertise_execution"
                assert entry["domain"] == expert.domain

    def test_all_experts_get_stats(self, tech_expert, business_expert, healthcare_expert, legal_expert):
        experts = [tech_expert, business_expert, healthcare_expert, legal_expert]

        for expert in experts:
            expert.record_execution("provide_expertise", "success", 2.5)
            stats = expert.get_expertise_stats()

            assert "total_expertise_queries" in stats
            assert "successful_queries" in stats
            assert "failed_queries" in stats
            assert "domain" in stats
            assert "expertise_areas" in stats


# ── Domain-Specific Tests ──────────────────────────────────────────────────────

class TestDomainSpecificBehavior:
    """Tests for domain-specific behavior"""

    @pytest.mark.asyncio
    async def test_healthcare_expert_uses_lower_temperature(self, initialized_healthcare_expert):
        """Healthcare expert uses lower temperature for safety"""
        with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate = AsyncMock(return_value='{"expertise": "test", "recommendations": [], "compliance_notes": [], "patient_safety_considerations": [], "confidence_score": 0.85}')
            MockLLM.return_value = mock_instance

            await initialized_healthcare_expert.execute({
                "task": "provide_expertise",
                "domain_question": "test",
                "expertise_type": "clinical",
            })

            # Check that generate was called with lower temperature
            call_args = mock_instance.generate.call_args
            assert call_args[1]["temperature"] == 0.6

    @pytest.mark.asyncio
    async def test_legal_expert_uses_lower_temperature(self, initialized_legal_expert):
        """Legal expert uses lower temperature for accuracy"""
        with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate = AsyncMock(return_value='{"expertise": "test", "recommendations": [], "legal_considerations": [], "compliance_requirements": [], "risk_factors": [], "confidence_score": 0.82}')
            MockLLM.return_value = mock_instance

            await initialized_legal_expert.execute({
                "task": "provide_expertise",
                "domain_question": "test",
                "expertise_type": "compliance",
            })

            call_args = mock_instance.generate.call_args
            assert call_args[1]["temperature"] == 0.6

    @pytest.mark.asyncio
    async def test_tech_expert_handles_architecture_type(self, initialized_tech_expert):
        """Tech expert handles architecture expertise type"""
        with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate = AsyncMock(return_value='{"expertise": "architecture advice", "recommendations": [], "best_practices": [], "confidence_score": 0.85}')
            MockLLM.return_value = mock_instance

            result = await initialized_tech_expert.execute({
                "task": "provide_expertise",
                "domain_question": "design scalable system",
                "expertise_type": "architecture",
            })

            assert result["metadata"]["expertise_type"] == "architecture"
            assert "best_practices" in result

    @pytest.mark.asyncio
    async def test_business_expert_includes_financial_metrics(self, initialized_business_expert):
        """Business expert includes financial metrics"""
        with patch("services.nvidia_llm_service.NvidiaLLMService") as MockLLM:
            mock_instance = AsyncMock()
            mock_instance.generate = AsyncMock(return_value='{"expertise": "financial analysis", "recommendations": [], "financial_metrics": {"roi": 0.35, "payback_period": 18}, "confidence_score": 0.8}')
            MockLLM.return_value = mock_instance

            result = await initialized_business_expert.execute({
                "task": "provide_expertise",
                "domain_question": "roi analysis",
                "expertise_type": "financial",
            })

            assert "financial_metrics" in result
