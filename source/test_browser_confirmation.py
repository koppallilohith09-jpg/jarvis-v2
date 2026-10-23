"""Synthetic launch confirmation tests. No desktop, browser or network access."""
import asyncio
import ctypes
import sys
from types import SimpleNamespace
import threading
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from core.browser_confirmation import (
    AddressObservation, Confirmation, confirm_native_url, display_url, urls_match,
)
from core import browser_confirmation
from actions import browser_control as browser


class URLMatchingTests(unittest.TestCase):
    def test_normalizes_browser_chrome_and_https_upgrade(self):
        self.assertTrue(urls_match("https://www.YouTube.com", "youtube.com/"))
        self.assertTrue(urls_match("http://example.com:80/a", "https://example.com/a"))
        self.assertTrue(urls_match("https://example.com/%7euser", "https://EXAMPLE.com/~user"))

    def test_path_and_query_must_match(self):
        self.assertFalse(urls_match("https://example.com/a", "https://example.com/b"))
        self.assertFalse(urls_match("https://google.com/search?q=cats", "https://google.com/search?q=dogs"))
        self.assertFalse(urls_match("https://example.com/a%2Fb", "https://example.com/a/b"))
        self.assertFalse(urls_match("https://example.com:443/", "https://example.com:444/"))
        self.assertTrue(urls_match("https://google.com/search?q=two+words&hl=en",
                                   "https://www.google.com/search?hl=en&q=two%20words&utm_source=launch"))

    def test_wrong_scheme_host_and_error_pages_rejected(self):
        for value in ("https://example.com.evil.test", "https://login.example.com/",
                      "http://example.com/", "chrome-error://chromewebdata/",
                      "about:blank", "example dot com", "https://example.com@evil.test/"):
            self.assertFalse(urls_match("https://example.com", value), value)

    def test_sensitive_url_parts_never_displayed(self):
        self.assertEqual(display_url("https://name:password@example.com/path?token=secret#private"),
                         "https://example.com/path")
        self.assertEqual(display_url("chrome-error://chromewebdata/"), "")


class NativeConfirmationTests(unittest.TestCase):
    def test_matching_foreground_tab_after_poll_confirms(self):
        samples = iter([AddressObservation("chrome", "https://wrong.test/"),
                        AddressObservation("chrome", "youtube.com/")])
        result = confirm_native_url("https://www.youtube.com", "chrome",
                                    reader=lambda: next(samples), interval=.001, timeout=.2)
        self.assertTrue(result.confirmed)
        self.assertEqual(result.browser, "chrome")

    def test_wrong_browser_target_and_unsupported_never_confirm(self):
        cases = [AddressObservation("edge", "https://youtube.com/"),
                 AddressObservation("chrome", "https://youtube.com/watch?v=wrong"),
                 AddressObservation("unknown", "https://youtube.com/"),
                 AddressObservation(reason="unsupported browser")]
        for sample in cases:
            result = confirm_native_url("https://youtube.com", "chrome", reader=lambda: sample,
                                        interval=.001, timeout=.01)
            self.assertFalse(result.confirmed, sample)
            self.assertEqual(result.url, "")

    def test_reader_failure_is_not_launch_failure_or_success(self):
        def blocked():
            raise PermissionError("internal secret or unrelated URL")
        result = confirm_native_url("https://youtube.com", reader=blocked, timeout=.1)
        self.assertFalse(result.confirmed)
        self.assertNotIn("secret", result.reason)
        self.assertIn("accessibility", result.reason)

    def test_stuck_accessibility_call_is_bounded(self):
        release = threading.Event()
        def stuck():
            release.wait(1)
            return AddressObservation("chrome", "https://youtube.com/")
        started = time.monotonic()
        try:
            result = confirm_native_url("https://youtube.com", reader=stuck, timeout=.025)
            self.assertFalse(result.confirmed)
            self.assertLess(time.monotonic() - started, .3)
        finally:
            release.set()

    def test_native_success_is_tab_only_and_strips_query(self):
        evidence = Confirmation(True, "https://google.com/search?q=private", "chrome")
        with patch.object(browser, "confirm_native_url", return_value=evidence):
            result = browser._native_launch_result("https://google.com/search?q=private", None)
        self.assertIn("status=done", result)
        self.assertIn("evidence=browser_tab_url", result)
        self.assertIn("load_verified=false", result)
        self.assertNotIn("private", result)

    def test_unreadable_native_launch_stays_requested(self):
        with patch.object(browser, "confirm_native_url", return_value=Confirmation(False, reason="not foreground")):
            result = browser._native_launch_result("https://youtube.com", "chrome")
        self.assertIn("status=unverified", result)
        self.assertIn("launch_requested=true", result)
        self.assertIn("load_verified=false", result)

    def test_explicit_browser_no_longer_claims_success_from_popen(self):
        with patch.object(browser, "_OS", "Windows"), \
             patch.object(browser, "_resolve_browser", return_value={"exe": "fake-chrome.exe"}), \
             patch.object(browser.subprocess, "Popen") as launch, \
             patch.object(browser, "confirm_native_url", return_value=Confirmation(False, reason="not foreground")):
            result = browser._open_native("https://youtube.com", "chrome")
        launch.assert_called_once()
        self.assertIn("status=unverified", result)
        self.assertNotIn("Opened in", result)

    def test_default_native_path_uses_same_confirmation(self):
        with patch.object(browser, "_OS", "Windows"), \
             patch.object(browser.os, "startfile", create=True) as launch, \
             patch.object(browser, "confirm_native_url", return_value=Confirmation(True, "https://youtube.com/", "edge")):
            result = browser._open_native("youtube.com", None)
        launch.assert_called_once_with("https://youtube.com")
        self.assertIn("evidence=browser_tab_url", result)
        self.assertIn("browser=edge", result)

    def test_native_url_saved_for_interactive_resume_only_when_requested(self):
        with patch.object(browser._registry, "has", return_value=False), \
             patch.object(browser._registry, "note_native_url") as note, \
             patch.object(browser, "_open_native", return_value="status=unverified launch_requested=true"):
            browser.browser_control({"action": "go_to", "url": "youtube.com"})
        note.assert_called_once_with("https://youtube.com")


