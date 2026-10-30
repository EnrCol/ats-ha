from __future__ import annotations

import re
from urllib.parse import urlparse

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback

from .const import (
    CONF_BASE_URL,
    CONF_COOKIE,
    CONF_INVOICE_PATH,
    CONF_READING_PATH,
    CONF_SCAN_INTERVAL as ATS_SCAN_INTERVAL,
    CONF_SUPPLY_PATH,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

class ATSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].strip().rstrip("/")
            parsed = urlparse(base_url)
            if parsed.scheme != "https" or not parsed.netloc:
                errors["base_url"] = "invalid_url"
            elif not user_input[CONF_SUPPLY_PATH].strip().startswith("/"):
                errors["supply_path"] = "invalid_path"
            elif not user_input[CONF_INVOICE_PATH].strip().startswith("/"):
                errors["invoice_path"] = "invalid_path"
            elif user_input.get(CONF_READING_PATH, "").strip() and not user_input[CONF_READING_PATH].strip().startswith("/"):
                errors["reading_path"] = "invalid_path"
            elif not user_input[CONF_COOKIE].strip():
                errors["cookie"] = "required"
            else:
                await self.async_set_unique_id("ats_portal")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Alto Trevigiano Servizi",
                    data={
                        CONF_BASE_URL: base_url,
                        CONF_SUPPLY_PATH: user_input[CONF_SUPPLY_PATH].strip(),
                        CONF_INVOICE_PATH: user_input[CONF_INVOICE_PATH].strip(),
                        CONF_READING_PATH: user_input.get(CONF_READING_PATH, "").strip(),
                        CONF_COOKIE: user_input[CONF_COOKIE].strip(),
                        ATS_SCAN_INTERVAL: int(user_input[ATS_SCAN_INTERVAL]),
                    },
                )

        schema = vol.Schema({
            vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
            vol.Required(CONF_SUPPLY_PATH): str,
            vol.Required(CONF_INVOICE_PATH): str,
            vol.Optional(CONF_READING_PATH, default=""): str,
            vol.Required(CONF_COOKIE): str,
            vol.Optional(ATS_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
            ),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ATSOptionsFlow(config_entry)

class ATSOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        current = {**self._entry.data, **self._entry.options}
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        schema = vol.Schema({
            vol.Required(CONF_BASE_URL, default=current.get(CONF_BASE_URL, DEFAULT_BASE_URL)): str,
            vol.Required(CONF_SUPPLY_PATH, default=current.get(CONF_SUPPLY_PATH, "")): str,
            vol.Required(CONF_INVOICE_PATH, default=current.get(CONF_INVOICE_PATH, "")): str,
            vol.Optional(CONF_READING_PATH, default=current.get(CONF_READING_PATH, "")): str,
            vol.Required(CONF_COOKIE, default=current.get(CONF_COOKIE, "")): str,
            vol.Required(ATS_SCAN_INTERVAL, default=current.get(ATS_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
            ),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
