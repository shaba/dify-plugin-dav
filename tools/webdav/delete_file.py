from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.webdav._common import error_message, webdav_client_from_credentials


class DeleteFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        path = str(tool_parameters.get("path") or "").strip()
        confirm = tool_parameters.get("confirm")
        recursive = bool(tool_parameters.get("recursive") or False)

        if not path:
            yield self.create_text_message("Error: the 'path' parameter is required")
            return
        if confirm is not True:
            yield self.create_text_message("refusing: pass confirm=true")
            return

        try:
            client = webdav_client_from_credentials(self.runtime.credentials)
        except ValueError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return
        try:
            client.delete(path, recursive=recursive)
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        yield self.create_text_message(f"Deleted {path}")
        yield self.create_json_message({
            "path": path,
            "recursive": recursive,
            "deleted": True,
        })
