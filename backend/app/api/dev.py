"""
Dev-only internal smoke endpoint for verifying wrapper client connectivity.

Endpoint:  GET /api/dev/wrapper-smoke
Auth:      JWT required (prevents accidental public exposure)
Purpose:   Tests one chat call and one embedding call through the wrapper.

This blueprint is only relevant in development. In production it can be left
registered (it is JWT-gated) or excluded via config if preferred.
"""

from flask import Blueprint, jsonify, current_app
from flask_jwt_extended import jwt_required

from app.services.wrapper.client import get_client, WrapperError

dev_bp = Blueprint("dev", __name__, url_prefix="/api/dev")


@dev_bp.get("/wrapper-smoke")
@jwt_required()
def wrapper_smoke():
    """
    Run a minimal chat completion and a minimal embedding call.
    Returns a JSON summary of both results.
    """
    results = {}

    # ── Chat smoke ───────────────────────────────────────────────────────────
    try:
        client = get_client()
        chat_resp = client.chat_completions(
            model=current_app.config.get(
                "WRAPPER_DEFAULT_MODEL", "routeway/glm-4.5-air:free"
            ),
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=8,
        )
        choice = chat_resp.get("choices", [{}])[0]
        results["chat"] = {
            "status": "ok",
            "model": chat_resp.get("model"),
            "reply": choice.get("message", {}).get("content", "").strip(),
        }
    except WrapperError as exc:
        results["chat"] = {
            "status": "error",
            "message": str(exc),
            "upstream_status": exc.status_code,
        }

    # ── Embedding smoke ──────────────────────────────────────────────────────
    try:
        client = get_client()
        emb_resp = client.embeddings(
            model=current_app.config.get(
                "WRAPPER_EMBEDDING_MODEL", "gemini/gemini-embedding-001"
            ),
            input="hello world",
        )
        data = emb_resp.get("data", [{}])
        vector = data[0].get("embedding", []) if data else []
        results["embedding"] = {
            "status": "ok",
            "model": emb_resp.get("model"),
            "dimensions": len(vector),
        }
    except WrapperError as exc:
        results["embedding"] = {
            "status": "error",
            "message": str(exc),
            "upstream_status": exc.status_code,
        }

    overall_ok = all(v.get("status") == "ok" for v in results.values())
    return jsonify({"ok": overall_ok, "results": results}), 200 if overall_ok else 502
