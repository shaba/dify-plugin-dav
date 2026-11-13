"""Minimal WebDAV client: PROPFIND listing/stat, GET download, write, delete,
mkdir, move and copy.

Works against any RFC 4918 WebDAV server (Nextcloud, ownCloud, Apache mod_dav,
sabre/dav, ...). Uses HTTP Basic auth.
"""

from __future__ import annotations

import posixpath
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import requests

from .errors import WebDAVError, redact_credentials
from .parser import WebDAVResource, parse_propfind

PROPFIND_BODY = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<d:propfind xmlns:d="DAV:"><d:prop>'
    "<d:resourcetype/>"
    "<d:getcontentlength/>"
    "<d:getcontenttype/>"
    "<d:getlastmodified/>"
    "</d:prop></d:propfind>"
)

__all__ = ["WebDAVClient", "WebDAVError", "redact_credentials"]


# Upper bound on a single download buffered into memory. The plugin runner's
# memory budget (manifest resource.memory) is 256 MiB; cap a single file well
# under that so one oversized share entry cannot OOM the runner.
DEFAULT_MAX_DOWNLOAD_BYTES = 200 * 1024 * 1024

_AUTH_ERROR = "WebDAV authentication failed (check username/password)"


class WebDAVClient:
    """A thin WebDAV client bound to a base URL and Basic-auth credentials.

    ``base_url`` is the WebDAV endpoint, e.g.
    ``https://example.com/remote.php/dav/files/alice/``.
    """

    def __init__(
        self,
        base_url: str,
        username: str = "",
        password: str = "",
        *,
        timeout: int = 30,
        session: requests.Session | None = None,
        max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
    ) -> None:
        if not base_url:
            raise WebDAVError("base_url is required")
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.max_download_bytes = max_download_bytes
        self._session = session or requests.Session()
        if username or password:
            self._session.auth = (username, password)

        split = urlsplit(self.base_url)
        # Only HTTP(S) WebDAV endpoints are supported; reject other schemes
        # (file://, ftp://, ...) so a misconfigured base_url cannot redirect
        # requests away from the intended transport.
        if split.scheme not in ("http", "https"):
            raise WebDAVError("base_url must use http or https scheme")
        if not split.netloc:
            raise WebDAVError("base_url must include a host")
        self._scheme = split.scheme
        self._netloc = split.netloc
        # URL-decoded path of the base endpoint, used to resolve relative paths.
        self.base_path = split.path or "/"

    # -- URL helpers ---------------------------------------------------------

    def _url_for_path(self, path: str) -> str:
        """Build an absolute URL from a URL-decoded server path.

        Paths reaching this method are always URL-decoded (PROPFIND hrefs are
        decoded by the parser, and base/relative paths are plain strings), so we
        percent-encode unconditionally. Branching on ``"%" in path`` would mis-
        handle a filename that legitimately contains a literal percent sign
        (e.g. ``50%.txt``), leaving an invalid, unencoded ``%`` in the URL.
        """
        if not path:
            path = self.base_path
        path = quote(path, safe="/")
        return urlunsplit((self._scheme, self._netloc, path, "", ""))

    def _resolve(self, rel: str | None) -> str:
        """Resolve a folder path relative to the base endpoint.

        ``rel`` is a path under the base (e.g. ``"docs/"``) or an absolute
        server path, or empty/None for the base itself.
        """
        rel = (rel or "").strip()
        if not rel:
            return self.base_url
        if rel.startswith("/"):
            return self._url_for_path(rel)
        return self._url_for_path(self.base_path.rstrip("/") + "/" + rel)

    def _safe_path(self, rel: str | None) -> str:
        """Resolve ``rel`` to a URL-decoded server path confined to base_path.

        Relative paths resolve under the base endpoint; absolute server paths
        are accepted as-is. The candidate is normalised (``.``/``..``
        segments resolved) and rejected with WebDAVError when it escapes
        ``base_path``, so a crafted path like ``../../etc/passwd`` cannot
        reach outside the configured endpoint.
        """
        rel = (rel or "").strip()
        if rel.startswith("/"):
            candidate = rel
        elif rel:
            candidate = self.base_path.rstrip("/") + "/" + rel
        else:
            candidate = self.base_path
        normalized = posixpath.normpath(candidate)
        if normalized == ".":
            normalized = "/"
        base = posixpath.normpath(self.base_path)
        if base == "/":
            inside = normalized.startswith("/")
        else:
            inside = normalized == base or normalized.startswith(base + "/")
        if not inside:
            raise WebDAVError(
                f"path escapes the configured base path: "
                f"{redact_credentials(rel)}"
            )
        return normalized

    def _safe_url(self, rel: str | None) -> str:
        """Absolute URL for a user-supplied path, validated by _safe_path."""
        return self._url_for_path(self._safe_path(rel))

    def _destination_url(self, dst: str) -> str:
        """Absolute URL for a MOVE/COPY Destination header.

        The destination must land on the same scheme://netloc as base_url; a
        cross-server Destination would make the server (or a redirect) touch a
        host the credentials were never meant for.
        """
        dst = (dst or "").strip()
        split = urlsplit(dst)
        if split.scheme or split.netloc:
            if (split.scheme, split.netloc) != (self._scheme, self._netloc):
                raise WebDAVError(
                    f"destination must be on the same server: "
                    f"{redact_credentials(dst)}"
                )
            return self._url_for_path(self._safe_path(unquote(split.path)))
        return self._safe_url(dst)

    # -- Operations ----------------------------------------------------------

    def check(self) -> None:
        """Validate connectivity and credentials with a Depth: 0 PROPFIND."""
        try:
            resp = self._session.request(
                "PROPFIND",
                self.base_url,
                data=PROPFIND_BODY,
                headers={"Depth": "0", "Content-Type": "application/xml"},
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise WebDAVError(
                f"WebDAV connection failed: {redact_credentials(exc)}"
            ) from exc
        if resp.status_code in (401, 403):
            raise WebDAVError(_AUTH_ERROR)
        if resp.status_code == 404:
            raise WebDAVError("WebDAV base_url not found (404)")
        if resp.status_code not in (207, 200):
            raise WebDAVError(
                f"Unexpected WebDAV response {resp.status_code} for base_url"
            )

    def list_dir(self, path: str | None = None) -> list[WebDAVResource]:
        """List children of a collection (Depth: 1 PROPFIND)."""
        safe = self._safe_path(path)
        if not safe.endswith("/"):
            safe += "/"
        url = self._url_for_path(safe)
        try:
            resp = self._session.request(
                "PROPFIND",
                url,
                data=PROPFIND_BODY,
                headers={"Depth": "1", "Content-Type": "application/xml"},
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise WebDAVError(
                f"WebDAV PROPFIND failed: {redact_credentials(exc)}"
            ) from exc
        if resp.status_code in (401, 403):
            raise WebDAVError(_AUTH_ERROR)
        if resp.status_code not in (207, 200):
            raise WebDAVError(
                f"WebDAV PROPFIND returned {resp.status_code} "
                f"for {redact_credentials(path or '/')}"
            )
        base_path = urlsplit(url).path
        return parse_propfind(resp.content, unquote(base_path))

    def stat(self, path: str) -> WebDAVResource:
        """Return the resource entry itself (Depth: 0 PROPFIND)."""
        url = self._safe_url(path)
        try:
            resp = self._session.request(
                "PROPFIND",
                url,
                data=PROPFIND_BODY,
                headers={"Depth": "0", "Content-Type": "application/xml"},
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise WebDAVError(
                f"WebDAV PROPFIND failed: {redact_credentials(exc)}"
            ) from exc
        if resp.status_code in (401, 403):
            raise WebDAVError(_AUTH_ERROR)
        if resp.status_code == 404:
            raise WebDAVError(
                f"WebDAV resource not found (404): "
                f"{redact_credentials(path)}"
            )
        if resp.status_code not in (207, 200):
            raise WebDAVError(
                f"WebDAV PROPFIND returned {resp.status_code} "
                f"for {redact_credentials(path)}"
            )
        # Depth: 0 returns the resource itself; pass base_path="" so the
        # parser keeps it instead of skipping it as the queried collection.
        entries = parse_propfind(resp.content, "")
        if not entries:
            raise WebDAVError(
                f"WebDAV resource not found: {redact_credentials(path)}"
            )
        return entries[0]

    def download(self, path: str) -> tuple[bytes, str]:
        """GET a file by its server path; return ``(content, content_type)``.

        A trailing slash marks a collection (folder); GETting one yields an HTML
        index or a 405 rather than file bytes, so reject it up front with a clear
        error instead of ingesting bogus content.
        """
        if path.endswith("/"):
            raise WebDAVError(
                f"Cannot download a folder: {redact_credentials(path)}"
            )
        url = self._safe_url(path)
        try:
            resp = self._session.get(
                url, timeout=self.timeout, allow_redirects=False, stream=True
            )
        except requests.RequestException as exc:
            raise WebDAVError(
                f"WebDAV GET failed: {redact_credentials(exc)}"
            ) from exc
        if resp.status_code in (401, 403):
            resp.close()
            raise WebDAVError(_AUTH_ERROR)
        if resp.status_code != 200:
            resp.close()
            raise WebDAVError(
                f"WebDAV GET returned {resp.status_code} "
                f"for {redact_credentials(path)}"
            )
        # stream=True keeps the body unbuffered until read, so an oversized
        # file is rejected on its declared length before any download, and
        # iter_content aborts early when the server streams past the cap.
        # Callers buffer the accepted bytes in memory; the limit stays well
        # under the manifest memory budget.
        declared = resp.headers.get("Content-Length")
        if declared is not None:
            try:
                if int(declared) > self.max_download_bytes:
                    resp.close()
                    raise WebDAVError(
                        f"File exceeds maximum download size "
                        f"({self.max_download_bytes} bytes): "
                        f"{redact_credentials(path)}"
                    )
            except ValueError:
                pass
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in resp.iter_content(chunk_size=65536):
                total += len(chunk)
                if total > self.max_download_bytes:
                    raise WebDAVError(
                        f"File exceeds maximum download size "
                        f"({self.max_download_bytes} bytes): "
                        f"{redact_credentials(path)}"
                    )
                chunks.append(chunk)
        except requests.RequestException as exc:
            raise WebDAVError(
                f"WebDAV GET failed: {redact_credentials(exc)}"
            ) from exc
        finally:
            resp.close()
        content = b"".join(chunks)
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        return content, content_type

    def write(
        self,
        path: str,
        data: bytes,
        content_type: str = "text/plain; charset=utf-8",
        overwrite: bool = False,
    ) -> None:
        """PUT file bytes at ``path``, refusing to clobber without overwrite."""
        if path.strip().endswith("/"):
            raise WebDAVError(
                f"Cannot write a file to a folder path: "
                f"{redact_credentials(path)}"
            )
        url = self._safe_url(path)
        try:
            head = self._session.request(
                "HEAD", url, timeout=self.timeout, allow_redirects=False
            )
        except requests.RequestException as exc:
            raise WebDAVError(
                f"WebDAV HEAD failed: {redact_credentials(exc)}"
            ) from exc
        if head.status_code in (401, 403):
            raise WebDAVError(_AUTH_ERROR)
        if head.status_code == 200 and not overwrite:
            raise WebDAVError(
                f"{redact_credentials(path)} already exists "
                f"(pass overwrite=true)"
            )
        try:
            resp = self._session.request(
                "PUT",
                url,
                data=data,
                headers={"Content-Type": content_type},
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise WebDAVError(
                f"WebDAV PUT failed: {redact_credentials(exc)}"
            ) from exc
        if resp.status_code in (401, 403):
            raise WebDAVError(_AUTH_ERROR)
        if resp.status_code not in (201, 204, 200):
            raise WebDAVError(
                f"WebDAV PUT returned {resp.status_code} "
                f"for {redact_credentials(path)}"
            )

    def delete(self, path: str, recursive: bool = False) -> None:
        """DELETE a file or collection.

        A non-recursive delete of a collection that still has children is
        refused up front (a recursive delete of a large tree is destructive
        enough to require an explicit flag).
        """
        url = self._safe_url(path)
        if not recursive:
            entry = self.stat(path)
            if entry.is_dir and self.list_dir(path):
                raise WebDAVError(
                    f"{redact_credentials(path)} is not empty "
                    f"(pass recursive=true)"
                )
        try:
            resp = self._session.request(
                "DELETE", url, timeout=self.timeout, allow_redirects=False
            )
        except requests.RequestException as exc:
            raise WebDAVError(
                f"WebDAV DELETE failed: {redact_credentials(exc)}"
            ) from exc
        if resp.status_code in (401, 403):
            raise WebDAVError(_AUTH_ERROR)
        if resp.status_code not in (204, 207):
            raise WebDAVError(
                f"WebDAV DELETE returned {resp.status_code} "
                f"for {redact_credentials(path)}"
            )

    def mkdir(self, path: str, recursive: bool = False) -> None:
        """MKCOL a collection; with recursive, create missing parents."""
        safe = self._safe_path(path)
        if not safe.endswith("/"):
            safe += "/"
        url = self._url_for_path(safe)

        def mkcol(target: str) -> requests.Response:
            return self._session.request(
                "MKCOL", target, timeout=self.timeout, allow_redirects=False
            )

        try:
            resp = mkcol(url)
        except requests.RequestException as exc:
            raise WebDAVError(
                f"WebDAV MKCOL failed: {redact_credentials(exc)}"
            ) from exc
        if resp.status_code == 201:
            return
        if resp.status_code in (401, 403):
            raise WebDAVError(_AUTH_ERROR)
        if resp.status_code == 405:
            raise WebDAVError(
                f"{redact_credentials(path)} already exists"
            )
        if resp.status_code == 409 and recursive:
            # A parent collection is missing; create the chain iteratively,
            # tolerating segments that already exist (405).
            base = posixpath.normpath(self.base_path)
            prefix = "" if base == "/" else base
            rel = safe[len(prefix):].strip("/") if prefix else safe.strip("/")
            segments = [seg for seg in rel.split("/") if seg]
            if segments:
                current = prefix
                for seg in segments:
                    current = current + "/" + seg
                    try:
                        parent_resp = mkcol(self._url_for_path(current + "/"))
                    except requests.RequestException as exc:
                        raise WebDAVError(
                            f"WebDAV MKCOL failed: {redact_credentials(exc)}"
                        ) from exc
                    if parent_resp.status_code not in (201, 405):
                        raise WebDAVError(
                            f"WebDAV MKCOL returned {parent_resp.status_code} "
                            f"for {redact_credentials(current)}"
                        )
                return
        raise WebDAVError(
            f"WebDAV MKCOL returned {resp.status_code} "
            f"for {redact_credentials(path)}"
        )

    def move(self, src: str, dst: str) -> None:
        """MOVE ``src`` to ``dst`` (same server only)."""
        self._move_copy("MOVE", src, dst, overwrite=True)

    def copy(self, src: str, dst: str, overwrite: bool = False) -> None:
        """COPY ``src`` to ``dst`` (same server only)."""
        self._move_copy("COPY", src, dst, overwrite=overwrite)

    def _move_copy(
        self, method: str, src: str, dst: str, *, overwrite: bool
    ) -> None:
        src_url = self._safe_url(src)
        dst_url = self._destination_url(dst)
        # The Destination header must be an absolute URL on the same
        # scheme://netloc as base_url; _destination_url enforces that.
        dst_split = urlsplit(dst_url)
        if (dst_split.scheme, dst_split.netloc) != (self._scheme, self._netloc):
            raise WebDAVError(
                f"destination must be on the same server: "
                f"{redact_credentials(dst)}"
            )
        try:
            resp = self._session.request(
                method,
                src_url,
                headers={
                    "Destination": dst_url,
                    "Overwrite": "T" if overwrite else "F",
                },
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise WebDAVError(
                f"WebDAV {method} failed: {redact_credentials(exc)}"
            ) from exc
        if resp.status_code in (401, 403):
            raise WebDAVError(_AUTH_ERROR)
        if resp.status_code == 412:
            raise WebDAVError(
                f"{redact_credentials(dst)}: destination exists (Overwrite: F)"
            )
        if resp.status_code not in (201, 204, 207):
            raise WebDAVError(
                f"WebDAV {method} returned {resp.status_code} "
                f"for {redact_credentials(src)}"
            )
