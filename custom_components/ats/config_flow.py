"""Configuration flow for ATS portal credentials or a legacy session cookie."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlparse

import aiohttp

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback

from .auth import (
    ATSDiscoveryError,
    ATSInvalidCredentials,
    ATSLoginError,
    async_discover_identifiers,
    async_login,
)
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

    # Automatic mode = credentials present and no manual supply path: the
    # supply/invoice paths are discovered after login and are not required.
    supply = str(data.get(CONF_SUPPLY_PATH) or "").strip()
    auto = bool(username) and not supply
    if not auto:
        for key in (CONF_SUPPLY_PATH, CONF_INVOICE_PATH):
            if not str(data.get(key) or "").strip().startswith("/"):
                return "invalid_path"
    # Any path that is supplied must still be well-formed.
    for key in (CONF_SUPPLY_PATH, CONF_INVOICE_PATH, CONF_READING_PATH):
        value = str(data.get(key) or "").strip()
        if value and not value.startswith("/"):
            return "invalid_path"
    interval = data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    if not isinstance(interval, int) or not MIN_SCAN_INTERVAL <= interval <= MAX_SCAN_INTERVAL:
        return "invalid_interval"
    return None


async def _validate_portal_credentials(
    username: str, password: str, *, discover: bool = False
) -> str | None:
    """Check credentials against ATS without logging or returning secrets.

    When ``discover`` is set (automatic mode), also confirm the account exposes
    the identifiers needed for self-configuration.
    """
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=20)
        ) as session:
            await async_login(session, DEFAULT_BASE_URL, username, password)
            if discover:
                await async_discover_identifiers(session, DEFAULT_BASE_URL)
    except ATSInvalidCredentials:
        return "invalid_auth"
    except ATSDiscoveryError:
        # Subclass of ATSLoginError: must be caught before it.
        return "discovery_failed"
    except (ATSLoginError, aiohttp.ClientError, TimeoutError):
        return "cannot_connect"
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
                username = (user_input.get(CONF_USERNAME) or "").strip()
                password = user_input.get(CONF_PASSWORD) or ""
                if username:
                    auto = not (user_input.get(CONF_SUPPLY_PATH) or "").strip()
                    error = await _validate_portal_credentials(
                        username, password, discover=auto
                    )
                    if error:
                        errors["base"] = error
                if not errors:
                    # One config entry per HA instance, preserving the legacy
                    # unique ID until explicit multi-customer support exists.
                    await self.async_set_unique_id("ats_portal")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                    title="Alto Trevigiano Servizi",
                    data={
                        CONF_BASE_URL: user_input[CONF_BASE_URL].strip().rstrip("/"),
                        CONF_SUPPLY_PATH: (user_input.get(CONF_SUPPLY_PATH) or "").strip(),
                        CONF_INVOICE_PATH: (user_input.get(CONF_INVOICE_PATH) or "").strip(),
                        CONF_READING_PATH: (user_input.get(CONF_READING_PATH) or "").strip(),
                        CONF_COOKIE: (user_input.get(CONF_COOKIE) or "").strip(),
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                        CONF_SCAN_INTERVAL: int(
                            user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                        ),
                    },
                )

        schema = vol.Schema({
            vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
            vol.Optional(CONF_USERNAME): TextSelector(
                TextSelectorConfig(autocomplete="username")
            ),
            vol.Optional(CONF_PASSWORD): _PASSWORD_FIELD,
            vol.Optional(CONF_SUPPLY_PATH): str,
            vol.Optional(CONF_INVOICE_PATH): str,
            vol.Optional(CONF_READING_PATH, default=""): str,
            vol.Optional(CONF_COOKIE): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
            ),
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, object]):
        """Reauthenticate the existing ATS entry, never create a new one."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        """Request only the password, so the ATS username cannot change."""
        entry = self._get_reauth_entry()
        username = entry.data.get(CONF_USERNAME)
        if not isinstance(username, str) or not username.strip():
            return self.async_abort(reason="reauth_not_supported")

        errors = {}
        if user_input is not None:
            password = user_input[CONF_PASSWORD]
            error = await _validate_portal_credentials(username, password)
            if error:
                errors["base"] = error
            else:
                # Credentials are stored in entry.data, not in options.
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={CONF_PASSWORD: password},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD_FIELD}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return ATSOptionsFlow(config_entry)


class ATSOptionsFlow(config_entries.OptionsFlow):
    """Manage endpoints and polling, without copying passwords into options."""

    def __init__(self, config_entry):
        self._entry = config_entry

    async def async_step_init(self, user_input=None):
        current = {**self._entry.data, **self._entry.options}
        errors = {}
        if user_input is not None:
            # Only non-secret settings belong in options.
            proposed = {
                **current,
                **user_input,
                CONF_USERNAME: self._entry.data.get(CONF_USERNAME, ""),
                CONF_PASSWORD: self._entry.data.get(CONF_PASSWORD, ""),
                CONF_COOKIE: user_input.get(
                    CONF_COOKIE, current.get(CONF_COOKIE, "")
                ),
            }
            error = _validate_input(proposed)
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_BASE_URL: proposed[CONF_BASE_URL].strip().rstrip("/"),
                        CONF_SUPPLY_PATH: (proposed.get(CONF_SUPPLY_PATH) or "").strip(),
                        CONF_INVOICE_PATH: (proposed.get(CONF_INVOICE_PATH) or "").strip(),
                        CONF_READING_PATH: (proposed.get(CONF_READING_PATH) or "").strip(),
                        CONF_COOKIE: (proposed.get(CONF_COOKIE) or "").strip(),
                        CONF_SCAN_INTERVAL: int(
                            proposed.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                        ),
                    },
                )

        schema = vol.Schema({
            vol.Required(CONF_BASE_URL, default=current.get(CONF_BASE_URL, DEFAULT_BASE_URL)): str,
            vol.Optional(CONF_SUPPLY_PATH, default=current.get(CONF_SUPPLY_PATH, "")): str,
            vol.Optional(CONF_INVOICE_PATH, default=current.get(CONF_INVOICE_PATH, "")): str,
            vol.Optional(CONF_READING_PATH, default=current.get(CONF_READING_PATH, "")): str,
            vol.Optional(CONF_COOKIE, default=current.get(CONF_COOKIE, "")): str,
            vol.Optional(CONF_SCAN_INTERVAL, default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
            ),
        })
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
