# Tutor Bot - Master Implementation Plan (Agent-by-Agent)

Last updated: 2026-02-24
Source reference: `t.txt` + current repository state

## 1. Purpose

This plan is written so you can assign one step at a time to different agents.
Each step has:
- dependencies
- exact files to touch
- environment variable updates
- database updates and migration timing
- API and frontend work
- definition of done

## 2. Current Baseline (as of 2026-02-24)

Already implemented in repo:
- Phase 1 scaffold: done
- Phase 2 auth + user model + JWT: done
- Auth endpoints working: `/api/auth/register`, `/api/auth/login`, `/api/auth/refresh`, `/api/auth/me`
- Frontend migrated from Streamlit to vanilla HTML/CSS/JS (landing + login + signup)
- Frontend API contract centralized in `frontend/components/api_client.js`

Pending:
- Phase 3 documents + RAG chat
- Phase 4 quiz generation and taking
- Phase 5 analytics
- Phase 6 docker/production setup

## 3. Non-Negotiable Rules

1. Frontend must call only Flask backend (`frontend/components/api_client.js`).
2. Backend API must call LLM only through `backend/app/services/wrapper/client.py`.
3. DB access must use SQLAlchemy models (raw SQL only in migrations).
4. JWT identity must be `user.id`.
5. DB schema changes only via Flask-Migrate.
6. Every completed agent task must create a new docs file: `docs/YYYY-MM-DD_<short_description>.md`.
7. Never commit secrets from `.env`.

## 4. Recommended Execution Calendar

Suggested timeline starting Tuesday, 2026-02-24:

- Day 1: Steps 0-2
- Day 2: Steps 3-4
- Day 3: Steps 5-6
- Day 4: Steps 7-8
- Day 5: Steps 9-10
- Day 6: Steps 11-12
- Day 7: Steps 13-14
- Day 8: Steps 15-16

If working with multiple agents in parallel:
- backend-only and frontend-only steps can overlap after dependencies are satisfied
- never run two agents that edit the same files at the same time

## 5. Step-by-Step Breakdown

---

## Step 0 - Baseline Audit and Task Branch Setup

Status: Recommended before all work
Estimated time: 30-60 minutes
Owner: Lead agent
Depends on: none

### Actions
1. Read `AGENTS.MD` and all files in `docs/` newest-first.
2. Confirm current phase status against code.
3. Create a branch for the step (example: `step0-audit`).
4. Capture current run status for backend and frontend.

### Commands
```bash
cd backend
flask run

cd ../frontend
python -m http.server 5500
```

### Definition of done
- Baseline validated.
- Branch created.
- Notes captured in docs file.

---

## Step 1 - Dependency Manifests and Dev Setup

Status in repo: partially missing (backend requirements file absent)
Estimated time: 1-2 hours
Owner: Backend + frontend setup agent
Depends on: Step 0

### Environment updates (now)
Update `.env.example` and local `.env` as needed:
- `DATABASE_URL`
- `FLASK_ENV`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `WRAPPER_BASE_URL`
- `WRAPPER_KEY`
- `API_BASE_URL`
- `CORS_ALLOWED_ORIGINS`

### Files to create/update
- `backend/requirements.txt` (create)
- `README.md` run instructions (update)
- `frontend/README.md` (verify run/config instructions stay current)

### Package targets
Backend minimum:
- Flask
- Flask-SQLAlchemy
- Flask-Migrate
- Flask-JWT-Extended
- psycopg2-binary
- python-dotenv
- requests
- pgvector (python package if needed for ORM type mapping)

Frontend minimum:
- static files only (`frontend/` HTML/CSS/JS)
- no required Python package manifest for runtime
- local static serving via `python -m http.server` (or equivalent static server)

### Definition of done
- Fresh environment install works.
- Backend and frontend start without dependency errors.

---

## Step 2 - Database Provisioning and Extension Setup

