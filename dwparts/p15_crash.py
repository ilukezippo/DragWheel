"""DragWheel: Crash reports — off by default. When turned on, DragWheel shows the report and asks before anything is sent;

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


# ============================================================================
# Crash reports — off by default. When turned on, DragWheel shows the report and asks before anything is sent;
# sending opens a GitHub issue in your browser that you can read and edit first. Nothing is sent by itself.
# ============================================================================
def _crash_dir() -> Path:
    d = winsys.log_path().parent / "crash"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _anonymize(text: str) -> str:
    """Hide the Windows user name and home folder in a report."""
    import getpass
    home = str(Path.home())
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    for needle in {home, home.replace("\\", "/")}:
        if needle:
            text = text.replace(needle, "%USERPROFILE%")
    if user and len(user) > 2:
        text = text.replace(user, "<user>")
    return text


def crash_report_text(kind, details) -> str:
    import platform
    try:
        from PySide6 import __version__ as qt
    except Exception:
        qt = "?"
    lines = [f"DragWheel {VERSION} ({'installed' if getattr(sys, 'frozen', False) else 'source'})",
             f"Windows {platform.version()} · Python {platform.python_version()} · Qt {qt}",
             f"Language: {settings().value('language', '') or 'system'}", "", f"What happened: {kind}", "", details.strip()]
    try:                                                           # the last lines of the log help a lot
        tail = winsys.log_path().read_text(encoding="utf-8", errors="replace").splitlines()[-25:]
        lines += ["", "Last log lines:"] + tail
    except OSError:
        pass
    return _anonymize("\n".join(lines))


class CrashDialog(QDialog):
    """Shows exactly what a report contains, then lets you send it (on GitHub), copy it, or close."""

    def __init__(self, text):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        self.text = text
        self.setWindowTitle(f"{APP} — " + tr("Something went wrong"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.resize(620, 460)
        lay = QVBoxLayout(self)
        head = QLabel("<b>" + tr("Something went wrong in DragWheel") + "</b><br>" +
                      tr("Sending this report helps fix it. This is everything it contains — your user name is hidden. "
                         "Send opens GitHub in your browser, where you can read it again and change it before posting."))
        head.setWordWrap(True)
        lay.addWidget(head)
        from PySide6.QtWidgets import QPlainTextEdit
        box = QPlainTextEdit(text)
        box.setReadOnly(True)
        box.setStyleSheet(f"background:{theme.hexc('surface')};color:{theme.hexc('text')};font:9pt Consolas")
        lay.addWidget(box, 1)
        row = QHBoxLayout()
        b = QPushButton(tr("Copy"))
        b.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.text))
        row.addWidget(b)
        row.addStretch(1)
        b = QPushButton(tr("Don't send"))
        b.clicked.connect(self.reject)
        row.addWidget(b)
        send = QPushButton(tr("Send report"))
        send.setDefault(True)
        send.clicked.connect(self._send)
        row.addWidget(send)
        lay.addLayout(row)

    def _send(self):
        from urllib.parse import quote
        first = next((ln for ln in reversed(self.text.splitlines()) if "Error" in ln or "Exception" in ln), "Crash report")
        body = self.text if len(self.text) < 6000 else self.text[:6000] + "\n…"
        url = (f"{updater.REPO_URL}/issues/new?title={quote('Crash: ' + first.strip()[:90])}"
               f"&labels=crash&body={quote('```\n' + body + '\n```')}")
        QDesktopServices.openUrl(QUrl(url))
        winsys.log("crash report: opened on GitHub")
        self.accept()


_CRASH_SEEN = set()


_CRASH_LOGGED = set()


def report_crash(kind, details):
    """Every crash goes to the log and the crash folder (once per kind of error per session); the report window
    only when crash reports are on."""
    key = (details.strip().splitlines()[-1] if details.strip() else kind) + "|" + \
        next((ln.strip() for ln in reversed(details.splitlines()) if ln.strip().startswith("File ")), "")
    if key in _CRASH_LOGGED:
        return
    _CRASH_LOGGED.add(key)
    text = crash_report_text(kind, details)
    import time
    try:
        (_crash_dir() / time.strftime("crash-%Y%m%d-%H%M%S.txt")).write_text(text, encoding="utf-8")
    except OSError:
        pass
    winsys.log(f"crash: {kind}: {details.strip().splitlines()[-1] if details.strip() else ''}")
    if settings().value("crash_reports", "false") != "true" or key in _CRASH_SEEN:
        return
    _CRASH_SEEN.add(key)
    app = QApplication.instance()
    if app is not None:
        QTimer.singleShot(0, lambda: CrashDialog(text).exec())


def install_crash_handlers():
    import faulthandler
    import threading as _th
    import traceback as _tb

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            return
        report_crash(exc_type.__name__, "".join(_tb.format_exception(exc_type, exc, tb)))
    sys.excepthook = hook
    _th.excepthook = lambda a: hook(a.exc_type, a.exc_value, a.exc_traceback)
    # a hard crash (inside Qt or a library) can't be caught: faulthandler writes it down, and the next start offers it
    d = _crash_dir()
    try:                                            # keep the crash folder small: the newest 20, under 30 days
        import time as _t
        old = sorted(d.glob("crash-*.txt"), key=lambda f: f.stat().st_mtime, reverse=True)
        for i, f in enumerate(old):
            if i >= 20 or _t.time() - f.stat().st_mtime > 30 * 86400:
                f.unlink(missing_ok=True)
    except OSError:
        pass
    native, running = d / "last-session.txt", d / "running"
    if running.exists() and native.exists() and native.stat().st_size > 0:
        QTimer.singleShot(3000, lambda t=native.read_text(encoding="utf-8", errors="replace"):
                          report_crash("DragWheel closed unexpectedly last time", t))
    running.write_text(str(os.getpid()), encoding="utf-8")
    global _FAULT_FILE
    _FAULT_FILE = open(native, "w", encoding="utf-8")
    faulthandler.enable(_FAULT_FILE, all_threads=True)


def crash_handlers_clean_exit():
    try:
        (_crash_dir() / "running").unlink(missing_ok=True)
    except OSError:
        pass


_FAULT_FILE = None
