"""
Chart Engine — Intelligent Chart Generation.

Auto-detects numerical data in RAG answers and generates
appropriate visualizations using Matplotlib.
"""

import re
import io
import textwrap
from typing import List, Dict, Any, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
from matplotlib.patches import FancyBboxPatch
import numpy as np


# Corporate color palette
BRAND_COLORS = {
    "primary": "#3C8C81",
    "secondary": "#2D6A5F",
    "accent": "#E8764D",
    "dark": "#1A1A2E",
    "light": "#F0F4F3",
    "text": "#2C3E50",
    "muted": "#95A5A6",
    "success": "#27AE60",
    "warning": "#F39C12",
    "danger": "#E74C3C",
}

CHART_PALETTE = [
    "#3C8C81", "#E8764D", "#5B8DEF", "#F5A623",
    "#9B59B6", "#1ABC9C", "#E74C3C", "#34495E",
    "#2ECC71", "#3498DB", "#E67E22", "#C0392B",
]


class ChartData:
    """Structured data for chart generation."""

    def __init__(
        self,
        labels: List[str],
        values: List[float],
        chart_type: str = "bar",
        title: str = "",
        xlabel: str = "",
        ylabel: str = "",
        series_name: str = "",
        secondary_values: Optional[List[float]] = None,
        secondary_name: str = "",
        unit: str = "",
    ):
        self.labels = labels
        self.values = values
        self.chart_type = chart_type
        self.title = title
        self.xlabel = xlabel
        self.ylabel = ylabel
        self.series_name = series_name
        self.secondary_values = secondary_values
        self.secondary_name = secondary_name
        self.unit = unit


