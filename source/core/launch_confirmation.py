"""Read-only Windows window evidence for application launch confirmation.

Process creation is insufficient: tray apps reuse processes, Store windows can
belong to ApplicationFrameHost, and a background process can have no window.
Window titles stay local and are never returned as confirmation text.
"""
from dataclasses import dataclass, field
import ntpath
import platform
import time

from core import appidentity


def _stem(value):
    return appidentity.fold(ntpath.splitext(ntpath.basename(str(value or '')))[0])


def _path(value):
    return ntpath.normcase(ntpath.normpath(str(value or '').strip('"')))


@dataclass(frozen=True)
class Process:
    pid: int
    name: str = ''
    exe: str = ''
    app_id: str = ''


@dataclass(frozen=True)
class Window:
    hwnd: int
    process: Process
    title: str = ''
    children: tuple = ()
    visible: bool = True
    minimized: bool = False
    cloaked: bool = False
    foreground: bool = False
    tool_window: bool = False
    window_class: str = ''
    width: int = 640
    height: int = 480

    def usable(self, allow_minimized=False):
        return (self.visible and not self.cloaked and bool(self.title.strip())
                and not self.tool_window
                and ((allow_minimized and self.minimized) or (self.width >= 40 and self.height >= 40))
                and (allow_minimized or not self.minimized)
                and self.window_class not in ('Progman', 'WorkerW', 'Shell_TrayWnd',
                                               'NotifyIconOverflowWindow'))


@dataclass(frozen=True)
class Identity:
    label: str
    names: frozenset
    paths: frozenset = field(default_factory=frozenset)
    app_ids: frozenset = field(default_factory=frozenset)

    def _match(self, window):
        """Only complete identities match, never fragments such as edge/webview."""
        best = (0, '', '')
        for proc in (window.process, *window.children):
            key = proc.app_id.casefold() or (_path(proc.exe) if proc.exe else _stem(proc.name))
            if proc.app_id and proc.app_id.casefold() in self.app_ids:
                best = max(best, (3, 'registered_app_id', key))
            generic_host = _stem(proc.name) in {
                'explorer', 'applicationframehost', 'rundll32', 'wscript',
                'cscript', 'cmd', 'powershell', 'msedgewebview2', 'update'}
            if (proc.exe and _path(proc.exe) in self.paths
                    and (not generic_host or _stem(proc.name) in self.names)):
                best = max(best, (2, 'installed_executable', key))
            if _stem(proc.name) in self.names:
                best = max(best, (1, 'exact_process_name', key))
        return best

    def evidence(self, window):
        return self._match(window)[1]


def _shortcut_identity(path):
    """Read an existing shortcut; never save it or execute its target."""
    try:
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        try:
            shell = win32com.client.Dispatch('WScript.Shell')
            link = shell.CreateShortcut(str(path))
            target = str(link.TargetPath or '')
            # explorer.exe with shell:AppsFolder arguments is an app ID,
            # not evidence that any Explorer window is the requested app.
            arguments = str(link.Arguments or '')
            app_id = arguments.split('shell:AppsFolder\\', 1)[-1].strip('" ')
            if 'shell:AppsFolder\\' in arguments:
                return '', app_id
            # An app shortcut may be Chrome --app-id=... or Update.exe
            # --processStart=.... The host path alone does not identify it.
            return target if target.lower().endswith('.exe') and not arguments else '', ''
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        return '', ''


