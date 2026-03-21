"""
End-to-end chat test with PDF document context.

Flow:
  1. Login (or register) a dedicated test user
  2. Upload Python1.pdf and wait for ingestion to complete
     (skips re-upload if a ready ingestion already exists for this user)
  3. Create a chat session
  4. Ask one general question about the PDF content  → expect PDF citations
  5. Ask one coding question from the PDF content   → expect coding model routed

Run from project root (Flask server must be running):
    python test_chat_with_pdf.py
"""

import json
import sys
import time
import requests

BASE    = "http://localhost:5000"
PDF     = r"C:\Users\jains\OneDrive\Desktop\clg_proj\Tutor_bot\PDF\Python1.pdf"
EMAIL   = "testdoc@tutor.local"   # has Python1.pdf already ingested via test_documents.py
PASSWORD = "doctest123"


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def register_or_login(email: str, password: str) -> dict:
    """Return full auth response (access_token, user …)."""
    r = requests.post(f"{BASE}/api/auth/register",
                      json={"email": email, "password": password})
    if r.status_code == 201:
        print("Registered new user.")
        return r.json()
    if r.status_code == 409:
        print("User already exists — logging in.")
        r2 = requests.post(f"{BASE}/api/auth/login",
                           json={"email": email, "password": password})
        check(r2, 200)
        return r2.json()
    check(r, 201)


def wait_for_ingestion(doc_id: str, ing_id: str, auth: dict, timeout: int = 180) -> str:
    """Poll ingestion status until 'ready' or 'failed'. Returns final status."""
    url = f"{BASE}/api/documents/{doc_id}/ingestions/{ing_id}/status"
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = requests.get(url, headers=auth)
        check(r, 200)
        status = r.json().get("status", "")
        print(f"  ingestion status: {status}")
        if status == "ready":
            return "ready"
        if status == "failed":
            print(f"  error: {r.json().get('error_message')}")
            return "failed"
        time.sleep(5)
    return "timeout"


# ═════════════════════════════════════════════════════════════════════════════
# 1.  LOGIN
# ═════════════════════════════════════════════════════════════════════════════
hdr("STEP 1 – Login / Register")
auth_resp = register_or_login(EMAIL, PASSWORD)
token = auth_resp["access_token"]
auth  = {"Authorization": f"Bearer {token}"}
print(f"Token: {token[:20]}…")

# ═════════════════════════════════════════════════════════════════════════════
# 2.  UPLOAD Python1.pdf  (skip if already ingested)
# ═════════════════════════════════════════════════════════════════════════════
hdr("STEP 2 – Upload Python1.pdf (or reuse existing)")

# Check existing docs first
existing = requests.get(f"{BASE}/api/documents", headers=auth)
check(existing, 200)
body = existing.json()
# API returns {"documents": [...]} or a plain list depending on version
docs = body.get("documents", body) if isinstance(body, dict) else body

doc_id = None
for d in docs:
    # current_ingestion_id is non-null only when ingestion completed successfully
    if (
        "python" in d.get("title", "").lower()
        and not d.get("is_deleted", False)
        and d.get("current_ingestion_id")
    ):
        doc_id = d["id"]
        print(f"Reusing already-ingested document: {d['title']} (id={doc_id})")
        break

if doc_id is None:
    print("No ready Python PDF found — uploading Python1.pdf …")
    print("Ingestion runs synchronously — this may take 30–120 seconds.")
    with open(PDF, "rb") as f:
        r = requests.post(
            f"{BASE}/api/documents/upload",
            headers=auth,
            files={"file": ("Python1.pdf", f, "application/pdf")},
            timeout=300,
        )
    check(r, 201, 202)
    upload_data = r.json()
    doc_id = upload_data["document"]["id"]
    ing_id = upload_data["ingestion"]["id"]
    print(f"Uploaded  doc_id={doc_id}  ing_id={ing_id}")

    if r.status_code == 202:
        print("Polling ingestion status …")
        final_status = wait_for_ingestion(doc_id, ing_id, auth)
        if final_status != "ready":
            print(f"Ingestion ended with status '{final_status}' — aborting.")
            sys.exit(1)
    else:
        print(f"Ingestion complete (synchronous).  status={upload_data['ingestion']['status']}")

# ═════════════════════════════════════════════════════════════════════════════
# 3.  CREATE CHAT SESSION
# ═════════════════════════════════════════════════════════════════════════════
hdr("STEP 3 – Create chat session")
r = requests.post(
    f"{BASE}/api/chat/sessions",
    json={"title": "Python1 PDF Chat Test"},
    headers=auth,
)
check(r, 201)
session_id = r.json()["id"]
print(f"Session created: {session_id}")


# ═════════════════════════════════════════════════════════════════════════════
# 4.  GENERAL QUESTION from the PDF
# ═════════════════════════════════════════════════════════════════════════════
hdr("STEP 4 – General question about Python (from PDF context)")
GENERAL_Q = "What is Python and what are its main features as described in the document?"
print(f"Question: {GENERAL_Q!r}")
print("Sending … (may take up to 60s)")

r = requests.post(
    f"{BASE}/api/chat/sessions/{session_id}/messages",
    json={"content": GENERAL_Q},
    headers=auth,
    timeout=120,
)
check(r, 200)
data1 = r.json()

user_msg1 = data1["user_message"]
asst_msg1 = data1["assistant_message"]
router1   = data1["router"]

