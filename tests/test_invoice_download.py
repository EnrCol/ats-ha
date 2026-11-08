"""Regression tests for ATS's private invoice downloader (no ATS network)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "custom_components"))

from ats import invoice_download as pdf


@pytest.mark.parametrize(
    ("raw", "wanted"),
    [
        ("SUPPLY_1", "SUPPLY_1"),
        (["SUPPLY_1"], "SUPPLY_1"),
        (("SUPPLY_1",), "SUPPLY_1"),
        ([], ""),
        (["A", "B"], ""),
        (None, ""),
        (17, ""),
    ],
)
def test_supply_number_accepts_a_single_item_array(raw, wanted):
    assert pdf._supply_code({"SupplyNo": raw}) == wanted


def test_identity_uses_no_and_emission_year():
    inv = {
        "No": "INV_100",
        "Id": "WRONG",
        "SupplyNo": ["SUPPLY_1"],
        "EmissionDate": "2026-05-19T00:00:00",
        "PdfExist": True,
    }
    assert pdf._invoice_identity(inv) == ("INV_100", "SUPPLY_1", 2026)


@pytest.mark.parametrize(
    "field,value",
    [
        ("No", "../oops"),
        ("No", "invoice 1"),
        ("SupplyNo", []),
        ("SupplyNo", ["X", "Y"]),
        ("EmissionDate", ""),
        ("EmissionDate", "bad-date"),
    ],
)
def test_identity_rejects_unsafe_or_incomplete_data(field, value):
    inv = {
        "No": "INV_1",
        "SupplyNo": ["SUPPLY_1"],
        "EmissionDate": "2026-01-10T00:00:00",
    }
    inv[field] = value
    with pytest.raises(pdf.ATSInvoiceDownloadError):
        pdf._invoice_identity(inv)


def test_signed_url_is_bound_to_the_original_https_origin():
    base = "https://sgc.altotrevigianoservizi.it"
    path = (
        "/webapi/visualizza-bolletta.aspx?"
        "username=u&timestamp=123&invoice=inv&hash=abc"
    )
    assert pdf._signed_download_url(base, path) == base + path

    for bad in (
        "https://example.net" + path,
        "http://sgc.altotrevigianoservizi.it" + path,
        "/other/path?" + path.split("?", 1)[1],
        "/webapi/visualizza-bolletta.aspx?username=u&invoice=inv&hash=abc",
    ):
        with pytest.raises(pdf.ATSInvoiceDownloadError):
            pdf._signed_download_url(base, bad)


def test_store_pdf_is_atomic_and_does_not_overwrite(tmp_path):
    dest = tmp_path / "2026" / "INV_1.pdf"
    assert pdf._store_pdf(dest, b"%PDF-1.7 TEST")
    assert dest.read_bytes() == b"%PDF-1.7 TEST"
    assert pdf._store_pdf(dest, b"%PDF-1.7 REPLACEMENT") is False
    assert dest.read_bytes() == b"%PDF-1.7 TEST"
    assert not list(dest.parent.glob("*.part"))
