"""Tool-layer tests for the 8 WebDAV tools (fake client, no network)."""

from types import SimpleNamespace

import pytest

import tools.webdav.copy_file as copy_module
import tools.webdav.create_directory as create_dir_module
import tools.webdav.delete_file as delete_module
import tools.webdav.list_files as list_module
import tools.webdav.move_file as move_module
import tools.webdav.read_file as read_module
import tools.webdav.stat_file as stat_module
import tools.webdav.write_file as write_module
from tools.webdav._common import READ_MAX_BYTES, WRITE_MAX_BYTES
from webdav_client.errors import WebDAVError
from webdav_client.parser import WebDAVResource

WEBDAV = {
    "webdav_url": "https://example.com/remote.php/dav/files/alice/",
    "webdav_username": "alice",
    "webdav_password": "web-pass",
}
CALDAV = {
    "caldav_url": "https://calendar.example.org/dav/alice/",
    "caldav_username": "cal-alice",
    "caldav_password": "cal-pass",
}

ALL_TOOLS = [
    (list_module, "ListFilesTool", {}),
    (stat_module, "StatFileTool", {"path": "readme.txt"}),
    (read_module, "ReadFileTool", {"path": "readme.txt"}),
    (write_module, "WriteFileTool", {"path": "a.txt", "content": "x"}),
    (delete_module, "DeleteFileTool", {"path": "a.txt", "confirm": True}),
    (create_dir_module, "CreateDirectoryTool", {"path": "docs"}),
    (move_module, "MoveFileTool", {"from_path": "a.txt", "to_path": "b.txt"}),
    (copy_module, "CopyFileTool", {"from_path": "a.txt", "to_path": "b.txt"}),
]


class FakeClient:
    """Records calls; results are scripted by the test."""

    def __init__(self):
        self.calls = []
        self.list_result = []
        self.stat_result = None
        self.download_result = (b"", "text/plain")

    def list_dir(self, path=None):
        self.calls.append(("list_dir", path))
        return self.list_result

    def stat(self, path):
        self.calls.append(("stat", path))
        return self.stat_result

    def download(self, path):
        self.calls.append(("download", path))
        return self.download_result

    def write(self, path, data, content_type, overwrite):
        self.calls.append(("write", path, data, content_type, overwrite))

    def delete(self, path, recursive=False):
        self.calls.append(("delete", path, recursive))

    def mkdir(self, path, recursive=False):
        self.calls.append(("mkdir", path, recursive))

    def move(self, src, dst):
        self.calls.append(("move", src, dst))

    def copy(self, src, dst, overwrite=False):
        self.calls.append(("copy", src, dst, overwrite))


def make_tool(module, class_name, credentials, monkeypatch, fake=None):
    tool = getattr(module, class_name).__new__(getattr(module, class_name))
    tool.runtime = SimpleNamespace(credentials=credentials)
    monkeypatch.setattr(
        type(tool), "create_text_message",
        lambda self, text: ("text", text), raising=False)
    monkeypatch.setattr(
        type(tool), "create_json_message",
        lambda self, obj: ("json", obj), raising=False)
    if fake is not None:
        monkeypatch.setattr(
            module, "webdav_client_from_credentials",
            lambda creds, **kwargs: fake)
    return tool


# -- credential group selection ----------------------------------------------


@pytest.mark.parametrize("module,class_name,params", ALL_TOOLS)
def test_missing_credentials_yield_group_values_message(
        module, class_name, params, monkeypatch):
    tool = make_tool(module, class_name, {}, monkeypatch)
    out = list(tool._invoke(dict(params)))
    assert out == [("text",
                    ("Error: WebDAV credentials are not configured "
                     "(set webdav_url, webdav_username, webdav_password)"))]


@pytest.mark.parametrize("module,class_name,params", ALL_TOOLS)
def test_incomplete_credentials_yield_missing_fields(
        module, class_name, params, monkeypatch):
    tool = make_tool(
        module, class_name, {"webdav_url": WEBDAV["webdav_url"]}, monkeypatch)
    out = list(tool._invoke(dict(params)))
    assert out == [("text",
                    ("Error: WebDAV credentials are incomplete: "
                     "missing webdav_username, webdav_password"))]


