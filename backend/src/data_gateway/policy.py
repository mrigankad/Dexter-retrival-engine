"""
SQL policy engine (sqlglot AST). Order of checks, as in the Bodham blueprint:

    parse → exactly one statement → SELECT/UNION only → table allowlist →
    column denylist (PII) → row-limit enforcement → complexity guardrail
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set

import sqlglot
from sqlglot import exp

from .models import SqlPolicyResult

_DIALECTS = {"postgres": "postgres", "postgresql": "postgres", "sqlite": "sqlite", "mssql": "tsql", "tsql": "tsql",
             "mysql": "mysql", "duckdb": "duckdb", "snowflake": "snowflake", "bigquery": "bigquery"}
_FORBIDDEN_FUNCS = {"pg_sleep", "pg_read_file", "load_file", "xp_cmdshell", "openrowset", "dblink", "copy", "sleep",
                    "benchmark", "readfile", "writefile"}


class SqlPolicyError(ValueError):
    def __init__(self, violations: List[str]):
        super().__init__("; ".join(violations))
        self.violations = violations


class SqlPolicy:
    def __init__(
        self,
        dialect: str = "postgres",
        allowed_tables: Optional[Iterable[str]] = None,
        denied_columns: Optional[Iterable[str]] = None,
        default_limit: int = 500,
        hard_limit: int = 5000,
        max_joins: int = 8,
        max_subqueries: int = 6,
    ):
        self.dialect = _DIALECTS.get(dialect.lower(), dialect.lower())
        self.allowed_tables = {t.lower() for t in (allowed_tables or [])}
        self.denied_columns = {c.lower() for c in (denied_columns or [])}
        self.default_limit = default_limit
        self.hard_limit = hard_limit
        self.max_joins = max_joins
        self.max_subqueries = max_subqueries

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _cte_names(tree: exp.Expression) -> Set[str]:
        return {c.alias.lower() for c in tree.find_all(exp.CTE) if c.alias}

    @staticmethod
    def _table_name(t: exp.Table) -> str:
        parts = [p for p in (t.args.get("catalog"), t.args.get("db"), t.this) if p is not None]
        return ".".join(p.name for p in parts).lower()

    def _table_allowed(self, name: str) -> bool:
        if not self.allowed_tables:
            return True
        bare = name.split(".")[-1]
        return name in self.allowed_tables or bare in self.allowed_tables or any(a.endswith("." + bare) for a in self.allowed_tables)

    def _column_denied(self, col: exp.Column, table_aliases: dict, tables_in_query: List[str]) -> Optional[str]:
        name = col.name.lower()
        table = (col.table or "").lower()
        real = table_aliases.get(table, table)
        candidates = {name}
        if real:
            candidates.add(f"{real}.{name}")
            candidates.add(f"{table}.{name}")
        else:
            # unqualified column: it may come from any table in the query
            for t in tables_in_query:
                candidates.add(f"{t.split('.')[-1]}.{name}")
        for c in candidates:
            if c in self.denied_columns:
                return c
        return None

    # ── main ───────────────────────────────────────────────────────────

    def validate(self, sql: str, limit: Optional[int] = None) -> SqlPolicyResult:
        violations: List[str] = []
        cleaned = sql.strip().rstrip(";").strip()
        if not cleaned:
            return SqlPolicyResult(ok=False, sql=sql, violations=["empty statement"])
        try:
            statements = [s for s in sqlglot.parse(cleaned, read=self.dialect) if s is not None and not isinstance(s, exp.Semicolon)]
        except Exception as exc:
            return SqlPolicyResult(ok=False, sql=sql, violations=[f"parse error: {str(exc)[:200]}"])
        if len(statements) != 1:
            return SqlPolicyResult(ok=False, sql=sql, violations=[f"exactly one statement required, got {len(statements)}"])
        tree = statements[0]
        if not isinstance(tree, (exp.Select, exp.Union)):
            kind = type(tree).__name__.upper()
            return SqlPolicyResult(ok=False, sql=sql, violations=[f"only SELECT statements are allowed (got {kind})"])

        # nested writes / commands hidden in subqueries
        for node in tree.walk():
            if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Drop, exp.Alter, exp.Create, exp.Command,
                                 exp.Grant, exp.Pragma, exp.Copy, exp.Truncate if hasattr(exp, "Truncate") else exp.Command)):
                violations.append(f"forbidden operation inside query: {type(node).__name__.upper()}")
            if isinstance(node, (exp.Anonymous, exp.Func)):
                fname = (node.name or getattr(node, "sql_name", lambda: "")() or "").lower()
                if fname in _FORBIDDEN_FUNCS:
                    violations.append(f"forbidden function: {fname}")
            if isinstance(node, exp.Into):
                violations.append("SELECT INTO is not allowed")

        cte_names = self._cte_names(tree)
        tables: List[str] = []
        aliases: dict = {}
        for t in tree.find_all(exp.Table):
            name = self._table_name(t)
            if not name:
                continue
            if t.alias:
                aliases[t.alias.lower()] = name.split(".")[-1]
            if name in cte_names:
                continue
            if name not in tables:
                tables.append(name)
            if not self._table_allowed(name):
                violations.append(f"table not allowed: {name}")

        columns: List[str] = []
        for c in tree.find_all(exp.Column):
            label = f"{c.table}.{c.name}" if c.table else c.name
            if label not in columns:
                columns.append(label)
            denied = self._column_denied(c, aliases, tables)
            if denied:
                violations.append(f"column not allowed: {denied}")
        if self.denied_columns:
            # A projected star (SELECT * / SELECT t.*) could expose denied columns of the tables in that scope.
            # COUNT(*) and similar function arguments are not projections and are fine.
            restricted_tables = {d.split(".")[0] for d in self.denied_columns if "." in d}
            for sel in tree.find_all(exp.Select):
                star_aliases: List[Optional[str]] = []
                for e in sel.expressions:
                    if isinstance(e, exp.Star):
                        star_aliases.append(None)
                    elif isinstance(e, exp.Column) and isinstance(e.this, exp.Star):
                        star_aliases.append((e.table or "").lower())
                if not star_aliases:
                    continue
                scoped: List[str] = []
                for t in sel.find_all(exp.Table):
                    if t.find_ancestor(exp.Select) is not sel:   # belongs to a nested subquery
                        continue
                    bare = self._table_name(t).split(".")[-1]
                    alias = (t.alias or "").lower()
                    for sa in star_aliases:
                        if sa is None or sa == alias or sa == bare:
                            scoped.append(bare)
                for bare in scoped:
                    if bare in restricted_tables:
                        violations.append(f"SELECT * not allowed on {bare} (contains restricted columns)")

        joins = len(list(tree.find_all(exp.Join)))
        subqueries = len(list(tree.find_all(exp.Subquery)))
        if joins > self.max_joins:
            violations.append(f"too many joins ({joins} > {self.max_joins})")
        if subqueries > self.max_subqueries:
            violations.append(f"too many subqueries ({subqueries} > {self.max_subqueries})")

        # row limit
        requested = limit or self.default_limit
        effective = min(requested, self.hard_limit)
        existing = tree.args.get("limit")
        if existing is not None:
            try:
                current = int(existing.expression.sql())
                effective = min(current, self.hard_limit)
            except (ValueError, AttributeError):
                effective = min(requested, self.hard_limit)
        if violations:
            return SqlPolicyResult(ok=False, sql=sql, tables=tables, columns=columns, violations=sorted(set(violations)))
        shown = tree.limit(effective).sql(dialect=self.dialect)
        probe = tree.limit(effective + 1).sql(dialect=self.dialect)   # one extra row reveals truncation
        return SqlPolicyResult(ok=True, sql=shown, exec_sql=probe, tables=tables, columns=columns, limit=effective)

    def enforce(self, sql: str, limit: Optional[int] = None) -> SqlPolicyResult:
        result = self.validate(sql, limit=limit)
        if not result.ok:
            raise SqlPolicyError(result.violations)
        return result


def normalize_question(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower().rstrip("?.!"))
