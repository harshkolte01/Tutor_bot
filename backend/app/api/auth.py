from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    jwt_required,
    get_jwt_identity,
)
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db
from app.db.models.user import User
import uuid

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


# ── Register ────────────────────────────────────────────────────────────────

@auth_bp.post("/register")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")
    username = (data.get("username") or "").strip() or None

    # Validation
    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "email already registered"}), 409
    if username and User.query.filter_by(username=username).first():
        return jsonify({"error": "username already taken"}), 409

    user = User(
        id=str(uuid.uuid4()),
        email=email,
        username=username,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    return jsonify(
        {
            "message": "Account created",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": _user_dict(user),
        }
    ), 201


# ── Login ────────────────────────────────────────────────────────────────────

@auth_bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "invalid credentials"}), 401
    if not user.is_active:
        return jsonify({"error": "account is disabled"}), 403

    access_token = create_access_token(identity=user.id)
    refresh_token = create_refresh_token(identity=user.id)

    return jsonify(
        {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": _user_dict(user),
        }
    ), 200


# ── Refresh ──────────────────────────────────────────────────────────────────

@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    user_id = get_jwt_identity()
    access_token = create_access_token(identity=user_id)
    return jsonify({"access_token": access_token}), 200


# ── Me ───────────────────────────────────────────────────────────────────────

@auth_bp.get("/me")
@jwt_required()
def me():
    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404
    return jsonify({"user": _user_dict(user)}), 200


# Password

@auth_bp.post("/password")
@jwt_required()
def change_password():
    data = request.get_json(silent=True) or {}
    current_password = data.get("current_password") or data.get("old_password") or ""
    new_password = data.get("new_password") or ""

    if not current_password or not new_password:
        return jsonify({"error": "old password and new password are required"}), 400
    if len(new_password) < 8:
        return jsonify({"error": "new password must be at least 8 characters"}), 400

    user_id = get_jwt_identity()
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404
    if not user.is_active:
        return jsonify({"error": "account is disabled"}), 403
    if not user.check_password(current_password):
        return jsonify({"error": "old password is incorrect"}), 401
    if user.check_password(new_password):
        return jsonify({"error": "new password must be different from old password"}), 400

    user.set_password(new_password)
    db.session.commit()
    return jsonify({"message": "Password updated"}), 200


# Helpers

def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "created_at": user.created_at.isoformat(),
        "is_active": user.is_active,
    }
