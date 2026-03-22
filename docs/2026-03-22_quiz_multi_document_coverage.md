# Quiz Multi-Document Coverage

## Task Summary

Fixed quiz generation so selecting all ready documents no longer collapses to a single-document source window by default.

Changed behavior:
- quiz retrieval now resolves the full ready-document scope before searching
- quiz retrieval can reserve source slots for multiple relevant documents instead of using only one global top-k list
- quiz validation now rejects generated quizzes that cite too few documents when multi-document coverage was required
- quiz integration coverage now exercises the all-ready multi-document path

## Files Created/Edited

Edited:
- `backend/app/services/rag/retrieval.py`
- `backend/app/services/quiz/generator.py`
- `backend/app/services/quiz/validator.py`
- `tests/test_quizzes.py`

Created:
- `docs/2026-03-22_quiz_multi_document_coverage.md`

## Endpoints Added/Changed

Changed behavior:
- `POST /api/quizzes`
  - when multiple ready documents are in scope, quiz source retrieval now requests diversified chunks across multiple documents
  - generated quiz JSON is validated to ensure citations span multiple documents when that coverage target applies

No new endpoints were added.

## DB Schema / Migration Changes

None.

## Decisions / Tradeoffs

1. Kept chat retrieval unchanged and added quiz-specific diversified retrieval usage so the fix stays scoped to the quiz flow.
2. Capped required multi-document coverage to a small number of documents per quiz so unrelated low-relevance documents are not forced into the quiz just because the user has many ready files.
3. Enforced document coverage in validation, not just prompt wording, so retries can repair single-document quiz outputs instead of silently accepting them.

## Validation Notes

Commands run:
- `python -m py_compile backend/app/services/rag/retrieval.py backend/app/services/quiz/generator.py backend/app/services/quiz/validator.py tests/test_quizzes.py`
- `$env:PYTHONPATH='backend'; python tests/test_quizzes.py`
- `python tests/test_analytics.py`
- `$env:PYTHONPATH='backend'; python tests/test_quiz_attempts.py`
- backend start smoke with `python -m flask --app run.py run --no-debugger --no-reload`
- frontend start smoke with `python -m http.server 5500`

Results:
- Python syntax checks passed
- quiz API integration test passed, including the new all-ready multi-document regression path
- analytics integration test passed
- quiz attempts integration test passed
- auth regression checks passed through the integration tests (`register`, `login`, `refresh`, `me`)
- backend smoke passed
- frontend smoke passed
