# Step 6 — Documents API + Ingestion Pipeline

**Date:** 2026-03-01  
**Time:** 12:00  
**Task:** Step 6 — Documents API + Ingestion Pipeline (PDF + Text)

---

## Summary

Implemented the full documents REST API and synchronous RAG ingestion pipeline.  
Users can upload PDF/text files or paste plain text; the pipeline chunks the content, batch-embeds via the wrapper (`gemini/gemini-embedding-001`), and stores vectors in `chunks`.

---

## Files Created

| File | Purpose |
|------|---------|
| `backend/app/api/documents.py` | All 6 document API route handlers |
| `backend/app/services/rag/chunking.py` | Character-based sliding-window chunker (plain text + page-aware PDF) |
| `backend/app/services/rag/ingestion.py` | Full ingestion pipeline: extract → chunk → embed → persist |

## Files Edited

| File | Change |
|------|--------|
| `backend/app/__init__.py` | Registered `documents_bp` blueprint |
| `backend/app/config.py` | Added `UPLOAD_FOLDER` config var (default: `instance/uploads`) |
| `backend/requirements.txt` | Added `pdfplumber`, `requests` |

---

## Endpoints Added

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/documents/upload` | JWT | Multipart file upload (PDF / plain text) |
| POST | `/api/documents/text` | JWT | JSON `{title, text}` plain-text context |
| GET | `/api/documents` | JWT | List user's non-deleted documents |
| GET | `/api/documents/<id>` | JWT | Document detail + current ingestion |
| DELETE | `/api/documents/<id>` | JWT | Soft delete (`is_deleted=true`) |
| GET | `/api/documents/<id>/ingestions/<ingestion_id>/status` | JWT | Ingestion status + chunk count |

---

## No DB / Migration Changes

All required tables (`documents`, `document_ingestions`, `chunks`) were created in Step 5.  
No new migrations needed.

---

## Processing Sequences

### Upload flow
1. Validate file (type: PDF / .txt / .md; size ≤ 20 MB).
2. Save to `UPLOAD_FOLDER` with a UUID-prefixed filename.
3. Create `documents` row (`source_type="upload"`, `filename`, `mime_type`).
4. Create `document_ingestions` row (`status="processing"`, `file_path` set).
5. **PDF**: extract text page-by-page via `pdfplumber`; call `chunk_pages()`.  
   **Text file**: read content; call `chunk_plain_text()`.
6. Batch-embed in groups of 100 via `WrapperClient.embeddings()`.
7. Insert `chunks` rows with vectors.
8. Mark ingestion `ready`, set `documents.current_ingestion_id`.
9. On any failure → mark ingestion `failed`, return 202 with warning.

### Text context flow
1. Validate `{title, text}` JSON.
2. Create `documents` row (`source_type="text"`, `original_text` stored).
3. Create `document_ingestions` row (`status="processing"`, `text_snapshot` set).
4. Call `chunk_plain_text()` (no page metadata).
5. Batch-embed → insert chunks → mark ready.
6. On failure → mark failed, return 202.

---

## Chunking Parameters

| Parameter | Value |
|-----------|-------|
| `CHUNK_SIZE` | 1000 characters |
| `CHUNK_OVERLAP` | 200 characters |
| Max embed batch | 100 chunks/request |
| Embedding model | `gemini/gemini-embedding-001` |
| Vector dimensions | 1536 (matches `chunks.embedding Vector(1536)`) |

---

## Decisions / Tradeoffs

- **Embedding dimension truncation**: `gemini/gemini-embedding-001` via the wrapper returns 3072-dim vectors, but the DB column is `Vector(1536)`. The ingestion service truncates to `embedding[:1536]`. Gemini uses Matryoshka-style embeddings, so the leading 1536 dims preserve full semantic quality. No migration needed.
- **Synchronous ingestion**: pipeline runs inside the HTTP request. Simple and correct for the current scale; can be moved to a task queue (Celery/RQ) later without changing the service interface.
- **20 MB upload cap**: enforced by reading the full file into memory before writing to disk to avoid partial writes. Suitable for typical lecture PDFs.
- **Scanned PDFs**: if pdfplumber extracts zero text, ingestion fails with a clear error message rather than silently producing zero chunks.
- **Soft delete**: `is_deleted=True` flag; chunks/ingestions remain in DB and can be purged by a separate cleanup job later.
- **page_start / page_end on plain text**: set to `None` to cleanly differentiate from PDF chunks (retrieval layer can filter accordingly).
- **No migration required**: Step 5 already created all three tables.

---

## Verification

- All 6 `/api/documents/*` routes registered (verified via `app.url_map.iter_rules()`).
- All 4 auth routes still present (`/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/me`).
- Chunking unit tests pass: `chunk_plain_text`, `chunk_pages`, empty-input edge case.
- No syntax errors in any new or modified file (verified via Pylance).