def resolve_identity(spoken, launcher_name=None):
    """Combine exact aliases with the same installed target used by launch()."""
    from core import windows_launcher
    import shutil
    launcher_name = launcher_name or appidentity.launcher_name(spoken)
    names = {_stem(spoken), _stem(launcher_name)} - {''}
    paths, app_ids = set(), set()
    # These Windows launchers delegate to a differently named app process.
    delegated = {'calc': 'calculatorapp', 'calculator': 'calculatorapp',
                 'mssettings': 'systemsettings', 'settings': 'systemsettings',
                 'wt': 'windowsterminal', 'terminal': 'windowsterminal'}
    names.update(delegated[name] for name in tuple(names) if name in delegated)
    for name in dict.fromkeys((launcher_name, spoken)):
        candidate = shutil.which(name)
        if candidate and candidate.lower().endswith('.exe'):
            paths.add(_path(candidate))
        target = windows_launcher.index().get(windows_launcher.key(name))
        if not target:
            continue
        kind, value = target
        if kind == 'exe':
            paths.add(_path(value))
        elif kind == 'store':
            app_ids.add(str(value).casefold())
        elif kind == 'shortcut':
            executable, app_id = _shortcut_identity(value)
            if executable:
                paths.add(_path(executable))
            if app_id:
                app_ids.add(app_id.casefold())
    return Identity(spoken, frozenset(names), frozenset(paths), frozenset(app_ids))


def snapshot():
    """Visible top-level HWNDs plus owner/child process identity. No input/UIA."""
    if platform.system() != 'Windows':
        raise RuntimeError('Window confirmation is available on Windows only')
    import ctypes
    from ctypes import wintypes
    import psutil
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    enum_callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user.EnumWindows.argtypes = [enum_callback, wintypes.LPARAM]
    user.EnumChildWindows.argtypes = [wintypes.HWND, enum_callback, wintypes.LPARAM]
    user.GetForegroundWindow.restype = wintypes.HWND
    user.IsWindowVisible.argtypes = [wintypes.HWND]
    user.IsIconic.argtypes = [wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    get_style = user.GetWindowLongPtrW if hasattr(user, 'GetWindowLongPtrW') else user.GetWindowLongW
    get_style.argtypes = [wintypes.HWND, ctypes.c_int]
    get_style.restype = ctypes.c_ssize_t
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    get_id = getattr(kernel, 'GetApplicationUserModelId', None)
    if get_id:
        get_id.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.UINT), wintypes.LPWSTR]
    try:
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                             ctypes.c_void_p, wintypes.DWORD]
    except OSError:
        dwm = None
    processes = {}
    def process(pid):
        if pid in processes:
            return processes[pid]
        name, exe, app_id = '', '', ''
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            try:
                exe = proc.exe()
            except psutil.Error:
                pass
        except psutil.Error:
            pass
        handle = kernel.OpenProcess(0x1000, False, pid) if get_id else None
        if handle:
            try:
                length = wintypes.UINT(0)
                if get_id(handle, ctypes.byref(length), None) == 122 and 0 < length.value < 4096:
                    buffer = ctypes.create_unicode_buffer(length.value)
                    if get_id(handle, ctypes.byref(length), buffer) == 0:
                        app_id = buffer.value
            finally:
                kernel.CloseHandle(handle)
        processes[pid] = Process(pid, name, exe, app_id)
        return processes[pid]
    def pid_for(hwnd):
        pid = wintypes.DWORD()
        user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value)
    foreground = int(user.GetForegroundWindow() or 0)
    windows = []
    def collect(hwnd, _):
        if not user.IsWindowVisible(hwnd):
            return True
        length = user.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(min(max(length + 1, 1), 32768))
        user.GetWindowTextW(hwnd, buffer, len(buffer))
        window_class = ctypes.create_unicode_buffer(256)
        user.GetClassNameW(hwnd, window_class, 256)
        rect = wintypes.RECT()
        user.GetWindowRect(hwnd, ctypes.byref(rect))
        cloaked = wintypes.DWORD(0)
        if dwm:
            dwm.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        pid = pid_for(hwnd)
        child_pids = set()
        def child(child_hwnd, _):
            child_pid = pid_for(child_hwnd)
            if child_pid and child_pid != pid:
                child_pids.add(child_pid)
            return True
        if _stem(process(pid).name) == 'applicationframehost':
            user.EnumChildWindows(hwnd, enum_callback(child), 0)
        windows.append(Window(int(hwnd), process(pid), buffer.value,
                              tuple(process(p) for p in sorted(child_pids)),
                              minimized=bool(user.IsIconic(hwnd)),
                              cloaked=bool(cloaked.value), foreground=int(hwnd) == foreground,
                              tool_window=bool(get_style(hwnd, -20) & 0x80),
                              window_class=window_class.value,
                              width=rect.right - rect.left, height=rect.bottom - rect.top))
        return True
    if not user.EnumWindows(enum_callback(collect), 0):
        raise ctypes.WinError(ctypes.get_last_error())
    return tuple(windows)


