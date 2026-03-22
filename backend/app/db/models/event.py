from datetime import datetime, timezone

from app.extensions import db


class Event(db.Model):
    __tablename__ = "events"
    __table_args__ = (
        db.Index("ix_events_user_created_at", "user_id", "created_at"),
        db.Index("ix_events_user_event_type", "user_id", "event_type"),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(50), nullable=True)
    entity_id = db.Column(db.String(64), nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<Event id={self.id} type={self.event_type!r} user={self.user_id}>"
