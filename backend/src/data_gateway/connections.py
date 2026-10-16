"""Read-only database connections, schema discovery and execution with limits."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from src.core.config import settings
from src.core.logger import get_logger

from .models import ColumnInfo, DataConnection, SchemaCatalog, TableInfo

logger = get_logger(__name__)


def resolve_url(url: str) -> str:
    import os
    if url.startswith("env:"):
        return os.environ.get(url[4:], "")
    return url


class DataConnectionManager:
    """Holds DataConnection definitions and lazily created read-only engines."""

    def __init__(self) -> None:
        self._connections: Dict[str, DataConnection] = {}
        self._engines: Dict[str, Engine] = {}
        self._catalogs: Dict[str, SchemaCatalog] = {}

    # ── registry ───────────────────────────────────────────────────────

    def register(self, conn: DataConnection) -> None:
        self._connections[conn.id] = conn
        self._engines.pop(conn.id, None)
        self._catalogs.pop(conn.id, None)

    def remove(self, connection_id: str) -> None:
        self._connections.pop(connection_id, None)
        eng = self._engines.pop(connection_id, None)
        if eng is not None:
            eng.dispose()
        self._catalogs.pop(connection_id, None)

    def get(self, connection_id: Optional[str] = None) -> DataConnection:
        if connection_id is None:
            enabled = [c for c in self._connections.values() if c.enabled]
            if not enabled:
                raise KeyError("No data connections configured")
            return enabled[0]
        if connection_id not in self._connections:
            raise KeyError(f"Unknown data connection '{connection_id}'")
        return self._connections[connection_id]

    def list(self) -> List[DataConnection]:
        return list(self._connections.values())

    def clear(self) -> None:
        for eng in self._engines.values():
            eng.dispose()
        self._connections.clear()
        self._engines.clear()
        self._catalogs.clear()

    # ── engines ────────────────────────────────────────────────────────

    def engine(self, connection_id: str) -> Engine:
        if connection_id not in self._engines:
            conn = self.get(connection_id)
            url = resolve_url(conn.url)
            if not url:
                raise RuntimeError(f"Data connection {conn.id} has no URL (set {conn.url})")
            kwargs: Dict[str, Any] = {"pool_pre_ping": True, "future": True}
            if url.startswith("sqlite"):
                kwargs["connect_args"] = {"check_same_thread": False}
            elif url.startswith("postgres"):
                kwargs["connect_args"] = {"options": f"-c default_transaction_read_only=on -c statement_timeout={conn.timeout_seconds * 1000}"}
            self._engines[connection_id] = create_engine(url, **kwargs)
        return self._engines[connection_id]

    # ── discovery ──────────────────────────────────────────────────────

    def _discover_sync(self, conn: DataConnection) -> SchemaCatalog:
        engine = self.engine(conn.id)
        insp = inspect(engine)
        schemas = conn.allowed_schemas or [None]
        tables: List[TableInfo] = []
        for schema in schemas:
            try:
                names = insp.get_table_names(schema=schema) + [v for v in insp.get_view_names(schema=schema)]
            except Exception as exc:
                logger.warning("Schema discovery failed", schema=schema, error=str(exc))
                continue
            for name in sorted(names):
                qualified = f"{schema}.{name}" if schema else name
                if conn.allowed_tables and name not in conn.allowed_tables and qualified not in conn.allowed_tables:
                    continue
                pks = set((insp.get_pk_constraint(name, schema=schema) or {}).get("constrained_columns") or [])
                fks: Dict[str, str] = {}
                for fk in insp.get_foreign_keys(name, schema=schema) or []:
                    for local, remote in zip(fk.get("constrained_columns") or [], fk.get("referred_columns") or []):
                        fks[local] = f"{fk.get('referred_table')}.{remote}"
                cols = [ColumnInfo(name=c["name"], type=str(c.get("type")), nullable=bool(c.get("nullable", True)),
                                   primary_key=c["name"] in pks, foreign_key=fks.get(c["name"]))
                        for c in insp.get_columns(name, schema=schema)]
                tables.append(TableInfo(schema_name=schema, name=name, columns=cols))
        return SchemaCatalog(connection_id=conn.id, dialect=conn.dialect, tables=tables)

    async def discover(self, connection_id: str, refresh: bool = False) -> SchemaCatalog:
        if refresh or connection_id not in self._catalogs:
            conn = self.get(connection_id)
            self._catalogs[connection_id] = await asyncio.to_thread(self._discover_sync, conn)
        return self._catalogs[connection_id]

    async def test(self, connection_id: str) -> Dict[str, Any]:
        conn = self.get(connection_id)
        started = time.perf_counter()
        def _ping():
            with self.engine(conn.id).connect() as c:
                return c.execute(text("SELECT 1")).scalar()
        value = await asyncio.to_thread(_ping)
        catalog = await self.discover(connection_id, refresh=True)
        return {"status": "ok" if value == 1 else "unexpected", "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "tables": len(catalog.tables), "dialect": conn.dialect}

    # ── execution ──────────────────────────────────────────────────────

    def _execute_sync(self, conn: DataConnection, sql: str, max_rows: int) -> Tuple[List[str], List[List[Any]], bool]:
        engine = self.engine(conn.id)
        with engine.connect() as c:
            if conn.dialect.startswith("sqlite"):
                c.execute(text("PRAGMA query_only = 1"))
            result = c.execute(text(sql))
            columns = list(result.keys())
            rows = [list(r) for r in result.fetchmany(max_rows + 1)]
            truncated = len(rows) > max_rows
            return columns, rows[:max_rows], truncated

    async def execute(self, connection_id: str, sql: str, max_rows: Optional[int] = None) -> Tuple[List[str], List[List[Any]], bool, float]:
        conn = self.get(connection_id)
        cap = min(max_rows or conn.default_row_limit, conn.hard_row_limit)
        started = time.perf_counter()
        try:
            columns, rows, truncated = await asyncio.wait_for(asyncio.to_thread(self._execute_sync, conn, sql, cap),
                                                              timeout=conn.timeout_seconds)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Query exceeded {conn.timeout_seconds}s timeout")
        rows = [[_jsonable(v) for v in r] for r in rows]
        return columns, rows, truncated, round((time.perf_counter() - started) * 1000, 1)


def _jsonable(value: Any) -> Any:
    import datetime as dt
    import decimal
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return value


_manager: Optional[DataConnectionManager] = None


def get_connection_manager() -> DataConnectionManager:
    global _manager
    if _manager is None:
        _manager = DataConnectionManager()
        _load_from_settings(_manager)
    return _manager


def reset_connection_manager() -> None:
    global _manager
    if _manager is not None:
        _manager.clear()
    _manager = None


def _load_from_settings(manager: DataConnectionManager) -> None:
    """Bootstrap connections from DATA_CONNECTIONS_JSON (list of DataConnection dicts)."""
    import json
    raw = settings.data_connections_json
    if not raw:
        return
    try:
        for item in json.loads(raw):
            manager.register(DataConnection(**item))
    except Exception as exc:
        logger.warning("DATA_CONNECTIONS_JSON could not be parsed", error=str(exc))
