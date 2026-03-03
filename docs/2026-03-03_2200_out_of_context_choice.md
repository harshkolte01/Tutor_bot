# Out-of-Context Response with General Knowledge Choice

**Date/Time**: 2026-03-03 22:00  
**Feature**: When the user asks a question not covered by their uploaded documents, the bot now says so explicitly and offers a choice to answer from general knowledge instead of silently supplementing.

---

## Task Summary

Previously, the system prompt instructed the LLM to "supplement with general knowledge and say so" when retrieved document context was insufficient. This caused confusing behaviour (screenshot: "what is java" was answered fully from general knowledge even though Python docs were attached).

**New behaviour:**
1. If retrieved document chunks do NOT cover the question → LLM emits the sentinel `[NO_CONTEXT]`.
2. Backend detects the sentinel, sets `out_of_context: true` in the response with a standard "documents don't contain info" message.
3. Frontend renders the "not found" message + a choice card: **"Yes, use general knowledge"** / **"No, thanks"**.
4. If the user clicks Yes → a follow-up request is sent with `use_general_knowledge: true`, which skips RAG entirely and answers freely from the model's training knowledge.

---

## Files Modified

| File | Change |
|------|--------|
| `backend/app/services/rag/answering.py` | New strict `_SYSTEM_TEMPLATE` with `[NO_CONTEXT]` sentinel; `generate_answer()` gains `use_general_knowledge` param; sentinel detection sets `out_of_context` flag; returns `out_of_context` in result dict |
| `backend/app/api/chat.py` | Reads `use_general_knowledge` from request body; passes it to `generate_answer()`; includes `out_of_context` in JSON response |
| `frontend/components/api_client.js` | `sendChatMessage()` accepts optional `useGeneralKnowledge = false`; when true, adds `use_general_knowledge: true` to payload |
| `frontend/assets/js/chat.js` | `submitMessage()` checks `result.out_of_context` and calls `appendOutOfContextCard()`; new `appendOutOfContextCard()` renders message + choice card; new `sendAsGeneralKnowledge()` calls the API with the flag |
| `frontend/assets/css/app.css` | Added `.ooc-card`, `.ooc-card-prompt`, `.ooc-card-actions` styles for the choice card |

---

## Endpoints Changed

| Method | URL | Change |
|--------|-----|--------|
| `POST` | `/api/chat/sessions/<id>/messages` | New optional request body field: `use_general_knowledge: bool`. New response field: `out_of_context: bool`. |

---

## DB / Migration Changes

None — no schema changes required.

---

## Decisions / Tradeoffs

1. **Sentinel approach over similarity threshold**: Cosine similarity thresholds are brittle (a low-similarity chunk may still be on-topic). Delegating relevance detection to the LLM via a prompt-level instruction is more accurate.

2. **`[NO_CONTEXT]` sentinel vs JSON**: A plain text prefix marker is simpler to parse than a JSON response, avoids requiring JSON mode in the API call, and is less likely to be prefixed with markdown formatting by the LLM.

3. **`use_general_knowledge` skips retrieval entirely**: When the user opts in, there's no point re-retrieving the same irrelevant chunks, so the pipeline skips vector search and uses `_NO_CONTEXT_SYSTEM` directly. This is faster and avoids the LLM seeing the same irrelevant context again.

4. **Choice card is transient**: The "Yes/No" buttons are rendered only for new out-of-context responses, not when reloading old messages from history. This is acceptable — the user can re-ask the question if needed.

5. **No new user bubble for general knowledge follow-up**: `sendAsGeneralKnowledge()` doesn't inject another user bubble. The original question bubble already exists in the thread; adding a duplicate would be confusing.
