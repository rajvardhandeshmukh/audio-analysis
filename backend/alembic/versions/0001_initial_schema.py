"""Initial schema — all tables.

Revision ID: 0001_initial_schema
Revises: (base)
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    op.create_table(
        "audio_sources",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("file_patterns", sa.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_audio_sources_created_by_users"),
        sa.PrimaryKeyConstraint("id", name="pk_audio_sources"),
    )

    op.create_table(
        "audio_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["source_id"], ["audio_sources.id"], name="fk_audio_jobs_source_id_audio_sources"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_audio_jobs_created_by_users"),
        sa.PrimaryKeyConstraint("id", name="pk_audio_jobs"),
        sa.UniqueConstraint("original_path", "source_id", name="ix_audio_jobs_original_path_source"),
    )
    op.create_index("ix_audio_jobs_status", "audio_jobs", ["status"])
    op.create_index("ix_audio_jobs_source_id", "audio_jobs", ["source_id"])

    op.create_table(
        "transcripts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("repaired_text", sa.Text(), nullable=True),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("segments", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("word_timestamps", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("is_repaired", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_diarized", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["audio_jobs.id"], name="fk_transcripts_job_id_audio_jobs", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_transcripts"),
        sa.UniqueConstraint("job_id", name="uq_transcripts_job_id"),
    )
    op.create_index("ix_transcripts_job_id", "transcripts", ["job_id"])

    op.create_table(
        "analyses",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("transcript_id", sa.UUID(), nullable=False),
        sa.Column("agent_performance_score", sa.Float(), nullable=False),
        sa.Column("customer_satisfaction_score", sa.Float(), nullable=False),
        sa.Column("call_resolution_score", sa.Float(), nullable=False),
        sa.Column("empathy_score", sa.Float(), nullable=False),
        sa.Column("closing_effectiveness_score", sa.Float(), nullable=False),
        sa.Column("closing_signal_detected", sa.Boolean(), nullable=False),
        sa.Column("upsell_attempt_detected", sa.Boolean(), nullable=False),
        sa.Column("compliance_passed", sa.Boolean(), nullable=False),
        sa.Column("objection_handling", sa.JSON(), nullable=False),
        sa.Column("agent_sentiment", sa.JSON(), nullable=False),
        sa.Column("customer_sentiment", sa.JSON(), nullable=False),
        sa.Column("compliance_flags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("call_metrics", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("improvement_areas", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("coaching_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["audio_jobs.id"], name="fk_analyses_job_id_audio_jobs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], name="fk_analyses_transcript_id_transcripts"),
        sa.PrimaryKeyConstraint("id", name="pk_analyses"),
        sa.UniqueConstraint("job_id", name="uq_analyses_job_id"),
    )
    op.create_index("ix_analyses_job_id", "analyses", ["job_id"])
    op.create_index("ix_analyses_compliance_passed", "analyses", ["compliance_passed"])

    op.create_table(
        "reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("analysis_id", sa.UUID(), nullable=False),
        sa.Column("transcript_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=True),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column("call_duration_seconds", sa.Float(), nullable=False),
        sa.Column("compliance_passed", sa.Boolean(), nullable=False),
        sa.Column("agent_sentiment", sa.String(50), nullable=False),
        sa.Column("customer_sentiment", sa.String(50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["audio_jobs.id"], name="fk_reports_job_id_audio_jobs", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"], name="fk_reports_analysis_id_analyses"),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"], name="fk_reports_transcript_id_transcripts"),
        sa.PrimaryKeyConstraint("id", name="pk_reports"),
        sa.UniqueConstraint("job_id", name="uq_reports_job_id"),
    )
    op.create_index("ix_reports_job_id", "reports", ["job_id"])

    op.create_table(
        "job_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("job_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("old_status", sa.String(50), nullable=True),
        sa.Column("new_status", sa.String(50), nullable=False),
        sa.Column("worker", sa.String(100), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["job_id"], ["audio_jobs.id"], name="fk_job_events_job_id_audio_jobs", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_job_events"),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])
    op.create_index("ix_job_events_occurred_at", "job_events", ["occurred_at"])


def downgrade() -> None:
    op.drop_table("job_events")
    op.drop_table("reports")
    op.drop_table("analyses")
    op.drop_table("transcripts")
    op.drop_table("audio_jobs")
    op.drop_table("audio_sources")
    op.drop_table("users")
