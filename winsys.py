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


def _guid(text):
    class GUID(ctypes.Structure):
        _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]
    g = GUID()
    ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(g))
    return g


def _vcall(ptr, index, *args, argtypes=()):
    """Call method number `index` of a COM interface pointer."""
    vtbl = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    fn = ctypes.WINFUNCTYPE(ctypes.HRESULT, ctypes.c_void_p, *argtypes)(vtbl[index])
    return fn(ptr, *args)


def system_volume():
    """Windows' speaker volume as (0..1, muted), or None. Core Audio IAudioEndpointVolume through plain ctypes."""
    if not IS_WIN:
        return None
    ole32 = ctypes.oledll.ole32
    try:
        ole32.CoInitialize(None)
    except OSError:
        pass
    enum, dev, vol = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        ole32.CoCreateInstance(ctypes.byref(_guid("{BCDE0395-E52F-467C-8E3D-C4579291692E}")), None, 23,
                               ctypes.byref(_guid("{A95664D2-9614-4F35-A746-DE8DB63617E6}")), ctypes.byref(enum))
        _vcall(enum, 4, 0, 1, ctypes.byref(dev),                                  # GetDefaultAudioEndpoint(render, multimedia)
               argtypes=(ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)))
        iid = _guid("{5CDF2C82-841E-4546-9722-0CF74078229A}")
        _vcall(dev, 3, ctypes.byref(iid), 23, None, ctypes.byref(vol),           # Activate(IAudioEndpointVolume)
               argtypes=(ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)))
        level, muted = ctypes.c_float(), ctypes.c_int()
        _vcall(vol, 9, ctypes.byref(level), argtypes=(ctypes.POINTER(ctypes.c_float),))   # GetMasterVolumeLevelScalar
        _vcall(vol, 15, ctypes.byref(muted), argtypes=(ctypes.POINTER(ctypes.c_int),))     # GetMute
        return max(0.0, min(1.0, level.value)), bool(muted.value)
    except Exception as e:
        log(f"system volume: {e}")
        return None
    finally:
        for p in (vol, dev, enum):
            if p.value:
                _vcall(p, 2)                                                       # Release


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


def _desktop_selection(focused=False) -> list[str]:
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
            if focused:
                it = desk.Document.FocusedItem
                return [it.Path] if it is not None else []
            return [it.Path for it in desk.Document.SelectedItems()]
        except Exception as e:
            log(f"desktop selection attempt failed: {e}")
    return []


def explorer_selection(hwnd: int | None = None, focused: bool = False) -> list[str]:
    """Paths selected in an Explorer window (the active tab) or on the desktop.
    hwnd: top-level window to read; defaults to the foreground window.
    focused=True returns the item with the focus rectangle instead (the one just Ctrl-clicked)."""
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
            if focused:
                it = chosen.Document.FocusedItem
                return [it.Path] if it is not None else []
            return [it.Path for it in chosen.Document.SelectedItems()]
        if cls in ("Progman", "WorkerW"):
            return _desktop_selection(focused)
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


def set_context_menu(enabled: bool, paste_label: str = "Save clipboard image here",
                     link_label: str = "Play copied link in Float") -> None:
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
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, BG_MENU + r"\shell\zlink") as k:     # listed after "paste"
            winreg.SetValueEx(k, "MUIVerb", 0, winreg.REG_SZ, link_label)
            winreg.SetValueEx(k, "Icon", 0, winreg.REG_SZ, "imageres.dll,-1004")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, BG_MENU + r"\shell\zlink\command") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, _quote(app_command()) + " --play-link")
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
    folder = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "SendTo"
    (folder / "DragWheel.lnk").unlink(missing_ok=True)            # the old name
    lnk = folder / "Send to Phone using DragWheel.lnk"
    if not enabled:
        lnk.unlink(missing_ok=True)
        return
    try:
        import win32com.client
        cmd = app_command()
        sc = win32com.client.Dispatch("WScript.Shell").CreateShortcut(str(lnk))
        sc.TargetPath = cmd[0]
        sc.Arguments = (_quote(cmd[1:]) + " " if len(cmd) > 1 else "") + "--send-phone"
        sc.IconLocation = icon_path()
        sc.Description = "Send to your phone over Wi-Fi (DragWheel)"
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
def reveal(path) -> None:
    """Open the folder in Explorer with the file(s) selected. `path` may be one path or a list
    (all in the same folder get selected). A folder on its own just opens."""
    paths = [Path(x) for x in (path if isinstance(path, (list, tuple)) else [path]) if x]
    if not paths:
        return
    p = paths[0]
    if not IS_WIN:
        subprocess.Popen(["xdg-open", str(p if p.is_dir() else p.parent)])
        return
    try:
        _select_in_explorer([str(x.resolve()) for x in paths if x.exists()] or [str(p)])
    except Exception as e:
        log(f"reveal fallback: {e}")
        subprocess.Popen(f'explorer /select,"{os.path.normpath(str(p))}"')


