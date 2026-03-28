# Tutor Bot

Tutor Bot is a personal AI study workspace where a student can upload study material, chat against their own documents, and generate or take quizzes inside the same authenticated workspace.

## 1) What Is Implemented

Implemented backend and frontend features:
- JWT auth with register, login, refresh, and me
- document upload for `pdf`, `txt`, and `md`
- plain-text study note ingestion
- ingestion status tracking, retry, and soft delete
- retrieval-augmented chat with citations
- per-chat document selection
- out-of-context handling with optional general-knowledge retry
- quiz generation from ready documents
- quiz scoping to all ready documents or selected documents only
- chat-to-quiz handoff using the active chat document scope
- quiz taking, scoring, answer review, and performance summary

Not implemented yet:
- analytics APIs and dashboard UI
- production packaging and deployment hardening
- async background ingestion workers

## 2) High-Level Architecture

```text
Browser (static frontend HTML/CSS/JS)
        |
        | HTTP + JWT
        v
Flask Backend API
  - auth routes
  - documents routes
  - chat routes
  - quiz routes
  - rag, router, quiz, wrapper services
        |
        | AI gateway client
        +--> Ollama for generation
        |
        +--> Wrapper service for Gemini embeddings

Flask Backend <-> PostgreSQL + pgvector
```

## 3) Tech Stack

Backend:
- Python
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-JWT-Extended
- PostgreSQL + pgvector
- `requests`
- `pdfplumber`

Frontend:
- Vanilla HTML/CSS/JavaScript
- shared API client in `frontend/components/api_client.js`
- localStorage session handling for access and refresh tokens

## 4) Repository Structure

```text
backend/
  app/
    api/                # auth, documents, chat, quizzes
    db/models/          # SQLAlchemy models
    services/           # wrapper, rag, router, quiz
  migrations/           # Alembic migrations
frontend/
  pages/                # login, signup, documents, chat, create-quiz, take-quiz
  assets/js/            # page controllers
  assets/css/           # shared styles
  components/           # api client + session helpers
docs/                   # persistent project memory for future agents
```

## 5) Current Pages

- `/index.html`
- `/pages/signup.html`
- `/pages/login.html`
- `/pages/documents.html`
- `/pages/chat.html`
- `/pages/create-quiz.html`
- `/pages/take-quiz.html`

## 6) Local Setup

### Prerequisites

- Python 3.10+
- PostgreSQL database with `pgvector`
- wrapper base URL and wrapper key for embeddings
- Ollama running locally for generation

### Environment

Copy `.env.example` to `.env` and fill in:

Backend vars:
- `DATABASE_URL`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `WRAPPER_BASE_URL`
- `WRAPPER_KEY`
- `WRAPPER_EMBEDDING_MODEL`
- `OLLAMA_BASE_URL`
- `OLLAMA_API_KEY`
- `OLLAMA_MODEL`
- `CORS_ALLOWED_ORIGINS`

Frontend config:
- `frontend/config.js`
- for local development, set `API_BASE_URL` to `http://127.0.0.1:5000` or `http://localhost:5000`

### Backend Run

```bash
cd backend
pip install -r requirements.txt
flask db upgrade
python -m flask --app run.py run
```

### Frontend Run

```bash
cd frontend
python -m http.server 5500
```

Open:
- `http://localhost:5500`

## 7) Current API Surface

Auth:
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/me`

Documents:
- `POST /api/documents/upload`
- `POST /api/documents/text`
- `GET /api/documents`
- `GET /api/documents/<doc_id>`
- `DELETE /api/documents/<doc_id>`
- `GET /api/documents/<doc_id>/ingestions/<ingestion_id>/status`
- `POST /api/documents/<doc_id>/reingest`

Chat:
- `POST /api/chat/sessions`
- `GET /api/chat/sessions`
- `GET /api/chat/sessions/<chat_id>/messages`
- `POST /api/chat/sessions/<chat_id>/messages`
- `GET /api/chat/sessions/<chat_id>/documents`
- `PUT /api/chat/sessions/<chat_id>/documents`

Quizzes:
- `POST /api/quizzes`
- `GET /api/quizzes`
- `GET /api/quizzes/<quiz_id>`
- `GET /api/quizzes/<quiz_id>/questions`
- `POST /api/quizzes/<quiz_id>/attempts/start`
- `POST /api/quizzes/<quiz_id>/attempts/<attempt_id>/submit`
- `GET /api/quizzes/attempts/<attempt_id>`

Dev:
- `GET /api/dev/wrapper-smoke`

## 8) Data Model Snapshot

Implemented tables:
- `users`
- `documents`
- `document_ingestions`
- `chunks`
- `chats`
- `chat_messages`
- `chat_message_sources`
- `chat_documents`
- `quizzes`
- `quiz_questions`
- `quiz_question_sources`
- `quiz_attempts`
- `quiz_attempt_answers`

## 9) Key Implementation Notes

- All AI traffic goes through `backend/app/services/wrapper/client.py`.
- Chat, quiz generation, and quiz summaries use Ollama.
- Document ingestion and retrieval embeddings stay on the wrapper.
- Retrieval is always user-scoped and limited to each document's `current_ingestion_id`.
- Chat sessions can be pinned to selected documents only.
- Quiz generation can use all ready documents or selected `document_ids`.
- The create quiz page also supports chat-scoped preselection through query params.
- The frontend uses only `frontend/components/api_client.js` for HTTP.
- Access tokens are auto-refreshed once on `401`.

## 10) Useful Test Scripts

Project root test scripts:
- `test_documents.py`
- `test_chat.py`
- `test_chat_with_pdf.py`
- `test_linear_regression_pdf.py`
- `test_quizzes.py`
- `test_quiz_attempts.py`
- `test_live_backend_quiz_flow.py`

These are integration-style checks and assume the environment is configured.

## 11) Current Gaps

- analytics feature set is still pending
- no async ingestion queue yet
- no CI pipeline yet
- no production deployment docs or containers yet
