"""Authenticated invoice HTTP view safety and clean-install integration checks."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from aiohttp import web
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))
import ats


class FakeHass:
    def __init__(self, invoices):
        self.data = {"ats": {"test_entry": SimpleNamespace(data={"invoices": invoices})}}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def invoice(number="INV_1", year=2026, *, pdf_exist=True):
    return {
        "No": number,
        "SupplyNo": ["SUPPLY_1"],
        "EmissionDate": f"{year}-05-19T00:00:00",
        "PdfExist": pdf_exist,
    }


@pytest.mark.asyncio
async def test_pdf_endpoint_accepts_only_known_pdf_in_private_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(ats, "_PDF_ROOT", tmp_path)
    dest = tmp_path / "2026" / "INV_1.pdf"
    dest.parent.mkdir()
    dest.write_bytes(b"%PDF-1.7 TEST")

    view = ats.ATSInvoicePDFView(FakeHass([invoice()]))
    assert view.requires_auth is True
    response = await view.get(None, "2026", "INV_1")
    assert isinstance(response, web.FileResponse)
    assert response.headers["Content-Type"] == "application/pdf"
    assert response.headers["Cache-Control"] == "no-store, private"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


@pytest.mark.asyncio
async def test_pdf_endpoint_rejects_unknown_invoice_and_wrong_year(tmp_path, monkeypatch):
    monkeypatch.setattr(ats, "_PDF_ROOT", tmp_path)
    (tmp_path / "2026").mkdir()
    (tmp_path / "2026" / "INV_1.pdf").write_bytes(b"%PDF-1.7 TEST")
    view = ats.ATSInvoicePDFView(FakeHass([invoice()]))

    for year, number in (
        ("2026", "OTHER"),
        ("2025", "INV_1"),
        ("2026", "../INV_1"),
        ("not-year", "INV_1"),
        ("2026", "INV_1.pdf"),
    ):
        with pytest.raises(web.HTTPNotFound):
            await view.get(None, year, number)


@pytest.mark.asyncio
async def test_pdf_endpoint_rejects_missing_local_file(tmp_path, monkeypatch):
    monkeypatch.setattr(ats, "_PDF_ROOT", tmp_path)
    view = ats.ATSInvoicePDFView(FakeHass([invoice()]))
    with pytest.raises(web.HTTPNotFound):
        await view.get(None, "2026", "INV_1")


@pytest.mark.asyncio
async def test_pdf_endpoint_rejects_portal_pdf_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(ats, "_PDF_ROOT", tmp_path)
    (tmp_path / "2026").mkdir()
    (tmp_path / "2026" / "INV_1.pdf").write_bytes(b"%PDF-1.7 TEST")
    view = ats.ATSInvoicePDFView(FakeHass([invoice(pdf_exist=False)]))
    with pytest.raises(web.HTTPNotFound):
        await view.get(None, "2026", "INV_1")


@pytest.mark.asyncio
async def test_clean_install_automatically_registers_card():
    # No Lovelace resource, /config/www copy, or external account required.
    registered = []
    paths = []

    class HTTP:
        async def async_register_static_paths(self, configs):
            paths.extend(configs)

        def register_view(self, view):
            registered.append(view)

    original = ats.add_extra_js_url
    module_urls = []
    ats.add_extra_js_url = lambda hass, url: module_urls.append(url)
    try:
        assert await ats.async_setup(SimpleNamespace(http=HTTP()), {})
    finally:
        ats.add_extra_js_url = original

    assert module_urls == ["/ats_static/invoice-history-card.js?v=0.4.0b6"]
    assert len(paths) == 1
    assert paths[0].url_path == "/ats_static/invoice-history-card.js"
    assert Path(paths[0].path).is_file()
    assert len(registered) == 1
    assert isinstance(registered[0], ats.ATSInvoicePDFView)
