"""
Excel Builder — Professional Excel Report Generation.

Uses openpyxl to create styled Excel workbooks with multiple
sheets for data, charts, sources, and summaries.
"""

import io
from typing import List, Dict, Any, Optional
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import (
    Font, PatternFill, Alignment, Border, Side, numbers,
)
from openpyxl.utils import get_column_letter
from openpyxl.chart import BarChart, PieChart, Reference

import pandas as pd


# ── Brand Styling ────────────────────────────────────────────
BRAND_PRIMARY = "3C8C81"
BRAND_DARK = "2D6A5F"
BRAND_ACCENT = "E8764D"
BRAND_BG = "F0F4F3"
BRAND_TEXT = "2C3E50"
WHITE = "FFFFFF"
LIGHT_GRAY = "F8F9FA"
BORDER_COLOR = "DEE2E6"

HEADER_FONT = Font(name="Calibri", size=11, bold=True, color=WHITE)
HEADER_FILL = PatternFill("solid", fgColor=BRAND_PRIMARY)
BODY_FONT = Font(name="Calibri", size=10, color=BRAND_TEXT)
TITLE_FONT = Font(name="Calibri", size=16, bold=True, color=BRAND_TEXT)
SUBTITLE_FONT = Font(name="Calibri", size=11, color="7F8C8D")
KPI_VALUE_FONT = Font(name="Calibri", size=14, bold=True, color=BRAND_PRIMARY)
KPI_LABEL_FONT = Font(name="Calibri", size=9, color="7F8C8D")
THIN_BORDER = Border(
    left=Side(style="thin", color=BORDER_COLOR),
    right=Side(style="thin", color=BORDER_COLOR),
    top=Side(style="thin", color=BORDER_COLOR),
    bottom=Side(style="thin", color=BORDER_COLOR),
)
ALT_ROW_FILL = PatternFill("solid", fgColor=LIGHT_GRAY)