def _select_in_explorer(paths: list) -> None:
    """SHOpenFolderAndSelectItems: reliable selection (explorer /select is ignored when Explorer is busy
    or the path has unusual characters) and it reuses an already-open window of that folder."""
    from ctypes import wintypes
    shell32, ole32 = ctypes.windll.shell32, ctypes.windll.ole32
    ole32.CoInitialize(None)
    shell32.ILCreateFromPathW.restype = ctypes.c_void_p
    shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
    shell32.ILFree.argtypes = [ctypes.c_void_p]
    shell32.SHOpenFolderAndSelectItems.argtypes = [ctypes.c_void_p, wintypes.UINT, ctypes.c_void_p, wintypes.DWORD]
    folder = os.path.dirname(os.path.normpath(paths[0]))
    same = [os.path.normpath(x) for x in paths if os.path.dirname(os.path.normpath(x)) == folder]
    pf = shell32.ILCreateFromPathW(folder)
    items = [shell32.ILCreateFromPathW(x) for x in same]
    items = [i for i in items if i]
    if not pf or not items:
        raise OSError("could not resolve path")
    try:
        arr = (ctypes.c_void_p * len(items))(*items)
        hr = shell32.SHOpenFolderAndSelectItems(pf, len(items), arr, 0)
        if hr < 0:                                   # failed HRESULT
            raise OSError(f"SHOpenFolderAndSelectItems {hr & 0xFFFFFFFF:#x}")
    finally:
        for i in items:
            shell32.ILFree(i)
        shell32.ILFree(pf)


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

    def __init__(self, on_wheel, should_swallow=lambda: False, on_ctrl_double=None, ctrl_double_enabled=lambda: False):
        self.on_wheel = on_wheel
        self.should_swallow = should_swallow
        self.on_ctrl_double = on_ctrl_double          # Ctrl + double-click on a file in Explorer -> Float
        self.ctrl_double_enabled = ctrl_double_enabled
        self._first = None                            # (time, x, y) of the first Ctrl-click
        self._eat_up = False
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

        WM_LBUTTONDOWN, WM_LBUTTONUP = 0x0201, 0x0202
        dbl_ms = user32.GetDoubleClickTime()
        dbl_dx, dbl_dy = max(4, user32.GetSystemMetrics(36)), max(4, user32.GetSystemMetrics(37))   # SM_CXDOUBLECLK

        def ctrl_click(w_param, info):
            """True = swallow. The 2nd click of a Ctrl+double-click on Explorer/desktop is kept from
            Explorer (so it doesn't open the file) and reported to the app instead."""
            if w_param == WM_LBUTTONUP and self._eat_up:
                self._eat_up = False
                return True
            if w_param != WM_LBUTTONDOWN or self.on_ctrl_double is None:
                return False
            if not (user32.GetAsyncKeyState(0x11) & 0x8000) or not self.ctrl_double_enabled():
                self._first = None
                return False
            root = root_window_at(info.pt.x, info.pt.y)
            if window_class(root) not in ("CabinetWClass", "ExploreWClass", "Progman", "WorkerW"):
                self._first = None
                return False
            f = self._first
            if f and info.time - f[0] <= dbl_ms and abs(info.pt.x - f[1]) <= dbl_dx and abs(info.pt.y - f[2]) <= dbl_dy:
                self._first = None
                self._eat_up = True
                self.on_ctrl_double(root)
                return True
            self._first = (info.time, info.pt.x, info.pt.y)
            return False

        def proc(n_code, w_param, l_param):
            if n_code == 0 and w_param in (WM_LBUTTONDOWN, WM_LBUTTONUP):
                try:
                    info = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
                    if ctrl_click(w_param, info):
                        return 1
                except Exception:
                    pass
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

        # ---- Ctrl + Enter on a selected file in Explorer / on the desktop -> Float (keyboard twin of the above)
        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

        class GUITHREADINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("flags", wintypes.DWORD), ("hwndActive", wintypes.HWND),
                        ("hwndFocus", wintypes.HWND), ("hwndCapture", wintypes.HWND), ("hwndMenuOwner", wintypes.HWND),
                        ("hwndMoveSize", wintypes.HWND), ("hwndCaret", wintypes.HWND), ("rcCaret", wintypes.RECT)]

        WH_KEYBOARD_LL, WM_KEYDOWN, WM_KEYUP, VK_RETURN = 13, 0x0100, 0x0101, 0x0D
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.c_void_p]
        user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.c_void_p]

        def focus_in_file_list():
            """The Explorer window (or desktop) in front, if its file list has the keyboard focus —
            not the address bar, search box or a file being renamed."""
            fg = user32.GetForegroundWindow()
            if not fg or window_class(fg) not in ("CabinetWClass", "ExploreWClass", "Progman", "WorkerW"):
                return None
            gti = GUITHREADINFO()
            gti.cbSize = ctypes.sizeof(GUITHREADINFO)
            if not user32.GetGUIThreadInfo(user32.GetWindowThreadProcessId(fg, None), ctypes.byref(gti)):
                return None
            if not gti.hwndFocus or window_class(gti.hwndFocus) not in ("DirectUIHWND", "SysListView32"):
                return None
            return fg

        def kproc(n_code, w_param, l_param):
            if n_code == 0 and w_param in (WM_KEYDOWN, WM_KEYUP) and self.on_ctrl_double is not None:
                try:
                    info = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    if info.vkCode == VK_RETURN:
                        if w_param == WM_KEYUP:
                            self._enter_down = False
                            if self._eat_enter_up:
                                self._eat_enter_up = False
                                return 1
                        if (w_param == WM_KEYDOWN and user32.GetAsyncKeyState(0x11) & 0x8000
                                and not user32.GetAsyncKeyState(0x10) & 0x8000 and not user32.GetAsyncKeyState(0x12) & 0x8000
                                and self.ctrl_double_enabled()):
                            fg = focus_in_file_list()
                            if fg:
                                self._eat_enter_up = True
                                if not self._enter_down:          # key repeat: open once
                                    self._enter_down = True
                                    self.on_ctrl_double(fg)
                                return 1
                except Exception:
                    pass
            return user32.CallNextHookEx(None, n_code, w_param, l_param)

        self._eat_enter_up = False
        self._enter_down = False
        self._proc = HOOKPROC(proc)            # keep a reference or it gets collected
        self._kproc = HOOKPROC(kproc)
        self._tid = kernel32.GetCurrentThreadId()
        hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            log("mouse hook could not be installed")
            return
        khook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._kproc, kernel32.GetModuleHandleW(None), 0)
        log("mouse hook installed" + ("" if khook else " (keyboard hook failed)"))
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        user32.UnhookWindowsHookEx(hook)
        if khook:
            user32.UnhookWindowsHookEx(khook)


