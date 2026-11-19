"""DragWheel: PDF: page grid (Arrange pages…) and signing (Sign…)

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


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
        for d in self.docs.values():                       # let go of the PDFs (else they can't be renamed/deleted)
            try:
                if d is not None:
                    d.close()
            except Exception:
                pass
        self.docs = {}

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


def _scan_icon(kind, color) -> "QIcon":
    """Line icons for Fix alignment's tool row."""
    from PySide6.QtGui import QIcon
    pm = QPixmap(48, 48)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 3.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if kind in ("left", "right"):
        p.drawRoundedRect(QRectF(14, 20, 20, 20), 3, 3)          # the page
        path = QPainterPath()
        if kind == "left":
            path.moveTo(34, 12)
            path.cubicTo(28, 6, 16, 6, 11, 14)
            p.drawPath(path)
            p.drawPolyline([QPointF(9, 6), QPointF(10, 15), QPointF(18, 14)])
        else:
            path.moveTo(14, 12)
            path.cubicTo(20, 6, 32, 6, 37, 14)
            p.drawPath(path)
            p.drawPolyline([QPointF(39, 6), QPointF(38, 15), QPointF(30, 14)])
    elif kind == "auto":
        pen.setStyle(Qt.DotLine)
        p.setPen(pen)
        p.drawRoundedRect(QRectF(9, 9, 30, 30), 4, 4)
        p.setPen(QPen(QColor(color), 3.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline([QPointF(17, 31), QPointF(17, 20), QPointF(31, 20), QPointF(31, 31)])
    else:                                                       # "all": the whole picture
        for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            cx, cy = 24 + sx * 14, 24 + sy * 14
            p.drawLine(QPointF(cx, cy), QPointF(cx - sx * 9, cy - sy * 9))
            p.drawPolyline([QPointF(cx - sx * 8, cy), QPointF(cx, cy), QPointF(cx, cy - sy * 8)])
    p.end()
    return QIcon(pm)


def _pil_to_qimage(img) -> QImage:
    img = img.convert("RGB")
    data = img.tobytes("raw", "RGB")
    return QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888).copy()


class CornerPicker(QWidget):
    """Fix alignment (like a scanner app): the photo with the page's corners found for you — drag any corner
    (a magnifier shows exactly where) — and a live preview of the result in each look, with rotate left/right.
    value() -> JSON {"corners", "look", "rotate"} for engine.image_scan."""
    VIEW_W, VIEW_H = 470, 560
    PREV_W, PREV_H = 300, 400
    LOOKS = engine.SCAN_LOOKS

    def __init__(self, path):
        super().__init__()
        from PySide6.QtWidgets import QButtonGroup, QToolButton
        self.path = str(path)
        self.pil = None                     # the photo, at most ~1400 px (enough for the view and the preview)
        self.img = None                     # the same, scaled to the view
        self.found = None
        self.pts = None
        self.look = settings().value("scan_look", self.LOOKS[0])
        if self.look not in self.LOOKS:
            self.look = self.LOOKS[0]
        self.rot = 0
        self.drag = None
        self._ver = 0                        # preview: newest request, and the result coming back from the thread
        self._done = None
        self._busy = False
        self._loaded = None
        self._angle = 0
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(8)
        self.view = QWidget()
        self.view.setFixedSize(self.VIEW_W, self.VIEW_H)
        self.view.setMouseTracking(True)
        self.view.paintEvent = self._paint
        self.view.mousePressEvent = self._press
        self.view.mouseMoveEvent = self._move
        self.view.mouseReleaseEvent = self._release
        left.addWidget(self.view, 0, Qt.AlignHCenter)
        self.hint = QLabel(tr("Finding the page…"))
        self.hint.setObjectName("sub")
        self.hint.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        self.hint.setAlignment(Qt.AlignCenter)
        left.addWidget(self.hint)
        tools = QHBoxLayout()
        tools.setSpacing(6)
        css = (f"QToolButton{{background:transparent;color:{theme.hexc('text')};border:none;border-radius:10px;"
               f"padding:6px 4px;font:600 9pt 'Segoe UI'}} QToolButton:hover{{background:{theme.hexc('hover')}}}"
               f"QToolButton:disabled{{color:{theme.hexc('dim')}}}")
        self.tool_btns = {}
        for kind, label, fn in (("left", tr("Left"), lambda: self._rotate(-90)), ("right", tr("Right"), lambda: self._rotate(90)),
                                ("auto", tr("Find the page"), lambda: self._set(self.found)),
                                ("all", tr("Whole picture"), lambda: self._set([[0, 0], [1, 0], [1, 1], [0, 1]]))):
            b = QToolButton()
            b.setIcon(_scan_icon(kind, theme.hexc("text")))
            b.setIconSize(QSize(26, 26))
            b.setText(label)
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setStyleSheet(css)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumWidth(104)
            b.clicked.connect(fn)
            self.tool_btns[kind] = b
            tools.addWidget(b)
        self.tool_btns["auto"].setEnabled(False)
        left.addLayout(tools)
        root.addLayout(left)
        right = QVBoxLayout()
        right.setSpacing(8)
        cap = QLabel(tr("Preview"))
        cap.setStyleSheet(f"color:{theme.hexc('dim')};font:600 9pt 'Segoe UI'")
        right.addWidget(cap)
        self.prev = QLabel()
        self.prev.setFixedSize(self.PREV_W, self.PREV_H)
        self.prev.setAlignment(Qt.AlignCenter)
        self.prev.setStyleSheet(f"background:{theme.hexc('surface')};border:1px solid {theme.hexc('border')};"
                                f"border-radius:12px")
        right.addWidget(self.prev)
        cap2 = QLabel(tr("Look"))
        cap2.setStyleSheet(f"color:{theme.hexc('dim')};font:600 9pt 'Segoe UI'")
        right.addWidget(cap2)
        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.chips = {}
        chip_css = (f"QToolButton{{background:transparent;color:{theme.hexc('dim')};border:2px solid transparent;"
                    f"border-radius:10px;padding:4px;font:600 8pt 'Segoe UI'}}"
                    f"QToolButton:hover{{background:{theme.hexc('hover')}}}"
                    f"QToolButton:checked{{border-color:{theme.hexc('accent')};color:{theme.hexc('text')}}}")
        short = {"Clean document": tr("Clean"), "Original colours": tr("Original"), "Black & white": tr("B&W"),
                 "Grayscale": tr("Gray")}
        for look in self.LOOKS:
            b = QToolButton()
            b.setCheckable(True)
            b.setChecked(look == self.look)
            b.setText(short.get(look, tr(look)))
            b.setToolTip(tr(look))
            b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            b.setIconSize(QSize(58, 76))
            b.setStyleSheet(chip_css)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, lk=look: self._set_look(lk))
            self.group.addButton(b)
            self.chips[look] = b
            chips.addWidget(b)
        right.addLayout(chips)
        right.addStretch(1)
        root.addLayout(right)
        self._poll = QTimer(self, interval=60, timeout=self._update)
        self._poll.start()
        self._debounce = QTimer(self, singleShot=True, interval=180, timeout=self._render)

        def load():                                       # off the main thread: open, shrink, find the page
            try:
                pil = engine.open_image(self.path)
                pil.thumbnail((1400, 1400))
                pil = pil.convert("RGB")
                found = engine.detect_document(pil)
                self._loaded = ("ok", pil, found)
            except Exception as e:
                self._loaded = ("err", str(e), None)
        threading.Thread(target=load, daemon=True).start()

    # ---- state
    def _update(self):
        if self._loaded is not None:
            kind, val, found = self._loaded
            self._loaded = None
            if kind == "err":
                self.hint.setText(f"<span style='color:{theme.hexc('danger')}'>{val}</span>")
                return
            self.pil = val
            q = _pil_to_qimage(val)
            self.img = q.scaled(self.VIEW_W - 28, self.VIEW_H - 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.found = found
            self.tool_btns["auto"].setEnabled(found is not None)
            self.pts = [list(p) for p in (found or [[0.04, 0.04], [0.96, 0.04], [0.96, 0.96], [0.04, 0.96]])]
            self.hint.setText(tr("Drag the corners onto the corners of the page.") if found else
                              tr("No page edge found: drag the corners onto the corners of the page."))
            self.view.update()
            self._render()
        if self._done is not None:
            ver, results = self._done
            self._done = None
            self._busy = False
            if ver == self._ver:
                for look, img in results.items():
                    q = _pil_to_qimage(img)
                    if look == self.look:
                        self.prev.setPixmap(QPixmap.fromImage(q.scaled(self.PREV_W - 16, self.PREV_H - 16,
                                                                      Qt.KeepAspectRatio, Qt.SmoothTransformation)))
                    self.chips[look].setIcon(QIcon(QPixmap.fromImage(q.scaled(58, 76, Qt.KeepAspectRatio,
                                                                              Qt.SmoothTransformation))))
                self._results = results
            else:
                self._render()
        if self.pil is None:
            self._angle = (self._angle + 12) % 360
            self.view.update()

    def _changed(self):
        self._ver += 1
        self.view.update()
        self._debounce.start()

    def _render(self):
        """Straighten a small copy in every look, in the background; the newest request wins."""
        if self.pil is None or self.pts is None:
            return
        if self._busy:
            self._debounce.start()
            return
        self._busy = True
        ver, pts, rot, pil = self._ver, [list(p) for p in self.pts], self.rot, self.pil

        def work():
            out = {}
            try:
                small = pil.copy()
                small.thumbnail((700, 700))
                for look in self.LOOKS:
                    im = engine.straighten(small, pts, look)
                    if rot:
                        im = im.rotate(-rot, expand=True)
                    out[look] = im
            except Exception as e:
                winsys.log(f"fix alignment preview: {e}")
            self._done = (ver, out)
        threading.Thread(target=work, daemon=True).start()

    def _set(self, pts):
        if pts and self.pil is not None:
            self.pts = [list(p) for p in pts]
            self._changed()

    def _rotate(self, deg):
        self.rot = (self.rot + deg) % 360
        self._changed()

    def _set_look(self, look):
        self.look = look
        settings().setValue("scan_look", look)
        res = getattr(self, "_results", {}).get(look)
        if res is not None:
            q = _pil_to_qimage(res)
            self.prev.setPixmap(QPixmap.fromImage(q.scaled(self.PREV_W - 16, self.PREV_H - 16, Qt.KeepAspectRatio,
                                                           Qt.SmoothTransformation)))

    # ---- drawing and dragging
    def _origin(self):
        return QPointF((self.VIEW_W - self.img.width()) / 2, (self.VIEW_H - self.img.height()) / 2)

    def _to_view(self, q):
        o = self._origin()
        return QPointF(o.x() + q[0] * (self.img.width() - 1), o.y() + q[1] * (self.img.height() - 1))

    def _paint(self, _e):
        p = QPainter(self.view)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.view.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(theme.hexc("border")), 1))
        p.setBrush(QColor(theme.hexc("surface")))
        p.drawRoundedRect(r, 14, 14)
        if self.img is None:                              # still opening: a spinning wheel
            c = r.center()
            ring = QRectF(c.x() - 24, c.y() - 24, 48, 48)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(theme.hexc("border")), 5))
            p.drawEllipse(ring)
            p.setPen(QPen(QColor(theme.hexc("accent")), 5, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(ring, int(-self._angle * 16), 100 * 16)
            return
        o = self._origin()
        p.drawImage(o, self.img)
        poly = QPolygonF([self._to_view(q) for q in self.pts])
        outside = QPainterPath()
        outside.addRect(QRectF(o.x(), o.y(), self.img.width(), self.img.height()))
        inside = QPainterPath()
        inside.addPolygon(poly)
        inside.closeSubpath()
        p.fillPath(outside.subtracted(inside), QColor(0, 0, 0, 130))      # what will be cut away
        accent = QColor(theme.hexc("accent"))
        p.setPen(QPen(accent, 2.5))
        p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 28))
        p.drawPolygon(poly)
        for i in range(4):                                # edge middles: drag a whole side
            a, b = self._to_view(self.pts[i]), self._to_view(self.pts[(i + 1) % 4])
            m = (a + b) / 2
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.setBrush(accent)
            p.drawEllipse(m, 6, 6)
        for i, q in enumerate(self.pts):
            c = self._to_view(q)
            p.setPen(QPen(QColor("#ffffff"), 2.5))
            p.setBrush(QColor("#ffffff") if i == self.drag else accent)
            p.drawEllipse(c, 10, 10)
        if isinstance(self.drag, int):                    # magnifier: exactly where the corner is
            c = self._to_view(self.pts[self.drag])
            R, zoom = 58, 3.0
            at = QPointF(o.x() + R + 10, o.y() + R + 10)
            if c.x() < self.VIEW_W / 2 and c.y() < self.VIEW_H / 2:
                at = QPointF(self.VIEW_W - o.x() - R - 10, o.y() + R + 10)
            clip = QPainterPath()
            clip.addEllipse(at, R, R)
            p.save()
            p.setClipPath(clip)
            p.fillRect(QRectF(at.x() - R, at.y() - R, 2 * R, 2 * R), QColor("#000000"))
            src = QRectF(c.x() - o.x() - R / zoom, c.y() - o.y() - R / zoom, 2 * R / zoom, 2 * R / zoom)
            p.drawImage(QRectF(at.x() - R, at.y() - R, 2 * R, 2 * R), self.img, src)
            p.restore()
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor("#ffffff"), 3))
            p.drawEllipse(at, R, R)
            p.setPen(QPen(accent, 1.5))
            p.drawLine(QPointF(at.x() - 12, at.y()), QPointF(at.x() + 12, at.y()))
            p.drawLine(QPointF(at.x(), at.y() - 12), QPointF(at.x(), at.y() + 12))

    def _hit(self, pos):
        if self.img is None:
            return None
        for i, q in enumerate(self.pts):
            if (self._to_view(q) - pos).manhattanLength() < 26:
                return i
        for i in range(4):
            m = (self._to_view(self.pts[i]) + self._to_view(self.pts[(i + 1) % 4])) / 2
            if (m - pos).manhattanLength() < 20:
                return ("side", i)
        return None

    def _press(self, e):
        self.drag = self._hit(e.position())
        self._last = e.position()
        self.view.update()

    def _norm(self, pos):
        o = self._origin()
        return [min(1.0, max(0.0, (pos.x() - o.x()) / max(1, self.img.width() - 1))),
                min(1.0, max(0.0, (pos.y() - o.y()) / max(1, self.img.height() - 1)))]

    def _move(self, e):
        pos = e.position()
        if self.drag is None:
            self.view.setCursor(Qt.OpenHandCursor if self._hit(pos) is not None else Qt.ArrowCursor)
            return
        self.view.setCursor(Qt.ClosedHandCursor)
        if isinstance(self.drag, int):
            self.pts[self.drag] = [round(v, 4) for v in self._norm(pos)]
        else:                                             # a side: both of its corners move together
            i = self.drag[1]
            dx = (pos.x() - self._last.x()) / max(1, self.img.width() - 1)
            dy = (pos.y() - self._last.y()) / max(1, self.img.height() - 1)
            for k in (i, (i + 1) % 4):
                self.pts[k] = [round(min(1.0, max(0.0, self.pts[k][0] + dx)), 4),
                               round(min(1.0, max(0.0, self.pts[k][1] + dy)), 4)]
        self._last = pos
        self._changed()

    def _release(self, _e):
        self.drag = None
        self.view.update()

    def stop(self):
        self._poll.stop()

    def value(self):
        if self.pts is None:
            return ""
        return json.dumps({"corners": self.pts, "look": self.look, "rotate": self.rot})


