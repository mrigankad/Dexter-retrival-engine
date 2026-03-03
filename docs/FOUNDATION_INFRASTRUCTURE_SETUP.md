# Foundation Infrastructure Setup - Complete Implementation

**Duration:** Weeks 1-2
**Objective:** Build core agent framework
**Files to Create:** 4 main files + tests
**Time Estimate:** 1-2 weeks for 1 engineer

---

## 📁 Step 1: Create Directory Structure

```bash
# Navigate to backend directory
cd backend

# Create agents directory structure
mkdir -p agents/{base,specialized,domain,support,patterns,tools}
mkdir -p tests/agents/{unit,integration}

# Create __init__.py files
touch agents/__init__.py
touch agents/base/__init__.py
touch agents/specialized/__init__.py
touch agents/domain/__init__.py
touch agents/support/__init__.py
touch agents/patterns/__init__.py
touch agents/tools/__init__.py
touch tests/agents/__init__.py
touch tests/agents/unit/__init__.py
touch tests/agents/integration/__init__.py
```

**Result:**
```
backend/
├── agents/
│   ├── __init__.py
│   ├── base/
│   │   ├── __init__.py
│   │   ├── base_agent.py          ← Create
│   │   ├── agent_memory.py        ← Create
│   │   └── execution_engine.py    ← Create
│   ├── communication/
│   │   ├── __init__.py
│   │   └── communication_bus.py   ← Create
│   ├── specialized/
│   │   ├── __init__.py
│   │   ├── search_agent.py        ← Phase 2
│   │   ├── analysis_agent.py      ← Phase 2
│   │   └── ...
│   └── patterns/
│       └── ...
│
└── tests/
    └── agents/
        ├── unit/
        │   ├── test_base_agent.py
        │   ├── test_agent_memory.py
        │   └── test_communication_bus.py
        └── integration/
            └── test_full_flow.py
```

---

## 🔧 Step 2: Create Base Agent Class

**File:** `backend/agents/base/base_agent.py`

