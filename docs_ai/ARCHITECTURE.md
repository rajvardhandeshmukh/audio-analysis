# Audio Analysis Platform — Architecture & Engineering Standards

> **These rules are non-negotiable. No exceptions. No shortcuts.**
> Every engineer, every agent, every PR must comply.

---

## System Architecture

```
Frontend (Next.js)
        │
        ▼
FastAPI
 ├── JWT Auth
 ├── RBAC
 ├── APIs
 └── Upload URL Generation (Presigned)
        │
        ▼
PostgreSQL | Redis | RabbitMQ | Object Storage

────────────────────────────────────────────────

Source Registry
        │
        ▼
Watcher Service
        │
        ▼
Audio Job
        │
        ▼
RabbitMQ

ingestion_queue
        ▼
STT Workers
 ├── PostgreSQL (persist)
 ├── Object Storage (persist)
 └── Redis Events (publish)
        ▼
repair_queue
        ▼
Repair Workers
        ▼
analysis_queue
        ▼
Analysis Workers
        ▼
report_queue
        ▼
Report Workers
        ▼
COMPLETED

────────────────────────────────────────────────

Dead Letter Queue (DLQ) — Per Stage

────────────────────────────────────────────────

Redis Pub/Sub
        │
        ▼
WebSocket Service
        │
        ▼
Frontend (real-time updates)
```

---

## Clean Architecture — Mandatory

### Layer Stack

```
Presentation
     ↓
Application
     ↓
Domain
     ↓
Infrastructure
```

**Dependencies flow inward only. Never outward. Never sideways.**

### Allowed

```
Route → Service → Repository Interface
```

### Forbidden

```
Route → Repository          (skip layer)
Repository → Service        (reversed dependency)
Worker → Route              (reversed dependency)
```

---

## Rule 1 — Hexagonal Architecture

All code lives inside one of these four layers:

| Layer | Contains |
|---|---|
| `presentation/` | Routes, WebSocket handlers, request/response DTOs |
| `application/` | Services, Use Cases — orchestration only |
| `domain/` | Entities, Value Objects, Enums, Domain Errors — pure business logic |
| `infrastructure/` | DB, Repositories, Messaging, Storage, Providers |

---

## Rule 2 — Dependency Rule

- Inner layers have **zero knowledge** of outer layers
- `domain/` imports nothing from `infrastructure/`
- `application/` imports domain types and infrastructure **interfaces** only
- `infrastructure/` implements interfaces defined in `domain/` or `application/`

---

## Rule 3 — Domain First

All business concepts live in `domain/`. Domain knows **nothing** about:

- RabbitMQ
- OpenAI / any LLM
- PostgreSQL / SQLAlchemy
- FastAPI
- Redis

### Domain Entities (examples)

```python
AudioJob
Transcript
Analysis
Report
WatcherSource
```

---

## Rule 4 — No Direct Database Access Outside Repositories

### Forbidden — anywhere except repositories

```python
await async_session.execute(...)
```

### The only classes allowed to touch the DB

```python
AudioJobRepository
TranscriptRepository
AnalysisRepository
ReportRepository
```

If a service needs data, it calls a repository. Full stop.

---

## Rule 5 — No OpenAI / LLM Calls Outside Providers

### Forbidden — inside workers, services, routes

```python
from openai import OpenAI
client.audio.transcriptions.create(...)
```

### Allowed — provider interface pattern

```python
class STTProvider(ABC):
    async def transcribe(self, file_path: str) -> TranscriptResult: ...

class OpenAIWhisperProvider(STTProvider): ...
class IBMSTTProvider(STTProvider): ...
```

Workers call `stt_provider.transcribe()` — never OpenAI directly.

---

## Rule 6 — No RabbitMQ Calls Outside Messaging Layer

### Forbidden — inside services, workers directly

```python
channel.basic_publish(...)
```

### Allowed — messaging abstraction

```python
class MessagePublisher(ABC):
    async def publish(self, queue: str, message: BaseModel) -> None: ...

class MessageConsumer(ABC):
    async def consume(self, queue: str) -> AsyncIterator[BaseModel]: ...
```

---

## Rule 7 — Single Responsibility

