# Backend Documentation

This document describes the implemented backend in `backend/` as of March 16, 2026.

## 1) Backend Purpose

The backend provides:
- JWT authentication and user-scoped access control
- document ingestion and vector retrieval for RAG
- chat session and message APIs with citations
- quiz generation, quiz attempts, grading, and result summaries
- Ollama-mediated generation for chat, quiz generation, and quiz summaries
- wrapper-mediated Gemini embeddings for ingestion and retrieval

## 2) Application Bootstrap

Entry points:
- `backend/run.py`
- `backend/app/__init__.py`

`create_app()` responsibilities:
- load config from environment via `app/config.py`
- initialize `db`, `migrate`, and `jwt`
- apply CORS handling for allowed browser origins
- import models for migration discovery
- register blueprints:
  - `auth_bp`
  - `dev_bp`
  - `documents_bp`
  - `chat_bp`
  - `quizzes_bp`

## 3) Configuration

`app/config.py` exposes:
- `SQLALCHEMY_DATABASE_URI`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `WRAPPER_BASE_URL`
- `WRAPPER_KEY`
- `WRAPPER_EMBEDDING_MODEL`
- `OLLAMA_BASE_URL`
- `OLLAMA_API_KEY`
- `OLLAMA_MODEL`
- provider timeout and retry settings
- `UPLOAD_FOLDER`
- `CORS_ALLOWED_ORIGINS`

## 4) Authentication

Auth is built with `Flask-JWT-Extended`.

Implemented endpoints in `app/api/auth.py`:
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/me`

Behavior:
- password hashing and duplicate checks on registration
- `is_active` enforcement on login
- refresh-token-based access renewal
- JWT identity is always `user.id`

## 5) Database Schema

Current migrations:
- `b0536757bfa6_create_users_table.py`
- `f3a9c1d2e4b7_create_documents_ingestions_chunks.py`
- `b68382d50595_create_chats_chat_messages_chat_message_.py`
- `8d5a35927e58_add_chat_documents_table.py`
- `8553dfd2f555_create_quiz_tables.py`

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

Scope isolation:
- all protected APIs enforce `user_id` ownership
- retrieval and quiz creation remain user-scoped

## 6) AI Client Layer

Files:
- `app/services/wrapper/client.py`
- `app/services/wrapper/retry.py`

Implemented rules:
- backend AI calls only through `app/services/wrapper/client.py`
- chat and quiz generation use Ollama OpenAI-compatible chat completions
  - `POST /v1/chat/completions` via `OLLAMA_BASE_URL`
- embeddings stay on the wrapper
  - `POST /v1/embeddings`
- bearer auth with `WRAPPER_KEY` for embedding calls
- retry on `429`, `502`, `503`, `504`
- timeout and error normalization through `WrapperError`
- singleton access through `get_client()`

## 7) Document Ingestion and Retrieval

Document routes in `app/api/documents.py`:
- `POST /api/documents/upload`
- `POST /api/documents/text`
- `GET /api/documents`
- `GET /api/documents/<doc_id>`
- `DELETE /api/documents/<doc_id>`
- `GET /api/documents/<doc_id>/ingestions/<ingestion_id>/status`
- `POST /api/documents/<doc_id>/reingest`

Ingestion flow:
1. create `Document` and `DocumentIngestion(status=processing)`
2. extract text from PDF or text input
3. chunk text
4. request embeddings through wrapper
5. persist chunk rows
6. mark ingestion `ready` and update `current_ingestion_id`
7. on failure, mark ingestion `failed`

Retrieval file:
- `app/services/rag/retrieval.py`

Retrieval behavior:
- user-scoped vector search against `chunks.embedding`
- filters to each document's `current_ingestion_id`
- optional `document_ids` filter
- returns chunk ids, snippets, similarity, and document metadata

## 8) Chat and Routing

Chat routes in `app/api/chat.py`:
- `POST /api/chat/sessions`
- `GET /api/chat/sessions`
- `GET /api/chat/sessions/<chat_id>/messages`
- `POST /api/chat/sessions/<chat_id>/messages`
- `GET /api/chat/sessions/<chat_id>/documents`
- `PUT /api/chat/sessions/<chat_id>/documents`

Implemented behavior:
- session ownership validation
- recent-history loading for answers
- per-chat document scoping
- routed model selection
- assistant answer persistence with citations
- out-of-context signaling
- automatic session title update for default chat titles

Routing and answering files:
- `app/services/router/heuristics.py`
- `app/services/router/classifier.py`
- `app/services/rag/answering.py`

## 9) Quiz Backend

Quiz routes in `app/api/quizzes.py`:
- `POST /api/quizzes`
- `GET /api/quizzes`
- `GET /api/quizzes/<quiz_id>`
- `GET /api/quizzes/<quiz_id>/questions`
- `POST /api/quizzes/<quiz_id>/attempts/start`
- `POST /api/quizzes/<quiz_id>/attempts/<attempt_id>/submit`
- `GET /api/quizzes/attempts/<attempt_id>`

Quiz creation behavior:
- parses and validates topic, counts, marks, difficulty, time limit, and optional `document_ids`
- validates ownership and readiness of selected documents
- retrieves context from the user's latest ready ingestions
- generates structured quiz JSON through the AI gateway
- validates question schema, citations, marks, and answer references
- stores quizzes, questions, and question-source citations
- hides answer keys on quiz fetch endpoints

Quiz attempt behavior:
- creates attempt rows on start
- grades answers deterministically from stored `correct_json`
- stores one answer row per question
- returns explanations and correct answers only after submission
- stores a performance summary in `summary_json`

Quiz service files:
- `app/services/quiz/spec_parser.py`
- `app/services/quiz/generator.py`
- `app/services/quiz/validator.py`
- `app/services/quiz/grading.py`
- `app/services/quiz/summarizer.py`

## 10) Dev Endpoint

`GET /api/dev/wrapper-smoke`:
- JWT-protected
- runs one Ollama chat call and one wrapper embedding call

## 11) Error Handling

Common API patterns:
- `400` for invalid payloads
- `401` for missing or expired auth
- `404` for missing scoped resources
- `409` for conflicting state such as resubmitting an attempt
- `413` and `415` for invalid document uploads
- `503` for AI provider availability problems in AI-backed flows

## 12) Current Constraints

- analytics endpoints are not implemented yet
- ingestion still runs synchronously inside the request lifecycle
- no streaming chat responses yet
- current test coverage is integration-script based rather than a full pytest suite

## 13) Useful Backend Checks

Common checks used in the repo:
- `python test_quizzes.py`
- `python test_quiz_attempts.py`
- `python test_documents.py`
- `python test_chat.py`
- `python test_chat_with_pdf.py`

## 14) Next Backend Work

Recommended next backend steps:
1. implement analytics events and metrics endpoints
2. move ingestion to background workers
3. add fuller automated test coverage
4. add production observability and deployment support
