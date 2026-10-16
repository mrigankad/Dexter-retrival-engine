"""Safe declarative chart specs (the model never emits frontend code)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

ALLOWED_TYPES = {"kpi", "table", "line", "bar", "stacked_bar"}
_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?")


def _is_numeric(values: List[Any]) -> bool:
    nums = [v for v in values if v is not None]
    return bool(nums) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in nums)


def _is_temporal(name: str, values: List[Any]) -> bool:
    if any(k in name.lower() for k in ("date", "month", "week", "year", "day", "period", "quarter", "time")):
        return True
    sample = [v for v in values if v is not None][:5]
    return bool(sample) and all(isinstance(v, str) and _DATE_RE.match(v) for v in sample)


def suggest_chart(columns: List[str], rows: List[List[Any]], title: str = "") -> Optional[Dict[str, Any]]:
    """Pick kpi / line / bar / table from the result shape; None when nothing sensible applies."""
    if not columns or not rows:
        return None
    if len(rows) == 1 and len(columns) == 1 and _is_numeric([rows[0][0]]):
        return {"type": "kpi", "title": title or columns[0], "value": rows[0][0], "label": columns[0]}
    if len(columns) < 2 or len(rows) > 500:
        return {"type": "table", "title": title, "columns": columns}
    col_values = {c: [r[i] for r in rows] for i, c in enumerate(columns)}
    numeric = [c for c in columns if _is_numeric(col_values[c])]
    non_numeric = [c for c in columns if c not in numeric]
    if not numeric or not non_numeric:
        return {"type": "table", "title": title, "columns": columns}
    x = non_numeric[0]
    y = numeric[:3]
    kind = "line" if _is_temporal(x, col_values[x]) else "bar"
    if kind == "bar" and len(rows) > 40:
        return {"type": "table", "title": title, "columns": columns}
    return {"type": kind, "title": title or f"{', '.join(y)} by {x}", "x": x, "y": y, "format": {"y": "number"}}


def validate_chart_spec(spec: Dict[str, Any], columns: List[str]) -> Dict[str, Any]:
    kind = spec.get("type")
    if kind not in ALLOWED_TYPES:
        raise ValueError(f"unsupported chart type: {kind}")
    out: Dict[str, Any] = {"type": kind, "title": str(spec.get("title", ""))[:120]}
    if kind in ("line", "bar", "stacked_bar"):
        x = spec.get("x")
        ys = spec.get("y") if isinstance(spec.get("y"), list) else [spec.get("y")]
        if x not in columns or not ys or any(y not in columns for y in ys):
            raise ValueError("chart axes must reference result columns")
        out.update({"x": x, "y": ys, "format": {"y": str((spec.get("format") or {}).get("y", "number"))}})
    elif kind == "kpi":
        out.update({"value": spec.get("value"), "label": str(spec.get("label", ""))[:80]})
    else:
        out["columns"] = columns
    return out


def rows_to_markdown(columns: List[str], rows: List[List[Any]], max_rows: int = 50) -> str:
    if not columns:
        return "(no columns)"
    head = "| " + " | ".join(str(c) for c in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = ["| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in rows[:max_rows]]
    tail = [f"| ... {len(rows) - max_rows} more rows ... |"] if len(rows) > max_rows else []
    return "\n".join([head, sep] + body + tail)
