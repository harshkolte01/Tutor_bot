"""
Centralized AI gateway for generation and embeddings.

Architecture rule: every AI call in this project MUST go through this module.
No Flask route may contact an AI provider directly.

Provider split:
  - chat / quiz / summarization generation -> Ollama
  - embeddings -> wrapper service
"""

from __future__ import annotations

import logging
from typing import Optional

import requests
from flask import current_app

from app.services.wrapper.retry import call_with_retry

log = logging.getLogger(__name__)

DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434/v1"
DEFAULT_OLLAMA_API_KEY = "ollama"
DEFAULT_OLLAMA_MODEL = "qwen3.5:0.8b"
DEFAULT_OLLAMA_REASONING_EFFORT = "none"
DEFAULT_WRAPPER_EMBEDDING_MODEL = "gemini/gemini-embedding-001"


class WrapperError(Exception):
    """
    Normalized error raised by the AI gateway for all failure modes.

    Attributes
    ----------
    status_code : int or None
        HTTP status that triggered the error (None for network errors)
    upstream : str
        Raw error body / exception message from upstream
    """

    def __init__(self, message: str, status_code: Optional[int] = None, upstream: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.upstream = upstream

    def __repr__(self):
        return f"WrapperError({self.args[0]!r}, status_code={self.status_code})"


class _HTTPProviderClient:
    """Thin JSON-over-HTTP client for one upstream provider."""

    def __init__(
        self,
        *,
        provider_name: str,
        base_url: str,
        key: str = "",
        timeout: int = 30,
        max_retries: int = 3,
        base_delay: float = 1.0,
        require_key: bool = False,
        key_name: str = "API key",
    ):
        if not base_url:
            raise ValueError(f"{provider_name} base URL is not set")
        if require_key and not key:
            raise ValueError(f"{key_name} is not set")

        self._provider_name = provider_name
        self._base_url = base_url.rstrip("/")
        self._headers = {"Content-Type": "application/json"}
        if key:
            self._headers["Authorization"] = f"Bearer {key}"
        self._timeout = timeout
        self._max_retries = max_retries
        self._base_delay = base_delay

    def post_json(self, path: str, payload: dict, max_retries: Optional[int] = None) -> dict:
        url = self._base_url + path
        retries = self._max_retries if max_retries is None else max_retries

        def do_request():
            return requests.post(
                url,
                json=payload,
                headers=self._headers,
                timeout=self._timeout,
            )

        try:
            response = call_with_retry(
                do_request,
                max_retries=retries,
                base_delay=self._base_delay,
            )
        except requests.exceptions.Timeout:
            raise WrapperError(
                f"{self._provider_name} request to {path} timed out after {self._timeout}s",
                status_code=None,
                upstream="timeout",
            )
        except requests.exceptions.ConnectionError as exc:
            raise WrapperError(
                f"Connection error calling {self._provider_name} {path}: {exc}",
                status_code=None,
                upstream=str(exc),
            )
        except requests.exceptions.RequestException as exc:
            raise WrapperError(
                f"Network error calling {self._provider_name} {path}: {exc}",
                status_code=None,
                upstream=str(exc),
            )

        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = response.text
            raise WrapperError(
                f"{self._provider_name} returned {response.status_code} for {path}",
                status_code=response.status_code,
                upstream=str(body),
            )

        try:
            return response.json()
        except Exception as exc:
            raise WrapperError(
                f"Invalid JSON from {self._provider_name} at {path}: {exc}",
                status_code=response.status_code,
                upstream=response.text,
            )


class AIClient:
    """Gateway client that routes generation and embedding calls to different providers."""

    def __init__(
        self,
        *,
        generation_config: dict,
        embedding_config: dict,
    ):
        self._generation_config = generation_config
        self._embedding_config = embedding_config
        self._generation_client: Optional[_HTTPProviderClient] = None
        self._embedding_client: Optional[_HTTPProviderClient] = None

    def _get_generation_client(self) -> _HTTPProviderClient:
        if self._generation_client is None:
            self._generation_client = _HTTPProviderClient(**self._generation_config)
        return self._generation_client

    def _get_embedding_client(self) -> _HTTPProviderClient:
        if self._embedding_client is None:
            self._embedding_client = _HTTPProviderClient(**self._embedding_config)
        return self._embedding_client

    def chat_completions(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        max_retries: Optional[int] = None,
        response_format: Optional[dict] = None,
        reasoning_effort: Optional[str] = None,
    ) -> dict:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if response_format is not None:
            payload["response_format"] = response_format
        resolved_reasoning_effort = reasoning_effort
        if resolved_reasoning_effort is None:
            resolved_reasoning_effort = get_generation_reasoning_effort()
        if resolved_reasoning_effort:
            payload["reasoning_effort"] = resolved_reasoning_effort

        log.debug("generation chat_completions model=%s messages_count=%d", model, len(messages))
        return self._get_generation_client().post_json(
            "/chat/completions",
            payload,
            max_retries=max_retries,
        )

    def embeddings(self, model: str, input) -> dict:
        payload = {"model": model, "input": input}
        log.debug(
            "embedding provider embeddings model=%s input_type=%s",
            model,
            type(input).__name__,
        )
        return self._get_embedding_client().post_json("/v1/embeddings", payload)


_client: Optional[AIClient] = None
_client_signature: Optional[tuple] = None


def get_generation_model() -> str:
    model = str(current_app.config.get("OLLAMA_MODEL") or "").strip()
    return model or DEFAULT_OLLAMA_MODEL


def get_generation_fallback_model() -> Optional[str]:
    fallback = str(current_app.config.get("OLLAMA_FALLBACK_MODEL") or "").strip()
    if not fallback or fallback == get_generation_model():
        return None
    return fallback


def get_generation_reasoning_effort() -> str:
    effort = str(current_app.config.get("OLLAMA_REASONING_EFFORT") or "").strip().lower()
    return effort or DEFAULT_OLLAMA_REASONING_EFFORT


def get_embedding_model() -> str:
    model = str(current_app.config.get("WRAPPER_EMBEDDING_MODEL") or "").strip()
    return model or DEFAULT_WRAPPER_EMBEDDING_MODEL


def get_client() -> AIClient:
    """
    Return the module-level AI gateway singleton.

    Generation config:
        OLLAMA_BASE_URL
        OLLAMA_API_KEY      (optional for local Ollama)
        OLLAMA_TIMEOUT      (default 120)
        OLLAMA_MAX_RETRIES  (default 1)
        OLLAMA_BASE_DELAY   (default 0.5)

    Embedding config:
        WRAPPER_BASE_URL
        WRAPPER_KEY
        WRAPPER_TIMEOUT      (default 30)
        WRAPPER_MAX_RETRIES  (default 3)
        WRAPPER_BASE_DELAY   (default 1.0)

    Must be called inside a Flask application context.
    """
    global _client, _client_signature

    cfg = current_app.config
    signature = (
        cfg.get("OLLAMA_BASE_URL"),
        cfg.get("OLLAMA_API_KEY"),
        int(cfg.get("OLLAMA_TIMEOUT", 120)),
        int(cfg.get("OLLAMA_MAX_RETRIES", 1)),
        float(cfg.get("OLLAMA_BASE_DELAY", 0.5)),
        cfg.get("WRAPPER_BASE_URL"),
        cfg.get("WRAPPER_KEY"),
        int(cfg.get("WRAPPER_TIMEOUT", 30)),
        int(cfg.get("WRAPPER_MAX_RETRIES", 3)),
        float(cfg.get("WRAPPER_BASE_DELAY", 1.0)),
    )

    if _client is None or _client_signature != signature:
        _client = AIClient(
            generation_config={
                "provider_name": "Ollama",
                "base_url": cfg.get("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_BASE_URL,
                "key": cfg.get("OLLAMA_API_KEY") or DEFAULT_OLLAMA_API_KEY,
                "timeout": int(cfg.get("OLLAMA_TIMEOUT", 120)),
                "max_retries": int(cfg.get("OLLAMA_MAX_RETRIES", 1)),
                "base_delay": float(cfg.get("OLLAMA_BASE_DELAY", 0.5)),
                "require_key": False,
                "key_name": "OLLAMA_API_KEY",
            },
            embedding_config={
                "provider_name": "embedding wrapper",
                "base_url": cfg.get("WRAPPER_BASE_URL", ""),
                "key": cfg.get("WRAPPER_KEY", ""),
                "timeout": int(cfg.get("WRAPPER_TIMEOUT", 30)),
                "max_retries": int(cfg.get("WRAPPER_MAX_RETRIES", 3)),
                "base_delay": float(cfg.get("WRAPPER_BASE_DELAY", 1.0)),
                "require_key": True,
                "key_name": "WRAPPER_KEY",
            },
        )
        _client_signature = signature

    return _client
