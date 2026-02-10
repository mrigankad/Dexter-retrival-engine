"""
Table Canonicalization Layer - Structured Table Normalization.

Normalizes raw table data into canonical structured formats:
- Row/column mapping with header inference
- Numeric typing and unit detection
- Time series detection
- Financial metric tagging
- Export to structured JSON for embedding
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple
import re
import json

from core.logger import get_logger

logger = get_logger(__name__)


# ── Financial metric patterns ─────────────────────────────────
FINANCIAL_METRICS = {
    "revenue": ["revenue", "sales", "turnover", "top line", "net sales"],
    "profit": ["profit", "income", "earnings", "bottom line", "pbt", "pat", "ebit", "ebitda"],
    "margin": ["margin", "gross margin", "operating margin", "net margin", "ebitda margin"],
    "cost": ["cost", "expense", "expenditure", "capex", "opex", "cogs"],
    "asset": ["asset", "total assets", "current assets", "fixed assets", "goodwill"],
    "liability": ["liability", "debt", "borrowing", "loan", "payable"],
    "equity": ["equity", "share capital", "retained earnings", "book value"],
    "cashflow": ["cash flow", "operating cash flow", "free cash flow", "fcf"],
    "ratio": ["ratio", "pe ratio", "debt equity", "current ratio", "roe", "roa", "roce"],
    "per_share": ["eps", "dps", "book value per share", "per share"],
}

CURRENCY_PATTERNS = [
    r"(?:Rs\.?|₹|INR)\s*[\d,]+(?:\.\d+)?",
    r"\$\s*[\d,]+(?:\.\d+)?",
    r"€\s*[\d,]+(?:\.\d+)?",
    r"£\s*[\d,]+(?:\.\d+)?",
]

UNIT_PATTERNS = {
    "crore": r"(?:cr|crore|crores)",
    "lakh": r"(?:lac|lakh|lakhs)",
    "million": r"(?:mn|million|millions|mil)",
    "billion": r"(?:bn|billion|billions)",
    "thousand": r"(?:k|thousand|thousands)",
    "percentage": r"%",
    "per_tonne": r"(?:/(?:d?mt|tonne|ton))",
}

TIME_PATTERNS = [
    r"FY\s*\d{2,4}(?:-\d{2,4})?",
    r"Q[1-4]\s*(?:FY)?\s*\d{2,4}",
    r"H[12]\s*(?:FY)?\s*\d{2,4}",
    r"\b\d{4}-\d{2,4}\b",
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}",
    r"\b(?:20[0-3]\d|19\d{2})\b",
]


@dataclass
class CanonicalCell:
    """A single cell in a canonical table."""
    raw_value: str
    clean_value: str
    numeric_value: Optional[float] = None
    unit: Optional[str] = None
    currency: Optional[str] = None
    is_header: bool = False
    is_numeric: bool = False
    is_percentage: bool = False
    row: int = 0
    col: int = 0


@dataclass
class CanonicalColumn:
    """Metadata about a table column."""
    index: int
    header: str
    data_type: str = "text"  # text | numeric | percentage | currency | date
    unit: Optional[str] = None
    financial_metric: Optional[str] = None
    is_time_period: bool = False
    sample_values: List[str] = field(default_factory=list)


@dataclass
class CanonicalTable:
    """Fully normalized table structure."""
    id: str
    page: int
    caption: Optional[str]
    headers: List[str]
    columns: List[CanonicalColumn]
    rows: List[List[CanonicalCell]]
    num_rows: int
    num_cols: int
    is_time_series: bool = False
    is_financial: bool = False
    financial_metrics_found: List[str] = field(default_factory=list)
    time_periods_found: List[str] = field(default_factory=list)
    orientation: str = "row"  # row | column (time periods in rows vs. columns)
    summary: str = ""
    markdown: str = ""
    structured_json: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "page": self.page,
            "caption": self.caption,
            "headers": self.headers,
            "num_rows": self.num_rows,
            "num_cols": self.num_cols,
            "is_time_series": self.is_time_series,
            "is_financial": self.is_financial,
            "financial_metrics_found": self.financial_metrics_found,
            "time_periods_found": self.time_periods_found,
            "orientation": self.orientation,
            "summary": self.summary,
            "markdown": self.markdown,
            "structured_json": self.structured_json,
        }


class TableCanonicalizer:
    """
    Normalizes raw extracted tables into structured, queryable formats.
    
    Pipeline:
    1. Parse raw table data (list of lists / markdown / HTML)
    2. Infer headers
    3. Detect column types (numeric, currency, percentage, text)
    4. Tag financial metrics
    5. Detect time series patterns
    6. Generate canonical output (JSON + markdown + summary)
    """

    def __init__(self):
        self._time_pattern = re.compile("|".join(TIME_PATTERNS), re.IGNORECASE)
        self._currency_patterns = [re.compile(p) for p in CURRENCY_PATTERNS]
        self._unit_patterns = {k: re.compile(v, re.IGNORECASE) for k, v in UNIT_PATTERNS.items()}

    def canonicalize(
        self,
        table_id: str,
        page: int,
        headers: List[str],
        rows: List[List[str]],
        caption: Optional[str] = None,
        context_before: str = "",
        context_after: str = "",
    ) -> CanonicalTable:
        """
        Main entry: normalize a raw table into canonical form.
        
        Args:
            table_id: Unique ID for the table
            page: Source page number
            headers: Column headers
            rows: List of row data (each row = list of cell strings)
            caption: Table caption if detected
            context_before: Text before the table for context
            context_after: Text after the table for context
            
        Returns:
            CanonicalTable with full normalization
        """
        if not rows:
            return CanonicalTable(
                id=table_id, page=page, caption=caption,
                headers=headers, columns=[], rows=[],
                num_rows=0, num_cols=len(headers),
            )

        # Step 1: Infer headers if not provided
        if not headers and rows:
            headers, rows = self._infer_headers(rows)

        # Ensure consistent column count
        num_cols = max(len(headers), max(len(r) for r in rows) if rows else 0)
        headers = self._pad_list(headers, num_cols, "")
        rows = [self._pad_list(r, num_cols, "") for r in rows]

        # Step 2: Parse all cells
        canonical_rows = []
        for r_idx, row in enumerate(rows):
            canonical_row = []
            for c_idx, cell_val in enumerate(row):
                canonical_row.append(self._parse_cell(str(cell_val), r_idx, c_idx))
            canonical_rows.append(canonical_row)

        # Step 3: Analyze columns
        columns = self._analyze_columns(headers, canonical_rows)

        # Step 4: Tag financial metrics
        financial_metrics = self._tag_financial_metrics(headers, caption, context_before)

        # Step 5: Detect time series
        time_periods, is_time_series, orientation = self._detect_time_series(
            headers, canonical_rows
        )

        # Step 6: Generate outputs
        markdown = self._to_markdown(headers, rows)
        structured_json = self._to_structured_json(headers, canonical_rows, columns)
        summary = self._generate_summary(
            caption, headers, canonical_rows, columns,
            financial_metrics, time_periods, is_time_series
        )

        return CanonicalTable(
            id=table_id,
            page=page,
            caption=caption,
            headers=headers,
            columns=columns,
            rows=canonical_rows,
            num_rows=len(canonical_rows),
            num_cols=num_cols,
            is_time_series=is_time_series,
            is_financial=bool(financial_metrics),
            financial_metrics_found=financial_metrics,
            time_periods_found=time_periods,
            orientation=orientation,
            summary=summary,
            markdown=markdown,
            structured_json=structured_json,
        )

    # ── Internal Methods ───────────────────────────────────────

    def _infer_headers(self, rows: List[List[str]]) -> Tuple[List[str], List[List[str]]]:
        """Infer if the first row is a header row."""
        if len(rows) < 2:
            return [f"Col_{i}" for i in range(len(rows[0]))], rows

        first_row = rows[0]
        second_row = rows[1]

        # Heuristic: if first row has more text and second has more numbers,
        # first is likely headers
        first_numeric = sum(1 for c in first_row if self._is_numeric_str(str(c)))
        second_numeric = sum(1 for c in second_row if self._is_numeric_str(str(c)))

        if first_numeric < second_numeric:
            return [str(h).strip() for h in first_row], rows[1:]

        # Another heuristic: if first row cells are shorter on average
        avg_first = sum(len(str(c)) for c in first_row) / max(len(first_row), 1)
        avg_second = sum(len(str(c)) for c in second_row) / max(len(second_row), 1)

        if avg_first < avg_second * 0.7:
            return [str(h).strip() for h in first_row], rows[1:]

        return [f"Col_{i}" for i in range(len(first_row))], rows

    def _parse_cell(self, raw_value: str, row: int, col: int) -> CanonicalCell:
        """Parse a raw cell value into a canonical cell."""
        clean = raw_value.strip()
        cell = CanonicalCell(raw_value=raw_value, clean_value=clean, row=row, col=col)

        if not clean or clean in ("-", "–", "—", "N/A", "n/a", "NA", "nil"):
            return cell

        # Detect percentage
        if "%" in clean:
            cell.is_percentage = True
            cell.is_numeric = True
            num_match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", clean.replace("%", ""))
            if num_match:
                cell.numeric_value = self._parse_number(num_match.group())
            cell.unit = "percentage"
            return cell

        # Detect currency
        for pat in self._currency_patterns:
            if pat.search(clean):
                cell.is_numeric = True
                if "₹" in clean or "Rs" in clean or "INR" in clean:
                    cell.currency = "INR"
                elif "$" in clean:
                    cell.currency = "USD"
                elif "€" in clean:
                    cell.currency = "EUR"
                elif "£" in clean:
                    cell.currency = "GBP"
                num_match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", clean)
                if num_match:
                    cell.numeric_value = self._parse_number(num_match.group())
                break

        # Detect units
        for unit_name, unit_pat in self._unit_patterns.items():
            if unit_pat.search(clean):
                cell.unit = unit_name
                break

        # Detect plain numeric
        if not cell.is_numeric and self._is_numeric_str(clean):
            cell.is_numeric = True
            num_match = re.search(r"[-+]?\d[\d,]*(?:\.\d+)?", clean)
            if num_match:
                cell.numeric_value = self._parse_number(num_match.group())

        return cell

    def _analyze_columns(
        self, headers: List[str], rows: List[List[CanonicalCell]]
    ) -> List[CanonicalColumn]:
        """Analyze column data types and metadata."""
        columns = []
        for c_idx, header in enumerate(headers):
            col_cells = [row[c_idx] for row in rows if c_idx < len(row)]

            numeric_count = sum(1 for c in col_cells if c.is_numeric)
            percentage_count = sum(1 for c in col_cells if c.is_percentage)
            total = len(col_cells) or 1

            # Determine data type
            if percentage_count / total > 0.5:
                data_type = "percentage"
            elif numeric_count / total > 0.5:
                # Check for currency
                currencies = [c.currency for c in col_cells if c.currency]
                if len(currencies) / total > 0.3:
                    data_type = "currency"
                else:
                    data_type = "numeric"
            elif self._time_pattern.search(header):
                data_type = "date"
            else:
                data_type = "text"

            # Detect unit from most common
            units = [c.unit for c in col_cells if c.unit]
            unit = max(set(units), key=units.count) if units else None

            # Tag financial metric
            financial_metric = self._match_financial_metric(header)

            # Check if column represents a time period
            is_time = bool(self._time_pattern.search(header))

            sample_vals = [c.clean_value for c in col_cells[:3]]

            columns.append(CanonicalColumn(
                index=c_idx,
                header=header,
                data_type=data_type,
                unit=unit,
                financial_metric=financial_metric,
                is_time_period=is_time,
                sample_values=sample_vals,
            ))

        return columns

    def _tag_financial_metrics(
        self, headers: List[str], caption: Optional[str], context: str
    ) -> List[str]:
        """Identify financial metrics present in the table."""
        found = []
        search_text = " ".join(headers).lower()
        if caption:
            search_text += " " + caption.lower()
        search_text += " " + context.lower()

        for metric_name, keywords in FINANCIAL_METRICS.items():
            for kw in keywords:
                if kw.lower() in search_text:
                    found.append(metric_name)
                    break

        return list(set(found))

    def _detect_time_series(
        self,
        headers: List[str],
        rows: List[List[CanonicalCell]],
    ) -> Tuple[List[str], bool, str]:
        """Detect if the table contains time series data."""
        # Check headers for time patterns
        header_periods = []
        for h in headers:
            matches = self._time_pattern.findall(h)
            header_periods.extend(matches)

        if len(header_periods) >= 2:
            return header_periods, True, "column"

        # Check first column for time patterns
        if rows:
            row_periods = []
            for row in rows:
                if row:
                    matches = self._time_pattern.findall(row[0].clean_value)
                    row_periods.extend(matches)

            if len(row_periods) >= 2:
                return row_periods, True, "row"

        return header_periods or [], False, "row"

    def _match_financial_metric(self, text: str) -> Optional[str]:
        """Match a text string to a known financial metric category."""
        text_lower = text.lower()
        for metric_name, keywords in FINANCIAL_METRICS.items():
            for kw in keywords:
                if kw in text_lower:
                    return metric_name
        return None

    def _to_markdown(self, headers: List[str], rows: List[List[str]]) -> str:
        """Convert table to markdown format."""
        if not headers and not rows:
            return ""

        lines = []
        # Header
        lines.append("| " + " | ".join(str(h) for h in headers) + " |")
        lines.append("| " + " | ".join("---" for _ in headers) + " |")

        # Rows
        for row in rows:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")

        return "\n".join(lines)

    def _to_structured_json(
        self,
        headers: List[str],
        rows: List[List[CanonicalCell]],
        columns: List[CanonicalColumn],
    ) -> str:
        """Convert table to structured JSON for embedding."""
        records = []
        for row in rows:
            record = {}
            for c_idx, cell in enumerate(row):
                if c_idx < len(headers):
                    key = headers[c_idx] or f"col_{c_idx}"
                    if cell.is_numeric and cell.numeric_value is not None:
                        record[key] = {
                            "value": cell.numeric_value,
                            "display": cell.clean_value,
                            "unit": cell.unit,
                            "currency": cell.currency,
                        }
                    else:
                        record[key] = cell.clean_value
            records.append(record)

        return json.dumps(records, indent=2, default=str)

    def _generate_summary(
        self,
        caption: Optional[str],
        headers: List[str],
        rows: List[List[CanonicalCell]],
        columns: List[CanonicalColumn],
        financial_metrics: List[str],
        time_periods: List[str],
        is_time_series: bool,
    ) -> str:
        """Generate a natural language summary of the table."""
        parts = []

        if caption:
            parts.append(f"Table: {caption}.")
        else:
            parts.append(f"Table with {len(rows)} rows and {len(headers)} columns.")

        # Describe columns
        col_descs = []
        for col in columns:
            desc = col.header
            if col.data_type != "text":
                desc += f" ({col.data_type}"
                if col.unit:
                    desc += f", {col.unit}"
                desc += ")"
            col_descs.append(desc)

        if col_descs:
            parts.append(f"Columns: {', '.join(col_descs)}.")

        if financial_metrics:
            parts.append(f"Financial metrics: {', '.join(financial_metrics)}.")

        if is_time_series:
            parts.append(f"Time series data covering: {', '.join(time_periods[:5])}.")

        # Add numeric highlights
        numeric_cols = [c for c in columns if c.data_type in ("numeric", "currency", "percentage")]
        if numeric_cols and rows:
            highlights = []
            for col in numeric_cols[:3]:
                values = [
                    r[col.index].numeric_value
                    for r in rows
                    if col.index < len(r) and r[col.index].numeric_value is not None
                ]
                if values:
                    min_val = min(values)
                    max_val = max(values)
                    highlights.append(
                        f"{col.header}: range {min_val:,.2f} to {max_val:,.2f}"
                    )
            if highlights:
                parts.append(f"Key ranges: {'; '.join(highlights)}.")

        return " ".join(parts)

    # ── Utility ────────────────────────────────────────────────

    @staticmethod
    def _is_numeric_str(s: str) -> bool:
        """Check if a string represents a numeric value."""
        cleaned = re.sub(r"[,\s₹$€£%]", "", s.strip())
        cleaned = re.sub(r"\((.+)\)", r"-\1", cleaned)  # Handle parenthetical negatives
        try:
            float(cleaned)
            return True
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _parse_number(s: str) -> Optional[float]:
        """Parse a numeric string to float."""
        try:
            cleaned = s.replace(",", "").strip()
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _pad_list(lst: list, target_len: int, pad_value: Any = "") -> list:
        """Pad a list to target length."""
        return lst + [pad_value] * max(0, target_len - len(lst))
