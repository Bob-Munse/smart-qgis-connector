# api/smart_client.py
# This file TALKS TO THE SMART CONNECT SERVER.
#
# SMART Connect accepts HTTP Basic Auth: every request carries a header like
#     Authorization: Basic <base64 of "username:password">
# Some Connect pages (like query downloads) may instead expect the web-login
# form. If we get the login page back, we log in through the form once and retry.
#
# We send requests through QgsNetworkAccessManager (QGIS's own network layer),
# so any proxy or SSL settings you've set in QGIS are used automatically, and
# login cookies are kept between requests.
#
# The small helper functions at the top don't need QGIS at all, which makes
# them easy to test on their own.

import base64
import re
from urllib.parse import quote, urlencode

# ---------------------------------------------------------------------------
# Addresses on the SMART Connect server. If your server uses different paths,
# change them HERE — nothing else needs to change.
# ---------------------------------------------------------------------------

# Lists the conservation areas this account can see (needs a valid login).
TEST_ENDPOINT = "/server/api/conservationarea/"

# Lists every saved query, grouped by conservation area and folder.
QUERY_TREE_ENDPOINT = "/server/api/query/tree"

# Runs one saved query and returns its results. {uuid} is the query's ID.
QUERY_DATA_ENDPOINT = "/server/connect/query/api/{uuid}"

# Web-login form (used only if Basic Auth isn't accepted for a request).
LOGIN_FORM_ENDPOINT = "/server/j_security_check"

# How long to wait for a query download before giving up (10 minutes).
# QGIS's normal limit is 60 seconds, which is too short for months of patrol tracks.
DOWNLOAD_TIMEOUT_MS = 10 * 60 * 1000

# Which date fields each SMART query type can be filtered on.
# The FIRST one in each list is the default the plugin picks.
DATE_FILTERS_BY_QUERY_TYPE = {
    "patrolquery": ["patrolstart", "patrolend", "waypointlastmodified"],
    "patrolwaypoint": ["waypointdate", "patrolstart", "patrolend", "waypointlastmodified"],
    "patrolobservation": ["waypointdate", "patrolstart", "patrolend", "waypointlastmodified"],
    "patrolsummary": ["patrolstart", "waypointdate", "patrolend", "waypointlastmodified"],
    "patrolgrid": ["patrolstart", "waypointdate", "patrolend", "waypointlastmodified"],
    "observationwaypoint": ["waypointdate", "waypointlastmodified"],
    "observationobservation": ["waypointdate", "waypointlastmodified"],
    "observationsummary": ["waypointdate", "waypointlastmodified"],
    "observationgrid": ["waypointdate", "waypointlastmodified"],
    "surveymission": ["missionstartdate", "missionenddate"],
    "surveymissiontrack": ["missiontrackdate", "missionstartdate", "missionenddate"],
    "surveywaypoint": ["waypointdate", "missionstartdate", "missionenddate", "waypointlastmodified"],
    "surveyobservation": ["waypointdate", "missionstartdate", "missionenddate", "waypointlastmodified"],
    "surveysummary": ["waypointdate", "missionstartdate", "missionenddate", "waypointlastmodified"],
    "surveygrid": ["waypointdate", "missionstartdate", "missionenddate", "waypointlastmodified"],
    "entitywaypoint": ["waypointdate"],
    "entityobservation": ["waypointdate"],
    "entitysummary": ["waypointdate"],
    "entitygrid": ["waypointdate"],
    "assetwaypoint": ["waypointdate", "waypointlastmodified"],
    "assetobservation": ["waypointdate", "waypointlastmodified"],
    "assetsummary": ["waypointdate", "waypointlastmodified"],
    "assetdeploymentsummary": ["assetdeploymentdate"],
    "i2_obs_query": ["waypointdate"],
    "i2_record_query": ["RecordDate"],
    "i2_record_summ_query": ["RecordDate"],
}

# Used when we don't know the query type (e.g. a pasted UUID).
ALL_DATE_FILTERS = sorted({f for filters in DATE_FILTERS_BY_QUERY_TYPE.values() for f in filters})

# Summary queries are tables, not map features, so we ask for CSV instead of GeoJSON.
TABLE_QUERY_TYPES = {k for k in DATE_FILTERS_BY_QUERY_TYPE if k.endswith(("summary", "summ_query"))}

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}"
)


