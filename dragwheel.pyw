"""
DragWheel — drag a file, tap a key, drop on the wheel. Offline file converter for Windows.

Drag a file, tap Shift  -> conversion wheel
                 tap Ctrl   -> file tools (compress, trim, resize, merge…)
                 tap Alt    -> file actions (copy, move, terminal, float…)
Drop on a slice to apply it. Everything runs locally.

Also: select files in Explorer and press Ctrl+Alt+Space, or right-click > "DragWheel".
"""
from __future__ import annotations

import getpass
import json
import math
import os
import shutil
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPointF, QPropertyAnimation, QRectF, QRunnable, QSizeF, QVariantAnimation,
                            QRect, QSettings, QSize, Qt, QThreadPool, QTimer, QUrl, Signal, QMimeData, QPoint)
from PySide6.QtGui import (QTextDocumentFragment, QAction, QBrush, QColor, QCursor, QDesktopServices, QDrag, QFont, QFontMetrics,
                           QGuiApplication, QIcon, QImage, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
                           QPolygonF, QRadialGradient)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QTabWidget,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox,
                               QPushButton, QSystemTrayIcon, QVBoxLayout, QWidget)

import engine
import i18n
import theme
import updater
import winsys
from i18n import tr

APP = "DragWheel"
DONATE_URL = "https://buymeacoffee.com/ilukezippo"
VERSION = "1.2.3"

ACCENT = QColor("#ff8a00")
ACCENT_2 = QColor("#ffb347")
ON_ACCENT = QColor("#1c1c1e")


def sync_accent():
    """The theme's accent colour, used by everything that's painted (changed in place, so it's everywhere)."""
    try:
        ACCENT.setRgba(QColor(theme.hexc("accent")).rgba())
        ON_ACCENT.setRgba(QColor(theme.hexc("on_accent")).rgba())
    except Exception:
        pass


def C(name):
    """Current theme colour (see theme.py)."""
    return theme.color(name)

MODES = ["convert", "tool", "action"]
MODE_LABEL = {"convert": "Convert", "tool": "Tools", "action": "Actions"}   # translated at use: tr(MODE_LABEL[m])
DEFAULT_KEYS = {"convert": "Shift", "tool": "Ctrl", "action": "Alt"}


def settings() -> QSettings:
    return QSettings(APP, APP)


_KEYS_CACHE: list = [0.0, None]


def mode_keys() -> dict[str, str]:
    """The wheel keys. The drag watcher asks 30 times a second, so this is kept for 2 s rather than read from
    the registry each time (a slow registry read once froze the app); saving settings clears it at once."""
    now = time.monotonic()
    if _KEYS_CACHE[1] is None or now - _KEYS_CACHE[0] > 2.0:
        s = settings()
        _KEYS_CACHE[:] = [now, {m: s.value(f"keys/{m}", DEFAULT_KEYS[m]) for m in MODES}]
    return dict(_KEYS_CACHE[1])


_QUICK: dict = {}


def quick_setting(key: str, default: str) -> str:
    """A setting read while painting or animating: kept for 1 s, so a 60-a-second repaint doesn't hit the registry."""
    now = time.monotonic()
    hit = _QUICK.get(key)
    if hit is None or now - hit[0] > 1.0:
        hit = _QUICK[key] = (now, settings().value(key, default))
    return hit[1]


def keys_changed():
    _KEYS_CACHE[1] = None
    _QUICK.clear()


def trigger_mode() -> str:
    """When a wheel key opens the wheel: "drag" (while dragging a file), "hover" (also when pointing at a file),
    "select" (also for the files selected in Explorer)."""
    v = settings().value("trigger_mode", "drag")
    return v if v in ("drag", "hover", "select") else "drag"


def peek_key() -> str:
    """The key that shows Quick preview while dragging (Space unless you chose another, or turned it off)."""
    s = settings()
    v = s.value("keys/peek", None)
    if v is None:
        v = "Space" if s.value("peek", "true") == "true" else "None"
    return v


