# DAV (CalDAV + CardDAV + WebDAV) for Dify

Source repository: <https://github.com/shaba/dify-plugin-dav>

One tool provider `dav` with three independent credential groups: CalDAV
(calendar events and tasks), CardDAV (contacts) and WebDAV (file utilities).
Works with any standards compliant DAV server (Nextcloud, Radicale, …).

This plugin merges the former separate `shaba/caldav` and `shaba/carddav`
plugins. All 11 tool names, parameters and outputs are preserved; the tool
provider ID changes to `shaba/dav/dav` — select the new provider in your tool
nodes after installation. Knowledge-base ingestion of WebDAV files is a
different kind of plugin (datasource) and remains a separate package,
`shaba/webdav`.

## Configuration

Each credential record may configure one or more protocols; URL and login of
one protocol are never derived from or sent to the others:

```text
CalDAV URL:  https://calendar.example.org/dav/alice/
CardDAV URL: https://contacts.example.net/addressbooks/bob/
WebDAV URL:  https://example.com/remote.php/dav/files/alice/
```

- CalDAV-only record: fill `caldav_*` fields, leave `carddav_*`/`webdav_*` empty.
- CardDAV-only record: fill `carddav_*` fields, leave `caldav_*`/`webdav_*` empty.
- WebDAV-only record: fill `webdav_*` fields, leave `caldav_*`/`carddav_*` empty.
- To use two servers with different accounts independently, create two
  credential records and pick the needed one in each tool node.
- On save, only the filled groups are validated; a partially filled group is
  rejected naming the protocol.

## Tools

CalDAV: `list_calendars`, `list_events`, `search_events`, `list_tasks`,
`create_event`, `create_task`.
CardDAV: `list_addressbooks`, `list_contacts`, `search_contacts`,
`get_contact`, `create_contact`.

WebDAV file utilities (paths are relative to the configured WebDAV URL;
text reads/writes are capped at 1 MiB — use the `shaba/webdav` datasource
plugin to ingest larger or binary files into a knowledge base):

| Tool | Description |
| --- | --- |
| `list_files` | List files and folders in a directory |
| `stat_file` | Get metadata of a single file or folder |
| `read_file` | Read a UTF-8 text file (max 1 MiB) |
| `write_file` | Write a text file (refuses overwrite unless `overwrite=true`) |
| `delete_file` | Delete a file or folder (requires `confirm=true`; non-empty folders need `recursive=true`) |
| `create_directory` | Create a folder (`recursive=true` creates missing parents) |
| `move_file` | Move/rename a file or folder |
| `copy_file` | Copy a file or folder (refuses overwrite unless `overwrite=true`) |

## Development

```bash
uv lock --python 3.12
uv sync --python 3.12 --frozen --group dev
uv run --frozen --group dev python -m pytest -q
```

Package with the Dify plugin CLI (`dify plugin package . -o dav.difypkg`).
