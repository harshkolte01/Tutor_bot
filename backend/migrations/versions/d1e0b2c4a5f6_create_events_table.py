"""create events table

Revision ID: d1e0b2c4a5f6
Revises: 8553dfd2f555
Create Date: 2026-03-22 16:20:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "d1e0b2c4a5f6"
down_revision = "8553dfd2f555"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.create_index("ix_events_user_created_at", ["user_id", "created_at"], unique=False)
        batch_op.create_index("ix_events_user_event_type", ["user_id", "event_type"], unique=False)


def downgrade():
    with op.batch_alter_table("events", schema=None) as batch_op:
        batch_op.drop_index("ix_events_user_event_type")
        batch_op.drop_index("ix_events_user_created_at")

    op.drop_table("events")
