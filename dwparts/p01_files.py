"""DragWheel: Files: batch rename, checksum, shred, send to phone

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


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


_IPS = (0.0, None)


def _lan_ips() -> list[str]:
    """IPv4 addresses a phone could reach, best first (looked up in the background a moment earlier when possible:
    the lookup can take a second and would freeze a playing float)."""
    t, ips = _IPS
    if ips and time.time() - t < 120:
        return list(ips)
    return _find_lan_ips()


def warm_lan_ips():
    def run():
        global _IPS
        try:
            _IPS = (time.time(), _find_lan_ips())
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def _find_lan_ips() -> list[str]:
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


class FrontDialog(QDialog):
    """A window that comes to the front when it opens (even from the tray or the wheel) but doesn't stay on top
    of everything afterwards, so you can keep working while a long upload runs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)

    back = None                          # set by Send to phone: reopens the chooser to pick another way

    def header(self, lay, title, sub=""):
        """The top of the window: ‹ Back on the left (only when opened from the Send to phone chooser), the title in
        the middle and, under it, what's being sent."""
        from PySide6.QtWidgets import QToolButton
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        b = QToolButton()
        b.setObjectName("back")
        b.setText(tr("Back"))
        b.setIcon(_chevron_icon(QGuiApplication.layoutDirection() == Qt.RightToLeft))
        b.setIconSize(QSize(14, 14))
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tr("Choose another way to send"))
        b.clicked.connect(self._go_back)
        b.setVisible(False)
        pad = QWidget()                                   # same width on the right, so the title stays centred
        pad.setFixedWidth(b.sizeHint().width())
        pad.setVisible(False)
        t = QLabel(title)
        t.setObjectName("title")
        t.setAlignment(Qt.AlignCenter)
        row.addWidget(b, 0, Qt.AlignVCenter)
        row.addWidget(t, 1)
        row.addWidget(pad)
        lay.addLayout(row)
        self._back_b, self._back_pad = b, pad
        if sub:
            sl = QLabel(sub)
            sl.setObjectName("sub")
            sl.setAlignment(Qt.AlignCenter)
            sl.setWordWrap(True)
            sl.setFixedWidth(QR_W)
            lay.addWidget(sl, 0, Qt.AlignHCenter)
        lay.addSpacing(4)
        return t

    def buttons(self, lay, *btns):
        """A row of buttons at the bottom."""
        row = QHBoxLayout()
        row.setSpacing(8)
        for b in btns:
            b.setMinimumHeight(34)
            row.addWidget(b, 1)
        lay.addSpacing(4)
        lay.addLayout(row)

    _leaving = False
    keep_hides = False                   # "Keep sharing" hides the window (the share lives in it)

    def sharing(self) -> bool:
        """Something this window shares that could be stopped."""
        return False

    def stop_sharing(self):
        pass

    def stop_question(self) -> str:
        return ""

    def _ask_stop(self):
        """"stop", "keep" or None (stay here)."""
        box = QMessageBox(self)
        box.setWindowTitle(f"{APP} — " + tr("Send to phone"))
        box.setStyleSheet(i18n.css(DIALOG_CSS))
        box.setText("<b>" + tr("Stop sharing?") + "</b>")
        box.setInformativeText(self.stop_question())
        stop = box.addButton(tr("Stop sharing"), QMessageBox.DestructiveRole)
        keep = box.addButton(tr("Keep sharing"), QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel).setText(tr("Cancel"))
        box.setDefaultButton(keep)
        box.exec()
        return "stop" if box.clickedButton() is stop else "keep" if box.clickedButton() is keep else None

    def leave_ok(self, e=None) -> bool:
        """Closing with X: ask whether to stop sharing. False = the window stays (or only hides)."""
        if self._leaving or not self.sharing():
            return True
        r = self._ask_stop()
        if r is None:
            if e is not None:
                e.ignore()
            return False
        if r == "keep" and self.keep_hides:
            if e is not None:
                e.ignore()
            self.hide()
            return False
        if r == "stop":
            self.stop_sharing()
        self._leaving = True
        return True

    def _go_back(self):
        go = self.back
        if not self._leaving and self.sharing():
            r = self._ask_stop()
            if r is None:
                return
            if r == "keep" and self.keep_hides:            # still sharing: the tray (or choosing it again) brings it back
                self.hide()
            else:
                if r == "stop":
                    self.stop_sharing()
                self._leaving = True
                self.close()
        else:
            self._leaving = True
            self.close()
        if go:
            QTimer.singleShot(0, go)

    def showEvent(self, e):
        if getattr(self, "_back_b", None) is not None:
            self._back_b.setVisible(self.back is not None)
            self._back_pad.setVisible(self.back is not None)
        super().showEvent(e)
        if not getattr(self, "_fronted", False):
            self._fronted = True
            QTimer.singleShot(0, lambda: (self.raise_(), self.activateWindow(), winsys.bring_to_front(int(self.winId()))))


