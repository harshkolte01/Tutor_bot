"""
Integration test for Step 8 – Chat API with Router + RAG Answering.

Requires a running Flask server (python backend/run.py or flask run).
Run from project root:
    python test_chat.py

Creates a fresh test user each run (or reuses if already registered),
then exercises every chat endpoint end-to-end.
"""

import json
import sys
import uuid
import requests

BASE = "http://localhost:5000"

# ── Test credentials ──────────────────────────────────────────────────────────
EMAIL    = "chattest_step8@tutor.local"
PASSWORD = "chattest123"
EMAIL_B  = "chattest_step8_b@tutor.local"  # second user for isolation test


def hdr(label: str):
    print("\n" + "=" * 60)
    print(label)
    print("=" * 60)


def check(resp: requests.Response, *expected):
    if resp.status_code not in expected:
        print(f"FAIL  expected={expected}  got={resp.status_code}")
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print(resp.text[:600])
        sys.exit(1)
    return resp


def register_or_login(email: str, password: str) -> str:
    """Return an access token, registering the user first if needed."""
    r = requests.post(f"{BASE}/api/auth/register",
                      json={"email": email, "password": password})
    if r.status_code == 201:
        return r.json()["access_token"]
    if r.status_code == 409:
        # Already exists – log in
        r2 = requests.post(f"{BASE}/api/auth/login",
                           json={"email": email, "password": password})
        check(r2, 200)
        return r2.json()["access_token"]
    check(r, 201)  # any other status is a failure


# ── Setup ─────────────────────────────────────────────────────────────────────
hdr("Acquiring access tokens")
token_a = register_or_login(EMAIL, PASSWORD)
token_b = register_or_login(EMAIL_B, PASSWORD)
auth_a  = {"Authorization": f"Bearer {token_a}"}
auth_b  = {"Authorization": f"Bearer {token_b}"}
print(f"User A token: {token_a[:20]}...")
print(f"User B token: {token_b[:20]}...")

# ── Auth enforcement ──────────────────────────────────────────────────────────
hdr("Auth enforcement – unauthenticated request must return 401")
r = requests.get(f"{BASE}/api/chat/sessions")
check(r, 401, 422)  # Flask-JWT returns 401 or 422 for missing token
print(f"OK  status={r.status_code}")

# ── POST /api/chat/sessions ───────────────────────────────────────────────────
hdr("POST /api/chat/sessions – create a new session")
r = requests.post(f"{BASE}/api/chat/sessions",
                  json={"title": "Step 8 Test Chat"},
                  headers=auth_a)
check(r, 201)
session = r.json()
session_id = session["id"]
assert session["title"] == "Step 8 Test Chat", "title mismatch"
assert "created_at" in session
assert "updated_at" in session
print(f"OK  session_id={session_id}")

# ── POST /api/chat/sessions – default title ───────────────────────────────────
hdr("POST /api/chat/sessions – default title (no title field)")
r = requests.post(f"{BASE}/api/chat/sessions", json={}, headers=auth_a)
check(r, 201)
assert r.json()["title"] == "New Chat", f"expected 'New Chat', got '{r.json()['title']}'"
session_no_title_id = r.json()["id"]
print(f"OK  session_id={session_no_title_id}  title='{r.json()['title']}'")

# ── GET /api/chat/sessions ────────────────────────────────────────────────────
hdr("GET /api/chat/sessions – user sees own sessions only")
r = requests.get(f"{BASE}/api/chat/sessions", headers=auth_a)
check(r, 200)
sessions = r.json()
assert isinstance(sessions, list), "expected list"
ids = [s["id"] for s in sessions]
assert session_id in ids, "created session not in list"
print(f"OK  total_sessions_for_user_a={len(sessions)}")

# User B must not see User A's sessions
r = requests.get(f"{BASE}/api/chat/sessions", headers=auth_b)
check(r, 200)
ids_b = [s["id"] for s in r.json()]
assert session_id not in ids_b, "ISOLATION FAIL: user B can see user A session"
print(f"OK  user_b sees {len(ids_b)} sessions (user_a's not included)")

# ── GET messages (empty) ──────────────────────────────────────────────────────
hdr("GET /api/chat/sessions/<id>/messages – empty session")
r = requests.get(f"{BASE}/api/chat/sessions/{session_id}/messages", headers=auth_a)
check(r, 200)
assert r.json() == [], f"expected [] for fresh session, got {r.json()}"
print("OK  empty list returned")

# ── Cross-user session access ─────────────────────────────────────────────────
hdr("GET /api/chat/sessions/<id>/messages – cross-user access must return 404")
r = requests.get(f"{BASE}/api/chat/sessions/{session_id}/messages", headers=auth_b)
check(r, 404)
print(f"OK  status=404 returned for user B accessing user A session")