class NativeAddressReaderTests(unittest.TestCase):
    """Exercise the native adapter against synthetic Win32/UIA objects."""
    def reader(self, *, page_field=False, other_browser=False, focused=False):
        hwnd = 2 ** 40 + 12
        user = SimpleNamespace(GetForegroundWindow=Mock(return_value=hwnd),
                               GetWindowThreadProcessId=Mock())
        def pid_for(received_hwnd, output):
            self.assertEqual(received_hwnd, hwnd)
            output._obj.value = 42
            return 1
        user.GetWindowThreadProcessId.side_effect = pid_for
        top = SimpleNamespace(handle=hwnd, element_info=SimpleNamespace(control_type="Window"))
        parent = (SimpleNamespace(handle=0, element_info=SimpleNamespace(control_type="Document"))
                  if page_field else top)
        control = SimpleNamespace(
            is_visible=lambda: True,
            element_info=SimpleNamespace(element=SimpleNamespace(CurrentHasKeyboardFocus=focused)),
            parent=lambda: parent,
            iface_value=SimpleNamespace(CurrentValue="https://youtube.com/"))
        field = SimpleNamespace(exists=lambda timeout: True, wrapper_object=lambda: control)
        window = SimpleNamespace(child_window=Mock(return_value=field))
        desktop = Mock(return_value=SimpleNamespace(window=Mock(return_value=window)))
        pythoncom = SimpleNamespace(CoInitialize=Mock(), CoUninitialize=Mock())
        with patch.object(ctypes, "windll", SimpleNamespace(user32=user)), \
             patch.dict(sys.modules, {"pythoncom": pythoncom,
                                      "pywinauto": SimpleNamespace(Desktop=desktop)}), \
             patch("psutil.Process", return_value=SimpleNamespace(name=lambda: "unrelated.exe" if other_browser else "chrome.exe")):
            result = browser_confirmation._foreground_address("chrome")
        pythoncom.CoUninitialize.assert_called_once()
        return result, desktop, user

    def test_pointer_sized_browser_handle_and_known_chrome_field_read(self):
        result, desktop, user = self.reader()
        self.assertEqual(result.url, "https://youtube.com/")
        self.assertEqual(result.browser, "chrome")
        self.assertIs(user.GetWindowThreadProcessId.argtypes[0], ctypes.wintypes.HWND)

    def test_in_page_or_edited_address_does_not_confirm_current_tab(self):
        for options in ({"page_field": True}, {"focused": True}):
            result, _, _ = self.reader(**options)
            self.assertEqual(result.url, "")

    def test_unrelated_foreground_process_never_inspected_with_uia(self):
        result, desktop, _ = self.reader(other_browser=True)
        self.assertEqual(result.url, "")
        desktop.assert_not_called()


