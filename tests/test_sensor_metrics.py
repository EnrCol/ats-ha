"""Regression tests for current-year invoices and meter-based annual forecast."""
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
        self.assertEqual(sensor_mod._invoice_total_for_year(invoices, 2026), (None, 3))

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


if __name__ == "__main__":
    unittest.main()
