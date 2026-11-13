from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.webdav._common import (
    error_message,
    resource_dict,
    webdav_client_from_credentials,
)


class StatFileTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        path = str(tool_parameters.get("path") or "").strip()

        if not path:
            yield self.create_text_message("Error: the 'path' parameter is required")
            return

        try:
            client = webdav_client_from_credentials(self.runtime.credentials)
        except ValueError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return
        try:
            entry = client.stat(path)
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        kind = "DIR " if entry.is_dir else "FILE"
        yield self.create_text_message(
            f"{kind}  {entry.name}  {entry.size}  "
            f"{entry.content_type}  {entry.modified}")
        yield self.create_json_message(resource_dict(entry))
