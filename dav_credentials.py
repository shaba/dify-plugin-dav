"""Selection and validation of per-protocol credential groups for the DAV provider.

Each protocol (CalDAV, CardDAV, WebDAV) owns its credential group with an
independent URL, username and password. Tools and the provider must only ever
see their own protocol's group: there is no fallback to the other groups, no
shared session and no global state.
"""

from __future__ import annotations

from typing import Any

GROUP_KEYS: dict[str, tuple[str, str, str]] = {
    "CalDAV": ("caldav_url", "caldav_username", "caldav_password"),
    "CardDAV": ("carddav_url", "carddav_username", "carddav_password"),
    "WebDAV": ("webdav_url", "webdav_username", "webdav_password"),
}


def has_group(protocol: str, credentials: dict[str, Any]) -> bool:
    """True when any field of the protocol's credential group is filled."""
    keys = GROUP_KEYS[protocol]
    return any(str(credentials.get(key) or "").strip() for key in keys)


def group_values(protocol: str, credentials: dict[str, Any]) -> dict[str, str]:
    """Return base_url/username/password for one protocol group only.

    Raises ValueError naming the protocol when the group is empty or partial.
    Never falls back to the other protocol's group.
    """
    keys = GROUP_KEYS[protocol]
    base_url = str(credentials.get(keys[0]) or "").strip()
    username = str(credentials.get(keys[1]) or "").strip()
    password = str(credentials.get(keys[2]) or "")
    filled = [bool(base_url), bool(username), bool(password)]
    if not any(filled):
        raise ValueError(
            f"{protocol} credentials are not configured "
            f"(set {keys[0]}, {keys[1]}, {keys[2]})")
    if not all(filled):
        missing = [keys[i] for i, ok in enumerate(filled) if not ok]
        raise ValueError(
            f"{protocol} credentials are incomplete: missing {', '.join(missing)}")
    return {"base_url": base_url, "username": username, "password": password}


def caldav_group(credentials: dict[str, Any]) -> tuple[str, str, str]:
    group = group_values("CalDAV", credentials)
    return group["base_url"], group["username"], group["password"]


def carddav_group(credentials: dict[str, Any]) -> tuple[str, str, str]:
    group = group_values("CardDAV", credentials)
    return group["base_url"], group["username"], group["password"]


def webdav_group(credentials: dict[str, Any]) -> tuple[str, str, str]:
    group = group_values("WebDAV", credentials)
    return group["base_url"], group["username"], group["password"]
