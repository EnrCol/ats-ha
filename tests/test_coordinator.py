"""Coordinator behaviour tests with a fake aiohttp session (no network).

Fictional identifiers only. Requires Home Assistant to import the coordinator.
"""

from __future__ import annotations

import sys
import unittest
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components"))

try:
    from ats import coordinator as coord
    from ats.auth import ATSDiscoveryError
    from homeassistant.exceptions import ConfigEntryAuthFailed
    from homeassistant.helpers.update_coordinator import UpdateFailed
    HA_AVAILABLE = True
except Exception:  # pragma: no cover - skipped when HA not installed
    HA_AVAILABLE = False

FAKE_AT = "00000000-1111-2222-3333-444444444444"
FAKE_AT2 = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FAKE_CS = "C12345678"
BASE = "https://sgc.altotrevigianoservizi.it"


def home_html(at):
    return (
        "<script>sol.conf = {"
        "solSessionId: 'sid1234', "
        f"solUserAT: '{at}', solUserCS: '{FAKE_CS}', "
        "solUserAId: '99999999-8888-7777-6666-555555555555', "
        "solUserEmail: 'TEST@EXAMPLE.COM'};</script>"
    )


def supply(no, active=True, state="Attiva"):
    return {"SupplyNo": no, "Active": active, "StateDescription": state,
            "SupplyType": 2, "Service": "Solo servizio acqua"}


class FakeResp:
    def __init__(self, status, *, json_data=None, text=""):
        self.status = status
        self._json = json_data
        self._text = text

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def text(self):
        return self._text

    async def json(self, content_type=None):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def raise_for_status(self):
        if self.status >= 400:
            import aiohttp
            raise aiohttp.ClientResponseError(None, (), status=self.status)


class FakeCookieJar:
    def clear(self):
        pass


class FakeAiohttpSession:
    """Routes GET by URL substring. ``script`` maps a list of queued responses."""

    def __init__(self, routes):
        self.routes = routes
        self.closed = False
        self.cookie_jar = FakeCookieJar()
        self.get_log = []

    def get(self, url, headers=None, allow_redirects=True, **kw):
        self.get_log.append(url)
        for key, resp in self.routes.items():
            if key in url:
                r = resp() if callable(resp) else resp
                return r
        return FakeResp(404, text="not found")

    async def close(self):
        self.closed = True


def make_coordinator(hass, **kw):
    """Build a coordinator WITHOUT DataUpdateCoordinator.__init__.

    The HA base class needs the frame helper / a config entry, which is out of
    scope for these unit tests. We replicate exactly the attribute setup our
    own __init__ performs and reuse decide_mode so there is no drift.
    """
    import logging
    d = dict(
        base_url=BASE, supply_path="", invoice_path="", reading_path="",
        cookie="", username="user", password="pw",
    )
    d.update(kw)
    c = coord.ATSCoordinator.__new__(coord.ATSCoordinator)
    c.hass = hass
    c.logger = logging.getLogger("ats.test")
    c.base_url = d["base_url"]
    c.supply_path = d["supply_path"]
    c.invoice_path = d["invoice_path"]
    c.reading_path = d["reading_path"]
    c.cookie = d["cookie"]
    c.username = d["username"]
    c.password = d["password"]
    c.mode = coord.decide_mode(d["username"], d["password"], d["supply_path"])
    c._authenticated = False
    c._session = None
    c._session_token = None
    c._customer_code = None
    return c


