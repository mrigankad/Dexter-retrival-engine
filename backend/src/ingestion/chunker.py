"""
Hierarchical, structure-aware chunker.

* Tracks the section path from markdown headings or heading-like lines.
* Packs paragraphs up to ``chunk_size`` tokens with sentence-aware overlap.
* Keeps markdown tables intact as ``table`` chunks (plus a short summary chunk
  for semantic matching when the table is large).
* Prefixes a contextual header (document title + section path) to the text that
  is embedded — "contextual retrieval" — while keeping the raw text for display.
"""

from __future__ import annotations

import re
import uuid
from typing import List, Optional, Tuple

from src.contracts import Chunk, ChunkLevel, ContentType, ParsedDocument
from src.core.config import settings

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_NUMBERED_HEADING = re.compile(r"^(\d+(?:\.\d+){0,3})[.)]?\s+([A-Z][^\n]{2,80})$")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _looks_like_heading(line: str) -> Optional[Tuple[int, str]]:
    s = line.strip()
    if not s or len(s) > 90:
        return None
    m = _MD_HEADING.match(s)
    if m:
        return len(m.group(1)), m.group(2)
    m = _NUMBERED_HEADING.match(s)
    if m and not s.endswith("."):
        return min(1 + m.group(1).count("."), 6), s
    words = s.split()
    if 1 < len(words) <= 10 and (s.isupper() or (s.istitle() and not s.endswith((".", ",", ";", ":")))):
        return 2, s
    return None


def _is_table_block(block: str) -> bool:
    lines = [l for l in block.splitlines() if l.strip()]
    return len(lines) >= 2 and all(l.strip().startswith("|") for l in lines)


