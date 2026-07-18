"""SQLAlchemy Core table definitions — no ORM models.

Using SQLAlchemy Core + asyncpg:
- Table objects for Alembic autogenerate
- Typed column definitions
- No ORM: repositories use Core select/insert/update/delete

Alembic reads metadata from here for migration autogeneration.
"""

import sqlalchemy as sa
from sqlalchemy import MetaData

# Naming convention for Alembic to generate deterministic constraint names
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)

# ─── users ────────────────────────────────────────────────────────────────────

users_table = sa.Table(
    "users",
    metadata,
    sa.Column("id", sa.UUID, primary_key=True),
    sa.Column("email", sa.String(255), nullable=False, unique=True),
    sa.Column("hashed_password", sa.String(255), nullable=False),
    sa.Column("role", sa.String(50), nullable=False, server_default="viewer"),
    sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    ),
)

# ─── audio_sources ────────────────────────────────────────────────────────────

audio_sources_table = sa.Table(
    "audio_sources",
    metadata,
    sa.Column("id", sa.UUID, primary_key=True),
    sa.Column("name", sa.String(255), nullable=False),
    sa.Column("source_type", sa.String(50), nullable=False),
    sa.Column("path", sa.Text, nullable=False),
    sa.Column(
        "file_patterns",
        sa.ARRAY(sa.Text),
        nullable=False,
        server_default="{}",
    ),
    sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("created_by", sa.UUID, sa.ForeignKey("users.id"), nullable=False),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
)

# ─── audio_jobs ───────────────────────────────────────────────────────────────

audio_jobs_table = sa.Table(
    "audio_jobs",
    metadata,
    sa.Column("id", sa.UUID, primary_key=True),
    sa.Column(
        "source_id",
        sa.UUID,
        sa.ForeignKey("audio_sources.id"),
        nullable=False,
    ),
    sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
    sa.Column("file_name", sa.String(500), nullable=False),
    sa.Column("original_path", sa.Text, nullable=False),
    sa.Column("file_hash", sa.String(64), nullable=True),
    sa.Column("storage_path", sa.Text, nullable=True),
    # Audio metadata stored as JSONB for flexibility
    sa.Column("metadata", sa.JSON, nullable=True),
    sa.Column("error_message", sa.Text, nullable=True),
    sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("created_by", sa.UUID, sa.ForeignKey("users.id"), nullable=True),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    # Index for common query patterns
    sa.Index("ix_audio_jobs_status", "status"),
    sa.Index("ix_audio_jobs_source_id", "source_id"),
    sa.Index("ix_audio_jobs_file_hash", "file_hash"),
    sa.Index(
        "ix_audio_jobs_original_path_source",
        "original_path",
        "source_id",
        unique=True,
    ),
)

# ─── transcripts ──────────────────────────────────────────────────────────────

