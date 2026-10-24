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
import sys
import threading
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import (QEasingCurve, QObject, QPointF, QPropertyAnimation, QRectF, QRunnable, QSizeF, QVariantAnimation,
                            QRect, QSettings, QSize, Qt, QThreadPool, QTimer, QUrl, Signal, QMimeData, QPoint)
from PySide6.QtGui import (QAction, QBrush, QColor, QCursor, QDesktopServices, QDrag, QFont, QFontMetrics,
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
VERSION = "1.2.0"

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
        title = QLabel("<b>" + tr("Scan with your phone's camera") + "</b>")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        self.qr = QLabel()
        self.qr.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.qr)
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
            self.qr.setPixmap(QPixmap.fromImage(QImage.fromData(buf.getvalue())))
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
            A("phone", "Send to phone", self.phone, "over Wi-Fi"),
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
        w = PhoneShare(paths)
        self.app._phone_windows = getattr(self.app, "_phone_windows", [])
        self.app._phone_windows.append(w)
        w.show()
        w.raise_()

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


class Worker(QRunnable):
    def __init__(self, op, paths, params):
        super().__init__()
        self.op, self.paths, self.params = op, paths, params
        self.sig = WorkerSignals()
        self.cancel_requested = False
        self.card = None

    def cancel(self):
        self.cancel_requested = True

    def run(self):
        """The job runs in its own process (jobproc) so Cancel can stop it instantly."""
        try:
            import jobproc
            job = jobproc.JobProcess(self.op.group, self.op.id, self.paths, self.params,
                                     getattr(self, "output_dir", None) or engine.OUTPUT_DIR,
                                     on_progress=lambda f: self.sig.progress.emit(self, f))
            kind, val = job.run(lambda: self.cancel_requested)
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
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.sig = LinkSignals()

    def run(self):
        try:
            self.sig.done.emit(engine.resolve_link(self.url), None)
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
        self._resize_for(1)

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
        self.update()

    def set_paths(self, paths):
        self.paths = paths
        self.set_mode(self.mode)

    # ------------------------------------------------------------- show/hide
    def popup(self, mode, paths=None, click_mode=False, at: QPoint | None = None):
        self.click_mode = click_mode
        self.dropped = False
        self.scroll_active = False
        self.scroll_anchor = None
        self.paths = paths or []
        self.mode = mode
        self.set_mode(mode)
        pos = at or QCursor.pos()
        c = self.center()
        geo = QGuiApplication.screenAt(pos).availableGeometry() if QGuiApplication.screenAt(pos) else None
        x, y = int(pos.x() - c.x()), int(pos.y() - c.y())
        if geo and click_mode:   # keep it fully on-screen when not dragging
            x = max(geo.left(), min(x, geo.right() - self.width()))
            y = max(geo.top(), min(y, geo.bottom() - self.height()))
        self.move(x, y)
        self.setWindowOpacity(0.0)
        if click_mode:
            self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, False)
        else:
            self.setWindowFlag(Qt.WindowDoesNotAcceptFocus, True)
        self.show()
        self.raise_()
        if click_mode:
            self.activateWindow()
            self.setFocus()
        self.opacity_anim.stop()
        self.opacity_anim.setStartValue(0.0)
        self.opacity_anim.setEndValue(1.0)
        self.opacity_anim.start()

    def dismiss(self):
        self.pill_timer.stop()
        self.hide()
        self.paths = []
        self.ops = []
        self.hover = -1

    # ------------------------------------------------------------- drag & drop
    def _paths_from(self, md) -> list[str]:
        return [u.toLocalFile() for u in md.urls() if u.isLocalFile() and u.toLocalFile()]

    def dragEnterEvent(self, e):
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
            self.hover = new_hover
            self.update()
        return kind

    def _pill_dwell(self):
        if self.hover_pill:
            self.set_mode(self.hover_pill)

    # ------------------------------------------------------------- click mode
    def mouseMoveEvent(self, e):
        self._track(e.position())

    def mousePressEvent(self, e):
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
            self.update()
        elif k in (Qt.Key_Left, Qt.Key_Up) and n:
            self.hover = (self.hover - 1) % n if self.hover >= 0 else n - 1
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
                    self.set_mode(m)

    def focusOutEvent(self, e):
        if self.click_mode:
            QTimer.singleShot(120, lambda: (not self.isActiveWindow()) and self.dismiss())

    # ------------------------------------------------------------- painting
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        c = self.center()
        rings = self._rings()
        outer = rings[-1][1]

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
                if n == 1:                            # a single slice is the whole ring, no seam
                    path = QPainterPath()
                    path.setFillRule(Qt.OddEvenFill)
                    path.addEllipse(c, r1 - 3, r1 - 3)
                    path.addEllipse(c, r0 + 3, r0 + 3)
                else:
                    path = self._wedge(c, r0 + 3, r1 - 3, a_mid - step / 2 + 0.9, step - 1.8)
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
            offset += n

        # center
        p.setPen(Qt.NoPen)
        p.setBrush(C("ring_hover") if self.hover == -2 else C("ring"))
        p.drawEllipse(c, self.R_IN - 4, self.R_IN - 4)
        self._center_text(p, c)

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
            p.drawText(r, Qt.AlignCenter, f"{tr(keys[m])}  ·  {tr(MODE_LABEL[m])}")
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
        self.cancel_btn = QPushButton()
        self.cancel_btn.setObjectName("cancel")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._cancel)
        lay.addWidget(self.cancel_btn)
        self.timer = QTimer(self, singleShot=True, timeout=self.close_card)
        self.target = None
        self.on_cancel = None
        self.spin = 0
        self.spin_timer = QTimer(self, interval=60, timeout=self._spin)
        self.restyle()

    def restyle(self):
        """Apply the current language's font and button texts."""
        self.setStyleSheet(i18n.css(self.TOAST_CSS))
        self.btn.setText(tr("Show"))
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
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawEllipse(3, 3, 24, 24)
            p.setPen(QPen(ON_ACCENT if kind != "err" else QColor("#ffffff"), 2.6))
            if kind == "ok":
                p.drawPolyline([QPointF(9, 15.5), QPointF(13.5, 20), QPointF(21, 11)])
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
        self.restyle()
        self.title.setText(title)
        self.body.setText(body)
        self.btn.setVisible(show_btn)
        self.on_cancel = cancel
        self.cancel_btn.setVisible(cancel is not None)
        if kind == "busy":
            self.spin_timer.start()
        else:
            self.spin_timer.stop()
        self._set_icon(kind)
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

    def show_result(self, title, outs):
        outs = [Path(o) for o in outs if o]
        self.target = [str(o) for o in outs] if outs else None     # all of them get selected
        body = outs[0].name if len(outs) == 1 else tr("{n} items saved", n=len(outs))
        self._show(title, body, "ok", show_btn=bool(self.target), ms=5000)

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
        args = ["-hide_banner", "-loglevel", "error", "-fflags", "+genpts"]
        ua = next((v for k, v in hdr.items() if k.lower() == "user-agent"), None)
        if ua:
            args += ["-user_agent", ua]
        extra = "".join(f"{k}: {v}\r\n" for k, v in hdr.items() if k.lower() != "user-agent")
        if extra:
            args += ["-headers", extra]
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
                sent = 0
                try:
                    while True:
                        chunk = proc.stdout.read(65536)
                        if not chunk:
                            break
                        h.wfile.write(chunk)
                        sent += len(chunk)
                except OSError:
                    pass                                       # the float closed or reconnected
                finally:
                    try:
                        proc.kill()
                        err = proc.stderr.read().decode("utf-8", "replace").strip()
                    except Exception:
                        err = ""
                    winsys.log(f"live relay: ffmpeg stopped after {sent // 1024} KB" + (f": {err[-300:]}" if err else ""))
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


