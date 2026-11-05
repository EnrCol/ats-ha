from __future__ import annotations

import logging
import re
from datetime import timedelta
from typing import Any
from urllib.parse import urljoin

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .auth import ATSLoginError, async_login

_LOGGER = logging.getLogger(__name__)

# Only replace a whole UUID path segment, never a customer or meter identifier.
_SESSION_UUID_RE = re.compile(
    r"(?<=/)[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}(?=/|\?|$)"
)

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
    ) -> None:
        self.base_url = base_url
        self.supply_path = supply_path
        self.invoice_path = invoice_path
        self.reading_path = reading_path
        self.cookie = cookie
        self.username = username
        self.password = password
        self._authenticated = False
        self._session: aiohttp.ClientSession | None = None
        super().__init__(
            hass,
            _LOGGER,
            name="Alto Trevigiano Servizi",
            update_interval=update_interval,
        )

    async def _login(self) -> None:
        """Obtain fresh authentication cookies using secrets.yaml credentials."""
        if self._session is None or not self.username or not self.password:
            raise UpdateFailed("ATS: credenziali non configurate")
        self._authenticated = False
        try:
            await async_login(self._session, self.base_url, self.username, self.password)
        except ATSLoginError as err:
            # ATSLoginError contains only short, sanitized messages.
            diagnostic = f"ATS login: {err}"
            _LOGGER.warning("%s", diagnostic)
            raise UpdateFailed(diagnostic) from None
        self._authenticated = True

    def _current_api_path(self, label: str, path: str) -> str:
        """Substitute the fresh ATS session UUID, without persisting or logging it."""
        if not (self.username and self.password) or label not in ("utenze", "fatture", "letture"):
            return path
        has_placeholder = "{session_uuid}" in path
        if not has_placeholder and not _SESSION_UUID_RE.search(path):
            return path

        if self._session is None:
            raise UpdateFailed("ATS: sessione HTTP non disponibile")

        session_tokens = [
            morsel.value
            for morsel in self._session.cookie_jar
            if morsel.key.startswith("sol-") and morsel.key.endswith("-at")
        ]
        if len(session_tokens) != 1 or not re.fullmatch(
            r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}",
            session_tokens[0],
        ):
            raise UpdateFailed("ATS: identificativo sessione corrente non disponibile")
        if has_placeholder:
            if path.count("{session_uuid}") != 1:
                raise UpdateFailed("ATS: percorso letture con identificativi ambigui")
            return path.replace("{session_uuid}", session_tokens[0])
        if len(_SESSION_UUID_RE.findall(path)) != 1:
            raise UpdateFailed("ATS: percorso API con identificativi ambigui")
        return _SESSION_UUID_RE.sub(session_tokens[0], path, count=1)

    async def _async_update_data(self) -> dict[str, Any]:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
            )
            self._authenticated = False
        if self.username and self.password and not self._authenticated:
            await self._login()
        elif not (self.username and self.password) and not self.cookie:
            raise UpdateFailed("ATS: aggiungi le credenziali in secrets.yaml o un cookie nelle opzioni")

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Referer": self.base_url + "/",
            "User-Agent": "HomeAssistant-ATS/0.4.0",
        }
        if not (self.username and self.password):
            # Legacy mode only. In automatic mode, aiohttp sends CookieJar cookies.
            headers["Cookie"] = self.cookie

        try:
            supplies_payload, invoices_payload, readings_payload = await self._fetch_data(headers)
        except UpdateFailed:
            raise
        except Exception:
            raise UpdateFailed("ATS: errore inatteso durante l'aggiornamento") from None

        return {
            "supplies": _as_list(supplies_payload),
            "invoices": _as_list(invoices_payload),
            "readings": _as_list(readings_payload),
            "last_update": self.hass.loop.time(),
        }

    async def _request_json(self, label: str, path: str, headers: dict) -> Any:
        """Get JSON, renewing the authenticated session at most once per request."""
        auto_auth = bool(self.username and self.password)
        for attempt in range(2 if auto_auth else 1):
            status: int | None = None
            try:
                async with self._session.get(
                    urljoin(
                        self.base_url + "/",
                        self._current_api_path(label, path).lstrip("/"),
                    ),
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
            except UpdateFailed:
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

    async def _fetch_data(self, headers: dict) -> tuple[Any, Any, Any]:
        supplies = await self._request_json("utenze", self.supply_path, headers)
        invoice_path = self.invoice_path
        if self.username and self.password and "/invoice/" in invoice_path:
            # Keep the tested history start; move the last YYYYMMDD to today.
            dates = re.search(r"/\d{8}/(?P<end>\d{8})/?$", invoice_path)
            if dates:
                invoice_path = (
                    invoice_path[:dates.start("end")]
                    + dt_util.now().strftime("%Y%m%d")
                    + invoice_path[dates.end("end"):]
                )
        invoices = await self._request_json("fatture", invoice_path, headers)
        readings = []
        reading_path = self.reading_path
        if not reading_path and self.username and self.password:
            # The authenticated portal requests the preceding 365 days.
            # Keep a placeholder: _request_json resolves the current session
            # token again after any automatic reauthentication.
            end_date = dt_util.now().date()
            start_date = end_date - timedelta(days=365)
            reading_path = (
                "/webapi/api/v1/reading-base/{session_uuid}/-1/"
                f"{start_date:%Y%m%d}/{end_date:%Y%m%d}/"
            )
        if reading_path:
            readings = await self._request_json("letture", reading_path, headers)
        return supplies, invoices, readings

    async def async_shutdown(self) -> None:
        self._authenticated = False
        if self._session and not self._session.closed:
            await self._session.close()
