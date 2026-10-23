"""Bounded, read-only confirmation of a foreground browser's address bar.

This does not attach a debugger, open a profile, enumerate tabs, read page
content or send keys. An address-bar match proves only that a matching tab is
open. Loading and HTTP status require an existing managed browser session.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import queue
import re
import threading
import time
from typing import Callable
from urllib.parse import parse_qsl, urlsplit, urlunsplit


_EXECUTABLES = {
    "chrome.exe": "chrome", "msedge.exe": "edge", "firefox.exe": "firefox",
    "brave.exe": "brave", "vivaldi.exe": "vivaldi", "opera.exe": "opera",
}
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def _unreserved(text: str) -> str:
    def replace(match):
        char = chr(int(match.group()[1:], 16))
        return char if char in _UNRESERVED else match.group().upper()
    return re.sub(r"%[0-9a-fA-F]{2}", replace, text)


def _web_url(value: str):
    value = str(value or "").strip()
    if not value or any(char.isspace() for char in value):
        return None
    if "://" not in value:
        value = "https://" + value
    try:
        parts = urlsplit(value)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
            return None
        host = parts.hostname.rstrip(".").lower().encode("idna").decode("ascii")
        if host.startswith("www."):
            host = host[4:]
        port = parts.port
        if port == (443 if parts.scheme == "https" else 80):
            port = None
        # Tracking parameters are immaterial to opening the requested page;
        # all other query values, including duplicate values, must agree.
        query = sorted((key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True)
                       if not key.lower().startswith("utm_") and key.lower() not in ("gclid", "fbclid"))
        return parts.scheme, host, port, _unreserved(parts.path or "/"), query, _unreserved(parts.fragment)
    except (ValueError, UnicodeError):
        return None


def urls_match(requested: str, observed: str) -> bool:
    """Match host, port, path and meaningful query, permitting an HTTPS upgrade.

    Browser chrome may hide the scheme and 'www'. A different search query,
    path, port, subdomain or an HTTPS downgrade cannot confirm the request.
    """
    wanted, actual = _web_url(requested), _web_url(observed)
    if not wanted or not actual:
        return False
    if wanted[0] == "https" and actual[0] != "https":
        return False
    return wanted[1:5] == actual[1:5] and (not wanted[5] or wanted[5] == actual[5])


def is_web_url(value: str) -> bool:
    return _web_url(value) is not None


def display_url(value: str) -> str:
    """URL evidence for tool facts/logs, excluding credentials/query/fragment."""
    text = str(value or "").strip()
    if "://" not in text:
        text = "https://" + text
    try:
        parts = urlsplit(text)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return ""
        host = parts.hostname
        if ":" in host:
            host = "[" + host + "]"
        port = parts.port
        if port is not None:
            host += ":" + str(port)
        return urlunsplit((parts.scheme, host, parts.path or "/", "", ""))
    except ValueError:
        return ""


@dataclass(frozen=True)
class AddressObservation:
    browser: str = ""
    url: str = ""
    reason: str = ""


@dataclass(frozen=True)
class Confirmation:
    confirmed: bool
    url: str = ""
    browser: str = ""
    reason: str = ""


def _foreground_address(expected_browser: str | None) -> AddressObservation:
    """Runs only inside a bounded worker; reads a known browser chrome field.

    We deliberately do not fall back to a generic Edit or window-title match:
    either could be a page input, search text or an unrelated window.
    """
    import ctypes
    from ctypes import wintypes
    import psutil
    import pythoncom
    from pywinauto import Desktop

    pythoncom.CoInitialize()
    try:
        user32 = ctypes.windll.user32
        # HWND is pointer-sized. Without prototypes ctypes truncates it on
        # 64-bit Windows, so a real foreground browser could never be checked.
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return AddressObservation(reason="no foreground window is available")
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        browser = _EXECUTABLES.get(psutil.Process(pid.value).name().lower(), "")
        wanted = "opera" if expected_browser == "operagx" else expected_browser
        if not browser or (wanted and browser != wanted):
            return AddressObservation(reason="the requested browser is not in the foreground")
        # These IDs/names identify browser chrome. Never inspect a page DOM,
        # document, tab list, history or generic edit field for a URL.
        selectors = ([{"auto_id": "urlbar-input", "control_type": "Edit"},
                      {"auto_id": "urlbar", "control_type": "ComboBox"}]
                     if browser == "firefox" else
                     [{"auto_id": "addressEditBox", "control_type": "Edit"},
                      {"title": "Address and search bar", "control_type": "Edit"},
                      {"title": "Search or enter web address", "control_type": "Edit"}])
        window = Desktop(backend="uia").window(handle=hwnd)
        for selector in selectors:
            field = window.child_window(**selector)
            if not field.exists(timeout=0):
                continue
            control = field.wrapper_object()
            if not control.is_visible() or control.element_info.element.CurrentHasKeyboardFocus:
                # An edited, unsubmitted address is not the selected tab's URL.
                continue
            # In-page Edit controls must not be mistaken for browser chrome.
            parent = control.parent()
            in_document = False
            reached_browser_window = False
            for _ in range(16):
                if parent is None:
                    break
                if parent.element_info.control_type == "Document":
                    in_document = True
                    break
                if parent.handle == hwnd or parent.element_info.control_type == "Window":
                    reached_browser_window = parent.handle == hwnd
                    break
                parent = parent.parent()
            if in_document or not reached_browser_window:
                continue
            value = str(control.iface_value.CurrentValue or "").strip()
            # A focus change while reading makes this observation inapplicable.
            if user32.GetForegroundWindow() != hwnd:
                return AddressObservation(reason="the foreground window changed during confirmation")
            if is_web_url(value):
                return AddressObservation(browser, value)
        return AddressObservation(browser=browser, reason="this browser did not expose a readable address bar")
    finally:
        pythoncom.CoUninitialize()


def confirm_native_url(requested: str, browser: str | None = None, *,
                       reader: Callable[[], AddressObservation] | None = None,
                       timeout: float = 4.0, interval: float = .2) -> Confirmation:
    """Poll after launch without focusing the browser, bounded even if UIA hangs.

    A daemon worker bounds unresponsive accessibility providers. Only one worker
    is used per command; a stuck accessibility call never creates a polling
    thread storm or delays the response beyond the allotted time.
    Tests inject a reader; they never access the desktop.
    """
    if not is_web_url(requested):
        return Confirmation(False, reason="no web address was supplied for confirmation")
    if reader is None:
        if os.name != "nt":
            return Confirmation(False, reason="address-bar confirmation is available only on Windows")
        reader = lambda: _foreground_address(browser)
    deadline = time.monotonic() + max(0., min(float(timeout), 5.0))
    results: queue.Queue[Confirmation] = queue.Queue(maxsize=1)
    stop = threading.Event()

    def poll():
        reason = "the browser address could not be read before the confirmation deadline"
        try:
            while not stop.is_set() and time.monotonic() < deadline:
                sample = reader()
                expected = "opera" if browser == "operagx" else browser
                actual = "opera" if sample.browser == "operagx" else sample.browser
                if sample.url and actual in _EXECUTABLES.values() and (not expected or actual == expected) and urls_match(requested, sample.url):
                    results.put_nowait(Confirmation(True, sample.url, sample.browser))
                    return
                reason = sample.reason or "the foreground browser address does not match the requested address"
                stop.wait(min(interval, max(0., deadline - time.monotonic())))
            if not stop.is_set():
                results.put_nowait(Confirmation(False, reason=reason))
        except Exception:
            # Accessibility errors can include unrelated UI/provider internals;
            # keep them out of the conversation and do not treat them as launch failures.
            if not stop.is_set():
                results.put_nowait(Confirmation(False, reason="Windows accessibility could not read the browser address bar"))

    threading.Thread(target=poll, name="JARVISBrowserConfirm", daemon=True).start()
    try:
        return results.get(timeout=max(0., deadline - time.monotonic()))
    except queue.Empty:
        return Confirmation(False, reason="the browser address could not be confirmed in time; check its visible tab")
    finally:
        stop.set()
