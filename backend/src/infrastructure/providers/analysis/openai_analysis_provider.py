"""OpenAI GPT-4o Analysis provider — behavioral analysis with structured output.

Rule 5: Only this file calls openai.chat.completions for analysis.
Rule 27: All LLM output is structured — GPT-4o's parse() API enforces the schema.
CallMetrics are computed locally from speaker segments (no LLM needed).
"""

from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel, Field

from src.domain.entities.analysis import (
    Analysis,
    ComplianceFlag,
    ObjectionHandling,
    SentimentScore,
)
from src.domain.entities.transcript import Transcript
from src.domain.errors.domain_errors import (
    AnalysisProviderError,
    ProviderRateLimitError,
    ProviderResponseParseError,
)
from src.domain.ports.providers import AnalysisProvider
from src.domain.value_objects.audio_metadata import AudioMetadata
from src.domain.value_objects.call_metrics import CallMetrics
from src.infrastructure.config.settings import OpenAISettings, get_openai_settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


# ─── GPT-4o structured output schema (Rule 27) ───────────────────────────────
# Mirrors Analysis entity fields but without id/job_id/transcript_id/created_at.
# These are assigned by the worker, not the LLM.

class _AnalysisLLMOutput(BaseModel):
    """Exact contract sent to GPT-4o via response_format. Never changed ad-hoc."""

    agent_performance_score: float = Field(..., ge=0.0, le=10.0)
    customer_satisfaction_score: float = Field(..., ge=0.0, le=10.0)
    call_resolution_score: float = Field(..., ge=0.0, le=10.0)
    empathy_score: float = Field(..., ge=0.0, le=10.0)
    closing_effectiveness_score: float = Field(..., ge=0.0, le=10.0)
    closing_signal_detected: bool
    upsell_attempt_detected: bool
    objection_handling: ObjectionHandling
    agent_sentiment: SentimentScore
    customer_sentiment: SentimentScore
    compliance_flags: list[ComplianceFlag] = Field(default_factory=list)
    summary: str
    strengths: list[str] = Field(default_factory=list)
    improvement_areas: list[str] = Field(default_factory=list)
    recommendation: str
    coaching_notes: str | None = None


# ─── Provider ─────────────────────────────────────────────────────────────────

