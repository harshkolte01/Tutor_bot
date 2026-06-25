from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from time import monotonic, perf_counter
from urllib.parse import urljoin

from flask import current_app
import requests

_cache_lock = Lock()
_cache: dict[str, object] = {
    "expires_at": 0.0,
    "payload": None,
}


def get_ai_agent_status() -> dict:
    """
    Probe the wrapper with a plain HTTP request.

    The endpoint that calls this function is public, so this function never
    returns wrapper secrets or raw upstream error bodies. The frontend also
    stores the first connected state in sessionStorage so each browser session
    stops polling once it sees a 200.
    """
    now = monotonic()
    cached_payload = _cache.get("payload")
    if cached_payload and now < float(_cache.get("expires_at", 0.0)):
        return dict(cached_payload)

    with _cache_lock:
        now = monotonic()
        cached_payload = _cache.get("payload")
        if cached_payload and now < float(_cache.get("expires_at", 0.0)):
            return dict(cached_payload)

        payload = _probe_wrapper()
        ttl = _cache_ttl(payload)
        _cache["payload"] = payload
        _cache["expires_at"] = monotonic() + ttl
        return dict(payload)


def clear_ai_agent_status_cache() -> None:
    with _cache_lock:
        _cache["payload"] = None
        _cache["expires_at"] = 0.0


def _probe_wrapper() -> dict:
    started = perf_counter()
    checked_at = datetime.now(timezone.utc).isoformat()
    base_url = current_app.config.get("WRAPPER_BASE_URL")

    if not base_url:
        return _status_payload(
            ok=False,
            status="not_configured",
            message="AI agent connection is not configured.",
            checked_at=checked_at,
            latency_ms=_latency_ms(started),
        )

    status_url = _status_url(base_url)
    timeout = float(current_app.config.get("WRAPPER_STATUS_TIMEOUT", 45))

    try:
        response = requests.get(
            status_url,
            timeout=timeout,
            allow_redirects=True,
            headers={"Accept": "application/json,text/plain,*/*"},
        )
    except requests.exceptions.Timeout:
        return _status_payload(
            ok=False,
            status="waking",
            message="Connecting to AI agent. The Render service may be waking up.",
            checked_at=checked_at,
            latency_ms=_latency_ms(started),
        )
    except requests.exceptions.RequestException:
        return _status_payload(
            ok=False,
            status="waking",
            message="Connecting to AI agent. The Render service may be waking up.",
            checked_at=checked_at,
            latency_ms=_latency_ms(started),
        )

    if response.status_code == 200:
        return _status_payload(
            ok=True,
            status="connected",
            message="AI agent connected.",
            checked_at=checked_at,
            latency_ms=_latency_ms(started),
            upstream_status=response.status_code,
        )

    return _status_payload(
        ok=False,
        status=_http_status(response.status_code),
        message=_http_message(response.status_code),
        checked_at=checked_at,
        latency_ms=_latency_ms(started),
        upstream_status=response.status_code,
    )


def _status_url(base_url: str) -> str:
    path = current_app.config.get("WRAPPER_STATUS_PATH", "/")
    if not path:
        path = "/"
    if path.startswith("/"):
        return base_url.rstrip("/") + path
    return urljoin(base_url.rstrip("/") + "/", path)


def _http_status(status_code: int) -> str:
    if status_code in {502, 503, 504}:
        return "waking"
    return "unavailable"


def _http_message(status_code: int) -> str:
    if _http_status(status_code) == "waking":
        return "Connecting to AI agent. The Render service may be waking up."
    return (
        "AI agent responded but did not return 200 "
        f"(received {status_code})."
    )


def _status_payload(
    *,
    ok: bool,
    status: str,
    message: str,
    checked_at: str,
    latency_ms: int,
    upstream_status: int | None = None,
) -> dict:
    payload = {
        "ok": ok,
        "status": status,
        "message": message,
        "checked_at": checked_at,
        "latency_ms": latency_ms,
        "retry_after_sec": int(current_app.config.get("WRAPPER_STATUS_RETRY_SECONDS", 10)),
    }
    if upstream_status is not None:
        payload["upstream_status"] = upstream_status
    return payload


def _latency_ms(started: float) -> int:
    return max(0, int((perf_counter() - started) * 1000))


def _cache_ttl(payload: dict) -> int:
    if payload.get("ok"):
        return int(current_app.config.get("WRAPPER_STATUS_CACHE_SECONDS", 120))
    return int(current_app.config.get("WRAPPER_STATUS_RETRY_SECONDS", 10))
