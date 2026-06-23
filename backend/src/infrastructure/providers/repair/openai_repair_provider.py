"""OpenAI GPT-4o Repair provider — LLM transcript correction + speaker diarization.

Rule 5: Only this file calls openai.chat.completions for repair/diarization.
Two operations, two structured calls:
  1. repair_transcript  — fixes STT errors
  2. diarize           — groups word timestamps into speaker turns
"""

import json

from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel

from src.domain.errors.domain_errors import (
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseParseError,
)
from src.domain.ports.providers import RepairProvider
from src.domain.value_objects.audio_metadata import AudioMetadata
from src.domain.value_objects.speaker_segment import SpeakerSegment
from src.domain.value_objects.word_timestamp import WordTimestamp
from src.infrastructure.config.settings import OpenAISettings, get_openai_settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


# ─── Structured output schemas for GPT-4o ────────────────────────────────────

class _SpeakerTurn(BaseModel):
    speaker_id: str  # "AGENT" or "CUSTOMER"
    text: str
    start_time: float
    end_time: float
    word_count: int


class _DiarizationOutput(BaseModel):
    turns: list[_SpeakerTurn]


# ─── Provider ─────────────────────────────────────────────────────────────────

class OpenAIRepairProvider(RepairProvider):
    """Repairs STT errors and performs speaker diarization using GPT-4o.

    Both operations use structured output (Rule 27) — no free-text parsing.
    Model is configurable via OpenAISettings (supports future IBM swap-in).
    """

    _REPAIR_SYSTEM = (
        "You are a professional transcript editor for call center recordings. "
        "Fix any speech-to-text errors, filler words, and misheard words. "
        "Preserve the speaker's meaning and natural language. "
        "Return only the corrected transcript text — no commentary."
    )

    _DIARIZE_SYSTEM = (
        "You are a speaker diarization expert analyzing a call center conversation. "
        "Given a transcript and word-level timestamps, identify which words were spoken "
        "by the AGENT (call center representative) and which by the CUSTOMER. "
        "Return speaker turns in chronological order. "
        "Use only 'AGENT' or 'CUSTOMER' as speaker_id values."
    )

    def __init__(self, client: AsyncOpenAI, settings: OpenAISettings) -> None:
        self._client = client
        self._settings = settings

    @classmethod
    def from_settings(cls, settings: OpenAISettings | None = None) -> "OpenAIRepairProvider":
        cfg = settings or get_openai_settings()
        return cls(
            client=AsyncOpenAI(
                api_key=cfg.active_api_key,
                base_url=cfg.ai_provider_orchestration_api_url,
                timeout=float(cfg.openai_repair_timeout_seconds),
                max_retries=0,
            ),
            settings=cfg,
        )

    async def repair_transcript(
        self,
        raw_text: str,
        audio_metadata: AudioMetadata,
    ) -> str:
        """Correct STT errors using GPT-4o.

        Returns:
            Corrected plain-text transcript.
        """
        context = (
            f"Audio: {audio_metadata.format}, "
            f"{audio_metadata.duration_seconds:.0f}s, "
            f"{audio_metadata.channels}ch"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._settings.openai_repair_model,
                temperature=self._settings.openai_repair_temperature,
                messages=[
                    {"role": "system", "content": self._REPAIR_SYSTEM},
                    {
                        "role": "user",
                        "content": f"Audio context: {context}\n\nRaw transcript:\n{raw_text}",
                    },
                ],
            )
        except RateLimitError as exc:
            raise ProviderRateLimitError(f"Repair rate limit: {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"Transcript repair failed: {exc}") from exc

        repaired = (response.choices[0].message.content or "").strip()
        logger.info(
            "repair.transcript_fixed",
            raw_chars=len(raw_text),
            repaired_chars=len(repaired),
        )
        return repaired

    async def diarize(
        self,
        transcript: "Transcript",  # type: ignore[name-defined]  # avoid circular import
        audio_metadata: AudioMetadata,
    ) -> list[SpeakerSegment]:
        """Group word timestamps into AGENT/CUSTOMER speaker turns via GPT-4o.

        Uses transcript.word_timestamps (from Whisper) for precise turn boundaries.
        Falls back to text-only heuristics when timestamps are unavailable.

        Returns:
            Ordered list of SpeakerSegment value objects.
        """
        # Format timeline for GPT-4o
        timeline = self._build_timeline(
            transcript.word_timestamps,
            transcript.effective_text,
        )

        prompt = (
            f"Call duration: {audio_metadata.duration_seconds:.0f}s\n\n"
            f"Word timeline:\n{timeline}\n\n"
            "Full transcript:\n"
            f"{transcript.effective_text}"
        )

        try:
            response = await self._client.beta.chat.completions.parse(
                model=self._settings.openai_repair_model,
                temperature=self._settings.openai_repair_temperature,
                messages=[
                    {"role": "system", "content": self._DIARIZE_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
                response_format=_DiarizationOutput,
            )
        except RateLimitError as exc:
            raise ProviderRateLimitError(f"Diarization rate limit: {exc}") from exc
        except Exception as exc:
            raise ProviderError(f"Diarization failed: {exc}") from exc

        parsed = response.choices[0].message.parsed
        if not parsed:
            raise ProviderResponseParseError("GPT-4o returned empty diarization output.")

        segments = [
            SpeakerSegment(
                speaker_id=turn.speaker_id,
                text=turn.text,
                start_time=turn.start_time,
                end_time=turn.end_time,
                word_count=turn.word_count,
            )
            for turn in parsed.turns
        ]
        logger.info(
            "repair.diarized",
            turn_count=len(segments),
            speakers=list({s.speaker_id for s in segments}),
        )
        return segments

    @staticmethod
    def _build_timeline(
        word_timestamps: list[WordTimestamp],
        fallback_text: str,
    ) -> str:
        """Format word timestamps as a numbered timeline string for GPT-4o.

        Falls back to plain text when timestamps are empty.
        """
        if not word_timestamps:
            return fallback_text

        lines = [
            f"[{wt.start:.2f}s-{wt.end:.2f}s] {wt.word}"
            for wt in word_timestamps
        ]
        return "\n".join(lines)


# Avoid circular import — Transcript is referenced in type hint only
from src.domain.entities.transcript import Transcript  # noqa: E402