```python
"""
Base Agent Class

All agents (SearchAgent, AnalysisAgent, etc.) inherit from this class.
Provides common functionality for all agents:
- Task execution
- Memory management
- Performance tracking
- Error handling
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import uuid
from datetime import datetime
import asyncio
import logging

logger = logging.getLogger(__name__)


class Agent(ABC):
    """
    Abstract base class for all agents.

    Every agent must:
    1. Have a name and role
    2. Be able to execute tasks
    3. Maintain memory of previous interactions
    4. Track its performance metrics
    """

    def __init__(self, name: str, role: str, model_name: str = "llama-3.3-nemotron"):
        """
        Initialize agent.

        Args:
            name: Agent name (e.g., "SearchAgent")
            role: Agent role description (e.g., "Information Retrieval Specialist")
            model_name: LLM model to use (default: NVIDIA Nemotron)
        """
        self.id = str(uuid.uuid4())
        self.name = name
        self.role = role
        self.model_name = model_name

        # Agent capabilities
        self.tools: Dict[str, Any] = {}  # Tools available to this agent
        self.memory = None  # Initialized separately to avoid circular imports

        # Performance tracking
        self.performance_metrics = {
            "total_tasks": 0,
            "successful_tasks": 0,
            "failed_tasks": 0,
            "total_response_time": 0.0,
            "avg_response_time": 0.0,
            "avg_quality_score": 0.0,
            "success_rate": 0.0,
            "last_updated": None
        }

        # Execution history
        self.execution_history: List[Dict[str, Any]] = []

        logger.info(f"Initialized agent: {self.name} ({self.role})")

    async def initialize_memory(self):
        """Initialize memory (call this after agent creation)"""
        from backend.agents.base.agent_memory import AgentMemory
        self.memory = AgentMemory(self.name)

    @abstractmethod
    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task.

        This method must be implemented by subclasses.

        Args:
            task: Task description with parameters
                {
                    "task": "retrieve_documents",
                    "query": "what is AI?",
                    "top_k": 10,
                    "previous_results": {...}  # Results from previous agents
                }

        Returns:
            Task result
                {
                    "documents": [...],
                    "status": "success",
                    "metadata": {...}
                }
        """
        pass

    async def think(self, context: str) -> str:
        """
        Agent reasoning process.

        Used by agents to reason through problems before executing.
        Optional - subclasses can override.

        Args:
            context: Context for reasoning

        Returns:
            Reasoning output
        """
        # Default implementation - subclasses can override
        return ""

    async def observe(self, observation: Dict[str, Any]) -> None:
        """
        Learn from observation/feedback.

        Called when agent receives feedback about its execution.

        Args:
            observation: Feedback data
                {
                    "success": True,
                    "quality_score": 0.85,
                    "feedback": "Good results",
                    "user_rating": 5
                }
        """
        if self.memory:
            observation["timestamp"] = datetime.now().isoformat()
            observation["agent"] = self.name
            await self.memory.store(observation)

    async def learn_from_feedback(self, feedback: Dict[str, Any]) -> None:
        """
        Learn from user feedback.

        Store feedback for future improvements.
        Can be used for fine-tuning or strategy adjustments.

        Args:
            feedback: User feedback
        """
        await self.observe({
            "type": "user_feedback",
            "feedback": feedback,
            "importance": feedback.get("importance", 0.5)
        })

    def update_performance(self,
                          success: bool,
                          quality_score: float,
                          response_time: float) -> None:
        """
        Update agent performance metrics.

        Called after each task execution.

        Args:
            success: Whether task succeeded
            quality_score: Quality of result (0-1)
            response_time: Time taken in seconds
        """
        self.performance_metrics["total_tasks"] += 1

        if success:
            self.performance_metrics["successful_tasks"] += 1
        else:
            self.performance_metrics["failed_tasks"] += 1

        # Update total response time
        self.performance_metrics["total_response_time"] += response_time

        # Recalculate averages
        total = self.performance_metrics["total_tasks"]

        # Average response time
        self.performance_metrics["avg_response_time"] = (
            self.performance_metrics["total_response_time"] / total
        )

        # Average quality score (moving average)
        current_avg = self.performance_metrics["avg_quality_score"]
        self.performance_metrics["avg_quality_score"] = (
            (current_avg * (total - 1) + quality_score) / total
        )

        # Success rate
        self.performance_metrics["success_rate"] = (
            self.performance_metrics["successful_tasks"] / total
        )

        # Last updated
        self.performance_metrics["last_updated"] = datetime.now().isoformat()

        logger.debug(
            f"{self.name} - Tasks: {total}, Success Rate: "
            f"{self.performance_metrics['success_rate']:.1%}, "
            f"Avg Quality: {self.performance_metrics['avg_quality_score']:.2f}"
        )

    def record_execution(self, task_name: str, status: str, duration: float, metadata: Dict = None):
        """
        Record task execution in history.

        Args:
            task_name: Name of task executed
            status: "success" or "failed"
            duration: Time taken in seconds
            metadata: Additional metadata
        """
        execution_record = {
            "task_name": task_name,
            "status": status,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {}
        }
        self.execution_history.append(execution_record)

    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics"""
        return self.performance_metrics.copy()

    def get_execution_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent execution history"""
        return self.execution_history[-limit:]

    async def reset(self):
        """Reset agent state (for testing)"""
        self.execution_history = []
        if self.memory:
            await self.memory.clear()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, role={self.role})>"


# Example subclass for testing
class TestAgent(Agent):
    """Simple test agent for testing base class"""

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Simple test execution"""
        return {
            "status": "success",
            "result": f"Executed {task.get('task', 'unknown')}",
            "agent": self.name
        }
```

---

## 💾 Step 3: Create Agent Memory System

**File:** `backend/agents/base/agent_memory.py`

