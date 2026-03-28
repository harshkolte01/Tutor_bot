"""
Direct connectivity check for the configured Ollama chat endpoint.

Run from project root:
    python tests/test_ollama_direct_chat.py

This script:
  - loads OLLAMA_* settings from .env
  - calls the configured OpenAI-compatible chat completions URL directly
  - prints HTTP status, model, latency, and assistant response
  - exits non-zero on connectivity or response-shape failures
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - fallback for minimal environments
    load_dotenv = None


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def info(message: str) -> None:
    print(message)


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def load_env() -> None:
    if load_dotenv is not None:
        load_dotenv(ENV_FILE)
        return

    if not ENV_FILE.exists():
        return

    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    load_env()

    base_url = (os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434/v1").rstrip("/")
    api_key = os.getenv("OLLAMA_API_KEY") or "ollama"
    model = os.getenv("OLLAMA_MODEL") or "qwen3.5:0.8b"
    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": "Reply with exactly one short line that confirms you are working.",
            }
        ],
        "temperature": 0,
        "max_tokens": 64,
        # Thinking-capable models like qwen3.5 can spend the whole token budget
        # in the reasoning field, so disable reasoning for a simple health check.
        "reasoning_effort": "none",
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    info("=" * 60)
    info("OLLAMA DIRECT CHAT CHECK")
    info("=" * 60)
    info(f"URL: {url}")
    info(f"Model: {model}")

    started = time.perf_counter()
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
    except requests.RequestException as exc:
        fail(f"request failed: {exc}")
    elapsed_ms = (time.perf_counter() - started) * 1000

    info(f"HTTP status: {response.status_code}")
    info(f"Elapsed: {elapsed_ms:.0f} ms")

    try:
        body = response.json()
    except ValueError:
        fail(f"response was not valid JSON: {response.text[:500]}")

    if response.status_code >= 400:
        formatted = json.dumps(body, indent=2) if isinstance(body, dict) else str(body)
        fail(f"upstream returned error JSON:\n{formatted}")

    try:
        assistant_text = body["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError):
        formatted = json.dumps(body, indent=2)
        fail(f"response JSON did not match chat-completions shape:\n{formatted}")

    reported_model = body.get("model") or "(missing model)"
    finish_reason = body.get("choices", [{}])[0].get("finish_reason", "(missing finish_reason)")
    info(f"Reported model: {reported_model}")
    info(f"Finish reason: {finish_reason}")
    info("Assistant reply:")
    info(assistant_text or "(empty)")

    if not assistant_text:
        fail("assistant reply was empty")

    info("PASS: Ollama chat endpoint responded successfully.")


if __name__ == "__main__":
    main()
