from __future__ import annotations

from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.db.models.document import Document
from app.db.models.quiz import Quiz
from app.db.models.quiz_attempt import QuizAttempt
from app.db.models.quiz_attempt_answer import QuizAttemptAnswer
from app.db.models.quiz_question import QuizQuestion
from app.db.models.quiz_question_source import QuizQuestionSource
from app.extensions import db
from app.services.analytics.events import EVENT_QUIZ_SUBMITTED, record_event
from app.services.quiz.generator import QuizGenerationError, generate_and_store_quiz
from app.services.quiz.grading import QuizGradingError, grade_quiz_submission
from app.services.quiz.spec_parser import QuizRequestSpec, QuizSpecError, parse_quiz_request
from app.services.quiz.summarizer import summarize_attempt

quizzes_bp = Blueprint("quizzes", __name__, url_prefix="/api/quizzes")


def _quiz_to_dict(quiz: Quiz) -> dict:
    return {
        "id": quiz.id,
        "title": quiz.title,
        "instructions": quiz.instructions,
        "spec": quiz.spec_json,
        "total_marks": quiz.total_marks,
        "time_limit_sec": quiz.time_limit_sec,
        "model_used": quiz.model_used,
        "created_at": quiz.created_at.isoformat(),
        "question_count": quiz.questions.count(),
    }


def _source_to_dict(source: QuizQuestionSource) -> dict:
    return {
        "chunk_id": source.chunk_id,
        "document_id": source.document_id,
        "similarity_score": source.similarity_score,
        "snippet": source.snippet,
    }


def _attempt_to_dict(attempt: QuizAttempt) -> dict:
    return {
        "id": attempt.id,
        "quiz_id": attempt.quiz_id,
        "user_id": attempt.user_id,
        "started_at": attempt.started_at.isoformat(),
        "submitted_at": attempt.submitted_at.isoformat() if attempt.submitted_at else None,
        "time_spent_sec": attempt.time_spent_sec,
        "score": attempt.score,
        "total_marks": attempt.total_marks,
        "summary": attempt.summary_json,
    }


def _question_to_dict(question: QuizQuestion, *, include_sources: bool = True) -> dict:
    payload = {
        "id": question.id,
        "quiz_id": question.quiz_id,
        "question_index": question.question_index,
        "type": question.type,
        "question_text": question.question_text,
        "options": question.options_json,
        "marks": question.marks,
    }
    if include_sources:
        payload["sources"] = [_source_to_dict(source) for source in question.sources]
    return payload


def _attempt_answer_to_dict(
    attempt_answer: QuizAttemptAnswer,
    *,
    include_correct: bool,
) -> dict:
    question = attempt_answer.question
    payload = {
        "id": attempt_answer.id,
        "question_id": attempt_answer.question_id,
        "question_index": question.question_index,
        "type": question.type,
        "question_text": question.question_text,
        "options": question.options_json,
        "marks": question.marks,
        "chosen_json": attempt_answer.chosen_json,
        "is_correct": attempt_answer.is_correct,
        "marks_awarded": attempt_answer.marks_awarded,
        "sources": [_source_to_dict(source) for source in question.sources],
    }
    if include_correct:
        payload["correct_json"] = question.correct_json
        payload["explanation"] = question.explanation
    return payload


def _validate_document_ids(
    user_id: str,
    spec: QuizRequestSpec,
) -> tuple[bool, tuple[dict, int] | None]:
    if not spec.document_ids:
        return True, None

    documents = Document.query.filter(
        Document.id.in_(spec.document_ids),
        Document.user_id == user_id,
        Document.is_deleted.is_(False),
    ).all()
    if len(documents) != len(spec.document_ids):
        return False, ({"error": "one or more document IDs were not found"}, 404)

    not_ready = [document.id for document in documents if not document.current_ingestion_id]
    if not_ready:
        return False, (
            {"error": "one or more selected documents do not have a ready ingestion"},
            400,
        )

    return True, None