```python
"""
Agent Memory System

Manages short-term and long-term memory for agents:
- Short-term: Current conversation context (last 20 items)
- Long-term: Important facts and learnings (persisted)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import logging

logger = logging.getLogger(__name__)


class AgentMemory:
    """
    Memory system for agents.

    Two-tier memory:
    1. Short-term: Recent interactions (in-memory)
    2. Long-term: Important facts (could be persisted to DB)
    """

    def __init__(self, agent_name: str, max_short_term: int = 20):
        """
        Initialize memory for an agent.

        Args:
            agent_name: Name of agent owning this memory
            max_short_term: Max items in short-term memory before rolling
        """
        self.agent_name = agent_name
        self.max_short_term = max_short_term

        # Short-term memory (current conversation)
        self.short_term: List[Dict[str, Any]] = []

        # Long-term memory (important facts)
        self.long_term: List[Dict[str, Any]] = []

        logger.info(f"Initialized memory for agent: {agent_name}")

    async def store(self, item: Dict[str, Any]) -> None:
        """
        Store item in memory.

        If item is marked as important (importance > 0.7),
        it moves to long-term memory.

        Args:
            item: Item to store
                {
                    "type": "observation",
                    "content": "Some fact",
                    "importance": 0.8,  # 0-1, default 0.5
                    "timestamp": "2026-02-27T..."
                }
        """
        # Add metadata if not present
        if "timestamp" not in item:
            item["timestamp"] = datetime.now().isoformat()
        if "agent" not in item:
            item["agent"] = self.agent_name

        # Determine importance
        importance = item.get("importance", 0.5)

        # Store in short-term
        self.short_term.append(item)

        # If important, also store in long-term
        if importance > 0.7:
            self.long_term.append(item)
            logger.debug(
                f"Stored important item in long-term memory for {self.agent_name}"
            )

        # Manage short-term memory size
        if len(self.short_term) > self.max_short_term:
            # Move oldest items to long-term if important
            for old_item in self.short_term[:-self.max_short_term]:
                if old_item.get("importance", 0.5) > 0.6:
                    if old_item not in self.long_term:
                        self.long_term.append(old_item)

            # Keep only recent items
            self.short_term = self.short_term[-self.max_short_term:]

    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieve relevant memories based on query.

        Simple implementation: keyword matching.
        Can be enhanced with semantic search.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of relevant memories
        """
        query_lower = query.lower()
        relevant = []

        # Search both short-term and long-term
        all_memories = self.short_term + self.long_term

        for memory in all_memories:
            # Simple keyword matching
            content = str(memory).lower()
            if query_lower in content:
                relevant.append(memory)

        # Return top_k most recent
        relevant.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return relevant[:top_k]

    async def retrieve_by_type(self, memory_type: str) -> List[Dict[str, Any]]:
        """
        Retrieve memories of specific type.

        Args:
            memory_type: Type of memory to retrieve

        Returns:
            List of memories matching type
        """
        all_memories = self.short_term + self.long_term
        return [m for m in all_memories if m.get("type") == memory_type]

    def get_short_term_summary(self) -> str:
        """Get summary of short-term memory"""
        return json.dumps(self.short_term, indent=2, default=str)

    def get_long_term_summary(self) -> str:
        """Get summary of long-term memory"""
        return json.dumps(self.long_term, indent=2, default=str)

    async def clear(self) -> None:
        """Clear all memory (for testing or GDPR compliance)"""
        self.short_term = []
        self.long_term = []
        logger.info(f"Cleared memory for agent: {self.agent_name}")

    async def clear_short_term(self) -> None:
        """Clear only short-term memory"""
        self.short_term = []

    def __len__(self) -> int:
        """Get total memory items"""
        return len(self.short_term) + len(self.long_term)

    def __repr__(self) -> str:
        return (
            f"<AgentMemory(agent={self.agent_name}, "
            f"short_term={len(self.short_term)}, "
            f"long_term={len(self.long_term)})>"
        )
```

---

## 📡 Step 4: Create Communication Bus

**File:** `backend/agents/communication/communication_bus.py`

