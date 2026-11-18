"""DragWheel: Sticky notes: a note on the desktop that saves itself (a .txt file you can open anywhere)

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations

NOTE_EXTS = {"txt", "text", "md", "log"}           # floated, these open as an editable sticky note
NOTE_COLORS = [                                    # name, paper, top bar, text
    ("Yellow", "#fff4b0", "#fce77d", "#26231a"),
    ("Green", "#d4f2c9", "#b6e5a7", "#1b2618"),
    ("Pink", "#ffd6e4", "#fdbbd0", "#2a1a20"),
    ("Blue", "#d3e8ff", "#b5d6fb", "#18202b"),
    ("Purple", "#e7dbff", "#d3c0fb", "#211a2c"),
    ("Charcoal", "#34353a", "#2a2b2f", "#eceef1"),
]


def default_notes_base() -> Path:
    from PySide6.QtCore import QStandardPaths
    return Path(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or Path.home())


def notes_folder() -> Path:
    """Where new sticky notes are kept: Documents › DragWheel Notes, or a DragWheel Notes folder in a cloud
    (OneDrive, Google Drive…) chosen from a note's ⋯ menu, so they follow you to your other PCs."""
    base = settings().value("notes_base", "") or ""
    return Path(base) / "DragWheel Notes" if base else default_notes_base() / "DragWheel Notes"


def _note_states() -> list:
    try:
        v = json.loads(settings().value("sticky_notes", "[]") or "[]")
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


