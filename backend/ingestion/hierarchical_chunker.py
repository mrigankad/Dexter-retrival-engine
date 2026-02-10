"""
Hierarchical Chunking Engine - Multi-Resolution Document Chunking.

Implements production-grade chunking with:
- Section-level chunks (large context)
- Paragraph-level chunks (high precision)
- Table summary chunks (data points)
- Chart summary chunks (visual insights)

Each chunk stores rich metadata for retrieval filtering.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union
import hashlib
import re

from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class HierarchicalChunk:
    """
    Production-grade chunk schema with full metadata.
    
    Designed for:
    - Multi-resolution retrieval
    - Content-type filtering
    - Temporal filtering
    - Section-based navigation
    """
    id: str
    document_id: str
    content: str
    
    # Hierarchy metadata
    section_title: str
    subsection: Optional[str]
    hierarchy_path: str  # e.g., "Financial Performance > Revenue Analysis"
    
    # Location metadata
    page: int
    page_end: Optional[int] = None
    chunk_index: int = 0
    total_chunks: int = 0
    
    # Content classification
    content_type: str  # "text" | "table_summary" | "table_raw" | "chart_summary"
    chunk_level: str  # "section" | "paragraph" | "asset"
    
    # Semantic metadata
    semantic_summary: Optional[str] = None
    entities: List[str] = field(default_factory=list)
    time_period: Optional[str] = None
    
    # Source tracking
    source_filename: str = ""
    source_asset_id: Optional[str] = None
    
    # Quality indicators
    has_numerical_data: bool = False
    is_financial: bool = False
    word_count: int = 0
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return asdict(self)
    
    def to_payload(self) -> Dict[str, Any]:
        """Convert to Qdrant payload format."""
        return {
            "document_id": self.document_id,
            "content": self.content,
            "source": self.source_filename,
            "page": self.page,
            "page_end": self.page_end,
            "chunk_index": self.chunk_index,
            "total_chunks": self.total_chunks,
            "content_type": self.content_type,
            "chunk_level": self.chunk_level,
            "section_title": self.section_title,
            "subsection": self.subsection,
            "hierarchy_path": self.hierarchy_path,
            "semantic_summary": self.semantic_summary,
            "entities": self.entities,
            "time_period": self.time_period,
            "source_asset_id": self.source_asset_id,
            "has_numerical_data": self.has_numerical_data,
            "is_financial": self.is_financial,
            "word_count": self.word_count,
        }


# Patterns for detecting content characteristics
FINANCIAL_KEYWORDS = [
    'revenue', 'profit', 'margin', 'ebitda', 'ebit', 'cost', 'expense',
    'sales', 'income', 'asset', 'liability', 'equity', 'cash flow',
    'balance sheet', 'income statement', 'p&l', 'financial highlight',
    'key metric', 'performance indicator', 'benchmark', 'price',
    'capex', 'opex', 'depreciation', 'amortization', 'dividend',
]

TIME_PERIOD_PATTERNS = [
    r'FY\s*\d{2,4}',
    r'Q[1-4]\s*\d{2,4}',
    r'H[1-2]\s*\d{2,4}',
    r'\d{4}[-–]\d{2,4}',
    r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}',
]

NUMERICAL_PATTERNS = [
    r'(?:Rs\.?|₹|\$|€|£)\s*[\d,]+(?:\.\d+)?',
    r'[\d,]+(?:\.\d+)?\s*(?:million|billion|crore|lakh|mn|bn|cr)',
    r'\d+(?:\.\d+)?\s*%',
]


class HierarchicalChunker:
    """
    Multi-resolution chunking engine for enterprise documents.
    
    Produces three levels of chunks:
    1. Section-level: Full section context for broad queries
    2. Paragraph-level: Fine-grained chunks for precise retrieval
    3. Asset-level: Table/chart summaries with structured data
    """
    
    def __init__(
        self,
        section_chunk_size: int = 2000,
        paragraph_chunk_size: int = 500,
        chunk_overlap: int = 100,
        min_chunk_size: int = 50,
    ):
        self.section_chunk_size = section_chunk_size
        self.paragraph_chunk_size = paragraph_chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    def _generate_id(self, content: str, doc_id: str, chunk_type: str) -> str:
        """Generate unique chunk ID."""
        hash_val = hashlib.md5(f"{doc_id}:{content[:200]}".encode()).hexdigest()[:12]
        return f"{chunk_type}_{hash_val}"
    
    def _detect_time_period(self, text: str) -> Optional[str]:
        """Extract time period from text."""
        for pattern in TIME_PERIOD_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None
    
    def _is_financial_content(self, text: str) -> bool:
        """Check if text contains financial content."""
        text_lower = text.lower()
        matches = sum(1 for kw in FINANCIAL_KEYWORDS if kw in text_lower)
        return matches >= 2
    
    def _has_numerical_data(self, text: str) -> bool:
        """Check if text contains numerical data."""
        for pattern in NUMERICAL_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    def _extract_entities(self, text: str) -> List[str]:
        """Extract key entities from text (basic NER)."""
        entities = set()
        
        # Financial metrics
        metrics = ['EBITDA', 'EBIT', 'PAT', 'PBT', 'EPS', 'ROE', 'ROA', 'ROCE']
        for metric in metrics:
            if metric in text.upper():
                entities.add(metric)
        
        # Currency amounts (simplified)
        amounts = re.findall(r'(?:Rs\.?|₹|\$)\s*[\d,]+(?:\.\d+)?\s*(?:crore|million|billion)?', text, re.IGNORECASE)
        entities.update(amounts[:5])  # Limit to avoid bloat
        
        return list(entities)[:10]  # Cap at 10 entities
    
    def chunk_document(
        self,
        docling_output,  # DoclingOutput from docling_parser
        generate_summaries: bool = False,
    ) -> List[HierarchicalChunk]:
        """
        Create multi-resolution chunks from Docling output.
        
        Args:
            docling_output: Parsed document from DoclingParser
            generate_summaries: Whether to generate semantic summaries (requires LLM)
            
        Returns:
            List of HierarchicalChunk objects at multiple resolutions
        """
        all_chunks: List[HierarchicalChunk] = []
        
        # 1. Create section-level chunks
        section_chunks = self._create_section_chunks(docling_output)
        all_chunks.extend(section_chunks)
        
        # 2. Create paragraph-level chunks from full text
        paragraph_chunks = self._create_paragraph_chunks(docling_output)
        all_chunks.extend(paragraph_chunks)
        
        # 3. Create table summary chunks
        table_chunks = self._create_table_chunks(docling_output)
        all_chunks.extend(table_chunks)
        
        # 4. Create chart summary chunks
        chart_chunks = self._create_chart_chunks(docling_output)
        all_chunks.extend(chart_chunks)
        
        # Assign global indices
        for i, chunk in enumerate(all_chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(all_chunks)
        
        logger.info(
            "Hierarchical chunking complete",
            document_id=docling_output.document_id,
            section_chunks=len(section_chunks),
            paragraph_chunks=len(paragraph_chunks),
            table_chunks=len(table_chunks),
            chart_chunks=len(chart_chunks),
            total_chunks=len(all_chunks),
        )
        
        return all_chunks
    
    def _create_section_chunks(self, docling_output) -> List[HierarchicalChunk]:
        """Create section-level chunks for broad context retrieval."""
        chunks = []
        
        # Group content by sections
        section_texts = {}
        current_section = "Introduction"
        
        for section in docling_output.sections:
            section_texts[section.title] = {
                "content": section.content,
                "page_start": section.page_start,
                "page_end": section.page_end,
                "level": section.level,
            }
        
        # If no explicit sections, create from full text
        if not section_texts:
            # Split by page markers or large chunks
            text = docling_output.full_text
            for i in range(0, len(text), self.section_chunk_size):
                chunk_text = text[i:i + self.section_chunk_size]
                if len(chunk_text.split()) < self.min_chunk_size:
                    continue
                
                chunk = HierarchicalChunk(
                    id=self._generate_id(chunk_text, docling_output.document_id, "sec"),
                    document_id=docling_output.document_id,
                    content=chunk_text,
                    section_title="Document Content",
                    subsection=None,
                    hierarchy_path="Document Content",
                    page=1 + (i // 3000),  # Estimate page
                    content_type="text",
                    chunk_level="section",
                    source_filename=docling_output.filename,
                    has_numerical_data=self._has_numerical_data(chunk_text),
                    is_financial=self._is_financial_content(chunk_text),
                    word_count=len(chunk_text.split()),
                    entities=self._extract_entities(chunk_text),
                    time_period=self._detect_time_period(chunk_text),
                )
                chunks.append(chunk)
        else:
            for title, data in section_texts.items():
                if len(data["content"].split()) < self.min_chunk_size:
                    continue
                
                chunk = HierarchicalChunk(
                    id=self._generate_id(data["content"], docling_output.document_id, "sec"),
                    document_id=docling_output.document_id,
                    content=data["content"],
                    section_title=title,
                    subsection=None,
                    hierarchy_path=title,
                    page=data["page_start"],
                    page_end=data["page_end"],
                    content_type="text",
                    chunk_level="section",
                    source_filename=docling_output.filename,
                    has_numerical_data=self._has_numerical_data(data["content"]),
                    is_financial=self._is_financial_content(data["content"]),
                    word_count=len(data["content"].split()),
                    entities=self._extract_entities(data["content"]),
                    time_period=self._detect_time_period(data["content"]),
                )
                chunks.append(chunk)
        
        return chunks
    
    def _create_paragraph_chunks(self, docling_output) -> List[HierarchicalChunk]:
        """Create paragraph-level chunks for precise retrieval."""
        chunks = []
        text = docling_output.full_text
        
        # Split into paragraphs
        paragraphs = re.split(r'\n\s*\n', text)
        
        current_section = "Document"
        current_page = 1
        
        buffer = []
        buffer_size = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # Detect page markers
            page_match = re.search(r'---\s*Page\s*(\d+)\s*---', para)
            if page_match:
                current_page = int(page_match.group(1))
                continue
            
            # Detect section headers (heuristic)
            if len(para) < 100 and para.isupper():
                current_section = para
                continue
            
            para_words = len(para.split())
            
            # Add to buffer
            buffer.append(para)
            buffer_size += para_words
            
            # Flush when buffer is full
            if buffer_size >= self.paragraph_chunk_size:
                chunk_text = "\n\n".join(buffer)
                
                chunk = HierarchicalChunk(
                    id=self._generate_id(chunk_text, docling_output.document_id, "para"),
                    document_id=docling_output.document_id,
                    content=chunk_text,
                    section_title=current_section,
                    subsection=None,
                    hierarchy_path=current_section,
                    page=current_page,
                    content_type="text",
                    chunk_level="paragraph",
                    source_filename=docling_output.filename,
                    has_numerical_data=self._has_numerical_data(chunk_text),
                    is_financial=self._is_financial_content(chunk_text),
                    word_count=buffer_size,
                    entities=self._extract_entities(chunk_text),
                    time_period=self._detect_time_period(chunk_text),
                )
                chunks.append(chunk)
                
                # Keep overlap
                overlap_words = 0
                overlap_buffer = []
                for p in reversed(buffer):
                    p_words = len(p.split())
                    if overlap_words + p_words <= self.chunk_overlap:
                        overlap_buffer.insert(0, p)
                        overlap_words += p_words
                    else:
                        break
                
                buffer = overlap_buffer
                buffer_size = overlap_words
        
        # Flush remaining buffer
        if buffer and buffer_size >= self.min_chunk_size:
            chunk_text = "\n\n".join(buffer)
            chunk = HierarchicalChunk(
                id=self._generate_id(chunk_text, docling_output.document_id, "para"),
                document_id=docling_output.document_id,
                content=chunk_text,
                section_title=current_section,
                subsection=None,
                hierarchy_path=current_section,
                page=current_page,
                content_type="text",
                chunk_level="paragraph",
                source_filename=docling_output.filename,
                has_numerical_data=self._has_numerical_data(chunk_text),
                is_financial=self._is_financial_content(chunk_text),
                word_count=buffer_size,
                entities=self._extract_entities(chunk_text),
                time_period=self._detect_time_period(chunk_text),
            )
            chunks.append(chunk)
        
        return chunks
    
    def _create_table_chunks(self, docling_output) -> List[HierarchicalChunk]:
        """Create chunks for extracted tables."""
        chunks = []
        
        for table in docling_output.tables:
            # Create summary chunk
            summary = self._generate_table_summary(table)
            
            chunk = HierarchicalChunk(
                id=self._generate_id(table.markdown, docling_output.document_id, "tbl"),
                document_id=docling_output.document_id,
                content=summary,
                section_title="Tables and Data",
                subsection=table.caption or "Data Table",
                hierarchy_path=f"Tables > {table.caption or 'Table'}",
                page=table.page,
                content_type="table_summary",
                chunk_level="asset",
                source_filename=docling_output.filename,
                source_asset_id=table.id,
                has_numerical_data=True,
                is_financial=self._is_financial_content(table.markdown),
                word_count=len(summary.split()),
                entities=self._extract_entities(table.markdown),
                time_period=self._detect_time_period(table.markdown),
                confidence=table.confidence,
            )
            chunks.append(chunk)
            
            # Also create a raw table chunk for exact lookups
            raw_chunk = HierarchicalChunk(
                id=self._generate_id(table.markdown + "_raw", docling_output.document_id, "tbl_raw"),
                document_id=docling_output.document_id,
                content=table.markdown,
                section_title="Tables and Data",
                subsection=table.caption or "Data Table",
                hierarchy_path=f"Tables > {table.caption or 'Table'} (Raw)",
                page=table.page,
                content_type="table_raw",
                chunk_level="asset",
                source_filename=docling_output.filename,
                source_asset_id=table.id,
                has_numerical_data=True,
                is_financial=self._is_financial_content(table.markdown),
                word_count=len(table.markdown.split()),
                confidence=table.confidence,
            )
            chunks.append(raw_chunk)
        
        return chunks
    
    def _generate_table_summary(self, table) -> str:
        """Generate a natural language summary of a table."""
        parts = []
        
        if table.caption:
            parts.append(f"Table: {table.caption}")
        
        if table.headers:
            parts.append(f"Columns: {', '.join(table.headers)}")
        
        parts.append(f"Contains {len(table.rows)} rows of data.")
        
        # Include first few rows as context
        if table.rows:
            parts.append("Sample data:")
            for row in table.rows[:3]:
                row_str = " | ".join(str(cell) for cell in row if cell)
                parts.append(f"  - {row_str}")
        
        parts.append(f"\nFull table data:\n{table.markdown}")
        
        return "\n".join(parts)
    
    def _create_chart_chunks(self, docling_output) -> List[HierarchicalChunk]:
        """Create chunks for extracted charts/figures."""
        chunks = []
        
        for chart in docling_output.charts:
            # Create description chunk
            description = self._generate_chart_description(chart)
            
            chunk = HierarchicalChunk(
                id=self._generate_id(description, docling_output.document_id, "chart"),
                document_id=docling_output.document_id,
                content=description,
                section_title="Charts and Figures",
                subsection=chart.title or "Figure",
                hierarchy_path=f"Charts > {chart.title or 'Figure'}",
                page=chart.page,
                content_type="chart_summary",
                chunk_level="asset",
                source_filename=docling_output.filename,
                source_asset_id=chart.id,
                has_numerical_data=True,
                is_financial=True,  # Charts in financial docs are usually financial
                word_count=len(description.split()),
            )
            chunks.append(chunk)
        
        return chunks
    
    def _generate_chart_description(self, chart) -> str:
        """Generate a description for a chart."""
        parts = []
        
        if chart.title:
            parts.append(f"Chart: {chart.title}")
        
        if chart.caption:
            parts.append(f"Caption: {chart.caption}")
        
        parts.append(f"Type: {chart.chart_type}")
        parts.append(f"Located on page {chart.page}")
        
        if chart.raw_data:
            parts.append(f"Data points: {len(chart.raw_data)}")
        
        # Note: Actual chart analysis would be done by ChartAnalyzer
        parts.append("[Note: Detailed chart analysis pending VLM processing]")
        
        return "\n".join(parts)
