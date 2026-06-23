"""File hasher — SHA-256 fingerprint for audio file deduplication.

Used by WatcherService before creating a job to check if this exact
file content has already been processed (not just path-based check).
"""

import hashlib


def sha256(path: str, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hex digest of a file.

    Reads in chunks — safe for large audio files.

    Args:
        path: Absolute path to the file.
        chunk_size: Read chunk size in bytes.

    Returns:
        Lowercase hex SHA-256 digest string.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
