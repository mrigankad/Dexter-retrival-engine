# Multi-Agent System Implementation Guide

**Version:** 1.0
**Date:** February 27, 2026
**Audience:** Development Team
**Duration:** 6-8 weeks for Phase 1

---

## Quick Start: Multi-Agent Integration

### Current System Architecture
```
FastAPI (main.py)
    ↓
API Routes (auth, chat, ingest, etc.)
    ↓
Orchestrator (single pipeline)
    ├→ QueryRouter
    └→ RAG Pipeline
         ├→ Retrieval Service
         ├→ Reranker Service
         └→ LLM Service
              ↓
              Answer
```

### New Architecture (Multi-Agent)
```
FastAPI (main.py) + Agent Router
    ↓
API Routes (existing + new /chat/multi-agent)
    ↓
CoordinatorAgent
    ├→ Intent Understanding
    ├→ Execution Planning
    ├→ Agent Orchestration
    │   ├→ SearchAgent
    │   ├→ AnalysisAgent
    │   ├→ VerificationAgent
    │   ├→ SynthesisAgent
    │   └→ Domain Experts
    ├→ Quality Evaluation
    └→ Memory & Learning
         ↓
         Enhanced Answer + Reasoning
```

---

## Implementation Details

### Phase 1: Setup & Core Agents (Weeks 1-4)

#### Week 1-2: Foundation Infrastructure

**1. Create Agent Framework**

```bash
# Directory structure
mkdir -p backend/agents/{base,specialized,domain,support,patterns}
touch backend/agents/__init__.py
touch backend/agents/base_agent.py
touch backend/agents/agent_memory.py
touch backend/agents/communication_bus.py
touch backend/agents/execution_engine.py
touch backend/agents/coordinator_agent.py
```

**2. Core Files to Create**

**backend/agents/base_agent.py:**
```python
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import asyncio
import uuid
from datetime import datetime

class Agent(ABC):
    """Base agent class for all specialized agents"""

    def __init__(self, name: str, role: str, model_name: str = "claude-opus-4-6"):
        self.id = str(uuid.uuid4())
        self.name = name
        self.role = role
        self.model_name = model_name
        self.tools = {}
        self.memory = AgentMemory(self.name)
        self.conversation_history = []
        self.performance_metrics = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "avg_response_time": 0,
            "avg_quality_score": 0
        }

    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute assigned task"""
        pass

    async def think(self, context: str) -> str:
        """Agent reasoning process"""
        # Use LLM to think through the problem
        prompt = f"""
        You are a {self.role} agent.
        Context: {context}

        Think through this step-by-step and provide your analysis.
        """
        return await self._call_llm(prompt)

    async def act(self, decision: str) -> Any:
        """Execute the decision"""
        pass

    async def observe(self, observation: str) -> None:
        """Learn from observation"""
        await self.memory.store({
            "timestamp": datetime.now().isoformat(),
            "observation": observation,
            "type": "feedback"
        })

    async def _call_llm(self, prompt: str) -> str:
        """Call LLM for reasoning"""
        from backend.services.nvidia_llm_service import nvidia_llm_service

        response = await nvidia_llm_service.generate(
            prompt=prompt,
            max_tokens=500,
            temperature=0.7
        )
        return response

    def update_performance(self, success: bool, quality_score: float, response_time: float):
        """Update agent performance metrics"""
        self.performance_metrics["total_tasks"] += 1
        if success:
            self.performance_metrics["successful_tasks"] += 1

        # Update averages
        total = self.performance_metrics["total_tasks"]
        current_avg_quality = self.performance_metrics["avg_quality_score"]
        self.performance_metrics["avg_quality_score"] = (
            (current_avg_quality * (total - 1) + quality_score) / total
        )

        current_avg_time = self.performance_metrics["avg_response_time"]
        self.performance_metrics["avg_response_time"] = (
            (current_avg_time * (total - 1) + response_time) / total
        )


class AgentMemory:
    """Memory system for agents"""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.short_term = []  # Current conversation
        self.long_term = []   # Persistent knowledge
        self.max_short_term = 20

    async def store(self, item: Dict) -> None:
        """Store in short-term memory"""
        self.short_term.append(item)

        # Move old items to long-term if important
        if len(self.short_term) > self.max_short_term:
            important_items = [
                i for i in self.short_term
                if i.get("importance", 0) > 0.7
            ]
            self.long_term.extend(important_items)
            self.short_term = self.short_term[-self.max_short_term:]

    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        """Retrieve relevant memories"""
        # Simple similarity matching
        relevant = []

        for item in self.short_term + self.long_term:
            if query.lower() in item.get("observation", "").lower():
                relevant.append(item)

        return relevant[:top_k]

    async def clear(self) -> None:
        """Clear memory (GDPR compliance)"""
        self.short_term = []
        self.long_term = []
```

