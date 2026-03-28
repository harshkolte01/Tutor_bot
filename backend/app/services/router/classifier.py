"""
LLM-based message classifier.

Called when heuristics returns confidence="low" (uncertain).
Uses the configured Ollama generation model for local classification.

Return value
------------
dict with keys:
    category  : str  - "coding" | "reasoning" | "general"
    model     : str  - selected generation model slug
    confidence: str  - "high" (LLM decided) | "fallback" (LLM failed)
    method    : str  - "classifier" | "classifier_fallback"
"""

from __future__ import annotations

import json
import logging

from app.services.wrapper.client import WrapperError, get_client, get_generation_model

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a query classifier for an AI tutoring system. "
    "Classify the user's message into exactly one of these categories:\n"
    "  coding    - the message is primarily about programming or code\n"
    "  reasoning - the message requires multi-step mathematical, logical, "
    "or scientific reasoning\n"
    "  general   - everything else (factual question, concept explanation, etc.)\n\n"
    "Respond ONLY with a JSON object on a single line, no markdown:\n"
    '{"category": "<coding|reasoning|general>"}'
)


def classify(message: str) -> dict:
    """
    Call the LLM classifier to categorize *message*.

    Falls back to "general" / configured generation model when the LLM call
    fails or returns an unrecognized category.
    """
    model = get_generation_model()

    try:
        client = get_client()
        resp = client.chat_completions(
            model=model,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": message},
            ],
            temperature=0.0,
            max_tokens=32,
            response_format={"type": "json_object"},
            reasoning_effort="none",
        )
        raw = resp["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("```")[-2] if raw.count("```") >= 2 else raw
            raw = raw.lstrip("json").strip()
        data = json.loads(raw)
        category = str(data.get("category", "general")).lower()
        if category not in {"coding", "reasoning", "general"}:
            category = "general"
        return {
            "category": category,
            "model": model,
            "confidence": "high",
            "method": "classifier",
        }

    except (WrapperError, KeyError, json.JSONDecodeError, Exception) as exc:
        log.warning("classifier failed, falling back to general: %s", exc)
        return {
            "category": "general",
            "model": model,
            "confidence": "fallback",
            "method": "classifier_fallback",
        }
