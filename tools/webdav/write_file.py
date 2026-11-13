from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.webdav._common import (
    WRITE_MAX_BYTES,
    error_message,
    webdav_client_from_credentials,
)


class WriteFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        path = str(tool_parameters.get("path") or "").strip()
        content = str(tool_parameters.get("content") or "")
        content_type = (
            str(tool_parameters.get("content_type") or "").strip()
            or "text/plain; charset=utf-8")
        overwrite = bool(tool_parameters.get("overwrite") or False)

        if not path:
            yield self.create_text_message("Error: the 'path' parameter is required")
            return
        if tool_parameters.get("content") is None:
            yield self.create_text_message("Error: the 'content' parameter is required")
            return

        data = content.encode("utf-8")
        if len(data) > WRITE_MAX_BYTES:
            yield self.create_text_message(
                f"Error: content is {len(data)} bytes, over the "
                f"{WRITE_MAX_BYTES}-byte limit of this tool")
            return

        try:
            client = webdav_client_from_credentials(self.runtime.credentials)
        except ValueError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return
        try:
            client.write(path, data, content_type, overwrite)
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        yield self.create_text_message(
            f"Wrote {len(data)} byte(s) to {path}"
            + (" (overwritten)" if overwrite else ""))
        yield self.create_json_message({
            "path": path,
            "size": len(data),
            "content_type": content_type,
        })