```python
"""
Agent Communication Bus

Enables inter-agent communication.
Central hub for agents to send/receive messages.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
import asyncio
from collections import defaultdict
from datetime import datetime
import uuid
import logging

logger = logging.getLogger(__name__)


@dataclass
class AgentMessage:
    """Message between agents"""

    sender: str
    recipient: str
    message_type: str  # "request", "response", "update", "query"
    content: Dict
    priority: int = 1  # 1=low, 5=high
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

    def to_dict(self) -> Dict:
        """Convert message to dictionary"""
        return {
            "message_id": self.message_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "message_type": self.message_type,
            "content": self.content,
            "priority": self.priority,
            "timestamp": self.timestamp
        }


class AgentCommunicationBus:
    """
    Central communication hub for agents.

    Features:
    - Message passing between agents
    - Pub/Sub pattern for events
    - Message history tracking
    - Priority queue support
    """

    def __init__(self):
        """Initialize communication bus"""
        # Message queue (agents pick up their messages)
        self.message_queue = asyncio.Queue()

        # Message subscriptions (agent_name -> [message_types])
        self.subscriptions: Dict[str, List[str]] = defaultdict(list)

        # Message history
        self.message_history: List[Dict] = []

        # Handlers for different message types
        self.handlers: Dict[str, List[Callable]] = defaultdict(list)

        # Agent registry
        self.agents: Dict[str, Any] = {}

        logger.info("Initialized AgentCommunicationBus")

    async def send_message(self, message: AgentMessage) -> str:
        """
        Send message to recipient agent.

        Args:
            message: AgentMessage to send

        Returns:
            Message ID
        """
        # Record in history
        self.message_history.append(message.to_dict())

        # Add to queue
        await self.message_queue.put(message)

        logger.debug(
            f"Message sent: {message.sender} → {message.recipient} "
            f"({message.message_type})"
        )

        return message.message_id

    async def broadcast(self, message: AgentMessage) -> None:
        """
        Broadcast message to all subscribed agents.

        Args:
            message: AgentMessage to broadcast
        """
        subscribed_agents = self.subscriptions.get(message.message_type, [])

        for agent_name in subscribed_agents:
            if agent_name != message.sender:  # Don't send to self
                message.recipient = agent_name
                await self.send_message(message)

    async def subscribe(self, agent_name: str, message_types: List[str]) -> None:
        """
        Agent subscribes to message types.

        Args:
            agent_name: Name of subscribing agent
            message_types: List of message types to receive
        """
        for msg_type in message_types:
            if agent_name not in self.subscriptions[msg_type]:
                self.subscriptions[msg_type].append(agent_name)

        logger.debug(
            f"Agent {agent_name} subscribed to: {message_types}"
        )

    async def unsubscribe(self, agent_name: str, message_types: List[str]) -> None:
        """
        Agent unsubscribes from message types.

        Args:
            agent_name: Name of agent
            message_types: Message types to unsubscribe from
        """
        for msg_type in message_types:
            if agent_name in self.subscriptions[msg_type]:
                self.subscriptions[msg_type].remove(agent_name)

    async def register_handler(self,
                              message_type: str,
                              handler: Callable) -> None:
        """
        Register handler for specific message type.

        Args:
            message_type: Type of message to handle
            handler: Async callable to handle message
        """
        self.handlers[message_type].append(handler)
        logger.debug(f"Handler registered for message type: {message_type}")

    async def get_next_message(self, agent_name: str) -> Optional[AgentMessage]:
        """
        Get next message for an agent.

        Non-blocking - returns None if no messages.

        Args:
            agent_name: Name of agent

        Returns:
            Next message or None
        """
        try:
            message = self.message_queue.get_nowait()
            if message.recipient == agent_name:
                return message
            else:
                # Put back if not for this agent
                await self.message_queue.put(message)
        except asyncio.QueueEmpty:
            pass

        return None

    def get_history(self, agent_name: str = None, limit: int = 100) -> List[Dict]:
        """
        Get message history.

        Args:
            agent_name: Filter by agent name (optional)
            limit: Maximum messages to return

        Returns:
            List of message history
        """
        history = self.message_history

        if agent_name:
            history = [
                m for m in history
                if m["sender"] == agent_name or m["recipient"] == agent_name
            ]

        return history[-limit:]

    def get_statistics(self) -> Dict:
        """Get communication statistics"""
        return {
            "total_messages": len(self.message_history),
            "active_subscriptions": len(self.subscriptions),
            "registered_agents": len(self.agents),
            "queue_size": self.message_queue.qsize()
        }

    async def clear_history(self) -> None:
        """Clear message history"""
        self.message_history = []
        logger.info("Message history cleared")

    def __repr__(self) -> str:
        return (
            f"<AgentCommunicationBus(messages={len(self.message_history)}, "
            f"subscriptions={len(self.subscriptions)})>"
        )
```

---

## ⚙️ Step 5: Create Execution Engine

**File:** `backend/agents/base/execution_engine.py`