One class. One responsibility.

### Bad

```python
class AudioService:
    # DB access
    # Queue publishing
    # OpenAI calls
    # Validation
    # Report generation
```

### Good

```python
class AudioJobService      # job lifecycle only
class TranscriptService    # transcript operations only
class AnalysisService      # analysis logic only
class ReportService        # report generation only
```

---

## Rule 8 — Workers Must Be Stateless

Worker state lives **only** in:

- PostgreSQL
- Redis
- Object Storage

### Forbidden

```python
# At module level
global_cache = {}
processed_ids = set()
```

---

## Rule 9 — No Shared Mutable State

### Forbidden

```python
GLOBAL_CONFIG = {}
SHARED_STATE = []
```

### Required

Dependency Injection everywhere. Pass dependencies explicitly.

---

## Rule 10 — Configuration

All configuration via:

- Environment variables (`.env`)
- YAML config files
- Secret Manager (production)

### Forbidden — hardcoded secrets or config

```python
OPENAI_KEY = "sk-..."
DB_URL = "postgresql://..."
```

Use a typed settings class:

```python
class Settings(BaseSettings):
    openai_api_key: str
    database_url: str
    rabbitmq_url: str
    redis_url: str
```

---

## Rule 11 — Type Safety — Pydantic Everywhere

### Forbidden — raw dicts passed around

```python
def process(data: dict): ...
```

### Required — typed models

```python
class AudioJobCreate(BaseModel):
    source_id: UUID
    file_path: str
    duration_seconds: float

class TranscriptResult(BaseModel):
    job_id: UUID
    text: str
    confidence: float
    language: str

class AnalysisResult(BaseModel):
    job_id: UUID
    summary: str
    score: float
    recommendation: str
```

No `dict`. No `Any`. No `Optional` without reason.

---

## Rule 12 — Repository Pattern

Repositories are **data access only**. No business logic.

### Allowed repository methods

```python
async def create(self, entity: AudioJob) -> AudioJob: ...
async def get_by_id(self, id: UUID) -> AudioJob | None: ...
async def update(self, entity: AudioJob) -> AudioJob: ...
async def delete(self, id: UUID) -> None: ...
async def list_by_status(self, status: JobStatus) -> list[AudioJob]: ...
```

### Forbidden inside repositories

```python
def calculate_score(self): ...
def validate_audio(self): ...
def publish_to_queue(self): ...
```

---

## Rule 13 — Service Layer — Business Logic Only

### Allowed inside services

```python
async def create_audio_job(self, cmd: CreateAudioJobCommand) -> AudioJob: ...
async def retry_job(self, job_id: UUID) -> AudioJob: ...
async def mark_completed(self, job_id: UUID) -> None: ...
```

### Forbidden inside services

- Raw SQL
- Direct RabbitMQ calls (`channel.publish`)
- Direct OpenAI calls
- Direct DB session access

---

## Rule 14 — Provider Pattern

Define interfaces in `domain/` or `application/`. Implement in `infrastructure/providers/`.

### STT Provider

```python
class STTProvider(ABC):
    async def transcribe(self, audio_path: str) -> TranscriptResult: ...

class OpenAIWhisperProvider(STTProvider): ...
class IBMSTTProvider(STTProvider): ...
```

### Storage Provider

```python
class StorageProvider(ABC):
    async def upload(self, path: str, data: bytes) -> str: ...
    async def download(self, path: str) -> bytes: ...
    async def generate_presigned_url(self, path: str) -> str: ...

class S3StorageProvider(StorageProvider): ...
class MinioStorageProvider(StorageProvider): ...
class LocalStorageProvider(StorageProvider): ...
```

### Analysis Provider

```python
class AnalysisProvider(ABC):
    async def analyze(self, transcript: str) -> AnalysisResult: ...

class OpenAIAnalysisProvider(AnalysisProvider): ...
```

---

## Rule 15 — Message Contracts

Every queue message must have a typed Pydantic schema.

```python
class IngestionMessage(BaseModel):
    job_id: UUID
    file_id: UUID
    source_id: UUID
    audio_path: str

class STTCompletedMessage(BaseModel):
    job_id: UUID
    transcript_id: UUID

class RepairCompletedMessage(BaseModel):
    job_id: UUID
    transcript_id: UUID

class AnalysisCompletedMessage(BaseModel):
    job_id: UUID
    analysis_id: UUID
```

