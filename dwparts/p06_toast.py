"""DragWheel: Toast

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


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


_WAV_CACHE = {}


def _play_wav(name, volume, pack=None) -> bool:
    """Windows: play a short DragWheel sound without Qt's audio engine (which can stall the app for seconds
    when sounds are started and stopped quickly, e.g. sweeping over the wheel's slices). The volume is baked
    into a small copy of the sound, made once per volume level."""
    if not winsys.IS_WIN:
        return False
    try:
        import tempfile
        import wave
        import winsound
        import array
        vol = max(0, min(100, int(volume)))
        pack = pack or sound_pack()
        key = (name, vol, pack)
        path = _WAV_CACHE.get(key)
        if path is None or not os.path.exists(path):
            folder = Path(tempfile.gettempdir()) / "DragWheel sounds"
            folder.mkdir(parents=True, exist_ok=True)
            path = str(folder / f"{name}-{pack}-{vol}.wav")
            with wave.open(sound_file(name, pack), "rb") as src:
                params = src.getparams()
                frames = src.readframes(src.getnframes())
            if params.sampwidth == 2:
                a = array.array("h", frames)
                k = vol / 100
                a = array.array("h", (int(x * k) for x in a))
                frames = a.tobytes()
            with wave.open(path, "wb") as out:
                out.setparams(params)
                out.writeframes(frames)
            _WAV_CACHE[key] = path
        if vol == 0:
            return True
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        return True
    except Exception as e:
        winsys.log(f"sound {name}: {e}")
        return False


SOUND_PACKS = [("classic", "Classic"), ("soft", "Soft"), ("glass", "Glass"), ("bubble", "Bubble"),
               ("mechanical", "Mechanical"), ("retro", "Retro"), ("velvet", "Velvet"), ("crystal", "Crystal"),
               ("pulse", "Pulse")]


def sound_pack() -> str:
    v = settings().value("sound_pack", "classic")
    v = {"steam": "velvet", "playstation": "crystal", "xbox": "pulse"}.get(v, v)    # names in early 1.2.1 builds
    return v if v in dict(SOUND_PACKS) else "classic"


def sound_file(name, pack=None) -> str:
    """The .wav for 'tick', 'select', 'open' or 'close' in the chosen sound style."""
    pack = pack or sound_pack()
    if pack != "classic":
        f = asset(f"sounds/{name}-{pack}.wav")
        if os.path.exists(f):
            return f
    return asset(f"sounds/{name}.wav")


def _tick_effect(name="tick"):
    """Qt's player for a wheel sound (only used where Windows' own player isn't available)."""
    from PySide6.QtMultimedia import QSoundEffect
    key = (name, sound_pack())
    if key not in _EFFECTS:
        fx = QSoundEffect()
        fx.setSource(QUrl.fromLocalFile(sound_file(name)))
        _EFFECTS[key] = fx
    return _EFFECTS[key]


def play_wheel_sound(name):
    """The soft rising sound when the wheel opens and the falling one when it closes (same switch and volume as the tick)."""
    if settings().value("tick_sound", "true") != "true":
        return
    if name == "close" and time.monotonic() - _LAST_SELECT < 0.8:
        return                                   # choosing a slice already made its own sound
    vol = int(int(settings().value("tick_volume", 70)) * 0.8)
    if _play_wav(name, vol):
        return
    try:
        fx = _tick_effect(name)
        fx.setVolume(max(0, min(100, vol)) / 100)
        fx.play()
    except Exception as e:
        winsys.log(f"{name} sound: {e}")


def play_select():
    """The deeper "press" when you choose a slice (like the iPod's centre button). Same switch and volume as the tick."""
    global _LAST_SELECT
    _LAST_SELECT = time.monotonic()
    if settings().value("tick_sound", "true") != "true":
        return
    vol = int(settings().value("tick_volume", 70))
    if _play_wav("select", vol):
        return
    try:
        fx = _tick_effect("select")
        fx.setVolume(max(0, min(100, vol)) / 100)
        fx.play()
    except Exception as e:
        winsys.log(f"select sound: {e}")


def play_tick(force=False):
    """The click when the highlight moves to another slice (Settings → Everyday, with its own volume)."""
    if settings().value("tick_sound", "true") != "true" and not force:
        return
    vol = int(settings().value("tick_volume", 70))
    if _play_wav("tick", vol):
        return
    try:
        fx = _tick_effect()
        fx.setVolume(max(0, min(100, vol)) / 100)
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
        self._is_action = False
        self.undo_btn.setText(tr("Undo"))
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

    def set_action(self, label, fn):
        """A button of its own on the card (in the Undo button's place); clicking it runs fn and closes the card."""
        self.undo_btn.setText(label)
        self.on_undo = fn
        self._is_action = True
        self.undo_btn.setVisible(True)
        if self.timer.isActive():
            self.timer.start(max(self.timer.remainingTime(), 12000))
        self._place()
        return self

    def _undo(self):
        fn, self.on_undo = self.on_undo, None
        if fn and getattr(self, "_is_action", False):     # set_action's button, not Undo
            self._is_action = False
            self.undo_btn.setText(tr("Undo"))
            fn()
            self.close_card()
            return
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