def _ranked(identity, windows, allow_minimized=False):
    matches = [(identity._match(window), window) for window in windows
               if window.usable(allow_minimized) and identity.evidence(window)]
    strongest = max((match[0][0] for match in matches), default=0)
    return [(evidence, window) for evidence, window in matches if evidence[0] == strongest]


def candidates(identity, windows, allow_minimized=False):
    matches = _ranked(identity, windows, allow_minimized)
    # Two different executables called Editor.exe are not interchangeable.
    # Prefer the installed target; if identity is still ambiguous, do not guess.
    if len({evidence[2] for evidence, _ in matches}) > 1:
        return []
    return [window for _, window in matches]


def focus_window(window):
    """Raise the exact HWND, then read back foreground state; no guessed PID."""
    import ctypes
    from ctypes import wintypes
    user = ctypes.WinDLL('user32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    user.GetForegroundWindow.restype = wintypes.HWND
    user.IsIconic.argtypes = [wintypes.HWND]
    user.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user.SetForegroundWindow.argtypes = [wintypes.HWND]
    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
    hwnd = window.hwnd
    if user.IsIconic(hwnd):
        user.ShowWindow(hwnd, 9)
    if not user.SetForegroundWindow(hwnd):
        fore = user.GetForegroundWindow()
        theirs = user.GetWindowThreadProcessId(fore, None) if fore else 0
        ours = kernel.GetCurrentThreadId()
        if theirs and theirs != ours and user.AttachThreadInput(ours, theirs, True):
            try:
                user.SetForegroundWindow(hwnd)
            finally:
                user.AttachThreadInput(ours, theirs, False)
    return int(user.GetForegroundWindow() or 0) == hwnd


@dataclass(frozen=True)
class Confirmation:
    verified: bool
    evidence: str = ''
    window: Window | None = None
    reason: str = ''


def wait_for_window(identity, before, timeout=12.0, poll=.15,
                    read_windows=None, clock=None, sleep=None):
    """Require a newly visible/restored/focused matching window, stable twice.

    An unchanged stale window cannot prove the request worked. Existing PIDs
    are deliberately allowed when they expose a new HWND or return from tray.
    """
    read_windows, clock, sleep = read_windows or snapshot, clock or time.monotonic, sleep or time.sleep
    deadline = clock() + timeout
    old = {window.hwnd: window for window in before}
    previous = None
    last_reason = 'No matching visible application window appeared.'
    while clock() <= deadline:
        try:
            windows = read_windows()
            ranked = _ranked(identity, windows)
            current = candidates(identity, windows)
        except Exception:
            return Confirmation(False, reason='Windows did not allow the application window check.')
        changed = []
        for window in current:
            prior = old.get(window.hwnd)
            if (prior is None or prior.process.pid != window.process.pid
                    or not prior.usable() or (window.foreground and not prior.foreground)):
                changed.append(window)
        if changed:
            changed.sort(key=lambda item: not item.foreground)
            selected = changed[0]
            marker = (selected.hwnd, selected.process.pid)
            if marker == previous:
                return Confirmation(True, identity.evidence(selected), selected)
            previous = marker
        else:
            previous = None
            if ranked and not current:
                last_reason = 'Several different applications matched that name, so no window was assumed to be the right one.'
            elif current:
                last_reason = 'An existing window remained open, but the launch or focus change could not be confirmed.'
        sleep(poll)
    return Confirmation(False, reason=last_reason)
