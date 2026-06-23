"""Analysis domain entity — output of the Behavioral Analysis Worker.

Specific to call center and sales call use cases.
Schema is structured so LLM output maps directly to it (Rule 27).
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.domain.value_objects.call_metrics import CallMetrics


class ComplianceFlag(BaseModel):
    """A single detected compliance issue or required phrase."""

    model_config = {"frozen": True}

    flag_type: str = Field(..., description="Category e.g. 'MISSING_DISCLOSURE', 'PROHIBITED_TERM'")
    description: str = Field(..., description="Human-readable explanation")
    severity: str = Field(..., pattern=r"^(low|medium|high|critical)$")
    timestamp_seconds: float | None = Field(
        default=None, description="Approximate position in audio where flag occurred"
    )


class ObjectionHandling(BaseModel):
    """Assessment of how the agent handled customer objections."""

    model_config = {"frozen": True}

    objections_detected: int = Field(default=0, ge=0)
    objections_addressed: int = Field(default=0, ge=0)
    score: float = Field(..., ge=0.0, le=10.0, description="Objection handling score 0-10")
    examples: list[str] = Field(
        default_factory=list,
        description="Quoted examples from transcript",
    )


class SentimentScore(BaseModel):
    """Sentiment assessment for a call participant."""

    model_config = {"frozen": True}

    overall: str = Field(..., pattern=r"^(positive|neutral|negative)$")
    score: float = Field(..., ge=-1.0, le=1.0, description="-1 very negative, +1 very positive")
    trend: str = Field(
        ...,
        pattern=r"^(improving|stable|declining)$",
        description="Sentiment direction over the call",
    )


class Analysis(BaseModel):
    """Behavioral analysis result for a call center / sales call.

    Produced by AnalysisWorker via GPT-4o structured output.
    The JSON schema here is the exact contract sent to the LLM (Rule 27).
    """

    model_config = {"frozen": False}

    id: UUID = Field(default_factory=uuid4)
    job_id: UUID = Field(..., description="Parent AudioJob ID")
    transcript_id: UUID = Field(..., description="Source Transcript ID")

    # ─── Scores (all 0–10 unless stated) ─────────────────────────────────────
    agent_performance_score: float = Field(
        ..., ge=0.0, le=10.0, description="Overall agent performance score"
    )
    customer_satisfaction_score: float = Field(
        ..., ge=0.0, le=10.0, description="Estimated customer satisfaction score"
    )
    call_resolution_score: float = Field(
        ..., ge=0.0, le=10.0, description="Whether the call issue was resolved"
    )
    empathy_score: float = Field(
        ..., ge=0.0, le=10.0, description="Agent empathy and emotional intelligence score"
    )
    closing_effectiveness_score: float = Field(
        ..., ge=0.0, le=10.0, description="Effectiveness of call close / next steps"
    )

    # ─── Sales specific ───────────────────────────────────────────────────────
    closing_signal_detected: bool = Field(
        default=False, description="Whether the agent attempted a closing signal"
    )
    upsell_attempt_detected: bool = Field(
        default=False, description="Whether an upsell was attempted"
    )
    objection_handling: ObjectionHandling = Field(...)

    # ─── Sentiment ────────────────────────────────────────────────────────────
    agent_sentiment: SentimentScore = Field(...)
    customer_sentiment: SentimentScore = Field(...)

    # ─── Compliance ───────────────────────────────────────────────────────────
    compliance_flags: list[ComplianceFlag] = Field(default_factory=list)
    compliance_passed: bool = Field(
        default=True, description="False if any high/critical compliance flags exist"
    )

    # ─── Call Metrics ─────────────────────────────────────────────────────────
    call_metrics: CallMetrics = Field(...)

    # ─── Summary & Recommendations ───────────────────────────────────────────
    summary: str = Field(..., min_length=1, description="Executive summary of the call")
    strengths: list[str] = Field(
        default_factory=list, description="What the agent did well"
    )
    improvement_areas: list[str] = Field(
        default_factory=list, description="Areas for agent improvement"
    )
    recommendation: str = Field(
        ..., description="Primary actionable recommendation for the agent"
    )
    coaching_notes: str | None = Field(
        default=None, description="Manager-facing coaching notes"
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context: object) -> None:
        """Auto-compute compliance_passed based on flag severity."""
        critical_flags = [
            f for f in self.compliance_flags if f.severity in ("high", "critical")
        ]
        self.compliance_passed = len(critical_flags) == 0
