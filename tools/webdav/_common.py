"""Shared credential extraction and error formatting for WebDAV tools."""

from __future__ import annotations

from typing import Any

from dav_credentials import group_values
from webdav_client.client import WebDAVClient
from webdav_client.errors import redact_credentials

# Text tools buffer whole files into LLM context, so cap them well under the
# plugin runner memory budget; knowledge-base ingestion of large/binary files
# stays with the shaba/webdav datasource plugin.
READ_MAX_BYTES = 1024 * 1024  # 1 MiB
WRITE_MAX_BYTES = 1024 * 1024  # 1 MiB


def error_message(exc: object) -> str:
    """User/LLM-facing error text with any embedded URL credentials stripped."""
    return f"WebDAV error: {redact_credentials(exc)}"


def webdav_client_from_credentials(
    credentials: dict[str, Any],
    *,
    max_download_bytes: int | None = None,
) -> WebDAVClient:
    group = group_values("WebDAV", credentials)
    kwargs = {} if max_download_bytes is None else {
        "max_download_bytes": max_download_bytes}
    return WebDAVClient(
        group["base_url"], group["username"], group["password"], **kwargs)


def resource_dict(item) -> dict[str, Any]:
    """JSON-ready dict for one WebDAVResource entry."""
    return {
        "name": item.name,
        "path": item.href,
        "type": "dir" if item.is_dir else "file",
        "size": item.size,
        "content_type": item.content_type,
        "modified": item.modified,
    }
