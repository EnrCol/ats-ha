"""Authenticated, on-demand PDF invoice retrieval for the ATS WebForms portal.

A signed PDF URL must be obtained using the authenticated invoice detail
postback each time. Never log request URLs, cookies, tokens, or response bodies.
"""

from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import aiohttp
from homeassistant.core import HomeAssistant

from .auth import MODE_COOKIE, _HiddenFormFields

_PDF_ROOT = Path("/media/ats/fatture")
_PDF_MAX_BYTES = 20 * 1024 * 1024
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_DETAIL_PATH = "/Dettaglio/edit-fattura.aspx"
_PDF_PATH = "/webapi/visualizza-bolletta.aspx"
_REQUIRED_HIDDEN = (
    "__VIEWSTATE",
    "__VIEWSTATEGENERATOR",
    "__EVENTVALIDATION",
    "__AntiXsrfToken",
)
_REQUIRED_QUERY = ("username", "timestamp", "invoice", "hash")


class ATSInvoiceDownloadError(Exception):
    """Safe-to-display failure without credentials, URLs or document contents."""


class _ATSInvoiceSessionExpired(ATSInvoiceDownloadError):
    """The current WebForms session is no longer authenticated."""


def _supply_code(invoice: dict) -> str:
    """ATS exposes SupplyNo as a single-item JSON array (or a string)."""
    value = invoice.get("SupplyNo")
    if isinstance(value, str):
        return value.strip()
    if (
        isinstance(value, (list, tuple))
        and len(value) == 1
        and isinstance(value[0], str)
    ):
        return value[0].strip()
    return ""


def _invoice_identity(invoice: dict) -> tuple[str, str, int]:
    """Use invoice.No, not invoice.Id; accept only safe path components."""
    number = str(invoice.get("No") or "").strip()
    supply = _supply_code(invoice)
    if not _SAFE_NAME.fullmatch(number) or not _SAFE_NAME.fullmatch(supply):
        raise ATSInvoiceDownloadError("Identificativi della fattura ATS mancanti o non validi")

    issued = invoice.get("EmissionDate")
    if isinstance(issued, datetime):
        parsed = issued
    elif isinstance(issued, str):
        value = issued.strip()
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
            for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
                try:
                    parsed = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue
    else:
        parsed = None
    if parsed is None or not 2000 <= parsed.year <= 2100:
        raise ATSInvoiceDownloadError("Data di emissione fattura ATS non valida")
    return number, supply, parsed.year


def _signed_download_url(base_url: str, location: str) -> str:
    """Accept only ATS's expected signed endpoint on the original HTTPS host."""
    signed = urljoin(base_url.rstrip("/") + "/", location)
    actual = urlsplit(signed)
    expected = urlsplit(base_url)
    if (
        actual.scheme != "https"
        or actual.hostname != expected.hostname
        or actual.port != expected.port
        or actual.username is not None
        or actual.password is not None
        or actual.path.lower() != _PDF_PATH.lower()
    ):
        raise ATSInvoiceDownloadError("Redirect PDF ATS inatteso")
    params = parse_qs(actual.query, keep_blank_values=True)
    if not all(len(params.get(key, [])) == 1 and params[key][0] for key in _REQUIRED_QUERY):
        raise ATSInvoiceDownloadError("Parametri firmati del PDF ATS mancanti")
    return signed


