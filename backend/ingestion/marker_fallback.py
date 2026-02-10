"""
Marker PDF Fallback Parser - Backup parser when Docling is unavailable.

Uses marker-pdf for high-quality PDF extraction:
- OCR-capable text extraction
- Layout-aware parsing
- Table detection (basic)
- Structured markdown output

Falls back to PyMuPDF for basic extraction if marker is also unavailable.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import os
import re

from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MarkerPage:
    """Parsed page output from Marker."""
    page_number: int
    text: str
    tables: List[Dict[str, Any]] = field(default_factory=list)
    images: List[Dict[str, Any]] = field(default_factory=list)
    sections: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class MarkerOutput:
    """Full document output from Marker."""
    pages: List[MarkerPage]
    metadata: Dict[str, Any] = field(default_factory=dict)
    total_pages: int = 0
    parser_used: str = "marker"


class MarkerFallbackParser:
    """
    Fallback PDF parser using marker-pdf.
    
    Priority:
    1. marker-pdf (high quality, OCR capable)
    2. PyMuPDF (basic, fast)
    """

    def __init__(self):
        self._marker_available = self._check_marker()
        self._pymupdf_available = self._check_pymupdf()

    def _check_marker(self) -> bool:
        """Check if marker-pdf is installed."""
        try:
            import marker  # noqa: F401
            return True
        except ImportError:
            logger.info("marker-pdf not available")
            return False

    def _check_pymupdf(self) -> bool:
        """Check if PyMuPDF is installed."""
        try:
            import fitz  # noqa: F401
            return True
        except ImportError:
            logger.info("PyMuPDF not available")
            return False

    async def parse_document(
        self,
        file_path: str,
        document_id: str,
        extract_images: bool = True,
    ) -> Dict[str, Any]:
        """
        Parse a document using the best available parser.
        
        Args:
            file_path: Path to the document
            document_id: Unique document ID
            extract_images: Whether to extract images
            
        Returns:
            Parsed document in standardized format compatible with Docling output
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Try marker first
        if self._marker_available:
            try:
                return await self._parse_with_marker(file_path, document_id, extract_images)
            except Exception as e:
                logger.warning("Marker parsing failed, falling back to PyMuPDF", error=str(e))

        # Fallback to PyMuPDF
        if self._pymupdf_available:
            try:
                return await self._parse_with_pymupdf(file_path, document_id, extract_images)
            except Exception as e:
                logger.error("PyMuPDF parsing also failed", error=str(e))
                raise

        raise RuntimeError("No PDF parser available. Install marker-pdf or PyMuPDF.")

    async def _parse_with_marker(
        self, file_path: str, document_id: str, extract_images: bool
    ) -> Dict[str, Any]:
        """Parse using marker-pdf."""
        import asyncio

        def _marker_parse():
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict

            models = create_model_dict()
            converter = PdfConverter(artifact_dict=models)
            rendered = converter(file_path)

            return rendered

        # Run in thread pool since marker is synchronous
        loop = asyncio.get_event_loop()
        rendered = await loop.run_in_executor(None, _marker_parse)

        # Convert marker output to standardized format
        pages = []
        
        # Marker output is typically markdown text
        if hasattr(rendered, 'document'):
            doc = rendered.document
            text_content = doc.render() if hasattr(doc, 'render') else str(doc)
        elif isinstance(rendered, tuple):
            text_content = rendered[0] if rendered else ""
        else:
            text_content = str(rendered)

        # Split into pages (marker may not provide page boundaries)
        page_texts = self._split_into_pages(text_content)
        
        for i, page_text in enumerate(page_texts, 1):
            tables = self._extract_markdown_tables(page_text)
            sections = self._extract_sections(page_text)
            
            pages.append({
                "page_number": i,
                "text": page_text,
                "tables": tables,
                "graphics": [],
                "images": [],
                "sections": sections,
            })

        return {
            "pages": pages,
            "metadata": {
                "parser": "marker",
                "document_id": document_id,
                "total_pages": len(pages),
                "filename": os.path.basename(file_path),
            },
        }

    async def _parse_with_pymupdf(
        self, file_path: str, document_id: str, extract_images: bool
    ) -> Dict[str, Any]:
        """Parse using PyMuPDF (fitz)."""
        import fitz
        import asyncio

        def _pymupdf_parse():
            doc = fitz.open(file_path)
            pages = []
            
            for page_num, page in enumerate(doc, 1):
                # Extract text
                text = page.get_text("text")
                
                # Extract tables (basic using tabular text detection)
                tables = []
                try:
                    page_tables = page.find_tables()
                    for table in page_tables:
                        extracted = table.extract()
                        if extracted:
                            headers = extracted[0] if extracted else []
                            rows = extracted[1:] if len(extracted) > 1 else []
                            tables.append({
                                "headers": headers,
                                "rows": rows,
                                "bbox": list(table.bbox) if hasattr(table, 'bbox') else None,
                            })
                except Exception:
                    pass
                
                # Extract images
                images = []
                if extract_images:
                    try:
                        image_list = page.get_images(full=True)
                        for img_idx, img in enumerate(image_list):
                            xref = img[0]
                            base_image = doc.extract_image(xref)
                            if base_image:
                                images.append({
                                    "xref": xref,
                                    "width": base_image.get("width", 0),
                                    "height": base_image.get("height", 0),
                                    "colorspace": base_image.get("colorspace", ""),
                                })
                    except Exception:
                        pass
                
                # Extract sections from text structure
                sections = self._extract_sections(text)
                
                pages.append({
                    "page_number": page_num,
                    "text": text,
                    "tables": tables,
                    "graphics": [],
                    "images": images,
                    "sections": sections,
                })
            
            total = len(doc)
            doc.close()
            return pages, total

        loop = asyncio.get_event_loop()
        pages, total = await loop.run_in_executor(None, _pymupdf_parse)

        return {
            "pages": pages,
            "metadata": {
                "parser": "pymupdf",
                "document_id": document_id,
                "total_pages": total,
                "filename": os.path.basename(file_path),
            },
        }

    # ── Utility Methods ────────────────────────────────────────

    @staticmethod
    def _split_into_pages(text: str) -> List[str]:
        """Split text into approximate pages."""
        # Look for page break markers
        page_break_patterns = [
            r"\f",  # Form feed
            r"---\s*Page\s+\d+\s*---",
            r"\n\n\n+",  # Multiple blank lines as page separator
        ]
        
        for pattern in page_break_patterns:
            parts = re.split(pattern, text)
            if len(parts) > 1:
                return [p.strip() for p in parts if p.strip()]
        
        # Fallback: split by rough character count (~ 3000 chars per page)
        chars_per_page = 3000
        if len(text) <= chars_per_page:
            return [text]
        
        pages = []
        for i in range(0, len(text), chars_per_page):
            page = text[i:i + chars_per_page]
            # Try to break at paragraph boundary
            last_para = page.rfind("\n\n")
            if last_para > chars_per_page * 0.5:
                page = text[i:i + last_para]
            pages.append(page.strip())
        
        return [p for p in pages if p]

    @staticmethod
    def _extract_markdown_tables(text: str) -> List[Dict]:
        """Extract markdown-formatted tables from text."""
        tables = []
        lines = text.split("\n")
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            # Look for markdown table start (line with |)
            if "|" in line and not line.startswith("#"):
                table_lines = []
                while i < len(lines) and "|" in lines[i]:
                    table_lines.append(lines[i].strip())
                    i += 1
                
                if len(table_lines) >= 2:
                    # Parse table
                    rows = []
                    for tl in table_lines:
                        cells = [c.strip() for c in tl.split("|")[1:-1]]
                        # Skip separator rows (----)
                        if not all(re.match(r"^[-:]+$", c) for c in cells):
                            rows.append(cells)
                    
                    if rows:
                        headers = rows[0]
                        data_rows = rows[1:]
                        tables.append({
                            "headers": headers,
                            "rows": data_rows,
                        })
            else:
                i += 1

        return tables

    @staticmethod
    def _extract_sections(text: str) -> List[Dict]:
        """Extract section structure from text."""
        sections = []
        
        # Look for markdown-style headers
        header_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
        
        matches = list(header_pattern.finditer(text))
        
        for i, match in enumerate(matches):
            level = len(match.group(1))
            title = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            
            sections.append({
                "title": title,
                "level": level,
                "content": content,
            })
        
        # Also detect non-markdown headers (ALL CAPS lines, numbered sections)
        if not sections:
            cap_header = re.compile(r"^([A-Z][A-Z\s]{5,})$", re.MULTILINE)
            matches = list(cap_header.finditer(text))
            
            for i, match in enumerate(matches):
                title = match.group(1).strip()
                start = match.end()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                content = text[start:end].strip()
                
                sections.append({
                    "title": title,
                    "level": 1,
                    "content": content,
                })

        return sections
