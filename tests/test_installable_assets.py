"""Packaging and sample dashboard smoke tests (no ATS credentials)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "ats"


def test_manifest_and_frontend_asset_in_installed_integration():
    manifest = json.loads((INTEGRATION / "manifest.json").read_text())
    assert manifest["version"] == "0.4.0b8"
    assert {"frontend", "http", "lovelace"} <= set(manifest["dependencies"])

    card = (INTEGRATION / "www" / "invoice-history-card.js").read_text()
    assert 'customElements.define("ats-invoice-history-card"' in card
    assert "this._hass.fetchWithAuth(" in card
    assert "pdf.min.mjs" in card
    assert "anchor.download" in card
    assert 'window.open("about:blank"' not in card


def test_example_cards_are_valid_yaml_and_reference_existing_entities():
    yaml = pytest.importorskip("yaml")
    card = yaml.safe_load((ROOT / "examples" / "ats-card.yaml").read_text())
    assert card["type"] == "vertical-stack"
    assert any(
        c.get("type") == "custom:ats-invoice-history-card"
        and "entity" not in c  # Autodetection: no fixed entity ID
        for c in card["cards"]
    )
    summary = next(c for c in card["cards"] if c.get("type") == "markdown")["content"]
    assert "integration_entities('ats')" in summary
    assert "ats_metric" in summary
    assert "states('sensor.ats_" not in summary
    assert any(
        c.get("tap_action", {}).get("perform_action") == "ats.download_invoices"
        for c in card["cards"]
    )

    dashboard = yaml.safe_load((ROOT / "examples" / "ats-dashboard.yaml").read_text())
    assert dashboard["views"][0]["cards"][0]["type"] == "vertical-stack"


def test_readme_explains_security_and_android_workflow():
    readme = (ROOT / "README.md").read_text()
    assert "/media/ats/fatture/" in readme
    assert "/api/ats/invoice/" in readme
    assert "Apri PDF" in readme
    assert "Scarica PDF" in readme
    assert "www/" in readme
