"""DragWheel: Settings

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


# ============================================================================
# Settings
# ============================================================================
KEY_NAMES = ["Shift", "Ctrl", "Alt", "CapsLock", "None"]


_KEY_ORDER = ["Ctrl", "Shift", "Alt", "Win"]


_CLICK_ORDER = ["LeftClick", "RightClick", "MiddleMouse", "Mouse4", "Mouse5"]


def qt_key_name(k) -> str | None:
    """A Qt key as DragWheel names it ('Shift', 'Q', 'F8', ...), or None for keys that can't be used."""
    named = {Qt.Key_Shift: "Shift", Qt.Key_Control: "Ctrl", Qt.Key_Alt: "Alt", Qt.Key_Meta: "Win",
             Qt.Key_CapsLock: "CapsLock", Qt.Key_Tab: "Tab", Qt.Key_Space: "Space", Qt.Key_Insert: "Insert",
             Qt.Key_Delete: "Delete", Qt.Key_Home: "Home", Qt.Key_End: "End", Qt.Key_PageUp: "PageUp",
             Qt.Key_PageDown: "PageDown", Qt.Key_Left: "Left", Qt.Key_Right: "Right", Qt.Key_Up: "Up",
             Qt.Key_Down: "Down", Qt.Key_Backspace: "Backspace", Qt.Key_Return: "Enter", Qt.Key_Enter: "Enter",
             Qt.Key_QuoteLeft: "`", Qt.Key_Minus: "-", Qt.Key_Equal: "=", Qt.Key_BracketLeft: "[",
             Qt.Key_BracketRight: "]", Qt.Key_Semicolon: ";", Qt.Key_Apostrophe: "'", Qt.Key_Comma: ",",
             Qt.Key_Period: ".", Qt.Key_Slash: "/", Qt.Key_Backslash: "\\"}
    k = int(k)
    if k in {int(a): b for a, b in named.items()}:
        return {int(a): b for a, b in named.items()}[k]
    if int(Qt.Key_A) <= k <= int(Qt.Key_Z) or int(Qt.Key_0) <= k <= int(Qt.Key_9):
        return chr(k)
    if int(Qt.Key_F1) <= k <= int(Qt.Key_F24):
        return f"F{k - int(Qt.Key_F1) + 1}"
    return None


def combo_text(names) -> str:
    names = list(dict.fromkeys(names))
    names.sort(key=lambda n: (_KEY_ORDER.index(n) if n in _KEY_ORDER else 20 + _CLICK_ORDER.index(n)
                              if n in _CLICK_ORDER else 9))
    return "+".join(names)


class ToggleSwitch(QPushButton):
    """An on/off switch (like Windows Settings) that works like a tick box: isChecked(), setChecked(), toggled."""

    def __init__(self, on=False, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(bool(on))
        self.setAutoDefault(False)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)
        self.setStyleSheet("QPushButton{background:transparent;border:none;padding:0}")
        self._pos = 1.0 if on else 0.0
        self._anim = QVariantAnimation(self, duration=140)
        self._anim.valueChanged.connect(self._moved)
        self.toggled.connect(self._slide)

    def _moved(self, v):
        self._pos = float(v)
        self.update()

    def _slide(self, on):
        self._anim.stop()
        if not self.isVisible():                        # set up before it's shown: no sliding
            self._pos = 1.0 if on else 0.0
            self.update()
            return
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(1, 2, self.width() - 2, self.height() - 4)
        on = self._pos
        track = QColor(ACCENT) if self.isChecked() else C("button")
        if not self.isEnabled():
            track.setAlphaF(0.4)
        p.setPen(QPen(ACCENT if self.isChecked() else C("line"), 1))
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + on * (r.width() - 6 - d)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#ffffff") if self.isChecked() else C("text"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))
        p.end()


