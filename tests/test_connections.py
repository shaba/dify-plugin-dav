"""Transport-spy tests: each protocol client receives only its own group.

No real network: connect/make_session/get_* are replaced with recorders.
"""

from types import SimpleNamespace

import pytest
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

import provider.dav as provider_module
import tools.caldav._common as caldav_common
import tools.carddav.list_addressbooks as carddav_books_tool
import tools.webdav._common as webdav_common
from provider.dav import DAVProvider

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
WEBDAV = {
    "webdav_url": "https://example.com/remote.php/dav/files/alice/",
    "webdav_username": "web-alice",
    "webdav_password": "web-pass",
}
BOTH = {**CALDAV, **CARDDAV}


class Recorder:
    def __init__(self, return_value=None):
        self.calls = []
        self.return_value = return_value

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.return_value


def _wire_provider(monkeypatch):
    cal_connect = Recorder(SimpleNamespace(name="cal-client"))
    cal_list = Recorder([])
    card_session = Recorder(SimpleNamespace(name="card-session"))
    card_books = Recorder([])
    webdav_check = Recorder(None)
    webdav_client = Recorder(SimpleNamespace(check=webdav_check))
    monkeypatch.setattr(provider_module, "connect", cal_connect)
    monkeypatch.setattr(provider_module, "list_calendars", cal_list)
    monkeypatch.setattr(provider_module, "make_session", card_session)
    monkeypatch.setattr(provider_module, "get_addressbooks", card_books)
    monkeypatch.setattr(provider_module, "WebDAVClient", webdav_client)
    return cal_connect, cal_list, card_session, card_books, webdav_client, webdav_check


def _provider():
    return DAVProvider.__new__(DAVProvider)


def test_caldav_client_from_credentials_uses_only_caldav_group(monkeypatch):
    rec = Recorder(SimpleNamespace(name="cal-client"))
    monkeypatch.setattr(caldav_common, "connect", rec)

    caldav_common.client_from_credentials(BOTH)

    (args, _), = rec.calls
    assert args[0] == CALDAV["caldav_url"]
    assert args[1:] == ("cal-alice", "cal-pass")
    flat = repr(rec.calls)
    assert "contacts.example.net" not in flat
    assert "card-bob" not in flat and "card-pass" not in flat


def test_carddav_tool_sends_only_carddav_credentials(monkeypatch):
    sess_rec = Recorder(SimpleNamespace(name="card-session"))
    books_rec = Recorder([])
    monkeypatch.setattr(carddav_books_tool, "make_session", sess_rec)
    monkeypatch.setattr(carddav_books_tool, "get_addressbooks", books_rec)

    tool = carddav_books_tool.ListAddressbooksTool.__new__(
        carddav_books_tool.ListAddressbooksTool)
    tool.runtime = SimpleNamespace(credentials=BOTH)
    monkeypatch.setattr(
        type(tool), "create_text_message",
        lambda self, text: ("text", text), raising=False)
    monkeypatch.setattr(
        type(tool), "create_json_message",
        lambda self, obj: ("json", obj), raising=False)

    out = list(tool._invoke({}))
    assert ("text", "No address books found on the CardDAV server.") in out

    ((username, password), _), = sess_rec.calls
    assert (username, password) == ("card-bob", "card-pass")
    _, base_url = books_rec.calls[0][0]
    assert base_url == CARDDAV["carddav_url"]
    flat = repr(sess_rec.calls) + repr(books_rec.calls)
    assert "calendar.example.org" not in flat
    assert "cal-alice" not in flat and "cal-pass" not in flat


def test_validate_caldav_only_never_touches_carddav(monkeypatch):
    cal_connect, cal_list, card_session, card_books, webdav_client, _ = \
        _wire_provider(monkeypatch)
    _provider()._validate_credentials(dict(CALDAV))
    assert len(cal_connect.calls) == 1
    assert len(cal_list.calls) == 1
    assert card_session.calls == []
    assert card_books.calls == []
    assert webdav_client.calls == []


def test_validate_carddav_only_never_touches_caldav(monkeypatch):
    cal_connect, cal_list, card_session, card_books, webdav_client, _ = \
        _wire_provider(monkeypatch)
    _provider()._validate_credentials(dict(CARDDAV))
    assert len(card_session.calls) == 1
    assert len(card_books.calls) == 1
    assert cal_connect.calls == []
    assert cal_list.calls == []
    assert webdav_client.calls == []


