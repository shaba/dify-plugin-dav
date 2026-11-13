"""Shared credential extraction for CalDAV tools."""

from __future__ import annotations

from typing import Any

from caldav_client.connection import connect
from caldav_client.errors import redact_credentials
from dav_credentials import group_values


def error_message(exc: object) -> str:
    """User/LLM-facing error text with any embedded URL credentials stripped."""
    return f"CalDAV error: {redact_credentials(exc)}"


def client_from_credentials(credentials: dict[str, Any]):
    group = group_values("CalDAV", credentials)
    return connect(group["base_url"], group["username"], group["password"])
