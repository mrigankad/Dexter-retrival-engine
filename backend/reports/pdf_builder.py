"""
PDF Builder — Professional PDF Report Generation.

Uses ReportLab to create polished, corporate-style PDF reports
from RAG query results with charts, tables, and source citations.
"""

import io
import os
import textwrap
from datetime import datetime
from typing import List, Optional, Dict, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm, cm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.lib.colors import HexColor


# ── Brand Colors ─────────────────────────────────────────────
BRAND_PRIMARY = HexColor("#3C8C81")
BRAND_DARK = HexColor("#2D6A5F")
BRAND_ACCENT = HexColor("#E8764D")
BRAND_BG = HexColor("#F0F4F3")
BRAND_TEXT = HexColor("#2C3E50")
BRAND_MUTED = HexColor("#7F8C8D")
WHITE = colors.white
LIGHT_GRAY = HexColor("#F8F9FA")
BORDER_GRAY = HexColor("#DEE2E6")


class PDFBuilder:
    """Builds professional PDF reports using ReportLab."""

    def __init__(
        self,
        title: str = "RAG Analysis Report",
        subtitle: str = "",
        brand_color: str = "#3C8C81",
    ):
        self.title = title
        self.subtitle = subtitle
        self.brand_color = HexColor(brand_color)
        self.elements = []
        self.styles = self._create_styles()

    def _create_styles(self) -> Dict[str, ParagraphStyle]:
        """Create custom paragraph styles."""
        base = getSampleStyleSheet()
        styles = {}

        styles["title"] = ParagraphStyle(
            "CustomTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            textColor=BRAND_TEXT,
            spaceAfter=6,
            alignment=TA_LEFT,
        )

        styles["subtitle"] = ParagraphStyle(
            "CustomSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            textColor=BRAND_MUTED,
            spaceAfter=20,
        )

        styles["section_header"] = ParagraphStyle(
            "SectionHeader",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            textColor=BRAND_PRIMARY,
            spaceBefore=20,
            spaceAfter=10,
            borderWidth=0,
            borderPadding=0,
        )

        styles["subsection"] = ParagraphStyle(
            "SubSection",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=BRAND_TEXT,
            spaceBefore=12,
            spaceAfter=6,
        )

        styles["body"] = ParagraphStyle(
            "BodyText",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=BRAND_TEXT,
            leading=14,
            spaceAfter=8,
            alignment=TA_JUSTIFY,
        )

        styles["body_bold"] = ParagraphStyle(
            "BodyBold",
            parent=styles["body"],
            fontName="Helvetica-Bold",
        )

        styles["quote"] = ParagraphStyle(
            "Quote",
            parent=styles["body"],
            fontName="Helvetica-Oblique",
            fontSize=10,
            textColor=BRAND_MUTED,
            leftIndent=20,
            rightIndent=20,
            spaceBefore=6,
            spaceAfter=6,
        )

        styles["source_ref"] = ParagraphStyle(
            "SourceRef",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=BRAND_MUTED,
            leading=11,
            spaceAfter=4,
        )

        styles["footer"] = ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=BRAND_MUTED,
            alignment=TA_CENTER,
        )

        styles["kpi_value"] = ParagraphStyle(
            "KPIValue",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=18,
            textColor=BRAND_PRIMARY,
            alignment=TA_CENTER,
        )

        styles["kpi_label"] = ParagraphStyle(
            "KPILabel",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=BRAND_MUTED,
            alignment=TA_CENTER,
        )

        return styles

    # ── Header ───────────────────────────────────────────────

    def add_header(self, query: str = ""):
        """Add report header with title and metadata."""
        # Title
        self.elements.append(Paragraph(self.title, self.styles["title"]))

        if self.subtitle:
            self.elements.append(Paragraph(self.subtitle, self.styles["subtitle"]))

        # Metadata bar
        now = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        meta_text = f"<font color='#7F8C8D'>Generated: {now}</font>"
        self.elements.append(Paragraph(meta_text, self.styles["source_ref"]))

        # Divider
        self.elements.append(Spacer(1, 8))
        self.elements.append(HRFlowable(
            width="100%", thickness=2, color=BRAND_PRIMARY,
            spaceBefore=2, spaceAfter=12,
        ))

        # Query box
        if query:
            query_table = Table(
                [[Paragraph(
                    f"<b>Query:</b> {self._escape(query)}",
                    self.styles["body"],
                )]],
                colWidths=[460],
            )
            query_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_BG),
                ("BOX", (0, 0), (-1, -1), 1, BRAND_PRIMARY),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
            ]))
            self.elements.append(query_table)
            self.elements.append(Spacer(1, 14))

    # ── Sections ─────────────────────────────────────────────

    def add_section(self, title: str, content: str):
        """Add a titled section with formatted body text."""
        if title:
            self.elements.append(Paragraph(title, self.styles["section_header"]))

        # Process content paragraphs
        paragraphs = content.split("\n\n") if "\n\n" in content else content.split("\n")

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Format bullet points
            if para.startswith(("- ", "• ", "* ")):
                bullet_text = para[2:].strip()
                self.elements.append(Paragraph(
                    f"&bull; {self._escape(bullet_text)}", self.styles["body"],
                ))
            # Format numbered points
            elif re.match(r'^\d+\.', para):
                self.elements.append(Paragraph(self._escape(para), self.styles["body"]))
            # Bold headers within content
            elif para.startswith("**") and para.endswith("**"):
                self.elements.append(Paragraph(
                    para.strip("*"), self.styles["subsection"],
                ))
            else:
                self.elements.append(Paragraph(self._escape(para), self.styles["body"]))

        self.elements.append(Spacer(1, 6))

    def add_answer(self, answer: str, section_title: str = "Analysis"):
        """Add the RAG answer as the main body, intelligently formatted."""
        self.elements.append(Paragraph(section_title, self.styles["section_header"]))

        # Clean up markdown formatting
        lines = answer.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                self.elements.append(Spacer(1, 4))
                continue

            # Headers (### or **)
            if line.startswith("### "):
                self.elements.append(Paragraph(
                    self._escape(line[4:]), self.styles["subsection"],
                ))
            elif line.startswith("## "):
                self.elements.append(Paragraph(
                    self._escape(line[3:]), self.styles["section_header"],
                ))
            elif line.startswith("**") and line.endswith("**"):
                self.elements.append(Paragraph(
                    self._escape(line.strip("*")), self.styles["body_bold"],
                ))
            # Bullet points
            elif line.startswith(("- ", "• ", "* ")):
                text = line[2:].strip()
                # Handle bold within bullets
                text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
                self.elements.append(Paragraph(
                    f"&bull; {self._escape_partial(text)}", self.styles["body"],
                ))
            # Numbered points
            elif re.match(r'^\d+\.', line):
                text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
                self.elements.append(Paragraph(
                    self._escape_partial(text), self.styles["body"],
                ))
            # Regular text
            else:
                text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', line)
                self.elements.append(Paragraph(
                    self._escape_partial(text), self.styles["body"],
                ))

        self.elements.append(Spacer(1, 10))

    # ── Charts ───────────────────────────────────────────────

    def add_chart(self, chart_bytes: bytes, caption: str = "", width: float = 5.5):
        """Add a chart image to the report."""
        img_buf = io.BytesIO(chart_bytes)
        img = Image(img_buf, width=width * inch, height=width * 0.625 * inch)

        items = [img]
        if caption:
            items.append(Spacer(1, 4))
            items.append(Paragraph(
                f"<i>{self._escape(caption)}</i>", self.styles["source_ref"],
            ))

        self.elements.append(KeepTogether(items))
        self.elements.append(Spacer(1, 12))

    # ── Tables ───────────────────────────────────────────────

    def add_table(self, data: list, headers: list = None, title: str = ""):
        """Add a styled data table."""
        if title:
            self.elements.append(Paragraph(title, self.styles["subsection"]))
            self.elements.append(Spacer(1, 4))

        table_data = []
        if headers:
            table_data.append(headers)
        table_data.extend(data)

        # Wrap long text in cells
        wrapped_data = []
        for row in table_data:
            wrapped_row = []
            for cell in row:
                cell_str = str(cell) if cell is not None else ""
                if len(cell_str) > 50:
                    wrapped_row.append(Paragraph(self._escape(cell_str), self.styles["source_ref"]))
                else:
                    wrapped_row.append(cell_str)
            wrapped_data.append(wrapped_row)

        n_cols = len(wrapped_data[0]) if wrapped_data else 1
        col_width = 460 / n_cols

        table = Table(wrapped_data, colWidths=[col_width] * n_cols)

        style_cmds = [
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (-1, -1), BRAND_TEXT),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ]

        if headers:
            style_cmds.extend([
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
            ])

        # Alternate row colors
        for i in range(1 if headers else 0, len(wrapped_data)):
            if i % 2 == 0:
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), LIGHT_GRAY))

        table.setStyle(TableStyle(style_cmds))
        self.elements.append(table)
        self.elements.append(Spacer(1, 12))

    def add_dataframe(self, df, title: str = ""):
        """Add a pandas DataFrame as a table."""
        headers = list(df.columns)
        data = df.values.tolist()
        self.add_table(data, headers=headers, title=title)

    # ── KPI Cards ────────────────────────────────────────────

    def add_kpi_cards(self, kpis: Dict[str, Any], title: str = "Key Metrics"):
        """Add KPI summary cards."""
        if not kpis:
            return

        self.elements.append(Paragraph(title, self.styles["section_header"]))
        self.elements.append(Spacer(1, 6))

        items = list(kpis.items())
        # Layout 3 per row
        for i in range(0, len(items), 3):
            row_items = items[i:i + 3]
            cells = []

            for key, val in row_items:
                val_str = f"{val:,.1f}" if isinstance(val, float) and val != int(val) else f"{int(val):,}" if isinstance(val, (int, float)) else str(val)
                cell_content = [
                    Paragraph(val_str, self.styles["kpi_value"]),
                    Spacer(1, 3),
                    Paragraph(key, self.styles["kpi_label"]),
                ]
                cells.append(cell_content)

            # Pad to 3 columns
            while len(cells) < 3:
                cells.append([Paragraph("", self.styles["body"])])

            kpi_table = Table([cells], colWidths=[153] * 3)
            kpi_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_BG),
                ("BOX", (0, 0), (0, 0), 1, BRAND_PRIMARY),
                ("BOX", (1, 0), (1, 0), 1, BRAND_PRIMARY),
                ("BOX", (2, 0), (2, 0), 1, BRAND_PRIMARY),
                ("TOPPADDING", (0, 0), (-1, -1), 12),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]))
            self.elements.append(kpi_table)
            self.elements.append(Spacer(1, 6))

        self.elements.append(Spacer(1, 8))

    # ── Sources ──────────────────────────────────────────────

    def add_sources(self, sources: List[dict], title: str = "Source References"):
        """Add source citations table."""
        if not sources:
            return

        self.elements.append(Paragraph(title, self.styles["section_header"]))
        self.elements.append(Spacer(1, 4))

        headers = ["Ref", "Page", "Source", "Score", "Content Preview"]
        data = []
        for i, src in enumerate(sources, 1):
            content = src.get("content", "")
            preview = content[:100] + "..." if len(content) > 100 else content
            data.append([
                str(i),
                str(src.get("page", "N/A")),
                str(src.get("source", "Unknown")),
                f"{src.get('score', 0):.3f}",
                preview,
            ])

        self.add_table(data, headers=headers)

    # ── Page Break ───────────────────────────────────────────

    def add_page_break(self):
        self.elements.append(PageBreak())

    # ── Build ────────────────────────────────────────────────

    def build(self, output_path: str = None) -> bytes:
        """Build the PDF and return as bytes (or save to file)."""
        buf = io.BytesIO()

        doc = SimpleDocTemplate(
            buf if not output_path else output_path,
            pagesize=A4,
            topMargin=25 * mm,
            bottomMargin=20 * mm,
            leftMargin=20 * mm,
            rightMargin=20 * mm,
            title=self.title,
            author="RAG Analysis Engine",
        )

        def add_page_footer(canvas, doc):
            """Add footer with page number and branding."""
            canvas.saveState()
            page_text = f"Page {doc.page}"
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(BRAND_MUTED)
            canvas.drawString(20 * mm, 10 * mm, "Generated by RAG Analysis Engine")
            canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, page_text)

            # Top brand line
            canvas.setStrokeColor(BRAND_PRIMARY)
            canvas.setLineWidth(2)
            canvas.line(20 * mm, A4[1] - 15 * mm, A4[0] - 20 * mm, A4[1] - 15 * mm)
            canvas.restoreState()

        doc.build(self.elements, onFirstPage=add_page_footer, onLaterPages=add_page_footer)

        if not output_path:
            buf.seek(0)
            return buf.getvalue()
        return b""

    # ── Helpers ───────────────────────────────────────────────

    def _escape(self, text: str) -> str:
        """Escape text for ReportLab XML."""
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        return text

    def _escape_partial(self, text: str) -> str:
        """Escape text but preserve allowed HTML tags like <b>."""
        # Temporarily protect <b> and </b>
        text = text.replace("<b>", "%%BOLD_OPEN%%")
        text = text.replace("</b>", "%%BOLD_CLOSE%%")
        text = self._escape(text)
        text = text.replace("%%BOLD_OPEN%%", "<b>")
        text = text.replace("%%BOLD_CLOSE%%", "</b>")
        return text


# ── Convenience Function ─────────────────────────────────────

import re

def generate_pdf_report(
    query: str,
    answer: str,
    sources: List[dict] = None,
    charts: List[tuple] = None,
    kpis: Dict[str, Any] = None,
    title: str = "RAG Analysis Report",
    output_path: str = None,
) -> bytes:
    """One-call function to generate a complete PDF report.

    Args:
        query: The original user question
        answer: The RAG-generated answer
        sources: List of source chunk dicts
        charts: List of (png_bytes, caption) tuples
        kpis: Dict of KPI name -> value
        title: Report title
        output_path: Optional file path to save

    Returns:
        PDF bytes
    """
    pdf = PDFBuilder(title=title, subtitle="RAG-Powered Analysis Report")

    # Header
    pdf.add_header(query=query)

    # KPIs
    if kpis:
        pdf.add_kpi_cards(kpis)

    # Charts
    if charts:
        pdf.add_section("Data Visualization", "")
        for chart_bytes, caption in charts:
            pdf.add_chart(chart_bytes, caption=caption)

    # Answer
    pdf.add_answer(answer, section_title="Detailed Analysis")

    # Sources
    if sources:
        pdf.add_page_break()
        pdf.add_sources(sources)

    return pdf.build(output_path)
