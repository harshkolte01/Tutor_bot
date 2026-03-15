# Frontend Documentation

This document describes the implemented frontend in `frontend/` as of March 16, 2026.

## 1) Frontend Purpose

The frontend is a static web client that provides:
- authentication UI
- document upload and ingestion monitoring
- chat with citations and per-chat document controls
- quiz creation with document scoping
- quiz taking, answer submission, and result review

It communicates only with the Flask backend API.

## 2) Frontend Architecture

Core folders:
- `pages/` - route-level HTML pages
- `assets/js/` - page controllers
- `assets/css/` - shared and page styles
- `components/` - shared JS modules such as `api_client.js` and `session.js`

Enforced design rule:
- all HTTP calls go through `frontend/components/api_client.js`

## 3) Configuration

Files:
- `frontend/config.js`
- `frontend/config.example.js`

The API base URL is read from:
- `window.TUTOR_BOT_CONFIG.API_BASE_URL`

Default fallback in code:
- `http://localhost:5000`

For local development:
- update `frontend/config.js`
- point `API_BASE_URL` to `http://127.0.0.1:5000` or `http://localhost:5000`

## 4) Session and Auth State

### `components/session.js`

Stores session data in localStorage key:
- `tutorbot.session.v1`

Stored fields:
- `accessToken`
- `refreshToken`
- `user`

### `components/api_client.js`

Implements:
- centralized request helper
- timeout and network error normalization
- `APIError` for consistent UI handling
- one refresh attempt on `401`
- retry of the original request after refresh
- logout redirect to `/pages/login.html` if refresh fails

## 5) API Client Surface

Auth methods:
- `register(...)`
- `login(...)`
- `refreshToken(...)`
- `getMe(...)`

Generic helpers:
- `authedGet(...)`
- `authedPost(...)`
- `authedDelete(...)`

Document methods:
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

Quiz methods:
- `createQuiz(...)`
- `listQuizzes(...)`
- `getQuiz(...)`
- `getQuizQuestions(...)`
- `startQuizAttempt(...)`
- `submitQuizAttempt(...)`
- `getQuizAttempt(...)`

## 6) Implemented Pages

Primary pages:
- `/index.html`
- `/pages/signup.html`
- `/pages/login.html`
- `/pages/documents.html`
- `/pages/chat.html`
- `/pages/create-quiz.html`
- `/pages/take-quiz.html`

This is a multi-page static app, not an SPA.

## 7) Page-Level Behavior

### Landing

Files:
- `index.html`
- `assets/js/landing.js`

Behavior:
- shows guest or authenticated actions based on session state
- supports sign-out from the landing top bar
- uses reveal animations for the hero and sections

### Signup and Login

Files:
- `pages/signup.html`
- `pages/login.html`
- `assets/js/auth.js`

Behavior:
- client-side validation for required fields
- signup password length and confirmation checks
- stores session after successful auth
- redirects to the landing page

### Documents

Files:
- `pages/documents.html`
- `assets/js/documents.js`

Behavior:
- auth guard
- drag/drop file upload
- optional document title on upload
- plain-text context creation
- document list with ingestion badges
- polling for processing ingestions
- retry for failed ingestions
- soft delete with confirmation

### Chat

Files:
- `pages/chat.html`
- `assets/js/chat.js`

Behavior:
- auth guard
- chat session list and new chat creation
- active session switching
- message sending with optimistic user bubble
- assistant markdown rendering with `marked`
- collapsible citations
- out-of-context retry with general knowledge
- per-chat document picker modal
- `Quiz This Chat` redirect using the current chat document scope

### Create Quiz

Files:
- `pages/create-quiz.html`
- `assets/js/create-quiz.js`

Behavior:
- auth guard
- topic, question count, marks, difficulty, and time limit inputs
- document scope choice:
  - all ready documents
  - selected ready documents only
- ready-document checklist loaded from `GET /api/documents`
- chat-to-quiz preselection support through query params
- generated quiz preview after successful creation

### Take Quiz

Files:
- `pages/take-quiz.html`
- `assets/js/take-quiz.js`

Behavior:
- auth guard
- quiz library sidebar
- quiz question preview
- attempt start
- answer selection and submit
- result view with score, correctness, explanations, and summary
- retake flow for the same quiz

## 8) Styling

Shared styles:
- `assets/css/base.css`
- `assets/css/auth.css`
- `assets/css/landing.css`
- `assets/css/app.css`

Typography:
- DM Sans
- Sora

## 9) Run Locally

```bash
cd frontend
python -m http.server 5500
```

Open:
- `http://localhost:5500`

Requirements:
- backend must be running
- `frontend/config.js` must point to the reachable backend API base URL

## 10) Current Constraints

- analytics page is not implemented yet
- no state management library is used by design
- markdown is rendered from assistant output without an additional sanitization layer
- no frontend build pipeline or asset bundling is configured

## 11) Frontend Next Steps

Recommended next frontend work:
1. build analytics dashboard pages once analytics APIs exist
2. add richer loading and empty states
3. add browser-based end-to-end tests
4. add production asset build and minification support
