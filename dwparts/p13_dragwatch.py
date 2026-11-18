"""DragWheel: Drag watcher — polls input state (no hooks, nothing injected)

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


# ============================================================================
# Drag watcher — polls input state (no hooks, nothing injected)
# ============================================================================
class CursorBusy(QWidget):
    """A small spinning circle next to the mouse pointer while DragWheel is working (Settings → Everyday)."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(22, 22)
        self.angle = 0
        self.timer = QTimer(self, interval=30, timeout=self._tick)

    def set_busy(self, busy):
        if busy and not self.isVisible():
            self._tick()
            self.show()
            self.timer.start()
        elif not busy and self.isVisible():
            self.timer.stop()
            self.hide()

    def _tick(self):
        pos = QCursor.pos()
        self.move(pos.x() + 16, pos.y() + 18)
        self.angle = (self.angle + 14) % 360
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(3, 3, 16, 16)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 110))
        p.drawEllipse(r.adjusted(-2, -2, 2, 2))
        p.setPen(QPen(QColor(255, 255, 255, 90), 2.6))
        p.drawEllipse(r)
        pen = QPen(ACCENT, 2.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(r, -self.angle * 16, 110 * 16)
        p.end()


DOC_PREVIEW_CATS = ("pdf", "document", "spreadsheet", "slides", "ebook")


TEXTLIKE_EXT = (".txt", ".md", ".csv", ".tsv", ".json", ".html", ".htm", ".rtf", ".log")


class ButtonPolish(QObject):
    """Buttons act like buttons: clicking one doesn't leave it lit up as the window's default button.
    Only the main button of a dialog's button row (Save, OK) stays highlighted."""

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Polish and isinstance(obj, QPushButton) and not obj.property("_dw_polished"):
            obj.setProperty("_dw_polished", True)
            if not isinstance(obj.parent(), QDialogButtonBox):
                obj.setAutoDefault(False)
                obj.setDefault(False)
        return False


class PeekSignals(QObject):
    ready = Signal(object, object)      # path, QImage


def _office_to_pdf(src: Path, dest: Path) -> bool:
    """Print a Word, Excel or PowerPoint file (or RTF, ODT…) to `dest` as a PDF, read-only, without touching
    the original's folder: Microsoft Office when it's installed, else LibreOffice."""
    cat = engine.EXT_CATEGORY.get(engine.ext_of(str(src)))
    if winsys.IS_WIN:
        try:
            import pythoncom
            import win32com.client as wc
            pythoncom.CoInitialize()
            try:
                if cat in ("document", "pdf"):
                    app = wc.DispatchEx("Word.Application")
                    app.Visible = False
                    app.DisplayAlerts = 0
                    try:
                        doc = app.Documents.Open(str(src), ConfirmConversions=False, ReadOnly=True,
                                                 AddToRecentFiles=False, Visible=False)
                        doc.ExportAsFixedFormat(str(dest), 17, OpenAfterExport=False, OptimizeFor=1,
                                                Range=3, From=1, To=1)          # first page is enough
                        doc.Close(False)
                    finally:
                        app.Quit()
                elif cat == "spreadsheet":
                    app = wc.DispatchEx("Excel.Application")
                    app.Visible = False
                    app.DisplayAlerts = False
                    try:
                        wb = app.Workbooks.Open(str(src), ReadOnly=True, UpdateLinks=0)
                        wb.ActiveSheet.ExportAsFixedFormat(0, str(dest), From=1, To=1, OpenAfterPublish=False)
                        wb.Close(False)
                    finally:
                        app.Quit()
                elif cat == "slides":
                    app = wc.DispatchEx("PowerPoint.Application")
                    try:
                        pres = app.Presentations.Open(str(src), ReadOnly=True, WithWindow=False)
                        pres.SaveAs(str(dest), 32)
                        pres.Close()
                    finally:
                        app.Quit()
            finally:
                pythoncom.CoUninitialize()
            if dest.exists() and dest.stat().st_size > 0:
                return True
        except Exception as e:
            winsys.log(f"preview: Office could not open {src.name}: {e}")
    exe = engine.soffice()
    if exe:
        import subprocess
        import tempfile
        td = Path(tempfile.mkdtemp(prefix="dw-prev-"))
        try:
            subprocess.run([exe, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", str(td), str(src)],
                           timeout=90, stdin=subprocess.DEVNULL, capture_output=True, creationflags=engine.NO_WINDOW)
            made = list(td.glob("*.pdf"))
            if made:
                shutil.move(str(made[0]), str(dest))
                return True
        except Exception as e:
            winsys.log(f"preview: LibreOffice could not open {src.name}: {e}")
        finally:
            shutil.rmtree(td, ignore_errors=True)
    return False


_PREVIEW_LOCK = threading.Lock()


def _pdf_for_preview(p: Path) -> Path | None:
    """A PDF of an Office-type file for previews, made once and kept in the temp folder until the file changes."""
    import hashlib
    import tempfile
    try:
        st = p.stat()
    except OSError:
        return None
    key = hashlib.sha1(f"{p}|{st.st_size}|{st.st_mtime_ns}".encode("utf-8")).hexdigest()[:16]
    folder = Path(tempfile.gettempdir()) / "DragWheel previews"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{key}.pdf"
    with _PREVIEW_LOCK:                      # Float and Quick preview asking at once make it only once
        if out.exists() and out.stat().st_size > 0:
            return out
        part = folder / f"{key}.tmp.pdf"
        part.unlink(missing_ok=True)
        if _office_to_pdf(p.resolve(), part):
            os.replace(part, out)
            return out
        part.unlink(missing_ok=True)
        winsys.log(f"preview: no page for {p.name} (needs Microsoft Office or LibreOffice)")
        return None


def _text_page_image(p: Path, width: int) -> "QImage | None":
    """Text, Markdown, HTML, CSV and JSON files drawn as a white page."""
    from PySide6.QtGui import QTextDocument, QTextOption
    try:
        raw = p.read_bytes()[:400_000]
    except OSError:
        return None
    txt = None
    for enc in ("utf-8-sig", "utf-16", "cp1256", "latin-1"):
        try:
            txt = raw.decode(enc)
            if enc == "utf-16" and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
                continue
            break
        except UnicodeDecodeError:
            continue
    if txt is None:
        return None
    e = p.suffix.lower()
    doc = QTextDocument()
    doc.setDocumentMargin(36)
    f = QFont(i18n.ui_font() if e in (".md", ".markdown", ".html", ".htm") else "Consolas", 11)
    doc.setDefaultFont(f)
    opt = QTextOption()
    opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    if any("\u0600" <= ch <= "\u06ff" for ch in txt[:2000]):
        opt.setTextDirection(Qt.RightToLeft)
        opt.setAlignment(Qt.AlignRight)
    doc.setDefaultTextOption(opt)
    if e in (".html", ".htm"):
        doc.setHtml(txt)
    elif e in (".md", ".markdown"):
        doc.setMarkdown(txt)
    elif e in (".csv", ".tsv"):
        import csv
        import html as _h
        rows = list(csv.reader(txt.splitlines()[:60], delimiter="\t" if e == ".tsv" else ","))
        doc.setHtml("<table border='1' cellspacing='0' cellpadding='4' style='border-collapse:collapse'>" + "".join(
            "<tr>" + "".join(f"<td>{_h.escape(c)}</td>" for c in r[:12]) + "</tr>" for r in rows) + "</table>")
    elif opt.textDirection() == Qt.RightToLeft:
        import html as _h
        doc.setDefaultFont(QFont(i18n.ui_font(), 12))
        doc.setHtml("<div dir='rtl' align='right' style='white-space:pre-wrap'>" + _h.escape(txt[:20000]) + "</div>")
    else:
        doc.setPlainText(txt[:20000])
    page_w = 620
    doc.setTextWidth(page_w)
    page_h = int(page_w * 1.414)
    scale = width / page_w
    img = QImage(width, int(page_h * scale), QImage.Format_RGB888)
    img.fill(QColor(255, 255, 255))
    pnt = QPainter(img)
    pnt.setRenderHint(QPainter.Antialiasing)
    pnt.setRenderHint(QPainter.TextAntialiasing)
    pnt.scale(scale, scale)
    pnt.setClipRect(QRectF(0, 0, page_w, page_h))
    from PySide6.QtGui import QAbstractTextDocumentLayout
    ctx = QAbstractTextDocumentLayout.PaintContext()
    ctx.palette.setColor(ctx.palette.ColorRole.Text, QColor(20, 20, 20))
    doc.documentLayout().draw(pnt, ctx)
    pnt.end()
    return img


def document_page_image(path, width=1200, page=0) -> "QImage | None":
    """First page of any document as a picture: PDFs, e-books and comics directly, Word/Excel/PowerPoint/RTF/ODT
    through a PDF, and text, Markdown, HTML and CSV files drawn as a page."""
    p = Path(path)
    cat = engine.EXT_CATEGORY.get(engine.ext_of(str(p)))
    e = p.suffix.lower()
    if e in TEXTLIKE_EXT or e in (".markdown", ".json"):
        try:
            return _text_page_image(p, width)
        except Exception as ex:
            winsys.log(f"preview: {p.name}: {ex}")
            return None
    src = p
    if cat in ("document", "spreadsheet", "slides"):
        src = _pdf_for_preview(p)
        if src is None:
            return None
    try:
        import pymupdf
        with pymupdf.open(str(src)) as doc:
            if doc.page_count == 0:
                return None
            pg = doc[min(page, doc.page_count - 1)]
            zoom = width / max(1.0, pg.rect.width)
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            return QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
    except Exception as ex:
        winsys.log(f"preview: {p.name}: {ex}")
        return None


def _peek_image(path) -> "QImage | None":
    """A picture of the file for Quick preview: the image itself, a PDF's first page, a video frame."""
    p = Path(path)
    cat = engine.EXT_CATEGORY.get(engine.ext_of(str(p)))
    try:
        if cat == "image":
            img = QImage(str(p))
            if img.isNull():
                from PIL import Image
                try:
                    import pillow_heif
                    pillow_heif.register_heif_opener()
                except Exception:
                    pass
                with Image.open(p) as im:
                    im.thumbnail((900, 900))
                    im = im.convert("RGBA")
                    img = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, QImage.Format_RGBA8888).copy()
            return None if img.isNull() else img.scaled(900, 900, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if cat in DOC_PREVIEW_CATS or p.suffix.lower() in (".cbz", ".xps", ".json"):
            return document_page_image(p, 900)
        if cat == "video":
            import subprocess
            import tempfile
            out = Path(tempfile.gettempdir()) / f"dw-peek-{os.getpid()}.jpg"
            subprocess.run([engine.ffmpeg(), "-y", "-v", "error", "-ss", "2", "-i", str(p), "-frames:v", "1",
                            "-vf", "scale='min(900,iw)':-2", str(out)], timeout=8, stdin=subprocess.DEVNULL,
                           capture_output=True, creationflags=engine.NO_WINDOW)
            img = QImage(str(out))
            try:
                out.unlink()
            except OSError:
                pass
            return None if img.isNull() else img
    except Exception as e:
        winsys.log(f"peek: {p.name}: {e}")
    return None


class PeekWindow(QWidget):
    """Quick preview: tap Space while dragging to see what you're holding."""

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.path = None
        self.img = None
        self.text = ""
        self.sig = PeekSignals()
        self.sig.ready.connect(self._got, Qt.QueuedConnection)
        self.follow = QTimer(self, interval=15, timeout=self._place)    # rides along with the pointer
        self._last_pos = None

    def peek(self, paths):
        self.path = paths[0]
        p = Path(self.path)
        self.img = None
        self.text = ""
        cat = engine.EXT_CATEGORY.get(engine.ext_of(str(p)))
        if p.is_file() and (cat in ("subtitle",) or p.suffix.lower() in (".log", ".py", ".ini", ".xml", ".srt")):
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    self.text = "".join(f.readline() for _ in range(24))[:2400]
            except OSError:
                pass
        elif p.is_file():
            threading.Thread(target=lambda path=self.path: self.sig.ready.emit(path, _peek_image(path)),
                             daemon=True).start()
        self.extra = tr("{n} files", n=len(paths)) if len(paths) > 1 else ""
        self._layout()
        self.show()
        self.raise_()

    def _got(self, path, img):
        if path == self.path and self.isVisible() and img is not None:
            self.img = img
            self._layout()
            self.update()

    def _layout(self):
        w, h = 340, 120
        if self.img is not None:
            sc = min(420 / self.img.width(), 380 / self.img.height(), 1.0)
            w, h = max(240, int(self.img.width() * sc) + 24), int(self.img.height() * sc) + 74
        elif self.text:
            w, h = 420, 300
        else:
            w, h = 300, 150
        self.resize(w, h)
        self._last_pos = None
        self._place()

    def _place(self):
        pos = QCursor.pos()
        if pos == self._last_pos:
            return
        self._last_pos = pos
        w, h = self.width(), self.height()
        scr = (QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()).availableGeometry()
        x = pos.x() + 28 if pos.x() + 28 + w < scr.right() else pos.x() - 28 - w
        y = max(scr.top() + 8, min(pos.y() - h // 2, scr.bottom() - h - 8))
        self.move(x, y)

    def showEvent(self, e):
        self.follow.start()
        super().showEvent(e)

    def hideEvent(self, e):
        self.follow.stop()
        super().hideEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setPen(QPen(C("line"), 1))
        p.setBrush(C("panel"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)
        path = Path(self.path or "")
        body = QRectF(12, 12, self.width() - 24, self.height() - 74)
        if self.img is not None:
            pm = QPixmap.fromImage(self.img)
            if pm.width() > body.width() or pm.height() > body.height():      # shrink big pictures, never blow up small ones
                pm = pm.scaled(body.size().toSize(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            p.drawPixmap(int(body.center().x() - pm.width() / 2), int(body.center().y() - pm.height() / 2), pm)
        elif self.text:
            p.setPen(C("text"))
            p.setFont(QFont("Consolas", 8))
            p.drawText(body, Qt.AlignLeft | Qt.AlignTop | Qt.TextWrapAnywhere, self.text)
        else:
            from PySide6.QtCore import QFileInfo
            from PySide6.QtWidgets import QFileIconProvider
            ic = QFileIconProvider().icon(QFileInfo(str(path))).pixmap(56, 56)
            p.drawPixmap(int(body.center().x() - 28), int(body.center().y() - 28), ic)
        p.setPen(C("text"))
        p.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
        fm = QFontMetrics(p.font())
        p.drawText(QRectF(14, self.height() - 58, self.width() - 28, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(path.name, Qt.ElideMiddle, self.width() - 28))
        p.setPen(C("dim"))
        p.setFont(QFont("Segoe UI", 9))
        info = " · ".join(x for x in (_human(path), self.extra, tr("{key} to close", key=key_label(peek_key()))) if x)
        p.drawText(QRectF(14, self.height() - 36, self.width() - 28, 20), Qt.AlignLeft | Qt.AlignVCenter, info)
        p.end()


class TourCanvas(QWidget):
    """A looping little film: drag a file, tap the key, drop on a slice, done."""
    LOOP = 7.2

    def __init__(self, key, parent=None):
        super().__init__(parent)
        import time
        self.key = key
        self.t0 = time.monotonic()
        self.setFixedSize(620, 330)
        w = Wheel(_APP)
        w._style = "none"
        w.mode, w.paths = "convert", ["C:/example/Holiday.heic"]
        w.ops = [engine.Op(f"to_{x.lower()}", x, lambda *a: None) for x in ("JPG", "PNG", "WEBP", "PDF", "GIF", "AVIF", "TIFF", "ICO")]
        w.hover = -1
        self.plain = w.grab()
        w.hover = 1
        self.lit = w.grab()
        self.wheel_c = w.center()
        self.slice_pos = None
        from PySide6.QtCore import QFileInfo
        from PySide6.QtWidgets import QFileIconProvider
        self.icon = QFileIconProvider().icon(QFileInfo("x.jpg")).pixmap(48, 48)
        if self.icon.isNull() or self.icon.toImage().allGray() and self.icon.toImage().pixelColor(24, 24).alpha() == 0:
            self.icon = QPixmap(48, 48)                      # a plain picture-file shape
            self.icon.fill(Qt.transparent)
            q = QPainter(self.icon)
            q.setRenderHint(QPainter.Antialiasing)
            q.setPen(QPen(QColor("#9aa0a6"), 1.5))
            q.setBrush(QColor("#ffffff"))
            q.drawRoundedRect(QRectF(8, 3, 32, 42), 4, 4)
            q.setPen(Qt.NoPen)
            q.setBrush(QColor("#4a90e2"))
            q.drawPolygon(QPolygonF([QPointF(12, 38), QPointF(22, 24), QPointF(28, 32), QPointF(32, 27), QPointF(36, 38)]))
            q.setBrush(QColor("#f5a623"))
            q.drawEllipse(QPointF(30, 14), 4, 4)
            q.end()
        self.timer = QTimer(self, interval=16, timeout=self.update)
        self.timer.start()

    def step(self):
        import time
        t = (time.monotonic() - self.t0) % self.LOOP
        return 0 if t < 1.3 else 1 if t < 2.2 else 2 if t < 4.2 else 3

    def paintEvent(self, _e):
        import time
        t = (time.monotonic() - self.t0) % self.LOOP
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setPen(QPen(C("line"), 1))
        p.setBrush(QColor(theme.hexc("canvas")))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)

        def ease(a):
            a = max(0.0, min(1.0, a))
            return a * a * (3 - 2 * a)

        start, center = QPointF(80, 250), QPointF(310, 150)
        scale = 0.5
        ang = math.radians(45)                       # the PNG slice: second of eight, 45° clockwise from the top
        rr = (Wheel.R_IN + Wheel.R_MID + 14) / 2 * scale
        target = center + QPointF(math.sin(ang) * rr, -math.cos(ang) * rr)
        if t < 1.3:
            cur = start + (center - start) * ease(t / 1.3)
        elif t < 2.2:
            cur = center
        elif t < 3.4:
            cur = center + (target - center) * ease((t - 2.2) / 1.2)
        else:
            cur = target
        # the wheel
        show = 0.0
        if 1.45 <= t < 4.0:
            show = ease((t - 1.45) / 0.35) if t < 3.6 else 1 - ease((t - 3.6) / 0.4)
        if show > 0:
            pm = self.lit if 3.0 <= t < 3.8 else self.plain
            w, h = pm.width() / pm.devicePixelRatio() * scale, pm.height() / pm.devicePixelRatio() * scale
            c = self.wheel_c * scale
            p.save()
            p.setOpacity(show)
            p.translate(center)
            k = 0.8 + 0.2 * show
            p.scale(k, k)
            p.drawPixmap(QRectF(-c.x(), -c.y(), w, h), pm, QRectF(pm.rect()))
            p.restore()
        # the file being dragged (and the pointer)
        if t < 3.7:
            p.setOpacity(1.0 if t < 3.5 else 1 - (t - 3.5) / 0.2)
            p.drawPixmap(int(cur.x() - 10), int(cur.y() - 6), self.icon)
            p.setOpacity(1.0)
        arrow = QPolygonF([QPointF(0, 0), QPointF(0, 17), QPointF(4.5, 13), QPointF(8, 20), QPointF(10.5, 19),
                           QPointF(7, 12), QPointF(13, 12)])
        p.save()
        p.translate(cur)
        p.setPen(QPen(QColor("#000000"), 1.2))
        p.setBrush(QColor("#ffffff"))
        p.drawPolygon(arrow)
        p.restore()
        # the key
        pressed = 1.25 <= t < 1.6
        kf = QFont("Segoe UI", 11, QFont.DemiBold)
        label = QFontMetrics(kf).elidedText(self.key, Qt.ElideRight, 220)
        key = QRectF(30, 26, max(92, QFontMetrics(kf).horizontalAdvance(label) + 30), 40)
        p.setPen(QPen(ACCENT if pressed else C("line"), 2))
        p.setBrush(ACCENT if pressed else C("panel"))
        p.drawRoundedRect(key.translated(0, 3 if pressed else 0), 8, 8)
        p.setPen(ON_ACCENT if pressed else C("text"))
        p.setFont(kf)
        p.drawText(key.translated(0, 3 if pressed else 0), Qt.AlignCenter, label)
        # the finished notification
        if 4.1 <= t < 6.8:
            a = ease((t - 4.1) / 0.3) if t < 6.4 else 1 - ease((t - 6.4) / 0.4)
            r = QRectF(self.width() - 250, self.height() - 74 + (1 - a) * 20, 232, 56)
            p.setOpacity(a)
            p.setPen(QPen(C("line"), 1))
            p.setBrush(C("panel"))
            p.drawRoundedRect(r, 12, 12)
            p.setPen(Qt.NoPen)
            p.setBrush(C("ok"))
            p.drawEllipse(QPointF(r.x() + 26, r.center().y()), 12, 12)
            p.setPen(QPen(ON_ACCENT, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            x0, y0 = r.x() + 26, r.center().y()
            p.drawPolyline([QPointF(x0 - 6, y0), QPointF(x0 - 1.5, y0 + 4.5), QPointF(x0 + 6, y0 - 4)])
            p.setPen(C("text"))
            p.setFont(QFont("Segoe UI", 10, QFont.DemiBold))
            p.drawText(QRectF(r.x() + 48, r.y() + 8, 180, 20), Qt.AlignLeft | Qt.AlignVCenter,
                       tr("Converted to {fmt}", fmt="PNG"))
            p.setPen(C("dim"))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(QRectF(r.x() + 48, r.y() + 28, 180, 18), Qt.AlignLeft | Qt.AlignVCenter, "Holiday.png")
        p.end()


class TourDialog(QDialog):
    """First launch: how DragWheel works in three steps, shown as a short looping animation."""

    def __init__(self, app, parent=None):
        super().__init__(parent, Qt.WindowStaysOnTopHint if parent is None else Qt.Dialog)
        self.app = app
        keys = mode_keys()
        shake = keys["convert"] == "None"
        key = tr("Shake") if shake else key_label(keys["convert"])
        self.setWindowTitle(tr("Welcome to {app}", app=APP))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS) + f"QLabel#step{{padding:8px 10px;border-radius:10px;color:{theme.hexc('dim')}}}"
                           f"QLabel#step[on=true]{{background:{theme.hexc('surface')};color:{theme.hexc('text')}}}")
        lay = QVBoxLayout(self)
        head = QLabel(f"<b style='font-size:13pt'>{tr('Welcome to {app}', app=APP)}</b><br>"
                      f"<span style='color:{theme.hexc('dim')}'>{tr('Convert any file without opening an app, in three moves:')}</span>")
        lay.addWidget(head)
        self.canvas = TourCanvas(key)
        lay.addWidget(self.canvas, 0, Qt.AlignHCenter)
        row = QHBoxLayout()
        self.steps = []
        for i, text in enumerate((tr("Drag a file (keep holding the mouse)"),
                                  tr("Shake the mouse — the wheel opens") if shake else tr("Tap {key} — the wheel opens", key=key),
                                  tr("Drop it on a slice. Done!"))):
            lbl = QLabel(f"<b>{i + 1}</b>&nbsp;&nbsp;{text}")
            lbl.setObjectName("step")
            lbl.setWordWrap(True)
            row.addWidget(lbl, 1)
            self.steps.append(lbl)
        lay.addLayout(row)
        if keys["tool"] != "None" and keys["action"] != "None":
            more = QLabel(tr("{tools} opens Tools and {actions} opens Actions. Prefer clicking? Right-click a file → DragWheel.",
                             tools=tr(keys["tool"]), actions=tr(keys["action"])))
        else:
            more = QLabel(tr("Switch wheels by resting on the buttons under the wheel. Prefer clicking? Right-click a file → DragWheel."))
        more.setWordWrap(True)
        more.setStyleSheet(f"color:{theme.hexc('dim')}")
        lay.addWidget(more)
        bb = QHBoxLayout()
        self.never = QCheckBox(tr("Don't show this again"))
        self.never.setChecked(settings().value("tour_at_start", "true") != "true")
        self.never.toggled.connect(lambda on: settings().setValue("tour_at_start", "false" if on else "true"))
        bb.addWidget(self.never)
        b = QPushButton(tr("More help"))
        b.clicked.connect(lambda: (self.accept(), app.show_help()))
        bb.addWidget(b)
        bb.addStretch(1)
        ok = QPushButton(tr("Got it"))
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        bb.addWidget(ok)
        lay.addLayout(bb)
        self._last = -1
        self._t = QTimer(self, interval=100, timeout=self._mark)
        self._t.start()

    def _mark(self):
        s = min(self.canvas.step(), 2)
        if s != self._last:
            self._last = s
            for i, lbl in enumerate(self.steps):
                lbl.setProperty("on", i == s)
                lbl.style().unpolish(lbl)
                lbl.style().polish(lbl)


class DragWatcher(QObject):
    tapped = Signal(str)     # mode
    released = Signal()
    hotkey = Signal()
    idle_tap = Signal(str)   # a wheel key tapped on its own, not while dragging (Trigger on: hover / selection)
    moved = Signal()         # every tick while a drag is in progress
    scrolled = Signal(int)   # wheel delta while dragging (from the hook thread, delivered queued)
    cancelled = Signal()     # Esc pressed during a drag
    ctrl_open = Signal(int)  # Ctrl + double-click on a file in Explorer (window handle), from the hook thread
    peek = Signal()          # Space tapped while dragging (Quick preview)
    volume_key = Signal(int)  # a volume key or knob step (from the hook thread)
    shaken = Signal()        # the mouse was shaken while dragging
    peek_up = Signal()       # File preview key let go (File preview set to "hold to show")
    click_drag = Signal(str)  # a wheel key + right click while dragging (from the hook thread)

    def __init__(self):
        super().__init__()
        self.timer = QTimer(self, interval=20, timeout=self.tick)
        self.down_at = None
        self.dragging = False
        self.prev = {}
        self.spoiled = set()     # combinations interrupted by a longer one (see tick)
        self.hotkey_latch = False
        self.source_hwnd = 0     # top-level window the drag started in
        self.esc_prev = False
        self.space_prev = False
        self.trail = []          # (time, x) while dragging, to notice a shake
        self.shook = False
        self.refresh_settings()
        self.hook = winsys.WheelHook(self._on_wheel, self._swallow_wheel,
                                     on_ctrl_double=lambda hwnd: self.ctrl_open.emit(int(hwnd)),
                                     ctrl_double_enabled=lambda: getattr(self, "ctrl_float", False))
        self.hook.on_volume_key = lambda vk: self.volume_key.emit(vk)
        self.hook.on_click = self._on_click
        self._click_specs = []   # (mode, other keys, button) for wheel keys that end in a mouse click
        self._click_pending = None   # (mode, keys) — fires when those keys are let go (Trigger on hover / selection)
        self._hold_keys = None       # keys holding File preview open (hold to show)

    def refresh_settings(self):
        s = settings()
        self.trigger = trigger_mode()
        self.scroll_enabled = s.value("scroll", "true") == "true"
        self.any_drag = False
        self.ctrl_float = s.value("float_ctrl_open", "true") == "true"
        self.shake_enabled = s.value("shake", "true") == "true"
        self.peek_vks = winsys.combo_vks(peek_key())
        self.peek_enabled = bool(self.peek_vks)
        self.peek_hold = s.value("peek_hold", "false") == "true"

    # ---- wheel key + mouse click (Ctrl + right click…): seen by the mouse hook, so the click never reaches Explorer
    CLICKS = (0x01, 0x02)

    def _hook_clicks(self):
        """Buttons the hook handles: during a file drag the left button is already down, so only right clicks."""
        return (0x02,) if getattr(self, "trigger", "drag") == "drag" else self.CLICKS

    def _on_click(self, btn, down):
        """On the hook thread: True = this click belongs to a wheel key, keep it from Windows."""
        if not down or btn not in self._hook_clicks():
            return False
        for mode, others, b in list(self._click_specs):
            if b != btn or not others or not all(winsys.key_down(v) for v in others):
                continue
            if getattr(self, "trigger", "drag") == "drag":
                if not self.dragging:
                    continue
                self.click_drag.emit(mode)
                if mode == "peek" and self.peek_hold:
                    self._hold_keys = others
                return True
            if self.dragging:
                continue
            if mode == "peek" and self.peek_hold:
                self.idle_tap.emit("peek")             # shown now, closed when the keys are let go
                self._hold_keys = others
            else:
                self._click_pending = (mode, others)   # after the keys are let go (so they don't change the selection)
            return True
        return False

    def _update_click_specs(self, keys):
        specs = []
        for mode, spec in list(keys.items()) + [("peek", peek_key())]:
            vks = winsys.combo_vks(spec)
            btns = [v for v in vks if v in self._hook_clicks()]
            if btns:
                specs.append((mode, [v for v in vks if v not in self.CLICKS], btns[-1]))
        self._click_specs = specs

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
        if time.monotonic() < winsys.SYNTH_UNTIL:
            return                                     # DragWheel is clicking for you: held keys briefly read as up
        keys = mode_keys()
        combos = {spec: set(winsys.combo_vks(spec)) for spec in set(keys.values())}
        hooked = set(self._hook_clicks())
        combos = {k: v for k, v in combos.items() if v and not v & hooked}    # key + click: the mouse hook handles those
        self._update_click_specs(keys)
        if self._click_pending and not any(winsys.key_down(v) for v in self._click_pending[1]):
            mode, self._click_pending = self._click_pending[0], None
            self.idle_tap.emit(mode)
        if self._hold_keys is not None and not any(winsys.key_down(v) for v in self._hold_keys):
            self._hold_keys = None
            self.peek_up.emit()
        down = {vk: winsys.key_down(vk) for vk in set().union(*combos.values())} if combos else {}
        held = {spec: all(down[v] for v in vks) for spec, vks in combos.items()}
        # a key that's part of a longer combination (Ctrl, when another wheel is Ctrl+Q) counts when it's let go
        # without the rest of that combination having been pressed
        subset = {spec for spec, vks in combos.items() if any(vks < o for o in combos.values())}
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
                pv = getattr(self, "peek_vks", [winsys.VK_SPACE])
                if set(pv) & hooked:
                    pv = []                            # File preview is a key + click: the mouse hook handles it
                space = bool(pv) and all(winsys.key_down(v) for v in pv) and (
                    len(pv) > 1 or pv[0] in (0x10, 0x11, 0x12) or not (winsys.key_down(0x11) or winsys.key_down(0x12)))
                if (space and not self.space_prev and self.peek_enabled and getattr(self, "trigger", "drag") == "drag"
                        and winsys.file_drag_active()):
                    self.peek.emit()
                elif not space and self.space_prev and self.peek_hold and getattr(self, "trigger", "drag") == "drag":
                    self.peek_up.emit()                # hold to show: let go closes it
                self.space_prev = space
                if self.shake_enabled and not self.shook and self._shake(pos):
                    self.shook = True
                    if winsys.file_drag_active() or False:
                        self.shaken.emit()
                any_drag = False
                for spec in combos:                         # was a longer combination pressed meanwhile?
                    if any(held.get(o) for o in combos if combos[spec] < combos[o]):
                        self.spoiled.add(spec)
                for m, name in keys.items():
                    if name not in combos:
                        continue
                    if name in subset:
                        fire = (not held.get(name) and self.prev.get(name) and name not in self.spoiled)
                    else:
                        fire = held.get(name) and not self.prev.get(name)
                    if not held.get(name) and not self.prev.get(name):
                        self.spoiled.discard(name)
                    if fire and getattr(self, "trigger", "drag") == "drag" and (any_drag or winsys.file_drag_active()):
                        self.tapped.emit(m)
                    if fire or (not held.get(name) and self.prev.get(name)):
                        self.spoiled.discard(name)
        else:
            if self.down_at is not None and self.dragging:
                self.released.emit()
            self.down_at = None
            self.dragging = False
            self.trail = []
            self.shook = False
            self.space_prev = False
        # Trigger on hover / selection: a clean tap of a wheel key (nothing else pressed meanwhile, no click)
        if getattr(self, "trigger", "drag") != "drag":
            clean = getattr(self, "clean", {})
            pv = getattr(self, "peek_vks", [])
            if pv and not set(pv) & hooked:            # File preview follows the same choice
                combos["__peek__"] = set(pv)
                held["__peek__"] = all(winsys.key_down(v) for v in pv)
            else:
                pv = []
            for m, name in list(keys.items()) + ([("peek", "__peek__")] if pv else []):
                vks = combos.get(name)
                if not vks:
                    continue
                hold = m == "peek" and self.peek_hold
                if held.get(name) and not self.prev.get(name):
                    clean[name] = not lmb
                    if hold and clean[name] and not self.dragging and not winsys.other_keys_down(vks):
                        self.idle_tap.emit(m)          # hold to show: open on press…
                        clean[name] = "open"
                elif held.get(name) and clean.get(name) is True and (lmb or winsys.other_keys_down(vks)):
                    clean[name] = False
                elif not held.get(name) and self.prev.get(name):
                    if clean.get(name) == "open":
                        self.peek_up.emit()            # …and close on release
                    elif clean.get(name) and not lmb and not self.dragging and not hold:
                        self.idle_tap.emit(m)
                    clean[name] = False
            self.clean = clean
        self.prev = held

    def _shake(self, pos) -> bool:
        """Three or more quick left-right turns of at least 40 px within 0.8 s."""
        import time
        now = time.monotonic()
        self.trail = [(t, x) for t, x in self.trail if now - t < 0.8] + [(now, pos[0])]
        turns, direction, anchor = 0, 0, self.trail[0][1]
        for _t, x in self.trail[1:]:
            d = x - anchor
            if abs(d) >= 40:
                sign = 1 if d > 0 else -1
                if direction and sign != direction:
                    turns += 1
                direction, anchor = sign, x
            elif direction and (x - anchor) * direction > 0:
                anchor = x                             # still going the same way: follow the far end
        return turns >= 3