def test_validate_webdav_only_never_touches_other_protocols(monkeypatch):
    cal_connect, cal_list, card_session, card_books, webdav_client, webdav_check = \
        _wire_provider(monkeypatch)
    _provider()._validate_credentials(dict(WEBDAV))
    assert len(webdav_client.calls) == 1
    assert len(webdav_check.calls) == 1
    (args, kwargs), = webdav_client.calls
    assert args == (WEBDAV["webdav_url"], "web-alice", "web-pass")
    assert kwargs["timeout"] == 15
    assert cal_connect.calls == [] and cal_list.calls == []
    assert card_session.calls == [] and card_books.calls == []


def test_validate_both_groups_validates_both(monkeypatch):
    cal_connect, _cal_list, card_session, _card_books, webdav_client, _ = \
        _wire_provider(monkeypatch)
    _provider()._validate_credentials(dict(BOTH))
    assert len(cal_connect.calls) == 1
    assert len(card_session.calls) == 1
    assert webdav_client.calls == []


def test_validate_all_three_groups_validates_all(monkeypatch):
    cal_connect, _cal_list, card_session, _card_books, webdav_client, webdav_check = \
        _wire_provider(monkeypatch)
    _provider()._validate_credentials({**CALDAV, **CARDDAV, **WEBDAV})
    assert len(cal_connect.calls) == 1
    assert len(card_session.calls) == 1
    assert len(webdav_client.calls) == 1
    assert len(webdav_check.calls) == 1


def test_validate_empty_raises_without_any_network_call(monkeypatch):
    cal_connect, _cal_list, card_session, _card_books, webdav_client, _ = \
        _wire_provider(monkeypatch)
    with pytest.raises(ToolProviderCredentialValidationError) as exc:
        _provider()._validate_credentials({})
    assert "webdav_url" in str(exc.value)
    assert cal_connect.calls == [] and card_session.calls == []
    assert webdav_client.calls == []


def test_validate_partial_group_raises_without_network(monkeypatch):
    cal_connect, _cal_list, card_session, _card_books, webdav_client, _ = \
        _wire_provider(monkeypatch)
    with pytest.raises(ToolProviderCredentialValidationError) as exc:
        _provider()._validate_credentials({"caldav_url": CALDAV["caldav_url"]})
    assert "caldav_username" in str(exc.value)
    assert cal_connect.calls == []
    assert card_session.calls == []
    assert webdav_client.calls == []


def test_validate_partial_webdav_group_raises_without_network(monkeypatch):
    _cal_connect, _cal_list, _card_session, _card_books, webdav_client, _ = \
        _wire_provider(monkeypatch)
    with pytest.raises(ToolProviderCredentialValidationError) as exc:
        _provider()._validate_credentials({"webdav_url": WEBDAV["webdav_url"]})
    assert "webdav_username" in str(exc.value)
    assert "webdav_password" in str(exc.value)
    assert webdav_client.calls == []


def test_broken_carddav_record_does_not_block_caldav_record(monkeypatch):
    _cal_connect, _cal_list, _card_session, _card_books, _webdav_client, _ = \
        _wire_provider(monkeypatch)
    monkeypatch.setattr(provider_module, "make_session", _Failing())

    # CalDAV-only record validates fine while CardDAV is entirely broken.
    _provider()._validate_credentials(dict(CALDAV))
    with pytest.raises(ToolProviderCredentialValidationError) as exc:
        _provider()._validate_credentials(dict(CARDDAV))
    assert "CardDAV" in str(exc.value)


def test_broken_webdav_record_does_not_block_other_records(monkeypatch):
    _cal_connect, _cal_list, _card_session, _card_books, _webdav_client, _ = \
        _wire_provider(monkeypatch)
    monkeypatch.setattr(provider_module, "WebDAVClient", _Failing())

    # CalDAV-only record validates fine while WebDAV is entirely broken.
    _provider()._validate_credentials(dict(CALDAV))
    with pytest.raises(ToolProviderCredentialValidationError) as exc:
        _provider()._validate_credentials(dict(WEBDAV))
    assert "WebDAV" in str(exc.value)


def test_webdav_client_from_credentials_uses_only_webdav_group(monkeypatch):
    rec = Recorder(SimpleNamespace(name="web-client"))
    monkeypatch.setattr(webdav_common, "WebDAVClient", rec)

    webdav_common.webdav_client_from_credentials({**BOTH, **WEBDAV})

    (args, _), = rec.calls
    assert args[0] == WEBDAV["webdav_url"]
    assert args[1:] == ("web-alice", "web-pass")
    flat = repr(rec.calls)
    assert "calendar.example.org" not in flat
    assert "contacts.example.net" not in flat
    assert "cal-alice" not in flat and "cal-pass" not in flat
    assert "card-bob" not in flat and "card-pass" not in flat


class _Failing:
    def __init__(self):
        self.calls = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise OSError("carddav is down")
