# 📊 Report & Artifact Generation Service — Implementation Plan

## Overview

Build a production-grade reporting microservice within the RAG-POC backend that can generate
downloadable artifacts (PDFs, Excel, Word, Charts, CSV) from RAG query results. This integrates
with the existing FastAPI backend, RAG pipeline, and Redis job queue.

---

## 🏗️ Architecture

```
                    ┌─────────────────────────┐
                    │     Frontend (React)     │
                    │  "Generate Report" btn   │
                    └────────┬────────────────┬┘
                             │ POST           │ GET
                    ┌────────▼────────┐  ┌────▼─────────────┐
                    │  /api/reports   │  │ /api/reports/     │
                    │  /generate      │  │ {id}/download     │
                    └────────┬────────┘  └────▲─────────────┘
                             │                │
                    ┌────────▼────────────────┐│
                    │   ReportOrchestrator    ││
                    │  (async job via Redis)  ││
                    └────────┬───────────────┘│
              ┌──────────────┼──────────────┐ │
              ▼              ▼              ▼ │
     ┌────────────┐  ┌────────────┐  ┌───────┴────┐
     │ ChartEngine│  │ DataEngine │  │ DocAssembler│
     │ (matplotlib│  │ (pandas)   │  │ (reportlab/ │
     │  + plotly) │  │            │  │  docx/xlsx) │
     └────────────┘  └────────────┘  └────────────┘
              │              │              │
              └──────────────┼──────────────┘
                             ▼
                    ┌─────────────────┐
                    │ MinIO / Local   │
                    │ File Storage    │
                    └─────────────────┘
```

---

## 📂 File Structure

```
backend/
├── services/
│   └── report_service.py          # Phase 1: Main orchestrator
├── reports/
│   ├── __init__.py
│   ├── chart_engine.py            # Phase 2: Matplotlib/Plotly chart generation
│   ├── data_engine.py             # Phase 3: Pandas data processing
│   ├── pdf_builder.py             # Phase 4: ReportLab PDF assembly
│   ├── excel_builder.py           # Phase 5: Openpyxl Excel generation
│   ├── word_builder.py            # Phase 5: python-docx Word generation
│   ├── csv_builder.py             # Phase 3: CSV/data export
│   └── templates/                 # Phase 4: Report templates
│       ├── base_report.py
│       ├── financial_report.py
│       └── safety_report.py
├── api/
│   └── report_routes.py           # Phase 1: FastAPI endpoints
└── schemas/
    └── report_schema.py           # Phase 1: Pydantic models
```

---

## 🔧 Dependencies to Install

```
pip install matplotlib reportlab python-docx openpyxl plotly kaleido
```

| Package       | Purpose                        | Size    |
|---------------|--------------------------------|---------|
| matplotlib    | Chart/plot generation          | ~35MB   |
| reportlab     | Professional PDF generation    | ~4MB    |
| python-docx   | Word document generation       | ~1MB    |
| openpyxl      | Excel file generation          | ~3MB    |
| plotly         | Interactive charts             | ~15MB   |
| kaleido       | Export Plotly charts to images  | ~80MB   |
| pandas        | Already installed              | —       |

---

## 🚀 Implementation Phases

---

### Phase 1: Foundation — Report Service + API Routes + Schemas
**Estimated: ~200 lines**
**Priority: HIGH**

#### 1A. Report Schema (`schemas/report_schema.py`)
```python
# Pydantic models for report requests and responses

class ReportRequest:
    report_type: str          # "pdf", "excel", "word", "csv", "chart"
    title: str
    query: str                # Original RAG query
    answer: str               # RAG-generated answer
    sources: List[dict]       # Retrieved context chunks with page numbers
    options: ReportOptions    # Formatting preferences

class ReportOptions:
    include_charts: bool = True
    include_sources: bool = True
    include_metadata: bool = True
    template: str = "default"  # "financial", "safety", "executive"
    chart_types: List[str] = ["bar", "pie"]

class ReportResponse:
    report_id: str
    status: str               # "queued", "processing", "ready", "error"
    download_url: str | None
    filename: str
    format: str
    created_at: datetime

class ReportStatus:
    report_id: str
    status: str
    progress: int             # 0-100
    error: str | None
```

#### 1B. API Routes (`api/report_routes.py`)
```
POST /api/reports/generate     → Queue report generation job
GET  /api/reports/{id}/status  → Check generation progress
GET  /api/reports/{id}/download → Download generated file
GET  /api/reports/list          → List user's generated reports
DELETE /api/reports/{id}        → Delete a report
```