```python
"""
Execution Engine

Manages execution of agent plans:
- Sequential execution (one after another)
- Parallel execution (concurrent)
- Error handling and retries
"""

import asyncio
from typing import Dict, List, Any, Callable
import time
import logging

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Executes agent plans.

    Supports multiple execution patterns:
    1. Sequential: Agent A → Agent B → Agent C
    2. Parallel: Agent A, B, C all at once
    """

    def __init__(self, max_retries: int = 3, timeout: float = 300):
        """
        Initialize execution engine.

        Args:
            max_retries: Max retries on failure
            timeout: Max time for execution in seconds
        """
        self.max_retries = max_retries
        self.timeout = timeout
        self.execution_history: List[Dict[str, Any]] = []

    async def execute_sequential(self,
                                plan: Dict[str, Any],
                                agents: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute steps one after another.

        Each step can use results from previous steps.

        Args:
            plan: Execution plan with steps
                {
                    "steps": [
                        {"agent": "SearchAgent", "task": "retrieve"},
                        {"agent": "AnalysisAgent", "task": "analyze"}
                    ]
                }
            agents: Dict of available agents

        Returns:
            Results from all agents
        """
        results = {}
        previous_output = None

        logger.info(f"Starting sequential execution with {len(plan['steps'])} steps")

        for step_idx, step in enumerate(plan["steps"], 1):
            agent_name = step.get("agent")
            task_name = step.get("task")

            agent = agents.get(agent_name)
            if not agent:
                raise ValueError(f"Agent '{agent_name}' not found")

            logger.info(f"Step {step_idx}: Executing {agent_name} ({task_name})")

            # Prepare task input
            task_input = {
                "task": task_name,
                "previous_results": previous_output,
                **{k: v for k, v in step.items() if k not in ["agent", "task"]}
            }

            # Execute with timeout and retry
            try:
                start_time = time.time()
                result = await asyncio.wait_for(
                    self._execute_with_retry(agent, task_input),
                    timeout=self.timeout
                )
                duration = time.time() - start_time

                results[agent_name] = {
                    "status": "success",
                    "result": result,
                    "duration": duration,
                    "step": step_idx
                }

                logger.info(
                    f"Step {step_idx} completed in {duration:.2f}s"
                )

                previous_output = result

            except asyncio.TimeoutError:
                logger.error(f"Step {step_idx} timed out after {self.timeout}s")
                results[agent_name] = {
                    "status": "timeout",
                    "error": f"Execution timed out after {self.timeout}s",
                    "step": step_idx
                }
                raise

            except Exception as e:
                logger.error(f"Step {step_idx} failed: {str(e)}")
                results[agent_name] = {
                    "status": "error",
                    "error": str(e),
                    "step": step_idx
                }
                raise

        # Record execution
        self.execution_history.append({
            "pattern": "sequential",
            "steps": len(plan["steps"]),
            "status": "success",
            "timestamp": time.time()
        })

        return results

    async def execute_parallel(self,
                              plan: Dict[str, Any],
                              agents: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute steps concurrently.

        All agents run at same time.
        Can wait for all to complete or first to succeed.

        Args:
            plan: Execution plan
            agents: Available agents

        Returns:
            Results from all agents
        """
        tasks = {}
        results = {}

        logger.info(f"Starting parallel execution with {len(plan['steps'])} steps")

        # Create tasks for all steps
        for step in plan["steps"]:
            agent_name = step.get("agent")
            task_name = step.get("task")

            agent = agents.get(agent_name)
            if not agent:
                raise ValueError(f"Agent '{agent_name}' not found")

            task_input = {
                "task": task_name,
                **{k: v for k, v in step.items() if k not in ["agent", "task"]}
            }

            # Create task
            task = asyncio.create_task(
                self._execute_with_timeout_and_retry(agent, task_input)
            )
            tasks[agent_name] = (task, step)

        # Wait for all tasks to complete
        logger.info("Waiting for all parallel tasks to complete...")

        for agent_name, (task, step) in tasks.items():
            try:
                start_time = time.time()
                result = await task
                duration = time.time() - start_time

                results[agent_name] = {
                    "status": "success",
                    "result": result,
                    "duration": duration
                }

                logger.info(f"{agent_name} completed in {duration:.2f}s")

            except Exception as e:
                logger.error(f"{agent_name} failed: {str(e)}")
                results[agent_name] = {
                    "status": "error",
                    "error": str(e)
                }

        # Record execution
        self.execution_history.append({
            "pattern": "parallel",
            "steps": len(plan["steps"]),
            "status": "success",
            "timestamp": time.time()
        })

        return results

    async def _execute_with_retry(self,
                                 agent: Any,
                                 task_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute agent task with retry logic.

        Args:
            agent: Agent to execute
            task_input: Task input

        Returns:
            Task result
        """
        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(f"Attempt {attempt}/{self.max_retries} for {agent.name}")
                result = await agent.execute(task_input)
                return result

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Attempt {attempt} failed for {agent.name}: {str(e)}"
                )

                if attempt < self.max_retries:
                    # Wait before retry (exponential backoff)
                    wait_time = 2 ** (attempt - 1)
                    logger.info(f"Retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)

        # All retries failed
        raise last_error

    async def _execute_with_timeout_and_retry(self,
                                             agent: Any,
                                             task_input: Dict[str, Any]) -> Dict[str, Any]:
        """Execute with both timeout and retry"""
        try:
            return await asyncio.wait_for(
                self._execute_with_retry(agent, task_input),
                timeout=self.timeout
            )
        except asyncio.TimeoutError:
            raise TimeoutError(f"Execution timed out after {self.timeout}s")

    def get_history(self) -> List[Dict[str, Any]]:
        """Get execution history"""
        return self.execution_history.copy()

    def __repr__(self) -> str:
        return (
            f"<ExecutionEngine(max_retries={self.max_retries}, "
            f"timeout={self.timeout})>"
        )
```

