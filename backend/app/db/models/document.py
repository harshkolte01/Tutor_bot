import uuid
from datetime import datetime, timezone
from app.extensions import db


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(
        db.String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(255), nullable=False)
    source_type = db.Column(db.String(20), nullable=False)  # 'upload' | 'text'
    filename = db.Column(db.String(255), nullable=True)
    mime_type = db.Column(db.String(100), nullable=True)
    original_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    current_ingestion_id = db.Column(
        db.String(36),
        db.ForeignKey(
            "document_ingestions.id",
            use_alter=True,
            name="fk_documents_current_ingestion_id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # Relationships
    ingestions = db.relationship(
        "DocumentIngestion",
        foreign_keys="DocumentIngestion.document_id",
        back_populates="document",
        lazy="dynamic",
    )
    current_ingestion = db.relationship(
        "DocumentIngestion",
        foreign_keys=[current_ingestion_id],
        post_update=True,
    )
    chunks = db.relationship(
        "Chunk",
        back_populates="document",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Document {self.id} title={self.title!r} source_type={self.source_type!r}>"