#### 1C. Report Orchestrator (`services/report_service.py`)
- Receives report request
- Coordinates chart generation, data processing, document assembly
- Stores generated files (local or MinIO)
- Updates job status in Redis
- Returns download URL

---

### Phase 2: Chart Engine
**Estimated: ~250 lines**
**Priority: HIGH**

#### What it does:
- Extracts numerical data from RAG answers and source chunks
- Auto-detects chart-worthy data (tables, comparisons, trends)
- Generates appropriate chart types

#### Supported Chart Types:
```python
CHART_TYPES = {
    "bar":         "Comparisons (e.g., revenue by year)",
    "line":        "Trends over time (e.g., safety incidents)",
    "pie":         "Proportions (e.g., workforce distribution)",
    "hbar":        "Horizontal bar (e.g., ranked items)",
    "stacked_bar": "Multi-category comparisons",
    "scatter":     "Correlation analysis",
    "gauge":       "KPI indicators (e.g., LTIFR)",
    "table_chart": "Styled data table as image",
}
```

#### Key Functions:
```python
class ChartEngine:
    def detect_chartable_data(answer: str, sources: list) -> list[ChartData]
    def generate_chart(data: ChartData, style: str) -> bytes  # PNG
    def generate_matplotlib_chart(data, chart_type, **opts) -> bytes
    def generate_plotly_chart(data, chart_type, **opts) -> bytes
    def apply_corporate_style(fig) -> fig  # JSW brand colors
```

#### Smart Data Extraction:
- Regex patterns to find tables, numbers, percentages in RAG output
- Parse structured data (FY comparisons, KPIs, metrics)
- Auto-suggest appropriate visualizations

---

### Phase 3: Data Engine + CSV Builder
**Estimated: ~150 lines**
**Priority: MEDIUM**

#### What it does:
- Parses RAG answers into structured DataFrames
- Handles financial data, KPIs, metrics
- Exports clean CSV files

#### Key Functions:
```python
class DataEngine:
    def extract_tables(answer: str) -> List[pd.DataFrame]
    def extract_kpis(answer: str) -> dict
    def normalize_financial_data(data: dict) -> pd.DataFrame
    def to_csv(df: pd.DataFrame, filename: str) -> str  # file path
```

---

### Phase 4: PDF Builder (ReportLab)
**Estimated: ~350 lines**
**Priority: HIGH**

#### What it does:
- Assembles professional PDF reports from RAG answers
- Includes charts, tables, source citations, and metadata
- Supports template-based layouts

#### Document Structure:
```
┌─────────────────────────────┐
│  HEADER (Logo + Title)      │
├─────────────────────────────┤
│  Executive Summary          │
│  (RAG-generated answer)     │
├─────────────────────────────┤
│  Data Visualization         │
│  (Charts from ChartEngine)  │
├─────────────────────────────┤
│  Detailed Findings          │
│  (Structured answer text)   │
├─────────────────────────────┤
│  Data Tables                │
│  (Extracted from sources)   │
├─────────────────────────────┤
│  Source References           │
│  (Page numbers, scores)     │
├─────────────────────────────┤
│  FOOTER (Page # + Date)     │
└─────────────────────────────┘
```

#### Key Functions:
```python
class PDFBuilder:
    def __init__(template: str = "default")
    def set_header(title, subtitle, logo_path)
    def add_section(title, content: str)
    def add_chart(chart_bytes: bytes, caption: str)
    def add_table(df: pd.DataFrame, title: str)
    def add_sources(sources: list)
    def add_page_break()
    def build(output_path: str) -> str
```

#### Templates:
- `default` — Clean corporate report
- `financial` — Financial analysis layout with KPI highlights
- `safety` — Safety metrics dashboard layout
- `executive` — 1-2 page executive summary

---

### Phase 5: Excel & Word Builders
**Estimated: ~200 lines each**
**Priority: MEDIUM**

#### Excel Builder (`openpyxl`):
```python
class ExcelBuilder:
    def create_workbook(title: str)
    def add_summary_sheet(answer: str)
    def add_data_sheet(df: pd.DataFrame, name: str)
    def add_chart_sheet(chart_data, chart_type: str)
    def add_source_sheet(sources: list)
    def style_corporate()  # Brand colors, headers
    def build(output_path: str) -> str
```

#### Word Builder (`python-docx`):
```python
class WordBuilder:
    def create_document(title: str)
    def add_heading(text: str, level: int)
    def add_paragraph(text: str, style: str)
    def add_table(df: pd.DataFrame)
    def add_chart_image(chart_bytes: bytes)
    def add_sources(sources: list)
    def build(output_path: str) -> str
```

---

### Phase 6: Integration with RAG Chat Flow
**Estimated: ~100 lines**
**Priority: HIGH**

