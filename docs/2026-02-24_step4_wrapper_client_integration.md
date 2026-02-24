# Step 4 - Wrapper Client Integration

**Date:** 2026-02-24  
**Phase:** Foundation for all AI calls  
**Status:** Complete

---

## Task Summary

Implemented the wrapper HTTP client layer so that every LLM call in the project
goes through a single, well-tested module. No API route may call an AI provider
directly — all calls must use `get_client()` from `client.py`.

---

## Files Created / Edited

| File | Action |
|------|--------|
| `backend/app/services/wrapper/retry.py` | Created — retry helper |
| `backend/app/services/wrapper/client.py` | Created — WrapperClient + WrapperError + singleton |
| `backend/app/config.py` | Edited — added wrapper timeout/retry config keys |
| `backend/app/api/dev.py` | Created — smoke endpoint |
| `backend/app/__init__.py` | Edited — registered `dev_bp` |

---

## Endpoints Added

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | `/api/dev/wrapper-smoke` | JWT required | Tests one chat call + one embedding call |

Response shape:
```json
{
  "ok": true,
  "results": {
    "chat": { "status": "ok", "model": "...", "reply": "..." },
    "embedding": { "status": "ok", "model": "...", "dimensions": 768 }
  }
}
```
Returns `200` when both succeed, `502` if either fails.

---

## DB / Migration Changes

None — no schema changes in this step.

---

## Config Keys Added

| Key | Default | Source |
|-----|---------|--------|
| `WRAPPER_TIMEOUT` | `30` | `WRAPPER_TIMEOUT` env var |
| `WRAPPER_MAX_RETRIES` | `3` | `WRAPPER_MAX_RETRIES` env var |
| `WRAPPER_BASE_DELAY` | `1.0` | `WRAPPER_BASE_DELAY` env var |
| `WRAPPER_DEFAULT_MODEL` | `routeway/glm-4.5-air:free` | `WRAPPER_DEFAULT_MODEL` env var |
| `WRAPPER_EMBEDDING_MODEL` | `gemini/gemini-embedding-001` | `WRAPPER_EMBEDDING_MODEL` env var |

`WRAPPER_BASE_URL` and `WRAPPER_KEY` were already in config; values confirmed present in `.env`.

---

## Implementation Details

### retry.py — `call_with_retry(fn, max_retries, base_delay)`
- Wraps any `() -> requests.Response` callable
- Retries on HTTP status codes: `429`, `502`, `503`, `504`
- Exponential backoff with full jitter: `sleep = random(0, base_delay * 2^attempt)`
- Respects `Retry-After` header on 429
- Re-raises network-level exceptions (`RequestException`) after exhausting retries

### client.py — `WrapperClient`
- `chat_completions(model, messages, temperature=0.7, max_tokens=None)` → `POST /v1/chat/completions`
- `embeddings(model, input)` → `POST /v1/embeddings`
- Bearer auth via `Authorization: Bearer <WRAPPER_KEY>` header
- Normalises all failures into `WrapperError(message, status_code, upstream)`
- Network errors (timeout, connection) → `WrapperError` with `status_code=None`
- HTTP ≥ 400 → `WrapperError` with upstream body captured

### `get_client()` singleton
- Module-level `_client` initialised on first call from `current_app.config`
- Must be called inside a Flask application context
- Services import and call `get_client()` — never instantiate `WrapperClient` directly

---

## Decisions / Tradeoffs

- **Singleton per process** — `_client` is module-level, not per-request. Safe because
  wrapper config (URL, key, timeout) does not change at runtime.
- **No `__init__.py` in `services/wrapper/`** — stubs already existed without one;
  imports work as plain modules.
- **Smoke endpoint is JWT-gated** — prevents accidental public exposure in production
  while still being callable from any authenticated session for quick healthchecks.
- **`max_tokens` is optional** — omitted from payload when `None` so the wrapper
  can apply its own default, avoiding unnecessary token limits.

---

## Auth Regression Check

Ran `python -c "from app import create_app; app = create_app()"` — app factory
imports cleanly. Both `auth` and `dev` blueprints registered successfully.

Existing auth endpoints unmodified:
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/me`