### Forbidden — untyped queue messages

```json
{ "someData": "...", "stuff": "..." }
```

---

## Rule 16 — No Generic Utils

### Forbidden

```
utils.py
helpers.py
common.py
misc.py
```

These become garbage dumps that nobody owns.

### Required — every utility belongs to a specific module

```
infrastructure/storage/path_builder.py
domain/audio/duration_calculator.py
application/jobs/job_status_resolver.py
```

---

## Rule 17 — Error Handling

### Forbidden

```python
try:
    ...
except Exception:
    pass
```

### Required — typed domain errors

```python
class DomainError(Exception): ...
class ValidationError(DomainError): ...
class ProviderError(DomainError): ...
class StorageError(DomainError): ...
class MessagingError(DomainError): ...
class JobNotFoundError(DomainError): ...
class DuplicateJobError(DomainError): ...
```

Every `except` must catch a **specific** error type and handle it explicitly.

---

## Rule 18 — Structured Logging

### Forbidden

```python
print("error happened")
print(f"processing {job_id}")
logging.info("done")
```

### Required — structured JSON logs

```python
logger.info("stt.started", extra={
    "job_id": str(job_id),
    "worker": "stt",
    "event": "started",
    "file_path": audio_path
})

logger.error("stt.failed", extra={
    "job_id": str(job_id),
    "worker": "stt",
    "event": "failed",
    "error": str(exc),
    "error_type": type(exc).__name__
})
```

Use `structlog` or equivalent JSON logger. Never bare `print`.

---

## Rule 19 — Retry Strategy

**Retries are handled exclusively by RabbitMQ policy configuration.**

### Forbidden — manual retry loops in code

```python
while True:
    try:
        ...
    except:
        time.sleep(5)
        continue
```

Configure dead-letter exchanges and retry policies at the broker level.

---

## Rule 20 — Idempotency

Every worker must be safe to execute twice with the same message.

If STT Worker crashes and RabbitMQ redelivers the message:
- The result must **not** create a duplicate transcript
- Check existence before write
- Use `INSERT ... ON CONFLICT DO NOTHING` or equivalent
- Use `job_id` + `stage` as idempotency key

---

## Rule 21 — Testing — Not Optional

### Required test types

| Type | What it covers |
|---|---|
| Unit Tests | Domain logic, services (mocked dependencies) |
| Integration Tests | Repository → DB, Provider → external service |
| Contract Tests | Message schema compatibility across queues |

Minimum coverage enforced in CI.

---

## Rule 22 — Database Migrations

### Required

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

### Forbidden in production code

```python
Base.metadata.create_all(engine)
```

All schema changes go through Alembic. No exceptions.

---

## Rule 23 — API Design

REST only. All routes versioned under `/api/v1/`.

```
/api/v1/jobs
/api/v1/jobs/{job_id}
/api/v1/jobs/{job_id}/transcript
/api/v1/jobs/{job_id}/analysis
/api/v1/sources
/api/v1/sources/{source_id}
/api/v1/uploads/presigned-url
```

---

## Rule 24 — API Response Format

Single unified response envelope. No exceptions.

### Success

```json
{
  "success": true,
  "data": { ... },
  "error": null
}
```

