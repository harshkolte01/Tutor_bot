"""
Wrapper HTTP client for all AI calls (chat completions + embeddings).

Architecture rule: every LLM call in this project MUST go through this module.
No Flask route may contact an AI provider directly.

Usage:
    from app.services.wrapper.client import get_client

    client = get_client()
    result = client.chat_completions(
        model="routeway/glm-4.5-air:free",
        messages=[{"role": "user", "content": "Hello"}],
    )

`get_client()` returns a module-level singleton initialised from Flask app config
on first call. Import and use only inside a Flask application context.
"""

import logging
from typing import Optional

import requests
from flask import current_app

from app.services.wrapper.retry import call_with_retry

log = logging.getLogger(__name__)


# ── Exceptions ───────────────────────────────────────────────────────────────

class WrapperError(Exception):
    """
    Normalised error raised by WrapperClient for all failure modes.

    Attributes
    ----------
    status_code : int or None   HTTP status that triggered the error (None for network errors)
    upstream    : str           raw error body / exception message from upstream
    """

    def __init__(self, message: str, status_code: Optional[int] = None, upstream: str = ""):
        super().__init__(message)
        self.status_code = status_code
        self.upstream = upstream

    def __repr__(self):
        return f"WrapperError({self.args[0]!r}, status_code={self.status_code})"


# ── Client ───────────────────────────────────────────────────────────────────

class WrapperClient:
    """
    Thin HTTP client that talks to the AI wrapper service.

    Parameters
    ----------
    base_url    : str   wrapper base URL (no trailing slash)
    key         : str   bearer token
    timeout     : int   request timeout in seconds
    max_retries : int   retry attempts on 429/502/503/504
    base_delay  : float base backoff delay in seconds
    """

    def __init__(
        self,
        base_url: str,
        key: str,
        timeout: int = 30,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ):
        if not base_url:
            raise ValueError("WRAPPER_BASE_URL is not set")
        if not key:
            raise ValueError("WRAPPER_KEY is not set")

        self._base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        self._timeout = timeout
        self._max_retries = max_retries
        self._base_delay = base_delay

    # ── Public methods ───────────────────────────────────────────────────────

    def chat_completions(
        self,
        model: str,
        messages: list,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> dict:
        """
        Call POST /v1/chat/completions.

        Returns the parsed JSON response dict from the wrapper.
        Raises WrapperError on any failure.
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        log.debug("wrapper chat_completions model=%s messages_count=%d", model, len(messages))
        return self._post("/v1/chat/completions", payload)

    def embeddings(self, model: str, input) -> dict:
        """
        Call POST /v1/embeddings.

        `input` may be a str or list[str].
        Returns the parsed JSON response dict from the wrapper.
        Raises WrapperError on any failure.
        """
        payload = {"model": model, "input": input}
        log.debug(
            "wrapper embeddings model=%s input_type=%s",
            model,
            type(input).__name__,
        )
        return self._post("/v1/embeddings", payload)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _post(self, path: str, payload: dict) -> dict:
        url = self._base_url + path

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
                max_retries=self._max_retries,
                base_delay=self._base_delay,
            )
        except requests.exceptions.Timeout:
            raise WrapperError(
                f"Request to {path} timed out after {self._timeout}s",
                status_code=None,
                upstream="timeout",
            )
        except requests.exceptions.ConnectionError as exc:
            raise WrapperError(
                f"Connection error calling {path}: {exc}",
                status_code=None,
                upstream=str(exc),
            )
        except requests.exceptions.RequestException as exc:
            raise WrapperError(
                f"Network error calling {path}: {exc}",
                status_code=None,
                upstream=str(exc),
            )

        if response.status_code >= 400:
            try:
                body = response.json()
            except Exception:
                body = response.text
            raise WrapperError(
                f"Wrapper returned {response.status_code} for {path}",
                status_code=response.status_code,
                upstream=str(body),
            )

        try:
            return response.json()
        except Exception as exc:
            raise WrapperError(
                f"Invalid JSON from wrapper at {path}: {exc}",
                status_code=response.status_code,
                upstream=response.text,
            )


# ── Singleton ────────────────────────────────────────────────────────────────

_client: Optional[WrapperClient] = None


def get_client() -> WrapperClient:
    """
    Return the module-level WrapperClient singleton.

    Initialises on first call using current Flask app config:
        WRAPPER_BASE_URL
        WRAPPER_KEY
        WRAPPER_TIMEOUT      (default 30)
        WRAPPER_MAX_RETRIES  (default 3)
        WRAPPER_BASE_DELAY   (default 1.0)

    Must be called inside a Flask application context.
    """
    global _client
    if _client is None:
        cfg = current_app.config
        _client = WrapperClient(
            base_url=cfg["WRAPPER_BASE_URL"],
            key=cfg["WRAPPER_KEY"],
            timeout=int(cfg.get("WRAPPER_TIMEOUT", 30)),
            max_retries=int(cfg.get("WRAPPER_MAX_RETRIES", 3)),
            base_delay=float(cfg.get("WRAPPER_BASE_DELAY", 1.0)),
        )
    return _client
