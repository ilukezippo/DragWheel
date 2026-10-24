"""Windows-specific plumbing: input polling, Explorer selection, shell integration."""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
from pathlib import Path

IS_WIN = sys.platform == "win32"

VK = {"Shift": 0x10, "Ctrl": 0x11, "Alt": 0x12, "CapsLock": 0x14}
VK_LBUTTON = 0x01
VK_SPACE = 0x20
VK_ESCAPE = 0x1B

if IS_WIN:
    user32 = ctypes.windll.user32
    user32.GetAsyncKeyState.restype = ctypes.c_short
    from ctypes import wintypes
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowExW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def key_down(vk: int) -> bool:
    if not IS_WIN:
        return False
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def mouse_down() -> bool:
    if not IS_WIN:
        return False
    # respect swapped buttons
    vk = 0x02 if user32.GetSystemMetrics(23) else VK_LBUTTON
    return bool(user32.GetAsyncKeyState(vk) & 0x8000)


def cursor_pos() -> tuple[int, int]:
    if not IS_WIN:
        return (0, 0)
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y


def drag_threshold() -> int:
    if not IS_WIN:
        return 4
    return max(user32.GetSystemMetrics(68), 4)  # SM_CXDRAG


def file_drag_active() -> bool:
    """Explorer (and most shell drag sources) show a 'SysDragImage' layered window
    while an OLE drag is in flight. Its visibility is a reliable 'a file is being dragged' signal."""
    if not IS_WIN:
        return False
    hwnd = user32.FindWindowW("SysDragImage", None)
    while hwnd:
        if user32.IsWindowVisible(hwnd):
            return True
        hwnd = user32.FindWindowExW(None, hwnd, "SysDragImage", None)
    return False


def foreground_hwnd() -> int:
    return (user32.GetForegroundWindow() or 0) if IS_WIN else 0


def window_class(hwnd: int) -> str:
    if not IS_WIN or not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


# ----------------------------------------------------------------------------
# Explorer selection
# ----------------------------------------------------------------------------
def root_window_at(x: int, y: int) -> int:
    """Top-level window under a screen point."""
    if not IS_WIN:
        return 0
    from ctypes import wintypes
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.WindowFromPoint.argtypes = [POINT]
    user32.GetAncestor.restype = wintypes.HWND
    user32.GetAncestor.argtypes = [wintypes.HWND, ctypes.c_uint]
    h = user32.WindowFromPoint(POINT(x, y))
    return (user32.GetAncestor(h, 2) or 0) if h else 0   # GA_ROOT


def window_title(hwnd: int) -> str:
    if not IS_WIN or not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(ctypes.c_void_p(hwnd), buf, 512)
    return buf.value


def _active_tab_hwnd(frame: int) -> int:
    """Windows 11 Explorer tabs: the visible ShellTabWindowClass child is the active tab."""
    from ctypes import wintypes
    user32.FindWindowExW.restype = wintypes.HWND
    child = user32.FindWindowExW(frame, None, "ShellTabWindowClass", None)
    while child:
        if user32.IsWindowVisible(child):
            return child
        child = user32.FindWindowExW(frame, child, "ShellTabWindowClass", None)
    return 0


def _tab_hwnd_of(w) -> int:
    try:
        import pythoncom
        from win32com.shell import shell
        sp = w._oleobj_.QueryInterface(pythoncom.IID_IServiceProvider)
        sid_top = pythoncom.MakeIID("{4C96BE40-915C-11CF-99D3-00AA004AE837}")   # SID_STopLevelBrowser
        browser = sp.QueryService(sid_top, shell.IID_IShellBrowser)
        return int(browser.GetWindow())
    except Exception:
        return 0


def _desktop_selection() -> list[str]:
    import pythoncom
    import win32com.client
    sw = win32com.client.Dispatch("{9BA05972-F6A8-11CF-A442-00A0C90A8F39}")   # ShellWindows
    empty = win32com.client.VARIANT(pythoncom.VT_EMPTY, None)
    attempts = (
        lambda: sw.FindWindowSW(empty, empty, 8, win32com.client.VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0), 1),
        lambda: sw.FindWindowSW(empty, empty, 8, 0, 1),
        lambda: sw.FindWindowSW(0, 0, 8, 0, 1),
    )
    for attempt in attempts:
        try:
            desk = attempt()
            if isinstance(desk, tuple):
                desk = desk[0]
            if desk is None:
                continue
            if not hasattr(desk, "Document"):
                desk = win32com.client.Dispatch(desk)
            return [it.Path for it in desk.Document.SelectedItems()]
        except Exception as e:
            log(f"desktop selection attempt failed: {e}")
    return []


