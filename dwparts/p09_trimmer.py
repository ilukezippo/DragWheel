"""DragWheel: Waveform trimmer (Ringtone…): pick the part on the sound wave and listen before saving

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


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
        self.max_len = max_len or float("inf")   # None: no limit (Trim)
        self._drag = None                    # ("a" | "b" | "move" | "new", anchor seconds, a, b)

    def set_data(self, peaks, dur):
        self.peaks, self.dur = peaks, max(dur, 0.1)
        self.v0, self.v1 = 0.0, self.dur
        # Ringtone starts with 30 s; Trim (no limit) with the whole file
        self.a, self.b = 0.0, (self.dur if self.max_len == float("inf") else min(30.0, self.dur, self.max_len))
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


class VideoPreview(QWidget):
    """The video's picture for Trim: the frame at the edge you're dragging, or the part playing."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(560, 300)
        self.img = None

    def set_frame(self, frame):
        try:
            img = frame.toImage()
        except Exception:
            return
        if not img.isNull():
            self.img = img
            self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor(0, 0, 0))
        if self.img is None:
            p.setPen(theme.color("dim"))
            p.drawText(self.rect(), Qt.AlignCenter, tr("Loading…"))
            return
        s = min(self.width() / self.img.width(), self.height() / self.img.height())
        w, h = self.img.width() * s, self.img.height() * s
        p.drawImage(QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h), self.img)


class TrimWidget(QWidget):
    """Waveform + play button + start/end boxes (+ the picture for videos). value() -> 'start-end' in seconds.
    max_len None = any length (Trim)."""

    def __init__(self, path, max_len=40.0, video=False):
        super().__init__()
        self.path = path
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.screen_ = VideoPreview() if video else None
        if self.screen_ is not None:
            lay.addWidget(self.screen_, 1)
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
        hint = QLabel(tr("Drag the orange edges or the part itself · scroll to zoom · up to {n} seconds", n=int(max_len))
                      if max_len else tr("Drag the orange edges or the part itself · scroll to zoom"))
        hint.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        lay.addWidget(hint)
        self.view.changed.connect(self._sync)
        self._ab = (None, None)
        self._show_at = None                         # where the picture should go while you drag
        self._frame_timer = QTimer(self, singleShot=True, interval=60, timeout=self._show_frame)
        self.view.seek.connect(lambda t: self._play_from(t) if self._playing() else None)
        self.player = None
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            if self.screen_ is not None:
                from PySide6.QtMultimedia import QVideoSink
                self.sink = QVideoSink(self)
                self.sink.videoFrameChanged.connect(self.screen_.set_frame)
                self.player.setVideoOutput(self.sink)
            self.player.setSource(QUrl.fromLocalFile(path))
            if self.screen_ is not None:
                self.player.pause()                  # loads the first picture without playing
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
        a, b = self.view.a, self.view.b
        if self.screen_ is not None and self.player is not None and not self._playing():
            self._show_at = b if (a == self._ab[0] and b != self._ab[1]) else a    # the edge that moved
            self._frame_timer.start()
        self._ab = (a, b)
        self.start_ed.setText(_fmt_secs(self.view.a))
        self.end_ed.setText(_fmt_secs(self.view.b))
        self.len_lbl.setText(tr("{s} seconds", s=f"{self.view.b - self.view.a:.1f}"))

    def _show_frame(self):
        if self._show_at is None or self.player is None or self._playing():
            return
        self.player.setPosition(int(self._show_at * 1000))
        self.player.pause()

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
            self._label()
        else:
            self._play_from(self.view.a)

    def _pos(self, ms):
        if not self._playing():
            return
        t = ms / 1000
        if t >= self.view.b or t < self.view.a - 0.5:
            self.player.pause()
            self.view.head = None
            self._show_at = self.view.a
            self._frame_timer.start()                    # back to the first picture of the part
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
