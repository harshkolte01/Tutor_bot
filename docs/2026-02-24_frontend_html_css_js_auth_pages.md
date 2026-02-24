# 2026-02-24 - Frontend Migration to HTML/CSS/JS (Landing + Login/Signup)

## Task Summary

Replaced the Streamlit frontend with a vanilla HTML/CSS/JS multi-page frontend and implemented:
- landing page
- login page
- signup page

The new frontend preserves existing backend auth API behavior and keeps all frontend-to-backend HTTP calls centralized through a single client module.

## Files Created

- `frontend/index.html`
- `frontend/pages/login.html`
- `frontend/pages/signup.html`
- `frontend/assets/css/base.css`
- `frontend/assets/css/landing.css`
- `frontend/assets/css/auth.css`
- `frontend/assets/js/landing.js`
- `frontend/assets/js/auth.js`
- `frontend/components/api_client.js`
- `frontend/components/session.js`
- `frontend/config.js`
- `frontend/config.example.js`
- `frontend/README.md`
- `docs/2026-02-24_frontend_html_css_js_auth_pages.md`

## Files Edited

- `AGENTS.MD`
- `backend/app/__init__.py`
- `backend/app/config.py`
- `.env.example`

## Files Removed

- `frontend/Home.py`
- `frontend/.streamlit/config.toml`
- `frontend/components/__init__.py`
- `frontend/components/api_client.py`
- `frontend/pages/0_Login.py`
- `frontend/pages/1_Chat_Tutor.py`
- `frontend/pages/2_Upload_Documents.py`
- `frontend/pages/3_Create_Quiz.py`
- `frontend/pages/4_Take_Quiz.py`
- `frontend/pages/5_Analytics.py`

## Endpoints Added/Changed

No new auth endpoints were added.

Frontend now uses existing endpoints via `frontend/components/api_client.js`:
- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/refresh`
- `GET /api/auth/me`

Behavior update:
- Added backend CORS response headers (origin allowlist via `CORS_ALLOWED_ORIGINS`) so browser JS frontend can call backend APIs.

## DB Schema / Migration Changes

None.

## Decisions and Tradeoffs

- Chose a plain multi-page static frontend to align with requested stack (`HTML/CSS/JS`) and remove Streamlit entirely.
- Kept one centralized frontend API client (`api_client.js`) to preserve architectural discipline from prior implementation.
- Added `session.js` to keep token/user storage behavior consistent and isolated from page scripts.
- Added backend CORS allowlist configuration to make browser-based auth calls functional in local development.
- Updated `AGENTS.MD` rules and ownership paths so future agents do not follow outdated Streamlit instructions.
