from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.webdav._common import (
    error_message,
    resource_dict,
    webdav_client_from_credentials,
)


class ListFilesTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        path = str(tool_parameters.get("path") or "").strip() or None

        try:
            client = webdav_client_from_credentials(self.runtime.credentials)
        except ValueError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return
        try:
            items = client.list_dir(path)
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        shown = path or "/"
        lines = [f"{len(items)} item(s) in {shown}:"]
        for item in items:
            kind = "DIR " if item.is_dir else "FILE"
            lines.append(
                f"{kind}  {item.name}  {item.size}  "
                f"{item.content_type}  {item.modified}")
        yield self.create_text_message("\n".join(lines))
        yield self.create_json_message({
            "path": shown,
            "count": len(items),
            "items": [resource_dict(item) for item in items],
        })
