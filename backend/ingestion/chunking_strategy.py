"""
Chunking Strategy - Semantic document chunking.

Enhanced implementation with:
- Intelligent document chunking with overlap
- Table/financial data detection and preservation
- Larger chunks for numerical content
"""

from typing import List, Dict, Any
import re

from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)


# Patterns to detect tabular/financial content that should stay together
TABLE_PATTERNS = [
    r'(?:\t.*){2,}',  # Multiple tabs (tabular data)
    r'(?:\|.*\|)',  # Pipe-delimited tables
    r'(?:[\d,]+\s+[\d,]+\s+[\d,]+)',  # Multiple numbers in sequence
    r'(?:Rs\.?\s*[\d,]+|₹\s*[\d,]+|\$\s*[\d,]+)',  # Currency values
    r'(?:\d+\.?\d*\s*%)',  # Percentages
    r'(?:FY\s*\d{2,4}|Q[1-4]\s*\d{2,4})',  # Fiscal year/quarter references
]

FINANCIAL_SECTION_KEYWORDS = [
    'revenue', 'profit', 'margin', 'ebitda', 'ebit', 'cost', 'expense',
    'sales', 'income', 'asset', 'liability', 'equity', 'cash flow',
    'balance sheet', 'income statement', 'p&l', 'financial highlight',
    'key metric', 'performance indicator', 'benchmark', 'price',
]


def contains_tabular_content(text: str) -> bool:
    """Check if text contains tabular or structured data."""
    for pattern in TABLE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def is_financial_section(text: str) -> bool:
    """Check if text appears to be a financial section."""
    text_lower = text.lower()
    matches = sum(1 for keyword in FINANCIAL_SECTION_KEYWORDS if keyword in text_lower)
    return matches >= 2