**backend/agents/communication_bus.py:**
```python
from dataclasses import dataclass
from typing import Dict, List, Callable, Optional
import asyncio
from collections import defaultdict
import json

@dataclass
class AgentMessage:
    """Message between agents"""
    sender: str
    recipient: str
    message_type: str  # "request", "response", "update", "query"
    content: Dict
    priority: int = 1
    message_id: str = None
    timestamp: float = None

    def __post_init__(self):
        import time
        import uuid
        if not self.message_id:
            self.message_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = time.time()


class AgentCommunicationBus:
    """Central communication hub for agents"""

    def __init__(self):
        self.message_queue = asyncio.Queue()
        self.subscriptions = defaultdict(list)
        self.message_history = []
        self.handlers = defaultdict(list)

    async def send_message(self, message: AgentMessage) -> str:
        """Send message to agent"""
        self.message_history.append({
            "sender": message.sender,
            "recipient": message.recipient,
            "message_type": message.message_type,
            "timestamp": message.timestamp,
            "message_id": message.message_id
        })
        await self.message_queue.put(message)
        return message.message_id

    async def subscribe(self, agent_name: str, message_types: List[str]):
        """Agent subscribes to message types"""
        for msg_type in message_types:
            self.subscriptions[msg_type].append(agent_name)

    async def register_handler(self, message_type: str, handler: Callable):
        """Register handler for message type"""
        self.handlers[message_type].append(handler)

    async def broadcast(self, message: AgentMessage) -> None:
        """Broadcast to all subscribed agents"""
        for agent_name in self.subscriptions[message.message_type]:
            await self.send_message(message)

    async def get_next_message(self) -> Optional[AgentMessage]:
        """Get next message from queue"""
        try:
            return self.message_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def get_history(self, agent_name: str = None) -> List[Dict]:
        """Get message history"""
        if agent_name:
            return [
                m for m in self.message_history
                if m["sender"] == agent_name or m["recipient"] == agent_name
            ]
        return self.message_history
```

