"""Unit tests for the WebDAV client against a scripted fake session."""

import pytest
import requests

from tests.webdav.conftest import FakeResponse, load_fixture
from webdav_client.client import WebDAVClient
from webdav_client.errors import WebDAVError, redact_credentials


def propfind_ok(handler_body):
    return FakeResponse(207, handler_body)


# -- check -------------------------------------------------------------------


def test_check_sends_depth0_propfind(make_client):
    client, session = make_client(lambda m, u, k: propfind_ok(b""))
    client.check()
    (method, url, kwargs), = session.calls
    assert method == "PROPFIND"
    assert url == client.base_url
    assert kwargs["headers"]["Depth"] == "0"
    assert kwargs["allow_redirects"] is False


def test_check_auth_failure(make_client):
    client, _ = make_client(lambda m, u, k: FakeResponse(401))
    with pytest.raises(WebDAVError, match="authentication failed"):
        client.check()


def test_check_connection_error_is_redacted(make_client):
    def handler(m, u, k):
        raise requests.ConnectionError(
            "https://alice:secret@example.com/remote.php/dav/files/alice/ refused")

    client, _ = make_client(handler)
    with pytest.raises(WebDAVError) as exc:
        client.check()
    assert "secret" not in str(exc.value)
    assert "alice:secret" not in str(exc.value)


def test_base_url_scheme_and_host_validated():
    with pytest.raises(WebDAVError, match="http or https"):
        WebDAVClient("ftp://example.com/dav/")
    with pytest.raises(WebDAVError, match="host"):
        WebDAVClient("https://")


# -- path safety -------------------------------------------------------------


def test_relative_dotdot_escaping_base_is_rejected(make_client):
    client, session = make_client()
    with pytest.raises(WebDAVError, match="escapes"):
        client.list_dir("../../etc/passwd")
    assert session.calls == []


def test_absolute_path_outside_base_is_rejected(make_client):
    client, session = make_client()
    with pytest.raises(WebDAVError, match="escapes"):
        client.download("/other/place/file.txt")
    assert session.calls == []


def test_absolute_path_inside_base_is_allowed(make_client):
    client, session = make_client(
        lambda m, u, k: propfind_ok(load_fixture("listing.xml")))
    items = client.list_dir("/remote.php/dav/files/alice/docs/")
    assert "readme.txt" in [i.name for i in items]
    (_, url, _), = session.calls
    assert url == "https://example.com/remote.php/dav/files/alice/docs/"


def test_dotdot_staying_inside_base_is_allowed(make_client):
    client, _session = make_client(
        lambda m, u, k: propfind_ok(load_fixture("stat_file.xml")))
    entry = client.stat("docs/../readme.txt")
    assert entry.name == "readme.txt"


# -- list_dir / stat ---------------------------------------------------------


def test_list_dir_parses_children(make_client):
    client, session = make_client(
        lambda m, u, k: propfind_ok(load_fixture("listing.xml")))
    items = client.list_dir("")
    assert [i.name for i in items] == ["docs", "readme.txt"]
    docs, readme = items
    assert docs.is_dir and docs.size == 0
    assert not readme.is_dir
    assert readme.size == 12
    assert readme.content_type == "text/plain"
    assert readme.modified == "Wed, 07 Jan 2026 12:00:00 GMT"
    (_, _, kwargs), = session.calls
    assert kwargs["headers"]["Depth"] == "1"


def test_list_dir_error_status(make_client):
    client, _ = make_client(lambda m, u, k: FakeResponse(500))
    with pytest.raises(WebDAVError, match="PROPFIND returned 500"):
        client.list_dir("docs/")


def test_stat_returns_single_resource(make_client):
    client, session = make_client(
        lambda m, u, k: propfind_ok(load_fixture("stat_file.xml")))
    entry = client.stat("readme.txt")
    assert entry.name == "readme.txt"
    assert entry.href == "/remote.php/dav/files/alice/readme.txt"
    assert entry.size == 12
    assert entry.content_type == "text/plain"
    assert entry.modified == "Wed, 07 Jan 2026 12:00:00 GMT"
    (_, _, kwargs), = session.calls
    assert kwargs["headers"]["Depth"] == "0"


def test_stat_collection(make_client):
    client, _ = make_client(
        lambda m, u, k: propfind_ok(load_fixture("stat_dir.xml")))
    entry = client.stat("docs/")
    assert entry.is_dir


def test_stat_not_found(make_client):
    client, _ = make_client(lambda m, u, k: FakeResponse(404))
    with pytest.raises(WebDAVError, match="not found"):
        client.stat("missing.txt")


# -- download ----------------------------------------------------------------


