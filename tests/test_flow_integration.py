"""End-to-end config flow using the HA test harness. Fictional data only."""
import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ats.const import (
    DOMAIN, CONF_BASE_URL, CONF_SUPPLY_PATH, CONF_INVOICE_PATH,
    CONF_READING_PATH, CONF_COOKIE, CONF_SCAN_INTERVAL, DEFAULT_BASE_URL,
)

FAKE_AT = "00000000-1111-2222-3333-444444444444"


@pytest.fixture
def patch_validate(monkeypatch):
    async def ok_login(session, base, u, p):
        return None
    async def ok_discover(session, base):
        return (FAKE_AT, "C1")
    monkeypatch.setattr("custom_components.ats.config_flow.async_login", ok_login)
    monkeypatch.setattr("custom_components.ats.config_flow.async_discover_identifiers", ok_discover)


async def test_auto_flow_creates_entry(hass, patch_validate):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_USERNAME: "user",
            CONF_PASSWORD: "pw",
            CONF_SCAN_INTERVAL: 60,
        },
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    entry = result["result"]
    # unique_id preserved (single customer per instance), not derived/changed.
    assert entry.unique_id == "ats_portal"
    assert entry.data[CONF_USERNAME] == "user"
    assert entry.data.get(CONF_SUPPLY_PATH, "") == ""
    assert entry.data.get(CONF_INVOICE_PATH, "") == ""


async def test_second_entry_aborts(hass, patch_validate):
    # First entry
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    await hass.config_entries.flow.async_configure(
        r["flow_id"],
        {CONF_USERNAME: "u", CONF_PASSWORD: "p", CONF_SCAN_INTERVAL: 60},
    )
    # Second entry must abort (one instance)
    r2 = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r2 = await hass.config_entries.flow.async_configure(
        r2["flow_id"],
        {CONF_USERNAME: "u", CONF_PASSWORD: "p", CONF_SCAN_INTERVAL: 60},
    )
    assert r2["type"] == FlowResultType.ABORT


async def test_new_user_form_has_only_three_fields(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert {field.schema for field in result["data_schema"].schema} == {
        CONF_USERNAME, CONF_PASSWORD, CONF_SCAN_INTERVAL
    }


async def test_coordinator_accepts_config_entry(hass):
    """The coordinator must construct on the running HA version with config_entry
    passed through to DataUpdateCoordinator (required from HA 2026.8)."""
    from datetime import timedelta
    from custom_components.ats.coordinator import ATSCoordinator, MODE_AUTO
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    c = ATSCoordinator(
        hass=hass,
        base_url=DEFAULT_BASE_URL,
        supply_path="",
        invoice_path="",
        reading_path="",
        cookie="",
        update_interval=timedelta(minutes=60),
        username="u",
        password="p",
        config_entry=entry,
    )
    assert c.mode == MODE_AUTO
    assert c.config_entry is entry