# Windows language ids NSIS uses for each app language (Setup remembers its choice under "InstallerLanguage")
INSTALLER_LANG_IDS = {"en": 1033, "ar": 1025, "fr": 1036, "es": 1034, "de": 1031, "it": 1040, "pt": 1046, "tr": 1055,
                      "ru": 1049, "fa": 1065, "ur": 1056, "hi": 1081, "ja": 1041, "zh": 2052}


def peek_hold() -> bool:
    """File preview: True = shown while the key is held, False = press to open, press again to close."""
    return settings().value("peek_hold", "false") == "true"


def key_label(spec: str) -> str:
    """'Ctrl+Q' as shown to you (each part translated)."""
    return " + ".join(tr(p) for p in (spec or "None").split("+") if p) or tr("None")



# ============================================================================
# The rest of the program, in parts by feature (dwparts/)
# ============================================================================
PARTS = ["p01_files", "p02_actions", "p03_notes", "p04_worker", "p05_wheel", "p06_toast", "p07_float", "p08_dialogs",
         "p09_trimmer", "p10_pdfpages", "p11_settings", "p12_customize", "p13_dragwatch", "p14_app", "p15_crash"]


def load_parts(ns):
    """Run each part of the program in `ns` (this file's namespace), in order. They behave exactly as if they
    were still written here; tracebacks name the part's own file and line."""
    import importlib.util
    for name in PARTS:
        spec = importlib.util.find_spec(f"dwparts.{name}")
        exec(spec.loader.get_code(spec.name), ns)


load_parts(globals())



# ============================================================================
# Single instance
# ============================================================================
SERVER_NAME = f"dragwheel-{getpass.getuser()}"