def _parse_time_spent_sec(payload: dict, attempt: QuizAttempt) -> int:
    if payload.get("time_spent_sec") is not None:
        try:
            time_spent_sec = int(payload.get("time_spent_sec"))
        except (TypeError, ValueError):
            raise QuizGradingError("time_spent_sec must be an integer")
        if time_spent_sec < 0:
            raise QuizGradingError("time_spent_sec must be >= 0")
        return time_spent_sec

    elapsed = datetime.now(timezone.utc) - attempt.started_at
    return max(0, int(elapsed.total_seconds()))


def _load_attempt_answers(attempt_id: str) -> list[QuizAttemptAnswer]:
    return (
        QuizAttemptAnswer.query
        .join(QuizQuestion, QuizQuestion.id == QuizAttemptAnswer.question_id)
        .filter(QuizAttemptAnswer.attempt_id == attempt_id)
        .order_by(QuizQuestion.question_index.asc())
        .all()
    )


@quizzes_bp.post("")
@jwt_required()
def create_quiz():
    user_id = get_jwt_identity()

    try:
        spec = parse_quiz_request(request.get_json(silent=True) or {})
    except QuizSpecError as exc:
        return jsonify({"error": str(exc)}), 400

    ok, error_response = _validate_document_ids(user_id=user_id, spec=spec)
    if not ok and error_response is not None:
        body, status_code = error_response
        return jsonify(body), status_code

    try:
        quiz = generate_and_store_quiz(user_id=user_id, spec=spec)
    except QuizGenerationError as exc:
        return jsonify({"error": str(exc)}), exc.status_code

    questions = quiz.questions.order_by(QuizQuestion.question_index.asc()).all()
    return jsonify(
        {
            "quiz": _quiz_to_dict(quiz),
            "questions": [_question_to_dict(question) for question in questions],
        }
    ), 201


@quizzes_bp.get("")
@jwt_required()
def list_quizzes():
    user_id = get_jwt_identity()
    quizzes = (
        Quiz.query
        .filter_by(user_id=user_id)
        .order_by(Quiz.created_at.desc())
        .all()
    )
    return jsonify({"quizzes": [_quiz_to_dict(quiz) for quiz in quizzes]}), 200


@quizzes_bp.get("/<string:quiz_id>")
@jwt_required()
def get_quiz(quiz_id: str):
    user_id = get_jwt_identity()
    quiz = Quiz.query.filter_by(id=quiz_id, user_id=user_id).first()
    if not quiz:
        return jsonify({"error": "quiz not found"}), 404

    return jsonify({"quiz": _quiz_to_dict(quiz)}), 200


@quizzes_bp.get("/<string:quiz_id>/questions")
@jwt_required()
def get_quiz_questions(quiz_id: str):
    user_id = get_jwt_identity()
    quiz = Quiz.query.filter_by(id=quiz_id, user_id=user_id).first()
    if not quiz:
        return jsonify({"error": "quiz not found"}), 404

    questions = quiz.questions.order_by(QuizQuestion.question_index.asc()).all()
    return jsonify(
        {
            "quiz": _quiz_to_dict(quiz),
            "questions": [_question_to_dict(question) for question in questions],
        }
    ), 200


@quizzes_bp.post("/<string:quiz_id>/attempts/start")
@jwt_required()
def start_quiz_attempt(quiz_id: str):
    user_id = get_jwt_identity()
    quiz = Quiz.query.filter_by(id=quiz_id, user_id=user_id).first()
    if not quiz:
        return jsonify({"error": "quiz not found"}), 404

    attempt = QuizAttempt(
        quiz_id=quiz.id,
        user_id=user_id,
        total_marks=quiz.total_marks,
    )
    db.session.add(attempt)
    db.session.commit()

    questions = quiz.questions.order_by(QuizQuestion.question_index.asc()).all()
    return jsonify(
        {
            "attempt": _attempt_to_dict(attempt),
            "quiz": _quiz_to_dict(quiz),
            "questions": [_question_to_dict(question) for question in questions],
            "answers": [],
        }
    ), 201