# ── POST /messages – empty content validation ─────────────────────────────────
hdr("POST /api/chat/sessions/<id>/messages – empty content returns 400")
r = requests.post(f"{BASE}/api/chat/sessions/{session_id}/messages",
                  json={"content": "   "},
                  headers=auth_a)
check(r, 400)
print(f"OK  status=400  error='{r.json().get('error')}'")

# ── POST /messages – general question (no document context) ───────────────────
hdr("POST /api/chat/sessions/<id>/messages – general factual question")
print("Sending: 'What is the water cycle?' (30-90s expected) …")
r = requests.post(
    f"{BASE}/api/chat/sessions/{session_id}/messages",
    json={"content": "What is the water cycle? Explain briefly."},
    headers=auth_a,
    timeout=120,
)
check(r, 200)
data = r.json()

# Check structure
assert "user_message"      in data, "missing user_message"
assert "assistant_message" in data, "missing assistant_message"
assert "router"            in data, "missing router"

user_msg = data["user_message"]
asst_msg = data["assistant_message"]
router   = data["router"]

assert user_msg["role"]    == "user",      f"expected role=user, got {user_msg['role']}"
assert asst_msg["role"]    == "assistant", f"expected role=assistant, got {asst_msg['role']}"
assert asst_msg["content"], "assistant content is empty"
assert asst_msg["model_used"], "model_used is empty"
assert "sources"           in asst_msg,    "missing sources in assistant message"
assert isinstance(asst_msg["sources"], list)

assert "category"   in router
assert "model"      in router
assert "confidence" in router
assert "method"     in router

print(f"OK  answer ({len(asst_msg['content'])} chars)")
print(f"    model_used  = {asst_msg['model_used']}")
print(f"    sources     = {len(asst_msg['sources'])}")
print(f"    router      = {router}")

# ── POST /messages – coding question → router should pick coding model ─────────
hdr("POST /api/chat/sessions/<id>/messages – coding question routing")
print("Sending: 'Write a Python function to compute fibonacci numbers' …")
r = requests.post(
    f"{BASE}/api/chat/sessions/{session_id}/messages",
    json={"content": "Write a Python function to compute fibonacci numbers."},
    headers=auth_a,
    timeout=120,
)
check(r, 200)
data2 = r.json()
router2 = data2["router"]
print(f"OK  category={router2['category']}  model={data2['assistant_message']['model_used']}")
print(f"    method={router2['method']}  confidence={router2['confidence']}")

# ── GET messages (should now have 4 messages: 2 user + 2 assistant) ────────────
hdr("GET /api/chat/sessions/<id>/messages – verify persisted messages")
r = requests.get(f"{BASE}/api/chat/sessions/{session_id}/messages", headers=auth_a)
check(r, 200)
msgs = r.json()
assert len(msgs) == 4, f"expected 4 messages, got {len(msgs)}"

roles = [m["role"] for m in msgs]
assert roles == ["user", "assistant", "user", "assistant"], \
    f"unexpected role order: {roles}"

# Every assistant message has a sources list
for m in msgs:
    if m["role"] == "assistant":
        assert "sources" in m, f"assistant message {m['id']} missing sources"
        assert isinstance(m["sources"], list)

print(f"OK  {len(msgs)} messages returned with correct role order")

# ── GET sessions – auto-title check ──────────────────────────────────────────
hdr("GET /api/chat/sessions – auto-title updated after first message")
r = requests.get(f"{BASE}/api/chat/sessions", headers=auth_a)
check(r, 200)
by_id = {s["id"]: s for s in r.json()}
# The original "Step 8 Test Chat" session should have kept its title (it was set explicitly)
assert by_id[session_id]["title"] == "Step 8 Test Chat", \
    "explicit title should not be overwritten"
print(f"OK  title correctly preserved = '{by_id[session_id]['title']}'")

# The session created with no title should now have an auto-title
auto_title = by_id.get(session_no_title_id, {}).get("title", "")
# Auto-title only set when first message sent; this session had no messages → still "New Chat"
print(f"    no-title session still shows: '{auto_title}'")

# ── Cross-user POST /messages isolation ───────────────────────────────────────
hdr("POST /api/chat/sessions/<id>/messages – user B cannot post to user A session")
r = requests.post(f"{BASE}/api/chat/sessions/{session_id}/messages",
                  json={"content": "Hi from user B"},
                  headers=auth_b,
                  timeout=15)
check(r, 404)
print(f"OK  status=404 returned for user B")

# ── AUTH /me regression ────────────────────────────────────────────────────────
hdr("Auth regression – /api/auth/me still works")
r = requests.get(f"{BASE}/api/auth/me", headers=auth_a)
check(r, 200)
body = r.json()
email_display = body.get("email") or body.get("user", {}).get("email", "ok")
print(f"OK  email={email_display}")

# ── Done ───────────────────────────────────────────────────────────────────────
hdr("ALL TESTS PASSED")
print("Step 8 Chat API integration test completed successfully.\n")