**backend/agents/coordinator_agent.py:**
```python
from typing import Dict, List, Optional
import asyncio
from enum import Enum

class ExecutionPattern(Enum):
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"
    HIERARCHICAL = "hierarchical"
    DEBATE = "debate"
    FEEDBACK_LOOP = "feedback_loop"


class CoordinatorAgent:
    """Master agent that orchestrates all other agents"""

    def __init__(self, agents: Dict[str, 'Agent']):
        self.agents = agents
        self.communication_bus = AgentCommunicationBus()
        self.execution_history = []

    async def handle_query(self, query: str, user_context: Dict = None) -> Dict:
        """Main entry point for multi-agent handling"""

        # Step 1: Understand intent
        intent = await self.understand_intent(query, user_context)

        # Step 2: Plan execution
        plan = await self.plan_execution(intent)

        # Step 3: Execute plan
        results = await self.execute_plan(plan)

        # Step 4: Validate and synthesize
        final_response = await self.synthesize_results(results, query)

        return final_response

    async def understand_intent(self, query: str, context: Dict = None) -> Dict:
        """Use LLM to understand query intent"""

        prompt = f"""
        Analyze this user query and determine:
        1. Query type (search, analysis, verification, synthesis, comparison)
        2. Complexity level (simple, moderate, complex)
        3. Required domain (general, finance, legal, medical, technical)
        4. Required agents (SearchAgent, AnalysisAgent, VerificationAgent, etc.)
        5. Best execution pattern (sequential, parallel, debate)

        Query: {query}

        Return as JSON with keys: query_type, complexity, domain, required_agents, pattern
        """

        from backend.services.nvidia_llm_service import nvidia_llm_service
        response = await nvidia_llm_service.generate(prompt=prompt, json_mode=True)

        return response

    async def plan_execution(self, intent: Dict) -> Dict:
        """Create execution plan"""

        plan = {
            "query_id": uuid.uuid4().hex,
            "pattern": intent.get("pattern", "sequential"),
            "agents": intent.get("required_agents", ["SearchAgent", "SynthesisAgent"]),
            "steps": [],
            "dependencies": {},
            "estimated_duration": 0,
            "estimated_cost": 0
        }

        if plan["pattern"] == "sequential":
            plan["steps"] = [
                {"agent": "SearchAgent", "task": "retrieve_documents"},
                {"agent": "AnalysisAgent", "task": "analyze_documents"},
                {"agent": "VerificationAgent", "task": "verify_findings"},
                {"agent": "SynthesisAgent", "task": "generate_response"}
            ]

        elif plan["pattern"] == "parallel":
            plan["steps"] = [
                {"agent": "SearchAgent", "task": "retrieve_documents", "parallel_group": 1},
                {"agent": "AnalysisAgent", "task": "initial_analysis", "parallel_group": 1},
            ]
            plan["dependencies"] = {"SynthesisAgent": ["SearchAgent", "AnalysisAgent"]}

        return plan

    async def execute_plan(self, plan: Dict) -> Dict:
        """Execute the plan with error handling"""

        results = {}

        if plan["pattern"] == "sequential":
            results = await self.execute_sequential(plan)
        elif plan["pattern"] == "parallel":
            results = await self.execute_parallel(plan)
        elif plan["pattern"] == "debate":
            results = await self.execute_debate(plan)

        return results

    async def execute_sequential(self, plan: Dict) -> Dict:
        """Execute steps one after another"""

        results = {}
        previous_output = None

        for step in plan["steps"]:
            agent_name = step["agent"]
            task = step["task"]

            try:
                agent = self.agents.get(agent_name)
                if not agent:
                    raise ValueError(f"Agent {agent_name} not found")

                # Prepare input
                task_input = {
                    "task": task,
                    "previous_results": previous_output
                }

                # Execute
                start_time = time.time()
                result = await agent.execute(task_input)
                duration = time.time() - start_time

                results[agent_name] = {
                    "status": "success",
                    "result": result,
                    "duration": duration
                }

                previous_output = result

            except Exception as e:
                results[agent_name] = {
                    "status": "error",
                    "error": str(e)
                }

        return results

    async def execute_parallel(self, plan: Dict) -> Dict:
        """Execute steps concurrently"""

        tasks = {}

        for step in plan["steps"]:
            agent_name = step["agent"]
            agent = self.agents.get(agent_name)

            if agent:
                task = asyncio.create_task(agent.execute({"task": step["task"]}))
                tasks[agent_name] = task

        results = {}
        for agent_name, task in tasks.items():
            try:
                results[agent_name] = {
                    "status": "success",
                    "result": await task
                }
            except Exception as e:
                results[agent_name] = {
                    "status": "error",
                    "error": str(e)
                }

        return results

    async def synthesize_results(self, results: Dict, original_query: str) -> Dict:
        """Combine results into final response"""

        synthesis_agent = self.agents.get("SynthesisAgent")

        if not synthesis_agent:
            # Fallback: simple combination
            return {
                "response": "Combined results",
                "agents_used": list(results.keys()),
                "results": results
            }

        final = await synthesis_agent.execute({
            "task": "synthesize",
            "previous_results": results,
            "original_query": original_query
        })

        return final
```

**3. Register in main.py**

```python
# backend/main.py
from backend.agents.coordinator_agent import CoordinatorAgent

# Initialize agents
from backend.agents.specialized.search_agent import SearchAgent
from backend.agents.specialized.analysis_agent import AnalysisAgent
from backend.agents.specialized.verification_agent import VerificationAgent
from backend.agents.specialized.synthesis_agent import SynthesisAgent

agents_dict = {
    "SearchAgent": SearchAgent(),
    "AnalysisAgent": AnalysisAgent(),
    "VerificationAgent": VerificationAgent(),
    "SynthesisAgent": SynthesisAgent()
}

coordinator_agent = CoordinatorAgent(agents_dict)

# Add to FastAPI app
app.state.coordinator_agent = coordinator_agent
```

#### Week 3-4: Implement Specialized Agents

**backend/agents/specialized/search_agent.py:**
```python
from backend.agents.base_agent import Agent

class SearchAgent(Agent):
    """Specialized in document retrieval"""

    def __init__(self):
        super().__init__(
            name="SearchAgent",
            role="Information Retrieval Specialist"
        )

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute search task"""

        if task["task"] == "retrieve_documents":
            query = task.get("query", "")

            # Use existing retrieval service
            from backend.services.retrieval_service import retrieval_service

            results = await retrieval_service.retrieve(
                query=query,
                top_k=task.get("top_k", 12)
            )

            return {
                "documents": results["documents"],
                "scores": results["scores"],
                "search_strategy": "hybrid"
            }

        return {}
```

