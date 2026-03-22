"""
Integration test for Step 11 - Quiz API.

This test uses Flask's test client and patches quiz-generation dependencies
so endpoint behavior can be verified deterministically without live wrapper
calls.

Run from project root:
    python test_quizzes.py
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

# Import create_app before app.db.* imports to avoid the repo's import shadowing issue.
from app import create_app  # noqa: E402

app = create_app()
app.testing = True
client = app.test_client()

from app.db.models.chunk import Chunk  # noqa: E402
from app.db.models.document import Document  # noqa: E402
from app.db.models.document_ingestion import DocumentIngestion  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.extensions import db  # noqa: E402
from app.services.quiz import generator as quiz_generator  # noqa: E402
from app.services.quiz.spec_parser import parse_quiz_request  # noqa: E402


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


email_a = f"quiztest_a_{uuid.uuid4().hex[:8]}@tutor.local"
email_b = f"quiztest_b_{uuid.uuid4().hex[:8]}@tutor.local"
password = "quiztest123"

original_retrieve = quiz_generator._retrieve_context_sources
original_get_client = quiz_generator.get_client
original_retrieve_chunks = quiz_generator.retrieve_chunks
original_retrieve_chunks_diversified = quiz_generator.retrieve_chunks_diversified
fake_client_holder: dict[str, int] = {}


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def chat_completions(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            # First response is intentionally invalid to exercise the repair loop.
            content = json.dumps(
                {
                    "title": "Broken Quiz",
                    "questions": [
                        {
                            "type": "mcq_single",
                            "question_text": "What is Python?",
                            "options": ["A snake", "A programming language"],
                            "correct_answer": {"option_index": 1},
                            "marks": 5,
                            "explanation": "Python is a language.",
                        },
                        {
                            "type": "mcq_single",
                            "question_text": "Which keyword defines a function in Python?",
                            "options": ["define", "def", "func", "lambda"],
                            "correct_answer": {"option_index": 1},
                            "marks": 5,
                            "explanation": "Functions use def.",
                        },
                    ],
                }
            )
        else:
            chunk_id = fake_client_holder["chunk_id"]
            content = json.dumps(
                {
                    "title": "Python Basics Quiz",
                    "instructions": "Answer all questions using the study notes.",
                    "questions": [
                        {
                            "type": "mcq_single",
                            "question_text": "What is Python mainly described as in the notes?",
                            "options": [
                                "A spreadsheet format",
                                "A programming language",
                                "A database engine",
                                "A compiler flag",
                            ],
                            "correct_answer": {"option_index": 1},
                            "marks": 5,
                            "explanation": "The notes describe Python as a programming language.",
                            "citations": [chunk_id],
                        },
                        {
                            "type": "mcq_single",
                            "question_text": "Which keyword is used to define functions in Python?",
                            "options": ["function", "method", "def", "class"],
                            "correct_answer": {"option_index": 2},
                            "marks": 5,
                            "explanation": "The notes explicitly mention the def keyword.",
                            "citations": [chunk_id],
                        },
                    ],
                }
            )
        return {"choices": [{"message": {"content": content}}]}


fake_client = FakeClient()
quiz_generator.get_client = lambda: fake_client

try:
    hdr("REGISTER USERS")
    register_a = client.post(
        "/api/auth/register",
        json={"email": email_a, "password": password},
    )
    check(register_a, 201)
    body_a = register_a.get_json()
    token_a = body_a["access_token"]
    refresh_a = body_a["refresh_token"]
    user_a_id = body_a["user"]["id"]
    print(f"user A: {email_a}")

    register_b = client.post(
        "/api/auth/register",
        json={"email": email_b, "password": password},
    )
    check(register_b, 201)
    body_b = register_b.get_json()
    token_b = body_b["access_token"]
    user_b_id = body_b["user"]["id"]
    print(f"user B: {email_b}")

    hdr("AUTH SETUP CHECKS")
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
    print("auth setup is working")

    hdr("SEED READY DOCUMENTS FOR USER A")
    with app.app_context():
        document = Document(
            user_id=user_a_id,
            title="Quiz Test Notes",
            source_type="text",
            original_text=(
                "Python is a high-level programming language used for automation and "
                "problem solving. Functions are defined with the def keyword."
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

        second_document = Document(
            user_id=user_a_id,
            title="Python Functions Notes",
            source_type="text",
            original_text=(
                "A function groups reusable logic. Python functions can accept "
                "parameters and may return values."
            ),
        )
        db.session.add(second_document)
        db.session.flush()

        second_ingestion = DocumentIngestion(
            document_id=second_document.id,
            user_id=user_a_id,
            source_type="text",
            text_snapshot=second_document.original_text,
            status="ready",
            completed_at=datetime.now(timezone.utc),
        )
        db.session.add(second_ingestion)
        db.session.flush()

        second_document.current_ingestion_id = second_ingestion.id

        second_chunk = Chunk(
            user_id=user_a_id,
            document_id=second_document.id,
            ingestion_id=second_ingestion.id,
            chunk_index=0,
            content=second_document.original_text,
            embedding=[0.0] * 1536,
        )
        db.session.add(second_chunk)
        db.session.commit()

        fake_client_holder["chunk_id"] = chunk.id
        fake_client_holder["chunk_id_two"] = second_chunk.id
        doc_id = document.id
        second_doc_id = second_document.id
        fake_source = {
            "chunk_id": chunk.id,
            "document_id": document.id,
            "snippet": chunk.content,
            "score": 0.99,
            "document_title": document.title,
            "source_type": "text",
            "filename": None,
        }
        fake_source_two = {
            "chunk_id": second_chunk.id,
            "document_id": second_document.id,
            "snippet": second_chunk.content,
            "score": 0.97,
            "document_title": second_document.title,
            "source_type": "text",
            "filename": None,
        }

    hdr("MULTI-DOCUMENT SOURCE COVERAGE")
    retrieve_calls: dict[str, dict] = {}

    def fake_retrieve_chunks(**kwargs):
        retrieve_calls["basic"] = kwargs
        return [fake_source]

    def fake_retrieve_chunks_diversified(**kwargs):
        retrieve_calls["diversified"] = kwargs
        return [fake_source, fake_source_two]

    quiz_generator.retrieve_chunks = fake_retrieve_chunks
    quiz_generator.retrieve_chunks_diversified = fake_retrieve_chunks_diversified

    multi_doc_spec = parse_quiz_request(
        {
            "topic": "Python basics",
            "question_count": 2,
            "marks": 10,
        }
    )
    with app.app_context():
        multi_doc_sources = quiz_generator._retrieve_context_sources(
            user_id=user_a_id,
            spec=multi_doc_spec,
        )
    require("basic" not in retrieve_calls, "all-ready quiz flow should not use basic retrieval")
    require("diversified" in retrieve_calls, "all-ready quiz flow should use diversified retrieval")
    require(
        set(retrieve_calls["diversified"]["document_ids"]) == {doc_id, second_doc_id},
        "diversified retrieval did not receive all ready document IDs",
    )
    require(
        retrieve_calls["diversified"]["minimum_document_count"] == 2,
        "diversified retrieval should require two documents for a two-question quiz",
    )
    require(
        {source["document_id"] for source in multi_doc_sources} == {doc_id, second_doc_id},
        "retrieved sources should include both ready documents",
    )
    print("all-ready quiz retrieval now requests multi-document coverage")

    quiz_generator.retrieve_chunks = original_retrieve_chunks
    quiz_generator.retrieve_chunks_diversified = original_retrieve_chunks_diversified

    quiz_generator._retrieve_context_sources = (
        lambda user_id, spec: [fake_source] if user_id == user_a_id else []
    )
    print(f"seeded document_ids={doc_id}, {second_doc_id}")

    hdr("AUTH ENFORCEMENT")
    unauth_list = client.get("/api/quizzes")
    check(unauth_list, 401, 422)
    print(f"unauthenticated request rejected with {unauth_list.status_code}")

    hdr("VALIDATION CHECKS")
    missing_topic = client.post(
        "/api/quizzes",
        headers=auth_header(token_a),
        json={"question_count": 2, "marks": 10},
    )
    check(missing_topic, 400)
    print(f"missing topic rejected: {missing_topic.get_json()['error']}")

    bad_document = client.post(
        "/api/quizzes",
        headers=auth_header(token_a),
        json={
            "topic": "Python basics",
            "question_count": 2,
            "marks": 10,
            "document_ids": [str(uuid.uuid4())],
        },
    )
    check(bad_document, 404)
    print(f"bad document_ids rejected: {bad_document.get_json()['error']}")

    hdr("POST /api/quizzes")
    create_quiz = client.post(
        "/api/quizzes",
        headers=auth_header(token_a),
        json={
            "topic": "Python basics",
            "question_count": 2,
            "difficulty": "easy",
            "marks": 10,
            "time_limit_sec": 600,
            "instructions": "Focus on introductory concepts.",
            "document_ids": [doc_id],
        },
    )
    check(create_quiz, 201)
    create_payload = create_quiz.get_json()
    quiz = create_payload["quiz"]
    questions = create_payload["questions"]
    quiz_id = quiz["id"]

    require(quiz["question_count"] == 2, "question_count mismatch")
    require(len(questions) == 2, "create response did not return 2 questions")
    require(quiz["spec"]["document_ids"] == [doc_id], "document_ids filter not preserved")
    require(abs(sum(question["marks"] for question in questions) - 10) <= 0.05, "marks total mismatch")
    require(fake_client.calls >= 2, "repair loop was not exercised")

    for index, question in enumerate(questions):
        require(bool(question.get("sources")), f"question {index} missing sources")
        require("correct_json" not in question, f"question {index} leaked correct_json")
        require("correct_answer" not in question, f"question {index} leaked correct_answer")
        require("explanation" not in question, f"question {index} leaked explanation")

    print(f"quiz created: {quiz_id}")

    hdr("POST /api/quizzes WITH ALL READY DOCUMENTS")

    class MultiDocumentFakeClient:
        def chat_completions(self, **kwargs):
            content = json.dumps(
                {
                    "title": "Python Sources Quiz",
                    "instructions": "Use both study sources.",
                    "questions": [
                        {
                            "type": "mcq_single",
                            "question_text": "What is Python described as in the first notes?",
                            "options": [
                                "A file archive",
                                "A programming language",
                                "A shell alias",
                                "A browser tab",
                            ],
                            "correct_answer": {"option_index": 1},
                            "marks": 5,
                            "explanation": "The first notes describe Python as a programming language.",
                            "citations": [fake_client_holder["chunk_id"]],
                        },
                        {
                            "type": "mcq_single",
                            "question_text": "What can Python functions do according to the second notes?",
                            "options": [
                                "Only print text",
                                "Accept parameters and return values",
                                "Run without definitions",
                                "Store database schemas",
                            ],
                            "correct_answer": {"option_index": 1},
                            "marks": 5,
                            "explanation": "The second notes say functions can accept parameters and return values.",
                            "citations": [fake_client_holder["chunk_id_two"]],
                        },
                    ],
                }
            )
            return {"choices": [{"message": {"content": content}}]}

    quiz_generator.get_client = lambda: MultiDocumentFakeClient()
    quiz_generator._retrieve_context_sources = (
        lambda user_id, spec: [fake_source, fake_source_two] if user_id == user_a_id else []
    )

    create_multi_doc_quiz = client.post(
        "/api/quizzes",
        headers=auth_header(token_a),
        json={
            "topic": "Python basics",
            "question_count": 2,
            "difficulty": "easy",
            "marks": 10,
        },
    )
    check(create_multi_doc_quiz, 201)
    multi_doc_payload = create_multi_doc_quiz.get_json()
    multi_doc_questions = multi_doc_payload["questions"]
    multi_doc_source_docs = {
        source["document_id"]
        for question in multi_doc_questions
        for source in question["sources"]
    }
    require(
        multi_doc_payload["quiz"]["spec"]["document_ids"] is None,
        "all-ready quiz mode should not persist explicit document_ids",
    )
    require(
        multi_doc_source_docs == {doc_id, second_doc_id},
        "multi-document quiz should cite both ready documents",
    )
    print("all-ready quiz generation now keeps coverage across multiple documents")

    quiz_generator.get_client = lambda: fake_client
    quiz_generator._retrieve_context_sources = (
        lambda user_id, spec: [fake_source] if user_id == user_a_id else []
    )

    hdr("GET /api/quizzes")
    list_a = client.get("/api/quizzes", headers=auth_header(token_a))
    check(list_a, 200)
    quizzes_a = list_a.get_json()["quizzes"]
    require(any(item["id"] == quiz_id for item in quizzes_a), "user A cannot see created quiz")
    print("user A can see created quiz")

    list_b = client.get("/api/quizzes", headers=auth_header(token_b))
    check(list_b, 200)
    quizzes_b = list_b.get_json()["quizzes"]
    require(all(item["id"] != quiz_id for item in quizzes_b), "user B can see user A quiz")
    print("user B cannot see user A quiz")

    hdr("GET /api/quizzes/<quiz_id>")
    detail_a = client.get(f"/api/quizzes/{quiz_id}", headers=auth_header(token_a))
    check(detail_a, 200)
    require(detail_a.get_json()["quiz"]["id"] == quiz_id, "detail endpoint returned wrong quiz")
    print("detail endpoint passed for owner")

    detail_b = client.get(f"/api/quizzes/{quiz_id}", headers=auth_header(token_b))
    check(detail_b, 404)
    print("detail endpoint blocks cross-user access")

    hdr("GET /api/quizzes/<quiz_id>/questions")
    questions_a = client.get(f"/api/quizzes/{quiz_id}/questions", headers=auth_header(token_a))
    check(questions_a, 200)
    payload_a = questions_a.get_json()
    require(payload_a["quiz"]["id"] == quiz_id, "questions endpoint returned wrong quiz")
    require(len(payload_a["questions"]) == 2, "questions endpoint returned wrong question count")

    for index, question in enumerate(payload_a["questions"]):
        require(bool(question.get("options")), f"question {index} missing options")
        require(bool(question.get("sources")), f"question {index} missing sources")
        require("correct_json" not in question, f"question {index} leaked correct_json on questions endpoint")
        require("correct_answer" not in question, f"question {index} leaked answer key on questions endpoint")

    print("questions endpoint passed for owner")

    questions_b = client.get(f"/api/quizzes/{quiz_id}/questions", headers=auth_header(token_b))
    check(questions_b, 404)
    print("questions endpoint blocks cross-user access")

    hdr("ALL QUIZ ENDPOINT TESTS PASSED")
    print("Quiz API integration test completed successfully.")

finally:
    quiz_generator._retrieve_context_sources = original_retrieve
    quiz_generator.get_client = original_get_client
    quiz_generator.retrieve_chunks = original_retrieve_chunks
    quiz_generator.retrieve_chunks_diversified = original_retrieve_chunks_diversified
    with app.app_context():
        for email in (email_a, email_b):
            user = User.query.filter_by(email=email).first()
            if user is not None:
                db.session.delete(user)
        db.session.commit()