def _float_pins() -> list:
    """Floats that reopen when Windows starts: [{"id", "src", "link", "x", "y", "w", "on_top"}]."""
    try:
        v = json.loads(settings().value("float_pins", "[]") or "[]")
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


def _save_float_pins(pins):
    settings().setValue("float_pins", json.dumps(pins))


class FloatWindow(QWidget):
    closed = Signal()
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
        if self._live():
            self._start_relay()
            self.player.mediaStatusChanged.connect(lambda st: winsys.log(f"float: live status {st.name}"))
            self.player.setSource(QUrl(self._relay.url))
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
        self.companion.setSource(QUrl(audio_url))
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
        if busy and self.link and now - getattr(self, "_busy_since", now) > 15 \
                and now - getattr(self, "_last_refresh", 0) > 45:
            self.refresh_link(auto=True)                      # stuck: fetch a fresh link by itself
        if busy or busy != self._busy:
            self._spin = (self._spin + 12) % 360
            self._busy = busy
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
        if status == QMediaPlayer.EndOfMedia and settings().value("float_autoplay", "true") == "true":
            if self._neighbour(1):
                QTimer.singleShot(300, lambda: self._step(1))

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

    def restart_live(self, info):
        """The link was renewed: keep the float as it is (size, place, volume) and carry on playing —
        live streams through a fresh relay, other videos from where they were."""
        if self.player is None or info.get("audio") or self.companion is not None:
            pos = 0 if (self.player is None or info.get("live")) else self.player.position()
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
        else:
            self._stop_relay()
            self._resume_ms = pos
            self.autoplay = True
            self.player.setSource(QUrl(info["url"]))
        self.player.play()

    def refresh_link(self, auto=False):
        """Ask the site again for the video (its links expire) and continue."""
        if not self.link or _APP is None:
            return
        import time
        self._last_refresh = time.monotonic()
        winsys.log(f"float: refresh link ({'automatic, stuck loading' if auto else 'from the menu'})")
        self._live_fixing = time.monotonic()
        _APP._resolve_and_play(self.link["page"], self, quiet=True)

    def _live_continue(self, error=False):
        import time
        now = time.monotonic()
        recent = [t for t in getattr(self, "_live_reloads", []) if now - t < 20] + [now]
        self._live_reloads = recent
        if len(recent) > 4 or error:                    # the link expired or keeps failing: ask YouTube again
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
            QTimer.singleShot(500, lambda: self._live_continue(error=True))
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
            return
        if key == "play":
            self._toggle_play()
        elif key == "stop":
            self.player.pause()
            self.player.setPosition(0)
        else:
            self._step(1 if key == "next" else -1)

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
        if getattr(self, "_busy", False) and self.player is not None and self.kind == "video":
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
        elif e.key() in (Qt.Key_PageUp, Qt.Key_PageDown, Qt.Key_MediaPrevious, Qt.Key_MediaNext) and self.player:
            self._step(-1 if e.key() in (Qt.Key_PageUp, Qt.Key_MediaPrevious) else 1)
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
            m.addSeparator()
        m.addAction(tr("Open"), self._open_original)
        if self.link:
            m.addAction(tr("Copy"), lambda: QGuiApplication.clipboard().setText(self.link["page"]))
        else:
            m.addAction(tr("Show in Explorer"), lambda: winsys.reveal(self.path))
            m.addAction(tr("Copy path"), lambda: QGuiApplication.clipboard().setText(str(Path(self.path))))
        if self.link:
            m.addAction(tr("Refresh"), self.refresh_link)
        if _APP is not None:
            m.addAction(tr("Play copied link"), lambda: _APP.play_link(target=self))
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
KEY_NAMES = ["Shift", "Ctrl", "Alt", "CapsLock"]


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
            "startup": self.startup.isChecked(),
            "menu": self.menu.isChecked(),
            "hotkey": self.hotkey.isChecked(),
            "auto_update": self.auto_update.isChecked(),
            "autoplay": self.autoplay.isChecked(),
            "on_top": self.on_top.isChecked(),
            "ctrl_open": self.ctrl_open.isChecked(),
        }

    def _initial(self) -> dict:
        s = settings()
        return {
            "keys": mode_keys(),
            "detect": int(s.value("detect_any", 0)),
            "scroll": s.value("scroll", "true") == "true",
            "out": s.value("output_dir", ""),
            "startup": winsys.startup_enabled(),
            "menu": winsys.context_menu_enabled(),
            "hotkey": s.value("hotkey", "true") == "true",
            "auto_update": s.value("check_updates", "true") == "true",
            "autoplay": s.value("float_autoplay", "true") == "true",
            "on_top": s.value("float_on_top", "true") == "true",
            "ctrl_open": s.value("float_ctrl_open", "true") == "true",
        }

    def _theme_changed(self, _idx):
        code = self.theme_box.currentData()
        if code == theme.mode():
            return
        state = self._state()
        settings().setValue("theme", code)
        self.app.apply_theme()
        QTimer.singleShot(0, lambda: self._build(state))

    def _language_changed(self, _idx):
        code = self.lang.currentData()
        if code == settings().value("language", ""):
            return
        state = self._state()
        settings().setValue("language", code)
        self.app.apply_language()
        QTimer.singleShot(0, lambda: self._build(state))     # rebuild outside the combo's signal

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
        self.tabs.addTab(self._settings_tab(st), tr("Settings"))
        self.tabs.addTab(self._about_tab(st), tr("About"))
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
        for code, label in (("system", tr("System default")), ("dark", tr("Dark")), ("light", tr("Light"))):
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
        lay.addWidget(g1)

        g2 = QGroupBox(tr("Output"))
        f2 = QFormLayout(g2)
        row = QHBoxLayout()
        self.out = QLineEdit(st["out"])
        self.out.setPlaceholderText(tr("Next to the original file"))
        b = QPushButton(tr("Browse…"))
        b.clicked.connect(lambda: self.out.setText(QFileDialog.getExistingDirectory(self, tr("Output folder")) or self.out.text()))
        row.addWidget(self.out, 1)
        row.addWidget(b)
        f2.addRow(tr("Save to"), row)
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

    def save(self):
        keys = {m: cb.currentData() for m, cb in self.key_boxes.items()}
        if len(set(keys.values())) < 3:
            QMessageBox.warning(self, APP, tr("Each wheel needs a different key."))
            return
        s = settings()
        for m, k in keys.items():
            s.setValue(f"keys/{m}", k)
        s.setValue("detect_any", self.detect.currentIndex())
        s.setValue("output_dir", self.out.text().strip())
        s.setValue("hotkey", "true" if self.hotkey.isChecked() else "false")
        s.setValue("scroll", "true" if self.scroll.isChecked() else "false")
        s.setValue("check_updates", "true" if self.auto_update.isChecked() else "false")
        s.setValue("float_autoplay", "true" if self.autoplay.isChecked() else "false")
        s.setValue("float_on_top", "true" if self.on_top.isChecked() else "false")
        s.setValue("float_ctrl_open", "true" if self.ctrl_open.isChecked() else "false")
        self.app.watcher.refresh_settings()
        engine.OUTPUT_DIR = self.out.text().strip() or None
        s.setValue("language", self.lang.currentData())
        s.setValue("theme", self.theme_box.currentData())
        try:
            winsys.set_startup(self.startup.isChecked())
            winsys.set_context_menu(self.menu.isChecked(), paste_label=tr("Save clipboard image here"), link_label=tr("Play copied link in Float"))
        except Exception as e:
            QMessageBox.warning(self, APP, tr("Couldn't update Windows integration:") + f"\n{e}")
        self.accept()


