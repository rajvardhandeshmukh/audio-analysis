"""OpenAI Whisper STT provider — implements STTProvider port.

Rule 5: Only this file calls openai.audio.transcriptions.
Model + temperature + timeout are all configurable via OpenAISettings.
"""

import os
import tempfile

import httpx
from openai import AsyncOpenAI, RateLimitError

from src.domain.errors.domain_errors import ProviderRateLimitError, STTProviderError
from src.domain.ports.providers import STTProvider
from src.domain.value_objects.audio_metadata import AudioMetadata
from src.domain.value_objects.word_timestamp import WordTimestamp
from src.infrastructure.audio import metadata_extractor
from src.infrastructure.config.settings import OpenAISettings, get_openai_settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


class OpenAIWhisperSTTProvider(STTProvider):
    """Transcribes audio using OpenAI Whisper with word-level timestamps.

    Returns (raw_text, language, confidence, word_timestamps).
    word_timestamps are stored in Transcript and used by RepairProvider for diarization.
    """

    def __init__(self, client: AsyncOpenAI, settings: OpenAISettings) -> None:
        self._client = client
        self._settings = settings

    @classmethod
    def from_settings(cls, settings: OpenAISettings | None = None) -> "OpenAIWhisperSTTProvider":
        cfg = settings or get_openai_settings()
        return cls(
            client=AsyncOpenAI(
                api_key=cfg.active_api_key,
                base_url=cfg.ai_provider_orchestration_api_url,
                timeout=float(cfg.openai_stt_timeout_seconds),
                max_retries=0,
            ),
            settings=cfg,
        )

    async def transcribe(
        self,
        audio_path: str,
        language: str | None = None,
    ) -> tuple[str, str, float, list[WordTimestamp]]:
        """Transcribe audio with word-level timestamps via Whisper verbose_json.

        Args:
            audio_path: Path to the local audio file.
            language: Optional ISO-639-1 language code hint.

        Returns:
            (raw_text, detected_language, average_word_probability, word_timestamps)
        """
        try:
            with open(audio_path, "rb") as audio_file:
                response = await self._client.audio.transcriptions.create(
                    model=self._settings.openai_stt_model,
                    file=audio_file,
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["word"],
                    temperature=self._settings.openai_stt_temperature,
                )
        except RateLimitError as exc:
            raise ProviderRateLimitError(
                f"Whisper rate limit exceeded: {exc}"
            ) from exc
        except Exception as exc:
            raise STTProviderError(f"Whisper transcription failed: {exc}") from exc

        raw_text: str = response.text or ""
        detected_language: str = getattr(response, "language", language or "en")

        words = getattr(response, "words", None) or []
        word_timestamps: list[WordTimestamp] = []
        for w in words:
            if isinstance(w, dict):
                text = w.get("word", "")
                start = w.get("start", 0.0)
                end = w.get("end", 0.0)
                prob = w.get("probability", 1.0)
            else:
                text = getattr(w, "word", "")
                start = getattr(w, "start", 0.0)
                end = getattr(w, "end", 0.0)
                prob = getattr(w, "probability", 1.0)
            
            if text.strip():
                word_timestamps.append(
                    WordTimestamp(
                        word=text.strip(),
                        start=float(start),
                        end=float(end),
                        probability=float(prob),
                    )
                )

        # Average word probability as a proxy for overall confidence
        confidence = (
            sum(wt.probability for wt in word_timestamps) / len(word_timestamps)
            if word_timestamps
            else 0.9  # Whisper default when probabilities unavailable
        )

        logger.info(
            "stt.transcribed",
            audio_path=audio_path,
            language=detected_language,
            word_count=len(word_timestamps),
            confidence=round(confidence, 3),
        )
        return raw_text, detected_language, confidence, word_timestamps

    async def extract_metadata(self, audio_path: str) -> AudioMetadata:
        """Extract metadata locally using mutagen — no API call needed."""
        return metadata_extractor.extract(audio_path)