class ExcelBuilder:
    """Builds professional Excel reports with styled sheets."""

    def __init__(self, title: str = "RAG Analysis Report"):
        self.wb = Workbook()
        self.title = title
        # Remove default sheet
        self.wb.remove(self.wb.active)

    def add_summary_sheet(
        self,
        query: str,
        answer: str,
        kpis: Dict[str, Any] = None,
        metadata: Dict[str, Any] = None,
    ):
        """Add a summary sheet with the query, answer, and KPIs."""
        ws = self.wb.create_sheet("Summary")

        # Title
        ws.merge_cells("A1:F1")
        ws["A1"] = self.title
        ws["A1"].font = TITLE_FONT

        # Subtitle
        ws.merge_cells("A2:F2")
        ws["A2"] = f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
        ws["A2"].font = SUBTITLE_FONT

        # Query
        row = 4
        ws[f"A{row}"] = "Query"
        ws[f"A{row}"].font = Font(name="Calibri", size=11, bold=True, color=BRAND_PRIMARY)
        row += 1
        ws.merge_cells(f"A{row}:F{row}")
        ws[f"A{row}"] = query
        ws[f"A{row}"].font = BODY_FONT
        ws[f"A{row}"].alignment = Alignment(wrap_text=True)
        ws.row_dimensions[row].height = 40

        # KPIs
        if kpis:
            row += 2
            ws[f"A{row}"] = "Key Metrics"
            ws[f"A{row}"].font = Font(name="Calibri", size=12, bold=True, color=BRAND_PRIMARY)
            row += 1

            col = 1
            for key, val in kpis.items():
                cell_val = ws.cell(row=row, column=col)
                val_str = f"{val:,.1f}" if isinstance(val, float) and val != int(val) else str(val)
                cell_val.value = val_str
                cell_val.font = KPI_VALUE_FONT
                cell_val.alignment = Alignment(horizontal="center")

                cell_lbl = ws.cell(row=row + 1, column=col)
                cell_lbl.value = key
                cell_lbl.font = KPI_LABEL_FONT
                cell_lbl.alignment = Alignment(horizontal="center")

                # Background
                cell_val.fill = PatternFill("solid", fgColor=BRAND_BG)
                cell_lbl.fill = PatternFill("solid", fgColor=BRAND_BG)
                cell_val.border = THIN_BORDER
                cell_lbl.border = THIN_BORDER

                col += 1
                if col > 6:
                    break

            row += 3

        # Answer
        row += 1
        ws[f"A{row}"] = "Analysis"
        ws[f"A{row}"].font = Font(name="Calibri", size=12, bold=True, color=BRAND_PRIMARY)
        row += 1

        # Split answer into manageable lines
        for para in answer.split("\n"):
            para = para.strip()
            if not para:
                continue
            ws.merge_cells(f"A{row}:F{row}")
            ws[f"A{row}"] = para.replace("**", "").replace("*", "")
            ws[f"A{row}"].font = BODY_FONT
            ws[f"A{row}"].alignment = Alignment(wrap_text=True)
            ws.row_dimensions[row].height = max(15, len(para) // 8)
            row += 1

        # Auto-fit column widths
        for col_idx in range(1, 7):
            ws.column_dimensions[get_column_letter(col_idx)].width = 22

    def add_data_sheet(self, df: pd.DataFrame, name: str = "Data"):
        """Add a DataFrame as a styled data sheet."""
        ws = self.wb.create_sheet(name)

        # Headers
        for col_idx, col_name in enumerate(df.columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.alignment = Alignment(horizontal="center")
            cell.border = THIN_BORDER

        # Data rows
        for row_idx, (_, row) in enumerate(df.iterrows(), 2):
            for col_idx, val in enumerate(row, 1):
                cell = ws.cell(row=row_idx, column=col_idx, value=val)
                cell.font = BODY_FONT
                cell.border = THIN_BORDER
                cell.alignment = Alignment(wrap_text=True)

                # Alternate row colors
                if row_idx % 2 == 0:
                    cell.fill = ALT_ROW_FILL

        # Auto-fit columns
        for col_idx in range(1, len(df.columns) + 1):
            col_letter = get_column_letter(col_idx)
            max_len = max(
                len(str(df.columns[col_idx - 1])),
                df.iloc[:, col_idx - 1].astype(str).str.len().max() if len(df) > 0 else 0,
            )
            ws.column_dimensions[col_letter].width = min(50, max(12, max_len + 4))

    def add_sources_sheet(self, sources: List[dict]):
        """Add source references as a sheet."""
        ws = self.wb.create_sheet("Sources")

        headers = ["Ref #", "Page", "Source", "Score", "Content Type", "Content Preview"]
        for col_idx, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.font = HEADER_FONT
            cell.fill = HEADER_FILL
            cell.border = THIN_BORDER
            cell.alignment = Alignment(horizontal="center")

        for i, src in enumerate(sources, 1):
            row = i + 1
            content = src.get("content", "")
            preview = content[:200] + "..." if len(content) > 200 else content

            values = [
                i,
                src.get("page", "N/A"),
                src.get("source", "Unknown"),
                round(src.get("score", 0), 3),
                src.get("content_type", "text"),
                preview,
            ]

            for col_idx, val in enumerate(values, 1):
                cell = ws.cell(row=row, column=col_idx, value=val)
                cell.font = BODY_FONT
                cell.border = THIN_BORDER
                cell.alignment = Alignment(wrap_text=True, vertical="top")
                if row % 2 == 0:
                    cell.fill = ALT_ROW_FILL

        # Column widths
        widths = [6, 8, 25, 10, 12, 60]
        for col_idx, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(col_idx)].width = w

    def add_chart_sheet(
        self,
        data: Dict[str, float],
        chart_type: str = "bar",
        sheet_name: str = "Chart",
    ):
        """Add a sheet with an embedded Excel chart."""
        ws = self.wb.create_sheet(sheet_name)

        # Write data
        ws["A1"] = "Category"
        ws["B1"] = "Value"
        ws["A1"].font = HEADER_FONT
        ws["A1"].fill = HEADER_FILL
        ws["B1"].font = HEADER_FONT
        ws["B1"].fill = HEADER_FILL

        for i, (key, val) in enumerate(data.items(), 2):
            ws[f"A{i}"] = key
            ws[f"B{i}"] = val
            ws[f"A{i}"].font = BODY_FONT
            ws[f"B{i}"].font = BODY_FONT

        # Create chart
        if chart_type == "pie":
            chart = PieChart()
            chart.title = sheet_name
            data_ref = Reference(ws, min_col=2, min_row=1, max_row=len(data) + 1)
            cats = Reference(ws, min_col=1, min_row=2, max_row=len(data) + 1)
            chart.add_data(data_ref, titles_from_data=True)
            chart.set_categories(cats)
        else:
            chart = BarChart()
            chart.title = sheet_name
            chart.type = "col"
            data_ref = Reference(ws, min_col=2, min_row=1, max_row=len(data) + 1)
            cats = Reference(ws, min_col=1, min_row=2, max_row=len(data) + 1)
            chart.add_data(data_ref, titles_from_data=True)
            chart.set_categories(cats)
            chart.shape = 4

        chart.width = 18
        chart.height = 12
        ws.add_chart(chart, "D2")

        ws.column_dimensions["A"].width = 25
        ws.column_dimensions["B"].width = 15

    def build(self, output_path: str = None) -> bytes:
        """Build the Excel file and return as bytes."""
        buf = io.BytesIO()
        self.wb.save(buf)
        buf.seek(0)
        data = buf.getvalue()

        if output_path:
            with open(output_path, "wb") as f:
                f.write(data)

        return data


# ── Convenience Function ─────────────────────────────────────

def generate_excel_report(
    query: str,
    answer: str,
    sources: List[dict] = None,
    kpis: Dict[str, Any] = None,
    dataframes: Dict[str, pd.DataFrame] = None,
    title: str = "RAG Analysis Report",
    output_path: str = None,
) -> bytes:
    """One-call function to generate a complete Excel report."""
    xls = ExcelBuilder(title=title)

    # Summary
    xls.add_summary_sheet(query, answer, kpis=kpis)

    # Data sheets
    if dataframes:
        for name, df in dataframes.items():
            xls.add_data_sheet(df, name=name[:31])

    # KPI chart
    if kpis:
        xls.add_chart_sheet(kpis, chart_type="bar", sheet_name="KPI Chart")

    # Sources
    if sources:
        xls.add_sources_sheet(sources)

    return xls.build(output_path)
