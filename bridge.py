"""DragWheel for Browser: the bridge between the browser extension and DragWheel.

The extension talks to DragWheel through the browser's "native messaging": the browser starts DragWheel.exe
with the extension's address as the argument and exchanges small JSON messages over stdin/stdout. This module
is that short-lived helper: it reads one message, hands the work to the DragWheel that's running (or starts
it), answers, and exits. It never opens a window.

Messages from the extension:
  {"type": "ping"}                                            -> {"ok": true, "version": "..."}
  {"type": "float", "url": "...", "title": "..."}             play a page, video or song link in a Float
  {"type": "image", "data": "<base64>", "mime": "image/png",
   "name": "photo", "url": "...", "format": "png"}            save a picture in that format (Downloads)
                                                             format "original" keeps it as it is,
                                                             "wheel" opens DragWheel's Convert wheel on it
"""
from __future__ import annotations

import base64
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HOST = "com.ilukezippo.dragwheel"
EXTENSION_ID = "jlenhhcngfnmbeipchmfonemmlinooha"            # fixed by the "key" in the extension's manifest
CHROME_STORE_ID = "mabjkdfbddokmmfbdhgkgcmhalgkbbcj"         # the Chrome Web Store gives its own id
EXTENSION_IDS = [EXTENSION_ID, CHROME_STORE_ID]              # the bundled copy and the store one may both talk to us
CHROME_LIVE = True                    # the Chrome Web Store published it (Nov 2026)
FIREFOX_LIVE = True                   # Firefox Add-ons published it (Nov 9 2026)
STORE_LIVE = CHROME_LIVE or FIREFOX_LIVE
CHROME_STORE_URL = f"https://chromewebstore.google.com/detail/{CHROME_STORE_ID}"
FIREFOX_STORE_URL = "https://addons.mozilla.org/firefox/addon/dragwheel-for-browser/"
CWS_UPDATE_URL = "https://clients2.google.com/service/update2/crx"
OFFER_KEYS = (("Chrome", r"Software\Google\Chrome\Extensions"), ("Edge", r"Software\Microsoft\Edge\Extensions"),
              ("Brave", r"Software\BraveSoftware\Brave-Browser\Extensions"))
FIREFOX_ID = "dragwheel@ilukezippo"
FORMATS = {"png", "jpg", "webp", "avif", "gif", "bmp", "tiff", "ico", "pdf", "heic", "original", "wheel"}
MIME_EXT = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg", "image/webp": "webp", "image/gif": "gif",
            "image/avif": "avif", "image/bmp": "bmp", "image/svg+xml": "svg", "image/x-icon": "ico",
            "image/vnd.microsoft.icon": "ico", "image/tiff": "tiff", "image/heic": "heic"}


def is_host_launch(argv) -> bool:
    """Started by a browser for the extension: Chrome/Edge pass "chrome-extension://<id>/", Firefox passes the
    manifest's path and the extension's id."""
    return any(a.startswith("chrome-extension://") for a in argv) or \
        (len(argv) >= 2 and argv[0].lower().endswith(".json") and argv[1] == FIREFOX_ID)


def _pipes():
    """stdin/stdout as binary files. DragWheel.exe is a windowed program, so Python leaves sys.stdin/stdout
    empty; the browser's pipes are still there as Windows handles."""
    if sys.stdin is not None and sys.stdout is not None and hasattr(sys.stdin, "buffer"):
        return sys.stdin.buffer, sys.stdout.buffer
    import ctypes
    import msvcrt
    k = ctypes.windll.kernel32
    k.GetStdHandle.restype = ctypes.c_void_p
    fin = os.fdopen(msvcrt.open_osfhandle(k.GetStdHandle(-10), os.O_RDONLY | os.O_BINARY), "rb", buffering=0)
    fout = os.fdopen(msvcrt.open_osfhandle(k.GetStdHandle(-11), os.O_BINARY), "wb", buffering=0)
    return fin, fout


def _read(fin):
    head = fin.read(4)
    if len(head) < 4:
        return None
    n = struct.unpack("<I", head)[0]
    data = b""
    while len(data) < n:
        part = fin.read(n - len(data))
        if not part:
            break
        data += part
    return json.loads(data.decode("utf-8"))


def _write(fout, obj):
    data = json.dumps(obj).encode("utf-8")
    fout.write(struct.pack("<I", len(data)) + data)
    fout.flush()


def _safe_name(name, ext):
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", (name or "").strip())[:80].strip(" .") or "image"
    stem = re.sub(r"\.(png|jpe?g|webp|gif|avif|bmp|svg|ico|tiff?|heic)$", "", stem, flags=re.I) or "image"
    return f"{stem}.{ext}"


_SEND = None        # DragWheel's "send to the running instance", given by run_host
_VERSION = ""


def _deliver(flags, paths):
    """Hand the work to the running DragWheel, or start DragWheel with it."""
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication.instance() or QCoreApplication([])     # (the local socket wants one)
    if _SEND is not None and _SEND({"paths": paths, "flags": flags}):
        return True
    exe = sys.executable if getattr(sys, "frozen", False) else None
    cmd = [exe] if exe else [sys.executable, str(Path(__file__).with_name("dragwheel.pyw"))]
    subprocess.Popen(cmd + flags + paths, close_fds=True,
                     creationflags=0x00000008 | 0x00000200 if os.name == "nt" else 0)   # detached, own group
    del app
    return True


