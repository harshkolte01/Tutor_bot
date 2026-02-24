# Tutor Bot - Implementation Summary

Last updated: 2026-02-24
Current completed phase: Step 4 (Wrapper Client Integration)

## Scope Of This Summary

This file reflects the code currently present in the repository (not just planned scaffold files).

## Current Status By Step

| Step | Goal | Status |
|---|---|---|
| 0 | Baseline audit | Done |
| 1 | Dependency manifests and dev setup | Done |
| 2 | Database provisioning | Done |
| 3 | Auth hardening and regression check | Done |
| 4 | Wrapper client integration | Done |
| 5 | Document data model + migrations | Not implemented |
| 6 | Document ingestion API | Not implemented |
| 7 | RAG chat API | Not implemented |
| 8 | Quiz engine | Not implemented |
| 9 | Analytics | Not implemented |
| 10 | Docker / production config | Not implemented |

## Backend — All Implemented Endpoints

### Auth API

Blueprint: `/api/auth` — `backend/app/api/auth.py`

| Method | Path | Auth | Behavior |
|---|---|---|---|
| POST | `/api/auth/register` | None | Creates user; returns access + refresh JWT + user payload |
| POST | `/api/auth/login` | None | Verifies credentials; returns access + refresh JWT + user payload |
| POST | `/api/auth/refresh` | Refresh JWT | Issues new access token |
| GET | `/api/auth/me` | Access JWT | Returns current user payload |

Validation rules:
- Email + password required; password minimum 8 characters.
- Duplicate email and duplicate username rejected with 409.
- Disabled accounts blocked at login with 403.
- JWT identity is `user.id` (UUID string).
- Passwords hashed via Werkzeug.

### Dev / Internal API

Blueprint: `/api/dev` — `backend/app/api/dev.py`

| Method | Path | Auth | Behavior |
|---|---|---|---|
| GET | `/api/dev/wrapper-smoke` | Access JWT | Fires one chat call + one embedding call through wrapper; returns JSON summary |

Response shape:
```json
{
  "ok": true,
  "results": {
    "chat":      { "status": "ok", "model": "...", "reply": "..." },
    "embedding": { "status": "ok", "model": "...", "dimensions": 768 }
  }
}
```
Returns `200` when both succeed, `502` if either fails.

### Stub API Modules (Empty — Not Yet Implemented)

| File | Future blueprint |
|---|---|
| `backend/app/api/documents.py` | `/api/documents` (Phase 3) |
| `backend/app/api/chat.py` | `/api/chat` (Phase 3) |
| `backend/app/api/quizzes.py` | `/api/quizzes` (Phase 4) |
| `backend/app/api/analytics.py` | `/api/analytics` (Phase 5) |

---

## Backend — App Factory and Extensions

- `backend/app/__init__.py`
  - Loads config from `app.config.config_map`.
  - Initializes `db`, `migrate`, `jwt`.
  - Imports models for migration detection.
  - Registers `auth_bp` and `dev_bp`.
- `backend/app/extensions.py` — SQLAlchemy, Migrate, JWTManager singletons.
- `backend/app/config.py` — all config keys (see below).
- `backend/run.py` — starts Flask on `0.0.0.0:5000`.

### Config Keys

| Key | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | — | Neon PostgreSQL connection string |
| `SECRET_KEY` | `dev-secret` | Flask secret |
| `JWT_SECRET_KEY` | `dev-jwt-secret` | JWT signing key |
| `WRAPPER_BASE_URL` | `""` | AI wrapper service base URL |
| `WRAPPER_KEY` | `""` | Bearer token for wrapper |
| `WRAPPER_TIMEOUT` | `30` | Request timeout in seconds |
| `WRAPPER_MAX_RETRIES` | `3` | Retry attempts on 429/502/503/504 |
| `WRAPPER_BASE_DELAY` | `1.0` | Base backoff delay in seconds |
| `WRAPPER_DEFAULT_MODEL` | `routeway/glm-4.5-air:free` | Default chat model |
| `WRAPPER_EMBEDDING_MODEL` | `gemini/gemini-embedding-001` | Default embedding model |
| `CORS_ALLOWED_ORIGINS` | localhost:5500, 3000 | Allowed browser origins |

