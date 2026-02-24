# Tutor Bot - Implementation Summary

Last updated: 2026-02-23
Current completed phase: Phase 2 (Auth + User model + JWT)

## Scope Of This Summary

This file reflects the code currently present in the repository (not just planned scaffold files).

## Current Status By Phase

| Phase | Goal | Status |
|---|---|---|
| 1 | Project scaffold | Done |
| 2 | Auth + user model + JWT | Done |
| 3 | Documents + RAG chat | Not implemented (stub files only) |
| 4 | Quiz generation/taking/grading | Not implemented (stub files only) |
| 5 | Analytics | Not implemented (stub files only) |
| 6 | Docker/production config | Not implemented |

## Backend (Implemented)

### App Factory And Extensions

- `backend/app/__init__.py`
  - Loads config from `app.config.config_map`.
  - Initializes `db`, `migrate`, and `jwt`.
  - Imports models for migration detection.
  - Registers only `auth_bp`.
- `backend/app/extensions.py`
  - Defines singleton extension objects: SQLAlchemy, Migrate, JWTManager.
- `backend/run.py`
  - Starts Flask app on `0.0.0.0:5000`.

### Auth API

Blueprint: `/api/auth` in `backend/app/api/auth.py`.

Implemented endpoints:

| Method | Path | Behavior |
|---|---|---|
| POST | `/api/auth/register` | Creates user, returns access+refresh JWT and user payload |
| POST | `/api/auth/login` | Verifies credentials, returns access+refresh JWT and user payload |
| POST | `/api/auth/refresh` | Requires refresh token, returns new access token |
| GET | `/api/auth/me` | Requires access token, returns current user payload |

Validation and auth behavior implemented:

- Email/password required for register/login.
- Password minimum length 8 on register.
- Duplicate email/username checks.
- Disabled accounts blocked on login.
- JWT identity is the user ID string.
- Password hashing via Werkzeug helpers.

### Database Model And Migration

- `backend/app/db/models/user.py` defines `users` model:
  - `id` (string UUID primary key)
  - `email` (unique, required)
  - `username` (unique, nullable)
  - `password_hash` (required)
  - `created_at` (timezone-aware datetime, required)
  - `is_active` (boolean, required)
- `backend/migrations/versions/b0536757bfa6_create_users_table.py` creates the `users` table.

## Backend (Not Yet Implemented)

These files currently exist but are empty (stub placeholders):

- API: `backend/app/api/chat.py`, `backend/app/api/documents.py`, `backend/app/api/quizzes.py`, `backend/app/api/analytics.py`
- Wrapper services: `backend/app/services/wrapper/client.py`, `backend/app/services/wrapper/retry.py`
- RAG services: `backend/app/services/rag/ingestion.py`, `backend/app/services/rag/chunking.py`, `backend/app/services/rag/retrieval.py`, `backend/app/services/rag/answering.py`
- Router services: `backend/app/services/router/heuristics.py`, `backend/app/services/router/classifier.py`
- Quiz services: `backend/app/services/quiz/spec_parser.py`, `backend/app/services/quiz/generator.py`, `backend/app/services/quiz/validator.py`, `backend/app/services/quiz/grading.py`, `backend/app/services/quiz/summarizer.py`
- Analytics services: `backend/app/services/analytics/events.py`, `backend/app/services/analytics/metrics.py`

## Frontend (Implemented)

### Working Auth Flow

- `frontend/components/api_client.py`
  - Centralized HTTP client for all frontend->backend calls.
  - Implements `register`, `login`, `refresh_token`, `get_me`.
  - Includes generic authenticated helpers: `authed_get`, `authed_post`, `authed_delete`.
- `frontend/pages/0_Login.py`
  - Login and register forms.
  - Stores auth state in `st.session_state`:
    - `access_token`
    - `refresh_token`
    - `user`
- `frontend/Home.py`
  - Requires auth token before showing dashboard.
  - Provides sign-out behavior by clearing session auth keys.

### Stub Pages With Auth Guard

- `frontend/pages/1_Chat_Tutor.py`
- `frontend/pages/2_Upload_Documents.py`
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
