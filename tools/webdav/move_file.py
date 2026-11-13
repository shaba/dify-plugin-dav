from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.webdav._common import error_message, webdav_client_from_credentials


class MoveFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        from_path = str(tool_parameters.get("from_path") or "").strip()
        to_path = str(tool_parameters.get("to_path") or "").strip()

        if not from_path:
            yield self.create_text_message("Error: the 'from_path' parameter is required")
            return
        if not to_path:
            yield self.create_text_message("Error: the 'to_path' parameter is required")
            return

        try:
            client = webdav_client_from_credentials(self.runtime.credentials)
        except ValueError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return
        try:
            client.move(from_path, to_path)
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        yield self.create_text_message(f"Moved {from_path} to {to_path}")
        yield self.create_json_message({
            "from_path": from_path,
            "to_path": to_path,
            "moved": True,
        })