---

## 🧪 Step 6: Create Tests

### Test File 1: Base Agent Tests

**File:** `backend/tests/agents/unit/test_base_agent.py`

```python
"""Tests for base agent class"""

import pytest
import asyncio
from backend.agents.base.base_agent import Agent, TestAgent


@pytest.fixture
def test_agent():
    """Create test agent"""
    agent = TestAgent(name="TestAgent", role="Test Role")
    return agent


@pytest.mark.asyncio
async def test_agent_creation(test_agent):
    """Test agent creation"""
    assert test_agent.name == "TestAgent"
    assert test_agent.role == "Test Role"
    assert test_agent.id is not None
    assert len(test_agent.id) > 0


@pytest.mark.asyncio
async def test_agent_execute(test_agent):
    """Test agent execution"""
    result = await test_agent.execute({
        "task": "test_task"
    })
    assert result is not None
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_agent_memory_initialization(test_agent):
    """Test agent memory initialization"""
    await test_agent.initialize_memory()
    assert test_agent.memory is not None


@pytest.mark.asyncio
async def test_performance_tracking(test_agent):
    """Test performance metrics tracking"""
    # Initial metrics
    assert test_agent.performance_metrics["total_tasks"] == 0

    # Update performance
    test_agent.update_performance(
        success=True,
        quality_score=0.85,
        response_time=1.5
    )

    # Check metrics updated
    assert test_agent.performance_metrics["total_tasks"] == 1
    assert test_agent.performance_metrics["successful_tasks"] == 1
    assert test_agent.performance_metrics["avg_quality_score"] == 0.85
    assert test_agent.performance_metrics["success_rate"] == 1.0


@pytest.mark.asyncio
async def test_execution_history(test_agent):
    """Test execution history recording"""
    test_agent.record_execution(
        task_name="test_task",
        status="success",
        duration=1.5,
        metadata={"key": "value"}
    )

    history = test_agent.get_execution_history()
    assert len(history) == 1
    assert history[0]["task_name"] == "test_task"
    assert history[0]["status"] == "success"


@pytest.mark.asyncio
async def test_reset_agent(test_agent):
    """Test resetting agent state"""
    # Add some history
    test_agent.record_execution("task", "success", 1.0)
    assert len(test_agent.execution_history) == 1

    # Reset
    await test_agent.reset()
    assert len(test_agent.execution_history) == 0
```

### Test File 2: Agent Memory Tests

**File:** `backend/tests/agents/unit/test_agent_memory.py`

```python
"""Tests for agent memory"""

import pytest
from backend.agents.base.agent_memory import AgentMemory


@pytest.fixture
def memory():
    """Create memory instance"""
    return AgentMemory("TestAgent")


@pytest.mark.asyncio
async def test_memory_creation(memory):
    """Test memory creation"""
    assert memory.agent_name == "TestAgent"
    assert len(memory.short_term) == 0
    assert len(memory.long_term) == 0


@pytest.mark.asyncio
async def test_store_in_memory(memory):
    """Test storing items"""
    item = {"type": "observation", "content": "test content"}
    await memory.store(item)

    assert len(memory.short_term) == 1
    assert "timestamp" in memory.short_term[0]


@pytest.mark.asyncio
async def test_store_important_item(memory):
    """Test storing important items"""
    item = {
        "type": "fact",
        "content": "important fact",
        "importance": 0.9
    }
    await memory.store(item)

    assert len(memory.long_term) == 1
    assert memory.short_term[0] == memory.long_term[0]


@pytest.mark.asyncio
async def test_retrieve_by_query(memory):
    """Test retrieving by query"""
    await memory.store({"type": "fact", "content": "Python is great"})
    await memory.store({"type": "fact", "content": "Java is powerful"})

    results = await memory.retrieve("Python")
    assert len(results) > 0
    assert "Python" in results[0]["content"]


@pytest.mark.asyncio
async def test_clear_memory(memory):
    """Test clearing memory"""
    await memory.store({"content": "test"})
    assert len(memory) > 0

    await memory.clear()
    assert len(memory) == 0
```