Status in repo: Neon DB connected for users table only
Estimated time: 1-2 hours
Owner: Backend infra agent
Depends on: Step 1

### Database to use
Primary app database: Neon PostgreSQL (`tutorbot_db`)

### Database actions (timing)
Do this before Phase 3 models:
1. Confirm Neon connection string in `DATABASE_URL`.
2. Ensure `sslmode=require` in connection string.
3. Enable `pgvector` extension in app DB migration.
4. Validate existing `users` table still accessible.

### Migration policy
- Never edit existing migration manually unless absolutely necessary.
- Create new migration for pgvector enablement if not present.

### Definition of done
- `flask db upgrade` succeeds.
- `users` table intact.
- `vector` type available for upcoming chunk embeddings.

---

## Step 3 - Auth Hardening and Regression Check

Status in repo: implemented, needs regression verification only
Estimated time: 1-2 hours
Owner: Backend QA agent
Depends on: Step 2

### Actions
1. Re-test all auth endpoints.
2. Add/confirm tests for:
   - duplicate email
   - duplicate username
   - weak password
   - disabled account login
   - refresh token flow
3. Verify JWT identity is `user.id` everywhere.

### Endpoints
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/me`

### Definition of done
- Auth still works after dependency/DB setup changes.
- No regressions before Phase 3 starts.

---

## Step 4 - Wrapper Client Integration (Foundation for All AI Calls)

Status in repo: pending (stub files)
Estimated time: 3-4 hours
Owner: Backend services agent
Depends on: Step 3

### Environment updates (required now)
- `WRAPPER_BASE_URL` (example: `https://ai-api-wrapper-tutor-bot.onrender.com`)
- `WRAPPER_KEY` (store in backend env only)

### Files to implement
- `backend/app/services/wrapper/client.py`
- `backend/app/services/wrapper/retry.py`
- `backend/app/config.py` (if timeout/retry configs are added)

### Required wrapper methods
1. `chat_completions(model, messages, temperature, max_tokens)`
2. `embeddings(model, input)`

### Required behavior
- send bearer auth with `WRAPPER_KEY`
- configurable timeout
- retry for 429, 502, 503, 504 with exponential backoff
- normalize errors for API layer

### Suggested smoke endpoint
Add internal health endpoint (protected or dev-only) to test both:
- 1 chat call
- 1 embedding call

### Definition of done
- Wrapper client works independently.
- No direct Routeway/Gemini calls from API routes.

---

## Step 5 - Document Data Model and Migrations (Phase 3 DB)

Status in repo: pending
Estimated time: 3-4 hours
Owner: Backend DB agent
Depends on: Step 4

### Database update timing
This is the first major DB expansion after users.
Apply migration before implementing document APIs.

### New models/tables
1. `documents`
2. `document_ingestions`
3. `chunks` (with vector embedding column)

### Required columns
`documents`:
- `id` UUID PK
- `user_id` FK users
- `title`
- `created_at`
- `is_deleted`
- `current_ingestion_id` nullable FK

`document_ingestions`:
- `id` UUID PK
- `document_id` FK
- `user_id` FK
- `file_path`
- `status` (`processing|ready|failed`)
- `error_message`
- `created_at`
- `completed_at`

`chunks`:
- `id` BIGSERIAL PK
- `user_id` FK
- `document_id` FK
- `ingestion_id` FK
- `chunk_index`
- `page_start`
- `page_end`
- `content`
- `embedding` vector(3072)
- `created_at`

### Indexes/constraints
- unique `(ingestion_id, chunk_index)`
- vector index on `chunks.embedding` (cosine)
- btree index `(user_id, ingestion_id)`

### Files to update
- `backend/app/db/models/` (new files)
- `backend/app/db/models/__init__.py`
- `backend/app/__init__.py` (model imports)
- new migration under `backend/migrations/versions/`

### Definition of done
- Migration applied successfully.
- Tables and indexes verified.

