# HTTP-Only AI Status Probe

## Task Summary

Replaced the AI status probe implementation so it no longer calls `POST /v1/chat/completions` and no longer consumes Gemini/free-tier AI quota. The status endpoint now sends only a plain HTTP `GET` request to the configured Render wrapper URL/status path and treats HTTP `200` as connected.

This supersedes the earlier `2026-06-25_ai_agent_connection_status.md` implementation detail that used a tiny chat-completion probe.

## Files Created/Edited

Created:
- `docs/2026-06-25_http_only_ai_status_probe.md`

Edited:
- `backend/app/services/wrapper/status.py`
- `backend/app/config.py`
- `.env.example`
- `frontend/assets/js/ai_status.js`
- `tests/test_ai_status.py`

## Endpoints Added/Changed

Changed:
- `GET /api/ai/status`
  - Now uses `requests.get()` against `WRAPPER_BASE_URL + WRAPPER_STATUS_PATH`.
  - Does not use Gemini, chat completions, embeddings, or the wrapper bearer key.
  - Returns `connected` only when the upstream HTTP response is `200`.
  - Returns `waking` for timeouts/network errors and `502/503/504`.
  - Returns `unavailable` for other non-200 responses.

Frontend behavior changed:
- `frontend/assets/js/ai_status.js` now stores the first connected result in `sessionStorage`.
- Once a browser tab sees connected, that tab does not call `/api/ai/status` again while navigating within the site.
- New browser sessions/tabs still check and retry until they see connected.

## DB Schema / Migration Changes

None.

## Decisions / Tradeoffs

1. Used HTTP `GET` instead of `HEAD` because Render cold-start behavior is most reliably triggered by a normal request.
2. Kept the frontend calling only the Tutor Bot backend, not the Render wrapper directly.
3. Added `WRAPPER_STATUS_PATH` so deployments can use `/` or a future `/health` endpoint without code changes.
4. Kept short backend caching to reduce duplicate external probes, while frontend `sessionStorage` enforces the per-user/browser-session "stop after first 200" behavior.

## Validation Notes

Commands run:
- `$env:PYTHONPATH='backend'; python -m py_compile backend\app\services\wrapper\status.py backend\app\config.py tests\test_ai_status.py`
- `python tests\test_ai_status.py`
- `python tests\test_auth_profile_password.py`
- `node --check frontend\assets\js\ai_status.js`
- `node --check frontend\components\api_client.js`
- Backend start smoke on port 5003 and probe `GET /api/ai/status`
- Frontend static server smoke on port 5503 and probe `GET /index.html`

Results:
- Python syntax checks passed.
- AI status tests passed for HTTP 200 connected, cached connected, timeout waking, 503 waking, 404 unavailable, and not-configured states.
- Auth regression still passed.
- JavaScript syntax checks passed.
- Backend and frontend smokes passed.
