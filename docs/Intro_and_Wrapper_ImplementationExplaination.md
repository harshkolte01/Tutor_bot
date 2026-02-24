# Intro and Wrapper Implementation Explanation

Date: 2026-02-24
Audience: Beginners (no backend experience needed)

## 1) What this project is

Tutor Bot is a study app with two main parts:

1. Frontend (what user sees in browser): HTML/CSS/JS pages
2. Backend (server logic): Flask API + PostgreSQL database

The backend handles:
- user signup/login
- token-based auth (JWT)
- calling an external AI wrapper service for chat and embeddings

Right now, auth and wrapper foundation are implemented. Documents, chat sessions, quizzes, and analytics are still planned for later phases.

## 2) Current backend status (simple view)

Implemented now:
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/me`
- `GET /api/dev/wrapper-smoke` (internal test endpoint for wrapper)

Not implemented yet:
- `/api/documents/*`
- `/api/chat/*`
- `/api/quizzes/*`
- `/api/analytics/*`

## 3) High-level architecture

### Big-picture flow

```text
Browser (frontend pages)
   |
   | calls backend only through frontend/components/api_client.js
   v
Flask Backend API
   |
   +--> Auth routes --> User model --> PostgreSQL (Neon)
   |
   +--> Dev smoke route --> WrapperClient --> Wrapper Service --> AI providers
```

### Why this architecture

- Clear separation of responsibilities:
  - frontend only handles UI
  - backend handles security, auth, DB, and AI calls
- Safer key management:
  - wrapper key stays in backend env only
- Easier maintenance:
  - one wrapper client module used by all future AI features

## 4) Backend folder and file explanation

### Core app setup

- `backend/run.py`
  - starts Flask app on `0.0.0.0:5000`
- `backend/app/__init__.py`
  - app factory (`create_app`)
  - loads config
  - initializes extensions (`db`, `migrate`, `jwt`)
  - adds CORS headers for allowed frontend origins
  - registers blueprints (`auth_bp`, `dev_bp`)
- `backend/app/config.py`
  - reads environment variables
  - stores DB, JWT, wrapper, and CORS settings
- `backend/app/extensions.py`
  - creates shared singletons:
    - `SQLAlchemy`
    - `Migrate`
    - `JWTManager`

### Auth and API routes

- `backend/app/api/auth.py`
  - register/login/refresh/me endpoints
  - validates input and credentials
  - returns JWT tokens and user info
- `backend/app/api/dev.py`
  - wrapper smoke endpoint
  - makes one chat call and one embedding call
  - returns `200` if both succeed, else `502`

### Database layer

- `backend/app/db/models/user.py`
  - `User` SQLAlchemy model
  - fields: `id`, `email`, `username`, `password_hash`, `created_at`, `is_active`
- `backend/migrations/versions/b0536757bfa6_create_users_table.py`
  - Alembic migration that creates `users` table

### Wrapper service layer

- `backend/app/services/wrapper/client.py`
  - central HTTP client for AI wrapper
  - methods:
    - `chat_completions(...)`
    - `embeddings(...)`
  - normalizes failures into `WrapperError`
  - provides `get_client()` singleton (reuse one client instance)
- `backend/app/services/wrapper/retry.py`
  - retry helper for transient failures
  - retries on: `429`, `502`, `503`, `504`
  - uses exponential backoff with jitter
  - respects `Retry-After` header (important for rate limits)

## 5) Auth flow (how it works)

### Register flow (`POST /api/auth/register`)

```text
Client sends email/password/username
   -> backend validates input
   -> checks duplicate email/username in DB
   -> hashes password
   -> saves user row in users table
   -> creates access token + refresh token
   -> returns tokens + user payload
```

### Login flow (`POST /api/auth/login`)

```text
Client sends email/password
   -> backend finds user by email
   -> verifies hashed password
   -> checks user is active
   -> returns new access + refresh tokens
```

### Refresh flow (`POST /api/auth/refresh`)

```text
Client sends refresh token in Authorization header
   -> backend verifies refresh token
   -> issues new access token
```

### Me flow (`GET /api/auth/me`)

```text
Client sends access token
   -> backend reads JWT identity (user.id)
   -> fetches user from DB
   -> returns current user profile
```

## 6) Wrapper flow (important foundation)

The backend must never call AI providers directly. It calls only the wrapper service.

### Smoke endpoint flow (`GET /api/dev/wrapper-smoke`)

```text
1) Request hits /api/dev/wrapper-smoke (JWT required)
2) Route calls get_client() from wrapper/client.py
3) Client sends chat request to POST /v1/chat/completions on wrapper
4) Client sends embeddings request to POST /v1/embeddings on wrapper
5) Retry helper handles transient failures (429/502/503/504)
6) Route returns combined result JSON:
   - ok: true if both calls succeeded
   - results.chat + results.embedding details
```

### Sequence diagram (text)

```text
Frontend/Test Caller
   -> Flask /api/dev/wrapper-smoke
      -> WrapperClient.chat_completions()
         -> call_with_retry()
            -> Wrapper /v1/chat/completions
      -> WrapperClient.embeddings()
         -> call_with_retry()
            -> Wrapper /v1/embeddings
   <- Flask returns summary JSON
```

## 7) Why wrapper client was implemented this way

### Problem it solves

If every route wrote its own AI HTTP call, code would become inconsistent and error-prone.

### Chosen design

One shared wrapper client module with:
- shared auth header setup (`Bearer WRAPPER_KEY`)
- shared timeout and retry behavior
- shared error format (`WrapperError`)
- shared config from Flask app config

### Benefits

- easier debugging
- consistent error handling
- easier future upgrades (change once, affect all AI calls)
- safer architecture rule enforcement

## 8) Error handling behavior (simple)

`WrapperClient` converts many failure types into one app-level error: `WrapperError`.

Examples:
- timeout -> `WrapperError(..., status_code=None, upstream="timeout")`
- connection issue -> `WrapperError(..., status_code=None, upstream=<message>)`
- wrapper HTTP 4xx/5xx -> `WrapperError(..., status_code=<upstream status>, upstream=<body>)`
- invalid JSON from wrapper -> `WrapperError` with raw response text

This gives API routes one consistent way to handle wrapper failures.

## 9) Environment variables used by backend

Required core vars:
- `DATABASE_URL` (PostgreSQL URL)
- `SECRET_KEY` (Flask secret)
- `JWT_SECRET_KEY` (JWT signing key)
- `WRAPPER_BASE_URL` (wrapper base URL)
- `WRAPPER_KEY` (wrapper auth token)
- `CORS_ALLOWED_ORIGINS` (allowed browser origins)

Useful wrapper tuning vars:
- `WRAPPER_TIMEOUT` (seconds)
- `WRAPPER_MAX_RETRIES`
- `WRAPPER_BASE_DELAY` (seconds)
- `WRAPPER_DEFAULT_MODEL`
- `WRAPPER_EMBEDDING_MODEL`

## 10) Libraries used (short beginner explanation)

- Flask:
  - web framework to build API endpoints
- Flask-SQLAlchemy:
  - ORM layer (write Python models instead of raw SQL in app code)
- Flask-Migrate (Alembic):
  - database schema versioning and migrations
- Flask-JWT-Extended:
  - JWT token creation and protected route decorators
- Werkzeug security:
  - password hashing and password verification helpers
- requests:
  - HTTP client used to call wrapper service
- python-dotenv:
  - loads `.env` variables into app config
- PostgreSQL (Neon):
  - main relational database

## 11) Quick run and check (for beginners)

### Backend start

```bash
cd backend
flask run
```

### Frontend start

```bash
cd frontend
python -m http.server 5500
```

### Basic auth checks

1. Register user
2. Login
3. Refresh token
4. Get profile (`/api/auth/me`)

### Wrapper smoke check

1. Login and get access token
2. Call `GET /api/dev/wrapper-smoke` with `Authorization: Bearer <access_token>`
3. If both wrapper calls work, response shows `"ok": true`

## 12) What comes next in project roadmap

Planned next major backend work:
- documents upload + ingestion + embeddings storage
- RAG retrieval + chat sessions with citations
- quiz generation/taking/grading
- analytics events and metrics

These modules already exist as files but are currently empty placeholders.

## 13) Final takeaway for new developers

If you are new, remember this simple rule:

1. Frontend talks only to backend API.
2. Backend talks to DB using SQLAlchemy models.
3. Backend talks to AI only through `services/wrapper/client.py`.

That rule keeps the system clean, secure, and easier to scale.

