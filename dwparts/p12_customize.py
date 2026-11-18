"""DragWheel: Make it yours: wheel layout, presets, chains, your own slices, where results go, export/import

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


# ============================================================================
# Make it yours: wheel layout, presets, chains, your own slices, where results go, export/import
# ============================================================================
WHEEL_TYPES = [("image", "Image"), ("video", "Video"), ("audio", "Audio"), ("pdf", "PDF"), ("document", "Document"),
               ("spreadsheet", "Spreadsheet"), ("slides", "Slides"), ("archive", "Archive"), ("ebook", "E-book"),
               ("comic", "Comic book"), ("font", "Font"), ("subtitle", "Subtitles"), ("folder", "Folder"),
               ("other", "Other")]


WHEEL_MODES = [("convert", "Convert"), ("tool", "Tools"), ("action", "Actions")]


OUTPUT_MODES = ["next", "folder", "replace", "clipboard"]


def _jload(key, default):
    try:
        v = json.loads(settings().value(key, "") or "null")
        return default if v is None else v
    except (TypeError, ValueError):
        return default


def custom_slices() -> list:
    return _jload("custom_slices", [])


def save_custom_slices(lst):
    settings().setValue("custom_slices", json.dumps(lst, ensure_ascii=False))


def my_slices_file() -> Path:
    return Path(engine.models_dir()).parent / "my-slices.json"


MY_SLICES_TEMPLATE = """// Your own slices for the Actions wheel. Save this file and they appear right away.
// "for": image, video, audio, pdf, document, spreadsheet, slides, archive, ebook, comic, font, subtitle, folder, other
//        or "*" for everything. "each": true runs the command once per file.
// In "command" you can use {file}, {files} (all of them, quoted), {folder}, {name}, {stem}, {ext}.
// Lines starting with // are ignored.
[
  {
    "name": "Open in Paint",
    "for": ["image"],
    "command": "mspaint.exe \\"{file}\\"",
    "each": true
  },
  {
    "name": "Notepad",
    "for": ["document", "subtitle", "other"],
    "command": "notepad.exe \\"{file}\\"",
    "each": true
  }
]
"""


def load_my_slices() -> list:
    f = my_slices_file()
    try:
        text = f.read_text(encoding="utf-8-sig")
    except OSError:
        return []
    text = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("//"))
    try:
        data = json.loads(text)
        return [d for d in data if isinstance(d, dict) and d.get("name") and d.get("command")]
    except ValueError as e:
        winsys.log(f"my-slices.json: {e}")
        return []


def save_my_slices(lst):
    """Write Custom Slices back to my-slices.json (the file stays hand-editable)."""
    f = my_slices_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    head = "\n".join(line for line in MY_SLICES_TEMPLATE.splitlines() if line.startswith("//"))
    f.write_text(head + "\n" + json.dumps(lst, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slice_app(spec):
    """(app path, once per file) when a slice is simply "open these files with an app", else None."""
    import re
    m = re.fullmatch(r'\s*"([^"]+)"\s+(?:"\{file\}"|\{file\}|\{files\})\s*', spec.get("command", ""))
    if m:
        return m.group(1), "{files}" not in spec["command"]
    m = re.fullmatch(r'\s*(\S+)\s+(?:"\{file\}"|\{file\}|\{files\})\s*', spec.get("command", ""))
    if m:
        return m.group(1), "{files}" not in spec["command"]
    return None


def run_my_slice(spec, paths):
    import shlex  # noqa: F401  (quoting is done by hand for Windows)
    import subprocess

    def fill(cmd, files):
        f = Path(files[0])
        return (cmd.replace("{files}", " ".join(f'"{x}"' for x in files)).replace("{file}", str(f))
                .replace("{folder}", str(f.parent)).replace("{name}", f.name).replace("{stem}", f.stem)
                .replace("{ext}", f.suffix.lstrip(".")))
    groups = [[p] for p in paths] if spec.get("each", True) else [paths]
    for g in groups:
        cmd = fill(spec["command"], g)
        winsys.log(f"my slice '{spec['name']}': {cmd}")
        subprocess.Popen(cmd, cwd=str(Path(g[0]).parent), shell=True)


# How the wheels come: the slices most people use, the rest hidden (Settings → Wheel slices shows them all)
DEFAULT_WHEEL_LAYOUT = {
    "convert/image": {"order": ["to_png", "to_webp", "to_heic", "to_avif", "to_tiff", "to_bmp", "to_gif", "to_ico", "to_tga", "to_jp2", "to_icns", "to_pdf", "to_jpg", "to_jpeg"],
                     "hidden": ["to_heic", "to_avif", "to_tiff", "to_bmp", "to_tga", "to_jp2", "to_icns"]},
    "tool/image": {"order": ["compress", "edit", "scan", "rotate", "flip", "gray", "strip", "resize", "removebg", "ocr", "upscale", "sharpen", "watermark", "blurfaces", "zip", "protect_zip", "splitparts"],
                  "hidden": ["rotate", "flip", "gray", "strip", "resize", "splitparts"]},
    "tool/video": {"order": ["compress", "720p", "trim", "mute", "rotate", "fliph", "flipv", "snapshot", "speed", "gif", "social", "ringtone", "transcribe", "zip", "protect_zip", "splitparts"],
                  "hidden": ["compress", "720p", "mute", "speed", "gif", "transcribe", "protect_zip", "splitparts"]},
    "tool/audio": {"order": ["compress", "trim", "normalize", "mono", "fade", "ringtone", "transcribe", "zip", "protect_zip", "splitparts"],
                  "hidden": ["normalize", "mono", "protect_zip", "splitparts"]},
    "tool/pdf": {"order": ["compress", "split", "pages", "rotate", "images", "protect", "arrange", "numbers", "watermark", "sign", "gray", "count", "zip", "protect_zip", "splitparts"],
                "hidden": ["compress", "numbers", "gray", "count", "zip", "protect_zip", "splitparts"]},
    "tool/document": {"order": ["count", "zip", "protect_zip", "splitparts"],
                     "hidden": ["count", "zip", "protect_zip"]},
    "convert/document": {"order": ["to_pdf", "to_odt", "to_rtf", "to_txt", "to_html", "to_docx"],
                        "hidden": ["to_odt"]},
    "convert/spreadsheet": {"order": ["to_csv", "to_tsv", "to_json", "to_html", "to_md", "to_pdf", "to_ods", "to_xlsx"],
                           "hidden": ["to_ods"]},
    "tool/spreadsheet": {"order": ["zip", "protect_zip", "splitparts"],
                        "hidden": []},
    "tool/slides": {"order": ["count", "zip", "protect_zip", "splitparts"],
                   "hidden": []},
    "convert/video": {"order": ["to_mp4", "to_mov", "to_mkv", "to_webm", "to_avi", "to_wmv", "to_hevc", "to_gif", "to_mp3", "to_m4a", "to_mkv_hevc"],
                     "hidden": ["to_webm", "to_avi", "to_gif", "to_m4a"]},
    "convert/audio": {"order": ["to_mp3", "to_m4a", "to_wav", "to_flac", "to_ogg", "to_opus", "to_aiff", "to_wma", "to_ac3"],
                     "hidden": ["to_opus", "to_aiff", "to_ac3"]},
    "convert/pdf": {"order": ["to_docx", "to_docx_flow", "to_png", "to_jpg", "to_txt", "to_md", "to_html", "to_cbz"],
                   "hidden": []},
    "convert/slides": {"order": ["to_pdf", "to_png", "to_jpg", "to_pptx", "to_odp"],
                      "hidden": []},
    "convert/archive": {"order": ["to_zip", "to_7z", "to_rar", "to_tar", "to_tar.gz", "to_tar.bz2", "to_tar.xz"],
                       "hidden": []},
    "convert/ebook": {"order": ["to_pdf", "to_txt", "to_md", "to_html"],
                     "hidden": []},
    "convert/comic": {"order": ["to_pdf", "to_cbz"],
                     "hidden": []},
    "action/*": {"order": ["copy", "path", "move", "copyto", "terminal", "float", "reveal", "openwith", "rename", "hash", "unblock", "phone", "shred", "readqr"],
                "hidden": ["copy", "move", "copyto", "reveal", "openwith", "hash"]},
}


def wheel_layout() -> dict:
    """Your order and hidden slices per wheel and file type; a wheel you haven't changed is as DragWheel comes."""
    return dict(DEFAULT_WHEEL_LAYOUT, **_jload("wheel_layout", {}))


# the files the right-click menus are worked out for (one with few conversions first, so the common ones come too)
_SAMPLE_EXT = {"image": ("tga", "jpg"), "video": ("mkv", "mp4"), "audio": ("aiff", "mp3"), "pdf": ("pdf",),
               "document": ("odt", "docx"), "spreadsheet": ("ods", "xlsx"), "slides": ("odp", "pptx"),
               "archive": ("tar", "zip"), "ebook": ("fb2", "epub"), "comic": ("cb7", "cbz"), "font": ("woff", "ttf"),
               "subtitle": ("ass", "srt")}


def file_menu_spec(app) -> dict:
    """What right-click → DragWheel shows for each kind of file: the same slices as the wheels (your order, without
    the ones you hid). Built for a typical file of each kind; picking one that doesn't fit the file says so."""
    cats = {}
    groups = [("convert", tr("Convert")), ("tool", tr("Tools")), ("action", tr("Actions"))]
    by_cat = {}
    for ext, cat in engine.EXT_CATEGORY.items():
        by_cat.setdefault(cat, []).append(ext)
    plan = [(cat, [f"C:/DragWheel/sample.{e}" for e in _SAMPLE_EXT.get(cat, (by_cat[cat][0],))]) for cat in by_cat]
    plan += [("folder", ["C:/DragWheel/sample folder"]), ("other", ["C:/DragWheel/sample.xyz"])]
    for cat, samples in plan:
        c = {"exts": sorted(by_cat.get(cat, []))}
        for mode, _label in groups:
            seen, items = set(), []
            for smp in samples:
                try:
                    ops = app.ops_for(mode, [smp])
                except Exception as e:
                    winsys.log(f"menu: {cat}/{mode}: {e}")
                    ops = []
                for op in ops:
                    if op.id in seen or op.id == "none" or op.id.startswith("custom:"):
                        continue
                    seen.add(op.id)
                    items.append((op.id, tr(op.label).replace("&", "&&")))
            c[mode] = items
        cats[cat] = c
    return {"open": tr("Open the wheel"), "groups": groups, "cats": cats}


def apply_wheel_layout(mode, category, ops):
    """Your order and hidden slices for this wheel and file type."""
    layouts = wheel_layout()
    lay = layouts.get(f"{mode}/{category}")
    if not lay and mode == "action":
        lay = layouts.get("action/*")                  # Actions set up once for all file types
    if not lay:
        return ops
    hidden = set(lay.get("hidden", []))
    order = {k: i for i, k in enumerate(lay.get("order", []))}
    kept = [o for o in ops if o.id not in hidden] or ops[:1]
    return sorted(kept, key=lambda o: order.get(o.id, 10_000 + ops.index(o)))


