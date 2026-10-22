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
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import (QEasingCurve, QObject, QPointF, QPropertyAnimation, QRectF, QRunnable,
                            QSettings, QSize, Qt, QThreadPool, QTimer, QUrl, Signal, QMimeData, QPoint)
from PySide6.QtGui import (QAction, QBrush, QColor, QCursor, QDesktopServices, QDrag, QFont, QFontMetrics,
                           QGuiApplication, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient)
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
VERSION = "1.1.0"

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
        ]

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
            job = jobproc.JobProcess(self.op.group, self.op.id, self.paths, self.params, engine.OUTPUT_DIR)
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
        roughly 56 px of arc; past that the labels shrink to fit."""
        n = len(self.ops)
        mid = max(self.R_MID + 14, 2 * (56 * n / (2 * math.pi)) - self.R_IN)
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
                rm = (r0 + r1) / 2
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
        self.target = str(outs[0]) if outs else None
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
# Float window — pinned, always on top. Drag it anywhere; drag the grip to drop the file elsewhere.
# ============================================================================
class FloatWindow(QWidget):
    closed = Signal()
    PAD = 12
    BAR = 34          # bottom bar with name + drag-out grip
    CLOSE_R = 11

    def __init__(self, path):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.path = path
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.src = None
        try:
            if engine.EXT_CATEGORY.get(engine.ext_of(path)) == "image":
                img = engine.open_image(path)
                img.thumbnail((1200, 1200))
                q = QImage(img.convert("RGBA").tobytes("raw", "RGBA"), img.width, img.height,
                           img.width * 4, QImage.Format_RGBA8888)
                self.src = QPixmap.fromImage(q.copy())
        except Exception:
            self.src = None
        self.is_icon = self.src is None
        if self.is_icon:
            from PySide6.QtCore import QFileInfo
            from PySide6.QtWidgets import QFileIconProvider
            self.src = QFileIconProvider().icon(QFileInfo(path)).pixmap(128, 128)
        self.side = 120 if self.is_icon else 300       # longest side of the preview, Ctrl+scroll changes it
        self.hover = None
        self._move_from = None
        self._grip_press = None
        self._relayout()
        self.move(QCursor.pos() - QPoint(self.width() // 2, 40))
        self.setToolTip(f"{path}\n" + tr("Drag to move · drag ⠿ to drop the file · double-click to open · scroll to resize"))

    # geometry
    def _relayout(self):
        pm = self.src.scaled(self.side, self.side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.pix = pm
        w = max(pm.width() + 2 * self.PAD, 200)
        h = pm.height() + 2 * self.PAD + self.BAR
        self.setFixedSize(w, h)
        self.update()

    def _close_center(self):
        return QPointF(self.width() - 18, 18)

    def _grip_rect(self):
        return QRectF(self.width() - self.PAD - 30, self.height() - self.BAR + 2, 30, self.BAR - 8)

    def _hit(self, pos):
        c = self._close_center()
        if (pos.x() - c.x()) ** 2 + (pos.y() - c.y()) ** 2 <= (self.CLOSE_R + 4) ** 2:
            return "close"
        if self._grip_rect().contains(pos):
            return "grip"
        return "body"

    # paint
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(ACCENT if self.hover else C("line"), 1.2))
        p.setBrush(C("panel"))
        p.drawRoundedRect(r, 14, 14)
        p.drawPixmap((self.width() - self.pix.width()) // 2, self.PAD, self.pix)
        # name
        p.setPen(C("text"))
        f = QFont(i18n.ui_font(), 9)
        p.setFont(f)
        name_r = QRectF(self.PAD, self.height() - self.BAR, self.width() - 2 * self.PAD - 36, self.BAR - 6)
        p.drawText(name_r, Qt.AlignVCenter | Qt.AlignLeft,
                   QFontMetrics(f).elidedText(Path(self.path).name, Qt.ElideMiddle, int(name_r.width())))
        # grip (drag the file out from here)
        g = self._grip_rect()
        p.setPen(Qt.NoPen)
        p.setBrush(ACCENT if self.hover == "grip" else C("grip"))
        p.drawRoundedRect(g, 7, 7)
        p.setBrush(ON_ACCENT if self.hover == "grip" else C("text"))
        for i in range(3):
            for j in range(2):
                p.drawEllipse(QPointF(g.center().x() - 3 + j * 6, g.center().y() - 5 + i * 5), 1.6, 1.6)
        # close button — always visible
        c = self._close_center()
        p.setBrush(C("danger") if self.hover == "close" else C("close"))
        p.setPen(QPen(QColor(255, 255, 255, 60), 1))
        p.drawEllipse(c, self.CLOSE_R, self.CLOSE_R)
        pen = QPen(QColor("#ffffff"), 2)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        d = 4.2
        p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
        p.drawLine(QPointF(c.x() + d, c.y() - d), QPointF(c.x() - d, c.y() + d))

    # mouse
    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self._menu(e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        hit = self._hit(e.position())
        if hit == "close":
            self.close()
        elif hit == "grip":
            self._grip_press = e.position()
        else:
            self._move_from = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        if self._move_from is not None:
            self.move(e.globalPosition().toPoint() - self._move_from)
            return
        if self._grip_press is not None:
            if (e.position() - self._grip_press).manhattanLength() > 6:
                self._grip_press = None
                self._drag_out()
            return
        h = self._hit(e.position())
        if h != self.hover:
            self.hover = h
            self.setCursor({"close": Qt.PointingHandCursor, "grip": Qt.OpenHandCursor}.get(h, Qt.SizeAllCursor))
            self.update()

    def mouseReleaseEvent(self, e):
        self._move_from = None
        self._grip_press = None

    def leaveEvent(self, e):
        self.hover = None
        self.update()

    def mouseDoubleClickEvent(self, e):
        if self._hit(e.position()) == "body":
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))

    def wheelEvent(self, e):
        if True:   # scroll wheel resizes the float
            step = 30 if e.angleDelta().y() > 0 else -30
            center = self.frameGeometry().center()
            self.side = max(80, min(900, self.side + step))
            self._relayout()
            self.move(center - QPoint(self.width() // 2, self.height() // 2))

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.close()

    def _drag_out(self):
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(self.path)])
        drag = QDrag(self)
        drag.setMimeData(md)
        drag.setPixmap(self.pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        drag.exec(Qt.CopyAction | Qt.MoveAction | Qt.LinkAction, Qt.CopyAction)

    def _menu(self, at):
        m = QMenu(self)
        m.addAction(tr("Open"), lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.path)))
        m.addAction(tr("Show in Explorer"), lambda: winsys.reveal(self.path))
        m.addAction(tr("Copy path"), lambda: QGuiApplication.clipboard().setText(str(Path(self.path))))
        m.addSeparator()
        m.addAction(tr("Close"), self.close)
        m.exec(at)

    def closeEvent(self, e):
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
    for name, default in op.ask:
        ed = QLineEdit(default)
        if name == "Password":
            ed.setEchoMode(QLineEdit.Password)
        if name in ("Start", "End", "At time"):
            ed.setPlaceholderText(tr("seconds, m:ss or h:mm:ss"))
            ed.setLayoutDirection(Qt.LeftToRight)
        form.addRow(tr(name), ed)
        edits[name] = ed
    lay.addLayout(form)
    bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    bb.button(QDialogButtonBox.Ok).setText(tr("Apply"))
    bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
    bb.button(QDialogButtonBox.Ok).setDefault(True)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    lay.addWidget(bb)
    dlg.setMinimumWidth(340)
    dlg.move(QCursor.pos() - QPoint(170, 60))
    dlg.activateWindow()
    if dlg.exec() != QDialog.Accepted:
        return None
    return {k: e.text() for k, e in edits.items()}


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
        self.app.watcher.refresh_settings()
        engine.OUTPUT_DIR = self.out.text().strip() or None
        s.setValue("language", self.lang.currentData())
        s.setValue("theme", self.theme_box.currentData())
        try:
            winsys.set_startup(self.startup.isChecked())
            winsys.set_context_menu(self.menu.isChecked())
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
        self.hook = winsys.WheelHook(self._on_wheel, self._swallow_wheel)

    def refresh_settings(self):
        s = settings()
        self.scroll_enabled = s.value("scroll", "true") == "true"
        self.any_drag = int(s.value("detect_any", 0)) == 1

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
        self.floats = []
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

    def _build_tray_menu(self):
        self.tray.setToolTip(tr("{app} — drag a file, tap {key}", app=APP, key=tr(mode_keys()["convert"])))
        menu = QMenu()
        self._first_action = menu.addAction(tr("Convert files…"), self.pick_files)
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
                    dlg = CropResizeDialog(p, DIALOG_CSS, app_icon())
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
        if op.group == "action":
            try:
                op.fn(paths, params)
            except Exception as e:
                self.toast.show_msg(tr("Couldn't do that"), str(e), "err", 6000)
            return
        self._start(op, paths, params)

    def _start(self, op, paths, params):
        name = Path(paths[0]).name if len(paths) == 1 else tr("{n} files", n=len(paths))
        w = Worker(op, paths, params)
        cancel = lambda w=w: self._cancel_job(w)
        if op.group == "convert":
            w.card = self.toast.show_busy(tr("Converting to {fmt}…", fmt=tr(op.label)), name, cancel)
        else:
            w.card = self.toast.show_busy(tr(op.label).rstrip("…") + "…", name, cancel)
        w.setAutoDelete(False)
        self.running.add(w)                       # keep Python refs alive until done
        w.sig.done.connect(self._done, Qt.QueuedConnection)
        self.pool.start(w)

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
            target.show_msg(tr("{what} failed", what=tr(op.label).rstrip("…")), err, "err", 8000)
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
            if msg.get("paths"):
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
                winsys.set_context_menu(True)
            except Exception:
                pass
        QTimer.singleShot(500, app.show_help)
    if paths:
        app.queue_paths(paths)
    elif "--tray" not in flags and not first_run:
        app.tray.showMessage(APP, tr("Running in the tray. Drag a file and tap {key}.", key=tr(mode_keys()["convert"])),
                             app_icon(), 3000)
    return qapp.exec()


if __name__ == "__main__":
    sys.exit(main())
