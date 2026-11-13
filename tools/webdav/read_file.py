from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.webdav._common import (
    READ_MAX_BYTES,
    error_message,
    webdav_client_from_credentials,
)


class ReadFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        path = str(tool_parameters.get("path") or "").strip()

        if not path:
            yield self.create_text_message("Error: the 'path' parameter is required")
            return
        if path.endswith("/"):
            yield self.create_text_message(
                "Error: 'path' is a folder; use stat_file/list_files for folders")
            return

        try:
            client = webdav_client_from_credentials(
                self.runtime.credentials, max_download_bytes=READ_MAX_BYTES)
        except ValueError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return
        try:
            content, content_type = client.download(path)
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        if len(content) > READ_MAX_BYTES:
            yield self.create_text_message(
                f"Error: file is {len(content)} bytes, over the "
                f"{READ_MAX_BYTES}-byte limit of this tool; use the "
                f"shaba/webdav datasource plugin to ingest large files "
                f"into a knowledge base")
            return
        try:
            text = content.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            yield self.create_text_message(
                "Error: binary file; use the shaba/webdav datasource "
                "plugin to ingest it")
            return

        yield self.create_text_message(text)
        yield self.create_json_message({
            "path": path,
            "size": len(content),
            "content_type": content_type,
            "content": text,
        })
