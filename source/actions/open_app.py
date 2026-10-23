"""Launch an application and announce verified window evidence asynchronously.

Windows confirmation checks a visible window, including reused processes and
Store application child windows. A launcher return or a background PID is not
success. Window titles remain local to the matcher.
"""
import os
import platform
import shutil
import subprocess
import threading
import time

from core import appidentity, outcome
from core.lazyimport import LazyModule, installed

_PYAUTOGUI = installed("pyautogui")
pyautogui = LazyModule("pyautogui")

_SYSTEM = platform.system()          # "Windows" | "Darwin" | "Linux"

# How long to keep watching for the application to appear. Chosen from the two
# ends of the range rather than the middle: a text editor is up in a fraction
# of a second, a game launcher can take ten, and a limit that suits the first
# reports the second as broken.
_LAUNCH_TIMEOUT = 12.0

# Nothing here is a keyword list. The Start-Menu / Spotlight fallback types the
# name and presses Enter, which is what a person does, and works in every
# language the desktop is running in.
_SEARCH_SETTLE = 0.8


# ─────────────────────────────────────────────────────────────────────────────
#  Per-OS launching — no shell on any path
# ─────────────────────────────────────────────────────────────────────────────
def _desktop_search(app_name: str) -> bool:
    """Type the name into the desktop's own search and press Enter.

    The last resort, and the only one that reaches Store apps, shortcuts and
    anything else with no executable on PATH. It is also the one that cannot be
    verified from its own return value — which is fine, because nothing here is
    trusted on its own any more; a separate window check decides.
    """
    if _SYSTEM=='Windows':
        return False
    if not _PYAUTOGUI:
        return False
    try:
        if _SYSTEM == "Darwin":
            pyautogui.hotkey("command", "space")
        else:
            pyautogui.press("win")
        time.sleep(_SEARCH_SETTLE)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(_SEARCH_SETTLE)
        pyautogui.press("enter")
        return True
    except Exception as exc:
        print(f"[open_app] desktop search failed: {exc}")
        return False


def _launch_windows(app_name: str) -> bool:
    """Request launch by executable, installed shortcut or Store app ID.

    Never type into the desktop. The separate window check verifies launch.
    """
    from core.windows_launcher import launch
    return launch(app_name)


