"""NL → SQL generation with the fast model, constrained by schema context and policy feedback."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.core.logger import get_logger
from src.services.llm.nvidia_llm_service import LLMUsage, NvidiaLLMService, get_llm_service

logger = get_logger(__name__)

SYSTEM = """You translate business questions into ONE read-only SQL query for the {dialect} dialect.
Return ONLY JSON: {{"sql": "...", "explanation": "one sentence", "needs_clarification": false, "clarification": null,
"chart": {{"type": "line|bar|kpi|table", "x": "col", "y": ["col"]}} }}

Rules:
- Use only the tables and columns listed in the schema. Never invent columns. Prefer the approved metric and
  dimension definitions and the verified examples when they apply.
- A single SELECT (CTEs allowed). No INSERT/UPDATE/DELETE/DDL, no multiple statements, no comments.
- Always include a reasonable LIMIT (<= {limit}). Order results meaningfully (e.g. by the metric descending or by date).
- Relative dates ("last month", "this quarter") are resolved relative to {today}. Use the dialect's date functions.
- If the business meaning is ambiguous (e.g. "revenue" is not defined and several candidate columns exist),
  set needs_clarification=true with a short clarification question instead of guessing.
- Name output columns clearly (snake_case, no spaces)."""

USER = """Schema (relevant tables only):
{schema}

{examples}
Question: {question}
{feedback}"""


class SqlGenerator:
    def __init__(self, llm: Optional[NvidiaLLMService] = None):
        self._llm = llm

    @property
    def llm(self) -> NvidiaLLMService:
        if self._llm is None:
            self._llm = get_llm_service()
        return self._llm

    async def generate(self, question: str, schema: str, dialect: str, limit: int, examples: str = "",
                       feedback: str = "", today: str = "", usage: Optional[LLMUsage] = None) -> Dict[str, Any]:
        system = SYSTEM.format(dialect=dialect, limit=limit, today=today or "today")
        prompt = USER.format(schema=schema, examples=(f"Verified examples:\n{examples}\n" if examples else ""),
                             question=question, feedback=(f"\nPrevious attempt was rejected: {feedback}\nFix it." if feedback else ""))
        data = await self.llm.generate_json(prompt, system_prompt=system, max_tokens=700, fast=True, usage=usage)
        if not isinstance(data, dict):
            raise ValueError("SQL generator returned a non-object")
        sql = str(data.get("sql") or "").strip().strip("`")
        if sql.lower().startswith("sql\n"):
            sql = sql[4:]
        return {
            "sql": sql,
            "explanation": str(data.get("explanation") or "")[:300],
            "needs_clarification": bool(data.get("needs_clarification", False)),
            "clarification": data.get("clarification"),
            "chart": data.get("chart") if isinstance(data.get("chart"), dict) else None,
        }