def custom_ops_for(mode, paths) -> list:
    """Your presets, chains and own commands that fit these files."""
    cat = engine.category_of(paths)
    out = []
    for spec in custom_slices():
        wheel = "tool" if spec.get("kind") == "chain" else "convert"
        if wheel != mode or spec.get("for", spec.get("kind")) not in (cat, "*"):
            continue
        try:
            op = engine.custom_op(spec, wheel)
            op.spec = spec
            out.append(op)
        except Exception as e:
            winsys.log(f"custom slice: {e}")
    if mode == "action":
        for i, spec in enumerate(load_my_slices()):
            fors = spec.get("for") or ["*"]
            fors = [fors] if isinstance(fors, str) else fors
            if "*" in fors or cat in fors:
                out.append(engine.Op(f"mine:{i}", "✎ " + spec["name"], lambda ps, p, s=spec: run_my_slice(s, ps),
                                     group="action", multi=True))
    return out


def watch_folders() -> list:
    return _jload("watch_folders", [])


def _watch_ops(cat, path=None):
    """What a watch folder can do with a file type: conversions, tools and your presets/chains that need
    no window (questions are answered with their usual defaults)."""
    if path:
        paths = [path]
    else:                                    # every target of the type: ask with two different examples
        seen, out = set(), []
        for ext in {"image": ("png", "jpg"), "video": ("mkv", "mp4"), "audio": ("wav", "mp3"),
                    "document": ("txt", "docx"), "subtitle": ("vtt", "srt")}.get(cat, ("",)):
            for m, o in _watch_ops(cat, engine._fake_path(cat, ext)):
                if (m, o.id) not in seen:
                    seen.add((m, o.id))
                    out.append((m, o))
        return out
    out = []
    for mode, ops in (("convert", engine.conversions(paths)), ("tool", engine.tools(paths))):
        for o in ops + custom_ops_for(mode, paths):
            if o.ui or o.id == "none":
                continue
            out.append((mode, o))
    return out


class FolderWatch(QObject):
    """Watch folders: a file that lands in a chosen folder is converted automatically; results go to a
    'Converted' folder inside it (so they are never picked up again)."""

    def __init__(self, app):
        super().__init__()
        from PySide6.QtCore import QFileSystemWatcher
        self.app = app
        self.fs = QFileSystemWatcher(self)
        self.fs.directoryChanged.connect(self._changed)
        self.known = {}          # folder -> set of names seen
        self.waiting = {}        # path -> (size, stable checks)
        self.done = set()
        self.overwrite = set()   # originals whose result should replace them
        self.timer = QTimer(self, interval=1000, timeout=self._check)
        self.reload()

    def reload(self):
        if self.fs.directories():
            self.fs.removePaths(self.fs.directories())
        self.rules = [r for r in watch_folders() if r.get("on", True) and os.path.isdir(r.get("folder", ""))]
        self.known = {}
        for r in self.rules:
            f = r["folder"]
            self.known[f] = self._names(f)
            self.fs.addPath(f)
        if self.rules:
            self.timer.start()                 # also catches changes the watcher misses (network drives)
        else:
            self.timer.stop()

    @staticmethod
    def _names(folder):
        try:
            return {e.name for e in os.scandir(folder) if e.is_file()}
        except OSError:
            return set()

    def _changed(self, folder):
        self._scan(folder)

    def _scan(self, folder):
        now = self._names(folder)
        new = now - self.known.get(folder, set())
        self.known[folder] = now
        for name in new:
            if name.lower().endswith((".part", ".crdownload", ".tmp", ".download")) or name.startswith(("~$", ".")):
                continue
            self.waiting[os.path.join(folder, name)] = (-1, 0)

    def _check(self):
        for r in self.rules:
            self._scan(r["folder"])
        for path, (size, n) in list(self.waiting.items()):
            try:
                now = os.path.getsize(path)
            except OSError:
                self.waiting.pop(path, None)
                continue
            if now == size and now > 0:
                n += 1
            else:
                n = 0
            if n >= 2:                         # same size for two seconds: finished copying
                self.waiting.pop(path, None)
                try:
                    with open(path, "rb"):
                        pass
                except OSError:
                    self.waiting[path] = (now, 0)
                    continue
                self._run(path)
            else:
                self.waiting[path] = (now, n)

    def _run(self, path):
        if path in self.done:
            return
        folder = os.path.dirname(path)
        cat = engine.category_of([path])
        for r in self.rules:
            if os.path.normcase(r["folder"]) != os.path.normcase(folder) or r.get("cat") not in (cat, "*"):
                continue
            ops = {o.id: (m, o) for m, o in _watch_ops(cat, path)}
            hit = ops.get(r.get("id"))
            if hit is None:
                winsys.log(f"watch folder: {r.get('label')} doesn't apply to {Path(path).name}")
                continue
            mode, op = hit
            if op.model and not engine.model_ready(op.model):
                continue
            self.done.add(path)
            if r.get("save") == "overwrite":
                self.overwrite.add(path)         # result is made in "Converted", then takes the original's place
            out = Path(folder) / tr("Converted")
            out.mkdir(exist_ok=True)
            self.app.out_override[path] = str(out)
            params = {f: (d[0] if isinstance(d, (list, tuple)) and d else d) for f, d in (op.ask or [])}
            if getattr(op, "spec", None):
                params["_spec"] = op.spec
            winsys.log(f"watch folder: {op.id} on {Path(path).name}")
            if op.group == "action":
                try:
                    op.fn([path], params)
                except Exception as e:
                    winsys.log(f"watch folder action: {e}")
            else:
                self.app._start(op, [path], params)


