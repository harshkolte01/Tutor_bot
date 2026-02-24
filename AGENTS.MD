# AGENTS.MD - Tutor Bot Agent Operating Guide

Every agent working in this repository must read this file before starting any task.

After completing any implementation task, create a new file in `docs/`:

`YYYY-MM-DD_<short_description>.md`

Example: `2026-02-24_phase3_documents_api.md`

This file is persistent project memory for future agents.

---

## 1) Project Summary

Tutor Bot is a personal AI study workspace.

Stack:
- Backend API: Flask (Python), Flask-JWT-Extended
- Database: Neon PostgreSQL + SQLAlchemy + Alembic (Flask-Migrate)
- Frontend: Vanilla HTML/CSS/JS multi-page app
- LLM integration: external wrapper service (`WRAPPER_BASE_URL`) with OpenAI-compatible routes
- Vector search: `pgvector` in Neon

---

## 2) Current Implementation Snapshot (as of 2026-02-24)

Completed:
- Phase 1: scaffold
- Phase 2: auth + user model + JWT

Implemented backend:
- `backend/app/api/auth.py` endpoints:
  - `POST /api/auth/register`
  - `POST /api/auth/login`
  - `POST /api/auth/refresh`
  - `GET /api/auth/me`
- `backend/app/db/models/user.py`
- migration: `backend/migrations/versions/b0536757bfa6_create_users_table.py`

Implemented frontend:
- `frontend/index.html` (landing page)
- `frontend/pages/login.html`
- `frontend/pages/signup.html`
- `frontend/components/api_client.js` (centralized frontend HTTP client)

Pending (stub/empty modules):
- Phase 3: documents + RAG chat
- Phase 4: quiz engine
- Phase 5: analytics
- Phase 6: docker/production packaging

Read `plan.md` for step-by-step execution order.

---

## 3) Mandatory Start Checklist

Before writing code, do all of the following:

1. Read this file (`AGENTS.MD`).
2. Read all files in `docs/` sorted newest-first by filename.
3. Read `plan.md` and identify the exact step being implemented.
4. Confirm current code reality in backend/frontend files (do not trust old assumptions).
5. Keep task scope limited to the assigned step.

---

## 4) Architecture Rules (Do Not Break)

1. Frontend must call backend only via `frontend/components/api_client.js`.
2. Backend API routes must not call providers directly.
3. All LLM calls must go through `backend/app/services/wrapper/client.py`.
4. All DB access must use SQLAlchemy models in `backend/app/db/models/`.
5. Raw SQL is allowed only in migrations.
6. JWT identity must be `user.id` (UUID string).
7. Every protected route must scope data by `get_jwt_identity()`.
8. New models must be exported in `backend/app/db/models/__init__.py`.
9. New blueprints/models must be properly registered in `backend/app/__init__.py`.

---

## 5) Database and Migration Rules

Never update schema by hand in Neon.

Use:

```bash
cd backend
flask db migrate -m "clear description"
flask db upgrade
```

Migration sequence target:
1. Existing (done): `users`
2. Phase 3: `documents`, `document_ingestions`, `chunks` (+ pgvector)
3. Phase 3 chat: `chats`, `chat_messages`, `chat_message_sources`
4. Phase 4: quiz tables
5. Phase 5: analytics events table

If a migration is changed, explain exactly why in the docs memory file.

---

## 6) Environment Variables

Required backend vars:
- `DATABASE_URL`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `WRAPPER_BASE_URL`
- `WRAPPER_KEY`
- `CORS_ALLOWED_ORIGINS` (for browser frontend API calls)

Required frontend var:
- `API_BASE_URL` (default `http://localhost:5000`)

Rules:
- Never commit real secrets.
- Keep `.env.example` aligned with required vars.
- Wrapper key stays in backend env only.

---

## 7) Expected File Ownership by Layer

Backend API routes:
- `backend/app/api/auth.py`
- `backend/app/api/documents.py`
- `backend/app/api/chat.py`
- `backend/app/api/quizzes.py`
- `backend/app/api/analytics.py`

Backend service layer:
- `backend/app/services/wrapper/`
- `backend/app/services/rag/`
- `backend/app/services/router/`
- `backend/app/services/quiz/`
- `backend/app/services/analytics/`

Backend models:
- `backend/app/db/models/`

Frontend:
- `frontend/components/api_client.js`
- `frontend/components/session.js`
- `frontend/index.html`
- `frontend/pages/*`
- `frontend/assets/*`

---

## 8) Definition Of Done For Any Agent Task

A task is not complete until all are true:

1. Requested implementation is finished.
2. Existing auth flow still works.
3. New/changed endpoints run correctly.
4. New migrations apply cleanly (if schema changed).
5. Frontend still uses only `components/api_client.js` for HTTP.
6. A new docs memory file is added in `docs/`.
7. Docs memory file includes:
   - task summary
   - files created/edited
   - endpoints added/changed
   - DB schema/migration changes
   - decisions/tradeoffs

---

## 9) Testing Expectations

Minimum checks after changes:

1. Backend starts:
```bash
cd backend
flask run
```

2. Frontend starts:
```bash
cd frontend
python -m http.server 5500
```

3. Auth regression checks:
- register
- login
- refresh
- me

4. Validate only user-scoped data is returned on protected endpoints.

---

## 10) Wrapper Usage Policy

Tutor app talks only to wrapper endpoints:
- `POST /v1/chat/completions`
- `POST /v1/embeddings`

Operational expectations:
- retries for 429/502/503/504
- timeout handling
- normalized error handling in service layer

Model routing policy (target):
- default tutor: `routeway/glm-4.5-air:free`
- hard reasoning: `routeway/deepseek-r1:free`
- coding tasks: `routeway/devstral-2512:free`
- classification/fast tasks: `gemini/gemini-2.5-flash`
- embeddings: `gemini/gemini-embedding-001`

---

## 11) Common Mistakes To Avoid

- Do not bypass `api_client.js` from frontend pages/scripts.
- Do not call providers directly from Flask routes.
- Do not skip user scoping (`user_id`) in queries.
- Do not delete stub pages/modules for future phases.
- Do not skip docs memory file creation.
- Do not rely only on planned docs when code disagrees. Code is source of truth.

---

## 12) Handoff Template (Copy/Paste)

Use this when assigning one step to another agent:

```text
Read AGENTS.MD, docs/* (newest first), and plan.md.
Implement only Step <N>.
Constraints:
- preserve auth behavior
- use SQLAlchemy models and Flask-Migrate for schema changes
- frontend HTTP only via frontend/components/api_client.js
- backend LLM calls only via backend/app/services/wrapper/client.py
After completion:
- run relevant checks
- create docs/YYYY-MM-DD_step<N>_<short_desc>.md
- list changed files, migrations, and endpoints
```
