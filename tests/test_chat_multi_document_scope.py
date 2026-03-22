"""
Integration test for chat retrieval when a session uses all ready documents.

This test uses Flask's test client and patches retrieval / wrapper dependencies
so the chat flow can be verified deterministically without live AI calls.

Run from project root:
    python tests/test_chat_multi_document_scope.py
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
BACKEND_DIR = os.path.join(ROOT, "..", "backend")
BACKEND_DIR = os.path.abspath(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app import create_app  # noqa: E402

app = create_app()
app.testing = True
client = app.test_client()

from app.api import chat as chat_api  # noqa: E402
from app.db.models.chunk import Chunk  # noqa: E402
from app.db.models.document import Document  # noqa: E402
from app.db.models.document_ingestion import DocumentIngestion  # noqa: E402
from app.db.models.user import User  # noqa: E402
from app.extensions import db  # noqa: E402
from app.services.rag import answering  # noqa: E402


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


email = f"chatscope_{uuid.uuid4().hex[:8]}@tutor.local"
password = "chatscopetest123"

original_select_model = chat_api._select_model
original_retrieve_chunks = answering.retrieve_chunks
original_retrieve_chunks_diversified = answering.retrieve_chunks_diversified
original_get_client = answering.get_client


class FakeClient:
    def chat_completions(self, **kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "Python basics are covered in [Source 1], and reusable functions "
                            "are covered in [Source 2]."
                        )
                    }
                }
            ]
        }


try:
    hdr("REGISTER USER")
    register_response = client.post(
        "/api/auth/register",
        json={"email": email, "password": password},
    )
    check(register_response, 201)
    register_body = register_response.get_json()
    access_token = register_body["access_token"]
    refresh_token = register_body["refresh_token"]
    user_id = register_body["user"]["id"]
    print(f"user: {email}")

    hdr("AUTH REGRESSION CHECKS")
    login_response = client.post(
        "/api/auth/login",
        json={"email": email, "password": password},
    )
    check(login_response, 200)
    access_token = login_response.get_json()["access_token"]

    refresh_response = client.post(
        "/api/auth/refresh",
        headers=auth_header(refresh_token),
    )
    check(refresh_response, 200)

    me_response = client.get("/api/auth/me", headers=auth_header(access_token))
    check(me_response, 200)
    require(me_response.get_json()["user"]["id"] == user_id, "wrong /me user returned")
    print("auth flow is working")

    hdr("SEED TWO READY DOCUMENTS")
    with app.app_context():
        first_document = Document(
            user_id=user_id,
            title="Python Basics Notes",
            source_type="text",
            original_text=(
                "Python is a high-level programming language used for automation and "
                "problem solving."
            ),
        )
        db.session.add(first_document)
        db.session.flush()

        first_ingestion = DocumentIngestion(
            document_id=first_document.id,
            user_id=user_id,
            source_type="text",
            text_snapshot=first_document.original_text,
            status="ready",
            completed_at=datetime.now(timezone.utc),
        )
        db.session.add(first_ingestion)
        db.session.flush()
        first_document.current_ingestion_id = first_ingestion.id

        first_chunk = Chunk(
            user_id=user_id,
            document_id=first_document.id,
            ingestion_id=first_ingestion.id,
            chunk_index=0,
            content=first_document.original_text,
            embedding=[0.0] * 1536,
        )
        db.session.add(first_chunk)

        second_document = Document(
            user_id=user_id,
            title="Python Functions Notes",
            source_type="text",
            original_text=(
                "A Python function groups reusable logic, can accept parameters, "
                "and may return values."
            ),
        )
        db.session.add(second_document)
        db.session.flush()

        second_ingestion = DocumentIngestion(
            document_id=second_document.id,
            user_id=user_id,
            source_type="text",
            text_snapshot=second_document.original_text,
            status="ready",
            completed_at=datetime.now(timezone.utc),
        )
        db.session.add(second_ingestion)
        db.session.flush()
        second_document.current_ingestion_id = second_ingestion.id

        second_chunk = Chunk(
            user_id=user_id,
            document_id=second_document.id,
            ingestion_id=second_ingestion.id,
            chunk_index=0,
            content=second_document.original_text,
            embedding=[0.0] * 1536,
        )
        db.session.add(second_chunk)
        db.session.commit()

        first_source = {
            "chunk_id": first_chunk.id,
            "document_id": first_document.id,
            "snippet": first_chunk.content,
            "score": 0.99,
            "document_title": first_document.title,
            "source_type": "text",
            "filename": None,
        }
        second_source = {
            "chunk_id": second_chunk.id,
            "document_id": second_document.id,
            "snippet": second_chunk.content,
            "score": 0.97,
            "document_title": second_document.title,
            "source_type": "text",
            "filename": None,
        }
        first_doc_id = first_document.id
        second_doc_id = second_document.id
    print(f"seeded document_ids={first_doc_id}, {second_doc_id}")

    hdr("CREATE CHAT SESSION")
    create_chat_response = client.post(
        "/api/chat/sessions",
        headers=auth_header(access_token),
        json={"title": "All Docs Chat"},
    )
    check(create_chat_response, 201)
    chat_id = create_chat_response.get_json()["id"]
    print(f"chat_id={chat_id}")

    hdr("VERIFY ALL-DOCS SEMANTICS")
    chat_documents_response = client.get(
        f"/api/chat/sessions/{chat_id}/documents",
        headers=auth_header(access_token),
    )
    check(chat_documents_response, 200)
    require(
        chat_documents_response.get_json()["documents"] == [],
        "fresh chat should use all-documents mode by default",
    )

    hdr("PATCH CHAT ANSWERING DEPENDENCIES")
    retrieve_calls: dict[str, dict] = {}

    def fake_retrieve_chunks(**kwargs):
        retrieve_calls["basic"] = kwargs
        return [first_source]

    def fake_retrieve_chunks_diversified(**kwargs):
        retrieve_calls["diversified"] = kwargs
        return [first_source, second_source]

    chat_api._select_model = lambda message: {
        "category": "general",
        "model": "openrouter/google/gemma-3-27b-it:free",
        "confidence": "high",
        "method": "test",
    }
    answering.retrieve_chunks = fake_retrieve_chunks
    answering.retrieve_chunks_diversified = fake_retrieve_chunks_diversified
    answering.get_client = lambda: FakeClient()

    hdr("POST /api/chat/sessions/<chat_id>/messages")
    send_response = client.post(
        f"/api/chat/sessions/{chat_id}/messages",
        headers=auth_header(access_token),
        json={"content": "Explain Python basics and functions using all my notes."},
    )
    check(send_response, 200)
    send_payload = send_response.get_json()

    require("basic" not in retrieve_calls, "all-doc chat flow should not use basic retrieval")
    require("diversified" in retrieve_calls, "all-doc chat flow should use diversified retrieval")
    require(
        retrieve_calls["diversified"]["document_ids"] is None,
        "all-doc chat flow should keep document_ids unset",
    )
    require(
        retrieve_calls["diversified"]["minimum_document_count"] == 2,
        "chat diversified retrieval should target two documents by default",
    )

    response_source_docs = {
        source["document_id"]
        for source in send_payload["assistant_message"]["sources"]
    }
    require(
        response_source_docs == {first_doc_id, second_doc_id},
        "assistant response should include sources from both ready documents",
    )
    print("chat response kept both documents in source coverage")

    hdr("GET /api/chat/sessions/<chat_id>/messages")
    history_response = client.get(
        f"/api/chat/sessions/{chat_id}/messages",
        headers=auth_header(access_token),
    )
    check(history_response, 200)
    history = history_response.get_json()
    require(len(history) == 2, "chat should contain one user message and one assistant message")
    history_source_docs = {
        source["document_id"]
        for source in history[1]["sources"]
    }
    require(
        history_source_docs == {first_doc_id, second_doc_id},
        "persisted assistant sources should include both documents",
    )
    print("persisted chat sources kept both documents")

    hdr("CHAT MULTI-DOCUMENT TEST PASSED")
    print("all-doc chat retrieval now preserves multi-document source coverage")

finally:
    chat_api._select_model = original_select_model
    answering.retrieve_chunks = original_retrieve_chunks
    answering.retrieve_chunks_diversified = original_retrieve_chunks_diversified
    answering.get_client = original_get_client
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if user is not None:
            db.session.delete(user)
            db.session.commit()