class ManagedNavigationTests(unittest.IsolatedAsyncioTestCase):
    def session(self, page):
        session = browser._BrowserSession.__new__(browser._BrowserSession)
        session.profile_kind = "real"
        session.browser_name = "chrome"
        session._get_page = AsyncMock(return_value=page)
        return session

    def page(self, actual="https://youtube.com/", response=None, error=None):
        page = SimpleNamespace(url=actual, wait_for_load_state=AsyncMock())
        page.goto = AsyncMock(return_value=response, side_effect=error)
        return page

    def response(self, url="https://youtube.com/", status=200, redirected_from=None):
        request = SimpleNamespace(url=url, redirected_from=redirected_from)
        return SimpleNamespace(url=url, status=status, request=request)

    async def test_success_requires_url_and_dom_content_loaded(self):
        page = self.page(response=self.response())
        result = await self.session(page).go_to("https://youtube.com")
        page.goto.assert_awaited_once_with("https://youtube.com", wait_until="domcontentloaded", timeout=30_000)
        self.assertIn("status=done", result)
        self.assertIn("evidence=page_loaded", result)
        self.assertIn("load_verified=true", result)
        self.assertIn("http_status=200", result)

    async def test_stale_previous_url_after_exception_is_failure(self):
        page = self.page("https://old-private.test/", error=RuntimeError("secret destination"))
        result = await self.session(page).go_to("https://youtube.com")
        self.assertIn("status=failed", result)
        self.assertNotIn("old-private", result)
        self.assertNotIn("secret", result)

    async def test_timeout_with_target_address_is_still_unverified(self):
        class FakeTimeout(Exception):
            pass
        page = self.page(error=FakeTimeout())
        with patch.object(browser, "PlaywrightTimeout", FakeTimeout):
            result = await self.session(page).go_to("https://youtube.com")
        self.assertIn("status=unverified", result)
        self.assertIn("load_verified=false", result)

    async def test_error_url_never_done(self):
        for actual in ("chrome-error://chromewebdata/", "about:blank"):
            result = await self.session(self.page(actual, self.response())).go_to("https://youtube.com")
            self.assertIn("status=failed", result)

    async def test_http_errors_never_done(self):
        for status in (401, 404, 500):
            result = await self.session(self.page(response=self.response(status=status))).go_to("https://youtube.com")
            self.assertIn("status=failed", result)
            self.assertIn(f"http_status={status}", result)

    async def test_response_does_not_verify_stale_previous_tab(self):
        result = await self.session(self.page("https://old-private.test/", self.response())).go_to("https://youtube.com")
        self.assertIn("status=unverified", result)
        self.assertNotIn("old-private", result)

    async def test_wrong_search_query_is_not_confirmation(self):
        actual = "https://google.com/search?q=dogs"
        result = await self.session(self.page(actual, self.response(actual))).go_to("https://google.com/search?q=cats")
        self.assertIn("status=unverified", result)
        self.assertNotIn("dogs", result)
        self.assertNotIn("cats", result)

    async def test_verified_redirect_reports_actual_safe_destination(self):
        requested = "https://youtube.com/private?token=secret"
        original = SimpleNamespace(url=requested, redirected_from=None)
        actual = "https://accounts.google.com/login?state=private#token"
        result = await self.session(self.page(actual, self.response(actual, redirected_from=original))).go_to(requested)
        self.assertIn("status=done", result)
        self.assertIn("redirected=true", result)
        self.assertIn("opened=https://accounts.google.com/login", result)
        self.assertNotIn("state=", result)
        self.assertNotIn("secret", result)

    async def test_same_document_navigation_requires_load_check(self):
        page = self.page()
        result = await self.session(page).go_to("https://youtube.com/")
        page.wait_for_load_state.assert_awaited_once_with("domcontentloaded", timeout=3_000)
        self.assertIn("load_verified=true", result)

    async def test_same_document_failed_load_is_unverified(self):
        page = self.page()
        page.wait_for_load_state.side_effect = RuntimeError("not loaded")
        result = await self.session(page).go_to("https://youtube.com")
        self.assertIn("status=unverified", result)

    async def test_separate_profile_disclosed_even_when_page_loaded(self):
        session = self.session(self.page(response=self.response()))
        session.profile_kind = "separate"
        result = await session.go_to("https://youtube.com")
        self.assertIn("profile=separate", result)
        self.assertIn("signed_in_profile=false", result)


if __name__ == "__main__":
    unittest.main()
