"""Storage helper functions for generated Python code.

Uses aiobotocore for async S3-compatible storage operations.
Bucket name from S3_BUCKET env var. Endpoint from S3_ENDPOINT_URL (for MinIO/localstack).
"""

from __future__ import annotations

import os
from typing import Any, Optional

from aiobotocore.session import get_session
from botocore.exceptions import ClientError

_S3_BUCKET = os.environ["S3_BUCKET"]


def _get_s3_config() -> dict[str, object]:
    """Get S3 client config from environment."""
    config: dict[str, object] = {}
    endpoint = os.environ.get("S3_ENDPOINT_URL")
    if endpoint:
        config["endpoint_url"] = endpoint
    return config


async def _storage_upload(path: str, content: Any, options: Optional[dict] = None) -> str:
    """Upload file to S3."""
    session = get_session()
    kwargs: dict[str, object] = {"Bucket": _S3_BUCKET, "Key": path, "Body": content}
    if options and "contentType" in options:
        kwargs["ContentType"] = options["contentType"]
    if options and "metadata" in options:
        kwargs["Metadata"] = options["metadata"]
    async with session.create_client("s3", **_get_s3_config()) as client:
        await client.put_object(**kwargs)
    return path


async def _storage_download(path: str) -> object:
    """Download file from S3."""
    session = get_session()
    async with session.create_client("s3", **_get_s3_config()) as client:
        response = await client.get_object(Bucket=_S3_BUCKET, Key=path)
        async with response["Body"] as stream:
            return await stream.read()


async def _storage_delete(path: str) -> bool:
    """Delete file from S3."""
    session = get_session()
    async with session.create_client("s3", **_get_s3_config()) as client:
        await client.delete_object(Bucket=_S3_BUCKET, Key=path)
        return True


async def _storage_exists(path: str) -> bool:
    """Check if file exists in S3."""
    session = get_session()
    async with session.create_client("s3", **_get_s3_config()) as client:
        try:
            await client.head_object(Bucket=_S3_BUCKET, Key=path)
            return True
        except ClientError:
            return False


async def _storage_list(prefix: Optional[str] = None) -> list[dict[str, object]]:
    """List files in S3."""
    session = get_session()
    kwargs: dict[str, object] = {"Bucket": _S3_BUCKET}
    if prefix:
        kwargs["Prefix"] = prefix
    async with session.create_client("s3", **_get_s3_config()) as client:
        response = await client.list_objects_v2(**kwargs)
        return response.get("Contents", [])


async def _storage_get_url(path: str, expires: Optional[int] = None) -> str:
    """Get presigned URL for S3 object."""
    session = get_session()
    async with session.create_client("s3", **_get_s3_config()) as client:
        return client.generate_presigned_url(
            "get_object",
            Params={"Bucket": _S3_BUCKET, "Key": path},
            ExpiresIn=expires or 3600,
        )


async def _storage_copy(source: str, dest: str) -> bool:
    """Copy file within S3."""
    session = get_session()
    async with session.create_client("s3", **_get_s3_config()) as client:
        await client.copy_object(
            Bucket=_S3_BUCKET,
            Key=dest,
            CopySource={"Bucket": _S3_BUCKET, "Key": source},
        )
        return True


async def _storage_move(source: str, dest: str) -> bool:
    """Move file within S3 (copy + delete)."""
    await _storage_copy(source, dest)
    await _storage_delete(source)
    return True


async def _storage_get_metadata(path: str) -> dict[str, object]:
    """Get file metadata from S3."""
    session = get_session()
    async with session.create_client("s3", **_get_s3_config()) as client:
        response = await client.head_object(Bucket=_S3_BUCKET, Key=path)
        return {
            "contentType": response.get("ContentType"),
            "contentLength": response.get("ContentLength"),
            "lastModified": response.get("LastModified"),
            "metadata": response.get("Metadata", {}),
        }


async def _storage_set_metadata(path: str, metadata: dict[str, str]) -> None:
    """Set file metadata in S3 (copy-in-place with new metadata)."""
    session = get_session()
    async with session.create_client("s3", **_get_s3_config()) as client:
        await client.copy_object(
            Bucket=_S3_BUCKET,
            Key=path,
            CopySource={"Bucket": _S3_BUCKET, "Key": path},
            Metadata=metadata,
            MetadataDirective="REPLACE",
        )
