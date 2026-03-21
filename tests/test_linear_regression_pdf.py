"""
End-to-end test: account creation → PDF upload → Q&A on linear_regression.pdf
=============================================================================

Flow
----
  1. Register a brand-new user (or reuse if already registered)
  2. Upload linear_regression.pdf and wait for ingestion to finish
  3. Create a chat session
  4. Ask three questions about linear regression from the PDF context
  5. Assert structural correctness + print rich response details
  6. Verify final message history is consistent

Run from the project root (Flask server must be running on :5000):
    python test_linear_regression_pdf.py

Edit PDF_PATH below to point at your local copy of the file.
"""

import json
import sys
import time
import requests

# ── Configuration ─────────────────────────────────────────────────────────────
BASE     = "http://localhost:5000"
PDF_PATH = r"C:\Coding\Tutor_bot\Linear_Regression.pdf"

EMAIL    = "lr_test@tutor.local"
PASSWORD = "lrtest_pass123"

QUESTIONS = [
    # (label, question_text, assert_non_empty_sources)
    (
        "Conceptual  – What is linear regression?",
        "What is linear regression and when is it used? Explain based on the document.",
        False,   # sources are a bonus, not hard-required for a conceptual Q
    ),
    (
        "Math / Formula – Cost function & gradient descent",
        (
            "According to the document, what is the cost function used in linear regression "
            "and how does gradient descent minimise it?"
        ),
        False,
    ),
    (
        "Coding – Implement in Python",
        (
            "Based on the document, write a Python function that implements simple linear "
            "regression using gradient descent, including the weight update step."
        ),
        False,
    ),
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def banner(label: str):
    print("\n" + "=" * 65)
    print(f"  {label}")
    print("=" * 65)


PASS_COUNT = 0
FAIL_COUNT = 0

def ok(msg: str):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"  [PASS]  {msg}")


def fail(msg: str, resp: requests.Response | None = None):
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"  [FAIL]  {msg}")
    if resp is not None:
        try:
            print(json.dumps(resp.json(), indent=4))
        except Exception:
            print(resp.text[:800])


def check(resp: requests.Response, *expected_codes) -> requests.Response:
    """Hard-stop on unexpected status codes."""
    if resp.status_code not in expected_codes:
        fail(f"Expected status {expected_codes}, got {resp.status_code}", resp)
        sys.exit(1)
    return resp


def register_or_login(email: str, password: str) -> dict:
    """Register a new user or login if already registered. Returns full auth response."""
    r = requests.post(f"{BASE}/api/auth/register",
                      json={"email": email, "password": password})
    if r.status_code == 201:
        print(f"  Registered new user: {email}")
        return r.json()
    if r.status_code == 409:
        print(f"  User already exists — logging in as: {email}")
        r2 = requests.post(f"{BASE}/api/auth/login",
                           json={"email": email, "password": password})
        check(r2, 200)
        return r2.json()
    check(r, 201)  # any other status is fatal


def wait_for_ingestion(doc_id: str, ing_id: str, auth_headers: dict,
                       timeout: int = 240) -> str:
    """Poll ingestion status until 'ready' or 'failed'. Returns final status string."""
    url      = f"{BASE}/api/documents/{doc_id}/ingestions/{ing_id}/status"
    deadline = time.time() + timeout
    dots     = 0
    while time.time() < deadline:
        r      = requests.get(url, headers=auth_headers)
        check(r, 200)
        status = r.json().get("status", "unknown")
        # Print a compact progress line
        dots  += 1
        print(f"\r  Ingestion status: {status} {'.' * dots}   ", end="", flush=True)
        if status == "ready":
            print()
            return "ready"
        if status == "failed":
            print()
            print(f"  error_message: {r.json().get('error_message')}")
            return "failed"
        time.sleep(6)
    print()
    return "timeout"


def print_answer(label: str, data: dict):
    """Nicely format one Q&A exchange."""
    asst   = data["assistant_message"]
    router = data["router"]
    answer = asst["content"]
    print(f"\n  -- {label} --")
    print(f"  Model used : {asst.get('model_used', 'n/a')}")
    print(f"  Router     : category={router['category']}  method={router['method']}"
          f"  confidence={router['confidence']}")
    print(f"  Sources    : {len(asst['sources'])} chunk(s) cited")
    print(f"  Answer ({len(answer)} chars):")
    print("  " + "-" * 55)
    # Print first 700 chars of the answer, clearly indented
    for line in answer[:700].splitlines():
        print(f"  {line}")
    if len(answer) > 700:
        print(f"  … [truncated, {len(answer) - 700} chars remaining]")
    print("  " + "-" * 55)
    if asst["sources"]:
        print("  Citations:")
        for i, s in enumerate(asst["sources"][:3], 1):
            score   = s.get("similarity_score", 0)
            snippet = (s.get("snippet") or "")[:90]
            print(f"    [{i}] score={score:.4f}  snippet={snippet!r}…")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 – Register / Login