# ---------------------------------------------------------------------------
# Helpers (no QGIS needed)
# ---------------------------------------------------------------------------

def normalize_server_url(url):
    """
    Tidy up what the user typed:
      "example.smartconservationtools.org/"  ->  "https://example.smartconservationtools.org"
    """
    url = (url or "").strip()
    if not url:
        return ""
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    url = url.rstrip("/")
    # People often paste the web-app address; the API lives under the same host.
    if url.lower().endswith("/server"):
        url = url[: -len("/server")]
    return url


def normalize_uuid(text):
    """
    Find a UUID in any text (a bare UUID, one without dashes, or a pasted link)
    and return it in the standard dashed, lower-case form. Returns "" if none.
      "1A2B3C4D00001111222233334444555A" -> "1a2b3c4d-0000-1111-2222-33334444555a"
    """
    match = _UUID_RE.search(text or "")
    if not match:
        return ""
    h = match.group(0).replace("-", "").lower()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def build_auth_header(username, password):
    """Return the value for the Authorization header (as bytes, which Qt expects)."""
    token = base64.b64encode(f"{username}:{password}".encode("utf-8"))
    return b"Basic " + token


def interpret_response(status_code, error_message=""):
    """
    Turn a raw network result into (success, plain-language message).

    status_code   -- the HTTP status number (200, 401, ...), or 0 if no reply arrived
    error_message -- Qt's error text, used when there was no HTTP reply at all
    """
    if status_code == 200:
        return True, "Connected to SMART Connect successfully."
    if status_code == 401:
        return False, "Login failed: the username or password is wrong."
    if status_code == 403:
        return False, "Logged in, but this account isn't allowed to use the API. Ask your SMART Connect admin to check your permissions."
    if status_code == 404:
        return False, (
            "Reached the server, but the address was not found. "
            "Check the Server URL, or the endpoint paths at the top of api/smart_client.py."
        )
    if status_code and status_code >= 500:
        return False, f"The SMART Connect server had an internal error (HTTP {status_code}). Try again later."
    if status_code:
        return False, f"Unexpected reply from the server (HTTP {status_code})."
    # No HTTP status means the request never got a reply.
    detail = f" Details: {error_message}" if error_message else ""
    return False, "Could not reach the server. Check the Server URL and your internet connection." + detail


def looks_like_login_page(body):
    """
    True if the server sent back its HTML login page instead of data.
    We search the WHOLE page: on SMART Connect the login form comes after
    about 10,000 characters of styling, so only checking the start misses it.
    """
    if detect_payload_kind(body) != "html":
        return False          # real data (GeoJSON, CSV, zip...) is never a login page
    page = body.lower()
    return (
        b"j_security_check" in page
        or b"j_username" in page
        or re.search(rb"<title>[^<]*login", page) is not None
    )


def flatten_query_tree(tree, ca_uuid=""):
    """
    The query tree is nested: conservation areas -> folders -> sub-folders -> queries.
    Turn it into a flat list of dicts:
        {"name", "uuid", "type_key", "folder", "ca_uuid", "ca_name"}
    If ca_uuid is given, only queries from that conservation area are kept.
    """
    wanted_ca = normalize_uuid(ca_uuid)
    results = []

    def walk(node, path, ca_name, node_ca):
        node_ca = normalize_uuid(node.get("caUuid") or "") or node_ca
        for item in node.get("items") or []:
            item_ca = normalize_uuid(item.get("caUuid") or "") or node_ca
            if wanted_ca and item_ca and item_ca != wanted_ca:
                continue
            uuid = normalize_uuid(item.get("uuid") or "")
            if not uuid:
                continue
            results.append({
                "name": item.get("name") or "(unnamed query)",
                "uuid": uuid,
                "type_key": (item.get("typeKey") or "").strip(),
                "folder": path,
                "ca_uuid": item_ca,
                "ca_name": ca_name,
            })
        for sub in node.get("subFolders") or []:
            sub_name = sub.get("name") or ""
            walk(sub, f"{path}/{sub_name}" if path else sub_name, ca_name, node_ca)

    for ca_node in tree or []:
        ca_name = ca_node.get("name") or ""
        walk(ca_node, ca_name, ca_name, "")

    results.sort(key=lambda q: (q["folder"].lower(), q["name"].lower()))
    return results


