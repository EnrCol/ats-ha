from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from urllib.parse import urljoin

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

_LOGGER = logging.getLogger(__name__)

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
    ) -> None:
        self.base_url = base_url
        self.supply_path = supply_path
        self.invoice_path = invoice_path
        self.reading_path = reading_path
        self.cookie = cookie
        self._session: aiohttp.ClientSession | None = None
        super().__init__(
            hass,
            _LOGGER,
            name="Alto Trevigiano Servizi",
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Cookie": self.cookie,
            "Referer": self.base_url + "/",
            "User-Agent": "HomeAssistant-ATS/0.2.0",
        }
        try:
            supplies_payload, invoices_payload, readings_payload = await self._fetch_data(headers)
        except Exception as err:
            # Do not log headers/cookies or exception request details.
            raise UpdateFailed(
                "Impossibile aggiornare ATS. Verifica i percorsi API e che la sessione del portale sia ancora valida."
            ) from err

        supplies = _as_list(supplies_payload)
        invoices = _as_list(invoices_payload)
        readings = _as_list(readings_payload)
        return {
            "supplies": supplies,
            "invoices": invoices,
            "readings": readings,
            "last_update": self.hass.loop.time(),
        }

    async def _fetch_data(self, headers):
        async with self._session.get(
            urljoin(self.base_url + "/", self.supply_path.lstrip("/")),
            headers=headers,
        ) as response:
            if response.status in (401, 403):
                raise ValueError("Sessione ATS non valida o scaduta")
            response.raise_for_status()
            supplies = await response.json(content_type=None)
        async with self._session.get(
            urljoin(self.base_url + "/", self.invoice_path.lstrip("/")),
            headers=headers,
        ) as response:
            if response.status in (401, 403):
                raise ValueError("Sessione ATS non valida o scaduta")
            response.raise_for_status()
            invoices = await response.json(content_type=None)
        readings = []
        # The reading endpoint is optional to preserve existing v0.1.0 setups.
        # When configured, it is fetched using the same authenticated session cookie.
        if self.reading_path:
            async with self._session.get(
                urljoin(self.base_url + "/", self.reading_path.lstrip("/")),
                headers=headers,
            ) as response:
                if response.status in (401, 403):
                    raise ValueError("Sessione ATS non valida o scaduta")
                response.raise_for_status()
                readings = await response.json(content_type=None)
        return supplies, invoices, readings

    async def async_shutdown(self):
        if self._session and not self._session.closed:
            await self._session.close()
