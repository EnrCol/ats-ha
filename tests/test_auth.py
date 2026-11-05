"""Offline ATS login tests: no real accounts or network requests."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

AUTH_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "ats" / "auth.py"
spec = importlib.util.spec_from_file_location("ats_auth_tested", AUTH_PATH)
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)


FORM = (
    '<form><input type="hidden" name="__VIEWSTATE" value="view-test">'
    '<input type="hidden" name="__AntiXsrfToken" value="csrf-test"></form>'
)


class FakeCookieJar:
    def __init__(self):
        self.clear_calls = 0

    def clear(self):
        self.clear_calls += 1


class FakeResponse:
    def __init__(self, status, body="", cookies=None):
        self.status = status
        self.body = body
        self.cookies = cookies or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def text(self):
        return self.body


class FakeSession:
    def __init__(self, post_status=302, post_cookies=None, get_status=200, form=FORM):
        self.cookie_jar = FakeCookieJar()
        self.post_status = post_status
        self.post_cookies = post_cookies if post_cookies is not None else {".ASPNETAUTH": "demo"}
        self.get_status = get_status
        self.form = form
        self.post_data = None
        self.calls = []

    def get(self, url, allow_redirects):
        self.calls.append(("GET", url, allow_redirects))
        return FakeResponse(self.get_status, self.form)

    def post(self, url, data, headers, allow_redirects):
        self.calls.append(("POST", url, allow_redirects))
        self.post_data = data
        return FakeResponse(self.post_status, cookies=self.post_cookies)


class TestATSLogin(unittest.IsolatedAsyncioTestCase):
    async def test_valid_login_uses_current_csrf_and_disables_redirects(self):
        session = FakeSession()
        await auth.async_login(session, "https://sgc.altotrevigianoservizi.it", "example", "test-password")
        self.assertEqual(session.cookie_jar.clear_calls, 1)
        self.assertEqual(session.post_data["__VIEWSTATE"], "view-test")
        self.assertEqual(session.post_data["__AntiXsrfToken"], "csrf-test")
        self.assertEqual(session.post_data["username"], "example")
        self.assertEqual(session.post_data["password"], "test-password")
        self.assertEqual([x[0] for x in session.calls], ["GET", "POST"])
        self.assertTrue(all(allow is False for _, _, allow in session.calls))

    async def test_login_form_rejected_means_bad_credentials(self):
        session = FakeSession(post_status=200, post_cookies={})
        with self.assertRaises(auth.ATSInvalidCredentials) as raised:
            await auth.async_login(session, "https://sgc.altotrevigianoservizi.it", "example", "bad-password")
        self.assertNotIn("bad-password", str(raised.exception))
        self.assertEqual(session.cookie_jar.clear_calls, 2)

    async def test_forbidden_response_means_bad_credentials(self):
        session = FakeSession(post_status=403, post_cookies={})
        with self.assertRaises(auth.ATSInvalidCredentials):
            await auth.async_login(session, "https://sgc.altotrevigianoservizi.it", "example", "wrong")

    async def test_redirect_without_auth_cookie_is_not_password_failure(self):
        session = FakeSession(post_status=302, post_cookies={})
        with self.assertRaises(auth.ATSLoginError) as raised:
            await auth.async_login(session, "https://sgc.altotrevigianoservizi.it", "example", "unknown")
        self.assertNotIsInstance(raised.exception, auth.ATSInvalidCredentials)

    async def test_changed_login_form_is_not_password_failure(self):
        session = FakeSession(form="<form></form>")
        with self.assertRaises(auth.ATSLoginError) as raised:
            await auth.async_login(session, "https://sgc.altotrevigianoservizi.it", "example", "unused")
        self.assertNotIsInstance(raised.exception, auth.ATSInvalidCredentials)
        self.assertEqual(len(session.calls), 1)

    async def test_missing_password_is_invalid_credentials(self):
        session = FakeSession()
        with self.assertRaises(auth.ATSInvalidCredentials):
            await auth.async_login(session, "https://sgc.altotrevigianoservizi.it", "example", "")
        self.assertFalse(session.calls)


if __name__ == "__main__":
    unittest.main()
