"""
Chat API

Endpoints
---------
POST  /api/chat/sessions                         – create a new chat session
GET   /api/chat/sessions                         – list user's chat sessions
GET   /api/chat/sessions/<chat_id>/messages      – get messages for a session
POST  /api/chat/sessions/<chat_id>/messages      – send a message + get answer

All routes require a valid JWT access token (Bearer in Authorization header).
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.db.models.chat import Chat
from app.db.models.chat_message import ChatMessage
from app.db.models.chat_message_source import ChatMessageSource
from app.db.models.document import Document
from app.extensions import db
from app.services.analytics.events import EVENT_CHAT_ASKED, record_event
from app.services.rag.answering import generate_answer
from app.services.router.classifier import classify
from app.services.router.heuristics import route as heuristics_route
from app.services.wrapper.client import WrapperError

log = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__, url_prefix="/api/chat")

# Maximum prior turns to include as history in the LLM prompt
_MAX_HISTORY_TURNS = 10


# ── Helpers ───────────────────────────────────────────────────────────────────

def _chat_to_dict(chat: Chat) -> dict:
    return {
        "id":         chat.id,
        "title":      chat.title,
        "created_at": chat.created_at.isoformat(),
        "updated_at": chat.updated_at.isoformat(),
    }


def _message_to_dict(msg: ChatMessage, include_sources: bool = False) -> dict:
    d = {
        "id":         msg.id,
        "chat_id":    msg.chat_id,
        "role":       msg.role,
        "content":    msg.content,
        "model_used": msg.model_used,
        "created_at": msg.created_at.isoformat(),
    }
    if include_sources:
        d["sources"] = [_source_to_dict(s) for s in msg.sources]
    return d


def _source_to_dict(src: ChatMessageSource) -> dict:
    return {
        "chunk_id":        src.chunk_id,
        "document_id":     src.document_id,
        "similarity_score": src.similarity_score,
        "snippet":         src.snippet,
    }


def _select_model(message: str) -> dict:
    """Run heuristics then classifier if uncertain. Return router decision."""
    decision = heuristics_route(message)
    if decision["confidence"] == "low":
        decision = classify(message)
    return decision


# ── POST /api/chat/sessions ───────────────────────────────────────────────────

@chat_bp.post("/sessions")
@jwt_required()
def create_session():
    """Create a new chat session for the authenticated user."""
    user_id = get_jwt_identity()
    data    = request.get_json(silent=True) or {}
    title   = (data.get("title") or "New Chat").strip()[:255]

    chat = Chat(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=title,
    )
    db.session.add(chat)
    db.session.commit()

    return jsonify(_chat_to_dict(chat)), 201


# ── GET /api/chat/sessions ────────────────────────────────────────────────────

@chat_bp.get("/sessions")
@jwt_required()
def list_sessions():
    """Return all chat sessions for the authenticated user, newest first."""
    user_id = get_jwt_identity()
    chats = (
        Chat.query
        .filter_by(user_id=user_id)
        .order_by(Chat.updated_at.desc())
        .all()
    )
    return jsonify([_chat_to_dict(c) for c in chats]), 200


# ── GET /api/chat/sessions/<chat_id>/messages ─────────────────────────────────

@chat_bp.get("/sessions/<chat_id>/messages")
@jwt_required()
def get_messages(chat_id: str):
    """Return all messages for a session, oldest first, with sources."""
    user_id = get_jwt_identity()

    chat = Chat.query.filter_by(id=chat_id, user_id=user_id).first()
    if not chat:
        return jsonify({"error": "chat session not found"}), 404

    messages = (
        ChatMessage.query
        .filter_by(chat_id=chat_id, user_id=user_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    return jsonify([_message_to_dict(m, include_sources=True) for m in messages]), 200


# ── POST /api/chat/sessions/<chat_id>/messages ────────────────────────────────

@chat_bp.post("/sessions/<chat_id>/messages")
@jwt_required()
def send_message(chat_id: str):
    """
    Send a user message to a session and receive an AI-generated answer.

    Request body (JSON):
        content : str  – the user's message (required)

    Response (JSON):
        user_message      : MessageDict
        assistant_message : MessageDict (with sources)
        router            : dict  – routing decision metadata
    """
    user_id = get_jwt_identity()

    # ── Validate session ownership ───────────────────────────────────────────
    chat = Chat.query.filter_by(id=chat_id, user_id=user_id).first()
    if not chat:
        return jsonify({"error": "chat session not found"}), 404

    data    = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "content is required"}), 400
    use_general_knowledge = bool(data.get("use_general_knowledge", False))

    # ── 1. Save user message ─────────────────────────────────────────────────
    user_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        user_id=user_id,
        role="user",
        content=content,
    )
    db.session.add(user_msg)
    db.session.flush()  # get id without committing yet

    # ── 2. Route: pick model ─────────────────────────────────────────────────
    router_decision = _select_model(content)
    selected_model  = router_decision["model"]

    # ── 3. Build conversation history for context ────────────────────────────
    prior_messages = (
        ChatMessage.query
        .filter_by(chat_id=chat_id, user_id=user_id)
        .filter(ChatMessage.role.in_(["user", "assistant"]))
        .order_by(ChatMessage.created_at.desc())
        .limit(_MAX_HISTORY_TURNS * 2)   # each turn = 2 messages
        .all()
    )
    # Reverse to chronological order (oldest first); exclude the just-flushed user msg
    prior_messages = [m for m in reversed(prior_messages) if m.id != user_msg.id]
    history = [{"role": m.role, "content": m.content} for m in prior_messages]

    # ── 4. Load per-chat document filter ──────────────────────────────────────
    selected_docs   = chat.selected_documents.filter(
        Document.is_deleted.is_(False),
        Document.current_ingestion_id.isnot(None),
    ).all()
    doc_ids_filter  = [d.id for d in selected_docs] if selected_docs else None

    # ── 5. Generate RAG answer ────────────────────────────────────────────
    try:
        result = generate_answer(
            question=content,
            user_id=user_id,
            model=selected_model,
            history=history,
            document_ids=doc_ids_filter,
            use_general_knowledge=use_general_knowledge,
        )
    except WrapperError as exc:
        log.error("chat answering failed for user=%s: %s", user_id, exc)
        db.session.rollback()
        return jsonify({"error": "AI service unavailable, please try again"}), 503

    answer_text  = result["answer"]
    model_used   = result["model"]
    sources_data = result["sources"]

    # ── 6. Save assistant message ─────────────────────────────────────────────
    assistant_msg = ChatMessage(
        id=str(uuid.uuid4()),
        chat_id=chat_id,
        user_id=user_id,
        role="assistant",
        content=answer_text,
        model_used=model_used,
        router_json=json.dumps(router_decision),
    )
    db.session.add(assistant_msg)
    db.session.flush()

    # ── 7. Save source mappings ────────────────────────────────────────────────
    seen_chunk_ids: set = set()
    for src in sources_data:
        chunk_id = src.get("chunk_id")
        if chunk_id is None or chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        db.session.add(
            ChatMessageSource(
                message_id=assistant_msg.id,
                chunk_id=chunk_id,
                document_id=src["document_id"],
                similarity_score=src["score"],
                snippet=src.get("snippet"),
            )
        )

    # ── 8. Update chat timestamp ──────────────────────────────────────────────
    chat.updated_at = datetime.now(timezone.utc)

    # Auto-title the session after the first real exchange
    if chat.title == "New Chat" and content:
        chat.title = content[:80]

    record_event(
        user_id=user_id,
        event_type=EVENT_CHAT_ASKED,
        entity_type="chat_message",
        entity_id=user_msg.id,
        metadata={
            "chat_id": chat_id,
            "assistant_message_id": assistant_msg.id,
            "selected_document_count": len(doc_ids_filter or []),
            "model_used": model_used,
            "out_of_context": bool(result.get("out_of_context", False)),
        },
    )
    db.session.commit()

    # ── 9. Reload sources with relationships ──────────────────────────────────
    db.session.refresh(assistant_msg)

    return jsonify(
        {
            "user_message":      _message_to_dict(user_msg),
            "assistant_message": _message_to_dict(assistant_msg, include_sources=True),
            "router":            router_decision,
            "out_of_context":    result.get("out_of_context", False),
        }
    ), 200


# ── GET /api/chat/sessions/<chat_id>/documents ────────────────────────────────

@chat_bp.get("/sessions/<chat_id>/documents")
@jwt_required()
def get_chat_documents(chat_id: str):
    """
    Return the documents currently pinned to this chat for RAG context.
    An empty list means 'search all documents'.
    """
    user_id = get_jwt_identity()

    chat = Chat.query.filter_by(id=chat_id, user_id=user_id).first()
    if not chat:
        return jsonify({"error": "chat session not found"}), 404

    docs = chat.selected_documents.filter(
        Document.is_deleted.is_(False),
    ).all()

    return jsonify(
        {
            "chat_id":   chat_id,
            "documents": [
                {
                    "id":          d.id,
                    "title":       d.title,
                    "source_type": d.source_type,
                    "filename":    d.filename,
                }
                for d in docs
            ],
        }
    ), 200


# ── PUT /api/chat/sessions/<chat_id>/documents ────────────────────────────────

@chat_bp.put("/sessions/<chat_id>/documents")
@jwt_required()
def set_chat_documents(chat_id: str):
    """
    Replace the document selection for a chat session.

    Request body (JSON):
        document_ids : list[str]  – IDs to pin (empty list = use all docs)

    All supplied IDs must belong to the authenticated user and must not be
    deleted; otherwise the whole request is rejected.
    """
    user_id = get_jwt_identity()

    chat = Chat.query.filter_by(id=chat_id, user_id=user_id).first()
    if not chat:
        return jsonify({"error": "chat session not found"}), 404

    data    = request.get_json(silent=True) or {}
    doc_ids = data.get("document_ids", [])

    if not isinstance(doc_ids, list):
        return jsonify({"error": "document_ids must be a list"}), 400

    # De-duplicate
    doc_ids = list(dict.fromkeys(doc_ids))

    if doc_ids:
        docs = Document.query.filter(
            Document.id.in_(doc_ids),
            Document.user_id == user_id,
            Document.is_deleted.is_(False),
        ).all()
        if len(docs) != len(doc_ids):
            return jsonify({"error": "one or more document IDs not found"}), 404
    else:
        docs = []

    # Replace selection (SQLAlchemy takes care of the junction rows)
    chat.selected_documents = docs
    db.session.commit()

    return jsonify(
        {
            "chat_id":      chat_id,
            "document_ids": [d.id for d in docs],
        }
    ), 200
