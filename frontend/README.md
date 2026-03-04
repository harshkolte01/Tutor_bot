# Frontend Documentation

This document describes the implemented frontend in `frontend/` as of March 4, 2026.

## 1) Frontend Purpose

The frontend is a static web client (HTML/CSS/JS) that provides:
- authentication UI (signup/login)
- document upload and ingestion monitoring UI
- chat UI with citations and document-scoped context controls

It communicates only with the Flask backend API.

## 2) Frontend Architecture

Core folders:
- `pages/` - route-level HTML pages
- `assets/js/` - page controllers
- `assets/css/` - shared and page styles
- `components/` - shared JS modules (`api_client.js`, `session.js`)

Design principle enforced in code:
- all HTTP calls go through `components/api_client.js`

## 3) Configuration

Files:
- `frontend/config.js`
- `frontend/config.example.js`

The API base URL is read from:
- `window.TUTOR_BOT_CONFIG.API_BASE_URL`

Default:
- `http://localhost:5000`

## 4) Session and Auth State

### `components/session.js`
Stores user session in localStorage key:
- `tutorbot.session.v1`

Stored fields:
- `accessToken`
- `refreshToken`
- `user`

### `components/api_client.js`
Implements:
- centralized request helper with timeout/error normalization
- `APIError` class for consistent handling
- auto-refresh-on-401 behavior:
  - one refresh attempt via `/api/auth/refresh`
  - retry original request once
  - on failure: clear session and redirect to `/pages/login.html`

## 5) API Client Surface

Auth methods:
- `register(...)`
- `login(...)`
- `refreshToken(...)`
- `getMe(...)`

Generic auth helpers:
- `authedGet(...)`
- `authedPost(...)`
- `authedDelete(...)`

Documents methods:
- `uploadDocument(...)`
- `addTextDocument(...)`
- `listDocuments(...)`
- `getDocument(...)`
- `deleteDocument(...)`
- `getIngestionStatus(...)`
- `retryIngestion(...)`

Chat methods:
- `createChatSession(...)`
- `listChatSessions(...)`
- `getChatMessages(...)`
- `sendChatMessage(...)`
- `getChatDocuments(...)`
- `setChatDocuments(...)`

## 6) Page-Level Behavior

### Landing (`index.html` + `assets/js/landing.js`)
- shows guest CTA vs authenticated actions based on session
- displays active API base URL footer
- uses intersection observer for reveal animations
- allows sign-out directly from landing top bar

### Signup/Login (`pages/signup.html`, `pages/login.html`, `assets/js/auth.js`)
- validates required fields on client side
- signup checks password length and confirmation match
- on successful auth:
  - stores session
  - redirects to landing

### Documents (`pages/documents.html`, `assets/js/documents.js`)
Features implemented:
- auth guard redirect to login when no access token
- drag/drop or file-picker upload UI
- optional custom title on upload
- add plain-text document context
- list all current documents
- show ingestion status badge per document
- polling for processing ingestions every 3s
- retry button for failed/no-ingestion records
- soft delete with confirmation

UX details:
- fake progress animation during upload
- status line messaging (`ok` / `err`)

### Chat (`pages/chat.html`, `assets/js/chat.js`)
Features implemented:
- auth guard
- session list with new chat creation
- active session switching and message loading
- send message with optimistic user bubble
- assistant markdown rendering (via `marked` CDN)
- model/category metadata display on assistant messages
- collapsible citations block
- out-of-context choice card:
  - ask to use general knowledge
  - optional resend with `use_general_knowledge=true`
- per-chat document picker modal:
  - list user docs
  - save selected document IDs for session filtering
  - clear selection to search all docs

## 7) Frontend Routing Model

This is a multi-page static app (MPA), not SPA routing.

Primary pages:
- `/index.html`
- `/pages/signup.html`
- `/pages/login.html`
- `/pages/documents.html`
- `/pages/chat.html`

## 8) Styling

Shared style files:
- `assets/css/base.css`
- `assets/css/auth.css`
- `assets/css/landing.css`
- `assets/css/app.css`

Typography currently uses:
- DM Sans
- Sora

## 9) Run Locally

```bash
cd frontend
python -m http.server 5500
```

Open `http://localhost:5500`.

Backend must be running and reachable at configured `API_BASE_URL`.

## 10) Current Constraints

- No quiz pages implemented yet.
- No analytics dashboard page implemented yet.
- No state management library (intentionally simple module-level state).
- Markdown is rendered directly from model output; if stronger sanitization is required, add explicit sanitization policy.

## 11) Frontend Future Roadmap

Recommended next steps:
1. Build quiz creation/taking pages integrated with upcoming quiz APIs.
2. Build analytics dashboard page once metrics APIs are live.
3. Add improved loading skeletons and richer empty/error states.
4. Add end-to-end browser tests (Playwright/Cypress).
5. Add production asset build pipeline and minification strategy.
