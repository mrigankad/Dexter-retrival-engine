from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class DataConnection(BaseModel):
    id: str
    name: str
    dialect: str = "postgres"                    # postgres | sqlite | mssql | mysql
    url: str = Field(..., description="SQLAlchemy URL or env:VAR reference to one")
    tenant_id: Optional[str] = None
    allowed_schemas: List[str] = Field(default_factory=list)
    allowed_tables: List[str] = Field(default_factory=list, description="Empty = every discovered table in allowed schemas")
    denied_columns: List[str] = Field(default_factory=list, description="table.column or column names that must never be selected (PII)")
    default_row_limit: int = 500
    hard_row_limit: int = 5000
    timeout_seconds: int = 15
    enabled: bool = True
    description: str = ""


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    foreign_key: Optional[str] = None             # "table.column"


class TableInfo(BaseModel):
    schema_name: Optional[str] = None
    name: str
    columns: List[ColumnInfo] = Field(default_factory=list)
    row_estimate: Optional[int] = None

    @property
    def qualified(self) -> str:
        return f"{self.schema_name}.{self.name}" if self.schema_name else self.name


class SchemaCatalog(BaseModel):
    connection_id: str
    dialect: str
    tables: List[TableInfo] = Field(default_factory=list)

    def table(self, name: str) -> Optional[TableInfo]:
        low = name.lower()
        for t in self.tables:
            if t.name.lower() == low or t.qualified.lower() == low:
                return t
        return None


class SemanticEntity(BaseModel):
    name: str                                     # e.g. SalesOrder
    source: str                                   # table (schema.table)
    description: str = ""
    dimensions: Dict[str, str] = Field(default_factory=dict)      # dimension name -> column
    metrics: Dict[str, str] = Field(default_factory=dict)         # metric name -> SQL expression
    synonyms: Dict[str, List[str]] = Field(default_factory=dict)  # term -> synonyms
    relationships: Dict[str, str] = Field(default_factory=dict)   # name -> "a.col = b.col"
    status: str = "approved"                      # suggested | approved


class VerifiedQuery(BaseModel):
    question_pattern: str                         # regex or plain text (case-insensitive)
    sql: str
    description: str = ""
    approved_by: Optional[str] = None


class SemanticModel(BaseModel):
    connection_id: str
    entities: List[SemanticEntity] = Field(default_factory=list)
    verified_queries: List[VerifiedQuery] = Field(default_factory=list)
    glossary: Dict[str, str] = Field(default_factory=dict)        # business term -> definition


class SqlPolicyResult(BaseModel):
    ok: bool
    sql: str                                      # normalized SQL with LIMIT applied (when ok)
    exec_sql: Optional[str] = None                # same query with LIMIT+1, used for execution to detect truncation
    tables: List[str] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    violations: List[str] = Field(default_factory=list)
    limit: Optional[int] = None


class QueryResult(BaseModel):
    query_id: str
    connection_id: str
    connection_name: str
    question: Optional[str] = None
    sql: str
    columns: List[str] = Field(default_factory=list)
    rows: List[List[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    latency_ms: float = 0.0
    source: str = "generated"                     # generated | verified | raw
    explanation: str = ""
    tables: List[str] = Field(default_factory=list)