@pytest.mark.parametrize("module,class_name,params", ALL_TOOLS)
def test_no_fallback_to_other_groups(
        module, class_name, params, monkeypatch):
    tool = make_tool(module, class_name, dict(CALDAV), monkeypatch)
    out = list(tool._invoke(dict(params)))
    assert len(out) == 1
    assert "WebDAV credentials are not configured" in out[0][1]
    assert "cal-pass" not in out[0][1]


# -- list_files --------------------------------------------------------------


def test_list_ok(monkeypatch):
    fake = FakeClient()
    fake.list_result = [
        WebDAVResource("/base/docs/", "docs", True, 0, "",
                       "Tue, 06 Jan 2026 11:30:00 GMT"),
        WebDAVResource("/base/readme.txt", "readme.txt", False, 12,
                       "text/plain", "Wed, 07 Jan 2026 12:00:00 GMT"),
    ]
    tool = make_tool(list_module, "ListFilesTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({}))
    assert fake.calls == [("list_dir", None)]
    text = out[0][1]
    assert "2 item(s) in /:" in text
    assert "DIR   docs" in text
    assert "FILE  readme.txt  12  text/plain  Wed, 07 Jan 2026 12:00:00 GMT" in text
    payload = out[1][1]
    assert payload["path"] == "/"
    assert payload["count"] == 2
    assert payload["items"][1] == {
        "name": "readme.txt",
        "path": "/base/readme.txt",
        "type": "file",
        "size": 12,
        "content_type": "text/plain",
        "modified": "Wed, 07 Jan 2026 12:00:00 GMT",
    }


def test_list_passes_path(monkeypatch):
    fake = FakeClient()
    tool = make_tool(list_module, "ListFilesTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({"path": "docs/"}))
    assert fake.calls == [("list_dir", "docs/")]
    assert "0 item(s) in docs/:" in out[0][1]


# -- stat_file ---------------------------------------------------------------


def test_stat_ok(monkeypatch):
    fake = FakeClient()
    fake.stat_result = WebDAVResource(
        "/base/readme.txt", "readme.txt", False, 12, "text/plain",
        "Wed, 07 Jan 2026 12:00:00 GMT")
    tool = make_tool(stat_module, "StatFileTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({"path": "readme.txt"}))
    assert fake.calls == [("stat", "readme.txt")]
    assert out[0][0] == "text"
    assert "FILE  readme.txt  12  text/plain" in out[0][1]
    assert out[1][1]["name"] == "readme.txt"
    assert out[1][1]["type"] == "file"


def test_stat_requires_path(monkeypatch):
    tool = make_tool(stat_module, "StatFileTool", WEBDAV, monkeypatch,
                     FakeClient())
    out = list(tool._invoke({}))
    assert out == [("text", "Error: the 'path' parameter is required")]


# -- read_file ---------------------------------------------------------------


def test_read_ok(monkeypatch):
    fake = FakeClient()
    fake.download_result = (b"hello world", "text/plain")
    tool = make_tool(read_module, "ReadFileTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({"path": "readme.txt"}))
    assert fake.calls == [("download", "readme.txt")]
    assert out[0] == ("text", "hello world")
    assert out[1][1] == {
        "path": "readme.txt",
        "size": 11,
        "content_type": "text/plain",
        "content": "hello world",
    }


def test_read_rejects_folder_path(monkeypatch):
    fake = FakeClient()
    tool = make_tool(read_module, "ReadFileTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({"path": "docs/"}))
    assert fake.calls == []
    assert "use stat_file/list_files" in out[0][1]


def test_read_text_cap(monkeypatch):
    fake = FakeClient()
    fake.download_result = (b"x" * (READ_MAX_BYTES + 1), "text/plain")
    tool = make_tool(read_module, "ReadFileTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({"path": "big.txt"}))
    assert len(out) == 1
    assert "shaba/webdav datasource plugin" in out[0][1]


def test_read_binary_refused(monkeypatch):
    fake = FakeClient()
    fake.download_result = (b"\xff\xfe\x00binary", "application/octet-stream")
    tool = make_tool(read_module, "ReadFileTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({"path": "image.png"}))
    assert len(out) == 1
    assert "binary file; use the shaba/webdav datasource plugin" in out[0][1]


# -- write_file --------------------------------------------------------------


def test_write_ok(monkeypatch):
    fake = FakeClient()
    tool = make_tool(write_module, "WriteFileTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({"path": "notes.txt", "content": "hello",
                             "overwrite": True}))
    assert fake.calls == [
        ("write", "notes.txt", b"hello", "text/plain; charset=utf-8", True)]
    assert "Wrote 5 byte(s) to notes.txt" in out[0][1]
    assert out[1][1]["size"] == 5


def test_write_custom_content_type(monkeypatch):
    fake = FakeClient()
    tool = make_tool(write_module, "WriteFileTool", WEBDAV, monkeypatch, fake)
    list(tool._invoke({"path": "data.json", "content": "{}",
                       "content_type": "application/json"}))
    assert fake.calls == [
        ("write", "data.json", b"{}", "application/json", False)]


def test_write_size_cap(monkeypatch):
    fake = FakeClient()
    tool = make_tool(write_module, "WriteFileTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({"path": "big.txt",
                             "content": "x" * (WRITE_MAX_BYTES + 1)}))
    assert fake.calls == []
    assert len(out) == 1
    assert "over the" in out[0][1]


# -- delete_file -------------------------------------------------------------


def test_delete_without_confirm_refuses(monkeypatch):
    fake = FakeClient()
    tool = make_tool(delete_module, "DeleteFileTool", WEBDAV, monkeypatch,
                     fake)
    out = list(tool._invoke({"path": "readme.txt"}))
    assert out == [("text", "refusing: pass confirm=true")]
    assert fake.calls == []


def test_delete_with_confirm_false_refuses(monkeypatch):
    fake = FakeClient()
    tool = make_tool(delete_module, "DeleteFileTool", WEBDAV, monkeypatch,
                     fake)
    out = list(tool._invoke({"path": "readme.txt", "confirm": False}))
    assert out == [("text", "refusing: pass confirm=true")]
    assert fake.calls == []


def test_delete_confirmed(monkeypatch):
    fake = FakeClient()
    tool = make_tool(delete_module, "DeleteFileTool", WEBDAV, monkeypatch,
                     fake)
    out = list(tool._invoke({"path": "docs/", "confirm": True,
                             "recursive": True}))
    assert fake.calls == [("delete", "docs/", True)]
    assert out[0] == ("text", "Deleted docs/")
    assert out[1][1]["deleted"] is True


# -- create_directory --------------------------------------------------------


def test_mkdir_ok(monkeypatch):
    fake = FakeClient()
    tool = make_tool(create_dir_module, "CreateDirectoryTool", WEBDAV,
                     monkeypatch, fake)
    out = list(tool._invoke({"path": "a/b", "recursive": True}))
    assert fake.calls == [("mkdir", "a/b", True)]
    assert out[0] == ("text", "Created folder a/b")


# -- move_file / copy_file ---------------------------------------------------


def test_move_ok(monkeypatch):
    fake = FakeClient()
    tool = make_tool(move_module, "MoveFileTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({"from_path": "a.txt", "to_path": "b.txt"}))
    assert fake.calls == [("move", "a.txt", "b.txt")]
    assert out[0] == ("text", "Moved a.txt to b.txt")


def test_copy_ok(monkeypatch):
    fake = FakeClient()
    tool = make_tool(copy_module, "CopyFileTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({"from_path": "a.txt", "to_path": "b.txt"}))
    assert fake.calls == [("copy", "a.txt", "b.txt", False)]
    assert out[0] == ("text", "Copied a.txt to b.txt")


def test_copy_overwrite(monkeypatch):
    fake = FakeClient()
    tool = make_tool(copy_module, "CopyFileTool", WEBDAV, monkeypatch, fake)
    list(tool._invoke({"from_path": "a.txt", "to_path": "b.txt",
                       "overwrite": True}))
    assert fake.calls == [("copy", "a.txt", "b.txt", True)]


# -- error formatting --------------------------------------------------------


def test_client_errors_get_webdav_prefix_and_redaction(monkeypatch):
    fake = FakeClient()

    def boom(path):
        fake.calls.append(("stat", path))
        raise WebDAVError("PROPFIND failed for https://alice:secret@example.com/x")

    fake.stat = boom
    tool = make_tool(stat_module, "StatFileTool", WEBDAV, monkeypatch, fake)
    out = list(tool._invoke({"path": "x"}))
    assert len(out) == 1
    assert out[0][1].startswith("WebDAV error: ")
    assert "alice:secret" not in out[0][1]