@quizzes_bp.post("/<string:quiz_id>/attempts/<string:attempt_id>/submit")
@jwt_required()
def submit_quiz_attempt(quiz_id: str, attempt_id: str):
    user_id = get_jwt_identity()

    attempt = QuizAttempt.query.filter_by(
        id=attempt_id,
        quiz_id=quiz_id,
        user_id=user_id,
    ).first()
    if not attempt:
        return jsonify({"error": "quiz attempt not found"}), 404
    if attempt.submitted_at is not None:
        return jsonify({"error": "quiz attempt has already been submitted"}), 409

    quiz = Quiz.query.filter_by(id=quiz_id, user_id=user_id).first()
    if not quiz:
        return jsonify({"error": "quiz not found"}), 404

    payload = request.get_json(silent=True) or {}
    answers_payload = payload.get("answers", [])
    questions = quiz.questions.order_by(QuizQuestion.question_index.asc()).all()

    try:
        grading_result = grade_quiz_submission(
            questions=questions,
            submitted_answers=answers_payload,
        )
        time_spent_sec = _parse_time_spent_sec(payload, attempt)
    except QuizGradingError as exc:
        return jsonify({"error": str(exc)}), 400

    attempt.answers.delete(synchronize_session=False)
    for result in grading_result["results"]:
        question = result["question"]
        db.session.add(
            QuizAttemptAnswer(
                attempt_id=attempt.id,
                question_id=question.id,
                chosen_json=result["chosen_json"],
                is_correct=result["is_correct"],
                marks_awarded=result["marks_awarded"],
            )
        )

    attempt.submitted_at = datetime.now(timezone.utc)
    attempt.time_spent_sec = time_spent_sec
    attempt.score = grading_result["score"]
    attempt.total_marks = grading_result["total_marks"]
    attempt.summary_json = summarize_attempt(quiz=quiz, grading_result=grading_result)

    score_percent = round((attempt.score / attempt.total_marks) * 100, 2) if attempt.total_marks else 0.0
    topic = quiz.spec_json.get("topic") if isinstance(quiz.spec_json, dict) else None
    record_event(
        user_id=user_id,
        event_type=EVENT_QUIZ_SUBMITTED,
        entity_type="quiz_attempt",
        entity_id=attempt.id,
        metadata={
            "attempt_id": attempt.id,
            "quiz_id": quiz.id,
            "topic": topic or quiz.title,
            "score": attempt.score,
            "total_marks": attempt.total_marks,
            "score_percent": score_percent,
        },
    )
    db.session.commit()

    answers = _load_attempt_answers(attempt.id)
    return jsonify(
        {
            "attempt": _attempt_to_dict(attempt),
            "quiz": _quiz_to_dict(quiz),
            "score": attempt.score,
            "total_marks": attempt.total_marks,
            "summary": attempt.summary_json,
            "questions": [_question_to_dict(question) for question in questions],
            "answers": [
                _attempt_answer_to_dict(answer, include_correct=True)
                for answer in answers
            ],
        }
    ), 200


@quizzes_bp.get("/attempts/<string:attempt_id>")
@jwt_required()
def get_quiz_attempt(attempt_id: str):
    user_id = get_jwt_identity()
    attempt = QuizAttempt.query.filter_by(id=attempt_id, user_id=user_id).first()
    if not attempt:
        return jsonify({"error": "quiz attempt not found"}), 404

    quiz = Quiz.query.filter_by(id=attempt.quiz_id, user_id=user_id).first()
    if not quiz:
        return jsonify({"error": "quiz not found"}), 404

    include_correct = attempt.submitted_at is not None
    questions = quiz.questions.order_by(QuizQuestion.question_index.asc()).all()
    answers = _load_attempt_answers(attempt.id)

    return jsonify(
        {
            "attempt": _attempt_to_dict(attempt),
            "quiz": _quiz_to_dict(quiz),
            "questions": [_question_to_dict(question) for question in questions],
            "answers": [
                _attempt_answer_to_dict(answer, include_correct=include_correct)
                for answer in answers
            ],
        }
    ), 200
