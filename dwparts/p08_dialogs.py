"""DragWheel: Dialog styling + parameter prompt (trim times, password…)

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


# ============================================================================
# Dialog styling + parameter prompt (trim times, password…)
# ============================================================================
# Settings: the pages down the left side and which sections each one shows (by their English names)
SETTINGS_PAGES = [
    ("general", "General", "Language, look, and how DragWheel starts with Windows",
     ["Appearance", "Startup", "Right-click menu"]),
    ("wheel", "Wheel", "The keys and gestures that open the wheel while you drag a file",
     ["Wheel keys", "Mouse Control", "Animations"]),
    ("sounds", "Sounds & notifications", "What you see and hear when a job finishes",
     ["When a job finishes"]),
    ("files", "Files & jobs", "Where results go, and how several jobs run",
     ["Output", "Jobs", "Auto Convert"]),
    ("float", "Float", "The mini player for pictures, videos, music and links",
     ["Float"]),
    ("customize", "Customize", "Choose the slices, and add your own slices, presets and chains",
     ["Wheel slices", "Custom Slices", "Presets and chains"]),
    ("advanced", "Advanced", "Command line, moving to another PC, help and crash reports",
     ["Command line", "Settings Config", "Help"]),
    ("about", "About", "", None),
]


def nav_icon(kind: str) -> "QIcon":
    """Simple modern line icons for the Settings pages (drawn, so they're sharp at any size and follow the theme)."""
    import math
    from PySide6.QtGui import QIcon, QPainterPath

    def draw(color, accent):
        S = 48                                         # drawn at 2x, shown at 24 px
        pm = QPixmap(S, S)
        pm.setDevicePixelRatio(2.0)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(color, 1.9, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        c = QPointF(12, 12)
        if kind == "general":                          # gear
            path = QPainterPath()
            teeth, r1, r2 = 8, 9.2, 7.0
            for i in range(teeth * 2):
                a0 = (i / (teeth * 2)) * 2 * math.pi
                a1 = ((i + 1) / (teeth * 2)) * 2 * math.pi
                r = r1 if i % 2 == 0 else r2
                pt0 = QPointF(12 + r * math.cos(a0 + 0.08), 12 + r * math.sin(a0 + 0.08))
                pt1 = QPointF(12 + r * math.cos(a1 - 0.08), 12 + r * math.sin(a1 - 0.08))
                if i == 0:
                    path.moveTo(pt0)
                else:
                    path.lineTo(pt0)
                path.lineTo(pt1)
            path.closeSubpath()
            p.drawPath(path)
            p.drawEllipse(c, 3.0, 3.0)
        elif kind == "wheel":                          # the radial wheel
            p.drawEllipse(c, 9.0, 9.0)
            p.drawEllipse(c, 3.6, 3.6)
            for i in range(5):
                a = -math.pi / 2 + i * 2 * math.pi / 5
                p.drawLine(QPointF(12 + 3.6 * math.cos(a), 12 + 3.6 * math.sin(a)),
                           QPointF(12 + 9.0 * math.cos(a), 12 + 9.0 * math.sin(a)))
            p.setPen(Qt.NoPen)
            p.setBrush(accent)
            p.drawEllipse(c, 1.6, 1.6)
        elif kind == "sounds":                         # bell
            path = QPainterPath()
            path.moveTo(5, 17)
            path.lineTo(19, 17)
            path.cubicTo(17, 15, 17.5, 13, 17.5, 10.5)
            path.cubicTo(17.5, 7, 15, 4.5, 12, 4.5)
            path.cubicTo(9, 4.5, 6.5, 7, 6.5, 10.5)
            path.cubicTo(6.5, 13, 7, 15, 5, 17)
            p.drawPath(path)
            p.drawArc(QRectF(9.5, 16.5, 5, 4), 180 * 16, 180 * 16)
        elif kind == "files":                          # folder
            path = QPainterPath()
            path.moveTo(3.5, 7)
            path.lineTo(3.5, 18)
            path.quadTo(3.5, 19.5, 5, 19.5)
            path.lineTo(19, 19.5)
            path.quadTo(20.5, 19.5, 20.5, 18)
            path.lineTo(20.5, 9.5)
            path.quadTo(20.5, 8, 19, 8)
            path.lineTo(12, 8)
            path.lineTo(10, 5.5)
            path.lineTo(5, 5.5)
            path.quadTo(3.5, 5.5, 3.5, 7)
            p.drawPath(path)
        elif kind == "float":                          # a little screen with a play sign
            p.drawRoundedRect(QRectF(3, 5, 18, 14), 2.5, 2.5)
            path = QPainterPath()
            path.moveTo(10, 9)
            path.lineTo(15.5, 12)
            path.lineTo(10, 15)
            path.closeSubpath()
            p.setBrush(accent)
            p.setPen(Qt.NoPen)
            p.drawPath(path)
        elif kind == "customize":                      # sliders
            for y, kx in ((6.5, 15), (12, 8), (17.5, 13)):
                p.drawLine(QPointF(4, y), QPointF(20, y))
                p.setBrush(accent)
                p.drawEllipse(QPointF(kx, y), 2.4, 2.4)
                p.setBrush(Qt.NoBrush)
        elif kind == "advanced":                       # terminal
            p.drawRoundedRect(QRectF(3, 4.5, 18, 15), 2.5, 2.5)
            p.drawPolyline([QPointF(7, 9.5), QPointF(10, 12), QPointF(7, 14.5)])
            p.drawLine(QPointF(12, 15), QPointF(16.5, 15))
        elif kind == "quickshare":                     # two linked circles (share)
            p.drawEllipse(QPointF(6.5, 12), 2.6, 2.6)
            p.drawEllipse(QPointF(17.5, 6.5), 2.6, 2.6)
            p.drawEllipse(QPointF(17.5, 17.5), 2.6, 2.6)
            p.drawLine(QPointF(8.8, 10.8), QPointF(15.2, 7.7))
            p.drawLine(QPointF(8.8, 13.2), QPointF(15.2, 16.3))
        elif kind == "link":                           # chain
            p.drawRoundedRect(QRectF(2.5, 9, 10, 6), 3, 3)
            p.drawRoundedRect(QRectF(11.5, 9, 10, 6), 3, 3)
            p.setPen(QPen(accent, 1.9, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(9, 12), QPointF(15, 12))
        elif kind == "pclink":                         # a screen with a globe
            p.drawRoundedRect(QRectF(3, 4, 18, 12.5), 2, 2)
            p.drawLine(QPointF(9, 20), QPointF(15, 20))
            p.drawLine(QPointF(12, 16.5), QPointF(12, 20))
            p.setPen(QPen(accent, 1.6))
            p.drawEllipse(QPointF(12, 10.2), 3.6, 3.6)
            p.drawLine(QPointF(8.4, 10.2), QPointF(15.6, 10.2))
            p.drawEllipse(QPointF(12, 10.2), 1.5, 3.6)
        elif kind == "cloud":                          # cloud
            path = QPainterPath()
            path.moveTo(6.5, 18)
            path.cubicTo(3.5, 18, 2.5, 15.5, 3.2, 13.8)
            path.cubicTo(3.8, 12.2, 5.3, 11.6, 6.6, 11.8)
            path.cubicTo(7, 8.2, 9.6, 6, 12.6, 6.2)
            path.cubicTo(15.4, 6.4, 17.4, 8.5, 17.8, 11)
            path.cubicTo(20, 11.2, 21.5, 12.9, 21.3, 14.9)
            path.cubicTo(21.1, 16.8, 19.6, 18, 17.7, 18)
            path.closeSubpath()
            p.drawPath(path)
            p.setPen(QPen(accent, 1.9, Qt.SolidLine, Qt.RoundCap))
            p.drawLine(QPointF(12, 15.6), QPointF(12, 10.6))
            p.drawPolyline([QPointF(9.8, 12.6), QPointF(12, 10.4), QPointF(14.2, 12.6)])
        elif kind == "bluetooth":                      # the Bluetooth rune
            p.drawPolyline([QPointF(7, 7.5), QPointF(16.5, 16), QPointF(12, 20), QPointF(12, 4),
                            QPointF(16.5, 8), QPointF(7, 16.5)])
        elif kind == "wifi":                           # Wi-Fi arcs
            for r in (9.5, 6.3, 3.2):
                p.drawArc(QRectF(12 - r, 17.5 - r, 2 * r, 2 * r), 45 * 16, 90 * 16)
            p.setPen(Qt.NoPen)
            p.setBrush(accent)
            p.drawEllipse(QPointF(12, 17.8), 1.6, 1.6)
        elif kind == "about":                          # info
            p.drawEllipse(c, 9.0, 9.0)
            p.drawLine(QPointF(12, 11), QPointF(12, 16.5))
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(12, 7.8), 1.3, 1.3)
        p.end()
        return pm

    icon = QIcon()
    icon.addPixmap(draw(C("dim"), C("dim")), QIcon.Normal)
    icon.addPixmap(draw(C("text"), ACCENT), QIcon.Selected)
    icon.addPixmap(draw(C("text"), ACCENT), QIcon.Active)
    return icon


SETTINGS_CSS = """
QListWidget#nav{background:transparent;border:none;padding:0;outline:0;font:700 10.5pt 'Segoe UI'}
QListWidget#nav::item{color:$dim;padding:11px 12px;margin:2px 0;border-radius:8px;font:700 10.5pt 'Segoe UI'}
QListWidget#nav::item:hover{background:$surface;color:$text}
QListWidget#nav::item:selected{background:$surface;color:$text;border-left:3px solid $accent}
QLabel#pagetitle{color:$text;font:600 17pt 'Segoe UI';padding:2px 0 0 2px}
QLabel#pagesub{color:$dim;font:9.5pt 'Segoe UI';padding:0 0 6px 2px}
QGroupBox#section{background:$surface;color:$text;font:600 10pt 'Segoe UI';border:1px solid $border;border-radius:10px;
margin-top:30px;padding:14px 12px 12px 12px}
QGroupBox#section::title{subcontrol-origin:margin;subcontrol-position:top left;left:4px;top:4px;padding:0 2px}
QGroupBox#section QLabel,QGroupBox#section QCheckBox{background:transparent}
QPushButton#keycap{background:$bg;color:$text;border:1px solid $border;border-radius:6px;padding:6px 10px;
font:600 10pt 'Segoe UI';text-align:left} QPushButton#keycap:hover{border-color:$accent}
QPushButton#keycap:focus{border-color:$accent}
"""


DIALOG_CSS = """
*{font-family:'Segoe UI'}
QDialog{background:$bg} QWidget#page{background:$bg} QLabel{color:$text;font:10pt 'Segoe UI'} QGroupBox{color:$dim;font:600 9pt 'Segoe UI';
border:1px solid $border;border-radius:8px;margin-top:22px;padding:10px 8px 8px 8px} QGroupBox::title{subcontrol-origin:margin;subcontrol-position:top left;padding:0 6px;left:8px;top:0px}
QLineEdit,QComboBox{background:$surface;color:$text;border:1px solid $border;border-radius:6px;padding:5px 8px;font:10pt 'Segoe UI'}
QLineEdit:focus,QComboBox:focus{border-color:$accent} QCheckBox,QRadioButton{color:$text;font:10pt 'Segoe UI';spacing:10px}
QListWidget{font:10pt 'Segoe UI'} QListWidget::indicator{margin-right:10px}
QListWidget{background:$surface;color:$text;border:1px solid $border;border-radius:6px;padding:2px}
QScrollBar:vertical{background:transparent;width:10px;margin:2px} QScrollBar::handle:vertical{background:$button;border-radius:4px;min-height:30px}
QScrollBar::handle:vertical:hover{background:$hover} QScrollBar::add-line,QScrollBar::sub-line{height:0;width:0} QScrollBar::add-page,QScrollBar::sub-page{background:transparent}
QSlider::groove:horizontal{height:4px;background:$border;border-radius:2px} QSlider::sub-page:horizontal{background:$accent;border-radius:2px}
QSlider::handle:horizontal{background:$text;width:14px;height:14px;margin:-5px 0;border-radius:7px}
QListWidget{outline:0} QListWidget::item{padding:3px 4px;border:none} QListWidget::item:focus{border:none;outline:none}
QListWidget::item:selected{background:$accent;color:$on_accent;border-radius:4px}
QListWidget QLineEdit{background:$surface;color:$text;border:1px solid $accent;border-radius:4px;padding:2px 6px}
QPushButton{background:$button;color:$text;border:none;border-radius:6px;padding:6px 16px;font:600 9pt 'Segoe UI'}
QPushButton:default{background:$accent;color:$on_accent} QPushButton:hover{background:$hover} QPushButton:default:hover{background:$accent2}
QPushButton:pressed{background:$border} QPushButton:default:pressed{background:$accent} QPushButton:focus{outline:none}
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
QToolButton#back{background:transparent;color:$dim;border:none;border-radius:8px;padding:5px 10px 5px 4px;font:600 9pt 'Segoe UI'}
QToolButton#back:hover{background:$hover;color:$text}
QLabel#title{font:700 12pt 'Segoe UI';color:$text} QLabel#sub{color:$dim;font:9pt 'Segoe UI'} QLabel#note{color:$dim;font:9pt 'Segoe UI'}
QPushButton#primary{background:$accent;color:$on_accent} QPushButton#primary:hover{background:$accent2}
QPushButton#primary:disabled{background:$button;color:$dim}
"""
