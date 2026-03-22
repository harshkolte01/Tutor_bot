# Test Folder Reorganization (2026-03-21)

## Task Summary
Created a top-level `tests/` directory and moved all Python test files matching `test*.py` into this single folder for centralized test organization.

## Files Created/Edited
- Created: `tests/` (directory)
- Moved to `tests/`:
  - `test_chat.py`
  - `test_chat_with_pdf.py`
  - `test_documents.py`
  - `test_linear_regression_pdf.py`
  - `test_live_backend_quiz_flow.py`
  - `test_quizzes.py`
  - `test_quiz_attempts.py`
  - `backend/test_retrieval.py`
- Added documentation:
  - `docs/2026-03-21_test_folder_reorganization.md`

## Endpoints Added/Changed
None.

## DB Schema/Migration Changes
None.

## Decisions/Tradeoffs
- Used a top-level `tests/` folder to simplify discovery and standardize location.
- Included `backend/test_retrieval.py` so all test files follow one consistent placement rule.
- This reorganization may require updates to CI scripts or commands that referenced old test paths.
