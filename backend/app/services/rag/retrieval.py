"""
RAG retrieval engine.

Public API
----------
    retrieve_chunks(query_text, user_id, top_k=5) -> list[dict]
    retrieve_chunks_diversified(...) -> list[dict]

Each returned dict has the following keys:
    chunk_id        : int   - primary key of the Chunk row
    document_id     : str   - UUID of the parent Document
    snippet         : str   - raw chunk text (for display / citation)
    score           : float - cosine similarity (higher = more relevant)
    document_title  : str   - human-readable document title
    source_type     : str   - "upload" | "text"
    filename        : str | None - original filename (upload only, else None)

Architecture rules enforced here:
  - LLM/embedding calls only via WrapperClient (get_client).
  - DB access only via SQLAlchemy models.
  - All results scoped to the requesting user_id.
  - Only chunks belonging to the document's current ingestion are surfaced,
    so stale chunks from superseded ingestion runs are never returned.
"""

from __future__ import annotations

import logging
from typing import List

from app.db.models.chunk import Chunk
from app.db.models.document import Document
from app.extensions import db
from app.services.wrapper.client import WrapperError, get_client, get_embedding_model

log = logging.getLogger(__name__)

_EMBED_DIM = 1536  # Must match the Vector(1536) column on Chunk.embedding
_MAX_DIVERSIFIED_CANDIDATES = 48


def _embed_query(query_text: str) -> List[float]:
    """
    Embed a single query string via the wrapper and return a 1536-dim vector.

    Gemini embedding-001 returns 3072 dims; we truncate to 1536 using
    Matryoshka truncation (same strategy as ingestion) so the vectors are
    comparable to stored chunk embeddings.

    Raises WrapperError on any embedding failure.
    """
    client = get_client()
    response = client.embeddings(model=get_embedding_model(), input=query_text)

    data = response.get("data", [])
    if not data:
        raise WrapperError("Embeddings response contained no data items")

    embedding = data[0].get("embedding")
    if embedding is None:
        raise WrapperError("Embedding response missing 'embedding' field")

    return embedding[:_EMBED_DIM]


def retrieve_chunks(
    query_text: str,
    user_id: str,
    top_k: int = 5,
    document_ids: List[str] | None = None,
) -> List[dict]:
    """
    Embed *query_text* and return the *top_k* most similar chunks belonging
    to *user_id* whose parent document is not deleted and has a completed
    (current) ingestion.

    Parameters
    ----------
    query_text : str
        The user's raw query or passage to match against.
    user_id : str
        UUID of the requesting user. Results are strictly scoped to this user.
    top_k : int
        Maximum number of chunks to return (default 5).
    document_ids : list[str] | None
        When provided, restrict retrieval to only these document IDs.
        When ``None`` (or empty list treated as None), all of the user's
        non-deleted documents with a current ingestion are searched.

    Returns
    -------
    list[dict]
        Ordered by descending similarity (most relevant first).
        Each dict contains:
            chunk_id, document_id, snippet, score,
            document_title, source_type, filename
    """
    if not query_text or not query_text.strip():
        return []

    query_vector = _embed_query(query_text.strip())
    rows = _fetch_chunk_rows(
        query_vector=query_vector,
        user_id=user_id,
        top_k=top_k,
        document_ids=document_ids,
    )
    results = _rows_to_results(rows)

    log.debug(
        "retrieve_chunks user_id=%s top_k=%d doc_filter=%s query_len=%d results=%d",
        user_id,
        top_k,
        len(document_ids) if document_ids else "all",
        len(query_text),
        len(results),
    )

    return results


