# Privacy Policy

This plugin (`dify-plugin-dav`) does not collect, store or transmit any personal
data to the plugin author or any third party.

- The configured credentials are three independent groups: `caldav_url`,
  `caldav_username`, `caldav_password` for calendars, `carddav_url`,
  `carddav_username`, `carddav_password` for contacts, and `webdav_url`,
  `webdav_username`, `webdav_password` for files. They are stored by your
  Dify instance, not by the plugin author. A credential record may configure
  only the protocol you use; each tool receives only its own group.
- CalDAV tools connect **only** to `caldav_url` over the CalDAV protocol (HTTP),
  carrying the calendar name, query, event or task data you provided,
  authenticated with `caldav_username`/`caldav_password`.
- CardDAV tools send WebDAV/CardDAV requests (PROPFIND, REPORT, PUT) **only** to
  `carddav_url`, carrying the contact data, search query or address book
  selector you provided, authenticated with `carddav_username`/`carddav_password`.
  Requests use the User-Agent `dify-plugin-dav/<version>`.
- WebDAV tools send WebDAV requests (PROPFIND, GET, HEAD, PUT, DELETE, MKCOL,
  MOVE, COPY) **only** to `webdav_url`, carrying the file/folder paths and the
  file content you provided (read and write content is capped at 1 MiB),
  authenticated with `webdav_username`/`webdav_password`.
- No analytics, telemetry or external hosts are involved. The plugin itself
  persists nothing.

Your calendars, events, tasks, queries, contact data and WebDAV file content
are subject to the privacy policies of the CalDAV server configured in
`caldav_url`, the CardDAV server configured in `carddav_url` and the WebDAV
server configured in `webdav_url`. Knowledge-base ingestion of WebDAV files is
provided by the separate `shaba/webdav` datasource plugin with its own privacy
policy.
