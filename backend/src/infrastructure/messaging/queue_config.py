"""Queue name constants and topology configuration.

Single source of truth for all queue and exchange names.
Workers import from here — never hardcode queue names in worker code.
"""


class QueueNames:
    """RabbitMQ queue name constants.

    Topology:
        ingestion_queue -> stt_queue -> transcript_repair_queue
        -> behavioral_analysis_queue -> report_queue

    Each queue has a corresponding dead-letter queue:
        <queue_name>.dlq
    """

    INGESTION = "ingestion_queue"
    STT = "stt_queue"
    TRANSCRIPT_REPAIR = "transcript_repair_queue"
    BEHAVIORAL_ANALYSIS = "behavioral_analysis_queue"
    REPORT = "report_queue"

    # Dead-letter queues — one per processing stage
    INGESTION_DLQ = "ingestion_queue.dlq"
    STT_DLQ = "stt_queue.dlq"
    TRANSCRIPT_REPAIR_DLQ = "transcript_repair_queue.dlq"
    BEHAVIORAL_ANALYSIS_DLQ = "behavioral_analysis_queue.dlq"
    REPORT_DLQ = "report_queue.dlq"


class ExchangeNames:
    """RabbitMQ exchange name constants."""

    MAIN = "audio_analysis"
    DEAD_LETTER = "audio_analysis.dlx"


class RedisChannels:
    """Redis pub/sub channel name constants for real-time events."""

    JOB_EVENTS = "job_events"