def explorer_selection(hwnd: int | None = None) -> list[str]:
    """Paths selected in an Explorer window (the active tab) or on the desktop.
    hwnd: top-level window to read; defaults to the foreground window."""
    if not IS_WIN:
        return []
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return []
    try:
        pythoncom.CoInitialize()
    except Exception:
        pass
    target = hwnd or foreground_hwnd()
    cls = window_class(target)
    try:
        if cls in ("CabinetWClass", "ExploreWClass"):
            shell = win32com.client.Dispatch("Shell.Application")
            matches = []
            for w in shell.Windows():
                try:
                    if int(w.HWND) == target:
                        matches.append(w)
                except Exception:
                    continue
            if not matches:
                return []
            chosen = matches[0]
            if len(matches) > 1:                       # several tabs in one window
                active = _active_tab_hwnd(target)
                by_tab = [w for w in matches if active and _tab_hwnd_of(w) == active]
                title = window_title(target)
                by_title = [w for w in matches if title and str(w.LocationName) and title.startswith(str(w.LocationName))]
                chosen = (by_tab or by_title or matches)[0]
            return [it.Path for it in chosen.Document.SelectedItems()]
        if cls in ("Progman", "WorkerW"):
            return _desktop_selection()
    except Exception as e:
        log(f"explorer_selection failed ({cls}): {e}")
    return []


def is_elevated() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin()) if IS_WIN else False
    except Exception:
        return False


# ----------------------------------------------------------------------------
# Log file: %LOCALAPPDATA%\DragWheel\dragwheel.log (kept small)
# ----------------------------------------------------------------------------
def log_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "DragWheel"
    return base / "dragwheel.log"


def log(msg: str) -> None:
    try:
        import time
        p = log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists() and p.stat().st_size > 512_000:
            p.replace(p.with_suffix(".old.log"))
        with open(p, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Launch command for this app
# ----------------------------------------------------------------------------
def app_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    script = Path(__file__).with_name("dragwheel.pyw").resolve()
    return [str(pyw if pyw.exists() else exe), str(script)]


def _quote(parts: list[str]) -> str:
    return " ".join(f'"{p}"' for p in parts)


def icon_path() -> str:
    if getattr(sys, "frozen", False):
        return sys.executable + ",0"
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return str((base / "assets" / "dragwheel.ico").resolve())


# ----------------------------------------------------------------------------
# Start with Windows
# ----------------------------------------------------------------------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def set_startup(enabled: bool) -> None:
    if not IS_WIN:
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enabled:
            winreg.SetValueEx(k, "DragWheel", 0, winreg.REG_SZ, _quote(app_command()) + " --tray")
        else:
            try:
                winreg.DeleteValue(k, "DragWheel")
            except FileNotFoundError:
                pass


def startup_enabled() -> bool:
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, "DragWheel")
            return True
    except OSError:
        return False


# ----------------------------------------------------------------------------
# Explorer right-click menu + Send To
# ----------------------------------------------------------------------------
MENU_TARGETS = [r"Software\Classes\*\shell\DragWheel",
                r"Software\Classes\Directory\shell\DragWheel"]


BG_MENU = r"Software\Classes\Directory\Background\shell\DragWheel"   # right-click on the desktop / a folder's empty space


def set_context_menu(enabled: bool, paste_label: str = "Save clipboard image here") -> None:
    if not IS_WIN:
        return
    import winreg
    cmd = _quote(app_command()) + ' --open "%1"'
    # DragWheel ▸ Save clipboard image here  (on the desktop and in empty space of any folder)
    if enabled:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, BG_MENU) as k:
            winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "DragWheel")
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon_path())
            winreg.SetValueEx(k, "SubCommands", 0, winreg.REG_SZ, "")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, BG_MENU + r"\shell\paste") as k:
            winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, paste_label)
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, "imageres.dll,-5302")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, BG_MENU + r"\shell\paste\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, _quote(app_command()) + ' --paste-here "%V"')
    else:
        _delete_tree(winreg.HKEY_CURRENT_USER, BG_MENU)
    for key in MENU_TARGETS:
        if enabled:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
                winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, "DragWheel")
                winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, icon_path())
                winreg.SetValueEx(k, "MultiSelectModel", 0, winreg.REG_SZ, "Player")
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key + r"\command") as k:
                winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
        else:
            for sub in (key + r"\command", key):
                try:
                    winreg.DeleteKey(winreg.HKEY_CURRENT_USER, sub)
                except FileNotFoundError:
                    pass
    _sendto(enabled)


def context_menu_enabled() -> bool:
    if not IS_WIN:
        return False
    import winreg
    try:
        winreg.OpenKey(winreg.HKEY_CURRENT_USER, MENU_TARGETS[0]).Close()
        return True
    except OSError:
        return False


def _sendto(enabled: bool) -> None:
    lnk = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "SendTo" / "DragWheel.lnk"
    if not enabled:
        lnk.unlink(missing_ok=True)
        return
    try:
        import win32com.client
        cmd = app_command()
        sc = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(lnk))
        sc.TargetPath = cmd[0]
        sc.Arguments = (_quote(cmd[1:]) + " " if len(cmd) > 1 else "") + "--open"
        sc.IconLocation = icon_path()
        sc.Description = "DragWheel"
        sc.Save()
    except Exception as e:
        print("SendTo shortcut failed:", e, file=sys.stderr)


