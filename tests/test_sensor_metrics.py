"""Regression tests for yearly ATS invoice history and meter-based forecasts."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

try:
    from ats import sensor as sensor_mod
    HA_AVAILABLE = True
except ImportError:
    HA_AVAILABLE = False


def invoice(issued, amount, **extra):
    return {"EmissionDate": issued, "TotalAmount": amount, **extra}


def supply(meter, *, active=True, estimated=142):
    return {
        "MeterNo": meter,
        "Active": active,
        "StateDescription": "Attiva" if active else "Cessata",
        "EstimatedAnnualConsumptyion": estimated,
    }


def reading(meter, when, value, *, effective=True, validation="Positiva"):
    return {
        "MeterNo": meter,
        "Date": when,
        "Value": value,
        "Effective": effective,
        "ValidationResult": validation,
    }


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestAnnualCalculations(unittest.TestCase):
    def setUp(self):
        self.invoices = [
            invoice("2026-08-07T00:00:00", 39.72),
            invoice("2026-05-19T00:00:00", 26.65, PeriodFrom="2025-11-07"),
            invoice("2026-02-16T00:00:00", 45.50),
            invoice("2025-11-24T00:00:00", 105.40, PeriodTo="2026-01-31"),
        ]
        self.supplies = [supply("ACTIVE"), supply("CEASED", active=False, estimated=770)]
        self.readings = [
            reading("ACTIVE", "2026-05-05T00:00:00", 393),
            reading("ACTIVE", "2025-11-06T00:00:00", 340),
            reading("CEASED", "2026-05-05T00:00:00", 999),
            reading("CEASED", "2025-11-06T00:00:00", 100),
        ]

    def test_invoice_total_uses_issue_date_not_billing_period(self):
        self.assertEqual(
            sensor_mod._invoice_total_for_year(self.invoices, 2026), (111.87, 3)
        )
        self.assertEqual(
            sensor_mod._invoice_total_for_year(self.invoices, 2025), (105.4, 1)
        )

    def test_invoice_total_resets_at_year_boundary_and_handles_no_invoices(self):
        self.assertEqual(sensor_mod._invoice_total_for_year(self.invoices, 2027), (0.0, 0))
        self.assertEqual(sensor_mod._invoice_total_for_year([], 2027), (None, 0))

    def test_invoice_total_rejects_incomplete_amount(self):
        invoices = self.invoices + [invoice("2026-10-01T00:00:00", None)]
        self.assertEqual(sensor_mod._invoice_total_for_year(invoices, 2026), (None, 4))

    def test_forecast_only_active_validated_effective_meter(self):
        value, attrs = sensor_mod._annualized_consumption(self.supplies, self.readings)
        self.assertEqual(value, 107.5)
        self.assertEqual(attrs["stima_ats_m3_anno"], 142.0)
        self.assertEqual(attrs["periodo_giorni"], 180)
        self.assertEqual(attrs["consumo_periodo_m3"], 53)
        self.assertEqual(attrs["data_ultima_lettura"], "2026-05-05")
        self.assertEqual(len(attrs["dettaglio_contatori"]), 1)

    def test_invalid_readings_and_same_day_do_not_override_last_pair(self):
        self.readings.extend([
            reading("ACTIVE", "2026-11-05", 999, effective=False),
            reading("ACTIVE", "2026-11-04", 800, validation="Negativa"),
            reading("ACTIVE", "2026-05-05T08:00:00", 393),
        ])
        value, attrs = sensor_mod._annualized_consumption(self.supplies, self.readings)
        self.assertEqual(value, 107.5)
        self.assertEqual(attrs["periodo_giorni"], 180)

    def test_multiple_active_meters_are_summed_without_mixing_readings(self):
        supplies = [supply("A", estimated=120), supply("B", estimated=90)]
        readings = [
            reading("A", "2026-10-11", 110),
            reading("A", "2026-10-01", 100),
            reading("B", "2026-10-11", 210),
            reading("B", "2026-10-01", 200),
        ]
        value, attrs = sensor_mod._annualized_consumption(supplies, readings)
        self.assertEqual(value, 730.0)
        self.assertEqual(attrs["stima_ats_m3_anno"], 210.0)
        self.assertEqual(len(attrs["dettaglio_contatori"]), 2)

    def test_one_missing_meter_pair_does_not_report_partial_total(self):
        supplies = [supply("A"), supply("B")]
        readings = [
            reading("A", "2026-10-11", 110),
            reading("A", "2026-10-01", 100),
            reading("B", "2026-10-11", 210),
        ]
        value, attrs = sensor_mod._annualized_consumption(supplies, readings)
        self.assertIsNone(value)
        self.assertIn("due letture", attrs["nota"])

    def test_no_active_meter_missing_meter_and_negative_rollover(self):
        self.assertIsNone(
            sensor_mod._annualized_consumption([supply("X", active=False)], self.readings)[0]
        )
        self.assertIsNone(
            sensor_mod._annualized_consumption([supply(None)], self.readings)[0]
        )
        neg = [reading("ACTIVE", "2026-05-05", 50), reading("ACTIVE", "2025-11-06", 100)]
        value, attrs = sensor_mod._annualized_consumption([supply("ACTIVE")], neg)
        self.assertIsNone(value)
        self.assertIn("non confrontabili", attrs["nota"])

    def test_none_or_zero_consumption(self):
        only_one = [reading("ACTIVE", "2026-05-05", 393)]
        self.assertIsNone(
            sensor_mod._annualized_consumption([supply("ACTIVE")], only_one)[0]
        )
        flat = [reading("ACTIVE", "2026-05-05", 393),
                reading("ACTIVE", "2025-11-06", 393)]
        self.assertEqual(
            sensor_mod._annualized_consumption([supply("ACTIVE")], flat)[0], 0.0
        )


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestInvoiceHistory(unittest.TestCase):
    def setUp(self):
        self.invoices = [
            invoice("2026-08-07T00:00:00", 20.10, PaidAmount=20.10,
                    ExpirationDate="2026-09-08T00:00:00", StatusText="Pagata"),
            invoice("2026-01-04T00:00:00", 30.20, PaidAmount=0.0,
                    ExpirationDate="2026-02-04T00:00:00", StatusText="Da pagare"),
            invoice("2025-03-03T00:00:00", 10.0, PaidAmount=10.0,
                    ExpirationDate="2025-04-03T00:00:00", PeriodTo="2026-01-31"),
            invoice("2024-06-02T00:00:00", 5.5, PaidAmount=None,
                    ExpirationDate=None),
            invoice(None, 2.0, PaidAmount=2.0, StatusText="Senza data"),
        ]

    def test_group_by_issue_year_with_sorted_dates(self):
        out = sensor_mod._invoice_history(self.invoices)
        yearly = out["riepilogo_annuale"]
        self.assertEqual(list(yearly), ["2026", "2025", "2024"])
        self.assertEqual(yearly["2026"], {
            "numero_fatture": 2, "totale_fatturato": 50.30, "totale_pagato": 20.10
        })
        self.assertEqual(yearly["2025"]["numero_fatture"], 1)
        self.assertEqual(yearly["2025"]["totale_fatturato"], 10.0)
        self.assertEqual(yearly["2024"]["totale_fatturato"], 5.5)
        self.assertIsNone(yearly["2024"]["totale_pagato"])
        self.assertEqual(out["fatture_senza_data_emissione"], 1)
        history = out["storico_fatture"]
        self.assertEqual(len(history), 5)
        self.assertEqual(history[0], {
            "anno": 2026, "numero": None, "pdf_disponibile": False,
            "importo_totale": 20.10,
            "emissione": "07-08-2026", "scadenza": "08-09-2026",
            "stato": "Pagata", "importo_pagato": 20.10,
        })
        self.assertEqual(history[1]["emissione"], "04-01-2026")
        self.assertEqual(history[1]["importo_pagato"], 0.0)
        self.assertEqual(history[-1]["anno"], None)
        self.assertIsNone(history[-1]["emissione"])

    def test_partial_annual_totals_remain_unknown(self):
        items = [
            invoice("2026-08-07", 12.3, PaidAmount=4.5),
            invoice("2026-05-01", None, PaidAmount=None),
            invoice("2025-04-10", 9.0, PaidAmount=9.0),
        ]
        out = sensor_mod._invoice_history(items)["riepilogo_annuale"]
        self.assertEqual(out["2026"]["numero_fatture"], 2)
        self.assertIsNone(out["2026"]["totale_fatturato"])
        self.assertIsNone(out["2026"]["totale_pagato"])
        self.assertEqual(out["2025"]["totale_fatturato"], 9.0)
        self.assertEqual(sensor_mod._invoice_total_for_year(items, 2026), (None, 2))

    def test_invalid_dates_and_non_finite_values_not_included_in_totals(self):
        items = [
            invoice("not-a-date", 12.0, PaidAmount=2),
            invoice("2026-08-01", "nan", PaidAmount="inf"),
        ]
        out = sensor_mod._invoice_history(items)
        self.assertEqual(out["fatture_senza_data_emissione"], 1)
        self.assertEqual(out["storico_fatture"][0]["emissione"], "01-08-2026")
        self.assertIsNone(out["storico_fatture"][0]["importo_totale"])
        self.assertIsNone(out["storico_fatture"][0]["importo_pagato"])
        self.assertIsNone(out["riepilogo_annuale"]["2026"]["totale_fatturato"])
        self.assertIsNone(out["riepilogo_annuale"]["2026"]["totale_pagato"])

    def test_empty_history(self):
        self.assertEqual(sensor_mod._invoice_history([]), {
            "riepilogo_annuale": {},
            "storico_fatture": [],
            "fatture_senza_data_emissione": 0,
        })


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestAnnualSensorValues(unittest.TestCase):
    def test_sensor_current_year_and_forecast_attributes(self):
        class Coordinator:
            data = {
                "invoices": [
                    invoice("2026-08-07", 39.72),
                    invoice("2026-05-19", 26.65),
                    invoice("2026-02-16", 45.50),
                ],
                "supplies": [supply("ACTIVE")],
                "readings": [
                    reading("ACTIVE", "2026-05-05", 393),
                    reading("ACTIVE", "2025-11-06", 340),
                ],
            }
            last_update_success = True
            def async_add_listener(self, *args, **kwargs):
                return lambda: None
        class Entry:
            entry_id = "test-ats"

        annual = sensor_mod.ATSAggregateSensor(
            Coordinator(), Entry(), "invoices_current_year",
            "Totale fatture anno corrente", "invoices_current_year", unit="€"
        )
        forecast = sensor_mod.ATSAggregateSensor(
            Coordinator(), Entry(), "annual_consumption_forecast",
            "Previsione consumo annuo", "annual_consumption_forecast", unit="m³/anno"
        )
        with patch.object(sensor_mod.dt_util, "now", return_value=datetime(2026, 11, 5)):
            self.assertEqual(annual.native_value, 111.87)
        self.assertEqual(annual.extra_state_attributes["anno"], 2026)
        self.assertEqual(annual.extra_state_attributes["numero_fatture"], 3)
        self.assertEqual(forecast.native_value, 107.5)
        self.assertEqual(forecast.extra_state_attributes["stima_ats_m3_anno"], 142.0)

    def test_existing_invoice_sensors_expose_history_and_formatted_dates(self):
        class Coordinator:
            data = {
                "invoices": [
                    invoice("2026-08-07T00:00:00", 20.1, PaidAmount=20.1,
                            ExpirationDate="2026-09-08T00:00:00",
                            StatusText="Pagata"),
                    invoice("2025-05-06T00:00:00", 10.0, PaidAmount=0.0),
                ],
                "supplies": [],
                "readings": [],
            }
            last_update_success = True

            def async_add_listener(self, *args, **kwargs):
                return lambda: None

        class Entry:
            entry_id = "test-ats"

        count = sensor_mod.ATSAggregateSensor(
            Coordinator(), Entry(), "invoices_total",
            "Fatture presenti", "invoice_count"
        )
        detail = sensor_mod.ATSAggregateSensor(
            Coordinator(), Entry(), "invoice_details",
            "Dettagli fatture", "invoice_details"
        )
        self.assertEqual(count.native_value, 2)
        attrs = count.extra_state_attributes
        self.assertEqual(attrs["riepilogo_annuale"]["2026"]["numero_fatture"], 1)
        self.assertEqual(attrs["riepilogo_annuale"]["2026"]["totale_fatturato"], 20.1)
        self.assertEqual(attrs["storico_fatture"][0]["emissione"], "07-08-2026")
        self.assertEqual(attrs["storico_fatture"][0]["scadenza"], "08-09-2026")
        self.assertEqual(detail.native_value, 2)
        legacy = detail.extra_state_attributes["fattura_1"]
        self.assertEqual(legacy["emissione"], "2026-08-07T00:00:00")
        self.assertEqual(legacy["scadenza"], "2026-09-08T00:00:00")
        self.assertEqual(legacy["anno"], 2026)
        self.assertEqual(legacy["emissione_formattata"], "07-08-2026")
        self.assertEqual(legacy["scadenza_formattata"], "08-09-2026")



def _coord(data):
    class Coordinator:
        last_update_success = True
        def async_add_listener(self, *a, **k):
            return lambda: None
    c = Coordinator()
    c.data = data
    return c


class _Entry:
    entry_id = "test-ats"


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestLastReadingDateDisplay(unittest.TestCase):
    def _sensor(self, readings):
        coordinator = _coord({
            "supplies": [], "invoices": [], "readings": readings,
        })
        return sensor_mod.ATSAggregateSensor(
            coordinator, _Entry(), "last_reading_date",
            "Data ultima lettura", "last_reading_date",
        )

    def test_iso_date_displays_day_first_and_keeps_iso_attribute(self):
        sensor = self._sensor([
            reading("METER", "2025-11-06T00:00:00", 340),
            reading("METER", "2026-05-05T00:00:00", 393),
        ])
        self.assertEqual(sensor.native_value, "05-05-2026")
        self.assertEqual(sensor.extra_state_attributes["data_iso"], "2026-05-05")
        self.assertIsNone(sensor._attr_device_class)
        self.assertEqual(sensor._attr_icon, "mdi:calendar")

    def test_day_first_source_uses_same_display_and_iso_date(self):
        sensor = self._sensor([
            reading("METER", "06/11/2025", 340),
            reading("METER", "05/05/2026 08:30:00", 393),
        ])
        self.assertEqual(sensor.native_value, "05-05-2026")
        self.assertEqual(sensor.extra_state_attributes["data_iso"], "2026-05-05")

    def test_missing_and_invalid_readings_remain_unknown(self):
        missing = self._sensor([])
        self.assertIsNone(missing.native_value)
        self.assertIn("nota", missing.extra_state_attributes)
        invalid = self._sensor([reading("METER", "not-a-date", 393)])
        self.assertIsNone(invalid.native_value)
        self.assertIsNone(invalid.extra_state_attributes["data_iso"])


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestDateParsingFallback(unittest.TestCase):
    def test_iso_is_primary(self):
        self.assertEqual(sensor_mod._date("2026-05-05T00:00:00"), datetime(2026, 5, 5))
        self.assertEqual(sensor_mod._date("2026-05-07"), datetime(2026, 5, 7))

    def test_day_first_slash_and_dash(self):
        self.assertEqual(sensor_mod._date("05/05/2026"), datetime(2026, 5, 5))
        self.assertEqual(sensor_mod._date("05-05-2026"), datetime(2026, 5, 5))
        # Day-first, not month-first.
        self.assertEqual(sensor_mod._date("07/08/2026"), datetime(2026, 8, 7))
        self.assertEqual(sensor_mod._date("07-08-2026"), datetime(2026, 8, 7))

    def test_day_first_with_time(self):
        self.assertEqual(
            sensor_mod._date("05/05/2026 08:30:00"), datetime(2026, 5, 5, 8, 30)
        )

    def test_invalid_and_empty(self):
        for bad in ("not-a-date", "", None, "99/99/9999"):
            self.assertIsNone(sensor_mod._date(bad))

    def test_display_and_history_with_day_first_source(self):
        self.assertEqual(sensor_mod._display_date("05/05/2026"), "05-05-2026")
        out = sensor_mod._invoice_history([invoice("07/08/2026", 10.0)])
        self.assertEqual(out["riepilogo_annuale"]["2026"]["numero_fatture"], 1)
        self.assertEqual(out["storico_fatture"][0]["emissione"], "07-08-2026")


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestNextExpiryFutureOnly(unittest.TestCase):
    def _value(self, metric, invoices, now):
        sensor = sensor_mod.ATSAggregateSensor(
            _coord({"invoices": invoices, "supplies": [], "readings": []}),
            _Entry(), metric, metric, metric,
        )
        with patch.object(sensor_mod.dt_util, "now", return_value=now):
            return sensor.native_value

    def test_picks_earliest_future_not_overdue(self):
        invoices = [
            invoice("2026-01-01", 10.0, ExpirationDate="2026-02-01T00:00:00",
                    RemainingAmount=10.0),  # overdue
            invoice("2026-06-01", 20.0, ExpirationDate="2026-12-01T00:00:00",
                    RemainingAmount=20.0),  # future
            invoice("2026-06-02", 30.0, ExpirationDate="2026-11-20T00:00:00",
                    RemainingAmount=30.0),  # nearer future
        ]
        from datetime import date as _d
        self.assertEqual(
            self._value("next_expiry_date", invoices, datetime(2026, 11, 6)),
            _d(2026, 11, 20),
        )
        self.assertEqual(
            self._value("next_expiry_amount", invoices, datetime(2026, 11, 6)), 30.0
        )

    def test_all_overdue_returns_none(self):
        invoices = [invoice("2026-01-01", 10.0, ExpirationDate="2026-02-01T00:00:00")]
        self.assertIsNone(
            self._value("next_expiry_date", invoices, datetime(2026, 11, 6))
        )

    def test_due_today_counts_as_future(self):
        invoices = [invoice("2026-10-01", 5.0, ExpirationDate="2026-11-06T00:00:00")]
        from datetime import date as _d
        self.assertEqual(
            self._value("next_expiry_date", invoices, datetime(2026, 11, 6)),
            _d(2026, 11, 6),
        )


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestEmptyVsUnknownCounts(unittest.TestCase):
    def _nv(self, metric, data):
        return sensor_mod.ATSAggregateSensor(
            _coord(data), _Entry(), metric, metric, metric
        ).native_value

    def test_empty_list_is_zero(self):
        empty = {"supplies": [], "invoices": [], "readings": []}
        self.assertEqual(self._nv("total_supplies", empty), 0)
        self.assertEqual(self._nv("invoice_count", empty), 0)
        self.assertEqual(self._nv("supply_details", empty), 0)
        self.assertEqual(self._nv("invoice_details", empty), 0)

    def test_no_data_is_unknown(self):
        for metric in ("total_supplies", "invoice_count", "supply_details", "invoice_details"):
            self.assertIsNone(self._nv(metric, None))


if __name__ == "__main__":
    unittest.main()
