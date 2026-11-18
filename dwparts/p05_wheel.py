"""DragWheel: The wheel

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


# ============================================================================
# The wheel
# ============================================================================
WHEEL_ANIMS = [("bloom", "Bloom"), ("circle", "Circle"), ("fade", "Fade"), ("spin", "Spin"), ("zoom", "Zoom"),
               ("pop", "Pop"), ("drop", "Drop"), ("rise", "Rise"), ("flip", "Flip"), ("swirl", "Swirl"),
               ("none", "None")]


def wheel_anim() -> str:
    v = settings().value("wheel_anim", "bloom")
    return v if v in dict(WHEEL_ANIMS) else "bloom"


def wheel_anim_close() -> str:
    """How the wheel goes away: the opening style, unless you chose another one."""
    if settings().value("anim_same", "true") == "true":
        return wheel_anim()
    v = settings().value("wheel_anim_close", "fade")
    return v if v in dict(WHEEL_ANIMS) else "fade"


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
    PILL_H = 40

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
        t0 = time.monotonic()
        self.mode = mode
        self.ops = self.app.ops_for(mode, self.paths) if self.paths else []
        if time.monotonic() - t0 > 0.3:
            winsys.log(f"wheel: switching to {mode} took {time.monotonic() - t0:.1f}s")
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
        if self.isVisible() and not self._closing:
            self._style = wheel_anim_close()
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
            pressed = qt_key_name(k)
            for m, kname in keys.items():
                vks = winsys.combo_vks(kname)
                if pressed and vks and pressed in kname.split("+") and all(winsys.key_down(v) for v in vks):
                    if m == self.mode:
                        self.dismiss()                 # the same key again closes the wheel
                    else:
                        play_tick()
                        self.set_mode(m)
                    break

    def focusOutEvent(self, e):
        if self.click_mode:
            QTimer.singleShot(120, self, lambda: (not self.isActiveWindow()) and self.dismiss())

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
            elif self._style in ("zoom", "pop", "flip", "swirl"):
                if self._style == "zoom":                 # grows from small, with a little overshoot
                    sx = sy = max(0.05, 0.45 + 0.55 * _ease_back(t))
                    rot = 0
                elif self._style == "pop":                # lands from slightly bigger
                    sx = sy = 1.18 - 0.18 * t
                    rot = 0
                elif self._style == "flip":               # turns around like a card
                    sx, sy, rot = max(0.04, t), 1.0, 0
                else:                                     # spins in from small
                    sx = sy = max(0.05, 0.3 + 0.7 * t)
                    rot = -160 * (1 - t)
                p.translate(c)
                p.rotate(rot)
                p.scale(sx, sy)
                p.translate(-c)
                p.setOpacity(min(1.0, t * 1.3))
            elif self._style in ("drop", "rise"):         # slides into place from above / below
                p.translate(0, (-46 if self._style == "drop" else 46) * (1 - t) ** 2)
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
            inner = r.adjusted(10, 3, -10, -3)
            if keys[m] == "None":
                p.drawText(inner, Qt.AlignCenter, tr(MODE_LABEL[m]))
            else:                                       # the wheel's name, and its key under it (made to fit)
                top = QRectF(inner.left(), inner.top(), inner.width(), inner.height() * 0.55)
                bot = QRectF(inner.left(), top.bottom() - 1, inner.width(), inner.height() * 0.45)
                p.drawText(top, Qt.AlignHCenter | Qt.AlignBottom, tr(MODE_LABEL[m]))
                fk = QFont(i18n.ui_font(), 7)
                p.setFont(fk)
                col = QColor(ON_ACCENT if active else C("dim"))
                p.setPen(col)
                p.drawText(bot, Qt.AlignHCenter | Qt.AlignTop,
                           QFontMetrics(fk).elidedText(key_label(keys[m]), Qt.ElideRight, int(bot.width())))
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
