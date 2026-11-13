# DAV (CalDAV + CardDAV) for Dify

Source repository: <https://github.com/shaba/dify-plugin-dav>

One tool provider `dav` with two independent credential groups: CalDAV
(calendar events and tasks) and CardDAV (contacts). Works with any standards
compliant DAV server (Nextcloud, Radicale, …).

This plugin merges the former separate `shaba/caldav` and `shaba/carddav`
plugins. All 11 tool names, parameters and outputs are preserved; the tool
provider ID changes to `shaba/dav/dav` — select the new provider in your tool
nodes after installation. WebDAV file access is a different kind of plugin
(datasource) and remains a separate package, `shaba/webdav`.

## Configuration

Each credential record may configure one or both protocols; URL and login of
one protocol are never derived from or sent to the other:

```text
CalDAV URL:  https://calendar.example.org/dav/alice/
CardDAV URL: https://contacts.example.net/addressbooks/bob/
```

- CalDAV-only record: fill `caldav_*` fields, leave `carddav_*` empty.
- CardDAV-only record: fill `carddav_*` fields, leave `caldav_*` empty.
- To use two servers with different accounts independently, create two
  credential records and pick the needed one in each tool node.
- On save, only the filled groups are validated; a partially filled group is
  rejected naming the protocol.

## Tools

CalDAV: `list_calendars`, `list_events`, `search_events`, `list_tasks`,
`create_event`, `create_task`.
CardDAV: `list_addressbooks`, `list_contacts`, `search_contacts`,
`get_contact`, `create_contact`.

## Development

```bash
uv lock --python 3.12
uv sync --python 3.12 --frozen --group dev
uv run --frozen --group dev python -m pytest -q
```

Package with the Dify plugin CLI (`dify plugin package . -o dav.difypkg`).
