from flask import Blueprint, jsonify
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services.analytics.metrics import (
    get_overview_metrics,
    get_progress_metrics,
    get_weak_topics_metrics,
)

analytics_bp = Blueprint("analytics", __name__, url_prefix="/api/analytics")


@analytics_bp.get("/overview")
@jwt_required()
def analytics_overview():
    user_id = get_jwt_identity()
    return jsonify(get_overview_metrics(user_id)), 200


@analytics_bp.get("/progress")
@jwt_required()
def analytics_progress():
    user_id = get_jwt_identity()
    return jsonify(get_progress_metrics(user_id)), 200


@analytics_bp.get("/weak-topics")
@jwt_required()
def analytics_weak_topics():
    user_id = get_jwt_identity()
    return jsonify(get_weak_topics_metrics(user_id)), 200
