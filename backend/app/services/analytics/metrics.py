from __future__ import annotations

from datetime import datetime, time, timedelta, timezone

from sqlalchemy import func

from app.db.models.chat import Chat
from app.db.models.document import Document
from app.db.models.event import Event
from app.db.models.quiz import Quiz
from app.db.models.quiz_attempt import QuizAttempt
from app.db.models.quiz_attempt_answer import QuizAttemptAnswer
from app.extensions import db
from app.services.analytics.events import EVENT_TYPES, empty_event_counts

DEFAULT_PROGRESS_DAYS = 14
DEFAULT_WEAK_TOPICS_LIMIT = 5


def get_overview_metrics(user_id: str) -> dict:
    event_counts = empty_event_counts()
    rows = (
        db.session.query(Event.event_type, func.count(Event.id))
        .filter(Event.user_id == user_id)
        .group_by(Event.event_type)
        .all()
    )
    for event_type, count in rows:
        if event_type in event_counts:
            event_counts[event_type] = int(count)

    submitted_attempts = (
        QuizAttempt.query
        .filter(
            QuizAttempt.user_id == user_id,
            QuizAttempt.submitted_at.isnot(None),
        )
        .all()
    )
    latest_activity_at = (
        db.session.query(func.max(Event.created_at))
        .filter(Event.user_id == user_id)
        .scalar()
    )

    return {
        "totals": {
            "documents": Document.query.filter_by(user_id=user_id, is_deleted=False).count(),
            "uploaded_documents": Document.query.filter_by(
                user_id=user_id,
                is_deleted=False,
                source_type="upload",
            ).count(),
            "text_documents": Document.query.filter_by(
                user_id=user_id,
                is_deleted=False,
                source_type="text",
            ).count(),
            "chat_sessions": Chat.query.filter_by(user_id=user_id).count(),
            "quizzes": Quiz.query.filter_by(user_id=user_id).count(),
            "submitted_attempts": len(submitted_attempts),
        },
        "event_counts": event_counts,
        "average_score_percent": _average_score_percent(submitted_attempts),
        "latest_activity_at": _isoformat_or_none(latest_activity_at),
    }


def get_progress_metrics(
    user_id: str,
    *,
    days: int = DEFAULT_PROGRESS_DAYS,
) -> dict:
    day_count = max(1, int(days))
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=day_count - 1)
    start_at = datetime.combine(start_date, time.min, tzinfo=timezone.utc)

    activity_buckets = {
        day.isoformat(): {
            "date": day.isoformat(),
            "total": 0,
            **empty_event_counts(),
        }
        for day in _iter_days(start_date, today)
    }

    events = (
        Event.query
        .filter(
            Event.user_id == user_id,
            Event.created_at >= start_at,
        )
        .order_by(Event.created_at.asc())
        .all()
    )
    for event in events:
        day_key = _to_utc_date(event.created_at).isoformat()
        bucket = activity_buckets.get(day_key)
        if not bucket or event.event_type not in EVENT_TYPES:
            continue
        bucket[event.event_type] += 1
        bucket["total"] += 1

    attempts = (
        QuizAttempt.query
        .filter(
            QuizAttempt.user_id == user_id,
            QuizAttempt.submitted_at.isnot(None),
            QuizAttempt.submitted_at >= start_at,
        )
        .order_by(QuizAttempt.submitted_at.asc())
        .all()
    )
    score_buckets = {
        day.isoformat(): {
            "date": day.isoformat(),
            "attempt_count": 0,
            "average_score": None,
            "average_total_marks": None,
            "average_score_percent": None,
            "_score_total": 0.0,
            "_total_marks_total": 0.0,
        }
        for day in _iter_days(start_date, today)
    }
    for attempt in attempts:
        day_key = _to_utc_date(attempt.submitted_at).isoformat()
        bucket = score_buckets.get(day_key)
        if bucket is None:
            continue
        bucket["attempt_count"] += 1
        bucket["_score_total"] += float(attempt.score or 0.0)
        bucket["_total_marks_total"] += float(attempt.total_marks or 0.0)

    for bucket in score_buckets.values():
        if bucket["attempt_count"] <= 0:
            continue
        bucket["average_score"] = round(bucket["_score_total"] / bucket["attempt_count"], 2)
        bucket["average_total_marks"] = round(
            bucket["_total_marks_total"] / bucket["attempt_count"],
            2,
        )
        if bucket["_total_marks_total"] > 0:
            bucket["average_score_percent"] = round(
                (bucket["_score_total"] / bucket["_total_marks_total"]) * 100,
                2,
            )

    daily_activity = list(activity_buckets.values())
    quiz_score_trend = []
    for bucket in score_buckets.values():
        bucket.pop("_score_total", None)
        bucket.pop("_total_marks_total", None)
        quiz_score_trend.append(bucket)

    total_events = sum(item["total"] for item in daily_activity)
    active_days = sum(1 for item in daily_activity if item["total"] > 0)
    total_score = sum(float(attempt.score or 0.0) for attempt in attempts)
    total_marks = sum(float(attempt.total_marks or 0.0) for attempt in attempts)

    return {
        "summary": {
            "days": day_count,
            "active_days": active_days,
            "total_events": total_events,
            "submitted_attempts": len(attempts),
            "average_score_percent": round((total_score / total_marks) * 100, 2)
            if total_marks > 0
            else None,
        },
        "daily_activity": daily_activity,
        "quiz_score_trend": quiz_score_trend,
    }