# ----------------------------------------------------------------------------
# Run an Explorer right-click entry (e.g. "Send with Quick Share") on files
# ----------------------------------------------------------------------------
def quick_share_installed() -> str | None:
    """Path of Google's Quick Share for Windows, if installed."""
    if not IS_WIN:
        return None
    roots = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", ""),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")]
    for root in filter(None, roots):
        for sub in ("Google\\NearbyShare", "Google\\QuickShare", "Google\\Quick Share", "Google\\Nearby Share"):
            d = Path(root) / sub
            if d.is_dir():
                for name in ("nearby_share.exe", "quick_share.exe", "QuickShare.exe"):    # the app itself, not its helpers
                    hit = next(d.rglob(name), None)
                    if hit:
                        return str(hit)
    return None


def drop_files_on(target, paths) -> bool:
    """Drop files on `target` (a shortcut, program or folder) exactly as Explorer's drag-and-drop or Send To does."""
    if not IS_WIN or not paths:
        return False
    import pythoncom
    from win32com.shell import shell
    try:
        pythoncom.OleInitialize()
    except Exception:
        pass
    desktop = shell.SHGetDesktopFolder()

    def split(path):
        pidl, _attrs = shell.SHParseDisplayName(str(path), 0)
        parent = pidl[:-1]
        folder = desktop.BindToObject(parent, None, shell.IID_IShellFolder) if parent else desktop
        return folder, pidl[-1:]

    tfolder, tchild = split(target)
    drop = tfolder.GetUIObjectOf(0, [tchild], pythoncom.IID_IDropTarget, 0)[1]
    groups = {}
    for p in paths:
        groups.setdefault(str(Path(p).parent), []).append(Path(p))
    done = False
    for _parent, items in groups.items():
        folder, _c = split(items[0])
        kids = [split(x)[1] for x in items]
        data = folder.GetUIObjectOf(0, kids, pythoncom.IID_IDataObject, 0)[1]
        effect = drop.DragEnter(data, 1, (0, 0), 1)            # left button, copy
        if not effect:
            drop.DragLeave()
            continue
        drop.Drop(data, 1, (0, 0), 1)
        done = True
    log(f"dropped {len(paths)} item(s) on {Path(target).name}: {done}")
    return done