def retrieve_chunks_diversified(
    query_text: str,
    user_id: str,
    top_k: int = 5,
    document_ids: List[str] | None = None,
    minimum_document_count: int = 2,
) -> List[dict]:
    """
    Retrieve relevant chunks while reserving room for multiple documents.

    The final list still favors overall relevance, but first seeds the result
    set with the best chunk from the top matching documents so a single
    document cannot monopolize the entire source window.
    """
    if not query_text or not query_text.strip():
        return []

    minimum_document_count = max(1, min(int(minimum_document_count), top_k))
    query_vector = _embed_query(query_text.strip())

    if minimum_document_count <= 1:
        rows = _fetch_chunk_rows(
            query_vector=query_vector,
            user_id=user_id,
            top_k=top_k,
            document_ids=document_ids,
        )
        return _rows_to_results(rows)

    ranked_query, _ = _build_chunk_query(
        query_vector=query_vector,
        user_id=user_id,
        document_ids=document_ids,
        include_document_rank=True,
    )
    ranked_subquery = ranked_query.subquery()

    seed_rows = (
        db.session.query(ranked_subquery)
        .filter(ranked_subquery.c.document_rank == 1)
        .order_by(ranked_subquery.c.distance.asc())
        .limit(minimum_document_count)
        .all()
    )

    if len(seed_rows) <= 1:
        rows = _fetch_chunk_rows(
            query_vector=query_vector,
            user_id=user_id,
            top_k=top_k,
            document_ids=document_ids,
        )
        results = _rows_to_results(rows)
        log.debug(
            "retrieve_chunks_diversified fell back to global results user_id=%s top_k=%d "
            "doc_filter=%s query_len=%d results=%d",
            user_id,
            top_k,
            len(document_ids) if document_ids else "all",
            len(query_text),
            len(results),
        )
        return results

    candidate_limit = min(
        _MAX_DIVERSIFIED_CANDIDATES,
        max(top_k * 4, top_k + (minimum_document_count * 4)),
    )
    candidate_rows = (
        db.session.query(ranked_subquery)
        .order_by(ranked_subquery.c.distance.asc())
        .limit(candidate_limit)
        .all()
    )

    selected_rows = _select_diversified_rows(
        seed_rows=seed_rows,
        candidate_rows=candidate_rows,
        top_k=top_k,
    )
    results = _rows_to_results(selected_rows)

    log.debug(
        "retrieve_chunks_diversified user_id=%s top_k=%d doc_filter=%s min_docs=%d "
        "query_len=%d results=%d docs_used=%d",
        user_id,
        top_k,
        len(document_ids) if document_ids else "all",
        minimum_document_count,
        len(query_text),
        len(results),
        len({result["document_id"] for result in results}),
    )

    return results


def _fetch_chunk_rows(
    *,
    query_vector: List[float],
    user_id: str,
    top_k: int,
    document_ids: List[str] | None,
):
    query, distance_expr = _build_chunk_query(
        query_vector=query_vector,
        user_id=user_id,
        document_ids=document_ids,
    )
    return query.order_by(distance_expr.asc()).limit(top_k).all()


def _build_chunk_query(
    *,
    query_vector: List[float],
    user_id: str,
    document_ids: List[str] | None,
    include_document_rank: bool = False,
):
    # pgvector cosine distance operator (<=>).
    # Lower distance -> more similar -> we ORDER BY distance ASC.
    distance_expr = Chunk.embedding.cosine_distance(query_vector)

    columns = [
        Chunk.id.label("chunk_id"),
        Chunk.document_id.label("document_id"),
        Chunk.content.label("snippet"),
        Document.title.label("document_title"),
        Document.source_type.label("source_type"),
        Document.filename.label("filename"),
        distance_expr.label("distance"),
    ]
    if include_document_rank:
        columns.append(
            db.func.row_number().over(
                partition_by=Chunk.document_id,
                order_by=distance_expr.asc(),
            ).label("document_rank")
        )

    query = (
        db.session.query(*columns)
        .join(Document, Document.id == Chunk.document_id)
        .filter(
            Chunk.user_id == user_id,
            Document.user_id == user_id,
            Document.is_deleted.is_(False),
            Document.current_ingestion_id.isnot(None),
            Chunk.ingestion_id == Document.current_ingestion_id,
        )
    )

    if document_ids:
        query = query.filter(Document.id.in_(document_ids))

    return query, distance_expr


def _select_diversified_rows(
    *,
    seed_rows,
    candidate_rows,
    top_k: int,
):
    selected_rows = []
    seen_chunk_ids: set[int] = set()

    for row in list(seed_rows) + list(candidate_rows):
        chunk_id = int(_row_value(row, "chunk_id"))
        if chunk_id in seen_chunk_ids:
            continue
        selected_rows.append(row)
        seen_chunk_ids.add(chunk_id)
        if len(selected_rows) >= top_k:
            break

    selected_rows.sort(key=lambda row: float(_row_value(row, "distance")))
    return selected_rows


def _rows_to_results(rows) -> List[dict]:
    results: List[dict] = []
    for row in rows:
        distance = float(_row_value(row, "distance"))
        results.append(
            {
                "chunk_id": int(_row_value(row, "chunk_id")),
                "document_id": _row_value(row, "document_id"),
                "snippet": _row_value(row, "snippet"),
                "score": round(1.0 - distance, 6),
                "document_title": _row_value(row, "document_title"),
                "source_type": _row_value(row, "source_type"),
                "filename": _row_value(row, "filename"),
            }
        )
    return results


def _row_value(row, key: str):
    mapping = getattr(row, "_mapping", None)
    if mapping is not None and key in mapping:
        return mapping[key]
    return getattr(row, key)
