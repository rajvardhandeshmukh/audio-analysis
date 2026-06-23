"""Audio metadata value object.

Immutable. Validated on construction. No infrastructure imports.
"""

from pydantic import BaseModel, Field, field_validator

SUPPORTED_FORMATS: frozenset[str] = frozenset(
    {"mp3", "mp4", "wav", "flac", "ogg", "webm", "m4a", "aac"}
)
MIN_DURATION_SECONDS: float = 1.0
MAX_DURATION_SECONDS: float = 14400.0  # 4 hours
MAX_FILE_SIZE_BYTES: int = 500 * 1024 * 1024  # 500 MB


class AudioMetadata(BaseModel):
    """Immutable value object describing audio file properties.

    Validated at domain boundary — all fields must satisfy constraints
    before an AudioJob can be created.
    """

    model_config = {"frozen": True}

    duration_seconds: float = Field(..., gt=0, description="Audio duration in seconds")
    sample_rate: int = Field(..., gt=0, description="Sample rate in Hz")
    channels: int = Field(..., ge=1, le=2, description="1=mono, 2=stereo")
    format: str = Field(..., description="Audio format (extension without dot)")
    size_bytes: int = Field(..., gt=0, description="File size in bytes")
    bit_rate: int | None = Field(default=None, gt=0, description="Bit rate in bps")

    @field_validator("format")
    @classmethod
    def validate_format(cls, value: str) -> str:
        normalised = value.lower().lstrip(".")
        if normalised not in SUPPORTED_FORMATS:
            raise ValueError(
                f"Unsupported audio format '{normalised}'. "
                f"Supported: {sorted(SUPPORTED_FORMATS)}"
            )
        return normalised

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration(cls, value: float) -> float:
        if value < MIN_DURATION_SECONDS:
            raise ValueError(
                f"Audio too short: {value:.1f}s. Minimum is {MIN_DURATION_SECONDS}s."
            )
        if value > MAX_DURATION_SECONDS:
            raise ValueError(
                f"Audio too long: {value:.1f}s. Maximum is {MAX_DURATION_SECONDS}s."
            )
        return value

    @field_validator("size_bytes")
    @classmethod
    def validate_size(cls, value: int) -> int:
        if value > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File too large: {value / 1024 / 1024:.1f} MB. "
                f"Maximum is {MAX_FILE_SIZE_BYTES / 1024 / 1024:.0f} MB."
            )
        return value

    @property
    def duration_minutes(self) -> float:
        """Returns duration converted to minutes."""
        return self.duration_seconds / 60.0

    @property
    def is_stereo(self) -> bool:
        """Returns True if audio is stereo (2 channels)."""
        return self.channels == 2
