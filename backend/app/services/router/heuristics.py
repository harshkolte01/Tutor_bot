"""
Heuristic-based message router.

Inspects the user message using keyword patterns and returns a routing
decision without any LLM calls.

Return value
------------
dict with keys:
    category  : str  - "coding" | "reasoning" | "general" | "uncertain"
    model     : str | None  - model slug if confident, else None
    confidence: str  - "high" | "low"
    method    : str  - always "heuristics"
"""

from __future__ import annotations

import re

from app.services.wrapper.client import DEFAULT_OLLAMA_MODEL, get_generation_model

MODEL_DEFAULT = DEFAULT_OLLAMA_MODEL
MODEL_REASONING = DEFAULT_OLLAMA_MODEL
MODEL_CODING = DEFAULT_OLLAMA_MODEL
MODEL_CLASSIFY = DEFAULT_OLLAMA_MODEL

_CODING_KEYWORDS = re.compile(
    r"\b(code|coding|program|script|function|class|method|bug|debug|"
    r"algorithm|syntax|compile|runtime|exception|stack|array|list|dict|"
    r"javascript|python|java|c\+\+|typescript|sql|html|css|api|json|"
    r"git|github|docker|bash|shell|loop|variable|import|library|"
    r"framework|module|package|implement|refactor|test|unit test|"
    r"error|fix the code|write a|write the)\b",
    re.IGNORECASE,
)

_REASONING_KEYWORDS = re.compile(
    r"\b(prove|proof|derive|derivation|theorem|lemma|corollary|"
    r"explain why|reasoning|logic|infer|inference|hypothesis|"
    r"calculus|integral|derivative|equation|matrix|probability|"
    r"statistics|physics|chemistry|math|solve|step.?by.?step|"
    r"analyze|analysis|compare|evaluate|argue|argument)\b",
    re.IGNORECASE,
)


def route(message: str) -> dict:
    """
    Apply keyword heuristics to *message* and return a routing decision.

    Returns
    -------
    dict
        category   : "coding" | "reasoning" | "general" | "uncertain"
        model      : model slug (str) or None if uncertain
        confidence : "high" | "low"
        method     : "heuristics"
    """
    msg = message.strip()
    default_model = get_generation_model()
    if not msg:
        return _result("general", default_model, "high")

    coding_hits = len(_CODING_KEYWORDS.findall(msg))
    reasoning_hits = len(_REASONING_KEYWORDS.findall(msg))

    if coding_hits > 0 and coding_hits >= reasoning_hits:
        return _result("coding", default_model, "high")

    if reasoning_hits > 0:
        return _result("reasoning", default_model, "high")

    if len(msg.split()) < 6:
        return _result("uncertain", None, "low")

    return _result("general", default_model, "high")


def _result(category: str, model, confidence: str) -> dict:
    return {
        "category": category,
        "model": model,
        "confidence": confidence,
        "method": "heuristics",
    }