class ChartEngine:
    """Generates charts from structured and unstructured data."""

    def __init__(self, brand_color: str = "#3C8C81", accent_color: str = "#2D6A5F"):
        self.brand_color = brand_color
        self.accent_color = accent_color
        self._setup_style()

    def _setup_style(self):
        """Configure matplotlib global style."""
        plt.rcParams.update({
            "font.family": "sans-serif",
            "font.sans-serif": ["Segoe UI", "Arial", "Helvetica", "sans-serif"],
            "font.size": 11,
            "axes.titlesize": 14,
            "axes.titleweight": "bold",
            "axes.labelsize": 11,
            "axes.facecolor": "#FAFAFA",
            "axes.edgecolor": "#E0E0E0",
            "axes.grid": True,
            "grid.alpha": 0.3,
            "grid.color": "#CCCCCC",
            "figure.facecolor": "white",
            "figure.dpi": 150,
        })

    # ── Data Extraction ──────────────────────────────────────

    def detect_chartable_data(self, answer: str, sources: List[dict] = None) -> List[ChartData]:
        """Auto-detect numerical data in RAG answer text and return ChartData objects."""
        charts = []

        # Pattern 1: Bullet-point lists with numbers
        # e.g., "- Employees: 0.25\n- Workers: 0.19"
        bullet_pattern = r'(?:[-•*]\s*(.+?):\s*([\d,.]+)\s*(%|lakh|crore|mn|bn)?)'
        bullet_matches = re.findall(bullet_pattern, answer, re.IGNORECASE)
        if len(bullet_matches) >= 2:
            labels = [m[0].strip() for m in bullet_matches]
            values = [self._parse_number(m[1]) for m in bullet_matches]
            unit = bullet_matches[0][2] if bullet_matches[0][2] else ""
            charts.append(ChartData(
                labels=labels,
                values=values,
                chart_type="bar",
                title="Key Metrics",
                ylabel=unit,
                unit=unit,
            ))

        # Pattern 2: FY comparisons
        # e.g., "FY 2024-25: 0.25" or "FY2024: 5"
        fy_pattern = r'FY\s*(\d{2,4}(?:-\d{2,4})?)[:\s]+([\d,.]+)\s*(%|lakh|crore)?'
        fy_matches = re.findall(fy_pattern, answer, re.IGNORECASE)
        if len(fy_matches) >= 2:
            labels = [f"FY {m[0]}" for m in fy_matches]
            values = [self._parse_number(m[1]) for m in fy_matches]
            unit = fy_matches[0][2] if fy_matches[0][2] else ""
            charts.append(ChartData(
                labels=labels,
                values=values,
                chart_type="bar",
                title="Year-over-Year Comparison",
                xlabel="Financial Year",
                unit=unit,
            ))

        # Pattern 3: Percentage distributions
        pct_pattern = r'(.+?)\s*(?:accounts?\s*for|is|are|stands?\s*at)\s*([\d,.]+)\s*%'
        pct_matches = re.findall(pct_pattern, answer, re.IGNORECASE)
        if len(pct_matches) >= 2:
            labels = [m[0].strip()[-40:] for m in pct_matches]
            values = [self._parse_number(m[1]) for m in pct_matches]
            charts.append(ChartData(
                labels=labels,
                values=values,
                chart_type="pie",
                title="Distribution",
                unit="%",
            ))

        # Pattern 4: Large numbered lists (e.g., "1. Safety observations: 5.5 lakh")
        num_list_pattern = r'(?:\d+\.\s*)(.+?)(?::\s*|—\s*|–\s*)([\d,.]+)\s*(lakh|crore|%|observations|employees|workers)?'
        num_matches = re.findall(num_list_pattern, answer, re.IGNORECASE)
        if len(num_matches) >= 3 and not charts:
            labels = [m[0].strip()[:30] for m in num_matches[:8]]
            values = [self._parse_number(m[1]) for m in num_matches[:8]]
            unit = num_matches[0][2] if num_matches[0][2] else ""
            charts.append(ChartData(
                labels=labels,
                values=values,
                chart_type="hbar",
                title="Key Data Points",
                unit=unit,
            ))

        # Pattern 5: Key statistics from source context
        if sources and not charts:
            stat_data = self._extract_stats_from_sources(sources)
            if stat_data:
                charts.append(stat_data)

        return charts

    def _extract_stats_from_sources(self, sources: List[dict]) -> Optional[ChartData]:
        """Try to extract statistics from source chunks."""
        all_text = " ".join(s.get("content", "") for s in sources)

        # Look for tabular number patterns
        number_pattern = r'([\w\s]+?)\s+([\d,.]+)\s+([\d,.]+)'
        matches = re.findall(number_pattern, all_text)

        if len(matches) >= 2:
            labels = [m[0].strip()[:25] for m in matches[:6]]
            values = [self._parse_number(m[1]) for m in matches[:6]]
            return ChartData(
                labels=labels,
                values=values,
                chart_type="bar",
                title="Extracted Data Points",
            )
        return None

    def _parse_number(self, s: str) -> float:
        """Parse a number string into float."""
        s = s.replace(",", "").strip()
        try:
            return float(s)
        except ValueError:
            return 0.0

    # ── Chart Generation ─────────────────────────────────────

    def generate_chart(self, data: ChartData, width: float = 8, height: float = 5) -> bytes:
        """Generate a chart as PNG bytes."""
        generators = {
            "bar": self._gen_bar,
            "hbar": self._gen_hbar,
            "line": self._gen_line,
            "pie": self._gen_pie,
            "stacked_bar": self._gen_stacked_bar,
            "gauge": self._gen_gauge,
            "table_chart": self._gen_table_chart,
        }

        gen_func = generators.get(data.chart_type, self._gen_bar)
        fig = gen_func(data, width, height)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight", dpi=150, facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()

    def generate_all_charts(self, answer: str, sources: List[dict] = None) -> List[Tuple[bytes, str]]:
        """auto-detect and generate all possible charts from an answer.
        Returns list of (png_bytes, title) tuples."""
        chart_datas = self.detect_chartable_data(answer, sources)
        results = []
        for cd in chart_datas:
            png = self.generate_chart(cd)
            results.append((png, cd.title))
        return results

    # ── Individual Chart Generators ──────────────────────────

    def _gen_bar(self, data: ChartData, w: float, h: float) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(w, h))
        x = np.arange(len(data.labels))
        bars = ax.bar(x, data.values, color=CHART_PALETTE[:len(data.values)],
                      edgecolor="white", linewidth=0.5, width=0.6)

        if data.secondary_values:
            ax.bar(x + 0.3, data.secondary_values, color=CHART_PALETTE[1],
                   edgecolor="white", linewidth=0.5, width=0.3, alpha=0.7,
                   label=data.secondary_name)
            ax.legend()

        # Value labels on bars
        for bar, val in zip(bars, data.values):
            label = f"{val:,.1f}" if val != int(val) else f"{int(val):,}"
            if data.unit:
                label += f" {data.unit}"
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(data.values) * 0.02,
                    label, ha="center", va="bottom", fontsize=9, fontweight="bold",
                    color=BRAND_COLORS["text"])

        ax.set_xticks(x)
        ax.set_xticklabels([textwrap.fill(l, 15) for l in data.labels], fontsize=9)
        ax.set_title(data.title, pad=15, color=BRAND_COLORS["dark"])
        if data.xlabel:
            ax.set_xlabel(data.xlabel)
        if data.ylabel:
            ax.set_ylabel(data.ylabel)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_ylim(0, max(data.values) * 1.15)
        fig.tight_layout()
        return fig

    def _gen_hbar(self, data: ChartData, w: float, h: float) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(w, max(h, len(data.labels) * 0.6)))
        y = np.arange(len(data.labels))
        bars = ax.barh(y, data.values, color=CHART_PALETTE[:len(data.values)],
                       edgecolor="white", linewidth=0.5, height=0.5)

        for bar, val in zip(bars, data.values):
            label = f"{val:,.1f}" if val != int(val) else f"{int(val):,}"
            if data.unit:
                label += f" {data.unit}"
            ax.text(bar.get_width() + max(data.values) * 0.02, bar.get_y() + bar.get_height() / 2,
                    label, ha="left", va="center", fontsize=9, fontweight="bold")

        ax.set_yticks(y)
        ax.set_yticklabels([textwrap.fill(l, 25) for l in data.labels], fontsize=9)
        ax.set_title(data.title, pad=15, color=BRAND_COLORS["dark"])
        ax.spines[["top", "right"]].set_visible(False)
        ax.invert_yaxis()
        fig.tight_layout()
        return fig

    def _gen_line(self, data: ChartData, w: float, h: float) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(w, h))
        ax.plot(data.labels, data.values, color=self.brand_color, linewidth=2.5,
                marker="o", markersize=8, markerfacecolor="white", markeredgewidth=2,
                markeredgecolor=self.brand_color)

        # Fill under curve
        ax.fill_between(range(len(data.labels)), data.values, alpha=0.1, color=self.brand_color)

        for i, val in enumerate(data.values):
            label = f"{val:,.1f}"
            ax.text(i, val + max(data.values) * 0.03, label, ha="center", fontsize=9, fontweight="bold")

        ax.set_title(data.title, pad=15, color=BRAND_COLORS["dark"])
        if data.xlabel:
            ax.set_xlabel(data.xlabel)
        if data.ylabel:
            ax.set_ylabel(data.ylabel)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        return fig

    def _gen_pie(self, data: ChartData, w: float, h: float) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(w, h))
        colors = CHART_PALETTE[:len(data.values)]

        wedges, texts, autotexts = ax.pie(
            data.values, labels=None, colors=colors, autopct="%1.1f%%",
            startangle=90, pctdistance=0.75, wedgeprops=dict(width=0.4, edgecolor="white"),
        )

        for t in autotexts:
            t.set_fontsize(9)
            t.set_fontweight("bold")

        ax.legend(wedges, data.labels, loc="center left", bbox_to_anchor=(1, 0.5),
                  fontsize=9, frameon=False)
        ax.set_title(data.title, pad=15, color=BRAND_COLORS["dark"])
        fig.tight_layout()
        return fig

    def _gen_stacked_bar(self, data: ChartData, w: float, h: float) -> plt.Figure:
        fig, ax = plt.subplots(figsize=(w, h))
        x = np.arange(len(data.labels))

        ax.bar(x, data.values, color=CHART_PALETTE[0], label=data.series_name or "Series 1",
               edgecolor="white", width=0.5)
        if data.secondary_values:
            ax.bar(x, data.secondary_values, bottom=data.values, color=CHART_PALETTE[1],
                   label=data.secondary_name or "Series 2", edgecolor="white", width=0.5)

        ax.set_xticks(x)
        ax.set_xticklabels(data.labels, fontsize=9)
        ax.set_title(data.title, pad=15, color=BRAND_COLORS["dark"])
        ax.legend(frameon=False)
        ax.spines[["top", "right"]].set_visible(False)
        fig.tight_layout()
        return fig

    def _gen_gauge(self, data: ChartData, w: float, h: float) -> plt.Figure:
        """Generate a gauge/KPI card chart."""
        n = len(data.labels)
        cols = min(n, 3)
        rows = (n + cols - 1) // cols
        fig, axes = plt.subplots(rows, cols, figsize=(w, h * rows / 1.5))
        if n == 1:
            axes = [axes]
        else:
            axes = axes.flatten() if hasattr(axes, "flatten") else [axes]

        for i, (label, value) in enumerate(zip(data.labels, data.values)):
            if i >= len(axes):
                break
            ax = axes[i]
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis("off")

            # KPI card
            val_str = f"{value:,.1f}" if value != int(value) else f"{int(value):,}"
            if data.unit:
                val_str += f" {data.unit}"
            ax.text(0.5, 0.6, val_str, ha="center", va="center",
                    fontsize=24, fontweight="bold", color=self.brand_color)
            ax.text(0.5, 0.3, label, ha="center", va="center",
                    fontsize=11, color=BRAND_COLORS["text"])
            ax.add_patch(FancyBboxPatch((0.05, 0.1), 0.9, 0.8,
                                        boxstyle="round,pad=0.05",
                                        facecolor=BRAND_COLORS["light"],
                                        edgecolor=self.brand_color, linewidth=1.5))

        # Hide unused axes
        for j in range(i + 1, len(axes)):
            axes[j].axis("off")

        fig.suptitle(data.title, fontsize=14, fontweight="bold", color=BRAND_COLORS["dark"])
        fig.tight_layout()
        return fig

    def _gen_table_chart(self, data: ChartData, w: float, h: float) -> plt.Figure:
        """Render data as a styled table image."""
        fig, ax = plt.subplots(figsize=(w, max(2, len(data.labels) * 0.5 + 1)))
        ax.axis("off")

        cell_data = [[label, f"{val:,.2f}" if val != int(val) else f"{int(val):,}"]
                     for label, val in zip(data.labels, data.values)]
        headers = ["Item", "Value"]

        table = ax.table(cellText=cell_data, colLabels=headers,
                         cellLoc="center", loc="center",
                         colWidths=[0.5, 0.3])
        table.auto_set_font_size(False)
        table.set_fontsize(10)
        table.scale(1.2, 1.5)

        # Style header
        for j in range(2):
            cell = table[0, j]
            cell.set_facecolor(self.brand_color)
            cell.set_text_props(color="white", fontweight="bold")
            cell.set_edgecolor("white")

        # Alternate row colors
        for i in range(1, len(cell_data) + 1):
            for j in range(2):
                cell = table[i, j]
                cell.set_facecolor("#F8F9FA" if i % 2 == 0 else "white")
                cell.set_edgecolor("#E0E0E0")

        ax.set_title(data.title, pad=15, fontsize=13, fontweight="bold",
                     color=BRAND_COLORS["dark"])
        fig.tight_layout()
        return fig

    # ── Utility ──────────────────────────────────────────────

    def create_summary_chart(
        self,
        kpi_data: Dict[str, float],
        title: str = "Key Performance Indicators",
    ) -> bytes:
        """Create a KPI summary card chart from a dictionary."""
        data = ChartData(
            labels=list(kpi_data.keys()),
            values=list(kpi_data.values()),
            chart_type="gauge",
            title=title,
        )
        return self.generate_chart(data, width=10, height=4)