async def _fetch_pdf(coordinator, number: str, supply: str) -> bytes:
    """GET details, POST btnOpen, GET server-signed PDF, all in one session."""
    session = coordinator._session
    if session is None or session.closed:
        raise _ATSInvoiceSessionExpired("Sessione ATS non disponibile")

    detail_url = urljoin(
        coordinator.base_url.rstrip("/") + "/",
        _DETAIL_PATH.lstrip("/") + "?" + urlencode({
            "fattura": number,
            "codUtenza": supply,
        }),
    )
    headers = {
        "Referer": coordinator.base_url.rstrip("/") + "/",
        "User-Agent": "HomeAssistant-ATS/0.4.0",
    }
    if coordinator.mode == MODE_COOKIE:
        headers["Cookie"] = coordinator.cookie

    try:
        async with session.get(
            detail_url, headers=headers, allow_redirects=False,
        ) as response:
            if response.status in (301, 302, 303, 307, 308, 401, 403):
                raise _ATSInvoiceSessionExpired("Sessione ATS scaduta")
            if response.status != 200:
                raise ATSInvoiceDownloadError("Dettaglio fattura ATS non disponibile")
            page = await response.text()

        parser = _HiddenFormFields()
        parser.feed(page)
        hidden = parser.fields
        if not all(hidden.get(key) for key in _REQUIRED_HIDDEN):
            raise ATSInvoiceDownloadError("Campi WebForms della fattura ATS mancanti")

        form_data = {
            **hidden,
            "__EVENTTARGET": "btnOpen",
            "__EVENTARGUMENT": "",
        }
        async with session.post(
            detail_url,
            data=form_data,
            headers={
                **headers,
                "Origin": coordinator.base_url.rstrip("/"),
                "Referer": detail_url,
            },
            allow_redirects=False,
        ) as response:
            if response.status in (401, 403):
                raise _ATSInvoiceSessionExpired("Sessione ATS scaduta")
            if response.status not in (302, 303):
                raise ATSInvoiceDownloadError("Postback PDF ATS non riuscito")
            location = response.headers.get("Location") or ""

        if not location:
            raise ATSInvoiceDownloadError("Redirect PDF ATS mancante")
        if "login.aspx" in urlsplit(urljoin(detail_url, location)).path.lower():
            raise _ATSInvoiceSessionExpired("Sessione ATS scaduta")
        signed_url = _signed_download_url(coordinator.base_url, location)
        async with session.get(
            signed_url,
            headers={**headers, "Referer": detail_url, "Accept": "application/pdf"},
            allow_redirects=False,
        ) as response:
            if response.status in (301, 302, 303, 307, 308, 401, 403):
                raise _ATSInvoiceSessionExpired("Sessione ATS scaduta")
            if response.status != 200:
                raise ATSInvoiceDownloadError("Download PDF ATS non riuscito")
            if response.content_type.lower() != "application/pdf":
                raise ATSInvoiceDownloadError("La risposta ATS non è un PDF")
            if response.content_length is not None and response.content_length > _PDF_MAX_BYTES:
                raise ATSInvoiceDownloadError("PDF ATS oltre la dimensione massima")

            pdf = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                if len(pdf) + len(chunk) > _PDF_MAX_BYTES:
                    raise ATSInvoiceDownloadError("PDF ATS oltre la dimensione massima")
                pdf.extend(chunk)
            if len(pdf) < 5 or pdf[:5] != b"%PDF-":
                raise ATSInvoiceDownloadError("Firma PDF ATS non valida")
            return bytes(pdf)
    except (ATSInvoiceDownloadError, _ATSInvoiceSessionExpired):
        raise
    except (aiohttp.ClientError, TimeoutError, ValueError, UnicodeError):
        # aiohttp exceptions can include the signed URL: never expose them.
        raise ATSInvoiceDownloadError("Errore di rete durante il download PDF ATS") from None


def _store_pdf(filename: Path, data: bytes) -> bool:
    """Atomic file creation; existing invoices are never overwritten."""
    filename.parent.mkdir(parents=True, exist_ok=True)
    if filename.exists():
        if filename.is_file():
            return False
        raise ATSInvoiceDownloadError("Percorso PDF ATS occupato da una directory")

    fd, temporary = tempfile.mkstemp(
        prefix=".ats-", suffix=".part", dir=str(filename.parent),
    )
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if filename.exists():
            return False
        os.replace(temporary, filename)
        return True
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


async def async_download_invoice(hass: HomeAssistant, coordinator, invoice: dict) -> bool:
    """Download one invoice only if missing. Returns True for a new PDF."""
    if invoice.get("PdfExist") is not True:
        raise ATSInvoiceDownloadError("PDF della fattura non disponibile sul portale ATS")

    number, supply, year = _invoice_identity(invoice)
    destination = _PDF_ROOT / str(year) / (number + ".pdf")
    if await hass.async_add_executor_job(destination.is_file):
        return False

    for attempt in range(2 if coordinator.uses_credentials else 1):
        try:
            pdf = await _fetch_pdf(coordinator, number, supply)
            break
        except _ATSInvoiceSessionExpired:
            if attempt or not coordinator.uses_credentials:
                raise ATSInvoiceDownloadError("Sessione ATS scaduta durante il download") from None
            try:
                await coordinator._login()
            except Exception:
                raise ATSInvoiceDownloadError("Rinnovo sessione ATS non riuscito") from None
    else:
        raise ATSInvoiceDownloadError("Impossibile recuperare il PDF ATS")

    try:
        return await hass.async_add_executor_job(_store_pdf, destination, pdf)
    except ATSInvoiceDownloadError:
        raise
    except OSError:
        raise ATSInvoiceDownloadError("Impossibile salvare il PDF nella cartella media ATS") from None
