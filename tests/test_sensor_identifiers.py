"""Guard that HA entity/device identifiers stay stable across the refactor."""
import sys, types, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

try:
    from ats import sensor as sensor_mod
    from ats.const import DOMAIN
    HA = True
except Exception:
    HA = False


class FakeEntry:
    entry_id = "abc123entryid"


class FakeCoordinator:
    data = {"supplies": [], "invoices": [], "readings": [], "supply_numbers": []}
    last_update_success = True
    def async_add_listener(self, *a, **k):
        return lambda: None


# Keys/unique_ids that existing installations already have registered.
EXPECTED_KEYS = {
    "supplies_active", "supplies_total", "invoices_total", "invoices_unpaid",
    "invoices_remaining", "invoices_amount", "invoices_paid",
    "next_expiry_amount", "next_expiry_date", "invoiced_consumption",
    "last_invoice_status", "active_supply_details", "invoice_details",
    "last_reading_value", "last_reading_consumption", "last_reading_date",
    "reading_details",
    "invoices_current_year", "annual_consumption_forecast",
}


@unittest.skipUnless(HA, "Home Assistant not installed")
class TestSensorIdentifiers(unittest.IsolatedAsyncioTestCase):
    async def test_unique_ids_and_device_stable(self):
        hass = types.SimpleNamespace(data={DOMAIN: {FakeEntry.entry_id: FakeCoordinator()}})
        entry = FakeEntry()
        captured = []
        def add(entities):
            captured.extend(entities)
        await sensor_mod.async_setup_entry(hass, entry, add)
        keys = {e._key for e in captured}
        self.assertEqual(keys, EXPECTED_KEYS)
        for e in captured:
            # unique_id must stay entry_id-scoped (entity registry persistence)
            self.assertEqual(e._attr_unique_id, f"{entry.entry_id}_{e._key}")
            # device identifier must stay entry_id-scoped (device registry)
            ids = e._attr_device_info["identifiers"]
            self.assertIn((DOMAIN, entry.entry_id), ids)

        by_key = {e._key: e for e in captured}
        for key, unit in {
            "invoiced_consumption": "m³",
            "last_reading_value": "m³",
            "last_reading_consumption": "m³",
            "annual_consumption_forecast": "m³/anno",
        }.items():
            self.assertEqual(by_key[key]._attr_native_unit_of_measurement, unit)
            self.assertEqual(by_key[key]._attr_suggested_display_precision, 0)
        self.assertEqual(by_key["active_supply_details"]._attr_name, "Dettagli utenze")
        reading_date = by_key["last_reading_date"]
        self.assertIsNone(reading_date._attr_device_class)
        self.assertEqual(reading_date._attr_icon, "mdi:calendar")
        self.assertEqual(reading_date._attr_unique_id, f"{entry.entry_id}_last_reading_date")


if __name__ == "__main__":
    unittest.main()