def handle(msg) -> dict:
    kind = (msg or {}).get("type")
    if kind == "ping":
        return {"ok": True, "version": _VERSION}
    if kind == "float":
        url = str(msg.get("url") or "").strip()
        if not url.lower().startswith(("http://", "https://")):
            return {"ok": False, "error": "That isn't a web address DragWheel can play."}
        _deliver(["--play-url"], [url])
        return {"ok": True}
    if kind == "image":
        fmt = str(msg.get("format") or "png").lower()
        if fmt not in FORMATS:
            return {"ok": False, "error": f"Unknown format: {fmt}"}
        try:
            data = base64.b64decode(msg.get("data") or "", validate=False)
        except ValueError:
            data = b""
        if not data:
            return {"ok": False, "error": "The picture couldn't be read from the page."}
        ext = MIME_EXT.get(str(msg.get("mime") or "").split(";")[0].strip().lower())
        if not ext:
            m = re.search(r"\.(png|jpe?g|webp|gif|avif|bmp|svg|ico|tiff?|heic)(?:$|[?#])",
                          str(msg.get("url") or ""), re.I)
            ext = (m.group(1).lower().replace("jpeg", "jpg") if m else "png")
        folder = Path(tempfile.gettempdir()) / "DragWheel web pictures"
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / _safe_name(msg.get("name"), ext)
        n = 1
        while tmp.exists():
            n += 1
            tmp = folder / _safe_name(f"{msg.get('name') or 'image'} ({n})", ext)
        tmp.write_bytes(data)
        _deliver(["--save-image", f"--as={fmt}"], [str(tmp)])
        return {"ok": True}
    return {"ok": False, "error": "Unknown request"}


def run_host(version="", send=None) -> int:
    global _SEND, _VERSION
    _SEND, _VERSION = send, version
    fin, fout = _pipes()
    try:
        msg = _read(fin)
        reply = handle(msg) if msg is not None else {"ok": False, "error": "no message"}
    except Exception as e:                                      # always answer, so the extension can say why
        reply = {"ok": False, "error": str(e)}
    try:
        _write(fout, reply)
    except OSError:
        pass
    return 0


# ---- registration: tell Chrome, Edge (and Chromium browsers using Chrome's list) and Firefox where the host is
def register(exe: str, data_dir: Path) -> None:
    if os.name != "nt":
        return
    import winreg
    data_dir.mkdir(parents=True, exist_ok=True)
    chromium = data_dir / f"{HOST}.json"
    firefox = data_dir / f"{HOST}.firefox.json"
    base = {"name": HOST, "description": "DragWheel for Browser", "path": exe, "type": "stdio"}
    chromium.write_text(json.dumps(dict(base, allowed_origins=[f"chrome-extension://{i}/" for i in EXTENSION_IDS]), indent=1),
                        encoding="utf-8")
    firefox.write_text(json.dumps(dict(base, allowed_extensions=[FIREFOX_ID]), indent=1), encoding="utf-8")
    for key, manifest in ((rf"Software\Google\Chrome\NativeMessagingHosts\{HOST}", chromium),
                          (rf"Software\Microsoft\Edge\NativeMessagingHosts\{HOST}", chromium),
                          (rf"Software\BraveSoftware\Brave-Browser\NativeMessagingHosts\{HOST}", chromium),
                          (rf"Software\Chromium\NativeMessagingHosts\{HOST}", chromium),
                          (rf"Software\Vivaldi\NativeMessagingHosts\{HOST}", chromium),
                          (rf"Software\Mozilla\NativeMessagingHosts\{HOST}", firefox)):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, str(manifest))


def offer_extension() -> list:
    """Offer the store extension to Chrome, Edge and Brave, the way IDM does: each browser then shows
    "DragWheel for Browser was added" the next time it starts, and one click turns it on (it comes from the
    Chrome Web Store). A browser remembers when someone removes an extension offered like this, and doesn't add
    it again. (Firefox doesn't let programs add extensions since Firefox 74: DragWheel opens its add-on page
    instead, see firefox_exe.) Returns the browsers it was offered to."""
    if os.name != "nt" or not CHROME_LIVE:
        return []
    import winreg
    done = []
    for name, base in OFFER_KEYS:
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"{base}\{CHROME_STORE_ID}") as k:
                winreg.SetValueEx(k, "update_url", 0, winreg.REG_SZ, CWS_UPDATE_URL)
            done.append(name)
        except OSError:
            pass
    return done


def firefox_exe() -> str | None:
    """Where Firefox is installed (None if it isn't)."""
    if os.name != "nt":
        return None
    import winreg
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\firefox.exe") as k:
                path = str(winreg.QueryValueEx(k, "")[0]).strip('"')
                if os.path.exists(path):
                    return path
        except OSError:
            continue
    return None


def withdraw_extension() -> None:
    """Undo offer_extension (the browsers then remove the extension they got that way)."""
    if os.name != "nt":
        return
    import winreg
    for _name, base in OFFER_KEYS:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rf"{base}\{CHROME_STORE_ID}")
        except OSError:
            pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Mozilla\Firefox\Extensions", 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, FIREFOX_ID)
    except OSError:
        pass
