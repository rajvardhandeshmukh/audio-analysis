"""Source type enumeration for the watcher source registry."""

from enum import StrEnum


class SourceType(StrEnum):
    """Supported audio source types for the Watcher Service.

    New source types must be registered here first before implementation.
    See Rule 29: Interface before implementation.
    """

    LOCAL_FILESYSTEM = "local_filesystem"
    S3 = "s3"
