"""
Focused auth regression test for profile password updates.

Run from project root:
  python tests/test_auth_profile_password.py
"""

from __future__ import annotations

import json
import os
import sys
import uuid


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


def check(response, *expected_statuses: int):
    if response.status_code not in expected_statuses:
        payload = response.get_json(silent=True) or response.get_data(as_text=True)
        formatted = (
            json.dumps(payload, indent=2)
            if isinstance(payload, dict)
            else str(payload)
        )
        fail(
            f"unexpected status {response.status_code}, expected {expected_statuses}\n"
            f"response={formatted}"
        )
    return response


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


app = create_app()
app.testing = True

with app.app_context():
    db.create_all()

client = app.test_client()

email = f"profile_{uuid.uuid4().hex[:8]}@tutor.local"
username = f"profile_{uuid.uuid4().hex[:8]}"
old_password = "old-pass-123"
new_password = "new-pass-456"

register_response = check(
    client.post(
        "/api/auth/register",
        json={"email": email, "username": username, "password": old_password},
    ),
    201,
)
register_payload = register_response.get_json()
access_token = register_payload["access_token"]
refresh_token = register_payload["refresh_token"]

login_response = check(
    client.post("/api/auth/login", json={"email": email, "password": old_password}),
    200,
)
login_payload = login_response.get_json()
access_token = login_payload["access_token"]
refresh_token = login_payload["refresh_token"]

check(
    client.post("/api/auth/refresh", headers=auth_header(refresh_token)),
    200,
)

me_response = check(client.get("/api/auth/me", headers=auth_header(access_token)), 200)
me_payload = me_response.get_json()
if me_payload["user"]["email"] != email or me_payload["user"]["username"] != username:
    fail("me endpoint did not return the registered user")

check(
    client.post(
        "/api/auth/password",
        headers=auth_header(access_token),
        json={"current_password": "wrong-password", "new_password": new_password},
    ),
    401,
)

check(
    client.post(
        "/api/auth/password",
        headers=auth_header(access_token),
        json={"current_password": old_password, "new_password": "short"},
    ),
    400,
)

check(
    client.post(
        "/api/auth/password",
        headers=auth_header(access_token),
        json={"current_password": old_password, "new_password": old_password},
    ),
    400,
)

check(
    client.post(
        "/api/auth/password",
        headers=auth_header(access_token),
        json={"current_password": old_password, "new_password": new_password},
    ),
    200,
)

check(
    client.post("/api/auth/login", json={"email": email, "password": old_password}),
    401,
)

new_login_response = check(
    client.post("/api/auth/login", json={"email": email, "password": new_password}),
    200,
)
new_access_token = new_login_response.get_json()["access_token"]
check(client.get("/api/auth/me", headers=auth_header(new_access_token)), 200)

other_email = f"profile_other_{uuid.uuid4().hex[:8]}@tutor.local"
other_password = "other-pass-123"
other_register = check(
    client.post(
        "/api/auth/register",
        json={"email": other_email, "password": other_password},
    ),
    201,
)
other_access_token = other_register.get_json()["access_token"]
check(
    client.post(
        "/api/auth/password",
        headers=auth_header(other_access_token),
        json={"current_password": new_password, "new_password": "other-pass-456"},
    ),
    401,
)
check(
    client.post(
        "/api/auth/login",
        json={"email": other_email, "password": other_password},
    ),
    200,
)

print("AUTH PROFILE PASSWORD TESTS PASSED")