def get_weak_topics_metrics(
    user_id: str,
    *,
    limit: int = DEFAULT_WEAK_TOPICS_LIMIT,
) -> dict:
    rows = (
        db.session.query(
            Quiz.id.label("quiz_id"),
            Quiz.title.label("quiz_title"),
            Quiz.spec_json.label("spec_json"),
            QuizAttempt.id.label("attempt_id"),
            QuizAttempt.submitted_at.label("submitted_at"),
            QuizAttempt.score.label("score"),
            QuizAttempt.total_marks.label("total_marks"),
            QuizAttemptAnswer.is_correct.label("is_correct"),
        )
        .join(QuizAttempt, QuizAttempt.quiz_id == Quiz.id)
        .join(QuizAttemptAnswer, QuizAttemptAnswer.attempt_id == QuizAttempt.id)
        .filter(
            Quiz.user_id == user_id,
            QuizAttempt.user_id == user_id,
            QuizAttempt.submitted_at.isnot(None),
        )
        .all()
    )

    buckets: dict[str, dict] = {}
    for row in rows:
        topic = _topic_from_row(row.quiz_title, row.spec_json)
        bucket_key = topic.lower()
        bucket = buckets.setdefault(
            bucket_key,
            {
                "topic": topic,
                "quiz_ids": set(),
                "attempt_ids": set(),
                "question_count": 0,
                "correct_count": 0,
                "incorrect_count": 0,
                "unanswered_count": 0,
                "score_total": 0.0,
                "total_marks_total": 0.0,
                "latest_attempt_at": None,
            },
        )
        bucket["quiz_ids"].add(row.quiz_id)
        bucket["question_count"] += 1

        if row.is_correct is True:
            bucket["correct_count"] += 1
        elif row.is_correct is False:
            bucket["incorrect_count"] += 1
        else:
            bucket["unanswered_count"] += 1

        if row.attempt_id not in bucket["attempt_ids"]:
            bucket["attempt_ids"].add(row.attempt_id)
            bucket["score_total"] += float(row.score or 0.0)
            bucket["total_marks_total"] += float(row.total_marks or 0.0)

        latest_attempt_at = row.submitted_at
        if latest_attempt_at is not None:
            current_latest = bucket["latest_attempt_at"]
            if current_latest is None or latest_attempt_at > current_latest:
                bucket["latest_attempt_at"] = latest_attempt_at

    weak_topics = []
    for bucket in buckets.values():
        question_count = bucket["question_count"]
        total_marks_total = bucket["total_marks_total"]
        weak_topics.append(
            {
                "topic": bucket["topic"],
                "quiz_count": len(bucket["quiz_ids"]),
                "attempt_count": len(bucket["attempt_ids"]),
                "question_count": question_count,
                "correct_count": bucket["correct_count"],
                "incorrect_count": bucket["incorrect_count"],
                "unanswered_count": bucket["unanswered_count"],
                "accuracy_percent": round(
                    (bucket["correct_count"] / question_count) * 100,
                    2,
                )
                if question_count > 0
                else None,
                "average_score_percent": round(
                    (bucket["score_total"] / total_marks_total) * 100,
                    2,
                )
                if total_marks_total > 0
                else None,
                "latest_attempt_at": _isoformat_or_none(bucket["latest_attempt_at"]),
            }
        )

    weak_topics.sort(
        key=lambda item: (
            item["accuracy_percent"] if item["accuracy_percent"] is not None else 101.0,
            item["average_score_percent"] if item["average_score_percent"] is not None else 101.0,
            -item["question_count"],
            item["topic"].lower(),
        )
    )

    return {"weak_topics": weak_topics[: max(1, int(limit))]}


def _average_score_percent(attempts: list[QuizAttempt]) -> float | None:
    total_marks = sum(float(attempt.total_marks or 0.0) for attempt in attempts)
    if total_marks <= 0:
        return None
    total_score = sum(float(attempt.score or 0.0) for attempt in attempts)
    return round((total_score / total_marks) * 100, 2)


def _iter_days(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)


def _topic_from_row(quiz_title: str | None, spec_json) -> str:
    if isinstance(spec_json, dict):
        topic = str(spec_json.get("topic") or "").strip()
        if topic:
            return topic
    title = str(quiz_title or "").strip()
    return title or "Untitled Quiz"


def _isoformat_or_none(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _to_utc_date(value: datetime):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date()
