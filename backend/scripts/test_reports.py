"""
Quick test for the Report Generation Service.

Tests PDF, Excel, Word, and CSV generation using sample RAG data.
"""

import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

# Minimal env
os.environ.setdefault("QDRANT_HOST", "localhost")
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")

# Load .env for any missing vars
env_path = os.path.join(BACKEND_DIR, "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def main():
    from reports.chart_engine import ChartEngine
    from reports.data_engine import DataEngine
    from reports.pdf_builder import generate_pdf_report
    from reports.excel_builder import generate_excel_report
    from reports.word_builder import generate_word_report

    # ── Sample Data (from actual query results) ──────────────
    sample_query = "What measurable outcomes or indicators are cited in the document to demonstrate progress toward Zero Harm?"

    sample_answer = """Based on the provided context from JSW Steel's corporate report, the following measurable outcomes and indicators are cited to demonstrate progress toward Zero Harm:

**Safety Performance Metrics:**
- LTIFR (Lost Time Injury Frequency Rate): 0.25 in FY 2024-25, improved from 0.19 in FY 2023-24
- Fatalities: 0 employee fatalities, 5 contract worker fatalities in FY 2024-25
- Safety Observations: 5.5 lakh+ safety observations recorded

**Training & Capability:**
- 55,000+ employees and contract workers covered under Safety Culture Survey
- 3,435 e-learning modules deployed
- 1,071 SMEs certified across operations
- 26,355 planned safety inspections completed

**Digital Initiatives:**
- Project Rakshak: IoT wearables deployed to 2,500 workers at Dolvi plant
- Digital Vision Platform (DVP): AI-based PPE detection
- 95,000+ workmen assessed through digital tools

**Governance & Compliance:**
- ISO 45001:2018 certification maintained across all plants
- 90% corrective actions closed within target time
- 5 Group Safety Subcommittees operational"""

    sample_sources = [
        {"content": "LTIFR improved from 0.25 to 0.19. Zero Harm is the strategic goal.", "page": 82, "source": "Test1.pdf", "score": 0.92, "content_type": "text"},
        {"content": "Project Rakshak deployed IoT wearables to 2,500 workers at Dolvi.", "page": 46, "source": "Test1.pdf", "score": 0.88, "content_type": "text"},
        {"content": "Safety observations exceeded 5.5 lakh. CHETNA initiative launched.", "page": 176, "source": "Test1.pdf", "score": 0.85, "content_type": "text"},
        {"content": "ISO 45001:2018 maintained. 26,355 planned safety inspections.", "page": 155, "source": "Test1.pdf", "score": 0.82, "content_type": "text"},
        {"content": "55,000+ covered under Safety Culture Survey by M/s SafeMaps.", "page": 134, "source": "Test1.pdf", "score": 0.80, "content_type": "text"},
    ]

    output_dir = os.path.join(BACKEND_DIR, "..", "generated_reports_test")
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 60)
    print("  Report Generation Service — Test Suite")
    print("=" * 60)

    # ── Test 1: Chart Engine ─────────────────────────────────
    print("\n🔹 Test 1: Chart Engine")
    engine = ChartEngine()
    charts = engine.generate_all_charts(sample_answer, sample_sources)
    print(f"   Auto-detected {len(charts)} charts from answer text")
    for i, (png, title) in enumerate(charts):
        path = os.path.join(output_dir, f"chart_{i+1}.png")
        with open(path, "wb") as f:
            f.write(png)
        print(f"   ✅ Chart {i+1}: '{title}' → {len(png)/1024:.1f} KB → {path}")

    # ── Test 2: Data Engine ──────────────────────────────────
    print("\n🔹 Test 2: Data Engine")
    data_engine = DataEngine()
    kpis = data_engine.extract_kpis(sample_answer)
    print(f"   KPIs extracted: {kpis}")
    tables = data_engine.extract_tables(sample_answer)
    print(f"   Tables extracted: {len(tables)}")
    for i, df in enumerate(tables):
        print(f"   Table {i+1}: {len(df)} rows × {len(df.columns)} cols")

    # ── Test 3: PDF Report ───────────────────────────────────
    print("\n🔹 Test 3: PDF Report")
    pdf_path = os.path.join(output_dir, "test_report.pdf")
    pdf_bytes = generate_pdf_report(
        query=sample_query,
        answer=sample_answer,
        sources=sample_sources,
        charts=charts,
        kpis=kpis,
        title="JSW Steel — Zero Harm Analysis",
        output_path=pdf_path,
    )
    pdf_size = os.path.getsize(pdf_path) / 1024
    print(f"   ✅ PDF generated: {pdf_size:.1f} KB → {pdf_path}")

    # ── Test 4: Excel Report ─────────────────────────────────
    print("\n🔹 Test 4: Excel Report")
    xlsx_path = os.path.join(output_dir, "test_report.xlsx")
    dataframes = {}
    for i, df in enumerate(tables):
        dataframes[f"Data {i+1}"] = df
    src_df = data_engine.sources_to_dataframe(sample_sources)
    dataframes["Sources"] = src_df

    xlsx_bytes = generate_excel_report(
        query=sample_query,
        answer=sample_answer,
        sources=sample_sources,
        kpis=kpis,
        dataframes=dataframes,
        title="JSW Steel — Zero Harm Analysis",
        output_path=xlsx_path,
    )
    xlsx_size = os.path.getsize(xlsx_path) / 1024
    print(f"   ✅ Excel generated: {xlsx_size:.1f} KB → {xlsx_path}")

    # ── Test 5: Word Report ──────────────────────────────────
    print("\n🔹 Test 5: Word Report")
    docx_path = os.path.join(output_dir, "test_report.docx")
    docx_bytes = generate_word_report(
        query=sample_query,
        answer=sample_answer,
        sources=sample_sources,
        charts=charts,
        kpis=kpis,
        title="JSW Steel — Zero Harm Analysis",
        output_path=docx_path,
    )
    docx_size = os.path.getsize(docx_path) / 1024
    print(f"   ✅ Word generated: {docx_size:.1f} KB → {docx_path}")

    # ── Test 6: CSV Export ───────────────────────────────────
    print("\n🔹 Test 6: CSV Export")
    if tables:
        csv_bytes = data_engine.to_csv(tables[0])
        csv_path = os.path.join(output_dir, "test_report.csv")
        with open(csv_path, "wb") as f:
            f.write(csv_bytes)
        print(f"   ✅ CSV generated: {len(csv_bytes)/1024:.1f} KB → {csv_path}")
    else:
        print("   ⚠️  No table data for CSV")

    print("\n" + "=" * 60)
    print("  ✅ All tests passed!")
    print(f"  Output: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