transcripts_table = sa.Table(
    "transcripts",
    metadata,
    sa.Column("id", sa.UUID, primary_key=True),
    sa.Column(
        "job_id",
        sa.UUID,
        sa.ForeignKey("audio_jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One transcript per job
    ),
    sa.Column("raw_text", sa.Text, nullable=False),
    sa.Column("repaired_text", sa.Text, nullable=True),
    sa.Column("language", sa.String(10), nullable=False),
    sa.Column("confidence", sa.Float, nullable=False),
    # Diarized segments stored as JSONB array
    sa.Column("segments", sa.JSON, nullable=False, server_default="[]"),
    # Whisper word-level timestamps — consumed by RepairWorker for diarization
    sa.Column("word_timestamps", sa.JSON, nullable=False, server_default="[]"),
    sa.Column("is_repaired", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("is_diarized", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Column(
        "updated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Index("ix_transcripts_job_id", "job_id"),
)

# ─── analyses ─────────────────────────────────────────────────────────────────

analyses_table = sa.Table(
    "analyses",
    metadata,
    sa.Column("id", sa.UUID, primary_key=True),
    sa.Column(
        "job_id",
        sa.UUID,
        sa.ForeignKey("audio_jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    sa.Column(
        "transcript_id",
        sa.UUID,
        sa.ForeignKey("transcripts.id"),
        nullable=False,
    ),
    # All analysis fields stored as JSONB — schema enforced by Pydantic domain entity
    sa.Column("agent_performance_score", sa.Float, nullable=False),
    sa.Column("customer_satisfaction_score", sa.Float, nullable=False),
    sa.Column("call_resolution_score", sa.Float, nullable=False),
    sa.Column("empathy_score", sa.Float, nullable=False),
    sa.Column("closing_effectiveness_score", sa.Float, nullable=False),
    sa.Column("closing_signal_detected", sa.Boolean, nullable=False),
    sa.Column("upsell_attempt_detected", sa.Boolean, nullable=False),
    sa.Column("compliance_passed", sa.Boolean, nullable=False),
    # Complex nested structures as JSONB
    sa.Column("objection_handling", sa.JSON, nullable=False),
    sa.Column("agent_sentiment", sa.JSON, nullable=False),
    sa.Column("customer_sentiment", sa.JSON, nullable=False),
    sa.Column("compliance_flags", sa.JSON, nullable=False, server_default="[]"),
    sa.Column("call_metrics", sa.JSON, nullable=False),
    sa.Column("summary", sa.Text, nullable=False),
    sa.Column("strengths", sa.JSON, nullable=False, server_default="[]"),
    sa.Column("improvement_areas", sa.JSON, nullable=False, server_default="[]"),
    sa.Column("recommendation", sa.Text, nullable=False),
    sa.Column("coaching_notes", sa.Text, nullable=True),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Index("ix_analyses_job_id", "job_id"),
    sa.Index("ix_analyses_compliance_passed", "compliance_passed"),
)

# ─── reports ──────────────────────────────────────────────────────────────────

reports_table = sa.Table(
    "reports",
    metadata,
    sa.Column("id", sa.UUID, primary_key=True),
    sa.Column(
        "job_id",
        sa.UUID,
        sa.ForeignKey("audio_jobs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    sa.Column(
        "analysis_id",
        sa.UUID,
        sa.ForeignKey("analyses.id"),
        nullable=False,
    ),
    sa.Column(
        "transcript_id",
        sa.UUID,
        sa.ForeignKey("transcripts.id"),
        nullable=False,
    ),
    sa.Column("title", sa.String(500), nullable=False),
    sa.Column("storage_path", sa.Text, nullable=True),
    sa.Column("overall_score", sa.Float, nullable=False),
    sa.Column("call_duration_seconds", sa.Float, nullable=False),
    sa.Column("compliance_passed", sa.Boolean, nullable=False),
    sa.Column("agent_sentiment", sa.String(50), nullable=False),
    sa.Column("customer_sentiment", sa.String(50), nullable=False),
    sa.Column("summary", sa.Text, nullable=False),
    sa.Column(
        "generated_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Index("ix_reports_job_id", "job_id"),
)

# ─── job_events ───────────────────────────────────────────────────────────────

job_events_table = sa.Table(
    "job_events",
    metadata,
    sa.Column("id", sa.UUID, primary_key=True),
    sa.Column(
        "job_id",
        sa.UUID,
        sa.ForeignKey("audio_jobs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("event_type", sa.String(100), nullable=False),
    sa.Column("old_status", sa.String(50), nullable=True),
    sa.Column("new_status", sa.String(50), nullable=False),
    sa.Column("worker", sa.String(100), nullable=True),
    sa.Column("message", sa.Text, nullable=True),
    sa.Column("metadata", sa.JSON, nullable=True),
    sa.Column(
        "occurred_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    ),
    sa.Index("ix_job_events_job_id", "job_id"),
    sa.Index("ix_job_events_occurred_at", "occurred_at"),
)
