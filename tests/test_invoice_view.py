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
async def test_clean_install_registers_lovelace_resource():
    from unittest.mock import AsyncMock, create_autospec
    paths = []
    views = []
    fallback = []

    class HTTP:
        async def async_register_static_paths(self, cfg):
            paths.extend(cfg)
        def register_view(self, item):
            views.append(item)

    collection = create_autospec(ats.ResourceStorageCollection, instance=True)
    collection.async_get_info = AsyncMock(return_value={"resources": 0})
    collection.async_items.return_value = []
    collection.async_create_item = AsyncMock(return_value={"id": "resource1"})
    hass = SimpleNamespace(
        http=HTTP(), data={ats.LOVELACE_DATA: SimpleNamespace(resources=collection)}
    )
    original = ats.add_extra_js_url
    ats.add_extra_js_url = lambda hass, url: fallback.append(url)
    try:
        assert await ats.async_setup(hass, {})
    finally:
        ats.add_extra_js_url = original

    collection.async_create_item.assert_awaited_once_with({
        "res_type": "module",
        "url": "/ats_static/invoice-history-card.js?v=0.4.0b7",
    })
    assert not fallback
    assert len(paths) == 1
    assert paths[0].url_path == "/ats_static/invoice-history-card.js"
    assert Path(paths[0].path).is_file()
    assert isinstance(views[0], ats.ATSInvoicePDFView)


@pytest.mark.asyncio
async def test_lovelace_resource_idempotent():
    from unittest.mock import AsyncMock, create_autospec
    class HTTP:
        async def async_register_static_paths(self, paths):
            pass
        def register_view(self, view):
            pass
    collection = create_autospec(ats.ResourceStorageCollection, instance=True)
    collection.async_get_info = AsyncMock(return_value={"resources": 1})
    collection.async_items.return_value = [{
        "id": "same", "type": "module",
        "url": "/ats_static/invoice-history-card.js?v=0.4.0b7",
    }]
    collection.async_create_item = AsyncMock()
    hass = SimpleNamespace(
        http=HTTP(), data={ats.LOVELACE_DATA: SimpleNamespace(resources=collection)}
    )
    assert await ats.async_setup(hass, {})
    collection.async_create_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_yaml_lovelace_fallback_registers_frontend_module():
    class HTTP:
        async def async_register_static_paths(self, paths):
            pass
        def register_view(self, view):
            pass
    hass = SimpleNamespace(
        http=HTTP(), data={ats.LOVELACE_DATA: SimpleNamespace(resources=object())}
    )
    urls = []
    original = ats.add_extra_js_url
    ats.add_extra_js_url = lambda hass, url: urls.append(url)
    try:
        assert await ats.async_setup(hass, {})
    finally:
        ats.add_extra_js_url = original
    assert urls == ["/ats_static/invoice-history-card.js?v=0.4.0b7"]
