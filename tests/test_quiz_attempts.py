"""
Integration test for Step 12 - Quiz attempts, grading, and summaries.

This test uses Flask's test client and patches quiz-generation and quiz-summary
wrapper calls so the attempt endpoints can be verified deterministically.

Run from project root:
    python test_quiz_attempts.py
"""

from __future__ import annotations

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


ROOT = os.path.dirname(__file__)
BACKEND_DIR = os.path.join(ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import create_app  # noqa: E402

app = create_app()
app.testing = True
client = app.test_client()

from app.db.models.chunk import Chunk  # noqa: E402
from app.db.models.document import Document  # noqa: E402
from app.db.models.document_ingestion import DocumentIngestion  # noqa: E402
from app.db.models.quiz_attempt import QuizAttempt  # noqa: E402
from app.db.models.quiz_attempt_answer import QuizAttemptAnswer  # noqa: E402
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


email_a = f"quizattempts_a_{uuid.uuid4().hex[:8]}@tutor.local"
email_b = f"quizattempts_b_{uuid.uuid4().hex[:8]}@tutor.local"
password = "quizattempts123"

original_retrieve = quiz_generator._retrieve_context_sources
original_generator_get_client = quiz_generator.get_client
original_summary_get_client = quiz_summarizer.get_client
fake_client_holder: dict[str, int] = {}


class FakeGeneratorClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat_completions(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            content = json.dumps(
                {
                    "title": "Broken Quiz",
                    "questions": [
                        {
                            "type": "mcq_single",
                            "question_text": "Broken first question",
                            "options": ["One", "Two"],
                            "correct_answer": {"option_index": 0},
                            "marks": 5,
                        },
                        {
                            "type": "mcq_single",
                            "question_text": "Broken second question",
                            "options": ["One", "Two"],
                            "correct_answer": {"option_index": 0},
                            "marks": 5,
                        },
                    ],
                }
            )
        else:
            chunk_id = fake_client_holder["chunk_id"]
            content = json.dumps(
                {
                    "title": "Python Basics Quiz",
                    "instructions": "Answer all questions using the source material.",
                    "questions": [
                        {
                            "type": "mcq_single",
                            "question_text": "What is Python described as in the notes?",
                            "options": [
                                "A database",
                                "A programming language",
                                "A browser",
                                "A file system",
                            ],
                            "correct_answer": {"option_index": 1},
                            "marks": 5,
                            "explanation": "The notes describe Python as a programming language.",
                            "citations": [chunk_id],
                        },
                        {
                            "type": "mcq_single",
                            "question_text": "Which keyword defines a function in Python?",
                            "options": ["function", "method", "def", "class"],
                            "correct_answer": {"option_index": 2},
                            "marks": 5,
                            "explanation": "The notes mention that functions are defined with def.",
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
                "overall": "Solid attempt with one correct answer and one incorrect answer.",
                "strengths": ["You identified one core concept correctly."],
                "improvements": ["Review the function definition syntax in Python."],
                "recommended_next_step": "Revisit the lesson and retake the quiz.",
            }
        )
        return {"choices": [{"message": {"content": content}}]}


fake_generator_client = FakeGeneratorClient()
fake_summary_client = FakeSummaryClient()

quiz_generator.get_client = lambda: fake_generator_client
quiz_summarizer.get_client = lambda: fake_summary_client

try:
    hdr("REGISTER USERS")
    register_a = client.post(
        "/api/auth/register",
        json={"email": email_a, "password": password},
    )
    check(register_a, 201)
    payload_a = register_a.get_json()
    token_a = payload_a["access_token"]
    refresh_a = payload_a["refresh_token"]
    user_a_id = payload_a["user"]["id"]
    print(f"user A: {email_a}")

    register_b = client.post(
        "/api/auth/register",
        json={"email": email_b, "password": password},
    )
    check(register_b, 201)
    payload_b = register_b.get_json()
    token_b = payload_b["access_token"]
    print(f"user B: {email_b}")

    hdr("AUTH REGRESSION CHECKS")
    login_a = client.post(
        "/api/auth/login",
        json={"email": email_a, "password": password},
    )
    check(login_a, 200)
    token_a = login_a.get_json()["access_token"]

    refresh_response = client.post(
        "/api/auth/refresh",
        headers=auth_header(refresh_a),
    )
    check(refresh_response, 200)

    me_response = client.get("/api/auth/me", headers=auth_header(token_a))
    check(me_response, 200)
    require(me_response.get_json()["user"]["id"] == user_a_id, "wrong /me user returned")
    print("auth endpoints are working")

    hdr("SEED READY DOCUMENT")
    with app.app_context():
        document = Document(
            user_id=user_a_id,
            title="Attempt Test Notes",
            source_type="text",
            original_text=(
                "Python is a programming language. Functions in Python are defined with the def keyword."
            ),
        )
        db.session.add(document)
        db.session.flush()

        ingestion = DocumentIngestion(
            document_id=document.id,
            user_id=user_a_id,
            source_type="text",
            text_snapshot=document.original_text,
            status="ready",
            completed_at=datetime.now(timezone.utc),
        )
        db.session.add(ingestion)
        db.session.flush()

        document.current_ingestion_id = ingestion.id

        chunk = Chunk(
            user_id=user_a_id,
            document_id=document.id,
            ingestion_id=ingestion.id,
            chunk_index=0,
            content=document.original_text,
            embedding=[0.0] * 1536,
        )
        db.session.add(chunk)
        db.session.commit()

        fake_client_holder["chunk_id"] = chunk.id
        doc_id = document.id
        fake_source = {
            "chunk_id": chunk.id,
            "document_id": document.id,
            "snippet": chunk.content,
            "score": 0.99,
            "document_title": document.title,
            "source_type": "text",
            "filename": None,
        }

    quiz_generator._retrieve_context_sources = (
        lambda user_id, spec: [fake_source] if user_id == user_a_id else []
    )

    hdr("CREATE QUIZ FOR ATTEMPT TESTING")
    create_quiz = client.post(
        "/api/quizzes",
        headers=auth_header(token_a),
        json={
            "topic": "Python basics",
            "question_count": 2,
            "difficulty": "easy",
            "marks": 10,
            "document_ids": [doc_id],
        },
    )
    check(create_quiz, 201)
    create_payload = create_quiz.get_json()
    quiz = create_payload["quiz"]
    quiz_id = quiz["id"]
    questions = create_payload["questions"]
    require(len(questions) == 2, "quiz creation did not return 2 questions")
    question_1_id = questions[0]["id"]
    question_2_id = questions[1]["id"]
    print(f"quiz created: {quiz_id}")

    hdr("POST /api/quizzes/<quiz_id>/attempts/start")
    start_attempt = client.post(
        f"/api/quizzes/{quiz_id}/attempts/start",
        headers=auth_header(token_a),
    )
    check(start_attempt, 201)
    start_payload = start_attempt.get_json()
    attempt = start_payload["attempt"]
    attempt_id = attempt["id"]

    require(attempt["quiz_id"] == quiz_id, "attempt linked to wrong quiz")
    require(attempt["score"] is None, "new attempt should not have a score")
    require(attempt["summary"] is None, "new attempt should not have a summary")
    require(len(start_payload["questions"]) == 2, "start endpoint returned wrong question count")
    require(start_payload["answers"] == [], "new attempt should not have answers")
    print(f"attempt started: {attempt_id}")

    start_other = client.post(
        f"/api/quizzes/{quiz_id}/attempts/start",
        headers=auth_header(token_b),
    )
    check(start_other, 404)
    print("cross-user start blocked")

    hdr("GET /api/quizzes/attempts/<attempt_id> BEFORE SUBMIT")
    get_attempt_before = client.get(
        f"/api/quizzes/attempts/{attempt_id}",
        headers=auth_header(token_a),
    )
    check(get_attempt_before, 200)
    before_payload = get_attempt_before.get_json()
    require(before_payload["attempt"]["submitted_at"] is None, "attempt should not be submitted yet")
    require(before_payload["answers"] == [], "attempt should not have stored answers yet")
    print("pre-submit get endpoint passed")

    invalid_submit = client.post(
        f"/api/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        headers=auth_header(token_a),
        json={"answers": "not-a-list"},
    )
    check(invalid_submit, 400)
    print("invalid submit payload rejected")

    hdr("POST /api/quizzes/<quiz_id>/attempts/<attempt_id>/submit")
    submit_attempt = client.post(
        f"/api/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        headers=auth_header(token_a),
        json={
            "time_spent_sec": 95,
            "answers": [
                {"question_id": question_1_id, "chosen_option_index": 0},
                {"question_id": question_2_id, "chosen_option_index": 0},
            ],
        },
    )
    check(submit_attempt, 200)
    submit_payload = submit_attempt.get_json()

    require(submit_payload["score"] == 5.0, f"expected score 5.0, got {submit_payload['score']}")
    require(submit_payload["total_marks"] == 10.0, "wrong total_marks returned")
    require(submit_payload["summary"]["overall"] == "Solid attempt with one correct answer and one incorrect answer.", "summary not returned")
    require(len(submit_payload["answers"]) == 2, "submit endpoint did not return 2 graded answers")

    answer_1 = submit_payload["answers"][0]
    answer_2 = submit_payload["answers"][1]
    require(answer_1["is_correct"] is True, "first answer should be correct")
    require(answer_1["marks_awarded"] == 5.0, "first answer marks are wrong")
    require("correct_json" in answer_1, "correct answer should be exposed after submit")
    require("explanation" in answer_1, "explanation should be exposed after submit")
    require(answer_2["is_correct"] is False, "second answer should be incorrect")
    require(answer_2["marks_awarded"] == 0.0, "second answer marks are wrong")
    print("submit endpoint graded deterministically")

    hdr("DATABASE PERSISTENCE CHECK")
    with app.app_context():
        attempt_row = QuizAttempt.query.filter_by(id=attempt_id, user_id=user_a_id).first()
        require(attempt_row is not None, "attempt row was not stored")
        require(attempt_row.score == 5.0, "stored attempt score is wrong")
        require(attempt_row.time_spent_sec == 95, "stored attempt time_spent_sec is wrong")
        require(isinstance(attempt_row.summary_json, dict), "stored summary_json is missing")

        answer_rows = (
            QuizAttemptAnswer.query
            .filter_by(attempt_id=attempt_id)
            .order_by(QuizAttemptAnswer.id.asc())
            .all()
        )
        require(len(answer_rows) == 2, "stored attempt answers count is wrong")
        require(answer_rows[0].chosen_json["option_index"] == 0, "stored chosen_json is wrong for answer 1")
        require(answer_rows[1].marks_awarded == 0.0, "stored marks_awarded is wrong for answer 2")
    print("attempt and answer rows were stored correctly")

    resubmit = client.post(
        f"/api/quizzes/{quiz_id}/attempts/{attempt_id}/submit",
        headers=auth_header(token_a),
        json={"answers": []},
    )
    check(resubmit, 409)
    print("resubmit blocked")

    hdr("GET /api/quizzes/attempts/<attempt_id> AFTER SUBMIT")
    get_attempt_after = client.get(
        f"/api/quizzes/attempts/{attempt_id}",
        headers=auth_header(token_a),
    )
    check(get_attempt_after, 200)
    after_payload = get_attempt_after.get_json()
    require(after_payload["attempt"]["submitted_at"] is not None, "submitted_at should be present after submit")
    require(after_payload["attempt"]["summary"] is not None, "stored summary should be present on get attempt")
    require(len(after_payload["answers"]) == 2, "get attempt should return two graded answers")
    require("correct_json" in after_payload["answers"][0], "get attempt should expose correct_json after submit")
    print("get attempt endpoint returned stored result")

    get_attempt_other = client.get(
        f"/api/quizzes/attempts/{attempt_id}",
        headers=auth_header(token_b),
    )
    check(get_attempt_other, 404)
    print("cross-user attempt access blocked")

    hdr("ALL QUIZ ATTEMPT TESTS PASSED")
    print("Quiz attempt API integration test completed successfully.")

finally:
    quiz_generator._retrieve_context_sources = original_retrieve
    quiz_generator.get_client = original_generator_get_client
    quiz_summarizer.get_client = original_summary_get_client
    with app.app_context():
        for email in (email_a, email_b):
            user = User.query.filter_by(email=email).first()
            if user is not None:
                db.session.delete(user)
        db.session.commit()
