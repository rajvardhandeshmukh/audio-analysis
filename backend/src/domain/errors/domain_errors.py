"""Domain error hierarchy.

All application errors inherit from DomainError.
No bare 'except Exception' is ever acceptable — catch specific types only.

Rule 17: Every except must catch a specific error type.
"""


class DomainError(Exception):
    """Base class for all domain errors.

    Attributes:
        message: Human-readable description of the error.
        code: Machine-readable error code for API responses.
    """

    def __init__(self, message: str, code: str | None = None) -> None:
        self.message = message
        self.code = code or self.__class__.__name__.upper()
        super().__init__(message)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(code={self.code!r}, message={self.message!r})"


# ─── Validation ───────────────────────────────────────────────────────────────

class ValidationError(DomainError):
    """Raised when input data fails domain validation rules."""


class InvalidAudioFormatError(ValidationError):
    """Raised when the audio file format is not supported."""


class AudioFileTooLargeError(ValidationError):
    """Raised when audio file exceeds allowed size limit."""


class AudioFileTooShortError(ValidationError):
    """Raised when audio duration is below minimum threshold."""


# ─── Job Lifecycle ────────────────────────────────────────────────────────────

class JobNotFoundError(DomainError):
    """Raised when an AudioJob cannot be found by its identifier."""


class DuplicateJobError(DomainError):
    """Raised when an identical job (same file + source) already exists."""


class InvalidJobTransitionError(DomainError):
    """Raised when a job status transition is not allowed."""


class JobAlreadyCompletedError(DomainError):
    """Raised when attempting to modify a completed job."""


# ─── Provider Errors ──────────────────────────────────────────────────────────

class ProviderError(DomainError):
    """Raised when an external provider (STT, LLM) call fails."""


class STTProviderError(ProviderError):
    """Raised when the STT provider fails to transcribe audio."""


class AnalysisProviderError(ProviderError):
    """Raised when the analysis provider fails to analyze a transcript."""


class ProviderRateLimitError(ProviderError):
    """Raised when an external provider returns a rate limit response."""


class ProviderResponseParseError(ProviderError):
    """Raised when the provider response cannot be parsed into the expected schema."""


# ─── Storage Errors ───────────────────────────────────────────────────────────

class StorageError(DomainError):
    """Raised when object storage operations fail."""


class FileNotFoundInStorageError(StorageError):
    """Raised when a file cannot be found in object storage."""


class StorageUploadError(StorageError):
    """Raised when uploading a file to storage fails."""


# ─── Messaging Errors ─────────────────────────────────────────────────────────

class MessagingError(DomainError):
    """Raised when message broker operations fail."""


class MessagePublishError(MessagingError):
    """Raised when publishing a message to a queue fails."""


class MessageDeserializationError(MessagingError):
    """Raised when an incoming queue message cannot be deserialized."""


# ─── Auth Errors ──────────────────────────────────────────────────────────────

class AuthenticationError(DomainError):
    """Raised when authentication credentials are invalid."""


class AuthorizationError(DomainError):
    """Raised when a user lacks permission for the requested operation."""


class TokenExpiredError(AuthenticationError):
    """Raised when a JWT token has expired."""


# ─── Resource Not Found ───────────────────────────────────────────────────────

class SourceNotFoundError(DomainError):
    """Raised when a WatcherSource cannot be found."""


class UserNotFoundError(DomainError):
    """Raised when a User cannot be found."""


class TranscriptNotFoundError(DomainError):
    """Raised when a Transcript cannot be found for a given job."""


class AnalysisNotFoundError(DomainError):
    """Raised when an Analysis cannot be found for a given job."""


class ReportNotFoundError(DomainError):
    """Raised when a Report cannot be found for a given job."""
