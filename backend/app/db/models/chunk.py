from datetime import datetime, timezone
from pgvector.sqlalchemy import Vector
from app.extensions import db


class Chunk(db.Model):
    __tablename__ = "chunks"
    __table_args__ = (
        db.UniqueConstraint(
            "ingestion_id", "chunk_index", name="uq_chunks_ingestion_chunk_index"
        ),
        db.Index("ix_chunks_user_id_ingestion_id", "user_id", "ingestion_id"),
        db.Index("ix_chunks_user_id_document_id", "user_id", "document_id"),
    )

    id = db.Column(db.BigInteger, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.String(36),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id = db.Column(
        db.String(36),
        db.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    ingestion_id = db.Column(
        db.String(36),
        db.ForeignKey("document_ingestions.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index = db.Column(db.Integer, nullable=False)
    page_start = db.Column(db.Integer, nullable=True)
    page_end = db.Column(db.Integer, nullable=True)
    content = db.Column(db.Text, nullable=False)
    embedding = db.Column(Vector(1536), nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    document = db.relationship("Document", back_populates="chunks")
    ingestion = db.relationship("DocumentIngestion", back_populates="chunks")

    def __repr__(self):
        return f"<Chunk id={self.id} doc={self.document_id} idx={self.chunk_index}>"
