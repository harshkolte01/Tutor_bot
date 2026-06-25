# AI Agent Connection Status

## Task Summary

Added a public AI agent connection indicator for the frontend so users see an immediate "Connecting to AI agent" signal while the Render-hosted wrapper wakes up, and a connected signal once the wrapper responds.

The browser never calls the Render wrapper directly. It calls the Tutor Bot backend, and the backend probes the wrapper through the existing wrapper client.

## Files Created/Edited

Created:
- `backend/app/api/ai.py`
- `backend/app/services/wrapper/status.py`
- `frontend/assets/js/ai_status.js`
- `tests/test_ai_status.py`
- `docs/2026-06-25_ai_agent_connection_status.md`

Edited:
- `backend/app/__init__.py`
- `backend/app/config.py`
- `.env.example`
- `frontend/components/api_client.js`
- `frontend/assets/css/base.css`
- `frontend/index.html`
- `frontend/pages/login.html`
- `frontend/pages/signup.html`
- `frontend/pages/documents.html`
- `frontend/pages/chat.html`
- `frontend/pages/create-quiz.html`
- `frontend/pages/take-quiz.html`
- `frontend/pages/analytics.html`
- `frontend/pages/profile.html`

## Endpoints Added/Changed

Added:
- `GET /api/ai/status`
  - Public status endpoint used by the frontend connection indicator.
  - Uses a tiny `POST /v1/chat/completions` call through `backend/app/services/wrapper/client.py`.
  - Returns sanitized status only: `connected`, `waking`, `unavailable`, or `not_configured`.
  - Caches successful checks for `WRAPPER_STATUS_CACHE_SECONDS` and failed/waking checks for `WRAPPER_STATUS_RETRY_SECONDS`.

Changed:
- Frontend pages now load `frontend/assets/js/ai_status.js`.
- Frontend HTTP still goes only through `frontend/components/api_client.js`.

## DB Schema / Migration Changes

None.

## Decisions / Tradeoffs

1. Kept `WRAPPER_BASE_URL` and `WRAPPER_KEY` backend-only; the frontend never sees the Render wrapper URL or key.
2. Used a tiny chat completion instead of calling arbitrary wrapper health URLs so the app still follows the wrapper policy: only `/v1/chat/completions` and `/v1/embeddings`.
3. Added short in-memory caching so every page load does not trigger a wrapper/model call.
4. Returned `200` from `/api/ai/status` even when the AI service is waking or unavailable, because this endpoint reports state rather than failing the page load.
5. On mobile, the top bar shows the status dot as the visual signal and keeps the full label available through accessibility/title text to avoid header overflow.

## Validation Notes

Commands run:
- `$env:PYTHONPATH='backend'; python -m py_compile backend\app\api\ai.py backend\app\services\wrapper\status.py backend\app\config.py backend\app\__init__.py tests\test_ai_status.py tests\test_auth_profile_password.py`
- `python tests\test_ai_status.py`
- `python tests\test_auth_profile_password.py`
- `node --check frontend\assets\js\ai_status.js`
- `node --check frontend\components\api_client.js`
- `node --check frontend\assets\js\landing.js`
- Backend start smoke on port 5002 with empty wrapper env and probe `GET /api/ai/status`
- Frontend static server smoke on port 5502 and probe `GET /index.html`

Results:
- Python syntax checks passed.
- AI status endpoint regression passed for connected, cached connected, waking, and not-configured states.
- Auth regression still passed for `register`, `login`, `refresh`, `me`, and password update.
- JavaScript syntax checks passed.
- Backend and frontend smokes passed.
