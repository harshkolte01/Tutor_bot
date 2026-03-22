from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.db.models.event import Event
from app.extensions import db

EVENT_DOC_UPLOADED = "doc_uploaded"
EVENT_DOC_TEXT_ADDED = "doc_text_added"
EVENT_CHAT_ASKED = "chat_asked"
EVENT_QUIZ_CREATED = "quiz_created"
EVENT_QUIZ_SUBMITTED = "quiz_submitted"

EVENT_TYPES = (
    EVENT_DOC_UPLOADED,
    EVENT_DOC_TEXT_ADDED,
    EVENT_CHAT_ASKED,
    EVENT_QUIZ_CREATED,
    EVENT_QUIZ_SUBMITTED,
)
EVENT_TYPE_SET = set(EVENT_TYPES)


def empty_event_counts() -> dict[str, int]:
    return {event_type: 0 for event_type in EVENT_TYPES}


def record_event(
    user_id: str,
    event_type: str,
    *,
    entity_type: str | None = None,
    entity_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    created_at: datetime | None = None,
) -> Event:
    if event_type not in EVENT_TYPE_SET:
        raise ValueError(f"Unsupported analytics event type: {event_type}")

    event = Event(
        user_id=user_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=dict(metadata) if metadata else None,
        created_at=created_at or datetime.now(timezone.utc),
    )
    db.session.add(event)
    return event