def test_download_returns_content_and_type(make_client):
    client, session = make_client(
        lambda m, u, k: FakeResponse(200, b"hello world",
                                     {"Content-Type": "text/plain"}))
    content, content_type = client.download("readme.txt")
    assert content == b"hello world"
    assert content_type == "text/plain"
    (method, url, kwargs), = session.calls
    assert method == "GET"
    assert url == "https://example.com/remote.php/dav/files/alice/readme.txt"
    assert kwargs["allow_redirects"] is False


def test_download_folder_rejected(make_client):
    client, session = make_client()
    with pytest.raises(WebDAVError, match="Cannot download a folder"):
        client.download("docs/")
    assert session.calls == []


def test_download_size_cap(make_client):
    client, _ = make_client(
        lambda m, u, k: FakeResponse(200, b"x" * 10, {}),
        max_download_bytes=4)
    with pytest.raises(WebDAVError, match="maximum download size"):
        client.download("big.bin")


def test_download_declared_size_cap(make_client):
    client, _ = make_client(
        lambda m, u, k: FakeResponse(200, b"x" * 4, {"Content-Length": "10"}),
        max_download_bytes=4)
    with pytest.raises(WebDAVError, match="maximum download size"):
        client.download("big.bin")


def test_download_streams_and_closes_on_declared_cap(make_client):
    resp = FakeResponse(200, b"x" * 100, {"Content-Length": "100000000"})
    client, session = make_client(
        lambda m, u, k: resp, max_download_bytes=4)
    with pytest.raises(WebDAVError, match="maximum download size"):
        client.download("big.bin")
    (_, _, kwargs), = session.calls
    assert kwargs["stream"] is True
    assert resp.closed is True


# -- write -------------------------------------------------------------------


def test_write_refuses_overwrite_without_flag(make_client):
    client, session = make_client(lambda m, u, k: FakeResponse(200))
    with pytest.raises(WebDAVError, match="already exists \\(pass overwrite=true\\)"):
        client.write("readme.txt", b"new", "text/plain", overwrite=False)
    # Only the HEAD probe; no PUT may be sent.
    assert [c[0] for c in session.calls] == ["HEAD"]


def test_write_new_file(make_client):
    def handler(method, url, kwargs):
        if method == "HEAD":
            return FakeResponse(404)
        assert method == "PUT"
        return FakeResponse(201)

    client, session = make_client(handler)
    client.write("notes.txt", b"hello", "text/plain; charset=utf-8")
    (_, _, put_kwargs), = [c for c in session.calls if c[0] == "PUT"]
    assert put_kwargs["data"] == b"hello"
    assert put_kwargs["headers"]["Content-Type"] == "text/plain; charset=utf-8"
    assert put_kwargs["allow_redirects"] is False


def test_write_overwrite_existing(make_client):
    def handler(method, url, kwargs):
        return FakeResponse(200 if method == "HEAD" else 204)

    client, _ = make_client(handler)
    client.write("readme.txt", b"new", "text/plain", overwrite=True)


def test_write_auth_error(make_client):
    def handler(method, url, kwargs):
        return FakeResponse(403)

    client, _ = make_client(handler)
    with pytest.raises(WebDAVError, match="authentication failed"):
        client.write("readme.txt", b"new", "text/plain")


def test_write_unexpected_status(make_client):
    def handler(method, url, kwargs):
        return FakeResponse(404 if method == "HEAD" else 500)

    client, _ = make_client(handler)
    with pytest.raises(WebDAVError, match="PUT returned 500"):
        client.write("readme.txt", b"new", "text/plain")


# -- delete ------------------------------------------------------------------


def test_delete_non_empty_folder_refused_without_recursive(make_client):
    def handler(method, url, kwargs):
        depth = kwargs.get("headers", {}).get("Depth")
        if method == "PROPFIND" and depth == "0":
            return propfind_ok(load_fixture("stat_dir.xml"))
        if method == "PROPFIND" and depth == "1":
            return propfind_ok(load_fixture("listing.xml"))
        raise AssertionError(f"unexpected {method}")

    client, session = make_client(handler)
    with pytest.raises(WebDAVError, match="not empty \\(pass recursive=true\\)"):
        client.delete("docs/")
    assert "DELETE" not in [c[0] for c in session.calls]


def test_delete_file(make_client):
    def handler(method, url, kwargs):
        if method == "PROPFIND":
            return propfind_ok(load_fixture("stat_file.xml"))
        assert method == "DELETE"
        return FakeResponse(204)

    client, session = make_client(handler)
    client.delete("readme.txt")
    assert [c[0] for c in session.calls] == ["PROPFIND", "DELETE"]


def test_delete_recursive_skips_guard(make_client):
    client, session = make_client(lambda m, u, k: FakeResponse(204))
    client.delete("docs/", recursive=True)
    assert [c[0] for c in session.calls] == ["DELETE"]


