"""End-to-end pipeline test.

Usage:
    python scripts/test_pipeline.py --audio C:/path/to/call.mp3

What it does:
    1. Logs in as admin
    2. Creates a source (if not exists)
    3. Gets a presigned upload URL from MinIO
    4. Uploads your audio file directly to MinIO
    5. Confirms the upload → creates a job → workers start processing
    6. Polls job status every 5 seconds until COMPLETED or FAILED
    7. Prints the full transcript, analysis scores, and report
"""

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

BASE = "http://localhost:8000/api/v1"
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")


def _print_divider(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


async def run(audio_path: str) -> None:
    audio_file = Path(audio_path)
    if not audio_file.exists():
        print(f"❌ File not found: {audio_path}")
        sys.exit(1)

    print(f"\n🎵 Audio file: {audio_file.name} ({audio_file.stat().st_size // 1024} KB)")

    async with httpx.AsyncClient(timeout=30.0) as client:

        # ── 1. Login ──────────────────────────────────────────────────────────
        _print_divider("Step 1: Login")
        r = await client.post(f"{BASE}/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
        if r.status_code != 200:
            print(f"❌ Login failed: {r.json()}")
            sys.exit(1)
        token = r.json()["data"]["access_token"]
        role = r.json()["data"]["role"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"✅ Logged in as {ADMIN_EMAIL} (role={role})")

        # ── 2. Create source ──────────────────────────────────────────────────
        _print_divider("Step 2: Create source")
        r = await client.post(f"{BASE}/sources", json={
            "name": "Test CLI Upload",
            "source_type": "filesystem",
            "path": str(audio_file.parent),
            "file_patterns": [f"*{audio_file.suffix}"]
        }, headers=headers)
        if r.status_code not in (200, 201, 409):
            print(f"❌ Source creation failed: {r.json()}")
            sys.exit(1)
        source_id = r.json()["data"]["id"]
        print(f"✅ Source: {source_id}")

        # ── 3. Presign URL ────────────────────────────────────────────────────
        _print_divider("Step 3: Get upload URL")
        r = await client.post(f"{BASE}/uploads/presign", json={
            "file_name": audio_file.name,
            "source_id": source_id
        }, headers=headers)
        presign = r.json()["data"]
        storage_key = presign["storage_key"]
        upload_url = presign["upload_url"]
        print(f"✅ Upload URL ready (expires in {presign['expires_in']}s)")

        # ── 4. Upload to MinIO ────────────────────────────────────────────────
        _print_divider("Step 4: Upload audio to MinIO")
        audio_bytes = audio_file.read_bytes()
        # Direct PUT to MinIO — bypasses the API entirely
        async with httpx.AsyncClient(timeout=120.0) as upload_client:
            ur = await upload_client.put(
                upload_url,
                content=audio_bytes,
                headers={"Content-Type": "audio/mpeg"},
            )
        if ur.status_code not in (200, 204):
            print(f"❌ Upload to MinIO failed: HTTP {ur.status_code}")
            print("   Is MinIO running? http://localhost:9000")
            sys.exit(1)
        print(f"✅ Uploaded {len(audio_bytes) // 1024} KB to MinIO")
        print(f"   Storage key: {storage_key}")

        # ── 5. Confirm → create job ───────────────────────────────────────────
        _print_divider("Step 5: Create job")
        r = await client.post(f"{BASE}/uploads/confirm", json={
            "source_id": source_id,
            "file_name": audio_file.name,
            "storage_key": storage_key
        }, headers=headers)
        if r.status_code not in (200, 201):
            print(f"❌ Job creation failed: {r.json()}")
            sys.exit(1)
        job = r.json()["data"]
        job_id = job["id"]
        print(f"✅ Job created: {job_id}")
        print(f"   Workers will now pick this up automatically.")
        print(f"\n   Watch queues at: http://localhost:15672")
        print(f"   Watch Postgres:  SELECT status FROM audio_jobs WHERE id = '{job_id}';")

        # ── 6. Poll status ────────────────────────────────────────────────────
        _print_divider("Step 6: Watching pipeline progress")
        print("   (Takes 2-5 min. Make sure all 4 workers are running)\n")

        status_order = ["pending", "ingesting", "stt", "repairing", "analyzing", "reporting", "completed"]
        last_status = None
        start = time.time()

        while True:
            await asyncio.sleep(5)
            r = await client.get(f"{BASE}/jobs/{job_id}", headers=headers)
            if r.status_code != 200:
                print(f"   ⚠ Status check failed: {r.status_code}")
                continue

            status = r.json()["data"]["status"]
            elapsed = int(time.time() - start)

            if status != last_status:
                stage_idx = status_order.index(status) if status in status_order else -1
                bar = "▓" * (stage_idx + 1) + "░" * (len(status_order) - stage_idx - 1)
                print(f"   [{bar}] {status.upper()} ({elapsed}s)")
                last_status = status

            if status == "completed":
                print(f"\n✅ Pipeline complete in {elapsed}s")
                break
            elif status == "failed":
                err = r.json()["data"].get("error_message", "unknown")
                print(f"\n❌ Job failed: {err}")
                sys.exit(1)

        # ── 7. Print results ──────────────────────────────────────────────────
        _print_divider("Results: Transcript")
        r = await client.get(f"{BASE}/jobs/{job_id}/transcript", headers=headers)
        t = r.json()["data"]
        print(f"Language: {t['language']} | Confidence: {t['confidence']:.0%}")
        print(f"Repaired: {t['is_repaired']} | Diarized: {t['is_diarized']}")
        print(f"\nFirst 5 speaker turns:")
        for seg in (t.get("segments") or [])[:5]:
            speaker = seg.get("speaker_id", "?")
            text = seg.get("text", "")[:100]
            print(f"  [{speaker}]: {text}")

        _print_divider("Results: Analysis Scores")
        r = await client.get(f"{BASE}/jobs/{job_id}/analysis", headers=headers)
        a = r.json()["data"]
        scores = [
            ("Agent performance",      a["agent_performance_score"]),
            ("Customer satisfaction",  a["customer_satisfaction_score"]),
            ("Call resolution",        a["call_resolution_score"]),
            ("Empathy",                a["empathy_score"]),
            ("Closing effectiveness",  a["closing_effectiveness_score"]),
        ]
        for name, score in scores:
            bar = "█" * int(score) + "░" * (10 - int(score))
            print(f"  {name:<28} {bar} {score:.1f}/10")

        m = a["call_metrics"]
        print(f"\n  Agent talk time:   {m['agent_talk_time_pct']:.1f}%")
        print(f"  Customer talk:     {m['customer_talk_time_pct']:.1f}%")
        print(f"  Silence:           {m['silence_pct']:.1f}%")
        print(f"  Interruptions:     {m['interruption_count']}")
        print(f"  Compliance:        {'✅ PASSED' if a['compliance_passed'] else '❌ FAILED'}")
        if a.get("compliance_flags"):
            for flag in a["compliance_flags"]:
                print(f"    ⚠ {flag.get('description', flag)}")
        print(f"\n  Agent sentiment:   {a['agent_sentiment']['overall']} ({a['agent_sentiment']['score']:+.2f})")
        print(f"  Customer sentiment:{a['customer_sentiment']['overall']} ({a['customer_sentiment']['score']:+.2f})")

        _print_divider("Results: Summary & Coaching")
        print(f"\n{a['summary']}\n")
        print("Strengths:")
        for s in a.get("strengths", []):
            print(f"  ✅ {s}")
        print("\nImprovement areas:")
        for i in a.get("improvement_areas", []):
            print(f"  🔧 {i}")
        print(f"\nRecommendation:\n  {a.get('recommendation', '')}")
        if a.get("coaching_notes"):
            print(f"\nCoaching notes:\n  {a['coaching_notes']}")

        _print_divider("Results: Final Report")
        r = await client.get(f"{BASE}/jobs/{job_id}/report", headers=headers)
        rep = r.json()["data"]
        print(f"  Title:         {rep['title']}")
        print(f"  Overall score: {rep['overall_score']:.1f}/10")
        print(f"  Duration:      {int(rep['call_duration_seconds'] // 60)}m {int(rep['call_duration_seconds'] % 60)}s")
        print(f"  Compliance:    {'✅ PASSED' if rep['compliance_passed'] else '❌ FAILED'}")
        print(f"\n✅ All done. Job ID: {job_id}")
        print(f"   Full JSON: GET /api/v1/jobs/{job_id}/report")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the audio analysis pipeline end-to-end")
    parser.add_argument("--audio", required=True, help="Path to an MP3 or WAV file")
    args = parser.parse_args()
    asyncio.run(run(args.audio))