def _delete_tree(root, path: str) -> bool:
    """Delete a registry key and everything under it. True if something was removed."""
    import winreg
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_ALL_ACCESS) as k:
            while True:
                try:
                    child = winreg.EnumKey(k, 0)
                except OSError:
                    break
                _delete_tree(root, path + "\\" + child)
        winreg.DeleteKey(root, path)
        return True
    except OSError:
        return False


def remove_legacy_satsuma() -> list[str]:
    """DragWheel's early test builds were called "Satsuma". Remove what they left for the
    current user: the "Convert with Satsuma" right-click entry, Send To and Start Menu
    shortcuts, the start-with-Windows entry and their settings. Returns what was removed."""
    if not IS_WIN:
        return []
    import winreg
    hk = winreg.HKEY_CURRENT_USER
    removed = []
    for key in (r"Software\Classes\*\shell\Satsuma",
                r"Software\Classes\Directory\shell\Satsuma",
                r"Software\Classes\Directory\Background\shell\Satsuma",
                r"Software\Classes\SystemFileAssociations\image\shell\Satsuma",
                r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Satsuma",
                r"Software\Satsuma"):
        if _delete_tree(hk, key):
            removed.append(key)
    try:
        with winreg.OpenKey(hk, RUN_KEY, 0, winreg.KEY_ALL_ACCESS) as k:
            winreg.DeleteValue(k, "Satsuma")
            removed.append("Run\\Satsuma")
    except OSError:
        pass
    appdata = Path(os.environ.get("APPDATA", ""))
    for lnk in (appdata / "Microsoft" / "Windows" / "SendTo" / "Satsuma.lnk",
                appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Satsuma.lnk",
                Path.home() / "Desktop" / "Satsuma.lnk"):
        try:
            if lnk.exists():
                lnk.unlink()
                removed.append(str(lnk))
        except OSError:
            pass
    folder = appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Satsuma"
    if folder.is_dir():
        import shutil
        shutil.rmtree(folder, ignore_errors=True)
        removed.append(str(folder))
    return removed


# ----------------------------------------------------------------------------
# Shell helpers
# ----------------------------------------------------------------------------
def reveal(path: str) -> None:
    p = Path(path)
    if IS_WIN:
        if p.is_dir():
            subprocess.Popen(["explorer", str(p)])
        else:
            subprocess.Popen(f'explorer /select,"{p}"')
    else:
        subprocess.Popen(["xdg-open", str(p.parent)])


def open_terminal(folder: str) -> None:
    if not IS_WIN:
        return
    import shutil
    wt = shutil.which("wt")
    if wt:
        subprocess.Popen([wt, "-d", folder])
    else:
        subprocess.Popen(["powershell.exe", "-NoExit", "-Command", f"Set-Location -LiteralPath '{folder}'"],
                         creationflags=0x00000010)  # CREATE_NEW_CONSOLE


def open_with(path: str) -> None:
    if IS_WIN:
        subprocess.Popen(["rundll32.exe", "shell32.dll,OpenAs_RunDLL", path])


# ----------------------------------------------------------------------------
# Low-level mouse hook — only used to see the scroll wheel during a drag
# (GetAsyncKeyState can't report wheel movement). Runs on its own thread.
# ----------------------------------------------------------------------------
class WheelHook:
    """Calls on_wheel(delta) for every scroll notch. If should_swallow() returns True
    the scroll is kept from the window under the cursor (so Explorer doesn't scroll
    while you pick a slice)."""

    def __init__(self, on_wheel, should_swallow=lambda: False):
        self.on_wheel = on_wheel
        self.should_swallow = should_swallow
        self._thread = None
        self._tid = 0
        self._proc = None

    def start(self):
        if not IS_WIN or self._thread:
            return
        import threading
        self._thread = threading.Thread(target=self._run, name="DragWheelHook", daemon=True)
        self._thread.start()

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)   # WM_QUIT

    def _run(self):
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        WH_MOUSE_LL, WM_MOUSEWHEEL = 14, 0x020A
        LRESULT = ctypes.c_ssize_t

        class MSLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("pt", POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.restype = LRESULT
        user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.SetWindowsHookExW.restype = wintypes.HHOOK
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
        kernel32.GetModuleHandleW.restype = wintypes.HMODULE

        def proc(n_code, w_param, l_param):
            if n_code == 0 and w_param == WM_MOUSEWHEEL:
                try:
                    info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    delta = ctypes.c_short((info.mouseData >> 16) & 0xFFFF).value
                    swallow = self.should_swallow()
                    self.on_wheel(delta)
                    if swallow:
                        return 1
                except Exception:
                    pass
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        self._proc = HOOKPROC(proc)            # keep a reference or it gets collected
        self._tid = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            log("mouse hook could not be installed")
            return
        log("mouse hook installed")
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(hook)