def test_delete_unexpected_status(make_client):
    def handler(method, url, kwargs):
        if method == "PROPFIND":
            return propfind_ok(load_fixture("stat_file.xml"))
        return FakeResponse(403)

    client, _ = make_client(handler)
    with pytest.raises(WebDAVError, match="authentication failed"):
        client.delete("readme.txt")


# -- mkdir -------------------------------------------------------------------


def test_mkdir_created(make_client):
    client, session = make_client(lambda m, u, k: FakeResponse(201))
    client.mkdir("docs")
    (method, url, _), = session.calls
    assert method == "MKCOL"
    assert url == "https://example.com/remote.php/dav/files/alice/docs/"


def test_mkdir_already_exists(make_client):
    client, _ = make_client(lambda m, u, k: FakeResponse(405))
    with pytest.raises(WebDAVError, match="already exists"):
        client.mkdir("docs")


def test_mkdir_conflict_without_recursive(make_client):
    client, _ = make_client(lambda m, u, k: FakeResponse(409))
    with pytest.raises(WebDAVError, match="MKCOL returned 409"):
        client.mkdir("a/b/c")


def test_mkdir_recursive_creates_parent_chain(make_client):
    attempts = []

    def handler(method, url, kwargs):
        assert method == "MKCOL"
        attempts.append(url)
        # The direct MKCOL of the full path conflicts (missing parent);
        # every chain segment then succeeds.
        return FakeResponse(409 if len(attempts) == 1 else 201)

    client, session = make_client(handler)
    client.mkdir("a/b/c", recursive=True)
    urls = [c[1] for c in session.calls]
    assert urls == [
        "https://example.com/remote.php/dav/files/alice/a/b/c/",
        "https://example.com/remote.php/dav/files/alice/a/",
        "https://example.com/remote.php/dav/files/alice/a/b/",
        "https://example.com/remote.php/dav/files/alice/a/b/c/",
    ]


def test_mkdir_recursive_tolerates_existing_segments(make_client):
    def handler(method, url, kwargs):
        if url.endswith("/a/"):
            return FakeResponse(405)
        return FakeResponse(201)

    client, _ = make_client(handler)
    client.mkdir("a/b", recursive=True)


# -- move / copy -------------------------------------------------------------


def test_move_sends_same_host_destination(make_client):
    client, session = make_client(lambda m, u, k: FakeResponse(204))
    client.move("readme.txt", "docs/readme.txt")
    (method, _, kwargs), = session.calls
    assert method == "MOVE"
    assert kwargs["headers"]["Destination"] == \
        "https://example.com/remote.php/dav/files/alice/docs/readme.txt"
    assert kwargs["headers"]["Overwrite"] == "T"


def test_copy_overwrite_false_sends_overwrite_f(make_client):
    client, session = make_client(lambda m, u, k: FakeResponse(201))
    client.copy("readme.txt", "copy.txt", overwrite=False)
    (_, _, kwargs), = session.calls
    assert kwargs["headers"]["Overwrite"] == "F"


def test_copy_412_destination_exists(make_client):
    client, _ = make_client(lambda m, u, k: FakeResponse(412))
    with pytest.raises(WebDAVError, match="destination exists \\(Overwrite: F\\)"):
        client.copy("readme.txt", "copy.txt", overwrite=False)


def test_destination_other_server_rejected(make_client):
    client, session = make_client(lambda m, u, k: FakeResponse(204))
    with pytest.raises(WebDAVError, match="destination must be on the same server"):
        client.move("readme.txt", "https://evil.example.org/dav/files/alice/x.txt")
    assert session.calls == []


def test_destination_full_url_same_host_accepted(make_client):
    client, session = make_client(lambda m, u, k: FakeResponse(204))
    client.move(
        "readme.txt",
        "https://example.com/remote.php/dav/files/alice/docs/readme.txt")
    (_, _, kwargs), = session.calls
    assert kwargs["headers"]["Destination"] == \
        "https://example.com/remote.php/dav/files/alice/docs/readme.txt"


def test_move_unexpected_status(make_client):
    client, _ = make_client(lambda m, u, k: FakeResponse(500))
    with pytest.raises(WebDAVError, match="MOVE returned 500"):
        client.move("readme.txt", "copy.txt")


# -- redaction ---------------------------------------------------------------


def test_redact_credentials_strips_userinfo():
    assert redact_credentials(
        "GET https://alice:secret@example.com/dav/ failed") == \
        "GET https://example.com/dav/ failed"


def test_auth_error_never_contains_url(make_client):
    # base_url itself embeds credentials; no error message may leak them.
    client, _ = make_client(lambda m, u, k: FakeResponse(401))
    client.base_url = "https://alice:secret@example.com/dav/"
    with pytest.raises(WebDAVError) as exc:
        client.check()
    assert "secret" not in str(exc.value)
