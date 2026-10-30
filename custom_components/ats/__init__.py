from __future__ import annotations

from datetime import timedelta
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import (
    CONF_BASE_URL,
    CONF_COOKIE,
    CONF_INVOICE_PATH,
    CONF_READING_PATH,
    CONF_SCAN_INTERVAL as ATS_SCAN_INTERVAL,
    CONF_SUPPLY_PATH,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import ATSCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = {**entry.data, **entry.options}
    base_url = data[CONF_BASE_URL].rstrip("/")
    supply_path = data[CONF_SUPPLY_PATH].strip()
    invoice_path = data[CONF_INVOICE_PATH].strip()
    reading_path = data.get(CONF_READING_PATH, "").strip()
    cookie = data[CONF_COOKIE].strip()
    scan_minutes = int(data.get(ATS_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    coordinator = ATSCoordinator(
        hass=hass,
        base_url=base_url,
        supply_path=supply_path,
        invoice_path=invoice_path,
        reading_path=reading_path,
        cookie=cookie,
        update_interval=timedelta(minutes=scan_minutes),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception as err:
        raise ConfigEntryNotReady(f"ATS API non raggiungibile o sessione non valida: {err}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