class HierarchicalChunker:
    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        min_tokens: Optional[int] = None,
        contextual_headers: Optional[bool] = None,
    ):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None else settings.chunk_overlap
        self.min_tokens = min_tokens or settings.chunk_min_tokens
        self.contextual_headers = settings.contextual_headers if contextual_headers is None else contextual_headers

    # ── public ─────────────────────────────────────────────────────────

    def chunk_document(self, doc: ParsedDocument, document_id: str) -> List[Chunk]:
        chunks: List[Chunk] = []
        section_path: List[str] = []
        section_levels: List[int] = []
        title = doc.title or doc.filename

        for page in doc.pages:
            blocks = [b.strip() for b in re.split(r"\n\s*\n", page.text) if b.strip()]
            para_buf: List[str] = []
            buf_tokens = 0
            buf_path: List[str] = list(section_path)
            overlap_only = False   # buffer holds nothing but the carried-over overlap tail

            def flush() -> None:
                nonlocal para_buf, buf_tokens, overlap_only
                if not para_buf or overlap_only:
                    para_buf, buf_tokens, overlap_only = [], 0, False
                    return
                text = "\n\n".join(para_buf)
                chunks.append(self._make_chunk(document_id, doc, title, text, page.page, buf_path, ContentType.TEXT, ChunkLevel.PARAGRAPH))
                # overlap: carry the tail sentences into the next chunk
                tail = self._overlap_tail(text)
                para_buf = [tail] if tail else []
                buf_tokens = estimate_tokens(tail) if tail else 0
                overlap_only = bool(tail)

            for block in blocks:
                heading = _looks_like_heading(block) if "\n" not in block else None
                if heading:
                    flush()
                    para_buf, buf_tokens = [], 0
                    level, text = heading
                    while section_levels and section_levels[-1] >= level:
                        section_levels.pop()
                        section_path.pop()
                    section_levels.append(level)
                    section_path.append(text)
                    buf_path = list(section_path)
                    continue

                if _is_table_block(block):
                    flush()
                    para_buf, buf_tokens = [], 0
                    chunks.extend(self._table_chunks(document_id, doc, title, block, page.page, list(section_path)))
                    continue

                # Long paragraph: split by sentences into windows.
                for piece in self._split_long(block):
                    t = estimate_tokens(piece)
                    if buf_tokens + t > self.chunk_size and para_buf and not overlap_only:
                        flush()
                        buf_path = list(section_path)
                    para_buf.append(piece)
                    buf_tokens += t
                    overlap_only = False
            # Page end: flush but allow the final buffer to be small.
            if overlap_only:
                para_buf, buf_tokens, overlap_only = [], 0, False
            if para_buf and (buf_tokens >= self.min_tokens or not chunks):
                text = "\n\n".join(para_buf)
                chunks.append(self._make_chunk(document_id, doc, title, text, page.page, buf_path, ContentType.TEXT, ChunkLevel.PARAGRAPH))
            elif para_buf and chunks and chunks[-1].page == page.page and chunks[-1].content_type == ContentType.TEXT:
                # merge tiny tail into the previous chunk on the same page
                prev = chunks[-1]
                merged = prev.raw_content + "\n\n" + "\n\n".join(para_buf)
                chunks[-1] = self._make_chunk(document_id, doc, title, merged, page.page, prev.section_path, ContentType.TEXT, ChunkLevel.PARAGRAPH)
            elif para_buf:
                text = "\n\n".join(para_buf)
                chunks.append(self._make_chunk(document_id, doc, title, text, page.page, buf_path, ContentType.TEXT, ChunkLevel.PARAGRAPH))

        if settings.summary_chunks_enabled and chunks:
            chunks.insert(0, self._outline_chunk(document_id, doc, title, chunks))
        for i, c in enumerate(chunks):
            c.chunk_index = i
            c.total_pages = doc.total_pages
        return chunks

    def _outline_chunk(self, document_id: str, doc: ParsedDocument, title: str, chunks: List[Chunk]) -> Chunk:
        """Extractive document overview: title, section headings, opening text, table list."""
        headings: List[str] = []
        for c in chunks:
            for h in c.section_path:
                if h not in headings:
                    headings.append(h)
        first_text = next((c.raw_content for c in chunks if c.content_type == ContentType.TEXT), "")
        tables = sum(1 for c in chunks if c.chunk_level == ChunkLevel.TABLE_DATA)
        parts = [f"Overview of document '{title}' ({doc.total_pages} pages, {len(chunks)} sections indexed)."]
        if headings:
            parts.append("Sections: " + "; ".join(headings[:40]) + ".")
        if tables:
            parts.append(f"Contains {tables} table(s).")
        if first_text:
            parts.append("Opening: " + " ".join(first_text.split())[:600])
        text = "\n".join(parts)
        chunk = self._make_chunk(document_id, doc, title, text, chunks[0].page or 1, [], ContentType.TEXT, ChunkLevel.SECTION)
        chunk.metadata["chunk_level"] = "document_summary"
        return chunk

    # ── helpers ────────────────────────────────────────────────────────

    def _overlap_tail(self, text: str) -> str:
        if self.chunk_overlap <= 0:
            return ""
        sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
        tail: List[str] = []
        tokens = 0
        for s in reversed(sentences):
            t = estimate_tokens(s)
            if tokens + t > self.chunk_overlap and tail:
                break
            tail.insert(0, s)
            tokens += t
            if tokens >= self.chunk_overlap:
                break
        # Always carry at least the last sentence (bounded to roughly 2x the overlap budget).
        joined = " ".join(tail).strip()
        max_chars = max(self.chunk_overlap, 1) * 8
        return joined[-max_chars:] if len(joined) > max_chars else joined

    def _split_long(self, block: str) -> List[str]:
        if estimate_tokens(block) <= self.chunk_size:
            return [block]
        target = max(40, self.chunk_size - self.chunk_overlap)   # leave room for the carried overlap
        pieces: List[str] = []
        cur: List[str] = []
        cur_tokens = 0
        for sentence in _SENTENCE_SPLIT.split(block):
            t = estimate_tokens(sentence)
            if cur_tokens + t > target and cur:
                pieces.append(" ".join(cur))
                cur, cur_tokens = [], 0
            if t > target:  # pathological sentence: hard split
                step = target * 4
                pieces.extend(sentence[i:i + step] for i in range(0, len(sentence), step))
                continue
            cur.append(sentence)
            cur_tokens += t
        if cur:
            pieces.append(" ".join(cur))
        return pieces

    def _header(self, title: str, section_path: List[str], content_type: ContentType) -> str:
        if not self.contextual_headers:
            return ""
        parts = [f"Document: {title}"]
        if section_path:
            parts.append("Section: " + " > ".join(section_path[-3:]))
        if content_type != ContentType.TEXT:
            parts.append(f"Type: {content_type.value}")
        return " | ".join(parts) + "\n"

    def _make_chunk(self, document_id: str, doc: ParsedDocument, title: str, text: str, page: int,
                    section_path: List[str], content_type: ContentType, level: ChunkLevel) -> Chunk:
        header = self._header(title, section_path, content_type)
        return Chunk(
            id=str(uuid.uuid4()),
            document_id=document_id,
            content=header + text,
            raw_content=text,
            chunk_index=0,
            page=page,
            total_pages=doc.total_pages,
            content_type=content_type,
            chunk_level=level,
            section_path=list(section_path),
            source=doc.filename,
            token_estimate=estimate_tokens(header + text),
            metadata={"title": title, "parser": doc.parser},
        )

    def _table_chunks(self, document_id: str, doc: ParsedDocument, title: str, table_md: str, page: int,
                      section_path: List[str]) -> List[Chunk]:
        out: List[Chunk] = []
        rows = [r for r in table_md.splitlines() if r.strip()]
        header_rows = rows[:2]
        body = rows[2:]
        max_rows = max(8, (self.chunk_size * 4) // max(40, len(rows[0]) if rows else 40))
        if len(body) <= max_rows:
            out.append(self._make_chunk(document_id, doc, title, table_md, page, section_path, ContentType.TABLE, ChunkLevel.TABLE_DATA))
        else:
            for i in range(0, len(body), max_rows):
                part = "\n".join(header_rows + body[i:i + max_rows])
                out.append(self._make_chunk(document_id, doc, title, part, page, section_path, ContentType.TABLE, ChunkLevel.TABLE_DATA))
        if len(body) > 3:
            cols = [c.strip() for c in rows[0].strip("|").split("|")] if rows else []
            summary = f"Table with {len(body)} rows and columns: {', '.join(cols[:12])}." if cols else f"Table with {len(body)} rows."
            if section_path:
                summary += f" Located in section: {' > '.join(section_path[-2:])}."
            out.append(self._make_chunk(document_id, doc, title, summary, page, section_path, ContentType.TABLE, ChunkLevel.TABLE_SUMMARY))
        return out
