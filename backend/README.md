# Backend Documentation

This document describes the implemented backend in `backend/` as of March 4, 2026.

## 1) Backend Purpose

The backend provides:
- authentication and user-scoped access control
- document ingestion and vectorization for RAG
- chat session/message APIs with citation tracking
- model routing + wrapper-mediated AI calls

## 2) Application Bootstrap

Entry points:
- `backend/run.py`
- `backend/app/__init__.py`

`create_app()` responsibilities:
- load config from environment (`app/config.py`)
- initialize extensions (`db`, `migrate`, `jwt`)
- apply CORS headers via `after_request`
- import models for migration discovery
- register blueprints:
  - `auth_bp`
  - `dev_bp`
  - `documents_bp`
  - `chat_bp`

## 3) Configuration

`app/config.py` loads `.env` and exposes:
- DB: `SQLALCHEMY_DATABASE_URI`
- Auth: `SECRET_KEY`, `JWT_SECRET_KEY`
- Wrapper: `WRAPPER_BASE_URL`, `WRAPPER_KEY`, timeout/retry settings
- Uploads: `UPLOAD_FOLDER`
- CORS: `CORS_ALLOWED_ORIGINS`

## 4) Authentication Design

Auth is JWT-based via `Flask-JWT-Extended`.

Implemented endpoints (`app/api/auth.py`):
- `POST /api/auth/register`
  - validates email/password
  - checks duplicate email/username
  - hashes password
  - returns access + refresh tokens
- `POST /api/auth/login`
  - validates credentials
  - checks `is_active`
  - returns access + refresh tokens
- `POST /api/auth/refresh`
  - requires refresh token
  - returns new access token
- `GET /api/auth/me`
  - requires access token
  - returns current user profile

Identity in JWT is `user.id`.

## 5) Database Schema (Implemented)

Migrations:
- `b0536757bfa6_create_users_table.py`
- `f3a9c1d2e4b7_create_documents_ingestions_chunks.py`
- `b68382d50595_create_chats_chat_messages_chat_message_.py`
- `8d5a35927e58_add_chat_documents_table.py`

### Tables
- `users`
  - id, email, username, password_hash, created_at, is_active
- `documents`
  - source metadata for uploads/text docs
  - `current_ingestion_id` points to latest successful ingestion
- `document_ingestions`
  - ingestion execution record with status/error
- `chunks`
  - chunk text + `Vector(1536)` embedding
  - unique `(ingestion_id, chunk_index)`
  - ivfflat cosine index on embeddings
- `chats`
  - chat session metadata per user
- `chat_messages`
  - user/assistant messages and model/router metadata
- `chat_message_sources`
  - citation links from assistant message to chunk IDs
- `chat_documents`
  - association table for per-chat pinned documents

### Scope Isolation
All protected APIs and retrieval logic enforce user-scoped filtering by `user_id`.

## 6) Wrapper Client Layer

Files:
- `app/services/wrapper/client.py`
- `app/services/wrapper/retry.py`

Rules implemented:
- backend AI calls only via wrapper endpoints:
  - `POST /v1/chat/completions`
  - `POST /v1/embeddings`
- bearer auth with `WRAPPER_KEY`
- retry on `429/502/503/504`
- timeout and network error normalization via `WrapperError`
- singleton client from Flask config (`get_client()`)

## 7) Document Ingestion Pipeline

Routes in `app/api/documents.py`:
- `POST /api/documents/upload`
- `POST /api/documents/text`
- `GET /api/documents`
- `GET /api/documents/<doc_id>`
- `DELETE /api/documents/<doc_id>`
- `GET /api/documents/<doc_id>/ingestions/<ingestion_id>/status`
- `POST /api/documents/<doc_id>/reingest`

Implementation flow (`app/services/rag/ingestion.py`):
1. Create `Document` and `DocumentIngestion(status=processing)`.
2. Extract text:
   - PDF via `pdfplumber`
   - plain text via file read / provided text
3. Chunking (`app/services/rag/chunking.py`):
   - `CHUNK_SIZE=1000`, `CHUNK_OVERLAP=200`
4. Batch embeddings (`EMBED_BATCH_SIZE=100`).
5. Truncate embedding dimensions to 1536 for DB storage consistency.
6. Persist chunk rows.
7. Mark ingestion `ready`, set `completed_at`, update `document.current_ingestion_id`.
8. On failure, mark ingestion `failed` and store error message.

Current behavior: ingestion is synchronous inside request handling.

## 8) Retrieval Engine

File: `app/services/rag/retrieval.py`

`retrieve_chunks(query_text, user_id, top_k=5, document_ids=None)`:
- embeds query via wrapper embeddings
- computes cosine distance against `chunks.embedding`
- filters:
  - `Chunk.user_id == user_id`
  - `Document.user_id == user_id`
  - `Document.is_deleted == False`
  - `Document.current_ingestion_id IS NOT NULL`
  - `Chunk.ingestion_id == Document.current_ingestion_id`
- optional filter by supplied `document_ids`
- returns top-k chunks with score, snippet, document metadata

## 9) Answer Generation and Routing

### Routing
Files:
- `app/services/router/heuristics.py`
- `app/services/router/classifier.py`

Flow:
- heuristics first (keyword rules)
- if confidence low, classify via wrapper using `gemini/gemini-2.5-flash`
- current category mapping returns gemma as default/coding/reasoning model
- fallback model for failures: flash

### Answering
File: `app/services/rag/answering.py`

`generate_answer(...)` does:
1. optional retrieval (unless `use_general_knowledge=true`)
2. builds system prompt with source snippets
3. sends chat completion through wrapper
4. model fallback chain if primary fails
5. detects `[NO_CONTEXT]` sentinel and returns `out_of_context=true`

## 10) Chat API Behavior

Routes in `app/api/chat.py`:
- `POST /api/chat/sessions`
- `GET /api/chat/sessions`
- `GET /api/chat/sessions/<chat_id>/messages`
- `POST /api/chat/sessions/<chat_id>/messages`
- `GET /api/chat/sessions/<chat_id>/documents`
- `PUT /api/chat/sessions/<chat_id>/documents`

`POST /messages` flow:
1. verify session ownership
2. persist user message
3. select model using router
4. load recent history (max 10 turns)
5. apply per-chat document filter (if any)
6. call answer generator
7. persist assistant message and `router_json`
8. persist citation rows (`chat_message_sources`)
9. update chat `updated_at` and auto-title if chat title was `New Chat`

## 11) Dev Endpoint

`GET /api/dev/wrapper-smoke` (JWT-protected):
- runs one wrapper chat request
- runs one wrapper embedding request
- returns combined health summary

## 12) Error Handling and Status Codes

Patterns implemented:
- `400` for invalid inputs
- `401/403` for auth/access state
- `404` for missing scoped resources
- `409` for conflicts (duplicate auth registration)
- `413/415` for upload constraints/type
- `503` for wrapper unavailability during chat

Wrapper errors are normalized as `WrapperError` and handled at API boundaries.

## 13) Current Constraints

- Quiz and analytics backend modules exist but are empty placeholders.
- No async worker queue for ingestion yet.
- No streaming chat responses yet.
- Full automated test suite is not yet integrated; current scripts are mostly integration/manual style.

## 14) Backend Future Roadmap

Recommended next backend milestones:
1. Implement quiz APIs/services/schema.
2. Implement analytics event tracking and metrics endpoints.
3. Move ingestion to background workers with job status API.
4. Add comprehensive pytest coverage and CI.
5. Add production observability (structured logs, tracing, health probes).