### Error

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "JOB_NOT_FOUND",
    "message": "Audio job with id ... not found"
  }
}
```

No random response structures. No bare objects. No different shapes per endpoint.

---

## Rule 25 — File Structure

```
src/
│
├── domain/
│   ├── entities/
│   │   ├── audio_job.py
│   │   ├── transcript.py
│   │   ├── analysis.py
│   │   ├── report.py
│   │   └── watcher_source.py
│   ├── value_objects/
│   ├── enums/
│   │   └── job_status.py
│   └── errors/
│       └── domain_errors.py
│
├── application/
│   ├── services/
│   │   ├── audio_job_service.py
│   │   ├── transcript_service.py
│   │   ├── analysis_service.py
│   │   └── report_service.py
│   └── use_cases/
│
├── infrastructure/
│   ├── db/
│   │   ├── models/
│   │   └── session.py
│   ├── repositories/
│   │   ├── audio_job_repository.py
│   │   ├── transcript_repository.py
│   │   ├── analysis_repository.py
│   │   └── report_repository.py
│   ├── messaging/
│   │   ├── publisher.py
│   │   ├── consumer.py
│   │   └── schemas/
│   │       ├── ingestion_message.py
│   │       ├── stt_completed_message.py
│   │       ├── repair_completed_message.py
│   │       └── analysis_completed_message.py
│   ├── storage/
│   │   └── providers/
│   │       ├── s3_provider.py
│   │       ├── minio_provider.py
│   │       └── local_provider.py
│   └── providers/
│       ├── stt/
│       │   ├── base.py
│       │   ├── openai_whisper_provider.py
│       │   └── ibm_provider.py
│       └── analysis/
│           ├── base.py
│           └── openai_analysis_provider.py
│
├── presentation/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── jobs.py
│   │   │   ├── sources.py
│   │   │   └── uploads.py
│   │   ├── dependencies.py
│   │   └── response.py
│   └── websocket/
│       └── events.py
│
├── workers/
│   ├── stt_worker.py
│   ├── repair_worker.py
│   ├── analysis_worker.py
│   └── report_worker.py
│
└── tests/
    ├── unit/
    ├── integration/
    └── contract/
```

**No deviations from this structure.**

---

## Rule 26 — Frontend Rules (Next.js)

Frontend is **display layer only**.

### Allowed in frontend

- Render data from API
- Forms and user input
- WebSocket connection and event handling
- API calls via typed client

### Forbidden in frontend

- Business logic
- Data transformation
- Score calculation
- Validation beyond form UX
- Direct DB access

---

## Rule 27 — AI / LLM Output Must Be Structured

### Required — always request structured output

```json
{
  "summary": "...",
  "score": 0.87,
  "recommendation": "...",
  "flags": ["..."]
}
```

### Forbidden — free text parsing

```python
response = llm.complete(prompt)
score = extract_score_from_text(response)  # NO
```

Use `response_format`, function calling, or structured output mode. Never parse free text.

---

## Rule 28 — Never Duplicate Code (Most Important)

Before creating any new class, function, or module:

1. **Search the project** for an equivalent
2. If `AudioJobValidator` exists and you need `JobValidator` — **reuse it**
3. If the existing one is 80% there — **extend it**
4. Only create new if there is genuinely no equivalent

Duplication is a build failure.

---

## Rule 29 — No Implementation Before Contract (Second Most Important)

### Mandatory order of implementation

```
1. Interface / Abstract Base Class
2. Pydantic Schema / Message Contract
3. Repository
4. Service
5. Worker
6. Route
7. UI
```

### Forbidden

Writing a worker before its message schema exists.
Writing a service before its repository interface exists.
Writing a route before its service exists.

---

## CI Enforcement (Required)

The following CI checks must fail the build:

| Check | Tool |
|---|---|
| Duplicate code detection | `pylint`, `flake8-bugbear` |
| Missing type hints | `mypy --strict` |
| Test coverage below threshold | `pytest --cov` with minimum % |
| Architecture boundary violations | `import-linter` |
| Unstructured logs | Custom lint rule |
| Hardcoded secrets | `detect-secrets` |
| Missing Alembic migration | Migration diff check |

---

## Summary

| Principle | Status |
|---|---|
| Hexagonal Architecture | Mandatory |
| Domain-first, infrastructure-last | Mandatory |
| Pydantic everywhere | Mandatory |
| Repository pattern, no leakage | Mandatory |
| Provider pattern for all externals | Mandatory |
| Typed message contracts | Mandatory |
| Structured logging | Mandatory |
| Idempotent workers | Mandatory |
| Alembic migrations | Mandatory |
| CI architectural enforcement | Mandatory |
| No utils dumping ground | Mandatory |
| No hardcoded config | Mandatory |
| No code duplication | **Most Important** |
| Contract before implementation | **Second Most Important** |

---

*This document is the law of this codebase. If code doesn't comply, it doesn't ship.*
