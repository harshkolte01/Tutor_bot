# 2026-03-28 Ollama Generation Split

## Task Summary

Implemented a split-provider AI setup:
- Ollama now handles generation for chat responses, quiz generation, quiz repair, classifier fallback, and quiz attempt summaries.
- The existing wrapper service remains responsible for Gemini embeddings used by ingestion and retrieval.
- Environment/config support was added for local Ollama URL, model name, timeout, and optional fallback model.

## Files Created Or Edited

Created:
- `docs/2026-03-28_ollama_generation_split.md`

Edited:
- `.env`
- `.env.example`
- `README.md`
- `backend/README.md`
- `backend/app/api/dev.py`
- `backend/app/config.py`
- `backend/app/services/quiz/generator.py`
- `backend/app/services/quiz/summarizer.py`
- `backend/app/services/rag/answering.py`
- `backend/app/services/rag/ingestion.py`
- `backend/app/services/rag/retrieval.py`
- `backend/app/services/router/classifier.py`
- `backend/app/services/router/heuristics.py`
- `backend/app/services/wrapper/client.py`

## Endpoints Added Or Changed

No API routes were added or removed.

Behavior changed:
- `GET /api/dev/wrapper-smoke`
  - chat smoke now exercises Ollama generation
  - embedding smoke still exercises the wrapper embedding path
- `POST /api/chat/sessions/<chat_id>/messages`
  - answer generation now uses Ollama through the centralized AI gateway
- `POST /api/quizzes`
  - quiz generation now uses Ollama through the centralized AI gateway
- quiz attempt summary generation now uses Ollama through the centralized AI gateway

## DB Schema / Migration Changes

No schema changes.
No migrations added.

Rationale:
- Embeddings remain on Gemini via the wrapper, so the existing `Vector(1536)` chunk storage and current ingested vectors remain valid.
- No document re-ingestion is required for this provider split alone.

## Decisions And Tradeoffs

- Kept all AI calls centralized in `backend/app/services/wrapper/client.py` instead of scattering direct Ollama calls across services.
- Added explicit Ollama config:
  - `OLLAMA_BASE_URL`
  - `OLLAMA_API_KEY`
  - `OLLAMA_MODEL`
  - `OLLAMA_FALLBACK_MODEL`
  - `OLLAMA_TIMEOUT`
  - `OLLAMA_MAX_RETRIES`
  - `OLLAMA_BASE_DELAY`
- Left `WRAPPER_*` in place for embeddings and kept `WRAPPER_DEFAULT_MODEL` as a legacy alias for compatibility.
- Implemented lazy provider initialization in the AI gateway so generation-only paths do not fail just because embedding config is missing at startup.
- Routing categories are still returned, but all categories now resolve to the configured Ollama model unless a fallback model is explicitly configured.
- No frontend changes were required because frontend HTTP usage remains unchanged.

## Verification

Passed:
- `python - <<... compileall.compile_dir('backend/app', quiet=1) ...>>`
- `python tests/test_chat_multi_document_scope.py`

Blocked by environment:
- `python tests/test_quizzes.py`
- `python tests/test_quiz_attempts.py`

Blocker details:
- Both quiz scripts required `PYTHONPATH=backend` because of outdated script-local import assumptions.
- After that adjustment, both scripts failed on PostgreSQL connectivity to the configured Neon database from the current environment, so quiz-path verification could not be completed locally in this run.
