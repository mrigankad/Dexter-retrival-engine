"""
Docling Parser - Primary Multimodal Document Intelligence Engine.

Uses Docling for structural document understanding with:
- Layout-aware extraction
- Table detection and normalization
- Chart/figure region detection
- Semantic section hierarchy extraction
- Footnote and appendix linking
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import hashlib

from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ExtractedSection:
    """Represents a document section with hierarchy."""
    id: str
    title: str
    level: int  # h1=1, h2=2, etc.
    content: str
    page_start: int
    page_end: int
    parent_id: Optional[str] = None
    children: List[str] = field(default_factory=list)
    

@dataclass
class ExtractedTable:
    """Represents an extracted table with structure."""
    id: str
    page: int
    caption: Optional[str]
    headers: List[str]
    rows: List[List[str]]
    markdown: str
    html: str
    bounding_box: Optional[Dict[str, float]] = None
    confidence: float = 1.0
    context_before: str = ""
    context_after: str = ""


@dataclass
class ExtractedChart:
    """Represents an extracted chart/figure."""
    id: str
    page: int
    chart_type: str  # bar, line, pie, etc.
    title: Optional[str]
    caption: Optional[str]
    image_path: str
    bounding_box: Optional[Dict[str, float]] = None
    raw_data: Optional[Dict] = None  # If data extraction succeeds


@dataclass
class DoclingOutput:
    """Complete output from Docling parser."""
    document_id: str
    filename: str
    total_pages: int
    sections: List[ExtractedSection]
    tables: List[ExtractedTable]
    charts: List[ExtractedChart]
    full_text: str
    section_tree: Dict[str, Any]
    metadata: Dict[str, Any]
    parsing_confidence: float
    errors: List[str] = field(default_factory=list)


class DoclingParser:
    """
    Primary document parser using Docling for multimodal extraction.
    
    Responsibilities:
    - Structural document understanding
    - Layout-aware extraction
    - Table detection and normalization
    - Chart and figure region detection
    - Semantic section hierarchy extraction
    """
    
    def __init__(self):
        self.docling_available = self._check_docling()
        self.fallback_parser = None  # Will be set to MarkerFallback if needed
        
    def _check_docling(self) -> bool:
        """Check if Docling is available."""
        try:
            from docling.document_converter import DocumentConverter
            return True
        except ImportError:
            logger.warning("Docling not installed. Using fallback parsers.")
            return False
    
    def _generate_id(self, content: str, prefix: str = "") -> str:
        """Generate a unique ID for content."""
        hash_val = hashlib.md5(content.encode()).hexdigest()[:8]
        return f"{prefix}_{hash_val}" if prefix else hash_val
    
    async def parse_document(
        self,
        file_path: str,
        document_id: str,
        extract_images: bool = True,
    ) -> DoclingOutput:
        """
        Parse a document using Docling.
        
        Args:
            file_path: Path to the PDF/DOCX file
            document_id: Unique identifier for the document
            extract_images: Whether to extract chart/figure images
            
        Returns:
            DoclingOutput with all extracted content
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Document not found: {file_path}")
        
        logger.info("Starting Docling parse", document_id=document_id, file=str(file_path))
        
        if self.docling_available:
            return await self._parse_with_docling(file_path, document_id, extract_images)
        else:
            return await self._parse_with_fallback(file_path, document_id, extract_images)
    
    async def _parse_with_docling(
        self,
        file_path: Path,
        document_id: str,
        extract_images: bool,
    ) -> DoclingOutput:
        """Parse using Docling library."""
        from docling.document_converter import DocumentConverter
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        
        # Configure Docling pipeline
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = True
        pipeline_options.do_table_structure = True
        pipeline_options.generate_page_images = extract_images
        
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF, InputFormat.DOCX],
            pdf_pipeline_options=pipeline_options
        )
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: converter.convert(str(file_path))
        )
        
        # Extract document structure
        doc = result.document
        
        # Build section hierarchy
        sections = []
        section_tree = {}
        current_h1 = None
        current_h2 = None
        
        for item in doc.iterate_items():
            if hasattr(item, 'label') and 'heading' in str(item.label).lower():
                level = self._detect_heading_level(item)
                section = ExtractedSection(
                    id=self._generate_id(item.text, "sec"),
                    title=item.text.strip(),
                    level=level,
                    content="",
                    page_start=item.prov[0].page_no if item.prov else 1,
                    page_end=item.prov[0].page_no if item.prov else 1,
                )
                
                if level == 1:
                    current_h1 = section.id
                    section_tree[section.id] = {"title": section.title, "children": {}}
                elif level == 2 and current_h1:
                    current_h2 = section.id
                    section.parent_id = current_h1
                    if current_h1 in section_tree:
                        section_tree[current_h1]["children"][section.id] = {"title": section.title}
                
                sections.append(section)
        
        # Extract tables
        tables = []
        for table_item in doc.tables:
            table = self._extract_table_structure(table_item, document_id)
            if table:
                tables.append(table)
        
        # Extract charts/figures
        charts = []
        for picture in doc.pictures:
            chart = self._extract_chart_info(picture, document_id, file_path)
            if chart:
                charts.append(chart)
        
        # Get full text with reading order preserved
        full_text = doc.export_to_markdown()
        
        # Calculate parsing confidence
        confidence = self._calculate_confidence(doc, tables)
        
        output = DoclingOutput(
            document_id=document_id,
            filename=file_path.name,
            total_pages=doc.num_pages,
            sections=sections,
            tables=tables,
            charts=charts,
            full_text=full_text,
            section_tree=section_tree,
            metadata={
                "parser": "docling",
                "has_ocr": True,
                "table_count": len(tables),
                "chart_count": len(charts),
                "section_count": len(sections),
            },
            parsing_confidence=confidence,
        )
        
        logger.info(
            "Docling parse complete",
            document_id=document_id,
            pages=output.total_pages,
            tables=len(tables),
            charts=len(charts),
            confidence=confidence,
        )
        
        return output
    
    async def _parse_with_fallback(
        self,
        file_path: Path,
        document_id: str,
        extract_images: bool,
    ) -> DoclingOutput:
        """Fallback parser using PyMuPDF and basic extraction."""
        import fitz  # PyMuPDF
        
        doc = fitz.open(str(file_path))
        full_text_parts = []
        tables = []
        sections = []
        
        for page_num, page in enumerate(doc, 1):
            # Extract text
            text = page.get_text("text")
            full_text_parts.append(f"--- Page {page_num} ---\n{text}")
            
            # Detect headers (basic heuristic)
            blocks = page.get_text("dict")["blocks"]
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            # Large font or bold = likely header
                            if span["size"] > 14 or "bold" in span["font"].lower():
                                section = ExtractedSection(
                                    id=self._generate_id(span["text"], "sec"),
                                    title=span["text"].strip(),
                                    level=1 if span["size"] > 16 else 2,
                                    content="",
                                    page_start=page_num,
                                    page_end=page_num,
                                )
                                sections.append(section)
            
            # Extract tables (basic)
            page_tables = page.find_tables()
            for idx, table in enumerate(page_tables.tables):
                extracted_table = ExtractedTable(
                    id=self._generate_id(f"table_{page_num}_{idx}", "tbl"),
                    page=page_num,
                    caption=None,
                    headers=table.header.names if table.header else [],
                    rows=[list(row) for row in table.extract()],
                    markdown=table.to_markdown(),
                    html="",
                    confidence=0.7,  # Lower confidence for fallback
                )
                tables.append(extracted_table)
        
        doc.close()
        
        return DoclingOutput(
            document_id=document_id,
            filename=file_path.name,
            total_pages=len(full_text_parts),
            sections=sections,
            tables=tables,
            charts=[],  # Charts not extracted in fallback
            full_text="\n\n".join(full_text_parts),
            section_tree={},
            metadata={
                "parser": "pymupdf_fallback",
                "has_ocr": False,
                "table_count": len(tables),
                "chart_count": 0,
                "section_count": len(sections),
            },
            parsing_confidence=0.6,
            errors=["Docling not available, using fallback parser"],
        )
    
    def _detect_heading_level(self, item) -> int:
        """Detect heading level from Docling item."""
        label = str(item.label).lower()
        if "h1" in label or "title" in label:
            return 1
        elif "h2" in label:
            return 2
        elif "h3" in label:
            return 3
        return 2  # Default to h2
    
    def _extract_table_structure(self, table_item, document_id: str) -> Optional[ExtractedTable]:
        """Extract structured table from Docling table item."""
        try:
            # Get table data
            table_data = table_item.export_to_dataframe()
            headers = list(table_data.columns)
            rows = table_data.values.tolist()
            
            # Convert to markdown
            markdown = table_item.export_to_markdown()
            html = table_item.export_to_html()
            
            # Get bounding box if available
            bbox = None
            if hasattr(table_item, 'prov') and table_item.prov:
                prov = table_item.prov[0]
                bbox = {
                    "x0": prov.bbox.l,
                    "y0": prov.bbox.t,
                    "x1": prov.bbox.r,
                    "y1": prov.bbox.b,
                }
            
            return ExtractedTable(
                id=self._generate_id(markdown[:100], "tbl"),
                page=table_item.prov[0].page_no if table_item.prov else 0,
                caption=getattr(table_item, 'caption', None),
                headers=headers,
                rows=rows,
                markdown=markdown,
                html=html,
                bounding_box=bbox,
                confidence=0.9,
            )
        except Exception as e:
            logger.warning("Failed to extract table", error=str(e))
            return None
    
    def _extract_chart_info(self, picture, document_id: str, file_path: Path) -> Optional[ExtractedChart]:
        """Extract chart/figure information."""
        try:
            chart_id = self._generate_id(str(picture), "chart")
            
            # Save image if available
            image_path = ""
            if hasattr(picture, 'image') and picture.image:
                assets_dir = file_path.parent / "assets" / document_id
                assets_dir.mkdir(parents=True, exist_ok=True)
                image_path = str(assets_dir / f"{chart_id}.png")
                picture.image.save(image_path)
            
            return ExtractedChart(
                id=chart_id,
                page=picture.prov[0].page_no if hasattr(picture, 'prov') and picture.prov else 0,
                chart_type="unknown",  # Will be classified by ChartAnalyzer
                title=getattr(picture, 'caption', None),
                caption=getattr(picture, 'caption', None),
                image_path=image_path,
            )
        except Exception as e:
            logger.warning("Failed to extract chart", error=str(e))
            return None
    
    def _calculate_confidence(self, doc, tables: List[ExtractedTable]) -> float:
        """Calculate overall parsing confidence."""
        base_confidence = 0.85
        
        # Boost for successful table extraction
        if tables:
            avg_table_conf = sum(t.confidence for t in tables) / len(tables)
            base_confidence = (base_confidence + avg_table_conf) / 2
        
        return round(base_confidence, 2)
    
    async def should_use_fallback(self, docling_output: DoclingOutput) -> bool:
        """Determine if fallback parser should be used."""
        # Use fallback if:
        # 1. Parsing confidence is too low
        # 2. Expected tables weren't extracted
        # 3. Many parsing errors
        
        if docling_output.parsing_confidence < 0.6:
            return True
        
        if len(docling_output.errors) > 5:
            return True
        
        return False