# ══════════════════════════════════════════════════════════════════════════════
banner("STEP 1 – Register a new account (or re-use existing)")

auth_resp = register_or_login(EMAIL, PASSWORD)
token     = auth_resp["access_token"]
auth      = {"Authorization": f"Bearer {token}"}
user_info = auth_resp.get("user", {})

ok(f"Authenticated  email={EMAIL}  user_id={user_info.get('id', '?')}")
print(f"  Token: {token[:28]}…")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 – Upload linear_regression.pdf (skip if already ingested)
# ══════════════════════════════════════════════════════════════════════════════
banner("STEP 2 – Upload linear_regression.pdf")

# Check for an already-ingested copy so we don't spam the ingestion pipeline
existing_r = requests.get(f"{BASE}/api/documents", headers=auth)
check(existing_r, 200)
body     = existing_r.json()
docs     = body.get("documents", body) if isinstance(body, dict) else body

doc_id = None
for d in docs:
    if (
        "linear" in d.get("title", "").lower()
        and not d.get("is_deleted", False)
        and d.get("current_ingestion_id")
    ):
        doc_id = d["id"]
        print(f"  Reusing already-ingested document: \"{d['title']}\"  id={doc_id}")
        ok("Document already ingested — skipping re-upload")
        break

if doc_id is None:
    import os
    if not os.path.isfile(PDF_PATH):
        print(f"\n  ERROR: PDF not found at:\n    {PDF_PATH}")
        print("  Please update PDF_PATH at the top of this file.")
        sys.exit(1)

    print(f"  Uploading: {PDF_PATH}")
    print("  Ingestion runs synchronously — this may take 30–120 seconds …")
    with open(PDF_PATH, "rb") as f:
        r = requests.post(
            f"{BASE}/api/documents/upload",
            headers=auth,
            files={"file": ("linear_regression.pdf", f, "application/pdf")},
            timeout=300,
        )
    check(r, 201, 202)
    upload_data = r.json()
    doc_id      = upload_data["document"]["id"]
    ing_id      = upload_data["ingestion"]["id"]
    ing_status  = upload_data["ingestion"]["status"]
    print(f"  Upload accepted  doc_id={doc_id}  ing_id={ing_id}  status={ing_status}")

    if r.status_code == 202 or ing_status not in ("ready", "complete"):
        print("  Polling ingestion status …")
        final = wait_for_ingestion(doc_id, ing_id, auth)
        if final != "ready":
            fail(f"Ingestion ended with status '{final}'")
            sys.exit(1)
        ok(f"Ingestion complete (polled)  final_status={final}")
    else:
        ok(f"Ingestion complete (synchronous)  status={ing_status}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 – Create chat session
# ══════════════════════════════════════════════════════════════════════════════
banner("STEP 3 – Create chat session")

r = requests.post(
    f"{BASE}/api/chat/sessions",
    json={"title": "Linear Regression PDF Test"},
    headers=auth,
)
check(r, 201)
session_id = r.json()["id"]
ok(f"Session created  session_id={session_id}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 – Ask 3 questions and validate responses
# ══════════════════════════════════════════════════════════════════════════════
banner("STEP 4 – Ask 3 questions about linear regression")

qa_results = []  # collect assistant messages for history validation later

for q_num, (label, question, require_sources) in enumerate(QUESTIONS, start=1):
    print(f"\n  Question {q_num}/3: {label}")
    print(f"  Sending: {question[:90]}…" if len(question) > 90 else f"  Sending: {question}")
    print("  Waiting for response (may take up to 90s) …")

    r = requests.post(
        f"{BASE}/api/chat/sessions/{session_id}/messages",
        json={"content": question},
        headers=auth,
        timeout=150,
    )
    check(r, 200)
    data     = r.json()
    user_msg = data["user_message"]
    asst_msg = data["assistant_message"]
    router   = data["router"]

    # ── Structural assertions ─────────────────────────────────────────────
    passed = True

    if user_msg.get("role") == "user":
        ok(f"Q{q_num}: user message role='user'")
    else:
        fail(f"Q{q_num}: user message role expected 'user', got '{user_msg.get('role')}'")
        passed = False

    if asst_msg.get("role") == "assistant":
        ok(f"Q{q_num}: assistant message role='assistant'")
    else:
        fail(f"Q{q_num}: assistant message role expected 'assistant', got '{asst_msg.get('role')}'")
        passed = False

    if asst_msg.get("content"):
        ok(f"Q{q_num}: assistant answer is non-empty ({len(asst_msg['content'])} chars)")
    else:
        fail(f"Q{q_num}: assistant answer is EMPTY")
        passed = False

    if asst_msg.get("model_used"):
        ok(f"Q{q_num}: model_used present → {asst_msg['model_used']}")
    else:
        fail(f"Q{q_num}: model_used field is missing or empty")
        passed = False

    if isinstance(asst_msg.get("sources"), list):
        ok(f"Q{q_num}: sources field is a list ({len(asst_msg['sources'])} entries)")
    else:
        fail(f"Q{q_num}: sources field is not a list")
        passed = False

    if require_sources and not asst_msg["sources"]:
        fail(f"Q{q_num}: expected source citations but got none")
        passed = False

    # ── Coding question: router must classify as 'coding' ─────────────────
    if "Coding" in label:
        if router.get("category") == "coding":
            ok(f"Q{q_num}: router correctly classified as 'coding'")
        else:
            fail(f"Q{q_num}: expected router category='coding', got '{router.get('category')}'")
            passed = False

    # ── Print answer details ───────────────────────────────────────────────
    print_answer(label, data)
    qa_results.append((question, asst_msg))


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 – Verify message history
# ══════════════════════════════════════════════════════════════════════════════
banner("STEP 5 – Verify message history in session")

r = requests.get(
    f"{BASE}/api/chat/sessions/{session_id}/messages",
    headers=auth,
)
check(r, 200)
msgs  = r.json()
roles = [m["role"] for m in msgs]

expected_count = len(QUESTIONS) * 2   # 1 user + 1 assistant per question
expected_roles = ["user", "assistant"] * len(QUESTIONS)

if len(msgs) == expected_count:
    ok(f"Message count correct: {len(msgs)} ({len(QUESTIONS)} user + {len(QUESTIONS)} assistant)")
else:
    fail(f"Expected {expected_count} messages, got {len(msgs)}")

if roles == expected_roles:
    ok(f"Role sequence correct: {roles}")
else:
    fail(f"Unexpected role sequence: {roles}")

for m in msgs:
    if m["role"] == "assistant" and "sources" not in m:
        fail(f"Assistant message id={m['id']} is missing 'sources' field")
    elif m["role"] == "assistant":
        ok(f"Assistant message id={m['id']} has 'sources' field")

print("\n  Message log:")
for i, m in enumerate(msgs, 1):
    snippet = m["content"][:70].replace("\n", " ")
    extra   = f"  model={m.get('model_used','')}" if m["role"] == "assistant" else ""
    print(f"    [{i}] {m['role']:10s}  {snippet!r}…{extra}")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 – Auth regression check
# ══════════════════════════════════════════════════════════════════════════════
banner("STEP 6 – Auth regression (GET /api/auth/me)")

r = requests.get(f"{BASE}/api/auth/me", headers=auth)
check(r, 200)
me = r.json()
if me.get("user", {}).get("email") == EMAIL:
    ok(f"/api/auth/me returned correct user: {me['user']['email']}")
else:
    fail(f"/api/auth/me email mismatch: expected {EMAIL}, got {me.get('user', {}).get('email')}")


# ══════════════════════════════════════════════════════════════════════════════
# Final summary
# ══════════════════════════════════════════════════════════════════════════════
banner("TEST SUMMARY")
total = PASS_COUNT + FAIL_COUNT
print(f"  Total checks : {total}")
print(f"  Passed       : {PASS_COUNT}")
print(f"  Failed       : {FAIL_COUNT}")
print()
print(f"  User         : {EMAIL}")
print(f"  Doc ID       : {doc_id}")
print(f"  Session ID   : {session_id}")
for i, (q, asst) in enumerate(qa_results, 1):
    print(f"  Q{i} model     : {asst.get('model_used', 'n/a')}  "
          f"sources={len(asst.get('sources', []))}")

if FAIL_COUNT == 0:
    print("\n  *** ALL CHECKS PASSED ***\n")
else:
    print(f"\n  *** {FAIL_COUNT} CHECK(S) FAILED — review output above ***\n")
    sys.exit(1)