def sendto_entry(*words) -> Path | None:
    """A shortcut in the user's Send To folder whose name contains one of `words`."""
    folder = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "SendTo"
    try:
        for f in folder.iterdir():
            if any(w.lower() in f.name.lower() for w in words):
                return f
    except OSError:
        pass
    return None


def invoke_shell_verb(paths, *names) -> bool:
    """Run the right-click entry whose text contains one of `names` on all `paths` (same folder = one action).
    True if it was found and started."""
    if not IS_WIN or not paths:
        return False
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    shell = win32com.client.Dispatch("Shell.Application")
    by_folder = {}
    for p in paths:
        p = Path(p)
        by_folder.setdefault(str(p.parent), []).append(p.name)
    started = False
    for folder, files in by_folder.items():
        ns = shell.Namespace(folder)
        if ns is None:
            continue
        if len(files) == 1:
            item = ns.ParseName(files[0])
            verbs = item.Verbs() if item is not None else None
        else:
            items = ns.Items()
            try:
                items.Filter(0x20 | 0x40 | 0x80, ";".join(files))      # folders, files, hidden: just these
            except Exception:
                pass
            verbs = items.Verbs()
        if verbs is None:
            continue
        for i in range(verbs.Count):
            v = verbs.Item(i)
            label = (v.Name or "").replace("&", "").lower()
            if any(n.lower() in label for n in names):
                log(f"shell verb: {v.Name} on {len(files)} item(s)")
                v.DoIt()
                started = True
                break
    return started


def recycle(path: str) -> None:
    """Move a file or folder to the Recycle Bin (can be restored)."""
    if not IS_WIN:
        os.remove(path)
        return
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
    op = SHFILEOPSTRUCTW()
    op.wFunc = 3                                           # FO_DELETE
    op.pFrom = os.path.abspath(path) + "\0"
    op.fFlags = 0x0040 | 0x0010 | 0x0004 | 0x0400          # ALLOWUNDO, NOCONFIRMATION, SILENT, NOERRORUI
    r = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    if r != 0:
        raise OSError(f"Recycle Bin: error {r}")