def date_filters_for(type_key):
    """Date filters allowed for this query type (all of them if the type is unknown)."""
    return DATE_FILTERS_BY_QUERY_TYPE.get(type_key, ALL_DATE_FILTERS)


def output_format_for(type_key):
    """'csv' for summary (table) queries, 'geojson' for everything else."""
    return "csv" if type_key in TABLE_QUERY_TYPES else "geojson"


def geometry_kind_for(type_key):
    """
    Roughly what a query type gives back, for the little icon in the query list:
    'table', 'polygon' (grids), 'line' (patrol / mission tracks) or 'point'.
    """
    t = (type_key or "").lower()
    if t in TABLE_QUERY_TYPES or t in ("i2_record_query",):
        return "table"
    if t.endswith("grid"):
        return "polygon"
    if t in ("patrolquery", "surveymission", "surveymissiontrack"):
        return "line"
    if not t:
        return "unknown"
    return "point"


def build_query_data_path(query_uuid, date_filter, start_date, end_date, fmt="geojson", srid=4326):
    """
    Build the path (with ?parameters) that runs one saved query.
    start_date / end_date are "YYYY-MM-DD" strings; the whole of both days is included.
    Pass srid=None to leave the coordinate-system setting out.
    """
    params = {"format": fmt, "date_filter": date_filter}
    if fmt != "csv" and srid:
        params["srid"] = str(srid)
    if start_date:
        params["start_date"] = f"{start_date} 00:00:00"
    if end_date:
        params["end_date"] = f"{end_date} 23:59:59"
    return QUERY_DATA_ENDPOINT.format(uuid=query_uuid) + "?" + urlencode(params, quote_via=quote)


def detect_payload_kind(body):
    """
    Work out what the server sent us, from the first bytes:
      'geojson', 'zip' (zipped shapefile), 'tiff' (raster), 'html' (an error/login page),
      'empty', or 'csv' (any other text).
    """
    data = (body or b"").lstrip()
    # Some servers put an invisible "byte order mark" at the very start of text files.
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:].lstrip()
    if not data:
        return "empty"
    if data[:1] in (b"{", b"["):
        return "geojson"
    if data[:2] == b"PK":
        return "zip"
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if data[:200].lower().startswith((b"<!doctype html", b"<html")) or b"<html" in data[:500].lower():
        return "html"
    return "csv"


