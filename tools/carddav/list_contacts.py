from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from carddav_client.api import get_contacts, make_session
from carddav_client.contacts import format_contact_list
from dav_credentials import carddav_group
from tools.carddav._common import error_message


class ListContactsTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            base_url, username, password = carddav_group(self.runtime.credentials)
        except ValueError as exc:
            yield self.create_text_message(f"Error: {exc}")
            return
        addressbook = str(tool_parameters.get("addressbook") or "").strip() or None


        try:
            session = make_session(username, password)
            book, contacts = get_contacts(session, base_url, addressbook)
        except Exception as exc:  # noqa: BLE001
            yield self.create_text_message(error_message(exc))
            return

        yield self.create_text_message(
            format_contact_list(contacts, f'Contacts in "{book.name}"'))
        yield self.create_json_message({
            "addressbook": book.name,
            "count": len(contacts),
            "contacts": [c.to_dict() for c in contacts],
        })
