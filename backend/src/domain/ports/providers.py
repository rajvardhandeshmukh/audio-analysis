"""Provider port interfaces — abstractions for all external AI/ML providers.

Rule 5: No OpenAI/LLM calls outside providers.
Rule 14: Define interfaces here; implement in infrastructure/providers/.
"""

from abc import ABC, abstractmethod

from src.domain.entities.analysis import Analysis
from src.domain.entities.transcript import Transcript
from src.domain.value_objects.audio_metadata import AudioMetadata
from src.domain.value_objects.speaker_segment import SpeakerSegment
from src.domain.value_objects.word_timestamp import WordTimestamp


class STTProvider(ABC):
    """Speech-to-text provider interface.

    Implementations:
        infrastructure/providers/stt/openai_whisper_provider.py
    """

    @abstractmethod
    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> tuple[str, str, float, list[WordTimestamp]]:
        """Transcribe an audio file to text with word-level timestamps.

        Args:
            audio_path: Local or accessible path to audio file.
            language: Optional ISO 639-1 language hint.

        Returns:
            Tuple of (raw_text, detected_language, confidence, word_timestamps).
            word_timestamps: Required for RepairProvider diarization.

        Raises:
            STTProviderError: On provider failure.
            ProviderRateLimitError: On rate limit response.
        """
        ...

    @abstractmethod
    async def extract_metadata(self, audio_path: str) -> AudioMetadata:
        """Extract audio file metadata without transcribing.

        Args:
            audio_path: Path to audio file.

        Returns:
            AudioMetadata value object.

        Raises:
            STTProviderError: On metadata extraction failure.
        """
        ...


class RepairProvider(ABC):
    """Transcript repair and speaker diarization provider interface.

    Implementations:
        infrastructure/providers/repair/openai_repair_provider.py
    """

    @abstractmethod
    async def repair_transcript(
        self,
        raw_text: str,
        audio_metadata: AudioMetadata,
    ) -> str:
        """Correct STT errors in a raw transcript using an LLM.

        Args:
            raw_text: Raw transcript text from STT provider.
            audio_metadata: Audio properties for context.

        Returns:
            Corrected transcript text.

        Raises:
            ProviderError: On LLM failure.
            ProviderRateLimitError: On rate limit.
        """
        ...

    @abstractmethod
    async def diarize(
        self,
        transcript: Transcript,
        audio_metadata: AudioMetadata,
    ) -> list[SpeakerSegment]:
        """Perform speaker diarization on a transcript.

        Args:
            transcript: The transcript entity (uses effective_text).
            audio_metadata: Audio properties (duration, channels).

        Returns:
            Ordered list of SpeakerSegment value objects.

        Raises:
            ProviderError: On LLM/diarization failure.
        """
        ...


class AnalysisProvider(ABC):
    """Behavioral analysis provider interface.

    Implementations:
        infrastructure/providers/analysis/openai_analysis_provider.py

    Rule 27: LLM output must always be structured — never parsed from free text.
    """

    @abstractmethod
    async def analyze(
        self,
        transcript: Transcript,
        audio_metadata: AudioMetadata,
    ) -> Analysis:
        """Analyze a repaired, diarized transcript for behavioral insights.

        Args:
            transcript: Repaired and diarized transcript entity.
            audio_metadata: Call duration and properties.

        Returns:
            Populated Analysis entity (minus id, job_id, transcript_id — set by service).

        Raises:
            AnalysisProviderError: On LLM failure.
            ProviderResponseParseError: If LLM output cannot be parsed into Analysis schema.
        """
        ...