# Structural checks
assert user_msg1["role"] == "user",      "user message role wrong"
assert asst_msg1["role"] == "assistant", "assistant message role wrong"
assert asst_msg1["content"],             "assistant answer is empty"
assert asst_msg1["model_used"],          "model_used is missing"
assert isinstance(asst_msg1["sources"], list), "sources must be a list"

print(f"\nAnswer ({len(asst_msg1['content'])} chars):")
print("-" * 40)
print(asst_msg1["content"][:600], "…" if len(asst_msg1["content"]) > 600 else "")
print("-" * 40)
print(f"Model used : {asst_msg1['model_used']}")
print(f"Router     : category={router1['category']}  method={router1['method']}  confidence={router1['confidence']}")
print(f"Sources    : {len(asst_msg1['sources'])} chunk(s) cited")

if asst_msg1["sources"]:
    print("Citations:")
    for i, s in enumerate(asst_msg1["sources"], 1):
        score   = s.get("similarity_score", 0)
        snippet = (s.get("snippet") or "")[:80]
        print(f"  [{i}] chunk_id={s['chunk_id']}  score={score:.4f}  snippet={snippet!r}…")
else:
    print("  (no chunk citations — embedding retrieval returned no results)")

# The general question may still be classified as coding if it mentions Python —
# allow any category here; routing correctness is asserted in the coding step.
print(f"OK  general question answer received  (router category='{router1['category']}')")


# ═════════════════════════════════════════════════════════════════════════════
# 5.  CODING QUESTION from the PDF
# ═════════════════════════════════════════════════════════════════════════════
hdr("STEP 5 – Coding question from PDF content")
CODING_Q = (
    "Based on the document, write a Python function that demonstrates "
    "the use of variables and basic data types like int, float, and string."
)
print(f"Question: {CODING_Q!r}")
print("Sending … (may take up to 90s)")

r = requests.post(
    f"{BASE}/api/chat/sessions/{session_id}/messages",
    json={"content": CODING_Q},
    headers=auth,
    timeout=150,
)
check(r, 200)
data2 = r.json()

user_msg2 = data2["user_message"]
asst_msg2 = data2["assistant_message"]
router2   = data2["router"]

assert user_msg2["role"] == "user",      "user message role wrong"
assert asst_msg2["role"] == "assistant", "assistant message role wrong"
assert asst_msg2["content"],             "assistant coding answer is empty"
assert isinstance(asst_msg2["sources"], list)

print(f"\nCoding Answer ({len(asst_msg2['content'])} chars):")
print("-" * 40)
print(asst_msg2["content"][:800], "…" if len(asst_msg2["content"]) > 800 else "")
print("-" * 40)
print(f"Model used : {asst_msg2['model_used']}")
print(f"Router     : category={router2['category']}  method={router2['method']}  confidence={router2['confidence']}")
print(f"Sources    : {len(asst_msg2['sources'])} chunk(s) cited")

# Routing must resolve to coding model
assert router2["category"] == "coding", \
    f"Expected category='coding' for coding question, got '{router2['category']}'"
print("OK  router correctly identified coding question")

if asst_msg2["sources"]:
    print("Citations:")
    for i, s in enumerate(asst_msg2["sources"], 1):
        score   = s.get("similarity_score", 0)
        snippet = (s.get("snippet") or "")[:80]
        print(f"  [{i}] chunk_id={s['chunk_id']}  score={score:.4f}  snippet={snippet!r}…")


# ═════════════════════════════════════════════════════════════════════════════
# 6.  VERIFY MESSAGE HISTORY
# ═════════════════════════════════════════════════════════════════════════════
hdr("STEP 6 – Verify full message history")
r = requests.get(
    f"{BASE}/api/chat/sessions/{session_id}/messages",
    headers=auth,
)
check(r, 200)
msgs = r.json()

assert len(msgs) == 4, f"Expected 4 messages (2 user + 2 assistant), got {len(msgs)}"
roles = [m["role"] for m in msgs]
assert roles == ["user", "assistant", "user", "assistant"], \
    f"Unexpected role order: {roles}"

# Both assistant messages must include sources array
for m in msgs:
    if m["role"] == "assistant":
        assert "sources" in m, f"Assistant message {m['id']} missing sources"

print(f"OK  {len(msgs)} messages in session, roles: {roles}")
print(f"    Message 1 (user): {msgs[0]['content'][:60]}…")
print(f"    Message 2 (asst): {msgs[1]['content'][:60]}…  model={msgs[1]['model_used']}")
print(f"    Message 3 (user): {msgs[2]['content'][:60]}…")
print(f"    Message 4 (asst): {msgs[3]['content'][:60]}…  model={msgs[3]['model_used']}")


# ═════════════════════════════════════════════════════════════════════════════
# 7.  AUTH REGRESSION
# ═════════════════════════════════════════════════════════════════════════════
hdr("STEP 7 – Auth regression check")
r = requests.get(f"{BASE}/api/auth/me", headers=auth)
check(r, 200)
print(f"OK  /api/auth/me → {r.status_code}")


# ═════════════════════════════════════════════════════════════════════════════
hdr("ALL STEPS PASSED")
print("PDF chat integration test completed successfully.\n")
print("Summary:")
print(f"  User         : {EMAIL}")
print(f"  Doc ID       : {doc_id}")
print(f"  Session ID   : {session_id}")
print(f"  General Q model  : {asst_msg1['model_used']}")
print(f"  Coding Q model   : {asst_msg2['model_used']}")
print(f"  General Q sources: {len(asst_msg1['sources'])}")
print(f"  Coding Q sources : {len(asst_msg2['sources'])}")