class SignPlacer(QWidget):
    """Shows a page with your signature on it: drag it into place, drag its corner to size it,
    ◀ ▶ to choose the page. value() -> JSON for engine.pdf_sign."""
    VIEW_W = 470

    def __init__(self, paths):
        super().__init__()
        import pymupdf
        self.pdf = next(x for x in paths if engine.EXT_CATEGORY.get(engine.ext_of(x)) == "pdf")
        self.doc = pymupdf.open(self.pdf)
        self.pages = self.doc.page_count
        self.page_i = self.pages - 1                        # signatures usually go on the last page
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
        n = self.pages
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
        self.page_i = max(0, min(self.pages - 1, self.page_i + step))
        self.page_lbl.setText(tr("Page {i} of {n}", i=self.page_i + 1, n=self.pages))
        self.prev_b.setEnabled(self.page_i > 0)
        self.next_b.setEnabled(self.page_i < self.pages - 1)
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
        n = self.pages
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
        elif len(pages) == self.pages and len(pages) > 1:
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
        try:
            self.doc.close()                                # let go of the PDF
        except Exception:
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
        self.first = pymupdf.open()
        with pymupdf.open(self.pdf) as src:                 # only the first page is kept; the file is let go
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
    # Trim of one file: pick the part on the sound wave (and see the picture for a video), like Ringtone
    trim_one = op.id == "trim" and len(paths) == 1 and [n for n, _ in op.ask] == ["Start", "End"]
    if trim_one:
        tw = TrimWidget(paths[0], None, video=engine.EXT_CATEGORY.get(engine.ext_of(paths[0])) == "video")
        form.addRow(tw)
        edits["_clip"] = tw
        trims.append(tw)
    for name, default in op.ask:
        if trim_one:
            continue
        if default == "@trim":                          # waveform: pick the part and listen to it
            tw = TrimWidget(paths[0], engine.RINGTONE_MAX)
            form.addRow(tw)
            edits[name] = tw
            trims.append(tw)
            continue
        if default in ("@pages", "@sign", "@watermark", "@corners"):   # page grid / signature / watermark / corners
            try:
                w = (PageBoard(paths) if default == "@pages" else SignPlacer(paths) if default == "@sign"
                     else CornerPicker(paths[0]) if default == "@corners" else WatermarkEditor(paths))
            except Exception as e:
                message(APP, (tr("Couldn't open this picture") if default == "@corners" else tr("Couldn't open this PDF"))
                        + f"<br><small>{e}</small>")
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
    if any(isinstance(t, CornerPicker) for t in trims):
        dlg.adjustSize()
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        dlg.move(scr.availableGeometry().center() - QPoint(dlg.width() // 2, dlg.height() // 2))
    elif any(isinstance(t, (PageBoard, SignPlacer, WatermarkEditor)) for t in trims):
        dlg.resize(760, 560)
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        dlg.move(scr.availableGeometry().center() - QPoint(380, 280))
    elif trim_one and trims[0].screen_ is not None:
        dlg.resize(760, 620)
        scr = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        dlg.move(scr.availableGeometry().center() - QPoint(380, 310))
    else:
        dlg.move(QCursor.pos() - QPoint(310 if trims else 170, 60))
    dlg.activateWindow()
    ok = dlg.exec() == QDialog.Accepted
    for tw in trims:
        if tw is not None:
            tw.stop()
    if not ok:
        return None
    out = {k: (e.currentData() if isinstance(e, QComboBox) else e.value() if isinstance(e, (TrimWidget, CropPreview, PageBoard, SignPlacer, WatermarkEditor, CornerPicker)) else e.text())
           for k, e in edits.items()}
    if "_clip" in out:                                   # Trim keeps its Start / End (presets, chains, command line)
        a, b = out.pop("_clip").split("-")
        out["Start"], out["End"] = a, b
    return out


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
