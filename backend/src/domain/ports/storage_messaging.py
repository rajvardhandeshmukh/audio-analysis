"""Storage and messaging port interfaces.

Rule 6: No RabbitMQ calls outside the messaging layer.
Rule 14: StorageProvider interface — implementations in infrastructure/storage/.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel


class StorageProvider(ABC):
    """Object storage interface.

    Implementations:
        infrastructure/storage/minio_provider.py
        infrastructure/storage/local_provider.py
    """

    @abstractmethod
    async def upload(
        self,
        source_path: str,
        destination_key: str,
        content_type: str | None = None,
    ) -> str:
        """Upload a file to object storage.

        Args:
            source_path: Local filesystem path to the file.
            destination_key: Storage key / path within the bucket.
            content_type: MIME type of the file.

        Returns:
            The storage key of the uploaded file.

        Raises:
            StorageUploadError: On upload failure.
        """
        ...

    @abstractmethod
    async def download(self, storage_key: str, destination_path: str) -> None:
        """Download a file from object storage to local filesystem.

        Args:
            storage_key: Storage key / path within the bucket.
            destination_path: Local path to write the file.

        Raises:
            FileNotFoundInStorageError: If key does not exist.
            StorageError: On download failure.
        """
        ...

    @abstractmethod
    async def generate_presigned_url(
        self,
        storage_key: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        """Generate a time-limited presigned URL for direct client access.

        Args:
            storage_key: Storage key / path within the bucket.
            expires_in_seconds: URL expiry duration.

        Returns:
            Presigned URL string.

        Raises:
            FileNotFoundInStorageError: If key does not exist.
        """
        ...

    @abstractmethod
    async def delete(self, storage_key: str) -> None:
        """Delete a file from object storage.

        Args:
            storage_key: Storage key / path to delete.

        Raises:
            StorageError: On deletion failure.
        """
        ...

    @abstractmethod
    async def exists(self, storage_key: str) -> bool:
        """Check if a storage key exists.

        Args:
            storage_key: Storage key / path to check.

        Returns:
            True if file exists, False otherwise.
        """
        ...


class MessagePublisher(ABC):
    """Message broker publisher interface.

    Rule 6: Only this abstraction may publish to queues.
    Implementations:
        infrastructure/messaging/rabbitmq_publisher.py
    """

    @abstractmethod
    async def publish(
        self,
        queue_name: str,
        message: BaseModel,
        priority: int = 0,
    ) -> None:
        """Publish a typed Pydantic message to a named queue.

        Args:
            queue_name: Target queue name (use QueueNames constants).
            message: Typed Pydantic message — never raw dict.
            priority: Message priority (0 = normal, 10 = high).

        Raises:
            MessagePublishError: On broker failure.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the broker connection gracefully."""
        ...


class MessageConsumer(ABC):
    """Message broker consumer interface.

    Rule 6: Only this abstraction may consume from queues.
    Implementations:
        infrastructure/messaging/rabbitmq_consumer.py
    """

    @abstractmethod
    def consume(
        self,
        queue_name: str,
    ) -> AsyncIterator[tuple[BaseModel, "MessageAcknowledger"]]:
        """Async iterator that yields (message, acknowledger) pairs.

        Args:
            queue_name: Queue to consume from.

        Yields:
            Tuple of (deserialized message, acknowledger for ack/nack).

        Raises:
            MessagingError: On broker connection failure.
        """
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the broker connection gracefully."""
        ...


class MessageAcknowledger(ABC):
    """Controls ack/nack for a single consumed message."""

    @abstractmethod
    async def ack(self) -> None:
        """Acknowledge successful processing."""
        ...

    @abstractmethod
    async def nack(self, requeue: bool = False) -> None:
        """Negative-acknowledge — send to DLQ if requeue=False."""
        ...