**backend/agents/specialized/analysis_agent.py:**
```python
class AnalysisAgent(Agent):
    """Specialized in data analysis"""

    def __init__(self):
        super().__init__(
            name="AnalysisAgent",
            role="Data Analysis Specialist"
        )

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute analysis task"""

        documents = task.get("previous_results", {}).get("documents", [])

        prompt = f"""
        Analyze the following documents:
        {documents}

        Provide:
        1. Key findings
        2. Important patterns
        3. Data insights
        """

        analysis = await self._call_llm(prompt)

        return {
            "analysis": analysis,
            "key_findings": self.extract_key_findings(analysis)
        }

    def extract_key_findings(self, analysis: str) -> List[str]:
        """Extract key findings from analysis"""
        # Simple extraction logic
        lines = analysis.split("\n")
        findings = [l.strip() for l in lines if l.strip().startswith(("•", "-"))]
        return findings
```

**backend/agents/specialized/verification_agent.py:**
```python
class VerificationAgent(Agent):
    """Specialized in fact verification"""

    def __init__(self):
        super().__init__(
            name="VerificationAgent",
            role="Fact Verification Specialist"
        )

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute verification task"""

        findings = task.get("previous_results", {})
        documents = task.get("previous_results", {}).get("documents", [])

        prompt = f"""
        Verify the following findings against the documents:
        {findings}

        Documents:
        {documents}

        Check:
        1. Factual accuracy
        2. Source attribution
        3. Potential hallucinations
        4. Confidence level

        Return: verified (bool), confidence (0-1), issues (list)
        """

        verification = await self._call_llm(prompt)

        return {
            "verification": verification,
            "confidence_score": self.extract_confidence(verification),
            "issues": self.extract_issues(verification)
        }

    def extract_confidence(self, verification: str) -> float:
        """Extract confidence score"""
        # Parse from LLM response
        return 0.85

    def extract_issues(self, verification: str) -> List[str]:
        """Extract issues found"""
        return []
```

**backend/agents/specialized/synthesis_agent.py:**
```python
class SynthesisAgent(Agent):
    """Specialized in response generation"""

    def __init__(self):
        super().__init__(
            name="SynthesisAgent",
            role="Response Generation Specialist"
        )

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Generate final response"""

        previous_results = task.get("previous_results", {})
        original_query = task.get("original_query", "")

        # Collect all information
        search_results = previous_results.get("SearchAgent", {}).get("result", {})
        analysis = previous_results.get("AnalysisAgent", {}).get("result", {})
        verification = previous_results.get("VerificationAgent", {}).get("result", {})

        prompt = f"""
        Original Query: {original_query}

        Search Results: {search_results}
        Analysis: {analysis}
        Verification: {verification}

        Generate a comprehensive, well-cited response that:
        1. Answers the original query completely
        2. Includes citations to sources
        3. Notes any uncertainties
        4. Provides actionable insights
        """

        response = await self._call_llm(prompt)

        return {
            "response": response,
            "sources": self.extract_sources(search_results),
            "confidence": verification.get("confidence_score", 0.5),
            "reasoning_trace": self.build_reasoning_trace(previous_results)
        }

    def extract_sources(self, search_results: Dict) -> List[Dict]:
        """Extract and format sources"""
        return search_results.get("documents", [])

    def build_reasoning_trace(self, results: Dict) -> List[Dict]:
        """Build step-by-step reasoning trace"""
        trace = []
        for agent, result in results.items():
            if result.get("status") == "success":
                trace.append({
                    "agent": agent,
                    "action": result.get("result", {}).get("task", ""),
                    "output": result.get("result", {})
                })
        return trace
```

**4. Add API Endpoint for Multi-Agent Chat**

**backend/api/multi_agent_routes.py:**
```python
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from backend.schemas.chat_schema import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["multi-agent"])

@router.post("/multi-agent")
async def chat_multi_agent(
    request: ChatRequest,
    coordinator = Depends(get_coordinator_agent)
) -> ChatResponse:
    """Handle query with multi-agent system"""

    # Execute with coordinator
    result = await coordinator.handle_query(
        query=request.query,
        user_context={"session_id": request.session_id}
    )

    return ChatResponse(
        message=result.get("response", ""),
        agents_used=result.get("agents", []),
        reasoning_trace=result.get("reasoning_trace", []),
        sources=result.get("sources", []),
        confidence=result.get("confidence", 0.5)
    )


@router.get("/agents/list")
async def list_agents(coordinator = Depends(get_coordinator_agent)):
    """List available agents and their capabilities"""

    agents_info = {}
    for agent_name, agent in coordinator.agents.items():
        agents_info[agent_name] = {
            "role": agent.role,
            "capabilities": agent.tools.keys(),
            "performance": agent.performance_metrics
        }

    return agents_info
```

