"""
Live backend integration test for the document -> chat -> quiz flow.

Requires the Flask backend server to already be running.
Run from project root:
    python test_live_backend_quiz_flow.py

Config via environment variables:
    API_BASE_URL   default: http://localhost:5000
    QUIZ_TEST_PDF  optional absolute/relative PDF path
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import requests

BASE = os.getenv("API_BASE_URL", "http://localhost:5000").rstrip("/")
ROOT = Path(__file__).resolve().parent
DEFAULT_PDF = ROOT / "PDF" / "Python5.pdf"
PDF_PATH = Path(os.getenv("QUIZ_TEST_PDF", str(DEFAULT_PDF))).resolve()
PASSWORD = "quizflow123"
REQUEST_TIMEOUT = 300
POLL_INTERVAL_SEC = 3
POLL_TIMEOUT_SEC = 240
MAX_INGEST_RETRIES = 2
MAX_AI_RETRIES = 3
AI_RETRY_DELAY_SEC = 5


def hdr(label: str) -> None:
    print("\n" + "=" * 60)
    print(label)
    print("=" * 60)


def fail(message: str, response: requests.Response | None = None) -> None:
    print(f"FAIL: {message}")
    if response is not None:
        print(f"status: {response.status_code}")
        try:
            print(json.dumps(response.json(), indent=2))
        except Exception:
            print(response.text[:1500])
    sys.exit(1)


def check(response: requests.Response, *expected_statuses: int) -> requests.Response:
    if response.status_code not in expected_statuses:
        fail(f"expected {expected_statuses}, got {response.status_code}", response)
    return response


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def register_new_user() -> tuple[str, str, str]:
    email = f"quizflow_{uuid.uuid4().hex[:10]}@tutor.local"
    response = requests.post(
        f"{BASE}/api/auth/register",
        json={"email": email, "password": PASSWORD},
        timeout=REQUEST_TIMEOUT,
    )
    check(response, 201)
    payload = response.json()
    return email, payload["access_token"], payload["refresh_token"]


def wait_for_ingestion(doc_id: str, ingestion_id: str, token: str) -> dict:
    deadline = time.time() + POLL_TIMEOUT_SEC
    last_payload = None

    while time.time() < deadline:
        response = requests.get(
            f"{BASE}/api/documents/{doc_id}/ingestions/{ingestion_id}/status",
            headers=auth_header(token),
            timeout=REQUEST_TIMEOUT,
        )
        check(response, 200)
        payload = response.json()
        last_payload = payload

        status = payload.get("status")
        print(f"ingestion status: {status}")
        if status == "ready":
            return payload
        if status == "failed":
            return payload

        time.sleep(POLL_INTERVAL_SEC)

    fail(f"ingestion polling timed out: last_payload={last_payload}")


def ensure_ready_document(doc_id: str, ingestion_id: str, token: str) -> dict:
    current_ingestion_id = ingestion_id

    for attempt in range(1, MAX_INGEST_RETRIES + 2):
        payload = wait_for_ingestion(doc_id, current_ingestion_id, token)
        if payload.get("status") == "ready":
            return payload

        if attempt > MAX_INGEST_RETRIES:
            fail("document ingestion failed after retries")

        print("ingestion failed, retrying via reingest endpoint...")
        retry_response = requests.post(
            f"{BASE}/api/documents/{doc_id}/reingest",
            headers=auth_header(token),
            timeout=REQUEST_TIMEOUT,
        )
        check(retry_response, 200, 202)
        retry_payload = retry_response.json()
        current_ingestion_id = retry_payload["ingestion"]["id"]

    fail("unreachable ingestion retry state")


def post_ai_with_retries(
    url: str,
    token: str,
    payload: dict,
    *,
    expected_status: int,
) -> requests.Response:
    last_response = None
    for attempt in range(1, MAX_AI_RETRIES + 1):
        response = requests.post(
            url,
            headers=auth_header(token),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == expected_status:
            return response

        last_response = response
        if response.status_code not in (502, 503):
            fail(f"non-retryable AI endpoint failure on attempt {attempt}", response)

        print(
            f"AI endpoint returned {response.status_code} on attempt {attempt}/{MAX_AI_RETRIES}, "
            f"retrying in {AI_RETRY_DELAY_SEC}s..."
        )
        time.sleep(AI_RETRY_DELAY_SEC)

    fail("AI endpoint did not succeed after retries", last_response)


if not PDF_PATH.exists():
    fail(f"PDF file not found: {PDF_PATH}")

hdr("REGISTER NEW ACCOUNT")
email, access_token, refresh_token = register_new_user()
print(f"email: {email}")
print(f"pdf:   {PDF_PATH}")

hdr("AUTH CHECKS")
refresh_response = requests.post(
    f"{BASE}/api/auth/refresh",
    headers=auth_header(refresh_token),
    timeout=REQUEST_TIMEOUT,
)
check(refresh_response, 200)

me_response = requests.get(
    f"{BASE}/api/auth/me",
    headers=auth_header(access_token),
    timeout=REQUEST_TIMEOUT,
)
check(me_response, 200)
print(json.dumps(me_response.json(), indent=2))

hdr("UPLOAD PDF")
with PDF_PATH.open("rb") as pdf_file:
    upload_response = requests.post(
        f"{BASE}/api/documents/upload",
        headers=auth_header(access_token),
        files={"file": (PDF_PATH.name, pdf_file, "application/pdf")},
        timeout=REQUEST_TIMEOUT,
    )

check(upload_response, 201, 202)
upload_payload = upload_response.json()
print(json.dumps(upload_payload, indent=2))

document_id = upload_payload["document"]["id"]
ingestion_id = upload_payload["ingestion"]["id"]

hdr("WAIT FOR PDF INGESTION")
ready_payload = ensure_ready_document(document_id, ingestion_id, access_token)
print(json.dumps(ready_payload, indent=2))

hdr("CREATE CHAT SESSION")
chat_session_response = requests.post(
    f"{BASE}/api/chat/sessions",
    headers=auth_header(access_token),
    json={"title": "Live Quiz Flow Test"},
    timeout=REQUEST_TIMEOUT,
)
check(chat_session_response, 201)
chat_session = chat_session_response.json()
chat_id = chat_session["id"]
print(json.dumps(chat_session, indent=2))

hdr("ASK ONE QUESTION")
chat_message_response = post_ai_with_retries(
    f"{BASE}/api/chat/sessions/{chat_id}/messages",
    access_token,
    {
        "content": "Based on the uploaded PDF, what is Python? Answer briefly.",
    },
    expected_status=200,
)
chat_payload = chat_message_response.json()
print(json.dumps(chat_payload, indent=2))

assistant_message = chat_payload.get("assistant_message", {})
if not assistant_message.get("content"):
    fail("assistant message content is empty")

hdr("CREATE QUIZ")
create_quiz_response = post_ai_with_retries(
    f"{BASE}/api/quizzes",
    access_token,
    {
        "topic": "Python basics from the uploaded PDF",
        "question_count": 1,
        "difficulty": "easy",
        "marks": 5,
        "instructions": "Create one grounded multiple-choice question.",
        "document_ids": [document_id],
    },
    expected_status=201,
)
create_quiz_payload = create_quiz_response.json()
print(json.dumps(create_quiz_payload, indent=2))

quiz = create_quiz_payload["quiz"]
quiz_id = quiz["id"]
questions = create_quiz_payload["questions"]

if quiz["question_count"] != 1:
    fail(f"expected quiz question_count=1, got {quiz['question_count']}")
if len(questions) != 1:
    fail(f"expected 1 generated question, got {len(questions)}")
if not questions[0].get("sources"):
    fail("generated quiz question is missing sources")

hdr("CHECK QUIZ ENDPOINTS")
quiz_list_response = requests.get(
    f"{BASE}/api/quizzes",
    headers=auth_header(access_token),
    timeout=REQUEST_TIMEOUT,
)
check(quiz_list_response, 200)
quiz_list_payload = quiz_list_response.json()
if quiz_id not in [item["id"] for item in quiz_list_payload["quizzes"]]:
    fail("created quiz not found in quiz list")

quiz_detail_response = requests.get(
    f"{BASE}/api/quizzes/{quiz_id}",
    headers=auth_header(access_token),
    timeout=REQUEST_TIMEOUT,
)
check(quiz_detail_response, 200)
quiz_detail_payload = quiz_detail_response.json()
if quiz_detail_payload["quiz"]["id"] != quiz_id:
    fail("quiz detail endpoint returned wrong quiz")

quiz_questions_response = requests.get(
    f"{BASE}/api/quizzes/{quiz_id}/questions",
    headers=auth_header(access_token),
    timeout=REQUEST_TIMEOUT,
)
check(quiz_questions_response, 200)
quiz_questions_payload = quiz_questions_response.json()
if len(quiz_questions_payload["questions"]) != 1:
    fail("quiz questions endpoint returned wrong number of questions")

print(json.dumps(quiz_questions_payload, indent=2))

hdr("ALL REQUESTED ENDPOINT CHECKS PASSED")
print("Verified live flow:")
print("- register new account")
print("- refresh/me")
print("- upload PDF from PDF folder")
print("- wait for ingestion")
print("- create chat session")
print("- ask one question and receive an answer")
print("- create quiz")
print("- fetch quiz list/detail/questions")
