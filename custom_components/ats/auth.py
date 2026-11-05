"""ATS form login. Keep credentials and cookies out of all logs."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

import aiohttp


class ATSLoginError(Exception):
    """A sanitized login or network error (not necessarily invalid credentials)."""


class ATSDiscoveryError(ATSLoginError):
    """The authenticated page did not expose the expected ATS identifiers."""


class ATSInvalidCredentials(ATSLoginError):
    """The portal explicitly rejected the supplied username/password."""


class _HiddenFormFields(HTMLParser):
    """Extract hidden values from the current ASP.NET login page."""

    def __init__(self) -> None:
        super().__init__()
        self.fields: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "input":
            return
        values = {key.lower(): value for key, value in attrs if key}
        name = values.get("name")
        if name and (values.get("type") or "").lower() == "hidden":
            self.fields[name] = values.get("value") or ""


async def async_login(
    session: aiohttp.ClientSession,
    base_url: str,
    username: str,
    password: str,
) -> None:
    """Log in with a fresh cookie jar using the observed ASP.NET form.

    The GET collects anti-CSRF and viewstate fields for this exact session.
    The POST deliberately does not follow redirects or log response bodies.
    """
    if not username or not password:
        raise ATSInvalidCredentials("credenziali ATS mancanti")

    login_page = urljoin(base_url.rstrip("/") + "/", "Login.aspx")
    login_post = urljoin(base_url.rstrip("/") + "/", "login.aspx")
    session.cookie_jar.clear()
    try:
        async with session.get(login_page, allow_redirects=False) as response:
            if response.status != 200:
                raise ATSLoginError("pagina di login ATS non disponibile")
            document = await response.text()
        parser = _HiddenFormFields()
        parser.feed(document)
        fields = parser.fields
        if not fields.get("__VIEWSTATE") or not fields.get("__AntiXsrfToken"):
            raise ATSLoginError("campi antifalsificazione ATS mancanti")
        data = {
            **fields,
            "ReturnUrl": "/",
            "username": username,
            "password": password,
            "spidId": fields.get("spidId", ""),
        }
        async with session.post(
            login_post,
            data=data,
            headers={"Origin": base_url.rstrip("/"), "Referer": login_page},
            allow_redirects=False,
        ) as response:
            if response.status in (200, 401, 403):
                # The login form was returned again or the credentials were denied.
                raise ATSInvalidCredentials("credenziali ATS non accettate")
            if response.status not in (302, 303) or ".ASPNETAUTH" not in response.cookies:
                # Do not assume an unexpected redirect is a password error.
                raise ATSLoginError("procedura di accesso ATS cambiata")
    except ATSLoginError:
        session.cookie_jar.clear()
        raise
    except (aiohttp.ClientError, TimeoutError, UnicodeError, ValueError) as err:
        session.cookie_jar.clear()
        # Never include err text: it may contain private URLs or form data.
        raise ATSLoginError("errore di rete durante il login ATS") from None


# ---------------------------------------------------------------------------
# Automatic account discovery.
#
# After a successful login the portal renders every authenticated page with an
# inline ``sol.conf`` object that already contains the session token and the
# customer code. This is the verified, robust source for both values; the
# ``sol-<sid>-at`` / ``-cs`` cookies are HttpOnly (not reliably reusable) and
# are therefore NOT used as the primary source.
#
# Verified portal shapes:
#   solUserAT: '<uuid>'            -> session token (the "-at" segment)
#   solUserCS: 'C<digits>'         -> customer code (the "-cs" value)
# ---------------------------------------------------------------------------

# The AT is a bearer-style credential embedded in the API path: never log it.
_SOL_AT_RE = re.compile(r"solUserAT\s*:\s*'([^']*)'")
_SOL_CS_RE = re.compile(r"solUserCS\s*:\s*'([^']*)'")

_UUID_RE = re.compile(
    r"\A[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\Z"
)
_CUSTOMER_RE = re.compile(r"\AC\d{3,}\Z")

# A whole UUID path segment, used to substitute a fresh token into a legacy
# manual path. It never matches a customer or meter identifier.
_SESSION_UUID_SEGMENT_RE = re.compile(
    r"(?<=/)[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}(?=/|\?|$)"
)

_WEBAPI_PREFIX = "/webapi/api/v1/"


def parse_sol_conf_identifiers(document: str) -> tuple[str, str]:
    """Extract and validate (session_token, customer_code) from page HTML.

    Raises ATSDiscoveryError if either value is missing or malformed. The
    document and the parsed token are never included in the error text.
    """
    at_match = _SOL_AT_RE.search(document or "")
    cs_match = _SOL_CS_RE.search(document or "")
    session_token = (at_match.group(1).strip() if at_match else "")
    customer_code = (cs_match.group(1).strip() if cs_match else "")
    if not _UUID_RE.match(session_token):
        raise ATSDiscoveryError("token di sessione ATS non trovato nella pagina utente")
    if not _CUSTOMER_RE.match(customer_code):
        raise ATSDiscoveryError("codice cliente ATS non trovato nella pagina utente")
    return session_token, customer_code


async def async_discover_identifiers(
    session: aiohttp.ClientSession,
    base_url: str,
) -> tuple[str, str]:
    """Load the authenticated home page and return (session_token, customer_code).

    Must be called on a session that already holds a valid ATS login. Does not
    follow redirects: an unauthenticated session is redirected to the login
    page, which is reported as a discovery failure rather than being parsed.
    """
    home = urljoin(base_url.rstrip("/") + "/", "index.aspx")
    try:
        async with session.get(home, allow_redirects=False) as response:
            if response.status != 200:
                raise ATSDiscoveryError("pagina utente ATS non disponibile")
            document = await response.text()
    except ATSDiscoveryError:
        raise
    except (aiohttp.ClientError, TimeoutError, UnicodeError, ValueError):
        # Never include exception text: it may contain private URLs.
        raise ATSDiscoveryError("errore di rete durante la scoperta ATS") from None
    return parse_sol_conf_identifiers(document)


# ---------------------------------------------------------------------------
# API path construction (pure helpers, no Home Assistant dependency).
# ---------------------------------------------------------------------------

def build_supply_path(session_token: str, customer_code: str) -> str:
    """All supplies (active and ceased): .../supply-light/{AT}/{CS}/1/."""
    return f"{_WEBAPI_PREFIX}supply-light/{session_token}/{customer_code}/1/"


def build_invoice_path(session_token: str, date_from: str, date_to: str) -> str:
    """All invoices across every supply: .../invoice/{AT}/-1/{from}/{to}/.

    v1 is used (not v1.1) so the response keeps ``PdfExist``, which the
    sensors expose as ``pdf_disponibile``.
    """
    return f"{_WEBAPI_PREFIX}invoice/{session_token}/-1/{date_from}/{date_to}/"


def build_reading_path(session_token: str, date_from: str, date_to: str) -> str:
    """All readings across every supply: .../reading-base/{AT}/-1/{from}/{to}/."""
    return f"{_WEBAPI_PREFIX}reading-base/{session_token}/-1/{date_from}/{date_to}/"


def substitute_session_token(path: str, session_token: str) -> str:
    """Put a fresh token into a legacy manual path.

    Replaces a single ``{session_uuid}`` placeholder or a single whole-UUID
    path segment. Raises ATSLoginError on an ambiguous or tokenless path so a
    stale token is never silently reused.
    """
    if "{session_uuid}" in path:
        if path.count("{session_uuid}") != 1:
            raise ATSLoginError("percorso ATS con placeholder ambigui")
        return path.replace("{session_uuid}", session_token)
    matches = _SESSION_UUID_SEGMENT_RE.findall(path)
    if len(matches) != 1:
        raise ATSLoginError("percorso ATS con identificativi ambigui")
    return _SESSION_UUID_SEGMENT_RE.sub(session_token, path, count=1)


def path_has_session_token(path: str) -> bool:
    """True if a manual path carries a placeholder or a UUID segment to renew."""
    return "{session_uuid}" in path or bool(_SESSION_UUID_SEGMENT_RE.search(path))


# A legacy manual invoice path ends with /{YYYYMMDD}/{YYYYMMDD}/: keep the
# tested history start and move the end to "today".
_INVOICE_END_DATE_RE = re.compile(r"/\d{8}/(?P<end>\d{8})/?$")

MODE_AUTO = "auto"
MODE_CREDENTIALS = "credentials"
MODE_COOKIE = "cookie"

_LABELS = ("utenze", "fatture", "letture")


def rewrite_invoice_end_date(invoice_path: str, date_to: str) -> str:
    """Move the trailing end date of a manual invoice path to ``date_to``."""
    match = _INVOICE_END_DATE_RE.search(invoice_path)
    if not match:
        return invoice_path
    return invoice_path[: match.start("end")] + date_to + invoice_path[match.end("end"):]


def resolve_api_url(
    label: str,
    *,
    mode: str,
    session_token: str | None,
    customer_code: str | None,
    supply_path: str = "",
    invoice_path: str = "",
    reading_path: str = "",
    invoice_from: str = "00000000",
    invoice_to: str = "00000000",
    reading_from: str = "00000000",
    reading_to: str = "00000000",
) -> str | None:
    """Return the request path for ``label`` given the running mode.

    Pure and side-effect free, so the whole routing matrix is unit-tested
    offline. Returns None when a label is not configured (e.g. no readings in
    legacy cookie mode). Raises ATSLoginError for an unknown label/mode or a
    credentials mode without a current session token.
    """
    if label not in _LABELS:
        raise ATSLoginError(f"richiesta ATS sconosciuta: {label}")

    if mode == MODE_AUTO:
        if not session_token or not customer_code:
            raise ATSLoginError("ATS: identificativi di sessione non disponibili")
        if label == "utenze":
            return build_supply_path(session_token, customer_code)
        if label == "fatture":
            return build_invoice_path(session_token, invoice_from, invoice_to)
        return build_reading_path(session_token, reading_from, reading_to)

    if mode == MODE_CREDENTIALS:
        if not session_token:
            raise ATSLoginError("ATS: identificativo sessione corrente non disponibile")
        if label == "utenze":
            return _apply_token(supply_path, session_token)
        if label == "fatture":
            resolved = _apply_token(invoice_path, session_token)
            return rewrite_invoice_end_date(resolved, invoice_to)
        if reading_path:
            return _apply_token(reading_path, session_token)
        return build_reading_path(session_token, reading_from, reading_to)

    if mode == MODE_COOKIE:
        if label == "utenze":
            return supply_path
        if label == "fatture":
            return invoice_path
        return reading_path or None

    raise ATSLoginError(f"modalità ATS sconosciuta: {mode}")


def _apply_token(path: str, session_token: str) -> str:
    """Substitute the token only when the path actually carries one."""
    if path_has_session_token(path):
        return substitute_session_token(path, session_token)
    return path
