# 2026-02-23 - AGENTS Guide Rewrite

## Task

Review and rewrite `AGENTS.MD` so agents can execute work consistently with clear rules and handoff expectations.

## Files Updated

1. `AGENTS.MD` (rewritten)
2. `docs/2026-02-23_agents_md_rewrite.md` (this memory file)

## Why Rewrite Was Needed

The previous guide had two major issues:
- readability/clarity gaps for agent execution
- stale/inconsistent details that could cause confusion during implementation

## What Changed In `AGENTS.MD`

- Replaced the file with a clean, structured operating guide.
- Added a strict startup checklist.
- Added explicit architecture guardrails:
  - frontend HTTP only via `frontend/components/api_client.py`
  - backend LLM calls only via `backend/app/services/wrapper/client.py`
  - SQLAlchemy-only DB access in app code
- Added migration policy and target migration sequence.
- Added required environment variable section and secret-handling rules.
- Added definition-of-done checklist for every task.
- Added testing expectations (backend boot, frontend boot, auth regression checks).
- Added wrapper usage policy and target model-routing policy.
- Added common mistakes section.
- Added a copy-paste handoff template for assigning step-by-step tasks to agents.
- Aligned implementation snapshot to current repo state (Phase 1-2 done, Phase 3-6 pending).

## Endpoint Changes

- None (documentation-only change).

## Database Schema Changes

- None (documentation-only change).

## Decisions

- Kept the guide concise but strict so multiple agents can follow it without ambiguity.
- Kept instructions execution-focused and compatible with `plan.md` sequencing.