def describe_page(body, limit=400):
    """
    Turn a web page the server sent back into a short readable message:
    its <title> plus the start of its visible text, with the HTML tags removed.
    """
    text = (body or b"").decode("utf-8", errors="replace")
    title = re.search(r"<title[^>]*>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)          # drop the tags
    text = re.sub(r"\s+", " ", text).strip()      # squash spaces and newlines
    parts = []
    if title and title.group(1).strip():
        parts.append("Page title: " + re.sub(r"\s+", " ", title.group(1)).strip())
    if text:
        parts.append("Page text: " + (text[:limit] + "…" if len(text) > limit else text))
    return "\n".join(parts) or "(the page was empty)"


def parse_set_cookie(header_value):
    """
    Pull name=value pairs out of a Set-Cookie header (Qt joins several with newlines).
      b"JSESSIONID=abc; Path=/server; HttpOnly" -> {"JSESSIONID": "abc"}
    """
    cookies = {}
    text = header_value.decode("latin-1") if isinstance(header_value, bytes) else (header_value or "")
    for line in text.split("\n"):
        first = line.split(";", 1)[0].strip()
        if "=" in first:
            name, value = first.split("=", 1)
            if name.strip():
                cookies[name.strip()] = value.strip()
    return cookies


# ---------------------------------------------------------------------------
# The client (needs QGIS for the actual network calls)
# ---------------------------------------------------------------------------

class SmartConnectClient:
    """Holds one set of connection details and makes requests with them."""

    def __init__(self, server_url, username, password):
        self.server_url = normalize_server_url(server_url)
        self.username = username
        self.password = password
        # Session cookies the server gives us (e.g. JSESSIONID after the web login).
        # We keep them ourselves and send them with every request.
        self._cookies = {}

    def _request(self, endpoint, accept=b"application/json"):
        from qgis.PyQt.QtCore import QUrl
        from qgis.PyQt.QtNetwork import QNetworkRequest

        request = QNetworkRequest(QUrl(self.server_url + endpoint))
        request.setRawHeader(b"Authorization", build_auth_header(self.username, self.password))
        request.setRawHeader(b"Accept", accept)
        if self._cookies:
            cookie = "; ".join(f"{k}={v}" for k, v in self._cookies.items())
            request.setRawHeader(b"Cookie", cookie.encode("latin-1"))
        # We manage the session cookies ourselves. Tell QGIS not to add cookies from its
        # own store (an old, expired session cookie there would replace our fresh one and
        # the server would answer with its login page), and not to save new ones there.
        request.setAttribute(QNetworkRequest.Attribute.CookieLoadControlAttribute, QNetworkRequest.LoadControl.Manual)
        request.setAttribute(QNetworkRequest.Attribute.CookieSaveControlAttribute, QNetworkRequest.LoadControl.Manual)
        # Don't let QGIS store our replies in its cache (they contain your data).
        request.setAttribute(QNetworkRequest.Attribute.CacheSaveControlAttribute, False)
        return request

    def _remember_cookies(self, reply):
        """Keep every cookie the server set, so the next request carries the session."""
        for name in reply.rawHeaderList():
            if bytes(name).lower() == b"set-cookie":
                self._cookies.update(parse_set_cookie(bytes(reply.rawHeader(name))))

    def _unpack(self, reply):
        from qgis.PyQt.QtNetwork import QNetworkRequest

        self._remember_cookies(reply)
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        status_code = int(status) if status else 0
        return status_code, bytes(reply.content()), reply.errorString()

    def _send_get(self, endpoint, accept, timeout_ms=None, feedback=None):
        """One GET. forceRefresh=True: always ask the server, never reuse a cached answer
        (otherwise you could get old patrol data, or a login could look like it works
        when it no longer does).

        timeout_ms temporarily raises QGIS's network time limit for this one request.
        feedback (a QgsFeedback) lets the Cancel button stop the download."""
        from qgis.core import QgsNetworkAccessManager

        old_timeout = QgsNetworkAccessManager.timeout()
        if timeout_ms:
            QgsNetworkAccessManager.setTimeout(timeout_ms)
        try:
            reply = QgsNetworkAccessManager.instance().blockingGet(
                self._request(endpoint, accept), forceRefresh=True, feedback=feedback
            )
        finally:
            QgsNetworkAccessManager.setTimeout(old_timeout)  # always put the normal limit back
        return self._unpack(reply)

    def _form_login(self):
        """
        Sign in through Connect's web login form, exactly like a browser does:
          - we already hold the session cookie the server gave us with its login page,
          - we POST the username and password to /server/j_security_check,
          - the server answers "303 redirect" plus a NEW session cookie.

        We send this request ourselves and wait for it with a small event loop,
        instead of QGIS's blockingPost: blockingPost tries to follow the redirect,
        fails on the short address SMART Connect gives ("Protocol is unknown"),
        and throws away the reply — and the new cookie with it.
        """
        from qgis.PyQt.QtCore import QEventLoop, QTimer
        from qgis.PyQt.QtNetwork import QNetworkRequest
        from qgis.core import QgsNetworkAccessManager

        request = self._request(LOGIN_FORM_ENDPOINT, accept=b"text/html")
        request.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/x-www-form-urlencoded")
        # Don't follow the redirect — we only need this reply's cookie.
        request.setAttribute(
            QNetworkRequest.Attribute.RedirectPolicyAttribute,
            QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
        )
        form = urlencode({"j_username": self.username, "j_password": self.password}).encode("utf-8")

        reply = QgsNetworkAccessManager.instance().post(request, form)
        loop = QEventLoop()
        reply.finished.connect(loop.quit)
        QTimer.singleShot(60 * 1000, loop.quit)   # give up after 60 seconds
        if not reply.isFinished():
            loop.exec()                            # wait here until the reply arrives
        if reply.isFinished():
            self._remember_cookies(reply)
        else:
            reply.abort()
        reply.deleteLater()

    def get(self, endpoint, accept=b"application/json", timeout_ms=None, feedback=None):
        """
        Send a GET request to server_url + endpoint.
        Returns (status_code, body_bytes, error_message).

        If the server answers with its login page instead of data (no session yet,
        or the session expired), we sign in through the web form and try once more.
        If it STILL sends the login page, the username or password was rejected.

        This waits for the answer before returning (a "blocking" call).
        """
        status_code, body, error = self._send_get(endpoint, accept, timeout_ms, feedback)
        if feedback is not None and feedback.isCanceled():
            return 0, b"", "Cancelled"

        if status_code in (401, 302) or looks_like_login_page(body):
            self._form_login()
            status_code, body, error = self._send_get(endpoint, accept, timeout_ms, feedback)
            if looks_like_login_page(body):
                # Report it as a failed login (401), which gives a clear message.
                return 401, body, "The server rejected the sign-in."

        return status_code, body, error

    def test_connection(self):
        """Check that the server is reachable and the login works. Returns (success, message)."""
        if not self.server_url:
            return False, "Please enter the Server URL."
        if not self.username or not self.password:
            return False, "Please enter both username and password."
        status_code, _body, error = self.get(TEST_ENDPOINT)
        return interpret_response(status_code, error)

    def list_queries(self):
        """
        Fetch every saved query this account can run, from all conservation areas.
        (The Import window lets you pick which area to show.)
        Returns (queries, error_message). On success error_message is "".
        """
        import json

        status_code, body, error = self.get(QUERY_TREE_ENDPOINT)
        if status_code != 200:
            return [], interpret_response(status_code, error)[1]
        if looks_like_login_page(body):
            return [], "The server asked for a login again. Check your username and password in Connection Settings."
        try:
            tree = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return [], "The server's list of queries wasn't in the expected format."
        return flatten_query_tree(tree), ""

    def download_query(self, query_uuid, date_filter, start_date, end_date, type_key="", feedback=None):
        """
        Run a saved query on the server and return (kind, body, error_message, log).

        kind  -- what we got: 'geojson', 'zip', 'csv', 'empty'... or "" if every try failed
        log   -- one line per attempt, for the Details box

        Map queries are tried in up to three ways, stopping at the first that works:
          1. GeoJSON with srid=4326
          2. GeoJSON without srid (some servers reject that setting)
          3. a zipped shapefile
        Summary queries are fetched once, as a CSV table.
        """
        if output_format_for(type_key) == "csv":
            attempts = [("CSV table", "csv", None)]
            good_kinds = ("csv", "empty")
        else:
            attempts = [
                ("GeoJSON", "geojson", 4326),
                ("GeoJSON without srid", "geojson", None),
                ("Zipped shapefile", "shp", 4326),
            ]
            good_kinds = ("geojson", "zip", "tiff", "empty")

        log = []
        last_body, last_error = b"", ""
        for label, fmt, srid in attempts:
            path = build_query_data_path(query_uuid, date_filter, start_date, end_date, fmt, srid)
            if feedback is not None and feedback.isCanceled():
                return "", b"", "Import cancelled.", log + ["Cancelled by user."]
            status_code, body, error = self.get(path, accept=b"*/*", timeout_ms=DOWNLOAD_TIMEOUT_MS, feedback=feedback)
            kind = detect_payload_kind(body) if status_code == 200 else ""
            log.append(
                f"{label}: HTTP {status_code or 'no reply'}, {len(body):,} bytes"
                + (f", looks like {kind}" if kind else "")
                + (f" ({error})" if status_code == 0 and error else "")
            )

            if status_code == 200 and kind in good_kinds:
                return kind, body, "", log          # success — stop trying

            last_body = body
            if status_code == 200 and kind == "html":
                last_error = "The server sent a web page instead of data."
            elif status_code == 200:
                last_error = "The server sent something that isn't map data."
            else:
                last_error = interpret_response(status_code, error)[1]
                # No point trying other formats if the login or the query itself is the problem.
                if status_code in (401, 403, 404):
                    break

        if len(attempts) > 1:
            last_error = last_error.rstrip(".") + f" (tried {len(log)} ways)."
        return "", last_body, last_error, log
