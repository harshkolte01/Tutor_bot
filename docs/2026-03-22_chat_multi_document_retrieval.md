# Chat Multi-Document Retrieval

## Task Summary

Fixed chat answering so a session using all ready documents no longer collapses to a single-document source window by default.

Changed behavior:
- chat retrieval now uses diversified chunk selection when multiple documents may be in scope
- all-doc chat mode preserves source coverage across multiple relevant documents instead of letting one document monopolize the top-k window
- assistant prompting now explicitly allows synthesis across multiple relevant sources while still ignoring weak or irrelevant ones
- added a deterministic regression test for the all-doc multi-document chat path

## Files Created/Edited

Edited:
- `backend/app/services/rag/answering.py`

Created:
- `tests/test_chat_multi_document_scope.py`
- `docs/2026-03-22_chat_multi_document_retrieval.md`

## Endpoints Added/Changed

Changed behavior:
- `POST /api/chat/sessions/<chat_id>/messages`
  - when multiple documents may be in scope, retrieval now prefers a diversified multi-document source window instead of a single global top-k list

No new endpoints were added.

## DB Schema / Migration Changes

None.

## Decisions / Tradeoffs

1. Reused the existing diversified retrieval utility already introduced for quiz coverage, so the chat fix stays consistent with the retrieval strategy already in the codebase.
2. Kept the default chat document coverage target small (`2`) to improve cross-document coverage without flooding the prompt with low-value context.
3. Did not force answer citations to span multiple documents at validation time; chat now gets better multi-document context, but the model is still allowed to rely on only the relevant sources when some retrieved chunks are weaker.

## Validation Notes

Commands run:
- `python -m py_compile backend/app/services/rag/answering.py tests/test_chat_multi_document_scope.py`
- `python tests/test_chat_multi_document_scope.py`

Results:
- Python syntax checks passed
- new chat regression test passed
- auth regression checks passed inside the new test (`register`, `login`, `refresh`, `me`)
- all-doc chat retrieval preserved source coverage across two ready documents
