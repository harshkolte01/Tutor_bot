"""
Integration test for Step 14 - analytics event tracking and metrics APIs.

This test uses Flask's test client and patches document/chat/quiz wrapper
dependencies so analytics can be exercised deterministically.

Run from project root:
    python tests/test_analytics.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import uuid
from datetime import datetime, timezone


def hdr(label: str) -> None:
    print("\n" + "=" * 60)
    print(label)
    print("=" * 60)


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


ROOT = os.path.dirname(os.path.dirname(__file__))
BACKEND_DIR = os.path.join(ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import create_app  # noqa: E402

app = create_app()
app.testing = True
client = app.test_client()

from app.api import chat as chat_api  # noqa: E402
from app.api import documents as documents_api  # noqa: E402
from app.db.models.chunk import Chunk  # noqa: E402
from app.db.models.document import Document  # noqa: E402
from app.db.models.event import Event  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.extensions import db  # noqa: E402
from app.services.quiz import generator as quiz_generator  # noqa: E402
from app.services.quiz import summarizer as quiz_summarizer  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def response_json(response):
    try:
        return response.get_json()
    except Exception:
        return response.get_data(as_text=True)


def check(response, *expected_statuses: int):
    if response.status_code not in expected_statuses:
        payload = response_json(response)
        fail(
            f"unexpected status {response.status_code}, expected {expected_statuses}\n"
            f"response={json.dumps(payload, indent=2) if isinstance(payload, dict) else payload}"
        )
    return response


email_a = f"analytics_a_{uuid.uuid4().hex[:8]}@tutor.local"
email_b = f"analytics_b_{uuid.uuid4().hex[:8]}@tutor.local"
password = "analyticstest123"

original_ingest_text = documents_api.ingest_text
original_ingest_upload = documents_api.ingest_upload
original_select_model = chat_api._select_model
original_generate_answer = chat_api.generate_answer
original_retrieve = quiz_generator._retrieve_context_sources
original_generator_get_client = quiz_generator.get_client
original_summary_get_client = quiz_summarizer.get_client
fake_client_holder: dict[str, int] = {}


def fake_ingest_text(document, ingestion, text):
    chunk = Chunk(
        user_id=document.user_id,
        document_id=document.id,
        ingestion_id=ingestion.id,
        chunk_index=0,
        content=text,
        embedding=[0.0] * 1536,
    )
    db.session.add(chunk)
    ingestion.status = "ready"
    ingestion.completed_at = datetime.now(timezone.utc)
    document.current_ingestion_id = ingestion.id
    db.session.commit()
    fake_client_holder["chunk_id"] = chunk.id


def fake_ingest_upload(document, ingestion, file_bytes):
    chunk = Chunk(
        user_id=document.user_id,
        document_id=document.id,
        ingestion_id=ingestion.id,
        chunk_index=0,
        content=file_bytes.decode("utf-8", errors="replace"),
        embedding=[0.0] * 1536,
    )
    db.session.add(chunk)
    ingestion.status = "ready"
    ingestion.completed_at = datetime.now(timezone.utc)
    document.current_ingestion_id = ingestion.id
    db.session.commit()


class FakeQuizGeneratorClient:
    def chat_completions(self, **kwargs):
        chunk_id = fake_client_holder["chunk_id"]
        content = json.dumps(
            {
                "title": "Python Analytics Quiz",
                "instructions": "Answer using the notes.",
                "questions": [
                    {
                        "type": "mcq_single",
                        "question_text": "What is Python described as in the notes?",
                        "options": [
                            "A database",
                            "A programming language",
                            "A browser",
                            "A spreadsheet",
                        ],
                        "correct_answer": {"option_index": 2},
                        "marks": 5,
                        "explanation": "The notes call Python a programming language.",
                        "citations": [chunk_id],
                    },
                    {
                        "type": "mcq_single",
                        "question_text": "Which keyword defines a function in Python?",
                        "options": ["class", "lambda", "def", "return"],
                        "correct_answer": {"option_index": 3},
                        "marks": 5,
                        "explanation": "Functions are defined with def.",
                        "citations": [chunk_id],
                    },
                ],
            }
        )
        return {"choices": [{"message": {"content": content}}]}


class FakeSummaryClient:
    def chat_completions(self, **kwargs):
        content = json.dumps(
            {
                "overall": "One answer was correct and one needs review.",
                "strengths": ["You identified one key concept correctly."],
                "improvements": ["Review Python function syntax."],
                "recommended_next_step": "Revise the notes and try again.",
            }
        )
        return {"choices": [{"message": {"content": content}}]}


documents_api.ingest_text = fake_ingest_text
documents_api.ingest_upload = fake_ingest_upload
chat_api._select_model = lambda message: {
    "category": "general",
    "model": "openrouter/google/gemma-3-27b-it:free",
    "confidence": "high",
    "method": "test",
}
chat_api.generate_answer = lambda **kwargs: {
    "answer": "Python is a programming language used for many tasks.",
    "model": kwargs["model"],
    "sources": [],
    "out_of_context": False,
}
quiz_generator.get_client = lambda: FakeQuizGeneratorClient()
quiz_summarizer.get_client = lambda: FakeSummaryClient()

try:
    hdr("REGISTER USERS")
    register_a = client.post("/api/auth/register", json={"email": email_a, "password": password})
    check(register_a, 201)
    payload_a = register_a.get_json()
    token_a = payload_a["access_token"]
    refresh_a = payload_a["refresh_token"]
    user_a_id = payload_a["user"]["id"]

    register_b = client.post("/api/auth/register", json={"email": email_b, "password": password})
    check(register_b, 201)
    payload_b = register_b.get_json()
    token_b = payload_b["access_token"]
    user_b_id = payload_b["user"]["id"]

    hdr("AUTH REGRESSION CHECKS")
    login_a = client.post("/api/auth/login", json={"email": email_a, "password": password})
    check(login_a, 200)
    token_a = login_a.get_json()["access_token"]

    refresh_response = client.post("/api/auth/refresh", headers=auth_header(refresh_a))
    check(refresh_response, 200)

    me_response = client.get("/api/auth/me", headers=auth_header(token_a))
    check(me_response, 200)
    require(me_response.get_json()["user"]["id"] == user_a_id, "wrong /me user returned")

    hdr("DOCUMENT EVENTS")
    upload_response = client.post(
        "/api/documents/upload",
        headers=auth_header(token_a),
        data={
            "title": "Uploaded Python Notes",
            "file": (io.BytesIO(b"Python basics from upload."), "notes.txt"),
        },
        content_type="multipart/form-data",
    )
    check(upload_response, 201)

    text_response = client.post(
        "/api/documents/text",
        headers=auth_header(token_a),
        json={
            "title": "Typed Python Notes",
            "text": (
                "Python is a programming language. "
                "Functions in Python are defined with the def keyword."
            ),
        },
    )
    check(text_response, 201)
    text_doc_id = text_response.get_json()["document"]["id"]

    other_user_text = client.post(
        "/api/documents/text",
        headers=auth_header(token_b),
        json={
            "title": "Other User Notes",
            "text": "This should not affect user A analytics.",
        },
    )
    check(other_user_text, 201)

    hdr("CHAT EVENT")
    session_response = client.post(
        "/api/chat/sessions",
        headers=auth_header(token_a),
        json={"title": "Analytics Chat"},
    )
    check(session_response, 201)
    chat_id = session_response.get_json()["id"]

    message_response = client.post(
        f"/api/chat/sessions/{chat_id}/messages",
        headers=auth_header(token_a),
        json={"content": "What is Python?"},
    )
    check(message_response, 200)

    hdr("QUIZ CREATE + SUBMIT EVENTS")
    with app.app_context():
        text_document = Document.query.filter_by(id=text_doc_id, user_id=user_a_id).first()
        require(text_document is not None, "text document was not stored")
        chunk = (
            Chunk.query
            .filter_by(document_id=text_doc_id, ingestion_id=text_document.current_ingestion_id)
            .first()
        )
        require(chunk is not None, "text document chunk was not stored")
        fake_client_holder["chunk_id"] = chunk.id
        fake_source = {
            "chunk_id": chunk.id,
            "document_id": text_document.id,
            "snippet": chunk.content,
            "score": 0.99,
            "document_title": text_document.title,
            "source_type": "text",
            "filename": None,
        }

    quiz_generator._retrieve_context_sources = (
        lambda user_id, spec: [fake_source] if user_id == user_a_id else []
    )

    create_quiz = client.post(
        "/api/quizzes",
        headers=auth_header(token_a),
        json={
            "topic": "Python basics",
            "question_count": 2,
            "difficulty": "easy",
            "marks": 10,
            "document_ids": [text_doc_id],
        },
    )
    check(create_quiz, 201)
    create_payload = create_quiz.get_json()
    quiz_id = create_payload["quiz"]["id"]
    questions = create_payload["questions"]

    start_attempt = client.post(
        f"/api/quizzes/{quiz_id}/attempts/start",
        headers=auth_header(token_a),
    )
    check(start_attempt, 201)
    attempt_id = start_attempt.get_json()["attempt"]["id"]

    submit_attempt = client.post(
        f"/api/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        headers=auth_header(token_a),
        json={
            "time_spent_sec": 90,
            "answers": [
                {"question_id": questions[0]["id"], "chosen_option_index": 1},
                {"question_id": questions[1]["id"], "chosen_option_index": 0},
            ],
        },
    )
    check(submit_attempt, 200)
    submit_payload = submit_attempt.get_json()
    require(
        submit_payload["score"] == 5.0,
        f"quiz submission should score 5.0, got {submit_payload['score']}",
    )

    hdr("ANALYTICS AUTH ENFORCEMENT")
    unauth_overview = client.get("/api/analytics/overview")
    check(unauth_overview, 401, 422)

    hdr("GET /api/analytics/overview")
    overview_response = client.get("/api/analytics/overview", headers=auth_header(token_a))
    check(overview_response, 200)
    overview = overview_response.get_json()
    require(overview["totals"]["documents"] == 2, "overview documents total should be 2 for user A")
    require(overview["totals"]["uploaded_documents"] == 1, "overview uploaded document total should be 1")
    require(overview["totals"]["text_documents"] == 1, "overview text document total should be 1")
    require(overview["totals"]["chat_sessions"] == 1, "overview chat session total should be 1")
    require(overview["totals"]["quizzes"] == 1, "overview quiz total should be 1")
    require(overview["totals"]["submitted_attempts"] == 1, "overview submitted attempt total should be 1")
    require(overview["event_counts"]["doc_uploaded"] == 1, "overview doc_uploaded count should be 1")
    require(overview["event_counts"]["doc_text_added"] == 1, "overview doc_text_added count should be 1")
    require(overview["event_counts"]["chat_asked"] == 1, "overview chat_asked count should be 1")
    require(overview["event_counts"]["quiz_created"] == 1, "overview quiz_created count should be 1")
    require(overview["event_counts"]["quiz_submitted"] == 1, "overview quiz_submitted count should be 1")
    require(overview["average_score_percent"] == 50.0, "overview average score percent should be 50.0")
    require(overview["latest_activity_at"] is not None, "overview latest activity should be populated")

    overview_b_response = client.get("/api/analytics/overview", headers=auth_header(token_b))
    check(overview_b_response, 200)
    overview_b = overview_b_response.get_json()
    require(overview_b["totals"]["documents"] == 1, "user B should only see one document")
    require(overview_b["event_counts"]["doc_text_added"] == 1, "user B should only see one text event")
    require(overview_b["event_counts"]["quiz_created"] == 0, "user B should not see user A quiz events")

    hdr("GET /api/analytics/progress")
    progress_response = client.get("/api/analytics/progress", headers=auth_header(token_a))
    check(progress_response, 200)
    progress = progress_response.get_json()
    require(progress["summary"]["days"] == 14, "progress summary should default to 14 days")
    require(progress["summary"]["total_events"] == 5, "progress total_events should be 5")
    require(progress["summary"]["submitted_attempts"] == 1, "progress submitted_attempts should be 1")
    require(progress["summary"]["average_score_percent"] == 50.0, "progress average score percent should be 50.0")
    require(len(progress["daily_activity"]) == 14, "progress should return 14 daily activity buckets")
    require(len(progress["quiz_score_trend"]) == 14, "progress should return 14 score buckets")
    require(sum(day["chat_asked"] for day in progress["daily_activity"]) == 1, "progress should report one chat_asked event")
    require(sum(day["quiz_submitted"] for day in progress["daily_activity"]) == 1, "progress should report one quiz_submitted event")
    require(
        any(day["average_score_percent"] == 50.0 for day in progress["quiz_score_trend"]),
        "progress score trend should contain the submitted quiz score",
    )

    hdr("GET /api/analytics/weak-topics")
    weak_topics_response = client.get("/api/analytics/weak-topics", headers=auth_header(token_a))
    check(weak_topics_response, 200)
    weak_topics = weak_topics_response.get_json()["weak_topics"]
    require(len(weak_topics) == 1, "expected one weak topic result")
    require(weak_topics[0]["topic"] == "Python basics", "weak topic should come from quiz spec topic")
    require(weak_topics[0]["attempt_count"] == 1, "weak topic attempt_count should be 1")
    require(weak_topics[0]["question_count"] == 2, "weak topic question_count should be 2")
    require(weak_topics[0]["correct_count"] == 1, "weak topic correct_count should be 1")
    require(weak_topics[0]["incorrect_count"] == 1, "weak topic incorrect_count should be 1")
    require(weak_topics[0]["accuracy_percent"] == 50.0, "weak topic accuracy should be 50.0")
    require(weak_topics[0]["average_score_percent"] == 50.0, "weak topic score should be 50.0")

    hdr("EVENT TABLE CHECK")
    with app.app_context():
        event_rows_a = Event.query.filter_by(user_id=user_a_id).all()
        event_rows_b = Event.query.filter_by(user_id=user_b_id).all()
        require(len(event_rows_a) == 5, "user A should have exactly five analytics events")
        require(len(event_rows_b) == 1, "user B should have exactly one analytics event")

    hdr("ALL ANALYTICS TESTS PASSED")
    print("Analytics event tracking and metrics API integration test completed successfully.")

finally:
    documents_api.ingest_text = original_ingest_text
    documents_api.ingest_upload = original_ingest_upload
    chat_api._select_model = original_select_model
    chat_api.generate_answer = original_generate_answer
    quiz_generator._retrieve_context_sources = original_retrieve
    quiz_generator.get_client = original_generator_get_client
    quiz_summarizer.get_client = original_summary_get_client
    with app.app_context():
        for email in (email_a, email_b):
            user = User.query.filter_by(email=email).first()
            if user is not None:
                db.session.delete(user)
        db.session.commit()