---

## Step 6 - Documents API + Ingestion Pipeline

Status in repo: pending
Estimated time: 5-7 hours
Owner: Backend document agent
Depends on: Step 5

### API routes to implement
In `backend/app/api/documents.py`:
1. `POST /api/documents/upload`
2. `GET /api/documents`
3. `GET /api/documents/<id>`
4. `DELETE /api/documents/<id>` (soft delete)
5. `GET /api/documents/<id>/ingestions/<ingestion_id>/status`

### Service files
- `backend/app/services/rag/ingestion.py`
- `backend/app/services/rag/chunking.py`
- use `backend/app/services/wrapper/client.py` for embeddings

### Processing sequence
1. Receive file upload.
2. Persist file path.
3. Create ingestion row (`processing`).
4. Extract text.
5. Chunk text.
6. Batch embeddings (max 100 input chunks/request).
7. Insert chunk rows with vectors.
8. Mark ingestion `ready` and update `documents.current_ingestion_id`.
9. On error mark ingestion `failed` with reason.

### Definition of done
- User can upload document and see ingestion status flow.
- Chunks and vectors saved for the latest ingestion.

---

## Step 7 - Retrieval Engine and Source Tracing

Status in repo: pending
Estimated time: 3-5 hours
Owner: Backend RAG agent
Depends on: Step 6

### Files
- `backend/app/services/rag/retrieval.py`

### Retrieval requirements
1. Embed user query using wrapper embeddings model.
2. Query `chunks` by vector similarity.
3. Filter by `user_id` and latest `current_ingestion_id`.
4. Return top-k chunks with scores and metadata.

### Output contract
Return a structured payload including:
- chunk ids
- document id
- snippet text
- similarity score

### Definition of done
- Retrieval returns relevant chunks and can be attached as citations.

---

## Step 8 - Chat API with Router + RAG Answering

Status in repo: pending
Estimated time: 6-8 hours
Owner: Backend chat agent
Depends on: Step 7

### API routes
In `backend/app/api/chat.py`:
1. `POST /api/chat/sessions`
2. `GET /api/chat/sessions`
3. `GET /api/chat/sessions/<chat_id>/messages`
4. `POST /api/chat/sessions/<chat_id>/messages`

### New DB tables (migration timing)
Run migration before coding route logic:
1. `chats`
2. `chat_messages`
3. `chat_message_sources`

### Service files
- `backend/app/services/router/heuristics.py`
- `backend/app/services/router/classifier.py`
- `backend/app/services/rag/answering.py`

### Router model policy
- default tutor: `routeway/glm-4.5-air:free`
- hard reasoning: `routeway/deepseek-r1:free`
- coding tasks: `routeway/devstral-2512:free`
- classification: `gemini/gemini-2.5-flash`

### Flow per user message
1. save user message
2. run heuristics/classifier to select model
3. retrieve relevant chunks
4. generate answer via wrapper chat completions
5. save assistant message + selected model + router json
6. save source chunk mapping for traceability

### Definition of done
- End-to-end chat with citations works for authenticated user.

---

## Step 9 - Frontend Documents and Chat Pages (Phase 3 UI)

Status in repo: pending (frontend base migrated; Phase 3 pages not built yet)
Estimated time: 6-8 hours
Owner: Frontend web agent (HTML/CSS/JS)
Depends on: Steps 6 and 8

### Files to update
- `frontend/components/api_client.js` (add new endpoints)
- `frontend/pages/chat.html`
- `frontend/pages/documents.html`
- `frontend/assets/js/chat.js`
- `frontend/assets/js/documents.js`

### UI tasks
Upload Documents page:
- file uploader
- upload progress/status refresh
- list documents and latest ingestion status

Chat Tutor page:
- create/select chat session
- message history
- ask question form
- show answer with citation list
- show model used (optional debug)

