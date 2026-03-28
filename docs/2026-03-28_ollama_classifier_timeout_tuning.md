# 2026-03-28 Ollama Classifier And Embedding Timeout Tuning

## Task Summary

Adjusted the local Ollama generation path and wrapper embedding timeout after backend logs showed:
- classifier JSON parse failures on short prompts
- retrieval falling back to no-context because the embedding wrapper timed out at 30 seconds

Implemented fixes:
- defaulted Ollama generation requests to `reasoning_effort=none`
- updated the classifier request to use JSON response format plus `reasoning_effort=none`
- increased the wrapper embedding timeout default from 30s to 120s
- added matching non-secret values to the local `.env` and `.env.example`

## Files Created/Edited

Created:
- `docs/2026-03-28_ollama_classifier_timeout_tuning.md`

Edited:
- `.env`
- `.env.example`
- `backend/app/config.py`
- `backend/app/services/router/classifier.py`
- `backend/app/services/wrapper/client.py`

## Endpoints Added/Changed

No API endpoints were added or removed.

Behavior changed indirectly for existing generation calls:
- all Ollama-backed `chat_completions` calls now default to `reasoning_effort=none` unless explicitly overridden
- classifier requests now ask Ollama for JSON mode output instead of plain free-form text

## DB Schema/Migration Changes

None.

## Decisions/Tradeoffs

- Kept the classifier feature instead of removing it, but made the request shape deterministic enough for a thinking-capable local model.
- Used config-driven defaults so the behavior applies consistently across chat, quiz generation, and summaries without patching each caller separately.
- Increased `WRAPPER_TIMEOUT` to 120 seconds rather than changing retrieval logic, because the logged failure was a timeout from the upstream embedding provider path rather than a parsing or vector issue.

## Verification

Passed:
- backend syntax check via `compileall`
- direct classifier call inside Flask app context:
  - result: `{'category': 'general', 'model': 'qwen3.5:0.8b', 'confidence': 'high', 'method': 'classifier'}`

Configured locally:
- `.env` now includes `WRAPPER_TIMEOUT=120`
- `.env` now includes `OLLAMA_REASONING_EFFORT=none`

Not fully verified in this run:
- live wrapper embedding round-trip was not re-run end-to-end from the app, so the timeout increase is configured but still depends on the actual responsiveness of the external wrapper service at runtime