def _launch_macos(app_name: str) -> bool:
    for candidate in (app_name, f"{app_name}.app"):
        try:
            result = subprocess.run(
                ["open", "-a", candidate], capture_output=True, timeout=8
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            pass

    return _desktop_search(app_name)


_LINUX_TERMINALS = [
    "x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal",
    "xterm", "lxterminal", "mate-terminal", "tilix", "alacritty", "kitty",
]


def _launch_linux(app_name: str) -> bool:
    # "terminal" means whichever one this distribution actually ships.
    if app_name in ("x-terminal-emulator", "gnome-terminal", "terminal"):
        for term in _LINUX_TERMINALS:
            path = shutil.which(term)
            if not path:
                continue
            try:
                subprocess.Popen(
                    [path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                return True
            except Exception:
                continue

    binary = (
        shutil.which(app_name)
        or shutil.which(app_name.lower())
        or shutil.which(app_name.lower().replace(" ", "-"))
        or shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            pass

    for name in (
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ):
        try:
            result = subprocess.run(
                ["gtk-launch", name], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except FileNotFoundError:
            break
        except Exception:
            pass

    try:
        result = subprocess.run(
            ["xdg-open", app_name], capture_output=True, timeout=5
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass

    return _desktop_search(app_name)


_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin": _launch_macos,
    "Linux": _launch_linux,
}


# ─────────────────────────────────────────────────────────────────────────────
#  HUD helpers — no-ops without a player, exactly as the whatsapp plugins do
# ─────────────────────────────────────────────────────────────────────────────
def _log(player, message: str) -> None:
    if player:
        try:
            player.write_log(message)
        except Exception:
            pass


def _say(player, instruction: str) -> bool:
    if player and callable(getattr(player, "request_say", None)):
        try:
            player.request_say(instruction)
            return True
        except Exception:
            pass
    return False


# ─────────────────────────────────────────────────────────────────────────────
#  Launch + verify, off the conversation's thread
# ─────────────────────────────────────────────────────────────────────────────
def _announce(player, text: str) -> None:
    has_speech_channel = callable(getattr(player, 'request_say', None))
    _log(player, ('SYS: ' if has_speech_channel else 'JARVIS: ') + text)
    # A final task result is a literal announcement, never another user command
    # or an instruction for the cloud model to paraphrase.
    if has_speech_channel and not _say(player, '[JARVIS_TASK_RESULT]' + text):
        _log(player, 'JARVIS: ' + text)


def _launch_and_verify(player, spoken: str, launcher_name: str) -> None:
    from core import launch_confirmation as confirmation
    try:
        before_windows = ()
        read_error = ''
        if _SYSTEM == 'Windows':
            identity = confirmation.resolve_identity(spoken, launcher_name)
            try:
                before_windows = confirmation.snapshot()
            except Exception:
                read_error = 'Windows did not allow the application window check.'
            if not read_error:
                existing = confirmation.candidates(identity, before_windows, allow_minimized=True)
                existing.sort(key=lambda window: not window.foreground)
                for window in existing[:8]:
                    if window.foreground and window.usable():
                        _announce(player, f'{spoken} is already open and in front.')
                        return
                    try:
                        raised = confirmation.focus_window(window)
                        current = confirmation.snapshot() if raised else ()
                    except Exception:
                        current = ()
                    if any(item.hwnd == window.hwnd and item.foreground
                           and item.usable() and identity.evidence(item) for item in current):
                        _announce(player, f'{spoken} is open and in front.')
                        return
        else:
            before_pids = appidentity.snapshot()

        launcher = _LAUNCHERS[_SYSTEM]
        requested = launcher(launcher_name)
        if not requested and launcher_name.lower() != spoken.lower():
            requested = launcher(spoken)
        if not requested:
            _announce(player, f'I could not open {spoken}. Check that it is installed under that name.')
            return

        if _SYSTEM == 'Windows':
            if read_error:
                _announce(player, f'I asked to open {spoken}, but could not confirm it. {read_error}')
                return
            # launch() can discover a Store ID on its first call. Refresh that
            # identity so its ApplicationFrameHost window can be recognized.
            identity = confirmation.resolve_identity(spoken, launcher_name)
            result = confirmation.wait_for_window(identity, before_windows,
                                                   timeout=_LAUNCH_TIMEOUT)
            if result.verified:
                _announce(player, f'{spoken} is open.')
                return
            reason = result.reason
        else:
            appeared = appidentity.wait_for_launch(spoken, before_pids, timeout=_LAUNCH_TIMEOUT)
            reason = ('Its process is running, but the application window could not be checked.'
                      if appeared else 'No matching application window could be checked.')
        _announce(player, f'I asked to open {spoken}, but could not confirm it. {reason}')
    except Exception as exc:
        print(f'[open_app] {type(exc).__name__}: {exc}')
        _announce(player, f'I could not confirm opening {spoken}. The launch check encountered an error.')


def open_app(parameters=None, response=None, player=None,
             session_memory=None) -> str:
    spoken = ((parameters or {}).get('app_name') or '').strip()
    if not spoken:
        return outcome.failed('open_app', 'no application name was given')
    if _SYSTEM not in _LAUNCHERS:
        return outcome.failed('open_app', f'this operating system ({_SYSTEM}) is not supported', app=spoken)
    launcher_name = appidentity.launcher_name(spoken)
    _log(player, f'SYS: Opening {spoken}…')
    threading.Thread(target=_launch_and_verify,
                     args=(player, spoken, launcher_name), daemon=True,
                     name=f'open-app-{spoken[:20]}').start()
    return outcome.started('open_app', app=spoken)


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "open_app",
    "description": (
        "Opens an application on this computer. Use whenever the user asks to "
        "open, launch or start any app or program. Put the application's name "
        "in 'app_name' exactly as the user said it. "
        "This tool answers immediately and confirms the launch in the "
        "background by checking its visible window: on status=started say only that it is opening, never that "
        "it is open. Success or inability to confirm will be announced separately - "
        "relay that plainly rather than claiming success. Never say you opened "
        "something without calling this tool. "
        "To CLOSE an application use computer_control with action='close_app', "
        "not this tool. "
        "DO NOT use this tool to reach a WEB PAGE. 'open Chrome and go to "
        "YouTube', 'open YouTube', 'search the web' are all browser_control "
        "alone - it opens the browser itself. Calling open_app for the browser "
        "first and browser_control after it launches the browser TWICE, the "
        "second copy on a different profile, which is what puts a 'Who's using "
        "Chrome?' picker on the screen. Use this tool only when the user wants "
        "the application and nothing in it."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_name": {
                "type": "STRING",
                "description": (
                    "The application's REAL name, not the user's shorthand. "
                    "Expand abbreviations and nicknames before passing them: "
                    "'wp' or 'whats' is 'WhatsApp', 'ig' is 'Instagram', 'vs "
                    "code' is 'Visual Studio Code'. A two-letter fragment "
                    "matches the wrong program - 'wp' finds WPS Office. Any "
                    "application on the machine works; there is no fixed list."
                ),
            }
        },
        "required": ["app_name"],
    },
    "handler": open_app,
}

