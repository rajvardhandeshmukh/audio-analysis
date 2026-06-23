"""Call metrics value object — computed from diarized speaker segments.

Captures the quantitative measurements for a call center / sales call.
Produced by AnalysisWorker, consumed by Report generation.
"""

from pydantic import BaseModel, Field, model_validator


class CallMetrics(BaseModel):
    """Quantitative metrics derived from speaker-diarized transcript.

    All time percentages sum to 100.0 (agent + customer + silence + overlap).
    Immutable after construction.
    """

    model_config = {"frozen": True}

    # ─── Talk time ────────────────────────────────────────────────────────────
    agent_talk_time_pct: float = Field(
        ..., ge=0.0, le=100.0, description="Percentage of call time agent is speaking"
    )
    customer_talk_time_pct: float = Field(
        ..., ge=0.0, le=100.0, description="Percentage of call time customer is speaking"
    )
    silence_pct: float = Field(
        ..., ge=0.0, le=100.0, description="Percentage of call time with silence"
    )
    overlap_pct: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Percentage of simultaneous speech"
    )

    # ─── Interaction quality ──────────────────────────────────────────────────
    interruption_count: int = Field(
        default=0, ge=0, description="Number of times speech was interrupted"
    )
    longest_silence_seconds: float = Field(
        default=0.0, ge=0.0, description="Longest continuous silence in seconds"
    )
    average_response_time_seconds: float = Field(
        default=0.0, ge=0.0, description="Average time between speaker turns"
    )
    total_duration_seconds: float = Field(
        ..., gt=0.0, description="Total call duration in seconds"
    )
    agent_word_count: int = Field(
        default=0, ge=0, description="Total words spoken by agent"
    )
    customer_word_count: int = Field(
        default=0, ge=0, description="Total words spoken by customer"
    )

    @model_validator(mode="after")
    def validate_percentages_sum(self) -> "CallMetrics":
        total = (
            self.agent_talk_time_pct
            + self.customer_talk_time_pct
            + self.silence_pct
            + self.overlap_pct
        )
        # Allow small floating-point tolerance
        if abs(total - 100.0) > 1.0:
            raise ValueError(
                f"Talk time percentages must sum to ~100. Got {total:.2f}. "
                f"(agent={self.agent_talk_time_pct}, customer={self.customer_talk_time_pct}, "
                f"silence={self.silence_pct}, overlap={self.overlap_pct})"
            )
        return self

    @property
    def talk_ratio(self) -> float:
        """Agent-to-customer talk ratio. Values >1 mean agent talks more."""
        if self.customer_talk_time_pct == 0:
            return float("inf")
        return self.agent_talk_time_pct / self.customer_talk_time_pct
