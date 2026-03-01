"""
Documents API — upload, text context, listing, detail, delete, ingestion status.

Routes
------
POST   /api/documents/upload                            multipart file upload
POST   /api/documents/text                              JSON {title, text}
GET    /api/documents                                   list user's documents
GET    /api/documents/<id>                              document detail
DELETE /api/documents/<id>                              soft delete
GET    /api/documents/<id>/ingestions/<ingestion_id>/status
"""

import os
import uuid
import logging
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required
from werkzeug.utils import secure_filename

from app.db.models.chunk import Chunk
from app.db.models.document import Document
from app.db.models.document_ingestion import DocumentIngestion
from app.extensions import db
from app.services.rag.ingestion import ingest_text, ingest_upload

log = logging.getLogger(__name__)

documents_bp = Blueprint("documents", __name__, url_prefix="/api/documents")

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
}
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".text"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB hard cap


# ── Helpers ───────────────────────────────────────────────────────────────────

def _allowed_file(filename: str, mimetype: str) -> bool:
    ext = os.path.splitext(filename.lower())[1]
    return ext in ALLOWED_EXTENSIONS or mimetype in ALLOWED_MIME_TYPES


def _upload_folder() -> str:
    folder = current_app.config.get("UPLOAD_FOLDER") or os.path.join(
        current_app.instance_path, "uploads"
    )
    os.makedirs(folder, exist_ok=True)
    return folder


def _doc_dict(doc: Document) -> dict:
    return {
        "id": doc.id,
        "title": doc.title,
        "source_type": doc.source_type,
        "filename": doc.filename,
        "mime_type": doc.mime_type,
        "created_at": doc.created_at.isoformat(),
        "is_deleted": doc.is_deleted,
        "current_ingestion_id": doc.current_ingestion_id,
    }


def _ingestion_dict(ing: DocumentIngestion) -> dict:
    return {
        "id": ing.id,
        "document_id": ing.document_id,
        "source_type": ing.source_type,
        "status": ing.status,
        "error_message": ing.error_message,
        "created_at": ing.created_at.isoformat(),
        "completed_at": ing.completed_at.isoformat() if ing.completed_at else None,
    }


# ── POST /api/documents/upload ────────────────────────────────────────────────

@documents_bp.post("/upload")
@jwt_required()
def upload_document():
    user_id = get_jwt_identity()

    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400

    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"error": "No file selected"}), 400

    filename = secure_filename(file.filename)
    mime_type = file.content_type or "application/octet-stream"

    if not _allowed_file(filename, mime_type):
        return jsonify({"error": "File type not allowed. Upload PDF or plain text."}), 415

    # Read and size-check
    data = file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return jsonify({"error": f"File exceeds {MAX_UPLOAD_BYTES // (1024*1024)} MB limit"}), 413

    title = (request.form.get("title") or "").strip() or os.path.splitext(filename)[0]

    # Save file to disk
    unique_name = f"{uuid.uuid4()}_{filename}"
    folder = _upload_folder()
    file_path = os.path.join(folder, unique_name)
    with open(file_path, "wb") as fh:
        fh.write(data)

    # Create Document row
    doc = Document(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=title,
        source_type="upload",
        filename=filename,
        mime_type=mime_type,
    )
    db.session.add(doc)
    db.session.flush()  # get doc.id before creating ingestion

    # Create DocumentIngestion row
    ingestion = DocumentIngestion(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        user_id=user_id,
        source_type="upload",
        file_path=file_path,
        status="processing",
    )
    db.session.add(ingestion)
    db.session.commit()

    # Run ingestion pipeline (synchronous)
    try:
        ingest_upload(doc, ingestion, file_path)
    except Exception as exc:
        log.warning("Upload ingestion failed for doc=%s: %s", doc.id, exc)
        # ingestion already marked failed inside ingest_upload
        return jsonify({
            "document": _doc_dict(doc),
            "ingestion": _ingestion_dict(ingestion),
            "warning": "Ingestion failed. See ingestion status for details.",
        }), 202

    return jsonify({
        "document": _doc_dict(doc),
        "ingestion": _ingestion_dict(ingestion),
    }), 201


