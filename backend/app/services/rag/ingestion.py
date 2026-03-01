"""
RAG ingestion pipeline.

Two entry points:
  ingest_upload(document, ingestion, file_path)
  ingest_text(document, ingestion, text)

Both run synchronously inside the request context (no task queue).
On success  → ingestion.status = "ready", document.current_ingestion_id set.
On failure  → ingestion.status = "failed", ingestion.error_message set.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from app.extensions import db
from app.db.models.chunk import Chunk
from app.db.models.document import Document
from app.db.models.document_ingestion import DocumentIngestion
from app.services.rag.chunking import TextChunk, chunk_pages, chunk_plain_text
from app.services.wrapper.client import WrapperError, get_client

log = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 100
EMBEDDING_MODEL = "gemini/gemini-embedding-001"


# ── PDF text extraction ───────────────────────────────────────────────────────

def _extract_pdf_pages(file_path: str) -> List[dict]:
    """
    Return list of {"page": int (1-based), "text": str} dicts using pdfplumber.
    """
    import pdfplumber  # local import: only needed for PDF uploads

    pages = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                pages.append({"page": i, "text": text})
    except Exception as exc:
        raise RuntimeError(f"PDF extraction failed: {exc}") from exc
    return pages


# ── Embedding helper ──────────────────────────────────────────────────────────

def _embed_chunks(chunks: List[TextChunk]) -> List[List[float]]:
    """
    Batch-embed chunk contents in groups of EMBED_BATCH_SIZE.
    Returns a list of embedding vectors aligned with `chunks`.
    """
    client = get_client()
    vectors: List[List[float]] = []

    for batch_start in range(0, len(chunks), EMBED_BATCH_SIZE):
        batch = chunks[batch_start : batch_start + EMBED_BATCH_SIZE]
        texts = [c.content for c in batch]

        response = client.embeddings(model=EMBEDDING_MODEL, input=texts)
        # OpenAI-style: {"data": [{"index": N, "embedding": [...]}, ...]}
        data = response.get("data", [])
        # Sort by index to guarantee order
        data_sorted = sorted(data, key=lambda d: d.get("index", 0))
        for item in data_sorted:
            embedding = item.get("embedding")
            if embedding is None:
                raise WrapperError("Embedding response missing 'embedding' field")
            # DB column is Vector(1536); Gemini embedding-001 returns 3072 dims.
            # Matryoshka embeddings retain semantic quality when truncated.
            vectors.append(embedding[:1536])

    return vectors


# ── Chunk persistence ────────────────────────────────────────────────────────

def _save_chunks(
    document: Document,
    ingestion: DocumentIngestion,
    chunks: List[TextChunk],
    vectors: List[List[float]],
) -> None:
    for chunk, vector in zip(chunks, vectors):
        row = Chunk(
            user_id=document.user_id,
            document_id=document.id,
            ingestion_id=ingestion.id,
            chunk_index=chunk.index,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
            content=chunk.content,
            embedding=vector,
        )
        db.session.add(row)


# ── Mark ingestion done ───────────────────────────────────────────────────────

def _mark_ready(document: Document, ingestion: DocumentIngestion) -> None:
    ingestion.status = "ready"
    ingestion.completed_at = datetime.now(timezone.utc)
    document.current_ingestion_id = ingestion.id
    db.session.commit()


def _mark_failed(ingestion: DocumentIngestion, error: str) -> None:
    ingestion.status = "failed"
    ingestion.error_message = error[:2000]
    ingestion.completed_at = datetime.now(timezone.utc)
    db.session.commit()


# ── Public entry points ───────────────────────────────────────────────────────

def ingest_upload(
    document: Document,
    ingestion: DocumentIngestion,
    file_path: str,
) -> None:
    """
    Full pipeline for an uploaded file (PDF or plain text).
    Mutates ingestion.status in place.
    """
    try:
        mime = (document.mime_type or "").lower()

        if "pdf" in mime or file_path.lower().endswith(".pdf"):
            pages = _extract_pdf_pages(file_path)
            if not any(p["text"].strip() for p in pages):
                raise RuntimeError("PDF appears to contain no extractable text (possibly scanned).")
            chunks = chunk_pages(pages)
        else:
            # Plain text file
            with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
                raw_text = fh.read()
            chunks = chunk_plain_text(raw_text)

        if not chunks:
            raise RuntimeError("No text chunks produced from the uploaded file.")

        vectors = _embed_chunks(chunks)
        _save_chunks(document, ingestion, chunks, vectors)
        _mark_ready(document, ingestion)

        log.info(
            "ingest_upload success doc=%s ingestion=%s chunks=%d",
            document.id,
            ingestion.id,
            len(chunks),
        )

    except Exception as exc:
        log.exception("ingest_upload failed doc=%s ingestion=%s", document.id, ingestion.id)
        _mark_failed(ingestion, str(exc))
        raise


def ingest_text(
    document: Document,
    ingestion: DocumentIngestion,
    text: str,
) -> None:
    """
    Full pipeline for a plain-text context document.
    Mutates ingestion.status in place.
    """
    try:
        chunks = chunk_plain_text(text)

        if not chunks:
            raise RuntimeError("No text chunks produced from the provided text.")

        vectors = _embed_chunks(chunks)
        _save_chunks(document, ingestion, chunks, vectors)
        _mark_ready(document, ingestion)

        log.info(
            "ingest_text success doc=%s ingestion=%s chunks=%d",
            document.id,
            ingestion.id,
            len(chunks),
        )

    except Exception as exc:
        log.exception("ingest_text failed doc=%s ingestion=%s", document.id, ingestion.id)
        _mark_failed(ingestion, str(exc))
        raise
