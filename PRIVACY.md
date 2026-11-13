# Privacy Policy

This plugin (`dify-plugin-dav`) does not collect, store or transmit any personal
data to the plugin author or any third party.

- The configured credentials are two independent groups: `caldav_url`,
  `caldav_username`, `caldav_password` for calendars, and `carddav_url`,
  `carddav_username`, `carddav_password` for contacts. They are stored by your
  Dify instance, not by the plugin author. A credential record may configure
  only the protocol you use; each tool receives only its own group.
- CalDAV tools connect **only** to `caldav_url` over the CalDAV protocol (HTTP),
  carrying the calendar name, query, event or task data you provided,
  authenticated with `caldav_username`/`caldav_password`.
- CardDAV tools send WebDAV/CardDAV requests (PROPFIND, REPORT, PUT) **only** to
  `carddav_url`, carrying the contact data, search query or address book
  selector you provided, authenticated with `carddav_username`/`carddav_password`.
  Requests use the User-Agent `dify-plugin-dav/<version>`.
- No analytics, telemetry or external hosts are involved. The plugin itself
  persists nothing.

Your calendars, events, tasks, queries and contact data are subject to the
privacy policies of the CalDAV server configured in `caldav_url` and the
CardDAV server configured in `carddav_url`. WebDAV file access is provided by
the separate `shaba/webdav` datasource plugin with its own privacy policy.