# ── POST /api/documents/text ──────────────────────────────────────────────────

@documents_bp.post("/text")
@jwt_required()
def text_document():
    user_id = get_jwt_identity()
    data = request.get_json(silent=True) or {}

    title = (data.get("title") or "").strip()
    text = (data.get("text") or "").strip()

    if not title:
        return jsonify({"error": "'title' is required"}), 400
    if not text:
        return jsonify({"error": "'text' is required"}), 400
    if len(text) > 5_000_000:
        return jsonify({"error": "Text exceeds 5 MB limit"}), 413

    # Create Document row
    doc = Document(
        id=str(uuid.uuid4()),
        user_id=user_id,
        title=title,
        source_type="text",
        original_text=text,
    )
    db.session.add(doc)
    db.session.flush()

    # Create DocumentIngestion row
    ingestion = DocumentIngestion(
        id=str(uuid.uuid4()),
        document_id=doc.id,
        user_id=user_id,
        source_type="text",
        text_snapshot=text,
        status="processing",
    )
    db.session.add(ingestion)
    db.session.commit()

    # Run ingestion pipeline (synchronous)
    try:
        ingest_text(doc, ingestion, text)
    except Exception as exc:
        log.warning("Text ingestion failed for doc=%s: %s", doc.id, exc)
        return jsonify({
            "document": _doc_dict(doc),
            "ingestion": _ingestion_dict(ingestion),
            "warning": "Ingestion failed. See ingestion status for details.",
        }), 202

    return jsonify({
        "document": _doc_dict(doc),
        "ingestion": _ingestion_dict(ingestion),
    }), 201


# ── GET /api/documents ────────────────────────────────────────────────────────

@documents_bp.get("")
@jwt_required()
def list_documents():
    user_id = get_jwt_identity()
    docs = (
        Document.query
        .filter_by(user_id=user_id, is_deleted=False)
        .order_by(Document.created_at.desc())
        .all()
    )
    return jsonify({"documents": [_doc_dict(d) for d in docs]}), 200


# ── GET /api/documents/<id> ───────────────────────────────────────────────────

@documents_bp.get("/<string:doc_id>")
@jwt_required()
def get_document(doc_id: str):
    user_id = get_jwt_identity()
    doc = Document.query.filter_by(id=doc_id, user_id=user_id, is_deleted=False).first()
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    ingestion = None
    if doc.current_ingestion_id:
        ingestion = DocumentIngestion.query.get(doc.current_ingestion_id)

    return jsonify({
        "document": _doc_dict(doc),
        "current_ingestion": _ingestion_dict(ingestion) if ingestion else None,
    }), 200


# ── DELETE /api/documents/<id> ────────────────────────────────────────────────

@documents_bp.delete("/<string:doc_id>")
@jwt_required()
def delete_document(doc_id: str):
    user_id = get_jwt_identity()
    doc = Document.query.filter_by(id=doc_id, user_id=user_id, is_deleted=False).first()
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    doc.is_deleted = True
    db.session.commit()
    return jsonify({"message": "Document deleted"}), 200


# ── GET /api/documents/<id>/ingestions/<ingestion_id>/status ──────────────────

@documents_bp.get("/<string:doc_id>/ingestions/<string:ingestion_id>/status")
@jwt_required()
def ingestion_status(doc_id: str, ingestion_id: str):
    user_id = get_jwt_identity()

    doc = Document.query.filter_by(id=doc_id, user_id=user_id).first()
    if not doc:
        return jsonify({"error": "Document not found"}), 404

    ingestion = DocumentIngestion.query.filter_by(
        id=ingestion_id, document_id=doc_id, user_id=user_id
    ).first()
    if not ingestion:
        return jsonify({"error": "Ingestion not found"}), 404

    chunk_count = (
        Chunk.query.filter_by(ingestion_id=ingestion_id).count()
        if ingestion.status == "ready"
        else None
    )

    result = _ingestion_dict(ingestion)
    result["chunk_count"] = chunk_count
    return jsonify(result), 200
