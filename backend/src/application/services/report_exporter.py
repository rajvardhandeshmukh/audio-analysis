"""Report Exporter Service — generates human-readable .txt files for completed audio analyses.

Exports formatted reports to a local directory accessible by the frontend.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from src.domain.entities.analysis import Analysis
from src.domain.entities.audio_job import AudioJob
from src.domain.entities.transcript import Transcript
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

DEFAULT_EXPORT_DIR = "D:/projects/audio-analysis/exported_reports"


def export_report_as_text(
    job: AudioJob,
    analysis: Analysis,
    transcript: Transcript,
    output_dir: str | None = None,
) -> str:
    """Format and save a complete analysis report as a .txt file.

    Args:
        job: The completed AudioJob.
        analysis: The generated Analysis entity.
        transcript: The diarized/repaired Transcript entity.
        output_dir: Destination directory path. Defaults to DEFAULT_EXPORT_DIR or env var.

    Returns:
        Absolute path to the saved .txt file.
    """
    target_dir = output_dir or os.getenv("EXPORT_REPORTS_DIR", DEFAULT_EXPORT_DIR)
    os.makedirs(target_dir, exist_ok=True)

    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
    clean_filename = Path(job.file_name).stem.replace(" ", "_")
    file_path = os.path.join(target_dir, f"{clean_filename}_{timestamp_str}.txt")

    overall_score = round(
        (
            analysis.agent_performance_score
            + analysis.customer_satisfaction_score
            + analysis.call_resolution_score
        )
        / 3,
        2,
    )

    lines = [
        "================================================================================",
        f"CALL ANALYSIS REPORT: {job.file_name}",
        "================================================================================",
        f"Job ID          : {job.id}",
        f"Date Analyzed   : {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"Call Duration   : {analysis.call_metrics.total_duration_seconds:.1f} seconds",
        f"Compliance      : {'PASSED' if analysis.compliance_passed else 'FAILED'}",
        "--------------------------------------------------------------------------------",
        "PERFORMANCE SCORES (0 - 100)",
        "--------------------------------------------------------------------------------",
        f"Overall Score            : {overall_score}",
        f"Agent Performance        : {analysis.agent_performance_score}",
        f"Customer Satisfaction    : {analysis.customer_satisfaction_score}",
        f"Call Resolution          : {analysis.call_resolution_score}",
        f"Empathy Score            : {analysis.empathy_score}",
        f"Closing Effectiveness    : {analysis.closing_effectiveness_score}",
        "",
        "--------------------------------------------------------------------------------",
        "EXECUTIVE SUMMARY",
        "--------------------------------------------------------------------------------",
        analysis.summary.strip(),
        "",
        "--------------------------------------------------------------------------------",
        "KEY STRENGTHS",
        "--------------------------------------------------------------------------------",
    ]

    if analysis.strengths:
        for s in analysis.strengths:
            lines.append(f"  + {s}")
    else:
        lines.append("  (None recorded)")

    lines.extend([
        "",
        "--------------------------------------------------------------------------------",
        "AREAS FOR IMPROVEMENT",
        "--------------------------------------------------------------------------------",
    ])

    if analysis.improvement_areas:
        for imp in analysis.improvement_areas:
            lines.append(f"  - {imp}")
    else:
        lines.append("  (None recorded)")

    lines.extend([
        "",
        "--------------------------------------------------------------------------------",
        "RECOMMENDATION & COACHING",
        "--------------------------------------------------------------------------------",
        f"Recommendation: {analysis.recommendation.strip()}",
    ])

    if analysis.coaching_notes:
        lines.append(f"\nCoaching Notes:\n{analysis.coaching_notes.strip()}")

    lines.extend([
        "",
        "================================================================================",
        "FULL DIARIZED TRANSCRIPT",
        "================================================================================",
        "",
    ])

    if transcript.segments:
        for seg in transcript.segments:
            start_m, start_s = divmod(int(seg.start_time), 60)
            end_m, end_s = divmod(int(seg.end_time), 60)
            time_tag = f"[{start_m:02d}:{start_s:02d} - {end_m:02d}:{end_s:02d}]"
            lines.append(f"{time_tag} {seg.speaker_id}: {seg.text.strip()}")
    elif transcript.repaired_text:
        lines.append(transcript.repaired_text.strip())
    else:
        lines.append(transcript.raw_text.strip())

    lines.append("\n================================================================================")
    lines.append("END OF REPORT")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("report_exporter.saved", file_path=file_path, job_id=str(job.id))
    return file_path