### Rule check
No direct wrapper calls from frontend. All requests must go through backend endpoints.

### Definition of done
- Phase 3 usable from UI without manual API calls.

---

## Step 10 - Quiz Data Model and Migrations (Phase 4 DB)

Status in repo: pending
Estimated time: 3-4 hours
Owner: Backend DB agent
Depends on: Step 9

### New tables
1. `quizzes`
2. `quiz_questions`
3. `quiz_question_sources`
4. `quiz_attempts`
5. `quiz_attempt_answers`

### Migration timing
Create and apply migration before quiz APIs.

### Core fields
`quizzes`:
- `id`, `user_id`, `title`, `instructions`, `spec_json`, `total_marks`, `time_limit_sec`, `model_used`, `created_at`

`quiz_questions`:
- `id`, `quiz_id`, `question_index`, `type`, `question_text`, `options_json`, `correct_json`, `marks`, `explanation`
- unique `(quiz_id, question_index)`

`quiz_attempts`:
- `id`, `quiz_id`, `user_id`, `started_at`, `submitted_at`, `time_spent_sec`, `score`, `total_marks`, `summary_json`

`quiz_attempt_answers`:
- `id`, `attempt_id`, `question_id`, `chosen_json`, `is_correct`, `marks_awarded`
- unique `(attempt_id, question_id)`

### Definition of done
- Quiz tables created with constraints and verified.

---

## Step 11 - Quiz Generation and Validation APIs

Status in repo: pending
Estimated time: 6-8 hours
Owner: Backend quiz agent
Depends on: Step 10

### API routes
In `backend/app/api/quizzes.py`:
1. `POST /api/quizzes`
2. `GET /api/quizzes`
3. `GET /api/quizzes/<quiz_id>`
4. `GET /api/quizzes/<quiz_id>/questions`

### Service files
- `backend/app/services/quiz/spec_parser.py`
- `backend/app/services/quiz/generator.py`
- `backend/app/services/quiz/validator.py`

### Generation flow
1. parse user quiz request
2. retrieve relevant chunks from latest ingestion
3. generate structured quiz via wrapper chat
4. validate schema/marks/correct options
5. repair loop if invalid
6. store quiz + questions + citations

### Definition of done
- User can generate and fetch quiz data from API.

---

## Step 12 - Quiz Taking, Grading, and Attempt Summary APIs

Status in repo: pending
Estimated time: 4-6 hours
Owner: Backend quiz agent
Depends on: Step 11

### API routes
1. `POST /api/quizzes/<quiz_id>/attempts/start`
2. `POST /api/quizzes/<quiz_id>/attempts/<attempt_id>/submit`
3. `GET /api/quizzes/attempts/<attempt_id>`

### Service files
- `backend/app/services/quiz/grading.py`
- `backend/app/services/quiz/summarizer.py`

### Grading flow
1. accept answers
2. deterministic scoring from stored `correct_json`
3. save attempt + per-question answers
4. call wrapper (flash model) for performance summary
5. save summary in `summary_json`

### Definition of done
- Attempt submission returns score and stored summary.

---

## Step 13 - Frontend Quiz Pages (Create + Take)

Status in repo: pending (frontend base migrated; quiz pages not built yet)
Estimated time: 6-8 hours
Owner: Frontend web agent (HTML/CSS/JS)
Depends on: Steps 11 and 12

### Files
- `frontend/components/api_client.js`
- `frontend/pages/create-quiz.html`
- `frontend/pages/take-quiz.html`
- `frontend/assets/js/create-quiz.js`
- `frontend/assets/js/take-quiz.js`

### Create Quiz page
- form: topic, question count, marks, difficulty, time limit
- submit to create quiz
- show generation result

### Take Quiz page
- list quizzes
- render questions and options
- submit answers
- show score, correct/incorrect, explanation, summary

### Definition of done
- Full quiz loop from creation to score display works in UI.

---

