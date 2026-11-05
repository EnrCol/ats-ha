"""Configuration flow for ATS portal credentials or a legacy session cookie."""

from __future__ import annotations

from urllib.parse import urlparse

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_BASE_URL,
    CONF_COOKIE,
    CONF_INVOICE_PATH,
    CONF_READING_PATH,
    CONF_SCAN_INTERVAL,
    CONF_SUPPLY_PATH,
    DEFAULT_BASE_URL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


_PASSWORD_FIELD = TextSelector(
    TextSelectorConfig(
        type=TextSelectorType.PASSWORD, autocomplete="current-password"
    )
)


def _validate_input(data: dict) -> str | None:
    """Return a translated error key, without echoing credentials."""
    base_url = str(data.get(CONF_BASE_URL, "")).strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return "invalid_url"

    username = str(data.get(CONF_USERNAME) or "").strip()
    password = data.get(CONF_PASSWORD) or ""
    cookie = str(data.get(CONF_COOKIE) or "").strip()

    # Do not send password-based logins to a configurable third-party host.
    if username and base_url != DEFAULT_BASE_URL:
        return "invalid_url"
    if bool(username) != bool(password):
        return "missing_credentials"
    if not username and not cookie:
        return "missing_auth"
    for key in (CONF_SUPPLY_PATH, CONF_INVOICE_PATH):
        if not str(data.get(key) or "").strip().startswith("/"):
            return "invalid_path"
    reading = str(data.get(CONF_READING_PATH) or "").strip()
    if reading and not reading.startswith("/"):
        return "invalid_path"
    interval = data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    if not isinstance(interval, int) or not MIN_SCAN_INTERVAL <= interval <= MAX_SCAN_INTERVAL:
        return "invalid_interval"
    return None


class ATSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up ATS without requiring users to copy authentication cookies."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            error = _validate_input(user_input)
            if error:
                errors["base"] = error
            else:
                # Keep the existing stable unique ID until the automatic
                # account discovery and per-account migration are ready.
                await self.async_set_unique_id("ats_portal")
                self._abort_if_unique_id_configured()
                username = (user_input.get(CONF_USERNAME) or "").strip()
                password = user_input.get(CONF_PASSWORD) or ""
                return self.async_create_entry(
                    title="Alto Trevigiano Servizi",
                    data={
                        CONF_BASE_URL: user_input[CONF_BASE_URL].strip().rstrip("/"),
                        CONF_SUPPLY_PATH: user_input[CONF_SUPPLY_PATH].strip(),
                        CONF_INVOICE_PATH: user_input[CONF_INVOICE_PATH].strip(),
                        CONF_READING_PATH: (user_input.get(CONF_READING_PATH) or "").strip(),
                        CONF_COOKIE: (user_input.get(CONF_COOKIE) or "").strip(),
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                    },
                )

        schema = vol.Schema({
            vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
            vol.Optional(CONF_USERNAME): TextSelector(
                TextSelectorConfig(autocomplete="username")
            ),
            vol.Optional(CONF_PASSWORD): _PASSWORD_FIELD,
            vol.Required(CONF_SUPPLY_PATH): str,
            vol.Required(CONF_INVOICE_PATH): str,
            vol.Optional(CONF_READING_PATH, default=""): str,
            vol.Optional(CONF_COOKIE): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
            ),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ATSOptionsFlow(config_entry)


class ATSOptionsFlow(config_entries.OptionsFlow):
    """Change scan interval, endpoints and credentials without losing secrets."""

    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        current = {**self._entry.data, **self._entry.options}
        errors = {}

        if user_input is not None:
            proposed = {**current, **user_input}
            if not user_input.get(CONF_PASSWORD):
                # The password box is intentionally never pre-populated.
                proposed[CONF_PASSWORD] = current.get(CONF_PASSWORD, "")
            if not user_input.get(CONF_COOKIE):
                proposed[CONF_COOKIE] = current.get(CONF_COOKIE, "")
            if not (proposed.get(CONF_USERNAME) or "").strip():
                proposed[CONF_PASSWORD] = ""
            elif (
                proposed.get(CONF_USERNAME) != current.get(CONF_USERNAME)
                and not user_input.get(CONF_PASSWORD)
            ):
                errors["base"] = "missing_credentials"
            if not errors:
                error = _validate_input(proposed)
                if error:
                    errors["base"] = error
                else:
                    return self.async_create_entry(
                        title="", data={**self._entry.options, **proposed}
                    )

        schema = vol.Schema({
            vol.Required(CONF_BASE_URL, default=current.get(CONF_BASE_URL, DEFAULT_BASE_URL)): str,
            vol.Optional(CONF_USERNAME, default=current.get(CONF_USERNAME, "")): TextSelector(
                TextSelectorConfig(autocomplete="username")
            ),
            vol.Optional(CONF_PASSWORD): _PASSWORD_FIELD,
            vol.Required(CONF_SUPPLY_PATH, default=current.get(CONF_SUPPLY_PATH, "")): str,
            vol.Required(CONF_INVOICE_PATH, default=current.get(CONF_INVOICE_PATH, "")): str,
            vol.Optional(CONF_READING_PATH, default=current.get(CONF_READING_PATH, "")): str,
            vol.Optional(CONF_COOKIE): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
            ),
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