class OpenAIAnalysisProvider(AnalysisProvider):
    """Behavioral analysis for call center calls using GPT-4o structured output.

    Steps:
      1. Compute CallMetrics locally from diarized segments (fast, no LLM).
      2. Call GPT-4o with structured output schema for all scoring.
      3. Assemble and return the full Analysis entity.
    """

    _SYSTEM_PROMPT = (
        "You are an expert call center quality assurance analyst. "
        "Analyze the provided call transcript and evaluate agent performance. "
        "Be objective, specific, and cite evidence from the transcript. "
        "Scores are 0.0-10.0. Sentiment is 'positive'/'neutral'/'negative'. "
        "Compliance flags should only be raised for clear regulatory or policy violations."
    )

    def __init__(self, client: AsyncOpenAI, settings: OpenAISettings) -> None:
        self._client = client
        self._settings = settings

    @classmethod
    def from_settings(cls, settings: OpenAISettings | None = None) -> "OpenAIAnalysisProvider":
        cfg = settings or get_openai_settings()
        return cls(
            client=AsyncOpenAI(
                api_key=cfg.active_api_key,
                base_url=cfg.ai_provider_orchestration_api_url,
                timeout=float(cfg.openai_analysis_timeout_seconds),
                max_retries=0,
            ),
            settings=cfg,
        )

    async def analyze(
        self,
        transcript: Transcript,
        audio_metadata: AudioMetadata,
    ) -> Analysis:
        """Analyze a repaired, diarized transcript.

        Args:
            transcript: Fully repaired and diarized Transcript entity.
            audio_metadata: Call duration and properties.

        Returns:
            Complete Analysis entity.
        """
        call_metrics = _compute_call_metrics(transcript, audio_metadata)
        prompt = _build_analysis_prompt(transcript, audio_metadata, call_metrics)

        try:
            response = await self._client.beta.chat.completions.parse(
                model=self._settings.openai_analysis_model,
                temperature=self._settings.openai_analysis_temperature,
                messages=[
                    {"role": "system", "content": self._SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                response_format=_AnalysisLLMOutput,
            )
        except RateLimitError as exc:
            raise ProviderRateLimitError(f"Analysis rate limit: {exc}") from exc
        except Exception as exc:
            raise AnalysisProviderError(f"Analysis LLM call failed: {exc}") from exc

        parsed = response.choices[0].message.parsed
        if not parsed:
            raise ProviderResponseParseError("GPT-4o returned empty analysis output.")

        analysis = Analysis(
            job_id=transcript.job_id,
            transcript_id=transcript.id,
            agent_performance_score=parsed.agent_performance_score,
            customer_satisfaction_score=parsed.customer_satisfaction_score,
            call_resolution_score=parsed.call_resolution_score,
            empathy_score=parsed.empathy_score,
            closing_effectiveness_score=parsed.closing_effectiveness_score,
            closing_signal_detected=parsed.closing_signal_detected,
            upsell_attempt_detected=parsed.upsell_attempt_detected,
            objection_handling=parsed.objection_handling,
            agent_sentiment=parsed.agent_sentiment,
            customer_sentiment=parsed.customer_sentiment,
            compliance_flags=parsed.compliance_flags,
            call_metrics=call_metrics,
            summary=parsed.summary,
            strengths=parsed.strengths,
            improvement_areas=parsed.improvement_areas,
            recommendation=parsed.recommendation,
            coaching_notes=parsed.coaching_notes,
        )

        logger.info(
            "analysis.completed",
            job_id=str(transcript.job_id),
            agent_score=analysis.agent_performance_score,
            compliance_passed=analysis.compliance_passed,
        )
        return analysis


# ─── Helpers (module-private) ────────────────────────────────────────────────

def _compute_call_metrics(
    transcript: Transcript,
    audio_metadata: AudioMetadata,
) -> CallMetrics:
    """Compute quantitative call metrics from diarized speaker segments.

    Pure computation — no LLM call.
    """
    total = audio_metadata.duration_seconds or 1.0

    agent_time = sum(
        s.end_time - s.start_time
        for s in transcript.segments
        if s.speaker_id == "AGENT"
    )
    customer_time = sum(
        s.end_time - s.start_time
        for s in transcript.segments
        if s.speaker_id == "CUSTOMER"
    )
    spoken_time = agent_time + customer_time
    silence_time = max(0.0, total - spoken_time)

    agent_words = sum(
        s.word_count for s in transcript.segments if s.speaker_id == "AGENT"
    )
    customer_words = sum(
        s.word_count for s in transcript.segments if s.speaker_id == "CUSTOMER"
    )

    # Count interruptions: turns that start before previous turn ends
    interruptions = 0
    for i in range(1, len(transcript.segments)):
        prev, curr = transcript.segments[i - 1], transcript.segments[i]
        if curr.start_time < prev.end_time and curr.speaker_id != prev.speaker_id:
            interruptions += 1

    # Longest silence between turns
    turn_gaps = [
        transcript.segments[i].start_time - transcript.segments[i - 1].end_time
        for i in range(1, len(transcript.segments))
    ]
    longest_silence = max((g for g in turn_gaps if g > 0), default=0.0)

    avg_response_time = (
        sum(g for g in turn_gaps if g > 0) / len([g for g in turn_gaps if g > 0])
        if any(g > 0 for g in turn_gaps)
        else 0.0
    )

    # Clamp and normalise to ensure percentages sum to ~100
    agent_pct = round(min(100.0, (agent_time / total) * 100), 1)
    customer_pct = round(min(100.0, (customer_time / total) * 100), 1)
    silence_pct = round(max(0.0, 100.0 - agent_pct - customer_pct), 1)

    return CallMetrics(
        agent_talk_time_pct=agent_pct,
        customer_talk_time_pct=customer_pct,
        silence_pct=silence_pct,
        overlap_pct=0.0,
        interruption_count=interruptions,
        longest_silence_seconds=round(longest_silence, 2),
        average_response_time_seconds=round(avg_response_time, 2),
        total_duration_seconds=round(total, 2),
        agent_word_count=agent_words,
        customer_word_count=customer_words,
    )


def _build_analysis_prompt(
    transcript: Transcript,
    audio_metadata: AudioMetadata,
    metrics: CallMetrics,
) -> str:
    """Build the structured analysis prompt for GPT-4o."""
    speakers_block = "\n".join(
        f"[{seg.speaker_id} {seg.start_time:.1f}s-{seg.end_time:.1f}s]: {seg.text}"
        for seg in transcript.segments
    ) or transcript.effective_text

    return (
        f"== Call Metadata ==\n"
        f"Duration: {audio_metadata.duration_seconds:.0f}s | "
        f"Format: {audio_metadata.format} | "
        f"Channels: {audio_metadata.channels}\n\n"
        f"== Call Metrics ==\n"
        f"Agent talk: {metrics.agent_talk_time_pct}% | "
        f"Customer talk: {metrics.customer_talk_time_pct}% | "
        f"Silence: {metrics.silence_pct}% | "
        f"Interruptions: {metrics.interruption_count}\n\n"
        f"== Diarized Transcript ==\n"
        f"{speakers_block}"
    )
