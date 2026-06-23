"""WordTimestamp value object — single word with start/end time from Whisper.

Stored in Transcript.word_timestamps after STT processing.
Used by RepairProvider for speaker diarization (grouping words into speaker turns).
"""

from pydantic import BaseModel, Field


class WordTimestamp(BaseModel):
    """A single word with its position in the audio stream."""

    model_config = {"frozen": True}

    word: str = Field(..., description="The transcribed word token")
    start: float = Field(..., ge=0.0, description="Word start time in seconds")
    end: float = Field(..., ge=0.0, description="Word end time in seconds")
    probability: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Whisper word-level confidence"
    )
