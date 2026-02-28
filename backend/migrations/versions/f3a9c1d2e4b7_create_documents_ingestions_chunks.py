"""create documents, document_ingestions, chunks tables

Revision ID: f3a9c1d2e4b7
Revises: b0536757bfa6
Create Date: 2026-02-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = 'f3a9c1d2e4b7'
down_revision = 'b0536757bfa6'
branch_labels = None
depends_on = None


def upgrade():
    # Enable pgvector extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ── documents ────────────────────────────────────────────────────────
    op.create_table(
        'documents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=20), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=True),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('original_text', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('current_ingestion_id', sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_documents_user_id', 'documents', ['user_id'])

    # ── document_ingestions ──────────────────────────────────────────────
    op.create_table(
        'document_ingestions',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('source_type', sa.String(length=20), nullable=False),
        sa.Column('file_path', sa.String(length=500), nullable=True),
        sa.Column('text_snapshot', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='processing'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_document_ingestions_document_id', 'document_ingestions', ['document_id'])
    op.create_index('ix_document_ingestions_user_id', 'document_ingestions', ['user_id'])

    # Deferred circular FK: documents.current_ingestion_id -> document_ingestions.id
    op.create_foreign_key(
        'fk_documents_current_ingestion_id',
        'documents',
        'document_ingestions',
        ['current_ingestion_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # ── chunks ───────────────────────────────────────────────────────────
    op.create_table(
        'chunks',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('document_id', sa.String(length=36), nullable=False),
        sa.Column('ingestion_id', sa.String(length=36), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('page_start', sa.Integer(), nullable=True),
        sa.Column('page_end', sa.Integer(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['ingestion_id'], ['document_ingestions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ingestion_id', 'chunk_index', name='uq_chunks_ingestion_chunk_index'),
    )
    op.create_index('ix_chunks_user_id_ingestion_id', 'chunks', ['user_id', 'ingestion_id'])
    op.create_index('ix_chunks_user_id_document_id', 'chunks', ['user_id', 'document_id'])

    # Vector index (cosine) — 1536 dims is within pgvector's 2000-dim limit
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_chunks_embedding")
    op.drop_index('ix_chunks_user_id_document_id', table_name='chunks')
    op.drop_index('ix_chunks_user_id_ingestion_id', table_name='chunks')
    op.drop_table('chunks')

    op.drop_constraint('fk_documents_current_ingestion_id', 'documents', type_='foreignkey')

    op.drop_index('ix_document_ingestions_user_id', table_name='document_ingestions')
    op.drop_index('ix_document_ingestions_document_id', table_name='document_ingestions')
    op.drop_table('document_ingestions')

    op.drop_index('ix_documents_user_id', table_name='documents')
    op.drop_table('documents')
