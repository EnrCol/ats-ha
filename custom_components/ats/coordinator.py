from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from urllib.parse import urljoin

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .auth import (
    MODE_AUTO,
    MODE_COOKIE,
    MODE_CREDENTIALS,
    ATSDiscoveryError,
    ATSInvalidCredentials,
    ATSLoginError,
    async_discover_identifiers,
    async_login,
    path_has_session_token,
    resolve_api_url,
)

_LOGGER = logging.getLogger(__name__)

# The authenticated portal requests roughly the preceding year of readings.
_READING_WINDOW_DAYS = 365


def decide_mode(username: str | None, password: str | None, supply_path: str) -> str:
    """Pick the running mode from the stored configuration.

    - auto:        credentials, no manual supply path -> self-discovery
    - credentials: credentials + manual paths (early beta installs)
    - cookie:      legacy manual cookie + manual paths
    """
    if username and password:
        return MODE_AUTO if not supply_path else MODE_CREDENTIALS
    return MODE_COOKIE


def _as_list(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        for key in ("items", "data", "result", "results", "Items", "Data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    return []


def extract_supply_numbers(supplies: list[dict]) -> list[str]:
    """Return the real SupplyNo values from a supply-light payload.

    Identifiers are read only from the ``SupplyNo`` field; they are never
    inferred from names or addresses. Order is preserved and duplicates are
    dropped.
    """
    numbers: list[str] = []
    for supply in supplies:
        number = supply.get("SupplyNo")
        if isinstance(number, str) and number.strip() and number not in numbers:
            numbers.append(number.strip())
    return numbers


class ATSCoordinator(DataUpdateCoordinator):
    def __init__(
        self,
        hass: HomeAssistant,
        base_url: str,
        supply_path: str,
        invoice_path: str,
        reading_path: str,
        cookie: str,
        update_interval: timedelta,
        username: str | None = None,
        password: str | None = None,
        config_entry: ConfigEntry | None = None,
    ) -> None:
        self.base_url = base_url
        self.supply_path = supply_path
        self.invoice_path = invoice_path
        self.reading_path = reading_path
        self.cookie = cookie
        self.username = username
        self.password = password

        # Mode is decided once from the stored configuration.
        self.mode = decide_mode(username, password, supply_path)

        self._authenticated = False
        self._session: aiohttp.ClientSession | None = None
        # Session token and customer code, refreshed on every login. Never
        # logged: the token is an access credential embedded in the API path.
        self._session_token: str | None = None
        self._customer_code: str | None = None
        # config_entry is required by DataUpdateCoordinator from HA 2026.8;
        # passing it is accepted on earlier versions too (keyword since 2024.8).
        super().__init__(
            hass,
            _LOGGER,
            name="Alto Trevigiano Servizi",
            update_interval=update_interval,
            config_entry=config_entry,
        )

    @property
    def uses_credentials(self) -> bool:
        return self.mode in (MODE_AUTO, MODE_CREDENTIALS)

    async def _login(self) -> None:
        """Log in and refresh the session token (and customer code in auto mode).

        The token/customer are always taken from the authenticated page's
        ``sol.conf`` (verified, robust), never from the HttpOnly cookie jar.
        """
        if self._session is None or not self.username or not self.password:
            raise UpdateFailed("ATS: credenziali non configurate")
        self._authenticated = False
        self._session_token = None
        self._customer_code = None
        try:
            await async_login(self._session, self.base_url, self.username, self.password)
        except ATSInvalidCredentials:
            raise ConfigEntryAuthFailed("ATS: credenziali non accettate") from None
        except ATSLoginError as err:
            # ATSLoginError contains only short, sanitized messages.
            diagnostic = f"ATS login: {err}"
            _LOGGER.warning("%s", diagnostic)
            raise UpdateFailed(diagnostic) from None

        # Auto mode needs both token and customer code; credentials mode with
        # manual paths only needs a fresh token when a path carries one.
        needs_discovery = self.mode == MODE_AUTO or (
            self.mode == MODE_CREDENTIALS and self._credentials_paths_need_token()
        )
        if needs_discovery:
            try:
                token, customer = await async_discover_identifiers(
                    self._session, self.base_url
                )
            except ATSDiscoveryError as err:
                diagnostic = f"ATS discovery: {err}"
                _LOGGER.warning("%s", diagnostic)
                raise UpdateFailed(diagnostic) from None
            self._session_token = token
            self._customer_code = customer

        self._authenticated = True

    def _credentials_paths_need_token(self) -> bool:
        return any(
            path_has_session_token(path)
            for path in (self.supply_path, self.invoice_path, self.reading_path)
            if path
        )

    def _resolve_url(self, label: str) -> str | None:
        """Resolve the request path for ``label`` from the current session state."""
        now = dt_util.now().date()
        reading_from = (now - timedelta(days=_READING_WINDOW_DAYS)).strftime("%Y%m%d")
        today = now.strftime("%Y%m%d")
        return resolve_api_url(
            label,
            mode=self.mode,
            session_token=self._session_token,
            customer_code=self._customer_code,
            supply_path=self.supply_path,
            invoice_path=self.invoice_path,
            reading_path=self.reading_path,
            invoice_from="00000000",
            invoice_to=today,
            reading_from=reading_from,
            reading_to=today,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
            )
            self._authenticated = False
        if self.uses_credentials and not self._authenticated:
            await self._login()
        elif self.mode == MODE_COOKIE and not self.cookie:
            raise UpdateFailed(
                "ATS: aggiungi le credenziali oppure un cookie nelle opzioni"
            )

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": self.base_url + "/",
            "User-Agent": "HomeAssistant-ATS/0.4.0",
        }
        if self.mode == MODE_COOKIE:
            # Legacy mode only. With credentials, aiohttp sends CookieJar cookies.
            headers["Cookie"] = self.cookie

        try:
            supplies_payload = await self._request_json("utenze", headers)
            invoices_payload = await self._request_json("fatture", headers)
            readings_payload = []
            reading_url = self._resolve_url("letture")
            if reading_url:
                readings_payload = await self._request_json("letture", headers)
        except (UpdateFailed, ConfigEntryAuthFailed):
            raise
        except Exception:
            raise UpdateFailed("ATS: errore inatteso durante l'aggiornamento") from None

        supplies = _as_list(supplies_payload)
        return {
            "supplies": supplies,
            "supply_numbers": extract_supply_numbers(supplies),
            "invoices": _as_list(invoices_payload),
            "readings": _as_list(readings_payload),
            "last_update": self.hass.loop.time(),
        }

    async def _request_json(self, label: str, headers: dict) -> Any:
        """GET JSON for a label, renewing the session at most once per request.

        The URL is resolved from the current session token on every attempt, so
        a renewal mid-request automatically rebuilds the path with the new token.
        """
        auto_auth = self.uses_credentials
        for attempt in range(2 if auto_auth else 1):
            url = self._resolve_url(label)
            if url is None:
                raise UpdateFailed(f"ATS richiesta {label}: percorso non configurato")
            status: int | None = None
            try:
                async with self._session.get(
                    urljoin(self.base_url + "/", url.lstrip("/")),
                    headers=headers,
                    allow_redirects=False,
                ) as response:
                    status = response.status
                    if status in (401, 403, 301, 302, 303, 307, 308):
                        if auto_auth and attempt == 0:
                            _LOGGER.warning(
                                "ATS richiesta %s: rinnovo sessione (HTTP %s)",
                                label, status,
                            )
                            await self._login()
                            continue
                        if auto_auth:
                            diagnostic = (
                                f"ATS richiesta {label}: accesso/API rifiutati dopo nuovo login "
                                f"(HTTP {status}); verificare eventuale firma HMAC"
                            )
                        else:
                            diagnostic = f"ATS richiesta {label}: autenticazione rifiutata (HTTP {status})"
                        _LOGGER.warning("%s", diagnostic)
                        raise UpdateFailed(diagnostic)
                    response.raise_for_status()
                    return await response.json(content_type=None)
            except (UpdateFailed, ConfigEntryAuthFailed):
                raise
            except Exception as err:
                # No exception text: aiohttp errors can contain private URLs.
                if isinstance(err, aiohttp.ClientResponseError):
                    category = "errore HTTP"
                elif isinstance(err, TimeoutError):
                    category = "timeout"
                elif isinstance(err, (ValueError, UnicodeError)):
                    category = "risposta JSON non valida"
                elif isinstance(err, aiohttp.ClientError):
                    category = "errore di connessione"
                else:
                    category = "errore inatteso"
                diagnostic = f"ATS richiesta {label}: {category}"
                if status is not None:
                    diagnostic += f" (HTTP {status})"
                _LOGGER.warning("%s", diagnostic)
                raise UpdateFailed(diagnostic) from None
        raise UpdateFailed(f"ATS richiesta {label}: nessuna risposta valida")

    async def async_shutdown(self) -> None:
        self._authenticated = False
        self._session_token = None
        self._customer_code = None
        if self._session and not self._session.closed:
            await self._session.close()