# ============================================================================
# Drag watcher — polls input state (no hooks, nothing injected)
# ============================================================================
class DragWatcher(QObject):
    tapped = Signal(str)     # mode
    released = Signal()
    hotkey = Signal()
    moved = Signal()         # every tick while a drag is in progress
    scrolled = Signal(int)   # wheel delta while dragging (from the hook thread, delivered queued)
    cancelled = Signal()     # Esc pressed during a drag
    ctrl_open = Signal(int)  # Ctrl + double-click on a file in Explorer (window handle), from the hook thread

    def __init__(self):
        super().__init__()
        self.timer = QTimer(self, interval=20, timeout=self.tick)
        self.down_at = None
        self.dragging = False
        self.prev = {}
        self.hotkey_latch = False
        self.source_hwnd = 0     # top-level window the drag started in
        self.esc_prev = False
        self.refresh_settings()
        self.hook = winsys.WheelHook(self._on_wheel, self._swallow_wheel,
                                     on_ctrl_double=lambda hwnd: self.ctrl_open.emit(int(hwnd)),
                                     ctrl_double_enabled=lambda: getattr(self, "ctrl_float", False))

    def refresh_settings(self):
        s = settings()
        self.scroll_enabled = s.value("scroll", "true") == "true"
        self.any_drag = int(s.value("detect_any", 0)) == 1
        self.ctrl_float = s.value("float_ctrl_open", "true") == "true"

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
        held = {name: winsys.key_down(winsys.VK[name]) for name in set(keys.values())}
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
                any_drag = int(settings().value("detect_any", 0)) == 1
                for m, name in keys.items():
                    if held[name] and not self.prev.get(name):
                        if any_drag or winsys.file_drag_active():
                            self.tapped.emit(m)
        else:
            if self.down_at is not None and self.dragging:
                self.released.emit()
            self.down_at = None
            self.dragging = False
        self.prev = held


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
        engine.OUTPUT_DIR = settings().value("output_dir", "") or None

        self.watcher = DragWatcher()
        self.watcher.tapped.connect(self.on_tap)
        self.watcher.released.connect(self.on_release)
        self.watcher.hotkey.connect(self.on_hotkey)
        self.watcher.moved.connect(self.on_drag_move)
        self.watcher.scrolled.connect(self.on_scroll)
        self.watcher.ctrl_open.connect(self.on_ctrl_open)
        self.watcher.cancelled.connect(self.on_drag_cancel)
        self.watcher.start()

        self.pending: list[str] = []
        self.pending_timer = QTimer(self, singleShot=True, interval=350, timeout=self._flush_pending)

        self.tray = QSystemTrayIcon(app_icon())
        self.tray.activated.connect(lambda r: self.pick_files() if r == QSystemTrayIcon.DoubleClick else None)
        self._build_tray_menu()
        self.tray.show()
        self._update_jobs = set()
        QTimer.singleShot(8000, self._auto_update_check)
        QTimer.singleShot(1200, self.restore_pinned_floats)

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
                    self._resolve_and_play(src, None, pin=pin)
                continue
            if not os.path.exists(src):
                winsys.log(f"pinned float missing: {src}")
                continue
            w = FloatWindow(src, play=pin.get("playing", True), pin=pin)
            self.floats.append(w)
            w.closed.connect(lambda w=w: self.floats.remove(w) if w in self.floats else None)
            w.show()

    def _build_tray_menu(self):
        self.tray.setToolTip(tr("{app} — drag a file, tap {key}", app=APP, key=tr(mode_keys()["convert"])))
        menu = QMenu()
        self._first_action = menu.addAction(tr("Convert files…"), self.pick_files)
        menu.addAction(tr("Save image from clipboard"), self.save_clipboard_image)
        menu.addAction(tr("Play copied link in Float"), self.play_link)
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

    def _refresh_tray_menu(self):
        """Cancel entries go first in the tray menu, only while work is in progress."""
        menu = self._menu
        for act in self._cancel_actions:
            menu.removeAction(act)
            act.deleteLater()
        self._cancel_actions = []
        jobs = self._active_jobs()
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
            act.triggered.connect(lambda: [self._cancel_job(w) for w in self._active_jobs()])
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
            return ops or [engine.Op("none", "No conversions", lambda *a: None, hint="try Tools or Actions")]
        if mode == "tool":
            return engine.tools(paths) or [engine.Op("none", "No tools", lambda *a: None,
                                                     hint="try Convert or Actions")]
        return self.actions.ops(paths)

    # ---- triggers
    def on_tap(self, mode):
        if self.wheel.isVisible():
            if mode != self.wheel.mode:
                self.wheel.set_mode(mode)
            if not self.wheel.paths:
                self._fill_from_explorer()
            return
        self.wheel.popup(mode, click_mode=False)
        self._fill_from_explorer()

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
        if not w.isVisible():
            w.popup("convert", click_mode=False)
            self._fill_from_explorer()
            return
        if not w.click_mode:
            w.scroll_step(1 if delta < 0 else -1)

    def on_drag_cancel(self):
        if self.wheel.isVisible() and not self.wheel.click_mode:
            winsys.log("drag cancelled with Esc")
            self.wheel.dismiss()

    def on_drag_move(self):
        w = self.wheel
        if w.isVisible() and not w.click_mode:
            w._track(QPointF(w.mapFromGlobal(QCursor.pos())))

    def on_release(self):
        w = self.wheel
        if w.isVisible() and not w.click_mode:
            pos = QPointF(w.mapFromGlobal(QCursor.pos()))
            # give a real OLE drop time to arrive; if it doesn't, apply the slice under the cursor
            QTimer.singleShot(350, lambda: self._finish_drag(pos))

    def _finish_drag(self, pos):
        w = self.wheel
        if not w.isVisible() or w.click_mode or w.dropped:
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
        params = {}
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

    def _ensure_model(self, name, what, on_ready):
        """Download a model or tool once (after asking), then call on_ready()."""
        if engine.model_ready(name):
            on_ready()
            return
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
                return
            if err:
                self.toast.show_msg(tr("Couldn't download the AI model") if name != "yt-dlp" else tr("Couldn't do that"),
                                    err, "err", 8000)
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

    def play_link(self, target=None):
        """Play the link on the clipboard (YouTube and other sites, or a direct media link) in a float."""
        url = QGuiApplication.clipboard().text().strip()
        if not engine.is_link(url):
            self.toast.show_msg(tr("No link on the clipboard"), tr("Copy a link to a video or song first."), "info", 4000)
            return
        from urllib.parse import urlparse
        direct = urlparse(url).path.lower().endswith(engine.MEDIA_LINK_EXT)
        if direct or engine.model_ready("yt-dlp"):
            self._resolve_and_play(url, target)
        else:
            self._ensure_model("yt-dlp", tr("Play copied link"), lambda: self._resolve_and_play(url, target))

    def _resolve_and_play(self, url, target, pin=None, quiet=False):
        job = LinkResolve(url)
        job.setAutoDelete(False)
        self._update_jobs.add(job)
        card = None if (pin or quiet) else self.toast.show_busy(tr("Opening link…"), url[:70])

        def done(info, err, job=job):
            self._update_jobs.discard(job)
            if card is not None and card in self.toast.cards:
                card.close_card()
            if err and pin is not None and pin.get("_tries", 0) < 4:     # at sign-in the network may not be up yet
                pin["_tries"] = pin.get("_tries", 0) + 1
                QTimer.singleShot(15000, lambda: self._resolve_and_play(url, None, pin=pin))
                return
            if err:
                winsys.log(f"link failed: {url}: {err}")
                self.toast.show_msg(tr("Couldn't open this link"), tr(err), "err", 8000)
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
                target.media_key(key)
            self._media_down[vk] = down

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
        self.running.add(w)                       # keep Python refs alive until done
        w.sig.done.connect(self._done, Qt.QueuedConnection)
        w.sig.progress.connect(lambda wk, f, name=name: self._job_progress(wk, f, name), Qt.QueuedConnection)
        self.pool.start(w)

    def _job_progress(self, worker, frac, name):
        card = worker.card
        if card is not None and card in self.toast.cards and not worker.cancel_requested:
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
        worker.cancel()
        if worker.card is not None and worker.card in self.toast.cards:
            worker.card.show_busy(tr("Cancelling…"), Path(worker.paths[0]).name)

    def _done(self, worker, outs, err):
        self.running.discard(worker)
        op = worker.op
        card = worker.card if worker.card is not None and worker.card in self.toast.cards else None
        target = card or self.toast
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
            target.show_result(tr("Done") if op.group == "tool" else tr("Converted to {fmt}", fmt=tr(op.label)), outs)

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
        SettingsDialog(self).exec()

    def show_help(self):
        k = {m: tr(v) for m, v in mode_keys().items()}
        message(tr("{app} — How it works", app=APP), tr("HELP_HTML", app=APP, convert=k["convert"],
                                                         tool=k["tool"], action=k["action"])
                + "<br><br>" + tr("HELP_SCROLL"))


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
        if winsys.context_menu_enabled():
            winsys.set_context_menu(True, paste_label=tr("Save clipboard image here"), link_label=tr("Play copied link in Float"))
    except Exception as e:
        winsys.log(f"context menu refresh failed: {e}")

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
            if "--play-link" in msg.get("flags", []):
                app.play_link()
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
                winsys.set_context_menu(True, paste_label=tr("Save clipboard image here"), link_label=tr("Play copied link in Float"))
            except Exception:
                pass
        QTimer.singleShot(500, app.show_help)
    if "--play-link" in flags:
        QTimer.singleShot(400, app.play_link)
    elif "--paste-here" in flags:
        QTimer.singleShot(300, lambda: app.save_clipboard_image(paths[0] if paths else None))
    elif paths:
        app.queue_paths(paths)
    elif "--tray" not in flags and not first_run:
        app.tray.showMessage(APP, tr("Running in the tray. Drag a file and tap {key}.", key=tr(mode_keys()["convert"])),
                             app_icon(), 3000)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
