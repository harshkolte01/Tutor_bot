# Step 5 — Document Data Model & Migrations (Phase 3 DB)

**Date:** 2026-02-28  
**Task:** Step 5 — Document Data Model and Migrations

---

## Summary

Created the three core document/RAG tables (`documents`, `document_ingestions`, `chunks`) as the first major DB expansion after the initial `users` table. Migration applies cleanly on top of `b0536757bfa6` (users). Embedding column uses `vector(1536)` to stay within pgvector's 2000-dimension ANN index limit.

---

## Files Created

| File | Purpose |
|------|---------|
| `backend/app/db/models/document.py` | `Document` SQLAlchemy model |
| `backend/app/db/models/document_ingestion.py` | `DocumentIngestion` SQLAlchemy model |
| `backend/app/db/models/chunk.py` | `Chunk` SQLAlchemy model (with `Vector(1536)`) |
| `backend/migrations/versions/f3a9c1d2e4b7_create_documents_ingestions_chunks.py` | Alembic migration |

## Files Edited

| File | Change |
|------|--------|
| `backend/app/db/models/__init__.py` | Added imports/exports for `Document`, `DocumentIngestion`, `Chunk` |
| `backend/app/__init__.py` | Added model imports in `create_app()` so Flask-Migrate detects them |

---

## DB Schema Changes

### `documents` table
| Column | Type | Notes |
|--------|------|-------|
| id | `String(36)` PK | UUID default |
| user_id | `String(36)` FK → users.id | CASCADE delete, indexed |
| title | `String(255)` | NOT NULL |
| source_type | `String(20)` | `'upload'` or `'text'` |
| filename | `String(255)` | nullable (uploads only) |
| mime_type | `String(100)` | nullable (uploads only) |
| original_text | `Text` | nullable (text documents) |
| created_at | `DateTime(tz)` | NOT NULL |
| is_deleted | `Boolean` | default false |
| current_ingestion_id | `String(36)` FK → document_ingestions.id | nullable, SET NULL on delete |

### `document_ingestions` table
| Column | Type | Notes |
|--------|------|-------|
| id | `String(36)` PK | UUID default |
| document_id | `String(36)` FK → documents.id | CASCADE, indexed |
| user_id | `String(36)` FK → users.id | CASCADE, indexed |
| source_type | `String(20)` | `'upload'` or `'text'` |
| file_path | `String(500)` | nullable (uploads) |
| text_snapshot | `Text` | nullable (versioning/audit) |
| status | `String(20)` | `'processing'` / `'ready'` / `'failed'` |
| error_message | `Text` | nullable |
| created_at | `DateTime(tz)` | NOT NULL |
| completed_at | `DateTime(tz)` | nullable |

### `chunks` table
| Column | Type | Notes |
|--------|------|-------|
| id | `BigInteger` PK | BIGSERIAL auto-increment |
| user_id | `String(36)` FK → users.id | CASCADE |
| document_id | `String(36)` FK → documents.id | CASCADE |
| ingestion_id | `String(36)` FK → document_ingestions.id | CASCADE |
| chunk_index | `Integer` | NOT NULL |
| page_start | `Integer` | nullable |
| page_end | `Integer` | nullable |
| content | `Text` | NOT NULL |
| embedding | `vector(1536)` | NOT NULL |
| created_at | `DateTime(tz)` | NOT NULL |

### Indexes & Constraints
- `uq_chunks_ingestion_chunk_index` — UNIQUE(ingestion_id, chunk_index)
- `ix_chunks_embedding` — IVFFlat cosine index on embedding (lists=100)
- `ix_chunks_user_id_ingestion_id` — btree(user_id, ingestion_id)
- `ix_chunks_user_id_document_id` — btree(user_id, document_id)
- `ix_documents_user_id` — btree(user_id) on documents
- `ix_document_ingestions_document_id` — btree(document_id)
- `ix_document_ingestions_user_id` — btree(user_id)
- `fk_documents_current_ingestion_id` — deferred circular FK (use_alter)

### Migration
- Revision: `f3a9c1d2e4b7`
- Parent: `b0536757bfa6` (create users table)
- Enables `pgvector` extension (`CREATE EXTENSION IF NOT EXISTS vector`)

---

## Decisions & Tradeoffs

1. **vector(1536) instead of vector(3072):** pgvector's IVFFlat and HNSW indexes cap at 2000 dimensions. Using 1536 (OpenAI-compatible dimension) keeps ANN indexing working out of the box.
2. **IVFFlat with lists=100:** Chosen for initial deployment; can be rebuilt as HNSW later if needed.
3. **Circular FK (documents ↔ document_ingestions):** `current_ingestion_id` uses `use_alter=True` and `post_update=True` to break the circular dependency during table creation and ORM flushes.
4. **`source_type` on both documents and document_ingestions:** Redundant but recommended in the spec for easier querying and audit without joins.
5. **Soft delete (`is_deleted`):** On documents only — ingestions/chunks cascade-delete from their parent document if hard-deleted.

---

## Verification

- Migration applied cleanly: `f3a9c1d2e4b7 (head)`
- All 4 tables verified: `users`, `documents`, `document_ingestions`, `chunks`
- All indexes confirmed present
- Foreign keys (including circular FK) confirmed
- Users table columns unchanged
- Flask backend starts without errors
