"""ATS form login. Keep credentials and cookies out of all logs."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin

import aiohttp


class ATSLoginError(Exception):
    """A sanitized login or network error (not necessarily invalid credentials)."""


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
