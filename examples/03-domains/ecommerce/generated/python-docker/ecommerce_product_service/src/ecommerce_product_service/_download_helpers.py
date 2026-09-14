"""Helper functions for file download operations.

Provides streaming file download with SHA256 checksum verification and retry
logic for generated service code. Uses ``httpx`` for HTTP streaming and stdlib
``hashlib`` for checksums.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_DEFAULT_TIMEOUT_SECONDS: int = 300
_DEFAULT_CHUNK_SIZE: int = 65536
_DEFAULT_MAX_RETRIES: int = 3
_DEFAULT_RETRY_DELAY_SECONDS: float = 1.0


def _download_compute_sha256(data: bytes) -> str:
    """Compute SHA256 hex digest of the given bytes.

    Args:
        data: Bytes to hash.

    Returns:
        Lowercase hex string of the SHA256 digest.

    Raises:
        TypeError: If data is not bytes.
    """
    if not isinstance(data, bytes):
        raise TypeError(
            f"Expected bytes for SHA256 computation, got {type(data).__name__}. "
            "Provide raw bytes data."
        )
    return hashlib.sha256(data).hexdigest()


def _download_file(
    url: str,
    *,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    expected_sha256: str | None = None,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
) -> bytes:
    """Download file content from a URL with streaming, retry, and checksum verification.

    Streams the response in chunks to handle large files efficiently. Retries on
    transient failures (HTTP 429, 500, 502, 503, 504, and connection errors) with
    exponential backoff. Optionally verifies the SHA256 checksum of the downloaded
    content.

    Args:
        url: URL to download from.
        timeout_seconds: Total timeout for the HTTP request in seconds.
        expected_sha256: Expected SHA256 hex digest. If provided, the download
            is verified against this value.
        chunk_size: Size of streaming chunks in bytes.
        max_retries: Maximum number of retry attempts for transient failures.
        retry_delay_seconds: Base delay between retries in seconds. Actual delay
            uses exponential backoff (delay * 2^attempt).

    Returns:
        Downloaded file content as bytes.

    Raises:
        ValueError: If the downloaded content does not match expected_sha256.
        RuntimeError: If all retry attempts are exhausted.
    """
    last_error: Exception | None = None

    for attempt in range(max_retries):
        try:
            content = _download_stream_content(url, timeout_seconds, chunk_size)
            if expected_sha256 is not None:
                actual_sha256 = _download_compute_sha256(content)
                if not hmac.compare_digest(actual_sha256, expected_sha256.lower()):
                    raise ValueError(
                        f"SHA256 checksum mismatch for '{url}'. "
                        f"Expected: {expected_sha256.lower()}, "
                        f"Actual: {actual_sha256}. "
                        "The downloaded file may be corrupted or tampered with."
                    )
            logger.info(
                "Downloaded %d bytes from %s (attempt %d)",
                len(content),
                url,
                attempt + 1,
            )
            return content
        except ValueError:
            raise
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in _RETRYABLE_STATUS_CODES:
                raise RuntimeError(
                    f"Non-retryable HTTP error {exc.response.status_code} "
                    f"downloading '{url}'. Response: {exc.response.text[:200]}"
                ) from exc
            last_error = exc
            _download_wait_before_retry(attempt, retry_delay_seconds, url)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as exc:
            last_error = exc
            _download_wait_before_retry(attempt, retry_delay_seconds, url)

    raise RuntimeError(
        f"Failed to download '{url}' after {max_retries} attempts. "
        f"Last error: {last_error}. "
        "Check network connectivity and ensure the URL is accessible."
    )


def _download_file_to_path(
    url: str,
    dest_path: str,
    *,
    timeout_seconds: int = _DEFAULT_TIMEOUT_SECONDS,
    expected_sha256: str | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_delay_seconds: float = _DEFAULT_RETRY_DELAY_SECONDS,
) -> str:
    """Download a file to a local path with checksum verification.

    Args:
        url: URL to download from.
        dest_path: Local filesystem path to write the downloaded content to.
        timeout_seconds: Total timeout for the HTTP request in seconds.
        expected_sha256: Expected SHA256 hex digest for verification.
        max_retries: Maximum number of retry attempts for transient failures.
        retry_delay_seconds: Base delay between retries in seconds.

    Returns:
        The destination path where the file was written.

    Raises:
        ValueError: If the downloaded content does not match expected_sha256.
        RuntimeError: If all retry attempts are exhausted.
        OSError: If the destination path cannot be written to.
    """
    content = _download_file(
        url,
        timeout_seconds=timeout_seconds,
        expected_sha256=expected_sha256,
        max_retries=max_retries,
        retry_delay_seconds=retry_delay_seconds,
    )
    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    logger.info("Saved %d bytes to %s", len(content), dest_path)
    return dest_path


def _download_stream_content(url: str, timeout_seconds: int, chunk_size: int) -> bytes:
    """Stream content from a URL into memory.

    Args:
        url: URL to stream from.
        timeout_seconds: Total timeout for the HTTP request in seconds.
        chunk_size: Size of streaming chunks in bytes.

    Returns:
        Full response content as bytes.

    Raises:
        httpx.HTTPStatusError: If the response has an error status code.
        httpx.ConnectError: If the connection fails.
        httpx.TimeoutException: If the request times out.
    """
    chunks: list[bytes] = []
    with httpx.stream(
        "GET", url, timeout=timeout_seconds, follow_redirects=True
    ) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes(chunk_size=chunk_size):
            chunks.append(chunk)
    return b"".join(chunks)


def _download_wait_before_retry(attempt: int, base_delay: float, url: str) -> None:
    """Wait with exponential backoff before retrying a download.

    Args:
        attempt: Current attempt number (0-indexed).
        base_delay: Base delay in seconds.
        url: URL being downloaded (for logging).
    """
    delay = base_delay * (2**attempt)
    logger.warning(
        "Download attempt %d failed for %s, retrying in %.1f seconds",
        attempt + 1,
        url,
        delay,
    )
    time.sleep(delay)
