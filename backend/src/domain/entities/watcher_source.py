"""WatcherSource domain entity — registered audio source in the Source Registry."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from src.domain.enums.source_type import SourceType


class WatcherSource(BaseModel):
    """A registered source that the Watcher Service monitors for new audio files.

    The Source Registry holds all registered sources.
    Initially supports LOCAL_FILESYSTEM only; S3 extensible via SourceType enum.
    """

    model_config = {"frozen": False}

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., min_length=1, max_length=255, description="Human-readable source name")
    source_type: SourceType = Field(...)
    path: str = Field(
        ..., min_length=1, description="Filesystem path or S3 bucket/prefix"
    )
    file_patterns: list[str] = Field(
        default_factory=lambda: ["*.mp3", "*.wav", "*.mp4", "*.flac", "*.m4a"],
        description="Glob patterns for audio files to watch",
    )
    is_active: bool = Field(default=True)
    created_by: UUID = Field(..., description="Admin user who registered this source")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def deactivate(self) -> None:
        """Stop monitoring this source."""
        self.is_active = False
        self.updated_at = datetime.now(timezone.utc)

    def activate(self) -> None:
        """Resume monitoring this source."""
        self.is_active = True
        self.updated_at = datetime.now(timezone.utc)
