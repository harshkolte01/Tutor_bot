"""
Text chunking service for the RAG pipeline.

Splits text into overlapping character-based chunks.
For PDF ingestion, page metadata is preserved per chunk.
For plain-text ingestion, page_start / page_end are None.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

CHUNK_SIZE = 1000       # target characters per chunk
CHUNK_OVERLAP = 200     # overlap between consecutive chunks


@dataclass
class TextChunk:
    index: int
    content: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None


def chunk_plain_text(text: str) -> List[TextChunk]:
    """
    Split a plain string into overlapping chunks.
    page_start / page_end are left as None.
    """
    chunks: List[TextChunk] = []
    start = 0
    idx = 0
    text_len = len(text)

    while start < text_len:
        end = min(start + CHUNK_SIZE, text_len)
        content = text[start:end].strip()
        if content:
            chunks.append(TextChunk(index=idx, content=content))
            idx += 1
        if end >= text_len:
            break
        start = end - CHUNK_OVERLAP

    return chunks


def chunk_pages(pages: List[dict]) -> List[TextChunk]:
    """
    Chunk a list of page dicts: {"page": int (1-based), "text": str}.

    Strategy:
    - Walk pages in order.
    - Accumulate text into a buffer, tracking which pages contribute.
    - When buffer exceeds CHUNK_SIZE, flush a chunk with page metadata.
    - Overlap is seeded into the next buffer.
    """
    chunks: List[TextChunk] = []
    idx = 0

    buffer_text = ""
    buffer_page_start: Optional[int] = None
    buffer_page_end: Optional[int] = None

    def flush_chunk(text: str, p_start: Optional[int], p_end: Optional[int]) -> None:
        nonlocal idx
        content = text.strip()
        if content:
            chunks.append(
                TextChunk(index=idx, content=content, page_start=p_start, page_end=p_end)
            )
            idx += 1

    for page_dict in pages:
        page_num = page_dict["page"]
        page_text = (page_dict.get("text") or "").strip()
        if not page_text:
            continue

        if buffer_page_start is None:
            buffer_page_start = page_num
        buffer_page_end = page_num
        buffer_text += (" " if buffer_text else "") + page_text

        # Flush chunks while buffer is larger than CHUNK_SIZE
        while len(buffer_text) >= CHUNK_SIZE:
            chunk_text = buffer_text[:CHUNK_SIZE]
            flush_chunk(chunk_text, buffer_page_start, buffer_page_end)
            # Seed overlap
            overlap_text = buffer_text[CHUNK_SIZE - CHUNK_OVERLAP:]
            buffer_text = overlap_text
            # Page tracking: the overlap may still be on the same page(s)
            buffer_page_start = buffer_page_end  # best approximation

    # Flush remaining buffer
    if buffer_text.strip():
        flush_chunk(buffer_text, buffer_page_start, buffer_page_end)

    return chunks