def send_to_running(args) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(400):
        return False
    sock.write(json.dumps(args).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def ask_running_to_close() -> int:
    sock = QLocalSocket()
    sock.connectToServer(SERVER_NAME)
    if not sock.waitForConnected(1000):
        return 0                                   # not running
    sock.write(json.dumps({"paths": [], "flags": ["--prepare-update"]}).encode("utf-8"))
    sock.flush()
    sock.waitForBytesWritten(1000)
    reply = b""
    import time
    end = time.monotonic() + 15 * 60               # the user may take a while to answer the jobs warning
    while time.monotonic() < end and not reply:
        if sock.waitForReadyRead(500):
            reply = bytes(sock.readAll())
        elif sock.state() != QLocalSocket.ConnectedState:
            break
    if reply.startswith(b"no"):
        return 1
    # wait for DragWheel to finish closing (cancelled jobs clean up first)
    while time.monotonic() < end:
        probe = QLocalSocket()
        probe.connectToServer(SERVER_NAME)
        if not probe.waitForConnected(300):
            break
        probe.disconnectFromServer()
        time.sleep(0.4)
    return 0


def parse_args(argv):
    paths, flags = [], set()
    for a in argv:
        (flags.add(a) if a.startswith("--") else paths.append(a))
    return flags, paths


def selftest() -> int:
    """Diagnostics for the packaged app: runs a job in a worker process, then cancels one.
    Results go to the log file (%LOCALAPPDATA%\\DragWheel\\dragwheel.log)."""
    import tempfile
    import time
    import jobproc
    d = Path(tempfile.mkdtemp(prefix="dw-selftest-"))
    (d / "data").mkdir()
    (d / "data" / "a.txt").write_text("hello", encoding="utf-8")
    t0 = time.monotonic()
    res = jobproc.JobProcess("convert", "to_zip", [str(d / "data")], {}, None).run(lambda: False)
    winsys.log(f"selftest job: {res} in {time.monotonic() - t0:.1f}s")
    big = d / "big"
    big.mkdir()
    with open(big / "blob.bin", "wb") as fh:
        fh.write(os.urandom(80 * 1024 * 1024))
    start = time.monotonic()
    res = jobproc.JobProcess("convert", "to_7z", [str(big)], {}, None).run(lambda: time.monotonic() - start > 3)
    left = [p.name for p in d.iterdir()]
    winsys.log(f"selftest cancel: {res} after {time.monotonic() - start:.1f}s, folder={left}")
    try:                                     # PDF → Word (same look) works in the packaged app
        import pymupdf
        pdf = pymupdf.open()
        pg = pdf.new_page()
        pg.insert_text((72, 90), "Hello DragWheel", fontsize=14)
        pg.draw_rect(pymupdf.Rect(60, 60, 300, 110), color=(0, 0, 0))
        pdf.save(str(d / "letter.pdf"))
        pdf.close()
        res = jobproc.JobProcess("convert", "to_docx", [str(d / "letter.pdf")], {}, None).run(lambda: False)
        winsys.log(f"selftest pdf→docx: {res}")
    except Exception as e:
        winsys.log(f"selftest pdf→docx failed: {e}")
    import shutil
    shutil.rmtree(d, ignore_errors=True)
    return 0


def main():
    import multiprocessing
    multiprocessing.freeze_support()      # worker processes of the frozen exe start here and exit
    args = sys.argv[1:]
    import bridge
    if bridge.is_host_launch(args):                 # started by a browser for DragWheel for Browser: no window
        return bridge.run_host(VERSION, send_to_running)
    if args and args[0] == "--cli":                  # dragwheel.cmd
        args = args[1:] or ["help"]
    if args and args[0].lower() in ("convert", "tool", "list", "help", "/?", "-h"):
        import cli
        return cli.main(args)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DragWheel.App")
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)
    qapp.setApplicationName(APP)
    qapp.setWindowIcon(app_icon())
    qapp.setFont(QFont(i18n.ui_font(), 9))
    _button_fix = ButtonPolish(qapp)
    qapp.installEventFilter(_button_fix)

    flags, paths = parse_args(sys.argv[1:])
    paths = [os.path.abspath(p) if os.path.exists(p) else p for p in paths]
    try:
        os.chdir(tempfile.gettempdir())       # not System32 (where a browser starts us), or nothing can be written
    except OSError:
        pass
    if "--selftest" in flags:
        return selftest()
    if "--prepare-update" in flags:            # run by the installer: 0 = go ahead, 1 = the user said not now
        return ask_running_to_close()
    if send_to_running({"paths": paths, "flags": sorted(flags)}):
        return 0

    i18n.set_language(settings().value("language", ""))
    theme.set_mode(settings().value("theme", "system"))
    sync_accent()
    qapp.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
    qapp.setFont(QFont(i18n.ui_font(), 9))

    try:
        from PySide6 import __version__ as pyside_version
    except Exception:
        pyside_version = "?"
    winsys.log(f"start {APP} {VERSION} qt={pyside_version} frozen={getattr(sys, 'frozen', False)} "
               f"elevated={winsys.is_elevated()}")
    updater.cleanup(VERSION)          # the update installed fine: drop its downloaded installer
    try:
        gone = winsys.remove_legacy_satsuma()
        if gone:
            winsys.log("removed old Satsuma leftovers: " + ", ".join(gone))
    except Exception as e:
        winsys.log(f"Satsuma cleanup failed: {e}")

    try:
        winsys.ensure_cli_command()
    except Exception as e:
        winsys.log(f"cli command: {e}")
    try:
        if winsys.context_menu_enabled():
            winsys.set_context_menu(True, paste_label=tr("Save clipboard image here"), link_label=tr("Paste link to Float"),
                                    float_label=tr("Open Float"), qr_label=tr("Read QR code on screen"),
                                    note_label=tr("New sticky note"))
    except Exception as e:
        winsys.log(f"context menu refresh failed: {e}")

    try:
        install_crash_handlers()
        qapp.aboutToQuit.connect(crash_handlers_clean_exit)
    except Exception as e:
        winsys.log(f"crash handlers: {e}")

    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)
    app = DragWheelApp(qapp)

    def on_conn():
        sock = server.nextPendingConnection()

        def read():
            try:
                msg = json.loads(bytes(sock.readAll()).decode("utf-8") or "{}")
            except Exception:
                return
            if "--prepare-update" in msg.get("flags", []):
                ok = app.prepare_for_update()
                winsys.log(f"installer asked to close: {'ok' if ok else 'user said not now'}")
                sock.write(b"ok" if ok else b"no")
                sock.flush()
                sock.waitForBytesWritten(1000)
                if ok:
                    QTimer.singleShot(100, app.quit_for_update)
                return
            if "--open-float" in msg.get("flags", []):
                app.open_empty_float()
                return
            if "--play-link" in msg.get("flags", []):
                app.play_link()
                return
            if "--read-qr" in msg.get("flags", []):
                QTimer.singleShot(300, app.read_qr_on_screen)
                return
            if "--new-note" in msg.get("flags", []):
                app.open_note()
                return
            if "--star-note" in msg.get("flags", []):
                app._ask_for_star()
                return
            run = next((f[6:] for f in msg.get("flags", []) if f.startswith("--run=")), None)
            if run and msg.get("paths"):                 # right-click → DragWheel: Convert / Tools / Actions ▸ …
                app.run_from_menu(run, msg["paths"])
                return
            if "--play-url" in msg.get("flags", []) and msg.get("paths"):     # from the browser extension
                app.play_link(url=msg["paths"][0])
                return
            if "--save-image" in msg.get("flags", []) and msg.get("paths"):
                app.save_web_image(msg["paths"][0], next((f[5:] for f in msg["flags"] if f.startswith("--as=")), "png"))
                return
            if "--send-phone" in msg.get("flags", []) and msg.get("paths"):
                app.actions.phone(msg["paths"], {})
                return
            if "--paste-here" in msg.get("flags", []):
                app.save_clipboard_image((msg.get("paths") or [None])[0])
            elif msg.get("paths"):
                app.queue_paths(msg["paths"])
            elif "--tray" not in msg.get("flags", []):
                app.show_help()
        sock.readyRead.connect(read)
    server.newConnection.connect(on_conn)

    first_run = settings().value("first_run_done", "false") != "true"
    if first_run:
        settings().setValue("first_run_done", "true")
        if settings().value("installer", "") != "1":   # the installer already applied the user's choice
            try:
                winsys.set_context_menu(True, paste_label=tr("Save clipboard image here"), link_label=tr("Paste link to Float"),
                                    float_label=tr("Open Float"), qr_label=tr("Read QR code on screen"),
                                    note_label=tr("New sticky note"), sendto=True)
            except Exception:
                pass
        pass
    if (first_run or settings().value("tour_at_start", "true") == "true") and not paths and not (
            flags & {"--send-phone", "--play-link", "--paste-here", "--open-float", "--read-qr", "--new-note",
                     "--play-url", "--save-image", "--star-note"}) and not any(f.startswith("--run=") for f in flags):
        QTimer.singleShot(600, app.show_tour)         # until "Don't show this again" is ticked
    if "--send-phone" in flags and paths:
        QTimer.singleShot(300, lambda: app.actions.phone(paths, {}))
    elif "--open-float" in flags:
        QTimer.singleShot(300, app.open_empty_float)
    elif "--play-link" in flags:
        QTimer.singleShot(400, app.play_link)
    elif "--read-qr" in flags:
        QTimer.singleShot(500, app.read_qr_on_screen)
    elif "--new-note" in flags:
        QTimer.singleShot(600, app.open_note)
    elif "--star-note" in flags:
        QTimer.singleShot(1500, app._ask_for_star)
    elif any(f.startswith("--run=") for f in flags) and paths:
        spec = next(f[6:] for f in flags if f.startswith("--run="))
        QTimer.singleShot(400, lambda: app.run_from_menu(spec, paths))
    elif "--play-url" in flags and paths:
        QTimer.singleShot(600, lambda: app.play_link(url=paths[0]))
    elif "--save-image" in flags and paths:
        fmt = next((f[5:] for f in flags if f.startswith("--as=")), "png")
        QTimer.singleShot(600, lambda: app.save_web_image(paths[0], fmt))
    elif "--paste-here" in flags:
        QTimer.singleShot(300, lambda: app.save_clipboard_image(paths[0] if paths else None))
    elif paths:
        app.queue_paths(paths)
    elif "--tray" not in flags and not first_run:
        app.tray.showMessage(APP, tr("Running in the tray. Drag a file and shake the mouse.") if mode_keys()["convert"] == "None"
                             else tr("Running in the tray. Drag a file and tap {key}.", key=key_label(mode_keys()["convert"])),
                             app_icon(), 3000)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
