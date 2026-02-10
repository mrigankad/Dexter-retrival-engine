"""
Chart Understanding Layer - Semantic Chart Analysis Pipeline.

Implements chart analysis:
- Detects chart type from Docling output
- Extracts axis labels, legends, and titles
- Generates semantic chart summaries
- Converts charts into structured insight JSON
- Uses VLM (Vision Language Model) for deep analysis when available
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import re
import json
import hashlib

from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)


CHART_TYPE_INDICATORS = {
    "bar": ["bar chart", "bar graph", "histogram", "column chart"],
    "line": ["line chart", "line graph", "trend line", "time series"],
    "pie": ["pie chart", "donut chart", "pie graph"],
    "scatter": ["scatter plot", "scatter chart", "scatter graph"],
    "area": ["area chart", "area graph", "stacked area"],
    "waterfall": ["waterfall chart", "waterfall graph", "bridge chart"],
    "treemap": ["treemap", "tree map"],
    "heatmap": ["heatmap", "heat map"],
    "sankey": ["sankey diagram", "sankey chart"],
    "gauge": ["gauge chart", "speedometer"],
    "bubble": ["bubble chart", "bubble graph"],
    "radar": ["radar chart", "spider chart", "spider web"],
    "funnel": ["funnel chart", "funnel graph"],
    "candlestick": ["candlestick chart", "ohlc"],
}


@dataclass
class ChartAxis:
    """Represents an axis in a chart."""
    label: str
    data_type: str = "unknown"  # numeric | categorical | temporal
    unit: Optional[str] = None
    min_value: Optional[str] = None
    max_value: Optional[str] = None
    categories: List[str] = field(default_factory=list)


@dataclass
class ChartLegend:
    """Represents a legend entry in a chart."""
    label: str
    color: Optional[str] = None
    pattern: Optional[str] = None


@dataclass
class ChartDataPoint:
    """A single data point extracted from a chart."""
    label: str
    value: Optional[float] = None
    series: Optional[str] = None
    category: Optional[str] = None


@dataclass
class ChartInsight:
    """A semantic insight derived from chart analysis."""
    insight_type: str  # trend | comparison | proportion | outlier | composition
    description: str
    confidence: float = 0.8
    data_points: List[str] = field(default_factory=list)


@dataclass
class ChartAnalysis:
    """Complete chart analysis output."""
    id: str
    page: int
    chart_type: str
    title: Optional[str]
    caption: Optional[str]
    x_axis: Optional[ChartAxis]
    y_axis: Optional[ChartAxis]
    legends: List[ChartLegend]
    data_points: List[ChartDataPoint]
    insights: List[ChartInsight]
    semantic_summary: str
    structured_json: str
    image_path: Optional[str] = None
    confidence: float = 0.7
    is_financial: bool = False
    time_periods: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "page": self.page,
            "chart_type": self.chart_type,
            "title": self.title,
            "caption": self.caption,
            "semantic_summary": self.semantic_summary,
            "structured_json": self.structured_json,
            "is_financial": self.is_financial,
            "confidence": self.confidence,
            "insights": [
                {"type": i.insight_type, "description": i.description}
                for i in self.insights
            ],
        }

    def to_embedding_text(self) -> str:
        """Generate text optimized for semantic embedding."""
        parts = []
        if self.title:
            parts.append(f"Chart Title: {self.title}")
        parts.append(f"Chart Type: {self.chart_type}")
        if self.caption:
            parts.append(f"Caption: {self.caption}")
        parts.append(f"Summary: {self.semantic_summary}")
        for insight in self.insights:
            parts.append(f"Insight ({insight.insight_type}): {insight.description}")
        return "\n".join(parts)


class ChartAnalyzer:
    """
    Chart understanding pipeline for document intelligence.
    
    Analyzes extracted chart/figure regions to produce:
    1. Chart type classification
    2. Axis and legend extraction
    3. Data point estimation
    4. Semantic summary generation
    5. Structured insight JSON
    """

    def __init__(self, llm_service=None):
        """
        Args:
            llm_service: Optional NvidiaLLMService for VLM-based deep analysis
        """
        self.llm = llm_service
        self._time_pattern = re.compile(
            r"(?:FY\s*\d{2,4}|Q[1-4]\s*\d{2,4}|H[12]\s*\d{2,4}|\b20[0-3]\d\b|\b19\d{2}\b)",
            re.IGNORECASE,
        )
        self._financial_pattern = re.compile(
            r"\b(?:revenue|profit|margin|ebitda|sales|income|cost|growth|"
            r"decline|roi|roe|eps|dividend|capex|opex)\b",
            re.IGNORECASE,
        )

    def analyze_chart(
        self,
        chart_id: str,
        page: int,
        chart_type: Optional[str] = None,
        title: Optional[str] = None,
        caption: Optional[str] = None,
        image_path: Optional[str] = None,
        raw_data: Optional[Dict] = None,
        bounding_box: Optional[Dict] = None,
        context_text: str = "",
    ) -> ChartAnalysis:
        """
        Analyze a chart/figure and generate structured insights.
        
        Args:
            chart_id: Unique chart identifier
            page: Source page number
            chart_type: Detected chart type (if known)
            title: Chart title (if detected)
            caption: Chart caption (if detected)
            image_path: Path to chart image
            raw_data: Any raw data extracted from the chart
            bounding_box: Chart bounding box coordinates
            context_text: Surrounding text context
            
        Returns:
            ChartAnalysis with all extracted information
        """
        # Step 1: Classify chart type
        if not chart_type or chart_type == "unknown":
            chart_type = self._classify_chart_type(title, caption, context_text)

        # Step 2: Extract axes
        x_axis, y_axis = self._extract_axes(title, caption, context_text, raw_data)

        # Step 3: Extract legends
        legends = self._extract_legends(raw_data, context_text)

        # Step 4: Extract/estimate data points
        data_points = self._extract_data_points(raw_data, context_text)

        # Step 5: Generate insights
        insights = self._generate_insights(
            chart_type, title, caption, data_points, x_axis, y_axis
        )

        # Step 6: Detect financial nature
        search_text = f"{title or ''} {caption or ''} {context_text}"
        is_financial = bool(self._financial_pattern.search(search_text))
        time_periods = self._time_pattern.findall(search_text)

        # Step 7: Generate summary
        semantic_summary = self._generate_summary(
            chart_type, title, caption, insights,
            x_axis, y_axis, data_points, is_financial
        )

        # Step 8: Build structured JSON
        structured = self._build_structured_json(
            chart_type, title, x_axis, y_axis,
            legends, data_points, insights
        )

        return ChartAnalysis(
            id=chart_id,
            page=page,
            chart_type=chart_type,
            title=title,
            caption=caption,
            x_axis=x_axis,
            y_axis=y_axis,
            legends=legends,
            data_points=data_points,
            insights=insights,
            semantic_summary=semantic_summary,
            structured_json=json.dumps(structured, indent=2),
            image_path=image_path,
            is_financial=is_financial,
            time_periods=time_periods,
        )

    async def analyze_chart_with_vlm(
        self,
        chart_id: str,
        page: int,
        image_path: str,
        context_text: str = "",
    ) -> ChartAnalysis:
        """
        Deep chart analysis using a Vision Language Model.
        Falls back to heuristic analysis if VLM is unavailable.
        """
        if not self.llm:
            logger.warning("VLM unavailable, using heuristic analysis")
            return self.analyze_chart(
                chart_id=chart_id, page=page,
                image_path=image_path, context_text=context_text
            )

        try:
            vlm_prompt = f"""Analyze this chart/figure from a corporate document.

