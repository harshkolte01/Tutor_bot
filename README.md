# Tutor Bot

Tutor Bot is a personal AI study workspace where a student can upload study material, ask contextual questions, and keep conversations organized by session.

## 1) What Problem This Project Solves

Students usually split their study flow across many disconnected tools:
- notes/PDF storage
- generic AI chat
- manual revision tracking

That causes context loss and low-quality answers because the AI is not grounded in the student's own material.

Tutor Bot solves this by combining:
- user-authenticated workspace isolation
- document ingestion + vector retrieval (RAG)
- chat sessions with citations from uploaded material
- per-chat document selection and out-of-context handling

## 2) Current Product Scope (Implemented vs Pending)

### Implemented (Backend + Frontend)
- Auth: register, login, refresh, me (JWT-based).
- Document ingestion:
  - upload `pdf/txt/md`
  - add plain text documents
  - ingestion status tracking
  - soft delete
  - re-ingest failed documents
- RAG retrieval:
  - pgvector similarity search on chunk embeddings
  - user-scoped and current-ingestion-only retrieval
- Chat:
  - create/list sessions
  - list messages per session
  - send message with routed model + RAG answer
  - source mapping per assistant answer
  - per-chat document pinning
  - out-of-context detection with optional general-knowledge retry
- Frontend pages:
  - landing, signup, login
  - documents workspace
  - chat workspace

### Pending / Future Scope
- Quiz APIs and quiz UI flows.
- Analytics APIs and dashboard UI.
- Production packaging and deployment hardening.

## 3) High-Level Architecture

```text
Browser (frontend static HTML/CSS/JS)
        |
        | HTTP (JWT)
        v
Flask Backend API
  - Auth routes
  - Documents routes
  - Chat routes
  - RAG services (ingestion/retrieval/answering)
  - Router services (heuristics + classifier)
        |
        | Wrapper client (/v1/chat/completions, /v1/embeddings)
        v
AI Wrapper Service

Flask Backend <-> PostgreSQL + pgvector
```

## 4) Tech Stack

### Backend
- Python, Flask
- Flask-SQLAlchemy, Flask-Migrate
- Flask-JWT-Extended
- PostgreSQL + pgvector
- requests (wrapper HTTP client)
- pdfplumber (PDF extraction)

### Frontend
- Vanilla HTML/CSS/JavaScript (no framework)
- Centralized API layer in `frontend/components/api_client.js`
- Local session storage for JWT access/refresh tokens

## 5) Repository Structure

```text
backend/
  app/
    api/                # auth, documents, chat routes
    db/models/          # SQLAlchemy models
    services/           # wrapper, rag, router
  migrations/           # Alembic migrations
frontend/
  pages/                # login/signup/documents/chat
  assets/js/            # page logic
  assets/css/           # styling
  components/           # api client + session helpers
docs/                   # persistent agent memory files
```

## 6) Local Setup

## Prerequisites
- Python 3.10+
- PostgreSQL database with `pgvector` support
- AI wrapper base URL and key

## Environment
Copy `.env.example` to `.env` and fill values.

Required backend vars:
- `DATABASE_URL`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `WRAPPER_BASE_URL`
- `WRAPPER_KEY`
- `CORS_ALLOWED_ORIGINS`

Required frontend var:
- `API_BASE_URL` (configured in `frontend/config.js`)

## Backend run
```bash
cd backend
pip install -r requirements.txt
flask db upgrade
flask run
```

## Frontend run
```bash
cd frontend
python -m http.server 5500
```

Open: `http://localhost:5500`

## 7) API Surface (Current)

### Auth
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/me`

### Documents
- `POST /api/documents/upload`
- `POST /api/documents/text`
- `GET /api/documents`
- `GET /api/documents/<doc_id>`
- `DELETE /api/documents/<doc_id>`
- `GET /api/documents/<doc_id>/ingestions/<ingestion_id>/status`
- `POST /api/documents/<doc_id>/reingest`

### Chat
- `POST /api/chat/sessions`
- `GET /api/chat/sessions`
- `GET /api/chat/sessions/<chat_id>/messages`
- `POST /api/chat/sessions/<chat_id>/messages`
- `GET /api/chat/sessions/<chat_id>/documents`
- `PUT /api/chat/sessions/<chat_id>/documents`

### Dev
- `GET /api/dev/wrapper-smoke` (JWT-protected)

## 8) Data Model Snapshot

Core tables implemented:
- `users`
- `documents`
- `document_ingestions`
- `chunks` (Vector(1536), cosine ivfflat index)
- `chats`
- `chat_messages`
- `chat_message_sources`
- `chat_documents` (association table)

## 9) Key Implementation Decisions

- All AI traffic is centralized via `backend/app/services/wrapper/client.py`.
- Chunk embeddings use `Vector(1536)`; embeddings from `gemini-embedding-001` are truncated from 3072 to 1536 for storage/query consistency.
- Retrieval always filters to the document's `current_ingestion_id` to avoid stale chunk usage.
- Ingestion is currently synchronous in request lifecycle for simplicity.
- Frontend uses a single API client module and auto-refreshes access token on `401` once.

## 10) Known Gaps / Future Reference

- Asynchronous ingestion queue (Celery/RQ) not implemented yet.
- Quiz and analytics modules exist as placeholders but have no active endpoints/logic yet.
- No automated CI pipeline configured yet.
- Production deployment configs (Docker/infra) still pending.

## 11) Useful Test Scripts

Project root scripts include:
- `test_documents.py`
- `test_chat.py`
- `test_chat_with_pdf.py`
- `test_linear_regression_pdf.py`
- `backend/test_retrieval.py`

These are integration-style scripts and assume running services/environment variables.
