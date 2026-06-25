from flask import Blueprint, jsonify

from app.services.wrapper.status import get_ai_agent_status

ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")


@ai_bp.get("/status")
def ai_status():
    return jsonify(get_ai_agent_status()), 200
