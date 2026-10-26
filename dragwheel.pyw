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
import threading
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import (QEasingCurve, QObject, QPointF, QPropertyAnimation, QRectF, QRunnable, QSizeF, QVariantAnimation,
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
VERSION = "1.2.1"

ACCENT = QColor("#ff8a00")
ACCENT_2 = QColor("#ffb347")
ON_ACCENT = QColor("#1c1c1e")


def C(name):
    """Current theme colour (see theme.py)."""
    return theme.color(name)

MODES = ["convert", "tool", "action"]
MODE_LABEL = {"convert": "Convert", "tool": "Tools", "action": "Actions"}   # translated at use: tr(MODE_LABEL[m])
DEFAULT_KEYS = {"convert": "Shift", "tool": "Ctrl", "action": "Alt"}


def settings() -> QSettings:
    return QSettings(APP, APP)


def mode_keys() -> dict[str, str]:
    s = settings()
    return {m: s.value(f"keys/{m}", DEFAULT_KEYS[m]) for m in MODES}


# ============================================================================
# Files: batch rename, checksum, shred, send to phone
# ============================================================================
_AR_NUM = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
_EN_NUM = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _date_of(path, source):
    import datetime
    if source == "today":
        return datetime.date.today()
    if source == "taken":
        try:
            from PIL import Image
            with Image.open(path) as im:
                v = (im.getexif().get_ifd(0x8769) or {}).get(36867) or im.getexif().get(306)
            if v:
                return datetime.datetime.strptime(str(v)[:10], "%Y:%m:%d").date()
        except Exception:
            pass
    return datetime.date.fromtimestamp(os.path.getmtime(path))


class BatchRenameDialog(QDialog):
    """Rename many files at once with a live preview: new name or find/replace, numbers, dates,
    Arabic or Western numerals, letter case."""
    DATE_FORMATS = ["2026-10-24", "24-10-2026", "20261024"]

    def __init__(self, paths):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        from PySide6.QtWidgets import QSpinBox, QTableWidget, QHeaderView, QRadioButton, QButtonGroup
        self.setWindowTitle(f"{APP} — " + tr("Rename…").rstrip("…"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.resize(820, 560)
        natural = lambda t: [int(x) if x.isdigit() else x.lower() for x in __import__("re").split(r"(\d+)", Path(t).name)]
        self.paths = sorted((str(p) for p in paths), key=natural)
        root = QHBoxLayout(self)
        form = QFormLayout()
        side = QVBoxLayout()
        side.addLayout(form)
        root.addLayout(side, 0)
        self.name_mode = QComboBox()
        self.name_mode.addItem(tr("Keep the name"), "keep")
        self.name_mode.addItem(tr("New name"), "new")
        form.addRow(tr("Name"), self.name_mode)
        self.new_name = QLineEdit()
        self.new_name.setPlaceholderText(tr("e.g. Trip"))
        form.addRow("", self.new_name)
        self.find, self.repl = QLineEdit(), QLineEdit()
        form.addRow(tr("Find"), self.find)
        form.addRow(tr("Replace with"), self.repl)
        self.num_on = QCheckBox(tr("Add a number"))
        self.num_start, self.num_digits = QSpinBox(), QSpinBox()
        self.num_start.setRange(0, 99999)
        self.num_start.setValue(1)
        self.num_digits.setRange(1, 6)
        self.num_digits.setValue(max(2, len(str(len(self.paths)))))
        nrow = QHBoxLayout()
        nrow.addWidget(QLabel(tr("from")))
        nrow.addWidget(self.num_start)
        nrow.addWidget(QLabel(tr("digits")))
        nrow.addWidget(self.num_digits)
        form.addRow(self.num_on, nrow)
        self.date_on = QCheckBox(tr("Add the date"))
        self.date_src = QComboBox()
        for label, key in ((tr("Date taken (photos) or modified"), "taken"), (tr("Date modified"), "modified"), (tr("Today"), "today")):
            self.date_src.addItem(label, key)
        self.date_fmt = QComboBox()
        for f in self.DATE_FORMATS:
            self.date_fmt.addItem(f, f)
        drow = QVBoxLayout()
        drow.addWidget(self.date_src)
        drow.addWidget(self.date_fmt)
        form.addRow(self.date_on, drow)
        self.place = QComboBox()
        self.place.addItem(tr("After the name"), "after")
        self.place.addItem(tr("Before the name"), "before")
        form.addRow(tr("Number and date go"), self.place)
        self.digits = QComboBox()
        for label, key in ((tr("Keep numerals as they are"), "keep"), ("0123 " + tr("Western"), "en"), ("٠١٢٣ " + tr("Arabic"), "ar")):
            self.digits.addItem(label, key)
        form.addRow(tr("Numerals"), self.digits)
        self.case = QComboBox()
        for label, key in ((tr("Keep"), "keep"), ("lowercase", "lower"), ("UPPERCASE", "upper"), ("Title Case", "title")):
            self.case.addItem(label, key)
        form.addRow(tr("Letters"), self.case)
        side.addStretch(1)
        right = QVBoxLayout()
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("Now"), tr("After")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setStyleSheet(f"QTableWidget{{background:{theme.hexc('surface')};color:{theme.hexc('text')};"
                                 f"gridline-color:{theme.hexc('border')};border:1px solid {theme.hexc('border')};border-radius:6px}}"
                                 f"QHeaderView::section{{background:{theme.hexc('bg')};color:{theme.hexc('dim')};border:none;padding:4px}}")
        right.addWidget(self.table, 1)
        self.status = QLabel()
        right.addWidget(self.status)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.ok = bb.button(QDialogButtonBox.Ok)
        self.ok.setText(tr("Rename"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        root.addLayout(right, 1)
        for w in (self.name_mode, self.date_src, self.date_fmt, self.place, self.digits, self.case):
            w.currentIndexChanged.connect(self._preview)
        for w in (self.new_name, self.find, self.repl):
            w.textChanged.connect(self._preview)
        for w in (self.num_on, self.date_on):
            w.toggled.connect(self._preview)
        for w in (self.num_start, self.num_digits):
            w.valueChanged.connect(self._preview)
        self.new_name.textChanged.connect(lambda t: t and self.name_mode.setCurrentIndex(1))
        self._dates = {}
        self._preview()

    def new_names(self):
        out = []
        mode = self.name_mode.currentData()
        for i, p in enumerate(self.paths):
            src = Path(p)
            stem, suffix = (src.name, "") if src.is_dir() else (src.stem, src.suffix)
            base = self.new_name.text().strip() if mode == "new" and self.new_name.text().strip() else stem
            if self.find.text():
                base = base.replace(self.find.text(), self.repl.text())
            extra = []
            if self.date_on.isChecked():
                key = (p, self.date_src.currentData())
                if key not in self._dates:
                    self._dates[key] = _date_of(p, key[1])
                d = self._dates[key]
                fmt = self.date_fmt.currentData()
                extra.append(d.strftime("%Y-%m-%d") if fmt.startswith("2026-") else
                             d.strftime("%d-%m-%Y") if fmt.startswith("24-") else d.strftime("%Y%m%d"))
            if self.num_on.isChecked():
                extra.append(str(self.num_start.value() + i).zfill(self.num_digits.value()))
            if extra:
                tag = " ".join(extra)
                base = f"{tag} {base}" if self.place.currentData() == "before" else f"{base} {tag}"
            case = self.case.currentData()
            base = base.lower() if case == "lower" else base.upper() if case == "upper" else base.title() if case == "title" else base
            dig = self.digits.currentData()
            base = base.translate(_AR_NUM) if dig == "ar" else base.translate(_EN_NUM) if dig == "en" else base
            base = "".join(c for c in base if c not in '<>:"/\\|?*').strip().rstrip(".")
            out.append(str(src.with_name((base or stem) + suffix)))
        return out

    def _preview(self):
        from PySide6.QtWidgets import QTableWidgetItem
        new = self.new_names()
        self.table.setRowCount(len(self.paths))
        seen, problems = {}, 0
        for old, n in zip(self.paths, new):
            seen[n.lower()] = seen.get(n.lower(), 0) + 1
        olds = {p.lower() for p in self.paths}
        for r, (old, n) in enumerate(zip(self.paths, new)):
            a, b = QTableWidgetItem(Path(old).name), QTableWidgetItem(Path(n).name)
            clash = seen[n.lower()] > 1 or (n.lower() not in olds and os.path.exists(n))
            if clash:
                b.setForeground(QColor(theme.hexc("danger")))
                problems += 1
            self.table.setItem(r, 0, a)
            self.table.setItem(r, 1, b)
        changed = sum(1 for o, n in zip(self.paths, new) if o != n)
        self.status.setText(tr("{n} names clash — change the settings", n=problems) if problems
                            else tr("{n} of {m} files will be renamed", n=changed, m=len(self.paths)))
        self.ok.setEnabled(problems == 0 and changed > 0)

    def apply(self):
        """Two steps (via temporary names) so swapping names never collides. Returns [(old, new)]."""
        import uuid
        pairs = [(o, n) for o, n in zip(self.paths, self.new_names()) if o != n]
        temps = []
        for o, n in pairs:
            t = str(Path(o).with_name(f".dw-{uuid.uuid4().hex[:8]}{Path(o).suffix}"))
            os.rename(o, t)
            temps.append((t, n, o))
        done = []
        for t, n, o in temps:
            os.rename(t, n)
            done.append((o, n))
        return done


def file_sha256(path, progress=None) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(4 * 1024 * 1024):
            h.update(chunk)
    return h.hexdigest()


def shred_path(path):
    """Overwrite with random data, rename, then delete — so the content can't be undeleted.
    (On SSDs the drive may keep old copies internally; nothing outside the drive can fully prevent that.)"""
    import uuid
    p = Path(path)
    if p.is_dir() and not p.is_symlink():
        for f in sorted(p.rglob("*"), key=lambda x: len(x.parts), reverse=True):
            shred_path(f) if f.is_file() else f.rmdir()
        p.rmdir()
        return
    size = p.stat().st_size
    with open(p, "r+b", buffering=0) as f:
        left = size
        while left > 0:
            n = min(1024 * 1024, left)
            f.write(os.urandom(n))
            left -= n
        f.flush()
        os.fsync(f.fileno())
        f.truncate(0)
    tmp = p.with_name(uuid.uuid4().hex)
    os.rename(p, tmp)
    os.remove(tmp)


def _lan_ips() -> list[str]:
    """IPv4 addresses a phone could reach, best first (the Wi-Fi/LAN one used for the internet, then other
    private addresses; virtual adapters such as WSL/Hyper-V/VPN last)."""
    import socket
    best = _lan_ip()
    found = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip not in found and not ip.startswith(("127.", "169.254.")):
                found.append(ip)
    except OSError:
        pass

    def score(ip):
        if ip == best:
            return 0
        if ip.startswith("192.168."):
            return 1
        if ip.startswith("10."):
            return 2
        if ip.startswith("172."):                         # 172.16-31 is often WSL / Hyper-V / Docker
            return 3
        return 4
    out = sorted(set(found + ([best] if best != "127.0.0.1" else [])), key=score)
    return out or ["127.0.0.1"]


def allow_through_firewall() -> bool:
    """Ask Windows (UAC) to let phones reach DragWheel: removes old block rules, adds an allow rule."""
    if not winsys.IS_WIN:
        return False
    import ctypes
    exe = sys.executable
    cmd = (f'/c netsh advfirewall firewall delete rule name=all program="{exe}" & '
           f'netsh advfirewall firewall add rule name="DragWheel (Send to phone)" dir=in action=allow protocol=TCP '
           f'program="{exe}" profile=private,public enable=yes')
    r = ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd.exe", cmd, None, 0)
    winsys.log(f"firewall rule requested: {r}")
    return r > 32


def _lan_ip() -> str:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))                  # picks the Wi-Fi/LAN address; nothing is sent
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class PhoneShare(QDialog):
    """Share files with a phone on the same Wi-Fi: a QR code opens a page served straight from this PC."""

    def __init__(self, paths):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        import http.server
        import secrets
        import urllib.parse
        self.setWindowTitle(f"{APP} — " + tr("Send to phone"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.paths = [Path(x) for x in paths]
        token = secrets.token_urlsafe(6)
        share = self
        self.hits = 0

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(h):
                path = urllib.parse.unquote(h.path)
                winsys.log(f"send to phone: request from {h.client_address[0]}: {path[:60]}")
                share._seen = h.client_address[0]
                if not path.startswith(f"/{token}"):
                    h.send_error(404)
                    return
                rest = path[len(token) + 1:].strip("/")
                if rest == "" and not (len(share.paths) == 1 and share.paths[0].is_file()):
                    return h._page()
                if rest == "" or rest.startswith("f/"):
                    i = 0 if rest == "" else int(rest[2:])
                    f = share.paths[i]
                    return h._zip([f]) if f.is_dir() else h._file(f)
                if rest == "all.zip":
                    return h._zip(share.paths)
                h.send_error(404)

            def _page(h):
                import html as _h
                rows = "".join(f'<a class="f" href="/{token}/f/{i}">{_h.escape(p.name)}{" (ZIP)" if p.is_dir() else ""}'
                               f'<small>{_human(p)}</small></a>' for i, p in enumerate(share.paths))
                body = (f'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>DragWheel</title>'
                        f'<style>body{{font:16px system-ui;margin:0;padding:18px;background:#1c1c1e;color:#f5f5f7}}'
                        f'.f{{display:block;padding:14px;margin:10px 0;border-radius:12px;background:#2c2c2e;color:#fff;text-decoration:none}}'
                        f'small{{display:block;color:#a1a1a6;margin-top:4px}}.all{{background:#ff8a00;color:#1c1c1e;font-weight:600}}</style>'
                        f'<h3>DragWheel</h3>{rows}<a class="f all" href="/{token}/all.zip">Download all (ZIP)</a>').encode()
                h.send_response(200)
                h.send_header("Content-Type", "text/html; charset=utf-8")
                h.send_header("Content-Length", str(len(body)))
                h.end_headers()
                h.wfile.write(body)

            def _file(h, f):
                import mimetypes
                share._hit(f.name)
                h.send_response(200)
                h.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                h.send_header("Content-Length", str(f.stat().st_size))
                h.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(f.name))
                h.end_headers()
                with open(f, "rb") as fi:
                    try:
                        shutil_copy(fi, h.wfile)
                    except OSError:
                        pass

            def _zip(h, items):
                import zipfile
                name = (items[0].name if len(items) == 1 else "DragWheel") + ".zip"
                share._hit(name)
                h.send_response(200)
                h.send_header("Content-Type", "application/zip")
                h.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(name))
                h.end_headers()
                try:
                    with zipfile.ZipFile(h.wfile, "w", zipfile.ZIP_STORED) as z:      # streamed as it's made
                        for it in items:
                            files = [it] if it.is_file() else [x for x in it.rglob("*") if x.is_file()]
                            for x in files:
                                z.write(x, str(x.relative_to(it.parent)))
                except OSError:
                    pass

            def log_message(h, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("0.0.0.0", 0), H)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self._port, self._token = self.server.server_address[1], token
        self.ips = _lan_ips()
        lay = QVBoxLayout(self)
        from PySide6.QtWidgets import QLayout
        lay.setSizeConstraint(QLayout.SetFixedSize)          # the window always fits the code and the text
        title = QLabel("<b>" + tr("Scan with your phone's camera") + "</b>")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.qr, 0, Qt.AlignHCenter)
        self.link = QLabel()
        self.link.setAlignment(Qt.AlignCenter)
        self.link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.link)
        if len(self.ips) > 1:                              # several network adapters: let the user switch
            self.ip_box = QComboBox()
            for ip in self.ips:
                self.ip_box.addItem(tr("Network address: {ip}", ip=ip), ip)
            self.ip_box.currentIndexChanged.connect(lambda _i: self._show_qr(self.ip_box.currentData()))
            lay.addWidget(self.ip_box)
        self._show_qr(self.ips[0])
        what = self.paths[0].name if len(self.paths) == 1 else tr("{n} files", n=len(self.paths))
        info = QLabel(tr("Sharing {what}. Your phone must be on the same Wi-Fi. If Windows asks, allow DragWheel on "
                         "private networks. Nothing goes through the internet; sharing stops when you close this window.",
                         what=what))
        info.setWordWrap(True)
        info.setFixedWidth(360)
        lay.addWidget(info)
        self.count = QLabel()
        lay.addWidget(self.count)
        help_b = QPushButton(tr("Phone can't open it?"))
        help_b.clicked.connect(self._help)
        lay.addWidget(help_b)
        stop = QPushButton(tr("Stop sharing"))
        stop.clicked.connect(self.close)
        lay.addWidget(stop)
        self.diag = QLabel()
        self.diag.setWordWrap(True)
        self.diag.setFixedWidth(360)
        self.diag.setStyleSheet(f"color:{theme.hexc('danger')}")
        self.diag.hide()
        lay.insertWidget(lay.indexOf(self.count), self.diag)
        self._seen = None
        self._diag_lines = None
        self._poll = QTimer(self, interval=500, timeout=self._update)
        self._poll.start()
        self._last = ""
        threading.Thread(target=self._diagnose, daemon=True).start()

    def _show_qr(self, ip):
        self.url = f"http://{ip}:{self._port}/{self._token}/"
        winsys.log(f"send to phone: {self.url} (addresses: {', '.join(self.ips)})")
        self.link.setText(f"<span style='color:{theme.hexc('dim')}'>{self.url}</span>")
        try:
            import io as _io
            import segno
            buf = _io.BytesIO()
            segno.make(self.url, error="m").save(buf, kind="png", scale=7, border=3, dark="#000", light="#fff")
            pm = QPixmap.fromImage(QImage.fromData(buf.getvalue()))
            self.qr.setPixmap(pm)
            self.qr.setFixedSize(pm.size())               # never squeezed: a stretched code can't be scanned
            self.adjustSize()
        except Exception as e:
            winsys.log(f"qr: {e}")

    def _help(self):
        box = QMessageBox(self)
        box.setWindowTitle(f"{APP} — " + tr("Send to phone"))
        box.setStyleSheet(i18n.css(DIALOG_CSS))
        box.setTextFormat(Qt.RichText)
        box.setText("<b>" + tr("If the phone says the site can't be reached:") + "</b><ol>"
                    + "<li>" + tr("Windows Firewall is probably blocking it. Press Allow in firewall below (Windows asks for permission once).") + "</li>"
                    + "<li>" + tr("Make sure the phone is on the same Wi-Fi as this PC, not mobile data or a guest network.") + "</li>"
                    + ("<li>" + tr("Try the other network address in the list under the QR code.") + "</li>" if len(self.ips) > 1 else "")
                    + "<li>" + tr("Turn off any VPN on the phone and on this PC while sharing.") + "</li>"
                    + "<li>" + tr("Some routers keep Wi-Fi devices apart ('AP isolation' or 'client isolation'), or put the phone on a separate 2.4/5 GHz or mesh network. If nothing above helps, that's the cause — it can be turned off in the router's settings.") + "</li>"
                    + "</ol>")
        allow = box.addButton(tr("Allow in firewall"), QMessageBox.AcceptRole)
        box.addButton(tr("Close"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is allow:
            if allow_through_firewall():
                self.count.setText(tr("Allowed. Scan the code again on the phone."))

    def _diagnose(self):
        """Why a phone may not get through: network set to Public with incoming blocked, Windows' 'block all
        incoming connections', another security app's firewall, or no allow rule. Read-only, no admin."""
        if not winsys.IS_WIN:
            return
        import subprocess
        ip = self.url.split("//")[1].split(":")[0]
        exe = sys.executable.replace("'", "''")
        ps = f"""
$ErrorActionPreference='SilentlyContinue'
$a = Get-NetIPAddress -IPAddress '{ip}'
if ($a) {{ $p = Get-NetConnectionProfile -InterfaceIndex $a.InterfaceIndex; "iface|$($a.InterfaceAlias)|$($p.NetworkCategory)|$($p.Name)" }}
Get-NetFirewallProfile | ForEach-Object {{ "profile|$($_.Name)|$($_.Enabled)|$($_.DefaultInboundAction)|$($_.AllowInboundRules)" }}
Get-NetFirewallApplicationFilter -Program '{exe}' | Get-NetFirewallRule | ForEach-Object {{ "rule|$($_.DisplayName)|$($_.Direction)|$($_.Action)|$($_.Enabled)|$($_.Profile)" }}
Get-CimInstance -Namespace root/SecurityCenter2 -ClassName FirewallProduct | ForEach-Object {{ "fwproduct|$($_.displayName)" }}
Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntivirusProduct | ForEach-Object {{ "av|$($_.displayName)" }}
"""
        try:
            r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                               capture_output=True, timeout=40, creationflags=engine.NO_WINDOW)
            lines = [x.strip() for x in r.stdout.decode("utf-8", "replace").splitlines() if "|" in x]
        except Exception as e:
            lines = [f"error|{e}"]
        for x in lines:
            winsys.log("send to phone check: " + x)
        self._diag_lines = lines

    def _diag_text(self, lines):
        notes = []
        cat = next((x.split("|")[2] for x in lines if x.startswith("iface|")), "")
        profiles = {x.split("|")[1].lower(): x.split("|") for x in lines if x.startswith("profile|")}
        active = profiles.get("public" if cat.lower() == "public" else "private" if cat.lower() == "private" else "domain")
        if active and active[2].lower() == "true" and active[4].lower() == "false":
            notes.append(tr("Windows Security is set to block all incoming connections on this network, even for allowed apps. "
                            "Turn that off in Windows Security → Firewall & network protection → {net} network.", net=active[1]))
        rules = [x.split("|") for x in lines if x.startswith("rule|") and x.split("|")[2].lower() == "inbound"]
        if any(r[3].lower() == "block" and r[4].lower() == "true" for r in rules):
            notes.append(tr("A firewall rule blocks DragWheel. Press Allow in firewall."))
        elif not any(r[3].lower() == "allow" and r[4].lower() == "true" for r in rules):
            notes.append(tr("DragWheel isn't allowed in Windows Firewall yet. Press Allow in firewall."))
        others = [x.split("|", 1)[1] for x in lines if x.startswith("fwproduct|") and "windows" not in x.lower()]
        if any("eset" in o.lower() for o in others):
            notes.append(tr("ESET's firewall is blocking the phone. In ESET open Setup → Network protection → "
                            "Connected networks, and set this network to Trusted (Home or office). Or add a rule: "
                            "Firewall → Rules → Add → Allow incoming for DragWheel.exe."))
            others = [o for o in others if "eset" not in o.lower()]
        if others:
            notes.append(tr("{app} has its own firewall: allow DragWheel there too (or let it trust your home network).",
                            app=", ".join(others)))
        if cat.lower() == "public":
            notes.append(tr("This Wi-Fi is set as a Public network in Windows. Setting it to Private lets home devices connect."))
        return notes

    def _hit(self, name):
        self.hits += 1
        self._last = name

    def _update(self):
        if self._diag_lines is not None:
            notes = self._diag_text(self._diag_lines)
            self._diag_lines = None
            self._notes = notes
            if notes:
                self.diag.setText("⚠ " + "\n\n⚠ ".join(notes))
                self.diag.show()
        if self.hits:
            self.count.setText(tr("Downloaded {n} time(s) — last: {name}", n=self.hits, name=self._last))

    def closeEvent(self, e):
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
        super().closeEvent(e)


QUICK_SHARE_URL = "https://www.android.com/better-together/quick-share-app/"


class _Upload:
    """A file read in pieces for an HTTP upload (multipart), reporting progress and stoppable."""

    def __init__(self, path, field, fields, progress, cancelled):
        import uuid
        self.boundary = "----DragWheel" + uuid.uuid4().hex
        pre = "".join(f'--{self.boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
                      for k, v in fields.items())
        from urllib.parse import quote
        pre += (f'--{self.boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{quote(Path(path).name)}"\r\n'
                f"Content-Type: application/octet-stream\r\n\r\n")
        self.parts = [pre.encode(), None, f"\r\n--{self.boundary}--\r\n".encode()]
        self.f = open(path, "rb")
        self.size = Path(path).stat().st_size
        self.total = len(self.parts[0]) + self.size + len(self.parts[2])
        self.done = 0
        self.stage = 0
        self.progress, self.cancelled = progress, cancelled

    def read(self, n=-1):
        if self.cancelled():
            raise OSError("cancelled")
        n = 256 * 1024 if n is None or n < 0 else n
        while self.stage < 3:
            if self.stage == 1:
                data = self.f.read(n)
                if not data:
                    self.stage = 2
                    continue
            else:
                data, self.parts[self.stage] = self.parts[self.stage], b""
                self.stage += 1
                if not data:
                    continue
            self.done += len(data)
            self.progress(self.done / self.total)
            return data
        return b""

    def close(self):
        self.f.close()


def _post_upload(url, path, field, fields, progress, cancelled, timeout=180):
    import urllib.request
    body = _Upload(path, field, fields, progress, cancelled)
    try:
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": f"multipart/form-data; boundary={body.boundary}", "Content-Length": str(body.total),
            "User-Agent": f"DragWheel/{VERSION} (Windows)", "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace").strip()
    finally:
        body.close()


def _host_litterbox(path, minutes, progress, cancelled):
    hours = min((h for h in (1, 12, 24, 72) if h * 60 >= minutes), default=72)
    link = _post_upload("https://litterbox.catbox.moe/resources/internals/api.php", path, "fileToUpload",
                        {"reqtype": "fileupload", "time": f"{hours}h"}, progress, cancelled)
    if not link.startswith("https://"):
        raise OSError(link[:120])
    return link


def _host_0x0(path, minutes, progress, cancelled):
    link = _post_upload("https://0x0.st", path, "file", {"expires": str(max(1, -(-minutes // 60)))}, progress, cancelled)
    if not link.startswith("https://"):
        raise OSError(link[:120])
    return link


def _host_tmpfiles(path, minutes, progress, cancelled):
    import json as _json
    data = _json.loads(_post_upload("https://tmpfiles.org/api/v1/upload", path, "file",
                                    {"expire": str(min(48 * 60, minutes) * 60)}, progress, cancelled))
    return data["data"]["url"].replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)


def _host_uguu(path, minutes, progress, cancelled):
    import json as _json
    data = _json.loads(_post_upload("https://uguu.se/upload", path, "files[]", {}, progress, cancelled))
    return data["files"][0]["url"]


# name, function, size limit in MB, longest it keeps a file (minutes)
TEMP_HOSTS = [("litterbox.catbox.moe", _host_litterbox, 1000, 72 * 60),
              ("0x0.st", _host_0x0, 512, 365 * 24 * 60),
              ("tmpfiles.org", _host_tmpfiles, 100, 48 * 60),
              ("uguu.se", _host_uguu, 128, 3 * 60)]


BLOCKED_UPLOAD_EXT = {".exe", ".msi", ".msix", ".appx", ".bat", ".cmd", ".com", ".scr", ".dll", ".sys", ".cpl", ".jar",
                      ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".hta", ".lnk", ".reg", ".apk", ".xapk", ".ipa"}


def upload_temporary(path, minutes, progress=lambda f: None, cancelled=lambda: False) -> tuple[str, str]:
    """Upload to a free temporary host; returns (download link, host). Several hosts are tried in turn, because a
    network, country or security app may block one of them. Short times (under an hour) prefer hosts that delete soon."""
    size = Path(path).stat().st_size
    mb = size / (1024 * 1024)
    order = ["litterbox.catbox.moe", "0x0.st", "tmpfiles.org", "uguu.se"] if minutes >= 60 else \
        ["tmpfiles.org", "uguu.se", "0x0.st", "litterbox.catbox.moe"]
    hosts = {h[0]: h for h in TEMP_HOSTS}
    errors = []
    for name in order:
        _n, fn, limit, _keep = hosts[name]
        if mb > limit:
            continue
        for attempt in (1, 2):
            if cancelled():
                raise OSError("cancelled")
            try:
                progress(0.0)
                link = fn(path, minutes, progress, cancelled)
                winsys.log(f"temporary upload: {name} ok ({mb:.1f} MB, {minutes} min)" +
                           (f" after: {' | '.join(errors)}" if errors else ""))
                return link, name
            except Exception as e:
                if cancelled():
                    raise
                errors.append(f"{name}#{attempt}: {type(e).__name__}: {e}")
                if "EOF occurred" not in str(e) and "timed out" not in str(e) and "reset" not in str(e).lower():
                    break                                  # only retry dropped connections
    winsys.log(f"temporary upload failed ({mb:.1f} MB, {minutes} min): " + " | ".join(errors))
    if mb > 1000:
        raise OSError(tr("Too big for an internet link (the limit is 1 GB)."))
    if errors and all("EOF occurred" in e or "CERTIFICATE" in e.upper() or "SSL" in e.upper() for e in errors):
        raise OSError(tr("The upload was cut off by something on this PC or network, often an antivirus that checks "
                         "secure connections (like ESET). Let DragWheel through it, or try Quick Share."))
    raise OSError(tr("Couldn't upload. Check the internet connection and try again."))


def share_links() -> list:
    """Internet links still alive: [{"url", "name", "expires"}] (Unix time)."""
    import time
    try:
        v = json.loads(settings().value("share_links", "[]") or "[]")
    except (TypeError, ValueError):
        v = []
    alive = [x for x in v if isinstance(x, dict) and x.get("expires", 0) > time.time()]
    if len(alive) != len(v):
        settings().setValue("share_links", json.dumps(alive, ensure_ascii=False))
    return alive


def remember_share_link(url, name, minutes):
    import time
    links = [x for x in share_links() if x["url"] != url]
    links.insert(0, {"url": url, "name": name, "expires": time.time() + minutes * 60})
    settings().setValue("share_links", json.dumps(links[:20], ensure_ascii=False))


def qr_pixmap(text, scale=7) -> QPixmap:
    import io as _io
    import segno
    buf = _io.BytesIO()
    segno.make(text, error="m").save(buf, kind="png", scale=scale, border=3, dark="#000", light="#fff")
    return QPixmap.fromImage(QImage.fromData(buf.getvalue()))


def _time_left(expires) -> str:
    import time
    m = max(1, int((expires - time.time()) // 60))
    return tr("{n} min left", n=m) if m < 60 else tr("{h} h {m} min left", h=m // 60, m=m % 60)


class ShareQR(QDialog):
    """Tray → Send to phone — show QR code: an internet link made earlier, until it runs out."""

    def __init__(self, item):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        from PySide6.QtWidgets import QLayout
        self.item = item
        self.setWindowTitle(f"{APP} — " + tr("Send to phone"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.setAttribute(Qt.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        head = QLabel(f"<b>{item['name']}</b>")
        head.setFixedWidth(330)
        head.setWordWrap(True)
        lay.addWidget(head)
        self.left = QLabel()
        self.left.setStyleSheet(f"color:{theme.hexc('dim')}")
        lay.addWidget(self.left)
        qr = QLabel()
        pm = qr_pixmap(item["url"])
        qr.setPixmap(pm)
        qr.setFixedSize(pm.size())
        lay.addWidget(qr, 0, Qt.AlignHCenter)
        link = QLabel(f"<span style='color:{theme.hexc('dim')}'>{item['url']}</span>")
        link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        link.setAlignment(Qt.AlignCenter)
        lay.addWidget(link)
        b = QPushButton(tr("Copy link"))
        b.clicked.connect(lambda: QGuiApplication.clipboard().setText(item["url"]))
        lay.addWidget(b)
        b = QPushButton(tr("Close"))
        b.clicked.connect(self.close)
        lay.addWidget(b)
        self._t = QTimer(self, interval=20000, timeout=self._tick)
        self._t.start()
        self._tick()

    def _tick(self):
        import time
        if self.item["expires"] <= time.time():
            self.close()                                   # the link has run out
            return
        self.left.setText(_time_left(self.item["expires"]))


class InternetShare(QDialog):
    """Send to phone through a temporary internet link: upload, then a QR code to open it on any phone."""
    MINUTES = [5, 10, 15, 30, 60, 12 * 60, 24 * 60, 72 * 60]

    def __init__(self, paths):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        from PySide6.QtWidgets import QLayout, QProgressBar
        self.setWindowTitle(f"{APP} — " + tr("Send to phone"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.paths = [Path(x) for x in paths]
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        what = self.paths[0].name if len(self.paths) == 1 and self.paths[0].is_file() else \
            tr("{n} files (as one ZIP)", n=len(self.paths)) if len(self.paths) > 1 else self.paths[0].name + ".zip"
        if len(self.paths) == 1 and self.paths[0].is_file() and self.paths[0].suffix.lower() in BLOCKED_UPLOAD_EXT:
            what = self.paths[0].name + ".zip — " + tr("programs are sent inside a ZIP, because file services refuse them")
        head = QLabel(f"<b>{tr('Internet link')}</b><br><span style='color:{theme.hexc('dim')}'>{what}</span>")
        head.setWordWrap(True)
        head.setFixedWidth(360)
        lay.addWidget(head)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Keep the link for")))
        self.hours = QComboBox()
        for m in self.MINUTES:
            self.hours.addItem(tr("{n} minutes", n=m) if m < 60 else tr("{n} hour(s)", n=m // 60), m)
        self.hours.setCurrentIndex(max(0, self.hours.findData(int(settings().value("share_minutes", 60)))))
        row.addWidget(self.hours, 1)
        lay.addLayout(row)
        note = QLabel(tr("The file is uploaded to a free temporary file service (DragWheel tries several in turn) and deleted "
                         "automatically after about that time. Anyone with the link can download it until then. Up to 1 GB."))
        note.setWordWrap(True)
        note.setFixedWidth(360)
        note.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        lay.addWidget(note)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.hide()
        lay.addWidget(self.bar)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setFixedWidth(360)
        lay.addWidget(self.status)
        self.qr = QLabel()
        self.qr.hide()
        lay.addWidget(self.qr, 0, Qt.AlignHCenter)
        self.link = QLabel()
        self.link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.link.setAlignment(Qt.AlignCenter)
        self.link.hide()
        lay.addWidget(self.link)
        self.go = QPushButton(tr("Upload and make a link"))
        self.go.clicked.connect(self._start)
        lay.addWidget(self.go)
        self.copy = QPushButton(tr("Copy link"))
        self.copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.url))
        self.copy.hide()
        lay.addWidget(self.copy)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        lay.addWidget(close)
        self._cancel = False
        self._frac = 0.0
        self._result = None
        self._poll = QTimer(self, interval=150, timeout=self._update)

    def _start(self):
        settings().setValue("share_minutes", self.hours.currentData())
        self.shared_name = self.paths[0].name if len(self.paths) == 1 else tr("{n} files", n=len(self.paths))
        self.go.setEnabled(False)
        self.hours.setEnabled(False)
        self.bar.show()
        self.status.setText(tr("Uploading…"))
        hours = self.hours.currentData()

        def work():
            try:
                src = self.paths[0]
                # free file services refuse programs and scripts (.exe, .msi…): those travel inside a ZIP
                blocked = src.is_file() and src.suffix.lower() in BLOCKED_UPLOAD_EXT
                if len(self.paths) > 1 or src.is_dir() or blocked:
                    import tempfile
                    import zipfile
                    tmp = Path(tempfile.mkdtemp(prefix="dragwheel-share-"))
                    src = tmp / ((self.paths[0].name if len(self.paths) == 1 else "DragWheel") + ".zip")
                    with zipfile.ZipFile(src, "w", zipfile.ZIP_STORED if blocked else zipfile.ZIP_DEFLATED) as z:
                        for it in self.paths:
                            for f in ([it] if it.is_file() else [x for x in it.rglob("*") if x.is_file()]):
                                z.write(f, str(f.relative_to(it.parent)))
                link, host = upload_temporary(src, hours, lambda f: setattr(self, "_frac", f), lambda: self._cancel)
                self._result = ("ok", link, host)
            except Exception as e:
                self._result = ("err", str(e), "")
        threading.Thread(target=work, daemon=True).start()
        self._poll.start()

    def _update(self):
        self.bar.setValue(int(self._frac * 1000))
        if self._result is None:
            return
        self._poll.stop()
        kind, val, host = self._result
        self.bar.hide()
        if kind == "err":
            self.status.setText(f"<span style='color:{theme.hexc('danger')}'>{val}</span>")
            self.go.setEnabled(True)
            self.hours.setEnabled(True)
            return
        self.url = val
        winsys.log(f"send to phone (internet): uploaded to {host}")
        remember_share_link(val, self.shared_name, int(self.hours.currentData()))
        self.status.setText("<b>" + tr("Scan with your phone's camera") + "</b> — " +
                            tr("works on any network, even mobile data."))
        try:
            import io as _io
            import segno
            buf = _io.BytesIO()
            segno.make(val, error="m").save(buf, kind="png", scale=7, border=3, dark="#000", light="#fff")
            pm = QPixmap.fromImage(QImage.fromData(buf.getvalue()))
            self.qr.setPixmap(pm)
            self.qr.setFixedSize(pm.size())
            self.qr.show()
        except Exception as e:
            winsys.log(f"qr: {e}")
        self.link.setText(f"<span style='color:{theme.hexc('dim')}'>{val}</span>")
        self.link.show()
        self.go.hide()
        self.copy.show()

    def closeEvent(self, e):
        self._cancel = True
        super().closeEvent(e)


class SendChooser(QDialog):
    """How to send to the phone: Quick Share, an internet link, or the same Wi-Fi."""

    def __init__(self, paths):
        super().__init__(None, Qt.WindowStaysOnTopHint)
        from PySide6.QtWidgets import QLayout
        self.setWindowTitle(f"{APP} — " + tr("Send to phone"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS) + f"QPushButton#way{{text-align:left;padding:10px 14px;font:600 10pt 'Segoe UI'}}"
                           f"QPushButton#way[last=true]{{border:2px solid {theme.hexc('accent')}}}")
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        what = Path(paths[0]).name if len(paths) == 1 else tr("{n} files", n=len(paths))
        lay.addWidget(QLabel(f"<b>{tr('How do you want to send it?')}</b><br>"
                             f"<span style='color:{theme.hexc('dim')}'>{what}</span>"))
        self.choice = None
        last = settings().value("share_way", "quick")
        last = "internet" if last == "iphone" else last
        for key, title, desc in (
                ("quick", tr("Quick Share"), tr("Google's Quick Share sends straight to a nearby Android phone. No network setup.")),
                ("internet", tr("Internet link"), tr("Uploads to a temporary link that works on any network and any phone, iPhone too. Deleted after 5 minutes to 72 hours.")),
                ("bluetooth", tr("Bluetooth"), tr("Slower, but needs no network. Works with phones paired to this PC (Android; iPhones can't receive files over Bluetooth).")),
                ("wifi", tr("Same Wi-Fi"), tr("The phone downloads directly from this PC. Nothing leaves your home, but routers and firewalls can block it."))):
            b = QPushButton(f"{title}\n{desc}")
            b.setObjectName("way")
            b.setAutoDefault(False)
            b.setDefault(key == last)                         # the way used last time is highlighted
            b.setMinimumWidth(380)
            b.clicked.connect(lambda _=False, k=key: self._pick(k))
            lay.addWidget(b)

    def _pick(self, key):
        self.choice = key
        settings().setValue("share_way", key)
        self.accept()


def shutil_copy(fi, fo):
    while chunk := fi.read(1024 * 1024):
        fo.write(chunk)


def _human(p: Path) -> str:
    try:
        n = p.stat().st_size if p.is_file() else sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    except OSError:
        return ""
    for unit in ("bytes", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "bytes" else f"{n:.1f} {unit}"
        n /= 1024


# ============================================================================
# File actions (don't use the engine)
# ============================================================================
class Actions:
    def __init__(self, app: "DragWheelApp"):
        self.app = app

    def ops(self, paths):
        A = lambda i, l, f, h="": engine.Op(i, l, f, group="action", multi=True, hint=h)
        return [
            A("copy", "Copy", self.copy, "to clipboard"),  # labels are translated when drawn
            A("path", "Copy path", self.copy_path),
            A("move", "Move to…", self.move),
            A("copyto", "Copy to…", self.copy_to),
            A("terminal", "Terminal", self.terminal, "open here"),
            A("float", "Float", self.float),
            A("reveal", "Show", self.reveal, "in Explorer"),
            A("openwith", "Open with…", self.open_with),
            A("rename", "Rename…", self.rename, "several at once"),
            A("hash", "Checksum", self.checksum, "SHA-256"),
            A("phone", "Send to phone", self.phone),
            A("shred", "Shred…", self.shred, "can't be undone"),
        ]

    def rename(self, paths, p):
        dlg = BatchRenameDialog(paths)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            done = dlg.apply()
        except OSError as e:
            self.app.toast.show_msg(tr("Couldn't rename"), str(e), "err", 8000)
            return
        winsys.log("renamed: " + "; ".join(f"{Path(o).name} -> {Path(n).name}" for o, n in done[:50]))
        self.app.toast.show_result(tr("Renamed {n} files", n=len(done)), [n for _, n in done])

    def checksum(self, paths, p):
        files = [Path(x) for x in paths if Path(x).is_file()]
        if not files:
            self.app.toast.show_msg(tr("Checksum"), tr("Pick files, not folders"), "err", 4000)
            return
        card = self.app.toast.show_busy(tr("Checksum"), files[0].name if len(files) == 1 else tr("{n} files", n=len(files)))
        result = {}
        clip = QGuiApplication.clipboard().text().strip().lower()

        def work():
            try:
                result["ok"] = [(f, file_sha256(f)) for f in files]
            except Exception as e:
                result["err"] = str(e)

        def check():
            if not result:
                QTimer.singleShot(150, check)
                return
            if card in self.app.toast.cards:
                card.close_card()
            if "err" in result:
                self.app.toast.show_msg(tr("Checksum"), result["err"], "err", 6000)
                return
            pairs = result["ok"]
            text = "\n".join(f"{h}  {f.name}" for f, h in pairs)
            import re as _re
            if _re.fullmatch(r"[0-9a-f]{64}", clip):                     # a hash was copied: compare
                match = next((f for f, h in pairs if h == clip), None)
                if match:
                    self.app.toast.show_msg("✓ " + tr("Checksum matches"), tr("{name} is the genuine file.", name=match.name), "ok", 10000)
                else:
                    self.app.toast.show_msg("✗ " + tr("Checksum doesn't match"),
                                            tr("The copied checksum is different — the file may be damaged or not the original."),
                                            "err", 12000)
                return
            QGuiApplication.clipboard().setText(text)
            short = pairs[0][1][:16] + "…" if len(pairs) == 1 else tr("{n} files", n=len(pairs))
            self.app.toast.show_msg(tr("SHA-256 copied"), f"{short}<br><small>{tr('Copy a published checksum first to compare it instead.')}</small>", "ok", 9000)
        threading.Thread(target=work, daemon=True).start()
        QTimer.singleShot(150, check)

    def phone(self, paths, p):
        chooser = SendChooser(paths)
        if chooser.exec() != QDialog.Accepted:
            return
        if chooser.choice == "quick":
            self.quick_share(paths)
            return
        if chooser.choice == "bluetooth":
            self.bluetooth(paths)
            return
        w = PhoneShare(paths) if chooser.choice == "wifi" else InternetShare(paths)
        self.app._phone_windows = getattr(self.app, "_phone_windows", [])
        self.app._phone_windows.append(w)
        w.show()
        w.raise_()

    def quick_share(self, paths):
        exe = winsys.quick_share_installed()
        ok = False
        if exe:
            try:                                          # the same call Quick Share's own right-click entry makes
                import subprocess
                subprocess.Popen([exe, "--files-from=context-menu", *[str(Path(p)) for p in paths]],
                                 creationflags=engine.NO_WINDOW)
                winsys.log(f"quick share: started with {len(paths)} item(s)")
                ok = True
            except Exception as e:
                winsys.log(f"quick share: {e}")
        if ok:
            self.app.toast.show_msg(tr("Quick Share"), tr("Pick your phone in the Quick Share window, then tap Accept on the phone."), "info", 6000)
            return
        box = QMessageBox()
        box.setWindowTitle(f"{APP} — " + tr("Quick Share"))
        box.setWindowIcon(app_icon())
        box.setStyleSheet(i18n.css(DIALOG_CSS))
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        if exe:
            box.setText(tr("Quick Share is installed but didn't offer to send these files. Opening it — drag the files into its window."))
            box.exec()
            os.startfile(exe)
            winsys.reveal(paths)
            return
        box.setText("<b>" + tr("Quick Share isn't installed") + "</b><br><br>" +
                    tr("It's free from Google and sends files to nearby Android phones (Samsung phones have it built in). "
                       "Install it once, then choose Quick Share again."))
        get = box.addButton(tr("Get Quick Share"), QMessageBox.AcceptRole)
        box.addButton(tr("Close"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is get:
            QDesktopServices.openUrl(QUrl(QUICK_SHARE_URL))

    def bluetooth(self, paths):
        """Windows' own Bluetooth file sender, with the files already chosen (what Send To → Bluetooth does)."""
        exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "fsquirt.exe"
        files = [str(Path(p)) for p in paths if Path(p).is_file()]
        if not exe.exists():
            self.app.toast.show_msg(tr("Bluetooth"), tr("This PC has no Bluetooth file sending."), "err", 6000)
            return
        if not files:
            self.app.toast.show_msg(tr("Bluetooth"), tr("Pick files, not folders"), "err", 5000)
            return
        ok = False
        link = winsys.sendto_entry("bluetooth")
        if link is not None:
            try:                                          # what right-click → Send to → Bluetooth device does
                ok = winsys.drop_files_on(link, files)
            except Exception as e:
                winsys.log(f"bluetooth drop: {e}")
        if not ok:
            import subprocess
            subprocess.Popen([str(exe), *files])
        self.app.toast.show_msg(tr("Bluetooth"), tr("Choose your phone in the Bluetooth window, then accept the files on the phone. "
                                                    "The phone must be paired with this PC first."), "info", 8000)

    def shred(self, paths, p):
        box = QMessageBox()
        box.setWindowTitle(f"{APP} — " + tr("Shred…").rstrip("…"))
        box.setWindowIcon(app_icon())
        box.setStyleSheet(i18n.css(DIALOG_CSS))
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        box.setIcon(QMessageBox.Warning)
        names = "<br>".join("• " + Path(x).name for x in paths[:6]) + ("<br>…" if len(paths) > 6 else "")
        box.setText("<b>" + tr("Destroy {n} item(s) for good?", n=len(paths)) + "</b><br><br>" + names + "<br><br>" +
                    tr("They're overwritten and deleted. They won't go to the Recycle Bin and can't be recovered."))
        go = box.addButton(tr("Shred"), QMessageBox.DestructiveRole)
        box.addButton(tr("Cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not go:
            return
        card = self.app.toast.show_busy(tr("Shredding…"), Path(paths[0]).name)
        result = {}

        def work():
            errs = []
            for x in paths:
                try:
                    shred_path(x)
                except Exception as e:
                    errs.append(f"{Path(x).name}: {e}")
            result["errs"] = errs

        def check():
            if not result:
                QTimer.singleShot(200, check)
                return
            if card in self.app.toast.cards:
                card.close_card()
            winsys.log(f"shredded {len(paths)} item(s); errors: {result['errs']}")
            if result["errs"]:
                self.app.toast.show_msg(tr("Some items couldn't be shredded"), "<br>".join(result["errs"][:4]), "err", 10000)
            else:
                self.app.toast.show_msg(tr("Shredded"), tr("{n} item(s) destroyed", n=len(paths)), "ok", 4000)
        threading.Thread(target=work, daemon=True).start()
        QTimer.singleShot(200, check)

    def copy(self, paths, p):
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(x) for x in paths])
        QGuiApplication.clipboard().setMimeData(md)
        self.app.toast.show_msg(tr("Copied to clipboard"), tr("{n} item(s) — paste anywhere", n=len(paths)))

    def copy_path(self, paths, p):
        QGuiApplication.clipboard().setText("\n".join(str(Path(x)) for x in paths))
        self.app.toast.show_msg(tr("Path copied"), str(Path(paths[0])) if len(paths) == 1 else tr("{n} paths", n=len(paths)))

    def _pick_dir(self, title):
        s = settings()
        d = QFileDialog.getExistingDirectory(None, title, s.value("last_dir", str(Path(self._first).parent)))
        if d:
            s.setValue("last_dir", d)
        return d

    def move(self, paths, p):
        import shutil
        self._first = paths[0]
        d = self._pick_dir(tr("Move to"))
        if not d:
            return
        done = []
        for x in paths:
            target = engine.unique_path(Path(d) / Path(x).name)
            shutil.move(x, target)
            done.append(target)
        self.app.toast.show_result(tr("Moved"), done)

    def copy_to(self, paths, p):
        import shutil
        self._first = paths[0]
        d = self._pick_dir(tr("Copy to"))
        if not d:
            return
        done = []
        for x in paths:
            target = engine.unique_path(Path(d) / Path(x).name)
            (shutil.copytree if Path(x).is_dir() else shutil.copy2)(x, target)
            done.append(target)
        self.app.toast.show_result(tr("Copied"), done)

    def terminal(self, paths, p):
        x = Path(paths[0])
        winsys.open_terminal(str(x if x.is_dir() else x.parent))

    def float(self, paths, p):
        for x in paths[:6]:
            w = FloatWindow(x)
            self.app.floats.append(w)
            w.closed.connect(lambda w=w: self.app.floats.remove(w) if w in self.app.floats else None)
            w.show()
            w.come_forward()

    def reveal(self, paths, p):
        winsys.reveal(paths[0])

    def open_with(self, paths, p):
        winsys.open_with(paths[0])


# ============================================================================
# Background worker
# ============================================================================
CANCELLED = "__cancelled__"


class WorkerSignals(QObject):
    done = Signal(object, object, object)   # worker, outputs, error
    progress = Signal(object, float)         # worker, 0..1
    count = Signal(object, int, int)         # worker, files done, files in the batch


class Worker(QRunnable):
    def __init__(self, op, paths, params):
        super().__init__()
        self.op, self.paths, self.params = op, paths, params
        self.sig = WorkerSignals()
        self.cancel_requested = False
        self.card = None
        self.failed = []
        self.count = (0, len(paths))

    def cancel(self):
        self.cancel_requested = True

    def run(self):
        """The job runs in its own process (jobproc) so Cancel can stop it instantly."""
        try:
            import jobproc
            job = jobproc.JobProcess(self.op.group, self.op.id, self.paths, self.params,
                                     getattr(self, "output_dir", None) or engine.OUTPUT_DIR,
                                     on_progress=lambda f: self.sig.progress.emit(self, f),
                                     on_count=lambda a, b: self.sig.count.emit(self, a, b))
            kind, val = job.run(lambda: self.cancel_requested)
            self.failed = list(job.failed)
            if kind == "done":
                self.sig.done.emit(self, [Path(v) for v in val], None)
            elif kind == "cancelled":
                self.sig.done.emit(self, None, CANCELLED)
            else:
                self.sig.done.emit(self, None, str(val))
        except Exception as e:
            traceback.print_exc()
            self.sig.done.emit(self, None, str(e) or e.__class__.__name__)


# ============================================================================
# Update check / download (background)
# ============================================================================
class UpdateSignals(QObject):
    checked = Signal(object, object, bool)     # release | None, error | None, manual
    progress = Signal(int, int)
    downloaded = Signal(object, object)        # path | None, error | None


class UpdateCheck(QRunnable):
    def __init__(self, manual):
        super().__init__()
        self.manual = manual
        self.sig = UpdateSignals()

    def run(self):
        try:
            self.sig.checked.emit(updater.latest_release(), None, self.manual)
        except Exception as e:
            self.sig.checked.emit(None, str(e), self.manual)


class UpdateDownload(QRunnable):
    def __init__(self, release):
        super().__init__()
        self.release = release
        self.stop = False
        self.sig = UpdateSignals()

    def run(self):
        try:
            path = updater.download(self.release.installer_url, self.release.installer_name,
                                    progress=lambda d, t: self.sig.progress.emit(d, t),
                                    should_stop=lambda: self.stop,
                                    size=self.release.installer_size, sha256=self.release.installer_sha256)
            self.sig.downloaded.emit(path, None)
        except InterruptedError:
            self.sig.downloaded.emit(None, CANCELLED)
        except Exception as e:
            self.sig.downloaded.emit(None, str(e))


_APP = None          # the running DragWheelApp (floats use it for "Play copied link")


class LinkSignals(QObject):
    done = Signal(object, object)          # info dict | None, error | None


class LinkResolve(QRunnable):
    def __init__(self, url, quality=None):
        super().__init__()
        self.url = url
        self.quality = quality or settings().value("link_quality", "1080p")
        self.sig = LinkSignals()

    def run(self):
        try:
            self.sig.done.emit(engine.resolve_link(self.url, self.quality), None)
        except Exception as e:
            self.sig.done.emit(None, str(e))


class ModelDownload(QRunnable):
    """Downloads an AI model once into %LOCALAPPDATA%\\DragWheel\\models (checksum-verified)."""
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.stop = False
        self.sig = UpdateSignals()

    def run(self):
        m = engine.MODELS[self.name]
        try:
            path = updater.download(m["url"], m["file"], progress=lambda d, t: self.sig.progress.emit(d, t),
                                    should_stop=lambda: self.stop, size=m["size"], sha256=m["sha256"],
                                    folder=engine.models_dir())
            engine.mark_model_ready(self.name)
            self.sig.downloaded.emit(path, None)
        except InterruptedError:
            self.sig.downloaded.emit(None, CANCELLED)
        except Exception as e:
            self.sig.downloaded.emit(None, str(e))


# ============================================================================
# The wheel
# ============================================================================
WHEEL_ANIMS = [("bloom", "Bloom"), ("circle", "Circle"), ("fade", "Fade"), ("spin", "Spin"), ("none", "None")]


def wheel_anim() -> str:
    v = settings().value("wheel_anim", "bloom")
    return v if v in dict(WHEEL_ANIMS) else "bloom"


def anim_speed() -> float:
    """Animation speed from Settings: 100 = normal, 25 = four times slower, 250 = 2.5 times faster."""
    try:
        return max(25, min(250, int(settings().value("anim_speed", 100)))) / 100
    except (TypeError, ValueError):
        return 1.0


def _ease_back(k):
    """0..1 with a small overshoot, like something popping open."""
    k = max(0.0, min(1.0, k)) - 1
    return 1 + 2.2 * k ** 3 + 1.2 * k ** 2


class Wheel(QWidget):
    R_IN = 62
    R_MID = 158
    R_OUT = 246
    PAD = 18
    PILL_H = 34

    def __init__(self, app: "DragWheelApp"):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                         | Qt.WindowDoesNotAcceptFocus)
        self.app = app
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.paths: list[str] = []
        self.mode = "convert"
        self.ops: list[engine.Op] = []
        self.hover = -1          # index in ops, -1 none, -2 center
        self.hover_pill = None
        self.click_mode = False
        self.opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.opacity_anim.setDuration(110)
        self.opacity_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.pill_timer = QTimer(self, singleShot=True, interval=380, timeout=self._pill_dwell)
        self._t = 1.0                     # 0 = closed, 1 = fully open (open/close animation)
        self._closing = False
        self._style = "circle"
        self.t_anim = QVariantAnimation(self)
        self.t_anim.valueChanged.connect(self._set_t)
        self.t_anim.finished.connect(self._anim_done)
        self._resize_for(1)

    def _set_t(self, v):
        self._t = float(v)
        self.update()

    def _animate(self, to):
        self.t_anim.stop()
        opening = to > self._t
        fast = self._style == "fade"
        if self._style == "bloom":
            ms = 460 if opening else 320
        else:
            ms = (130 if fast else 190) if opening else (120 if fast else 180)
        self.t_anim.setDuration(max(40, int(ms / anim_speed())))
        self.t_anim.setEasingCurve(QEasingCurve.OutCubic if opening else QEasingCurve.InCubic)
        self.t_anim.setStartValue(self._t)
        self.t_anim.setEndValue(float(to))
        self.t_anim.start()

    def _anim_done(self):
        if self._closing and self._t <= 0.001:
            self._finish_hide()

    # ------------------------------------------------------------- geometry
    def _rings(self):
        """Always one ring. With many slices the ring grows (up to R_OUT) so each label keeps
        roughly 74 px of arc; past that the labels shrink to fit."""
        n = len(self.ops)
        mid = max(self.R_MID + 14, 2 * (74 * n / (2 * math.pi)) - self.R_IN)
        return [(self.R_IN, min(self.R_OUT, int(mid)), self.ops)]

    def _outer(self):
        return self._rings()[-1][1]

    def _resize_for(self, _):
        r = self.R_OUT
        side = 2 * (r + self.PAD)
        self.setFixedSize(side, side + self.PILL_H + 12)

    def center(self) -> QPointF:
        return QPointF(self.width() / 2, self.R_OUT + self.PAD)

    def _pill_rects(self):
        w, gap = 108, 8
        total = w * 3 + gap * 2
        x0 = (self.width() - total) / 2
        c = self.center()
        y = c.y() + self._outer() + 14
        return {m: QRectF(x0 + i * (w + gap), y, w, self.PILL_H) for i, m in enumerate(MODES)}

    def hit(self, pos: QPointF):
        for m, r in self._pill_rects().items():
            if r.contains(pos):
                return ("pill", m)
        c = self.center()
        dx, dy = pos.x() - c.x(), pos.y() - c.y()
        d = math.hypot(dx, dy)
        if d < self.R_IN:
            return ("center", None)
        ang = (math.degrees(math.atan2(dx, -dy)) + 360) % 360  # 0 = top, clockwise
        offset = 0
        for r0, r1, items in self._rings():
            if r0 <= d <= r1 and items:
                step = 360 / len(items)
                idx = int(((ang + step / 2) % 360) // step)
                return ("item", offset + idx)
            offset += len(items)
        return (None, None)

    # ------------------------------------------------------------- content
    def set_mode(self, mode):
        self.mode = mode
        self.ops = self.app.ops_for(mode, self.paths) if self.paths else []
        self.hover = -1
        if self.isVisible():
            self._keep_on_screen()                    # more slices = a bigger ring
        self.update()

    def _keep_on_screen(self):
        """Centre the wheel on the pointer, but slide it in so the whole ring and the key buttons show,
        even right at the edge of the screen."""
        pos = getattr(self, "_anchor", None) or QCursor.pos()
        scr = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = scr.availableGeometry()
        c = self.center()
        outer = self._outer() + 18                    # ring + its shadow
        pills = self._pill_rects()
        half_w = max(outer, (max(r.right() for r in pills.values()) - min(r.left() for r in pills.values())) / 2 + 4)
        top_extent = outer
        bottom_extent = max(outer, max(r.bottom() for r in pills.values()) - c.y() + 6)
        cx = min(max(pos.x(), geo.left() + half_w), geo.right() - half_w)
        cy = min(max(pos.y(), geo.top() + top_extent), geo.bottom() - bottom_extent)
        self.move(int(cx - c.x()), int(cy - c.y()))

    def set_paths(self, paths):
        self.paths = paths
        self.set_mode(self.mode)

    # ------------------------------------------------------------- show/hide
    def popup(self, mode, paths=None, click_mode=False, at: QPoint | None = None):
        if not self.is_open():
            play_wheel_sound("open")
        self.click_mode = click_mode
        self.dropped = False
        self.scroll_active = False
        self.scroll_anchor = None
        self.paths = paths or []
        self.mode = mode
        self.set_mode(mode)
        pos = at or QCursor.pos()
        c = self.center()
        self._anchor = pos
        self.move(int(pos.x() - c.x()), int(pos.y() - c.y()))
        self._keep_on_screen()
        self._closing = False
        self._style = wheel_anim()
        self.t_anim.stop()
        self._t = 0.0 if self._style != "none" else 1.0
        self.setWindowOpacity(1.0)
        if click_mode:
            self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, False)
        else:
            self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.show()
        self.raise_()
        if click_mode:
            self.activateWindow()
            self.setFocus()
        if self._style != "none" and click_mode:
            self._animate(1.0)
        elif self._style != "none":
            QTimer.singleShot(400, self.begin_anim)         # safety net if nobody starts it
        # while dragging, the app first asks Explorer which files are held (that can take a moment);
        # the animation starts once that's done, so it never jumps straight to the end

    def begin_anim(self):
        """Start opening (drag mode), once the slices are in place and the app is idle again."""
        if self.isVisible() and not self._closing and self._style != "none" and self._t < 1.0 \
                and self.t_anim.state() != QVariantAnimation.Running:
            self._animate(1.0)

    def dismiss(self):
        self.pill_timer.stop()
        if self.is_open():
            QTimer.singleShot(40, lambda: play_wheel_sound("close"))   # after a drop, the choice sound wins
        if self.isVisible() and self._style != "none" and not self._closing:
            self._closing = True                       # keep drawing what was there while it goes away
            self._animate(0.0)
            return
        if not self._closing:
            self._finish_hide()

    def is_open(self) -> bool:
        return self.isVisible() and not self._closing

    def _finish_hide(self):
        self._closing = False
        self.t_anim.stop()
        self._t = 1.0
        self.hide()
        self.paths = []
        self.ops = []
        self.hover = -1

    # ------------------------------------------------------------- drag & drop
    def _paths_from(self, md) -> list[str]:
        return [u.toLocalFile() for u in md.urls() if u.isLocalFile() and u.toLocalFile()]

    def dragEnterEvent(self, e):
        if self._closing:
            e.ignore()
            return
        paths = self._paths_from(e.mimeData())
        if not paths:
            e.ignore()
            return
        if not getattr(self, "_logged_enter", False):
            winsys.log(f"drag enter received: {len(paths)} path(s)")
            self._logged_enter = True
        if paths != self.paths:
            self.set_paths(paths)
        e.setDropAction(Qt.CopyAction)
        e.accept()
        self._track(e.position())

    def dragMoveEvent(self, e):
        kind = self._track(e.position())
        if kind == "item":
            e.setDropAction(Qt.CopyAction)   # never let Explorer treat it as a move
            e.accept()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self.hover = -1
        self.hover_pill = None
        self.pill_timer.stop()
        self.update()

    def dropEvent(self, e):
        self.dropped = True
        winsys.log("drop event received")
        kind, val = self.hit(e.position())
        if getattr(self, "scroll_active", False) and 0 <= self.hover < len(self.ops):
            kind, val = "item", self.hover
        paths = self._paths_from(e.mimeData()) or self.paths
        e.setDropAction(Qt.CopyAction)
        e.accept()
        if kind == "item" and 0 <= val < len(self.ops):
            op = self.ops[val]
            self.dismiss()
            QTimer.singleShot(0, lambda: self.app.execute(op, paths))
        else:
            self.dismiss()

    def scroll_step(self, step):
        """Move the highlight to the next/previous slice (mouse wheel)."""
        n = len(self.ops)
        if not n:
            return
        if self.hover >= 0:
            self.hover = (self.hover + step) % n
        else:
            self.hover = 0 if step > 0 else n - 1
        play_tick()
        self._announce()
        self.scroll_active = True
        local = QPointF(self.mapFromGlobal(QCursor.pos()))
        self.scroll_anchor = self.hit(local)
        self.update()

    def wheelEvent(self, e):
        self.scroll_step(1 if e.angleDelta().y() < 0 else -1)

    def _track(self, pos):
        kind, val = self.hit(pos)
        if getattr(self, "scroll_active", False):
            if (kind, val) == self.scroll_anchor or kind == "center":
                return "item" if self.hover >= 0 else kind      # keep the scrolled highlight
            self.scroll_active = False                            # pointer moved onto a slice: it wins
        new_hover = val if kind == "item" else (-2 if kind == "center" else -1)
        pill = val if kind == "pill" else None
        if pill != self.hover_pill:
            self.hover_pill = pill
            self.pill_timer.stop()
            if pill and pill != self.mode:
                self.pill_timer.start()
        if new_hover != self.hover:
            if new_hover >= 0:
                play_tick()
            self.hover = new_hover
            self.update()
            self._announce()
        return kind

    def _announce(self):
        """Screen readers: say the slice under the pointer."""
        try:
            from PySide6.QtGui import QAccessible, QAccessibleEvent
            if 0 <= self.hover < len(self.ops):
                o = self.ops[self.hover]
                text = tr(o.label) + (f", {tr(o.hint)}" if o.hint else "")
            else:
                text = tr(MODE_LABEL[self.mode])
            self.setAccessibleName(f"{APP} {tr(MODE_LABEL[self.mode])}: {text}")
            if QAccessible.isActive():
                QAccessible.updateAccessibility(QAccessibleEvent(self, QAccessible.NameChanged))
        except Exception:
            pass

    def _pill_dwell(self):
        if self.hover_pill:
            play_tick()
            self.set_mode(self.hover_pill)

    # ------------------------------------------------------------- click mode
    def mouseMoveEvent(self, e):
        self._track(e.position())

    def mousePressEvent(self, e):
        if self._closing:
            e.ignore()
            return
        kind, val = self.hit(e.position())
        if kind == "pill":
            self.set_mode(val)
        elif kind == "item" and 0 <= val < len(self.ops):
            op, paths = self.ops[val], list(self.paths)
            self.dismiss()
            QTimer.singleShot(0, lambda: self.app.execute(op, paths))
        else:
            self.dismiss()

    def keyPressEvent(self, e):
        k = e.key()
        n = len(self.ops)
        if k == Qt.Key_Escape:
            self.dismiss()
        elif k in (Qt.Key_Right, Qt.Key_Down) and n:
            self.hover = (self.hover + 1) % n if self.hover >= 0 else 0
            play_tick()
            self.update()
        elif k in (Qt.Key_Left, Qt.Key_Up) and n:
            self.hover = (self.hover - 1) % n if self.hover >= 0 else n - 1
            play_tick()
            self.update()
        elif k == Qt.Key_Tab:
            self.set_mode(MODES[(MODES.index(self.mode) + 1) % 3])
        elif k == Qt.Key_Backtab:
            self.set_mode(MODES[(MODES.index(self.mode) - 1) % 3])
        elif k in (Qt.Key_Return, Qt.Key_Enter) and 0 <= self.hover < n:
            op, paths = self.ops[self.hover], list(self.paths)
            self.dismiss()
            QTimer.singleShot(0, lambda: self.app.execute(op, paths))
        else:
            # modifier taps switch wheels, like during a drag
            keys = mode_keys()
            name = {Qt.Key_Shift: "Shift", Qt.Key_Control: "Ctrl", Qt.Key_Alt: "Alt"}.get(k)
            for m, kname in keys.items():
                if name == kname:
                    if m == self.mode:
                        self.dismiss()                 # the same key again closes the wheel
                    else:
                        play_tick()
                        self.set_mode(m)
                    break

    def focusOutEvent(self, e):
        if self.click_mode:
            QTimer.singleShot(120, lambda: (not self.isActiveWindow()) and self.dismiss())

    # ------------------------------------------------------------- painting
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        c = self.center()
        t = max(0.0, min(1.0, self._t))
        if t < 1.0:                                   # opening / closing animation
            if t <= 0.0:
                return
            if self._style == "circle":               # grows out of the pointer as a circle
                sc = 0.8 + 0.2 * t
                p.translate(c)
                p.scale(sc, sc)
                p.translate(-c)
                reach = math.hypot(self.width(), self.height())
                clip = QPainterPath()
                clip.addEllipse(c, 30 + t * reach, 30 + t * reach)
                p.setClipPath(clip)
                p.setOpacity(min(1.0, 0.35 + t))
            elif self._style == "bloom":
                pass                                  # drawn piece by piece below
            elif self._style == "spin":
                sc = 0.9 + 0.1 * t
                p.translate(c)
                p.rotate(-28 * (1 - t))
                p.scale(sc, sc)
                p.translate(-c)
                p.setOpacity(t)
            else:
                p.setOpacity(t)
        rings = self._rings()
        outer = rings[-1][1]

        bloom = self._style == "bloom" and t < 1.0
        if bloom:                                     # the disc fills in last, under the petals
            p.setOpacity(max(0.0, min(1.0, (t - 0.6) / 0.4)))
        # soft shadow
        g = QRadialGradient(c + QPointF(0, 6), outer + 16)
        g.setColorAt(0.86, C("shadow"))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(c + QPointF(0, 6), outer + 16, outer + 16)

        # disc
        p.setBrush(C("panel"))
        p.setPen(QPen(C("line"), 1))
        p.drawEllipse(c, outer, outer)

        offset = 0
        for ri, (r0, r1, items) in enumerate(rings):
            if ri > 0:
                p.setPen(QPen(C("line"), 1))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(c, r0 - 2, r0 - 2)
            n = len(items)
            if not n:
                continue
            step = 360 / n
            for i, op in enumerate(items):
                gi = offset + i
                a_mid = i * step                      # degrees clockwise from top
                hovered = gi == self.hover
                if bloom:                             # petals open one after another, clockwise from the top
                    k = (t - (0.18 + 0.55 * i / n)) / 0.27
                    if k <= 0:
                        continue
                    p.save()
                    p.setOpacity(min(1.0, k * 1.5))
                    sc = 0.5 + 0.5 * _ease_back(k)
                    p.translate(c)
                    p.scale(sc, sc)
                    p.translate(-c)
                if n == 1:                            # a single slice is the whole ring, no seam
                    path = QPainterPath()
                    path.setFillRule(Qt.OddEvenFill)
                    path.addEllipse(c, r1 - 3, r1 - 3)
                    path.addEllipse(c, r0 + 3, r0 + 3)
                else:
                    path = self._wedge(c, r0 + 3, r1 - 3, a_mid - step / 2 + 0.9, step - 1.8)
                if bloom:
                    p.setPen(Qt.NoPen)
                    p.setBrush(C("panel"))
                    p.drawPath(self._wedge(c, r0 - 4, r1, a_mid - step / 2, step) if n > 1 else path)
                if hovered:
                    grad = QRadialGradient(c, r1)
                    grad.setColorAt(0.25, ACCENT_2)
                    grad.setColorAt(1.0, ACCENT)
                    p.setBrush(grad)
                else:
                    p.setBrush(C("wedge"))
                p.setPen(Qt.NoPen)
                p.drawPath(path)
                # label
                rad = math.radians(a_mid)
                rm = r0 + (r1 - r0) * (0.6 if n > 10 else 0.5)   # wider part of the slice when crowded
                pt = QPointF(c.x() + rm * math.sin(rad), c.y() - rm * math.cos(rad))
                self._label(p, pt, op, hovered, (r1 - r0), step * math.pi / 180 * rm)
                if bloom:
                    p.restore()
            offset += n

        # center
        if bloom:                                     # the middle pops first
            p.save()
            p.setOpacity(min(1.0, t / 0.12))
            sc = max(0.05, _ease_back(t / 0.22))
            p.translate(c)
            p.scale(sc, sc)
            p.translate(-c)
        p.setPen(Qt.NoPen)
        p.setBrush(C("ring_hover") if self.hover == -2 else C("ring"))
        p.drawEllipse(c, self.R_IN - 4, self.R_IN - 4)
        self._center_text(p, c)
        if bloom:
            p.restore()
            p.setOpacity(max(0.0, min(1.0, (t - 0.65) / 0.3)))

        # mode pills
        keys = mode_keys()
        for m, r in self._pill_rects().items():
            active = m == self.mode
            p.setPen(QPen(C("line"), 1))
            p.setBrush(ACCENT if active else (C("ring_hover") if m == self.hover_pill else C("panel")))
            p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
            f = QFont(i18n.ui_font(), 9)
            f.setWeight(QFont.DemiBold)
            p.setFont(f)
            p.setPen(ON_ACCENT if active else C("text"))
            p.drawText(r, Qt.AlignCenter, tr(MODE_LABEL[m]) if keys[m] == "None" else f"{tr(keys[m])}  ·  {tr(MODE_LABEL[m])}")
        p.end()

    @staticmethod
    def _wedge(c, r0, r1, start_deg, span_deg) -> QPainterPath:
        # Qt angles: 0 = 3 o'clock, counter-clockwise. Ours: 0 = 12 o'clock, clockwise.
        qs = 90 - start_deg
        path = QPainterPath()
        outer = QRectF(c.x() - r1, c.y() - r1, 2 * r1, 2 * r1)
        inner = QRectF(c.x() - r0, c.y() - r0, 2 * r0, 2 * r0)
        path.arcMoveTo(outer, qs)
        path.arcTo(outer, qs, -span_deg)
        path.arcTo(inner, qs - span_deg, span_deg)
        path.closeSubpath()
        return path

    def _label(self, p, pt, op, hovered, depth, arc_len):
        label = tr(op.label)
        max_w = max(46, min(arc_len - 10, depth + 34))
        size = 10.0
        lines = [label]
        while True:
            f = QFont(i18n.ui_font(), 1)
            f.setPointSizeF(size)
            f.setWeight(QFont.DemiBold)
            fm = QFontMetrics(f)
            lines = [label]
            if fm.horizontalAdvance(label) > max_w and " " in label:
                words = label.split(" ")
                best = None
                for i in range(1, len(words)):      # most balanced two-line split
                    l1, l2 = " ".join(words[:i]), " ".join(words[i:])
                    wid = max(fm.horizontalAdvance(l1), fm.horizontalAdvance(l2))
                    if best is None or wid < best[0]:
                        best = (wid, [l1, l2])
                lines = best[1]
            if max(fm.horizontalAdvance(x) for x in lines) <= max_w or size <= 7.5:
                break
            size -= 0.5
        lines = [fm.elidedText(x, Qt.ElideRight, int(max_w)) for x in lines]
        p.setFont(f)
        p.setPen(ON_ACCENT if hovered else C("text"))
        lh = fm.height() - 2
        hint_h = 12 if op.hint else 0
        total = lh * len(lines) + hint_h
        y = pt.y() - total / 2
        for line in lines:
            p.drawText(QRectF(pt.x() - 80, y, 160, lh + 2), Qt.AlignCenter, line)
            y += lh
        if op.hint:
            f2 = QFont(i18n.ui_font(), 7)
            p.setFont(f2)
            p.setPen(QColor(28, 28, 30, 200) if hovered else C("dim"))
            p.drawText(QRectF(pt.x() - 80, y, 160, hint_h + 2), Qt.AlignCenter, tr(op.hint))

    def _center_text(self, p, c):
        r = QRectF(c.x() - self.R_IN + 6, c.y() - 30, 2 * self.R_IN - 12, 60)
        mode = tr(MODE_LABEL[self.mode])
        if self.hover == -2:
            title, sub = tr("Cancel"), tr("drop here")
        elif 0 <= self.hover < len(self.ops):
            title, sub = tr(self.ops[self.hover].label).rstrip("…"), mode
        elif not self.paths:
            title, sub = mode, tr("move to read file")
        else:
            n = len(self.paths)
            title = mode
            if n > 1:
                sub = tr("{n} files", n=n)
            else:
                name = Path(self.paths[0]).name
                cat = tr(engine.CATEGORY_LABEL.get(engine.category_of(self.paths), "File"))
                sub = name if len(name) <= 16 else (Path(name).suffix.upper().lstrip(".") or cat)
        f = QFont(i18n.ui_font(), 11)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.setPen((ACCENT_2 if theme.is_dark() else ACCENT) if self.hover >= 0 else C("text"))
        fm = QFontMetrics(f)
        if fm.horizontalAdvance(title) > r.width():
            f.setPointSizeF(9)
            p.setFont(f)
            p.drawText(QRectF(r.x(), r.y() - 6, r.width(), 38), Qt.AlignCenter | Qt.TextWordWrap, title)
        else:
            p.drawText(QRectF(r.x(), r.y() + 6, r.width(), 24), Qt.AlignCenter, title)
        f2 = QFont(i18n.ui_font(), 8)
        p.setFont(f2)
        p.setPen(C("dim"))
        p.drawText(QRectF(r.x(), r.y() + 30, r.width(), 18), Qt.AlignCenter,
                   QFontMetrics(f2).elidedText(sub, Qt.ElideMiddle, int(r.width())))


# ============================================================================
# Toast
# ============================================================================
_SOUND_CACHE = {}


def _media_sound(words) -> str | None:
    """A Windows sound file by name, e.g. ("notify", "calendar") -> C:\\Windows\\Media\\Windows Notify Calendar.wav."""
    if words in _SOUND_CACHE:
        return _SOUND_CACHE[words]
    found = None
    media = Path(os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows") / "Media"
    try:
        for f in sorted(media.glob("*.wav")):
            n = f.stem.lower()
            if all(w in n for w in words):
                found = str(f)
                break
    except OSError:
        pass
    _SOUND_CACHE[words] = found
    return found


_TICK = None


_SELECT = None
_EFFECTS = {}
_LAST_SELECT = 0.0


def _tick_effect(name="tick"):
    """Loaded once at start-up, so even the first click plays straight away."""
    global _TICK, _SELECT
    from PySide6.QtMultimedia import QSoundEffect
    if name in ("open", "close"):
        if name not in _EFFECTS:
            fx = QSoundEffect()
            fx.setSource(QUrl.fromLocalFile(asset(f"sounds/{name}.wav")))
            _EFFECTS[name] = fx
        return _EFFECTS[name]
    if name == "select":
        if _SELECT is None:
            _SELECT = QSoundEffect()
            _SELECT.setSource(QUrl.fromLocalFile(asset("sounds/select.wav")))
        return _SELECT
    if _TICK is None:
        _TICK = QSoundEffect()
        _TICK.setSource(QUrl.fromLocalFile(asset("sounds/tick.wav")))
    return _TICK


def play_wheel_sound(name):
    """The soft rising sound when the wheel opens and the falling one when it closes (same switch and volume as the tick)."""
    if settings().value("tick_sound", "true") != "true":
        return
    if name == "close" and time.monotonic() - _LAST_SELECT < 0.8:
        return                                   # choosing a slice already made its own sound
    try:
        fx = _tick_effect(name)
        fx.setVolume(max(0, min(100, int(settings().value("tick_volume", 70)))) / 100 * 0.8)
        fx.stop()
        fx.play()
    except Exception as e:
        winsys.log(f"{name} sound: {e}")


def play_select():
    """The deeper "press" when you choose a slice (like the iPod's centre button). Same switch and volume as the tick."""
    global _LAST_SELECT
    _LAST_SELECT = time.monotonic()
    if settings().value("tick_sound", "true") != "true":
        return
    try:
        fx = _tick_effect("select")
        fx.setVolume(max(0, min(100, int(settings().value("tick_volume", 70)))) / 100)
        fx.play()
    except Exception as e:
        winsys.log(f"select sound: {e}")


def play_tick(force=False):
    """The click when the highlight moves to another slice (Settings → Everyday, with its own volume)."""
    if settings().value("tick_sound", "true") != "true" and not force:
        return
    try:
        fx = _tick_effect()
        fx.setVolume(max(0, min(100, int(settings().value("tick_volume", 70)))) / 100)
        fx.stop()
        fx.play()
    except Exception as e:
        winsys.log(f"tick sound: {e}")


def play_finish_sound(kind="ok"):
    """Windows' "Notify Calendar" sound when a job finishes, "Notify Messaging" for an error (Settings → Everyday)."""
    if settings().value("finish_sound", "true") != "true" or not winsys.IS_WIN:
        return
    wav = _media_sound(("notify", "messaging") if kind == "err" else ("notify", "calendar"))
    try:
        import winsound
        if wav:
            winsound.PlaySound(wav, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        winsys.log(f"sound ({kind}): {Path(wav).name if wav else 'not found in Windows Media folder'}")
    except Exception as e:
        winsys.log(f"sound ({kind}) failed: {e}")


class Toast(QWidget):
    closed = Signal(object)
    resized = Signal()
    TOAST_CSS = """
    QLabel#title{color:$text;font:600 10pt 'Segoe UI'}
    QLabel#body{color:$dim;font:9pt 'Segoe UI'}
    QPushButton#show{background:$accent;color:$on_accent;border:none;border-radius:11px;padding:4px 12px;font:600 9pt 'Segoe UI'}
    QPushButton#show:hover{background:$accent2}
    QPushButton#cancel{background:$button;color:$text;border:none;border-radius:11px;padding:4px 12px;font:600 9pt 'Segoe UI'}
    QPushButton#cancel:hover{background:$danger;color:#ffffff}
    """

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedWidth(360)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 12, 12)
        lay.setSpacing(10)
        self.icon = QLabel()
        self.icon.setFixedSize(30, 30)
        lay.addWidget(self.icon)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.title = QLabel()
        self.title.setObjectName("title")
        self.body = QLabel()
        self.body.setObjectName("body")
        self.body.setWordWrap(True)
        col.addWidget(self.title)
        col.addWidget(self.body)
        lay.addLayout(col, 1)
        self.btn = QPushButton()
        self.btn.setObjectName("show")
        self.btn.setCursor(Qt.PointingHandCursor)
        self.btn.clicked.connect(self._reveal)
        lay.addWidget(self.btn)
        self.undo_btn = QPushButton()
        self.undo_btn.setObjectName("cancel")
        self.undo_btn.setCursor(Qt.PointingHandCursor)
        self.undo_btn.clicked.connect(self._undo)
        self.undo_btn.hide()
        lay.addWidget(self.undo_btn)
        self.on_undo = None
        self.cancel_btn = QPushButton()
        self.cancel_btn.setObjectName("cancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._cancel)
        lay.addWidget(self.cancel_btn)
        self.timer = QTimer(self, singleShot=True, timeout=self._fade_out)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.finished.connect(self._faded)
        self._fading = False
        self._auto_ms = 0
        self.target = None
        self.on_cancel = None
        self.spin = 0
        self.spin_timer = QTimer(self, interval=60, timeout=self._spin)
        self.restyle()

    def restyle(self):
        """Apply the current language's font and button texts."""
        self.setStyleSheet(i18n.css(self.TOAST_CSS))
        self.btn.setText(tr("Show"))
        self.undo_btn.setText(tr("Undo"))
        self.cancel_btn.setText(tr("Cancel"))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(C("line"), 1))
        p.setBrush(C("panel"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)

    def _place(self):
        self.adjustSize()
        self.resized.emit()          # the manager re-stacks all cards

    # like Windows' notifications: they fade away, and come back while the mouse is on them
    def _fade_out(self):
        if self.underMouse():
            return
        self._fading = True
        self._fade.stop()
        self._fade.setDuration(2200)                 # a slow, gentle fade
        self._fade.setStartValue(self.windowOpacity())
        self._fade.setEndValue(0.0)
        self._fade.start()

    def _faded(self):
        if self._fading and self.windowOpacity() < 0.05:
            self._fading = False
            self.close_card()

    def enterEvent(self, e):
        if self._fading:
            self._fading = False
            self._fade.stop()
        self.setWindowOpacity(1.0)
        self.timer.stop()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if self._auto_ms and getattr(self, "wanted", False):
            self.timer.start(4000)
        super().leaveEvent(e)

    def close_card(self):
        self.wanted = False
        self.timer.stop()
        self.spin_timer.stop()
        self.hide()
        self.closed.emit(self)

    def _set_icon(self, kind):
        pm = QPixmap(30, 30)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        if kind == "busy":
            p.setPen(QPen(C("busy_track"), 3))
            p.drawEllipse(4, 4, 22, 22)
            pen = QPen(ACCENT, 3)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(4, 4, 22, 22, -self.spin * 16, 100 * 16)
        else:
            col = {"ok": C("ok"), "err": C("danger"), "info": ACCENT}[kind]
            t = getattr(self, "_ok_t", 1.0) if kind == "ok" else 1.0
            r = 12 * min(1.0, 0.35 + t * 1.3) if t < 1.0 else 12
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(QPointF(15, 15), r, r)
            p.setPen(QPen(ON_ACCENT if kind != "err" else QColor("#ffffff"), 2.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            if kind == "ok":
                pts = [QPointF(9, 15.5), QPointF(13.5, 20), QPointF(21, 11)]
                k = max(0.0, min(1.0, (t - 0.3) / 0.7))          # the tick draws itself after the circle
                if k >= 1.0:
                    p.drawPolyline(pts)
                elif k > 0:
                    l1 = math.dist((9, 15.5), (13.5, 20))
                    l2 = math.dist((13.5, 20), (21, 11))
                    d = k * (l1 + l2)
                    if d <= l1:
                        p.drawLine(pts[0], pts[0] + (pts[1] - pts[0]) * (d / l1))
                    else:
                        p.drawPolyline([pts[0], pts[1], pts[1] + (pts[2] - pts[1]) * ((d - l1) / l2)])
            elif kind == "err":
                p.drawLine(10, 10, 20, 20)
                p.drawLine(20, 10, 10, 20)
            else:
                p.drawLine(15, 9, 15, 17)
                p.drawPoint(15, 21)
        p.end()
        self.icon.setPixmap(pm)

    def _spin(self):
        self.spin = (self.spin + 24) % 360
        self._set_icon("busy")

    def _show(self, title, body, kind, show_btn=False, cancel=None, ms=None):
        self.timer.stop()
        self._fade.stop()
        self._fading = False
        self.setWindowOpacity(1.0)
        if ms:
            ms = max(7000, int(ms * 2))             # long enough to read; hovering keeps it
        self._auto_ms = ms or 0
        self.restyle()
        self.title.setText(title)
        self.body.setText(body)
        self.btn.setVisible(show_btn)
        self.on_undo = None
        self.undo_btn.hide()
        self.on_cancel = cancel
        self.cancel_btn.setVisible(cancel is not None)
        if kind == "busy":
            self.spin_timer.start()
        else:
            self.spin_timer.stop()
        if kind == "ok" and settings().value("finish_anim", "true") == "true":
            self._ok_t = 0.0
            anim = QVariantAnimation(self)
            anim.setDuration(520)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.valueChanged.connect(lambda v: (setattr(self, "_ok_t", float(v)), self._set_icon("ok")))
            anim.start(QVariantAnimation.DeleteWhenStopped)
        else:
            self._ok_t = 1.0
        if kind == "err" or (kind == "ok" and getattr(self, "_sound_for_this", False)):
            play_finish_sound(kind)                  # every error; "done" only when a job finished
        self._sound_for_this = False
        self._set_icon(kind)
        # screen readers read the card by its name; no "alert" event: on Windows that also plays the system sound
        self.setAccessibleName(f"{title}. {QTextDocumentFragment.fromHtml(body).toPlainText()}")
        self.wanted = True          # counts in the stack even before Windows shows it
        self._place()               # position first, so it never flashes in the middle of the screen
        self.show()
        self.raise_()
        if ms:
            self.timer.start(ms)

    def show_busy(self, title, body, on_cancel=None):
        self._show(title, body, "busy", cancel=on_cancel)

    def show_msg(self, title, body, kind="info", ms=2600):
        self._show(title, body, kind, ms=ms)
        return self

    def show_result(self, title, outs):
        outs = [Path(o) for o in outs if o]
        self.target = [str(o) for o in outs] if outs else None     # all of them get selected
        body = outs[0].name if len(outs) == 1 else tr("{n} items saved", n=len(outs))
        self._show(title, body, "ok", show_btn=bool(self.target), ms=5000)
        return self

    def set_undo(self, fn):
        """An Undo button that takes back what the job just made (the files go to the Recycle Bin)."""
        self.on_undo = fn
        self.undo_btn.setVisible(fn is not None)
        if fn is not None and self.timer.isActive():
            self.timer.start(max(self.timer.remainingTime(), 9000))     # time to change your mind
        self._place()

    def _undo(self):
        fn, self.on_undo = self.on_undo, None
        if fn:
            play_finish_sound("err")
            ok = fn()
            self.btn.hide()
            self.undo_btn.hide()
            self.title.setText(tr("Undone") if ok else tr("Couldn't undo"))
            self.body.setText(tr("The new file went to the Recycle Bin.") if ok else self.body.text())
            self.target = None
            self._set_icon("info" if ok else "err")
            self._place()
            self.timer.start(3000)

    def _cancel(self):
        cb, self.on_cancel = self.on_cancel, None
        self.cancel_btn.setEnabled(False)
        if cb:
            cb()
        self.cancel_btn.setEnabled(True)

    def _reveal(self):
        if self.target:
            winsys.reveal(self.target)
        self.close_card()


class ToastManager(QObject):
    """Stacks notification cards bottom-right (bottom-left in Arabic). Each job gets its own card,
    so a new message never hides a running conversion."""
    GAP = 10
    MAX = 6

    def __init__(self):
        super().__init__()
        self.cards: list[Toast] = []

    def _new(self) -> Toast:
        t = Toast()
        t.closed.connect(self._closed)
        t.resized.connect(self.reflow)
        self.cards.append(t)
        while len(self.cards) > self.MAX:       # drop the oldest finished card
            old = next((c for c in self.cards if c.on_cancel is None), self.cards[0])
            old.close_card()
        return t

    def _closed(self, card):
        if card in self.cards:
            self.cards.remove(card)
        card.deleteLater()
        self.reflow()

    def reflow(self):
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        y = g.bottom() - 18
        for c in reversed(self.cards):          # newest at the bottom
            if not getattr(c, "wanted", False):
                continue
            c.adjustSize()
            x = g.left() + 18 if i18n.is_rtl() else g.right() - c.width() - 18
            y -= c.height()
            c.move(x, y)
            y -= self.GAP

    def restyle(self):
        for c in self.cards:
            c.restyle()

    # same API as a single card — every call makes a new card and returns it
    def show_busy(self, title, body, on_cancel=None) -> Toast:
        t = self._new()
        t.show_busy(title, body, on_cancel)
        return t

    def show_msg(self, title, body, kind="info", ms=2600) -> Toast:
        t = self._new()
        t.show_msg(title, body, kind, ms)
        return t

    def show_result(self, title, outs) -> Toast:
        t = self._new()
        t.show_result(title, outs)
        return t

    def set_undo(self, fn):
        pass


# ============================================================================
# Float window — pinned, always on top, like a mini player.
# The picture fills the card; the close button, name, grip (and video controls) fade in only while
# the cursor is over it. Drag to move, drag an edge or corner to resize, drag the grip to drop the
# file into another app. Videos and audio play in place; other files show their icon, click to open.
# ============================================================================
def _fmt_time(ms):
    s = max(0, int(ms // 1000))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _find_side_subtitles(video) -> list[str]:
    """Subtitle files next to a video with the same name: movie.srt, movie.en.srt, movie.vtt ..."""
    v = Path(video)
    try:
        return sorted(str(f) for f in v.parent.iterdir()
                      if f.suffix.lower() in (".srt", ".vtt") and f.name.lower().startswith(v.stem.lower()))
    except OSError:
        return []


def _parse_subtitles(path) -> list[tuple[int, int, str]]:
    """Read an SRT or WebVTT file into (start ms, end ms, text) cues. Handles UTF-8 and Arabic (Windows-1256)."""
    import re
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    ts = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{1,3})|(\d\d):(\d\d)[,.](\d{1,3})")

    def ms(t):
        m = ts.fullmatch(t.strip().split(" ")[0])
        if not m:
            return None
        if m.group(1):
            h, mi, se, fr = m.group(1, 2, 3, 4)
        else:
            h, (mi, se, fr) = "0", m.group(5, 6, 7)
        return ((int(h) * 60 + int(mi)) * 60 + int(se)) * 1000 + int(fr.ljust(3, "0"))

    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", text.replace("\r\n", "\n")):
        lines = [l for l in block.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if "-->" in line:
                a, b = line.split("-->", 1)
                start, end = ms(a), ms(b)
                if start is not None and end is not None:
                    body = "\n".join(lines[i + 1:])
                    body = re.sub(r"<[^>]+>|\{[^}]*\}", "", body).strip()
                    if body:
                        cues.append((start, end, body))
                break
    return cues


class StreamCache:
    """Downloads an online video ahead of playback over several connections into a temp file and serves it to
    the float from a local address (with seeking). The player then never waits on a slow request; going back
    is instant. The temp file is deleted when the float closes."""
    CHUNK = 2 * 1024 * 1024
    WORKERS = 4
    AHEAD = 400 * 1024 * 1024          # how far past the playing point to fetch

    def __init__(self, url, headers=None, size=None):
        import http.server
        import tempfile
        import urllib.request
        self.url = url
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.headers.update(headers or {})
        if not size:                                     # YouTube links carry the length (clen=…)
            import urllib.parse as _up
            size = (_up.parse_qs(_up.urlparse(url).query).get("clen") or [0])[0]
        self.size = int(size or 0) or self._probe_size()
        if not self.size:
            raise OSError("size unknown")
        self.n = (self.size + self.CHUNK - 1) // self.CHUNK
        self.have = bytearray(self.n)
        self.busy = set()
        self.fails = 0
        self.focus = 0
        self.closed = False
        self.cond = threading.Condition()
        self.flock = threading.Lock()
        fd, self.tmp = tempfile.mkstemp(prefix="dragwheel-stream-", suffix=".bin")
        os.close(fd)
        self.f = open(self.tmp, "r+b")
        self.f.truncate(self.size)
        cache = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _range(h):
                import re as _re
                m = _re.match(r"bytes=(\d*)-(\d*)", h.headers.get("Range", ""))
                if not m:
                    return 0, cache.size - 1, False
                a = int(m.group(1) or 0)
                b = int(m.group(2)) if m.group(2) else cache.size - 1
                return a, min(b, cache.size - 1), True

            def do_HEAD(h):
                h.send_response(200)
                h.send_header("Content-Type", "video/mp4")
                h.send_header("Content-Length", str(cache.size))
                h.send_header("Accept-Ranges", "bytes")
                h.end_headers()

            def do_GET(h):
                a, b, partial = h._range()
                if a >= cache.size:
                    h.send_response(416)
                    h.send_header("Content-Range", f"bytes */{cache.size}")
                    h.send_header("Content-Length", "0")
                    h.end_headers()
                    return
                h.send_response(206 if partial else 200)
                h.send_header("Content-Type", "video/mp4")
                h.send_header("Accept-Ranges", "bytes")
                h.send_header("Content-Length", str(b - a + 1))
                if partial:
                    h.send_header("Content-Range", f"bytes {a}-{b}/{cache.size}")
                h.end_headers()
                cache.set_focus(a)
                pos = a
                try:
                    while pos <= b and not cache.closed:
                        i = pos // cache.CHUNK
                        if not cache.wait_chunk(i):
                            return
                        end = min(b + 1, (i + 1) * cache.CHUNK)
                        with cache.flock:
                            cache.f.seek(pos)
                            data = cache.f.read(end - pos)
                        h.wfile.write(data)
                        pos = end
                        if pos > cache.focus + cache.CHUNK:
                            cache.set_focus(pos)
                except OSError:
                    pass                                   # the player seeked or closed this connection

            def log_message(h, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.local = f"http://127.0.0.1:{self.server.server_address[1]}/media"
        for _ in range(self.WORKERS):
            threading.Thread(target=self._worker, daemon=True).start()

    def _request(self, a, b, timeout=20):
        import urllib.request
        req = urllib.request.Request(self.url, headers=dict(self.headers, Range=f"bytes={a}-{b}"))
        return urllib.request.urlopen(req, timeout=timeout)

    def _probe_size(self):
        try:
            with self._request(0, 0, timeout=6) as r:
                cr = r.headers.get("Content-Range", "")
                return int(cr.rsplit("/", 1)[1]) if "/" in cr else int(r.headers.get("Content-Length") or 0)
        except Exception as e:
            winsys.log(f"stream cache: size probe failed: {e}")
            return 0

    def set_focus(self, pos):
        with self.cond:
            self.focus = pos
            self.cond.notify_all()

    def wait_chunk(self, i):
        with self.cond:
            while not self.have[i] and not self.closed:
                self.cond.wait(0.5)
            return not self.closed

    def _next(self):
        """The first missing chunk at or after the playing point (within reach), else before it."""
        start = self.focus // self.CHUNK
        limit = min(self.n, start + self.AHEAD // self.CHUNK)
        for i in range(start, limit):
            if not self.have[i] and i not in self.busy:
                return i
        return None

    def _worker(self):
        while not self.closed:
            with self.cond:
                i = self._next()
                if i is None:
                    if all(self.have):
                        return
                    self.cond.wait(0.5)
                    continue
                self.busy.add(i)
            a = i * self.CHUNK
            b = min(self.size, a + self.CHUNK) - 1
            ok = False
            for attempt in range(3):
                try:
                    with self._request(a, b) as r:
                        data = r.read()
                    if len(data) == b - a + 1:
                        with self.flock:
                            self.f.seek(a)
                            self.f.write(data)
                        ok = True
                        break
                except Exception as e:
                    if attempt == 2:
                        winsys.log(f"stream cache: chunk {i} failed: {e}")
                    time.sleep(0.5 * (attempt + 1))
            with self.cond:
                self.busy.discard(i)
                if ok:
                    self.have[i] = 1
                else:
                    self.fails += 1
                self.cond.notify_all()
            if not ok:
                time.sleep(1.0)

    def close(self):
        with self.cond:
            self.closed = True
            self.cond.notify_all()
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
        try:
            with self.flock:
                self.f.close()
            os.remove(self.tmp)
        except OSError:
            pass


def _cacheable(url) -> bool:
    u = str(url).lower()
    own = u.startswith("http://127.0.0.1:") and u.endswith(("/media", "/live.ts"))     # DragWheel's own
    return u.startswith(("http://", "https://")) and "m3u8" not in u and "hls_playlist" not in u \
        and not own and ".mpd" not in u


LIVE_OUTPUT = ["-f", "mpegts"]
LIVE_INPUT_EXTRA = []          # tests add "-re" to feed a recorded stream at live speed


class LiveRelay:
    """Plays a live stream through ffmpeg: ffmpeg follows the live playlist as it grows (Qt's player stops when
    the first ~30 s run out) and passes one endless stream to the float over a local address."""

    def __init__(self, url, headers=None):
        import http.server
        import subprocess
        relay = self
        self.procs = []
        hdr = dict(headers or {})
        args = ["-hide_banner", "-loglevel", "warning", "-fflags", "+genpts"]
        self.last_data = time.monotonic()
        self.total = 0
        self.forbidden = False
        ua = next((v for k, v in hdr.items() if k.lower() == "user-agent"), None)
        if ua:
            args += ["-user_agent", ua]
        extra = "".join(f"{k}: {v}\r\n" for k, v in hdr.items() if k.lower() != "user-agent")
        if extra:
            args += ["-headers", extra]
        if "m3u8" in url or "hls" in url:
            args += ["-live_start_index", "-6", "-http_persistent", "1", "-http_multiple", "1"]
        cmd = [engine.ffmpeg(), *args, *LIVE_INPUT_EXTRA, "-i", url, "-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy",
               *LIVE_OUTPUT, "pipe:1"]

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(h):
                h.send_response(200)
                h.send_header("Content-Type", "video/mp2t")
                h.send_header("Cache-Control", "no-cache")
                h.end_headers()
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                        creationflags=engine.NO_WINDOW)
                relay.procs.append(proc)
                relay.last_data = time.monotonic()
                t0 = time.monotonic()

                def errors(stream=proc.stderr):            # ffmpeg's own warnings, so a stall can be explained
                    n = forbidden = 0
                    for raw in iter(stream.readline, b""):
                        line = raw.decode("utf-8", "replace").strip()
                        if line and n < 12:
                            n += 1
                            winsys.log(f"live relay ffmpeg [{time.monotonic() - t0:.0f}s]: {line[:220]}")
                        if "403 Forbidden" in line:
                            forbidden += 1
                            if forbidden == 3:             # this player's stream is refused: use another one
                                client = engine.yt_client(url)
                                engine.LIVE_BAD_CLIENTS.add(client)
                                relay.forbidden = True
                                winsys.log(f"live relay: YouTube refuses the {client or '?'} stream, switching player")
                                try:
                                    proc.kill()
                                except Exception:
                                    pass
                threading.Thread(target=errors, daemon=True).start()
                sent = 0
                try:
                    while True:
                        chunk = proc.stdout.read(65536)
                        if not chunk:
                            break
                        h.wfile.write(chunk)
                        sent += len(chunk)
                        relay.last_data = time.monotonic()
                        relay.total += len(chunk)
                except OSError:
                    pass                                       # the float closed or reconnected
                finally:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    winsys.log(f"live relay: ffmpeg stopped after {sent // 1024} KB, {time.monotonic() - t0:.0f}s")
                    if proc in relay.procs:
                        relay.procs.remove(proc)

            def log_message(h, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/live.ts"

    def close(self):
        for p in list(self.procs):
            try:
                p.kill()
            except Exception:
                pass
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass


def saved_links() -> list:
    """Links played in Float, newest first: [{"url", "title"}]."""
    try:
        v = json.loads(settings().value("float_links", "[]") or "[]")
        return [x for x in v if isinstance(x, dict) and x.get("url")]
    except (TypeError, ValueError):
        return []


def remember_link(url, title):
    links = [x for x in saved_links() if x["url"] != url]
    links.insert(0, {"url": url, "title": title or url})
    settings().setValue("float_links", json.dumps(links[:40], ensure_ascii=False))


def forget_link(url):
    settings().setValue("float_links", json.dumps([x for x in saved_links() if x["url"] != url], ensure_ascii=False))


def _float_pins() -> list:
    """Floats that reopen when Windows starts: [{"id", "src", "link", "x", "y", "w", "on_top"}]."""
    try:
        v = json.loads(settings().value("float_pins", "[]") or "[]")
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


def _save_float_pins(pins):
    settings().setValue("float_pins", json.dumps(pins))


class MediaOSD(QWidget):
    """A big see-through play/pause/next/previous sign in the middle of the screen for a second."""
    _one = None

    @staticmethod
    def wanted(focused) -> bool:
        s = settings()
        if s.value("media_osd", "true") != "true":
            return False
        return s.value("media_osd_when", "unfocused") == "always" or not focused

    @classmethod
    def flash(cls, kind, near=None, level=None, hold=750):
        if cls._one is None:
            cls._one = MediaOSD()
        cls._one.level = level
        cls._one._show(kind, near, hold)

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.kind = "play"
        self.level = None
        self.setFixedSize(180, 180)
        self._hold = QTimer(self, singleShot=True, timeout=self._fade)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.finished.connect(self._done)

    def _show(self, kind, near, hold=750):
        self.kind = kind
        scr = (near.screen() if near is not None else None) or QGuiApplication.screenAt(QCursor.pos()) \
            or QGuiApplication.primaryScreen()
        g = scr.geometry()
        self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        self._anim.stop()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self.update()
        self._hold.start(hold)

    def _fade(self):
        self._anim.setDuration(250)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _done(self):
        if self.windowOpacity() < 0.05:
            self.hide()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawEllipse(self.rect().adjusted(2, 2, -2, -2))
        p.setBrush(QColor(255, 255, 255, 215))
        c = self.rect().center()
        cx, cy = c.x() + 1, c.y() + 1

        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)

        def tri(x0, pointing_right=True, w=46, h=56):
            x1 = x0 + w if pointing_right else x0 - w
            path.addPolygon(QPolygonF([QPointF(x0, cy - h / 2), QPointF(x1, cy), QPointF(x0, cy + h / 2),
                                       QPointF(x0, cy - h / 2)]))

        k = self.kind
        if k == "play":
            tri(cx - 20, w=54, h=64)
        elif k == "pause":
            p.drawRoundedRect(QRectF(cx - 26, cy - 32, 18, 64), 4, 4)
            p.drawRoundedRect(QRectF(cx + 8, cy - 32, 18, 64), 4, 4)
        elif k == "stop":
            p.drawRoundedRect(QRectF(cx - 28, cy - 28, 56, 56), 6, 6)
        elif k == "next":
            tri(cx - 40)
            tri(cx - 4)
            p.drawRoundedRect(QRectF(cx + 40, cy - 28, 9, 56), 2, 2)
        elif k == "prev":
            tri(cx + 40, False)
            tri(cx + 4, False)
            p.drawRoundedRect(QRectF(cx - 49, cy - 28, 9, 56), 2, 2)
        elif k in ("volume", "mute"):
            sy = cy - 16                                   # speaker a little higher, the level bar under it
            sp = QPolygonF([QPointF(cx - 38, sy - 11), QPointF(cx - 26, sy - 11), QPointF(cx - 8, sy - 28),
                            QPointF(cx - 8, sy + 28), QPointF(cx - 26, sy + 11), QPointF(cx - 38, sy + 11)])
            path.addPolygon(sp)
            path.closeSubpath()
            pen = QPen(QColor(255, 255, 255, 215), 6, Qt.SolidLine, Qt.RoundCap)
            lvl = self.level if self.level is not None else 1.0
            if k == "mute" or lvl <= 0.001:
                p.setPen(pen)
                p.drawLine(QPointF(cx + 6, sy - 14), QPointF(cx + 34, sy + 14))
                p.drawLine(QPointF(cx + 34, sy - 14), QPointF(cx + 6, sy + 14))
            else:
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                for i, r in enumerate((14, 26, 38)):
                    if lvl > i / 3 or i == 0:
                        p.drawArc(QRectF(cx - 8 - r, sy - r, 2 * r, 2 * r), -45 * 16, 90 * 16)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 215))
            bar = QRectF(cx - 50, cy + 34, 100, 8)
            p.setBrush(QColor(255, 255, 255, 70))
            p.drawRoundedRect(bar, 4, 4)
            p.setBrush(QColor(255, 255, 255, 215) if k == "volume" else QColor(255, 255, 255, 110))
            p.drawRoundedRect(QRectF(bar.x(), bar.y(), bar.width() * lvl, bar.height()), 4, 4)
            f = QFont("Segoe UI", 10, QFont.DemiBold)
            p.setFont(f)
            p.setPen(QColor(255, 255, 255, 215))
            p.drawText(QRectF(cx - 50, cy + 44, 100, 22), Qt.AlignCenter, f"{round(lvl * 100)}")
            p.setPen(Qt.NoPen)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 215))
        p.drawPath(path.simplified())
        p.end()


class FloatWindow(QWidget):
    def come_forward(self):
        """A float you just opened shows in front of other windows, even when it isn't set to stay on top."""
        self.raise_()
        if not getattr(self, "on_top", True):
            QTimer.singleShot(60, lambda: winsys.bring_to_front(int(self.winId())))

    closed = Signal()
    page_ready = Signal(object, object)    # path, QImage of a document's first page (from a thread)
    RADIUS = 14
    EDGE = 7              # resize border
    CLOSE_R = 11
    MIN_W = 160

    def __init__(self, path, link=None, play=False, pin=None):
        on_top = settings().value("float_on_top", "true") == "true"
        if pin is not None:
            on_top = bool(pin.get("on_top", on_top))
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | (Qt.WindowStaysOnTopHint if on_top else Qt.Widget))
        self.on_top = on_top
        self._vol_open = False
        self._vol_drag = False
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)        # drop another file on the float to replace it
        self.player = None
        self.hover = None
        self.ctrl = 1.0                  # opacity of the controls; fades with the cursor
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.valueChanged.connect(self._set_ctrl)
        self._press = None               # (kind, global pos, local pos, geometry, edges)
        self._seeking = False
        self._drop_hover = False
        self.pin_id = None               # set when this float reopens with Windows
        self._pin_timer = QTimer(self, singleShot=True, interval=500, timeout=self._save_pin)
        self.companion = None
        self._relay = None
        self.repeat = settings().value("float_repeat", "off")     # off | one | all
        self._play_now = play
        self._load(path, link)
        self.move(QCursor.pos() - QPoint(self.width() // 2, 40))
        self._resume_ms = int((pin or {}).get("pos") or 0)     # where playback was before an update
        if pin is not None:
            self.pin_id = pin.get("id")
            try:
                w = max(self.MIN_W, int(pin.get("w", self.width())))
                self._apply_size(w, self._height_for(w))
                at = QPoint(int(pin["x"]), int(pin["y"]))
                if QGuiApplication.screenAt(at + QPoint(20, 20)) is not None:
                    self.move(at)
            except (KeyError, TypeError, ValueError):
                pass
        # show the controls briefly so people know they exist, then let them fade
        QTimer.singleShot(1600, self._maybe_hide_controls)

    def _load(self, path, link=None):
        """Show `path` in this float (also used when another file is dropped on it).
        `link` = {"url", "title", "page"} when playing a web link (path is then the media URL)."""
        self._drop_companion()
        self._stop_relay()
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())
            self.player.deleteLater()
            self.player = None
        prev_kind, prev_w = getattr(self, "kind", None), self.width()
        self.path = path
        self.link = link
        cat = "video" if link else engine.EXT_CATEGORY.get(engine.ext_of(path))
        self.kind = "other"          # image | video | audio | other
        self.src = None              # QPixmap for images, album covers and icons
        self.art = False             # True when src is an album cover
        self.frame = None            # current video frame (QImage)
        self.aspect = None           # width / height of the picture, kept while resizing
        self._scaled = None
        if cat == "image":
            try:
                img = engine.open_image(path)
                img.thumbnail((1600, 1600))
                q = QImage(img.convert("RGBA").tobytes("raw", "RGBA"), img.width, img.height,
                           img.width * 4, QImage.Format_RGBA8888)
                self.src = QPixmap.fromImage(q.copy())
                self.kind = "image"
                self.aspect = img.width / max(1, img.height)
            except Exception:
                self.src = None
        elif path and (cat in DOC_PREVIEW_CATS or cat == "comic") and Path(path).suffix.lower() not in (".cbr", ".cb7", ".cbt"):
            # PDFs, e-books and Office files show their first page; the icon stays until it's drawn
            if not getattr(self, "_page_hooked", False):
                self.page_ready.connect(self._got_page, Qt.QueuedConnection)
                self._page_hooked = True
            threading.Thread(target=lambda pp=path: self.page_ready.emit(pp, document_page_image(pp, 1400)),
                             daemon=True).start()
        elif not path and not link:                   # an empty float: drop a file, paste a link, or pick a saved one
            self.kind = "empty"
            self.aspect = 16 / 9
            self.src = QPixmap(2, 2)
            self.src.fill(Qt.transparent)
        elif link and link.get("pending"):           # reopening: the window shows now, the video when it's fetched
            self.kind = "video"
            self.aspect = 16 / 9
            self.src = QPixmap(2, 2)
            self.src.fill(QColor(0, 0, 0))
            self._busy, self._spin = True, 0.0
            self._pending_timer = QTimer(self, interval=40, timeout=self._pending_tick)
            self._pending_timer.start()
        elif cat in ("video", "audio") and self._start_player(cat):
            self.kind = cat
            if cat == "video":
                self.aspect = 16 / 9
            else:
                self._set_cover(engine.cover_art(path))
        if self.src is None:
            from PySide6.QtCore import QFileInfo
            from PySide6.QtWidgets import QFileIconProvider
            self.src = QFileIconProvider().icon(QFileInfo(path)).pixmap(256, 256)
        if self.kind == "image":
            w = 300 if self.aspect >= 1 else int(300 * self.aspect)
        elif self.kind == "video":
            w = 420
        elif self.art:
            w = 280
        elif self.kind == "empty":
            w = 360
        else:
            w = 200
        if self.isVisible() and self.kind == prev_kind and self.kind != "other":
            w = prev_w                                   # next/previous keeps the size you chose
        tl = self.pos() if self.isVisible() else None
        self._apply_size(w, self._height_for(w))
        if tl is not None:
            self.move(tl)                                # stay exactly where it is
        self._pin_changed()
        self.setToolTip(f"{link['page'] if link else path}\n" + tr("Drag to move · drag ⠿ to drop the file · double-click to open · scroll to resize"))
        self.update()

    def display_name(self):
        return self.link["title"] if self.link else Path(self.path).name

    def _got_page(self, path, img):
        if path != self.path or self.link or img is None or img.isNull():
            return
        self.src = QPixmap.fromImage(img)
        self.kind = "image"
        self.aspect = img.width() / max(1, img.height())
        self._scaled = None
        w = 300 if self.aspect >= 1 else max(self.MIN_W, int(400 * self.aspect))
        tl = self.pos() if self.isVisible() else None
        self._apply_size(w, self._height_for(w))
        if tl is not None:
            self.move(tl)
        self.update()

    def _open_original(self):
        QDesktopServices.openUrl(QUrl(self.link["page"]) if self.link else QUrl.fromLocalFile(self.path))

    def _set_cover(self, data):
        """Use an album cover (PNG bytes or QImage) as the picture of an audio float."""
        img = QImage.fromData(data) if isinstance(data, (bytes, bytearray)) else data
        if img is None or img.isNull():
            return
        self.src = QPixmap.fromImage(img)
        self.art = True
        self.aspect = img.width() / max(1, img.height())
        self._scaled = None

    def _on_metadata(self):
        if self.kind != "audio" or self.art or not self.player:
            return
        from PySide6.QtMultimedia import QMediaMetaData
        md = self.player.metaData()
        for key in (QMediaMetaData.CoverArtImage, QMediaMetaData.ThumbnailImage):
            img = md.value(key)
            if isinstance(img, QImage) and not img.isNull():
                self._set_cover(img)
                tl = self.pos()
                self._apply_size(self.width() if self.width() > 200 else 280, self._height_for(280))
                self.move(tl)
                return

    # ---------------------------------------------------------------- drop to replace
    def _dropped_path(self, md):
        if not md.hasUrls():
            return None
        files = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        return files[0] if files and os.path.exists(files[0]) and files[0] != self.path else None

    def dragEnterEvent(self, e):
        if self._dropped_path(e.mimeData()):
            e.acceptProposedAction()
            self._drop_hover = True
            self.update()

    def dragLeaveEvent(self, e):
        self._drop_hover = False
        self.update()

    def dropEvent(self, e):
        self._drop_hover = False
        path = self._dropped_path(e.mimeData())
        if path:
            e.acceptProposedAction()
            self._load(path)
            self._fade_to(1.0)
            QTimer.singleShot(1600, self._maybe_hide_controls)

    # ---------------------------------------------------------------- media
    def _start_player(self, cat):
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
        except Exception as e:                      # build without Qt Multimedia
            winsys.log(f"float: no multimedia ({e})")
            return False
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        try:
            self.audio.setVolume(float(settings().value("float_volume", 1.0)))
        except (TypeError, ValueError):
            pass
        self.player.setAudioOutput(self.audio)
        self.autoplay = settings().value("float_autoplay", "true") == "true" or getattr(self, "_play_now", False)
        self._play_now = False
        self.subs = None             # external subtitles: list of (start ms, end ms, text)
        self.sub_text = ""           # built-in subtitle line currently shown
        if cat == "video":
            self.sink = QVideoSink(self)
            self.player.setVideoSink(self.sink)
            self.sink.videoFrameChanged.connect(self._on_frame)
            self.sink.subtitleTextChanged.connect(self._on_subtitle)
            self._first_frame = True
            if not self.autoplay:
                # play until the first frame arrives (silently), then pause on it
                self.audio.setMuted(True)
        self.player.positionChanged.connect(lambda _p: self.update())
        # loading circle while the video waits for data (like YouTube's)
        if getattr(self, "_busy_timer", None) is not None:
            self._busy_timer.stop()
            self._busy_timer.deleteLater()
        self._busy = False
        self._spin = 0.0
        self._pos_seen = (-1, 0.0)
        self._busy_timer = QTimer(self, interval=40, timeout=self._check_busy)
        self._busy_timer.start()
        self.player.durationChanged.connect(lambda _d: self.update())
        self.player.playbackStateChanged.connect(lambda _s: self.update())
        self.player.errorOccurred.connect(self._on_media_error)
        if cat == "audio":
            self.player.metaDataChanged.connect(self._on_metadata)
        self.player.mediaStatusChanged.connect(self._on_status)
        if self.link and self.link.get("audio"):
            self._add_companion(self.link["audio"])
        if self.link and not self._live() and _cacheable(self.path):
            self.player.setSource(QUrl(self._cached(self.path, self.link.get("size"))))
        elif self._live():
            self._start_relay()
            self.player.mediaStatusChanged.connect(lambda st: winsys.log(f"float: live status {st.name}"))
            self.player.setSource(QUrl(self._relay.url))
            QTimer.singleShot(20000, self._prefetch_live)
        else:
            self.player.setSource(QUrl(self.path) if self.link else QUrl.fromLocalFile(self.path))
        if cat == "video" or self.autoplay:
            self.player.play()
        if cat == "video" and not self.link:
            side = _find_side_subtitles(self.path)
            if side:
                self._load_subs(side[0])
        return True

    # ---- separate sound stream (some YouTube videos only come as picture + sound apart)
    def _add_companion(self, audio_url):
        from PySide6.QtMultimedia import QMediaPlayer
        self.player.setAudioOutput(None)                    # the picture stream is silent anyway
        self.companion = QMediaPlayer(self)
        self.companion.setAudioOutput(self.audio)           # volume slider and mute keep working
        self.companion.setSource(QUrl(self._cached(audio_url, (self.link or {}).get("audio_size"))
                                      if _cacheable(audio_url) else audio_url))
        self.player.playbackStateChanged.connect(self._sync_companion_state)
        self.player.positionChanged.connect(self._sync_companion_pos)

    def _drop_companion(self):
        c = getattr(self, "companion", None)
        if c is not None:
            c.stop()
            c.setSource(QUrl())
            c.deleteLater()
            self.companion = None

    def _sync_companion_state(self, state):
        from PySide6.QtMultimedia import QMediaPlayer
        c = getattr(self, "companion", None)
        if c is None:
            return
        if state == QMediaPlayer.PlayingState:
            c.setPosition(self.player.position())
            c.play()
        elif state == QMediaPlayer.PausedState:
            c.pause()
        else:
            c.stop()

    def _sync_companion_pos(self, ms):
        c = getattr(self, "companion", None)
        if c is not None and abs(c.position() - ms) > 350:     # seeked, or drifted
            c.setPosition(ms)

    # ---- previous / next file in the same folder
    def _siblings(self):
        import re
        if self.link:
            return []
        cat = engine.EXT_CATEGORY.get(engine.ext_of(self.path))
        here = Path(self.path)
        try:
            files = [str(f) for f in here.parent.iterdir()
                     if f.is_file() and engine.EXT_CATEGORY.get(engine.ext_of(str(f))) == cat]
        except OSError:
            return []
        natural = lambda t: [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", Path(t).name)]
        return sorted(files, key=natural)

    def _neighbour(self, step):
        files = self._siblings()
        try:
            i = [os.path.normcase(f) for f in files].index(os.path.normcase(self.path))
        except ValueError:
            return None
        j = i + step
        return files[j] if 0 <= j < len(files) else None

    def _step(self, step):
        nxt = self._neighbour(step)
        if nxt:
            self._play_now = True
            self._load(nxt)
        return bool(nxt)

    def _check_busy(self):
        import time
        from PySide6.QtMultimedia import QMediaPlayer
        if self.player is None:
            return
        st = self.player.mediaStatus()
        now = time.monotonic()
        pos = self.player.position()
        if pos != self._pos_seen[0]:
            self._pos_seen = (pos, now)
        playing = self.player.playbackState() == QMediaPlayer.PlayingState
        busy = st in (QMediaPlayer.LoadingMedia, QMediaPlayer.StalledMedia) and (playing or self.link is not None)
        if not busy and self.link and playing and self.kind == "video":       # stream stuck waiting for data
            busy = now - self._pos_seen[1] > 0.9
        if self.kind == "video" and self.frame is None and (playing or self.link):
            busy = True                                                     # nothing to show yet
        if busy and not self._busy:
            self._busy_since = now
        relay = getattr(self, "_relay", None)
        if busy and self._live() and relay is not None and now - relay.last_data > 6 \
                and now - getattr(self, "_last_refresh", 0) > 20 and now - getattr(self, "_live_fixing", 0) > 6:
            winsys.log("float: live relay got nothing for 6 s")
            self._last_refresh = now
            self._live_continue(error=True) if getattr(self, "_spare", None) else self.refresh_link(auto=True)
        if busy and self.link and now - getattr(self, "_busy_since", now) > 15 \
                and now - getattr(self, "_last_refresh", 0) > 45 and now - getattr(self, "_live_fixing", 0) > 25:
            self.refresh_link(auto=True)                      # stuck: fetch a fresh link by itself
        if busy or busy != self._busy:
            self._spin = (self._spin + 12) % 360
            self._busy = busy
            self.update()

    def _pending_tick(self):
        if not (self.link or {}).get("pending"):
            self._pending_timer.stop()
            return
        self._spin = (self._spin + 12) % 360
        self.update()

    def _paint_busy(self, p):
        c = QPointF(self.width() / 2, self.height() / 2)
        rad = max(14.0, min(self.width(), self.height()) * 0.09)
        p.save()
        p.setOpacity(1.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawEllipse(c, rad + 10, rad + 10)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 60), max(3.0, rad / 5), Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(c, rad, rad)
        p.setPen(QPen(QColor(255, 255, 255, 235), max(3.0, rad / 5), Qt.SolidLine, Qt.RoundCap))
        box = QRectF(c.x() - rad, c.y() - rad, rad * 2, rad * 2)
        p.drawArc(box, int(-self._spin * 16), int(-100 * 16))
        p.restore()

    def _on_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.LoadedMedia and self._resume_ms and self.autoplay:
            self.player.setPosition(self._resume_ms)
            self._resume_ms = 0
        if status == QMediaPlayer.EndOfMedia and self._live():
            import time
            if time.monotonic() - getattr(self, "_live_fixing", 0) >= 8:
                QTimer.singleShot(50, self._live_continue)
            return
        if status == QMediaPlayer.EndOfMedia and self.repeat == "one":
            self.player.setPosition(0)                       # repeat this one
            self.player.play()
            return
        if status == QMediaPlayer.EndOfMedia and (self.repeat == "all" or settings().value("float_autoplay", "true") == "true"):
            if self._neighbour(1):
                QTimer.singleShot(300, lambda: self._step(1))
            elif self.repeat == "all":                       # end of the folder: back to the first one
                files = self._siblings() if not self.link else []
                if len(files) > 1:
                    QTimer.singleShot(300, lambda f=files[0]: (setattr(self, "_play_now", True), self._load(f)))
                else:
                    self.player.setPosition(0)
                    self.player.play()

    def set_repeat(self, mode):
        self.repeat = mode
        settings().setValue("float_repeat", mode)
        self.update()

    def _on_frame(self, frame):
        img = frame.toImage()
        if img.isNull():
            return
        self.frame = img
        if getattr(self, "_first_frame", False):
            self._first_frame = False
            if not self.autoplay:
                self.player.pause()
                self.player.setPosition(self._resume_ms or 0)
                self._resume_ms = 0
                self.audio.setMuted(False)
            a = img.width() / max(1, img.height())
            if abs(a - (self.aspect or 0)) > 0.01:
                self.aspect = a
                tl = self.pos()
                self._apply_size(self.width(), self._height_for(self.width()))
                self.move(tl)
        self.update()

    def _on_subtitle(self, text):
        self.sub_text = text or ""
        self.update()

    def _load_subs(self, path):
        try:
            self.subs = _parse_subtitles(path)
            self.subs_path = path
            self.player.setActiveSubtitleTrack(-1)        # one subtitle source at a time
        except Exception as e:
            winsys.log(f"float: cannot read subtitles {path}: {e}")
            self.subs = None
        self.update()

    def _current_subtitle(self):
        if self.subs:
            pos = self.player.position()
            return "\n".join(t for a, b, t in self.subs if a <= pos <= b)
        return self.sub_text

    @staticmethod
    def _track_name(md, i):
        from PySide6.QtCore import QLocale
        from PySide6.QtMultimedia import QMediaMetaData
        parts = []
        lang = md.value(QMediaMetaData.Language)
        try:
            if lang is not None and lang != QLocale.AnyLanguage:
                parts.append(QLocale.languageToString(lang))
        except Exception:
            pass
        title = md.stringValue(QMediaMetaData.Title)
        if title and title not in parts:
            parts.append(title)
        return " · ".join(parts) or tr("Track {n}", n=i + 1)

    def _add_track_menus(self, m):
        from PySide6.QtGui import QActionGroup
        audio = self.player.audioTracks()
        am = m.addMenu(tr("Audio track"))
        grp = QActionGroup(am)
        for i, md in enumerate(audio):
            a = am.addAction(self._track_name(md, i))
            a.setCheckable(True)
            a.setChecked(i == self.player.activeAudioTrack() or (len(audio) == 1))
            a.triggered.connect(lambda _c=False, i=i: self.player.setActiveAudioTrack(i))
            grp.addAction(a)
        if not audio:
            am.setEnabled(False)
        sm = m.addMenu(tr("Subtitles"))
        grp2 = QActionGroup(sm)
        off = sm.addAction(tr("Off"))
        off.setCheckable(True)
        off.setChecked(not self.subs and self.player.activeSubtitleTrack() < 0)
        off.triggered.connect(self._subs_off)
        grp2.addAction(off)
        for i, md in enumerate(self.player.subtitleTracks()):
            a = sm.addAction(self._track_name(md, i))
            a.setCheckable(True)
            a.setChecked(not self.subs and i == self.player.activeSubtitleTrack())
            a.triggered.connect(lambda _c=False, i=i: self._subs_track(i))
            grp2.addAction(a)
        for f in ([] if self.link else _find_side_subtitles(self.path)):
            a = sm.addAction(Path(f).name)
            a.setCheckable(True)
            a.setChecked(bool(self.subs) and getattr(self, "subs_path", "") == f)
            a.triggered.connect(lambda _c=False, f=f: self._load_subs(f))
            grp2.addAction(a)
        sm.addSeparator()
        sm.addAction(tr("Browse…"), self._browse_subs)

    def _subs_off(self):
        self.subs = None
        self.player.setActiveSubtitleTrack(-1)
        self.sub_text = ""
        self.update()

    def _subs_track(self, i):
        self.subs = None
        self.player.setActiveSubtitleTrack(i)
        self.update()

    def _browse_subs(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("Subtitles"), str(Path.home() if self.link else Path(self.path).parent),
                                           "Subtitles (*.srt *.vtt)")
        if f:
            self._load_subs(f)

    # ---- live streams: the player only gets the newest ~30 s at a time, so keep loading the next part
    def _live(self):
        return bool(self.link and self.link.get("live"))

    def _start_relay(self):
        self._stop_relay()
        try:
            self._relay = LiveRelay(self.path, (self.link or {}).get("headers"))
        except Exception as e:
            winsys.log(f"live relay failed: {e}")
            self._relay = None

    def _stop_relay(self):
        r = getattr(self, "_relay", None)
        if r is not None:
            r.close()
            self._relay = None
        for c in getattr(self, "_caches", []):
            threading.Thread(target=c.close, daemon=True).start()
        self._caches = []

    def _cached(self, url, size=None):
        """Local address of the download-ahead copy of `url` (or the url itself if that can't be set up)."""
        try:
            c = StreamCache(url, (self.link or {}).get("headers"), size)
        except Exception as e:
            winsys.log(f"stream cache not used: {e}")
            return url
        self._caches = getattr(self, "_caches", []) + [c]
        return c.local

    def restart_live(self, info):
        """The link was renewed: keep the float as it is (size, place, volume) and carry on playing —
        live streams through a fresh relay, other videos from where they were."""
        if self.player is None or info.get("audio") or self.companion is not None:
            keep = getattr(self, "_resume_ms", 0)
            pos = 0 if info.get("live") else (self.player.position() if self.player is not None else keep)
            self._play_now = True
            self._load(info["url"], info)                # picture and sound apart: set both up again
            self._resume_ms = pos
            return
        pos = 0 if info.get("live") else self.player.position()
        self.link = info
        self.path = info["url"]
        self._pos_seen = (-1, 0.0)
        if info.get("live"):
            self._start_relay()
            if self._relay is not None:
                self.player.setSource(QUrl(self._relay.url))
            QTimer.singleShot(20000, self._prefetch_live)
        else:
            self._stop_relay()
            self._resume_ms = pos
            self.autoplay = True
            self.player.setSource(QUrl(self._cached(info["url"], info.get("size")) if _cacheable(info["url"]) else info["url"]))
        self.player.play()

    def _set_quality(self, q):
        settings().setValue("link_quality", q)
        self.refresh_link(quality=q)

    def refresh_link(self, auto=False, quality=None):
        """Ask the site again for the video (its links expire) and continue."""
        if not self.link or _APP is None:
            return
        import time
        self._last_refresh = time.monotonic()
        winsys.log(f"float: refresh link ({'automatic, stuck loading' if auto else 'from the menu'})")
        self._live_fixing = time.monotonic()
        _APP._resolve_and_play(self.link["page"], self, quiet=True, quality=quality)

    def _prefetch_live(self):
        """Fetch a fresh stream link in the background while this one still plays, so a failure is fixed in
        seconds instead of waiting for YouTube."""
        if not self._live() or _APP is None or self.player is None:
            return
        job = LinkResolve(self.link["page"])
        job.setAutoDelete(False)
        _APP._update_jobs.add(job)

        def got(info, err, job=job):
            _APP._update_jobs.discard(job)
            if info and info.get("live"):
                self._spare = (time.monotonic(), info)
        job.sig.done.connect(got, Qt.QueuedConnection)
        _APP.pool.start(job)

    def _live_continue(self, error=False):
        import time
        now = time.monotonic()
        recent = [t for t in getattr(self, "_live_reloads", []) if now - t < 60] + [now]
        self._live_reloads = recent
        spare = getattr(self, "_spare", None)
        if spare and spare[1].get("client") in engine.LIVE_BAD_CLIENTS:
            spare = self._spare = None                   # made for a player YouTube now refuses
        relay = getattr(self, "_relay", None)
        if relay is not None and relay.forbidden and not spare and _APP is not None:
            winsys.log("float: live stream re-opened with another player")
            relay.forbidden = False
            self._live_reloads = []
            _APP._resolve_and_play(self.link["page"], self, quiet=True)
            return
        if spare and now - spare[0] < 90:                 # a fresh link is ready: switch to it right away
            self._spare = None
            winsys.log("float: live stream switched to the fresh link")
            self.restart_live(spare[1])
            return
        # a hiccup: just restart the local relay (2-3 s). Several in a minute: the link has expired, ask YouTube again
        if len(recent) > 3:
            self._live_reloads = []
            if _APP is not None:
                winsys.log(f"float: live stream re-opened ({'error' if error else 'stalled'})")
                _APP._resolve_and_play(self.link["page"], self, quiet=True)
            return
        relay = getattr(self, "_relay", None)
        self.player.setSource(QUrl(relay.url if relay is not None else self.path))   # ffmpeg starts again
        self.player.play()

    def _on_media_error(self, *_a):
        if self._live() and self.player is not None:
            import time
            if time.monotonic() - getattr(self, "_live_fixing", 0) < 8:      # one reconnect at a time
                return
            self._live_fixing = time.monotonic()
            winsys.log(f"float: live stream error, reconnecting: {self.player.errorString()}")
            QTimer.singleShot(300, self._live_continue)
            return
        winsys.log(f"float: cannot play {self.path}: {self.player.errorString()}")
        self.player.stop()
        self.player = None
        self.kind = "other"
        self.art = False
        self.aspect = None
        self.frame = None
        self._apply_size(200, 200)

    def _playing(self):
        from PySide6.QtMultimedia import QMediaPlayer
        return self.player is not None and self.player.playbackState() == QMediaPlayer.PlayingState

    def media_key(self, key):
        """Play/pause, next, previous, stop from the keyboard's media keys."""
        if not self.player:
            return None
        if key == "play":
            self._toggle_play()
            return "pause" if not self._playing() else "play"
        if key == "stop":
            self.player.pause()
            self.player.setPosition(0)
            return "stop"
        return key if self._step(1 if key == "next" else -1) else None

    def _toggle_play(self):
        if not self.player:
            return
        if self._playing():
            self.player.pause()
        else:
            if self.player.duration() and self.player.position() >= self.player.duration() - 200:
                self.player.setPosition(0)
            self.player.play()

    # ---------------------------------------------------------------- geometry
    def _height_for(self, w):
        if self.aspect:
            return int(round(w / self.aspect))
        return w if self.kind == "other" else 150      # audio: a short card

    def _apply_size(self, w, h):
        scr = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        w = max(self.MIN_W, min(int(w), scr.width()))
        h = max(110, min(int(h), scr.height()))
        if self.aspect:                                   # keep the shape when a limit kicked in
            if w / h > self.aspect + 0.01:
                w = max(self.MIN_W, int(h * self.aspect))
            else:
                h = max(110, int(w / self.aspect))
        self.resize(w, h)
        self._scaled = None
        self.update()

    def _close_center(self):
        return QPointF(self.width() - 20, 20)

    def _band_h(self):
        return 62 if self.player else 40

    def _grip_rect(self):
        return QRectF(self.width() - 42, self.height() - 36, 30, 26)

    def _seek_rect(self):
        return QRectF(14, self.height() - 52, self.width() - 28, 4)

    def _vol_rect(self):
        return QRectF(44, self.height() - 27, 74, 6)

    def _set_volume_x(self, x):
        r = self._vol_rect()
        v = min(1.0, max(0.0, (x - r.left()) / r.width()))
        self.audio.setVolume(v)
        self.audio.setMuted(False)
        settings().setValue("float_volume", round(v, 3))
        self.update()

    def _mute_rect(self):
        return QRectF(10, self.height() - 38, 28, 28)

    def _play_center(self):
        if self.kind == "audio" and not self.art:
            return QPointF(self.width() / 2, (self.height() - self._band_h()) / 2 + 8)
        return QPointF(self.width() / 2, self.height() / 2 - 8)

    def _icon_rect(self):
        side = min(self.width(), self.height() - self._band_h()) * 0.55
        side = max(48, min(side, 256))
        cx, cy = self.width() / 2, (self.height() - self._band_h()) / 2 + 6
        return QRectF(cx - side / 2, cy - side / 2, side, side)

    def _edges(self, pos):
        e, c = self.EDGE, 18                                 # edge band, corner grab area
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        l, t, r, b = x < e, y < e, x > w - e, y > h - e
        if (x < c or x > w - c) and (y < c or y > h - c) and (l or t or r or b):
            l, r, t, b = x < c, x > w - c, y < c, y > h - c    # near a corner: grab the corner
        return (l, t, r, b)                                   # left, top, right, bottom

    def _hit(self, pos):
        c = self._close_center()
        controls = self.ctrl > 0.4
        if controls and (pos.x() - c.x()) ** 2 + (pos.y() - c.y()) ** 2 <= (self.CLOSE_R + 4) ** 2:
            return "close"
        if controls and self._grip_rect().contains(pos):
            return "grip"
        if any(self._edges(pos)):
            return "edge"
        if self.player and controls:
            if self._seek_rect().adjusted(0, -8, 0, 8).contains(pos) and not self._live():
                return "seek"
            if self._mute_rect().contains(pos):
                return "mute"
            if self._vol_open and QRectF(38, self.height() - 38, 88, 28).contains(pos):
                return "vol"
            pc = self._play_center()
            if (pos.x() - pc.x()) ** 2 + (pos.y() - pc.y()) ** 2 <= 30 ** 2:
                return "play"
            for name, dx in (("prev", -62), ("next", 62)):
                if (pos.x() - pc.x() - dx) ** 2 + (pos.y() - pc.y()) ** 2 <= 22 ** 2:
                    return name
        if self.kind == "other" and self._icon_rect().contains(pos):
            return "icon"
        return "body"

    # ---------------------------------------------------------------- fading controls
    def set_on_top(self, on):
        self.on_top = bool(on)
        geo = self.geometry()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.on_top)
        self.setGeometry(geo)
        self.show()
        self._pin_changed()

    # ---------------------------------------------------------------- reopen when Windows starts
    def set_pinned(self, on):
        pins = [x for x in _float_pins() if x.get("id") != self.pin_id]
        if on:
            import uuid
            self.pin_id = self.pin_id or uuid.uuid4().hex[:12]
            _save_float_pins(pins)
            self._save_pin()
            if not winsys.startup_enabled():          # DragWheel itself has to start with Windows
                try:
                    winsys.set_startup(True)
                except Exception as e:
                    winsys.log(f"startup: {e}")
        else:
            self.pin_id = None
            _save_float_pins(pins)

    def _pin_changed(self):
        if getattr(self, "pin_id", None):
            self._pin_timer.start()

    def state(self) -> dict:
        """Everything needed to bring this float back: file or link, place, size, playback."""
        g = self.geometry()
        st = {"id": self.pin_id, "src": self.link["page"] if self.link else str(self.path), "link": bool(self.link),
              "title": (self.link or {}).get("title", ""),
              "x": g.x(), "y": g.y(), "w": g.width(), "on_top": self.on_top}
        if self.player is not None and not self._live():
            st["pos"] = int(self.player.position())
            st["playing"] = bool(self._playing())
        return st

    def _save_pin(self):
        if not self.pin_id:
            return
        entry = self.state()
        entry.pop("pos", None)
        entry.pop("playing", None)
        pins = [x for x in _float_pins() if x.get("id") != self.pin_id] + [entry]
        _save_float_pins(pins)

    def moveEvent(self, e):
        super().moveEvent(e)
        self._pin_changed()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._pin_changed()

    def close_by_user(self):
        """Closed with ✕, Esc or the menu: it no longer reopens with Windows."""
        if self.pin_id:
            self.set_pinned(False)
        self.close()

    def _set_ctrl(self, v):
        self.ctrl = float(v)
        self.update()

    def _fade_to(self, target):
        if abs(self.ctrl - target) < 0.01 and self._fade.state() != QVariantAnimation.Running:
            return
        self._fade.stop()
        self._fade.setStartValue(self.ctrl)
        self._fade.setEndValue(float(target))
        self._fade.start()

    def _maybe_hide_controls(self):
        if not self.underMouse() and self._press is None:
            self._fade_to(0.0)

    def enterEvent(self, e):
        self._fade_to(1.0)

    def leaveEvent(self, e):
        self.hover = None
        self._vol_open = False
        if self._press is None:
            self._fade_to(0.0)
        self.update()

    # ---------------------------------------------------------------- paint
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(r, self.RADIUS, self.RADIUS)
        p.setClipPath(clip)
        p.fillRect(r, QColor(0, 0, 0) if self.kind == "video" else C("panel"))
        media = self.kind in ("image", "video") or self.art
        if self.kind == "image" or self.art:
            if self._scaled is None or self._scaled.size() != self.size():
                self._scaled = self.src.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(0, 0, self._scaled)
        elif self.kind == "video":
            if self.frame is not None:
                fr = QSizeF(self.frame.size()).scaled(QSizeF(self.size()), Qt.KeepAspectRatio)
                p.drawImage(QRectF((self.width() - fr.width()) / 2, (self.height() - fr.height()) / 2,
                                   fr.width(), fr.height()), self.frame)
        elif self.kind == "empty":
            box = r.adjusted(10, 10, -10, -10)
            pen = QPen(ACCENT if self._drop_hover else C("line"), 1.6, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(box, 10, 10)
            p.setPen(C("text"))
            p.setFont(QFont(i18n.ui_font(), 11, QFont.DemiBold))
            p.drawText(box.adjusted(12, 0, -12, -box.height() / 2 + 6), Qt.AlignHCenter | Qt.AlignBottom, tr("Drop a file here"))
            p.setPen(C("dim"))
            p.setFont(QFont(i18n.ui_font(), 9))
            p.drawText(box.adjusted(14, box.height() / 2 + 8, -14, -8), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                       tr("or press Ctrl+V to play a copied link · right-click for saved links"))
        else:                                               # icon, centred; highlights on hover
            ir = self._icon_rect()
            if self.hover == "icon":
                hl = QColor(ACCENT)
                hl.setAlpha(46)
                p.setPen(QPen(ACCENT, 1.5))
                p.setBrush(hl)
                p.drawRoundedRect(ir.adjusted(-12, -12, 12, 12), 16, 16)
            p.drawPixmap(ir.toRect(), self.src.scaled(int(ir.width()), int(ir.height()),
                                                       Qt.KeepAspectRatio, Qt.SmoothTransformation))
        # ---- subtitles (above the controls when they are showing)
        if self.kind == "video" and self.player:
            text = self._current_subtitle()
            if text:
                self._paint_subtitle(p, text)
        if getattr(self, "_busy", False) and self.kind == "video" and (self.player is not None or (self.link or {}).get("pending")):
            self._paint_busy(p)
        # ---- overlay controls (fade with the cursor)
        if self.ctrl > 0.01:
            p.setOpacity(self.ctrl)
            band = self._band_h()
            if media:
                g = QLinearGradient(0, self.height() - band - 30, 0, self.height())
                g.setColorAt(0, QColor(0, 0, 0, 0))
                g.setColorAt(1, QColor(0, 0, 0, 175))
                p.fillRect(QRectF(0, self.height() - band - 30, self.width(), band + 30), g)
            fg = QColor("#ffffff") if media else C("text")
            f = QFont(i18n.ui_font(), 9)
            p.setFont(f)
            left = 14
            if self.player:
                self._paint_player(p, fg)
                left = 44
                if self._vol_open:                         # volume slider next to the speaker
                    vr = self._vol_rect()
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(255, 255, 255, 70) if (self.kind == "video" or self.art) else C("busy_track"))
                    p.drawRoundedRect(vr, 3, 3)
                    vol = 0.0 if self.audio.isMuted() else self.audio.volume()
                    p.setBrush(ACCENT)
                    p.drawRoundedRect(QRectF(vr.left(), vr.top(), vr.width() * vol, vr.height()), 3, 3)
                    p.drawEllipse(QPointF(vr.left() + vr.width() * vol, vr.center().y()), 6, 6)
                    left = 130
                t = ("● " + tr("LIVE")) if self._live() else f"{_fmt_time(self.player.position())} / {_fmt_time(self.player.duration())}"
                if not self._live() and self.repeat in ("one", "all"):
                    t += "   ↻" + ("1" if self.repeat == "one" or self.link else "")
                p.setPen(fg)
                tw = QFontMetrics(f).horizontalAdvance(t) + 12
                p.drawText(QRectF(left, self.height() - 38, tw, 28), Qt.AlignVCenter | Qt.AlignLeft, t)
                left += tw
            name_r = QRectF(left, self.height() - 38, self._grip_rect().left() - left - 6, 28)
            p.setPen(fg)
            p.drawText(name_r, Qt.AlignVCenter | Qt.AlignLeft,
                       QFontMetrics(f).elidedText(self.display_name(), Qt.ElideMiddle, int(max(0, name_r.width()))))
            gr = self._grip_rect()
            p.setPen(Qt.NoPen)
            p.setBrush(ACCENT if self.hover == "grip" else (QColor(255, 255, 255, 46) if media else C("grip")))
            p.drawRoundedRect(gr, 7, 7)
            p.setBrush(ON_ACCENT if self.hover == "grip" else fg)
            for i in range(3):
                for j in range(2):
                    p.drawEllipse(QPointF(gr.center().x() - 3 + j * 6, gr.center().y() - 5 + i * 5), 1.6, 1.6)
            c = self._close_center()
            p.setBrush(C("danger") if self.hover == "close" else QColor(20, 20, 22, 190))
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
            p.drawEllipse(c, self.CLOSE_R, self.CLOSE_R)
            pen = QPen(QColor("#ffffff"), 2)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            d = 4.2
            p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
            p.drawLine(QPointF(c.x() + d, c.y() - d), QPointF(c.x() - d, c.y() + d))
            p.setOpacity(1.0)
        # border
        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        if self._drop_hover:                                # a file is being dragged over: drop replaces
            p.setPen(QPen(ACCENT, 3))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), self.RADIUS, self.RADIUS)
        else:
            p.setPen(QPen(ACCENT if (self.hover and self.hover != "icon") else C("line"), 1.2))
            p.drawRoundedRect(r, self.RADIUS, self.RADIUS)

    def _paint_subtitle(self, p, text):
        size = max(10, min(22, self.height() / 18))
        f = QFont(i18n.ui_font(), 1)
        f.setPointSizeF(size)
        f.setWeight(QFont.DemiBold)
        fm = QFontMetrics(f)
        bottom = self.height() - (self._band_h() + 8) * self.ctrl - 12
        width = self.width() - 32
        rect = fm.boundingRect(QRect(0, 0, int(width), 1000), Qt.AlignHCenter | Qt.TextWordWrap, text)
        box = QRectF((self.width() - rect.width()) / 2 - 8, bottom - rect.height() - 4, rect.width() + 16, rect.height() + 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(box, 6, 6)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(box, Qt.AlignCenter | Qt.TextWordWrap, text)

    def _paint_player(self, p, fg):
        # big play / pause in the middle (hidden while the loading circle shows, like YouTube)
        pc = self._play_center()
        p.setPen(Qt.NoPen)
        if getattr(self, "_busy", False) and self.kind == "video":
            p.setOpacity(0.0)
        p.setBrush(ACCENT if self.hover == "play" else QColor(20, 20, 22, 170))
        p.drawEllipse(pc, 26, 26)
        p.setBrush(ON_ACCENT if self.hover == "play" else QColor("#ffffff"))
        if self._playing():
            p.drawRoundedRect(QRectF(pc.x() - 8, pc.y() - 10, 6, 20), 2, 2)
            p.drawRoundedRect(QRectF(pc.x() + 2, pc.y() - 10, 6, 20), 2, 2)
        else:
            tri = QPolygonF([QPointF(pc.x() - 7, pc.y() - 11), QPointF(pc.x() - 7, pc.y() + 11), QPointF(pc.x() + 11, pc.y())])
            p.drawPolygon(tri)
        # previous / next in the folder (dimmed at the ends)
        for name, dx, d in (("prev", -62, -1), ("next", 62, 1)):
            c = QPointF(pc.x() + dx, pc.y())
            have = self._neighbour(d) is not None
            p.setOpacity(0.0 if (getattr(self, "_busy", False) and self.kind == "video") else self.ctrl * (1.0 if have else 0.35))
            p.setBrush(ACCENT if (self.hover == name and have) else QColor(20, 20, 22, 150))
            p.drawEllipse(c, 18, 18)
            p.setBrush(ON_ACCENT if (self.hover == name and have) else QColor("#ffffff"))
            sgn = 1 if d > 0 else -1
            p.drawPolygon(QPolygonF([QPointF(c.x() - 5 * sgn, c.y() - 7), QPointF(c.x() - 5 * sgn, c.y() + 7),
                                     QPointF(c.x() + 4 * sgn, c.y())]))
            p.drawRect(QRectF(c.x() + 4 * sgn - (2 if sgn > 0 else 0), c.y() - 7, 2, 14))
        p.setOpacity(self.ctrl)
        # seek bar
        sr = self._seek_rect()
        p.setBrush(QColor(255, 255, 255, 70) if (self.kind == "video" or self.art) else C("busy_track"))
        p.drawRoundedRect(sr, 2, 2)
        dur = self.player.duration()
        if dur > 0 and not self._live():
            frac = min(1.0, self.player.position() / dur)
            p.setBrush(ACCENT)
            p.drawRoundedRect(QRectF(sr.left(), sr.top(), sr.width() * frac, sr.height()), 2, 2)
            p.drawEllipse(QPointF(sr.left() + sr.width() * frac, sr.center().y()), 6 if self.hover == "seek" else 4.5,
                          6 if self.hover == "seek" else 4.5)
        # speaker (click to mute)
        mr = self._mute_rect()
        cx, cy = mr.center().x(), mr.center().y()
        p.setBrush(ACCENT if self.hover == "mute" else fg)
        p.drawPolygon(QPolygonF([QPointF(cx - 8, cy - 3), QPointF(cx - 4, cy - 3), QPointF(cx + 1, cy - 8),
                                 QPointF(cx + 1, cy + 8), QPointF(cx - 4, cy + 3), QPointF(cx - 8, cy + 3)]))
        pen = QPen(ACCENT if self.hover == "mute" else fg, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if self.audio.isMuted():
            p.drawLine(QPointF(cx + 4, cy - 4), QPointF(cx + 10, cy + 4))
            p.drawLine(QPointF(cx + 10, cy - 4), QPointF(cx + 4, cy + 4))
        else:
            p.drawArc(QRectF(cx - 3, cy - 6, 10, 12), -50 * 16, 100 * 16)
            p.drawArc(QRectF(cx - 3, cy - 10, 16, 20), -50 * 16, 100 * 16)
        p.setPen(Qt.NoPen)

    # ---------------------------------------------------------------- mouse
    def _seek_to(self, x):
        sr = self._seek_rect()
        if self.player and self.player.duration() > 0:
            frac = min(1.0, max(0.0, (x - sr.left()) / max(1.0, sr.width())))
            self.player.setPosition(int(self.player.duration() * frac))

    last_used = None                 # the float the keyboard media keys control

    def mousePressEvent(self, e):
        FloatWindow.last_used = self
        if e.button() == Qt.RightButton:
            self._menu(e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        hit = self._hit(e.position())
        gp = e.globalPosition().toPoint()
        if hit == "close":
            self.close_by_user()
            return
        if hit == "mute":
            self.audio.setMuted(not self.audio.isMuted())
            self.update()
            return
        if hit == "vol":
            self._vol_drag = True
            self._set_volume_x(e.position().x())
            return
        if hit == "seek":
            self._seeking = True
            self._seek_to(e.position().x())
        if hit == "edge":
            self._press = ("edge", gp, e.position(), self.geometry(), self._edges(e.position()))
        else:
            self._press = (hit, gp, e.position(), self.geometry(), None)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._vol_drag:
            self._set_volume_x(pos.x())
            return
        if self._press is not None:
            kind, gp0, lp0, geo0, edges = self._press
            gp = e.globalPosition().toPoint()
            moved = (gp - gp0).manhattanLength()
            if self._seeking:
                self._seek_to(pos.x())
            elif kind == "grip":
                if moved > 6:
                    self._press = None
                    self._drag_out()
            elif kind == "edge":
                self._resize_drag(gp - gp0, geo0, edges)
            elif moved > 3 or kind == "moving":
                if kind != "moving":
                    self._press = ("moving", gp0, lp0, geo0, None)
                self.move(geo0.topLeft() + (gp - gp0))
            return
        h = self._hit(pos)
        vol_open = h in ("mute", "vol")
        if vol_open != self._vol_open:
            self._vol_open = vol_open
            h = self._hit(pos)
            self.update()
        if h != self.hover:
            self.hover = h
            if h == "edge":
                l, t, r, b = self._edges(pos)
                cur = (Qt.SizeFDiagCursor if (l and t) or (r and b) else Qt.SizeBDiagCursor if (r and t) or (l and b)
                       else Qt.SizeHorCursor if (l or r) else Qt.SizeVerCursor)
            else:
                cur = {"close": Qt.PointingHandCursor, "grip": Qt.OpenHandCursor, "icon": Qt.PointingHandCursor,
                       "play": Qt.PointingHandCursor, "prev": Qt.PointingHandCursor, "next": Qt.PointingHandCursor, "seek": Qt.PointingHandCursor, "mute": Qt.PointingHandCursor, "vol": Qt.PointingHandCursor
                       }.get(h, Qt.SizeAllCursor)
            self.setCursor(cur)
            self.update()

    def _resize_drag(self, delta, geo0, edges):
        l, t, r, b = edges
        x, y, w, h = geo0.x(), geo0.y(), geo0.width(), geo0.height()
        dw = (delta.x() if r else -delta.x() if l else 0)
        dh = (delta.y() if b else -delta.y() if t else 0)
        nw, nh = w + dw, h + dh
        if self.aspect:                       # keep the picture's shape
            if (l or r) and (t or b):         # corner: follow the mouse in any direction (project on the diagonal)
                k = (dw * self.aspect + dh) / (self.aspect ** 2 + 1)
                nw, nh = w + k * self.aspect, h + k
            elif l or r:
                nh = nw / self.aspect
            else:
                nw = nh * self.aspect
        self._apply_size(nw, nh)
        nw, nh = self.width(), self.height()
        nx = x + (w - nw) if l else x
        ny = y + (h - nh) if t else y
        if self.aspect and (t or b) and not (l or r):          # grow sideways around the centre
            nx = x + (w - nw) // 2
        if self.aspect and (l or r) and not (t or b):
            ny = y + (h - nh) // 2
        self.move(int(nx), int(ny))

    def mouseReleaseEvent(self, e):
        self._vol_drag = False
        press, self._press = self._press, None
        was_seeking, self._seeking = self._seeking, False
        if press is None or was_seeking or e.button() != Qt.LeftButton:
            return
        kind = press[0]
        if kind == "icon":
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))
        elif kind in ("prev", "next"):
            self._step(-1 if kind == "prev" else 1)
        elif kind == "play" or (kind == "body" and self.kind == "video"):
            self._toggle_play()
        if not self.underMouse():
            self._fade_to(0.0)

    def mouseDoubleClickEvent(self, e):
        if self._hit(e.position()) == "body" and self.kind == "image":
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))

    def wheelEvent(self, e):
        if self.player and self.hover in ("mute", "vol"):          # scroll over the speaker = volume
            v = min(1.0, max(0.0, self.audio.volume() + (0.05 if e.angleDelta().y() > 0 else -0.05)))
            self.audio.setVolume(v)
            self.audio.setMuted(False)
            settings().setValue("float_volume", round(v, 3))
            self.update()
            return
        step = 1.1 if e.angleDelta().y() > 0 else 1 / 1.1
        center = self.frameGeometry().center()
        self._apply_size(self.width() * step, (self._height_for(self.width() * step) if self.aspect
                                                else self.height() * step))
        self.move(center - QPoint(self.width() // 2, self.height() // 2))

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.Paste):
            if _APP is not None:
                _APP.play_link(target=self)
            return
        if e.key() == Qt.Key_Escape:
            self.close_by_user()
        elif e.key() == Qt.Key_Space and self.player:
            self._toggle_play()
        elif e.key() == Qt.Key_R and self.player:                             # R: repeat off → this one → all
            order = ["off", "one"] if self.link else ["off", "one", "all"]
            self.set_repeat(order[(order.index(self.repeat) + 1) % len(order)] if self.repeat in order else "off")
        elif e.key() in (Qt.Key_PageUp, Qt.Key_PageDown) and self.player:     # media keys: DragWheelApp._media_tick
            self._step(-1 if e.key() == Qt.Key_PageUp else 1)
        elif e.key() in (Qt.Key_Left, Qt.Key_Right) and self.player:
            self.player.setPosition(max(0, self.player.position() + (5000 if e.key() == Qt.Key_Right else -5000)))

    def _drag_out(self):
        md = QMimeData()
        md.setUrls([QUrl(self.link["page"]) if self.link else QUrl.fromLocalFile(self.path)])
        drag = QDrag(self)
        drag.setMimeData(md)
        thumb = QPixmap.fromImage(self.frame) if (self.kind == "video" and self.frame is not None) else self.src
        drag.setPixmap(thumb.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        drag.exec(Qt.CopyAction | Qt.MoveAction | Qt.LinkAction, Qt.CopyAction)

    def _menu(self, at):
        m = QMenu(self)
        if self.kind == "video" and self.player:
            self._add_track_menus(m)
        if self.player and not self._live():
            rm = m.addMenu(tr("Repeat"))
            for key, label in (("off", tr("Off")), ("one", tr("Repeat this one")),
                               ("all", tr("Loop all (the whole folder)") if not self.link else tr("Loop"))):
                if self.link and key == "all":
                    continue
                a = rm.addAction(label)
                a.setCheckable(True)
                a.setChecked(self.repeat == key or (self.link and key == "one" and self.repeat == "all"))
                a.triggered.connect(lambda _=False, k=key: self.set_repeat(k))
        if self.player:
            m.addSeparator()
        m.addAction(tr("Open"), self._open_original)
        if self.link:
            m.addAction(tr("Copy"), lambda: QGuiApplication.clipboard().setText(self.link["page"]))
        else:
            m.addAction(tr("Show in Explorer"), lambda: winsys.reveal(self.path))
            m.addAction(tr("Copy path"), lambda: QGuiApplication.clipboard().setText(str(Path(self.path))))
        if self.link:
            m.addAction(tr("Refresh"), self.refresh_link)
            qm = m.addMenu(tr("Quality"))
            cur = settings().value("link_quality", "1080p")
            for q in engine.LINK_QUALITIES:
                a = qm.addAction(q + (f"  ({tr('now playing')})" if self.link.get("height") and str(self.link.get("height")) + "p" == q else ""))
                a.setCheckable(True)
                a.setChecked(q == cur)
                a.triggered.connect(lambda _=False, q=q: self._set_quality(q))
        if _APP is not None:
            m.addAction(tr("Play copied link"), lambda: _APP.play_link(target=self))
            saved = saved_links()
            sm = m.addMenu(tr("Saved links"))
            if not saved:
                a = sm.addAction(tr("Links you play in Float show up here"))
                a.setEnabled(False)
            for it in saved:
                title = it.get("title") or it["url"]
                title = title if len(title) <= 60 else title[:57] + "…"
                a = sm.addAction(title, lambda u=it["url"]: _APP.play_link(target=self, url=u))
                a.setToolTip(it["url"])
            if saved:
                sm.addSeparator()
                if self.link and any(x["url"] == self.link.get("page") for x in saved):
                    sm.addAction(tr("Remove this link from the list"), lambda: forget_link(self.link.get("page")))
                sm.addAction(tr("Clear the list"), lambda: settings().setValue("float_links", "[]"))
            sm.setToolTipsVisible(True)
        m.addSeparator()
        top = m.addAction(tr("Always on top"))
        top.setCheckable(True)
        top.setChecked(self.on_top)
        top.toggled.connect(self.set_on_top)
        boot = m.addAction(tr("Open when Windows starts"))
        boot.setCheckable(True)
        boot.setChecked(bool(self.pin_id))
        boot.setToolTip(tr("This float comes back at the same place, playing the same file or link"))
        boot.toggled.connect(self.set_pinned)
        m.addAction(tr("Close"), self.close_by_user)
        m.exec(at)

    def closeEvent(self, e):
        self._drop_companion()
        self._stop_relay()
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())
        self.closed.emit()
        super().closeEvent(e)


# ============================================================================
# Dialog styling + parameter prompt (trim times, password…)
# ============================================================================
DIALOG_CSS = """
QDialog{background:$bg} QWidget#page{background:$bg} QLabel{color:$text;font:10pt 'Segoe UI'} QGroupBox{color:$dim;font:600 9pt 'Segoe UI';
border:1px solid $border;border-radius:8px;margin-top:22px;padding:10px 8px 8px 8px} QGroupBox::title{subcontrol-origin:margin;subcontrol-position:top left;padding:0 6px;left:8px;top:0px}
QLineEdit,QComboBox{background:$surface;color:$text;border:1px solid $border;border-radius:6px;padding:5px 8px;font:10pt 'Segoe UI'}
QLineEdit:focus,QComboBox:focus{border-color:$accent} QCheckBox{color:$text;font:10pt 'Segoe UI'}
QListWidget{background:$surface;color:$text;border:1px solid $border;border-radius:6px;padding:2px}
QScrollBar:vertical{background:transparent;width:10px;margin:2px} QScrollBar::handle:vertical{background:$button;border-radius:4px;min-height:30px}
QScrollBar::handle:vertical:hover{background:$hover} QScrollBar::add-line,QScrollBar::sub-line{height:0;width:0} QScrollBar::add-page,QScrollBar::sub-page{background:transparent}
QSlider::groove:horizontal{height:4px;background:$border;border-radius:2px} QSlider::sub-page:horizontal{background:$accent;border-radius:2px}
QSlider::handle:horizontal{background:$text;width:14px;height:14px;margin:-5px 0;border-radius:7px}
QListWidget::item{padding:3px 4px} QListWidget::item:selected{background:$accent;color:$on_accent;border-radius:4px}
QPushButton{background:$button;color:$text;border:none;border-radius:6px;padding:6px 16px;font:600 9pt 'Segoe UI'}
QPushButton:default{background:$accent;color:$on_accent} QPushButton:hover{background:$hover} QPushButton:default:hover{background:$accent2}
QComboBox QAbstractItemView{background:$surface;color:$text;selection-background-color:$accent;selection-color:$on_accent}
QMessageBox{background:$bg}
QTabWidget::pane{border:none;background:$bg} QTabWidget{background:$bg}
QTabBar{background:transparent;qproperty-drawBase:0} QTabWidget::tab-bar{left:4px} QTabBar::tab{background:transparent;color:$dim;padding:9px 22px;margin:0 2px;border:none;
border-bottom:2px solid transparent;font:600 10pt 'Segoe UI'} QTabBar::tab:selected{color:$text;border-bottom:2px solid $accent}
QTabBar::tab:hover{color:$text}
QPushButton#donate{background:#ffdd00;color:#1c1c1e;border-radius:8px;padding:8px 18px;font:700 10pt 'Segoe UI'}
QPushButton#donate:hover{background:#ffe94d}
QPushButton#link{background:transparent;color:$link;padding:6px 10px;border:1px solid $border;border-radius:8px}
QPushButton#link:hover{background:$hover}
QLabel#appname{font:700 20pt 'Segoe UI';color:$text} QLabel#tagline{color:$dim;font:10pt 'Segoe UI'}
QLabel#version{color:$accent;font:600 10pt 'Segoe UI'} QLabel#dim{color:$dim;font:9pt 'Segoe UI'}
QFrame#card{background:$surface;border:1px solid $border;border-radius:10px}
QFrame#card QLabel{background:transparent}
"""


# ============================================================================
# Waveform trimmer (Ringtone…): pick the part on the sound wave and listen before saving
# ============================================================================
class _WaveSignals(QObject):
    ready = Signal(list, float)


def _fmt_secs(s):
    s = max(0.0, s)
    return f"{int(s // 60)}:{s % 60:04.1f}"


class WaveView(QWidget):
    """Draws the waveform with the chosen part highlighted. Drag the handles to adjust, drag the middle to
    move it, click/drag elsewhere to choose a new part; the mouse wheel zooms, Shift+wheel scrolls."""
    changed = Signal()
    seek = Signal(float)
    HANDLE = 7

    def __init__(self, max_len):
        super().__init__()
        self.setMinimumSize(560, 120)
        self.setMouseTracking(True)
        self.setCursor(Qt.IBeamCursor)
        self.peaks, self.dur = [], 0.0
        self.a, self.b = 0.0, 0.0
        self.v0, self.v1 = 0.0, 1.0          # visible time range (zoom)
        self.head = None                     # playback position (s)
        self.max_len = max_len
        self._drag = None                    # ("a" | "b" | "move" | "new", anchor seconds, a, b)

    def set_data(self, peaks, dur):
        self.peaks, self.dur = peaks, max(dur, 0.1)
        self.v0, self.v1 = 0.0, self.dur
        self.a, self.b = 0.0, min(30.0, self.dur, self.max_len)
        self.changed.emit()
        self.update()

    # time <-> x
    def _x(self, t):
        return (t - self.v0) / max(1e-6, self.v1 - self.v0) * self.width()

    def _t(self, x):
        return max(0.0, min(self.dur, self.v0 + x / max(1, self.width()) * (self.v1 - self.v0)))

    def set_range(self, a, b, keep="b"):
        a, b = max(0.0, min(a, self.dur)), max(0.0, min(b, self.dur))
        if b - a > self.max_len:
            if keep == "a":
                b = a + self.max_len
            else:
                a = b - self.max_len
        if b - a < 1.0:
            if keep == "a":
                b = min(self.dur, a + 1.0)
                a = b - 1.0 if b - a < 1.0 else a
            else:
                a = max(0.0, b - 1.0)
                b = a + 1.0 if b - a < 1.0 else b
        self.a, self.b = a, b
        self.changed.emit()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), theme.color("surface"))
        mid = h / 2
        if not self.peaks:
            p.setPen(theme.color("dim"))
            p.drawText(self.rect(), Qt.AlignCenter, tr("Loading…"))
            return
        n = len(self.peaks)
        xa, xb = self._x(self.a), self._x(self.b)
        sel = QColor(theme.hexc("accent"))
        sel.setAlpha(46)
        p.fillRect(QRectF(xa, 0, xb - xa, h), sel)
        on, off = QColor(theme.hexc("accent")), QColor(theme.hexc("faint"))
        for x in range(w):
            t0, t1 = self._t(x), self._t(x + 1)
            i0 = int(t0 / self.dur * n)
            i1 = max(i0 + 1, int(t1 / self.dur * n))
            v = max(self.peaks[i0:i1] or [0.0])
            p.setPen(on if xa <= x <= xb else off)
            hh = max(1.0, v * (h / 2 - 6))
            p.drawLine(QPointF(x + 0.5, mid - hh), QPointF(x + 0.5, mid + hh))
        p.setPen(QPen(on, 2))
        for xx in (xa, xb):
            p.drawLine(QPointF(xx, 0), QPointF(xx, h))
            p.setBrush(on)
            p.drawRoundedRect(QRectF(xx - 4, mid - 14, 8, 28), 3, 3)
        if self.head is not None:
            p.setPen(QPen(QColor(theme.hexc("text")), 1.5))
            hx = self._x(self.head)
            p.drawLine(QPointF(hx, 0), QPointF(hx, h))

    def _hit(self, x):
        if abs(x - self._x(self.a)) <= self.HANDLE:
            return "a"
        if abs(x - self._x(self.b)) <= self.HANDLE:
            return "b"
        if self._x(self.a) < x < self._x(self.b):
            return "move"
        return "new"

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag is None:
            k = self._hit(x) if self.peaks else None
            self.setCursor(Qt.SizeHorCursor if k in ("a", "b") else Qt.OpenHandCursor if k == "move" else Qt.IBeamCursor)
            return
        kind, t0, a, b = self._drag
        t = self._t(x)
        if kind == "a":
            self.set_range(min(t, self.b - 1.0), self.b, keep="a")
        elif kind == "b":
            self.set_range(self.a, max(t, self.a + 1.0), keep="b")
        elif kind == "move":
            d = max(-a, min(self.dur - b, t - t0))
            self.set_range(a + d, b + d, keep="a")
        else:
            if abs(t - t0) * self.width() / max(1e-6, self.v1 - self.v0) > 4:
                self._drag = ("new-moved", t0, a, b)
                self.set_range(min(t0, t), max(t0, t), keep="a" if t > t0 else "b")

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or not self.peaks:
            return
        x = e.position().x()
        self._drag = (self._hit(x), self._t(x), self.a, self.b)
        if self._drag[0] == "move":
            self.setCursor(Qt.ClosedHandCursor)

    def mouseReleaseEvent(self, e):
        if self._drag and self._drag[0] == "new":       # a plain click: the part starts here
            t = self._drag[1]
            ln = self.b - self.a
            self.set_range(t, t + ln, keep="a")
            self.seek.emit(self.a)
        self._drag = None
        self.setCursor(Qt.IBeamCursor)

    def wheelEvent(self, e):
        if not self.peaks:
            return
        d = e.angleDelta().y() or e.angleDelta().x()
        span = self.v1 - self.v0
        if e.modifiers() & Qt.ShiftModifier or e.angleDelta().x():
            shift = -d / 120 * span * 0.15
            shift = max(-self.v0, min(self.dur - self.v1, shift))
            self.v0, self.v1 = self.v0 + shift, self.v1 + shift
        else:
            at = self._t(e.position().x())
            f = 0.8 if d > 0 else 1.25
            new = max(2.0, min(self.dur, span * f))
            r = (at - self.v0) / max(1e-6, span)
            self.v0 = max(0.0, min(self.dur - new, at - r * new))
            self.v1 = self.v0 + new
        self.update()


class TrimWidget(QWidget):
    """Waveform + play button + start/end boxes. value() -> 'start-end' in seconds."""

    def __init__(self, path, max_len=40.0):
        super().__init__()
        self.path = path
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = WaveView(max_len)
        lay.addWidget(self.view)
        row = QHBoxLayout()
        self.play = QPushButton("▶  " + tr("Play"))
        self.play.setEnabled(False)
        self.play.clicked.connect(self.toggle)
        row.addWidget(self.play)
        self.start_ed, self.end_ed = QLineEdit(), QLineEdit()
        for lbl, ed in ((tr("Start"), self.start_ed), (tr("End"), self.end_ed)):
            ed.setFixedWidth(84)
            ed.setLayoutDirection(Qt.LeftToRight)
            ed.editingFinished.connect(self._typed)
            row.addSpacing(10)
            row.addWidget(QLabel(lbl))
            row.addWidget(ed)
        self.len_lbl = QLabel()
        row.addSpacing(10)
        row.addWidget(self.len_lbl)
        row.addStretch(1)
        lay.addLayout(row)
        hint = QLabel(tr("Drag the orange edges or the part itself · scroll to zoom · up to {n} seconds", n=int(max_len)))
        hint.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        lay.addWidget(hint)
        self.view.changed.connect(self._sync)
        self.view.seek.connect(lambda t: self._play_from(t) if self._playing() else None)
        self.player = None
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            self.player.setSource(QUrl.fromLocalFile(path))
            self.player.positionChanged.connect(self._pos)
            self.player.playbackStateChanged.connect(lambda *_: self._label())
        except Exception as e:
            winsys.log(f"trim: no player ({e})")
        self.sig = _WaveSignals()
        self.sig.ready.connect(self._ready, Qt.QueuedConnection)
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            peaks, dur = engine.waveform(self.path)
        except Exception as e:
            winsys.log(f"waveform failed: {e}")
            peaks, dur = [], 0.0
        try:
            self.sig.ready.emit(peaks or [0.0] * 10, float(dur or engine.media_duration(self.path) or 30.0))
        except RuntimeError:
            pass                                    # dialog already closed

    def _ready(self, peaks, dur):
        self.view.set_data(peaks, dur)
        self.play.setEnabled(self.player is not None)

    def _sync(self):
        self.start_ed.setText(_fmt_secs(self.view.a))
        self.end_ed.setText(_fmt_secs(self.view.b))
        self.len_lbl.setText(tr("{s} seconds", s=f"{self.view.b - self.view.a:.1f}"))

    def _typed(self):
        try:
            a = engine._secs(engine.parse_time(self.start_ed.text()))
            b = engine._secs(engine.parse_time(self.end_ed.text()))
            self.view.set_range(a, max(b, a + 1.0), keep="a" if self.sender() is self.start_ed else "b")
        except Exception:
            self._sync()

    def _playing(self):
        from PySide6.QtMultimedia import QMediaPlayer
        return self.player is not None and self.player.playbackState() == QMediaPlayer.PlayingState

    def _label(self):
        self.play.setText(("■  " + tr("Stop")) if self._playing() else ("▶  " + tr("Play")))

    def _play_from(self, t):
        self.player.setPosition(int(t * 1000))
        self.player.play()

    def toggle(self):
        if not self.player:
            return
        if self._playing():
            self.player.pause()
            self.view.head = None
            self.view.update()
        else:
            self._play_from(self.view.a)

    def _pos(self, ms):
        if not self._playing():
            return
        t = ms / 1000
        if t >= self.view.b or t < self.view.a - 0.5:
            self.player.pause()
            self.view.head = None
        else:
            self.view.head = t
        self.view.update()

    def stop(self):
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())

    def value(self):
        return f"{self.view.a:.3f}-{self.view.b:.3f}"


class _CropSignals(QObject):
    ready = Signal(object, object)


class CropPreview(QWidget):
    """A frame of the video with the crop box on it. The box starts on the faces it finds;
    drag it sideways (or up and down) to choose what stays in the picture. value() -> centre (0..1)."""

    def __init__(self, path):
        super().__init__()
        self.setMinimumSize(560, 250)
        self.setCursor(Qt.OpenHandCursor)
        self.img = None
        self.ratio = 9 / 16
        self.cx = 0.5
        self.moved = False
        self._drag = None
        self.sig = _CropSignals()
        self.sig.ready.connect(self._ready, Qt.QueuedConnection)
        threading.Thread(target=self._load, args=(path,), daemon=True).start()

    def _load(self, path):
        img, cx = None, None
        try:
            import tempfile
            png = Path(tempfile.mkdtemp(prefix="dw-crop-")) / "frame.png"
            if engine.preview_frame(path, png):
                img = QImage(str(png))
                self.sig.ready.emit(img, None)          # show the frame now, the faces follow
            cx = engine._face_center_x(path)
        except Exception as e:
            winsys.log(f"crop preview: {e}")
        try:
            self.sig.ready.emit(img, cx)
        except RuntimeError:
            pass

    def _ready(self, img, cx):
        self.img = img if img is not None and not img.isNull() else None
        if cx is not None and not self.moved:
            self.cx = cx
        self.update()

    def set_shape(self, label):
        a, b = (int(x) for x in str(label).split()[0].split(":"))
        self.ratio = a / b
        self.update()

    def _rects(self):
        """(picture rect on screen, crop rect on screen)"""
        iw, ih = (self.img.width(), self.img.height()) if self.img else (16, 9)
        s = min(self.width() / iw, self.height() / ih)
        pw, ph = iw * s, ih * s
        pic = QRectF((self.width() - pw) / 2, (self.height() - ph) / 2, pw, ph)
        if pw / ph > self.ratio:
            cw, ch = ph * self.ratio, ph
            x = max(0.0, min(pw - cw, pw * self.cx - cw / 2))
            crop = QRectF(pic.x() + x, pic.y(), cw, ch)
        else:
            cw, ch = pw, pw / self.ratio
            crop = QRectF(pic.x(), pic.y() + (ph - ch) / 2, cw, ch)
        return pic, crop

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), theme.color("surface"))
        if self.img is None:
            p.setPen(theme.color("dim"))
            p.drawText(self.rect(), Qt.AlignCenter, tr("Loading…"))
            return
        pic, crop = self._rects()
        p.drawImage(pic, self.img)
        path = QPainterPath()
        path.addRect(pic)
        inner = QPainterPath()
        inner.addRect(crop)
        p.fillPath(path.subtracted(inner), QColor(0, 0, 0, 150))
        p.setPen(QPen(QColor(theme.hexc("accent")), 2))
        p.setBrush(Qt.NoBrush)
        p.drawRect(crop.adjusted(1, 1, -1, -1))
        # rule-of-thirds guides
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        for i in (1, 2):
            x = crop.x() + crop.width() * i / 3
            y = crop.y() + crop.height() * i / 3
            p.drawLine(QPointF(x, crop.top()), QPointF(x, crop.bottom()))
            p.drawLine(QPointF(crop.left(), y), QPointF(crop.right(), y))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.img is not None:
            self._drag = (e.position().x(), self.cx)
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._drag is None:
            return
        pic, crop = self._rects()
        x0, cx0 = self._drag
        half = crop.width() / 2 / max(1.0, pic.width())
        self.cx = max(half, min(1 - half, cx0 + (e.position().x() - x0) / max(1.0, pic.width())))
        self.moved = True
        self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None
        self.setCursor(Qt.OpenHandCursor)

    def value(self):
        if self.img is None:
            return ""                     # not loaded yet: let the tool find the faces itself
        pic, crop = self._rects()
        return f"{(crop.center().x() - pic.x()) / max(1.0, pic.width()):.4f}"


# ============================================================================
# PDF: page grid (Arrange pages…) and signing (Sign…)
# ============================================================================
def _render_page(doc, i, width, extra_rot=0):
    """QImage of page i, `width` px wide (visible orientation plus extra_rot degrees)."""
    import pymupdf
    page = doc[i]
    z = width / max(1.0, page.rect.width)
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z).prerotate(extra_rot), alpha=False)
    return QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()


class PageBoard(QWidget):
    """The pages of one or more PDFs (and pictures) as thumbnails. Drag to reorder (an orange line shows where
    they'll go), Ctrl/Shift to pick several, Delete removes, turn left/right; drop PDFs or pictures from Explorer
    to add their pages. value() -> JSON for engine.pdf_arrange."""
    TH = 128            # thumbnail box
    GAP = 18
    LABEL = 20

    def __init__(self, paths):
        super().__init__()
        from PySide6.QtWidgets import QScrollArea
        self.sources = []       # file paths
        self.docs = {}          # source index -> open PyMuPDF document
        self.items = []         # dicts: src, page, rot, thumb (QImage | None), sel
        self._anchor = None
        self._press = None      # (pos, index, was_selected)
        self._drop_at = None    # insertion index while dragging
        self.canvas = QWidget()
        self.canvas.setMouseTracking(True)
        self.canvas.setFocusPolicy(Qt.StrongFocus)
        self.canvas.paintEvent = self._paint
        self.canvas.mousePressEvent = self._mouse_press
        self.canvas.mouseMoveEvent = self._mouse_move
        self.canvas.mouseReleaseEvent = self._mouse_release
        self.canvas.keyPressEvent = self._key
        self.canvas.resizeEvent = lambda e: self._relayout()
        self.scroll = QScrollArea()
        self.scroll.setWidget(self.canvas)
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumSize(640, 380)
        self.scroll.setStyleSheet(f"QScrollArea{{background:{theme.hexc('canvas')};border:none;border-radius:8px}}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.scroll)
        row = QHBoxLayout()
        for label, fn in (("⟲  " + tr("Turn left"), lambda: self._turn(-90)), ("⟳  " + tr("Turn right"), lambda: self._turn(90)),
                          ("✕  " + tr("Delete"), self._delete), ("＋  " + tr("Add files…"), self._add_dialog)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        self.count = QLabel()
        row.addWidget(self.count)
        lay.addLayout(row)
        hint = QLabel(tr("Drag pages to change the order · Ctrl or Shift picks several · Delete removes them · "
                         "drop PDFs or pictures here to add their pages"))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        lay.addWidget(hint)
        self.setAcceptDrops(True)
        self._timer = QTimer(self, interval=0, timeout=self._render_some)
        for f in paths:
            self._add_file(f)
        self._original = len(self.items)

    # ---- content
    def _add_file(self, f, at=None):
        import pymupdf
        cat = engine.EXT_CATEGORY.get(engine.ext_of(f))
        if cat not in ("pdf", "image"):
            return 0
        si = len(self.sources)
        self.sources.append(str(f))
        try:
            self.docs[si] = pymupdf.open(str(f)) if cat == "pdf" else None
        except Exception as e:
            winsys.log(f"page board: {f}: {e}")
            return 0
        n = self.docs[si].page_count if cat == "pdf" else 1
        new = [{"src": si, "page": i, "rot": 0, "thumb": None, "sel": False} for i in range(n)]
        at = len(self.items) if at is None else at
        self.items[at:at] = new
        self._relayout()
        self._timer.start()
        return n

    def _render_some(self):
        import time
        t0 = time.monotonic()
        for it in self.items:
            if it["thumb"] is not None:
                continue
            try:
                d = self.docs.get(it["src"])
                if d is None:                                 # a picture
                    img = QImage(self.sources[it["src"]])
                    if img.isNull():
                        pil = engine.open_image(self.sources[it["src"]])
                        pil.thumbnail((400, 400))
                        img = QImage(pil.convert("RGBA").tobytes("raw", "RGBA"), pil.width, pil.height,
                                     pil.width * 4, QImage.Format_RGBA8888).copy()
                    it["thumb"] = img.scaled(self.TH * 2, self.TH * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                else:
                    it["thumb"] = _render_page(d, it["page"], self.TH * 2)
            except Exception as e:
                winsys.log(f"page board thumb: {e}")
                it["thumb"] = QImage()
            if time.monotonic() - t0 > 0.04:
                break
        self.canvas.update()
        if all(it["thumb"] is not None for it in self.items):
            self._timer.stop()

    # ---- layout
    def _cols(self):
        return max(1, (self.scroll.viewport().width() - self.GAP) // (self.TH + self.GAP))

    def _cell(self, i):
        c = self._cols()
        x = self.GAP + (i % c) * (self.TH + self.GAP)
        y = self.GAP + (i // c) * (self.TH + self.LABEL + self.GAP)
        return QRectF(x, y, self.TH, self.TH)

    def _relayout(self):
        rows = (len(self.items) + self._cols() - 1) // self._cols()
        self.canvas.setMinimumHeight(self.GAP + rows * (self.TH + self.LABEL + self.GAP))
        n, orig = len(self.items), getattr(self, "_original", len(self.items))
        self.count.setText(tr("{n} pages", n=n))
        self.canvas.update()

    def _index_at(self, pos):
        for i in range(len(self.items)):
            if self._cell(i).adjusted(-4, -4, 4, self.LABEL).contains(pos):
                return i
        return None

    def _insert_at(self, pos):
        """Where dropped pages would go: before the page under the cursor, or after it on its right half."""
        c = self._cols()
        row_h = self.TH + self.LABEL + self.GAP
        r = max(0, int((pos.y() - self.GAP / 2) // row_h))
        col = int(round((pos.x() - self.GAP) / (self.TH + self.GAP)))
        col = max(0, min(c, col))
        return max(0, min(len(self.items), r * c + col))

    # ---- painting
    def _paint(self, _):
        p = QPainter(self.canvas)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.canvas.rect(), theme.color("canvas"))
        from PySide6.QtGui import QTransform
        for i, it in enumerate(self.items):
            cell = self._cell(i)
            if it["sel"]:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(theme.hexc("accent")))
                p.drawRoundedRect(cell.adjusted(-6, -6, 6, self.LABEL), 8, 8)
            img = it["thumb"]
            if img is not None and not img.isNull():
                if it["rot"]:
                    img = img.transformed(QTransform().rotate(it["rot"]))
                s = min(cell.width() / img.width(), cell.height() / img.height())
                w, h = img.width() * s, img.height() * s
                r = QRectF(cell.center().x() - w / 2, cell.center().y() - h / 2, w, h)
                p.fillRect(r, QColor("white"))
                p.drawImage(r, img)
            else:
                p.setPen(QPen(theme.color("dim"), 1, Qt.DashLine))
                p.setBrush(Qt.NoBrush)
                p.drawRect(cell.adjusted(20, 10, -20, -10))
            p.setPen(QColor(theme.hexc("on_accent")) if it["sel"] else theme.color("text"))
            label = str(i + 1) if len(self.sources) == 1 else f"{i + 1}  ·  {Path(self.sources[it['src']]).stem[:14]}"
            p.drawText(QRectF(cell.left() - 6, cell.bottom() + 2, cell.width() + 12, self.LABEL - 2),
                       Qt.AlignCenter, label)
        if self._drop_at is not None:
            i = self._drop_at
            c = self._cols()
            if i < len(self.items):
                ref = self._cell(i)
                x = ref.left() - self.GAP / 2
            else:
                ref = self._cell(max(0, i - 1))
                x = ref.right() + self.GAP / 2
            if i > 0 and i % c == 0 and i < len(self.items):           # start of a row: show after the last of the row above
                prev = self._cell(i - 1)
                p.setPen(QPen(QColor(theme.hexc("accent")), 3))
                p.drawLine(QPointF(prev.right() + self.GAP / 2, prev.top()), QPointF(prev.right() + self.GAP / 2, prev.bottom()))
            p.setPen(QPen(QColor(theme.hexc("accent")), 3))
            p.drawLine(QPointF(x, ref.top()), QPointF(x, ref.bottom()))

    # ---- mouse
    def _mouse_press(self, e):
        self.canvas.setFocus()
        if e.button() != Qt.LeftButton:
            return
        pos = e.position()
        i = self._index_at(pos)
        mods = e.modifiers()
        if i is None:
            if not mods & (Qt.ControlModifier | Qt.ShiftModifier):
                for it in self.items:
                    it["sel"] = False
            self.canvas.update()
            return
        was = self.items[i]["sel"]
        if mods & Qt.ShiftModifier and self._anchor is not None:
            a, b = sorted((self._anchor, i))
            for k, it in enumerate(self.items):
                it["sel"] = a <= k <= b
        elif mods & Qt.ControlModifier:
            self.items[i]["sel"] = not was
            self._anchor = i
        elif not was:
            for k, it in enumerate(self.items):
                it["sel"] = k == i
            self._anchor = i
        self._press = (pos, i, was)
        self.canvas.update()

    def _mouse_move(self, e):
        if self._press is None or not e.buttons() & Qt.LeftButton:
            return
        pos = e.position()
        if self._drop_at is None and (pos - self._press[0]).manhattanLength() < 8:
            return
        self.canvas.setCursor(Qt.ClosedHandCursor)
        self._drop_at = self._insert_at(pos)
        self.scroll.ensureVisible(int(pos.x()), int(pos.y()), 10, 40)      # scroll near the edges
        self.canvas.update()

    def _mouse_release(self, e):
        if self._drop_at is not None:
            at = self._drop_at
            moving = [it for it in self.items if it["sel"]]
            before = sum(1 for k, it in enumerate(self.items) if it["sel"] and k < at)
            self.items = [it for it in self.items if not it["sel"]]
            at -= before
            self.items[at:at] = moving
        elif self._press is not None and not e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier):
            i = self._press[1]                            # plain click on a selected page: just that one
            for k, it in enumerate(self.items):
                it["sel"] = k == i
            self._anchor = i
        self._press = None
        self._drop_at = None
        self.canvas.setCursor(Qt.ArrowCursor)
        self._relayout()

    def _key(self, e):
        if e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self._delete()
        elif e.key() == Qt.Key_A and e.modifiers() & Qt.ControlModifier:
            for it in self.items:
                it["sel"] = True
            self.canvas.update()

    # ---- buttons
    def _turn(self, deg):
        for it in self.items:
            if it["sel"]:
                it["rot"] = (it["rot"] + deg) % 360
        self.canvas.update()

    def _delete(self):
        keep = [it for it in self.items if not it["sel"]]
        if keep and len(keep) < len(self.items):
            self.items = keep
            self._relayout()

    def _add_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(self, tr("Add files…"), str(Path(self.sources[0]).parent),
                                                "PDF / Images (*.pdf *.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.heic)")
        for f in files:
            self._add_file(f)

    # ---- files dropped from Explorer
    def _files(self, e):
        md = e.mimeData()
        return [u.toLocalFile() for u in (md.urls() if md.hasUrls() else []) if u.isLocalFile()
                and engine.EXT_CATEGORY.get(engine.ext_of(u.toLocalFile())) in ("pdf", "image")]

    def dragEnterEvent(self, e):
        if self._files(e):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if self._files(e):
            pos = self.canvas.mapFrom(self, e.position().toPoint())
            self._drop_at = self._insert_at(QPointF(pos))
            self.canvas.update()
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._drop_at = None
        self.canvas.update()

    def dropEvent(self, e):
        at = self._drop_at if self._drop_at is not None else len(self.items)
        for f in self._files(e):
            at += self._add_file(f, at)
        self._drop_at = None
        self._relayout()
        e.acceptProposedAction()

    def stop(self):
        self._timer.stop()

    def value(self):
        return json.dumps({"sources": self.sources, "pages": [[it["src"], it["page"], it["rot"]] for it in self.items]})


def _signature_file() -> Path:
    return Path(engine.models_dir()).parent / "signature.png"


def _clean_signature(src, dst):
    """A photo or scan of a signature -> the ink only, on transparent background."""
    from PIL import Image
    img = engine.open_image(src).convert("RGBA")
    img.thumbnail((1400, 1400))
    gray = img.convert("L")
    alpha = gray.point(lambda v: 0 if v > 200 else 255 if v < 120 else int((200 - v) * 255 / 80))
    if img.split()[-1].getextrema()[0] < 250:          # already has transparency: keep it
        alpha = Image.composite(img.split()[-1], alpha, img.split()[-1].point(lambda v: 255 if v < 250 else 0))
    img.putalpha(alpha)
    box = img.getbbox()
    if box:
        img = img.crop(box)
    dst.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst)
    return dst


class DrawPad(QDialog):
    """Sign with the mouse or a pen."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint)
        self.setWindowTitle(f"{APP} — " + tr("Draw your signature"))
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        lay = QVBoxLayout(self)
        self.canvas = QWidget()
        self.canvas.setMinimumSize(520, 200)
        self.canvas.setCursor(Qt.CrossCursor)
        self.canvas.setAttribute(Qt.WA_StaticContents)
        self.strokes, self._cur = [], None
        self.canvas.paintEvent = self._paint
        self.canvas.mousePressEvent = lambda e: self._start(e.position())
        self.canvas.mouseMoveEvent = lambda e: self._move(e.position())
        self.canvas.mouseReleaseEvent = lambda e: self._end()
        lay.addWidget(self.canvas)
        row = QHBoxLayout()
        clear = QPushButton(tr("Clear"))
        clear.clicked.connect(lambda: (self.strokes.clear(), self.canvas.update()))
        row.addWidget(clear)
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Use this signature"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)

    def _start(self, pt):
        self._cur = [QPointF(pt)]
        self.strokes.append(self._cur)

    def _move(self, pt):
        if self._cur is not None:
            self._cur.append(QPointF(pt))
            self.canvas.update()

    def _end(self):
        self._cur = None

    def _draw(self, p, scale=1.0):
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(20, 30, 90), 3.2 * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        for s in self.strokes:
            if len(s) == 1:
                p.drawPoint(s[0] * scale)
            path = QPainterPath(s[0] * scale)
            for q in s[1:]:
                path.lineTo(q * scale)
            p.drawPath(path)

    def _paint(self, _):
        p = QPainter(self.canvas)
        p.fillRect(self.canvas.rect(), QColor("white"))
        p.setPen(QPen(QColor(200, 200, 205), 1, Qt.DashLine))
        y = self.canvas.height() * 0.72
        p.drawLine(QPointF(20, y), QPointF(self.canvas.width() - 20, y))
        self._draw(p)

    def save(self, dst):
        if not any(len(s) > 1 for s in self.strokes):
            return None
        img = QImage(self.canvas.size() * 3, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        self._draw(p, 3.0)
        p.end()
        dst.parent.mkdir(parents=True, exist_ok=True)
        tmp = dst.with_name("signature-drawn.png")
        img.save(str(tmp))
        return _clean_signature(tmp, dst)


class SignPlacer(QWidget):
    """Shows a page with your signature on it: drag it into place, drag its corner to size it,
    ◀ ▶ to choose the page. value() -> JSON for engine.pdf_sign."""
    VIEW_W = 470

    def __init__(self, paths):
        super().__init__()
        import pymupdf
        self.pdf = next(x for x in paths if engine.EXT_CATEGORY.get(engine.ext_of(x)) == "pdf")
        self.doc = pymupdf.open(self.pdf)
        self.page_i = self.doc.page_count - 1               # signatures usually go on the last page
        dropped = next((x for x in paths if engine.EXT_CATEGORY.get(engine.ext_of(x)) == "image"), None)
        self.sig_path = None
        if dropped:
            try:
                self.sig_path = _clean_signature(dropped, _signature_file().with_name("signature-dropped.png"))
            except Exception as e:
                winsys.log(f"signature image: {e}")
        elif _signature_file().exists():
            self.sig_path = _signature_file()
        self.sig_img = QImage(str(self.sig_path)) if self.sig_path else None
        self.places = {}                                     # page -> [x0, y0, x1, y1] (0..1 of the page)
        self._last = [0.58, 0.78, 0.90, 0.88]
        self._drag = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = QWidget()
        self.view.setMinimumSize(self.VIEW_W, 360)
        self.view.setMouseTracking(True)
        self.view.paintEvent = self._paint
        self.view.mousePressEvent = self._press
        self.view.mouseMoveEvent = self._move
        self.view.mouseReleaseEvent = lambda e: setattr(self, "_drag", None)
        lay.addWidget(self.view, 1)
        side = QVBoxLayout()
        nav = QHBoxLayout()
        self.prev_b, self.next_b = QPushButton("◀"), QPushButton("▶")
        self.prev_b.clicked.connect(lambda: self._go(-1))
        self.next_b.clicked.connect(lambda: self._go(1))
        self.page_lbl = QLabel()
        self.page_lbl.setAlignment(Qt.AlignCenter)
        nav.addWidget(self.prev_b)
        nav.addWidget(self.page_lbl, 1)
        nav.addWidget(self.next_b)
        side.addLayout(nav)
        from PySide6.QtWidgets import QButtonGroup, QRadioButton, QSpinBox
        side.addWidget(QLabel("<b>" + tr("Sign") + "</b>"))
        self.mode_group = QButtonGroup(self)
        n = self.doc.page_count
        self.modes = {}
        for key, label in (("this", tr("Only the page shown")), ("all", tr("All pages")),
                           ("range", tr("Pages from")), ("pick", tr("Pages I click"))):
            rb = QRadioButton(label)
            self.mode_group.addButton(rb)
            self.modes[key] = rb
            if key == "range":
                rr = QHBoxLayout()
                rr.addWidget(rb)
                self.r_from, self.r_to = QSpinBox(), QSpinBox()
                for sp, v in ((self.r_from, 1), (self.r_to, n)):
                    sp.setRange(1, n)
                    sp.setValue(v)
                    sp.setFixedWidth(64)
                    sp.valueChanged.connect(self._range_changed)
                rr.addWidget(self.r_from)
                rr.addWidget(QLabel(tr("to")))
                rr.addWidget(self.r_to)
                rr.addStretch(1)
                side.addLayout(rr)
            else:
                side.addWidget(rb)
            rb.toggled.connect(lambda on, k=key: on and self._set_mode(k))
        self.mode = None
        self.signed_lbl = QLabel()
        self.signed_lbl.setWordWrap(True)
        self.signed_lbl.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        side.addWidget(self.signed_lbl)
        draw = QPushButton(tr("Draw signature…"))
        draw.clicked.connect(self._draw_new)
        side.addWidget(draw)
        pick = QPushButton(tr("Use a picture…"))
        pick.clicked.connect(self._pick)
        side.addWidget(pick)
        self.del_b = QPushButton(tr("Delete signature"))
        self.del_b.clicked.connect(self._delete_sig)
        side.addWidget(self.del_b)
        tip = QLabel(tr("Drag the signature into place and drag its corner to make it bigger or smaller. "
                        "It's remembered for next time.") + "\n\n" + tr("You can also drop a picture of your signature here."))
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        side.addWidget(tip)
        side.addStretch(1)
        lay.addLayout(side)
        self._page_img = None
        self.setAcceptDrops(True)
        self.shared = list(self._last)                       # signatures usually go on the last page
        self._go(0)
        mode = settings().value("sign_mode", "this")
        self.modes.get(mode, self.modes["this"]).setChecked(True)
        self.del_b.setEnabled(self.sig_img is not None)
        if self.sig_img is None:
            QTimer.singleShot(200, self._draw_new)

    @property
    def box(self):
        if self.mode == "pick":
            return self.places.get(self.page_i)
        if self.mode == "range" and not (self.r_from.value() - 1 <= self.page_i <= self.r_to.value() - 1):
            return None
        return self.shared

    @box.setter
    def box(self, v):
        if self.mode == "pick":
            self.places[self.page_i] = v
        else:
            self.shared = v
        self._last = list(v)

    # page
    def _go(self, step):
        self.page_i = max(0, min(self.doc.page_count - 1, self.page_i + step))
        self.page_lbl.setText(tr("Page {i} of {n}", i=self.page_i + 1, n=self.doc.page_count))
        self.prev_b.setEnabled(self.page_i > 0)
        self.next_b.setEnabled(self.page_i < self.doc.page_count - 1)
        self._page_img = _render_page(self.doc, self.page_i, 900)
        if self.mode is not None:
            self._signed_label()
        self.view.update()

    def _set_mode(self, key):
        self.mode = key
        settings().setValue("sign_mode", key)
        if key == "pick" and not self.places:
            self.places[self.page_i] = list(self._last)
        self.r_from.setEnabled(key == "range")
        self.r_to.setEnabled(key == "range")
        self._fit_rect_to_sig()
        self._signed_label()
        self.view.update()

    def _range_changed(self):
        if self.r_to.value() < self.r_from.value():
            self.sender().setValue(self.r_from.value() if self.sender() is self.r_to else self.r_to.value())
        if self.mode != "range":
            self.modes["range"].setChecked(True)
        self._signed_label()
        self.view.update()

    def signed_pages(self):
        n = self.doc.page_count
        if self.mode == "all":
            return list(range(n))
        if self.mode == "range":
            return list(range(self.r_from.value() - 1, self.r_to.value()))
        if self.mode == "pick":
            return sorted(self.places)
        return [self.page_i]

    def _signed_label(self):
        if self.mode == "pick":
            hint = tr("Click a page to sign it; right-click the signature to take it off that page.")
        elif self.mode == "this":
            hint = tr("The signature goes on the page shown when you press Apply.")
        else:
            hint = tr("The signature goes in the same place on each of these pages.")
        pages = self.signed_pages()
        if not pages:
            txt = tr("No page signed yet")
        elif len(pages) == self.doc.page_count and len(pages) > 1:
            txt = tr("Signed on every page")
        else:
            txt = tr("Signed pages: {list}", list=", ".join(str(i + 1) for i in pages[:12]) + ("…" if len(pages) > 12 else ""))
        self.signed_lbl.setText(txt + "\n" + hint)

    def _page_rect(self):
        img = self._page_img
        s = min((self.view.width() - 8) / img.width(), (self.view.height() - 8) / img.height())
        w, h = img.width() * s, img.height() * s
        return QRectF((self.view.width() - w) / 2, (self.view.height() - h) / 2, w, h)

    def _sig_rect(self):
        pr = self._page_rect()
        x0, y0, x1, y1 = self.box
        return QRectF(pr.x() + x0 * pr.width(), pr.y() + y0 * pr.height(), (x1 - x0) * pr.width(), (y1 - y0) * pr.height())

    def _fit_rect_to_sig(self):
        """Keep the box the signature's shape (same width, matching height)."""
        if self.sig_img is None or self.sig_img.isNull() or self.box is None:
            return
        pr = self._page_rect()
        x0, y0, x1, _ = self.box
        w_px = (x1 - x0) * pr.width()
        h_px = w_px * self.sig_img.height() / max(1, self.sig_img.width())
        y1 = y0 + h_px / max(1.0, pr.height())
        if y1 > 1.0:
            y0, y1 = max(0.0, 1.0 - (y1 - y0)), 1.0
        self.box = [x0, y0, x1, y1]

    def _paint(self, _):
        p = QPainter(self.view)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.view.rect(), theme.color("canvas"))
        pr = self._page_rect()
        p.drawImage(pr, self._page_img)
        if self.sig_img is not None and not self.sig_img.isNull() and self.box is not None:
            sr = self._sig_rect()
            p.drawImage(sr, self.sig_img)
            p.setPen(QPen(QColor(theme.hexc("accent")), 1.5, Qt.DashLine))
            p.setBrush(Qt.NoBrush)
            p.drawRect(sr)
            p.setBrush(QColor(theme.hexc("accent")))
            p.setPen(Qt.NoPen)
            p.drawEllipse(sr.bottomRight(), 6, 6)

    def _press(self, e):
        if self.sig_img is None:
            return
        if e.button() == Qt.RightButton:
            if self.mode == "pick" and self.box is not None and self._sig_rect().contains(e.position()):
                self.places.pop(self.page_i, None)
                self._signed_label()
                self.view.update()
            return
        if self.box is None:                                 # click on an unsigned page: sign it here
            if self.mode != "pick":
                return
            pr = self._page_rect()
            pos = e.position()
            w, h = self._last[2] - self._last[0], self._last[3] - self._last[1]
            x = min(max(0.0, (pos.x() - pr.x()) / pr.width() - w / 2), 1 - w)
            y = min(max(0.0, (pos.y() - pr.y()) / pr.height() - h / 2), 1 - h)
            self.box = [x, y, x + w, y + h]
            self._signed_label()
            self.view.update()
            return
        pos = e.position()
        sr = self._sig_rect()
        if (pos - sr.bottomRight()).manhattanLength() < 16:
            self._drag = ("size", pos, list(self.box))
        elif sr.contains(pos):
            self._drag = ("move", pos, list(self.box))

    def _move(self, e):
        pos = e.position()
        if self._drag is None:
            sr = self._sig_rect() if (self.sig_img is not None and self.box is not None) else QRectF()
            near = (pos - sr.bottomRight()).manhattanLength() < 16
            self.view.setCursor(Qt.SizeFDiagCursor if near else Qt.OpenHandCursor if sr.contains(pos) else Qt.ArrowCursor)
            return
        kind, start, r0 = self._drag
        pr = self._page_rect()
        dx, dy = (pos.x() - start.x()) / pr.width(), (pos.y() - start.y()) / pr.height()
        x0, y0, x1, y1 = r0
        if kind == "move":
            w, h = x1 - x0, y1 - y0
            nx = max(0.0, min(1.0 - w, x0 + dx))
            ny = max(0.0, min(1.0 - h, y0 + dy))
            self.box = [nx, ny, nx + w, ny + h]
        else:
            nx1 = max(x0 + 0.05, min(1.0, x1 + dx))
            self.box = [x0, y0, nx1, y1]
            self._fit_rect_to_sig()
        self.view.update()

    # signature source
    def _set_sig(self, path):
        self.sig_path = path
        self.sig_img = QImage(str(path))
        self.del_b.setEnabled(True)
        self._fit_rect_to_sig()
        self.view.update()

    def _image_url(self, e):
        md = e.mimeData()
        for u in (md.urls() if md.hasUrls() else []):
            if u.isLocalFile() and engine.EXT_CATEGORY.get(engine.ext_of(u.toLocalFile())) == "image":
                return u.toLocalFile()
        return None

    def dragEnterEvent(self, e):
        if self._image_url(e) or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        if self._image_url(e) or e.mimeData().hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e):
        f = self._image_url(e)
        try:
            if not f and e.mimeData().hasImage():               # a picture dragged from a browser
                f = str(_signature_file().with_name("signature-pasted.png"))
                _signature_file().parent.mkdir(parents=True, exist_ok=True)
                QImage(e.mimeData().imageData()).save(f)
            if f:
                self._set_sig(_clean_signature(f, _signature_file()))
                e.acceptProposedAction()
        except Exception as ex:
            winsys.log(f"signature drop: {ex}")

    def _delete_sig(self):
        for f in _signature_file().parent.glob("signature*.png"):
            try:
                f.unlink()
            except OSError:
                pass
        self.sig_path, self.sig_img = None, None
        self.del_b.setEnabled(False)
        self.view.update()

    def _draw_new(self):
        pad = DrawPad(self)
        if pad.exec() == QDialog.Accepted:
            out = pad.save(_signature_file())
            if out:
                self._set_sig(out)

    def _pick(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("Use a picture…"), str(Path.home()),
                                           "Images (*.png *.jpg *.jpeg *.webp *.bmp *.heic)")
        if f:
            try:
                self._set_sig(_clean_signature(f, _signature_file()))
            except Exception as e:
                winsys.log(f"signature picture: {e}")

    def stop(self):
        pass

    def value(self):
        if not self.sig_path:
            return ""
        if self.mode == "pick":
            places = [{"page": i, "rect": [round(v, 5) for v in r]} for i, r in sorted(self.places.items())]
        else:
            places = [{"page": i, "rect": [round(v, 5) for v in self.shared]} for i in self.signed_pages()]
        return json.dumps({"sig": str(self.sig_path), "places": places}) if places else ""


class WatermarkEditor(QWidget):
    """Watermark… with a live preview of the first page: text (or the logo dragged with the PDF), angle,
    size and strength. Remembers the last choices. value() -> JSON for engine.pdf_watermark."""

    def __init__(self, paths):
        super().__init__()
        from PySide6.QtWidgets import QSlider
        import pymupdf
        self.pdf = next(x for x in paths if engine.EXT_CATEGORY.get(engine.ext_of(x)) == "pdf")
        self.logo = next((x for x in paths if engine.EXT_CATEGORY.get(engine.ext_of(x)) == "image"), None)
        src = pymupdf.open(self.pdf)
        self.first = pymupdf.open()
        self.first.insert_pdf(src, from_page=0, to_page=0)
        try:
            saved = json.loads(settings().value("pdf_watermark", "") or "{}")
        except ValueError:
            saved = {}
        self.spec = dict(engine.WATERMARK_DEFAULT, **saved)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.view = QLabel()
        self.view.setMinimumSize(380, 440)
        self.view.setAlignment(Qt.AlignCenter)
        self.view.setStyleSheet(f"background:{theme.hexc('canvas')};border-radius:8px")
        lay.addWidget(self.view, 1)
        side = QVBoxLayout()
        side.setSpacing(8)
        if not self.logo:
            side.addWidget(QLabel(tr("Text")))
            self.text = QLineEdit(self.spec.get("text") or "")
            self.text.textChanged.connect(lambda t: self._set("text", t))
            side.addWidget(self.text)
        if not self.logo:
            side.addWidget(QLabel(tr("Color")))
            crow = QHBoxLayout()
            self._swatches = []
            for col in ("#808080", "#000000", "#d0312d", "#1f5fbf", "#2e8b57", "#ff8a00"):
                b = QPushButton()
                b.setFixedSize(28, 28)
                b.setToolTip(col)
                b.clicked.connect(lambda _=False, c=col: self._set_color(c))
                crow.addWidget(b)
                self._swatches.append((b, col))
            more = QPushButton("…")
            more.setFixedSize(34, 28)
            more.setToolTip(tr("More colors…"))
            more.clicked.connect(self._pick_color)
            crow.addWidget(more)
            crow.addStretch(1)
            side.addLayout(crow)
            self._paint_swatches()
        side.addWidget(QLabel(tr("Direction")))
        row = QHBoxLayout()
        for label, ang in (("↗", 45), ("→", 0), ("↘", -45), ("↑", 90)):
            b = QPushButton(label)
            b.setFixedWidth(46)
            b.clicked.connect(lambda _=False, a=ang: self.angle.setValue(a))
            row.addWidget(b)
        row.addStretch(1)
        side.addLayout(row)
        self.angle = self._slider(-90, 90, int(self.spec["angle"]), "angle", lambda v: f"{v}°")
        side.addLayout(self.angle._row)
        side.addWidget(QLabel(tr("Size")))
        self.size = self._slider(10, 100, int(float(self.spec["size"]) * 100), "size", lambda v: f"{v}%", scale=100)
        side.addLayout(self.size._row)
        side.addWidget(QLabel(tr("Strength")))
        self.opacity = self._slider(5, 80, int(float(self.spec["opacity"]) * 100), "opacity", lambda v: f"{v}%", scale=100)
        side.addLayout(self.opacity._row)
        side.addStretch(1)
        lay.addLayout(side)
        self._timer = QTimer(self, singleShot=True, interval=120, timeout=self._render)
        self._render()

    def _slider(self, lo, hi, val, key, fmt, scale=1):
        from PySide6.QtWidgets import QSlider
        s = QSlider(Qt.Horizontal)
        s.setRange(lo, hi)
        s.setValue(val)
        lbl = QLabel(fmt(val))
        lbl.setFixedWidth(44)
        s.valueChanged.connect(lambda v: (lbl.setText(fmt(v)), self._set(key, v / scale)))
        s._row = QHBoxLayout()
        s._row.addWidget(s, 1)
        s._row.addWidget(lbl)
        return s

    def _set(self, key, v):
        self.spec[key] = v
        self._timer.start()

    def _paint_swatches(self):
        cur = str(self.spec.get("color", "#808080")).lower()
        for b, col in self._swatches:
            ring = theme.hexc("accent") if col == cur else theme.hexc("border")
            b.setStyleSheet(f"QPushButton{{background:{col};border:3px solid {ring};border-radius:14px;padding:0}}")

    def _set_color(self, col):
        self._set("color", col)
        self._paint_swatches()

    def _pick_color(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self.spec.get("color", "#808080")), self, tr("Color"))
        if c.isValid():
            self._set_color(c.name())

    def _render(self):
        import pymupdf
        try:
            d = pymupdf.open()
            d.insert_pdf(self.first)
            engine.apply_watermark(d, self.spec, self.logo)
            pg = d[0]
            z = 420 / max(pg.rect.width, pg.rect.height)
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False)
            img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
            self.view.setPixmap(QPixmap.fromImage(img))
        except Exception as e:
            winsys.log(f"watermark preview: {e}")

    def stop(self):
        keep = {k: v for k, v in self.spec.items() if k in ("text", "angle", "size", "opacity", "color")}
        settings().setValue("pdf_watermark", json.dumps(keep))

    def value(self):
        return json.dumps(self.spec)


def ask_params(op, paths) -> dict | None:
    dlg = QDialog(None, Qt.WindowStaysOnTopHint)
    title = tr(op.label).rstrip("…")
    dlg.setWindowTitle(f"{APP} — {title}")
    dlg.setWindowIcon(app_icon())
    dlg.setStyleSheet(i18n.css(DIALOG_CSS))
    lay = QVBoxLayout(dlg)
    who = Path(paths[0]).name if len(paths) == 1 else tr("{n} files", n=len(paths))
    lay.addWidget(QLabel(f"<b>{title}</b> &nbsp;<span style='color:{theme.hexc("dim")}'>{who}</span>"))
    form = QFormLayout()
    edits = {}
    trims = []
    for name, default in op.ask:
        if default == "@trim":                          # waveform: pick the part and listen to it
            tw = TrimWidget(paths[0], engine.RINGTONE_MAX)
            form.addRow(tw)
            edits[name] = tw
            trims.append(tw)
            continue
        if default in ("@pages", "@sign", "@watermark"):     # PDF page grid / signature / watermark preview
            try:
                w = (PageBoard(paths) if default == "@pages" else SignPlacer(paths) if default == "@sign"
                     else WatermarkEditor(paths))
            except Exception as e:
                message(APP, tr("Couldn't open this PDF") + f"<br><small>{e}</small>")
                return None
            form.addRow(w)
            edits[name] = w
            trims.append(w)
            continue
        if isinstance(default, (list, tuple)):          # a fixed set of choices
            cb = QComboBox()
            for opt in default:
                cb.addItem(tr(opt), opt)
            form.addRow(tr(name), cb)
            edits[name] = cb
            continue
        ed = QLineEdit(default)
        if name == "Password":
            ed.setEchoMode(QLineEdit.Password)
        if name in ("Start", "End", "At time"):
            ed.setPlaceholderText(tr("seconds, m:ss or h:mm:ss"))
            ed.setLayoutDirection(Qt.LeftToRight)
        form.addRow(tr(name), ed)
        edits[name] = ed
    if op.id == "social" and "Shape" in edits:          # see the crop on a frame of the video
        pv = CropPreview(paths[0])
        shape = edits["Shape"]
        pv.set_shape(shape.currentData())
        shape.currentIndexChanged.connect(lambda _=0: pv.set_shape(shape.currentData()))
        form.addRow(pv)
        hint = QLabel(tr("Drag the box to choose what stays in the picture"))
        hint.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        form.addRow(hint)
        edits["Center"] = pv
        trims.append(None)
    lay.addLayout(form)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText(tr("Apply"))
    bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
    bb.button(QDialogButtonBox.Ok).setDefault(True)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    dlg.setMinimumWidth(680 if any(isinstance(t, (PageBoard, SignPlacer, WatermarkEditor)) for t in trims) else 620 if trims else 340)
    if any(isinstance(t, (PageBoard, SignPlacer, WatermarkEditor)) for t in trims):
        dlg.resize(760, 560)
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        dlg.move(scr.availableGeometry().center() - QPoint(380, 280))
    else:
        dlg.move(QCursor.pos() - QPoint(310 if trims else 170, 60))
    dlg.activateWindow()
    ok = dlg.exec() == QDialog.Accepted
    for tw in trims:
        if tw is not None:
            tw.stop()
    if not ok:
        return None
    return {k: (e.currentData() if isinstance(e, QComboBox) else e.value() if isinstance(e, (TrimWidget, CropPreview, PageBoard, SignPlacer, WatermarkEditor)) else e.text())
            for k, e in edits.items()}


def message(title, html):
    box = QMessageBox()
    box.setWindowTitle(title)
    box.setWindowIcon(app_icon())
    box.setStyleSheet(i18n.css(DIALOG_CSS))
    box.setIconPixmap(app_icon().pixmap(48, 48))
    box.setTextFormat(Qt.RichText)
    box.setText(html)
    box.setStandardButtons(QMessageBox.Ok)
    box.button(QMessageBox.Ok).setText(tr("OK"))
    box.exec()


# ============================================================================
# Settings
# ============================================================================
KEY_NAMES = ["Shift", "Ctrl", "Alt", "CapsLock", "None"]


# ============================================================================
# Make it yours: wheel layout, presets, chains, your own slices, where results go, export/import
# ============================================================================
WHEEL_TYPES = [("image", "Image"), ("video", "Video"), ("audio", "Audio"), ("pdf", "PDF"), ("document", "Document"),
               ("spreadsheet", "Spreadsheet"), ("slides", "Slides"), ("archive", "Archive"), ("ebook", "E-book"),
               ("comic", "Comic book"), ("font", "Font"), ("subtitle", "Subtitles"), ("folder", "Folder"),
               ("other", "Other")]
WHEEL_MODES = [("convert", "Convert"), ("tool", "Tools"), ("action", "Actions")]
OUTPUT_MODES = ["next", "folder", "replace", "clipboard"]


def _jload(key, default):
    try:
        v = json.loads(settings().value(key, "") or "null")
        return default if v is None else v
    except (TypeError, ValueError):
        return default


def custom_slices() -> list:
    return _jload("custom_slices", [])


def save_custom_slices(lst):
    settings().setValue("custom_slices", json.dumps(lst, ensure_ascii=False))


def my_slices_file() -> Path:
    return Path(engine.models_dir()).parent / "my-slices.json"


MY_SLICES_TEMPLATE = """// Your own slices for the Actions wheel. Save this file and they appear right away.
// "for": image, video, audio, pdf, document, spreadsheet, slides, archive, ebook, comic, font, subtitle, folder, other
//        or "*" for everything. "each": true runs the command once per file.
// In "command" you can use {file}, {files} (all of them, quoted), {folder}, {name}, {stem}, {ext}.
// Lines starting with // are ignored.
[
  {
    "name": "Open in Paint",
    "for": ["image"],
    "command": "mspaint.exe \\"{file}\\"",
    "each": true
  },
  {
    "name": "Notepad",
    "for": ["document", "subtitle", "other"],
    "command": "notepad.exe \\"{file}\\"",
    "each": true
  }
]
"""


def load_my_slices() -> list:
    f = my_slices_file()
    try:
        text = f.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    try:
        data = json.loads(text)
        return [d for d in data if isinstance(d, dict) and d.get("name") and d.get("command")]
    except ValueError as e:
        winsys.log(f"my-slices.json: {e}")
        return []


def run_my_slice(spec, paths):
    import shlex  # noqa: F401  (quoting is done by hand for Windows)
    import subprocess

    def fill(cmd, files):
        f = Path(files[0])
        return (cmd.replace("{files}", " ".join(f'"{x}"' for x in files)).replace("{file}", str(f))
                .replace("{folder}", str(f.parent)).replace("{name}", f.name).replace("{stem}", f.stem)
                .replace("{ext}", f.suffix.lstrip(".")))
    groups = [[p] for p in paths] if spec.get("each", True) else [paths]
    for g in groups:
        cmd = fill(spec["command"], g)
        winsys.log(f"my slice '{spec['name']}': {cmd}")
        subprocess.Popen(cmd, cwd=str(Path(g[0]).parent), shell=True)


def wheel_layout() -> dict:
    return _jload("wheel_layout", {})


def apply_wheel_layout(mode, category, ops):
    """Your order and hidden slices for this wheel and file type."""
    lay = wheel_layout().get(f"{mode}/{category}")
    if not lay:
        return ops
    hidden = set(lay.get("hidden", []))
    order = {k: i for i, k in enumerate(lay.get("order", []))}
    kept = [o for o in ops if o.id not in hidden] or ops[:1]
    return sorted(kept, key=lambda o: order.get(o.id, 10_000 + ops.index(o)))


def custom_ops_for(mode, paths) -> list:
    """Your presets, chains and own commands that fit these files."""
    cat = engine.category_of(paths)
    out = []
    for spec in custom_slices():
        wheel = "tool" if spec.get("kind") == "chain" else "convert"
        if wheel != mode or spec.get("for", spec.get("kind")) not in (cat, "*"):
            continue
        try:
            op = engine.custom_op(spec, wheel)
            op.spec = spec
            out.append(op)
        except Exception as e:
            winsys.log(f"custom slice: {e}")
    if mode == "action":
        for i, spec in enumerate(load_my_slices()):
            fors = spec.get("for") or ["*"]
            fors = [fors] if isinstance(fors, str) else fors
            if "*" in fors or cat in fors:
                out.append(engine.Op(f"mine:{i}", "✎ " + spec["name"], lambda ps, p, s=spec: run_my_slice(s, ps),
                                     group="action", multi=True))
    return out


def watch_folders() -> list:
    return _jload("watch_folders", [])


def _watch_ops(cat, path=None):
    """What a watch folder can do with a file type: conversions, tools and your presets/chains that need
    no window (questions are answered with their usual defaults)."""
    if path:
        paths = [path]
    else:                                    # every target of the type: ask with two different examples
        seen, out = set(), []
        for ext in {"image": ("png", "jpg"), "video": ("mkv", "mp4"), "audio": ("wav", "mp3"),
                    "document": ("txt", "docx"), "subtitle": ("vtt", "srt")}.get(cat, ("",)):
            for m, o in _watch_ops(cat, engine._fake_path(cat, ext)):
                if (m, o.id) not in seen:
                    seen.add((m, o.id))
                    out.append((m, o))
        return out
    out = []
    for mode, ops in (("convert", engine.conversions(paths)), ("tool", engine.tools(paths))):
        for o in ops + custom_ops_for(mode, paths):
            if o.ui or o.id == "none":
                continue
            out.append((mode, o))
    return out


class FolderWatch(QObject):
    """Watch folders: a file that lands in a chosen folder is converted automatically; results go to a
    'Converted' folder inside it (so they are never picked up again)."""

    def __init__(self, app):
        super().__init__()
        from PySide6.QtCore import QFileSystemWatcher
        self.app = app
        self.fs = QFileSystemWatcher(self)
        self.fs.directoryChanged.connect(self._changed)
        self.known = {}          # folder -> set of names seen
        self.waiting = {}        # path -> (size, stable checks)
        self.done = set()
        self.timer = QTimer(self, interval=1000, timeout=self._check)
        self.reload()

    def reload(self):
        if self.fs.directories():
            self.fs.removePaths(self.fs.directories())
        self.rules = [r for r in watch_folders() if r.get("on", True) and os.path.isdir(r.get("folder", ""))]
        self.known = {}
        for r in self.rules:
            f = r["folder"]
            self.known[f] = self._names(f)
            self.fs.addPath(f)
        if self.rules:
            self.timer.start()                 # also catches changes the watcher misses (network drives)
        else:
            self.timer.stop()

    @staticmethod
    def _names(folder):
        try:
            return {e.name for e in os.scandir(folder) if e.is_file()}
        except OSError:
            return set()

    def _changed(self, folder):
        self._scan(folder)

    def _scan(self, folder):
        now = self._names(folder)
        new = now - self.known.get(folder, set())
        self.known[folder] = now
        for name in new:
            if name.lower().endswith((".part", ".crdownload", ".tmp", ".download")) or name.startswith(("~$", ".")):
                continue
            self.waiting[os.path.join(folder, name)] = (-1, 0)

    def _check(self):
        for r in self.rules:
            self._scan(r["folder"])
        for path, (size, n) in list(self.waiting.items()):
            try:
                now = os.path.getsize(path)
            except OSError:
                self.waiting.pop(path, None)
                continue
            if now == size and now > 0:
                n += 1
            else:
                n = 0
            if n >= 2:                         # same size for two seconds: finished copying
                self.waiting.pop(path, None)
                try:
                    with open(path, "rb"):
                        pass
                except OSError:
                    self.waiting[path] = (now, 0)
                    continue
                self._run(path)
            else:
                self.waiting[path] = (now, n)

    def _run(self, path):
        if path in self.done:
            return
        folder = os.path.dirname(path)
        cat = engine.category_of([path])
        for r in self.rules:
            if os.path.normcase(r["folder"]) != os.path.normcase(folder) or r.get("cat") not in (cat, "*"):
                continue
            ops = {o.id: (m, o) for m, o in _watch_ops(cat, path)}
            hit = ops.get(r.get("id"))
            if hit is None:
                winsys.log(f"watch folder: {r.get('label')} doesn't apply to {Path(path).name}")
                continue
            mode, op = hit
            if op.model and not engine.model_ready(op.model):
                continue
            self.done.add(path)
            out = Path(folder) / tr("Converted")
            out.mkdir(exist_ok=True)
            self.app.out_override[path] = str(out)
            params = {f: (d[0] if isinstance(d, (list, tuple)) and d else d) for f, d in (op.ask or [])}
            if getattr(op, "spec", None):
                params["_spec"] = op.spec
            winsys.log(f"watch folder: {op.id} on {Path(path).name}")
            if op.group == "action":
                try:
                    op.fn([path], params)
                except Exception as e:
                    winsys.log(f"watch folder action: {e}")
            else:
                self.app._start(op, [path], params)


class WatchRuleDialog(QDialog):
    """Add a watch folder: which folder, which files, what to do."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP} — " + tr("Watch a folder"))
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        form = QFormLayout(self)
        row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setMinimumWidth(320)
        row.addWidget(self.folder, 1)
        b = QPushButton(tr("Choose…"))
        b.clicked.connect(self._pick)
        row.addWidget(b)
        form.addRow(tr("Folder"), row)
        self.kind = QComboBox()
        for k, label in WHEEL_TYPES:
            if k != "folder":
                self.kind.addItem(tr(label), k)
        form.addRow(tr("When this arrives"), self.kind)
        self.op = QComboBox()
        form.addRow(tr("Do this"), self.op)
        note = QLabel(tr("Results go to a “Converted” folder inside it. Files already there are left alone."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        form.addRow(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.kind.currentIndexChanged.connect(self._fill)
        self._fill()
        self.rule = None

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, tr("Pick a folder"), self.folder.text() or str(Path.home()))
        if d:
            self.folder.setText(str(Path(d)))

    def _fill(self):
        self.op.clear()
        for mode, o in _watch_ops(self.kind.currentData()):
            label = tr("Convert to {fmt}", fmt=tr(o.label)) if mode == "convert" and not o.id.startswith("custom:") else tr(o.label)
            self.op.addItem(label.rstrip("…"), (mode, o.id))

    def _ok(self):
        f = self.folder.text().strip()
        if not f or not os.path.isdir(f) or self.op.currentData() is None:
            self.folder.setFocus()
            return
        mode, oid = self.op.currentData()
        self.rule = {"folder": f, "cat": self.kind.currentData(), "mode": mode, "id": oid,
                     "label": self.op.currentText(), "on": True}
        self.accept()


class WheelPreview(QLabel):
    """The wheel as it will look, drawn by the real Wheel (never shown on its own)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wheel = Wheel(_APP)
        self.wheel._style = "none"
        self.setMinimumSize(300, 330)
        self.setAlignment(Qt.AlignCenter)

    def show_ops(self, mode, paths, ops, hover=-1):
        w = self.wheel
        w.mode, w.paths = mode, paths
        w.ops = ops or [engine.Op("none", "No conversions" if mode == "convert" else "No tools", lambda *a: None)]
        w.hover = hover if ops else -1
        w._t = 1.0
        img = w.grab()
        dpr = self.devicePixelRatioF() or 1.0
        side = min(self.width(), self.height()) * dpr
        pm = img.scaled(int(side), int(side), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        self.setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.wheel.ops:
            self.show_ops(self.wheel.mode, self.wheel.paths, self.wheel.ops, self.wheel.hover)


class WheelLayoutDialog(QDialog):
    """Pick which slices show on a wheel for a file type, and their order (drag to reorder)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QListWidget, QAbstractItemView
        self.setWindowTitle(f"{APP} — " + tr("Wheel slices"))
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.resize(820, 580)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.mode = QComboBox()
        for k, label in WHEEL_MODES:
            self.mode.addItem(tr(label), k)
        self.kind = QComboBox()
        for k, label in WHEEL_TYPES:
            self.kind.addItem(tr(label), k)
        row.addWidget(QLabel(tr("Wheel")))
        row.addWidget(self.mode, 1)
        row.addWidget(QLabel(tr("For")))
        row.addWidget(self.kind, 1)
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        self.preview = WheelPreview()
        body.addWidget(self.preview, 1)
        lay.addLayout(body, 1)
        self._ops_now = []
        self._redraw = QTimer(self, singleShot=True, interval=0, timeout=self._update_preview)
        self.list.model().rowsMoved.connect(lambda *a: self._redraw.start())
        self.list.itemChanged.connect(lambda *a: self._redraw.start())
        self.list.currentRowChanged.connect(lambda *a: self._redraw.start())
        hint = QLabel(tr("Untick a slice to hide it. Drag to change the order — the first ones go at the top of the wheel."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        bb.button(QDialogButtonBox.Ok).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.button(QDialogButtonBox.Reset).setText(tr("Reset this wheel"))
        bb.accepted.connect(self._save_and_close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Reset).clicked.connect(self._reset)
        lay.addWidget(bb)
        self.layouts = wheel_layout()
        self._key = None
        self.mode.currentIndexChanged.connect(self._load)
        self.kind.currentIndexChanged.connect(self._load)
        self._load()

    def _ops(self, mode, cat):
        paths = [engine._fake_path(cat)] if cat not in ("folder",) else ["C:/example/folder"]
        if mode == "convert":
            ops = engine.conversions(paths)
        elif mode == "tool":
            ops = engine.tools(paths)
        else:
            ops = _APP.actions.ops(paths) if _APP is not None else []
        if _APP is not None:
            ops = ops + [o for o in custom_ops_for(mode, paths) if not o.id.startswith("mine:")]
        return ops

    def _store(self):
        if self._key is None:
            return
        order, hidden = [], []
        for i in range(self.list.count()):
            it = self.list.item(i)
            order.append(it.data(Qt.UserRole))
            if it.checkState() != Qt.Checked:
                hidden.append(it.data(Qt.UserRole))
        self.layouts[self._key] = {"order": order, "hidden": hidden}

    def _load(self):
        from PySide6.QtWidgets import QListWidgetItem
        self._store()
        mode, cat = self.mode.currentData(), self.kind.currentData()
        self._key = f"{mode}/{cat}"
        lay = self.layouts.get(self._key, {})
        hidden = set(lay.get("hidden", []))
        order = {k: i for i, k in enumerate(lay.get("order", []))}
        ops = self._ops(mode, cat)
        ops = sorted(ops, key=lambda o: order.get(o.id, 10_000 + ops.index(o)))
        self._ops_now = ops
        self.list.blockSignals(True)
        self.list.clear()
        for o in ops:
            it = QListWidgetItem(tr(o.label) + (f"   ·  {tr(o.hint)}" if o.hint else ""))
            it.setData(Qt.UserRole, o.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            it.setCheckState(Qt.Unchecked if o.id in hidden else Qt.Checked)
            self.list.addItem(it)
        self.list.blockSignals(False)
        self._redraw.start()

    def _update_preview(self):
        by_id = {o.id: o for o in self._ops_now}
        shown, hover = [], -1
        cur = self.list.currentRow()
        for i in range(self.list.count()):
            it = self.list.item(i)
            o = by_id.get(it.data(Qt.UserRole))
            if o is None or it.checkState() != Qt.Checked:
                continue
            if i == cur:
                hover = len(shown)
            shown.append(o)
        cat = self.kind.currentData()
        paths = [engine._fake_path(cat)] if cat != "folder" else ["C:/example/folder"]
        self.preview.show_ops(self.mode.currentData(), paths, shown, hover)

    def _reset(self):
        self.layouts.pop(self._key, None)
        self._key = None
        self._load()

    def _save_and_close(self):
        self._store()
        settings().setValue("wheel_layout", json.dumps({k: v for k, v in self.layouts.items() if v.get("hidden") or v.get("order")}))
        self.accept()


class PresetDialog(QDialog):
    """Make or edit an image or video preset (one slice in the Convert wheel)."""

    def __init__(self, kind, spec=None, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QSlider, QSpinBox
        self.kind = kind
        spec = dict(spec or {})
        self.setWindowTitle(f"{APP} — " + (tr("Image preset") if kind == "image" else tr("Video preset")))
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        form = QFormLayout(self)
        self.name = QLineEdit(spec.get("name", ""))
        self.name.setPlaceholderText(tr("e.g. For the web"))
        form.addRow(tr("Name"), self.name)
        self.fmt = QComboBox()
        for f in (engine.PRESET_IMAGE_FORMATS if kind == "image" else engine.PRESET_VIDEO_FORMATS):
            self.fmt.addItem(f.upper(), f)
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(spec.get("format"))))
        form.addRow(tr("Format"), self.fmt)
        self.q = QSlider(Qt.Horizontal)
        self.q.setRange(10, 100)
        self.q.setValue(int(spec.get("quality", 80 if kind == "image" else 70)))
        ql = QLabel(str(self.q.value()))
        self.q.valueChanged.connect(lambda v: ql.setText(str(v)))
        qrow = QHBoxLayout()
        qrow.addWidget(self.q, 1)
        qrow.addWidget(ql)
        form.addRow(tr("Quality"), qrow)
        if kind == "image":
            self.size = QSpinBox()
            self.size.setRange(0, 20000)
            self.size.setSingleStep(100)
            self.size.setSpecialValueText(tr("Keep the size"))
            self.size.setSuffix(" px")
            self.size.setValue(int(spec.get("max_side", 1920)))
            form.addRow(tr("Longest side at most"), self.size)
            self.strip = QCheckBox(tr("Remove photo details (location, camera…)"))
            self.strip.setChecked(bool(spec.get("strip", True)))
            form.addRow("", self.strip)
        else:
            self.height = QComboBox()
            for h in engine.PRESET_VIDEO_HEIGHTS:
                self.height.addItem(tr("Keep the size") if h == 0 else f"{h}p", h)
            self.height.setCurrentIndex(max(0, self.height.findData(int(spec.get("max_height", 1080)))))
            form.addRow(tr("Picture size at most"), self.height)
            self.mute = QCheckBox(tr("Remove the sound"))
            self.mute.setChecked(bool(spec.get("mute", False)))
            form.addRow("", self.mute)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.uid = spec.get("uid")

    def spec(self):
        import uuid
        s = {"uid": self.uid or uuid.uuid4().hex[:8], "kind": self.kind, "for": self.kind,
             "name": self.name.text().strip() or tr("Preset"), "format": self.fmt.currentData(), "quality": self.q.value()}
        if self.kind == "image":
            s.update(max_side=self.size.value(), strip=self.strip.isChecked())
            s["hint"] = f"{s['format'].upper()} · {s['quality']}" + (f" · ≤{s['max_side']}px" if s["max_side"] else "")
        else:
            s.update(max_height=self.height.currentData(), mute=self.mute.isChecked())
            s["hint"] = f"{s['format'].upper()}" + (f" · {s['max_height']}p" if s["max_height"] else "")
        return s


class ChainDialog(QDialog):
    """Make a chain: several steps that run one after another as one slice in the Tools wheel."""

    def __init__(self, spec=None, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QListWidget
        spec = dict(spec or {})
        self.setWindowTitle(f"{APP} — " + tr("Chain"))
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.resize(520, 520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(spec.get("name", ""))
        self.name.setPlaceholderText(tr("e.g. Resize, WebP and ZIP"))
        form.addRow(tr("Name"), self.name)
        self.kind = QComboBox()
        for k, label in WHEEL_TYPES:
            if k not in ("folder", "other"):
                self.kind.addItem(tr(label), k)
        self.kind.setCurrentIndex(max(0, self.kind.findData(spec.get("for", "image"))))
        form.addRow(tr("For"), self.kind)
        lay.addLayout(form)
        lay.addWidget(QLabel("<b>" + tr("Steps") + "</b>"))
        self.steps_view = QListWidget()
        lay.addWidget(self.steps_view, 1)
        add = QHBoxLayout()
        self.next_op = QComboBox()
        add.addWidget(self.next_op, 1)
        self.params_box = QWidget()
        self.params_lay = QFormLayout(self.params_box)
        self.params_lay.setContentsMargins(0, 0, 0, 0)
        b_add = QPushButton(tr("Add step"))
        b_add.clicked.connect(self._add)
        add.addWidget(b_add)
        lay.addLayout(add)
        lay.addWidget(self.params_box)
        row = QHBoxLayout()
        b_del = QPushButton(tr("Remove last step"))
        b_del.clicked.connect(self._remove_last)
        row.addWidget(b_del)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.uid = spec.get("uid")
        self.steps = list(spec.get("steps") or [])
        self.kind.currentIndexChanged.connect(lambda _i: (self.steps.clear(), self._refresh()))
        self.next_op.currentIndexChanged.connect(self._show_params)
        self._refresh()

    def _ext_now(self):
        ext = engine._fake_path(self.kind.currentData()).rsplit(".", 1)[1]
        for st in self.steps:
            op = next((o for o in engine.chain_step_ops(ext) if o.id == st["id"] and o.group == st["group"]), None)
            if op is not None:
                ext = engine._step_ext(ext, op)
        return ext

    def _refresh(self):
        self.steps_view.clear()
        for i, st in enumerate(self.steps, 1):
            extra = ", ".join(f"{tr(k)}: {tr(v)}" for k, v in (st.get("params") or {}).items())
            self.steps_view.addItem(f"{i}.  {tr(st['label'])}" + (f"  ({extra})" if extra else ""))
        self.ops_now = engine.chain_step_ops(self._ext_now())
        self.next_op.blockSignals(True)
        self.next_op.clear()
        for o in self.ops_now:
            self.next_op.addItem((tr("Convert to {fmt}", fmt=tr(o.label)) if o.group == "convert" else tr(o.label)), o.id + "|" + o.group)
        self.next_op.blockSignals(False)
        self._show_params()

    def _show_params(self, *_):
        while self.params_lay.rowCount():
            self.params_lay.removeRow(0)
        self.param_edits = {}
        op = self._current()
        if op is None:
            return
        for name, default in op.ask:
            if isinstance(default, (list, tuple)):
                w = QComboBox()
                for opt in default:
                    w.addItem(tr(opt), opt)
            else:
                w = QLineEdit(str(default))
                if name == "Password":
                    w.setEchoMode(QLineEdit.Password)
            self.params_lay.addRow(tr(name), w)
            self.param_edits[name] = w

    def _current(self):
        key = self.next_op.currentData()
        if not key:
            return None
        oid, grp = key.split("|")
        return next((o for o in self.ops_now if o.id == oid and o.group == grp), None)

    def _add(self):
        op = self._current()
        if op is None:
            return
        params = {k: (w.currentData() if isinstance(w, QComboBox) else w.text()) for k, w in self.param_edits.items()}
        self.steps.append({"group": op.group, "id": op.id, "label": op.label if op.group != "convert" else
                           f"Convert to {op.label}", "params": params})
        self._refresh()

    def _remove_last(self):
        if self.steps:
            self.steps.pop()
            self._refresh()

    def _ok(self):
        if len(self.steps) < 2:
            QMessageBox.information(self, APP, tr("A chain needs at least two steps."))
            return
        self.accept()

    def spec(self):
        import uuid
        return {"uid": self.uid or uuid.uuid4().hex[:8], "kind": "chain", "for": self.kind.currentData(),
                "name": self.name.text().strip() or tr("Chain"), "steps": self.steps,
                "hint": " → ".join(tr(s["label"]).replace("…", "") for s in self.steps)[:60]}


def export_settings(path):
    s = settings()
    data = {"app": APP, "version": VERSION, "settings": {k: s.value(k) for k in s.allKeys()
                                                        if not k.startswith(("float_resume", "last_update", "geometry"))}}
    try:
        data["my_slices"] = my_slices_file().read_text(encoding="utf-8")
    except OSError:
        pass
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def import_settings(path) -> int:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("app") != APP or "settings" not in data:
        raise ValueError(tr("This isn't a DragWheel settings file."))
    s = settings()
    for k, v in data["settings"].items():
        s.setValue(k, v)
    if data.get("my_slices"):
        my_slices_file().parent.mkdir(parents=True, exist_ok=True)
        my_slices_file().write_text(data["my_slices"], encoding="utf-8")
    s.sync()
    return len(data["settings"])


class SettingsDialog(QDialog):
    """Changing the language applies immediately (the window rebuilds itself in the new
    language, keeping unsaved edits). Cancel switches the language back."""

    def __init__(self, app: "DragWheelApp"):
        super().__init__(None)
        self.app = app
        self.setWindowIcon(app_icon())
        self.setMinimumWidth(660)
        self.orig_lang = settings().value("language", "")
        self.orig_theme = theme.mode()
        self.tabs = None
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(0, 0, 0, 0)
        self.body = None
        self._build(None)

    # ------------------------------------------------------------------ state
    def _state(self) -> dict:
        return {
            "keys": {m: cb.currentData() for m, cb in self.key_boxes.items()},
            "detect": self.detect.currentIndex(),
            "scroll": self.scroll.isChecked(),
            "out": self.out.text(),
            "out_mode": self.out_mode.currentData(),
            "startup": self.startup.isChecked(),
            "menu": self.menu.isChecked(),
            "hotkey": self.hotkey.isChecked(),
            "auto_update": self.auto_update.isChecked(),
            "autoplay": self.autoplay.isChecked(),
            "on_top": self.on_top.isChecked(),
            "ctrl_open": self.ctrl_open.isChecked(),
            "media_osd": self.media_osd.isChecked(),
            "anim": self.anim.currentData(),
            "anim_speed": self.anim_speed.value(),
            "shake": self.shake.isChecked(),
            "tour_start": self.tour_start.isChecked(),
            "cursor_busy": self.cursor_busy.isChecked(),
            "tick_sound": self.tick_sound.isChecked(),
            "tick_volume": self.tick_volume.value(),
            "crash_reports": self.crash_reports.isChecked(),
            "job_mode": self.job_mode.currentData(),
            "link_stops": self.link_stops.isChecked(),
            "peek": self.peek.isChecked(),
            "finish_anim": self.finish_anim.isChecked(),
            "finish_sound": self.finish_sound.isChecked(),
            "full_menu": self.full_menu.isChecked() if self.full_menu is not None else False,
            "media_osd_when": self.media_osd_when.currentData(),
        }

    def _initial(self) -> dict:
        s = settings()
        return {
            "keys": mode_keys(),
            "detect": int(s.value("detect_any", 0)),
            "scroll": s.value("scroll", "true") == "true",
            "out": s.value("output_dir", ""),
            "out_mode": s.value("output_mode", "folder" if s.value("output_dir", "") else "next"),
            "startup": winsys.startup_enabled(),
            "menu": winsys.context_menu_enabled(),
            "hotkey": s.value("hotkey", "true") == "true",
            "auto_update": s.value("check_updates", "true") == "true",
            "autoplay": s.value("float_autoplay", "true") == "true",
            "on_top": s.value("float_on_top", "true") == "true",
            "ctrl_open": s.value("float_ctrl_open", "true") == "true",
            "media_osd": s.value("media_osd", "true") == "true",
            "anim": wheel_anim(),
            "anim_speed": int(round(anim_speed() * 100)),
            "shake": s.value("shake", "true") == "true",
            "tour_start": s.value("tour_at_start", "true") == "true",
            "cursor_busy": s.value("cursor_busy", "true") == "true",
            "tick_sound": s.value("tick_sound", "true") == "true",
            "tick_volume": int(s.value("tick_volume", 70)),
            "crash_reports": s.value("crash_reports", "false") == "true",
            "job_mode": s.value("job_mode", "queue"),
            "link_stops": s.value("float_link_stops", "true") == "true",
            "peek": s.value("peek", "true") == "true",
            "finish_anim": s.value("finish_anim", "true") == "true",
            "finish_sound": s.value("finish_sound", "true") == "true",
            "full_menu": winsys.full_menu_enabled(),
            "media_osd_when": s.value("media_osd_when", "unfocused"),
        }

    def _theme_changed(self, _idx):
        code = self.theme_box.currentData()
        if code == theme.mode():
            return
        state = self._state()
        cover = self._freeze()
        settings().setValue("theme", code)
        self.app.apply_theme()
        QTimer.singleShot(0, lambda: self._rebuild_under(cover, state))

    def _language_changed(self, _idx):
        code = self.lang.currentData()
        if code == settings().value("language", ""):
            return
        state = self._state()
        cover = self._freeze()                               # a picture of the old look stays on top…
        settings().setValue("language", code)
        self.app.apply_language()
        QTimer.singleShot(0, lambda: self._rebuild_under(cover, state))     # rebuild outside the combo's signal

    def _freeze(self):
        """Cover the window with a still picture of itself, so a rebuild underneath never flickers."""
        from PySide6.QtWidgets import QLabel
        pm = self.grab()
        cover = QLabel(self)
        cover.setPixmap(pm)
        cover.setGeometry(0, 0, pm.width(), pm.height())
        cover.setAttribute(Qt.WA_TransparentForMouseEvents)
        cover.show()
        cover.raise_()
        return cover

    def _rebuild_under(self, cover, state):
        """…the new language or theme is built under it, then the picture fades away."""
        from PySide6.QtWidgets import QGraphicsOpacityEffect
        self.setUpdatesEnabled(False)
        try:
            self._build(state)
        finally:
            cover.raise_()
            self.setUpdatesEnabled(True)
        fx = QGraphicsOpacityEffect(cover)
        fx.setOpacity(1.0)
        cover.setGraphicsEffect(fx)
        anim = QPropertyAnimation(fx, b"opacity", cover)
        anim.setDuration(int(260 / anim_speed()))
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.finished.connect(cover.deleteLater)
        QTimer.singleShot(30, anim.start)                     # once the new page has painted

    def reject(self):
        if settings().value("language", "") != self.orig_lang:   # Cancel undoes a language switch
            settings().setValue("language", self.orig_lang)
            self.app.apply_language()
        if theme.mode() != self.orig_theme:                       # …and a theme switch
            settings().setValue("theme", self.orig_theme)
            self.app.apply_theme()
        super().reject()

    # ------------------------------------------------------------------ UI
    def _build(self, state):
        st = state or self._initial()
        self.setWindowTitle(tr("{app} Settings", app=APP))
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
        keep_tab = self.tabs.currentIndex() if getattr(self, "tabs", None) is not None else 0
        if self.body is not None:
            self.outer.removeWidget(self.body)
            self.body.deleteLater()
        self.body = QWidget(self)
        self.body.setObjectName("page")
        self.outer.addWidget(self.body)
        root = QVBoxLayout(self.body)
        root.setContentsMargins(12, 8, 12, 12)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        def scroll(page):                          # long tabs scroll instead of growing past the screen
            from PySide6.QtWidgets import QScrollArea
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            area.setWidget(page)
            area.setStyleSheet("QScrollArea{background:transparent}")
            area.viewport().setAutoFillBackground(False)
            return area
        self.tabs.addTab(scroll(self._settings_tab(st)), tr("Settings"))
        self.tabs.addTab(scroll(self._everyday_tab(st)), tr("Everyday"))
        self.tabs.addTab(scroll(self._mine_tab()), tr("Make it yours"))
        self.tabs.addTab(scroll(self._about_tab(st)), tr("About"))
        self.tabs.setCurrentIndex(keep_tab)
        root.addWidget(self.tabs)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.button(QDialogButtonBox.Save).setDefault(True)
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self.adjustSize()
        scr = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        widest = max(self.tabs.widget(i).widget().sizeHint().width() for i in range(self.tabs.count()))
        self.resize(min(scr.width() - 40, max(self.width(), widest + 60)), min(scr.height() - 80, 760))

    # ---- Settings tab
    def _settings_tab(self, st):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 6, 2, 2)

        g0 = QGroupBox(tr("Appearance"))
        f0 = QFormLayout(g0)
        self.lang = QComboBox()
        self.lang.addItem(tr("System default"), "")
        for code, native in i18n.LANGUAGES:
            self.lang.addItem(native, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(settings().value("language", ""))))
        self.lang.currentIndexChanged.connect(self._language_changed)
        f0.addRow(tr("App language"), self.lang)
        self.theme_box = QComboBox()
        for code, label in (("system", tr("System default")), ("dark", tr("Dark")), ("light", tr("Light")),
                            ("contrast", tr("High contrast"))):
            self.theme_box.addItem(label, code)
        self.theme_box.setCurrentIndex(max(0, self.theme_box.findData(theme.mode())))
        self.theme_box.currentIndexChanged.connect(self._theme_changed)
        f0.addRow(tr("Theme"), self.theme_box)
        lay.addWidget(g0)

        g1 = QGroupBox(tr("Wheel keys — tap while dragging a file"))
        f1 = QFormLayout(g1)
        self.key_boxes = {}
        for m in MODES:
            cb = QComboBox()
            for k in KEY_NAMES:
                cb.addItem(tr(k), k)
            cb.setCurrentIndex(KEY_NAMES.index(st["keys"][m]))
            f1.addRow(tr(MODE_LABEL[m]), cb)
            self.key_boxes[m] = cb
        self.detect = QComboBox()
        self.detect.addItems([tr("File drags only (recommended)"), tr("Any mouse drag")])
        self.detect.setCurrentIndex(st["detect"])
        f1.addRow(tr("Trigger on"), self.detect)
        self.scroll = QCheckBox(tr("Scroll the mouse wheel while dragging to open the wheel and move between slices"))
        self.scroll.setChecked(st["scroll"])
        f1.addRow(self.scroll)
        self.anim = QComboBox()
        for k, label in WHEEL_ANIMS:
            self.anim.addItem(tr(label), k)
        self.anim.setCurrentIndex(max(0, self.anim.findData(st["anim"])))
        from PySide6.QtWidgets import QSlider
        arow = QHBoxLayout()
        arow.addWidget(self.anim)
        arow.addSpacing(12)
        arow.addWidget(QLabel(tr("Speed")))
        self.anim_speed = QSlider(Qt.Horizontal)
        self.anim_speed.setRange(25, 250)
        self.anim_speed.setSingleStep(5)
        self.anim_speed.setPageStep(25)
        self.anim_speed.setValue(st["anim_speed"])
        self.anim_speed.setFixedWidth(150)
        self.anim_speed_lbl = QLabel()
        self.anim_speed_lbl.setMinimumWidth(44)

        def speed_label(v):
            self.anim_speed_lbl.setText(f"{v / 100:.2g}×")
        speed_label(self.anim_speed.value())
        self.anim_speed.valueChanged.connect(speed_label)
        self.anim.currentIndexChanged.connect(lambda _i: self.anim_speed.setEnabled(self.anim.currentData() != "none"))
        self.anim_speed.setEnabled(st["anim"] != "none")
        arow.addWidget(self.anim_speed)
        arow.addWidget(self.anim_speed_lbl)
        arow.addStretch(1)
        f1.addRow(tr("Animations"), arow)
        lay.addWidget(g1)

        g2 = QGroupBox(tr("Output"))
        f2 = QFormLayout(g2)
        self.out_mode = QComboBox()
        for key, label in (("next", tr("Next to the original file")), ("folder", tr("In this folder")),
                           ("replace", tr("Replace the original (asks first)")), ("clipboard", tr("Copy to the clipboard"))):
            self.out_mode.addItem(label, key)
        self.out_mode.setCurrentIndex(max(0, self.out_mode.findData(st.get("out_mode", "next"))))
        f2.addRow(tr("Results go"), self.out_mode)
        row = QHBoxLayout()
        self.out = QLineEdit(st["out"])
        self.out.setPlaceholderText(tr("Pick a folder"))
        b = QPushButton(tr("Browse…"))
        b.clicked.connect(lambda: self.out.setText(QFileDialog.getExistingDirectory(self, tr("Output folder")) or self.out.text()))
        row.addWidget(self.out, 1)
        row.addWidget(b)
        self.out_row = QWidget()
        self.out_row.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        f2.addRow("", self.out_row)
        self.out_row.setVisible(self.out_mode.currentData() == "folder")
        self.out_mode.currentIndexChanged.connect(lambda _i: self.out_row.setVisible(self.out_mode.currentData() == "folder"))
        lay.addWidget(g2)

        gf = QGroupBox(tr("Float"))
        vf = QVBoxLayout(gf)
        self.autoplay = QCheckBox(tr("Play videos and music as soon as they open in Float"))
        self.autoplay.setChecked(st["autoplay"])
        vf.addWidget(self.autoplay)
        self.on_top = QCheckBox(tr("Keep floats on top of other windows"))
        self.on_top.setChecked(st["on_top"])
        vf.addWidget(self.on_top)
        self.ctrl_open = QCheckBox(tr("Hold Ctrl and double-click a file, or press Ctrl+Enter, to open it in Float"))
        self.ctrl_open.setChecked(st["ctrl_open"])
        vf.addWidget(self.ctrl_open)
        self.link_stops = QCheckBox(tr("When a float plays a new link, stop what it was playing until the link is ready"))
        self.link_stops.setChecked(st["link_stops"])
        vf.addWidget(self.link_stops)
        self.media_osd = QCheckBox(tr("Show a big sign on screen (play, pause, next, volume…) when the keyboard's media keys control a float"))
        self.media_osd.setChecked(st["media_osd"])
        vf.addWidget(self.media_osd)
        self.media_osd_when = QComboBox()
        self.media_osd_when.addItem(tr("Only when the float isn't in focus"), "unfocused")
        self.media_osd_when.addItem(tr("All the time"), "always")
        self.media_osd_when.setCurrentIndex(max(0, self.media_osd_when.findData(st["media_osd_when"])))
        self.media_osd_when.setEnabled(st["media_osd"])
        self.media_osd.toggled.connect(self.media_osd_when.setEnabled)
        row = QHBoxLayout()
        row.setContentsMargins(24, 0, 0, 0)
        row.addWidget(self.media_osd_when)
        row.addStretch(1)
        vf.addLayout(row)
        lay.addWidget(gf)

        g3 = QGroupBox("Windows")
        v3 = QVBoxLayout(g3)
        self.startup = QCheckBox(tr("Start {app} when I sign in", app=APP))
        self.startup.setChecked(st["startup"])
        self.menu = QCheckBox(tr("Add {app} to the Explorer right-click menu and Send To", app=APP))
        self.menu.setChecked(st["menu"])
        self.hotkey = QCheckBox(tr("Ctrl + Alt + Space opens the wheel for files selected in Explorer"))
        self.hotkey.setChecked(st["hotkey"])
        for w in (self.startup, self.menu, self.hotkey):
            v3.addWidget(w)
        lay.addWidget(g3)
        lay.addStretch(1)
        return page

    # ---- About tab
    # ---- Everyday tab
    def _everyday_tab(self, st):
        from PySide6.QtWidgets import QListWidget
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 6, 2, 2)
        g = QGroupBox(tr("While dragging a file"))
        v = QVBoxLayout(g)
        self.shake = QCheckBox(tr("Shake the mouse to open the wheel (instead of tapping a key)"))
        self.shake.setChecked(st["shake"])
        v.addWidget(self.shake)
        self.peek = QCheckBox(tr("Tap Space to peek at the file"))
        self.peek.setChecked(st["peek"])
        v.addWidget(self.peek)
        lay.addWidget(g)

        g = QGroupBox(tr("When a job finishes"))
        v = QVBoxLayout(g)
        self.finish_anim = QCheckBox(tr("Animate the tick on the notification"))
        self.finish_anim.setChecked(st["finish_anim"])
        v.addWidget(self.finish_anim)
        self.finish_sound = QCheckBox(tr("Play notification sounds"))
        self.finish_sound.setChecked(st["finish_sound"])
        v.addWidget(self.finish_sound)
        from PySide6.QtWidgets import QSlider
        row = QHBoxLayout()
        self.tick_sound = QCheckBox(tr("Click sounds on the wheel (moving and choosing)"))
        self.tick_sound.setChecked(st["tick_sound"])
        row.addWidget(self.tick_sound)
        row.addSpacing(12)
        row.addWidget(QLabel(tr("Volume")))
        self.tick_volume = QSlider(Qt.Horizontal)
        self.tick_volume.setRange(0, 100)
        self.tick_volume.setValue(st["tick_volume"])
        self.tick_volume.setFixedWidth(160)
        self.tick_volume.setEnabled(st["tick_sound"])
        self.tick_sound.toggled.connect(self.tick_volume.setEnabled)

        def try_tick():                            # hear it while you choose
            settings().setValue("tick_volume", self.tick_volume.value())
            play_tick(force=True)
        self.tick_volume.sliderReleased.connect(try_tick)
        self.tick_volume.valueChanged.connect(lambda _v: None if self.tick_volume.isSliderDown() else try_tick())
        row.addWidget(self.tick_volume)
        row.addStretch(1)
        v.addLayout(row)
        lay.addWidget(g)

        g = QGroupBox(tr("While DragWheel is working"))
        v = QVBoxLayout(g)
        self.cursor_busy = QCheckBox(tr("Show a small spinning circle next to the mouse pointer"))
        self.cursor_busy.setChecked(st["cursor_busy"])
        v.addWidget(self.cursor_busy)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Several jobs")))
        self.job_mode = QComboBox()
        self.job_mode.addItem(tr("One after another (a queue)"), "queue")
        self.job_mode.addItem(tr("All at the same time"), "parallel")
        self.job_mode.setCurrentIndex(max(0, self.job_mode.findData(st["job_mode"])))
        row.addWidget(self.job_mode, 1)
        v.addLayout(row)
        lay.addWidget(g)

        g = QGroupBox(tr("Watch folders"))
        v = QVBoxLayout(g)
        lbl = QLabel(tr("Anything that lands in these folders is converted by itself, e.g. every HEIC photo in Downloads becomes a JPG."))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        self.watch_list = QListWidget()
        self.watch_list.setMinimumHeight(70)
        self.watch_list.setMaximumHeight(130)
        v.addWidget(self.watch_list)
        row = QHBoxLayout()
        b = QPushButton(tr("Add…"))
        b.clicked.connect(self._add_watch)
        row.addWidget(b)
        b = QPushButton(tr("Remove"))
        b.clicked.connect(self._remove_watch)
        row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        lay.addWidget(g)
        self._fill_watch()

        if winsys.windows_11():
            g = QGroupBox(tr("Windows right-click menu"))
            v = QVBoxLayout(g)
            self.full_menu = QCheckBox(tr("Show the full menu straight away (no “Show more options”)"))
            self.full_menu.setChecked(st["full_menu"])
            v.addWidget(self.full_menu)
            lbl = QLabel(tr("Windows 11 hides DragWheel and other apps under “Show more options”. This turns on Windows' own "
                            "full menu for your account (like Windows 10). Explorer restarts to apply it."))
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
            v.addWidget(lbl)
            lay.addWidget(g)
        else:
            self.full_menu = None

        g = QGroupBox(tr("Command line"))
        v = QVBoxLayout(g)
        lbl = QLabel(tr("Use DragWheel in Command Prompt or in your own scripts, e.g. "
                        "<b>dragwheel convert photo.heic --to jpg</b>. The button opens a Command Prompt in Downloads "
                        "with the list of commands."))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        b = QPushButton(tr("Open a Command Prompt"))
        b.clicked.connect(winsys.open_cli_window)
        v.addWidget(b, 0, Qt.AlignLeft)
        lay.addWidget(g)

        g = QGroupBox(tr("Help"))
        v = QVBoxLayout(g)
        row = QHBoxLayout()
        self.tour_start = QCheckBox(tr("Show the welcome tour every time DragWheel starts"))
        self.tour_start.setChecked(st["tour_start"])
        row.addWidget(self.tour_start)
        row.addStretch(1)
        b = QPushButton(tr("Show the quick tour again"))
        b.clicked.connect(lambda: self.app.show_tour(parent=self))
        row.addWidget(b)
        v.addLayout(row)
        self.crash_reports = QCheckBox(tr("When something goes wrong, offer to send a crash report (you see it first)"))
        self.crash_reports.setChecked(st["crash_reports"])
        v.addWidget(self.crash_reports)
        lay.addWidget(g)
        lay.addStretch(1)
        return page

    def _fill_watch(self):
        self.watch_list.clear()
        for r in watch_folders():
            kind = dict(WHEEL_TYPES).get(r.get("cat"), r.get("cat", ""))
            self.watch_list.addItem(f"{r.get('folder')}   ·   {tr(kind)} → {r.get('label')}")

    def _add_watch(self):
        d = WatchRuleDialog(self)
        if d.exec() == QDialog.Accepted and d.rule:
            rules = watch_folders() + [d.rule]
            settings().setValue("watch_folders", json.dumps(rules, ensure_ascii=False))
            self._fill_watch()
            self.app.watch.reload()

    def _remove_watch(self):
        i = self.watch_list.currentRow()
        rules = watch_folders()
        if 0 <= i < len(rules):
            rules.pop(i)
            settings().setValue("watch_folders", json.dumps(rules, ensure_ascii=False))
            self._fill_watch()
            self.app.watch.reload()

    def _about_tab(self, st):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 10, 2, 2)
        lay.setSpacing(12)

        # header: icon + name + version + tagline
        head = QHBoxLayout()
        head.setSpacing(14)
        icon = QLabel()
        icon.setPixmap(app_icon().pixmap(72, 72))
        icon.setFixedSize(76, 76)
        head.addWidget(icon, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(APP)
        name.setObjectName("appname")
        ver = QLabel(tr("Version {v}", v=VERSION))
        ver.setObjectName("version")
        tag = QLabel(tr("Drag a file, tap a key, drop it on the wheel."))
        tag.setObjectName("tagline")
        tag.setWordWrap(True)
        made = QLabel(tr("Made by {who}", who="<b>ilukezippo</b> (BoYaqoub)"))
        made.setTextFormat(Qt.RichText)
        for w in (name, ver, tag, made):
            col.addWidget(w)
        head.addLayout(col, 1)
        lay.addLayout(head)

        # buttons: donate + GitHub
        btns = QHBoxLayout()
        donate = QPushButton("☕  " + tr("Donate"))
        donate.setObjectName("donate")
        donate.setCursor(Qt.PointingHandCursor)
        donate.setToolTip("buymeacoffee.com/ilukezippo")
        donate.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(DONATE_URL)))
        gh = QPushButton(tr("GitHub page"))
        gh.setObjectName("link")
        gh.setCursor(Qt.PointingHandCursor)
        gh.setToolTip(updater.REPO_URL)
        gh.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(updater.REPO_URL)))
        issues = QPushButton(tr("Report a problem"))
        issues.setObjectName("link")
        issues.setCursor(Qt.PointingHandCursor)
        issues.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(updater.REPO_URL + "/issues")))
        btns.addWidget(donate)
        btns.addWidget(gh)
        btns.addWidget(issues)
        btns.addStretch(1)
        lay.addLayout(btns)

        # updates
        g4 = QGroupBox(tr("Updates"))
        v4 = QVBoxLayout(g4)
        self.auto_update = QCheckBox(tr("Check for updates automatically (once a day)"))
        self.auto_update.setChecked(st["auto_update"])
        v4.addWidget(self.auto_update)
        row4 = QHBoxLayout()
        last = float(settings().value("last_update_check", 0) or 0)
        import time as _t
        when = _t.strftime("%Y-%m-%d %H:%M", _t.localtime(last)) if last else tr("never")
        lastlbl = QLabel(tr("Last checked: {when}", when=when))
        lastlbl.setObjectName("dim")
        row4.addWidget(lastlbl, 1)
        chk = QPushButton(tr("Check now"))
        chk.clicked.connect(lambda: self.app.check_updates(manual=True))
        row4.addWidget(chk)
        v4.addLayout(row4)
        lay.addWidget(g4)

        # info card
        card = QFrame()
        card.setObjectName("card")
        cv = QVBoxLayout(card)
        cv.setContentsMargins(14, 12, 14, 12)
        cv.setSpacing(6)
        conv, tl = engine.count_catalog()

        def line(icon_txt, text):
            r = QHBoxLayout()
            r.setSpacing(10)
            a = QLabel(icon_txt)
            a.setFixedWidth(22)
            a.setAlignment(Qt.AlignCenter)
            b = QLabel(text)
            b.setWordWrap(True)
            b.setTextFormat(Qt.RichText)
            b.setOpenExternalLinks(True)
            r.addWidget(a, 0, Qt.AlignTop)
            r.addWidget(b, 1)
            cv.addLayout(r)

        line("⚙", tr("{c}+ conversions · {t}+ tools · 8 actions", c=conv, t=tl))
        office_ok = engine.office_available()
        line("✔" if office_ok else "✖", "Office / LibreOffice: " + (tr("found") if office_ok else
             tr("not found — DOCX/PPTX/XLS conversions need Microsoft Office or LibreOffice")))
        line("🔒", tr("Everything runs locally — nothing is uploaded.") + " "
             + tr("The only connection is the update check to GitHub.")
             + f" <a style='color:{theme.hexc('link')}' href='{updater.REPO_URL}/blob/main/PRIVACY.md'>"
             + tr("Privacy policy") + "</a>")
        line("⚖", tr("Free and open source (MIT License)"))
        lay.addWidget(card)
        lay.addStretch(1)
        return page

    # ---- Make it yours tab (changes here are saved straight away)
    def _mine_tab(self):
        from PySide6.QtWidgets import QListWidget
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 6, 2, 2)
        g = QGroupBox(tr("Wheel slices"))
        v = QVBoxLayout(g)
        lbl = QLabel(tr("Choose which slices each wheel shows and in what order."))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        b = QPushButton(tr("Choose slices…"))
        b.clicked.connect(lambda: WheelLayoutDialog(self).exec())
        v.addWidget(b, 0, Qt.AlignLeft)
        lay.addWidget(g)

        g = QGroupBox(tr("Presets and chains"))
        v = QVBoxLayout(g)
        lbl = QLabel(tr("A preset is your favourite settings as one slice in Convert (e.g. WebP · quality 80 · max 1920 px). "
                        "A chain runs several steps as one slice in Tools (e.g. resize → WebP → ZIP)."))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        self.custom_list = QListWidget()
        self.custom_list.setMinimumHeight(110)
        self.custom_list.itemDoubleClicked.connect(lambda _it: self._edit_custom())
        v.addWidget(self.custom_list)
        row = QHBoxLayout()
        for label, fn in ((tr("New image preset"), lambda: self._new_custom("image")),
                          (tr("New video preset"), lambda: self._new_custom("video")),
                          (tr("New chain"), lambda: self._new_custom("chain")),
                          (tr("Edit"), self._edit_custom), (tr("Delete"), self._delete_custom)):
            bt = QPushButton(label)
            bt.clicked.connect(fn)
            row.addWidget(bt)
        v.addLayout(row)
        lay.addWidget(g)
        self._fill_custom()

        g = QGroupBox(tr("Your own slices"))
        v = QVBoxLayout(g)
        lbl = QLabel(tr("Add your own commands to the Actions wheel (e.g. open in another app) in a simple settings file."))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        row = QHBoxLayout()
        b = QPushButton(tr("Edit my slices…"))
        b.clicked.connect(self._edit_my_slices)
        row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        lay.addWidget(g)

        g = QGroupBox(tr("Move your setup to another PC"))
        row = QHBoxLayout(g)
        b = QPushButton(tr("Export settings…"))
        b.clicked.connect(self._export)
        row.addWidget(b)
        b = QPushButton(tr("Import settings…"))
        b.clicked.connect(self._import)
        row.addWidget(b)
        row.addStretch(1)
        lay.addWidget(g)
        lay.addStretch(1)
        return page

    def _fill_custom(self):
        from PySide6.QtWidgets import QListWidgetItem
        self.custom_list.clear()
        kinds = {"image": tr("Image preset"), "video": tr("Video preset"), "chain": tr("Chain")}
        for spec in custom_slices():
            it = QListWidgetItem(f"★ {spec.get('name')}   —   {kinds.get(spec.get('kind'), '')}"
                                 + (f"  ·  {spec.get('hint')}" if spec.get("hint") else ""))
            it.setData(Qt.UserRole, spec.get("uid"))
            self.custom_list.addItem(it)

    def _new_custom(self, kind, spec=None):
        dlg = ChainDialog(spec, self) if kind == "chain" else PresetDialog(kind, spec, self)
        if dlg.exec() != QDialog.Accepted:
            return
        new = dlg.spec()
        lst = [x for x in custom_slices() if x.get("uid") != new["uid"]]
        if spec:
            idx = next((i for i, x in enumerate(custom_slices()) if x.get("uid") == new["uid"]), len(lst))
            lst.insert(idx, new)
        else:
            lst.append(new)
        save_custom_slices(lst)
        self._fill_custom()

    def _edit_custom(self):
        it = self.custom_list.currentItem()
        if it is None:
            return
        spec = next((x for x in custom_slices() if x.get("uid") == it.data(Qt.UserRole)), None)
        if spec:
            self._new_custom(spec.get("kind"), spec)

    def _delete_custom(self):
        it = self.custom_list.currentItem()
        if it is None:
            return
        save_custom_slices([x for x in custom_slices() if x.get("uid") != it.data(Qt.UserRole)])
        self._fill_custom()

    def _edit_my_slices(self):
        f = my_slices_file()
        if not f.exists():
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(MY_SLICES_TEMPLATE, encoding="utf-8")
        import subprocess
        subprocess.Popen(["notepad.exe", str(f)])

    def _export(self):
        f, _ = QFileDialog.getSaveFileName(self, tr("Export settings…"), str(Path.home() / "DragWheel settings.json"),
                                           "JSON (*.json)")
        if f:
            export_settings(f)
            QMessageBox.information(self, APP, tr("Settings saved to {file}", file=f))

    def _import(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("Import settings…"), str(Path.home()), "JSON (*.json)")
        if not f:
            return
        try:
            n = import_settings(f)
        except Exception as e:
            QMessageBox.warning(self, APP, str(e))
            return
        QMessageBox.information(self, APP, tr("Imported {n} settings. Some take effect after DragWheel restarts.", n=n))
        self.app.apply_language()
        self.app.apply_theme()
        self.app.watcher.refresh_settings()
        QDialog.reject(self)                       # close without undoing the imported language/theme

    def save(self):
        keys = {m: cb.currentData() for m, cb in self.key_boxes.items()}
        used = [k for k in keys.values() if k != "None"]
        if len(set(used)) < len(used):
            QMessageBox.warning(self, APP, tr("Each wheel needs a different key."))
            return
        if keys["convert"] == "None" and not self.shake.isChecked() and not self.scroll.isChecked() \
                and all(k == "None" for k in keys.values()):
            QMessageBox.warning(self, APP, tr("With no wheel keys, turn on Shake (Everyday tab) or scrolling, "
                                              "or the wheel can only open from the right-click menu."))
        s = settings()
        for m, k in keys.items():
            s.setValue(f"keys/{m}", k)
        s.setValue("detect_any", self.detect.currentIndex())
        mode = self.out_mode.currentData()
        s.setValue("output_mode", mode)
        s.setValue("output_dir", self.out.text().strip() if mode == "folder" else "")
        s.setValue("hotkey", "true" if self.hotkey.isChecked() else "false")
        s.setValue("scroll", "true" if self.scroll.isChecked() else "false")
        s.setValue("check_updates", "true" if self.auto_update.isChecked() else "false")
        s.setValue("float_autoplay", "true" if self.autoplay.isChecked() else "false")
        s.setValue("float_on_top", "true" if self.on_top.isChecked() else "false")
        s.setValue("float_ctrl_open", "true" if self.ctrl_open.isChecked() else "false")
        s.setValue("media_osd", "true" if self.media_osd.isChecked() else "false")
        s.setValue("wheel_anim", self.anim.currentData())
        s.setValue("anim_speed", self.anim_speed.value())
        s.setValue("job_mode", self.job_mode.currentData())
        s.setValue("tick_volume", self.tick_volume.value())
        for key, box in (("shake", self.shake), ("peek", self.peek), ("finish_anim", self.finish_anim),
                         ("finish_sound", self.finish_sound), ("tour_at_start", self.tour_start),
                         ("cursor_busy", self.cursor_busy), ("float_link_stops", self.link_stops),
                         ("tick_sound", self.tick_sound), ("crash_reports", self.crash_reports)):
            s.setValue(key, "true" if box.isChecked() else "false")
        if self.full_menu is not None and self.full_menu.isChecked() != winsys.full_menu_enabled():
            try:
                winsys.set_full_menu(self.full_menu.isChecked())
                winsys.restart_explorer()
            except Exception as e:
                winsys.log(f"full menu: {e}")
        s.setValue("media_osd_when", self.media_osd_when.currentData())
        self.app.watcher.refresh_settings()
        engine.OUTPUT_DIR = (self.out.text().strip() or None) if mode == "folder" else None
        s.setValue("language", self.lang.currentData())
        s.setValue("theme", self.theme_box.currentData())
        try:
            winsys.set_startup(self.startup.isChecked())
            winsys.set_context_menu(self.menu.isChecked(), paste_label=tr("Save clipboard image here"), link_label=tr("Play copied link in Float"),
                                    float_label=tr("Open Float"))
        except Exception as e:
            QMessageBox.warning(self, APP, tr("Couldn't update Windows integration:") + f"\n{e}")
        self.accept()


# ============================================================================
# Drag watcher — polls input state (no hooks, nothing injected)
# ============================================================================
class CursorBusy(QWidget):
    """A small spinning circle next to the mouse pointer while DragWheel is working (Settings → Everyday)."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(22, 22)
        self.angle = 0
        self.timer = QTimer(self, interval=30, timeout=self._tick)

    def set_busy(self, busy):
        if busy and not self.isVisible():
            self._tick()
            self.show()
            self.timer.start()
        elif not busy and self.isVisible():
            self.timer.stop()
            self.hide()

    def _tick(self):
        pos = QCursor.pos()
        self.move(pos.x() + 16, pos.y() + 18)
        self.angle = (self.angle + 14) % 360
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(3, 3, 16, 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 110))
        p.drawEllipse(r.adjusted(-2, -2, 2, 2))
        p.setPen(QPen(QColor(255, 255, 255, 90), 2.6))
        p.drawEllipse(r)
        pen = QPen(ACCENT, 2.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, -self.angle * 16, 110 * 16)
        p.end()


DOC_PREVIEW_CATS = ("pdf", "document", "spreadsheet", "slides", "ebook")
TEXTLIKE_EXT = (".txt", ".md", ".csv", ".tsv", ".json", ".html", ".htm", ".rtf", ".log")


class PeekSignals(QObject):
    ready = Signal(object, object)      # path, QImage


def _office_to_pdf(src: Path, dest: Path) -> bool:
    """Print a Word, Excel or PowerPoint file (or RTF, ODT…) to `dest` as a PDF, read-only, without touching
    the original's folder: Microsoft Office when it's installed, else LibreOffice."""
    cat = engine.EXT_CATEGORY.get(engine.ext_of(str(src)))
    if winsys.IS_WIN:
        try:
            import pythoncom
            import win32com.client as wc
            pythoncom.CoInitialize()
            try:
                if cat in ("document", "pdf"):
                    app = wc.DispatchEx("Word.Application")
                    app.Visible = False
                    app.DisplayAlerts = 0
                    try:
                        doc = app.Documents.Open(str(src), ConfirmConversions=False, ReadOnly=True,
                                                 AddToRecentFiles=False, Visible=False)
                        doc.ExportAsFixedFormat(str(dest), 17, OpenAfterExport=False, OptimizeFor=1,
                                                Range=3, From=1, To=1)          # first page is enough
                        doc.Close(False)
                    finally:
                        app.Quit()
                elif cat == "spreadsheet":
                    app = wc.DispatchEx("Excel.Application")
                    app.Visible = False
                    app.DisplayAlerts = False
                    try:
                        wb = app.Workbooks.Open(str(src), ReadOnly=True, UpdateLinks=0)
                        wb.ActiveSheet.ExportAsFixedFormat(0, str(dest), From=1, To=1, OpenAfterPublish=False)
                        wb.Close(False)
                    finally:
                        app.Quit()
                elif cat == "slides":
                    app = wc.DispatchEx("PowerPoint.Application")
                    try:
                        pres = app.Presentations.Open(str(src), ReadOnly=True, WithWindow=False)
                        pres.SaveAs(str(dest), 32)
                        pres.Close()
                    finally:
                        app.Quit()
            finally:
                pythoncom.CoUninitialize()
            if dest.exists() and dest.stat().st_size > 0:
                return True
        except Exception as e:
            winsys.log(f"preview: Office could not open {src.name}: {e}")
    exe = engine.soffice()
    if exe:
        import subprocess
        import tempfile
        td = Path(tempfile.mkdtemp(prefix="dw-prev-"))
        try:
            subprocess.run([exe, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", str(td), str(src)],
                           timeout=90, stdin=subprocess.DEVNULL, capture_output=True, creationflags=engine.NO_WINDOW)
            made = list(td.glob("*.pdf"))
            if made:
                shutil.move(str(made[0]), str(dest))
                return True
        except Exception as e:
            winsys.log(f"preview: LibreOffice could not open {src.name}: {e}")
        finally:
            shutil.rmtree(td, ignore_errors=True)
    return False


_PREVIEW_LOCK = threading.Lock()


def _pdf_for_preview(p: Path) -> Path | None:
    """A PDF of an Office-type file for previews, made once and kept in the temp folder until the file changes."""
    import hashlib
    import tempfile
    try:
        st = p.stat()
    except OSError:
        return None
    key = hashlib.sha1(f"{p}|{st.st_size}|{st.st_mtime_ns}".encode("utf-8")).hexdigest()[:16]
    folder = Path(tempfile.gettempdir()) / "DragWheel previews"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{key}.pdf"
    with _PREVIEW_LOCK:                      # Float and Quick preview asking at once make it only once
        if out.exists() and out.stat().st_size > 0:
            return out
        part = folder / f"{key}.tmp.pdf"
        part.unlink(missing_ok=True)
        if _office_to_pdf(p.resolve(), part):
            os.replace(part, out)
            return out
        part.unlink(missing_ok=True)
        winsys.log(f"preview: no page for {p.name} (needs Microsoft Office or LibreOffice)")
        return None


def _text_page_image(p: Path, width: int) -> "QImage | None":
    """Text, Markdown, HTML, CSV and JSON files drawn as a white page."""
    from PySide6.QtGui import QTextDocument, QTextOption
    try:
        raw = p.read_bytes()[:400_000]
    except OSError:
        return None
    txt = None
    for enc in ("utf-8-sig", "utf-16", "cp1256", "latin-1"):
        try:
            txt = raw.decode(enc)
            if enc == "utf-16" and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            break
        except UnicodeDecodeError:
            continue
    if txt is None:
        return None
    e = p.suffix.lower()
    doc = QTextDocument()
    doc.setDocumentMargin(36)
    f = QFont(i18n.ui_font() if e in (".md", ".markdown", ".html", ".htm") else "Consolas", 11)
    doc.setDefaultFont(f)
    opt = QTextOption()
    opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    if any("\u0600" <= ch <= "\u06ff" for ch in txt[:2000]):
        opt.setTextDirection(Qt.RightToLeft)
        opt.setAlignment(Qt.AlignRight)
    doc.setDefaultTextOption(opt)
    if e in (".html", ".htm"):
        doc.setHtml(txt)
    elif e in (".md", ".markdown"):
        doc.setMarkdown(txt)
    elif e in (".csv", ".tsv"):
        import csv
        import html as _h
        rows = list(csv.reader(txt.splitlines()[:60], delimiter="\t" if e == ".tsv" else ","))
        doc.setHtml("<table border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse'>" + "".join(
            "<tr>" + "".join(f"<td>{_h.escape(c)}</td>" for c in r[:12]) + "</tr>" for r in rows) + "</table>")
    elif opt.textDirection() == Qt.RightToLeft:
        import html as _h
        doc.setDefaultFont(QFont(i18n.ui_font(), 12))
        doc.setHtml("<div dir='rtl' align='right' style='white-space:pre-wrap'>" + _h.escape(txt[:20000]) + "</div>")
    else:
        doc.setPlainText(txt[:20000])
    page_w = 620
    doc.setTextWidth(page_w)
    page_h = int(page_w * 1.414)
    scale = width / page_w
    img = QImage(width, int(page_h * scale), QImage.Format_RGB888)
    img.fill(QColor(255, 255, 255))
    pnt = QPainter(img)
    pnt.setRenderHint(QPainter.Antialiasing)
    pnt.setRenderHint(QPainter.TextAntialiasing)
    pnt.scale(scale, scale)
    pnt.setClipRect(QRectF(0, 0, page_w, page_h))
    from PySide6.QtGui import QAbstractTextDocumentLayout
    ctx = QAbstractTextDocumentLayout.PaintContext()
    ctx.palette.setColor(ctx.palette.ColorRole.Text, QColor(20, 20, 20))
    doc.documentLayout().draw(pnt, ctx)
    pnt.end()
    return img


def document_page_image(path, width=1200, page=0) -> "QImage | None":
    """First page of any document as a picture: PDFs, e-books and comics directly, Word/Excel/PowerPoint/RTF/ODT
    through a PDF, and text, Markdown, HTML and CSV files drawn as a page."""
    p = Path(path)
    cat = engine.EXT_CATEGORY.get(engine.ext_of(str(p)))
    e = p.suffix.lower()
    if e in TEXTLIKE_EXT or e in (".markdown", ".json"):
        try:
            return _text_page_image(p, width)
        except Exception as ex:
            winsys.log(f"preview: {p.name}: {ex}")
            return None
    src = p
    if cat in ("document", "spreadsheet", "slides"):
        src = _pdf_for_preview(p)
        if src is None:
            return None
    try:
        import pymupdf
        with pymupdf.open(str(src)) as doc:
            if doc.page_count == 0:
                return None
            pg = doc[min(page, doc.page_count - 1)]
            zoom = width / max(1.0, pg.rect.width)
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            return QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
    except Exception as ex:
        winsys.log(f"preview: {p.name}: {ex}")
        return None


def _peek_image(path) -> "QImage | None":
    """A picture of the file for Quick preview: the image itself, a PDF's first page, a video frame."""
    p = Path(path)
    cat = engine.EXT_CATEGORY.get(engine.ext_of(str(p)))
    try:
        if cat == "image":
            img = QImage(str(p))
            if img.isNull():
                from PIL import Image
                try:
                    import pillow_heif
                    pillow_heif.register_heif_opener()
                except Exception:
                    pass
                with Image.open(p) as im:
                    im.thumbnail((900, 900))
                    im = im.convert("RGBA")
                    img = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, QImage.Format_RGBA8888).copy()
            return None if img.isNull() else img.scaled(900, 900, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if cat in DOC_PREVIEW_CATS or p.suffix.lower() in (".cbz", ".xps", ".json"):
            return document_page_image(p, 900)
        if cat == "video":
            import subprocess
            import tempfile
            out = Path(tempfile.gettempdir()) / f"dw-peek-{os.getpid()}.jpg"
            subprocess.run([engine.ffmpeg(), "-y", "-v", "error", "-ss", "2", "-i", str(p), "-frames:v", "1",
                            "-vf", "scale='min(900,iw)':-2", str(out)], timeout=8, stdin=subprocess.DEVNULL,
                           capture_output=True, creationflags=engine.NO_WINDOW)
            img = QImage(str(out))
            try:
                out.unlink()
            except OSError:
                pass
            return None if img.isNull() else img
    except Exception as e:
        winsys.log(f"peek: {p.name}: {e}")
    return None


class PeekWindow(QWidget):
    """Quick preview: tap Space while dragging to see what you're holding."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.path = None
        self.img = None
        self.text = ""
        self.sig = PeekSignals()
        self.sig.ready.connect(self._got, Qt.QueuedConnection)
        self.follow = QTimer(self, interval=15, timeout=self._place)    # rides along with the pointer
        self._last_pos = None

    def peek(self, paths):
        self.path = paths[0]
        p = Path(self.path)
        self.img = None
        self.text = ""
        cat = engine.EXT_CATEGORY.get(engine.ext_of(str(p)))
        if p.is_file() and (cat in ("subtitle",) or p.suffix.lower() in (".log", ".py", ".ini", ".xml", ".srt")):
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    self.text = "".join(f.readline() for _ in range(24))[:2400]
            except OSError:
                pass
        elif p.is_file():
            threading.Thread(target=lambda path=self.path: self.sig.ready.emit(path, _peek_image(path)),
                             daemon=True).start()
        self.extra = tr("{n} files", n=len(paths)) if len(paths) > 1 else ""
        self._layout()
        self.show()
        self.raise_()

    def _got(self, path, img):
        if path == self.path and self.isVisible() and img is not None:
            self.img = img
            self._layout()
            self.update()

    def _layout(self):
        w, h = 340, 120
        if self.img is not None:
            sc = min(420 / self.img.width(), 380 / self.img.height(), 1.0)
            w, h = max(240, int(self.img.width() * sc) + 24), int(self.img.height() * sc) + 74
        elif self.text:
            w, h = 420, 300
        else:
            w, h = 300, 150
        self.resize(w, h)
        self._last_pos = None
        self._place()

    def _place(self):
        pos = QCursor.pos()
        if pos == self._last_pos:
            return
        self._last_pos = pos
        w, h = self.width(), self.height()
        scr = (QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()).availableGeometry()
        x = pos.x() + 28 if pos.x() + 28 + w < scr.right() else pos.x() - 28 - w
        y = max(scr.top() + 8, min(pos.y() - h // 2, scr.bottom() - h - 8))
        self.move(x, y)

    def showEvent(self, e):
        self.follow.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.follow.stop()
        super().hideEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setPen(QPen(C("line"), 1))
        p.setBrush(C("panel"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)
        path = Path(self.path or "")
        body = QRectF(12, 12, self.width() - 24, self.height() - 74)
        if self.img is not None:
            pm = QPixmap.fromImage(self.img)
            if pm.width() > body.width() or pm.height() > body.height():      # shrink big pictures, never blow up small ones
                pm = pm.scaled(body.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(int(body.center().x() - pm.width() / 2), int(body.center().y() - pm.height() / 2), pm)
        elif self.text:
            p.setPen(C("text"))
            p.setFont(QFont("Consolas", 8))
            p.drawText(body, Qt.AlignLeft | Qt.AlignTop | Qt.TextWrapAnywhere, self.text)
        else:
            from PySide6.QtCore import QFileInfo
            from PySide6.QtWidgets import QFileIconProvider
            ic = QFileIconProvider().icon(QFileInfo(str(path))).pixmap(56, 56)
            p.drawPixmap(int(body.center().x() - 28), int(body.center().y() - 28), ic)
        p.setPen(C("text"))
        p.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
        fm = QFontMetrics(p.font())
        p.drawText(QRectF(14, self.height() - 58, self.width() - 28, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(path.name, Qt.ElideMiddle, self.width() - 28))
        p.setPen(C("dim"))
        p.setFont(QFont("Segoe UI", 9))
        info = " · ".join(x for x in (_human(path), self.extra, tr("Space to close")) if x)
        p.drawText(QRectF(14, self.height() - 36, self.width() - 28, 20), Qt.AlignLeft | Qt.AlignVCenter, info)
        p.end()


class TourCanvas(QWidget):
    """A looping little film: drag a file, tap the key, drop on a slice, done."""
    LOOP = 7.2

    def __init__(self, key, parent=None):
        super().__init__(parent)
        import time
        self.key = key
        self.t0 = time.monotonic()
        self.setFixedSize(620, 330)
        w = Wheel(_APP)
        w._style = "none"
        w.mode, w.paths = "convert", ["C:/example/Holiday.heic"]
        w.ops = [engine.Op(f"to_{x.lower()}", x, lambda *a: None) for x in ("JPG", "PNG", "WEBP", "PDF", "GIF", "AVIF", "TIFF", "ICO")]
        w.hover = -1
        self.plain = w.grab()
        w.hover = 1
        self.lit = w.grab()
        self.wheel_c = w.center()
        self.slice_pos = None
        from PySide6.QtCore import QFileInfo
        from PySide6.QtWidgets import QFileIconProvider
        self.icon = QFileIconProvider().icon(QFileInfo("x.jpg")).pixmap(48, 48)
        if self.icon.isNull() or self.icon.toImage().allGray() and self.icon.toImage().pixelColor(24, 24).alpha() == 0:
            self.icon = QPixmap(48, 48)                      # a plain picture-file shape
            self.icon.fill(Qt.transparent)
            q = QPainter(self.icon)
            q.setRenderHint(QPainter.Antialiasing)
            q.setPen(QPen(QColor("#9aa0a6"), 1.5))
            q.setBrush(QColor("#ffffff"))
            q.drawRoundedRect(QRectF(8, 3, 32, 42), 4, 4)
            q.setPen(Qt.NoPen)
            q.setBrush(QColor("#4a90e2"))
            q.drawPolygon(QPolygonF([QPointF(12, 38), QPointF(22, 24), QPointF(28, 32), QPointF(32, 27), QPointF(36, 38)]))
            q.setBrush(QColor("#f5a623"))
            q.drawEllipse(QPointF(30, 14), 4, 4)
            q.end()
        self.timer = QTimer(self, interval=16, timeout=self.update)
        self.timer.start()

    def step(self):
        import time
        t = (time.monotonic() - self.t0) % self.LOOP
        return 0 if t < 1.3 else 1 if t < 2.2 else 2 if t < 4.2 else 3

    def paintEvent(self, _e):
        import time
        t = (time.monotonic() - self.t0) % self.LOOP
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setPen(QPen(C("line"), 1))
        p.setBrush(QColor(theme.hexc("canvas")))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)

        def ease(a):
            a = max(0.0, min(1.0, a))
            return a * a * (3 - 2 * a)

        start, center = QPointF(80, 250), QPointF(310, 150)
        scale = 0.5
        ang = math.radians(45)                       # the PNG slice: second of eight, 45° clockwise from the top
        rr = (Wheel.R_IN + Wheel.R_MID + 14) / 2 * scale
        target = center + QPointF(math.sin(ang) * rr, -math.cos(ang) * rr)
        if t < 1.3:
            cur = start + (center - start) * ease(t / 1.3)
        elif t < 2.2:
            cur = center
        elif t < 3.4:
            cur = center + (target - center) * ease((t - 2.2) / 1.2)
        else:
            cur = target
        # the wheel
        show = 0.0
        if 1.45 <= t < 4.0:
            show = ease((t - 1.45) / 0.35) if t < 3.6 else 1 - ease((t - 3.6) / 0.4)
        if show > 0:
            pm = self.lit if 3.0 <= t < 3.8 else self.plain
            w, h = pm.width() / pm.devicePixelRatio() * scale, pm.height() / pm.devicePixelRatio() * scale
            c = self.wheel_c * scale
            p.save()
            p.setOpacity(show)
            p.translate(center)
            k = 0.8 + 0.2 * show
            p.scale(k, k)
            p.drawPixmap(QRectF(-c.x(), -c.y(), w, h), pm, QRectF(pm.rect()))
            p.restore()
        # the file being dragged (and the pointer)
        if t < 3.7:
            p.setOpacity(1.0 if t < 3.5 else 1 - (t - 3.5) / 0.2)
            p.drawPixmap(int(cur.x() - 10), int(cur.y() - 6), self.icon)
            p.setOpacity(1.0)
        arrow = QPolygonF([QPointF(0, 0), QPointF(0, 17), QPointF(4.5, 13), QPointF(8, 20), QPointF(10.5, 19),
                           QPointF(7, 12), QPointF(13, 12)])
        p.save()
        p.translate(cur)
        p.setPen(QPen(QColor("#000000"), 1.2))
        p.setBrush(QColor("#ffffff"))
        p.drawPolygon(arrow)
        p.restore()
        # the key
        pressed = 1.25 <= t < 1.6
        key = QRectF(30, 26, 92, 40)
        p.setPen(QPen(ACCENT if pressed else C("line"), 2))
        p.setBrush(ACCENT if pressed else C("panel"))
        p.drawRoundedRect(key.translated(0, 3 if pressed else 0), 8, 8)
        p.setPen(ON_ACCENT if pressed else C("text"))
        p.setFont(QFont("Segoe UI", 11, QFont.DemiBold))
        p.drawText(key.translated(0, 3 if pressed else 0), Qt.AlignCenter, self.key)
        # the finished notification
        if 4.1 <= t < 6.8:
            a = ease((t - 4.1) / 0.3) if t < 6.4 else 1 - ease((t - 6.4) / 0.4)
            r = QRectF(self.width() - 250, self.height() - 74 + (1 - a) * 20, 232, 56)
            p.setOpacity(a)
            p.setPen(QPen(C("line"), 1))
            p.setBrush(C("panel"))
            p.drawRoundedRect(r, 12, 12)
            p.setPen(Qt.NoPen)
            p.setBrush(C("ok"))
            p.drawEllipse(QPointF(r.x() + 26, r.center().y()), 12, 12)
            p.setPen(QPen(ON_ACCENT, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            x0, y0 = r.x() + 26, r.center().y()
            p.drawPolyline([QPointF(x0 - 6, y0), QPointF(x0 - 1.5, y0 + 4.5), QPointF(x0 + 6, y0 - 4)])
            p.setPen(C("text"))
            p.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
            p.drawText(QRectF(r.x() + 48, r.y() + 8, 180, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       tr("Converted to {fmt}", fmt="PNG"))
            p.setPen(C("dim"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(r.x() + 48, r.y() + 28, 180, 18), Qt.AlignLeft | Qt.AlignVCenter, "Holiday.png")
        p.end()


class TourDialog(QDialog):
    """First launch: how DragWheel works in three steps, shown as a short looping animation."""

    def __init__(self, app, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint if parent is None else Qt.Dialog)
        self.app = app
        keys = mode_keys()
        shake = keys["convert"] == "None"
        key = tr("Shake") if shake else tr(keys["convert"])
        self.setWindowTitle(tr("Welcome to {app}", app=APP))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS) + f"QLabel#step{{padding:8px 10px;border-radius:10px;color:{theme.hexc('dim')}}}"
                           f"QLabel#step[on=true]{{background:{theme.hexc('surface')};color:{theme.hexc('text')}}}")
        lay = QVBoxLayout(self)
        head = QLabel(f"<b style='font-size:13pt'>{tr('Welcome to {app}', app=APP)}</b><br>"
                      f"<span style='color:{theme.hexc('dim')}'>{tr('Convert any file without opening an app, in three moves:')}</span>")
        lay.addWidget(head)
        self.canvas = TourCanvas(key)
        lay.addWidget(self.canvas, 0, Qt.AlignHCenter)
        row = QHBoxLayout()
        self.steps = []
        for i, text in enumerate((tr("Drag a file (keep holding the mouse)"),
                                  tr("Shake the mouse — the wheel opens") if shake else tr("Tap {key} — the wheel opens", key=key),
                                  tr("Drop it on a slice. Done!"))):
            lbl = QLabel(f"<b>{i + 1}</b>&nbsp;&nbsp;{text}")
            lbl.setObjectName("step")
            lbl.setWordWrap(True)
            row.addWidget(lbl, 1)
            self.steps.append(lbl)
        lay.addLayout(row)
        if keys["tool"] != "None" and keys["action"] != "None":
            more = QLabel(tr("{tools} opens Tools and {actions} opens Actions. Prefer clicking? Right-click a file → DragWheel.",
                             tools=tr(keys["tool"]), actions=tr(keys["action"])))
        else:
            more = QLabel(tr("Switch wheels by resting on the buttons under the wheel. Prefer clicking? Right-click a file → DragWheel."))
        more.setWordWrap(True)
        more.setStyleSheet(f"color:{theme.hexc('dim')}")
        lay.addWidget(more)
        bb = QHBoxLayout()
        self.never = QCheckBox(tr("Don't show this again"))
        self.never.setChecked(settings().value("tour_at_start", "true") != "true")
        self.never.toggled.connect(lambda on: settings().setValue("tour_at_start", "false" if on else "true"))
        bb.addWidget(self.never)
        b = QPushButton(tr("More help"))
        b.clicked.connect(lambda: (self.accept(), app.show_help()))
        bb.addWidget(b)
        bb.addStretch(1)
        ok = QPushButton(tr("Got it"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        bb.addWidget(ok)
        lay.addLayout(bb)
        self._last = -1
        self._t = QTimer(self, interval=100, timeout=self._mark)
        self._t.start()

    def _mark(self):
        s = min(self.canvas.step(), 2)
        if s != self._last:
            self._last = s
            for i, lbl in enumerate(self.steps):
                lbl.setProperty("on", i == s)
                lbl.style().unpolish(lbl)
                lbl.style().polish(lbl)


class DragWatcher(QObject):
    tapped = Signal(str)     # mode
    released = Signal()
    hotkey = Signal()
    moved = Signal()         # every tick while a drag is in progress
    scrolled = Signal(int)   # wheel delta while dragging (from the hook thread, delivered queued)
    cancelled = Signal()     # Esc pressed during a drag
    ctrl_open = Signal(int)  # Ctrl + double-click on a file in Explorer (window handle), from the hook thread
    peek = Signal()          # Space tapped while dragging (Quick preview)
    volume_key = Signal(int)  # a volume key or knob step (from the hook thread)
    shaken = Signal()        # the mouse was shaken while dragging

    def __init__(self):
        super().__init__()
        self.timer = QTimer(self, interval=20, timeout=self.tick)
        self.down_at = None
        self.dragging = False
        self.prev = {}
        self.hotkey_latch = False
        self.source_hwnd = 0     # top-level window the drag started in
        self.esc_prev = False
        self.space_prev = False
        self.trail = []          # (time, x) while dragging, to notice a shake
        self.shook = False
        self.refresh_settings()
        self.hook = winsys.WheelHook(self._on_wheel, self._swallow_wheel,
                                     on_ctrl_double=lambda hwnd: self.ctrl_open.emit(int(hwnd)),
                                     ctrl_double_enabled=lambda: getattr(self, "ctrl_float", False))
        self.hook.on_volume_key = lambda vk: self.volume_key.emit(vk)

    def refresh_settings(self):
        s = settings()
        self.scroll_enabled = s.value("scroll", "true") == "true"
        self.any_drag = int(s.value("detect_any", 0)) == 1
        self.ctrl_float = s.value("float_ctrl_open", "true") == "true"
        self.shake_enabled = s.value("shake", "true") == "true"
        self.peek_enabled = s.value("peek", "true") == "true"

    # called on the hook thread — keep it tiny
    def _drag_qualifies(self):
        return self.dragging and self.scroll_enabled and (self.any_drag or winsys.file_drag_active())

    def _on_wheel(self, delta):
        if self._drag_qualifies():
            self.scrolled.emit(delta)

    def _swallow_wheel(self):
        return self._drag_qualifies()

    def start(self):
        if winsys.IS_WIN:
            self.timer.start()
            self.hook.start()

    def tick(self):
        keys = mode_keys()
        held = {name: winsys.key_down(winsys.VK[name]) for name in set(keys.values()) if name in winsys.VK}
        lmb = winsys.mouse_down()

        # global hotkey: Ctrl+Alt+Space
        combo = winsys.key_down(0x11) and winsys.key_down(0x12) and winsys.key_down(winsys.VK_SPACE)
        if combo and not self.hotkey_latch:
            self.hotkey_latch = True
            if settings().value("hotkey", "true") == "true":
                self.hotkey.emit()
        elif not combo:
            self.hotkey_latch = False

        if lmb:
            pos = winsys.cursor_pos()
            if self.down_at is None:
                self.down_at = pos
                self.dragging = False
                self.source_hwnd = winsys.root_window_at(*pos)
            elif not self.dragging:
                dx, dy = pos[0] - self.down_at[0], pos[1] - self.down_at[1]
                if abs(dx) + abs(dy) > winsys.drag_threshold() * 2:
                    self.dragging = True
            if self.dragging:
                self.moved.emit()
                esc = winsys.key_down(winsys.VK_ESCAPE)
                if esc and not self.esc_prev:
                    self.cancelled.emit()
                self.esc_prev = esc
                space = winsys.key_down(winsys.VK_SPACE) and not winsys.key_down(0x11) and not winsys.key_down(0x12)
                if space and not self.space_prev and self.peek_enabled and winsys.file_drag_active():
                    self.peek.emit()
                self.space_prev = space
                if self.shake_enabled and not self.shook and self._shake(pos):
                    self.shook = True
                    if winsys.file_drag_active() or int(settings().value("detect_any", 0)) == 1:
                        self.shaken.emit()
                any_drag = int(settings().value("detect_any", 0)) == 1
                for m, name in keys.items():
                    if held.get(name) and not self.prev.get(name):
                        if any_drag or winsys.file_drag_active():
                            self.tapped.emit(m)
        else:
            if self.down_at is not None and self.dragging:
                self.released.emit()
            self.down_at = None
            self.dragging = False
            self.trail = []
            self.shook = False
            self.space_prev = False
        self.prev = held

    def _shake(self, pos) -> bool:
        """Three or more quick left-right turns of at least 40 px within 0.8 s."""
        import time
        now = time.monotonic()
        self.trail = [(t, x) for t, x in self.trail if now - t < 0.8] + [(now, pos[0])]
        turns, direction, anchor = 0, 0, self.trail[0][1]
        for _t, x in self.trail[1:]:
            d = x - anchor
            if abs(d) >= 40:
                sign = 1 if d > 0 else -1
                if direction and sign != direction:
                    turns += 1
                direction, anchor = sign, x
            elif direction and (x - anchor) * direction > 0:
                anchor = x                             # still going the same way: follow the far end
        return turns >= 3


# ============================================================================
# App
# ============================================================================
def asset(name) -> str:
    return str(Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets" / name)


_ICON = None


def app_icon() -> QIcon:
    global _ICON
    if _ICON is None:
        _ICON = QIcon(asset("dragwheel.ico")) if os.path.exists(asset("dragwheel.ico")) else QIcon()
    return _ICON


class DragWheelApp(QObject):
    def __init__(self, qapp: QApplication):
        super().__init__()
        self.qapp = qapp
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(max(2, (os.cpu_count() or 4) // 2))
        self.actions = Actions(self)
        global _APP
        _APP = self
        self.floats = []
        self.out_override = {}           # temp file -> folder its results go to (clipboard "save here")
        self._media_down = {}
        self._media_timer = QTimer(self, interval=60, timeout=self._media_tick)
        self._media_timer.start()
        self.wheel = Wheel(self)
        self.toast = ToastManager()
        self.running = set()
        self.waiting = []                # jobs in line (Settings → one at a time)
        engine.OUTPUT_DIR = (settings().value("output_dir", "") or None) \
            if settings().value("output_mode", "folder") == "folder" else None

        self.watcher = DragWatcher()
        self.watcher.tapped.connect(self.on_tap)
        self.watcher.released.connect(self.on_release)
        self.watcher.hotkey.connect(self.on_hotkey)
        self.watcher.moved.connect(self.on_drag_move)
        self.watcher.scrolled.connect(self.on_scroll)
        self.watcher.ctrl_open.connect(self.on_ctrl_open)
        self.watcher.cancelled.connect(self.on_drag_cancel)
        self.watcher.peek.connect(self.on_peek)
        self.watcher.volume_key.connect(self.on_volume_key, Qt.QueuedConnection)
        self.watcher.shaken.connect(lambda: self.on_tap("convert") if not self.wheel.is_open() else None)
        self.watcher.released.connect(self._close_peek)
        self.watcher.start()
        self._peek = None
        self.watch = FolderWatch(self)
        try:
            _tick_effect()                       # load the click sounds now
            _tick_effect("select")
        except Exception as e:
            winsys.log(f"tick sound: {e}")
        self.cursor_busy = CursorBusy()
        self._busy_timer = QTimer(self, interval=250, timeout=self._update_cursor_busy)
        self._busy_timer.start()

        self.pending: list[str] = []
        self.pending_timer = QTimer(self, singleShot=True, interval=350, timeout=self._flush_pending)

        self.tray = QSystemTrayIcon(app_icon())
        self.tray.activated.connect(lambda r: self.show_settings() if r == QSystemTrayIcon.Trigger else None)
        self._build_tray_menu()
        self.tray.show()
        self._update_jobs = set()
        QTimer.singleShot(8000, self._auto_update_check)
        QTimer.singleShot(150, self.restore_pinned_floats)
        self.predownload()

    def restore_pinned_floats(self):
        """Reopen the floats that were open before an update, and those set to 'Open when Windows starts'."""
        try:
            resume = json.loads(settings().value("float_resume", "[]") or "[]")
        except (TypeError, ValueError):
            resume = []
        settings().remove("float_resume")
        ids = {r.get("id") for r in resume if r.get("id")}
        for pin in resume + [x for x in _float_pins() if x.get("id") not in ids]:
            src = pin.get("src")
            if not src:
                continue
            if pin.get("link"):
                if engine.model_ready("yt-dlp"):
                    w = FloatWindow("", {"page": src, "title": pin.get("title") or src, "pending": True}, pin=pin)
                    self.floats.append(w)
                    w.closed.connect(lambda w=w: self.floats.remove(w) if w in self.floats else None)
                    w.show()
                    self._resolve_and_play(src, w, pin=pin, quiet=True)
                continue
            if not os.path.exists(src):
                winsys.log(f"pinned float missing: {src}")
                continue
            w = FloatWindow(src, play=pin.get("playing", True), pin=pin)
            self.floats.append(w)
            w.closed.connect(lambda w=w: self.floats.remove(w) if w in self.floats else None)
            w.show()

    def _build_tray_menu(self):
        ck = mode_keys()["convert"]
        self.tray.setToolTip(tr("{app} — drag a file and shake the mouse", app=APP) if ck == "None"
                             else tr("{app} — drag a file, tap {key}", app=APP, key=tr(ck)))
        menu = QMenu()
        self._first_action = menu.addAction(tr("Convert files…"), self.pick_files)
        menu.addAction(tr("Save image from clipboard"), self.save_clipboard_image)
        menu.addAction(tr("Play copied link in Float"), self.play_link)
        recent = menu.addMenu(tr("Recent results"))
        recent.aboutToShow.connect(lambda m=recent: self._fill_recent(m))
        self._qr_menu = menu.addMenu(tr("Send to phone — show QR code"))
        menu.addSeparator()
        menu.addAction(tr("How it works"), self.show_help)
        menu.addAction(tr("Settings…"), self.show_settings)
        menu.addAction(tr("Check for updates…"), lambda: self.check_updates(manual=True))
        menu.addSeparator()
        menu.addAction(tr("Quit {app}", app=APP), self.qapp.quit)
        self._cancel_actions = []
        menu.aboutToShow.connect(self._refresh_tray_menu)
        old = self.tray.contextMenu()
        self.tray.setContextMenu(menu)
        self._menu = menu
        if old:
            old.deleteLater()

    def _active_jobs(self):
        """Conversions/tools still running and not already being cancelled."""
        return [w for w in list(self.running) if not w.cancel_requested]

    def _fill_qr_menu(self):
        sub = self._qr_menu
        sub.clear()
        links = share_links()
        sub.menuAction().setVisible(bool(links))           # only while an internet link is still alive
        for it in links:
            name = it["name"] if len(it["name"]) <= 40 else it["name"][:37] + "…"
            sub.addAction(f"{name}   ·   {_time_left(it['expires'])}", lambda it=it: self._show_qr(it))

    def _show_qr(self, it):
        w = ShareQR(it)
        self._phone_windows = getattr(self, "_phone_windows", [])
        self._phone_windows.append(w)
        w.show()
        w.raise_()
        w.activateWindow()

    def _refresh_tray_menu(self):
        """Cancel entries go first in the tray menu, only while work is in progress."""
        self._fill_qr_menu()
        menu = self._menu
        for act in self._cancel_actions:
            menu.removeAction(act)
            act.deleteLater()
        self._cancel_actions = []
        jobs = self._active_jobs() + [w for w in self.waiting if not w.cancel_requested]
        if not jobs:
            return
        before = self._first_action
        for w in jobs:
            name = Path(w.paths[0]).name if len(w.paths) == 1 else tr("{n} files", n=len(w.paths))
            if len(name) > 40:
                name = name[:37] + "…"
            what = (tr("Converting to {fmt}…", fmt=tr(w.op.label)) if w.op.group == "convert"
                    else tr(w.op.label)).rstrip("…")
            act = QAction(tr("Cancel: {what} — {name}", what=what, name=name), menu)
            act.triggered.connect(lambda _=False, w=w: self._cancel_job(w))
            menu.insertAction(before, act)
            self._cancel_actions.append(act)
        if len(jobs) > 1:
            act = QAction(tr("Cancel all ({n})", n=len(jobs)), menu)
            act.triggered.connect(lambda: [self._cancel_job(w) for w in list(self.waiting) + self._active_jobs()])
            menu.insertAction(before, act)
            self._cancel_actions.append(act)
        sep = menu.insertSeparator(before)
        self._cancel_actions.append(sep)

    def apply_theme(self):
        theme.set_mode(settings().value("theme", "system"))
        self.toast.restyle()
        for c in self.toast.cards:
            c.update()
        for f in self.floats:
            f.update()
        self.wheel.update()

    def apply_language(self):
        i18n.set_language(settings().value("language", ""))
        self.qapp.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
        self.qapp.setFont(QFont(i18n.ui_font(), 9))
        self.toast.restyle()
        self._build_tray_menu()
        self.wheel.update()

    # ---- ops for a mode
    def ops_for(self, mode, paths):
        if mode == "convert":
            ops = engine.conversions(paths)
        elif mode == "tool":
            ops = engine.tools(paths)
        else:
            ops = self.actions.ops(paths)
        try:
            ops = ops + custom_ops_for(mode, paths)                     # your presets, chains and commands
            ops = apply_wheel_layout(mode, engine.category_of(paths), ops)
        except Exception as e:
            winsys.log(f"wheel layout: {e}")
        if not ops:
            return [engine.Op("none", "No conversions" if mode == "convert" else "No tools", lambda *a: None,
                              hint="try Tools or Actions" if mode == "convert" else "try Convert or Actions")]
        return ops

    # ---- triggers
    def on_tap(self, mode):
        now = time.monotonic()
        if now - getattr(self, "_last_tap", 0.0) < 0.22:
            return                                    # one press is one toggle, never open-then-close
        self._last_tap = now
        if self.wheel.is_open():
            if mode == self.wheel.mode:
                self.wheel.dismiss()                 # the same key again closes the wheel
                return
            if mode != self.wheel.mode:
                play_tick()
                self.wheel.set_mode(mode)
            if not self.wheel.paths:
                self._fill_from_explorer()
            return
        self.wheel.popup(mode, click_mode=False)
        self._fill_from_explorer()
        QTimer.singleShot(0, self.wheel.begin_anim)

    def on_peek(self):
        """Space while dragging: show (or hide) a quick preview of the file being dragged."""
        if self._peek is not None and self._peek.isVisible():
            self._peek.hide()
            return
        paths = self.wheel.paths if self.wheel.is_open() and self.wheel.paths else []
        if not paths:
            hwnd = self.watcher.source_hwnd
            paths = [p for p in winsys.explorer_selection(hwnd) if p and os.path.exists(p)]
        if not paths:
            return
        if self._peek is None:
            self._peek = PeekWindow()
        self._peek.peek(paths)

    def _close_peek(self):
        if self._peek is not None:
            self._peek.hide()

    def _fill_from_explorer(self):
        """Ask Explorer which files are being dragged, so the wheel works even if
        Windows never delivers the drag to it (security software, elevation, Qt quirks)."""
        hwnd = self.watcher.source_hwnd
        paths = [p for p in winsys.explorer_selection(hwnd) if p and os.path.exists(p)]
        winsys.log(f"tap: source={winsys.window_class(hwnd)!r} selection={len(paths)}")
        if paths and not self.wheel.paths:
            self.wheel.set_paths(paths)

    def on_scroll(self, delta):
        w = self.wheel
        if not w.is_open():
            w.popup("convert", click_mode=False)
            self._fill_from_explorer()
            QTimer.singleShot(0, w.begin_anim)
            return
        if not w.click_mode:
            w.scroll_step(1 if delta < 0 else -1)

    def on_drag_cancel(self):
        if self.wheel.is_open() and not self.wheel.click_mode:
            winsys.log("drag cancelled with Esc")
            self.wheel.dismiss()

    def on_drag_move(self):
        w = self.wheel
        if w.is_open() and not w.click_mode:
            w._track(QPointF(w.mapFromGlobal(QCursor.pos())))

    def on_release(self):
        w = self.wheel
        if w.is_open() and not w.click_mode:
            pos = QPointF(w.mapFromGlobal(QCursor.pos()))
            # give a real OLE drop time to arrive; if it doesn't, apply the slice under the cursor
            QTimer.singleShot(350, lambda: self._finish_drag(pos))

    def _finish_drag(self, pos):
        w = self.wheel
        if not w.is_open() or w.click_mode or w.dropped:
            return
        kind, val = w.hit(pos)
        if w.scroll_active and 0 <= w.hover < len(w.ops):
            kind, val = "item", w.hover
        paths = list(w.paths)
        if kind == "item" and paths and 0 <= val < len(w.ops):
            op = w.ops[val]
            winsys.log(f"applied via release fallback: {op.id} on {len(paths)} file(s)")
            w.dismiss()
            QTimer.singleShot(0, lambda: self.execute(op, paths))
        else:
            if kind == "item" and not paths:
                self.toast.show_msg(tr("Couldn't read the dragged file"),
                                    tr("Try again, or select it and press Ctrl+Alt+Space"), "err", 5000)
            w.dismiss()

    def on_hotkey(self):
        if self.wheel.is_open():                   # Ctrl+Alt+Space again closes it
            self.wheel.dismiss()
            return
        paths = winsys.explorer_selection()
        if not paths:
            self.toast.show_msg(tr("Nothing selected"), tr("Select files in File Explorer, then press Ctrl+Alt+Space"))
            return
        self.open_paths(paths)

    def open_paths(self, paths, mode="convert"):
        paths = [str(Path(p)) for p in paths if os.path.exists(p)]
        if paths:
            self.wheel.popup(mode, paths, click_mode=True)

    def queue_paths(self, paths):
        self.pending += paths
        self.pending_timer.start()

    def _flush_pending(self):
        paths, self.pending = list(dict.fromkeys(self.pending)), []
        self.open_paths(paths)

    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(None, tr("Choose files to convert"))
        if files:
            self.open_paths(files)

    # ---- run
    def execute(self, op: engine.Op, paths: list[str]):
        if op.id == "none":
            return
        play_select()
        params = {}
        if getattr(op, "spec", None):
            params["_spec"] = op.spec
        if op.ui == "crop":
            from editor import CropResizeDialog
            for p in paths[:5]:           # one editor per image
                try:
                    dlg = CropResizeDialog(p, DIALOG_CSS, app_icon(), ensure_model=self._ensure_model)
                except Exception as e:
                    self.toast.show_msg(tr("Couldn't open image"), str(e), "err", 6000)
                    continue
                if dlg.exec() == QDialog.Accepted:
                    self._start(op, [p], dlg.params())
            return
        if op.ask:
            params = ask_params(op, paths)
            if params is None:
                return
        if op.model and not engine.model_ready(op.model):
            self._get_model(op, paths, params)
            return
        if op.group == "action":
            try:
                op.fn(paths, params)
            except Exception as e:
                self.toast.show_msg(tr("Couldn't do that"), str(e), "err", 6000)
            return
        self._start(op, paths, params)

    def _get_model(self, op, paths, params):
        """Ask once, then download the AI model `op` needs and run the op when it's ready."""
        self._ensure_model(op.model, tr(op.label).rstrip("…"), lambda: self._start(op, paths, params))

    def predownload(self):
        """Downloads ticked in the installer ("Optional downloads"), one after another, after DragWheel starts."""
        s = settings()
        s.beginGroup("predownload")
        names = [k for k in s.childKeys() if s.value(k) == "1"]
        s.endGroup()
        labels = {"isnet": tr("Remove background"), "whisper-small": tr("Transcribe…").rstrip("…"),
                  "yt-dlp": tr("Play copied link in Float")}
        todo = [n for n in names if n in engine.MODELS]

        def nxt():
            while todo:
                name = todo.pop(0)
                if engine.model_ready(name):
                    settings().remove(f"predownload/{name}")
                    continue

                def done(name=name):
                    settings().remove(f"predownload/{name}")
                    QTimer.singleShot(500, nxt)
                self._ensure_model(name, labels.get(name, name), done, ask=False, on_fail=lambda: QTimer.singleShot(500, nxt))
                return
        if todo:
            winsys.log(f"optional downloads from the installer: {todo}")
            QTimer.singleShot(4000, nxt)

    def _ensure_model(self, name, what, on_ready, ask=True, on_fail=None):
        """Download a model or tool once (after asking), then call on_ready()."""
        if engine.model_ready(name):
            on_ready()
            return
        if not ask:
            return self._download_model(name, what, on_ready, on_fail)
        m = engine.MODELS[name]
        mb = m.get("mb") or m["size"] // 1048576
        box = QMessageBox()
        box.setWindowTitle(APP)
        box.setWindowIcon(app_icon())
        box.setStyleSheet(i18n.css(DIALOG_CSS))
        box.setIconPixmap(app_icon().pixmap(48, 48))
        if name == "yt-dlp":
            box.setText(tr("{what} needs a one-time download of the free yt-dlp tool ({mb} MB) to play links "
                           "from YouTube and other sites.", what=what, mb=mb))
        else:
            box.setText(tr("{what} needs a one-time download of its AI model ({mb} MB). It is saved on this PC, "
                           "and everything runs offline after that.", what=what, mb=mb))
        ok = box.addButton(tr("Download"), QMessageBox.AcceptRole)
        box.addButton(tr("Cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(ok)
        box.exec()
        if box.clickedButton() is not ok:
            return
        self._download_model(name, what, on_ready, on_fail)

    def _download_model(self, name, what, on_ready, on_fail=None):
        job = ModelDownload(name)
        job.setAutoDelete(False)
        self._update_jobs.add(job)

        def cancel():
            job.stop = True
        job.card = self.toast.show_busy(tr("Downloading AI model…") if name != "yt-dlp" else tr("Download") + "…",
                                        what, cancel)

        def progress(done, total, card=job.card):
            if total and card in self.toast.cards:
                card.body.setText(f"{what} — {done * 100 // total}%  ({done / 1048576:.0f} / {total / 1048576:.0f} MB)")

        def finished(path, err, job=job):
            self._update_jobs.discard(job)
            if job.card in self.toast.cards:
                job.card.close_card()
            if err == CANCELLED:
                if on_fail:
                    on_fail()
                return
            if err:
                self.toast.show_msg(tr("Couldn't download the AI model") if name != "yt-dlp" else tr("Couldn't do that"),
                                    err, "err", 8000)
                if on_fail:
                    on_fail()
                return
            winsys.log(f"model {name} ready: {path}")
            on_ready()
        job.sig.progress.connect(progress, Qt.QueuedConnection)
        job.sig.downloaded.connect(finished, Qt.QueuedConnection)
        self.pool.start(job)

    def on_ctrl_open(self, hwnd):
        """Ctrl + double-click on a file in Explorer or on the desktop: open it in a float."""
        def go():
            paths = winsys.explorer_selection(hwnd, focused=True)
            winsys.log(f"ctrl+double-click: {paths}")
            if paths and os.path.exists(paths[0]):
                self.actions.float(paths[:1], {})
        QTimer.singleShot(120, go)

    def open_empty_float(self):
        """Right-click on the desktop → Open Float: an empty float to drop a file on or paste a link into."""
        w = FloatWindow("")
        self.floats.append(w)
        w.closed.connect(lambda w=w: self.floats.remove(w) if w in self.floats else None)
        w.show()
        w.come_forward()
        w.activateWindow()
        w.setFocus()

    def play_link(self, target=None, url=None):
        """Play the link on the clipboard (YouTube and other sites, or a direct media link) in a float.
        The float opens straight away with the loading circle and plays when the link is ready."""
        url = url or QGuiApplication.clipboard().text().strip()
        if not engine.is_link(url):
            self.toast.show_msg(tr("No link on the clipboard"), tr("Copy a link to a video or song first."), "info", 4000)
            return
        from urllib.parse import urlparse
        direct = urlparse(url).path.lower().endswith(engine.MEDIA_LINK_EXT)

        def go():
            t = target if target is not None and target in self.floats else None
            title = next((x.get("title") for x in saved_links() if x["url"] == url), None) or url
            pending = {"page": url, "title": title, "pending": True}
            restore = None
            if t is None:                                      # a new float, loading right away
                t = FloatWindow("", pending)
                self.floats.append(t)
                t.closed.connect(lambda w=t: self.floats.remove(w) if w in self.floats else None)
                t.show()
                t.come_forward()
            elif settings().value("float_link_stops", "true") == "true" or t.kind == "empty":
                if t.kind != "empty":
                    restore = (t.path, t.link)                 # put back if the link doesn't open
                t._load("", pending)                           # stop what's playing, show the loading circle
            t._play_now = True
            self._resolve_and_play(url, t, show_card=False, restore=restore, new=target is None)
        if direct or engine.model_ready("yt-dlp"):
            go()
        else:
            self._ensure_model("yt-dlp", tr("Play copied link"), go)

    def _resolve_and_play(self, url, target, pin=None, quiet=False, quality=None, show_card=True, restore=None, new=False):
        job = LinkResolve(url, quality)
        job.setAutoDelete(False)
        self._update_jobs.add(job)
        self.busy_links = getattr(self, "busy_links", 0) + 1
        card = None if (pin or quiet or not show_card) else self.toast.show_busy(tr("Opening link…"), url[:70])

        def done(info, err, job=job):
            self._update_jobs.discard(job)
            self.busy_links = max(0, getattr(self, "busy_links", 1) - 1)
            if card is not None and card in self.toast.cards:
                card.close_card()
            if not err and info and not pin and not quiet:
                remember_link(info.get("page") or url, info.get("title"))
            if err and pin is not None and pin.get("_tries", 0) < 4:     # at sign-in the network may not be up yet
                pin["_tries"] = pin.get("_tries", 0) + 1
                QTimer.singleShot(15000, lambda: self._resolve_and_play(url, None, pin=pin))
                return
            if err:
                winsys.log(f"link failed: {url}: {err}")
                self.toast.show_msg(tr("Couldn't open this link"), tr(err), "err", 8000)
                if target is not None and target in self.floats and (target.link or {}).get("pending") and not quiet:
                    if new:
                        target.close()                         # the float made just for this link
                    elif restore and (restore[0] or restore[1]):
                        target._play_now = False
                        target._load(*restore)                 # back to what it showed before
                    else:
                        target._load("")
                return
            if target is not None and target in self.floats:
                if quiet:                                  # live stream reconnect: keep size and controls as they are
                    target.restart_live(info)
                    return
                target._load(info["url"], info)
                target._fade_to(1.0)
                QTimer.singleShot(1600, target._maybe_hide_controls)
                return
            w = FloatWindow(info["url"], info, play=bool(pin.get("playing", True)) if pin else False, pin=pin)
            self.floats.append(w)
            w.closed.connect(lambda w=w: self.floats.remove(w) if w in self.floats else None)
            w.show()
            if not pin:
                w.come_forward()
        job.sig.done.connect(done, Qt.QueuedConnection)
        self.pool.start(job)

    def save_clipboard_image(self, folder=None):
        """Save the image on the clipboard: the Convert wheel opens on it so you pick the file type, and the
        file is saved in `folder` (the folder you right-clicked in), or Pictures\\DragWheel from the tray.
        Files copied in Explorer open the wheel directly."""
        import datetime
        import tempfile
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        files = [u.toLocalFile() for u in (md.urls() if md and md.hasUrls() else []) if u.isLocalFile()]
        if files:
            self.open_paths(files)
            return
        img = cb.image()
        if img.isNull():
            self.toast.show_msg(tr("No image on the clipboard"), tr("Copy a picture or take a screenshot first."), "info", 4000)
            return
        if not folder or not os.path.isdir(folder):
            folder = str(Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Pictures" / APP)
            Path(folder).mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.gettempdir()) / "DragWheel-clipboard"
        tmp.mkdir(exist_ok=True)
        path = tmp / f"Clipboard {datetime.datetime.now():%Y-%m-%d %H-%M-%S}.bmp"
        if not img.save(str(path), "BMP"):
            self.toast.show_msg(tr("Couldn't do that"), str(path), "err", 6000)
            return
        self.out_override[str(path)] = folder
        self.wheel.popup("convert", [str(path)], click_mode=True)

    def _media_tick(self):
        """Keyboard media keys control the float that was used last (or one that is playing)."""
        floats = [f for f in self.floats if getattr(f, "player", None)]
        if not floats:
            return
        for vk, key in ((0xB3, "play"), (0xB0, "next"), (0xB1, "prev"), (0xB2, "stop")):
            down = winsys.key_down(vk)
            if down and not self._media_down.get(vk):
                target = FloatWindow.last_used if FloatWindow.last_used in floats else None
                target = target or next((f for f in floats if f._playing()), floats[-1])
                focused = target.isActiveWindow()
                shown = target.media_key(key)
                if shown and MediaOSD.wanted(focused):
                    MediaOSD.flash(shown, target)
            self._media_down[vk] = down
    def _update_cursor_busy(self):
        busy = bool(self._active_jobs() or getattr(self, "busy_links", 0))
        self.cursor_busy.set_busy(busy and settings().value("cursor_busy", "true") == "true")

    def on_volume_key(self, vk):
        """Volume keys or a volume knob: Windows changes the volume; show it big while a float is playing.
        Every step refreshes the sign; it goes away 2 seconds after the last one."""
        playing = [f for f in self.floats if getattr(f, "player", None) and f._playing()]
        if not playing:
            return
        target = FloatWindow.last_used if FloatWindow.last_used in playing else playing[-1]
        if MediaOSD.wanted(target.isActiveWindow()):
            QTimer.singleShot(40, lambda t=target: self._show_volume(t))

    def _show_volume(self, target):
        v = winsys.system_volume()
        if v is not None:
            MediaOSD.flash("mute" if v[1] else "volume", target, level=v[0], hold=2000)

    def _start(self, op, paths, params):
        name = Path(paths[0]).name if len(paths) == 1 else tr("{n} files", n=len(paths))
        w = Worker(op, paths, params)
        w.output_dir = self.out_override.get(paths[0])     # e.g. clipboard image saved "here"
        cancel = lambda w=w: self._cancel_job(w)
        if op.group == "convert":
            w.card = self.toast.show_busy(tr("Converting to {fmt}…", fmt=tr(op.label)), name, cancel)
        else:
            w.card = self.toast.show_busy(tr(op.label).rstrip("…") + "…", name, cancel)
        w.setAutoDelete(False)
        w.sig.done.connect(self._done, Qt.QueuedConnection)
        w.sig.progress.connect(lambda wk, f, name=name: self._job_progress(wk, f, name), Qt.QueuedConnection)
        w.sig.count.connect(self._job_count, Qt.QueuedConnection)
        if settings().value("job_mode", "queue") == "queue" and self._active_jobs():
            self.waiting.append(w)                # one job at a time: wait for the ones before it
            w.card.body.setText(name + " — " + tr("waiting ({n} in line)", n=len(self.waiting)))
            return
        self._launch(w)

    def _launch(self, w):
        self.running.add(w)                       # keep Python refs alive until done
        self.pool.start(w)

    def _next_in_line(self):
        while self.waiting and not self._active_jobs():
            w = self.waiting.pop(0)
            if w.cancel_requested:
                continue
            if w.card is not None and w.card in self.toast.cards:
                w.card.body.setText(Path(w.paths[0]).name if len(w.paths) == 1 else tr("{n} files", n=len(w.paths)))
            self._launch(w)
        for i, w in enumerate(self.waiting):
            if w.card is not None and w.card in self.toast.cards:
                name = Path(w.paths[0]).name if len(w.paths) == 1 else tr("{n} files", n=len(w.paths))
                w.card.body.setText(name + " — " + tr("waiting ({n} in line)", n=i + 1))

    def _job_count(self, worker, done, total):
        worker.count = (done, total)

    def _job_progress(self, worker, frac, name):
        card = worker.card
        if card is not None and card in self.toast.cards and not worker.cancel_requested:
            done, total = worker.count
            if total > 1:                      # a batch: "12 of 40 done — 31%"
                card.body.setText(tr("{a} of {b} done", a=done, b=total) + f" — {int(frac * 100)}%")
            else:
                card.body.setText(f"{name} — {int(frac * 100)}%")

    # ---- updating: warn about running jobs, keep the open floats
    def _ask_jobs_before_update(self, installer_waiting):
        """None = no jobs. Otherwise the button chosen: "now" | "wait" | "cancel"."""
        jobs = self._active_jobs()
        if not jobs:
            return None
        box = QMessageBox()
        box.setWindowTitle(f"{APP} — " + tr("Update"))
        box.setWindowIcon(app_icon())
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        box.setStyleSheet(i18n.css(DIALOG_CSS))
        box.setIconPixmap(app_icon().pixmap(48, 48))
        names = "<br>".join(f"• {Path(w.paths[0]).name}" for w in jobs[:5])
        box.setText(f"<b>{tr('Jobs still running: {n}', n=len(jobs))}</b><br><br>{names}<br><br>"
                    + tr("Updating closes DragWheel and stops them; their unfinished files are removed."))
        now = box.addButton(tr("Stop them and update"), QMessageBox.DestructiveRole)
        wait = None if installer_waiting else box.addButton(tr("Update when they finish"), QMessageBox.AcceptRole)
        no = box.addButton(tr("Don't update now"), QMessageBox.RejectRole)
        box.setDefaultButton(wait or no)
        box.exec()
        b = box.clickedButton()
        return "now" if b is now else "wait" if (wait is not None and b is wait) else "cancel"

    def save_open_floats(self):
        states = []
        for f in list(self.floats):
            try:
                states.append(f.state())
            except Exception as e:
                winsys.log(f"float state: {e}")
        settings().setValue("float_resume", json.dumps(states))
        settings().sync()
        winsys.log(f"saved {len(states)} open floats for after the update")

    def prepare_for_update(self) -> bool:
        """The installer is about to replace DragWheel (asked over the local socket). False = the user said not now."""
        if not getattr(self, "_update_confirmed", False):
            choice = self._ask_jobs_before_update(installer_waiting=True)
            if choice == "cancel":
                return False
        for w in self._active_jobs():
            self._cancel_job(w)
        self.save_open_floats()
        return True

    def quit_for_update(self, started=None):
        """Quit once cancelled jobs have cleaned up (at most ~6 s)."""
        import time
        started = started or time.monotonic()
        if self.running and time.monotonic() - started < 6:
            QTimer.singleShot(200, lambda: self.quit_for_update(started))
            return
        for f in list(self.floats):
            if f.player:
                f.player.stop()
        self.qapp.quit()

    def _cancel_job(self, worker):
        if worker.cancel_requested:
            return
        play_finish_sound("err")
        if worker in self.waiting:                 # not started yet: just take it out of the line
            self.waiting.remove(worker)
            worker.cancel()
            if worker.card is not None and worker.card in self.toast.cards:
                worker.card.show_msg(tr("Cancelled"), tr("Nothing was saved."), "info", 3000)
            self._next_in_line()
            return
        worker.cancel()
        if worker.card is not None and worker.card in self.toast.cards:
            worker.card.show_busy(tr("Cancelling…"), Path(worker.paths[0]).name)

    def _done(self, worker, outs, err):
        self.running.discard(worker)
        QTimer.singleShot(0, self._next_in_line)
        op = worker.op
        card = worker.card if worker.card is not None and worker.card in self.toast.cards else None
        target = card or self.toast
        if card is not None and err != CANCELLED:
            card._sound_for_this = True            # finish sound (when turned on)
        elif card is None and err != CANCELLED and not err:
            play_finish_sound("ok")
        if err == CANCELLED:
            target.show_msg(tr("Cancelled"), tr("Nothing was saved."), "info", 3000)
        elif err:
            winsys.log(f"job failed: {op.group}/{op.id} on {worker.paths[:3]}: {err}")
            target.show_msg(tr("{what} failed", what=tr(op.label).rstrip("…")), tr(err), "err", 8000)
        elif op.id == "install" and outs:
            names = [json.loads(str(o)[5:]).get("font", "") for o in outs if str(o).startswith("info:")]
            target.show_msg(tr("Font installed"), ", ".join(names) + "<br>" + tr("Ready in your apps (restart an app if it was open)."), "ok", 8000)
        elif op.id == "count" and outs:
            infos = [json.loads(str(o)[5:]) for o in outs if str(o).startswith("info:")]
            tot = {k: sum(i.get(k, 0) for i in infos) for k in ("words", "chars", "chars_spaces", "pages")}
            title = infos[0]["name"] if len(infos) == 1 else tr("{n} files", n=len(infos))
            lines = [tr("Words: {n}", n=f"{tot['words']:,}"),
                     tr("Characters: {n} ({m} with spaces)", n=f"{tot['chars']:,}", m=f"{tot['chars_spaces']:,}")]
            if any("pages" in i for i in infos):
                lines.append(tr("Pages: {n}", n=f"{tot['pages']:,}"))
            minutes = max(1, round(tot["words"] / 200))
            lines.append(tr("About {n} min to read", n=minutes))
            QGuiApplication.clipboard().setText("\n".join([title] + lines))
            target.show_msg(title, "<br>".join(lines), "ok", 12000)
        elif op.id == "ocr" and outs:
            try:
                QGuiApplication.clipboard().setText(Path(outs[0]).read_text(encoding="utf-8").strip())
                target.show_result(tr("Copied to clipboard"), outs)
            except Exception as e:
                target.show_msg(tr("Couldn't do that"), str(e), "err", 6000)
        else:
            outs = self._place_results(worker, outs)
            if outs is None:
                if card is not None:
                    card.close_card()
                return
            title = tr("Done") if op.group == "tool" else tr("Converted to {fmt}", fmt=tr(op.label))
            if worker.failed:
                names = ", ".join(n for n, _e in worker.failed[:3]) + ("…" if len(worker.failed) > 3 else "")
                winsys.log(f"batch: {len(worker.failed)} failed: " + " | ".join(f"{n}: {e}" for n, e in worker.failed[:10]))
                c = target.show_msg(title, tr("{a} of {b} done. These couldn't be done: {names}",
                                              a=len(worker.paths) - len(worker.failed), b=len(worker.paths), names=names),
                                    "err", 12000) or target
                c.target = [str(o) for o in outs]
                c.btn.setVisible(bool(outs))
                c.set_undo(self._undo_for(outs, worker))
            else:
                c = target.show_result(title, outs) or target
                c.set_undo(self._undo_for(outs, worker))
            self._remember(outs, worker)

    def _undo_for(self, outs, worker):
        """Undo for files a job just made — not when they replaced the originals or went to the clipboard."""
        outs = [Path(o) for o in outs or [] if o]
        if not outs or settings().value("output_mode", "next") in ("replace", "clipboard"):
            return None
        srcs = {str(Path(p)).lower() for p in worker.paths}
        if any(str(o).lower() in srcs for o in outs):            # edited in place: nothing to take back safely
            return None

        def undo():
            ok = True
            for o in outs:
                try:
                    if o.exists():
                        winsys.recycle(str(o))
                except Exception as e:
                    winsys.log(f"undo: {o}: {e}")
                    ok = False
            self._forget(outs)
            winsys.log(f"undo: {len(outs)} result(s) to the Recycle Bin")
            return ok
        return undo

    # ---- recent results (tray menu)
    def _remember(self, outs, worker):
        try:
            recent = json.loads(settings().value("recent_results", "[]") or "[]")
        except (TypeError, ValueError):
            recent = []
        what = tr("Converted to {fmt}", fmt=tr(worker.op.label)) if worker.op.group == "convert" else tr(worker.op.label).rstrip("…")
        for o in outs or []:
            o = str(o)
            if not o or o.startswith("info:"):
                continue
            recent = [r for r in recent if r.get("path") != o]
            recent.insert(0, {"path": o, "what": what})
        settings().setValue("recent_results", json.dumps(recent[:10], ensure_ascii=False))

    def _forget(self, outs):
        try:
            recent = json.loads(settings().value("recent_results", "[]") or "[]")
        except (TypeError, ValueError):
            return
        gone = {str(o) for o in outs}
        settings().setValue("recent_results", json.dumps([r for r in recent if r.get("path") not in gone], ensure_ascii=False))

    def _fill_recent(self, sub):
        sub.clear()
        try:
            recent = json.loads(settings().value("recent_results", "[]") or "[]")
        except (TypeError, ValueError):
            recent = []
        recent = [r for r in recent if os.path.exists(r.get("path", ""))]
        if not recent:
            a = sub.addAction(tr("Nothing yet"))
            a.setEnabled(False)
            return
        from PySide6.QtCore import QFileInfo
        from PySide6.QtWidgets import QFileIconProvider
        prov = QFileIconProvider()
        for r in recent:
            p = Path(r["path"])
            name = p.name if len(p.name) <= 46 else p.name[:43] + "…"
            m = sub.addMenu(prov.icon(QFileInfo(str(p))), name)
            m.setToolTipsVisible(True)
            m.addAction(tr("Open"), lambda p=p: os.startfile(str(p)) if hasattr(os, "startfile") else None)
            m.addAction(tr("Show in folder"), lambda p=p: winsys.reveal([str(p)]))
            m.addAction(tr("Open in Float"), lambda p=p: self.actions.float([str(p)], {}))
            info = m.addAction(r.get("what", ""))
            info.setEnabled(False)
        sub.addSeparator()
        sub.addAction(tr("Clear this list"), lambda: settings().setValue("recent_results", "[]"))

    def _place_results(self, worker, outs):
        """Where results go (Settings → Output): replace the original (asks first) or copy to the clipboard.
        Returns the final paths, or None when the clipboard took them."""
        mode = settings().value("output_mode", "next")
        outs = [Path(o) for o in outs if o]
        if worker.paths and worker.paths[0] in self.watch.done:
            return outs                                  # watch folders keep results in their own folder
        if not outs or mode not in ("replace", "clipboard"):
            return outs
        if mode == "clipboard":
            import tempfile
            dest = Path(tempfile.gettempdir()) / "DragWheel clipboard"
            dest.mkdir(exist_ok=True)
            moved = []
            for o in outs:
                t = engine.unique_path(dest / o.name)
                shutil.move(str(o), str(t))
                moved.append(t)
            md = QMimeData()
            md.setUrls([QUrl.fromLocalFile(str(m)) for m in moved])
            if len(moved) == 1 and engine.EXT_CATEGORY.get(engine.ext_of(str(moved[0]))) == "image":
                img = QImage(str(moved[0]))
                if not img.isNull():
                    md.setImageData(img)                      # paste works in chat apps and editors too
            QGuiApplication.clipboard().setMimeData(md)
            self.toast.show_msg(tr("Copied to clipboard"), moved[0].name if len(moved) == 1 else
                                tr("{n} files", n=len(moved)), "ok", 4000)
            return None
        # replace: only when each result clearly belongs to one original
        src = [Path(p) for p in worker.paths]
        if worker.op.multi or len(src) != len(outs) or any(o.is_dir() for o in outs):
            return outs
        if settings().value("replace_no_ask", "false") != "true":
            box = QMessageBox()
            box.setWindowTitle(f"{APP} — " + tr("Replace the original"))
            box.setWindowIcon(app_icon())
            box.setStyleSheet(i18n.css(DIALOG_CSS))
            box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            pairs = "<br>".join(f"{a.name} → {b.name}" for a, b in list(zip(src, outs))[:6])
            box.setText(tr("Replace the original file(s) with the new one(s)? The originals go to the Recycle Bin.")
                        + "<br><br>" + pairs)
            again = QCheckBox(tr("Don't ask again"))
            box.setCheckBox(again)
            yes = box.addButton(tr("Replace"), QMessageBox.AcceptRole)
            box.addButton(tr("Keep both"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not yes:
                return outs
            if again.isChecked():
                settings().setValue("replace_no_ask", "true")
        final = []
        for a, b in zip(src, outs):
            try:
                winsys.recycle(str(a))
                target = a.with_suffix(b.suffix) if a.suffix.lower() != b.suffix.lower() else a
                if target.exists():
                    target = engine.unique_path(target)
                shutil.move(str(b), str(target))
                final.append(target)
            except Exception as e:
                winsys.log(f"replace failed for {a}: {e}")
                final.append(b)
        return final

    # ---- updates
    def _auto_update_check(self):
        import time
        s = settings()
        if s.value("check_updates", "true") != "true":
            return
        if time.time() - float(s.value("last_update_check", 0) or 0) < 20 * 3600:
            return
        self.check_updates(manual=False)

    def check_updates(self, manual=True):
        import time
        settings().setValue("last_update_check", time.time())
        job = UpdateCheck(manual)
        job.setAutoDelete(False)
        self._update_jobs.add(job)
        job.sig.checked.connect(lambda rel, err, m, job=job: self._update_checked(job, rel, err, m), Qt.QueuedConnection)
        job.card = self.toast.show_busy(tr("Checking for updates…"), "github.com/" + updater.REPO) if manual else None
        self.pool.start(job)

    def _update_checked(self, job, rel, err, manual):
        self._update_jobs.discard(job)
        card = getattr(job, "card", None) if job is not None else None
        card = card if card is not None and card in self.toast.cards else None
        target = card or self.toast
        winsys.log(f"update check: latest={getattr(rel, 'version', None)} err={err}")
        if err:
            if manual:
                target.show_msg(tr("Couldn't check for updates"), err, "err", 6000)
            return
        if not updater.is_newer(rel.version, VERSION):
            if manual:
                target.show_msg(tr("You're up to date"), tr("{app} {v} is the latest version.", app=APP, v=VERSION), "ok", 4000)
            return
        if not manual and settings().value("skip_version", "") == rel.version:
            return
        if card:
            card.close_card()
        self._offer_update(rel)

    def _offer_update(self, rel):
        box = QMessageBox()
        box.setWindowTitle(tr("{app} update", app=APP))
        box.setWindowIcon(app_icon())
        box.setStyleSheet(i18n.css(DIALOG_CSS))
        box.setIconPixmap(app_icon().pixmap(48, 48))
        box.setTextFormat(Qt.RichText)
        notes = rel.notes.split("\n\n")[0][:400].replace("**", "") if rel.notes else ""
        dimc = theme.hexc("dim")
        box.setText(f"<b>{tr('{app} {v} is available', app=APP, v=rel.version)}</b><br>"
                    f"<span style='color:{dimc}'>{tr('You have {v}.', v=VERSION)}</span><br><br>{notes}")
        install = box.addButton(tr("Download && install"), QMessageBox.AcceptRole) if rel.installer_url else None
        page = box.addButton(tr("Open release page"), QMessageBox.ActionRole)
        skip = box.addButton(tr("Skip this version"), QMessageBox.RejectRole)
        later = box.addButton(tr("Later"), QMessageBox.RejectRole)
        box.setDefaultButton(install or page)
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        box.exec()
        clicked = box.clickedButton()
        if clicked is install:
            self._download_update(rel)
        elif clicked is page:
            QDesktopServices.openUrl(QUrl(rel.page))
        elif clicked is skip:
            settings().setValue("skip_version", rel.version)

    def _download_update(self, rel):
        job = UpdateDownload(rel)
        job.setAutoDelete(False)
        self._update_jobs.add(job)

        def cancel():
            job.stop = True
        name = rel.installer_name or "DragWheel-Setup.exe"
        job.card = self.toast.show_busy(tr("Downloading update…"), name, cancel)

        def progress(done, total, card=job.card):
            if total and card in self.toast.cards:
                card.body.setText(f"{name} — {done * 100 // total}%  ({done / 1048576:.0f} / {total / 1048576:.0f} MB)")
        job.sig.progress.connect(progress, Qt.QueuedConnection)
        job.sig.downloaded.connect(lambda path, err, job=job: self._update_downloaded(job, path, err), Qt.QueuedConnection)
        self.pool.start(job)

    def _update_downloaded(self, job, path, err):
        self._update_jobs.discard(job)
        card = job.card if job.card in self.toast.cards else None
        if card:
            card.close_card()
        if err == CANCELLED:
            self.toast.show_msg(tr("Cancelled"), tr("The update was not downloaded."), "info", 3000)
            return
        if err:
            self.toast.show_msg(tr("Couldn't download the update"), err, "err", 8000)
            return
        choice = self._ask_jobs_before_update(installer_waiting=False)
        if choice == "cancel":
            self.toast.show_msg(tr("Update postponed"), tr("Check for updates again from the tray when you're ready."), "info", 5000)
            return
        if choice == "wait":
            self.toast.show_msg(tr("Update waiting"), tr("It installs when the running jobs finish."), "info", 5000)
            self._install_when_idle(path)
            return
        self._update_confirmed = choice == "now"
        self._launch_installer(path)

    def _install_when_idle(self, path):
        if self._active_jobs():
            QTimer.singleShot(1500, lambda: self._install_when_idle(path))
            return
        self._launch_installer(path)

    def _launch_installer(self, path):
        winsys.log(f"launching installer {path}")
        try:
            os.startfile(str(path))          # Windows asks for admin
        except Exception as e:
            self.toast.show_msg(tr("Couldn't start the installer"), str(e), "err", 8000)
            return
        self.toast.show_msg(tr("Installing update…"), tr("Finish the steps in the setup window."), "info", 4000)
        # Keep running: the installer closes DragWheel itself when Install is pressed
        # (and cancelling setup leaves the app running).

    # ---- windows
    def show_settings(self):
        open_one = getattr(self, "_settings_dlg", None)
        if open_one is not None:                    # already open: bring it forward instead of a second one
            open_one.raise_()
            open_one.activateWindow()
            return
        self._settings_dlg = SettingsDialog(self)
        try:
            self._settings_dlg.exec()
        finally:
            self._settings_dlg = None

    def show_tour(self, parent=None):
        if parent is not None:                 # from Settings: on top of it, and usable while it's open
            TourDialog(self, parent).exec()
            return
        d = TourDialog(self)
        d.show()
        d.raise_()
        d.activateWindow()
        self._tour = d

    def show_help(self):
        k = {m: tr(v) for m, v in mode_keys().items()}
        message(tr("{app} — How it works", app=APP), tr("HELP_HTML", app=APP, convert=k["convert"],
                                                         tool=k["tool"], action=k["action"])
                + "<br><br>" + tr("HELP_SCROLL"))


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
    import shutil
    shutil.rmtree(d, ignore_errors=True)
    return 0


def main():
    import multiprocessing
    multiprocessing.freeze_support()      # worker processes of the frozen exe start here and exit
    args = sys.argv[1:]
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

    flags, paths = parse_args(sys.argv[1:])
    if "--selftest" in flags:
        return selftest()
    if "--prepare-update" in flags:            # run by the installer: 0 = go ahead, 1 = the user said not now
        return ask_running_to_close()
    if send_to_running({"paths": paths, "flags": sorted(flags)}):
        return 0

    i18n.set_language(settings().value("language", ""))
    theme.set_mode(settings().value("theme", "system"))
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
            winsys.set_context_menu(True, paste_label=tr("Save clipboard image here"), link_label=tr("Play copied link in Float"),
                                    float_label=tr("Open Float"))
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
                winsys.set_context_menu(True, paste_label=tr("Save clipboard image here"), link_label=tr("Play copied link in Float"),
                                    float_label=tr("Open Float"))
            except Exception:
                pass
        pass
    if (first_run or settings().value("tour_at_start", "true") == "true") and not paths and not (
            flags & {"--send-phone", "--play-link", "--paste-here", "--open-float"}):
        QTimer.singleShot(600, app.show_tour)         # until "Don't show this again" is ticked
    if "--send-phone" in flags and paths:
        QTimer.singleShot(300, lambda: app.actions.phone(paths, {}))
    elif "--open-float" in flags:
        QTimer.singleShot(300, app.open_empty_float)
    elif "--play-link" in flags:
        QTimer.singleShot(400, app.play_link)
    elif "--paste-here" in flags:
        QTimer.singleShot(300, lambda: app.save_clipboard_image(paths[0] if paths else None))
    elif paths:
        app.queue_paths(paths)
    elif "--tray" not in flags and not first_run:
        app.tray.showMessage(APP, tr("Running in the tray. Drag a file and shake the mouse.") if mode_keys()["convert"] == "None"
                             else tr("Running in the tray. Drag a file and tap {key}.", key=tr(mode_keys()["convert"])),
                             app_icon(), 3000)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