Context from surrounding text: {context_text[:500]}

Please extract:
1. Chart type (bar, line, pie, scatter, etc.)
2. Title and axis labels
3. Key data points or trends visible
4. What business metrics or KPIs are shown
5. Time periods covered (if any)
6. Key takeaways and insights

Respond in JSON format:
{{
    "chart_type": "",
    "title": "",
    "x_axis_label": "",
    "y_axis_label": "",
    "data_points": [{{"label": "", "value": ""}}],
    "trends": [""],
    "insights": [""],
    "is_financial": true/false
}}"""

            response = await self.llm.generate(
                prompt=vlm_prompt,
                max_tokens=800,
                temperature=0.2,
            )

            # Parse VLM response
            vlm_data = self._parse_vlm_response(response)
            
            chart_type = vlm_data.get("chart_type", "unknown")
            title = vlm_data.get("title")

            x_axis = ChartAxis(
                label=vlm_data.get("x_axis_label", ""),
                data_type="categorical"
            )
            y_axis = ChartAxis(
                label=vlm_data.get("y_axis_label", ""),
                data_type="numeric"
            )

            data_points = [
                ChartDataPoint(label=dp.get("label", ""), value=self._safe_float(dp.get("value")))
                for dp in vlm_data.get("data_points", [])
            ]

            insights = [
                ChartInsight(insight_type="vlm_analysis", description=ins, confidence=0.9)
                for ins in vlm_data.get("insights", [])
            ]

            for trend in vlm_data.get("trends", []):
                insights.append(
                    ChartInsight(insight_type="trend", description=trend, confidence=0.85)
                )

            search_text = f"{title or ''} {context_text}"
            is_financial = vlm_data.get("is_financial", False) or bool(
                self._financial_pattern.search(search_text)
            )

            semantic_summary = self._generate_summary(
                chart_type, title, None, insights,
                x_axis, y_axis, data_points, is_financial
            )

            structured = self._build_structured_json(
                chart_type, title, x_axis, y_axis, [], data_points, insights
            )

            return ChartAnalysis(
                id=chart_id,
                page=page,
                chart_type=chart_type,
                title=title,
                caption=None,
                x_axis=x_axis,
                y_axis=y_axis,
                legends=[],
                data_points=data_points,
                insights=insights,
                semantic_summary=semantic_summary,
                structured_json=json.dumps(structured, indent=2),
                image_path=image_path,
                confidence=0.85,
                is_financial=is_financial,
            )

        except Exception as e:
            logger.error("VLM chart analysis failed", error=str(e))
            return self.analyze_chart(
                chart_id=chart_id, page=page,
                image_path=image_path, context_text=context_text
            )

    # ── Internal Methods ───────────────────────────────────────

    def _classify_chart_type(
        self, title: Optional[str], caption: Optional[str], context: str
    ) -> str:
        """Classify chart type from textual cues."""
        search_text = f"{title or ''} {caption or ''} {context}".lower()
        
        for chart_type, indicators in CHART_TYPE_INDICATORS.items():
            for indicator in indicators:
                if indicator in search_text:
                    return chart_type

        # Fallback heuristics
        if any(w in search_text for w in ["trend", "over time", "growth", "quarterly", "yearly"]):
            return "line"
        if any(w in search_text for w in ["distribution", "breakdown", "share", "composition"]):
            return "pie"
        if any(w in search_text for w in ["comparison", "versus", "vs"]):
            return "bar"

        return "unknown"

    def _extract_axes(
        self,
        title: Optional[str],
        caption: Optional[str],
        context: str,
        raw_data: Optional[Dict],
    ) -> tuple:
        """Extract axis information."""
        x_axis = ChartAxis(label="", data_type="categorical")
        y_axis = ChartAxis(label="", data_type="numeric")

        if raw_data:
            x_axis.label = raw_data.get("x_label", "")
            y_axis.label = raw_data.get("y_label", "")
            x_axis.categories = raw_data.get("x_categories", [])
            y_axis.unit = raw_data.get("y_unit")

        # Infer from context if missing
        search_text = f"{title or ''} {caption or ''}"
        if not x_axis.label:
            if self._time_pattern.search(search_text):
                x_axis.label = "Time Period"
                x_axis.data_type = "temporal"

        return x_axis, y_axis

    def _extract_legends(
        self, raw_data: Optional[Dict], context: str
    ) -> List[ChartLegend]:
        """Extract legend entries."""
        legends = []
        if raw_data and "legends" in raw_data:
            for leg in raw_data["legends"]:
                if isinstance(leg, str):
                    legends.append(ChartLegend(label=leg))
                elif isinstance(leg, dict):
                    legends.append(ChartLegend(
                        label=leg.get("label", ""),
                        color=leg.get("color"),
                    ))
        return legends

    def _extract_data_points(
        self, raw_data: Optional[Dict], context: str
    ) -> List[ChartDataPoint]:
        """Extract or estimate data points from the chart."""
        points = []
        if raw_data and "data_points" in raw_data:
            for dp in raw_data["data_points"]:
                if isinstance(dp, dict):
                    points.append(ChartDataPoint(
                        label=dp.get("label", ""),
                        value=self._safe_float(dp.get("value")),
                        series=dp.get("series"),
                        category=dp.get("category"),
                    ))

        # Try to extract numbers from context
        if not points:
            numbers = re.findall(r"\b(\d[\d,]*(?:\.\d+)?)\s*(%|cr|mn|bn)?", context)
            for num_str, unit in numbers[:10]:
                val = self._safe_float(num_str.replace(",", ""))
                if val is not None:
                    points.append(ChartDataPoint(
                        label=f"Value{unit}",
                        value=val,
                    ))

        return points

    def _generate_insights(
        self,
        chart_type: str,
        title: Optional[str],
        caption: Optional[str],
        data_points: List[ChartDataPoint],
        x_axis: Optional[ChartAxis],
        y_axis: Optional[ChartAxis],
    ) -> List[ChartInsight]:
        """Generate semantic insights from chart data."""
        insights = []

        # Chart type-specific insights
        if chart_type == "line":
            if len(data_points) >= 2:
                values = [dp.value for dp in data_points if dp.value is not None]
                if values:
                    if values[-1] > values[0]:
                        insights.append(ChartInsight(
                            insight_type="trend",
                            description=f"Upward trend observed from {values[0]} to {values[-1]}",
                            confidence=0.7,
                        ))
                    elif values[-1] < values[0]:
                        insights.append(ChartInsight(
                            insight_type="trend",
                            description=f"Downward trend observed from {values[0]} to {values[-1]}",
                            confidence=0.7,
                        ))

        elif chart_type == "pie":
            if data_points:
                values = [(dp.label, dp.value) for dp in data_points if dp.value is not None]
                if values:
                    largest = max(values, key=lambda x: x[1])
                    insights.append(ChartInsight(
                        insight_type="proportion",
                        description=f"Largest segment: {largest[0]} at {largest[1]}",
                        confidence=0.7,
                    ))

        elif chart_type == "bar":
            if data_points:
                values = [(dp.label, dp.value) for dp in data_points if dp.value is not None]
                if values:
                    highest = max(values, key=lambda x: x[1])
                    lowest = min(values, key=lambda x: x[1])
                    insights.append(ChartInsight(
                        insight_type="comparison",
                        description=f"Highest: {highest[0]} ({highest[1]}), Lowest: {lowest[0]} ({lowest[1]})",
                        confidence=0.7,
                    ))

        # Generic insights from title/caption
        if title:
            insights.append(ChartInsight(
                insight_type="context",
                description=f"Chart shows: {title}",
                confidence=0.9,
            ))
        if caption:
            insights.append(ChartInsight(
                insight_type="context",
                description=f"Described as: {caption}",
                confidence=0.9,
            ))

        return insights

    def _generate_summary(
        self,
        chart_type: str,
        title: Optional[str],
        caption: Optional[str],
        insights: List[ChartInsight],
        x_axis: Optional[ChartAxis],
        y_axis: Optional[ChartAxis],
        data_points: List[ChartDataPoint],
        is_financial: bool,
    ) -> str:
        """Generate natural language summary."""
        parts = []

        # Base description
        type_desc = chart_type if chart_type != "unknown" else "visual"
        if title:
            parts.append(f"{type_desc.title()} chart titled '{title}'.")
        else:
            parts.append(f"{type_desc.title()} chart visualization.")

        if caption:
            parts.append(f"Caption: {caption}")

        # Axis info
        if x_axis and x_axis.label:
            parts.append(f"X-axis: {x_axis.label}.")
        if y_axis and y_axis.label:
            unit_str = f" ({y_axis.unit})" if y_axis.unit else ""
            parts.append(f"Y-axis: {y_axis.label}{unit_str}.")

        # Data summary
        if data_points:
            values = [dp.value for dp in data_points if dp.value is not None]
            if values:
                parts.append(
                    f"Contains {len(data_points)} data points "
                    f"ranging from {min(values):,.2f} to {max(values):,.2f}."
                )

        # Key insights
        for insight in insights[:3]:
            parts.append(insight.description)

        if is_financial:
            parts.append("Contains financial/business metrics.")

        return " ".join(parts)

    def _build_structured_json(
        self,
        chart_type: str,
        title: Optional[str],
        x_axis: Optional[ChartAxis],
        y_axis: Optional[ChartAxis],
        legends: List[ChartLegend],
        data_points: List[ChartDataPoint],
        insights: List[ChartInsight],
    ) -> Dict:
        """Build structured JSON representation."""
        return {
            "chart_type": chart_type,
            "title": title,
            "axes": {
                "x": {"label": x_axis.label if x_axis else "", "type": x_axis.data_type if x_axis else "unknown"},
                "y": {"label": y_axis.label if y_axis else "", "type": y_axis.data_type if y_axis else "unknown"},
            },
            "legends": [{"label": l.label} for l in legends],
            "data_points": [
                {"label": dp.label, "value": dp.value, "series": dp.series}
                for dp in data_points
            ],
            "insights": [
                {"type": i.insight_type, "text": i.description, "confidence": i.confidence}
                for i in insights
            ],
        }

    def _parse_vlm_response(self, response: str) -> Dict:
        """Parse VLM JSON response."""
        try:
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0].strip()
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0].strip()
            else:
                json_str = response.strip()
            return json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            logger.warning("Failed to parse VLM response as JSON")
            return {"insights": [response[:500]]}

    @staticmethod
    def _safe_float(val) -> Optional[float]:
        """Safely convert a value to float."""
        if val is None:
            return None
        try:
            if isinstance(val, str):
                val = val.replace(",", "").strip()
            return float(val)
        except (ValueError, TypeError):
            return None