### Test File 3: Communication Bus Tests

**File:** `backend/tests/agents/unit/test_communication_bus.py`

```python
"""Tests for communication bus"""

import pytest
from backend.agents.communication.communication_bus import (
    AgentCommunicationBus,
    AgentMessage
)


@pytest.fixture
def bus():
    """Create communication bus"""
    return AgentCommunicationBus()


@pytest.mark.asyncio
async def test_bus_creation(bus):
    """Test bus creation"""
    assert bus is not None
    assert len(bus.message_history) == 0


@pytest.mark.asyncio
async def test_send_message(bus):
    """Test sending message"""
    message = AgentMessage(
        sender="Agent1",
        recipient="Agent2",
        message_type="request",
        content={"query": "test"}
    )

    msg_id = await bus.send_message(message)
    assert msg_id is not None
    assert len(bus.message_history) == 1


@pytest.mark.asyncio
async def test_subscribe(bus):
    """Test subscription"""
    await bus.subscribe("Agent1", ["request", "response"])

    assert "Agent1" in bus.subscriptions["request"]
    assert "Agent1" in bus.subscriptions["response"]


@pytest.mark.asyncio
async def test_broadcast(bus):
    """Test broadcasting"""
    await bus.subscribe("Agent1", ["update"])
    await bus.subscribe("Agent2", ["update"])

    message = AgentMessage(
        sender="Agent3",
        recipient="",  # Will be set by broadcast
        message_type="update",
        content={"data": "broadcast"}
    )

    await bus.broadcast(message)

    history = bus.get_history()
    assert len(history) >= 2  # Messages to Agent1 and Agent2


@pytest.mark.asyncio
async def test_message_history(bus):
    """Test message history"""
    msg1 = AgentMessage("A", "B", "request", {"q": "1"})
    msg2 = AgentMessage("C", "D", "request", {"q": "2"})

    await bus.send_message(msg1)
    await bus.send_message(msg2)

    history = bus.get_history()
    assert len(history) == 2

    history_a = bus.get_history("A")
    assert len(history_a) == 1
```

---

## 🔗 Step 7: Update Main FastAPI App

**File:** `backend/main.py`

Add this to your FastAPI app:

```python
# At the top of main.py, add imports
from backend.agents.base.base_agent import Agent
from backend.agents.base.agent_memory import AgentMemory
from backend.agents.communication.communication_bus import AgentCommunicationBus
from backend.agents.base.execution_engine import ExecutionEngine

# In the FastAPI app initialization, add:

# Initialize agent infrastructure
app.state.communication_bus = AgentCommunicationBus()
app.state.execution_engine = ExecutionEngine(max_retries=3, timeout=300)

# Log that agents are initialized
import logging
logger = logging.getLogger(__name__)
logger.info("Agent infrastructure initialized")
```

---

## ✅ Step 8: Verify Everything Works

### 1. Run Tests

```bash
# Navigate to project root
cd /path/to/Context\ Rag

# Run all foundation tests
pytest backend/tests/agents/unit/ -v

# Output should show:
# test_base_agent.py::test_agent_creation PASSED
# test_base_agent.py::test_agent_execute PASSED
# test_agent_memory.py::test_memory_creation PASSED
# test_agent_memory.py::test_store_in_memory PASSED
# test_communication_bus.py::test_bus_creation PASSED
# ... etc
```

### 2. Check Coverage

```bash
# Run with coverage report
pytest backend/tests/agents/unit/ --cov=backend/agents --cov-report=html

# View coverage
open htmlcov/index.html
```

### 3. Simple Manual Test

Create `test_foundation.py` in project root:

```python
"""Quick manual test of foundation"""

import asyncio
from backend.agents.base.base_agent import TestAgent
from backend.agents.base.agent_memory import AgentMemory
from backend.agents.communication.communication_bus import AgentCommunicationBus
from backend.agents.base.execution_engine import ExecutionEngine


async def main():
    """Test foundation infrastructure"""

    print("=" * 50)
    print("Foundation Infrastructure Test")
    print("=" * 50)

    # Test 1: Agent Creation
    print("\n1. Creating agent...")
    agent = TestAgent(name="TestAgent", role="Tester")
    print(f"   ✓ Agent created: {agent}")

    # Test 2: Initialize Memory
    print("\n2. Initializing memory...")
    await agent.initialize_memory()
    print(f"   ✓ Memory initialized: {agent.memory}")

    # Test 3: Store in Memory
    print("\n3. Storing in memory...")
    await agent.memory.store({
        "type": "fact",
        "content": "Python is awesome",
        "importance": 0.9
    })
    print(f"   ✓ Stored. Memory size: {len(agent.memory)}")

    # Test 4: Retrieve from Memory
    print("\n4. Retrieving from memory...")
    results = await agent.memory.retrieve("Python")
    print(f"   ✓ Retrieved {len(results)} items")

    # Test 5: Execute Task
    print("\n5. Executing task...")
    result = await agent.execute({"task": "test_task"})
    print(f"   ✓ Task executed: {result['status']}")

    # Test 6: Communication Bus
    print("\n6. Testing communication bus...")
    bus = AgentCommunicationBus()
    from backend.agents.communication.communication_bus import AgentMessage

    msg = AgentMessage(
        sender="Agent1",
        recipient="Agent2",
        message_type="request",
        content={"query": "test"}
    )
    msg_id = await bus.send_message(msg)
    print(f"   ✓ Message sent: {msg_id}")

    # Test 7: Execution Engine
    print("\n7. Testing execution engine...")
    engine = ExecutionEngine()
    print(f"   ✓ Engine created: {engine}")

    print("\n" + "=" * 50)
    print("All Foundation Tests Passed! ✓")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
```

Run it:
```bash
python test_foundation.py
```

Expected output:
```
==================================================
Foundation Infrastructure Test
==================================================

1. Creating agent...
   ✓ Agent created: <TestAgent(name=TestAgent, role=Tester)>

2. Initializing memory...
   ✓ Memory initialized: <AgentMemory(agent=TestAgent, short_term=0, long_term=0)>

3. Storing in memory...
   ✓ Stored. Memory size: 1

4. Retrieving from memory...
   ✓ Retrieved 1 items

5. Executing task...
   ✓ Task executed: success

6. Testing communication bus...
   ✓ Message sent: a1b2c3d4...

7. Testing execution engine...
   ✓ Engine created: <ExecutionEngine(max_retries=3, timeout=300)>

==================================================
All Foundation Tests Passed! ✓
==================================================
```

---

## 📋 Checklist: Foundation Infrastructure Complete

- [ ] Created directory structure (`backend/agents/base/`, etc.)
- [ ] Created `base_agent.py` with Agent class
- [ ] Created `agent_memory.py` with AgentMemory class
- [ ] Created `communication_bus.py` with AgentCommunicationBus
- [ ] Created `execution_engine.py` with ExecutionEngine
- [ ] Created unit tests (3 test files)
- [ ] All tests passing (`pytest backend/tests/agents/unit/ -v`)
- [ ] Updated `backend/main.py` to initialize infrastructure
- [ ] Ran manual test successfully
- [ ] Verified coverage >85%

---

## 🎉 Next Steps

Once foundation infrastructure is complete and tested:

**Move to Weeks 3-4:** Implement the 4 Core Agents
- SearchAgent
- AnalysisAgent
- VerificationAgent
- SynthesisAgent

**See:** `PHASE_1_DETAILED_EXPLANATION.md` Weeks 3-4 section

---

## 📞 Common Issues & Solutions

### Issue 1: Import Error: "No module named 'backend.agents'"

**Solution:** Make sure you're in the project root directory and `backend` is a Python package (has `__init__.py`)

```bash
touch backend/__init__.py
```

### Issue 2: Test fails with "agent.memory is None"

**Solution:** Remember to call `await agent.initialize_memory()` before using memory

```python
agent = TestAgent(...)
await agent.initialize_memory()  # ← Add this line
```

### Issue 3: AsyncIO errors

**Solution:** Make sure all async functions use `async def` and are awaited with `await`

```python
# ✓ Correct
result = await agent.execute(task)

# ✗ Wrong
result = agent.execute(task)
```

---

**Foundation Infrastructure is now complete and ready for Phase 1 Weeks 3-4!**

Start building the 4 core agents next.