class ChunkingStrategy:
    """Enhanced semantic chunking strategy with table preservation."""
    
    def __init__(
        self,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap or settings.chunk_overlap
    
    def chunk_text(
        self,
        text: str,
        metadata: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        """
        Chunk text into semantic segments.
        
        Enhanced to:
        - Preserve tabular data together
        - Use larger chunks for financial sections
        - Maintain numerical context
        
        Args:
            text: Full document text
            metadata: Document metadata to include in chunks
            
        Returns:
            List of chunk dictionaries with content and metadata
        """
        metadata = metadata or {}
        
        # Clean text
        text = self._clean_text(text)
        
        # Check if this appears to be financial content
        is_financial = is_financial_section(text)
        has_tables = contains_tabular_content(text)
        
        # Adjust chunk size for content type
        effective_chunk_size = self.chunk_size
        effective_overlap = self.chunk_overlap
        
        if is_financial or has_tables:
            # Use larger chunks for financial/tabular content to preserve context
            effective_chunk_size = int(self.chunk_size * 1.5)
            effective_overlap = int(self.chunk_overlap * 1.5)
            logger.debug("Using larger chunks for financial/tabular content")
        
        # Split into paragraphs first
        paragraphs = self._split_into_paragraphs(text)
        
        # Build chunks from paragraphs
        chunks = []
        current_chunk = []
        current_length = 0
        
        for para in paragraphs:
            para_len = len(para.split())
            
            # Check if this paragraph contains important data
            para_has_data = contains_tabular_content(para) or is_financial_section(para)
            
            # If paragraph has important data and current chunk is getting full,
            # start a new chunk to ensure data stays with its context
            if para_has_data and current_length > effective_chunk_size * 0.7:
                # Save current chunk
                if current_chunk:
                    chunk_text = "\n\n".join(current_chunk)
                    chunks.append({
                        "content": chunk_text,
                        "char_count": len(chunk_text),
                        "word_count": len(chunk_text.split()),
                        "has_numerical_data": contains_tabular_content(chunk_text),
                        **metadata,
                    })
                
                # Start new chunk with overlap
                overlap_text = self._get_overlap(current_chunk, effective_overlap)
                current_chunk = [overlap_text] if overlap_text else []
                current_length = len(overlap_text.split()) if overlap_text else 0
            
            elif current_length + para_len > effective_chunk_size:
                # Save current chunk
                if current_chunk:
                    chunk_text = "\n\n".join(current_chunk)
                    chunks.append({
                        "content": chunk_text,
                        "char_count": len(chunk_text),
                        "word_count": len(chunk_text.split()),
                        "has_numerical_data": contains_tabular_content(chunk_text),
                        **metadata,
                    })
                
                # Start new chunk with overlap
                overlap_text = self._get_overlap(current_chunk, effective_overlap)
                current_chunk = [overlap_text] if overlap_text else []
                current_length = len(overlap_text.split()) if overlap_text else 0
            
            current_chunk.append(para)
            current_length += para_len
        
        # Don't forget the last chunk
        if current_chunk:
            chunk_text = "\n\n".join(current_chunk)
            chunks.append({
                "content": chunk_text,
                "char_count": len(chunk_text),
                "word_count": len(chunk_text.split()),
                "has_numerical_data": contains_tabular_content(chunk_text),
                **metadata,
            })
        
        # Add chunk indices
        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = i
            chunk["total_chunks"] = len(chunks)
        
        logger.info(
            "Document chunked",
            total_chunks=len(chunks),
            avg_size=sum(c["word_count"] for c in chunks) // max(len(chunks), 1),
            is_financial=is_financial,
            has_tables=has_tables,
        )
        
        return chunks
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text while preserving table structure."""
        # Remove excessive whitespace but preserve table-like spacing
        text = re.sub(r'\n{4,}', '\n\n\n', text)  # Max 3 newlines
        text = re.sub(r'(?<!\n) {3,}(?!\n)', '  ', text)  # Reduce spaces, but not in tables
        text = text.strip()
        return text
    
    def _split_into_paragraphs(self, text: str) -> List[str]:
        """Split text into paragraphs, keeping tables together."""
        # Normalize line endings
        text = text.replace('\r\n', '\n')
        
        # If the text has double newlines, they are the best indicator
        if '\n\n' in text:
            paragraphs = text.split('\n\n')
        else:
            # Fallback for PDFs with only single newlines
            # Split by newline if followed by a capital letter, bullet, or number
            # This is heuristic but better than nothing
            paragraphs = re.split(r'\n(?=[A-Z0-9\*\-•])', text)
        
        result = []
        table_buffer = []
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            # If this looks like a table row, buffer it
            # Tables often have multiple spaces or tabs
            is_table_row = contains_tabular_content(para) or len(re.findall(r'\s{2,}', para)) > 2
            
            if is_table_row or (table_buffer and len(para) < 150):
                table_buffer.append(para)
            else:
                # Flush table buffer if we have one
                if table_buffer:
                    result.append("\n".join(table_buffer))
                    table_buffer = []
                result.append(para)
        
        # Flush remaining table buffer
        if table_buffer:
            result.append("\n".join(table_buffer))
        
        return result
    
    def _get_overlap(self, chunks: List[str], overlap_size: int = None) -> str:
        """Get overlap text from previous chunk."""
        if not chunks:
            return ""
        
        overlap_size = overlap_size or self.chunk_overlap
        
        # Take last paragraph(s) up to overlap size
        overlap_words = 0
        overlap_paras = []
        
        for para in reversed(chunks):
            para_words = len(para.split())
            if overlap_words + para_words <= overlap_size:
                overlap_paras.insert(0, para)
                overlap_words += para_words
            else:
                break
        
        return "\n\n".join(overlap_paras)


class ParagraphChunker(ChunkingStrategy):
    """
    Paragraph-wise chunking strategy.
    
    Treats each logical paragraph as a primary chunk. 
    Groups very small paragraphs to maintain context.
    Splits very large paragraphs if they exceed chunk_size.
    """
    
    def chunk_text(
        self,
        text: str,
        metadata: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        metadata = metadata or {}
        text = self._clean_text(text)
        
        # Split into paragraphs
        raw_paragraphs = self._split_into_paragraphs(text)
        
        chunks = []
        current_group = []
        current_length = 0
        
        # Minimum words to be considered a standalone chunk
        min_words = 40
        
        for para in raw_paragraphs:
            para = para.strip()
            if not para:
                continue
                
            para_len = len(para.split())
            
            # If paragraph is huge, split it using parent logic
            if para_len > self.chunk_size * 1.5:
                # Flush current group if any
                if current_group:
                    self._add_chunk(chunks, current_group, metadata)
                    current_group = []
                    current_length = 0
                
                # Use basic chunking for this giant paragraph
                sub_chunks = super().chunk_text(para, metadata)
                chunks.extend(sub_chunks)
                continue
            
            # If current paragraph is significant or current group is full, flush
            if (para_len >= min_words or current_length + para_len > self.chunk_size) and current_group:
                self._add_chunk(chunks, current_group, metadata)
                current_group = []
                current_length = 0
            
            current_group.append(para)
            current_length += para_len
            
            # If we've reached a good size, flush
            if current_length >= self.chunk_size:
                self._add_chunk(chunks, current_group, metadata)
                current_group = []
                current_length = 0
                
        # Final flush
        if current_group:
            self._add_chunk(chunks, current_group, metadata)
            
        # Renumber
        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = i
            chunk["total_chunks"] = len(chunks)
            
        return chunks

    def _add_chunk(self, chunks: list, para_list: list, metadata: dict):
        chunk_text = "\n\n".join(para_list)
        chunks.append({
            "content": chunk_text,
            "char_count": len(chunk_text),
            "word_count": len(chunk_text.split()),
            "has_numerical_data": contains_tabular_content(chunk_text),
            "is_financial": is_financial_section(chunk_text),
            **metadata,
        })
class SentenceChunker(ChunkingStrategy):
    """Chunk by sentences for finer granularity."""
    
    def chunk_text(
        self,
        text: str,
        metadata: Dict[str, Any] = None,
    ) -> List[Dict[str, Any]]:
        """Chunk text by sentences."""
        metadata = metadata or {}
        text = self._clean_text(text)
        
        # Split into sentences
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sent_len = len(sentence.split())
            
            if current_length + sent_len > self.chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                chunks.append({
                    "content": chunk_text,
                    "word_count": len(chunk_text.split()),
                    **metadata,
                })
                
                # Overlap: keep last few sentences
                overlap_count = min(2, len(current_chunk))
                current_chunk = current_chunk[-overlap_count:]
                current_length = sum(len(s.split()) for s in current_chunk)
            
            current_chunk.append(sentence)
            current_length += sent_len
        
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append({
                "content": chunk_text,
                "word_count": len(chunk_text.split()),
                **metadata,
            })
        
        for i, chunk in enumerate(chunks):
            chunk["chunk_index"] = i
            chunk["total_chunks"] = len(chunks)
        
        return chunks