**Register in main.py:**
```python
from backend.api.multi_agent_routes import router as multi_agent_router
app.include_router(multi_agent_router)
```

---

### Phase 2: Integration & Testing (Weeks 5-8)

#### Add to Docker Compose
```yaml
# docker-compose.yml - add if needed
services:
  # ... existing services ...

  # No additional services needed - agents run within API
  # But add Redis for agent message queue (if not using in-memory)
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

#### Integration Tests

**backend/tests/agents/test_coordinator.py:**
```python
import pytest
from backend.agents.coordinator_agent import CoordinatorAgent

@pytest.mark.asyncio
async def test_coordinator_handles_simple_query():
    """Test basic coordinator functionality"""

    # Setup
    agents = {
        "SearchAgent": MockSearchAgent(),
        "SynthesisAgent": MockSynthesisAgent()
    }
    coordinator = CoordinatorAgent(agents)

    # Execute
    result = await coordinator.handle_query("What is AI?")

    # Assert
    assert result is not None
    assert "response" in result
    assert len(result.get("agents", [])) > 0


@pytest.mark.asyncio
async def test_coordinator_parallel_execution():
    """Test parallel agent execution"""

    coordinator = CoordinatorAgent(agents)

    plan = {
        "pattern": "parallel",
        "steps": [
            {"agent": "SearchAgent", "task": "search"},
            {"agent": "AnalysisAgent", "task": "analyze"}
        ]
    }

    results = await coordinator.execute_parallel(plan)

    assert len(results) == 2
    assert all(r.get("status") == "success" for r in results.values())
```

---

## Migration Strategy

### Option A: Parallel Deployment (Recommended)
```
Week 1-4: Build agents alongside existing system
Week 5-6: Deploy agents on separate endpoint (/chat/multi-agent)
Week 7: A/B test both systems
Week 8: Monitor performance and user feedback
Week 9+: Migrate users gradually to multi-agent
```

### Option B: Gradual Replacement
```
Week 1-4: Build agents
Week 5: Replace components one at a time
Week 6: Full multi-agent integration
```

---

## Deployment Checklist

- [ ] All agent classes implemented
- [ ] Communication bus tested
- [ ] Coordinator agent working
- [ ] Unit tests passing (85%+ coverage)
- [ ] Integration tests passing
- [ ] Performance benchmarks acceptable
- [ ] Documentation complete
- [ ] API endpoints registered
- [ ] Database schema updated
- [ ] Monitoring/logging configured
- [ ] Cost tracking implemented
- [ ] Fallback mechanisms tested
- [ ] Error handling comprehensive
- [ ] Load testing completed
- [ ] Security review passed

---

## Quick Reference: Common Tasks

### Add a New Agent
1. Create file: `backend/agents/specialized/your_agent.py`
2. Inherit from `Agent` base class
3. Implement `execute()` method
4. Register in `CoordinatorAgent.__init__`
5. Add tests in `backend/tests/agents/`

### Add Agent Tool
1. Create: `backend/agents/tools/your_tool.py`
2. Add to agent: `self.tools["tool_name"] = YourTool()`
3. Call in execute: `await self.tools["tool_name"].execute(input)`

### Test Agents
```bash
pytest backend/tests/agents/
pytest -k "test_coordinator" -v
pytest backend/tests/agents/test_search_agent.py -cov
```

### Monitor Agent Performance
```python
# Check metrics
coordinator.agents["SearchAgent"].performance_metrics

# View communication history
coordinator.communication_bus.get_history("SearchAgent")
```

---

## Resources

- **Full Architecture:** See `MULTI_AGENT_ARCHITECTURE.md`
- **API Documentation:** See FastAPI docs at `/docs` after deployment
- **Example Agents:** Implement SearchAgent, AnalysisAgent as templates
- **Testing Guide:** See `backend/tests/agents/` examples

---

**Implementation Timeline:** 6-8 weeks for Phase 1 (Foundation + Core Agents)
**Next Phase:** Domain-specific agents (Finance, Legal, Medical, Technical)
**Full Rollout:** Target Q3 2026

