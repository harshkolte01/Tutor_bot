# Step 15 - Frontend Analytics Page

## Task Summary

Implemented the Step 15 frontend analytics page so the UI renders live backend analytics metrics from Step 14.

Added:
- analytics endpoint helpers in the shared frontend API client
- a protected analytics page with live overview, event mix, activity, score-trend, and weak-topic sections
- a frontend analytics page script that fetches and renders the backend metrics in parallel

## Files Created/Edited

Edited:
- `frontend/components/api_client.js`

Created:
- `frontend/pages/analytics.html`
- `frontend/assets/js/analytics.js`
- `docs/2026-03-22_1455_step15_frontend_analytics_page.md`

## Endpoints Added/Changed

No backend endpoints were changed in this step.

Frontend now consumes the existing protected analytics endpoints via `frontend/components/api_client.js`:
- `GET /api/analytics/overview`
- `GET /api/analytics/progress`
- `GET /api/analytics/weak-topics`

## DB Schema / Migration Changes

None.

## Decisions / Tradeoffs

1. Kept all analytics HTTP access inside `frontend/components/api_client.js` so the new page still follows the repo rule of one shared frontend API layer.
2. Kept analytics-specific styling inside `frontend/pages/analytics.html` so the step stayed limited to the requested frontend files.
3. Rendered the page with simple CSS-based charts and cards instead of adding a charting library, which keeps the page lightweight and dependency-free while still showing live metrics clearly.
4. Fetched overview, progress, and weak-topic payloads in parallel so the page reflects the live backend state without serial request delays.

## Validation Notes

Commands run:
- `node --check frontend/assets/js/analytics.js`
- `node --check frontend/components/api_client.js`
- `python tests/test_analytics.py`
- backend start smoke with `python -m flask --app run.py run --no-debugger --no-reload` plus an HTTP probe
- frontend start smoke with `python -m http.server 5500` plus an HTTP probe

Results:
- frontend JavaScript syntax checks passed
- analytics integration test passed, including auth regression coverage and user-scoped analytics checks
- backend start smoke passed
- frontend start smoke passed
