"""Speaker segment value object — output of diarization in transcript repair."""

from pydantic import BaseModel, Field


class SpeakerSegment(BaseModel):
    """Represents a contiguous speech segment attributed to one speaker.

    Immutable. Produced by the RepairWorker after diarization.
    Used by AnalysisWorker to compute per-speaker metrics.
    """

    model_config = {"frozen": True}

    speaker_id: str = Field(
        ...,
        pattern=r"^SPEAKER_\d+$",
        description="Diarization label e.g. 'SPEAKER_0', 'SPEAKER_1'",
    )
    start_time: float = Field(..., ge=0.0, description="Segment start in seconds")
    end_time: float = Field(..., gt=0.0, description="Segment end in seconds")
    text: str = Field(..., min_length=1, description="Transcribed text for this segment")
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0, description="STT confidence score for segment"
    )

    @property
    def duration(self) -> float:
        """Duration of this segment in seconds."""
        return self.end_time - self.start_time

    def model_post_init(self, __context: object) -> None:
        if self.end_time <= self.start_time:
            raise ValueError(
                f"end_time ({self.end_time}) must be greater than "
                f"start_time ({self.start_time})"
            )
