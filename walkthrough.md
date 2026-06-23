# Phase 2 Completion — Service Layer, Messaging, DI Wiring

## Project Tree (Phase 2 state)

```
backend/src/
├── domain/
│   ├── entities/
│   │   ├── audio_job.py          ✅ Status transitions owned by entity
│   │   ├── job_event.py          ✅ NEW — immutable audit log entry
│   │   ├── transcript.py         ✅
│   │   ├── analysis.py           ✅ Call center / sales scoring schema
│   │   ├── report.py             ✅
│   │   ├── watcher_source.py     ✅
│   │   └── user.py               ✅ Role hierarchy enforcement
│   ├── enums/
│   │   ├── job_status.py         ✅ Pipeline transitions + next_stage()
│   │   ├── source_type.py        ✅
│   │   └── user_role.py          ✅
│   ├── errors/
│   │   └── domain_errors.py      ✅ Full typed error hierarchy
│   ├── value_objects/
│   │   ├── audio_metadata.py     ✅ Format/duration/size validation
│   │   ├── speaker_segment.py    ✅
│   │   └── call_metrics.py       ✅ Talk-time % sum validation
│   └── ports/
│       ├── repositories.py       ✅ + JobEventRepository ABC added
│       ├── providers.py          ✅ STT / Repair / Analysis ABCs
│       └── storage_messaging.py  ✅ StorageProvider / MessagePublisher / MessageConsumer ABCs
│
├── application/
│   └── services/
│       ├── audio_job_service.py  ✅ NEW — full lifecycle, typed commands
│       └── job_event_service.py  ✅ NEW — audit log recorder
│
└── infrastructure/
    ├── config/
    │   └── settings.py           ✅ Per-service typed settings, lru_cache
    ├── db/
    │   ├── tables.py             ✅ SQLAlchemy Core (no ORM), all 6 tables
    │   └── session.py            ✅ Async connection factory
    ├── logging/
    │   └── logger.py             ✅ structlog JSON, get_logger()
    ├── messaging/
    │   ├── queue_config.py       ✅ QueueNames / ExchangeNames / RedisChannels
    │   ├── schemas.py            ✅ All typed message contracts
    │   ├── setup.py              ✅ NEW — DLX topology declaration
    │   ├── rabbitmq_publisher.py ✅ NEW — implements MessagePublisher
    │   └── rabbitmq_consumer.py  ✅ NEW — implements MessageConsumer + Acknowledger
    ├── repositories/
    │   ├── audio_job_repository.py    ✅
    │   ├── transcript_repository.py   ✅
    │   ├── analysis_repository.py     ✅
    │   ├── job_event_repository.py    ✅ NEW
    │   └── other_repositories.py     ✅ Report / WatcherSource / User
    └── container.py              ✅ NEW — DI wiring, RepositoryContainer, ServiceContainer

backend/
├── alembic/
│   ├── env.py                    ✅ NEW — async migrations, Core metadata
│   └── versions/                 (empty — run autogenerate after DB is up)
└── alembic.ini                   ✅ NEW
```

---

## Sequence Diagram — Job Creation Flow

```
Client / Watcher
      │
      │  CreateAudioJobCommand(source_id, file_name, original_path, storage_path)
      ▼
AudioJobService.create_job()
      │
      ├─► AudioJobRepository.exists_by_path_and_source()  ── Idempotency check
      │         │
      │         ▼
      │   PostgreSQL (audio_jobs table) ── SELECT EXISTS
      │
      │  [if already exists] ──► raise DuplicateJobError
      │
      ├─► AudioJob entity constructed (status=PENDING)
      │
      ├─► AudioJobRepository.create()
      │         │
      │         ▼
      │   PostgreSQL ── INSERT INTO audio_jobs RETURNING *
      │
      ├─► JobEventService.record_status_change(old=None, new=PENDING)
      │         │
      │         └─► JobEventRepository.create()
      │                   │
      │                   ▼
      │             PostgreSQL ── INSERT INTO job_events RETURNING *
      │
      ├─► MessagePublisher.publish(QueueNames.INGESTION, IngestionMessage)
      │         │
      │         ▼ [RabbitMQPublisher implements this]
      │   RabbitMQ ── Exchange: audio_analysis.main
      │               Routing key: ingestion_queue
      │               Delivery mode: PERSISTENT
      │               Body: IngestionMessage (JSON)
      │
      ▼
  return AudioJob (PENDING)
```

---

## Dependency Graph

```
┌──────────────────────────────────────────────────────────┐
│  DOMAIN (innermost — no external deps)                   │
│                                                          │
│  entities/  ──► enums/  ──► errors/  ──► value_objects/ │
│  ports/  (ABCs only — no implementations)               │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ depends on (inward only)
┌──────────────────────────────────────────────────────────┐
│  APPLICATION                                             │
│                                                          │
│  AudioJobService  ──► AudioJobRepository (port)          │
│                   ──► JobEventService                    │
│                   ──► MessagePublisher (port)            │
│                   ──► domain entities + errors           │
│                                                          │
│  JobEventService  ──► JobEventRepository (port)          │
│                   ──► domain entities                    │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ depends on (inward only)
┌──────────────────────────────────────────────────────────┐
│  INFRASTRUCTURE (outermost — all external deps live here)│
│                                                          │
│  PostgresAudioJobRepository  implements AudioJobRepository (port)  │
│  PostgresJobEventRepository  implements JobEventRepository (port)  │
│  RabbitMQPublisher           implements MessagePublisher (port)    │
│  RabbitMQConsumer            implements MessageConsumer (port)     │
│                                                          │
│  container.py — wires everything, injected into workers/routes │
└──────────────────────────────────────────────────────────┘
```

**Key rule enforcement verified:**

| Rule | Where enforced |
|---|---|
| Rule 2 — Deps inward only | `import-linter` contracts in `pyproject.toml` |
| Rule 4 — DB via repos only | `session.py` yields connection to repos only |
| Rule 6 — No direct RabbitMQ in services | `AudioJobService` calls `MessagePublisher` port only |
| Rule 9 — No shared mutable state | `container.py` uses frozen dataclasses, created per-request |
| Rule 12 — Repos are CRUD only | All repos: only `create/get/update/delete/list` methods |
| Rule 15 — Typed message contracts | All queue messages are Pydantic schemas in `schemas.py` |
| Rule 19 — No retry loops in code | Consumer `nack(requeue=False)` routes to DLQ — broker handles retries |
| Rule 20 — Idempotency | `exists_by_path_and_source()` in `create_job()` |
| Rule 22 — Alembic only | `alembic/env.py` configured, `create_all` never used |
| Rule 29 — Contract before impl | `JobEventRepository` ABC written before `PostgresJobEventRepository` |

---

## What's Next (Phase 3)

- [ ] OpenAI Whisper STT provider implementation
- [ ] OpenAI Repair provider (LLM correction + diarization)
- [ ] OpenAI Analysis provider (GPT-4o structured output)
- [ ] MinIO storage provider
- [ ] STT, Repair, Analysis, Report workers
- [ ] FastAPI presentation layer (routes, auth, response envelope)
- [ ] WebSocket service (Redis pub/sub → client)
- [ ] Filesystem watcher service
- [ ] Frontend (Next.js)
- [ ] Prometheus metrics + Grafana dashboards
- [ ] Unit + integration + contract tests
