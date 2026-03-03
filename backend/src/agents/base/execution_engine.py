"""
Execution Engine

Runs agent plans in different patterns:
  sequential  — each step feeds its output into the next
  parallel    — all steps run concurrently via asyncio.gather
"""

import asyncio
import time
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """
    Drives agent execution with retry and timeout support.

    Parameters
    ----------
    max_retries : int
        How many times to re-attempt a failing agent step (default 3).
    timeout : float
        Per-plan wall-clock timeout in seconds (default 300 = 5 min).
    """

    def __init__(self, max_retries: int = 3, timeout: float = 300.0) -> None:
        self.max_retries = max_retries
        self.timeout = timeout
        self.execution_history: List[Dict[str, Any]] = []

    # ── Public API ─────────────────────────────────────────────────────────────

    async def execute_sequential(
        self,
        plan: Dict[str, Any],
        agents: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute plan steps one after another.

        Each step receives the previous step's result in
        ``task_input["previous_results"]``.

        Plan schema
        -----------
        {
            "steps": [
                {"agent": "SearchAgent",     "task": "retrieve_documents"},
                {"agent": "AnalysisAgent",   "task": "analyze_documents"},
                {"agent": "SynthesisAgent",  "task": "synthesize_response"},
            ]
        }
        """
        results: Dict[str, Any] = {}
        previous_output: Any = None
        start_plan = time.time()

        logger.info(
            f"Sequential execution started — {len(plan['steps'])} step(s)"
        )

        for idx, step in enumerate(plan["steps"], start=1):
            agent_name = step["agent"]
            task_name  = step["task"]
            agent = agents.get(agent_name)

            if agent is None:
                raise ValueError(f"Unknown agent '{agent_name}'")

            logger.info(f"  Step {idx}/{len(plan['steps'])}: {agent_name} ({task_name})")

            task_input = {
                "task":             task_name,
                "previous_results": previous_output,
                **{k: v for k, v in step.items() if k not in ("agent", "task")},
            }

            step_start = time.time()
            try:
                result = await asyncio.wait_for(
                    self._run_with_retry(agent, task_input),
                    timeout=self.timeout,
                )
                duration = time.time() - step_start

                results[agent_name] = {
                    "status":   "success",
                    "result":   result,
                    "duration": round(duration, 3),
                    "step":     idx,
                }
                logger.info(f"  Step {idx} ✓  ({duration:.2f}s)")
                previous_output = result

            except asyncio.TimeoutError:
                duration = time.time() - step_start
                logger.error(f"  Step {idx} timed out after {self.timeout}s")
                results[agent_name] = {
                    "status": "timeout",
                    "error":  f"Timed out after {self.timeout}s",
                    "step":   idx,
                }
                raise

            except Exception as exc:
                duration = time.time() - step_start
                logger.error(f"  Step {idx} failed: {exc}")
                results[agent_name] = {
                    "status": "error",
                    "error":  str(exc),
                    "step":   idx,
                }
                raise

        total = round(time.time() - start_plan, 3)
        self._record("sequential", len(plan["steps"]), total, "success")
        logger.info(f"Sequential execution completed in {total}s")
        return results

    async def execute_parallel(
        self,
        plan: Dict[str, Any],
        agents: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute all plan steps concurrently.

        Steps do not share intermediate results — use sequential for that.
        """
        results: Dict[str, Any] = {}
        start_plan = time.time()

        logger.info(
            f"Parallel execution started — {len(plan['steps'])} step(s)"
        )

        # Build tasks
        tasks: Dict[str, asyncio.Task] = {}
        for step in plan["steps"]:
            agent_name = step["agent"]
            agent = agents.get(agent_name)
            if agent is None:
                raise ValueError(f"Unknown agent '{agent_name}'")

            task_input = {
                "task": step["task"],
                **{k: v for k, v in step.items() if k not in ("agent", "task")},
            }
            tasks[agent_name] = asyncio.create_task(
                self._run_with_timeout_and_retry(agent, task_input),
                name=agent_name,
            )

        # Gather results
        for agent_name, task in tasks.items():
            step_start = time.time()
            try:
                result   = await task
                duration = round(time.time() - step_start, 3)
                results[agent_name] = {
                    "status":   "success",
                    "result":   result,
                    "duration": duration,
                }
                logger.info(f"  {agent_name} ✓  ({duration:.2f}s)")
            except Exception as exc:
                duration = round(time.time() - step_start, 3)
                logger.error(f"  {agent_name} ✗  {exc}")
                results[agent_name] = {
                    "status":   "error",
                    "error":    str(exc),
                    "duration": duration,
                }

        total = round(time.time() - start_plan, 3)
        self._record("parallel", len(plan["steps"]), total, "success")
        logger.info(f"Parallel execution completed in {total}s")
        return results

    # ── Internal helpers ───────────────────────────────────────────────────────

    async def _run_with_retry(
        self, agent: Any, task_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Retry *agent.execute* up to *max_retries* times with exponential back-off."""
        last_exc: Exception = RuntimeError("No attempts made")

        for attempt in range(1, self.max_retries + 1):
            try:
                return await agent.execute(task_input)
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    wait = 2 ** (attempt - 1)   # 1s, 2s, 4s …
                    logger.warning(
                        f"{agent.name}: attempt {attempt} failed ({exc}). "
                        f"Retrying in {wait}s…"
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(
                        f"{agent.name}: all {self.max_retries} attempts failed."
                    )

        raise last_exc

    async def _run_with_timeout_and_retry(
        self, agent: Any, task_input: Dict[str, Any]
    ) -> Dict[str, Any]:
        return await asyncio.wait_for(
            self._run_with_retry(agent, task_input),
            timeout=self.timeout,
        )

    def _record(
        self, pattern: str, steps: int, duration: float, status: str
    ) -> None:
        self.execution_history.append({
            "pattern":  pattern,
            "steps":    steps,
            "duration": duration,
            "status":   status,
            "ts":       time.time(),
        })

    # ── Inspection ────────────────────────────────────────────────────────────

    def get_history(self) -> List[Dict[str, Any]]:
        return list(self.execution_history)

    def __repr__(self) -> str:
        return (
            f"<ExecutionEngine("
            f"max_retries={self.max_retries}, "
            f"timeout={self.timeout})>"
        )
