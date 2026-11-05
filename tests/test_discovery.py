"""Offline tests for ATS account discovery and URL building.

No real accounts, cookies or network requests. All identifiers are fictional.
auth.py has no Home Assistant dependency, so it is loaded directly.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

AUTH_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "ats" / "auth.py"
spec = importlib.util.spec_from_file_location("ats_auth_tested_disc", AUTH_PATH)
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)

# Fully fictional identifiers.
FAKE_AT = "00000000-1111-2222-3333-444444444444"
FAKE_CS = "C12345678"

GOOD_HTML = (
    "<html><head><script>var sol = sol || {}; sol.conf = {"
    "solSessionId: 'abcd1234sessionid', "
    "solUrlApi: 'https://sgc.altotrevigianoservizi.it/webapi/', "
    f"solUserAT: '{FAKE_AT}', solUserCS: '{FAKE_CS}', "
    "solUserAId: '99999999-8888-7777-6666-555555555555', "
    "solUserEmail: 'TEST@EXAMPLE.COM'"
    "};</script></head><body></body></html>"
)


class TestParseSolConf(unittest.TestCase):
    def test_parse_valid(self):
        at, cs = auth.parse_sol_conf_identifiers(GOOD_HTML)
        self.assertEqual(at, FAKE_AT)
        self.assertEqual(cs, FAKE_CS)

    def test_missing_at(self):
        html = GOOD_HTML.replace(f"solUserAT: '{FAKE_AT}', ", "")
        with self.assertRaises(auth.ATSDiscoveryError):
            auth.parse_sol_conf_identifiers(html)

    def test_missing_cs(self):
        html = GOOD_HTML.replace(f"solUserCS: '{FAKE_CS}', ", "")
        with self.assertRaises(auth.ATSDiscoveryError):
            auth.parse_sol_conf_identifiers(html)

    def test_empty_at(self):
        html = GOOD_HTML.replace(FAKE_AT, "")
        with self.assertRaises(auth.ATSDiscoveryError):
            auth.parse_sol_conf_identifiers(html)

    def test_malformed_at_not_uuid(self):
        html = GOOD_HTML.replace(FAKE_AT, "not-a-uuid")
        with self.assertRaises(auth.ATSDiscoveryError):
            auth.parse_sol_conf_identifiers(html)

    def test_malformed_cs(self):
        html = GOOD_HTML.replace(FAKE_CS, "X999")
        with self.assertRaises(auth.ATSDiscoveryError):
            auth.parse_sol_conf_identifiers(html)

    def test_empty_document(self):
        with self.assertRaises(auth.ATSDiscoveryError):
            auth.parse_sol_conf_identifiers("")

    def test_error_text_hides_token(self):
        html = GOOD_HTML.replace(FAKE_CS, "bad")
        try:
            auth.parse_sol_conf_identifiers(html)
        except auth.ATSDiscoveryError as err:
            self.assertNotIn(FAKE_AT, str(err))


class FakeResponse:
    def __init__(self, status, body=""):
        self.status = status
        self.body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def text(self):
        return self.body


class FakeSession:
    def __init__(self, status=200, body=GOOD_HTML):
        self.status = status
        self.body = body
        self.last_url = None
        self.last_allow_redirects = None

    def get(self, url, allow_redirects):
        self.last_url = url
        self.last_allow_redirects = allow_redirects
        return FakeResponse(self.status, self.body)


class TestAsyncDiscover(unittest.IsolatedAsyncioTestCase):
    async def test_discover_ok(self):
        session = FakeSession()
        at, cs = await auth.async_discover_identifiers(
            session, "https://sgc.altotrevigianoservizi.it"
        )
        self.assertEqual((at, cs), (FAKE_AT, FAKE_CS))
        self.assertTrue(session.last_url.endswith("/index.aspx"))
        self.assertFalse(session.last_allow_redirects)

    async def test_discover_redirect_to_login(self):
        session = FakeSession(status=302, body="")
        with self.assertRaises(auth.ATSDiscoveryError):
            await auth.async_discover_identifiers(
                session, "https://sgc.altotrevigianoservizi.it"
            )

    async def test_discover_incomplete_html(self):
        session = FakeSession(status=200, body="<html>no sol.conf here</html>")
        with self.assertRaises(auth.ATSDiscoveryError):
            await auth.async_discover_identifiers(
                session, "https://sgc.altotrevigianoservizi.it"
            )


class TestUrlBuilders(unittest.TestCase):
    def test_supply_path(self):
        self.assertEqual(
            auth.build_supply_path(FAKE_AT, FAKE_CS),
            f"/webapi/api/v1/supply-light/{FAKE_AT}/{FAKE_CS}/1/",
        )

    def test_invoice_path_v1_keeps_pdf(self):
        url = auth.build_invoice_path(FAKE_AT, "00000000", "20261105")
        self.assertEqual(url, f"/webapi/api/v1/invoice/{FAKE_AT}/-1/00000000/20261105/")
        self.assertIn("/api/v1/invoice/", url)  # v1 (not v1.1) keeps PdfExist

    def test_reading_path(self):
        url = auth.build_reading_path(FAKE_AT, "20251105", "20261105")
        self.assertEqual(
            url, f"/webapi/api/v1/reading-base/{FAKE_AT}/-1/20251105/20261105/"
        )


class TestTokenSubstitution(unittest.TestCase):
    def test_placeholder(self):
        path = "/webapi/api/v1/reading-base/{session_uuid}/-1/00000000/00000000/"
        out = auth.substitute_session_token(path, FAKE_AT)
        self.assertIn(FAKE_AT, out)
        self.assertNotIn("{session_uuid}", out)

    def test_uuid_segment(self):
        old = "11111111-2222-3333-4444-555555555555"
        path = f"/webapi/api/v1/supply-light/{old}/{FAKE_CS}/1/"
        out = auth.substitute_session_token(path, FAKE_AT)
        self.assertEqual(out, f"/webapi/api/v1/supply-light/{FAKE_AT}/{FAKE_CS}/1/")

    def test_ambiguous_double_placeholder(self):
        path = "/a/{session_uuid}/b/{session_uuid}/"
        with self.assertRaises(auth.ATSLoginError):
            auth.substitute_session_token(path, FAKE_AT)

    def test_no_token_segment(self):
        with self.assertRaises(auth.ATSLoginError):
            auth.substitute_session_token("/webapi/api/v1/supply-light/C1/1/", FAKE_AT)

    def test_path_has_token_detection(self):
        self.assertTrue(auth.path_has_session_token("/x/{session_uuid}/"))
        self.assertTrue(
            auth.path_has_session_token(f"/x/{FAKE_AT}/y/")
        )
        self.assertFalse(auth.path_has_session_token("/webapi/api/v1/invoice/-1/0/0/"))


class TestInvoiceDateRewrite(unittest.TestCase):
    def test_rewrites_end(self):
        path = "/webapi/api/v1/invoice/{session_uuid}/-1/20200101/20240101/"
        out = auth.rewrite_invoice_end_date(path, "20261105")
        self.assertTrue(out.endswith("/20200101/20261105/"))

    def test_no_dates_unchanged(self):
        path = "/webapi/api/v1/invoice/{session_uuid}/-1/"
        self.assertEqual(auth.rewrite_invoice_end_date(path, "20261105"), path)


class TestResolveApiUrl(unittest.TestCase):
    def test_auto_all_labels(self):
        common = dict(
            session_token=FAKE_AT, customer_code=FAKE_CS,
            invoice_from="00000000", invoice_to="20261105",
            reading_from="20251105", reading_to="20261105",
        )
        self.assertEqual(
            auth.resolve_api_url("utenze", mode=auth.MODE_AUTO, **common),
            f"/webapi/api/v1/supply-light/{FAKE_AT}/{FAKE_CS}/1/",
        )
        self.assertEqual(
            auth.resolve_api_url("fatture", mode=auth.MODE_AUTO, **common),
            f"/webapi/api/v1/invoice/{FAKE_AT}/-1/00000000/20261105/",
        )
        self.assertEqual(
            auth.resolve_api_url("letture", mode=auth.MODE_AUTO, **common),
            f"/webapi/api/v1/reading-base/{FAKE_AT}/-1/20251105/20261105/",
        )

    def test_auto_requires_identifiers(self):
        with self.assertRaises(auth.ATSLoginError):
            auth.resolve_api_url(
                "utenze", mode=auth.MODE_AUTO,
                session_token=None, customer_code=None,
            )

    def test_new_token_changes_url(self):
        url1 = auth.resolve_api_url(
            "utenze", mode=auth.MODE_AUTO,
            session_token=FAKE_AT, customer_code=FAKE_CS,
        )
        new_at = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        url2 = auth.resolve_api_url(
            "utenze", mode=auth.MODE_AUTO,
            session_token=new_at, customer_code=FAKE_CS,
        )
        self.assertNotEqual(url1, url2)
        self.assertIn(new_at, url2)

    def test_credentials_manual_paths_get_fresh_token(self):
        supply = "/webapi/api/v1/supply-light/{session_uuid}/C999/1/"
        invoice = "/webapi/api/v1/invoice/{session_uuid}/-1/20200101/20200101/"
        out_s = auth.resolve_api_url(
            "utenze", mode=auth.MODE_CREDENTIALS,
            session_token=FAKE_AT, customer_code=None,
            supply_path=supply, invoice_path=invoice, reading_path="",
            invoice_to="20261105",
        )
        out_i = auth.resolve_api_url(
            "fatture", mode=auth.MODE_CREDENTIALS,
            session_token=FAKE_AT, customer_code=None,
            supply_path=supply, invoice_path=invoice, reading_path="",
            invoice_to="20261105",
        )
        self.assertIn(FAKE_AT, out_s)
        self.assertTrue(out_i.endswith("/20200101/20261105/"))

    def test_credentials_reading_fallback_built(self):
        out = auth.resolve_api_url(
            "letture", mode=auth.MODE_CREDENTIALS,
            session_token=FAKE_AT, customer_code=None,
            supply_path="/x/", invoice_path="/y/", reading_path="",
            reading_from="20251105", reading_to="20261105",
        )
        self.assertEqual(
            out, f"/webapi/api/v1/reading-base/{FAKE_AT}/-1/20251105/20261105/"
        )

    def test_credentials_requires_token(self):
        with self.assertRaises(auth.ATSLoginError):
            auth.resolve_api_url(
                "utenze", mode=auth.MODE_CREDENTIALS,
                session_token=None, customer_code=None,
                supply_path="/x/{session_uuid}/",
            )

    def test_credentials_literal_manual_paths_without_session_token(self):
        # Existing manual URLs without a UUID must not require sol.conf.
        for label, expected in (
            ("utenze", "/webapi/static/supplies/"),
            ("fatture", "/webapi/static/invoices/"),
            ("letture", "/webapi/static/readings/"),
        ):
            with self.subTest(label=label):
                self.assertEqual(
                    auth.resolve_api_url(
                        label, mode=auth.MODE_CREDENTIALS,
                        session_token=None, customer_code=None,
                        supply_path="/webapi/static/supplies/",
                        invoice_path="/webapi/static/invoices/",
                        reading_path="/webapi/static/readings/",
                    ),
                    expected,
                )

    def test_credentials_reading_fallback_requires_discovered_token(self):
        with self.assertRaises(auth.ATSLoginError):
            auth.resolve_api_url(
                "letture", mode=auth.MODE_CREDENTIALS,
                session_token=None, customer_code=None,
                supply_path="/webapi/static/supplies/",
                invoice_path="/webapi/static/invoices/",
                reading_path="",
            )

    def test_cookie_legacy_literal(self):
        self.assertEqual(
            auth.resolve_api_url(
                "utenze", mode=auth.MODE_COOKIE,
                session_token=None, customer_code=None,
                supply_path="/s/", invoice_path="/i/", reading_path="/r/",
            ),
            "/s/",
        )

    def test_cookie_no_reading_returns_none(self):
        self.assertIsNone(
            auth.resolve_api_url(
                "letture", mode=auth.MODE_COOKIE,
                session_token=None, customer_code=None,
                supply_path="/s/", invoice_path="/i/", reading_path="",
            )
        )

    def test_unknown_label(self):
        with self.assertRaises(auth.ATSLoginError):
            auth.resolve_api_url("bogus", mode=auth.MODE_AUTO,
                                 session_token=FAKE_AT, customer_code=FAKE_CS)


if __name__ == "__main__":
    unittest.main()