class PhoneShare(FrontDialog):
    """Share files with a phone on the same Wi-Fi: a QR code opens a page served straight from this PC."""

    def __init__(self, paths, mode="wifi"):
        super().__init__(None)
        import http.server
        import secrets
        import urllib.parse
        self.mode = mode                 # "wifi": phones on this network · "tunnel": anywhere, through Cloudflare
        self.tunnel = None
        self.keep_hides = True
        self.key = share_key(paths)
        self.ended = False
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

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1" if mode == "tunnel" else "0.0.0.0", 0), H)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self._port, self._token = self.server.server_address[1], token
        self.ips = _lan_ips() if mode == "wifi" else []
        lay = QVBoxLayout(self)
        from PySide6.QtWidgets import QLayout
        lay.setSizeConstraint(QLayout.SetFixedSize)          # the window always fits the code and the text
        what = self.paths[0].name if len(self.paths) == 1 else tr("{n} files", n=len(self.paths))
        self.header(lay, tr("Link from this PC") if mode == "tunnel" else tr("Same Wi-Fi"), what)
        self.qr = QrBox()
        lay.addWidget(self.qr, 0, Qt.AlignHCenter)
        self.link = QLabel()
        self.link.setObjectName("sub")
        self.link.setAlignment(Qt.AlignCenter)
        self.link.setWordWrap(True)
        self.link.setFixedWidth(QR_W)
        self.link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.link, 0, Qt.AlignHCenter)
        if len(self.ips) > 1:                              # several network adapters: let the user switch
            self.ip_box = QComboBox()
            for ip in self.ips:
                self.ip_box.addItem(tr("Network address: {ip}", ip=ip), ip)
            self.ip_box.currentIndexChanged.connect(lambda _i: self._show_qr(self.ip_box.currentData()))
            lay.addWidget(self.ip_box)
        if mode == "tunnel":
            self.url = ""
            self.qr.busy(tr("Making the link…"))
            info = QLabel(tr("Sharing {what}. The link works on any network, even mobile data. The file goes straight "
                             "from this PC through Cloudflare and isn't stored anywhere; the link ends when you close "
                             "this window, so keep it open until it's downloaded.", what=what))
        else:
            self._show_qr(self.ips[0])
            info = QLabel(tr("Sharing {what}. Your phone must be on the same Wi-Fi. If Windows asks, allow DragWheel on "
                             "private networks. Nothing goes through the internet; sharing stops when you close this window.",
                             what=what))
        info.setObjectName("note")
        info.setWordWrap(True)
        info.setFixedWidth(QR_W)
        lay.addWidget(info)
        self.count = QLabel()
        lay.addWidget(self.count)
        stop = QPushButton(tr("Stop sharing"))
        stop.clicked.connect(self._stop_now)                 # the button says it: stop, no question
        if mode == "tunnel":
            self.copy_b = QPushButton(tr("Copy link"))
            self.copy_b.setObjectName("primary")
            self.copy_b.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.url))
            self.copy_b.setEnabled(False)
            self.buttons(lay, self.copy_b, stop)
        else:
            help_b = QPushButton(tr("Phone can't open it?"))
            help_b.clicked.connect(self._help)
            self.buttons(lay, help_b, stop)
        self.diag = QLabel()
        self.diag.setWordWrap(True)
        self.diag.setFixedWidth(QR_W)
        self.diag.setStyleSheet(f"color:{theme.hexc('danger')}")
        self.diag.hide()
        lay.insertWidget(lay.indexOf(self.count), self.diag)
        self._seen = None
        self._diag_lines = None
        self._poll = QTimer(self, interval=500, timeout=self._update)
        self._poll.start()
        self._last = ""
        self._tunnel_url = None
        self._tunnel_err = None
        if mode == "tunnel":
            threading.Thread(target=self._start_tunnel, daemon=True).start()
        else:
            threading.Thread(target=self._diagnose, daemon=True).start()

    def _start_tunnel(self):
        """Cloudflare's quick tunnel: a random https://….trycloudflare.com address that reaches this window's
        little web server. No account; it lasts while cloudflared runs."""
        import re
        import subprocess
        try:
            self.tunnel = subprocess.Popen(
                [str(engine.model_path("cloudflared")), "tunnel", "--no-autoupdate", "--url",
                 f"http://127.0.0.1:{self._port}"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, creationflags=engine.NO_WINDOW)
        except Exception as e:
            self._tunnel_err = str(e)
            return
        t0 = time.monotonic()
        for raw in iter(self.tunnel.stdout.readline, b""):
            line = raw.decode("utf-8", "replace")
            m = re.search(r"https://[-a-z0-9]+\.trycloudflare\.com", line)
            if m and self._tunnel_url is None:
                self._tunnel_url = m.group(0)
                winsys.log(f"send to phone: tunnel {self._tunnel_url} after {time.monotonic() - t0:.1f} s")
            elif ("ERR" in line or "error" in line.lower()) and self._tunnel_url is None:
                winsys.log("cloudflared: " + line.strip()[:200])
        if self._tunnel_url is None:
            self._tunnel_err = tr("Couldn't make the link. Check the internet connection, or that a firewall or "
                                  "antivirus lets cloudflared.exe connect.")

    def _show_qr(self, ip):
        self._show_url(f"http://{ip}:{self._port}/{self._token}/")

    def _show_url(self, url):
        self.url = url
        winsys.log(f"send to phone: {self.url} (addresses: {', '.join(self.ips) or 'tunnel'})")
        self.link.setText(self.url)
        self.qr.show_code(self.url)

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
        if self.mode == "tunnel" and not self.url:
            if self._tunnel_url:
                self._show_url(f"{self._tunnel_url}/{self._token}/")
                self.copy_b.setEnabled(True)
            elif self._tunnel_err:
                self.qr.idle(tr("No link"))
                self.link.setText(f"<span style='color:{theme.hexc('danger')}'>{self._tunnel_err}</span>")
                self._tunnel_err = ""
        if self._diag_lines is not None:
            notes = self._diag_text(self._diag_lines)
            self._diag_lines = None
            self._notes = notes
            if notes:
                self.diag.setText("⚠ " + "\n\n⚠ ".join(notes))
                self.diag.show()
        if self.hits:
            self.count.setText(tr("Downloaded {n} time(s) — last: {name}", n=self.hits, name=self._last))

    def sharing(self):
        return not self.ended

    def _stop_now(self):
        self._leaving = True
        self.close()

    def stop_question(self):
        what = self.paths[0].name if len(self.paths) == 1 else tr("{n} files", n=len(self.paths))
        return tr("Stop sharing ends the link for {what}. Keep sharing hides this window and the link keeps "
                  "working; open it again from the tray (Send to phone).", what=what)

    def closeEvent(self, e):
        if not self.leave_ok(e):
            return
        self.ended = True
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
        if self.tunnel is not None:                    # the link ends with the window
            try:
                self.tunnel.kill()
            except Exception:
                pass
        super().closeEvent(e)


# TODO RECOVER ['_stop_server'] (line 758)


QUICK_SHARE_URL = "https://www.android.com/better-together/quick-share-app/"


class _Upload:
    """A file read in pieces for an HTTP upload (multipart), reporting progress and stoppable."""

    def __init__(self, path, field, fields, progress, cancelled):
        import uuid
        self.boundary = "----DragWheel" + uuid.uuid4().hex
        pre = "".join(f'--{self.boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'
                      for k, v in fields.items())
        from urllib.parse import quote
        import mimetypes
        ctype = mimetypes.guess_type(Path(path).name)[0] or "application/octet-stream"   # e.g. application/zip
        pre += (f'--{self.boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{quote(Path(path).name)}"\r\n'
                f"Content-Type: {ctype}\r\n\r\n")
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
    url = data["data"]["url"].replace("http://", "https://", 1)
    return url.replace("tmpfiles.org/", "tmpfiles.org/dl/", 1)        # the file itself, not the page with ads


def _host_uguu(path, minutes, progress, cancelled):
    import json as _json
    data = _json.loads(_post_upload("https://uguu.se/upload", path, "files[]", {}, progress, cancelled))
    return data["files"][0]["url"]


# name, function, size limit in MB, longest it keeps a file (minutes)
TEMP_HOSTS = [("litterbox.catbox.moe", _host_litterbox, 1000, 72 * 60),
              ("0x0.st", _host_0x0, 512, 365 * 24 * 60),
              ("uguu.se", _host_uguu, 128, 3 * 60),
              ("tmpfiles.org", _host_tmpfiles, 100, 48 * 60)]


AUTO_HOSTS = ["litterbox.catbox.moe", "0x0.st", "uguu.se"]     # tried in turn; tmpfiles.org only when you pick it


# what the Service list shows, and the link times each one offers (minutes)
HOST_CHOICES = [("auto", "Automatic (tries each in turn)", [60, 12 * 60, 24 * 60, 72 * 60]),
                ("litterbox.catbox.moe", "Litterbox — up to 1 GB", [60, 12 * 60, 24 * 60, 72 * 60]),
                ("0x0.st", "0x0.st — up to 512 MB", [60, 12 * 60, 24 * 60, 72 * 60]),
                ("uguu.se", "uguu.se — up to 128 MB", [3 * 60]),
                ("tmpfiles.org", "tmpfiles.org — up to 100 MB (ads)", [5, 15, 30, 60, 12 * 60, 24 * 60, 48 * 60])]


def _short_reason(err: str) -> str:
    """One host's failure in a few words, for the message you see."""
    e = err.lower()
    if "refuses this connection" in e or "403" in e:
        return tr("refuses connections from your network")
    if "eof occurred" in e or "reset" in e or "timed out" in e:
        return tr("the upload was cut off partway")
    if "415" in e or "unsupported media" in e:
        return tr("refused this kind of file")
    if "413" in e or "too large" in e:
        return tr("the file is too big for it")
    if "can't be reached" in e or "getaddrinfo" in e or "urlopen error" in e:
        return tr("couldn't be reached")
    return tr("didn't work")


BLOCKED_UPLOAD_EXT = {".exe", ".msi", ".msix", ".appx", ".bat", ".cmd", ".com", ".scr", ".dll", ".sys", ".cpl", ".jar",
                      ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".hta", ".lnk", ".reg", ".apk", ".xapk", ".ipa"}


def _host_refuses(name) -> str:
    """A quick look at the service's home page (a few KB) before sending a big file: '' if it answers normally."""
    import urllib.error
    import urllib.request
    try:
        req = urllib.request.Request(f"https://{name}/", headers={"User-Agent": f"DragWheel/{VERSION} (Windows)"})
        with urllib.request.urlopen(req, timeout=8) as r:
            r.read(2048)
        return ""
    except urllib.error.HTTPError as e:
        return f"refuses this connection (HTTP {e.code})" if e.code in (401, 403, 451) else ""
    except Exception as e:
        return f"can't be reached ({type(e).__name__}: {e})"


def upload_temporary(path, minutes, progress=lambda f: None, cancelled=lambda: False, only=None) -> tuple[str, str]:
    """Upload to a free temporary host; returns (download link, host). Several hosts are tried in turn, because a
    network, country or security app may block one of them. Short times (under an hour) prefer hosts that delete soon."""
    size = Path(path).stat().st_size
    mb = size / (1024 * 1024)
    order = [only] if only and only != "auto" else list(AUTO_HOSTS)
    hosts = {h[0]: h for h in TEMP_HOSTS}
    errors = []
    for name in order:
        _n, fn, limit, _keep = hosts[name]
        if mb > limit or (_keep < minutes and name != order[-1]):
            errors.append(f"{name}: too large ({mb:.0f} MB, limit {limit} MB)" if mb > limit else
                          f"{name}: keeps files only {_keep // 60} h")
            continue                                   # too big, or it would delete the file too early
        why = _host_refuses(name)
        if why:                                        # e.g. this network or country is blocked there:
            errors.append(f"{name}: {why}")            # skip it instead of uploading half the file first
            continue
        for attempt in (1, 2):
            if cancelled():
                raise OSError("cancelled")
            seen = [0.0]
            t0 = time.monotonic()

            def prog(f, seen=seen):
                seen[0] = f
                progress(f)
            try:
                progress(0.0)
                link = fn(path, minutes, prog, cancelled)
                winsys.log(f"temporary upload: {name} ok ({mb:.1f} MB, {minutes} min)" +
                           (f" after: {' | '.join(errors)}" if errors else ""))
                return link, name
            except Exception as e:
                if cancelled():
                    raise
                errors.append(f"{name}#{attempt}: {type(e).__name__}: {e} (at {int(seen[0] * 100)}% after "
                              f"{time.monotonic() - t0:.0f} s)")
                if "EOF occurred" not in str(e) and "timed out" not in str(e) and "reset" not in str(e).lower():
                    break                                  # only retry dropped connections
    winsys.log(f"temporary upload failed ({mb:.1f} MB, {minutes} min): " + " | ".join(errors))
    if mb > 1000:
        raise OSError(tr("Too big for an internet link (the limit is 1 GB)."))
    # say what each service did (the last try counts), so it's clear which one to pick next time
    last = {}
    for e in errors:
        last[e.split(":", 1)[0].split("#")[0]] = e
    lines = [f"{n}: {_short_reason(e)}" for n, e in last.items() if "keeps files only" not in e]
    if lines:
        raise OSError(tr("Couldn't upload.") + "\n" + "\n".join("• " + x for x in lines) + "\n" +
                      tr("Pick another service in the list, or use Quick Share."))
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


def share_key(paths) -> str:
    """Which files were shared, and as they were then (a changed file is shared again, not the old copy)."""
    out = []
    for x in sorted(os.path.normcase(os.path.abspath(str(x))) for x in paths):
        try:
            st = os.stat(x)
            out.append(f"{x}|{st.st_size}|{int(st.st_mtime)}")
        except OSError:
            out.append(x)
    return "\n".join(out)


def remember_share_link(url, name, minutes, key=""):
    import time
    links = [x for x in share_links() if x["url"] != url]
    links.insert(0, {"url": url, "name": name, "expires": time.time() + minutes * 60, "key": key})
    settings().setValue("share_links", json.dumps(links[:20], ensure_ascii=False))


def qr_pixmap(text, scale=7) -> QPixmap:
    import io as _io
    import segno
    buf = _io.BytesIO()
    segno.make(text, error="m").save(buf, kind="png", scale=scale, border=3, dark="#000", light="#fff")
    return QPixmap.fromImage(QImage.fromData(buf.getvalue()))


QR_W = 372                    # content width of the Send to phone windows


def _chevron_icon(rtl=False) -> "QIcon":
    from PySide6.QtGui import QIcon
    icons = QIcon()
    for mode, col in ((QIcon.Normal, theme.hexc("dim")), (QIcon.Active, theme.hexc("text"))):
        pm = QPixmap(28, 28)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(col), 3.2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        pts = [QPointF(17, 6), QPointF(9, 14), QPointF(17, 22)]
        if rtl:
            pts = [QPointF(28 - q.x(), q.y()) for q in pts]
        p.drawPolyline(pts)
        p.end()
        icons.addPixmap(pm, mode)
    return icons


def qr_image(text) -> QImage:
    """The QR code as a tiny 1-pixel-per-module picture (drawn bigger without smoothing, so it stays sharp)."""
    import segno
    rows = list(segno.make(text, error="m").matrix_iter(scale=1, border=2))
    n = len(rows)
    img = QImage(n, n, QImage.Format_RGB32)
    img.fill(QColor("#ffffff"))
    black = QColor("#000000").rgb()
    for y, row in enumerate(rows):
        for x, v in enumerate(row):
            if v:
                img.setPixel(x, y, black)
    return img


class QrBox(QWidget):
    """The place for a QR code: a spinning wheel inside it while the link is being made, then the code.
    Clicking the code copies the link."""

    def __init__(self, side=236, parent=None):
        super().__init__(parent)
        self.setFixedSize(side, side)
        self.url, self._img, self._busy, self._text, self._angle = "", None, False, "", 0
        self._spin = QTimer(self, interval=16, timeout=self._tick)

    def busy(self, text=""):
        self._img, self._busy, self._text = None, True, text
        self._spin.start()
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def idle(self, text=""):
        self._img, self._busy, self._text = None, False, text
        self._spin.stop()
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def set_text(self, text):
        self._text = text
        self.update()

    def show_code(self, url):
        self.url = url
        self._busy = False
        self._spin.stop()
        try:
            self._img = qr_image(url)
        except Exception as e:
            winsys.log(f"qr: {e}")
            self._img = None
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tr("Click to copy the link"))
        self.update()

    def mousePressEvent(self, e):
        if self._img is not None and e.button() == Qt.LeftButton:
            QGuiApplication.clipboard().setText(self.url)
            from PySide6.QtWidgets import QToolTip
            QToolTip.showText(e.globalPosition().toPoint(), tr("Link copied"), self)

    def _tick(self):
        self._angle = (self._angle + 7) % 360
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._img is not None:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#ffffff"))
            p.drawRoundedRect(r, 16, 16)
            n = self._img.width()
            k = max(1, int((self.width() - 12) // n))
            size = n * k
            off = (self.width() - size) / 2
            p.setRenderHint(QPainter.SmoothPixmapTransform, False)
            p.drawImage(QRectF(off, off, size, size), self._img)
            return
        p.setPen(QPen(QColor(theme.hexc("border")), 1.5))
        p.setBrush(QColor(theme.hexc("surface")))
        p.drawRoundedRect(r, 16, 16)
        c = QPointF(self.width() / 2, self.height() / 2 - (12 if self._text else 0))
        if self._busy:
            ring = QRectF(c.x() - 26, c.y() - 26, 52, 52)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(theme.hexc("border")), 5))
            p.drawEllipse(ring)
            p.setPen(QPen(QColor(theme.hexc("accent")), 5, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(ring, int(-self._angle * 16), 100 * 16)
        else:                                             # a faint QR mark: where the code will appear
            dim = QColor(theme.hexc("dim"))
            dim.setAlpha(110)
            p.setPen(QPen(dim, 3))
            p.setBrush(Qt.NoBrush)
            for dx, dy in ((-26, -26), (6, -26), (-26, 6)):
                p.drawRoundedRect(QRectF(c.x() + dx, c.y() + dy, 20, 20), 4, 4)
            p.setPen(Qt.NoPen)
            p.setBrush(dim)
            for dx, dy in ((10, 10), (20, 10), (10, 20), (20, 20)):
                p.drawRect(QRectF(c.x() + dx - 2, c.y() + dy - 2, 6, 6))
        if self._text:
            p.setPen(QColor(theme.hexc("dim")))
            f = p.font()
            f.setPointSizeF(9)
            p.setFont(f)
            p.drawText(QRectF(14, c.y() + 38, self.width() - 28, 44), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                       self._text)


def find_codes(img: QImage) -> list:
    """QR codes (and other barcodes) in a picture: [{"text", "kind", "rect"}] with rect in the picture's pixels."""
    import numpy as np
    import zxingcpp
    g = img.convertToFormat(QImage.Format_Grayscale8)
    w, h, bpl = g.width(), g.height(), g.bytesPerLine()
    arr = np.frombuffer(g.constBits(), np.uint8, count=bpl * h).reshape(h, bpl)[:, :w].copy()
    out = []
    for r in zxingcpp.read_barcodes(arr):
        if not r.text:
            continue
        pos = r.position
        pts = [pos.top_left, pos.top_right, pos.bottom_right, pos.bottom_left]
        xs, ys = [q.x for q in pts], [q.y for q in pts]
        out.append({"text": r.text, "kind": str(r.format),
                    "rect": QRectF(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))})
    return out


def find_codes_in_file(path) -> list:
    img = QImage(str(path))
    if img.isNull():
        try:
            import io as _io
            pil = engine.open_image(path)
            buf = _io.BytesIO()
            pil.convert("RGB").save(buf, "PNG")
            img = QImage.fromData(buf.getvalue())
        except Exception:
            return []
    codes = find_codes(img)
    if not codes and max(img.width(), img.height()) < 1600:          # small codes: try again bigger
        codes = find_codes(img.scaled(img.width() * 2, img.height() * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    return codes


def _qr_meaning(text):
    """(kind label, main text, fields [(label, value)], url to open or None)."""
    t = text.strip()
    low = t.lower()
    if low.startswith(("http://", "https://")):
        from urllib.parse import urlparse
        return tr("Link"), t, [(tr("Website"), urlparse(t).netloc)], t
    if low.startswith("wifi:"):
        fields, parts, cur, esc = {}, [], "", False
        for ch in t[5:]:                                  # fields end at ";"; "\\;" is a ; inside a value
            if esc:
                cur, esc = cur + ch, False
            elif ch == "\\":
                esc = True
            elif ch == ";":
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        parts.append(cur)
        for part in parts:
            if ":" in part:
                k, v = part.split(":", 1)
                fields[k.upper()] = v
        rows = [(tr("Network"), fields.get("S", "")), (tr("Password"), fields.get("P", ""))]
        return tr("Wi-Fi network"), fields.get("S", ""), [x for x in rows if x[1]], None
    if low.startswith("mailto:"):
        return tr("Email"), t[7:], [], t
    if low.startswith("tel:"):
        return tr("Phone number"), t[4:], [], t
    return tr("Text"), t, [], None


class QrResult(FrontDialog):
    """What a QR code says, with Open / Copy."""

    def __init__(self, codes):
        super().__init__(None)
        from PySide6.QtWidgets import QLayout
        self.setWindowTitle(f"{APP} — " + tr("QR code"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.setAttribute(Qt.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        self.header(lay, tr("QR code") if len(codes) == 1 else tr("{n} codes", n=len(codes)))
        for c in codes[:6]:
            kind, main, fields, url = _qr_meaning(c["text"])
            card = QFrame()
            card.setObjectName("card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(14, 12, 14, 12)
            k = QLabel(kind.upper())
            k.setObjectName("sub")
            cl.addWidget(k)
            m = QLabel(main)
            m.setWordWrap(True)
            m.setFixedWidth(QR_W - 28)
            m.setTextInteractionFlags(Qt.TextSelectableByMouse)
            m.setTextFormat(Qt.PlainText)
            cl.addWidget(m)
            for label, value in fields:
                f = QLabel(f"<span style='color:{theme.hexc('dim')}'>{label}:</span> {html_escape(value)}")
                f.setTextInteractionFlags(Qt.TextSelectableByMouse)
                cl.addWidget(f)
            btns = []
            if url:
                o = QPushButton(tr("Open"))
                o.setObjectName("primary")
                o.clicked.connect(lambda _=False, u=url: (QDesktopServices.openUrl(QUrl(u)), self.close()))
                btns.append(o)
            pw = dict(fields).get(tr("Password"))
            if pw:
                b = QPushButton(tr("Copy password"))
                b.setObjectName("primary")
                b.clicked.connect(lambda _=False, v=pw: QGuiApplication.clipboard().setText(v))
                btns.append(b)
            b = QPushButton(tr("Copy"))
            b.clicked.connect(lambda _=False, v=c["text"], b=b: (QGuiApplication.clipboard().setText(v), b.setText(tr("Copied"))))
            btns.append(b)
            self.buttons(cl, *btns)
            lay.addWidget(card)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        self.buttons(lay, close)


def html_escape(t):
    import html as _h
    return _h.escape(str(t))


class QrScanOverlay(QWidget):
    """Read QR code on screen: a still picture of one screen with the codes on it lit up. Click one to read it,
    or drag a box around one. Esc cancels."""

    def __init__(self, screen, shot, codes, done):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.shot, self.done = shot, done
        dpr = shot.devicePixelRatio() or 1.0
        self.dpr = dpr
        self.codes = [dict(c, view=QRectF(c["rect"].x() / dpr, c["rect"].y() / dpr, c["rect"].width() / dpr,
                                          c["rect"].height() / dpr).adjusted(-8, -8, 8, 8)) for c in codes]
        self.hover, self.drag_from, self.drag_to, self.msg = None, None, None, ""
        self.setMouseTracking(True)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(screen.geometry())

    def _hint(self, any_codes):
        if self.msg:
            return self.msg
        return (tr("Click a QR code to read it — or drag a box around one. Esc to cancel.") if any_codes
                else tr("No QR code found here. Drag a box around one, or press Esc."))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.drawPixmap(self.rect(), self.shot)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        accent = QColor(theme.hexc("accent"))
        for i, c in enumerate(self.codes):
            v = c["view"]
            src = QRectF(v.x() * self.dpr, v.y() * self.dpr, v.width() * self.dpr, v.height() * self.dpr)
            p.drawPixmap(v, self.shot, src)                       # the code itself stays bright
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(accent, 5 if i == self.hover else 3))
            p.drawRoundedRect(v, 10, 10)
        if self.drag_from is not None and self.drag_to is not None:
            box = QRectF(self.drag_from, self.drag_to).normalized()
            src = QRectF(box.x() * self.dpr, box.y() * self.dpr, box.width() * self.dpr, box.height() * self.dpr)
            p.drawPixmap(box, self.shot, src)
            p.setPen(QPen(accent, 2, Qt.DashLine))
            p.drawRect(box)
        text = self._hint(any(True for _ in self.codes))
        f = p.font()
        f.setPointSizeF(10.5)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        w = fm.horizontalAdvance(text) + 40
        pill = QRectF((self.width() - w) / 2, 28, w, 40)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(28, 28, 30, 235))
        p.drawRoundedRect(pill, 20, 20)
        p.setPen(QColor("#ffffff"))
        p.drawText(pill, Qt.AlignCenter, text)

    def _at(self, pos):
        return next((i for i, c in enumerate(self.codes) if c["view"].contains(QPointF(pos))), None)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self.drag_from is not None and (pos - self.drag_from).manhattanLength() > 6:
            self.drag_to = pos
        h = self._at(pos)
        if h != self.hover:
            self.hover = h
            self.setCursor(Qt.PointingHandCursor if h is not None else Qt.CrossCursor)
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self.done(None)
            return
        self.drag_from, self.drag_to, self.msg = e.position(), None, ""

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton or self.drag_from is None:
            return
        if self.drag_to is None:                                  # a click
            i = self._at(e.position())
            self.drag_from = None
            if i is not None:
                self.done([self.codes[i]])
            return
        box = QRectF(self.drag_from, self.drag_to).normalized()
        self.drag_from = self.drag_to = None
        crop = self.shot.copy(QRectF(box.x() * self.dpr, box.y() * self.dpr, box.width() * self.dpr,
                                     box.height() * self.dpr).toRect()).toImage()
        codes = []
        for k in (1, 2, 3):                                      # small codes read better a bit bigger
            img = crop if k == 1 else crop.scaled(crop.width() * k, crop.height() * k, Qt.KeepAspectRatio,
                                                   Qt.SmoothTransformation)
            try:
                codes = find_codes(img)
            except Exception as ex:
                winsys.log(f"read qr: {ex}")
            if codes:
                break
        if codes:
            self.done(codes)
        else:
            self.msg = tr("No QR code in that box. Try again, or press Esc.")
            self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.done(None)


def _time_left(expires) -> str:
    import time
    m = max(1, int((expires - time.time()) // 60))
    return tr("{n} min left", n=m) if m < 60 else tr("{h} h {m} min left", h=m // 60, m=m % 60)


class ShareQR(FrontDialog):
    """Tray → Send to phone — show QR code: an internet link made earlier, until it runs out."""

    def __init__(self, item, title=None, new=None):
        super().__init__(None)
        from PySide6.QtWidgets import QLayout
        self.item = item
        self.setWindowTitle(f"{APP} — " + tr("Send to phone"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.setAttribute(Qt.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        self.header(lay, title or tr("Internet link"), item["name"])
        qr = QrBox()
        qr.show_code(item["url"])
        lay.addWidget(qr, 0, Qt.AlignHCenter)
        self.left = QLabel()
        self.left.setObjectName("sub")
        self.left.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.left)
        link = QLabel(item["url"])
        link.setObjectName("sub")
        link.setWordWrap(True)
        link.setFixedWidth(QR_W)
        link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        link.setAlignment(Qt.AlignCenter)
        lay.addWidget(link, 0, Qt.AlignHCenter)
        b = QPushButton(tr("Copy link"))
        b.setObjectName("primary")
        b.clicked.connect(lambda: QGuiApplication.clipboard().setText(item["url"]))
        c = QPushButton(tr("Close"))
        c.clicked.connect(self.close)
        if new is not None:                                # already shared: or make a fresh link instead
            n = QPushButton(tr("New link"))
            n.setToolTip(tr("Share it again with a new link"))
            n.clicked.connect(lambda: (self.close(), QTimer.singleShot(0, new)))
            self.buttons(lay, b, n, c)
        else:
            self.buttons(lay, b, c)
        self._t = QTimer(self, interval=20000, timeout=self._tick)
        self._t.start()
        self._tick()

    def sharing(self):
        return bool(self.item.get("path")) and Path(self.item["path"]).exists()

    def stop_question(self):
        return tr("Stop sharing deletes the copy from your cloud, so the link stops working. Keep sharing leaves "
                  "it until its time runs out.")

    def stop_sharing(self):
        stop_cloud_share(self.item["path"])

    def closeEvent(self, e):
        if not self.leave_ok(e):
            return
        super().closeEvent(e)

    def _tick(self):
        import time
        if not self.item.get("expires"):
            self.left.setText(tr("Kept until you delete it"))
            return
        if self.item["expires"] <= time.time():
            self.close()                                   # the link has run out
            return
        self.left.setText(_time_left(self.item["expires"]))


class InternetShare(FrontDialog):
    """Send to phone through a temporary internet link: upload, then a QR code to open it on any phone."""
    MINUTES = [60, 12 * 60, 24 * 60, 72 * 60]     # what the file services offer (none deletes sooner than an hour)

    def __init__(self, paths):
        super().__init__(None)
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
            what = self.paths[0].stem + ".zip — " + tr("programs are sent inside a ZIP, because file services refuse them")
        self.header(lay, tr("Internet link"), what)
        self.qr = QrBox()
        self.qr.idle(tr("The QR code appears here"))
        lay.addWidget(self.qr, 0, Qt.AlignHCenter)
        self.link = QLabel()
        self.link.setObjectName("sub")
        self.link.setWordWrap(True)
        self.link.setFixedWidth(QR_W)
        self.link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.link.setAlignment(Qt.AlignCenter)
        self.link.hide()
        lay.addWidget(self.link, 0, Qt.AlignHCenter)
        form = QFormLayout()
        self.host = QComboBox()
        for key, label, _m in HOST_CHOICES:
            self.host.addItem(tr(label), key)
        self.host.setCurrentIndex(max(0, self.host.findData(settings().value("share_host", "auto"))))
        form.addRow(tr("Service"), self.host)
        self.hours = QComboBox()
        form.addRow(tr("Keep the link for"), self.hours)
        lay.addLayout(form)
        self.ads = QLabel(tr("tmpfiles.org's download page shows ads and pop-ups, with fake Download buttons that open "
                             "other sites. DragWheel gives the direct file link, but tell whoever opens it not to tap "
                             "anything else on that page."))
        self.ads.setWordWrap(True)
        self.ads.setFixedWidth(QR_W)
        self.ads.setStyleSheet(f"color:{theme.hexc('danger')};font-size:9pt")
        lay.addWidget(self.ads)
        self.host.currentIndexChanged.connect(self._host_changed)
        self._host_changed()
        note = QLabel(tr("The file is uploaded to a free temporary file service and deleted automatically after about "
                         "that time. Anyone with the link can download it until then."))
        note.setObjectName("note")
        note.setWordWrap(True)
        note.setFixedWidth(QR_W)
        lay.addWidget(note)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setFixedWidth(QR_W)
        self.status.hide()
        lay.addWidget(self.status)
        self.go = QPushButton(tr("Upload and make a link"))
        self.go.setObjectName("primary")
        self.go.clicked.connect(self._start)
        self.copy = QPushButton(tr("Copy link"))
        self.copy.setObjectName("primary")
        self.copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.url))
        self.copy.hide()
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        self.buttons(lay, self.go, self.copy, close)
        self._cancel = False
        self._frac = 0.0
        self._result = None
        self._poll = QTimer(self, interval=150, timeout=self._update)

    def _host_changed(self, *_):
        key = self.host.currentData()
        times = next(m for k, _l, m in HOST_CHOICES if k == key)
        want = int(self.hours.currentData() or settings().value("share_minutes", 60))
        self.hours.clear()
        for m in times:
            self.hours.addItem(tr("{n} minutes", n=m) if m < 60 else tr("{n} hour(s)", n=m // 60), m)
        self.hours.setCurrentIndex(max(0, self.hours.findData(min(times, key=lambda m: abs(m - want)))))
        self.ads.setVisible(key == "tmpfiles.org")

    def _start(self):
        settings().setValue("share_minutes", self.hours.currentData())
        settings().setValue("share_host", self.host.currentData())
        self.shared_name = self.paths[0].name if len(self.paths) == 1 else tr("{n} files", n=len(self.paths))
        self.go.setEnabled(False)
        self.hours.setEnabled(False)
        self.host.setEnabled(False)
        self.status.hide()
        self.qr.busy(tr("Uploading…"))
        hours = self.hours.currentData()
        only = self.host.currentData()

        def work():
            try:
                src = self.paths[0]
                # free file services refuse programs and scripts (.exe, .msi…): those travel inside a ZIP
                blocked = src.is_file() and src.suffix.lower() in BLOCKED_UPLOAD_EXT
                if len(self.paths) > 1 or src.is_dir() or blocked:
                    import tempfile
                    import zipfile
                    tmp = Path(tempfile.mkdtemp(prefix="dragwheel-share-"))
                    src = tmp / ((self.paths[0].stem if blocked else self.paths[0].name if len(self.paths) == 1
                                  else "DragWheel") + ".zip")         # "Setup.zip", not "Setup.exe.zip": some services refuse that
                    with zipfile.ZipFile(src, "w", zipfile.ZIP_DEFLATED) as z:
                        for it in self.paths:
                            for f in ([it] if it.is_file() else [x for x in it.rglob("*") if x.is_file()]):
                                z.write(f, str(f.relative_to(it.parent)))
                link, host = upload_temporary(src, hours, lambda f: setattr(self, "_frac", f), lambda: self._cancel,
                                              only=only)
                self._result = ("ok", link, host)
            except Exception as e:
                self._result = ("err", str(e), "")
        threading.Thread(target=work, daemon=True).start()
        self._poll.start()

    def _update(self):
        if self._result is None:
            if self._frac > 0:
                self.qr.set_text(tr("Uploading…") + f"  {int(self._frac * 100)}%")
            return
        self._poll.stop()
        kind, val, host = self._result
        if kind == "err":
            self.qr.idle(tr("No link"))
            self.status.show()
            self.status.setText(f"<span style='color:{theme.hexc('danger')}'>" + val.replace("\n", "<br>") + "</span>")
            self.go.setEnabled(True)
            self.hours.setEnabled(True)
            self.host.setEnabled(True)
            return
        self.url = val
        winsys.log(f"send to phone (internet): uploaded to {host}")
        remember_share_link(val, self.shared_name, int(self.hours.currentData()), share_key(self.paths))
        self.status.show()
        self.status.setText("<b>" + tr("Scan with your phone's camera") + "</b> — " +
                            tr("works on any network, even mobile data."))
        self.qr.show_code(val)
        self.link.setText(val)
        self.link.show()
        self.go.hide()
        self.copy.show()

    def closeEvent(self, e):
        self._cancel = True
        super().closeEvent(e)


class SendChooser(FrontDialog):
    """How to send to the phone: Quick Share, an internet link, or the same Wi-Fi."""

    def __init__(self, paths):
        super().__init__(None)
        from PySide6.QtWidgets import QLayout
        self.setWindowTitle(f"{APP} — " + tr("Send to phone"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS) +
                           f"QPushButton#way{{text-align:left;padding:0;border-radius:10px;background:{theme.hexc('surface')};"
                           f"border:1px solid {theme.hexc('border')}}}"
                           f"QPushButton#way:hover{{border:1px solid {theme.hexc('accent')}}}"
                           f"QPushButton#way:disabled{{background:transparent}}"
                           "QLabel#waytitle{font:700 10.5pt 'Segoe UI';background:transparent}"
                           f"QLabel#waydesc{{color:{theme.hexc('dim')};font:9pt 'Segoe UI';background:transparent}}")
        lay = QVBoxLayout(self)
        lay.setSpacing(8)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        what = Path(paths[0]).name if len(paths) == 1 else tr("{n} files", n=len(paths))
        lay.addWidget(QLabel(f"<b>{tr('How do you want to send it?')}</b><br>"
                             f"<span style='color:{theme.hexc('dim')}'>{what}</span>"))
        self.choice = None
        last = settings().value("share_way", "quick")
        last = "internet" if last == "iphone" else last
        clouds = cloud_folders()
        refresh_clouds()
        warm_lan_ips()                                     # ready if Same Wi-Fi is chosen
        cloud_names = ", ".join(dict.fromkeys(n.split(" (")[0] for n, _ in clouds))
        from PySide6.QtCore import QSize as _QS
        for key, icon, title, desc, ok in (
                ("quick", "quickshare", tr("Quick Share"), tr("Straight to a nearby Android phone. No network setup."), True),
                ("internet", "link", tr("Internet link"), tr("Uploads to a free temporary file service. Any phone, any network."), True),
                ("pclink", "pclink", tr("Link from this PC"), tr("A link that works anywhere, served from this PC while the window is open. Nothing is uploaded."), True),
                ("cloud", "cloud", tr("Cloud link"),
                 tr("A share link from your {cloud}. Works even when this PC is off.", cloud=cloud_names) if clouds
                 else tr("A share link from OneDrive, Google Drive, iCloud Drive, Dropbox or Box. Works even when this PC is off."), True),
                ("bluetooth", "bluetooth", tr("Bluetooth"), tr("Slower, but needs no network. Android phones paired to this PC."), True),
                ("wifi", "wifi", tr("Same Wi-Fi"), tr("The phone downloads directly from this PC. Routers and firewalls can block it."), True)):
            b = QPushButton()
            b.setObjectName("way")
            b.setAutoDefault(False)
            b.setEnabled(ok)
            b.setMinimumWidth(440)
            row = QHBoxLayout(b)
            row.setContentsMargins(14, 10, 14, 10)
            row.setSpacing(14)
            ic = QLabel()
            ic.setPixmap(nav_icon(icon).pixmap(_QS(26, 26), QIcon.Selected if ok else QIcon.Normal))
            ic.setFixedSize(28, 28)
            col = QVBoxLayout()
            col.setSpacing(1)
            t = QLabel(title)
            t.setObjectName("waytitle")
            d = QLabel(desc)
            d.setObjectName("waydesc")
            d.setWordWrap(True)
            col.addWidget(t)
            col.addWidget(d)
            for w in (ic, t, d):
                w.setAttribute(Qt.WA_TransparentForMouseEvents)
            row.addWidget(ic, 0, Qt.AlignVCenter)
            row.addLayout(col, 1)
            b.setMinimumHeight(row.sizeHint().height() + 4)
            b.clicked.connect(lambda _=False, k=key: self._pick(k))
            lay.addWidget(b)

    def _pick(self, key):
        self.choice = key
        settings().setValue("share_way", key)
        self.accept()


CLOUD_APPS = [("OneDrive", "https://www.microsoft.com/microsoft-365/onedrive/download"),
              ("Google Drive", "https://www.google.com/drive/download/"),
              ("iCloud Drive", "https://apps.microsoft.com/detail/9pktq5699m62"),
              ("Dropbox", "https://www.dropbox.com/install"),
              ("Box", "https://www.box.com/resources/downloads/drive")]


_CLOUDS = None          # [(name, folder)] found in the background (looking can be slow: drives, network)


def _detect_clouds() -> list:
    """Cloud storage apps set up on this PC and their synced folders: OneDrive, Google Drive, iCloud Drive,
    Dropbox and Box."""
    out, seen = [], set()

    def add(name, folder):
        try:
            if folder and Path(folder).is_dir() and os.path.normcase(str(folder)) not in seen:
                seen.add(os.path.normcase(str(folder)))
                out.append((name, Path(folder)))
        except OSError:
            pass
    for env, name in (("OneDriveConsumer", "OneDrive"), ("OneDriveCommercial", "OneDrive (work)"), ("OneDrive", "OneDrive")):
        add(name, os.environ.get(env))
    # Google Drive for desktop: its settings say which drive letter it mounts ("My Drive" inside)
    gdrive = None
    if winsys.IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Google\DriveFS") as k:
                prefs = json.loads(winreg.QueryValueEx(k, "PerAccountPreferences")[0])
            for acc in prefs.get("per_account_preferences", []):
                mp = (acc.get("value") or {}).get("mount_point_path")
                if mp:
                    gdrive = Path((mp.rstrip(":\\") + ":\\") if len(mp.rstrip(":\\")) == 1 else mp) / "My Drive"
                    break
        except (OSError, ValueError, TypeError):
            pass
        if gdrive is None or not gdrive.is_dir():   # otherwise: the drive Google Drive puts up (it's labelled
            import ctypes                           # "Google Drive"); never network or CD drives
            gdrive = None
            mask = ctypes.windll.kernel32.GetLogicalDrives()
            for i in range(3, 26):
                if not mask & (1 << i):
                    continue
                root = f"{chr(65 + i)}:\\"
                if ctypes.windll.kernel32.GetDriveTypeW(root) not in (3, 4):
                    continue
                try:
                    label = ctypes.create_unicode_buffer(261)
                    ok = ctypes.windll.kernel32.GetVolumeInformationW(root, label, 261, None, None, None, None, 0)
                    if (ok and "google" in label.value.lower()) or Path(root, "My Drive").is_dir():
                        mine = Path(root, "My Drive")
                        if not mine.is_dir():       # "My Drive" in another language: the first ordinary folder
                            mine = next((d for d in sorted(Path(root).iterdir()) if d.is_dir() and not d.name.startswith(
                                (".", "$")) and d.name not in ("Shared drives", "Other computers")), None)
                        if mine is not None:
                            gdrive = mine
                            break
                except OSError:
                    continue
    add("Google Drive", gdrive)
    add("Google Drive", Path.home() / "My Drive")                  # Google Drive set to mirror files into a folder
    add("Google Drive", Path.home() / "Google Drive")              # the older Backup and Sync folder
    add("iCloud Drive", Path.home() / "iCloudDrive")
    for base in (os.environ.get("APPDATA"), os.environ.get("LOCALAPPDATA")):   # Dropbox writes where its folder is
        try:
            info = json.loads((Path(base) / "Dropbox" / "info.json").read_text(encoding="utf-8")) if base else {}
        except (OSError, ValueError):
            info = {}
        for kind, name in (("personal", "Dropbox"), ("business", "Dropbox (work)")):
            add(name, (info.get(kind) or {}).get("path"))
    add("Box", Path.home() / "Box")
    return out


def cloud_folders(wait=False) -> list:
    """The clouds found so far (looked for in the background, so opening a window never waits for drives)."""
    global _CLOUDS
    if _CLOUDS is None and wait:
        _CLOUDS = _detect_clouds()
    return list(_CLOUDS or [])


def refresh_clouds():
    def run():
        global _CLOUDS
        try:
            _CLOUDS = _detect_clouds()
        except Exception as e:
            winsys.log(f"clouds: {e}")
    threading.Thread(target=run, daemon=True).start()


def cloud_shares() -> list:
    return _jload("cloud_shares", []) if "_jload" in globals() else []


def remember_cloud_share(path, expires, key="", url="", name=""):
    old = next((x for x in cloud_shares() if x.get("path") == str(path)), {})
    item = dict(old, path=str(path), expires=expires)
    for k, v in (("key", key), ("url", url), ("name", name)):
        if v:
            item[k] = v
    lst = [x for x in cloud_shares() if x.get("path") != str(path)] + [item]
    settings().setValue("cloud_shares", json.dumps(lst, ensure_ascii=False))


def stop_cloud_share(path):
    """Stop sharing now: the cloud copy goes (to the cloud's recycle bin), so its link stops working."""
    try:
        Path(path).unlink(missing_ok=True)
        winsys.log(f"cloud link stopped: {Path(path).name}")
    except OSError as e:
        winsys.log(f"cloud link: couldn't delete {path}: {e}")
        return
    settings().setValue("cloud_shares", json.dumps([x for x in cloud_shares() if x.get("path") != str(path)],
                                                   ensure_ascii=False))


def live_share(kind, paths):
    """A link made earlier for these same files that still works: {"url", "name", "expires"} or None."""
    key = share_key(paths)
    if kind == "internet":
        return next((x for x in share_links() if x.get("key") == key), None)
    for x in cloud_shares():
        if x.get("key") == key and x.get("url") and (not x.get("expires") or x["expires"] > time.time()) \
                and Path(x["path"]).exists():
            return {"url": x["url"], "name": x.get("name") or Path(x["path"]).name, "expires": x.get("expires", 0),
                    "path": x["path"]}
    return None


def clean_cloud_shares():
    """Delete cloud-link copies whose time is up (they go to the cloud's own recycle bin)."""
    keep = []
    for x in cloud_shares():
        if x.get("expires") and x["expires"] <= time.time():
            try:
                Path(x["path"]).unlink(missing_ok=True)
                winsys.log(f"cloud link ended: {Path(x['path']).name}")
            except OSError as e:
                winsys.log(f"cloud link: couldn't delete {x['path']}: {e}")
                keep.append(x)
        else:
            keep.append(x)
    if len(keep) != len(cloud_shares()):
        settings().setValue("cloud_shares", json.dumps(keep, ensure_ascii=False))


_CLOUD_LINK = ("1drv.ms/", "onedrive.live.com/", "sharepoint.com/", "drive.google.com/", "docs.google.com/",
               "icloud.com/", "dropbox.com/", "db.tt/", "box.com/")


class CloudShare(FrontDialog):
    """Send to phone → Cloud link: a copy goes into your OneDrive or Google Drive, and its own Share window gives the
    link (trusted, no ads, works when this PC is off). DragWheel shows the link you copy as a QR code."""
    KEEP = [(60, "1 hour"), (12 * 60, "12 hours"), (24 * 60, "1 day"), (3 * 24 * 60, "3 days"), (7 * 24 * 60, "1 week"),
            (0, "Keep it")]

    def __init__(self, paths):
        super().__init__(None)
        from PySide6.QtWidgets import QLayout
        self.setWindowTitle(f"{APP} — " + tr("Send to phone"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.paths = [Path(x) for x in paths]
        self.clouds = cloud_folders(wait=True)
        refresh_clouds()                                   # anything set up since: ready for next time
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        what = self.paths[0].name if len(self.paths) == 1 and self.paths[0].is_file() else \
            tr("{n} files (as one ZIP)", n=len(self.paths)) if len(self.paths) > 1 else self.paths[0].name + ".zip"
        self.header(lay, tr("Cloud link"), what)
        self.qr = QrBox()
        self.qr.idle(tr("The QR code appears here"))
        lay.addWidget(self.qr, 0, Qt.AlignHCenter)
        self.link = QLabel()
        self.link.setObjectName("sub")
        self.link.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.link.setAlignment(Qt.AlignCenter)
        self.link.setWordWrap(True)
        self.link.setFixedWidth(QR_W)
        self.link.hide()
        lay.addWidget(self.link, 0, Qt.AlignHCenter)
        form = QFormLayout()
        self.cloud = QComboBox()
        for name, folder in self.clouds:
            self.cloud.addItem(name, str(folder))
        have = {n.split(" (")[0] for n, _ in self.clouds}
        missing = [(n, url) for n, url in CLOUD_APPS if n not in have]
        if missing:                                   # the others: a quick way to get them
            if self.clouds:
                self.cloud.insertSeparator(self.cloud.count())
            for n, url in missing:
                self.cloud.addItem(tr("{cloud} — not set up on this PC", cloud=n), "get:" + url)
        self.cloud.setCurrentIndex(max(0, self.cloud.findText(settings().value("cloud_last", ""))))
        self.cloud.currentIndexChanged.connect(self._cloud_changed)
        form.addRow(tr("Cloud"), self.cloud)
        self.keep = QComboBox()
        for m, label in self.KEEP:
            self.keep.addItem(tr(label), m)
        self.keep.setCurrentIndex(max(0, self.keep.findData(int(settings().value("cloud_keep", 24 * 60)))))
        form.addRow(tr("Delete it after"), self.keep)
        lay.addLayout(form)
        note = QLabel(tr("A copy goes into a “DragWheel shares” folder in your cloud, and the cloud's own Share window "
                         "opens: choose who can open it and copy the link. The link works even when this PC is off."))
        note.setObjectName("note")
        note.setWordWrap(True)
        note.setFixedWidth(QR_W)
        lay.addWidget(note)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setFixedWidth(QR_W)
        lay.addWidget(self.status)
        self.go = QPushButton(tr("Make a link"))
        self.go.setObjectName("primary")
        self.go.clicked.connect(self._start)
        self._note = note
        self._cloud_changed()
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        self.buttons(lay, self.go, close)
        self.dest = None
        self._copied = None
        self._clip_start = ""
        self._shared = None
        self._closed = False
        self._poll = QTimer(self, interval=400, timeout=self._update)

    def sharing(self):
        return self.dest is not None and Path(self.dest).exists()

    def stop_question(self):
        return tr("Stop sharing deletes the copy from {cloud}, so the link stops working. Keep sharing leaves it "
                  "until the time you chose.", cloud=self.cloud.currentText())

    def stop_sharing(self):
        stop_cloud_share(self.dest)

    def closeEvent(self, e):
        if not self.leave_ok(e):
            return
        self._closed = True
        super().closeEvent(e)

    def _cloud_changed(self, *_):
        data = str(self.cloud.currentData() or "")
        get = data.startswith("get:")
        name = self.cloud.currentText().split(" — ")[0]
        self.keep.setEnabled(not get)
        self.go.setText(tr("Get {cloud}", cloud=name) if get else tr("Make a link"))
        self._note.setText(tr("{cloud} isn't set up on this PC. Install it and sign in, then choose it here.", cloud=name)
                           if get else tr("A copy goes into a “DragWheel shares” folder in your cloud, and the cloud's "
                                          "own Share window opens: choose who can open it and copy the link. The link "
                                          "works even when this PC is off."))

    def _start(self):
        data = str(self.cloud.currentData() or "")
        if data.startswith("get:"):
            QDesktopServices.openUrl(QUrl(data[4:]))
            refresh_clouds()
            return
        settings().setValue("cloud_last", self.cloud.currentText())
        settings().setValue("cloud_keep", self.keep.currentData())
        self.go.setEnabled(False)
        self.cloud.setEnabled(False)
        self.keep.setEnabled(False)
        folder = Path(self.cloud.currentData()) / "DragWheel shares"
        self.status.setText(tr("Copying to {cloud}…", cloud=self.cloud.currentText()))
        self._clip_start = QGuiApplication.clipboard().text()

        def work():
            try:
                folder.mkdir(parents=True, exist_ok=True)
                src = self.paths[0]
                if len(self.paths) == 1 and src.is_file():
                    dest = engine.unique_path(folder / src.name)
                    shutil.copy2(src, dest)
                else:
                    import zipfile
                    dest = engine.unique_path(folder / ((src.name if len(self.paths) == 1 else "DragWheel") + ".zip"))
                    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
                        for it in self.paths:
                            for f in ([it] if it.is_file() else [x for x in it.rglob("*") if x.is_file()]):
                                z.write(f, str(f.relative_to(it.parent)))
                self._copied = ("ok", dest)
            except Exception as e:
                self._copied = ("err", str(e))
        threading.Thread(target=work, daemon=True).start()
        self._poll.start()

    def _update(self):
        if self._copied is not None:
            kind, val = self._copied
            self._copied = None
            if kind == "err":
                self.qr.idle(tr("No link"))
                self.status.setText(f"<span style='color:{theme.hexc('danger')}'>{val}</span>")
                self._poll.stop()
                return
            self.dest = val
            m = int(self.keep.currentData())
            remember_cloud_share(val, time.time() + m * 60 if m else 0, share_key(self.paths),
                                 name=self.paths[0].name if len(self.paths) == 1 else Path(val).name)
            winsys.log(f"send to phone (cloud): {val}")
            self.status.setText("")
            self.qr.busy(tr("Waiting for {cloud} to take the file…", cloud=self.cloud.currentText()))
            cloud = self.cloud.currentText()

            def ask():
                # the cloud's own right-click entry. Never the plain Windows "Share" (that's Quick Share / Nearby).
                # OneDrive only offers "Copy link" once the file has synced, so keep trying for a while.
                names = ["Copy link", "Copy Dropbox link", "Copy Shared Link", "Share with Google Drive",
                         "Share with iCloud", "Share with Dropbox", "Share with Box", "iCloud Drive"]
                ok = False
                for _ in range(20):
                    try:
                        ok = winsys.invoke_shell_verb([str(val)], *names)
                    except Exception as e:
                        winsys.log(f"cloud share verb: {e}")
                    if ok or self._closed:
                        break
                    time.sleep(2)
                self._shared = ok
            self._shared = None
            threading.Thread(target=ask, daemon=True).start()
            return
        if self._shared is not None:
            ok, self._shared = self._shared, None
            self.qr.busy(tr("Waiting for the link…"))
            if ok:
                self.status.setText(tr("In {cloud}'s Share window, choose who can open it and copy the link. "
                                       "It appears here as a QR code.", cloud=self.cloud.currentText()))
            else:
                winsys.reveal(str(self.dest))
                self.status.setText(tr("Right-click the file in the window that opened, choose Share (or Copy link), "
                                       "and copy the link. It appears here as a QR code."))
        text = QGuiApplication.clipboard().text().strip()
        if self.dest is not None and text != self._clip_start and text.startswith("http") and any(
                c in text for c in _CLOUD_LINK):
            self._poll.stop()
            self._show(text)

    def _show(self, url):
        self.url = url
        if self.dest is not None:
            m = int(self.keep.currentData())
            remember_cloud_share(self.dest, next((x["expires"] for x in cloud_shares() if x.get("path") == str(self.dest)),
                                                 time.time() + m * 60 if m else 0), url=url)
        self.status.setText("<b>" + tr("Scan with your phone's camera") + "</b> — " +
                            tr("works on any network, even mobile data."))
        self.qr.show_code(url)
        self.link.setText(url)
        self.link.show()
        self.go.setText(tr("Copy link"))
        self.go.setEnabled(True)
        try:
            self.go.clicked.disconnect()
        except Exception:
            pass
        self.go.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.url))
        self.adjustSize()


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
