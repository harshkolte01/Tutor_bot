# Step 14 - Analytics Event Tracking and Metrics APIs

## Task Summary

Implemented the Step 14 backend analytics flow for event tracking and dashboard metrics.

Added:
- an `events` table and migration for persistent user-scoped analytics events
- event tracking for document upload, text document creation, chat asks, quiz creation, and quiz submission
- analytics metrics services for overview, progress, and weak-topics data
- authenticated analytics API routes for dashboard chart consumption
- a focused integration test for the analytics flow

## Files Created/Edited

Edited:
- `backend/app/__init__.py`
- `backend/app/api/analytics.py`
- `backend/app/api/chat.py`
- `backend/app/api/documents.py`
- `backend/app/api/quizzes.py`
- `backend/app/db/models/__init__.py`
- `backend/app/services/quiz/generator.py`

Created:
- `backend/app/db/models/event.py`
- `backend/app/services/analytics/events.py`
- `backend/app/services/analytics/metrics.py`
- `backend/migrations/versions/d1e0b2c4a5f6_create_events_table.py`
- `tests/test_analytics.py`
- `docs/2026-03-22_1444_step14_analytics_event_tracking_metrics.md`

## Endpoints Added/Changed

Added:
- `GET /api/analytics/overview`
- `GET /api/analytics/progress`
- `GET /api/analytics/weak-topics`

Changed existing behavior:
- `POST /api/documents/upload`
  - now records `doc_uploaded`
- `POST /api/documents/text`
  - now records `doc_text_added`
- `POST /api/chat/sessions/<chat_id>/messages`
  - now records `chat_asked`
- `POST /api/quizzes`
  - now records `quiz_created`
- `POST /api/quizzes/<quiz_id>/attempts/<attempt_id>/submit`
  - now records `quiz_submitted`

All analytics routes require JWT auth and return only data scoped to the authenticated user.

## DB Schema / Migration Changes

Added migration:
- `backend/migrations/versions/d1e0b2c4a5f6_create_events_table.py`

New table:
- `events`
  - `id` bigint PK
  - `user_id` FK -> `users.id`
  - `event_type`
  - `entity_type`
  - `entity_id`
  - `metadata_json`
  - `created_at`

Indexes:
- `ix_events_user_created_at`
- `ix_events_user_event_type`

## Decisions / Tradeoffs

1. Overview metrics combine current table counts with historical event counts so the dashboard can show both present-state totals and activity totals.
2. Progress metrics use a fixed 14-day daily bucket series by default so the frontend gets chart-ready data without extra aggregation logic.
3. Weak-topic metrics group submitted results by `quiz.spec_json.topic` when available, which keeps the topic label stable even if quiz titles vary.
4. Event writes were kept inside the same backend flow as the originating action so analytics persistence stays aligned with successful user actions.

## Validation Notes

Commands run:
- `python -m py_compile backend/app/db/models/event.py backend/app/services/analytics/events.py backend/app/services/analytics/metrics.py backend/app/api/analytics.py backend/app/api/documents.py backend/app/api/chat.py backend/app/services/quiz/generator.py backend/app/api/quizzes.py tests/test_analytics.py`
- `python -m py_compile backend/migrations/versions/d1e0b2c4a5f6_create_events_table.py`
- `cd backend && python -m flask --app run.py db upgrade`
- `python tests/test_analytics.py`
- `$env:PYTHONPATH='backend'; python tests/test_quizzes.py`
- `$env:PYTHONPATH='backend'; python tests/test_quiz_attempts.py`
- backend start smoke with `python -m flask --app run.py run --no-debugger --no-reload` plus an HTTP probe
- frontend start smoke with `python -m http.server 5500` plus an HTTP probe

Results:
- syntax checks passed
- analytics integration test passed
- Step 11 quiz API regression test passed
- Step 12 quiz attempt regression test passed
- auth regression coverage passed in the analytics and quiz integration tests
- analytics routes returned user-scoped metrics
- migration upgrade applied cleanly
- backend start smoke passed
- frontend start smoke passed
