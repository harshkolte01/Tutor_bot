"""
Focused test for the public AI agent status endpoint.

Run from project root:
  python tests/test_ai_status.py
"""

from __future__ import annotations

import json
import os
import sys

import requests


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("WRAPPER_BASE_URL", "https://wrapper.test")
os.environ.setdefault("WRAPPER_KEY", "test-wrapper-key")
os.environ["WRAPPER_STATUS_CACHE_SECONDS"] = "120"
os.environ["WRAPPER_STATUS_RETRY_SECONDS"] = "1"
os.environ["WRAPPER_STATUS_TIMEOUT"] = "1"
os.environ["WRAPPER_STATUS_PATH"] = "/"

from app import create_app  # noqa: E402
from app.services.wrapper import status as wrapper_status  # noqa: E402


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def check(response, expected_status: int = 200) -> dict:
    if response.status_code != expected_status:
        payload = response.get_json(silent=True) or response.get_data(as_text=True)
        formatted = (
            json.dumps(payload, indent=2)
            if isinstance(payload, dict)
            else str(payload)
        )
        fail(
            f"unexpected status {response.status_code}, expected {expected_status}\n"
            f"response={formatted}"
        )
    return response.get_json()


class FakeResponse:
    def __init__(self, status_code: int):
        self.status_code = status_code


class FakeGet:
    def __init__(self, status_code: int | None = 200, exception: Exception | None = None):
        self.status_code = status_code
        self.exception = exception
        self.calls = 0
        self.urls: list[str] = []

    def __call__(self, url, **_kwargs):
        self.calls += 1
        self.urls.append(url)
        if self.exception:
            raise self.exception
        return FakeResponse(self.status_code)


app = create_app()
app.testing = True
client = app.test_client()

original_get = wrapper_status.requests.get

try:
    connected_get = FakeGet(200)
    wrapper_status.clear_ai_agent_status_cache()
    wrapper_status.requests.get = connected_get

    connected_payload = check(client.get("/api/ai/status"))
    if connected_payload.get("status") != "connected" or not connected_payload.get("ok"):
        fail(f"expected connected payload, got {connected_payload}")
    if connected_payload.get("upstream_status") != 200:
        fail("connected payload did not include sanitized upstream status")

    cached_payload = check(client.get("/api/ai/status"))
    if connected_get.calls != 1:
        fail("status endpoint did not reuse connected cache")
    if cached_payload.get("status") != "connected":
        fail("cached status changed unexpectedly")

    timeout_get = FakeGet(exception=requests.exceptions.Timeout("cold start"))
    wrapper_status.clear_ai_agent_status_cache()
    wrapper_status.requests.get = timeout_get
    timeout_payload = check(client.get("/api/ai/status"))
    if timeout_payload.get("status") != "waking" or timeout_payload.get("ok"):
        fail(f"expected waking payload for timeout, got {timeout_payload}")
    if "upstream" in timeout_payload:
        fail("status endpoint leaked raw upstream details")

    waking_get = FakeGet(503)
    wrapper_status.clear_ai_agent_status_cache()
    wrapper_status.requests.get = waking_get
    waking_payload = check(client.get("/api/ai/status"))
    if waking_payload.get("status") != "waking" or waking_payload.get("ok"):
        fail(f"expected waking payload for 503, got {waking_payload}")

    unavailable_get = FakeGet(404)
    wrapper_status.clear_ai_agent_status_cache()
    wrapper_status.requests.get = unavailable_get
    unavailable_payload = check(client.get("/api/ai/status"))
    if unavailable_payload.get("status") != "unavailable" or unavailable_payload.get("ok"):
        fail(f"expected unavailable payload for 404, got {unavailable_payload}")

    wrapper_status.clear_ai_agent_status_cache()
    app.config["WRAPPER_BASE_URL"] = ""
    not_configured_payload = check(client.get("/api/ai/status"))
    if not_configured_payload.get("status") != "not_configured":
        fail(f"expected not_configured payload, got {not_configured_payload}")
finally:
    wrapper_status.requests.get = original_get
    wrapper_status.clear_ai_agent_status_cache()

print("AI STATUS TESTS PASSED")