#### How it works in practice:

1. **User asks a question** in the chat UI
2. **RAG pipeline answers** with sources and page numbers
3. **Frontend shows a "Generate Report" button** beneath the answer
4. **User clicks** → selects format (PDF/Excel/Word/CSV)
5. **Backend generates** the report asynchronously
6. **Download link appears** in the chat

#### Chat Route Enhancement:
```python
# In chat_routes.py or a new endpoint
@router.post("/api/chat/{message_id}/export")
async def export_chat_response(
    message_id: str,
    format: str = "pdf",  # pdf, excel, word, csv
    options: ReportOptions = ReportOptions(),
):
    # Fetch the original answer + sources from message_id
    # Generate report
    # Return download URL
```

---

### Phase 7: Frontend Integration
**Estimated: ~150 lines (React)**
**Priority: MEDIUM**

#### UI Components Needed:
1. **Export Dropdown** — Below each RAG answer
   - 📄 Export as PDF
   - 📊 Export as Excel
   - 📝 Export as Word
   - 📁 Export as CSV

2. **Report Options Modal** — Quick configuration
   - Include charts? ☑️
   - Include sources? ☑️
   - Template style: [Default ▾]

3. **Download Progress** — Toast notification
   - "Generating PDF report... 45%"
   - "✅ Report ready — Click to download"

---

## 🔄 End-to-End Flow

```
User Question → RAG Pipeline → Answer + Sources
                                      │
                              ┌───────▼───────┐
                              │  Export Button │
                              └───────┬───────┘
                                      │ User clicks "Export as PDF"
                              ┌───────▼───────┐
                              │ POST /reports  │
                              │ /generate      │
                              └───────┬───────┘
                                      │
                              ┌───────▼───────┐
                              │ ReportService  │
                              │ (async job)    │
                              └───────┬───────┘
                        ┌─────────────┼──────────────┐
                        ▼             ▼              ▼
                 Extract Data   Generate Charts  Build Document
                 (DataEngine)   (ChartEngine)    (PDFBuilder)
                        │             │              │
                        └─────────────┼──────────────┘
                                      ▼
                              ┌───────────────┐
                              │  Save to MinIO │
                              │  / local disk  │
                              └───────┬───────┘
                                      │
                              ┌───────▼───────┐
                              │ Download URL   │
                              │ returned to UI │
                              └───────────────┘
```

---

## 📋 Implementation Order (Recommended)

| Step | Component                | Est. Lines | Depends On |
|------|--------------------------|------------|------------|
| 1    | Install dependencies     | —          | —          |
| 2    | `report_schema.py`       | ~60        | —          |
| 3    | `chart_engine.py`        | ~250       | —          |
| 4    | `data_engine.py`         | ~150       | —          |
| 5    | `pdf_builder.py`         | ~350       | Steps 3, 4 |
| 6    | `report_service.py`      | ~200       | Steps 3-5  |
| 7    | `report_routes.py`       | ~120       | Step 6     |
| 8    | `excel_builder.py`       | ~200       | Step 4     |
| 9    | `word_builder.py`        | ~200       | Step 4     |
| 10   | `csv_builder.py`         | ~60        | Step 4     |
| 11   | Frontend export UI       | ~150       | Step 7     |
| **Total** |                     | **~1740**  |            |

---

## 🎯 Quick Win: Start with PDF + Charts

The highest-impact first deliverable is:
1. **Chart Engine** (auto-detect data, generate matplotlib charts)
2. **PDF Builder** (assemble professional report with charts)
3. **API Route** (single endpoint to generate + download)

This alone gives you: User asks question → clicks "Export PDF" → gets a professional
report with charts, tables, source citations, and styled formatting.

---

## 💡 Design Decisions

1. **Async generation** — Reports are generated as background jobs (Redis queue),
   so the UI doesn't block. User gets a progress indicator.

2. **Template-based** — Different report templates for different use cases
   (financial, safety, executive). Easy to add new ones.

3. **Smart chart detection** — The ChartEngine auto-detects numerical data in RAG
   answers and suggests appropriate visualizations.

4. **Brand consistency** — All outputs use JSW Steel brand colors, fonts, and logo.
   Configurable per deployment.

5. **Storage flexibility** — Generated files stored in MinIO (production) or local
   disk (development). Configurable via settings.

6. **Stateless builders** — Each builder (PDF, Excel, Word) is stateless and can
   be scaled horizontally.

---

## ✅ Ready to Implement?

Say "go" and I'll start with:
1. Install dependencies
2. Build the schemas
3. Build the Chart Engine
4. Build the PDF Builder
5. Wire up the API route
6. Test with your existing query results
