"""
Data Engine — Data Extraction & Processing.

Extracts structured data from RAG answers and source chunks
for use by document builders and chart engines.
"""

import re
import io
from typing import List, Dict, Any, Optional, Tuple

import pandas as pd


class DataEngine:
    """Extracts and processes structured data from RAG outputs."""

    def extract_tables(self, text: str) -> List[pd.DataFrame]:
        """Extract table-like data from text into DataFrames."""
        tables = []

        # Pattern 1: Markdown-style tables
        md_table = self._extract_markdown_table(text)
        if md_table is not None:
            tables.append(md_table)

        # Pattern 2: Bullet lists with key-value pairs
        kv_df = self._extract_key_value_list(text)
        if kv_df is not None:
            tables.append(kv_df)

        # Pattern 3: Numbered lists with data
        num_df = self._extract_numbered_data(text)
        if num_df is not None and not tables:
            tables.append(num_df)

        return tables

    def extract_kpis(self, text: str) -> Dict[str, Any]:
        """Extract key performance indicators from text."""
        kpis = {}

        patterns = [
            # "LTIFR: 0.25"
            (r'(LTIFR|Lost Time Injury Frequency Rate)[:\s]+([\d,.]+)', 'LTIFR'),
            # "5.5 lakh safety observations"
            (r'([\d,.]+)\s*lakh\s+safety\s+observations', 'Safety Observations (Lakh)'),
            # "55,000+ employees"
            (r'([\d,]+)\+?\s+employees(?:\s+and\s+contract\s+workers)?', 'Employees Covered'),
            # "0 fatalities" or "5 fatalities"
            (r'(\d+)\s+fatalities', 'Fatalities'),
            # "90% corrective"
            (r'(\d+)%\s+corrective', 'Corrective Actions (%)'),
            # "26,355 planned safety inspections"
            (r'([\d,]+)\s+planned\s+safety\s+inspections', 'Safety Inspections'),
            # "3,435 e-learning modules"
            (r'([\d,]+)\s+e-learning\s+modules', 'E-Learning Modules'),
            # "1,071 SMEs"
            (r'([\d,]+)\s+SMEs?\s+(?:certified|trained)', 'SMEs Certified'),
        ]

        for pattern, key in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                val_str = match.group(1) if key != "LTIFR" else match.group(2)
                kpis[key] = self._parse_number(val_str)

        return kpis

    def extract_financial_data(self, text: str) -> Optional[pd.DataFrame]:
        """Extract financial/FY comparison data."""
        fy_pattern = r'(?:FY\s*)?(\d{4}(?:-\d{2,4})?)[:\s]+([\d,.]+)\s*(%|crore|lakh|mn|bn)?'
        matches = re.findall(fy_pattern, text, re.IGNORECASE)

        if len(matches) >= 2:
            data = {
                "Period": [f"FY {m[0]}" for m in matches],
                "Value": [self._parse_number(m[1]) for m in matches],
            }
            if matches[0][2]:
                data["Unit"] = [m[2] for m in matches]
            return pd.DataFrame(data)
        return None

    def answer_to_sections(self, answer: str) -> List[Dict[str, str]]:
        """Split a RAG answer into titled sections."""
        sections = []

        # Try splitting by numbered headers: "1. Title" or "**1. Title**"
        parts = re.split(r'\n(?=\d+\.\s+\*{0,2}[A-Z])', answer)
        if len(parts) >= 2:
            for part in parts:
                title_match = re.match(r'\d+\.\s+\*{0,2}(.+?)\*{0,2}[:\n]', part)
                if title_match:
                    title = title_match.group(1).strip()
                    body = part[title_match.end():].strip()
                    sections.append({"title": title, "body": body})
                else:
                    sections.append({"title": "", "body": part.strip()})
            return sections

        # Try splitting by bold headers: "**Title**"
        parts = re.split(r'\n(?=\*\*[A-Z])', answer)
        if len(parts) >= 2:
            for part in parts:
                title_match = re.match(r'\*\*(.+?)\*\*[:\n]?', part)
                if title_match:
                    title = title_match.group(1).strip()
                    body = part[title_match.end():].strip()
                    sections.append({"title": title, "body": body})
                else:
                    sections.append({"title": "", "body": part.strip()})
            return sections

        # Fallback: split by paragraphs
        paragraphs = [p.strip() for p in answer.split("\n\n") if p.strip()]
        for p in paragraphs:
            sections.append({"title": "", "body": p})

        return sections

    def sources_to_dataframe(self, sources: List[dict]) -> pd.DataFrame:
        """Convert source chunks to a DataFrame for tables."""
        rows = []
        for i, src in enumerate(sources, 1):
            rows.append({
                "Ref": i,
                "Page": src.get("page", "N/A"),
                "Source": src.get("source", "Unknown"),
                "Score": round(src.get("score", 0), 3),
                "Type": src.get("content_type", "text"),
                "Preview": src.get("content", "")[:80] + "...",
            })
        return pd.DataFrame(rows)

    def to_csv(self, df: pd.DataFrame, filename: str = "data.csv") -> bytes:
        """Export DataFrame to CSV bytes."""
        buf = io.StringIO()
        df.to_csv(buf, index=False)
        return buf.getvalue().encode("utf-8")

    # ── Private Helpers ──────────────────────────────────────

    def _extract_markdown_table(self, text: str) -> Optional[pd.DataFrame]:
        """Extract a markdown-style table."""
        lines = text.split("\n")
        table_lines = []
        in_table = False

        for line in lines:
            stripped = line.strip()
            if "|" in stripped and stripped.startswith("|"):
                if re.match(r'\|[\s\-:]+\|', stripped):
                    continue  # Skip separator lines
                cells = [c.strip() for c in stripped.split("|")[1:-1]]
                if cells:
                    table_lines.append(cells)
                    in_table = True
            elif in_table:
                break

        if len(table_lines) >= 2:
            headers = table_lines[0]
            data = table_lines[1:]
            return pd.DataFrame(data, columns=headers)
        return None

    def _extract_key_value_list(self, text: str) -> Optional[pd.DataFrame]:
        """Extract bullet-point key-value pairs."""
        pattern = r'[-•*]\s*(.+?):\s*([\d,.]+\s*(?:%|lakh|crore|mn|bn)?(?:\s*\w+)?)'
        matches = re.findall(pattern, text)

        if len(matches) >= 2:
            return pd.DataFrame({
                "Metric": [m[0].strip() for m in matches],
                "Value": [m[1].strip() for m in matches],
            })
        return None

    def _extract_numbered_data(self, text: str) -> Optional[pd.DataFrame]:
        """Extract numbered list items with data."""
        pattern = r'\d+\.\s+\*{0,2}(.+?)\*{0,2}[:\s—–-]+([\d,.]+\s*\S*)'
        matches = re.findall(pattern, text)

        if len(matches) >= 2:
            return pd.DataFrame({
                "Item": [m[0].strip() for m in matches],
                "Value": [m[1].strip() for m in matches],
            })
        return None

    def _parse_number(self, s: str) -> float:
        s = s.replace(",", "").strip()
        try:
            return float(s)
        except ValueError:
            return 0.0