class FakeHass:
    class _Loop:
        def time(self):
            return 0.0
    def __init__(self):
        self.loop = self._Loop()
        self.data = {}
        self.config_entries = None


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestCoordinatorAuto(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hass = FakeHass()

    async def _run(self, routes, **kw):
        c = make_coordinator(self.hass, **kw)
        c._session = FakeAiohttpSession(routes)
        # Bypass async_login network: stub it to just mark success.
        async def fake_login(session, base_url, username, password):
            return None
        import ats.coordinator as m
        orig = m.async_login
        m.async_login = fake_login
        try:
            data = await c._async_update_data()
        finally:
            m.async_login = orig
        return c, data

    async def test_mode_auto_selected(self):
        c = make_coordinator(self.hass)
        self.assertEqual(c.mode, coord.MODE_AUTO)

    async def test_multiple_supplies(self):
        routes = {
            "index.aspx": FakeResp(200, text=home_html(FAKE_AT)),
            "supply-light": FakeResp(200, json_data=[supply("CNT111-1"),
                                                     supply("CNT222-1", active=False, state="Cessata")]),
            "/invoice/": FakeResp(200, json_data=[{"No": "F1"}]),
            "reading-base": FakeResp(200, json_data=[{"Value": "10"}]),
        }
        _, data = await self._run(routes)
        self.assertEqual(data["supply_numbers"], ["CNT111-1", "CNT222-1"])
        self.assertEqual(len(data["supplies"]), 2)
        self.assertEqual(len(data["invoices"]), 1)
        self.assertEqual(len(data["readings"]), 1)

    async def test_single_supply(self):
        routes = {
            "index.aspx": FakeResp(200, text=home_html(FAKE_AT)),
            "supply-light": FakeResp(200, json_data=[supply("CNT111-1")]),
            "/invoice/": FakeResp(200, json_data=[]),
            "reading-base": FakeResp(200, json_data=[]),
        }
        _, data = await self._run(routes)
        self.assertEqual(data["supply_numbers"], ["CNT111-1"])
        self.assertEqual(data["invoices"], [])
        self.assertEqual(data["readings"], [])

    async def test_zero_supplies(self):
        routes = {
            "index.aspx": FakeResp(200, text=home_html(FAKE_AT)),
            "supply-light": FakeResp(200, json_data=[]),
            "/invoice/": FakeResp(200, json_data=[]),
            "reading-base": FakeResp(200, json_data=[]),
        }
        _, data = await self._run(routes)
        self.assertEqual(data["supply_numbers"], [])
        self.assertEqual(data["supplies"], [])

    async def test_discovery_failure_raises_updatefailed(self):
        routes = {
            "index.aspx": FakeResp(200, text="<html>no sol.conf</html>"),
            "supply-light": FakeResp(200, json_data=[]),
        }
        c = make_coordinator(self.hass)
        c._session = FakeAiohttpSession(routes)
        import ats.coordinator as m
        async def fake_login(*a):
            return None
        orig = m.async_login
        m.async_login = fake_login
        try:
            with self.assertRaises(UpdateFailed):
                await c._async_update_data()
        finally:
            m.async_login = orig

    async def test_session_renewed_with_new_token(self):
        # First supply-light returns 401 -> relogin -> discovery yields a new
        # token -> second attempt must use the NEW token in the URL.
        state = {"supply_calls": 0, "login_calls": 0}
        home_seq = [home_html(FAKE_AT), home_html(FAKE_AT2)]

        def index_resp():
            html = home_seq[min(state["login_calls"], len(home_seq) - 1)]
            return FakeResp(200, text=html)

        def supply_resp():
            state["supply_calls"] += 1
            if state["supply_calls"] == 1:
                return FakeResp(401)
            return FakeResp(200, json_data=[supply("CNT111-1")])

        routes = {
            "index.aspx": index_resp,
            "supply-light": supply_resp,
            "/invoice/": FakeResp(200, json_data=[]),
            "reading-base": FakeResp(200, json_data=[]),
        }
        c = make_coordinator(self.hass)
        c._session = FakeAiohttpSession(routes)
        import ats.coordinator as m
        async def fake_login(*a):
            state["login_calls"] += 1
            return None
        orig = m.async_login
        m.async_login = fake_login
        try:
            data = await c._async_update_data()
        finally:
            m.async_login = orig
        self.assertEqual(data["supply_numbers"], ["CNT111-1"])
        # The second supply-light request must carry the renewed token.
        supply_urls = [u for u in c._session.get_log if "supply-light" in u]
        self.assertTrue(any(FAKE_AT2 in u for u in supply_urls))
        self.assertGreaterEqual(state["login_calls"], 2)

    async def test_invalid_credentials_raises_auth_failed(self):
        c = make_coordinator(self.hass)
        c._session = FakeAiohttpSession({"index.aspx": FakeResp(200, text=home_html(FAKE_AT))})
        import ats.coordinator as m
        async def bad_login(*a):
            from ats.auth import ATSInvalidCredentials
            raise ATSInvalidCredentials("no")
        orig = m.async_login
        m.async_login = bad_login
        try:
            with self.assertRaises(ConfigEntryAuthFailed):
                await c._async_update_data()
        finally:
            m.async_login = orig


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestTokenNeverLeaks(unittest.IsolatedAsyncioTestCase):
    """The AT is a credential in the URL path: it must never reach diagnostics."""

    def setUp(self):
        self.hass = FakeHass()

    async def _login_patch(self):
        import ats.coordinator as m
        async def fake_login(*a):
            return None
        self._orig = m.async_login
        m.async_login = fake_login
        return m

    async def _restore(self, m):
        m.async_login = self._orig

    async def test_http_error_message_has_no_token(self):
        routes = {
            "index.aspx": FakeResp(200, text=home_html(FAKE_AT)),
            "supply-light": FakeResp(500, text="boom"),
        }
        c = make_coordinator(self.hass)
        c._session = FakeAiohttpSession(routes)
        m = await self._login_patch()
        try:
            with self.assertRaises(UpdateFailed) as ctx:
                await c._async_update_data()
        finally:
            await self._restore(m)
        self.assertNotIn(FAKE_AT, str(ctx.exception))
        self.assertNotIn(FAKE_CS, str(ctx.exception))

    async def test_auth_refused_after_relogin_message_has_no_token(self):
        routes = {
            "index.aspx": FakeResp(200, text=home_html(FAKE_AT)),
            "supply-light": FakeResp(401),  # always 401 -> relogin -> still 401
        }
        c = make_coordinator(self.hass)
        c._session = FakeAiohttpSession(routes)
        m = await self._login_patch()
        try:
            with self.assertRaises(UpdateFailed) as ctx:
                await c._async_update_data()
        finally:
            await self._restore(m)
        self.assertNotIn(FAKE_AT, str(ctx.exception))

    async def test_requested_urls_carry_token_but_diagnostics_do_not(self):
        # Sanity: the token IS in the request URL (needed), proving the
        # leak-tests above are meaningful.
        routes = {
            "index.aspx": FakeResp(200, text=home_html(FAKE_AT)),
            "supply-light": FakeResp(200, json_data=[supply("CNT1-1")]),
            "/invoice/": FakeResp(200, json_data=[]),
            "reading-base": FakeResp(200, json_data=[]),
        }
        c = make_coordinator(self.hass)
        c._session = FakeAiohttpSession(routes)
        m = await self._login_patch()
        try:
            await c._async_update_data()
        finally:
            await self._restore(m)
        self.assertTrue(any(FAKE_AT in u for u in c._session.get_log))


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestModeTransitions(unittest.TestCase):
    """decide_mode must keep existing installs on their current mode."""

    def test_new_install_auto(self):
        self.assertEqual(coord.decide_mode("u", "p", ""), coord.MODE_AUTO)

    def test_beta_credentials_with_paths(self):
        self.assertEqual(
            coord.decide_mode("u", "p", "/webapi/api/v1/supply-light/x/C1/1/"),
            coord.MODE_CREDENTIALS,
        )

    def test_legacy_cookie_no_credentials(self):
        self.assertEqual(coord.decide_mode(None, None, "/x/"), coord.MODE_COOKIE)
        self.assertEqual(coord.decide_mode("", "", "/x/"), coord.MODE_COOKIE)

    def test_password_without_username_is_cookie(self):
        # Half credentials never silently become auto/credentials.
        self.assertEqual(coord.decide_mode("", "p", ""), coord.MODE_COOKIE)

    def test_user_opts_into_auto_by_clearing_supply_path(self):
        # An existing credentials install that clears its manual supply path
        # (via options) transitions cleanly to auto on reload.
        before = coord.decide_mode("u", "p", "/webapi/api/v1/supply-light/x/C1/1/")
        after = coord.decide_mode("u", "p", "")
        self.assertEqual(before, coord.MODE_CREDENTIALS)
        self.assertEqual(after, coord.MODE_AUTO)


@unittest.skipUnless(HA_AVAILABLE, "Home Assistant not installed")
class TestCoordinatorModes(unittest.TestCase):
    def setUp(self):
        self.hass = FakeHass()

    def test_cookie_mode(self):
        c = make_coordinator(self.hass, username=None, password=None,
                             cookie="x", supply_path="/s/", invoice_path="/i/")
        self.assertEqual(c.mode, coord.MODE_COOKIE)

    def test_credentials_manual_mode(self):
        c = make_coordinator(self.hass, supply_path="/webapi/api/v1/supply-light/{session_uuid}/C1/1/",
                             invoice_path="/webapi/api/v1/invoice/{session_uuid}/-1/0/0/")
        self.assertEqual(c.mode, coord.MODE_CREDENTIALS)

    def test_credentials_literal_paths_skip_discovery(self):
        c = make_coordinator(
            self.hass,
            supply_path="/webapi/static/supplies/",
            invoice_path="/webapi/static/invoices/",
            reading_path="/webapi/static/readings/",
        )
        self.assertEqual(c.mode, coord.MODE_CREDENTIALS)
        self.assertFalse(c._credentials_paths_need_token())

    def test_credentials_reading_fallback_requires_discovery(self):
        c = make_coordinator(
            self.hass,
            supply_path="/webapi/static/supplies/",
            invoice_path="/webapi/static/invoices/",
            reading_path="",
        )
        self.assertTrue(c._credentials_paths_need_token())

    def test_credentials_tokenized_path_requires_discovery(self):
        c = make_coordinator(
            self.hass,
            supply_path="/webapi/api/v1/supply-light/{session_uuid}/C123/1/",
            invoice_path="/webapi/static/invoices/",
            reading_path="/webapi/static/readings/",
        )
        self.assertTrue(c._credentials_paths_need_token())

    def test_extract_supply_numbers_dedup_and_skip_bad(self):
        out = coord.extract_supply_numbers(
            [supply("CNT111-1"), supply("CNT111-1"),
             {"SupplyNo": " CNT111-1 "}, {"SupplyNo": None},
             {"SupplyNo": " CNT222-1 "}, {"SupplyNo": "CNT222-1"},
             {"nofield": 1}]
        )
        self.assertEqual(out, ["CNT111-1", "CNT222-1"])


if __name__ == "__main__":
    unittest.main()
