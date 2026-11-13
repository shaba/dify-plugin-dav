from pathlib import Path

import pytest

from webdav_client.client import WebDAVClient

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class FakeResponse:
    def __init__(self, status_code, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self.closed = False

    def iter_content(self, chunk_size=8192):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i:i + chunk_size]

    def close(self):
        self.closed = True


class FakeSession:
    """A scripted requests.Session: records every call, routes via handler.

    Mirrors the requests API surface the WebDAV client uses (request/get) so
    client behavior is exercised without any real network.
    """

    def __init__(self, handler=None):
        self.auth = None
        self.calls = []
        self._handler = handler

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if self._handler is None:
            return FakeResponse(404)
        return self._handler(method, url, kwargs)

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)


@pytest.fixture
def base_url():
    return "https://example.com/remote.php/dav/files/alice/"


@pytest.fixture
def make_client(base_url):
    def _make(handler=None, **kwargs):
        session = FakeSession(handler)
        client = WebDAVClient(
            base_url, "alice", "secret", session=session, **kwargs)
        return client, session

    return _make