## Step 14 - Analytics Event Tracking and Metrics APIs

Status in repo: pending
Estimated time: 4-6 hours
Owner: Backend analytics agent
Depends on: Steps 9, 13

### New table
- `events` (if not yet created)

### Event types
- `doc_uploaded`
- `chat_asked`
- `quiz_created`
- `quiz_submitted`

### API routes
In `backend/app/api/analytics.py`:
1. `GET /api/analytics/overview`
2. `GET /api/analytics/progress`
3. `GET /api/analytics/weak-topics`

### Service files
- `backend/app/services/analytics/events.py`
- `backend/app/services/analytics/metrics.py`

### Definition of done
- Metrics return user-scoped data for dashboard charts.

---

## Step 15 - Frontend Analytics Page

Status in repo: pending (frontend base migrated; analytics page not built yet)
Estimated time: 3-5 hours
Owner: Frontend web agent (HTML/CSS/JS)
Depends on: Step 14

### Files
- `frontend/components/api_client.js`
- `frontend/pages/analytics.html`
- `frontend/assets/js/analytics.js`

### UI sections
1. high-level cards (docs, chats, quizzes, average score)
2. progress over time chart
3. weak topics and recommended next quiz

### Definition of done
- Analytics page renders live backend metrics for logged-in user.

---

## Step 16 - Production Packaging and Deployment

Status in repo: pending
Estimated time: 4-6 hours
Owner: DevOps/full-stack agent
Depends on: Step 15

### Files to create/update
- `docker-compose.yml`
- backend and frontend Dockerfiles (if chosen)
- `.env.example` production notes
- `README.md` deployment section

### Requirements
- backend service
- frontend service
- app database connection from env
- wrapper URL/key from env
- health checks

### Definition of done
- App can be brought up in a reproducible way for staging/production.

---

## 6. Database Migration Schedule (Exact Order)

1. Existing migration (already done): users table
2. New migration A (Phase 3): enable pgvector + documents + document_ingestions + chunks
3. New migration B (Phase 3): chats + chat_messages + chat_message_sources
4. New migration C (Phase 4): quizzes + quiz_questions + quiz_question_sources + quiz_attempts + quiz_attempt_answers
5. New migration D (Phase 5): events table (if not included earlier)

Run for each migration:
```bash
cd backend
flask db migrate -m "<clear_description>"
flask db upgrade
```

## 7. API Delivery Order

1. Auth (already live)
2. Documents upload/list/status/delete
3. Chat sessions/messages + RAG citations
4. Quiz create/list/detail/questions
5. Quiz attempt start/submit/result
6. Analytics overview/progress/weak-topics

## 8. Test Gate After Every Major Step

Minimum checks after each step:
1. backend app boots without import errors
2. frontend app boots and auth guard still works
3. existing auth endpoints still pass manual test
4. new endpoint(s) return expected status codes
5. docs file added for that step

## 9. Agent Handoff Template (Copy-Paste)

Use this when assigning one step to an agent:

```text
Read AGENTS.MD and docs/* (newest first). Execute only Step <N> from plan.md.
Constraints:
- follow architecture rules in AGENTS.MD
- do not break existing auth flow
- use SQLAlchemy models and Flask-Migrate for DB changes
- frontend must call backend only via frontend/components/api_client.js
After completion:
- run relevant checks
- create docs/YYYY-MM-DD_step<N>_<short_desc>.md with full summary
- report changed files and commands run
```

## 10. Priority Queue If You Want Fastest Value First

If you want working product quickly with minimal delay, assign in this order:
1. Step 1
2. Step 4
3. Step 5
4. Step 6
5. Step 7
6. Step 8
7. Step 9
8. Step 10
9. Step 11
10. Step 12
11. Step 13
12. Step 14
13. Step 15
14. Step 16

This order gives: auth (already done) -> documents + chat -> quizzes -> analytics -> deployment.
