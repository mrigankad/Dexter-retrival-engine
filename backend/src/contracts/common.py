"""Enumerations shared by all contracts."""

from enum import Enum


class Intent(str, Enum):
    """Top-level route for a user question."""
    KNOWLEDGE = "KNOWLEDGE"          # answer from documents / knowledge base
    DATA = "DATA"                    # answer from structured data (reserved, see docs)
    HYBRID = "HYBRID"                # both
    CHAT = "CHAT"                    # conversational, no retrieval needed
    CLARIFICATION = "CLARIFICATION"  # ambiguous, ask the user
    ACTION = "ACTION"                # side effects, blocked by policy


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ContentType(str, Enum):
    TEXT = "text"
    TABLE = "table"
    CHART = "chart"
    IMAGE = "image"
    CODE = "code"


class ChunkLevel(str, Enum):
    SECTION = "section"
    PARAGRAPH = "paragraph"
    TABLE_SUMMARY = "table_summary"
    TABLE_DATA = "table_data"
    CHART_ANALYSIS = "chart_analysis"
