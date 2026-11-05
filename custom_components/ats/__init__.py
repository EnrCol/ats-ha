from __future__ import annotations

from datetime import timedelta
import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
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



async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    data = {**entry.data, **entry.options}
    base_url = data[CONF_BASE_URL].rstrip("/")
    # Paths are optional in automatic mode: they are discovered after login.
    supply_path = (data.get(CONF_SUPPLY_PATH) or "").strip()
    invoice_path = (data.get(CONF_INVOICE_PATH) or "").strip()
    reading_path = (data.get(CONF_READING_PATH) or "").strip()
    cookie = data.get(CONF_COOKIE, "").strip()
    scan_minutes = int(data.get(ATS_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))

    # Credentials are stored in this instance's config entry, not in a
    # global secrets.yaml that would incorrectly be shared across accounts.
    # Always read credentials from entry.data. Options are only for
    # polling and API paths, so a reauthentication cannot be shadowed.
    username = entry.data.get(CONF_USERNAME)
    password = entry.data.get(CONF_PASSWORD)
    if not (
        isinstance(username, str)
        and username.strip()
        and isinstance(password, str)
        and password
    ):
        username = password = None
    else:
        username = username.strip()

    coordinator = ATSCoordinator(
        hass=hass,
        base_url=base_url,
        supply_path=supply_path,
        invoice_path=invoice_path,
        reading_path=reading_path,
        cookie=cookie,
        update_interval=timedelta(minutes=scan_minutes),
        username=username,
        password=password,
        config_entry=entry,
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        await coordinator.async_shutdown()
        raise
    except Exception:
        # A first-refresh failure can happen repeatedly after HTTP 401.
        # Release the ClientSession before Home Assistant retries setup.
        await coordinator.async_shutdown()
        raise ConfigEntryNotReady(
            "ATS: impossibile completare il primo aggiornamento; "
            "controlla accesso e percorsi API"
        ) from None

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator is not None:
            await coordinator.async_shutdown()
    return unload_ok
