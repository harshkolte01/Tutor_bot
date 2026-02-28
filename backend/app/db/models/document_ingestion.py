import uuid
from datetime import datetime, timezone
from app.extensions import db


class DocumentIngestion(db.Model):
    __tablename__ = "document_ingestions"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    document_id = db.Column(
        db.String(36),
        db.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_type = db.Column(db.String(20), nullable=False)  # 'upload' | 'text'
    file_path = db.Column(db.String(500), nullable=True)
    text_snapshot = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.String(20), nullable=False, default="processing"
    )  # processing | ready | failed
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    document = db.relationship(
        "Document",
        foreign_keys=[document_id],
        back_populates="ingestions",
    )
    chunks = db.relationship(
        "Chunk",
        back_populates="ingestion",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<DocumentIngestion {self.id} status={self.status!r}>"
