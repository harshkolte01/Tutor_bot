# README Refresh

## Task Summary

Updated the root, backend, and frontend README files to match the current implemented state of the project.

Covered:
- auth, documents, chat, and quiz features
- current pages and API surface
- current database tables and migrations
- local run instructions and frontend API base URL notes
- current gaps and next steps

## Files Created/Edited

Edited:
- `README.md`
- `backend/README.md`
- `frontend/README.md`

Created:
- `docs/2026-03-16_0120_readme_refresh.md`

## Endpoints Added/Changed

None.

This task only updated documentation to reflect already-implemented endpoints, including:
- auth routes
- document routes
- chat routes
- quiz routes

## DB Schema / Migration Changes

None.

## Decisions / Tradeoffs

1. Rewrote each README to reflect the current implementation directly instead of making small incremental edits to outdated sections.
2. Included local-development guidance for `frontend/config.js` because the frontend API base URL can otherwise point at a deployed backend instead of the local Flask server.
3. Focused the docs on implemented behavior and current gaps, rather than copying the full long-term plan into the READMEs.

## Validation Notes

Commands run:
- `python test_quizzes.py`
- `python test_quiz_attempts.py`
- backend start smoke with `python -m flask --app run.py run --no-debugger --no-reload`
- frontend start smoke with `python -m http.server 5500` plus an HTTP probe

Results:
- quiz API integration test passed
- quiz attempt integration test passed
- auth regression coverage passed through the integration tests
- backend start smoke passed
- frontend start smoke passed