class SwitchBox(QWidget):
    """A flip switch with its words next to it; used like a tick box (isChecked, setChecked, toggled)."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(12)
        self.sw = ToggleSwitch(False)
        self.label = QLabel(text)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("font-size:10pt")
        row.addWidget(self.sw, 0, Qt.AlignVCenter)
        row.addWidget(self.label, 1)
        self.toggled = self.sw.toggled
        self.isChecked = self.sw.isChecked
        self.setChecked = self.sw.setChecked

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.isEnabled():
            self.sw.toggle()

    def setText(self, text):
        self.label.setText(text)

    def changeEvent(self, e):
        if e.type() == QEvent.EnabledChange:
            self.sw.setEnabled(self.isEnabled())
            self.label.setEnabled(self.isEnabled())
        super().changeEvent(e)


def setting_row(switch, title, desc, extra=None) -> QHBoxLayout:
    """[switch]  Title (bold) with a short description under it  ………  [extra control]"""
    row = QHBoxLayout()
    row.setSpacing(12)
    row.addWidget(switch, 0, Qt.AlignTop)
    col = QVBoxLayout()
    col.setSpacing(1)
    t = QLabel(title)
    t.setStyleSheet("font-weight:700;font-size:10.5pt")
    d = QLabel(desc)
    d.setObjectName("dim")
    d.setWordWrap(True)
    col.addWidget(t)
    col.addWidget(d)
    row.addLayout(col, 1)
    if extra is not None:
        lbl = QLabel(tr("Opens"))
        lbl.setObjectName("dim")
        row.addWidget(lbl, 0, Qt.AlignVCenter)
        extra.setMinimumWidth(150)
        row.addWidget(extra, 0, Qt.AlignVCenter)
        switch.toggled.connect(extra.setEnabled)
        extra.setEnabled(switch.isChecked())
    return row


class KeyCapture(QPushButton):
    """Click, then press any key or combination (Ctrl+Q, F8, the mouse's side buttons…). Esc cancels."""
    changed = Signal(str)

    def __init__(self, spec="None", parent=None):
        super().__init__(parent)
        self.spec = spec or "None"
        self._listening = False
        self._down, self._combo = set(), []
        self.setCheckable(False)
        self.setAutoDefault(False)
        self.setObjectName("keycap")
        self.setMinimumWidth(220)
        self.setCursor(Qt.PointingHandCursor)
        self.clicked.connect(self._listen)
        self._show()

    def _show(self):
        if self._listening:
            self.setText(key_label(combo_text(self._combo)) + " …" if self._combo else tr("Press a key or a combination…"))
        else:
            self.setText(key_label(self.spec))

    def _listen(self):
        self._listening, self._down, self._combo = True, set(), []
        self.setFocus()
        self.grabKeyboard()
        self.grabMouse()                                # a click anywhere: key + click, or cancel
        self._show()

    def _finish(self, spec=None):
        self.releaseKeyboard()
        self.releaseMouse()
        self._listening = False
        if spec is not None and spec != self.spec:
            self.spec = spec
            self.changed.emit(spec)
        self._show()

    def set_spec(self, spec):
        self.spec = spec or "None"
        self._show()

    def keyPressEvent(self, e):
        if not self._listening:
            return super().keyPressEvent(e)
        if e.key() == Qt.Key_Escape:
            self._finish()
            return
        if e.isAutoRepeat():
            return
        name = qt_key_name(e.key())
        if name:
            self._down.add(name)
            if name not in self._combo:
                self._combo.append(name)
            self._show()

    def keyReleaseEvent(self, e):
        if not self._listening or e.isAutoRepeat():
            return
        name = qt_key_name(e.key())
        self._down.discard(name)
        if not self._down and self._combo:          # everything let go: that's the combination
            self._finish(combo_text(self._combo))

    def mousePressEvent(self, e):
        if self._listening:
            extra = {Qt.MiddleButton: "MiddleMouse", Qt.BackButton: "Mouse4", Qt.ForwardButton: "Mouse5"}.get(e.button())
            if extra:
                self._finish(combo_text(self._combo + [extra]))
                return
            click = {Qt.LeftButton: "LeftClick", Qt.RightButton: "RightClick"}.get(e.button())
            if click and self._down:                    # a key held + left or right click
                self._finish(combo_text(self._combo + [click]))
                return
            if e.button() == Qt.LeftButton:
                self._finish()                          # clicked without a key: keep what it was
                return
            if e.button() == Qt.RightButton:
                return                                  # a right click on its own can't open a wheel
        super().mousePressEvent(e)

    def focusOutEvent(self, e):
        if self._listening:
            self._finish()
        super().focusOutEvent(e)
