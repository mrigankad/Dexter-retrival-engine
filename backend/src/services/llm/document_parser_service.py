"""
Document Parser Service.

Provides document parsing for PDF, DOCX, and TXT files.
Includes page-level extraction for source citation.
"""

import os
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple, Dict, Any

from src.core.logger import get_logger

logger = get_logger(__name__)


class DocumentParser(ABC):
    """Abstract base class for document parsers."""
    
    @abstractmethod
    async def parse(self, file_path: str) -> str:
        """Parse document and return text content."""
        pass
    
    @abstractmethod
    async def parse_with_pages(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse document and return text with page info."""
        pass
    
    @abstractmethod
    def supports(self, file_extension: str) -> bool:
        """Check if parser supports the file type."""
        pass


class PDFParser(DocumentParser):
    """PDF document parser using pypdf."""
    
    async def parse(self, file_path: str) -> str:
        """Parse PDF and extract text."""
        pages = await self.parse_with_pages(file_path)
        return "\n\n".join([p["content"] for p in pages])
    
    async def parse_with_pages(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse PDF and extract text with page numbers."""
        from pypdf import PdfReader
        
        reader = PdfReader(file_path)
        pages = []
        
        for page_num, page in enumerate(reader.pages, 1):
            text = page.extract_text()
            if text and text.strip():
                pages.append({
                    "page": page_num,
                    "content": text.strip(),
                    "total_pages": len(reader.pages),
                })
        
        return pages
    
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == "pdf"


class DOCXParser(DocumentParser):
    """DOCX document parser using python-docx."""
    
    async def parse(self, file_path: str) -> str:
        """Parse DOCX and extract text."""
        pages = await self.parse_with_pages(file_path)
        return "\n\n".join([p["content"] for p in pages])
    
    async def parse_with_pages(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse DOCX and extract text. DOCX doesn't have clear page breaks, so we estimate."""
        from docx import Document
        
        doc = Document(file_path)
        text_parts = []
        
        for para in doc.paragraphs:
            if para.text.strip():
                text_parts.append(para.text)
        
        # DOCX doesn't have pages, so return as single section
        full_text = "\n\n".join(text_parts)
        
        # Estimate pages (~3000 chars per page)
        char_per_page = 3000
        estimated_pages = max(1, len(full_text) // char_per_page)
        
        return [{
            "page": 1,
            "content": full_text,
            "total_pages": estimated_pages,
            "note": "DOCX files don't have page numbers; text may span multiple printed pages"
        }]
    
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == "docx"


class TXTParser(DocumentParser):
    """Plain text file parser."""
    
    async def parse(self, file_path: str) -> str:
        """Parse TXT file."""
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    
    async def parse_with_pages(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse TXT file. TXT files don't have pages."""
        content = await self.parse(file_path)
        return [{
            "page": 1,
            "content": content,
            "total_pages": 1,
        }]
    
    def supports(self, file_extension: str) -> bool:
        return file_extension.lower() == "txt"


class DocumentParserService:
    """Document parser factory and coordinator."""
    
    def __init__(self):
        self.parsers: List[DocumentParser] = [
            PDFParser(),
            DOCXParser(),
            TXTParser(),
        ]
    
    def get_parser(self, file_path: str) -> Optional[DocumentParser]:
        """Get appropriate parser for file type."""
        ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
        
        for parser in self.parsers:
            if parser.supports(ext):
                return parser
        
        return None
    
    async def parse(self, file_path: str) -> str:
        """Parse document and return text content."""
        parser = self.get_parser(file_path)
        
        if not parser:
            raise ValueError(f"Unsupported file type: {file_path}")
        
        logger.info("Parsing document", file_path=file_path, parser=type(parser).__name__)
        
        text = await parser.parse(file_path)
        
        logger.info("Document parsed", file_path=file_path, text_length=len(text))
        return text
    
    async def parse_with_pages(self, file_path: str) -> List[Dict[str, Any]]:
        """Parse document and return text with page info."""
        parser = self.get_parser(file_path)
        
        if not parser:
            raise ValueError(f"Unsupported file type: {file_path}")
        
        logger.info("Parsing document with pages", file_path=file_path, parser=type(parser).__name__)
        
        pages = await parser.parse_with_pages(file_path)
        
        logger.info("Document parsed", file_path=file_path, pages=len(pages))
        return pages
