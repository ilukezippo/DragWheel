"""DragWheel: App

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


# ============================================================================
# App
# ============================================================================
def asset(name) -> str:
    return str(Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets" / name)


def browser_extension_dir() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "browser-extension"


def _browser_exes() -> list:
    """Installed browsers: [(name, exe, extensions page)]."""
    out = []
    if not winsys.IS_WIN:
        return out
    import winreg
    for name, exe, page in (("Edge", "msedge.exe", "edge://extensions"), ("Chrome", "chrome.exe", "chrome://extensions"),
                            ("Brave", "brave.exe", "brave://extensions"),
                            ("Firefox", "firefox.exe", "about:debugging#/runtime/this-firefox")):
        path = None
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                    path = winreg.QueryValueEx(k, "")[0]
                    break
            except OSError:
                continue
        if path and os.path.exists(path.strip('"')):
            out.append((name, path.strip('"'), page))
    return out


class BrowserSetup(FrontDialog):
    """Tray → Add DragWheel to your browser: the extension comes with DragWheel; three steps put it in Edge,
    Chrome or Brave (Firefox: for this session). Browsers only install store extensions by themselves."""

    def __init__(self):
        super().__init__(None)
        from PySide6.QtWidgets import QLayout
        self.setWindowTitle(f"{APP} — " + tr("Browser extension"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.setAttribute(Qt.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        self.header(lay, tr("Add DragWheel to your browser"),
                    tr("Right-click any video or link → Play in DragWheel Float. Right-click any picture → "
                       "Save image as PNG, JPG, WebP and more."))
        import bridge
        if bridge.CHROME_LIVE:
            self._store_page(lay)
            return
        folder = str(browser_extension_dir())
        steps = QLabel("<ol style='margin-left:-20px'>"
                       f"<li>{tr('Open your browser’s extensions page (a button below).')}</li>"
                       f"<li>{tr('Turn on Developer mode.')}</li>"
                       f"<li>{tr('Click Load unpacked and choose the DragWheel extension folder (Copy folder path, then paste it in the window that opens).')}</li>"
                       "</ol>")
        steps.setWordWrap(True)
        steps.setFixedWidth(QR_W + 60)
        lay.addWidget(steps)
        path = QLabel(folder)
        path.setObjectName("sub")
        path.setWordWrap(True)
        path.setFixedWidth(QR_W + 60)
        path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(path)
        copy = QPushButton(tr("Copy folder path"))
        copy.setObjectName("primary")
        copy.clicked.connect(lambda: (QGuiApplication.clipboard().setText(folder), copy.setText(tr("Copied"))))
        show = QPushButton(tr("Show the folder"))
        show.clicked.connect(lambda: winsys.reveal(str(Path(folder) / "manifest.json")))
        self.buttons(lay, copy, show)
        found = _browser_exes()
        row = []
        for name, exe, page in found:
            if name == "Firefox" and bridge.FIREFOX_LIVE:   # (Firefox gets the store button below)
                continue
            b = QPushButton(tr("Open {browser}", browser=name))
            b.clicked.connect(lambda _=False, e=exe, pg=page: self._open(e, pg))
            row.append(b)
        if row:
            self.buttons(lay, *row)
        if bridge.FIREFOX_LIVE:                             # Firefox: from Firefox Add-ons, one click
            fox = QPushButton(tr("Firefox: Add from Firefox Add-ons"))
            fox.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(bridge.FIREFOX_STORE_URL)))
            self.buttons(lay, fox)
        else:
            note = QLabel(tr("Firefox: on the page that opens, click Load Temporary Add-on and pick manifest.json "
                             "in that folder (Firefox keeps it until it closes)."))
            note.setObjectName("note")
            note.setWordWrap(True)
            note.setFixedWidth(QR_W + 60)
            lay.addWidget(note)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        self.buttons(lay, close)

    def _store_page(self, lay):
        """Once the stores publish it: DragWheel has already offered it to the browsers (like IDM), so this only
        says what the browser shows, with the store pages for anyone who removed it or uses another browser."""
        import bridge
        steps = QLabel("<ol style='margin-left:-20px'>"
                       f"<li>{tr('Close your browser and open it again.')}</li>"
                       f"<li>{tr('It says DragWheel for Browser was added: click Turn on extension (Enable in Firefox).')}</li>"
                       "</ol>")
        steps.setWordWrap(True)
        steps.setFixedWidth(QR_W + 60)
        lay.addWidget(steps)
        note = QLabel(tr("Didn't see it, or using another browser? Add it from your browser's store:"))
        note.setObjectName("note")
        note.setWordWrap(True)
        note.setFixedWidth(QR_W + 60)
        lay.addWidget(note)
        chrome = QPushButton(tr("Chrome, Edge, Brave, Opera"))
        chrome.setObjectName("primary")
        chrome.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(bridge.CHROME_STORE_URL)))
        fox = QPushButton(tr("Firefox"))
        fox.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(bridge.FIREFOX_STORE_URL)))
        self.buttons(lay, chrome, fox)
        close = QPushButton(tr("Close"))
        close.clicked.connect(self.close)
        self.buttons(lay, close)

    def _open(self, exe, page):
        import subprocess
        try:
            subprocess.Popen([exe, page], close_fds=True)
        except OSError as e:
            winsys.log(f"browser setup: {e}")


_ICON = None


class StarDialog(FrontDialog):
    """"Enjoying DragWheel?": asks once (after 20 jobs that worked) for a star on GitHub. In the middle of the
    screen, on top, but it never blocks anything and closes with Esc."""

    def __init__(self, app):
        super().__init__(None)
        from PySide6.QtWidgets import QLayout
        self.app = app
        self.setWindowTitle(APP)
        self.setWindowIcon(app_icon())
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        lay.setContentsMargins(28, 24, 28, 22)
        lay.setSpacing(10)
        pic = QLabel()
        pm = QPixmap(asset("dragwheel.png"))
        if not pm.isNull():
            pic.setPixmap(pm.scaled(84, 84, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        pic.setAlignment(Qt.AlignCenter)
        lay.addWidget(pic)
        title = QLabel(tr("Enjoying DragWheel?"))
        title.setObjectName("title")
        title.setAlignment(Qt.AlignCenter)
        lay.addWidget(title)
        body = QLabel(tr("A star on GitHub helps other people find it. It's free and takes a second."))
        body.setObjectName("sub")
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignCenter)
        body.setFixedWidth(380)
        lay.addWidget(body, 0, Qt.AlignHCenter)
        lay.addSpacing(6)
        star = QPushButton("⭐  " + tr("Star on GitHub"))
        star.setObjectName("primary")
        star.setDefault(True)
        star.setMinimumHeight(40)
        star.setCursor(Qt.PointingHandCursor)
        star.clicked.connect(self._star)
        lay.addWidget(star)
        later = QPushButton(tr("Maybe later"))
        later.clicked.connect(self._later)
        no = QPushButton(tr("No thanks"))
        no.clicked.connect(self.reject)
        self.buttons(lay, later, no)

    def showEvent(self, e):
        super().showEvent(e)
        scr = (QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()).availableGeometry()
        self.adjustSize()
        self.move(scr.center() - self.rect().center())
        winsys.log("star request shown")

    def _star(self):
        QDesktopServices.openUrl(QUrl(updater.REPO_URL))
        winsys.log("star request: opened GitHub")
        self.accept()

    def _later(self):
        s = settings()
        try:
            n = int(s.value("jobs_done", 0) or 0)
        except (TypeError, ValueError):
            n = 0
        if s.value("star_later", "") != "1":          # asks once more, 50 jobs later; after that never again
            s.setValue("star_later", "1")
            s.setValue("star_asked", "later")
            s.setValue("star_again_at", n + 50)
        self.accept()


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
        global _APP
        _APP = self
        self.floats = []
        self.out_override = {}           # temp file -> folder its results go to (clipboard "save here")
        self._media_down = {}
        self._media_timer = QTimer(self, interval=60, timeout=self._media_tick)
        self._media_timer.start()
        self.wheel = Wheel(self)
        self.toast = ToastManager()
        self.running = set()
        self.waiting = []                # jobs in line (Settings → one at a time)
        engine.OUTPUT_DIR = (settings().value("output_dir", "") or None) \
            if settings().value("output_mode", "folder") == "folder" else None

        self.watcher = DragWatcher()
        self.watcher.tapped.connect(self.on_tap)
        self.watcher.released.connect(self.on_release)
        self.watcher.hotkey.connect(self.on_hotkey)
        self.watcher.idle_tap.connect(self.on_idle_tap)
        self.watcher.moved.connect(self.on_drag_move)
        self.watcher.scrolled.connect(self.on_scroll)
        self.watcher.ctrl_open.connect(self.on_ctrl_open)
        self.watcher.cancelled.connect(self.on_drag_cancel)
        self.watcher.peek.connect(self.on_peek)
        self.watcher.volume_key.connect(self.on_volume_key, Qt.QueuedConnection)
        self.watcher.shaken.connect(self.on_shake)
        self.watcher.released.connect(self._close_peek)
        self.watcher.peek_up.connect(self._peek_let_go)
        self.watcher.click_drag.connect(self.on_click_drag)
        self.watcher.start()
        self._peek = None
        self._peek_held = False
        self.watch = FolderWatch(self)
        try:
            _tick_effect()                       # load the click sounds now
            _tick_effect("select")
        except Exception as e:
            winsys.log(f"tick sound: {e}")
        self.cursor_busy = CursorBusy()
        self._busy_timer = QTimer(self, interval=250, timeout=self._update_cursor_busy)
        self._busy_timer.start()

        self.pending: list[str] = []
        self.pending_timer = QTimer(self, singleShot=True, interval=600, timeout=self._flush_pending)

        self.tray = QSystemTrayIcon(app_icon())
        self.tray.activated.connect(lambda r: self.show_settings() if r == QSystemTrayIcon.Trigger else None)
        self._build_tray_menu()
        self.tray.show()
        self._update_jobs = set()
        QTimer.singleShot(8000, self._auto_update_check)
        QTimer.singleShot(150, self.restore_pinned_floats)
        QTimer.singleShot(400, self.restore_notes)
        self.qapp.commitDataRequest.connect(self._session_ending)     # Windows signing out / restarting
        self.predownload()
        self._prebuild_settings(6000)
        QTimer.singleShot(3000, refresh_clouds)
        QTimer.singleShot(5000, self._register_browser_bridge)
        QTimer.singleShot(7000, self.refresh_file_menus)
        winsys.on_menu_changed = lambda: QTimer.singleShot(300, self.refresh_file_menus)
        self._stall_watch = StallWatch(self)
        QApplication.instance().aboutToQuit.connect(self._end_shares)
        self._cloud_timer = QTimer(self, interval=10 * 60 * 1000, timeout=clean_cloud_shares)
        self._cloud_timer.start()
        QTimer.singleShot(20000, clean_cloud_shares)

    def restore_pinned_floats(self):
        """Reopen the floats that were open before an update, and those set to 'Open when Windows starts'."""
        try:
            resume = json.loads(settings().value("float_resume", "[]") or "[]")
        except (TypeError, ValueError):
            resume = []
        settings().remove("float_resume")
        seen_ids, seen_src = set(), set()
        for pin in resume + _float_pins():                  # each float once, even if it was saved twice
            fid, src = pin.get("id"), pin.get("src")
            if (fid and fid in seen_ids) or (src and src in seen_src):
                continue
            seen_ids.add(fid)
            seen_src.add(src)
            self.open_float_state(pin)
        if len(_float_pins()) != len({x.get("id") for x in _float_pins()}):    # tidy duplicates left by older versions
            keep, ids = [], set()
            for x in _float_pins():
                if x.get("id") not in ids:
                    ids.add(x.get("id"))
                    keep.append(x)
            _save_float_pins(keep)

    def open_float_state(self, pin):
        """Open a float from FloatWindow.state(): the same file or link, place, size and point in the video."""
        src = pin.get("src")
        if not src:
            return None
        if pin.get("link"):
            if not engine.model_ready("yt-dlp"):
                return None
            w = FloatWindow("", {"page": src, "title": pin.get("title") or src, "pending": True}, pin=pin)
            self.floats.append(w)
            w.closed.connect(lambda w=w: self.floats.remove(w) if w in self.floats else None)
            w.show()
            self._resolve_and_play(src, w, pin=pin, quiet=True)
            return w
        if not os.path.exists(src):
            winsys.log(f"pinned float missing: {src}")
            if os.path.exists(Path(src).anchor or "/"):       # the drive is there but the file is gone: forget it
                _save_float_pins([x for x in _float_pins() if x.get("id") != pin.get("id")])
            return None
        w = FloatWindow(src, play=pin.get("playing", True), pin=pin)
        self.floats.append(w)
        w.closed.connect(lambda w=w: self.floats.remove(w) if w in self.floats else None)
        w.show()
        return w

    def _build_tray_menu(self):
        ck = mode_keys()["convert"]
        self.tray.setToolTip(tr("{app} — drag a file and shake the mouse", app=APP) if ck == "None"
                             else tr("{app} — drag a file, tap {key}", app=APP, key=key_label(ck)))
        menu = QMenu()
        self._first_action = menu.addAction(tr("Convert files…"), self.pick_files)
        menu.addAction(tr("Save image from clipboard"), self.save_clipboard_image)
        menu.addAction(tr("Paste link to Float"), self.play_link)
        menu.addAction(tr("Read QR code on screen"), lambda: QTimer.singleShot(300, self.read_qr_on_screen))
        menu.addAction(tr("New sticky note"), lambda: self.open_note())
        menu.addAction(tr("Show all notes"), self.open_all_notes)
        menu.addAction(tr("Add DragWheel to your browser…"), self.show_browser_setup)
        recent = menu.addMenu(tr("Recent results"))
        recent.aboutToShow.connect(lambda m=recent: self._fill_recent(m))
        self._qr_menu = menu.addMenu(tr("Send to phone — show QR code"))
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

    def _fill_qr_menu(self):
        sub = self._qr_menu
        sub.clear()
        links = share_links()
        short = lambda n: n if len(n) <= 40 else n[:37] + "…"
        live = []
        for (mode, _k), w in list(getattr(self, "_live_phone", {}).items()):
            try:
                if not w.ended:
                    live.append(w)
            except RuntimeError:
                pass
        clouds = [x for x in cloud_shares() if x.get("url") and Path(x.get("path", "")).exists()
                  and (not x.get("expires") or x["expires"] > time.time())]
        sub.menuAction().setVisible(bool(links or live or clouds))   # only while something is shared
        for w in live:
            name = w.paths[0].name if len(w.paths) == 1 else tr("{n} files", n=len(w.paths))
            way = tr("Link from this PC") if w.mode == "tunnel" else tr("Same Wi-Fi")
            sub.addAction(f"{short(name)}   ·   {way}", lambda _=False, w=w: (w.show(), w.raise_(), w.activateWindow()))
        for it in links:
            sub.addAction(f"{short(it['name'])}   ·   {_time_left(it['expires'])}", lambda _=False, it=it: self._show_qr(it))
        for x in clouds:
            it = {"url": x["url"], "name": x.get("name") or Path(x["path"]).name, "expires": x.get("expires", 0),
                  "path": x["path"]}
            left = _time_left(it["expires"]) if it["expires"] else tr("Cloud link")
            sub.addAction(f"{short(it['name'])}   ·   {left}", lambda _=False, it=it: self._show_qr(it, tr("Cloud link")))

    def _show_qr(self, it, title=None):
        w = ShareQR(it, title)
        self._phone_windows = getattr(self, "_phone_windows", [])
        self._phone_windows.append(w)
        w.show()
        w.raise_()
        w.activateWindow()

    def _refresh_tray_menu(self):
        """Cancel entries go first in the tray menu, only while work is in progress."""
        self._fill_qr_menu()
        menu = self._menu
        for act in self._cancel_actions:
            menu.removeAction(act)
            act.deleteLater()
        self._cancel_actions = []
        jobs = self._active_jobs() + [w for w in self.waiting if not w.cancel_requested]
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
            act.triggered.connect(lambda: [self._cancel_job(w) for w in list(self.waiting) + self._active_jobs()])
            menu.insertAction(before, act)
            self._cancel_actions.append(act)
        sep = menu.insertSeparator(before)
        self._cancel_actions.append(sep)

    def apply_theme(self):
        theme.set_mode(settings().value("theme", "system"))
        sync_accent()
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
        elif mode == "tool":
            ops = engine.tools(paths)
        else:
            ops = self.actions.ops(paths)
        try:
            ops = ops + custom_ops_for(mode, paths)                     # your presets, chains and commands
            ops = apply_wheel_layout(mode, engine.category_of(paths), ops)
        except Exception as e:
            winsys.log(f"wheel layout: {e}")
        if not ops:
            return [engine.Op("none", "No conversions" if mode == "convert" else "No tools", lambda *a: None,
                              hint="try Tools or Actions" if mode == "convert" else "try Convert or Actions")]
        return ops

    # ---- triggers
    def on_tap(self, mode):
        now = time.monotonic()
        if now - getattr(self, "_last_tap", 0.0) < 0.22:
            return                                    # one press is one toggle, never open-then-close
        self._last_tap = now
        if self.wheel.is_open():
            if mode == self.wheel.mode:
                self.wheel.dismiss()                 # the same key again closes the wheel
                return
            if mode != self.wheel.mode:
                play_tick()
                self.wheel.set_mode(mode)
            if not self.wheel.paths:
                self._fill_from_explorer()
            return
        self.wheel.popup(mode, click_mode=False)
        self._fill_from_explorer()
        QTimer.singleShot(0, self.wheel.begin_anim)

    def on_click_drag(self, mode):
        """A wheel key + right click while dragging a file."""
        if not winsys.file_drag_active():
            return
        if mode == "peek":
            self.on_peek()
        else:
            self.on_tap(mode)

    def on_peek(self):
        """Space while dragging: show (or hide) a quick preview of the file being dragged."""
        if self._peek is not None and self._peek.isVisible():
            if not peek_hold():
                self._peek.hide()                    # press to open, press again to close
            return
        paths = self.wheel.paths if self.wheel.is_open() and self.wheel.paths else []
        if not paths:
            hwnd = self.watcher.source_hwnd
            paths = [p for p in winsys.explorer_selection(hwnd) if p and os.path.exists(p)]
        if not paths:
            return
        if self._peek is None:
            self._peek = PeekWindow()
        self._peek.peek(paths)

    def _close_peek(self):
        if self._peek is not None:
            self._peek.hide()

    def _peek_let_go(self):
        """Hold to show: the key was let go — close it, or don't open it if it isn't up yet."""
        self._peek_held = False
        self._close_peek()

    def _fill_from_explorer(self):
        """Ask Explorer which files are being dragged, so the wheel works even if
        Windows never delivers the drag to it (security software, elevation, Qt quirks)."""
        hwnd = self.watcher.source_hwnd
        paths = [p for p in winsys.explorer_selection(hwnd) if p and os.path.exists(p)]
        winsys.log(f"tap: source={winsys.window_class(hwnd)!r} selection={len(paths)}")
        if paths and not self.wheel.paths:
            self.wheel.set_paths(paths)

    def on_shake(self):
        target = settings().value("shake_opens", "convert")
        if target == "peek":
            self.on_peek()
        elif not self.wheel.is_open():
            self.on_tap(target if target in MODES else "convert")

    def on_scroll(self, delta):
        w = self.wheel
        target = settings().value("scroll_opens", "convert")
        if not w.is_open() and target == "peek":
            if self._peek is None or not self._peek.isVisible():
                self.on_peek()
            return
        if not w.is_open():
            w.popup(target if target in MODES else "convert", click_mode=False)
            self._fill_from_explorer()
            QTimer.singleShot(0, w.begin_anim)
            return
        if not w.click_mode:
            w.scroll_step(1 if delta < 0 else -1)

    def on_drag_cancel(self):
        if self.wheel.is_open() and not self.wheel.click_mode:
            winsys.log("drag cancelled with Esc")
            self.wheel.dismiss()

    def on_drag_move(self):
        w = self.wheel
        if w.is_open() and not w.click_mode:
            w._track(QPointF(w.mapFromGlobal(QCursor.pos())))

    def on_release(self):
        w = self.wheel
        if w.is_open() and not w.click_mode:
            pos = QPointF(w.mapFromGlobal(QCursor.pos()))
            # give a real OLE drop time to arrive; if it doesn't, apply the slice under the cursor
            QTimer.singleShot(350, lambda: self._finish_drag(pos))

    def _finish_drag(self, pos):
        w = self.wheel
        if not w.is_open() or w.click_mode or w.dropped:
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

    EXPLORER_CLASSES = ("CabinetWClass", "ExploreWClass", "Progman", "WorkerW")

    def on_idle_tap(self, mode):
        """Trigger on hover / selection: the wheel for the file under the mouse, or the files selected."""
        if mode == "peek":
            if self._peek is not None and self._peek.isVisible():
                if not peek_hold():
                    self._peek.hide()
                return
            self._peek_held = True
            self._idle_paths(lambda paths: self._show_peek(paths) if self._peek_held or not peek_hold() else None)
            return
        if self.wheel.is_open():
            if mode == self.wheel.mode:
                self.wheel.dismiss()
            else:
                play_tick()
                self.wheel.set_mode(mode)
            return
        self._idle_paths(lambda paths: self.wheel.popup(mode, paths, click_mode=True))

    def _show_peek(self, paths):
        if self._peek is None:
            self._peek = PeekWindow()
        self._peek.peek(paths)

    def _idle_paths(self, then):
        """The file under the mouse (Mouse hover) or the files selected (File selection), handed to `then`."""
        trig = trigger_mode()
        if trig == "select":
            hwnd = winsys.foreground_hwnd()
            if winsys.window_class(hwnd) not in self.EXPLORER_CLASSES:
                return
            paths = [p for p in winsys.explorer_selection(hwnd) if p and os.path.exists(p)]
            winsys.log(f"selection tap: {len(paths)} file(s)")
            if paths:
                then(paths)
        elif trig == "hover":
            pos = winsys.cursor_pos()
            root = winsys.root_window_at(*pos)
            if winsys.window_class(root) not in self.EXPLORER_CLASSES:
                return
            winsys.click_at_cursor()                   # selects the file under the mouse

            def after():
                paths = [p for p in winsys.explorer_selection(root) if p and os.path.exists(p)]
                winsys.log(f"hover tap: {len(paths)} file(s)")
                if paths:
                    then(paths[:1])
            QTimer.singleShot(180, after)

    def on_hotkey(self):
        if self.wheel.is_open():                   # Ctrl+Alt+Space again closes it
            self.wheel.dismiss()
            return
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
        """Explorer starts DragWheel once per file when you right-click many files, and they arrive one by one:
        files that come in while that wheel is still open join it instead of replacing it."""
        paths, self.pending = list(dict.fromkeys(self.pending)), []
        now = time.monotonic()
        if (self.wheel.is_open() and self.wheel.click_mode and self.wheel.paths
                and now - getattr(self, "_last_batch", 0.0) < 8.0):
            merged = list(dict.fromkeys(self.wheel.paths + [str(Path(p)) for p in paths if os.path.exists(p)]))
            self.wheel.set_paths(merged)
            self.wheel.update()
            winsys.log(f"right-click batch: {len(merged)} files")
        elif (getattr(self, "_batch_op", None) and now - self._batch_op[1] < 10.0
              and now - getattr(self, "_last_batch", 0.0) < 10.0):
            # you already chose a slice while the rest of the files were still arriving: they get it too
            op = self._batch_op[0]
            late = [str(Path(p)) for p in paths if os.path.exists(p)]
            winsys.log(f"right-click batch: {len(late)} more files for {op.id}")
            if late:
                self.execute(op, late)
        else:
            self._batch_op = None
            self.open_paths(paths)
        self._last_batch = now

    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(None, tr("Choose files to convert"))
        if files:
            self.open_paths(files)

    # ---- run
    def execute(self, op: engine.Op, paths: list[str]):
        if op.id == "none":
            return
        if (self.wheel.click_mode and time.monotonic() - getattr(self, "_last_batch", 0.0) < 10.0
                and not op.ui and not op.ask and (op.group != "action" or op.id == "unblock")):
            self._batch_op = (op, time.monotonic())        # files still arriving from a right-click get it too
        else:
            self._batch_op = None
        play_select()
        params = {}
        if getattr(op, "spec", None):
            params["_spec"] = op.spec
        if op.ui == "crop":
            from editor import CropResizeDialog
            for p in paths[:5]:           # one editor per image
                try:
                    dlg = CropResizeDialog(p, DIALOG_CSS, app_icon(), ensure_model=self._ensure_model)
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
        if op.model and not engine.model_ready(op.model):
            self._get_model(op, paths, params)
            return
        if op.group == "action":
            try:
                op.fn(paths, params)
            except Exception as e:
                self.toast.show_msg(tr("Couldn't do that"), str(e), "err", 6000)
            return
        self._start(op, paths, params)

    def _get_model(self, op, paths, params):
        """Ask once, then download the AI model `op` needs and run the op when it's ready."""
        self._ensure_model(op.model, tr(op.label).rstrip("…"), lambda: self._start(op, paths, params))

    def predownload(self):
        """Downloads ticked in the installer ("Optional downloads"), one after another, after DragWheel starts."""
        s = settings()
        s.beginGroup("predownload")
        names = [k for k in s.childKeys() if s.value(k) == "1"]
        s.endGroup()
        labels = {"isnet": tr("Remove background"), "whisper-small": tr("Transcribe…").rstrip("…"),
                  "yt-dlp": tr("Paste link to Float"), "cloudflared": tr("Link from this PC")}
        todo = [n for n in names if n in engine.MODELS]

        def nxt():
            while todo:
                name = todo.pop(0)
                if engine.model_ready(name):
                    settings().remove(f"predownload/{name}")
                    continue

                def done(name=name):
                    settings().remove(f"predownload/{name}")
                    QTimer.singleShot(500, nxt)
                self._ensure_model(name, labels.get(name, name), done, ask=False, on_fail=lambda: QTimer.singleShot(500, nxt))
                return
        if todo:
            winsys.log(f"optional downloads from the installer: {todo}")
            QTimer.singleShot(4000, nxt)

    def _ensure_model(self, name, what, on_ready, ask=True, on_fail=None):
        """Download a model or tool once (after asking), then call on_ready()."""
        if engine.model_ready(name):
            on_ready()
            return
        if not ask:
            return self._download_model(name, what, on_ready, on_fail)
        m = engine.MODELS[name]
        mb = m.get("mb") or m["size"] // 1048576
        box = QMessageBox()
        box.setWindowTitle(APP)
        box.setWindowIcon(app_icon())
        box.setStyleSheet(i18n.css(DIALOG_CSS))
        box.setIconPixmap(app_icon().pixmap(48, 48))
        if name == "yt-dlp":
            box.setText(tr("{what} needs a one-time download of the free yt-dlp tool ({mb} MB) to play links "
                           "from YouTube and other sites.", what=what, mb=mb))
        elif name == "cloudflared":
            box.setText(tr("{what} needs a one-time download of Cloudflare's free tunnel tool ({mb} MB). "
                           "It needs no account.", what=what, mb=mb))
        else:
            box.setText(tr("{what} needs a one-time download of its AI model ({mb} MB). It is saved on this PC, "
                           "and everything runs offline after that.", what=what, mb=mb))
        ok = box.addButton(tr("Download"), QMessageBox.AcceptRole)
        box.addButton(tr("Cancel"), QMessageBox.RejectRole)
        box.setDefaultButton(ok)
        box.exec()
        if box.clickedButton() is not ok:
            return
        self._download_model(name, what, on_ready, on_fail)

    def _download_model(self, name, what, on_ready, on_fail=None):
        job = ModelDownload(name)
        job.setAutoDelete(False)
        self._update_jobs.add(job)

        def cancel():
            job.stop = True
        job.card = self.toast.show_busy(tr("Downloading AI model…") if name not in ("yt-dlp", "cloudflared") else tr("Download") + "…",
                                        what, cancel)

        def progress(done, total, card=job.card):
            if total and card in self.toast.cards:
                card.body.setText(f"{what} — {done * 100 // total}%  ({done / 1048576:.0f} / {total / 1048576:.0f} MB)")

        def finished(path, err, job=job):
            self._update_jobs.discard(job)
            if job.card in self.toast.cards:
                job.card.close_card()
            if err == CANCELLED:
                if on_fail:
                    on_fail()
                return
            if err:
                self.toast.show_msg(tr("Couldn't download the AI model") if name not in ("yt-dlp", "cloudflared") else tr("Couldn't do that"),
                                    err, "err", 8000)
                if on_fail:
                    on_fail()
                return
            winsys.log(f"model {name} ready: {path}")
            on_ready()
        job.sig.progress.connect(progress, Qt.QueuedConnection)
        job.sig.downloaded.connect(finished, Qt.QueuedConnection)
        self.pool.start(job)

    def on_ctrl_open(self, hwnd):
        """Ctrl + double-click on a file in Explorer or on the desktop: open it in a float."""
        def go():
            paths = winsys.explorer_selection(hwnd, focused=True)
            winsys.log(f"ctrl+double-click: {paths}")
            if paths and os.path.exists(paths[0]):
                self.actions.float(paths[:1], {})
        QTimer.singleShot(120, go)

    # ---- sticky notes
    def move_notes(self, base: Path):
        """Keep notes in another place (a cloud folder follows you to your other PCs): the notes DragWheel made
        move into <base> › DragWheel Notes, open ones carry on there."""
        old, new = notes_folder(), Path(base) / "DragWheel Notes"
        if os.path.normcase(str(old)) == os.path.normcase(str(new)):
            return
        try:
            new.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.toast.show_msg(tr("Keep notes in"), str(e), "err", 6000)
            return
        for n in getattr(self, "notes", []):
            n._write()                                      # nothing typed is left behind
        moved, failed, where = 0, 0, {}
        for f in (old.glob("*.txt") if old.exists() else []):
            dest = new / f.name
            if dest.exists():
                dest = Path(engine.unique_path(dest))
            try:
                shutil.move(str(f), str(dest))
                where[os.path.normcase(str(f))] = dest
                moved += 1
            except OSError as e:
                failed += 1
                winsys.log(f"move note {f.name}: {e}")
        settings().setValue("notes_base", "" if os.path.normcase(str(base)) == os.path.normcase(str(default_notes_base()))
                            else str(base))
        for n in getattr(self, "notes", []):
            dest = where.get(os.path.normcase(str(n.path)))
            if dest:
                n.relocate(dest)
        self._kept_notes = [dict(x, path=str(where.get(os.path.normcase(x["path"]), x["path"])))
                            for x in getattr(self, "_kept_notes", [])]
        self._save_notes()
        winsys.log(f"notes moved to {new}: {moved} moved, {failed} failed")
        self.toast.show_msg(tr("Notes are now kept in {folder}", folder=str(new)),
                            tr("{n} notes moved", n=moved) + (f" · {tr('{n} could not be moved', n=failed)}" if failed else ""),
                            "ok" if not failed else "err", 6000)

    def open_all_notes(self):
        """Every note in the notes folder, including ones written on another PC (cloud folder)."""
        folder = notes_folder()
        files = sorted(folder.glob("*.txt"), key=lambda f: f.stat().st_mtime) if folder.exists() else []
        if not files:
            self.toast.show_msg(tr("Show all notes"), tr("No notes yet"), "info", 4000)
            return
        for i, f in enumerate(files):
            st = None if any(os.path.normcase(str(n.path)) == os.path.normcase(str(f))
                             for n in getattr(self, "notes", [])) else {"x": 120 + 36 * (i % 10), "y": 120 + 36 * (i % 10), "path": str(f)}
            self.open_note(str(f), st)

    def open_note(self, path=None, state=None):
        """A sticky note: a new one (saved in Documents › DragWheel Notes) or a text file to edit."""
        self.notes = getattr(self, "notes", [])
        if path is None:
            folder = notes_folder()
            folder.mkdir(parents=True, exist_ok=True)
            path = engine.unique_path(folder / (time.strftime("Note %Y-%m-%d %H-%M") + ".txt"))
            Path(path).write_bytes(b"")
        for n in self.notes:                                # already open: bring it forward
            if os.path.normcase(str(n.path)) == os.path.normcase(str(path)):
                n.show()
                n.raise_()
                n.activateWindow()
                return n
        w = StickyNote(path, state)
        w.app_new = lambda: self.open_note(state={"color": w.color, "x": w.x() + 36, "y": w.y() + 36})
        w.closed.connect(self._note_closed)
        w.changed.connect(self._save_notes_soon)
        self.notes.append(w)
        w.show()
        w.raise_()
        w.activateWindow()
        if state is None or "x" not in state or not state.get("path"):
            w.edit.setFocus()
        self._save_notes_soon()
        return w

    def _note_closed(self, w):
        if not getattr(w, "by_user", False):              # Windows or DragWheel closing it: it comes back
            if w in getattr(self, "notes", []):
                self.notes.remove(w)
                self._kept_notes = getattr(self, "_kept_notes", []) + [w.state()]
            self._save_notes()
            settings().sync()
            return
        if w in getattr(self, "notes", []):
            self.notes.remove(w)
        gone = os.path.normcase(str(w.path))
        self._kept_notes = [x for x in getattr(self, "_kept_notes", []) if os.path.normcase(x["path"]) != gone]
        self._save_notes()

    def _save_notes_soon(self):
        t = getattr(self, "_notes_timer", None)
        if t is None:
            t = self._notes_timer = QTimer(self, singleShot=True, interval=700, timeout=self._save_notes)
        t.start()

    def _save_notes(self):
        states = []
        for n in getattr(self, "notes", []):
            try:
                states.append(n.state())
            except RuntimeError:
                pass
        seen = {os.path.normcase(x["path"]) for x in states}
        states += [x for x in getattr(self, "_kept_notes", []) if os.path.normcase(x["path"]) not in seen]
        settings().setValue("sticky_notes", json.dumps(states, ensure_ascii=False))

    def restore_notes(self):
        """The sticky notes that were open last time come back."""
        for st in _note_states():
            if st.get("path") and Path(st["path"]).exists():
                try:
                    self.open_note(st["path"], st)
                except Exception as e:
                    winsys.log(f"sticky note: {e}")

    # ---- right-click → DragWheel: Convert / Tools / Actions
    def run_from_menu(self, spec, paths):
        """Right-click → DragWheel → Convert/Tools/Actions → a slice. Explorer starts one request per selected file,
        so they're gathered for a moment and run together, like dropping them all on the wheel."""
        q = getattr(self, "_menu_runs", None)
        if q is None:
            q = self._menu_runs = {}
            self._menu_timer = QTimer(self, singleShot=True, interval=450, timeout=self._run_menu_batch)
        q.setdefault(spec, [])
        for p in paths:
            if p not in q[spec]:
                q[spec].append(p)
        self._menu_timer.start()

    def _run_menu_batch(self):
        runs, self._menu_runs = self._menu_runs, {}
        for spec, paths in runs.items():
            mode, _, op_id = spec.partition(":")
            paths = [p for p in paths if os.path.exists(p)]
            if not paths or mode not in ("convert", "tool", "action"):
                continue
            ops = self.ops_for(mode, paths)
            op = next((o for o in ops if o.id == op_id), None)
            winsys.log(f"menu: {spec} on {len(paths)} item(s){'' if op else ' — not for these files'}")
            if op is None:
                self.toast.show_msg(tr("Can't do that with these files"),
                                    tr("Pick another one, or open the wheel to see what fits."), "info", 6000)
                continue
            self.wheel.click_mode = False
            self.execute(op, paths)

    def refresh_file_menus(self):
        """Rebuild right-click → DragWheel (after start, and when slices or the language change)."""
        if not winsys.IS_WIN or not winsys.context_menu_enabled():
            return

        def work():
            try:
                winsys.set_file_menus(file_menu_spec(self))
            except Exception as e:
                winsys.log(f"menu: {e}")
        threading.Thread(target=work, daemon=True).start()

    # ---- DragWheel for Browser
    def show_browser_setup(self):
        w = BrowserSetup()
        self._phone_windows = getattr(self, "_phone_windows", [])
        self._phone_windows.append(w)
        w.show()
        w.raise_()
        w.activateWindow()

    def _register_browser_bridge(self):
        """Tell the browsers where DragWheel is, for the DragWheel for Browser extension (each start, so it
        follows DragWheel when it's moved or updated)."""
        if not getattr(sys, "frozen", False) or not winsys.IS_WIN:
            return
        import bridge
        try:
            bridge.register(sys.executable, Path(engine.models_dir()).parent / "browser")
        except Exception as e:
            winsys.log(f"browser bridge: {e}")
        choice = settings().value("browser_setup", "")
        if choice not in ("1", "shown"):                    # (the installer's Browser extension option was off)
            return
        settings().setValue("browser_setup", "shown")
        if bridge.CHROME_LIVE and settings().value("browser_offered", "") != "1":
            # offer it to Chrome, Edge and Brave (they ask to turn it on), once
            try:
                done = bridge.offer_extension()
            except Exception as e:
                done = []
                winsys.log(f"browser offer: {e}")
            winsys.log(f"browser extension offered to: {', '.join(done) or 'none'}")
            settings().setValue("browser_offered", "1")
            if done:                                        # no window: the browser itself asks to turn it on
                self.toast.show_msg(tr("DragWheel for Browser"),
                                    tr("Open your browser and click Turn on extension when it asks."), "ok", 8000)
        if bridge.FIREFOX_LIVE and settings().value("firefox_offered", "") != "1":
            # Firefox doesn't let programs add extensions: open its add-on page once (one click: Add to Firefox)
            fx = bridge.firefox_exe()
            settings().setValue("firefox_offered", "1")
            if fx:
                import subprocess
                try:
                    subprocess.Popen([fx, bridge.FIREFOX_STORE_URL], close_fds=True)
                    winsys.log("browser: opened the Firefox add-on page")
                except OSError as e:
                    winsys.log(f"browser: firefox: {e}")

    def save_web_image(self, path, fmt):
        """DragWheel for Browser → Save image as…: the picture from the page, saved in Downloads in the chosen
        format (or opened on the Convert wheel, which also saves into Downloads)."""
        from PySide6.QtCore import QStandardPaths
        dl = Path(QStandardPaths.writableLocation(QStandardPaths.DownloadLocation) or Path.home() / "Downloads")
        dl.mkdir(parents=True, exist_ok=True)
        src = Path(path)
        winsys.log(f"browser: save image as {fmt}: {src.name}")
        self.out_override[str(src)] = str(dl)
        if fmt == "wheel":
            self.open_paths([str(src)])
            return
        if fmt == "original" or engine.ext_of(src) == fmt or (fmt == "jpg" and engine.ext_of(src) == "jpeg"):
            dest = engine.unique_path(dl / src.name)
            try:
                shutil.copy2(src, dest)
            except OSError as e:
                self.toast.show_msg(tr("Couldn't save the picture"), str(e), "err", 8000)
                return
            self.toast.show_result(tr("Picture saved"), [str(dest)])
            return
        op = next((o for o in engine.conversions([str(src)]) if o.id == f"to_{fmt}"), None)
        if op is None:
            self.toast.show_msg(tr("Couldn't save the picture"),
                                tr("This picture can't be saved as {fmt}.", fmt=fmt.upper()), "err", 8000)
            return
        self._start(op, [str(src)], {})

    def open_empty_float(self):
        """Right-click on the desktop → Open Float: an empty float to drop a file on or paste a link into."""
        w = FloatWindow("")
        self.floats.append(w)
        w.closed.connect(lambda w=w: self.floats.remove(w) if w in self.floats else None)
        w.show()
        w.come_forward()
        w.activateWindow()
        w.setFocus()

    def read_qr_on_screen(self):
        """Tray or desktop right-click → Read QR code on screen: a still of each screen with its codes lit up."""
        if getattr(self, "_qr_overlays", None):
            return
        shots = []
        for sc in QGuiApplication.screens():
            pm = sc.grabWindow(0)
            try:
                codes = find_codes(pm.toImage())
            except Exception as e:
                winsys.log(f"read qr: {e}")
                codes = []
            shots.append((sc, pm, codes))
        winsys.log(f"read qr: {sum(len(c) for _s, _p, c in shots)} code(s) on {len(shots)} screen(s)")
        overlays = []

        def done(codes):
            for o in overlays:
                o.close()
            self._qr_overlays = None
            if codes:
                self.show_qr_result(codes)
        for sc, pm, codes in shots:
            overlays.append(QrScanOverlay(sc, pm, codes, done))
        self._qr_overlays = overlays
        under = QGuiApplication.screenAt(QCursor.pos())
        for o, (sc, _p, _c) in zip(overlays, shots):
            o.show()
            o.raise_()
            if sc is under:
                o.activateWindow()
                o.setFocus()
                winsys.bring_to_front(int(o.winId()))

    def _session_ending(self, *_):
        """Windows is signing out, restarting or shutting down: remember every open float and sticky note (with
        where they are) before the windows go, so they all come back."""
        self._quitting_notes = True
        try:
            self._save_notes()
            for n in list(getattr(self, "notes", [])):
                n._write()
        except Exception as e:
            winsys.log(f"session end notes: {e}")
        for f in list(getattr(self, "floats", [])):
            try:
                f._keep_tick()
                f._save_pin()
            except Exception:
                pass
        settings().sync()

    def _end_shares(self):
        """Quitting: shares that live in a window end without asking; open sticky notes are saved for next time."""
        try:
            self._save_notes()
            for n in list(getattr(self, "notes", [])):
                n._write()
        except Exception:
            pass
        self._quitting_notes = True
        for f in list(getattr(self, "floats", [])):           # where each float is, for next time
            try:
                f._keep_timer.stop()
                f._save_pin()
            except Exception:
                pass
        for w in list(getattr(self, "_phone_windows", [])):
            try:
                w._leaving = True
                if isinstance(w, PhoneShare) and not w.ended:
                    w.close()
            except RuntimeError:
                pass

    def show_qr_result(self, codes):
        winsys.log(f"read qr: {len(codes)} code(s) read")
        w = QrResult(codes)
        self._phone_windows = getattr(self, "_phone_windows", [])
        self._phone_windows.append(w)
        w.show()
        w.raise_()
        w.activateWindow()

    def play_link(self, target=None, url=None):
        """Play the link on the clipboard (YouTube and other sites, or a direct media link) in a float.
        The float opens straight away with the loading circle and plays when the link is ready."""
        if url is None and not engine.is_link(QGuiApplication.clipboard().text().strip()):
            f = _clipboard_media_file()               # a copied file or path: play it in Float too
            if f:
                if target is not None and target in self.floats:
                    target._play_now = True
                    target._load(f)
                    target._fade_to(1.0)
                    target.come_forward()
                else:
                    self.actions.float([f], {})
                return
        url = url or QGuiApplication.clipboard().text().strip()
        if not engine.is_link(url):
            self.toast.show_msg(tr("No link on the clipboard"), tr("Copy a link to a video or song first."), "info", 4000)
            return
        from urllib.parse import urlparse
        direct = urlparse(url).path.lower().endswith(engine.MEDIA_LINK_EXT)

        def go():
            t = target if target is not None and target in self.floats else None
            title = next((link_name(x) for x in saved_links() if x["url"] == url), None) or url
            pending = {"page": url, "title": title, "pending": True}
            restore = None
            if t is None:                                      # a new float, loading right away
                t = FloatWindow("", pending)
                self.floats.append(t)
                t.closed.connect(lambda w=t: self.floats.remove(w) if w in self.floats else None)
                t.show()
                t.come_forward()
            elif settings().value("float_link_stops", "true") == "true" or t.kind == "empty":
                if t.kind != "empty":
                    restore = (t.path, t.link)                 # put back if the link doesn't open
                t._load("", pending)                           # stop what's playing, show the loading circle
            t._play_now = True
            self._resolve_and_play(url, t, show_card=False, restore=restore, new=target is None)
        if direct or engine.model_ready("yt-dlp"):
            go()
        else:
            self._ensure_model("yt-dlp", tr("Paste link"), go)

    def _resolve_and_play(self, url, target, pin=None, quiet=False, quality=None, show_card=True, restore=None, new=False):
        job = LinkResolve(url, quality)
        job.setAutoDelete(False)
        self._update_jobs.add(job)
        self.busy_links = getattr(self, "busy_links", 0) + 1
        card = None if (pin or quiet or not show_card) else self.toast.show_busy(tr("Opening link…"), url[:70])

        def done(info, err, job=job):
            self._update_jobs.discard(job)
            self.busy_links = max(0, getattr(self, "busy_links", 1) - 1)
            if card is not None and card in self.toast.cards:
                card.close_card()
            if not err and info:
                page = info.get("page") or url
                # a saved link stays under the address you saved (the site may answer with a longer one)
                saved_urls = [x["url"] for x in saved_links()]
                key = url if url in saved_urls else page
                info["saved"] = key
                if key in saved_urls:
                    refresh_link_title(key, info.get("title"))   # saved links keep their place and name
                if not quiet:
                    remember_played("link", key, info.get("title"))   # Recently played (saving is up to you)
            if err and pin is not None and pin.get("_tries", 0) < 4:     # at sign-in the network may not be up yet
                pin["_tries"] = pin.get("_tries", 0) + 1
                QTimer.singleShot(15000, lambda: self._resolve_and_play(url, target, pin=pin, quiet=quiet))
                return
            if err:
                winsys.log(f"link failed: {url}: {err}")
                self.toast.show_msg(tr("Couldn't open this link"), tr(err), "err", 8000)
                if target is not None and target in self.floats and (target.link or {}).get("pending") and not quiet:
                    if new:
                        target.close()                         # the float made just for this link
                    elif restore and (restore[0] or restore[1]):
                        target._play_now = False
                        target._load(*restore)                 # back to what it showed before
                    else:
                        target._load("")
                return
            if target is not None:
                if target not in self.floats:
                    return                                 # it was closed while the link was loading
                if quiet:                                  # live stream reconnect: keep size and controls as they are
                    target.restart_live(info)
                    return
                target._load(info["url"], info)
                target._fade_to(1.0)
                QTimer.singleShot(1600, target._maybe_hide_controls)
                return
            w = FloatWindow(info["url"], info, play=bool(pin.get("playing", True)) if pin else False, pin=pin)
            self.floats.append(w)
            w.closed.connect(lambda w=w: self.floats.remove(w) if w in self.floats else None)
            w.show()
            if not pin:
                w.come_forward()
        job.sig.done.connect(done, Qt.QueuedConnection)
        self.pool.start(job)

    def save_clipboard_image(self, folder=None):
        """Save the image on the clipboard: the Convert wheel opens on it so you pick the file type, and the
        file is saved in `folder` (the folder you right-clicked in), or Pictures\\DragWheel from the tray.
        Files copied in Explorer open the wheel directly."""
        import datetime
        import tempfile
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        files = [u.toLocalFile() for u in (md.urls() if md and md.hasUrls() else []) if u.isLocalFile()]
        if files:
            self.open_paths(files)
            return
        img = cb.image()
        if img.isNull():
            self.toast.show_msg(tr("No image on the clipboard"), tr("Copy a picture or take a screenshot first."), "info", 4000)
            return
        if not folder or not os.path.isdir(folder):
            folder = str(Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Pictures" / APP)
            Path(folder).mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.gettempdir()) / "DragWheel-clipboard"
        tmp.mkdir(exist_ok=True)
        path = tmp / f"Clipboard {datetime.datetime.now():%Y-%m-%d %H-%M-%S}.bmp"
        if not img.save(str(path), "BMP"):
            self.toast.show_msg(tr("Couldn't do that"), str(path), "err", 6000)
            return
        self.out_override[str(path)] = folder
        self.wheel.popup("convert", [str(path)], click_mode=True)

    def _media_tick(self):
        """Keyboard media keys control the float that was used last (or one that is playing)."""
        floats = [f for f in self.floats if getattr(f, "player", None)]
        if not floats:
            return
        for vk, key in ((0xB3, "play"), (0xB0, "next"), (0xB1, "prev"), (0xB2, "stop")):
            down = winsys.key_down(vk)
            if down and not self._media_down.get(vk):
                target = FloatWindow.last_used if FloatWindow.last_used in floats else None
                target = target or next((f for f in floats if f._playing()), floats[-1])
                focused = target.isActiveWindow()
                shown = target.media_key(key)
                if shown and MediaOSD.wanted(focused):
                    MediaOSD.flash(shown, target)
            self._media_down[vk] = down
    def _update_cursor_busy(self):
        busy = bool(self._active_jobs() or getattr(self, "busy_links", 0))
        self.cursor_busy.set_busy(busy and settings().value("cursor_busy", "true") == "true")

    def on_volume_key(self, vk):
        """Volume keys or a volume knob: Windows changes the volume; show it big while a float is playing.
        Every step refreshes the sign; it goes away 2 seconds after the last one."""
        playing = [f for f in self.floats if getattr(f, "player", None) and f._playing()]
        if not playing:
            return
        target = FloatWindow.last_used if FloatWindow.last_used in playing else playing[-1]
        if MediaOSD.wanted(target.isActiveWindow()):
            QTimer.singleShot(40, lambda t=target: self._show_volume(t))

    def _show_volume(self, target):
        v = winsys.system_volume()
        if v is not None:
            MediaOSD.flash("mute" if v[1] else "volume", target, level=v[0], hold=2000)

    def _start(self, op, paths, params):
        name = Path(paths[0]).name if len(paths) == 1 else tr("{n} files", n=len(paths))
        w = Worker(op, paths, params)
        w.output_dir = self.out_override.get(paths[0])     # e.g. clipboard image saved "here"
        cancel = lambda w=w: self._cancel_job(w)
        if op.group == "convert":
            w.card = self.toast.show_busy(tr("Converting to {fmt}…", fmt=tr(op.label)), name, cancel)
        else:
            w.card = self.toast.show_busy(tr(op.label).rstrip("…") + "…", name, cancel)
        w.setAutoDelete(False)
        w.sig.done.connect(self._done, Qt.QueuedConnection)
        w.sig.progress.connect(lambda wk, f, name=name: self._job_progress(wk, f, name), Qt.QueuedConnection)
        w.sig.count.connect(self._job_count, Qt.QueuedConnection)
        if settings().value("job_mode", "queue") == "queue" and self._active_jobs():
            self.waiting.append(w)                # one job at a time: wait for the ones before it
            w.card.body.setText(name + " — " + tr("waiting ({n} in line)", n=len(self.waiting)))
            return
        self._launch(w)

    def _launch(self, w):
        self.running.add(w)                       # keep Python refs alive until done
        self.pool.start(w)

    def _next_in_line(self):
        while self.waiting and not self._active_jobs():
            w = self.waiting.pop(0)
            if w.cancel_requested:
                continue
            if w.card is not None and w.card in self.toast.cards:
                w.card.body.setText(Path(w.paths[0]).name if len(w.paths) == 1 else tr("{n} files", n=len(w.paths)))
            self._launch(w)
        for i, w in enumerate(self.waiting):
            if w.card is not None and w.card in self.toast.cards:
                name = Path(w.paths[0]).name if len(w.paths) == 1 else tr("{n} files", n=len(w.paths))
                w.card.body.setText(name + " — " + tr("waiting ({n} in line)", n=i + 1))

    def _job_count(self, worker, done, total):
        worker.count = (done, total)

    def _job_progress(self, worker, frac, name):
        card = worker.card
        if card is not None and card in self.toast.cards and not worker.cancel_requested:
            done, total = worker.count
            if total > 1:                      # a batch: "12 of 40 done — 31%"
                card.body.setText(tr("{a} of {b} done", a=done, b=total) + f" — {int(frac * 100)}%")
            else:
                card.body.setText(f"{name} — {int(frac * 100)}%")

    # ---- updating: warn about running jobs, keep the open floats
    def _ask_jobs_before_update(self, installer_waiting):
        """None = no jobs. Otherwise the button chosen: "now" | "wait" | "cancel"."""
        jobs = self._active_jobs()
        if not jobs:
            return None
        box = QMessageBox()
        box.setWindowTitle(f"{APP} — " + tr("Update"))
        box.setWindowIcon(app_icon())
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        box.setStyleSheet(i18n.css(DIALOG_CSS))
        box.setIconPixmap(app_icon().pixmap(48, 48))
        names = "<br>".join(f"• {Path(w.paths[0]).name}" for w in jobs[:5])
        box.setText(f"<b>{tr('Jobs still running: {n}', n=len(jobs))}</b><br><br>{names}<br><br>"
                    + tr("Updating closes DragWheel and stops them; their unfinished files are removed."))
        now = box.addButton(tr("Stop them and update"), QMessageBox.DestructiveRole)
        wait = None if installer_waiting else box.addButton(tr("Update when they finish"), QMessageBox.AcceptRole)
        no = box.addButton(tr("Don't update now"), QMessageBox.RejectRole)
        box.setDefaultButton(wait or no)
        box.exec()
        b = box.clickedButton()
        return "now" if b is now else "wait" if (wait is not None and b is wait) else "cancel"

    def save_open_floats(self):
        states = []
        for f in list(self.floats):
            try:
                states.append(f.state())
            except Exception as e:
                winsys.log(f"float state: {e}")
        settings().setValue("float_resume", json.dumps(states))
        settings().sync()
        winsys.log(f"saved {len(states)} open floats for after the update")

    def prepare_for_update(self) -> bool:
        """The installer is about to replace DragWheel (asked over the local socket). False = the user said not now."""
        if not getattr(self, "_update_confirmed", False):
            choice = self._ask_jobs_before_update(installer_waiting=True)
            if choice == "cancel":
                return False
        for w in self._active_jobs():
            self._cancel_job(w)
        self.save_open_floats()
        return True

    def quit_for_update(self, started=None):
        """Quit once cancelled jobs have cleaned up (at most ~6 s)."""
        import time
        started = started or time.monotonic()
        if self.running and time.monotonic() - started < 6:
            QTimer.singleShot(200, lambda: self.quit_for_update(started))
            return
        for f in list(self.floats):
            if f.player:
                f.player.stop()
        self.qapp.quit()

    def _cancel_job(self, worker):
        if worker.cancel_requested:
            return
        play_finish_sound("err")
        if worker in self.waiting:                 # not started yet: just take it out of the line
            self.waiting.remove(worker)
            worker.cancel()
            if worker.card is not None and worker.card in self.toast.cards:
                worker.card.show_msg(tr("Cancelled"), tr("Nothing was saved."), "info", 3000)
            self._next_in_line()
            return
        worker.cancel()
        if worker.card is not None and worker.card in self.toast.cards:
            worker.card.show_busy(tr("Cancelling…"), Path(worker.paths[0]).name)

    def _done(self, worker, outs, err):
        self.running.discard(worker)
        QTimer.singleShot(0, self._next_in_line)
        op = worker.op
        card = worker.card if worker.card is not None and worker.card in self.toast.cards else None
        target = card or self.toast
        if card is not None and err != CANCELLED:
            card._sound_for_this = True            # finish sound (when turned on)
        elif card is None and err != CANCELLED and not err:
            play_finish_sound("ok")
        if err == CANCELLED:
            target.show_msg(tr("Cancelled"), tr("Nothing was saved."), "info", 3000)
        elif err:
            winsys.log(f"job failed: {op.group}/{op.id} on {worker.paths[:3]}: {err}")
            target.show_msg(tr("{what} failed", what=tr(op.label).rstrip("…")), tr(err), "err", 8000)
        elif op.id == "install" and outs:
            names = [json.loads(str(o)[5:]).get("font", "") for o in outs if str(o).startswith("info:")]
            target.show_msg(tr("Font installed"), ", ".join(names) + "<br>" + tr("Ready in your apps (restart an app if it was open)."), "ok", 8000)
        elif op.id == "count" and outs:
            infos = [json.loads(str(o)[5:]) for o in outs if str(o).startswith("info:")]
            tot = {k: sum(i.get(k, 0) for i in infos) for k in ("words", "chars", "chars_spaces", "pages")}
            title = infos[0]["name"] if len(infos) == 1 else tr("{n} files", n=len(infos))
            lines = [tr("Words: {n}", n=f"{tot['words']:,}"),
                     tr("Characters: {n} ({m} with spaces)", n=f"{tot['chars']:,}", m=f"{tot['chars_spaces']:,}")]
            if any("pages" in i for i in infos):
                lines.append(tr("Pages: {n}", n=f"{tot['pages']:,}"))
            minutes = max(1, round(tot["words"] / 200))
            lines.append(tr("About {n} min to read", n=minutes))
            QGuiApplication.clipboard().setText("\n".join([title] + lines))
            target.show_msg(title, "<br>".join(lines), "ok", 12000)
        elif op.id == "ocr" and outs:
            try:
                QGuiApplication.clipboard().setText(Path(outs[0]).read_text(encoding="utf-8").strip())
                target.show_result(tr("Copied to clipboard"), outs)
            except Exception as e:
                target.show_msg(tr("Couldn't do that"), str(e), "err", 6000)
        else:
            outs = self._place_results(worker, outs)
            if outs is None:
                if card is not None:
                    card.close_card()
                return
            title = tr("Done") if op.group == "tool" else tr("Converted to {fmt}", fmt=tr(op.label))
            if worker.failed:
                names = ", ".join(n for n, _e in worker.failed[:3]) + ("…" if len(worker.failed) > 3 else "")
                winsys.log(f"batch: {len(worker.failed)} failed: " + " | ".join(f"{n}: {e}" for n, e in worker.failed[:10]))
                c = target.show_msg(title, tr("{a} of {b} done. These couldn't be done: {names}",
                                              a=len(worker.paths) - len(worker.failed), b=len(worker.paths), names=names),
                                    "err", 12000) or target
                c.target = [str(o) for o in outs]
                c.btn.setVisible(bool(outs))
                c.set_undo(self._undo_for(outs, worker))
            else:
                c = target.show_result(title, outs) or target
                c.set_undo(self._undo_for(outs, worker))
            self._count_success()
            self._remember(outs, worker)

    STAR_AFTER = 20

    def _count_success(self):
        """After 20 jobs that worked: a small window in the middle of the screen asking for a star on GitHub (it
        helps others find DragWheel). Maybe later asks once more 50 jobs on; Star or No thanks never again."""
        s = settings()
        try:
            n = int(s.value("jobs_done", 0) or 0) + 1
            again = int(s.value("star_again_at", 0) or 0)
        except (TypeError, ValueError):
            n, again = 1, 0
        s.setValue("jobs_done", n)
        asked = s.value("star_asked", "")
        if asked == "1" or n < self.STAR_AFTER or (asked == "later" and n < again):
            return
        s.setValue("star_asked", "1")
        QTimer.singleShot(2500, self, self._ask_for_star)    # after the result card

    def _ask_for_star(self):
        if getattr(self, "_star_window", None) is not None:
            return
        w = self._star_window = StarDialog(self)
        w.finished.connect(lambda _r: QTimer.singleShot(0, self, lambda: setattr(self, "_star_window", None)))
        w.show()
        w.raise_()
        w.activateWindow()

    def _undo_for(self, outs, worker):
        """Undo for files a job just made — not when they replaced the originals or went to the clipboard."""
        outs = [Path(o) for o in outs or [] if o]
        if not outs or settings().value("output_mode", "next") in ("replace", "clipboard"):
            return None
        srcs = {str(Path(p)).lower() for p in worker.paths}
        if any(str(o).lower() in srcs for o in outs):            # edited in place: nothing to take back safely
            return None

        def undo():
            ok = True
            for o in outs:
                try:
                    if o.exists():
                        winsys.recycle(str(o))
                except Exception as e:
                    winsys.log(f"undo: {o}: {e}")
                    ok = False
            self._forget(outs)
            winsys.log(f"undo: {len(outs)} result(s) to the Recycle Bin")
            return ok
        return undo

    # ---- recent results (tray menu)
    def _remember(self, outs, worker):
        try:
            recent = json.loads(settings().value("recent_results", "[]") or "[]")
        except (TypeError, ValueError):
            recent = []
        what = tr("Converted to {fmt}", fmt=tr(worker.op.label)) if worker.op.group == "convert" else tr(worker.op.label).rstrip("…")
        for o in outs or []:
            o = str(o)
            if not o or o.startswith("info:"):
                continue
            recent = [r for r in recent if r.get("path") != o]
            recent.insert(0, {"path": o, "what": what})
        settings().setValue("recent_results", json.dumps(recent[:10], ensure_ascii=False))

    def _forget(self, outs):
        try:
            recent = json.loads(settings().value("recent_results", "[]") or "[]")
        except (TypeError, ValueError):
            return
        gone = {str(o) for o in outs}
        settings().setValue("recent_results", json.dumps([r for r in recent if r.get("path") not in gone], ensure_ascii=False))

    def _fill_recent(self, sub):
        sub.clear()
        try:
            recent = json.loads(settings().value("recent_results", "[]") or "[]")
        except (TypeError, ValueError):
            recent = []
        recent = [r for r in recent if os.path.exists(r.get("path", ""))]
        if not recent:
            a = sub.addAction(tr("Nothing yet"))
            a.setEnabled(False)
            return
        from PySide6.QtCore import QFileInfo
        from PySide6.QtWidgets import QFileIconProvider
        prov = QFileIconProvider()
        for r in recent:
            p = Path(r["path"])
            name = p.name if len(p.name) <= 46 else p.name[:43] + "…"
            m = sub.addMenu(prov.icon(QFileInfo(str(p))), name)
            m.setToolTipsVisible(True)
            m.addAction(tr("Open"), lambda _=False, p=p: os.startfile(str(p)) if hasattr(os, "startfile") else None)
            m.addAction(tr("Show in folder"), lambda _=False, p=p: winsys.reveal([str(p)]))
            m.addAction(tr("Open in Float"), lambda _=False, p=p: self.actions.float([str(p)], {}))
            info = m.addAction(r.get("what", ""))
            info.setEnabled(False)
        sub.addSeparator()
        sub.addAction(tr("Clear this list"), lambda: settings().setValue("recent_results", "[]"))

    def _place_results(self, worker, outs):
        """Where results go (Settings → Output): replace the original (asks first) or copy to the clipboard.
        Returns the final paths, or None when the clipboard took them."""
        mode = settings().value("output_mode", "next")
        outs = [Path(o) for o in outs if o]
        if worker.paths and worker.paths[0] in self.watch.done:
            if worker.paths[0] in self.watch.overwrite:
                return self._watch_overwrite(worker.paths[0], outs)
            return outs                                  # watch folders keep results in their own folder
        if not outs or mode not in ("replace", "clipboard"):
            return outs
        if mode == "clipboard":
            import tempfile
            dest = Path(tempfile.gettempdir()) / "DragWheel clipboard"
            dest.mkdir(exist_ok=True)
            moved = []
            for o in outs:
                t = engine.unique_path(dest / o.name)
                shutil.move(str(o), str(t))
                moved.append(t)
            md = QMimeData()
            md.setUrls([QUrl.fromLocalFile(str(m)) for m in moved])
            if len(moved) == 1 and engine.EXT_CATEGORY.get(engine.ext_of(str(moved[0]))) == "image":
                img = QImage(str(moved[0]))
                if not img.isNull():
                    md.setImageData(img)                      # paste works in chat apps and editors too
            QGuiApplication.clipboard().setMimeData(md)
            self.toast.show_msg(tr("Copied to clipboard"), moved[0].name if len(moved) == 1 else
                                tr("{n} files", n=len(moved)), "ok", 4000)
            return None
        # replace: only when each result clearly belongs to one original
        src = [Path(p) for p in worker.paths]
        if worker.op.multi or len(src) != len(outs) or any(o.is_dir() for o in outs):
            return outs
        if settings().value("replace_no_ask", "false") != "true":
            box = QMessageBox()
            box.setWindowTitle(f"{APP} — " + tr("Replace the original"))
            box.setWindowIcon(app_icon())
            box.setStyleSheet(i18n.css(DIALOG_CSS))
            box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            pairs = "<br>".join(f"{a.name} → {b.name}" for a, b in list(zip(src, outs))[:6])
            box.setText(tr("Replace the original file(s) with the new one(s)? The originals go to the Recycle Bin.")
                        + "<br><br>" + pairs)
            again = QCheckBox(tr("Don't ask again"))
            box.setCheckBox(again)
            yes = box.addButton(tr("Replace"), QMessageBox.AcceptRole)
            box.addButton(tr("Keep both"), QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not yes:
                return outs
            if again.isChecked():
                settings().setValue("replace_no_ask", "true")
        final = []
        for a, b in zip(src, outs):
            try:
                winsys.recycle(str(a))
                target = a.with_suffix(b.suffix) if a.suffix.lower() != b.suffix.lower() else a
                if target.exists():
                    target = engine.unique_path(target)
                shutil.move(str(b), str(target))
                final.append(target)
            except Exception as e:
                winsys.log(f"replace failed for {a}: {e}")
                final.append(b)
        return final

    def _watch_overwrite(self, original, outs):
        """Auto Convert set to 'Overwrite original': the result takes the original's place (original to the Recycle Bin)."""
        self.watch.overwrite.discard(original)
        a = Path(original)
        if len(outs) != 1 or outs[0].is_dir():
            return outs                                  # several results: keep them in "Converted"
        b = outs[0]
        try:
            target = a.with_suffix(b.suffix)
            if target.exists() and target != a:
                target = engine.unique_path(target)
            self.watch.done.add(str(target))             # don't convert our own result again
            winsys.recycle(str(a))
            shutil.move(str(b), str(target))
            try:
                b.parent.rmdir()                         # "Converted" only if it is now empty
            except OSError:
                pass
            winsys.log(f"auto convert: {a.name} overwritten by {target.name}")
            return [target]
        except Exception as e:
            winsys.log(f"auto convert overwrite failed for {a}: {e}")
            return outs

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
        choice = self._ask_jobs_before_update(installer_waiting=False)
        if choice == "cancel":
            self.toast.show_msg(tr("Update postponed"), tr("Check for updates again from the tray when you're ready."), "info", 5000)
            return
        if choice == "wait":
            self.toast.show_msg(tr("Update waiting"), tr("It installs when the running jobs finish."), "info", 5000)
            self._install_when_idle(path)
            return
        self._update_confirmed = choice == "now"
        self._launch_installer(path)

    def _install_when_idle(self, path):
        if self._active_jobs():
            QTimer.singleShot(1500, lambda: self._install_when_idle(path))
            return
        self._launch_installer(path)

    def _launch_installer(self, path):
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
    # Settings has eight pages of controls; building them takes about a second, and everything else (a playing
    # float too) waits meanwhile. So a copy is built ahead of time, while no float is playing, and shown at once.
    _VOLATILE = ("float_resume", "sticky_notes", "note_color", "float_recent", "recent_results", "float_volume", "geometry",
                 "share_links", "float_pins", "last_dir", "float_links", "float_repeat", "link_quality",
                 "share_way", "share_minutes", "sign_mode", "pdf_watermark", "InstallerLanguage")

    def _settings_snapshot(self):
        s = settings()
        return hash(tuple((k, str(s.value(k))) for k in sorted(s.allKeys()) if not k.startswith(self._VOLATILE)))

    def _prebuild_settings(self, delay=4000):
        t = getattr(self, "_prebuild_timer", None)
        if t is None:
            t = self._prebuild_timer = QTimer(self, singleShot=True, timeout=self._do_prebuild_settings)
        t.start(delay)

    def _do_prebuild_settings(self):
        if getattr(self, "_settings_dlg", None) is not None or getattr(self, "_settings_spare", None) is not None:
            return
        if self.wheel.is_open():
            self._prebuild_settings(15000)          # not while the wheel is up
            return
        try:
            dlg = SettingsDialog(self, lazy=True)   # page by page, so a playing video doesn't stop
        except Exception as e:
            winsys.log(f"settings prebuild: {e}")
            return
        self._settings_spare = (dlg, self._settings_snapshot(), i18n.language(), theme.mode())

    def show_settings(self):
        open_one = getattr(self, "_settings_dlg", None)
        if open_one is not None:                    # already open: bring it forward instead of a second one
            open_one.raise_()
            open_one.activateWindow()
            return
        spare, self._settings_spare = getattr(self, "_settings_spare", None), None
        dlg = None
        if spare is not None:
            if spare[1:] == (self._settings_snapshot(), i18n.language(), theme.mode()):
                dlg = spare[0]                      # built ahead of time, nothing changed since: shows at once
            else:
                spare[0].deleteLater()
        if dlg is None:
            dlg = SettingsDialog(self)
        dlg.setModal(False)                         # the wheel and floats keep working while Settings is open
        dlg.setAttribute(Qt.WA_DeleteOnClose)
        dlg.finished.connect(lambda _r: setattr(self, "_settings_dlg", None))
        dlg.finished.connect(lambda _r: self._prebuild_settings())   # ready for next time
        self._settings_dlg = dlg
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def show_tour(self, parent=None):
        if parent is not None:                 # from Settings: on top of it, and usable while it's open
            TourDialog(self, parent).exec()
            return
        d = TourDialog(self)
        d.show()
        d.raise_()
        d.activateWindow()
        self._tour = d

    def show_help(self):
        k = {m: key_label(v) for m, v in mode_keys().items()}
        message(tr("{app} — How it works", app=APP), tr("HELP_HTML", app=APP, convert=k["convert"],
                                                         tool=k["tool"], action=k["action"])
                + "<br><br>" + tr("HELP_SCROLL"))
