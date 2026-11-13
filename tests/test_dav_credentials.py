"""Tests for per-protocol credential group selection (dav_credentials)."""

import pytest

from dav_credentials import (
    caldav_group,
    carddav_group,
    group_values,
    has_group,
)

CALDAV = {
    "caldav_url": "https://calendar.example.org/dav/alice/",
    "caldav_username": "cal-alice",
    "caldav_password": "cal-pass",
}
CARDDAV = {
    "carddav_url": "https://contacts.example.net/remote.php/dav/",
    "carddav_username": "card-bob",
    "carddav_password": "card-pass",
}


def test_group_values_caldav_only():
    assert group_values("CalDAV", CALDAV) == {
        "base_url": CALDAV["caldav_url"],
        "username": "cal-alice",
        "password": "cal-pass",
    }


def test_group_values_carddav_only():
    assert group_values("CardDAV", CARDDAV) == {
        "base_url": CARDDAV["carddav_url"],
        "username": "card-bob",
        "password": "card-pass",
    }


def test_group_values_with_both_groups_keeps_protocols_separate():
    creds = {**CALDAV, **CARDDAV}
    assert group_values("CalDAV", creds)["username"] == "cal-alice"
    assert group_values("CardDAV", creds)["username"] == "card-bob"
    assert group_values("CalDAV", creds)["base_url"] == CALDAV["caldav_url"]
    assert group_values("CardDAV", creds)["base_url"] == CARDDAV["carddav_url"]


def test_empty_credentials_raise_naming_protocol_without_network():
    for protocol in ("CalDAV", "CardDAV"):
        with pytest.raises(ValueError, match=protocol):
            group_values(protocol, {})


def test_partial_group_raises_naming_missing_fields():
    partial = {"caldav_url": "https://calendar.example.org/dav/"}
    with pytest.raises(ValueError, match="CalDAV") as exc:
        group_values("CalDAV", partial)
    assert "caldav_username" in str(exc.value)
    assert "caldav_password" in str(exc.value)


def test_has_group_detects_presence_and_partial_and_absence():
    assert has_group("CalDAV", CALDAV)
    assert not has_group("CardDAV", CALDAV)
    assert has_group("CalDAV", {"caldav_url": "x"})
    assert not has_group("CardDAV", {})


def test_caldav_tool_without_its_own_group_fails_without_leaks():
    from tools.caldav._common import client_from_credentials

    with pytest.raises(ValueError, match="CalDAV") as exc:
        client_from_credentials(CARDDAV)
    assert "card-pass" not in str(exc.value)
    assert "card-bob" not in str(exc.value)


def test_helpers_return_own_triples():
    creds = {**CALDAV, **CARDDAV}
    assert caldav_group(creds) == (CALDAV["caldav_url"], "cal-alice", "cal-pass")
    assert carddav_group(creds) == (CARDDAV["carddav_url"], "card-bob", "card-pass")