class StickyNote(QWidget):
    """A sticky note on the desktop. It's a plain text file (new notes go in Documents › DragWheel Notes; a .txt you
    float is edited in place) and saves itself as you type. Drag it by the top, resize from the corner; ⋯ has the
    colours, Keep on top, text size and Delete. Open notes come back when DragWheel starts."""
    closed = Signal(object)
    changed = Signal()            # moved, resized, recoloured: the app saves where the notes are
    SHADOW = 10

    def __init__(self, path, state=None):
        from PySide6.QtWidgets import QSizeGrip, QTextEdit, QToolButton
        st = state or {}
        self.on_top = bool(st.get("on_top", False))
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | (Qt.WindowStaysOnTopHint if self.on_top else Qt.Widget))
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.path = Path(path)
        self.mine = self.path.parent == notes_folder()        # a note we made (not a .txt you floated)
        self.color = st.get("color") if st.get("color") in [c[0] for c in NOTE_COLORS] \
            else settings().value("note_color", "Yellow")
        self.font_pt = float(st.get("font") or 11.5)
        self._enc, self._bom, self._nl, self._saved = "utf-8", False, "\r\n", ""
        self._drag = None
        self.setWindowTitle(self.path.stem)
        self.setWindowIcon(app_icon())
        outer = QVBoxLayout(self)
        m = self.SHADOW
        outer.setContentsMargins(m, m - 2, m, m + 2)
        outer.setSpacing(0)

        self.head = QWidget()
        self.head.setFixedHeight(32)
        self.head.setCursor(Qt.SizeAllCursor)
        hl = QHBoxLayout(self.head)
        hl.setContentsMargins(8, 2, 6, 0)
        hl.setSpacing(2)

        def tb(text, tip, fn):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedSize(26, 26)
            b.clicked.connect(fn)
            return b
        self.new_b = tb("+", tr("New sticky note"), lambda: self.app_new())
        self.title = QLabel("" if self.mine else self.path.name)
        self.title.setStyleSheet("background:transparent;font:600 8.5pt 'Segoe UI'")
        self.menu_b = tb("⋯", tr("Menu"), self._menu)
        self.close_b = tb("✕", tr("Close note"), self.close_by_user)
        hl.addWidget(self.new_b)
        hl.addWidget(self.title, 1)
        hl.addWidget(self.menu_b)
        hl.addWidget(self.close_b)
        outer.addWidget(self.head)

        self.edit = QTextEdit()
        self.edit.setAcceptRichText(False)
        self.edit.setFrameShape(QFrame.NoFrame)
        self.edit.setPlaceholderText(tr("Write a note…"))
        self.edit.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        outer.addWidget(self.edit, 1)
        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 2, 2)
        foot.addStretch(1)
        self.grip = QSizeGrip(self)
        foot.addWidget(self.grip, 0, Qt.AlignRight | Qt.AlignBottom)
        outer.addLayout(foot)

        self._read()
        self._apply_style()
        self._save_timer = QTimer(self, singleShot=True, interval=500, timeout=self._write)
        self.edit.textChanged.connect(lambda: self._save_timer.start())
        from PySide6.QtCore import QFileSystemWatcher
        self._watch = QFileSystemWatcher([str(self.path)], self)
        self._watch.fileChanged.connect(self._outside_change)
        self.resize(int(st.get("w") or 300), int(st.get("h") or 300))
        if "x" in st and "y" in st and QGuiApplication.screenAt(QPoint(int(st["x"]) + 30, int(st["y"]) + 30)):
            self.move(int(st["x"]), int(st["y"]))
        else:
            self.move(QCursor.pos() - QPoint(150, 20))
        self.app_new = lambda: None              # the app sets this: a new note next to this one

    def _read(self):
        try:
            data = self.path.read_bytes()
        except OSError:
            data = b""
        self._bom = data.startswith(b"\xef\xbb\xbf")
        self._nl = "\r\n" if b"\r\n" in data or not data else "\n"
        import locale
        for enc in ("utf-8-sig", locale.getpreferredencoding(False) or "cp1252", "latin-1"):
            try:
                text = data.decode(enc)
                self._enc = "utf-8" if enc == "utf-8-sig" else enc
                break
            except UnicodeDecodeError:
                continue
        text = text.replace("\r\n", "\n")
        self._saved = text
        self.edit.blockSignals(True)
        self.edit.setPlainText(text)
        self.edit.blockSignals(False)

    def _write(self):
        text = self.edit.toPlainText()
        if text == self._saved:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = text.replace("\n", self._nl).encode(self._enc, errors="replace")
            if self._bom:
                data = b"\xef\xbb\xbf" + data
            self._watch.removePath(str(self.path))       # our own save isn't a change from outside
            self.path.write_bytes(data)
            self._saved = text
            self._watch.addPath(str(self.path))
            self.title.setToolTip("")
        except OSError as e:
            winsys.log(f"sticky note: {e}")
            self.title.setText(tr("Couldn't save"))
            self.title.setToolTip(str(e))

    def _outside_change(self, _p):
        """Changed in another app: show the new text (if nothing was typed here since the last save)."""
        if self.edit.toPlainText() == self._saved and self.path.exists():
            cur = self.edit.textCursor().position()
            self._read()
            c = self.edit.textCursor()
            c.setPosition(min(cur, len(self.edit.toPlainText())))
            self.edit.setTextCursor(c)
        if self.path.exists() and str(self.path) not in self._watch.files():
            self._watch.addPath(str(self.path))           # editors that save by replacing the file

    def _colors(self):
        return next(c for c in NOTE_COLORS if c[0] == self.color)

    def _apply_style(self):
        _n, paper, head, ink = self._colors()
        self.head.setStyleSheet(f"background:transparent;color:{ink}")
        self.title.setStyleSheet(f"background:transparent;color:{ink};font:600 8.5pt 'Segoe UI'")
        btn = (f"QToolButton{{background:transparent;color:{ink};border:none;border-radius:6px;"
               f"font:700 12pt 'Segoe UI'}}QToolButton:hover{{background:rgba(0,0,0,0.10)}}")
        for b in (self.new_b, self.menu_b, self.close_b):
            b.setStyleSheet(btn)
        self.edit.setStyleSheet(
            f"QTextEdit{{background:transparent;color:{ink};border:none;selection-background-color:rgba(0,0,0,0.18);"
            f"padding:6px 10px 6px 12px;font:{self.font_pt}pt 'Segoe UI'}}"
            "QScrollBar:vertical{background:transparent;width:8px}"
            "QScrollBar::handle:vertical{background:rgba(0,0,0,0.18);border-radius:4px;min-height:24px}"
            "QScrollBar::add-line,QScrollBar::sub-line{height:0}")
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        _n, paper, head, _ink = self._colors()
        m = self.SHADOW
        r = QRectF(self.rect()).adjusted(m, m - 2, -m, -m + 2)
        for i in range(m, 0, -2):                       # a soft shadow
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, int(26 * (1 - i / m)) + 3))
            p.drawRoundedRect(r.adjusted(-i / 2, -i / 2 + 2, i / 2, i / 2 + 2), 12 + i / 2, 12 + i / 2)
        p.setBrush(QColor(paper))
        p.drawRoundedRect(r, 12, 12)
        top = QPainterPath()
        top.addRoundedRect(QRectF(r.x(), r.y(), r.width(), 44), 12, 12)
        clip = QPainterPath()
        clip.addRect(QRectF(r.x(), r.y(), r.width(), 32))
        p.fillPath(top.intersected(clip), QColor(head))

    # ---- moving by the top bar
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and e.position().y() < self.SHADOW + 32:
            self._drag = e.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, e):
        if self._drag is not None:
            self._drag = None
            self.changed.emit()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.changed.emit()

    # ---- ⋯ menu
    def _menu(self):
        menu = QMenu(self)
        from PySide6.QtGui import QIcon as _I
        for name, paper, head, _ink in NOTE_COLORS:
            pm = QPixmap(28, 28)
            pm.fill(Qt.transparent)
            pp = QPainter(pm)
            pp.setRenderHint(QPainter.Antialiasing)
            pp.setPen(QPen(QColor(head), 3))
            pp.setBrush(QColor(paper))
            pp.drawEllipse(QRectF(3, 3, 22, 22))
            pp.end()
            a = menu.addAction(_I(pm), tr(name), lambda n=name: self._set_color(n))
            a.setCheckable(True)
            a.setChecked(name == self.color)
        menu.addSeparator()
        a = menu.addAction(tr("Keep on top"), self._toggle_top)
        a.setCheckable(True)
        a.setChecked(self.on_top)
        menu.addAction(tr("Bigger text"), lambda: self._font(1.5))
        menu.addAction(tr("Smaller text"), lambda: self._font(-1.5))
        menu.addSeparator()
        if _APP is not None:
            km = menu.addMenu(tr("Keep notes in"))
            cur = os.path.normcase(str(notes_folder().parent))
            places = [(tr("This PC (Documents)"), default_notes_base())] + [(name, Path(folder))
                                                                         for name, folder in cloud_folders()]
            for label, base in places:
                a = km.addAction(label, lambda b=base: _APP.move_notes(b))
                a.setCheckable(True)
                a.setChecked(os.path.normcase(str(base)) == cur)
            km.addSeparator()
            km.addAction(tr("Choose a folder…"), self._choose_notes_folder)
            km.setToolTipsVisible(True)
            menu.addAction(tr("Show all notes"), _APP.open_all_notes)
        menu.addAction(tr("Show in Explorer"), lambda: (self._write(), winsys.reveal(str(self.path))))
        if self.mine:
            menu.addAction(tr("Delete note"), self._delete)
        menu.exec(self.menu_b.mapToGlobal(QPoint(0, self.menu_b.height())))

    def _choose_notes_folder(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(self, tr("Keep notes in"), str(notes_folder().parent))
        if d and _APP is not None:
            _APP.move_notes(Path(d))

    def relocate(self, new_path):
        """The notes folder moved (Keep notes in…): carry on with the same note in its new place."""
        self._watch.removePath(str(self.path))
        self.path = Path(new_path)
        self.mine = self.path.parent == notes_folder()
        if self.path.exists():
            self._watch.addPath(str(self.path))

    def _set_color(self, name):
        self.color = name
        settings().setValue("note_color", name)          # the next new note gets it too
        self._apply_style()
        self.changed.emit()

    def _toggle_top(self):
        self.on_top = not self.on_top
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.on_top)
        self.show()
        self.changed.emit()

    def _font(self, d):
        self.font_pt = max(8.0, min(28.0, self.font_pt + d))
        self._apply_style()
        self.changed.emit()

    def _delete(self):
        if self.edit.toPlainText().strip():
            box = QMessageBox(self)
            box.setWindowTitle(APP)
            box.setStyleSheet(i18n.css(DIALOG_CSS))
            box.setText(tr("Delete this note?"))
            box.setInformativeText(tr("It goes to the Recycle Bin."))
            yes = box.addButton(tr("Delete note"), QMessageBox.DestructiveRole)
            box.addButton(QMessageBox.Cancel).setText(tr("Cancel"))
            box.exec()
            if box.clickedButton() is not yes:
                return
        self._save_timer.stop()
        self._watch.removePath(str(self.path))
        try:
            if self.path.exists():
                winsys.recycle(str(self.path))
        except OSError as e:
            winsys.log(f"sticky note delete: {e}")
        self._deleted = True
        self.close_by_user()

    def close_by_user(self):
        """✕, Ctrl+W or Delete: this note no longer comes back. Any other close (Windows restarting or shutting
        down, DragWheel quitting) keeps it, so it opens again next time."""
        self.by_user = True
        self.close()

    def state(self):
        return {"path": str(self.path), "x": self.x(), "y": self.y(), "w": self.width(), "h": self.height(),
                "color": self.color, "on_top": self.on_top, "font": self.font_pt}

    def keyPressEvent(self, e):
        if e.modifiers() & Qt.ControlModifier and e.key() == Qt.Key_N:
            self.app_new()
            return
        if e.modifiers() & Qt.ControlModifier and e.key() == Qt.Key_W:
            self.close_by_user()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        if not getattr(self, "_deleted", False):
            self._write()
            if getattr(self, "by_user", False) and self.mine and not self.edit.toPlainText().strip():
                try:                                        # an empty note you closed isn't kept
                    self.path.unlink(missing_ok=True)
                except OSError:
                    pass
        self.closed.emit(self)
        super().closeEvent(e)