class CustomSliceDialog(QDialog):
    """Add or change a Custom Slice: a name, the app that opens the files, and which files it shows for."""

    def __init__(self, spec=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP} — " + tr("Custom Slices"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
        self.spec, self.old = None, dict(spec or {})
        form = QFormLayout(self)
        self.name = QLineEdit(self.old.get("name", ""))
        self.name.setPlaceholderText(tr("e.g. Open in Photoshop"))
        self.name.setMinimumWidth(340)
        form.addRow(tr("Name"), self.name)
        row = QHBoxLayout()
        self.app_edit = QLineEdit()
        self.app_edit.setPlaceholderText(tr("Choose the app…"))
        row.addWidget(self.app_edit, 1)
        b = QPushButton(tr("Browse…"))
        b.clicked.connect(self._browse)
        row.addWidget(b)
        form.addRow(tr("App"), row)
        self.kind = QComboBox()
        self.kind.addItem(tr("All files"), ["*"])
        for k, label in WHEEL_TYPES:
            self.kind.addItem(tr(label), [k])
        fors = self.old.get("for") or ["*"]
        fors = [fors] if isinstance(fors, str) else list(fors)
        i = self.kind.findData(fors)
        if i < 0:
            self.kind.addItem(", ".join(tr(dict(WHEEL_TYPES).get(f, f)) for f in fors), fors)
            i = self.kind.count() - 1
        self.kind.setCurrentIndex(i)
        form.addRow(tr("Show for"), self.kind)
        self.each = SwitchBox(tr("Open each file in its own window"))
        form.addRow(self.each)
        self.raw = None
        app = slice_app(self.old) if self.old else None
        if app:
            self.app_edit.setText(app[0])
            self.each.setChecked(app[1])
        elif self.old:
            self.raw = self.old.get("command", "")          # a hand-written command: keep it as it is
            self.app_edit.setText(self.raw)
            self.each.setChecked(bool(self.old.get("each", True)))
        else:
            self.each.setChecked(True)
        note = QLabel(tr("The slice appears in the Actions wheel for those files."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        form.addRow(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _browse(self):
        start = self.app_edit.text() if os.path.exists(self.app_edit.text()) else os.environ.get("ProgramFiles", str(Path.home()))
        f, _ = QFileDialog.getOpenFileName(self, tr("Choose the app…"), start,
                                           tr("Apps") + " (*.exe *.bat *.cmd *.lnk);;" + tr("All files") + " (*)")
        if f:
            f = str(Path(f))
            if f.lower().endswith(".lnk"):
                f = winsys.shortcut_target(f) or f
            self.raw = None
            self.app_edit.setText(f)
            if not self.name.text().strip():
                self.name.setText(tr("Open in {app}", app=Path(f).stem))

    def _ok(self):
        name, app = self.name.text().strip(), self.app_edit.text().strip().strip('"')
        if not app:
            self.app_edit.setFocus()
            return
        if not name:
            name = tr("Open in {app}", app=Path(app).stem)
        each = self.each.isChecked()
        if self.raw is not None and app == self.raw.strip().strip('"'):
            cmd = self.raw
        else:
            cmd = f'"{app}" ' + ('"{file}"' if each else "{files}")
        self.spec = {"name": name, "for": self.kind.currentData(), "command": cmd, "each": each}
        self.accept()


class WatchRuleDialog(QDialog):
    """Add a watch folder: which folder, which files, what to do."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP} — " + tr("Auto Convert"))
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        form = QFormLayout(self)
        row = QHBoxLayout()
        self.folder = QLineEdit()
        self.folder.setMinimumWidth(320)
        row.addWidget(self.folder, 1)
        b = QPushButton(tr("Choose…"))
        b.clicked.connect(self._pick)
        row.addWidget(b)
        form.addRow(tr("Folder"), row)
        self.kind = QComboBox()
        for k, label in WHEEL_TYPES:
            if k != "folder":
                self.kind.addItem(tr(label), k)
        form.addRow(tr("When this arrives"), self.kind)
        self.op = QComboBox()
        form.addRow(tr("Do this"), self.op)
        self.save = QComboBox()
        self.save.addItem(tr("Copy"), "copy")
        self.save.addItem(tr("Overwrite original"), "overwrite")
        form.addRow(tr("Save result as"), self.save)
        note = QLabel()
        self.save.currentIndexChanged.connect(lambda _i: note.setText(
            tr("Results go to a “Converted” folder inside it. Files already there are left alone.")
            if self.save.currentData() == "copy" else
            tr("The new file takes the original's place; the original goes to the Recycle Bin. Files already there are left alone.")))
        note.setText(tr("Results go to a “Converted” folder inside it. Files already there are left alone."))
        note.setWordWrap(True)
        note.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        form.addRow(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.kind.currentIndexChanged.connect(self._fill)
        self._fill()
        self.rule = None

    def _pick(self):
        d = QFileDialog.getExistingDirectory(self, tr("Pick a folder"), self.folder.text() or str(Path.home()))
        if d:
            self.folder.setText(str(Path(d)))

    def _fill(self):
        self.op.clear()
        for mode, o in _watch_ops(self.kind.currentData()):
            label = tr("Convert to {fmt}", fmt=tr(o.label)) if mode == "convert" and not o.id.startswith("custom:") else tr(o.label)
            self.op.addItem(label.rstrip("…"), (mode, o.id))

    def _ok(self):
        f = self.folder.text().strip()
        if not f or not os.path.isdir(f) or self.op.currentData() is None:
            self.folder.setFocus()
            return
        mode, oid = self.op.currentData()
        self.rule = {"folder": f, "cat": self.kind.currentData(), "mode": mode, "id": oid,
                     "label": self.op.currentText(), "on": True, "save": self.save.currentData()}
        self.accept()


class WheelPreview(QLabel):
    """The wheel as it will look, drawn by the real Wheel (never shown on its own)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.wheel = Wheel(_APP)
        self.wheel._style = "none"
        self.setMinimumSize(300, 330)
        self.setAlignment(Qt.AlignCenter)

    def show_ops(self, mode, paths, ops, hover=-1):
        w = self.wheel
        w.mode, w.paths = mode, paths
        w.ops = ops or [engine.Op("none", "No conversions" if mode == "convert" else "No tools", lambda *a: None)]
        w.hover = hover if ops else -1
        w._t = 1.0
        img = w.grab()
        dpr = self.devicePixelRatioF() or 1.0
        side = min(self.width(), self.height()) * dpr
        pm = img.scaled(int(side), int(side), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
        self.setPixmap(pm)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.wheel.ops:
            self.show_ops(self.wheel.mode, self.wheel.paths, self.wheel.ops, self.wheel.hover)


class WheelLayoutDialog(QDialog):
    """Pick which slices show on a wheel for a file type, and their order (drag to reorder)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QListWidget, QAbstractItemView
        self.setWindowTitle(f"{APP} — " + tr("Wheel slices"))
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.resize(820, 580)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.mode = QComboBox()
        for k, label in WHEEL_MODES:
            self.mode.addItem(tr(label), k)
        self.kind = QComboBox()
        for k, label in WHEEL_TYPES:
            self.kind.addItem(tr(label), k)
        row.addWidget(QLabel(tr("Wheel")))
        row.addWidget(self.mode, 1)
        row.addWidget(QLabel(tr("For")))
        row.addWidget(self.kind, 1)
        lay.addLayout(row)
        self.list = QListWidget()
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        body = QHBoxLayout()
        body.addWidget(self.list, 1)
        self.preview = WheelPreview()
        body.addWidget(self.preview, 1)
        lay.addLayout(body, 1)
        self._ops_now = []
        self._redraw = QTimer(self, singleShot=True, interval=0, timeout=self._update_preview)
        self.list.model().rowsMoved.connect(lambda *a: self._redraw.start())
        self.list.itemChanged.connect(lambda *a: self._redraw.start())
        self.list.currentRowChanged.connect(lambda *a: self._redraw.start())
        hint = QLabel(tr("Untick a slice to hide it. Drag to change the order — the first ones go at the top of the wheel."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.hexc('dim')};font-size:9pt")
        lay.addWidget(hint)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset)
        bb.button(QDialogButtonBox.Ok).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.button(QDialogButtonBox.Reset).setText(tr("Reset this wheel"))
        bb.accepted.connect(self._save_and_close)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Reset).clicked.connect(self._reset)
        lay.addWidget(bb)
        self.layouts = wheel_layout()
        self._key = None
        self._all_touched = False
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.kind.currentIndexChanged.connect(self._load)
        self._mode_changed()

    def _mode_changed(self):
        """Actions are the same for every type of file, so they can be arranged once for all of them."""
        self.kind.blockSignals(True)
        has_all = self.kind.count() and self.kind.itemData(0) == "*"
        if self.mode.currentData() == "action" and not has_all:
            self.kind.insertItem(0, tr("All file types"), "*")
            self.kind.setCurrentIndex(0)
        elif self.mode.currentData() != "action" and has_all:
            self.kind.removeItem(0)
            self.kind.setCurrentIndex(0)
        self.kind.blockSignals(False)
        self._load()

    def _ops(self, mode, cat):
        cat = "image" if cat == "*" else cat
        paths = [engine._fake_path(cat)] if cat not in ("folder",) else ["C:/example/folder"]
        if mode == "convert":
            ops = engine.conversions(paths)
            # a JPG never offers "JPG", so also ask a second type of the same kind: every format can be arranged
            alt = {"image": "png", "video": "mkv", "audio": "wav", "document": "odt", "slides": "odp",
                   "spreadsheet": "ods", "ebook": "mobi", "comic": "cbr", "font": "otf", "subtitle": "vtt",
                   "archive": "7z"}.get(cat)
            if alt:
                have = {o.id for o in ops}
                for i, o in enumerate(engine.conversions([engine._fake_path(cat, alt)])):
                    if o.id not in have:
                        ops.insert(min(i, len(ops)), o)
                        have.add(o.id)
        elif mode == "tool":
            ops = engine.tools(paths)
        else:
            ops = _APP.actions.ops(paths) if _APP is not None else []
        if _APP is not None:
            ops = ops + [o for o in custom_ops_for(mode, paths) if not o.id.startswith("mine:")]
        return ops

    def _store(self):
        if self._key is None:
            return
        order, hidden = [], []
        for i in range(self.list.count()):
            it = self.list.item(i)
            order.append(it.data(Qt.UserRole))
            if it.checkState() != Qt.Checked:
                hidden.append(it.data(Qt.UserRole))
        new = {"order": order, "hidden": hidden}
        if new == getattr(self, "_shown", None) and self._key not in self.layouts:
            return                                     # only looked at, not changed: nothing to keep
        if self._key == "action/*" and new != self._shown:
            self._all_touched = True
        self.layouts[self._key] = new

    def _load(self):
        from PySide6.QtWidgets import QListWidgetItem
        self._store()
        mode, cat = self.mode.currentData(), self.kind.currentData()
        self._key = f"{mode}/{cat}"
        lay = self.layouts.get(self._key) or (self.layouts.get("action/*", {}) if mode == "action" else {})
        hidden = set(lay.get("hidden", []))
        order = {k: i for i, k in enumerate(lay.get("order", []))}
        ops = self._ops(mode, cat)
        ops = sorted(ops, key=lambda o: order.get(o.id, 10_000 + ops.index(o)))
        self._ops_now = ops
        self.list.blockSignals(True)
        self.list.clear()
        for o in ops:
            it = QListWidgetItem(tr(o.label) + (f"   ·  {tr(o.hint)}" if o.hint else ""))
            it.setData(Qt.UserRole, o.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsDragEnabled)
            it.setCheckState(Qt.Unchecked if o.id in hidden else Qt.Checked)
            self.list.addItem(it)
        self.list.blockSignals(False)
        self._shown = {"order": [o.id for o in ops], "hidden": [o.id for o in ops if o.id in hidden]}
        self._redraw.start()

    def _update_preview(self):
        by_id = {o.id: o for o in self._ops_now}
        shown, hover = [], -1
        cur = self.list.currentRow()
        for i in range(self.list.count()):
            it = self.list.item(i)
            o = by_id.get(it.data(Qt.UserRole))
            if o is None or it.checkState() != Qt.Checked:
                continue
            if i == cur:
                hover = len(shown)
            shown.append(o)
        cat = self.kind.currentData()
        cat = "image" if cat == "*" else cat
        paths = [engine._fake_path(cat)] if cat != "folder" else ["C:/example/folder"]
        self.preview.show_ops(self.mode.currentData(), paths, shown, hover)

    def _reset(self):
        if self._key in DEFAULT_WHEEL_LAYOUT:              # back to how DragWheel comes
            self.layouts[self._key] = json.loads(json.dumps(DEFAULT_WHEEL_LAYOUT[self._key]))
        else:
            self.layouts.pop(self._key, None)
        self._key = None
        self._load()

    def _save_and_close(self):
        self._store()
        if self._all_touched:                          # "All file types" was changed: it wins over per-type ones
            for k in [k for k in self.layouts if k.startswith("action/") and k != "action/*"]:
                self.layouts.pop(k)
        settings().setValue("wheel_layout", json.dumps({k: v for k, v in self.layouts.items() if v.get("hidden") or v.get("order")}))
        if _APP is not None:                             # the right-click menus follow the wheels
            QTimer.singleShot(300, _APP.refresh_file_menus)
        self.accept()


class PresetDialog(QDialog):
    """Make or edit an image or video preset (one slice in the Convert wheel)."""

    def __init__(self, kind, spec=None, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QSlider, QSpinBox
        self.kind = kind
        spec = dict(spec or {})
        self.setWindowTitle(f"{APP} — " + (tr("Image preset") if kind == "image" else tr("Video preset")))
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        form = QFormLayout(self)
        self.name = QLineEdit(spec.get("name", ""))
        self.name.setPlaceholderText(tr("e.g. For the web"))
        form.addRow(tr("Name"), self.name)
        self.fmt = QComboBox()
        for f in (engine.PRESET_IMAGE_FORMATS if kind == "image" else engine.PRESET_VIDEO_FORMATS):
            self.fmt.addItem(f.upper(), f)
        self.fmt.setCurrentIndex(max(0, self.fmt.findData(spec.get("format"))))
        form.addRow(tr("Format"), self.fmt)
        self.q = QSlider(Qt.Horizontal)
        self.q.setRange(10, 100)
        self.q.setValue(int(spec.get("quality", 80 if kind == "image" else 70)))
        ql = QLabel(str(self.q.value()))
        self.q.valueChanged.connect(lambda v: ql.setText(str(v)))
        qrow = QHBoxLayout()
        qrow.addWidget(self.q, 1)
        qrow.addWidget(ql)
        form.addRow(tr("Quality"), qrow)
        if kind == "image":
            self.size = QSpinBox()
            self.size.setRange(0, 20000)
            self.size.setSingleStep(100)
            self.size.setSpecialValueText(tr("Keep the size"))
            self.size.setSuffix(" px")
            self.size.setValue(int(spec.get("max_side", 1920)))
            form.addRow(tr("Longest side at most"), self.size)
            self.strip = QCheckBox(tr("Remove photo details (location, camera…)"))
            self.strip.setChecked(bool(spec.get("strip", True)))
            form.addRow("", self.strip)
        else:
            self.height = QComboBox()
            for h in engine.PRESET_VIDEO_HEIGHTS:
                self.height.addItem(tr("Keep the size") if h == 0 else f"{h}p", h)
            self.height.setCurrentIndex(max(0, self.height.findData(int(spec.get("max_height", 1080)))))
            form.addRow(tr("Picture size at most"), self.height)
            self.mute = QCheckBox(tr("Remove the sound"))
            self.mute.setChecked(bool(spec.get("mute", False)))
            form.addRow("", self.mute)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)
        self.uid = spec.get("uid")

    def spec(self):
        import uuid
        s = {"uid": self.uid or uuid.uuid4().hex[:8], "kind": self.kind, "for": self.kind,
             "name": self.name.text().strip() or tr("Preset"), "format": self.fmt.currentData(), "quality": self.q.value()}
        if self.kind == "image":
            s.update(max_side=self.size.value(), strip=self.strip.isChecked())
            s["hint"] = f"{s['format'].upper()} · {s['quality']}" + (f" · ≤{s['max_side']}px" if s["max_side"] else "")
        else:
            s.update(max_height=self.height.currentData(), mute=self.mute.isChecked())
            s["hint"] = f"{s['format'].upper()}" + (f" · {s['max_height']}p" if s["max_height"] else "")
        return s


class ChainDialog(QDialog):
    """Make a chain: several steps that run one after another as one slice in the Tools wheel."""

    def __init__(self, spec=None, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QListWidget
        spec = dict(spec or {})
        self.setWindowTitle(f"{APP} — " + tr("Chain"))
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.resize(520, 520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.name = QLineEdit(spec.get("name", ""))
        self.name.setPlaceholderText(tr("e.g. Resize, WebP and ZIP"))
        form.addRow(tr("Name"), self.name)
        self.kind = QComboBox()
        for k, label in WHEEL_TYPES:
            if k not in ("folder", "other"):
                self.kind.addItem(tr(label), k)
        self.kind.setCurrentIndex(max(0, self.kind.findData(spec.get("for", "image"))))
        form.addRow(tr("For"), self.kind)
        lay.addLayout(form)
        lay.addWidget(QLabel("<b>" + tr("Steps") + "</b>"))
        self.steps_view = QListWidget()
        lay.addWidget(self.steps_view, 1)
        add = QHBoxLayout()
        self.next_op = QComboBox()
        add.addWidget(self.next_op, 1)
        self.params_box = QWidget()
        self.params_lay = QFormLayout(self.params_box)
        self.params_lay.setContentsMargins(0, 0, 0, 0)
        b_add = QPushButton(tr("Add step"))
        b_add.clicked.connect(self._add)
        add.addWidget(b_add)
        lay.addLayout(add)
        lay.addWidget(self.params_box)
        row = QHBoxLayout()
        b_del = QPushButton(tr("Remove last step"))
        b_del.clicked.connect(self._remove_last)
        row.addWidget(b_del)
        row.addStretch(1)
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.uid = spec.get("uid")
        self.steps = list(spec.get("steps") or [])
        self.kind.currentIndexChanged.connect(lambda _i: (self.steps.clear(), self._refresh()))
        self.next_op.currentIndexChanged.connect(self._show_params)
        self._refresh()

    def _ext_now(self):
        ext = engine._fake_path(self.kind.currentData()).rsplit(".", 1)[1]
        for st in self.steps:
            op = next((o for o in engine.chain_step_ops(ext) if o.id == st["id"] and o.group == st["group"]), None)
            if op is not None:
                ext = engine._step_ext(ext, op)
        return ext

    def _refresh(self):
        self.steps_view.clear()
        for i, st in enumerate(self.steps, 1):
            extra = ", ".join(f"{tr(k)}: {tr(v)}" for k, v in (st.get("params") or {}).items())
            self.steps_view.addItem(f"{i}.  {tr(st['label'])}" + (f"  ({extra})" if extra else ""))
        self.ops_now = engine.chain_step_ops(self._ext_now())
        self.next_op.blockSignals(True)
        self.next_op.clear()
        for o in self.ops_now:
            self.next_op.addItem((tr("Convert to {fmt}", fmt=tr(o.label)) if o.group == "convert" else tr(o.label)), o.id + "|" + o.group)
        self.next_op.blockSignals(False)
        self._show_params()

    def _show_params(self, *_):
        while self.params_lay.rowCount():
            self.params_lay.removeRow(0)
        self.param_edits = {}
        op = self._current()
        if op is None:
            return
        for name, default in op.ask:
            if isinstance(default, (list, tuple)):
                w = QComboBox()
                for opt in default:
                    w.addItem(tr(opt), opt)
            else:
                w = QLineEdit(str(default))
                if name == "Password":
                    w.setEchoMode(QLineEdit.Password)
            self.params_lay.addRow(tr(name), w)
            self.param_edits[name] = w

    def _current(self):
        key = self.next_op.currentData()
        if not key:
            return None
        oid, grp = key.split("|")
        return next((o for o in self.ops_now if o.id == oid and o.group == grp), None)

    def _add(self):
        op = self._current()
        if op is None:
            return
        params = {k: (w.currentData() if isinstance(w, QComboBox) else w.text()) for k, w in self.param_edits.items()}
        self.steps.append({"group": op.group, "id": op.id, "label": op.label if op.group != "convert" else
                           f"Convert to {op.label}", "params": params})
        self._refresh()

    def _remove_last(self):
        if self.steps:
            self.steps.pop()
            self._refresh()

    def _ok(self):
        if len(self.steps) < 2:
            QMessageBox.information(self, APP, tr("A chain needs at least two steps."))
            return
        self.accept()

    def spec(self):
        import uuid
        return {"uid": self.uid or uuid.uuid4().hex[:8], "kind": "chain", "for": self.kind.currentData(),
                "name": self.name.text().strip() or tr("Chain"), "steps": self.steps,
                "hint": " → ".join(tr(s["label"]).replace("…", "") for s in self.steps)[:60]}


# every option in Settings with the value it has when it was never changed — an export carries all of them,
# so importing on another PC sets each one (not only the ones that were changed on this PC)
SETTINGS_DEFAULTS = {
    "language": "", "theme": "system", "check_updates": "true", "tour_at_start": "true", "crash_reports": "false",
    "trigger_mode": "drag", "peek_hold": "false", "shake": "true", "shake_opens": "convert", "scroll": "true",
    "scroll_opens": "convert", "cursor_busy": "true", "wheel_anim": "bloom", "anim_same": "true", "anim_speed": 100,
    "tick_sound": "true", "tick_volume": 70, "sound_pack": "classic", "finish_sound": "true", "finish_anim": "true",
    "media_osd": "true", "media_osd_when": "unfocused", "output_mode": "next", "output_dir": "", "job_mode": "queue",
    "replace_no_ask": "false", "float_autoplay": "true", "float_on_top": "true", "float_ctrl_open": "true",
    "float_link_stops": "true", "float_icon_only": "true", "float_hide_name": "false", "float_keep": "true",
    "float_taskbar": "true",
    "float_repeat": "off", "float_volume": 1.0, "link_quality": "1080p", "share_way": "quick", "share_minutes": 60,
    "sign_mode": "this", "wheel_layout": "{}", "custom_slices": "[]", "watch_folders": "[]",
}


EXPORT_SKIP = ("float_resume", "sticky_notes", "last_update", "geometry", "installer", "first_run_done", "skip_version", "detect_any",
               "hotkey")


def export_settings(path):
    """Settings Config → Export: every option in Settings (also the ones never changed), your keys, wheel slices,
    presets, chains, Custom Slices, Auto Convert folders, saved links, and Windows' start-up and right-click menus."""
    s = settings()
    vals = {k: s.value(k) for k in s.allKeys() if not k.startswith(EXPORT_SKIP)}
    for k, d in SETTINGS_DEFAULTS.items():
        vals.setdefault(k, d)
    for m, k in mode_keys().items():
        vals[f"keys/{m}"] = k
    vals["keys/peek"] = peek_key()
    vals["wheel_anim_close"] = wheel_anim_close()
    data = {"app": APP, "version": VERSION, "settings": vals,
            "windows": {"startup": winsys.startup_enabled(), "menu": winsys.context_menu_enabled(),
                        "sendto": winsys.sendto_enabled(), "full_menu": winsys.full_menu_enabled()}}
    try:
        data["my_slices"] = my_slices_file().read_text(encoding="utf-8")
    except OSError:
        pass
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def import_settings(path) -> int:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("app") != APP or "settings" not in data:
        raise ValueError(tr("This isn't a DragWheel settings file."))
    s = settings()
    for k, v in data["settings"].items():
        s.setValue(k, v)
        keys_changed()
    if data.get("my_slices"):
        my_slices_file().parent.mkdir(parents=True, exist_ok=True)
        my_slices_file().write_text(data["my_slices"], encoding="utf-8")
    s.sync()
    win = data.get("windows") or {}
    try:                                            # start with Windows and the right-click menus, as they were
        if "startup" in win:
            winsys.set_startup(bool(win["startup"]))
        if "menu" in win or "sendto" in win:
            winsys.set_context_menu(bool(win.get("menu", winsys.context_menu_enabled())),
                                    paste_label=tr("Save clipboard image here"), link_label=tr("Paste link to Float"),
                                    float_label=tr("Open Float"), qr_label=tr("Read QR code on screen"),
                                    note_label=tr("New sticky note"), sendto=bool(win.get("sendto", winsys.sendto_enabled())))
        if "full_menu" in win and bool(win["full_menu"]) != winsys.full_menu_enabled():
            winsys.set_full_menu(bool(win["full_menu"]))
            winsys.restart_explorer()
    except Exception as e:
        winsys.log(f"import: Windows settings: {e}")
    return len(data["settings"])


class StallWatch:
    """Writes to the log what DragWheel was busy with whenever it stops responding for a moment (a playing float
    would stutter then), so the cause can be found and moved off the main thread."""
    LIMIT = 0.3

    def __init__(self, parent):
        self.beat = time.monotonic()
        self.main = threading.get_ident()
        self._t = QTimer(parent, interval=50, timeout=self._tick)
        self._t.start()
        threading.Thread(target=self._watch, daemon=True, name="stall-watch").start()

    def _tick(self):
        self.beat = time.monotonic()

    def _watch(self):
        reported, since = None, 0.0
        while True:
            t0 = time.monotonic()
            time.sleep(0.1)
            if time.monotonic() - t0 > 1.0:              # this thread was stopped too: the PC slept or hibernated,
                reported = self.beat                     # which isn't DragWheel freezing
                continue
            beat = self.beat
            lag = time.monotonic() - beat
            if lag > self.LIMIT and reported != beat and time.monotonic() - since > 3:
                frame = sys._current_frames().get(self.main)
                stack = traceback.extract_stack(frame)[-7:] if frame else []
                where = " < ".join(f"{Path(f.filename).stem}:{f.name}:{f.lineno}" for f in reversed(stack)) or "?"
                reported, since = beat, time.monotonic()
                slept = False
                while self.beat == beat and time.monotonic() - beat < 30:     # how long it lasts
                    t1 = time.monotonic()
                    time.sleep(0.05)
                    if time.monotonic() - t1 > 1.0:
                        slept = True
                        break
                if slept:
                    continue
                if len(stack) <= 2:                       # nothing of ours running: Qt or Windows itself was busy
                    where += " (inside Qt/Windows; " + self._context() + ")"
                winsys.log(f"stall {time.monotonic() - beat:.2f}s: {where}")

    @staticmethod
    def _context():
        """What was open, to tell native stalls apart (read without touching Qt objects from this thread)."""
        try:
            fl = list(getattr(_APP, "floats", []) or [])
            kinds = {}
            for f in fl:
                k = ("link " if getattr(f, "link", None) else "") + str(getattr(f, "kind", "?"))
                kinds[k] = kinds.get(k, 0) + 1
            notes = len(getattr(_APP, "notes", []) or [])
            return ", ".join(f"{n}× {k}" for k, n in kinds.items()) + f"; {notes} notes" if fl else f"no floats; {notes} notes"
        except Exception:
            return "?"


class SettingsDialog(QDialog):
    """Changing the language applies immediately (the window rebuilds itself in the new
    language, keeping unsaved edits). Cancel switches the language back."""

    def __init__(self, app: "DragWheelApp", lazy=False):
        super().__init__(None)
        self.app = app
        self._lazy = lazy             # built ahead of time: the pages are put in one at a time, so a playing
        self._pending = []            # float never stops for long
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
            "keys": {m: cb.spec for m, cb in self.key_boxes.items()},
            "detect": self.detect.currentData(),
            "peek_hold": bool(self.peek_hold.currentData()),
            "scroll": self.scroll.isChecked(),
            "out": self.out.text(),
            "out_mode": self.out_mode.currentData(),
            "startup": self.startup.isChecked(),
            "menu": self.menu.isChecked(),
            "sendto": self.sendto.isChecked(),
            "auto_update": self.auto_update.isChecked(),
            "autoplay": self.autoplay.isChecked(),
            "on_top": self.on_top.isChecked(),
            "ctrl_open": self.ctrl_open.isChecked(),
            "media_osd": self.media_osd.isChecked(),
            "icon_only": self.icon_only.isChecked(),
            "taskbar": self.taskbar.isChecked(),
            "sound_pack": self.sound_pack.currentData(),
            "hide_name": self.hide_name.isChecked(),
            "anim": self.anim.currentData(),
            "anim_close": self.anim_close.currentData(),
            "anim_same": self.anim_same.isChecked(),
            "shake_opens": self.shake_opens.currentData(),
            "scroll_opens": self.scroll_opens.currentData(),
            "anim_speed": self.anim_speed.value(),
            "shake": self.shake.isChecked(),
            "tour_start": self.tour_start.isChecked(),
            "cursor_busy": self.cursor_busy.isChecked(),
            "tick_sound": self.tick_sound.isChecked(),
            "tick_volume": self.tick_volume.value(),
            "crash_reports": self.crash_reports.isChecked(),
            "job_mode": self.job_mode.currentData(),
            "link_stops": self.link_stops.isChecked(),
            "finish_anim": self.finish_anim.isChecked(),
            "finish_sound": self.finish_sound.isChecked(),
            "full_menu": self.full_menu.isChecked() if self.full_menu is not None else False,
            "media_osd_when": self.media_osd_when.currentData(),
        }

    def _initial(self) -> dict:
        s = settings()
        return {
            "keys": {**mode_keys(), "peek": peek_key()},
            "detect": trigger_mode(),
            "peek_hold": peek_hold(),
            "scroll": s.value("scroll", "true") == "true",
            "out": s.value("output_dir", ""),
            "out_mode": s.value("output_mode", "folder" if s.value("output_dir", "") else "next"),
            "startup": winsys.startup_enabled(),
            "menu": winsys.context_menu_enabled(),
            "sendto": winsys.sendto_enabled(),
            "auto_update": s.value("check_updates", "true") == "true",
            "autoplay": s.value("float_autoplay", "true") == "true",
            "on_top": s.value("float_on_top", "true") == "true",
            "ctrl_open": s.value("float_ctrl_open", "true") == "true",
            "media_osd": s.value("media_osd", "true") == "true",
            "icon_only": s.value("float_icon_only", "true") == "true",
            "taskbar": s.value("float_taskbar", "true") == "true",
            "keep": s.value("float_keep", "true") == "true",
            "sound_pack": sound_pack(),
            "hide_name": s.value("float_hide_name", "false") == "true",
            "anim": wheel_anim(),
            "anim_close": settings().value("wheel_anim_close", wheel_anim()),
            "anim_same": settings().value("anim_same", "true") == "true",
            "shake_opens": s.value("shake_opens", "convert"),
            "scroll_opens": s.value("scroll_opens", "convert"),
            "anim_speed": int(round(anim_speed() * 100)),
            "shake": s.value("shake", "true") == "true",
            "tour_start": s.value("tour_at_start", "true") == "true",
            "cursor_busy": s.value("cursor_busy", "true") == "true",
            "tick_sound": s.value("tick_sound", "true") == "true",
            "tick_volume": int(s.value("tick_volume", 70)),
            "crash_reports": s.value("crash_reports", "false") == "true",
            "job_mode": s.value("job_mode", "queue"),
            "link_stops": s.value("float_link_stops", "true") == "true",
            "peek": s.value("peek", "true") == "true",
            "finish_anim": s.value("finish_anim", "true") == "true",
            "finish_sound": s.value("finish_sound", "true") == "true",
            "full_menu": winsys.full_menu_enabled(),
            "media_osd_when": s.value("media_osd_when", "unfocused"),
        }

    def _theme_changed(self, _idx):
        code = self.theme_box.currentData()
        if code == theme.mode():
            return
        state = self._state()

        def swap():
            settings().setValue("theme", code)
            self.app.apply_theme()
            self._build(state)
        self._fade_swap(swap)

    def _language_changed(self, _idx):
        code = self.lang.currentData()
        if code == settings().value("language", ""):
            return
        state = self._state()

        def swap():
            settings().setValue("language", code)
            self.app.apply_language()
            self._build(state)
        self._fade_swap(swap)

    def _fade_swap(self, swap):
        """The window fades out, changes language or theme while it can't be seen, then fades back in."""
        if getattr(self, "_swapping", False):
            return
        self._swapping = True
        ms = max(60, int(170 / anim_speed()))
        out = QPropertyAnimation(self, b"windowOpacity", self)
        out.setDuration(ms)
        out.setStartValue(self.windowOpacity())
        out.setEndValue(0.0)
        out.setEasingCurve(QEasingCurve.InCubic)

        def rebuild():
            try:
                swap()
            finally:
                QTimer.singleShot(40, back)                  # once the new page has painted

        def back():
            inn = QPropertyAnimation(self, b"windowOpacity", self)
            inn.setDuration(ms + 60)
            inn.setStartValue(0.0)
            inn.setEndValue(1.0)
            inn.setEasingCurve(QEasingCurve.OutCubic)
            inn.finished.connect(lambda: setattr(self, "_swapping", False))
            inn.start(QPropertyAnimation.DeleteWhenStopped)
        out.finished.connect(lambda: QTimer.singleShot(0, rebuild))   # outside the combo box's signal
        out.start(QPropertyAnimation.DeleteWhenStopped)

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
        self.setStyleSheet(i18n.css(DIALOG_CSS + (SETTINGS_CSS.replace("border-left", "border-right") if i18n.is_rtl()
                                                  else SETTINGS_CSS)))
        self.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
        keep_tab = self.tabs.currentRow() if getattr(self, "tabs", None) is not None else 0
        if self.body is not None:
            self.outer.removeWidget(self.body)
            self.body.deleteLater()
        self.body = QWidget(self)
        self.body.setObjectName("page")
        self.outer.addWidget(self.body)
        root = QVBoxLayout(self.body)
        root.setContentsMargins(12, 8, 12, 12)
        self._finish_pages()
        def scroll(page):                          # long pages scroll instead of growing past the screen
            from PySide6.QtWidgets import QScrollArea
            area = QScrollArea()
            area.setWidgetResizable(True)
            area.setFrameShape(QFrame.NoFrame)
            area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            area.setWidget(page)
            area.setStyleSheet("QScrollArea{background:transparent}")
            area.viewport().setAutoFillBackground(False)
            return area
        self._groups = {}
        old = [self._settings_tab(st), self._everyday_tab(st), self._mine_tab()]
        about = self._about_tab(st)
        from PySide6.QtWidgets import QListWidget, QListWidgetItem, QStackedWidget
        body = QHBoxLayout()
        body.setSpacing(14)
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setFixedWidth(236)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        from PySide6.QtCore import QSize as _QS
        self.nav.setIconSize(_QS(24, 24))
        self.nav.setFont(QFont(i18n.ui_font(), 10, QFont.Bold))
        self.nav.setFocusPolicy(Qt.NoFocus)
        self.stack = QStackedWidget()
        for icon, title, sub, keys in SETTINGS_PAGES:
            if keys is None:
                page = about
            else:
                page = QWidget()
                page.setObjectName("page")
                lay = QVBoxLayout(page)
                lay.setContentsMargins(4, 0, 8, 8)
                lay.setSpacing(4)
                head = QLabel(tr(title))
                head.setObjectName("pagetitle")
                lay.addWidget(head)
                if sub:
                    s_lbl = QLabel(tr(sub))
                    s_lbl.setObjectName("pagesub")
                    s_lbl.setWordWrap(True)
                    lay.addWidget(s_lbl)
                for k in keys:
                    g = self._groups.pop(k, None)
                    if g is not None:
                        lay.addWidget(g)
                lay.addStretch(1)
            it = QListWidgetItem(nav_icon(icon), "  " + tr(title))
            self.nav.addItem(it)
            if self._lazy and not self.isVisible() and self.stack.count() != keep_tab:
                self._pending.append((self.stack.count(), page))
                self.stack.addWidget(QWidget())                  # filled in a moment (_next_page)
            else:
                self.stack.addWidget(scroll(page))
        self._scroll = scroll
        for k in self._groups:                        # (Updates stays on the About page)
            if k != "Updates":
                winsys.log(f"settings: section {k} has no page")
        self._old = old
        if not self._pending:
            for w in old:
                w.deleteLater()
        else:
            QTimer.singleShot(150, self._next_page)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(min(keep_tab, self.nav.count() - 1))
        self.nav.currentRowChanged.connect(lambda _r: self._finish_pages())
        body.addWidget(self.nav)
        body.addWidget(self.stack, 1)
        self.tabs = self.nav                          # keeps the page you were on when the language changes
        root.addLayout(body, 1)

        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.button(QDialogButtonBox.Save).setDefault(True)
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)
        self.adjustSize()
        scr = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        widest = max([self.stack.widget(i).widget().sizeHint().width() for i in range(self.stack.count())
                      if hasattr(self.stack.widget(i), "widget")] + [600])
        self.resize(min(scr.width() - 40, max(900, widest + 236 + 70)), min(scr.height() - 80, 720))

    def _put_page(self, i, page):
        cur = self.stack.currentIndex()
        old = self.stack.widget(i)
        self.stack.insertWidget(i, self._scroll(page))
        self.stack.removeWidget(old)
        old.deleteLater()
        self.stack.setCurrentIndex(cur)

    def _next_page(self):
        """Put in one more page, then wait a little (each takes a moment for Qt to style)."""
        if not self._pending:
            return
        self._put_page(*self._pending.pop(0))
        if self._pending:
            QTimer.singleShot(120, self._next_page)
        else:
            for w in self._old:
                w.deleteLater()

    def showEvent(self, e):
        self._finish_pages()
        super().showEvent(e)

    def _finish_pages(self):
        """Opened (or a page clicked) before every page was in: put the rest in now."""
        while self._pending:
            self._put_page(*self._pending.pop(0))
        if getattr(self, "_old", None):
            for w in self._old:
                w.deleteLater()
            self._old = []

    def _key_taken(self, owner, spec):
        """One key does one thing: a key you give to this wheel is taken off any other."""
        if spec == "None":
            return
        for m, box in self.key_boxes.items():
            if m != owner and box.spec == spec:
                box.set_spec("None")

    def _group(self, key):
        """A section card; its English name says which page of Settings it goes on (SETTINGS_PAGES)."""
        g = QGroupBox(tr(key))
        g.setObjectName("section")
        self._groups[key] = g
        return g

    # ---- Settings tab
    def _settings_tab(self, st):
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 6, 2, 2)

        g0 = self._group("Appearance")
        f0 = QFormLayout(g0)
        self.lang = QComboBox()
        self.lang.addItem(tr("System default"), "")
        for code, native in i18n.LANGUAGES:
            self.lang.addItem(native, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(settings().value("language", ""))))
        self.lang.currentIndexChanged.connect(self._language_changed)
        f0.addRow(tr("App language"), self.lang)
        self.theme_box = QComboBox()
        for code, label in theme.NAMES:
            self.theme_box.addItem(tr(label), code)
        self.theme_box.setCurrentIndex(max(0, self.theme_box.findData(theme.mode())))
        self.theme_box.currentIndexChanged.connect(self._theme_changed)
        f0.addRow(tr("Theme"), self.theme_box)
        lay.addWidget(g0)

        g1 = self._group("Wheel keys")
        f1 = QFormLayout(g1)
        self.key_boxes = {}
        for m in MODES + ["peek"]:
            cap = KeyCapture(st["keys"].get(m, "Space" if m == "peek" else "None"))
            none = QPushButton(tr("None"))
            none.setToolTip(tr("No key for this wheel"))
            none.clicked.connect(lambda _=False, c=cap: c.set_spec("None"))
            row = QHBoxLayout()
            row.addWidget(cap, 1)
            row.addWidget(none)
            f1.addRow(tr(MODE_LABEL[m]) if m != "peek" else tr("File preview"), row)
            self.key_boxes[m] = cap
            cap.changed.connect(lambda spec, me=m: self._key_taken(me, spec))
        hint = QLabel(tr("Click a key box, then press any key or combination, e.g. Shift, Ctrl+Q or F8. "
                         "The mouse's side buttons work too, or hold a key and click (e.g. Ctrl + right click)."))
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        f1.addRow(hint)
        self.peek_hold = QComboBox()
        self.peek_hold.addItem(tr("Press to open, press again to close"), False)
        self.peek_hold.addItem(tr("Hold to show, let go to close"), True)
        self.peek_hold.setCurrentIndex(1 if st["peek_hold"] else 0)
        f1.addRow(tr("File preview opens"), self.peek_hold)
        self.detect = QComboBox()
        for k, label in (("drag", tr("File drag (recommended)")), ("hover", tr("Mouse hover")),
                         ("select", tr("File selection"))):
            self.detect.addItem(label, k)
        self.detect.setCurrentIndex(max(0, self.detect.findData(st["detect"])))
        f1.addRow(tr("Trigger on"), self.detect)
        tip = QLabel(tr("File drag: tap the key while dragging a file. Mouse hover: point at a file in File Explorer "
                        "or on the desktop and tap the key. File selection: select files and tap the key."))
        tip.setObjectName("dim")
        tip.setWordWrap(True)
        f1.addRow("", tip)
        lay.addWidget(g1)

        # Mouse Control: shake, scroll and the busy circle, each with a switch and a line about it
        gm = self._group("Mouse Control")
        vm = QVBoxLayout(gm)
        vm.setSpacing(12)
        opens = [(m, tr(MODE_LABEL[m])) for m in MODES] + [("peek", tr("File preview"))]

        def opens_box(value):
            cb = QComboBox()
            for k, label in opens:
                cb.addItem(label, k)
            cb.setCurrentIndex(max(0, cb.findData(value)))
            return cb
        self.shake = ToggleSwitch(st["shake"])
        self.shake_opens = opens_box(st["shake_opens"])
        vm.addLayout(setting_row(self.shake, tr("Mouse Shake"),
                                 tr("Shake the mouse while dragging a file to open the wheel without pressing a key."),
                                 self.shake_opens))
        self.scroll = ToggleSwitch(st["scroll"])
        self.scroll_opens = opens_box(st["scroll_opens"])
        vm.addLayout(setting_row(self.scroll, tr("Scroll Wheel"),
                                 tr("Scroll the mouse wheel while dragging to open the wheel, then scroll to move between slices."),
                                 self.scroll_opens))
        self.cursor_busy = ToggleSwitch(st["cursor_busy"])
        vm.addLayout(setting_row(self.cursor_busy, tr("Loading Spin"),
                                 tr("A small spinning circle next to the mouse pointer while DragWheel is working.")))
        lay.addWidget(gm)

        ga = self._group("Animations")
        f1 = QFormLayout(ga)
        self.anim = QComboBox()
        self.anim_close = QComboBox()
        for k, label in WHEEL_ANIMS:
            self.anim.addItem(tr(label), k)
            self.anim_close.addItem(tr(label), k)
        self.anim.setCurrentIndex(max(0, self.anim.findData(st["anim"])))
        self.anim_close.setCurrentIndex(max(0, self.anim_close.findData(st["anim_close"])))
        self.anim_same = SwitchBox(tr("Same style for opening and closing"))
        self.anim_same.setChecked(st["anim_same"])
        f1.addRow(self.anim_same)
        f1.addRow(tr("Opening"), self.anim)
        self.close_row_label = QLabel(tr("Closing"))
        f1.addRow(self.close_row_label, self.anim_close)

        def same_changed(on):
            self.anim_close.setVisible(not on)
            self.close_row_label.setVisible(not on)
        self.anim_same.toggled.connect(same_changed)
        same_changed(st["anim_same"])
        from PySide6.QtWidgets import QSlider
        arow = QHBoxLayout()
        self.anim_speed = QSlider(Qt.Horizontal)
        self.anim_speed.setRange(25, 250)
        self.anim_speed.setSingleStep(5)
        self.anim_speed.setPageStep(25)
        self.anim_speed.setValue(st["anim_speed"])
        self.anim_speed.setFixedWidth(150)
        self.anim_speed_lbl = QLabel()
        self.anim_speed_lbl.setMinimumWidth(44)

        def speed_label(v):
            self.anim_speed_lbl.setText(f"{v / 100:.2g}×")
        speed_label(self.anim_speed.value())
        self.anim_speed.valueChanged.connect(speed_label)
        self.anim.currentIndexChanged.connect(lambda _i: self.anim_speed.setEnabled(self.anim.currentData() != "none"))
        self.anim_speed.setEnabled(st["anim"] != "none")
        arow.addWidget(self.anim_speed)
        arow.addWidget(self.anim_speed_lbl)
        arow.addStretch(1)
        f1.addRow(tr("Speed"), arow)
        lay.addWidget(ga)

        g2 = self._group("Output")
        f2 = QFormLayout(g2)
        self.out_mode = QComboBox()
        for key, label in (("next", tr("Next to the original file")), ("folder", tr("In this folder")),
                           ("replace", tr("Replace the original (asks first)")), ("clipboard", tr("Copy to the clipboard"))):
            self.out_mode.addItem(label, key)
        self.out_mode.setCurrentIndex(max(0, self.out_mode.findData(st.get("out_mode", "next"))))
        f2.addRow(tr("Results go"), self.out_mode)
        row = QHBoxLayout()
        self.out = QLineEdit(st["out"])
        self.out.setPlaceholderText(tr("Pick a folder"))
        b = QPushButton(tr("Browse…"))
        b.clicked.connect(lambda: self.out.setText(QFileDialog.getExistingDirectory(self, tr("Output folder")) or self.out.text()))
        row.addWidget(self.out, 1)
        row.addWidget(b)
        self.out_row = QWidget()
        self.out_row.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        f2.addRow("", self.out_row)
        self.out_row.setVisible(self.out_mode.currentData() == "folder")
        self.out_mode.currentIndexChanged.connect(lambda _i: self.out_row.setVisible(self.out_mode.currentData() == "folder"))
        lay.addWidget(g2)

        gf = self._group("Float")
        vf = QVBoxLayout(gf)
        self.autoplay = SwitchBox(tr("Play files and links instantly"))
        self.autoplay.setChecked(st["autoplay"])
        vf.addWidget(self.autoplay)
        self.on_top = SwitchBox(tr("Always on top"))
        self.on_top.setChecked(st["on_top"])
        vf.addWidget(self.on_top)
        self.ctrl_open = SwitchBox(tr("Ctrl+Enter opens a file in Float"))
        self.ctrl_open.setChecked(st["ctrl_open"])
        vf.addWidget(self.ctrl_open)
        self.link_stops = SwitchBox(tr("Stop playing while loading"))
        self.link_stops.setChecked(st["link_stops"])
        vf.addWidget(self.link_stops)
        self.taskbar = SwitchBox(tr("Show in taskbar"))
        self.taskbar.setChecked(st["taskbar"])
        vf.addWidget(self.taskbar)
        self.icon_only = SwitchBox(tr("Remove float border"))
        self.icon_only.setChecked(st["icon_only"])
        vf.addWidget(self.icon_only)
        self.hide_name = SwitchBox(tr("Hide name"))
        self.hide_name.setChecked(st["hide_name"])
        vf.addWidget(self.hide_name)
        self.icon_only.toggled.connect(self.hide_name.setEnabled)
        self.hide_name.setEnabled(st["icon_only"])
        self.keep = SwitchBox(tr("Keep floats open after a restart, until you close them"))
        self.keep.setChecked(st["keep"])
        vf.addWidget(self.keep)
        self.media_osd = SwitchBox(tr("Enable multimedia logos on screen"))
        self.media_osd.setChecked(st["media_osd"])
        vf.addWidget(self.media_osd)
        self.media_osd_when = QComboBox()
        self.media_osd_when.addItem(tr("Only when the float isn't in focus"), "unfocused")
        self.media_osd_when.addItem(tr("All the time"), "always")
        self.media_osd_when.setCurrentIndex(max(0, self.media_osd_when.findData(st["media_osd_when"])))
        self.media_osd_when.setEnabled(st["media_osd"])
        self.media_osd.toggled.connect(self.media_osd_when.setEnabled)
        row = QHBoxLayout()
        row.setContentsMargins(24, 0, 0, 0)
        row.addWidget(self.media_osd_when)
        row.addStretch(1)
        vf.addLayout(row)
        lay.addWidget(gf)

        g3 = self._group("Startup")
        v3 = QVBoxLayout(g3)
        self.startup = SwitchBox(tr("Start {app} when I sign in", app=APP))
        self.startup.setChecked(st["startup"])
        v3.addWidget(self.startup)
        lay.addWidget(g3)

        g = self._group("Right-click menu")
        v = QVBoxLayout(g)
        self.menu = SwitchBox(tr("Add {app} to the context menu", app=APP))
        self.menu.setChecked(st["menu"])
        v.addWidget(self.menu)
        self.sendto = SwitchBox(tr("Add {app} to Send To", app=APP))
        self.sendto.setChecked(st["sendto"])
        v.addWidget(self.sendto)
        if winsys.windows_11():
            self.full_menu = SwitchBox(tr("Use the full right-click menu (like Windows 10)"))
            self.full_menu.setChecked(st["full_menu"])
            v.addWidget(self.full_menu)
            lbl = QLabel(tr("Windows 11's short menu only lets in apps installed as signed packages, so {app} sits under "
                            "“Show more options”. This turns on Windows' full menu for your account, with {app} right in it. "
                            "Explorer restarts to apply it.", app=APP))
            lbl.setWordWrap(True)
            lbl.setObjectName("dim")
            lbl.setContentsMargins(58, 0, 0, 0)
            v.addWidget(lbl)
        else:
            self.full_menu = None
        lay.addWidget(g)
        lay.addStretch(1)
        return page

    # ---- About tab
    # ---- Everyday tab
    def _everyday_tab(self, st):
        from PySide6.QtWidgets import QListWidget
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 6, 2, 2)
        g = self._group("When a job finishes")
        v = QVBoxLayout(g)
        self.finish_anim = SwitchBox(tr("Animate the tick on the notification"))
        self.finish_anim.setChecked(st["finish_anim"])
        v.addWidget(self.finish_anim)
        self.finish_sound = SwitchBox(tr("Enable notification sound"))
        self.finish_sound.setChecked(st["finish_sound"])
        v.addWidget(self.finish_sound)
        from PySide6.QtWidgets import QSlider
        row = QHBoxLayout()
        self.tick_sound = SwitchBox(tr("Enable wheel sound"))
        self.tick_sound.setChecked(st["tick_sound"])
        row.addWidget(self.tick_sound)
        row.addSpacing(12)
        row.addWidget(QLabel(tr("Volume")))
        self.tick_volume = QSlider(Qt.Horizontal)
        self.tick_volume.setRange(0, 100)
        self.tick_volume.setValue(st["tick_volume"])
        self.tick_volume.setFixedWidth(160)
        self.tick_volume.setEnabled(st["tick_sound"])
        self.tick_sound.toggled.connect(self.tick_volume.setEnabled)

        def try_tick():                            # hear it while you choose
            settings().setValue("tick_volume", self.tick_volume.value())
            play_tick(force=True)
        self.tick_volume.sliderReleased.connect(try_tick)
        self.tick_volume.valueChanged.connect(lambda _v: None if self.tick_volume.isSliderDown() else try_tick())
        row.addWidget(self.tick_volume)
        self.tick_volume_lbl = QLabel(f"{self.tick_volume.value()}%")
        self.tick_volume_lbl.setMinimumWidth(44)
        self.tick_volume.valueChanged.connect(lambda v: self.tick_volume_lbl.setText(f"{v}%"))
        self.tick_sound.toggled.connect(self.tick_volume_lbl.setEnabled)
        self.tick_volume_lbl.setEnabled(st["tick_sound"])
        row.addWidget(self.tick_volume_lbl)
        row.addStretch(1)
        v.addLayout(row)
        row = QHBoxLayout()
        row.setContentsMargins(58, 0, 0, 0)
        row.addWidget(QLabel(tr("Sound style")))
        self.sound_pack = QComboBox()
        for k, label in SOUND_PACKS:
            self.sound_pack.addItem(tr(label), k)
        self.sound_pack.setCurrentIndex(max(0, self.sound_pack.findData(st["sound_pack"])))
        self.sound_pack.setMinimumWidth(160)
        row.addWidget(self.sound_pack)
        hear = QPushButton(tr("Listen"))

        def preview():
            pack, vol = self.sound_pack.currentData(), self.tick_volume.value()
            for i, (nm, ms) in enumerate((("open", 0), ("tick", 380), ("tick", 560), ("select", 820), ("close", 1250))):
                QTimer.singleShot(ms, lambda nm=nm: _play_wav(nm, vol * (0.8 if nm in ("open", "close") else 1), pack))
        hear.clicked.connect(preview)
        self.sound_pack.currentIndexChanged.connect(lambda _i: preview())
        row.addWidget(hear)
        self.tick_sound.toggled.connect(self.sound_pack.setEnabled)
        self.tick_sound.toggled.connect(hear.setEnabled)
        self.sound_pack.setEnabled(st["tick_sound"])
        hear.setEnabled(st["tick_sound"])
        row.addStretch(1)
        v.addLayout(row)
        lay.addWidget(g)

        g = self._group("Jobs")
        v = QVBoxLayout(g)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Several jobs")))
        self.job_mode = QComboBox()
        self.job_mode.addItem(tr("One after another (a queue)"), "queue")
        self.job_mode.addItem(tr("All at the same time"), "parallel")
        self.job_mode.setCurrentIndex(max(0, self.job_mode.findData(st["job_mode"])))
        row.addWidget(self.job_mode, 1)
        v.addLayout(row)
        lay.addWidget(g)

        g = self._group("Auto Convert")
        v = QVBoxLayout(g)
        lbl = QLabel(tr("Anything that lands in these folders is converted by itself, e.g. every HEIC photo in Downloads becomes a JPG."))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        self.watch_list = QListWidget()
        self.watch_list.setMinimumHeight(70)
        self.watch_list.setMaximumHeight(130)
        v.addWidget(self.watch_list)
        row = QHBoxLayout()
        b = QPushButton(tr("Add…"))
        b.clicked.connect(self._add_watch)
        row.addWidget(b)
        b = QPushButton(tr("Remove"))
        b.clicked.connect(self._remove_watch)
        row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        lay.addWidget(g)
        self._fill_watch()


        g = self._group("Command line")
        v = QVBoxLayout(g)
        lbl = QLabel(tr("Use DragWheel in Command Prompt or in your own scripts, e.g. "
                        "<b>dragwheel convert photo.heic --to jpg</b>. The button opens a Command Prompt in Downloads "
                        "with the list of commands."))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        b = QPushButton(tr("Open a Command Prompt"))
        b.clicked.connect(winsys.open_cli_window)
        v.addWidget(b, 0, Qt.AlignLeft)
        lay.addWidget(g)

        g = self._group("Help")
        v = QVBoxLayout(g)
        row = QHBoxLayout()
        self.tour_start = SwitchBox(tr("Show the welcome tour every time DragWheel starts"))
        self.tour_start.setChecked(st["tour_start"])
        row.addWidget(self.tour_start)
        row.addStretch(1)
        b = QPushButton(tr("Show the quick tour again"))
        b.clicked.connect(lambda: self.app.show_tour(parent=self))
        row.addWidget(b)
        v.addLayout(row)
        self.crash_reports = SwitchBox(tr("When something goes wrong, offer to send a crash report (you see it first)"))
        self.crash_reports.setChecked(st["crash_reports"])
        v.addWidget(self.crash_reports)
        row = QHBoxLayout()
        row.addStretch(1)
        b = QPushButton(tr("Open the log"))
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(winsys.log_path()))))
        row.addWidget(b)
        b = QPushButton(tr("Show the log folder"))
        b.clicked.connect(lambda: winsys.reveal([str(winsys.log_path())]))
        row.addWidget(b)
        v.addLayout(row)
        lay.addWidget(g)
        lay.addStretch(1)
        return page

    def _fill_watch(self):
        self.watch_list.clear()
        for r in watch_folders():
            kind = dict(WHEEL_TYPES).get(r.get("cat"), r.get("cat", ""))
            how = tr("Overwrite original") if r.get("save") == "overwrite" else tr("Copy")
            self.watch_list.addItem(f"{r.get('folder')}   ·   {tr(kind)} → {r.get('label')}   ·   {how}")

    def _add_watch(self):
        d = WatchRuleDialog(self)
        if d.exec() == QDialog.Accepted and d.rule:
            rules = watch_folders() + [d.rule]
            settings().setValue("watch_folders", json.dumps(rules, ensure_ascii=False))
            self._fill_watch()
            self.app.watch.reload()

    def _remove_watch(self):
        i = self.watch_list.currentRow()
        rules = watch_folders()
        if 0 <= i < len(rules):
            rules.pop(i)
            settings().setValue("watch_folders", json.dumps(rules, ensure_ascii=False))
            self._fill_watch()
            self.app.watch.reload()

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
        gh = QPushButton("⭐  " + tr("Star on GitHub"))
        gh.setObjectName("link")
        gh.setCursor(Qt.PointingHandCursor)
        gh.setToolTip(tr("A star helps other people find DragWheel") + "\n" + updater.REPO_URL)
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
        g4 = self._group("Updates")
        v4 = QVBoxLayout(g4)
        self.auto_update = SwitchBox(tr("Check for updates automatically (once a day)"))
        self.auto_update.setChecked(st["auto_update"])
        v4.addWidget(self.auto_update)
        row4 = QHBoxLayout()
        last = float(settings().value("last_update_check", 0) or 0)
        import time as _t
        if last:
            lt = _t.localtime(last)
            hour = lt.tm_hour % 12 or 12
            when = f"{_t.strftime('%Y-%m-%d', lt)}  {hour}:{lt.tm_min:02d} {tr('AM') if lt.tm_hour < 12 else tr('PM')}"
        else:
            when = tr("never")
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

    # ---- Make it yours tab (changes here are saved straight away)
    def _mine_tab(self):
        from PySide6.QtWidgets import QListWidget
        page = QWidget()
        page.setObjectName("page")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 6, 2, 2)
        g = self._group("Wheel slices")
        v = QVBoxLayout(g)
        lbl = QLabel(tr("Choose which slices each wheel shows and in what order."))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        b = QPushButton(tr("Choose slices…"))
        b.clicked.connect(lambda: WheelLayoutDialog(self).exec())
        v.addWidget(b, 0, Qt.AlignLeft)
        lay.addWidget(g)

        g = self._group("Custom Slices")
        v = QVBoxLayout(g)
        lbl = QLabel(tr("Open files with any app right from the Actions wheel — pick the app and the files it's for."))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        self.mine_list = QListWidget()
        self.mine_list.setFixedHeight(84)
        self.mine_list.itemDoubleClicked.connect(lambda _it: self._edit_mine())
        v.addWidget(self.mine_list)
        row = QHBoxLayout()
        for label, fn in ((tr("Add…"), lambda: self._edit_mine(new=True)), (tr("Edit"), self._edit_mine),
                          (tr("Remove"), self._remove_mine)):
            bt = QPushButton(label)
            bt.clicked.connect(fn)
            row.addWidget(bt)
        row.addStretch(1)
        bt = QPushButton(tr("Advanced…"))
        bt.setToolTip(tr("Edit the slices file by hand (commands with {file}, {folder} and more)"))
        bt.clicked.connect(self._edit_my_slices)
        row.addWidget(bt)
        v.addLayout(row)
        lay.addWidget(g)
        self._fill_mine()

        g = self._group("Presets and chains")
        v = QVBoxLayout(g)
        lbl = QLabel(tr("A preset is your favourite settings as one slice in Convert (e.g. WebP · quality 80 · max 1920 px). "
                        "A chain runs several steps as one slice in Tools (e.g. resize → WebP → ZIP)."))
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        self.custom_list = QListWidget()
        self.custom_list.setFixedHeight(84)
        self.custom_list.itemDoubleClicked.connect(lambda _it: self._edit_custom())
        v.addWidget(self.custom_list)
        row = QHBoxLayout()
        for label, fn in ((tr("New image preset"), lambda: self._new_custom("image")),
                          (tr("New video preset"), lambda: self._new_custom("video")),
                          (tr("New chain"), lambda: self._new_custom("chain")),
                          (tr("Edit"), self._edit_custom), (tr("Delete"), self._delete_custom)):
            bt = QPushButton(label)
            bt.clicked.connect(fn)
            row.addWidget(bt)
        v.addLayout(row)
        lay.addWidget(g)
        self._fill_custom()


        g = self._group("Settings Config")
        row = QHBoxLayout(g)
        b = QPushButton(tr("Export settings…"))
        b.clicked.connect(self._export)
        row.addWidget(b)
        b = QPushButton(tr("Import settings…"))
        b.clicked.connect(self._import)
        row.addWidget(b)
        b = QPushButton(tr("Restore defaults…"))
        b.clicked.connect(self._restore_defaults)
        row.addWidget(b)
        row.addStretch(1)
        lay.addWidget(g)
        lay.addStretch(1)
        return page

    def _fill_custom(self):
        from PySide6.QtWidgets import QListWidgetItem
        self.custom_list.clear()
        kinds = {"image": tr("Image preset"), "video": tr("Video preset"), "chain": tr("Chain")}
        for spec in custom_slices():
            it = QListWidgetItem(f"★ {spec.get('name')}   —   {kinds.get(spec.get('kind'), '')}"
                                 + (f"  ·  {spec.get('hint')}" if spec.get("hint") else ""))
            it.setData(Qt.UserRole, spec.get("uid"))
            self.custom_list.addItem(it)

    def _new_custom(self, kind, spec=None):
        dlg = ChainDialog(spec, self) if kind == "chain" else PresetDialog(kind, spec, self)
        if dlg.exec() != QDialog.Accepted:
            return
        new = dlg.spec()
        lst = [x for x in custom_slices() if x.get("uid") != new["uid"]]
        if spec:
            idx = next((i for i, x in enumerate(custom_slices()) if x.get("uid") == new["uid"]), len(lst))
            lst.insert(idx, new)
        else:
            lst.append(new)
        save_custom_slices(lst)
        self._fill_custom()

    def _edit_custom(self):
        it = self.custom_list.currentItem()
        if it is None:
            return
        spec = next((x for x in custom_slices() if x.get("uid") == it.data(Qt.UserRole)), None)
        if spec:
            self._new_custom(spec.get("kind"), spec)

    def _delete_custom(self):
        it = self.custom_list.currentItem()
        if it is None:
            return
        save_custom_slices([x for x in custom_slices() if x.get("uid") != it.data(Qt.UserRole)])
        self._fill_custom()

    def _fill_mine(self):
        self.mine_list.clear()
        for spec in load_my_slices():
            fors = spec.get("for") or ["*"]
            fors = [fors] if isinstance(fors, str) else fors
            kinds = tr("All files") if "*" in fors else ", ".join(tr(dict(WHEEL_TYPES).get(f, f)) for f in fors)
            app = slice_app(spec)
            how = Path(app[0]).stem if app else spec["command"]
            self.mine_list.addItem(f"{spec['name']}   ·   {kinds}   ·   {how}")

    def _edit_mine(self, new=False):
        lst = load_my_slices()
        i = self.mine_list.currentRow()
        if not new and not (0 <= i < len(lst)):
            return
        d = CustomSliceDialog(None if new else lst[i], self)
        if d.exec() == QDialog.Accepted and d.spec:
            if new:
                lst.append(d.spec)
            else:
                lst[i] = d.spec
            save_my_slices(lst)
            self._fill_mine()

    def _remove_mine(self):
        lst = load_my_slices()
        i = self.mine_list.currentRow()
        if 0 <= i < len(lst):
            lst.pop(i)
            save_my_slices(lst)
            self._fill_mine()

    def _edit_my_slices(self):
        f = my_slices_file()
        if not f.exists():
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(MY_SLICES_TEMPLATE, encoding="utf-8")
        import subprocess
        subprocess.Popen(["notepad.exe", str(f)])

    def _export(self):
        f, _ = QFileDialog.getSaveFileName(self, tr("Export settings…"), str(Path.home() / "DragWheel settings.json"),
                                           "JSON (*.json)")
        if f:
            export_settings(f)
            QMessageBox.information(self, APP, tr("Settings saved to {file}", file=f))

    # what Restore defaults keeps: things you made or played, not preferences
    KEEP_ON_RESET = ("first_run_done", "installer", "InstallerLanguage", "last_update_check", "skip_version", "float_links", "float_recent",
                     "float_pins", "float_resume", "recent_results", "custom_slices", "share_links", "language")

    def _restore_defaults(self):
        if QMessageBox.question(self, APP, tr("Put every setting back to how DragWheel comes? Your saved links, "
                                              "presets, chains and your own slices are kept.")) != QMessageBox.Yes:
            return
        s = settings()
        keep = {k: s.value(k) for k in self.KEEP_ON_RESET if s.contains(k)}
        s.clear()
        for k, v in keep.items():
            s.setValue(k, v)
        keys_changed()
        s.sync()
        winsys.log("settings restored to defaults")
        self.app.apply_language()
        self.app.apply_theme()
        self.app.watcher.refresh_settings()
        QDialog.reject(self)
        QTimer.singleShot(150, self.app.show_settings)    # open again, now showing the defaults

    def _import(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("Import settings…"), str(Path.home()), "JSON (*.json)")
        if not f:
            return
        try:
            n = import_settings(f)
        except Exception as e:
            QMessageBox.warning(self, APP, str(e))
            return
        QMessageBox.information(self, APP, tr("Imported {n} settings. Some take effect after DragWheel restarts.", n=n))
        self.app.apply_language()
        self.app.apply_theme()
        self.app.watcher.refresh_settings()
        try:
            self.app.watch.reload()                    # Auto Convert folders
            self.app._build_tray_menu()
        except Exception as e:
            winsys.log(f"import: {e}")
        QDialog.reject(self)                       # close without undoing the imported language/theme

    def save(self):
        keys = {m: cb.spec for m, cb in self.key_boxes.items()}
        used = [k for k in keys.values() if k != "None"]
        if len(set(used)) < len(used):
            QMessageBox.warning(self, APP, tr("Each wheel and File preview need a different key."))
            return
        if keys["convert"] == "None" and not self.shake.isChecked() and not self.scroll.isChecked() \
                and all(keys[m] == "None" for m in MODES):
            QMessageBox.warning(self, APP, tr("With no wheel keys, turn on Shake (Everyday tab) or scrolling, "
                                              "or the wheel can only open from the right-click menu."))
        s = settings()
        for m, k in keys.items():
            s.setValue(f"keys/{m}", k)
        keys_changed()
        s.setValue("trigger_mode", self.detect.currentData())
        s.setValue("peek_hold", "true" if self.peek_hold.currentData() else "false")
        s.setValue("detect_any", 0)
        mode = self.out_mode.currentData()
        s.setValue("output_mode", mode)
        s.setValue("output_dir", self.out.text().strip() if mode == "folder" else "")
        s.setValue("hotkey", "false")                    # replaced by "Trigger on: file selection"
        s.setValue("scroll", "true" if self.scroll.isChecked() else "false")
        s.setValue("check_updates", "true" if self.auto_update.isChecked() else "false")
        s.setValue("float_autoplay", "true" if self.autoplay.isChecked() else "false")
        s.setValue("float_on_top", "true" if self.on_top.isChecked() else "false")
        s.setValue("float_ctrl_open", "true" if self.ctrl_open.isChecked() else "false")
        s.setValue("media_osd", "true" if self.media_osd.isChecked() else "false")
        s.setValue("float_icon_only", "true" if self.icon_only.isChecked() else "false")
        s.setValue("float_hide_name", "true" if self.hide_name.isChecked() else "false")
        keys_changed()
        tb_changed = (s.value("float_taskbar", "true") == "true") != self.taskbar.isChecked()
        s.setValue("float_taskbar", "true" if self.taskbar.isChecked() else "false")
        s.setValue("float_keep", "true" if self.keep.isChecked() else "false")
        for w in getattr(self.app, "floats", []):
            if tb_changed:
                w.set_taskbar(self.taskbar.isChecked())
            w.update()
        s.setValue("wheel_anim", self.anim.currentData())
        s.setValue("wheel_anim_close", self.anim_close.currentData())
        s.setValue("anim_same", "true" if self.anim_same.isChecked() else "false")
        s.setValue("shake_opens", self.shake_opens.currentData())
        s.setValue("scroll_opens", self.scroll_opens.currentData())
        s.setValue("anim_speed", self.anim_speed.value())
        s.setValue("job_mode", self.job_mode.currentData())
        s.setValue("tick_volume", self.tick_volume.value())
        s.setValue("sound_pack", self.sound_pack.currentData())
        s.setValue("peek", "false" if keys.get("peek", "None") == "None" else "true")
        for key, box in (("shake", self.shake), ("finish_anim", self.finish_anim),
                         ("finish_sound", self.finish_sound), ("tour_at_start", self.tour_start),
                         ("cursor_busy", self.cursor_busy), ("float_link_stops", self.link_stops),
                         ("tick_sound", self.tick_sound), ("crash_reports", self.crash_reports)):
            s.setValue(key, "true" if box.isChecked() else "false")
        if self.full_menu is not None and self.full_menu.isChecked() != winsys.full_menu_enabled():
            try:
                winsys.set_full_menu(self.full_menu.isChecked())
                winsys.restart_explorer()
            except Exception as e:
                winsys.log(f"full menu: {e}")
        s.setValue("media_osd_when", self.media_osd_when.currentData())
        self.app.watcher.refresh_settings()
        engine.OUTPUT_DIR = (self.out.text().strip() or None) if mode == "folder" else None
        s.setValue("language", self.lang.currentData())
        lcid = INSTALLER_LANG_IDS.get(self.lang.currentData())
        if lcid:
            s.setValue("InstallerLanguage", str(lcid))     # the next Setup offers the same language first
        s.setValue("theme", self.theme_box.currentData())
        try:
            winsys.set_startup(self.startup.isChecked())
            winsys.set_context_menu(self.menu.isChecked(), paste_label=tr("Save clipboard image here"), link_label=tr("Paste link to Float"),
                                    float_label=tr("Open Float"), qr_label=tr("Read QR code on screen"),
                                    note_label=tr("New sticky note"), sendto=self.sendto.isChecked())
        except Exception as e:
            QMessageBox.warning(self, APP, tr("Couldn't update Windows integration:") + f"\n{e}")
        self.accept()
