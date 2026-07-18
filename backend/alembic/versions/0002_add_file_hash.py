"""Add file_hash column to audio_jobs.

Revision ID: 0002_add_file_hash
Revises: 0001_initial_schema
Create Date: 2026-06-29
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_add_file_hash"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("audio_jobs", sa.Column("file_hash", sa.String(64), nullable=True))
    op.create_index("ix_audio_jobs_file_hash", "audio_jobs", ["file_hash"])


def downgrade() -> None:
    op.drop_index("ix_audio_jobs_file_hash", table_name="audio_jobs")
    op.drop_column("audio_jobs", "file_hash")
