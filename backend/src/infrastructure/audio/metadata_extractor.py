"""Local audio metadata extractor using mutagen.

Used by STT Worker during ingestion to validate and tag jobs
before uploading to object storage. Fast, no network calls.
"""

import os

import mutagen

from src.domain.errors.domain_errors import InvalidAudioFormatError
from src.domain.value_objects.audio_metadata import AudioMetadata
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_SUPPORTED_EXTENSIONS = frozenset({".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4"})
_MAX_FILE_SIZE_BYTES = 500 * 1024 * 1024  # 500 MB


def extract(local_path: str) -> AudioMetadata:
    """Extract audio metadata from a local file using mutagen.

    Args:
        local_path: Absolute path to the audio file.

    Returns:
        Populated AudioMetadata value object.

    Raises:
        InvalidAudioFormatError: If the format is unsupported or file is corrupt.
    """
    ext = os.path.splitext(local_path)[1].lower()
    if ext not in _SUPPORTED_EXTENSIONS:
        raise InvalidAudioFormatError(
            f"Unsupported audio format '{ext}'. "
            f"Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )

    file_size_bytes = os.path.getsize(local_path)

    try:
        audio = mutagen.File(local_path)  # type: ignore[assignment]
    except Exception as exc:
        raise InvalidAudioFormatError(
            f"Failed to read audio metadata from '{local_path}': {exc}"
        ) from exc

    if audio is None:
        raise InvalidAudioFormatError(
            f"Could not identify audio format for '{local_path}'."
        )

    duration_seconds: float = getattr(audio.info, "length", 0.0) or 0.0
    sample_rate: int = getattr(audio.info, "sample_rate", 0) or 0
    channels: int = getattr(audio.info, "channels", 1) or 1
    bitrate_kbps: int = int(getattr(audio.info, "bitrate", 0) or 0) // 1000

    # Normalise format label
    codec = ext.lstrip(".")

    logger.info(
        "audio.metadata_extracted",
        path=local_path,
        duration_seconds=duration_seconds,
        sample_rate=sample_rate,
        channels=channels,
    )

    return AudioMetadata(
        format=codec,
        duration_seconds=duration_seconds,
        sample_rate=sample_rate,
        channels=channels,
        bitrate_kbps=bitrate_kbps,
        file_size_bytes=file_size_bytes,
    )
