"""
Full document endpoint integration test.
Run from project root:
  python test_documents.py
"""

import json
import sys
import requests

BASE = "http://localhost:5000"
PDF = r"C:\Users\jains\OneDrive\Desktop\clg_proj\Tutor_bot\PDF\Python1.pdf"


def hdr(label):
    print("\n" + "=" * 60)
    print(label)
    print("=" * 60)


def check(resp, *expected_statuses):
    if resp.status_code not in expected_statuses:
        print(f"UNEXPECTED STATUS {resp.status_code}")
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print(resp.text[:500])
        sys.exit(1)


# ── LOGIN ─────────────────────────────────────────────────────────────────────
hdr("LOGIN")
r = requests.post(f"{BASE}/api/auth/login",
                  json={"email": "testdoc@tutor.local", "password": "doctest123"})
print("status:", r.status_code)
check(r, 200)
token = r.json()["access_token"]
auth = {"Authorization": f"Bearer {token}"}
print("token acquired")

# ── LIST (expected empty or already has docs from previous run) ────────────────
hdr("GET /api/documents")
r = requests.get(f"{BASE}/api/documents", headers=auth)
print("status:", r.status_code)
check(r, 200)
print(json.dumps(r.json(), indent=2))

# ── UPLOAD PDF ────────────────────────────────────────────────────────────────
hdr("POST /api/documents/upload  (Python1.pdf)")
print("Uploading PDF and running ingestion pipeline — this may take ~30s ...")
with open(PDF, "rb") as f:
    r = requests.post(
        f"{BASE}/api/documents/upload",
        headers=auth,
        files={"file": ("Python1.pdf", f, "application/pdf")},
        timeout=240,
    )
print("status:", r.status_code)
check(r, 201, 202)
upload_data = r.json()
print(json.dumps(upload_data, indent=2))
doc_id = upload_data["document"]["id"]
ing_id = upload_data["ingestion"]["id"]
print(f"\ndoc_id = {doc_id}")
print(f"ing_id = {ing_id}")

# ── INGESTION STATUS ──────────────────────────────────────────────────────────
hdr(f"GET /api/documents/{doc_id}/ingestions/{ing_id}/status")
r = requests.get(
    f"{BASE}/api/documents/{doc_id}/ingestions/{ing_id}/status",
    headers=auth,
)
print("status:", r.status_code)
check(r, 200)
print(json.dumps(r.json(), indent=2))

# ── TEXT DOCUMENT ─────────────────────────────────────────────────────────────
hdr("POST /api/documents/text")
text_payload = {
    "title": "Python Notes",
    "text": (
        "Python is a high-level, general-purpose programming language. "
        "It supports multiple programming paradigms including procedural, "
        "object-oriented, and functional programming. Python uses dynamic "
        "typing and garbage collection. Its design philosophy emphasizes "
        "code readability with the use of significant indentation. "
        "Python is the most popular language for data science and AI."
    ),
}
r = requests.post(f"{BASE}/api/documents/text", headers=auth, json=text_payload, timeout=120)
print("status:", r.status_code)
check(r, 201, 202)
text_data = r.json()
print(json.dumps(text_data, indent=2))
text_doc_id = text_data["document"]["id"]
text_ing_id = text_data["ingestion"]["id"]

# ── TEXT INGESTION STATUS ─────────────────────────────────────────────────────
hdr(f"GET /api/documents/{text_doc_id}/ingestions/{text_ing_id}/status")
r = requests.get(
    f"{BASE}/api/documents/{text_doc_id}/ingestions/{text_ing_id}/status",
    headers=auth,
)
print("status:", r.status_code)
check(r, 200)
print(json.dumps(r.json(), indent=2))

# ── LIST (should have both) ───────────────────────────────────────────────────
hdr("GET /api/documents  (should show both documents)")
r = requests.get(f"{BASE}/api/documents", headers=auth)
print("status:", r.status_code)
check(r, 200)
print(json.dumps(r.json(), indent=2))

# ── GET SINGLE DOC (PDF) ──────────────────────────────────────────────────────
hdr(f"GET /api/documents/{doc_id}  (PDF doc detail)")
r = requests.get(f"{BASE}/api/documents/{doc_id}", headers=auth)
print("status:", r.status_code)
check(r, 200)
print(json.dumps(r.json(), indent=2))

# ── DELETE TEXT DOC (soft delete) ────────────────────────────────────────────
hdr(f"DELETE /api/documents/{text_doc_id}  (soft delete text doc)")
r = requests.delete(f"{BASE}/api/documents/{text_doc_id}", headers=auth)
print("status:", r.status_code)
check(r, 200)
print(json.dumps(r.json(), indent=2))

# ── LIST AFTER DELETE (only PDF doc) ──────────────────────────────────────────
hdr("GET /api/documents  (only PDF doc should remain)")
r = requests.get(f"{BASE}/api/documents", headers=auth)
print("status:", r.status_code)
check(r, 200)
print(json.dumps(r.json(), indent=2))

print("\n\n" + "=" * 60)
print("ALL DOCUMENT ENDPOINT TESTS PASSED")
print("=" * 60)