---

## Backend — Wrapper Service Layer

### `backend/app/services/wrapper/retry.py`

- `call_with_retry(fn, max_retries=3, base_delay=1.0)`
- Retries on HTTP 429, 502, 503, 504.
- Exponential backoff with full jitter; honours `Retry-After` header.
- Re-raises network-level `RequestException` after exhausted retries.

### `backend/app/services/wrapper/client.py`

- `WrapperError(message, status_code, upstream)` — normalised exception for all failure modes.
- `WrapperClient` — thin HTTP client:
  - `chat_completions(model, messages, temperature=0.7, max_tokens=None)` → `POST /v1/chat/completions`
  - `embeddings(model, input)` → `POST /v1/embeddings`
  - Bearer auth header on every request.
  - Configurable timeout, retries, backoff via constructor.
- `get_client()` — module-level singleton; initialised from Flask app config on first call.
  Must be called within a Flask application context.

### Stub Service Modules (Empty — Not Yet Implemented)

- `backend/app/services/rag/` — ingestion, chunking, retrieval, answering
- `backend/app/services/router/` — heuristics, classifier
- `backend/app/services/quiz/` — spec_parser, generator, validator, grading, summarizer
- `backend/app/services/analytics/` — events, metrics

---

## Backend — Database Model and Migrations

- `backend/app/db/models/user.py` — `users` table:
  - `id` (string UUID, PK)
  - `email` (unique, required)
  - `username` (unique, nullable)
  - `password_hash` (required)
  - `created_at` (timezone-aware datetime)
  - `is_active` (boolean)
- `backend/migrations/versions/b0536757bfa6_create_users_table.py` — creates `users` table.

Pending migrations (Phase 3+):
- `documents`, `document_ingestions`, `chunks` (with pgvector column)
- `chats`, `chat_messages`, `chat_message_sources`
- quiz tables
- analytics events table

---

## Frontend — Implemented

Stack: Vanilla HTML / CSS / JS (multi-page, no framework).

### Pages

| File | Purpose |
|---|---|
| `frontend/index.html` | Landing page (hero, features) |
| `frontend/pages/login.html` | Login form |
| `frontend/pages/signup.html` | Registration form |

### Components

- `frontend/components/api_client.js` — centralised HTTP client for all frontend → backend calls.
  - `register(email, password, username)`
  - `login(email, password)`
  - `refreshToken(refreshToken)`
  - `getMe(accessToken)`
  - `authedGet / authedPost / authedDelete` generic helpers.
- `frontend/components/session.js` — localStorage session management.
  - `getSession()`, `setSessionFromAuth()`, `clearSession()`, `getAccessToken()`

### Assets

- `frontend/assets/css/base.css` — global styles, `[hidden] { display: none !important }` fix.
- `frontend/assets/css/landing.css` — landing page styles.
- `frontend/assets/css/auth.css` — login/signup form styles.
- `frontend/assets/js/landing.js` — auth state display (username chip, hide guest actions when signed in).
- `frontend/assets/js/auth.js` — login + signup form handlers.

### Auth State Behaviour (Landing Page)

- Signed-in: shows username chip + Sign Out button; hides Sign In, Get Started, Create Account, I Already Have an Account.
- Signed-out: shows Sign In + Get Started; hides username chip and Sign Out.

- `frontend/pages/3_Create_Quiz.py`
- `frontend/pages/4_Take_Quiz.py`
- `frontend/pages/5_Analytics.py`

Each page checks for `access_token` and shows placeholder text for future phase implementation.

## Config And Environment

Defined in `.env.example`:

- `DATABASE_URL`
- `FLASK_ENV`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `WRAPPER_BASE_URL`
- `WRAPPER_KEY`
- `API_BASE_URL`

Backend config defaults are in `backend/app/config.py`.

## Repository Notes (Current Reality)

- `README.md` currently exists but is empty.
- `backend/requirements.txt` and `frontend/requirements.txt` are not present.
- `docker-compose.yml` is not present.

## Next Work Items

1. Add dependency manifests (`backend/requirements.txt`, `frontend/requirements.txt`).
2. Implement Phase 3 backend routes/services and connect frontend chat/document pages.
3. Expand docs with run/test commands once requirements are defined.
