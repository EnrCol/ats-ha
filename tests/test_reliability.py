"""Independent regression tests for ATS 0.3.x fixes."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

from homeassistant.const import MATCH_ALL

from custom_components.ats.sensor import ATSAggregateSensor, _date


def _sensor(metric, invoices=None, supplies=None):
    coordinator = SimpleNamespace(
        data={"invoices": invoices or [], "supplies": supplies or [], "readings": []},
        last_update_success=True,
        async_add_listener=lambda *a, **kw: (lambda: None),
    )
    return ATSAggregateSensor(
        coordinator, SimpleNamespace(entry_id="unchanged-entry-id"),
        metric, metric, metric,
    )


def test_paid_flag_precedence():
    s = _sensor("unpaid_count", [
        {"Payed": True, "ToPay": True, "StatusText": "Non pagata"},
        {"Payed": False, "ToPay": True},
        {"Payed": True, "ToPay": False},
    ])
    assert s.native_value == 1


def test_invoice_details_preserve_raw_portal_flag():
    s = _sensor("invoice_details", [{"Payed": True, "ToPay": True}])
    assert s.native_value == 1
    attrs = s.extra_state_attributes["fattura_1"]
    assert attrs["pagata"] is True
    assert attrs["da_pagare"] is False
    assert attrs["da_pagare_ats"] is True


def test_next_expiry_excludes_past_and_paid():
    now = datetime(2026, 11, 9)
    invoices = [
        {"Payed": False, "ToPay": True, "ExpirationDate": (now - timedelta(days=3)).isoformat(), "RemainingAmount": 99},
        {"Payed": True, "ToPay": True, "ExpirationDate": (now + timedelta(days=1)).isoformat(), "RemainingAmount": 40},
        {"Payed": False, "ToPay": True, "ExpirationDate": (now + timedelta(days=7)).isoformat(), "RemainingAmount": 20},
    ]
    with patch("custom_components.ats.sensor.dt_util.now", return_value=now):
        assert _sensor("next_expiry_amount", invoices).native_value == 20


def test_portal_day_first_and_iso_dates():
    assert _date("2026-05-05T00:00:00").date().isoformat() == "2026-05-05"
    assert _date("05/05/2026").date().isoformat() == "2026-05-05"
    assert _date("05-05-2026").date().isoformat() == "2026-05-05"
    assert _date("not a date") is None


def test_empty_api_lists_mean_zero_when_loaded():
    assert _sensor("total_supplies").native_value == 0
    assert _sensor("invoice_count").native_value == 0


def test_privacy_does_not_remove_current_attributes_or_state_class():
    s = _sensor("invoice_details", [{"No": "TEST", "Payed": True}])
    assert s.native_value == 1
    assert s.extra_state_attributes["fattura_1"]["pagata"] is True
    assert s._unrecorded_attributes == frozenset({MATCH_ALL})
    assert s.unique_id == "unchanged-entry-id_invoice_details"
    assert _sensor("unpaid_count").state_class is not None
