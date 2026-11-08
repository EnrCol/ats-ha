"""Config-flow validation tests. Fictional data only; no real network."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

try:
    from ats import config_flow as cf
    from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
    HA_AVAILABLE = True
except Exception:  # pragma: no cover
    HA_AVAILABLE = False

BASE = "https://sgc.altotrevigianoservizi.it"


def base_data(**kw):
    d = {
        cf.CONF_BASE_URL: BASE,
        cf.CONF_SCAN_INTERVAL: 60,
    }
    d.update(kw)
    return d


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestValidateInput(unittest.TestCase):
    def test_auto_no_paths_ok(self):
        data = base_data(**{CONF_USERNAME: "u", CONF_PASSWORD: "p"})
        self.assertIsNone(cf._validate_input(data))

    def test_cookie_requires_paths(self):
        data = base_data(**{cf.CONF_COOKIE: "c"})
        self.assertEqual(cf._validate_input(data), "invalid_path")

    def test_cookie_with_paths_ok(self):
        data = base_data(**{
            cf.CONF_COOKIE: "c",
            cf.CONF_SUPPLY_PATH: "/webapi/api/v1/supply-light/x/C1/1/",
            cf.CONF_INVOICE_PATH: "/webapi/api/v1/invoice/x/-1/0/0/",
        })
        self.assertIsNone(cf._validate_input(data))

    def test_credentials_with_partial_paths_invalid(self):
        # Supply path present -> credentials/manual mode -> invoice required too.
        data = base_data(**{
            CONF_USERNAME: "u", CONF_PASSWORD: "p",
            cf.CONF_SUPPLY_PATH: "/webapi/api/v1/supply-light/{session_uuid}/C1/1/",
        })
        self.assertEqual(cf._validate_input(data), "invalid_path")

    def test_malformed_path_rejected_even_in_auto(self):
        data = base_data(**{
            CONF_USERNAME: "u", CONF_PASSWORD: "p",
            cf.CONF_READING_PATH: "no-leading-slash",
        })
        self.assertEqual(cf._validate_input(data), "invalid_path")

    def test_missing_password(self):
        data = base_data(**{CONF_USERNAME: "u"})
        self.assertEqual(cf._validate_input(data), "missing_credentials")

    def test_no_auth_at_all(self):
        data = base_data()
        self.assertEqual(cf._validate_input(data), "missing_auth")

    def test_username_non_default_host_rejected(self):
        data = base_data(**{
            CONF_USERNAME: "u", CONF_PASSWORD: "p",
            cf.CONF_BASE_URL: "https://evil.example.com",
        })
        self.assertEqual(cf._validate_input(data), "invalid_url")

    def test_bad_interval(self):
        data = base_data(**{CONF_USERNAME: "u", CONF_PASSWORD: "p",
                            cf.CONF_SCAN_INTERVAL: 99999})
        self.assertEqual(cf._validate_input(data), "invalid_interval")


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestValidatePortalCredentials(unittest.IsolatedAsyncioTestCase):
    async def _patch(self, login_exc=None, discover_exc=None):
        async def fake_login(session, base, u, p):
            if login_exc:
                raise login_exc
        async def fake_discover(session, base):
            if discover_exc:
                raise discover_exc
            return ("00000000-1111-2222-3333-444444444444", "C1")
        cf.async_login = fake_login
        cf.async_discover_identifiers = fake_discover

    async def test_ok_auto(self):
        from ats.auth import async_login, async_discover_identifiers
        await self._patch()
        try:
            self.assertIsNone(await cf._validate_portal_credentials("u", "p", discover=True))
        finally:
            cf.async_login, cf.async_discover_identifiers = async_login, async_discover_identifiers

    async def test_invalid_auth(self):
        from ats.auth import ATSInvalidCredentials, async_login, async_discover_identifiers
        await self._patch(login_exc=ATSInvalidCredentials("x"))
        try:
            self.assertEqual(
                await cf._validate_portal_credentials("u", "p", discover=True), "invalid_auth")
        finally:
            cf.async_login, cf.async_discover_identifiers = async_login, async_discover_identifiers

    async def test_discovery_failed(self):
        from ats.auth import ATSDiscoveryError, async_login, async_discover_identifiers
        await self._patch(discover_exc=ATSDiscoveryError("x"))
        try:
            self.assertEqual(
                await cf._validate_portal_credentials("u", "p", discover=True), "discovery_failed")
        finally:
            cf.async_login, cf.async_discover_identifiers = async_login, async_discover_identifiers

    async def test_cannot_connect(self):
        from ats.auth import ATSLoginError, async_login, async_discover_identifiers
        await self._patch(login_exc=ATSLoginError("x"))
        try:
            self.assertEqual(
                await cf._validate_portal_credentials("u", "p", discover=True), "cannot_connect")
        finally:
            cf.async_login, cf.async_discover_identifiers = async_login, async_discover_identifiers

    async def test_no_discovery_when_manual(self):
        # discover=False must not call discovery at all.
        from ats.auth import async_login, async_discover_identifiers
        called = {"d": False}
        async def fake_login(session, base, u, p):
            pass
        async def fake_discover(session, base):
            called["d"] = True
            return ("x", "y")
        cf.async_login, cf.async_discover_identifiers = fake_login, fake_discover
        try:
            self.assertIsNone(await cf._validate_portal_credentials("u", "p", discover=False))
            self.assertFalse(called["d"])
        finally:
            cf.async_login, cf.async_discover_identifiers = async_login, async_discover_identifiers


if __name__ == "__main__":
    unittest.main()
