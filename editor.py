"""Crop & Resize editor: live preview, draggable crop box, aspect presets, output size, rotate/flip."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QImage, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QPushButton, QSizePolicy, QSpinBox, QToolButton, QVBoxLayout, QWidget)

import engine
from i18n import tr

ACCENT = QColor("#ff8a00")
HANDLE = 9          # handle half-size in px
MIN_CROP = 8        # in image pixels

ASPECTS = [("Free", None), ("Original", "orig"), ("1:1", 1.0), ("4:3", 4 / 3), ("3:2", 3 / 2),
           ("16:9", 16 / 9), ("9:16", 9 / 16), ("4:5", 4 / 5)]


def pil_to_qimage(img) -> QImage:
    img = img.convert("RGBA")
    q = QImage(img.tobytes("raw", "RGBA"), img.width, img.height, img.width * 4, QImage.Format_RGBA8888)
    return q.copy()


class CropCanvas(QWidget):
    """Shows the image fitted to the widget; crop box is kept in IMAGE coordinates."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.setMinimumSize(520, 380)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.img: QImage | None = None
        self.full = QSize(1, 1)        # full-resolution size of the (rotated) image
        self.crop = QRectF()           # in full-res image pixels
        self.aspect: float | None = None
        self._drag = None              # (mode, start_mouse_img, start_crop)

    # ---------------------------------------------------------- data
    def set_image(self, qimg: QImage, full: QSize):
        self.img = qimg
        self.full = full
        self.crop = QRectF(0, 0, full.width(), full.height())
        self.apply_aspect()
        self.update()

    def set_aspect(self, aspect):
        self.aspect = aspect
        self.apply_aspect()

    def apply_aspect(self):
        if not self.aspect:
            self.changed.emit()
            self.update()
            return
        W, H = self.full.width(), self.full.height()
        c = self.crop.center()
        w = self.crop.width()
        h = w / self.aspect
        if h > self.crop.height():
            h = self.crop.height()
            w = h * self.aspect
        # if the box became tiny, grow it to the largest fitting box
        if w < W * 0.25 and h < H * 0.25:
            w, h = W, W / self.aspect
            if h > H:
                h, w = H, H * self.aspect
        r = QRectF(0, 0, w, h)
        r.moveCenter(c)
        self.crop = self._clamp_move(r)
        self.changed.emit()
        self.update()

    def set_crop(self, r: QRectF):
        self.crop = self._clamp_move(r)
        self.changed.emit()
        self.update()

    # ---------------------------------------------------------- geometry
    def _view(self) -> QRectF:
        """Rect where the image is drawn, in widget coords."""
        if not self.img:
            return QRectF()
        pad = 18
        aw, ah = self.width() - 2 * pad, self.height() - 2 * pad
        W, H = self.full.width(), self.full.height()
        s = min(aw / W, ah / H)
        w, h = W * s, H * s
        return QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)

    def _scale(self):
        v = self._view()
        return v.width() / self.full.width() if self.full.width() else 1

    def to_widget(self, r: QRectF) -> QRectF:
        v, s = self._view(), self._scale()
        return QRectF(v.x() + r.x() * s, v.y() + r.y() * s, r.width() * s, r.height() * s)

    def to_image(self, p: QPointF) -> QPointF:
        v, s = self._view(), self._scale()
        return QPointF((p.x() - v.x()) / s, (p.y() - v.y()) / s)

    def _handles(self):
        r = self.to_widget(self.crop)
        cx, cy = r.center().x(), r.center().y()
        return {"tl": QPointF(r.left(), r.top()), "t": QPointF(cx, r.top()), "tr": QPointF(r.right(), r.top()),
                "r": QPointF(r.right(), cy), "br": QPointF(r.right(), r.bottom()), "b": QPointF(cx, r.bottom()),
                "bl": QPointF(r.left(), r.bottom()), "l": QPointF(r.left(), cy)}

    def _hit(self, pos: QPointF):
        for k, pt in self._handles().items():
            if abs(pos.x() - pt.x()) <= HANDLE + 3 and abs(pos.y() - pt.y()) <= HANDLE + 3:
                return k
        if self.to_widget(self.crop).contains(pos):
            return "move"
        if self._view().contains(pos):
            return "new"
        return None

    CURSORS = {"tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor, "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
               "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor, "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
               "move": Qt.SizeAllCursor, "new": Qt.CrossCursor}

    def _clamp_move(self, r: QRectF) -> QRectF:
        W, H = self.full.width(), self.full.height()
        w, h = min(r.width(), W), min(r.height(), H)
        x = min(max(r.x(), 0), W - w)
        y = min(max(r.y(), 0), H - h)
        return QRectF(x, y, w, h)

    # ---------------------------------------------------------- mouse
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or not self.img:
            return
        mode = self._hit(e.position())
        if not mode:
            return
        start = self.to_image(e.position())
        if mode == "new":
            self.crop = QRectF(start, start)
            mode = "br"
        self._drag = (mode, start, QRectF(self.crop))

    def mouseMoveEvent(self, e):
        if not self._drag:
            self.setCursor(self.CURSORS.get(self._hit(e.position()), Qt.ArrowCursor))
            return
        mode, start, c0 = self._drag
        p = self.to_image(e.position())
        W, H = self.full.width(), self.full.height()
        if mode == "move":
            r = QRectF(c0)
            r.translate(p.x() - start.x(), p.y() - start.y())
            self.crop = self._clamp_move(r)
        else:
            px, py = min(max(p.x(), 0), W), min(max(p.y(), 0), H)
            l, t, r_, b = c0.left(), c0.top(), c0.right(), c0.bottom()
            if "l" in mode: l = min(px, r_ - MIN_CROP)
            if "r" in mode: r_ = max(px, l + MIN_CROP)
            if "t" in mode: t = min(py, b - MIN_CROP)
            if "b" in mode: b = max(py, t + MIN_CROP)
            if self.aspect:
                w, h = r_ - l, b - t
                if mode in ("t", "b"):
                    w = h * self.aspect
                    cx = (c0.left() + c0.right()) / 2
                    l, r_ = cx - w / 2, cx + w / 2
                elif mode in ("l", "r"):
                    h = w / self.aspect
                    cy = (c0.top() + c0.bottom()) / 2
                    t, b = cy - h / 2, cy + h / 2
                else:   # corners: follow the larger movement
                    if w / self.aspect > h:
                        h = w / self.aspect
                    else:
                        w = h * self.aspect
                    if "l" in mode: l = r_ - w
                    else: r_ = l + w
                    if "t" in mode: t = b - h
                    else: b = t + h
                # keep inside image by shrinking
                if l < 0 or r_ > W or t < 0 or b > H:
                    return
            self.crop = QRectF(l, t, r_ - l, b - t)
        self.changed.emit()
        self.update()

    def mouseReleaseEvent(self, e):
        self._drag = None
        if self.crop.width() < MIN_CROP or self.crop.height() < MIN_CROP:
            self.crop = QRectF(0, 0, self.full.width(), self.full.height())
            self.apply_aspect()
        self.update()

    def mouseDoubleClickEvent(self, e):
        self.crop = QRectF(0, 0, self.full.width(), self.full.height())
        self.apply_aspect()

    # ---------------------------------------------------------- paint
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#141416"))
        if not self.img:
            return
        v = self._view()
        # checkerboard behind transparent images
        tile = 10
        p.save()
        p.setClipRect(v)
        for yy in range(int(v.top()), int(v.bottom()) + tile, tile):
            for xx in range(int(v.left()), int(v.right()) + tile, tile):
                if ((xx - int(v.left())) // tile + (yy - int(v.top())) // tile) % 2:
                    p.fillRect(xx, yy, tile, tile, QColor("#2a2a2d"))
                else:
                    p.fillRect(xx, yy, tile, tile, QColor("#222225"))
        p.restore()
        p.drawImage(v, self.img)
        c = self.to_widget(self.crop)
        # shade outside
        shade = QPainterPath()
        shade.addRect(v)
        inner = QPainterPath()
        inner.addRect(c)
        p.fillPath(shade.subtracted(inner), QColor(0, 0, 0, 150))
        # thirds
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        for i in (1, 2):
            x = c.left() + c.width() * i / 3
            y = c.top() + c.height() * i / 3
            p.drawLine(QPointF(x, c.top()), QPointF(x, c.bottom()))
            p.drawLine(QPointF(c.left(), y), QPointF(c.right(), y))
        p.setPen(QPen(QColor("#ffffff"), 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawRect(c)
        # handles
        p.setPen(QPen(QColor("#1c1c1e"), 1))
        p.setBrush(ACCENT)
        for k, pt in self._handles().items():
            s = HANDLE if len(k) == 2 else HANDLE - 2
            p.drawRoundedRect(QRectF(pt.x() - s / 2 - 2, pt.y() - s / 2 - 2, s + 4, s + 4), 3, 3)


class CropResizeDialog(QDialog):
    def __init__(self, path: str, css: str, icon=None):
        super().__init__(None, Qt.Window | Qt.WindowStaysOnTopHint)
        self.path = path
        self.setWindowTitle(f"DragWheel — {tr('Crop & Resize')} — {Path(path).name}")
        if icon:
            self.setWindowIcon(icon)
        self.setStyleSheet(css + EDITOR_CSS)
        self.resize(1060, 700)

        src = engine.open_image(path)
        self.src_size = src.size
        prev = src.copy()
        prev.thumbnail((1800, 1800))
        self.base_preview = pil_to_qimage(prev)
        self.rotate = 0
        self.flip_h = False
        self.flip_v = False
        self._sync = False

        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)
        self.canvas = CropCanvas()
        self.canvas.changed.connect(self._crop_changed)
        root.addWidget(self.canvas, 1)

        side = QFrame()
        side.setObjectName("side")
        side.setFixedWidth(300)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 14, 14, 14)
        sv.setSpacing(10)
        root.addWidget(side)

        # --- aspect
        sv.addWidget(self._title(tr("Aspect ratio")))
        grid = QGridLayout()
        grid.setSpacing(6)
        self.aspect_group = QButtonGroup(self)
        for i, (name, val) in enumerate(ASPECTS):
            b = QToolButton()
            b.setText(tr(name))
            b.setCheckable(True)
            b.setObjectName("chip")
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, v=val: self._set_aspect(v))
            self.aspect_group.addButton(b, i)
            grid.addWidget(b, i // 4, i % 4)
        self.aspect_group.button(0).setChecked(True)
        sv.addLayout(grid)

        # --- rotate / flip
        sv.addWidget(self._title(tr("Rotate & flip")))
        rr = QHBoxLayout()
        rr.setSpacing(6)
        for txt, tip, fn in (("⟲", tr("Rotate left"), lambda: self._rotate(-90)),
                             ("⟳", tr("Rotate right"), lambda: self._rotate(90)),
                             ("⇋", tr("Flip horizontal"), self._flip_h),
                             ("⇵", tr("Flip vertical"), self._flip_v)):
            b = QToolButton()
            b.setText(txt)
            b.setToolTip(tip)
            b.setObjectName("icon")
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(fn)
            rr.addWidget(b)
        sv.addLayout(rr)

        # --- crop readout
        self.crop_lbl = QLabel()
        self.crop_lbl.setObjectName("dim")
        sv.addWidget(self._title(tr("Crop")))
        sv.addWidget(self.crop_lbl)

        # --- output size
        sv.addWidget(self._title(tr("Output size")))
        sz = QGridLayout()
        sz.setHorizontalSpacing(10)
        sz.setVerticalSpacing(8)
        sz.setColumnStretch(1, 1)
        self.w_spin = QSpinBox()
        self.h_spin = QSpinBox()
        for s in (self.w_spin, self.h_spin):
            s.setRange(1, 30000)
            s.setSuffix(" px")
            s.setMinimumHeight(38)
            s.setMinimumWidth(150)
            s.setAlignment(Qt.AlignCenter)
            s.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.w_spin.valueChanged.connect(lambda v: self._size_edited("w"))
        self.h_spin.valueChanged.connect(lambda v: self._size_edited("h"))
        sz.addWidget(QLabel(tr("Width")), 0, 0)
        sz.addWidget(self.w_spin, 0, 1)
        sz.addWidget(QLabel(tr("Height")), 1, 0)
        sz.addWidget(self.h_spin, 1, 1)
        sv.addLayout(sz)
        self.lock = QCheckBox(tr("Keep proportions"))
        self.lock.setChecked(True)
        sv.addWidget(self.lock)
        pr = QHBoxLayout()
        pr.setSpacing(6)
        for pct in (100, 75, 50, 25):
            b = QToolButton()
            b.setText(f"{pct}%")
            b.setObjectName("chip")
            b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, v=pct: self._percent(v))
            pr.addWidget(b)
        sv.addLayout(pr)

        # --- format
        sv.addWidget(self._title(tr("Save as")))
        self.fmt = QComboBox()
        ext = engine.ext_of(path)
        self.fmt.addItem(tr("Same as original") + f" ({ext.upper()})", "")
        for f in ("png", "jpg", "webp", "avif", "tiff", "bmp"):
            if f != ext:
                self.fmt.addItem(f.upper(), f)
        sv.addWidget(self.fmt)

        sv.addStretch(1)
        reset = QPushButton(tr("Reset"))
        reset.clicked.connect(self._reset)
        sv.addWidget(reset)
        btns = QHBoxLayout()
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)
        save = QPushButton(tr("Save copy"))
        save.setDefault(True)
        save.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(save, 1)
        sv.addLayout(btns)
        hint = QLabel(tr("Drag the box or its corners. Double-click the image to reset the crop."))
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        sv.addWidget(hint)

        self._rebuild_preview()

    def _title(self, text):
        l = QLabel(text)
        l.setObjectName("section")
        return l

    # ---------------------------------------------------------- state
    def _rotated_full(self) -> QSize:
        w, h = self.src_size
        return QSize(h, w) if self.rotate % 180 else QSize(w, h)

    def _rebuild_preview(self):
        t = QTransform().rotate(self.rotate)
        img = self.base_preview.transformed(t, Qt.SmoothTransformation)
        img = img.mirrored(self.flip_h, self.flip_v)
        self.canvas.set_image(img, self._rotated_full())
        self._apply_aspect_choice()

    def _apply_aspect_choice(self):
        idx = self.aspect_group.checkedId()
        val = ASPECTS[idx][1] if idx >= 0 else None
        self._set_aspect(val)

    def _set_aspect(self, val):
        if val == "orig":
            f = self._rotated_full()
            val = f.width() / f.height()
        self.canvas.set_aspect(val)

    def _rotate(self, deg):
        self.rotate = (self.rotate + deg) % 360
        self._rebuild_preview()

    def _flip_h(self):
        self.flip_h = not self.flip_h
        self._rebuild_preview()

    def _flip_v(self):
        self.flip_v = not self.flip_v
        self._rebuild_preview()

    def _reset(self):
        self.rotate, self.flip_h, self.flip_v = 0, False, False
        self.aspect_group.button(0).setChecked(True)
        self._rebuild_preview()

    def _crop_changed(self):
        c = self.canvas.crop
        w, h = max(1, round(c.width())), max(1, round(c.height()))
        self.crop_lbl.setText(f"{w} × {h} px   ·   x {round(c.x())}, y {round(c.y())}")
        self._sync = True
        self.w_spin.setValue(w)
        self.h_spin.setValue(h)
        self._sync = False

    def _size_edited(self, which):
        if self._sync or not self.lock.isChecked():
            return
        c = self.canvas.crop
        ratio = c.width() / c.height() if c.height() else 1
        self._sync = True
        if which == "w":
            self.h_spin.setValue(max(1, round(self.w_spin.value() / ratio)))
        else:
            self.w_spin.setValue(max(1, round(self.h_spin.value() * ratio)))
        self._sync = False

    def _percent(self, pct):
        c = self.canvas.crop
        self._sync = True
        self.w_spin.setValue(max(1, round(c.width() * pct / 100)))
        self.h_spin.setValue(max(1, round(c.height() * pct / 100)))
        self._sync = False

    def params(self) -> dict:
        c = self.canvas.crop
        return {"rotate": self.rotate, "flip_h": self.flip_h, "flip_v": self.flip_v,
                "box": (c.left(), c.top(), c.right(), c.bottom()),
                "size": (self.w_spin.value(), self.h_spin.value()),
                "format": self.fmt.currentData()}


EDITOR_CSS = """
QFrame#side{background:#232326;border-radius:12px}
QLabel#section{color:#a1a1a6;font:600 8.5pt 'Segoe UI';padding-top:4px}
QLabel#dim{color:#8e8e93;font:8.5pt 'Segoe UI'}
QToolButton#chip,QToolButton#icon{background:#2c2c2e;color:#f5f5f7;border:1px solid #3a3a3c;border-radius:6px;
  padding:5px 4px;font:600 9pt 'Segoe UI'}
QToolButton#icon{font:13pt 'Segoe UI Symbol'}
QToolButton#chip:hover,QToolButton#icon:hover{background:#3a3a3c}
QToolButton#chip:checked{background:#ff8a00;color:#1c1c1e;border-color:#ff8a00}
QSpinBox{background:#2c2c2e;color:#f5f5f7;border:1px solid #3a3a3c;border-radius:8px;padding:0 10px;min-height:38px;font:600 11pt 'Segoe UI'}
QSpinBox:focus{border-color:#ff8a00}
QSpinBox QLineEdit{padding:0;margin:0;border:none;background:transparent;min-height:30px}
QSpinBox::up-button,QSpinBox::down-button{width:0;border:none}
"""
