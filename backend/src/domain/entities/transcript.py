"""Transcript domain entity — output of STT and Repair workers."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.domain.value_objects.speaker_segment import SpeakerSegment
from src.domain.value_objects.word_timestamp import WordTimestamp


class Transcript(BaseModel):
    """Represents a processed audio transcript.

    Lifecycle:
        1. Created by STT Worker with raw_text and no segments.
        2. Updated by Repair Worker: repaired_text + speaker segments added.
    """

    model_config = {"frozen": False}

    id: UUID = Field(default_factory=uuid4)
    job_id: UUID = Field(..., description="Parent AudioJob ID")

    # ─── STT output ───────────────────────────────────────────────────────────
    raw_text: str = Field(..., min_length=1, description="Raw STT output, uncorrected")
    language: str = Field(..., description="Detected language code e.g. 'en'")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Overall STT confidence")
    word_timestamps: list[WordTimestamp] = Field(
        default_factory=list,
        description="Word-level timestamps from Whisper — used by RepairWorker for diarization",
    )

    # ─── Repair Worker output ─────────────────────────────────────────────────
    repaired_text: str | None = Field(
        default=None, description="LLM-corrected transcript text"
    )
    segments: list[SpeakerSegment] = Field(
        default_factory=list,
        description="Diarized speaker segments (populated by RepairWorker)",
    )
    is_repaired: bool = Field(default=False)
    is_diarized: bool = Field(default=False)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def apply_repair(self, repaired_text: str) -> None:
        """Apply LLM-corrected text from Repair Worker."""
        self.repaired_text = repaired_text
        self.is_repaired = True
        self.updated_at = datetime.now(timezone.utc)

    def apply_diarization(self, segments: list[SpeakerSegment]) -> None:
        """Apply speaker-diarized segments from Repair Worker."""
        self.segments = segments
        self.is_diarized = True
        self.updated_at = datetime.now(timezone.utc)

    @property
    def effective_text(self) -> str:
        """Returns repaired text if available, otherwise raw STT output."""
        return self.repaired_text if self.repaired_text else self.raw_text

    @property
    def unique_speakers(self) -> set[str]:
        """Returns the set of unique speaker IDs from diarization."""
        return {seg.speaker_id for seg in self.segments}

    def get_speaker_text(self, speaker_id: str) -> str:
        """Returns concatenated text for a specific speaker."""
        return " ".join(
            seg.text for seg in self.segments if seg.speaker_id == speaker_id
        )
