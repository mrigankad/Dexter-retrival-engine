"""
Structured-data query gateway: governed natural-language questions over live databases.

    question → semantic lookup (relevant entities, metrics, verified examples)
             → SQL generation (LLM) or verified template
             → AST policy (single read-only SELECT, table allowlist, PII denylist, LIMIT)
             → read-only execution with timeout and row caps
             → QueryResult + SQL evidence (+ table / chart blocks)

No LLM output ever reaches a database without passing ``SqlPolicy``.
"""

from .models import (
    DataConnection, SemanticEntity, SemanticModel, VerifiedQuery, SqlPolicyResult, QueryResult, ColumnInfo, TableInfo,
    SchemaCatalog,
)
from .policy import SqlPolicy, SqlPolicyError
from .connections import DataConnectionManager, get_connection_manager
from .service import DataQueryService, get_data_query_service, DataQueryError
from .charts import suggest_chart, validate_chart_spec, rows_to_markdown

__all__ = [
    "DataConnection", "SemanticEntity", "SemanticModel", "VerifiedQuery", "SqlPolicyResult", "QueryResult",
    "ColumnInfo", "TableInfo", "SchemaCatalog", "SqlPolicy", "SqlPolicyError", "DataConnectionManager",
    "get_connection_manager", "DataQueryService", "get_data_query_service", "DataQueryError",
    "suggest_chart", "validate_chart_spec", "rows_to_markdown",
]
