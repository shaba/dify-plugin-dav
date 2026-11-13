from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from caldav_client.connection import connect, list_calendars
from caldav_client.errors import redact_credentials as caldav_redact
from carddav_client.api import get_addressbooks, make_session
from carddav_client.errors import redact_credentials as carddav_redact
from dav_credentials import group_values, has_group

_REDACT = {"CalDAV": caldav_redact, "CardDAV": carddav_redact}


class DAVProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        protocols = [p for p in ("CalDAV", "CardDAV") if has_group(p, credentials)]
        if not protocols:
            raise ToolProviderCredentialValidationError(
                "configure at least one complete credential group: "
                "caldav_url/caldav_username/caldav_password or "
                "carddav_url/carddav_username/carddav_password")
        errors: list[str] = []
        for protocol in protocols:
            try:
                group = group_values(protocol, credentials)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            redact = _REDACT[protocol]
            safe_url = redact(group["base_url"])
            try:
                if protocol == "CalDAV":
                    client = connect(
                        group["base_url"], group["username"], group["password"],
                        timeout=15)
                    list_calendars(client)
                else:
                    session = make_session(
                        group["username"], group["password"], timeout=15)
                    get_addressbooks(session, group["base_url"])
            except Exception as exc:  # noqa: BLE001
                errors.append(
                    f"{protocol} server is not reachable at {safe_url}: "
                    f"{redact(exc)}")
        if errors:
            raise ToolProviderCredentialValidationError("; ".join(errors))
