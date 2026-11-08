from __future__ import annotations

from datetime import timedelta
import asyncio
import logging
from pathlib import Path

from aiohttp import web
import voluptuous as vol
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.components.http import HomeAssistantView, StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
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
from .invoice_download import (
    _PDF_ROOT,
    _SAFE_NAME,
    _invoice_identity,
    ATSInvoiceDownloadError,
    async_download_invoice,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


class ATSInvoicePDFView(HomeAssistantView):
    """Serve only locally archived ATS invoices to authenticated HA users."""

    url = "/api/ats/invoice/{year}/{number}"
    name = "api:ats:invoice"
    requires_auth = True

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass

    async def get(self, request: web.Request, year: str, number: str) -> web.StreamResponse:
        if (
            len(year) != 4
            or not year.isascii()
            or not year.isdecimal()
            or not 2000 <= int(year) <= 2100
            or _SAFE_NAME.fullmatch(number) is None
        ):
            raise web.HTTPNotFound()

        # A valid file path alone is insufficient: the invoice must also
        # belong to an ATS account currently loaded in this HA instance.
        matching_invoice = False
        for coordinator in self._hass.data.get(DOMAIN, {}).values():
            for invoice in (coordinator.data or {}).get("invoices") or []:
                if invoice.get("PdfExist") is not True:
                    continue
                try:
                    invoice_number, _, invoice_year = _invoice_identity(invoice)
                except ATSInvoiceDownloadError:
                    continue
                if invoice_number == number and str(invoice_year) == year:
                    matching_invoice = True
                    break
            if matching_invoice:
                break
        if not matching_invoice:
            raise web.HTTPNotFound()

        filename = _PDF_ROOT / year / (number + ".pdf")
        # Never follow a link outside the private ATS archive. This check
        # and the filesystem lookup run in an executor.
        def _allowed_file() -> bool:
            return (
                filename.is_file()
                and filename.resolve().is_relative_to(_PDF_ROOT.resolve())
            )

        if not await self._hass.async_add_executor_job(_allowed_file):
            raise web.HTTPNotFound()

        return web.FileResponse(
            filename,
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": f'inline; filename="{number}.pdf"',
                "Cache-Control": "no-store, private",
                "X-Content-Type-Options": "nosniff",
            },
        )


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    # Called once per HA process (unlike async_setup_entry on config reload).
    # The Lovelace card is bundled with ATS; no /config/www copy is required.
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                "/ats_static/invoice-history-card.js",
                str(Path(__file__).parent / "www" / "invoice-history-card.js"),
                False,
            )
        ]
    )
    card_url = "/ats_static/invoice-history-card.js?v=0.4.0b7"
    lovelace_data = hass.data.get(LOVELACE_DATA)
    resources = lovelace_data.resources if lovelace_data else None
    if isinstance(resources, ResourceStorageCollection):
        # Persist the module in the actual Lovelace storage resource list.
        # A plain add_extra_js_url is not consistently loaded by dashboards.
        await resources.async_get_info()
        entries = resources.async_items()
        if not any(
            (item.get("url") or "").split("?")[0] == "/ats_static/invoice-history-card.js"
            for item in entries
        ):
            await resources.async_create_item({"res_type": "module", "url": card_url})
    else:
        # YAML resource mode cannot be written through the storage collection.
        add_extra_js_url(hass, card_url)
    hass.http.register_view(ATSInvoicePDFView(hass))
    return True



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

    # One explicit action, never called from the periodic coordinator refresh.
    download_lock = asyncio.Lock()

    async def _async_download_invoices(call: ServiceCall) -> None:
        number = str(call.data.get("invoice_number") or "").strip()
        invoices = (coordinator.data or {}).get("invoices") or []

        if number:
            selected = [invoice for invoice in invoices if str(invoice.get("No") or "").strip() == number]
            if not selected:
                raise HomeAssistantError("ATS: numero fattura non trovato")
        else:
            selected = [invoice for invoice in invoices if invoice.get("PdfExist") is True]
            if not selected:
                raise HomeAssistantError("ATS: nessuna fattura PDF disponibile")

        saved_count = 0
        skipped_count = 0
        error_count = 0
        async with download_lock:
            for invoice in selected:
                try:
                    saved = await async_download_invoice(hass, coordinator, invoice)
                except ATSInvoiceDownloadError as err:
                    # The downloader raises only fixed, sanitized diagnostics.
                    # Never log a request URL, invoice identifier or traceback.
                    _LOGGER.warning("ATS PDF: fattura non scaricata: %s", err)
                    error_count += 1
                    continue
                if saved:
                    saved_count += 1
                else:
                    skipped_count += 1

        _LOGGER.info(
            "ATS PDF: salvate=%s, già presenti=%s, errori=%s",
            saved_count, skipped_count, error_count,
        )
        if error_count:
            raise HomeAssistantError(
                f"ATS: {error_count} fatture non scaricate. "
                "Ritenta l'azione; i PDF già presenti vengono saltati."
            )

    hass.services.async_register(
        DOMAIN,
        "download_invoices",
        _async_download_invoices,
        schema=vol.Schema({vol.Optional("invoice_number"): cv.string}),
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.services.async_remove(DOMAIN, "download_invoices")
        coordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator is not None:
            await coordinator.async_shutdown()
    return unload_ok
