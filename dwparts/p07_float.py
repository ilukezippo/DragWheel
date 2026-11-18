"""DragWheel: Float window — pinned, always on top, like a mini player.

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


# ============================================================================
# Float window — pinned, always on top, like a mini player.
# The picture fills the card; the close button, name, grip (and video controls) fade in only while
# the cursor is over it. Drag to move, drag an edge or corner to resize, drag the grip to drop the
# file into another app. Videos and audio play in place; other files show their icon, click to open.
# ============================================================================
def _fmt_time(ms):
    s = max(0, int(ms // 1000))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _find_side_subtitles(video) -> list[str]:
    """Subtitle files next to a video with the same name: movie.srt, movie.en.srt, movie.vtt ..."""
    v = Path(video)
    try:
        return sorted(str(f) for f in v.parent.iterdir()
                      if f.suffix.lower() in (".srt", ".vtt") and f.name.lower().startswith(v.stem.lower()))
    except OSError:
        return []


def _parse_subtitles(path) -> list[tuple[int, int, str]]:
    """Read an SRT or WebVTT file into (start ms, end ms, text) cues. Handles UTF-8 and Arabic (Windows-1256)."""
    import re
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    ts = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{1,3})|(\d\d):(\d\d)[,.](\d{1,3})")

    def ms(t):
        m = ts.fullmatch(t.strip().split(" ")[0])
        if not m:
            return None
        if m.group(1):
            h, mi, se, fr = m.group(1, 2, 3, 4)
        else:
            h, (mi, se, fr) = "0", m.group(5, 6, 7)
        return ((int(h) * 60 + int(mi)) * 60 + int(se)) * 1000 + int(fr.ljust(3, "0"))

    cues = []
    for block in re.split(r"\r?\n\s*\r?\n", text.replace("\r\n", "\n")):
        lines = [l for l in block.split("\n") if l.strip()]
        for i, line in enumerate(lines):
            if "-->" in line:
                a, b = line.split("-->", 1)
                start, end = ms(a), ms(b)
                if start is not None and end is not None:
                    body = "\n".join(lines[i + 1:])
                    body = re.sub(r"<[^>]+>|\{[^}]*\}", "", body).strip()
                    if body:
                        cues.append((start, end, body))
                break
    return cues


def _make_sparse(f):
    """Windows: mark a file sparse, so setting a big size doesn't write gigabytes of zeros first."""
    if not winsys.IS_WIN:
        return
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes
        h = msvcrt.get_osfhandle(f.fileno())
        ret = wintypes.DWORD(0)
        if not ctypes.windll.kernel32.DeviceIoControl(wintypes.HANDLE(h), 0x900C4, None, 0, None, 0,   # FSCTL_SET_SPARSE
                                                      ctypes.byref(ret), None):
            winsys.log(f"stream cache: sparse failed ({ctypes.GetLastError()})")
    except Exception as e:
        winsys.log(f"stream cache: sparse: {e}")


def _set_file_size(f, size):
    """Give a file its full size at once. Python's truncate() on Windows grows a file by writing zeros (3 s for a
    long video, on the main thread); SetEndOfFile just moves the end, and a sparse file then costs nothing."""
    if winsys.IS_WIN:
        try:
            import ctypes
            import msvcrt
            from ctypes import wintypes
            k = ctypes.windll.kernel32
            h = wintypes.HANDLE(msvcrt.get_osfhandle(f.fileno()))
            f.flush()
            if k.SetFilePointerEx(h, ctypes.c_longlong(size), None, 0) and k.SetEndOfFile(h):
                k.SetFilePointerEx(h, ctypes.c_longlong(0), None, 0)
                f.seek(0)
                return
            winsys.log(f"stream cache: SetEndOfFile failed ({ctypes.GetLastError()})")
        except Exception as e:
            winsys.log(f"stream cache: size: {e}")
    f.truncate(size)


class StreamCache:
    """Downloads an online video ahead of playback over several connections into a temp file and serves it to
    the float from a local address (with seeking). The player then never waits on a slow request; going back
    is instant. The temp file is deleted when the float closes."""
    CHUNK = 2 * 1024 * 1024
    WORKERS = 4
    AHEAD = 400 * 1024 * 1024          # how far past the playing point to fetch

    def __init__(self, url, headers=None, size=None):
        import http.server
        import tempfile
        import urllib.request
        self.url = url
        self.headers = {"User-Agent": "Mozilla/5.0"}
        self.headers.update(headers or {})
        if not size:                                     # YouTube links carry the length (clen=…)
            import urllib.parse as _up
            size = (_up.parse_qs(_up.urlparse(url).query).get("clen") or [0])[0]
        self.size = int(size or 0)
        self.ready = threading.Event()     # the temp file is ready (or the cache gave up: failed)
        self.failed = False
        self.n = 0
        self.have = bytearray(0)
        self.busy = set()
        self.fails = 0
        self.forbidden = 0       # chunks refused in a row (403): the link has expired
        self.expired = False
        self.focus = 0
        self.closed = False
        self.cond = threading.Condition()
        self.flock = threading.Lock()
        self.f = None
        self.tmp = None
        cache = self

        class H(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _range(h):
                import re as _re
                m = _re.match(r"bytes=(\d*)-(\d*)", h.headers.get("Range", ""))
                if not m:
                    return 0, cache.size - 1, False
                a = int(m.group(1) or 0)
                b = int(m.group(2)) if m.group(2) else cache.size - 1
                return a, min(b, cache.size - 1), True

            def _not_cached(h):
                """No size (the site doesn't say): the player gets the original address instead."""
                if cache.ready.wait(15) and not cache.failed:
                    return False
                h.send_response(302)
                h.send_header("Location", cache.url)
                h.send_header("Content-Length", "0")
                h.end_headers()
                return True

            def do_HEAD(h):
                if h._not_cached():
                    return
                h.send_response(200)
                h.send_header("Content-Type", "video/mp4")
                h.send_header("Content-Length", str(cache.size))
                h.send_header("Accept-Ranges", "bytes")
                h.end_headers()

            def do_GET(h):
                if h._not_cached():
                    return
                a, b, partial = h._range()
                if a >= cache.size:
                    h.send_response(416)
                    h.send_header("Content-Range", f"bytes */{cache.size}")
                    h.send_header("Content-Length", "0")
                    h.end_headers()
                    return
                h.send_response(206 if partial else 200)
                h.send_header("Content-Type", "video/mp4")
                h.send_header("Accept-Ranges", "bytes")
                h.send_header("Content-Length", str(b - a + 1))
                if partial:
                    h.send_header("Content-Range", f"bytes {a}-{b}/{cache.size}")
                h.end_headers()
                cache.set_focus(a)
                pos = a
                try:
                    while pos <= b and not cache.closed:
                        i = pos // cache.CHUNK
                        if not cache.wait_chunk(i):
                            return
                        end = min(b + 1, (i + 1) * cache.CHUNK)
                        with cache.flock:
                            cache.f.seek(pos)
                            data = cache.f.read(end - pos)
                        h.wfile.write(data)
                        pos = end
                        if pos > cache.focus + cache.CHUNK:
                            cache.set_focus(pos)
                except OSError:
                    pass                                   # the player seeked or closed this connection

            def log_message(h, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.local = f"http://127.0.0.1:{self.server.server_address[1]}/media"
        if self.size:
            self._start(self.size)
        else:                                            # ask the site for the size off the main thread
            threading.Thread(target=lambda: self._start(self._probe_size()), daemon=True).start()

    def _start(self, size):
        """Reserve the temp file and start downloading. Runs at once when the size is known, else after asking."""
        import tempfile
        try:
            if not size or self.closed:
                raise OSError("size unknown")
            fd, tmp = tempfile.mkstemp(prefix="dragwheel-stream-", suffix=".bin")
            os.close(fd)
            f = open(tmp, "r+b")
            _make_sparse(f)
            _set_file_size(f, size)
            with self.cond:
                self.size, self.tmp, self.f = int(size), tmp, f
                self.n = (self.size + self.CHUNK - 1) // self.CHUNK
                self.have = bytearray(self.n)
            if self.closed:                              # the float closed meanwhile
                self.close()
                return
            for _ in range(self.WORKERS):
                threading.Thread(target=self._worker, daemon=True).start()
        except Exception as e:
            self.failed = True
            winsys.log(f"stream cache not used: {e}")
        finally:
            self.ready.set()

    def _request(self, a, b, timeout=20):
        import urllib.request
        req = urllib.request.Request(self.url, headers=dict(self.headers, Range=f"bytes={a}-{b}"))
        return urllib.request.urlopen(req, timeout=timeout)

    def _probe_size(self):
        try:
            with self._request(0, 0, timeout=6) as r:
                cr = r.headers.get("Content-Range", "")
                return int(cr.rsplit("/", 1)[1]) if "/" in cr else int(r.headers.get("Content-Length") or 0)
        except Exception as e:
            winsys.log(f"stream cache: size probe failed: {e}")
            return 0

    def set_focus(self, pos):
        with self.cond:
            self.focus = pos
            self.cond.notify_all()

    def wait_chunk(self, i):
        with self.cond:
            while not self.have[i] and not self.closed:
                self.cond.wait(0.5)
            return not self.closed

    def _next(self):
        """The first missing chunk at or after the playing point (within reach), else before it."""
        start = self.focus // self.CHUNK
        limit = min(self.n, start + self.AHEAD // self.CHUNK)
        for i in range(start, limit):
            if not self.have[i] and i not in self.busy:
                return i
        return None

    def _worker(self):
        while not self.closed and not self.expired:
            with self.cond:
                i = self._next()
                if i is None:
                    if all(self.have):
                        return
                    self.cond.wait(0.5)
                    continue
                self.busy.add(i)
            a = i * self.CHUNK
            b = min(self.size, a + self.CHUNK) - 1
            ok = refused = False
            for attempt in range(3):
                try:
                    with self._request(a, b) as r:
                        data = r.read()
                    if len(data) == b - a + 1:
                        with self.flock:
                            if self.closed:                    # the file is gone
                                return
                            self.f.seek(a)
                            self.f.write(data)
                        ok = True
                        break
                except Exception as e:
                    if self.closed:
                        return
                    refused = getattr(e, "code", None) == 403
                    if attempt == 2 or refused:
                        winsys.log(f"stream cache: chunk {i} failed: {e}")
                    if refused:
                        break                              # asking again won't help
                    time.sleep(0.5 * (attempt + 1))
            with self.cond:
                self.busy.discard(i)
                if ok:
                    self.have[i] = 1
                    self.forbidden = 0
                else:
                    self.fails += 1
                    self.forbidden = self.forbidden + 1 if refused else 0
                    if self.forbidden >= 3 and not self.expired:
                        self.expired = True                # the float asks the site for a fresh link
                        winsys.log("stream cache: the link has expired")
                self.cond.notify_all()
            if not ok:
                time.sleep(1.0)

    def close(self):
        with self.cond:
            self.closed = True
            self.cond.notify_all()
        try:
            _stop_server(self.server)
        except Exception:
            pass
        try:
            with self.flock:
                if self.f is not None:
                    self.f.close()
            if self.tmp:
                os.remove(self.tmp)
        except OSError:
            pass


def _cacheable(url) -> bool:
    u = str(url).lower()
    own = u.startswith("http://127.0.0.1:") and u.endswith(("/media", "/live.ts"))     # DragWheel's own
    return u.startswith(("http://", "https://")) and "m3u8" not in u and "hls_playlist" not in u \
        and not own and ".mpd" not in u


LIVE_OUTPUT = ["-f", "mpegts"]


LIVE_INPUT_EXTRA = []          # tests add "-re" to feed a recorded stream at live speed


class LiveRelay:
    """Plays a live stream through ffmpeg: ffmpeg follows the live playlist as it grows (Qt's player stops when
    the first ~30 s run out) and passes one endless stream to the float over a local address."""

    safe_http = False            # after YouTube refused a reused connection: one request per segment from then on

    def __init__(self, url, headers=None, client=""):
        import http.server
        import subprocess
        relay = self
        self.client = client or engine.yt_client(url)
        self.procs = []
        hdr = dict(headers or {})
        args = ["-hide_banner", "-loglevel", "warning", "-fflags", "+genpts"]
        self.last_data = time.monotonic()
        self.total = 0
        self.forbidden = False
        ua = next((v for k, v in hdr.items() if k.lower() == "user-agent"), None)
        if ua:
            args += ["-user_agent", ua]
        extra = "".join(f"{k}: {v}\r\n" for k, v in hdr.items() if k.lower() != "user-agent")
        if extra:
            args += ["-headers", extra]
        if "m3u8" in url or "hls" in url:
            args += ["-live_start_index", "-6"]
            args += (["-http_persistent", "0", "-http_multiple", "0"] if LiveRelay.safe_http
                     else ["-http_persistent", "1", "-http_multiple", "1"])
            args += ["-reconnect", "1", "-reconnect_on_network_error", "1", "-reconnect_delay_max", "4"]
        cmd = [engine.ffmpeg(), *args, *LIVE_INPUT_EXTRA, "-i", url, "-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy",
               *LIVE_OUTPUT, "pipe:1"]

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(h):
                h.send_response(200)
                h.send_header("Content-Type", "video/mp2t")
                h.send_header("Cache-Control", "no-cache")
                h.end_headers()
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                        creationflags=engine.NO_WINDOW)
                relay.procs.append(proc)
                relay.last_data = time.monotonic()
                t0 = time.monotonic()

                def errors(stream=proc.stderr):            # ffmpeg's own warnings, so a stall can be explained
                    n = forbidden = 0
                    for raw in iter(stream.readline, b""):
                        line = raw.decode("utf-8", "replace").strip()
                        if line and n < 12:
                            n += 1
                            winsys.log(f"live relay ffmpeg [{time.monotonic() - t0:.0f}s]: {line[:220]}")
                        if "403 Forbidden" in line:
                            forbidden += 1
                            if forbidden == 3:             # this player's stream is refused: use another one
                                client = relay.client
                                if client:
                                    engine.LIVE_BAD_CLIENTS.add(client)
                                LiveRelay.safe_http = True
                                relay.forbidden = True
                                winsys.log(f"live relay: YouTube refuses the {client or '?'} stream, switching player")
                                try:
                                    proc.kill()
                                except Exception:
                                    pass
                threading.Thread(target=errors, daemon=True).start()
                sent = 0
                try:
                    while True:
                        chunk = proc.stdout.read(65536)
                        if not chunk:
                            break
                        h.wfile.write(chunk)
                        sent += len(chunk)
                        relay.last_data = time.monotonic()
                        relay.total += len(chunk)
                except OSError:
                    pass                                       # the float closed or reconnected
                finally:
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    winsys.log(f"live relay: ffmpeg stopped after {sent // 1024} KB, {time.monotonic() - t0:.0f}s")
                    if proc in relay.procs:
                        relay.procs.remove(proc)

            def log_message(h, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/live.ts"

    def close(self):
        for p in list(self.procs):
            try:
                p.kill()
            except Exception:
                pass
        try:
            _stop_server(self.server)
        except Exception:
            pass


_SAVED_LINKS = (None, [])


def saved_links() -> list:
    """Links played in Float, newest first: [{"url", "title"}]. (Read again only when the setting changed: a
    playing link float asks for its name on every frame while the controls show.)"""
    global _SAVED_LINKS
    raw = settings().value("float_links", "[]") or "[]"
    if raw == _SAVED_LINKS[0]:
        return [dict(x) for x in _SAVED_LINKS[1]]
    try:
        v = json.loads(raw)
        v = [x for x in v if isinstance(x, dict) and x.get("url")]
    except (TypeError, ValueError):
        v = []
    _SAVED_LINKS = (raw, v)
    return [dict(x) for x in v]


def remember_link(url, title):
    old = next((x for x in saved_links() if x["url"] == url), {})
    links = [x for x in saved_links() if x["url"] != url]
    item = {"url": url, "title": title or url}
    if old.get("name"):
        item["name"] = old["name"]                  # a name you gave it stays
    links.insert(0, item)
    settings().setValue("float_links", json.dumps(links[:40], ensure_ascii=False))


def link_name(it: dict) -> str:
    """What a saved link is called: the name you gave it, else the page's title."""
    return it.get("name") or it.get("title") or it.get("url", "")


def rename_link(url, name):
    links = saved_links()
    for x in links:
        if x["url"] == url:
            if name and name.strip() and name.strip() != x.get("title"):
                x["name"] = name.strip()
            else:
                x.pop("name", None)                  # an empty name goes back to the page's title
    settings().setValue("float_links", json.dumps(links, ensure_ascii=False))


class SavedLinksDialog(QDialog):
    """Rename, remove, reorder and play the links you played in Float."""

    def __init__(self, play=None, parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QAbstractItemView, QListWidget, QListWidgetItem
        self.play = play
        self.setWindowTitle(f"{APP} — " + tr("Saved links"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        tip = QLabel(tr("Double-click a name to rename it. Drag to change the order."))
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.list = QListWidget()
        self.list.setStyleSheet("QListWidget::item{padding:6px 8px; min-height:24px}"
                                "QListWidget QLineEdit{padding:2px 6px; min-height:26px; margin:0}")
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
                                  | QAbstractItemView.SelectedClicked)
        for it in saved_links():
            self._add_item(it)
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        for label, fn in ((tr("Play"), self._play), (tr("Add…"), self._add), (tr("Rename"), self._rename),
                          (tr("Remove"), self._remove), (tr("Clear the list"), self._clear)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        lay.addLayout(row)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _add_item(self, it, select=False):
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QListWidgetItem
        li = QListWidgetItem(link_name(it))
        li.setData(Qt.UserRole, dict(it))
        li.setToolTip(it["url"])
        li.setFlags(li.flags() | Qt.ItemIsEditable)
        li.setSizeHint(QSize(0, 36))                 # room to type when renaming
        self.list.addItem(li)
        if select:
            self.list.setCurrentItem(li)
        return li

    def _add(self):
        from PySide6.QtWidgets import QInputDialog
        clip = QGuiApplication.clipboard().text().strip()
        url, ok = QInputDialog.getText(self, tr("Add…"), tr("Link to a video or song"),
                                       text=clip if engine.is_link(clip) else "")
        url = url.strip()
        if not ok or not url:
            return
        if not engine.is_link(url):
            QMessageBox.information(self, tr("Saved links"), tr("That isn't a link to a web page."))
            return
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole)["url"] == url:
                self.list.setCurrentRow(i)
                return
        name, ok = QInputDialog.getText(self, tr("Rename"), tr("Name for this link (empty = the page's title)"))
        it = {"url": url, "title": url}
        if ok and name.strip():
            it["name"] = name.strip()
        li = self._add_item(it)
        self.list.takeItem(self.list.row(li))       # newest first, like links you play
        self.list.insertItem(0, li)
        self.list.setCurrentItem(li)

    def _clear(self):
        if not self.list.count():
            return
        if QMessageBox.question(self, tr("Saved links"), tr("Remove all saved links?")) == QMessageBox.Yes:
            self.list.clear()

    def _items(self):
        out = []
        for i in range(self.list.count()):
            li = self.list.item(i)
            it = dict(li.data(Qt.UserRole))
            name = li.text().strip()
            if name and name != it.get("title"):
                it["name"] = name
            else:
                it.pop("name", None)
            out.append(it)
        return out

    def _save(self):
        settings().setValue("float_links", json.dumps(self._items(), ensure_ascii=False))
        self.accept()

    def _rename(self):
        li = self.list.currentItem()
        if li is not None:
            self.list.editItem(li)

    def _remove(self):
        row = self.list.currentRow()
        if row >= 0:
            self.list.takeItem(row)

    def _play(self):
        li = self.list.currentItem()
        if li is None:
            return
        self._save()
        if self.play:
            self.play(li.data(Qt.UserRole)["url"])


def forget_link(url):
    settings().setValue("float_links", json.dumps([x for x in saved_links() if x["url"] != url], ensure_ascii=False))


def refresh_link_title(url, title):
    """A saved link that was played again: keep its place and your name, just update the page's title."""
    links = saved_links()
    for x in links:
        if x["url"] == url and title:
            x["title"] = title
    settings().setValue("float_links", json.dumps(links, ensure_ascii=False))


def recent_played() -> list:
    """Links and files played in Float, newest first: [{"kind": "link"|"file", "key", "title"}]."""
    try:
        v = json.loads(settings().value("float_recent", "[]") or "[]")
        return [x for x in v if isinstance(x, dict) and x.get("key")]
    except (TypeError, ValueError):
        return []


def remember_played(kind, key, title):
    items = [x for x in recent_played() if x["key"] != key]
    items.insert(0, {"kind": kind, "key": key, "title": title or key})
    settings().setValue("float_recent", json.dumps(items[:30], ensure_ascii=False))


def forget_played(key=None):
    items = [] if key is None else [x for x in recent_played() if x["key"] != key]
    settings().setValue("float_recent", json.dumps(items, ensure_ascii=False))


class RecentPlayedDialog(QDialog):
    """The links and files you played in Float: play one again, save a link, or remove them."""

    def __init__(self, play=None, parent=None):
        super().__init__(parent)
        from PySide6.QtCore import QSize
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        self.play = play
        self.setWindowTitle(f"{APP} — " + tr("Recently played"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        self.setLayoutDirection(Qt.RightToLeft if i18n.is_rtl() else Qt.LeftToRight)
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        self.list = QListWidget()
        for it in recent_played():
            li = QListWidgetItem(("🔗  " if it["kind"] == "link" else "🎞  ") + it.get("title", it["key"]))
            li.setData(Qt.UserRole, it)
            li.setToolTip(it["key"])
            li.setSizeHint(QSize(0, 34))
            self.list.addItem(li)
        self.list.itemDoubleClicked.connect(lambda _i: self._play())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        for label, fn in ((tr("Play"), self._play), (tr("Save this link"), self._save),
                          (tr("Remove"), self._remove), (tr("Clear the list"), self._clear)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        b = QPushButton(tr("Close"))
        b.clicked.connect(self.accept)
        row.addWidget(b)
        lay.addLayout(row)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _cur(self):
        li = self.list.currentItem()
        return li.data(Qt.UserRole) if li is not None else None

    def _play(self):
        it = self._cur()
        if it and self.play:
            self.accept()
            self.play(it)

    def _save(self):
        it = self._cur()
        if it and it["kind"] == "link" and not any(x["url"] == it["key"] for x in saved_links()):
            remember_link(it["key"], it.get("title"))

    def _remove(self):
        it = self._cur()
        if it:
            forget_played(it["key"])
            self.list.takeItem(self.list.currentRow())

    def _clear(self):
        if self.list.count() and QMessageBox.question(self, tr("Recently played"),
                                                      tr("Remove everything from the list?")) == QMessageBox.Yes:
            forget_played()
            self.list.clear()


def _float_pins() -> list:
    """Floats that reopen when Windows starts: [{"id", "src", "link", "x", "y", "w", "on_top"}]."""
    try:
        v = json.loads(settings().value("float_pins", "[]") or "[]")
        return v if isinstance(v, list) else []
    except (TypeError, ValueError):
        return []


def _save_float_pins(pins):
    settings().setValue("float_pins", json.dumps(pins))


class MediaOSD(QWidget):
    """A big see-through play/pause/next/previous sign in the middle of the screen for a second."""
    _one = None

    @staticmethod
    def wanted(focused) -> bool:
        s = settings()
        if s.value("media_osd", "true") != "true":
            return False
        return s.value("media_osd_when", "unfocused") == "always" or not focused

    @classmethod
    def flash(cls, kind, near=None, level=None, hold=750):
        if cls._one is None:
            cls._one = MediaOSD()
        cls._one.level = level
        cls._one._show(kind, near, hold)

    def __init__(self):
        super().__init__(None, Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.kind = "play"
        self.level = None
        self.setFixedSize(180, 180)
        self._hold = QTimer(self, singleShot=True, timeout=self._fade)
        self._anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._anim.finished.connect(self._done)

    def _show(self, kind, near, hold=750):
        self.kind = kind
        scr = (near.screen() if near is not None else None) or QGuiApplication.screenAt(QCursor.pos()) \
            or QGuiApplication.primaryScreen()
        g = scr.geometry()
        self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        self._anim.stop()
        self.setWindowOpacity(1.0)
        self.show()
        self.raise_()
        self.update()
        self._hold.start(hold)

    def _fade(self):
        self._anim.setDuration(250)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def _done(self):
        if self.windowOpacity() < 0.05:
            self.hide()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 120))
        p.drawEllipse(self.rect().adjusted(2, 2, -2, -2))
        p.setBrush(QColor(255, 255, 255, 215))
        c = self.rect().center()
        cx, cy = c.x() + 1, c.y() + 1

        path = QPainterPath()
        path.setFillRule(Qt.WindingFill)

        def tri(x0, pointing_right=True, w=46, h=56):
            x1 = x0 + w if pointing_right else x0 - w
            path.addPolygon(QPolygonF([QPointF(x0, cy - h / 2), QPointF(x1, cy), QPointF(x0, cy + h / 2),
                                       QPointF(x0, cy - h / 2)]))

        k = self.kind
        if k == "play":
            tri(cx - 20, w=54, h=64)
        elif k == "pause":
            p.drawRoundedRect(QRectF(cx - 26, cy - 32, 18, 64), 4, 4)
            p.drawRoundedRect(QRectF(cx + 8, cy - 32, 18, 64), 4, 4)
        elif k == "stop":
            p.drawRoundedRect(QRectF(cx - 28, cy - 28, 56, 56), 6, 6)
        elif k == "next":
            tri(cx - 40)
            tri(cx - 4)
            p.drawRoundedRect(QRectF(cx + 40, cy - 28, 9, 56), 2, 2)
        elif k == "prev":
            tri(cx + 40, False)
            tri(cx + 4, False)
            p.drawRoundedRect(QRectF(cx - 49, cy - 28, 9, 56), 2, 2)
        elif k in ("volume", "mute"):
            sy = cy - 16                                   # speaker a little higher, the level bar under it
            sp = QPolygonF([QPointF(cx - 38, sy - 11), QPointF(cx - 26, sy - 11), QPointF(cx - 8, sy - 28),
                            QPointF(cx - 8, sy + 28), QPointF(cx - 26, sy + 11), QPointF(cx - 38, sy + 11)])
            path.addPolygon(sp)
            path.closeSubpath()
            pen = QPen(QColor(255, 255, 255, 215), 6, Qt.SolidLine, Qt.RoundCap)
            lvl = self.level if self.level is not None else 1.0
            if k == "mute" or lvl <= 0.001:
                p.setPen(pen)
                p.drawLine(QPointF(cx + 6, sy - 14), QPointF(cx + 34, sy + 14))
                p.drawLine(QPointF(cx + 34, sy - 14), QPointF(cx + 6, sy + 14))
            else:
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                for i, r in enumerate((14, 26, 38)):
                    if lvl > i / 3 or i == 0:
                        p.drawArc(QRectF(cx - 8 - r, sy - r, 2 * r, 2 * r), -45 * 16, 90 * 16)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 215))
            bar = QRectF(cx - 50, cy + 34, 100, 8)
            p.setBrush(QColor(255, 255, 255, 70))
            p.drawRoundedRect(bar, 4, 4)
            p.setBrush(QColor(255, 255, 255, 215) if k == "volume" else QColor(255, 255, 255, 110))
            p.drawRoundedRect(QRectF(bar.x(), bar.y(), bar.width() * lvl, bar.height()), 4, 4)
            f = QFont("Segoe UI", 10, QFont.DemiBold)
            p.setFont(f)
            p.setPen(QColor(255, 255, 255, 215))
            p.drawText(QRectF(cx - 50, cy + 44, 100, 22), Qt.AlignCenter, f"{round(lvl * 100)}")
            p.setPen(Qt.NoPen)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 215))
        p.drawPath(path.simplified())
        p.end()


def _clipboard_media_file():
    """A file copied in Explorer (Ctrl+C), or a copied path ("Copy as path"), when it's something Float shows."""
    md = QGuiApplication.clipboard().mimeData()
    cands = []
    if md is not None and md.hasUrls():
        cands += [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
    txt = QGuiApplication.clipboard().text().strip()
    if txt and len(txt) < 1000:
        cands.append(txt.splitlines()[0].strip().strip('"').strip("'"))
    for c in cands:
        if c and os.path.isfile(c):
            return c
    return None


def _link_still_good(link, margin=20 * 60):
    """True while a site's media address stays valid for `margin` more seconds (YouTube writes when it
    stops working into the address: expire=<unix time>). Then a long pause restarts the player on the same
    address at once instead of asking the site again."""
    from urllib.parse import parse_qs, urlsplit
    import time
    urls = [u for u in (link.get("url"), link.get("audio")) if u]
    if not urls or link.get("live"):
        return False
    for u in urls:
        try:
            exp = int(parse_qs(urlsplit(u).query).get("expire", ["0"])[0])
        except ValueError:
            return False
        if exp - time.time() < margin:
            return False
    return True


class _FollowDefaultOutput(QObject):
    """Qt keeps a float's sound on the device it started on. When Windows switches to another one (a headset
    unplugged or turned off, speakers chosen in the sound menu), the float went silent: this moves its sound to
    the new default device, as other players do. A child of the float's audio output, so it goes with it."""
    _devices = None

    def __init__(self, audio):
        super().__init__(audio)
        from PySide6.QtMultimedia import QMediaDevices
        self.audio = audio
        if _FollowDefaultOutput._devices is None:
            _FollowDefaultOutput._devices = QMediaDevices()
        _FollowDefaultOutput._devices.audioOutputsChanged.connect(self.check)
        self._last = QMediaDevices.defaultAudioOutput().id()
        self._timer = QTimer(self, interval=1500, timeout=self.check)    # (not every change is announced)
        self._timer.start()

    def check(self):
        from PySide6.QtMultimedia import QMediaDevices
        try:
            dev = QMediaDevices.defaultAudioOutput()
            if dev.isNull() or dev.id() == self._last:
                return
            self._last = dev.id()
            self.audio.setDevice(dev)
            winsys.log(f"float: sound now goes to {dev.description()}")
        except RuntimeError:
            pass


LABEL_COLORS = [("White", "#ffffff"), ("Black", "#1c1e22"), ("Orange", "#ff8c1a"), ("Yellow", "#ffd84d"),
                ("Red", "#ef4b45"), ("Green", "#5fd38d"), ("Blue", "#5aa9ff"), ("Pink", "#ff7eb6")]


_LABELS = (None, {})      # the float_labels setting as read last time (it's read while painting)


def _float_labels() -> dict:
    global _LABELS
    raw = quick_setting("float_labels", "{}") or "{}"     # (asked while painting: not from the registry each time)
    if raw != _LABELS[0]:
        try:
            d = json.loads(raw)
            _LABELS = (raw, d if isinstance(d, dict) else {})
        except (ValueError, TypeError):
            _LABELS = (raw, {})
    return {k: dict(v) for k, v in _LABELS[1].items()}


def float_label(path) -> dict:
    return dict(_float_labels().get(str(Path(path)), {})) if path else {}


def set_float_label(path, style: dict) -> None:
    d = _float_labels()
    key = str(Path(path))
    style = {k: v for k, v in style.items() if v not in (None, "")}
    if style:
        d[key] = style
    else:
        d.pop(key, None)
    settings().setValue("float_labels", json.dumps(d, ensure_ascii=False))
    keys_changed()                                       # (quick_setting reads it fresh)


def _shell_pixmap(path):
    """The big icon Explorer shows for a file (custom icons of .url and .lnk shortcuts too), else Qt's."""
    got = None
    if winsys.IS_WIN and str(path).lower().endswith(".url"):
        chosen = winsys.url_shortcut_icon(str(path))    # (Explorer itself shows a .url's own icon small)
        if chosen:
            got = winsys.icon_from_file(*chosen)
    if got is None and winsys.IS_WIN:
        got = winsys.shell_icon(str(path))
    if got:
        w, h, data = got
        img = QImage(data, w, h, w * 4, QImage.Format_ARGB32).copy()
        if not img.isNull():
            return QPixmap.fromImage(img)
    from PySide6.QtCore import QFileInfo
    from PySide6.QtWidgets import QFileIconProvider
    return QFileIconProvider().icon(QFileInfo(str(path))).pixmap(256, 256)


def float_icon_pixmap(path):
    """The icon a float of an app, folder, shortcut or file shows: the one you chose (right-click → Name and icon →
    Change icon…), else the one Explorer shows."""
    custom = float_label(path).get("icon") if path else None
    if custom and Path(custom).exists():
        pm = QPixmap(custom)
        if not pm.isNull():
            return pm
    return _shell_pixmap(path)


def float_icons_folder() -> Path:
    return Path(engine.models_dir()).parent / "float icons"


def save_float_icon(source) -> str | None:
    """Make an icon from a picture, an .ico, or a program/shortcut's own icon, and keep a copy of it (so it stays
    even if the original moves). Returns the copy's path."""
    import hashlib
    ext = Path(source).suffix.lower()
    pm = _shell_pixmap(source) if ext in (".exe", ".dll", ".lnk", ".url", ".msi") else QPixmap(str(source))
    if pm.isNull() and ext not in (".exe", ".dll", ".lnk", ".url", ".msi"):
        try:                                            # HEIC, AVIF… that Qt can't read
            im = engine.open_image(str(source)).convert("RGBA")
            q = QImage(im.tobytes("raw", "RGBA"), im.width, im.height, im.width * 4, QImage.Format_RGBA8888)
            pm = QPixmap.fromImage(q.copy())
        except Exception:
            return None
    if pm.isNull():
        return None
    if max(pm.width(), pm.height()) > 256:
        pm = pm.scaled(256, 256, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    folder = float_icons_folder()
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / (hashlib.sha1(f"{source}{os.path.getmtime(source)}".encode("utf-8", "replace")).hexdigest()[:16] + ".png")
    return str(dest) if pm.save(str(dest), "PNG") else None


class FloatNameDialog(FrontDialog):
    """Float → right-click → Name → Font, size and colour…: changes show on the float as you pick them."""

    def __init__(self, fw):
        super().__init__(fw)
        from PySide6.QtWidgets import QFontComboBox, QLayout, QSlider, QCheckBox, QLineEdit, QToolButton, QGridLayout
        self.fw = fw
        self.old = float_label(fw.path)
        self.st = dict(self.old)
        self.setWindowTitle(f"{APP} — " + tr("Name"))
        self.setWindowIcon(app_icon())
        self.setStyleSheet(i18n.css(DIALOG_CSS))
        lay = QVBoxLayout(self)
        lay.setSizeConstraint(QLayout.SetFixedSize)
        self.header(lay, tr("The name under the icon"), tr("Only this float changes, not the file or app itself."))
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        self.show_cb = QCheckBox(tr("Show the name"))
        self.show_cb.setChecked(not fw._name_hidden())
        self.show_cb.toggled.connect(lambda on: self._set(
            "hide", None if on == (settings().value("float_hide_name", "false") != "true") else not on))
        form.addWidget(self.show_cb, 0, 0, 1, 2)
        self.hover_cb = QCheckBox(tr("Auto hide name"))
        self.hover_cb.setToolTip(tr("The name fades in when you point at the float and hides when you move away"))
        self.hover_cb.setChecked(bool(self.st.get("hover")))
        self.hover_cb.setEnabled(self.show_cb.isChecked())
        self.hover_cb.toggled.connect(lambda on: self._set("hover", True if on else None))
        self.show_cb.toggled.connect(self.hover_cb.setEnabled)
        form.addWidget(self.hover_cb, 1, 0, 1, 2)

        form.addWidget(QLabel(tr("Name")), 2, 0)
        self.name = QLineEdit(self.st.get("name", ""))
        self.name.setPlaceholderText(fw._default_label())
        self.name.textChanged.connect(lambda t: self._set("name", t.strip() or None))
        form.addWidget(self.name, 2, 1)

        form.addWidget(QLabel(tr("Font")), 3, 0)
        self.font = QFontComboBox()
        self.font.setCurrentFont(QFont(self.st.get("font") or "Segoe UI"))
        self.font.currentFontChanged.connect(
            lambda f: self._set("font", None if f.family() == "Segoe UI" else f.family()))
        form.addWidget(self.font, 3, 1)

        form.addWidget(QLabel(tr("Size")), 4, 0)
        srow = QHBoxLayout()
        self.size = QSlider(Qt.Horizontal)
        self.size.setRange(6, 40)
        self.size.setValue(int(self.st.get("size") or round(fw._auto_label_pt())))
        self.auto = QCheckBox(tr("Automatic"))
        self.auto.setToolTip(tr("Grows and shrinks with the icon"))
        self.auto.setChecked(not self.st.get("size"))
        self.size.setEnabled(not self.auto.isChecked())
        self.size_l = QLabel(str(self.size.value()))
        self.size_l.setMinimumWidth(22)
        self.size.valueChanged.connect(lambda v: (self.size_l.setText(str(v)), self._set("size", v)))
        self.auto.toggled.connect(lambda on: (self.size.setEnabled(not on),
                                              self._set("size", None if on else self.size.value())))
        srow.addWidget(self.size, 1)
        srow.addWidget(self.size_l)
        srow.addWidget(self.auto)
        form.addLayout(srow, 4, 1)
        self.bold = QCheckBox(tr("Bold"))
        self.bold.setChecked(self.st.get("bold", True))
        self.bold.toggled.connect(lambda on: self._set("bold", None if on else False))
        form.addWidget(self.bold, 5, 1)

        form.addWidget(QLabel(tr("Colour")), 6, 0)
        crow = QHBoxLayout()
        crow.setSpacing(6)
        self.swatches = []
        for cname, hexc in LABEL_COLORS:
            b = QToolButton()
            b.setFixedSize(24, 24)
            b.setToolTip(tr(cname))
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("hex", hexc)
            b.clicked.connect(lambda _=False, h=hexc: self._color(h))
            crow.addWidget(b)
            self.swatches.append(b)
        other = QPushButton(tr("Other…"))
        other.clicked.connect(self._pick)
        crow.addWidget(other)
        crow.addStretch(1)
        form.addLayout(crow, 6, 1)
        lay.addLayout(form)
        self._paint_swatches()

        reset = QPushButton(tr("Back to normal"))
        reset.clicked.connect(self._reset)
        cancel = QPushButton(tr("Cancel"))
        cancel.clicked.connect(self.reject)
        done = QPushButton(tr("Done"))
        done.setObjectName("primary")
        done.setDefault(True)
        done.clicked.connect(self.accept)
        self.buttons(lay, reset, cancel, done)
        self.rejected.connect(lambda: (set_float_label(fw.path, self.old), fw.update()))

    def _set(self, key, value):
        if value is None:
            self.st.pop(key, None)
        else:
            self.st[key] = value
        set_float_label(self.fw.path, self.st)
        self.fw.update()

    def _color(self, hexc):
        self._set("color", None if hexc.lower() == "#ffffff" else hexc)
        self._paint_swatches()

    def _pick(self):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self.st.get("color") or "#ffffff"), self, tr("Colour"))
        if c.isValid():
            self._color(c.name())

    def _paint_swatches(self):
        cur = (self.st.get("color") or "#ffffff").lower()
        for b in self.swatches:
            h = b.property("hex")
            ring = "#ff8c1a" if h.lower() == cur else "rgba(128,128,128,0.55)"
            width = 3 if h.lower() == cur else 1
            b.setStyleSheet(f"QToolButton {{ background: {h}; border: {width}px solid {ring}; border-radius: 12px; }}")

    def _reset(self):
        self.st = {}
        set_float_label(self.fw.path, {})
        for w, v in ((self.name, ""),):
            w.blockSignals(True)
            w.setText(v)
            w.blockSignals(False)
        for w, fn in ((self.font, lambda: self.font.setCurrentFont(QFont("Segoe UI"))),
                      (self.auto, lambda: self.auto.setChecked(True)), (self.bold, lambda: self.bold.setChecked(True)),
                      (self.hover_cb, lambda: self.hover_cb.setChecked(False)),
                      (self.show_cb, lambda: self.show_cb.setChecked(settings().value("float_hide_name", "false") != "true"))):
            w.blockSignals(True)
            fn()
            w.blockSignals(False)
        self.size.setEnabled(False)
        self._paint_swatches()
        self.fw.update()


class FloatWindow(QWidget):
    def come_forward(self):
        """A float you just opened shows in front of other windows, even when it isn't set to stay on top."""
        self.raise_()
        if not getattr(self, "on_top", True):
            QTimer.singleShot(60, self, lambda: winsys.bring_to_front(int(self.winId())))

    closed = Signal()
    page_ready = Signal(object, object)    # path, QImage of a document's first page (from a thread)
    RADIUS = 14
    EDGE = 7              # resize border
    CLOSE_R = 11
    MIN_W = 160

    def __init__(self, path, link=None, play=False, pin=None):
        on_top = settings().value("float_on_top", "true") == "true"
        if pin is not None:
            on_top = bool(pin.get("on_top", on_top))
        taskbar = settings().value("float_taskbar", "true") == "true"
        super().__init__(None, Qt.FramelessWindowHint | (Qt.Window if taskbar else Qt.Tool)
                         | (Qt.WindowStaysOnTopHint if on_top else Qt.Widget))
        self.on_top = on_top
        self._vol_open = False
        self._vol_drag = False
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAcceptDrops(True)        # drop another file on the float to replace it
        self.player = None
        self.hover = None
        self.ctrl = 1.0                  # opacity of the controls; fades with the cursor
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.valueChanged.connect(self._set_ctrl)
        self._press = None               # (kind, global pos, local pos, geometry, edges)
        self._seeking = False
        self._drop_hover = False
        self.pin_id = None               # set when this float reopens with Windows
        self._pin_timer = QTimer(self, singleShot=True, interval=500, timeout=self._save_pin)
        self._no_keep = False            # "Keep open after restart" turned off for this float
        self._keep_timer = QTimer(self, interval=5000, timeout=self._keep_tick)
        self._keep_timer.start()
        self._tb_state = None
        self._tb_timer = QTimer(self, interval=1000, timeout=self._taskbar_tick)
        self._tb_timer.start()
        self.companion = None
        self._relay = None
        self.repeat = settings().value("float_repeat", "off")     # off | one | all
        self._play_now = play
        self.free_shape = bool((pin or {}).get("free", False))     # Keep aspect ratio off
        self._load(path, link)
        self.move(QCursor.pos() - QPoint(self.width() // 2, 40))
        self._resume_ms = int((pin or {}).get("pos") or 0)     # where playback was before an update
        self._placing = False
        self._pin_play = bool((pin or {}).get("playing", True))    # a reopened link keeps playing or stays paused
        if pin is not None:
            self.pin_id = pin.get("id")
            self._place_from(pin)
        QTimer.singleShot(1500, self._keep_tick)
        # show the controls briefly so people know they exist, then let them fade
        QTimer.singleShot(1600, self._maybe_hide_controls)

    def _place_from(self, pin, tries=0):
        """Put a reopened float back exactly where it was, at the same size. Right after signing in to Windows the
        screens may not be ready yet: then it waits (up to 20 s) instead of saving a wrong place over the right one."""
        try:
            w = max(self.MIN_W, int(pin.get("w", self.width())))
            h = int(pin.get("h") or 0)
            at = QPoint(int(pin["x"]), int(pin["y"]))
        except (KeyError, TypeError, ValueError):
            self._placing = False
            return
        self._placing = True
        if h and self.aspect and self.kind in ("video", "image"):
            self.aspect = w / max(1, h)               # the shape it had (a video corrects it with its first frame)
        self._apply_size(w, h or self._height_for(w))
        if QGuiApplication.screenAt(at + QPoint(20, 20)) is None and tries < 20:
            QTimer.singleShot(1000, self, lambda: self._place_from(pin, tries + 1))
            return
        if QGuiApplication.screenAt(at + QPoint(20, 20)) is not None:
            self.move(at)
        self._placing = False

    def _load(self, path, link=None):
        """Show `path` in this float (also used when another file is dropped on it).
        `link` = {"url", "title", "page"} when playing a web link (path is then the media URL)."""
        self._drop_companion()
        self._stop_relay()
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())
            self.player.deleteLater()
            self.player = None
        prev_kind, prev_w = getattr(self, "kind", None), self.width()
        self.path = path
        self.link = link
        cat = "video" if link else engine.EXT_CATEGORY.get(engine.ext_of(path))
        self.kind = "other"          # image | video | audio | other
        self.src = None              # QPixmap for images, album covers and icons
        self.art = False             # True when src is an album cover
        self.frame = None            # current video frame (QImage)
        self.aspect = None           # width / height of the picture, kept while resizing
        self._scaled = None
        if cat == "image":
            try:
                img = engine.open_image(path)
                img.thumbnail((1600, 1600))
                q = QImage(img.convert("RGBA").tobytes("raw", "RGBA"), img.width, img.height,
                           img.width * 4, QImage.Format_RGBA8888)
                self.src = QPixmap.fromImage(q.copy())
                self.kind = "image"
                self.aspect = img.width / max(1, img.height)
            except Exception:
                self.src = None
        elif path and (cat in DOC_PREVIEW_CATS or cat == "comic") and Path(path).suffix.lower() not in (".cbr", ".cb7", ".cbt"):
            # PDFs, e-books and Office files show their first page; the icon stays until it's drawn
            if not getattr(self, "_page_hooked", False):
                self.page_ready.connect(self._got_page, Qt.QueuedConnection)
                self._page_hooked = True
            threading.Thread(target=lambda pp=path: self.page_ready.emit(pp, document_page_image(pp, 1400)),
                             daemon=True).start()
        elif not path and not link:                   # an empty float: drop a file, paste a link, or pick a saved one
            self.kind = "empty"
            self.aspect = 16 / 9
            self.src = QPixmap(2, 2)
            self.src.fill(Qt.transparent)
        elif link and link.get("pending"):           # reopening: the window shows now, the video when it's fetched
            self.kind = "video"
            self.aspect = 16 / 9
            self.src = QPixmap(2, 2)
            self.src.fill(QColor(0, 0, 0))
            self._busy, self._spin = True, 0.0
            self._pending_timer = QTimer(self, interval=40, timeout=self._pending_tick)
            self._pending_timer.start()
        elif cat in ("video", "audio") and self._start_player(cat):
            self.kind = cat
            if path and not link:
                remember_played("file", str(path), Path(path).name)
            if cat == "video":
                self.aspect = 16 / 9
            else:
                self._set_cover(engine.cover_art(path))
        if self.src is None:
            self.src = float_icon_pixmap(path)
        if self.kind == "image":
            w = 300 if self.aspect >= 1 else int(300 * self.aspect)
        elif self.kind == "video":
            w = 420
        elif self.art:
            w = 280
        elif self.kind == "empty":
            w = 360
        else:
            w = 200
        if self.isVisible() and self.kind == prev_kind and self.kind != "other":
            w = prev_w                                   # next/previous keeps the size you chose
        tl = self.pos() if self.isVisible() else None
        self._apply_size(w, self._height_for(w))
        if tl is not None:
            self.move(tl)                                # stay exactly where it is
        self._pin_changed()
        self.setToolTip(f"{link['page'] if link else path}\n" + tr("Drag to move · drag ⠿ to drop the file · double-click to open · scroll to resize"))
        try:
            self.setWindowTitle((self.display_name() if (path or link) else tr("Open Float")) or APP)   # the taskbar button
        except Exception:
            self.setWindowTitle(APP)
        self.update()

    def set_rate(self, rate):
        """Play faster or slower (the sound keeps its pitch)."""
        if self.player is not None:
            self.player.setPlaybackRate(rate)
        if getattr(self, "companion", None) is not None:
            self.companion.setPlaybackRate(rate)
            if self.player is not None:
                self.companion.setPosition(self.player.position())

    def _play_recent(self, it):
        if it["kind"] == "link":
            if _APP is not None:
                _APP.play_link(target=self, url=it["key"])
        elif os.path.isfile(it["key"]):
            self._play_now = True
            self._load(it["key"])
            self._fade_to(1.0)
            self.come_forward()
        else:
            forget_played(it["key"])                     # the file was moved or deleted

    # ---- the name under an app's or folder's icon (right-click → Name and icon)
    def _default_label(self) -> str:
        pp = Path(self.path or "")
        return pp.name if pp.is_dir() or not pp.suffix else pp.stem

    def _auto_label_pt(self) -> float:
        return max(7.0, min(22.0, self._icon_rect().width() * 0.085))

    def _name_hidden(self) -> bool:
        hide = float_label(self.path).get("hide") if self.path and not self.link else None
        return quick_setting("float_hide_name", "false") == "true" if hide is None else bool(hide)

    def _set_name_shown(self, on):
        st = float_label(self.path)
        default_shown = settings().value("float_hide_name", "false") != "true"
        if on == default_shown:
            st.pop("hide", None)                         # as Settings says
        else:
            st["hide"] = not on
        set_float_label(self.path, st)
        self.update()

    def _set_name_hover(self, on):
        st = float_label(self.path)
        st["hover"] = True if on else None
        set_float_label(self.path, st)
        self.update()

    def _change_icon(self):
        """Right-click → Name and icon → Change icon…: any picture (PNG, JPG, ICO, WebP…) or the icon of a program
        or shortcut. Only this float changes, not the file itself."""
        from PySide6.QtWidgets import QFileDialog
        self.activateWindow()
        winsys.set_foreground(int(self.winId()))
        f, _ = QFileDialog.getOpenFileName(
            self, tr("Change icon…"), str(Path.home() / "Pictures"),
            tr("Pictures and icons") + " (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.ico *.svg *.heic *.exe *.dll *.lnk);;"
            + tr("All files") + " (*.*)")
        if not f:
            return
        dest = save_float_icon(f)
        if not dest:
            if _APP is not None:
                _APP.toast.show_msg(tr("Change icon…"), tr("Couldn't use that file as an icon"), "err", 5000)
            return
        self._set_icon(dest)

    def _set_icon(self, icon_path):
        st = float_label(self.path)
        old = st.get("icon")
        st["icon"] = icon_path
        set_float_label(self.path, st)
        if old and old != icon_path and str(float_icons_folder()) in old:
            try:
                Path(old).unlink(missing_ok=True)        # our copy of the icon it had before
            except OSError:
                pass
        self.src = float_icon_pixmap(self.path)
        self._scaled = None
        self.update()

    def _rename_float(self):
        from PySide6.QtWidgets import QInputDialog
        self.activateWindow()
        winsys.set_foreground(int(self.winId()))
        st = float_label(self.path)
        name, ok = QInputDialog.getText(self, tr("Rename"), tr("Name under the icon (empty = the file's name)"),
                                        text=st.get("name") or self._default_label())
        if ok:
            name = name.strip()
            st["name"] = name if name and name != self._default_label() else None
            set_float_label(self.path, st)
            self.update()

    def _name_style(self):
        self.activateWindow()
        winsys.set_foreground(int(self.winId()))
        FloatNameDialog(self).exec()
        self.update()

    def display_name(self):
        if not self.link and self.path and float_label(self.path).get("name"):
            return float_label(self.path)["name"]
        if self.link:
            keys = (self.link.get("saved"), self.link.get("page"))
            saved = next((x for x in saved_links() if x["url"] in keys), None)
            return link_name(saved) if saved else self.link["title"]
        return Path(self.path).name

    def _rename_link(self):
        from PySide6.QtWidgets import QInputDialog
        keys = (self.link.get("saved"), self.link.get("page")) if self.link else ()
        saved = next((x for x in saved_links() if x["url"] in keys), None)
        page = saved["url"] if saved else None
        if not saved:
            return
        self.activateWindow()
        winsys.set_foreground(int(self.winId()))
        name, ok = QInputDialog.getText(self, tr("Rename"), tr("Name for this link (empty = the page's title)"),
                                        text=link_name(saved))
        if ok:
            rename_link(page, name)
            self.update()

    def _got_page(self, path, img):
        if path != self.path or self.link or img is None or img.isNull():
            return
        self.src = QPixmap.fromImage(img)
        self.kind = "image"
        self.aspect = img.width() / max(1, img.height())
        self._scaled = None
        w = 300 if self.aspect >= 1 else max(self.MIN_W, int(400 * self.aspect))
        tl = self.pos() if self.isVisible() else None
        self._apply_size(w, self._height_for(w))
        if tl is not None:
            self.move(tl)
        self.update()

    def _has_content(self) -> bool:
        return bool(self.link) or (self.kind != "empty" and bool(self.path))

    def _open_original(self):
        if not self._has_content():                  # an empty float: Open picks a file to show in it
            QTimer.singleShot(0, self._browse_file)  # once the menu has closed
            return
        QDesktopServices.openUrl(QUrl(self.link["page"]) if self.link else QUrl.fromLocalFile(self.path))

    def _browse_file(self):
        """Choose a picture, video, song or document to show in this float."""
        start = str(Path(self.path).parent) if self.path and not self.link else str(Path.home())
        # floats never take the focus by themselves, so make DragWheel the foreground app first:
        # otherwise Windows opens the file window behind everything else
        self.activateWindow()
        winsys.set_foreground(int(self.winId()))
        f, _ = QFileDialog.getOpenFileName(self, tr("Open"), start)
        if f:
            self._load(f)
            self._fade_to(1.0)
            self.come_forward()
            QTimer.singleShot(1600, self._maybe_hide_controls)

    def _nothing_playing(self) -> bool:
        if self.kind == "empty":
            return True
        if self.player is None or self.kind not in ("video", "audio"):
            return False
        from PySide6.QtMultimedia import QMediaPlayer
        return self.player.playbackState() == QMediaPlayer.StoppedState and not getattr(self, "_busy", False)

    def _set_cover(self, data):
        """Use an album cover (PNG bytes or QImage) as the picture of an audio float."""
        img = QImage.fromData(data) if isinstance(data, (bytes, bytearray)) else data
        if img is None or img.isNull():
            return
        self.src = QPixmap.fromImage(img)
        self.art = True
        self.aspect = img.width() / max(1, img.height())
        self._scaled = None

    def _on_metadata(self):
        if self.kind != "audio" or self.art or not self.player:
            return
        from PySide6.QtMultimedia import QMediaMetaData
        md = self.player.metaData()
        for key in (QMediaMetaData.CoverArtImage, QMediaMetaData.ThumbnailImage):
            img = md.value(key)
            if isinstance(img, QImage) and not img.isNull():
                self._set_cover(img)
                tl = self.pos()
                self._apply_size(self.width() if self.width() > 200 else 280, self._height_for(280))
                self.move(tl)
                return

    # ---------------------------------------------------------------- drop to replace
    def _dropped_path(self, md):
        if not md.hasUrls():
            return None
        files = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
        return files[0] if files and os.path.exists(files[0]) and files[0] != self.path else None

    @staticmethod
    def _dropped_link(md):
        """A web page dragged from the browser (the address bar's site icon, a link, a tab)."""
        cands = [u.toString() for u in md.urls() if not u.isLocalFile()] if md.hasUrls() else []
        if md.hasText():
            cands.append(md.text().strip().splitlines()[0] if md.text().strip() else "")
        return next((c for c in cands if c and engine.is_link(c)), None)

    def dragEnterEvent(self, e):
        if self._dropped_path(e.mimeData()) or (_APP is not None and self._dropped_link(e.mimeData())):
            e.acceptProposedAction()
            self._drop_hover = True
            self.update()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._drop_hover = False
        self.update()

    def dropEvent(self, e):
        self._drop_hover = False
        path = self._dropped_path(e.mimeData())
        if path:
            e.acceptProposedAction()
            self._load(path)
            self._fade_to(1.0)
            QTimer.singleShot(1600, self._maybe_hide_controls)
            return
        link = self._dropped_link(e.mimeData()) if _APP is not None else None
        if link:                                     # a video page dragged from the browser plays here
            e.acceptProposedAction()
            _APP.play_link(target=self, url=link)
        self.update()

    # ---------------------------------------------------------------- media
    def _start_player(self, cat):
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
        except Exception as e:                      # build without Qt Multimedia
            winsys.log(f"float: no multimedia ({e})")
            return False
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        try:
            self.audio.setVolume(float(settings().value("float_volume", 1.0)))
        except (TypeError, ValueError):
            pass
        self.player.setAudioOutput(self.audio)
        try:
            _FollowDefaultOutput(self.audio)
        except Exception as e:
            winsys.log(f"float: sound device watch: {e}")
        self.autoplay = settings().value("float_autoplay", "true") == "true" or getattr(self, "_play_now", False)
        self._play_now = False
        self.subs = None             # external subtitles: list of (start ms, end ms, text)
        self.sub_text = ""           # built-in subtitle line currently shown
        if cat == "video":
            self.sink = QVideoSink(self)
            self.player.setVideoSink(self.sink)
            self.sink.videoFrameChanged.connect(self._on_frame)
            self.sink.subtitleTextChanged.connect(self._on_subtitle)
            self._first_frame = True
            if not self.autoplay:
                # play until the first frame arrives (silently), then pause on it
                self.audio.setMuted(True)
        self.player.positionChanged.connect(lambda _p: self.update())
        # loading circle while the video waits for data (like YouTube's)
        if getattr(self, "_busy_timer", None) is not None:
            self._busy_timer.stop()
            self._busy_timer.deleteLater()
        self._busy = False
        self._spin = 0.0
        self._pos_seen = (-1, 0.0)
        self._busy_timer = QTimer(self, interval=40, timeout=self._check_busy)
        self._busy_timer.start()
        self.player.durationChanged.connect(lambda _d: self.update())
        self.player.playbackStateChanged.connect(lambda _s: self.update())
        self.player.errorOccurred.connect(self._on_media_error)
        if cat == "audio":
            self.player.metaDataChanged.connect(self._on_metadata)
        self.player.mediaStatusChanged.connect(self._on_status)
        if self.link and self.link.get("audio"):
            self._add_companion(self.link["audio"])
        if self.link and not self._live() and _cacheable(self.path):
            self.player.setSource(QUrl(self._cached(self.path, self.link.get("size"))))
        elif self._live():
            self._start_relay()
            self.player.mediaStatusChanged.connect(lambda st: winsys.log(f"float: live status {st.name}"))
            self.player.setSource(QUrl(self._relay.url))
            QTimer.singleShot(20000, self._prefetch_live)
        else:
            self.player.setSource(QUrl(self.path) if self.link else QUrl.fromLocalFile(self.path))
        if cat == "video" or self.autoplay:
            self.player.play()
        if cat == "video" and not self.link:
            side = _find_side_subtitles(self.path)
            if side:
                self._load_subs(side[0])
        return True

    # ---- separate sound stream (some YouTube videos only come as picture + sound apart)
    def _add_companion(self, audio_url):
        from PySide6.QtMultimedia import QMediaPlayer
        self.player.setAudioOutput(None)                    # the picture stream is silent anyway
        self.companion = QMediaPlayer(self)
        self.companion.setAudioOutput(self.audio)           # volume slider and mute keep working
        self.companion.setSource(QUrl(self._cached(audio_url, (self.link or {}).get("audio_size"))
                                      if _cacheable(audio_url) else audio_url))
        self.player.playbackStateChanged.connect(self._sync_companion_state)
        self.player.positionChanged.connect(self._sync_companion_pos)

    def _drop_companion(self):
        c = getattr(self, "companion", None)
        if c is not None:
            c.stop()
            c.setSource(QUrl())
            c.deleteLater()
            self.companion = None

    def _sync_companion_state(self, state):
        from PySide6.QtMultimedia import QMediaPlayer
        c = getattr(self, "companion", None)
        if c is None:
            return
        if state == QMediaPlayer.PlayingState:
            c.setPosition(self.player.position())
            c.play()
        elif state == QMediaPlayer.PausedState:
            c.pause()
        else:
            c.stop()

    def _sync_companion_pos(self, ms):
        c = getattr(self, "companion", None)
        if c is not None and abs(c.position() - ms) > 350:     # seeked, or drifted
            c.setPosition(ms)

    # ---- previous / next file in the same folder
    def _siblings(self, fresh=False):
        """The other files of the same kind in this file's folder, in name order (for ⏮ ⏭). Looked up at most every
        few seconds: painting the controls asks for it on every video frame, and scanning a big folder (Downloads)
        that often made the video stutter while the mouse was over the float."""
        import re
        if self.link:
            return []
        now = time.monotonic()
        cached = getattr(self, "_sib_cache", None)
        if not fresh and cached and cached[0] == self.path and now - cached[1] < 5:
            return cached[2]
        cat = engine.EXT_CATEGORY.get(engine.ext_of(self.path))
        here = Path(self.path)
        try:
            files = [str(f) for f in here.parent.iterdir()
                     if f.is_file() and engine.EXT_CATEGORY.get(engine.ext_of(str(f))) == cat]
        except OSError:
            return []
        natural = lambda t: [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", Path(t).name)]
        files = sorted(files, key=natural)
        self._sib_cache = (self.path, now, files)
        return files

    def _neighbour(self, step, fresh=False):
        files = self._siblings(fresh)
        try:
            i = [os.path.normcase(f) for f in files].index(os.path.normcase(self.path))
        except ValueError:
            return None
        j = i + step
        return files[j] if 0 <= j < len(files) else None

    def _step(self, step):
        nxt = self._neighbour(step, fresh=True)
        if nxt:
            self._play_now = True
            self._load(nxt)
        return bool(nxt)

    def _check_busy(self):
        import time
        from PySide6.QtMultimedia import QMediaPlayer
        if self.player is None:
            return
        st = self.player.mediaStatus()
        now = time.monotonic()
        pos = self.player.position()
        if pos != self._pos_seen[0]:
            self._pos_seen = (pos, now)
        playing = self.player.playbackState() == QMediaPlayer.PlayingState
        busy = st in (QMediaPlayer.LoadingMedia, QMediaPlayer.StalledMedia) and (playing or self.link is not None)
        if not busy and self.link and playing and self.kind == "video":       # stream stuck waiting for data
            busy = now - self._pos_seen[1] > 0.9
        if self.kind == "video" and self.frame is None and (playing or self.link):
            busy = True                                                     # nothing to show yet
        if busy and not self._busy:
            self._busy_since = now
        relay = getattr(self, "_relay", None)
        if busy and self._live() and relay is not None and now - relay.last_data > 6 \
                and now - getattr(self, "_last_refresh", 0) > 20 and now - getattr(self, "_live_fixing", 0) > 6:
            winsys.log("float: live relay got nothing for 6 s")
            self._last_refresh = now
            self._live_continue(error=True) if getattr(self, "_spare", None) else self.refresh_link(auto=True)
        if busy and self.link and now - getattr(self, "_busy_since", now) > 15 \
                and now - getattr(self, "_last_refresh", 0) > 45 and now - getattr(self, "_live_fixing", 0) > 25:
            self.refresh_link(auto=True)                      # stuck: fetch a fresh link by itself
        if busy or busy != self._busy:
            self._spin = (self._spin + 12) % 360
            self._busy = busy
            self.update()

    def _pending_tick(self):
        if not (self.link or {}).get("pending"):
            self._pending_timer.stop()
            return
        self._spin = (self._spin + 12) % 360
        self.update()

    def _paint_busy(self, p):
        c = QPointF(self.width() / 2, self.height() / 2)
        rad = max(14.0, min(self.width(), self.height()) * 0.09)
        p.save()
        p.setOpacity(1.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 90))
        p.drawEllipse(c, rad + 10, rad + 10)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 60), max(3.0, rad / 5), Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(c, rad, rad)
        p.setPen(QPen(QColor(255, 255, 255, 235), max(3.0, rad / 5), Qt.SolidLine, Qt.RoundCap))
        box = QRectF(c.x() - rad, c.y() - rad, rad * 2, rad * 2)
        p.drawArc(box, int(-self._spin * 16), int(-100 * 16))
        p.restore()

    def _on_status(self, status):
        from PySide6.QtMultimedia import QMediaPlayer
        if status == QMediaPlayer.LoadedMedia and self._resume_ms and self.autoplay:
            self.player.setPosition(self._resume_ms)
            self._resume_ms = 0
        if status == QMediaPlayer.EndOfMedia and self._live():
            import time
            if time.monotonic() - getattr(self, "_live_fixing", 0) >= 8:
                QTimer.singleShot(50, self._live_continue)
            return
        if status == QMediaPlayer.EndOfMedia and self.repeat == "one":
            self.player.setPosition(0)                       # repeat this one
            self.player.play()
            return
        if status == QMediaPlayer.EndOfMedia and (self.repeat == "all" or settings().value("float_autoplay", "true") == "true"):
            if self._neighbour(1):
                QTimer.singleShot(300, self, lambda: self._step(1))
            elif self.repeat == "all":                       # end of the folder: back to the first one
                files = self._siblings() if not self.link else []
                if len(files) > 1:
                    QTimer.singleShot(300, self, lambda f=files[0]: (setattr(self, "_play_now", True), self._load(f)))
                else:
                    self.player.setPosition(0)
                    self.player.play()

    def set_repeat(self, mode):
        self.repeat = mode
        settings().setValue("float_repeat", mode)
        self.update()

    def _on_frame(self, frame):
        img = frame.toImage()
        if img.isNull():
            return
        self.frame = img
        if getattr(self, "_first_frame", False):
            self._first_frame = False
            if not self.autoplay:
                self.player.pause()
                self.player.setPosition(self._resume_ms or 0)
                self._resume_ms = 0
                self.audio.setMuted(False)
            a = img.width() / max(1, img.height())
            if abs(a - (self.aspect or 0)) > 0.01:
                self.aspect = a
                if not self.free_shape:                  # any shape: the size stays as you made it
                    tl = self.pos()
                    self._apply_size(self.width(), self._height_for(self.width()))
                    self.move(tl)
        self.update()

    def _on_subtitle(self, text):
        self.sub_text = text or ""
        self.update()

    def _load_subs(self, path):
        try:
            self.subs = _parse_subtitles(path)
            self.subs_path = path
            self.player.setActiveSubtitleTrack(-1)        # one subtitle source at a time
        except Exception as e:
            winsys.log(f"float: cannot read subtitles {path}: {e}")
            self.subs = None
        self.update()

    def _current_subtitle(self):
        if self.subs:
            pos = self.player.position()
            return "\n".join(t for a, b, t in self.subs if a <= pos <= b)
        return self.sub_text

    @staticmethod
    def _track_name(md, i):
        from PySide6.QtCore import QLocale
        from PySide6.QtMultimedia import QMediaMetaData
        parts = []
        lang = md.value(QMediaMetaData.Language)
        try:
            if lang is not None and lang != QLocale.AnyLanguage:
                parts.append(QLocale.languageToString(lang))
        except Exception:
            pass
        title = md.stringValue(QMediaMetaData.Title)
        if title and title not in parts:
            parts.append(title)
        return " · ".join(parts) or tr("Track {n}", n=i + 1)

    def _add_track_menus(self, m):
        from PySide6.QtGui import QActionGroup
        audio = self.player.audioTracks()
        am = m.addMenu(tr("Audio track"))
        grp = QActionGroup(am)
        for i, md in enumerate(audio):
            a = am.addAction(self._track_name(md, i))
            a.setCheckable(True)
            a.setChecked(i == self.player.activeAudioTrack() or (len(audio) == 1))
            a.triggered.connect(lambda _c=False, i=i: self.player.setActiveAudioTrack(i))
            grp.addAction(a)
        if not audio:
            am.setEnabled(False)
        sm = m.addMenu(tr("Subtitles"))
        grp2 = QActionGroup(sm)
        off = sm.addAction(tr("Off"))
        off.setCheckable(True)
        off.setChecked(not self.subs and self.player.activeSubtitleTrack() < 0)
        off.triggered.connect(self._subs_off)
        grp2.addAction(off)
        for i, md in enumerate(self.player.subtitleTracks()):
            a = sm.addAction(self._track_name(md, i))
            a.setCheckable(True)
            a.setChecked(not self.subs and i == self.player.activeSubtitleTrack())
            a.triggered.connect(lambda _c=False, i=i: self._subs_track(i))
            grp2.addAction(a)
        for f in ([] if self.link else _find_side_subtitles(self.path)):
            a = sm.addAction(Path(f).name)
            a.setCheckable(True)
            a.setChecked(bool(self.subs) and getattr(self, "subs_path", "") == f)
            a.triggered.connect(lambda _c=False, f=f: self._load_subs(f))
            grp2.addAction(a)
        sm.addSeparator()
        sm.addAction(tr("Browse…"), self._browse_subs)

    def _subs_off(self):
        self.subs = None
        self.player.setActiveSubtitleTrack(-1)
        self.sub_text = ""
        self.update()

    def _subs_track(self, i):
        self.subs = None
        self.player.setActiveSubtitleTrack(i)
        self.update()

    def _browse_subs(self):
        f, _ = QFileDialog.getOpenFileName(self, tr("Subtitles"), str(Path.home() if self.link else Path(self.path).parent),
                                           "Subtitles (*.srt *.vtt)")
        if f:
            self._load_subs(f)

    # ---- live streams: the player only gets the newest ~30 s at a time, so keep loading the next part
    def _live(self):
        return bool(self.link and self.link.get("live"))

    def _start_relay(self):
        self._stop_relay()
        try:
            self._relay = LiveRelay(self.path, (self.link or {}).get("headers"), (self.link or {}).get("client", ""))
        except Exception as e:
            winsys.log(f"live relay failed: {e}")
            self._relay = None

    def _stop_relay(self):
        r = getattr(self, "_relay", None)
        if r is not None:
            r.close()
            self._relay = None
        for c in getattr(self, "_caches", []):
            threading.Thread(target=c.close, daemon=True).start()
        self._caches = []

    def _cached(self, url, size=None):
        """Local address of the download-ahead copy of `url` (or the url itself if that can't be set up)."""
        try:
            c = StreamCache(url, (self.link or {}).get("headers"), size)
        except Exception as e:
            winsys.log(f"stream cache not used: {e}")
            return url
        self._caches = getattr(self, "_caches", []) + [c]
        if getattr(self, "_expiry_timer", None) is None:
            self._expiry_timer = QTimer(self, interval=2000, timeout=self._check_expired)
        self._expiry_timer.start()
        return c.local

    def _check_expired(self):
        """A video link stopped working (sites give links that last a few hours): get a fresh one, same place."""
        caches = getattr(self, "_caches", [])
        if not caches:
            self._expiry_timer.stop()
            return
        if not any(c.expired for c in caches) or _APP is None or not (self.link or {}).get("page"):
            return
        now = time.monotonic()
        if now - getattr(self, "_renewed_at", 0.0) < 60:
            return                                       # renewed a moment ago: don't loop
        self._renewed_at = now
        self._resume_ms = self.player.position() if self.player is not None else 0
        winsys.log("float: link expired, getting a fresh one")
        for c in caches:
            c.expired = False                            # so this runs once per renewal
        _APP._resolve_and_play(self.link["page"], self, quiet=True)

    def restart_live(self, info):
        """The link was renewed: keep the float as it is (size, place, volume) and carry on playing —
        live streams through a fresh relay, other videos from where they were."""
        if self.player is None or info.get("audio") or self.companion is not None:
            keep = getattr(self, "_resume_ms", 0)
            pos = 0 if info.get("live") else (self.player.position() if self.player is not None else keep)
            self._play_now = True if self.player is not None else getattr(self, "_pin_play", True)
            self._load(info["url"], info)                # picture and sound apart: set both up again
            self._resume_ms = pos
            return
        pos = 0 if info.get("live") else self.player.position()
        self.link = info
        self.path = info["url"]
        self._pos_seen = (-1, 0.0)
        if info.get("live"):
            self._start_relay()
            if self._relay is not None:
                self.player.setSource(QUrl(self._relay.url))
            QTimer.singleShot(20000, self._prefetch_live)
        else:
            self._stop_relay()
            self._resume_ms = pos
            self.autoplay = True
            self.player.setSource(QUrl(self._cached(info["url"], info.get("size")) if _cacheable(info["url"]) else info["url"]))
        self.player.play()

    def _set_quality(self, q):
        settings().setValue("link_quality", q)
        self.refresh_link(quality=q)

    def refresh_link(self, auto=False, quality=None):
        """Ask the site again for the video (its links expire) and continue."""
        if not self.link or _APP is None:
            return
        import time
        self._last_refresh = time.monotonic()
        winsys.log(f"float: refresh link ({'automatic, stuck loading' if auto else 'from the menu'})")
        self._live_fixing = time.monotonic()
        _APP._resolve_and_play(self.link["page"], self, quiet=True, quality=quality)

    def _prefetch_live(self):
        """Fetch a fresh stream link in the background while this one still plays, so a failure is fixed in
        seconds instead of waiting for YouTube."""
        if not self._live() or _APP is None or self.player is None:
            return
        job = LinkResolve(self.link["page"])
        job.setAutoDelete(False)
        _APP._update_jobs.add(job)

        def got(info, err, job=job):
            _APP._update_jobs.discard(job)
            if info and info.get("live"):
                self._spare = (time.monotonic(), info)
        job.sig.done.connect(got, Qt.QueuedConnection)
        _APP.pool.start(job)

    def _live_continue(self, error=False):
        import time
        now = time.monotonic()
        recent = [t for t in getattr(self, "_live_reloads", []) if now - t < 60] + [now]
        self._live_reloads = recent
        spare = getattr(self, "_spare", None)
        if spare and spare[1].get("client") in engine.LIVE_BAD_CLIENTS:
            spare = self._spare = None                   # made for a player YouTube now refuses
        relay = getattr(self, "_relay", None)
        if relay is not None and relay.forbidden:
            alts = [a for a in (self.link or {}).get("alts", []) if a.get("client") not in engine.LIVE_BAD_CLIENTS]
            if alts:                                     # another player's stream is already known: switch now
                nxt = dict(self.link, url=alts[0]["url"], headers=alts[0].get("headers") or {},
                           client=alts[0].get("client", ""), alts=alts[1:])
                winsys.log(f"float: live stream switched to the {nxt['client']} player")
                relay.forbidden = False
                self._live_reloads = []
                self.restart_live(nxt)
                return
        if relay is not None and relay.forbidden and not spare and _APP is not None:
            winsys.log("float: live stream re-opened with another player")
            relay.forbidden = False
            self._live_reloads = []
            _APP._resolve_and_play(self.link["page"], self, quiet=True)
            return
        if spare and now - spare[0] < 90:                 # a fresh link is ready: switch to it right away
            self._spare = None
            winsys.log("float: live stream switched to the fresh link")
            self.restart_live(spare[1])
            return
        # a hiccup: just restart the local relay (2-3 s). Several in a minute: the link has expired, ask YouTube again
        if len(recent) > 3:
            self._live_reloads = []
            if _APP is not None:
                winsys.log(f"float: live stream re-opened ({'error' if error else 'stalled'})")
                _APP._resolve_and_play(self.link["page"], self, quiet=True)
            return
        relay = getattr(self, "_relay", None)
        self.player.setSource(QUrl(relay.url if relay is not None else self.path))   # ffmpeg starts again
        self.player.play()

    def _on_media_error(self, *_a):
        if self._live() and self.player is not None:
            import time
            if time.monotonic() - getattr(self, "_live_fixing", 0) < 8:      # one reconnect at a time
                return
            self._live_fixing = time.monotonic()
            winsys.log(f"float: live stream error, reconnecting: {self.player.errorString()}")
            QTimer.singleShot(300, self._live_continue)
            return
        winsys.log(f"float: cannot play {self.path}: {self.player.errorString()}")
        self.player.stop()
        self.player = None
        self.kind = "other"
        self.art = False
        self.aspect = None
        self.frame = None
        self._apply_size(200, 200)

    def _playing(self):
        from PySide6.QtMultimedia import QMediaPlayer
        return self.player is not None and self.player.playbackState() == QMediaPlayer.PlayingState

    def media_key(self, key):
        """Play/pause, next, previous, stop from the keyboard's media keys."""
        if not self.player:
            return None
        if key == "play":
            self._toggle_play()
            return "pause" if not self._playing() else "play"
        if key == "stop":
            self.player.pause()
            self.player.setPosition(0)
            return "stop"
        return key if self._step(1 if key == "next" else -1) else None

    LONG_PAUSE = 10 * 60          # seconds paused after which Play reopens the float instead

    def _toggle_play(self):
        if not self.player:
            return
        if self._playing():
            self.player.pause()
            self._paused_at = time.monotonic()
        else:
            paused = getattr(self, "_paused_at", None)
            if (paused is not None and time.monotonic() - paused > self.LONG_PAUSE and self.kind == "video"
                    and _APP is not None):
                # after hours (or a night asleep) the player and the video link are stale: the sound came back
                # but the picture and the window froze. Start it fresh in this same window, from the same point.
                winsys.log(f"float: playing again after {int((time.monotonic() - paused) / 60)} min paused — fresh start")
                self._paused_at = None
                pos = self.player.position()
                if self.link and self.link.get("page") and not _link_still_good(self.link):
                    self._resume_ms = pos
                    self.refresh_link()                  # a fresh address from the site (about 14 s)
                    return
                self._play_now = True
                self._load(self.path, self.link)
                self._resume_ms = pos
                return
            self._paused_at = None
            if self.player.duration() and self.player.position() >= self.player.duration() - 200:
                self.player.setPosition(0)
            self.player.play()

    # ---------------------------------------------------------------- geometry
    def _ratio(self):
        """The shape resizing keeps: the picture's or video's, unless Keep aspect ratio is off for this float."""
        return None if getattr(self, "free_shape", False) else self.aspect

    def set_keep_ratio(self, on):
        self.free_shape = not on
        if on and self.aspect:                           # back to the picture's shape
            tl = self.pos()
            self._apply_size(self.width(), self._height_for(self.width()))
            self.move(tl)
        self._scaled = None
        self.update()
        self._pin_changed()

    def _height_for(self, w):
        if self._ratio():
            return int(round(w / self._ratio()))
        return w if self.kind == "other" else 150      # audio: a short card

    def _apply_size(self, w, h):
        scr = (self.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        w = max(self.MIN_W, min(int(w), scr.width()))
        h = max(110, min(int(h), scr.height()))
        a = self._ratio()
        if a:                                             # keep the shape when a limit kicked in
            if w / h > a + 0.01:
                w = max(self.MIN_W, int(h * a))
            else:
                h = max(110, int(w / a))
        self.resize(w, h)
        self._scaled = None
        self.update()

    def _close_center(self):
        return QPointF(self.width() - 20, 20)

    def _band_h(self):
        return 62 if self.player else 40

    def _grip_rect(self):
        return QRectF(self.width() - 42, self.height() - 36, 30, 26)

    def _seek_rect(self):
        return QRectF(14, self.height() - 52, self.width() - 28, 4)

    def _vol_rect(self):
        return QRectF(44, self.height() - 27, 74, 6)

    def _set_volume_x(self, x):
        r = self._vol_rect()
        v = min(1.0, max(0.0, (x - r.left()) / r.width()))
        self.audio.setVolume(v)
        self.audio.setMuted(False)
        settings().setValue("float_volume", round(v, 3))
        self.update()

    def _mute_rect(self):
        return QRectF(10, self.height() - 38, 28, 28)

    def _play_center(self):
        if self.kind == "audio" and not self.art:
            return QPointF(self.width() / 2, (self.height() - self._band_h()) / 2 + 8)
        return QPointF(self.width() / 2, self.height() / 2 - 8)

    def _icon_rect(self):
        side = min(self.width(), self.height() - self._band_h()) * 0.55
        side = max(48, min(side, 256))
        cx, cy = self.width() / 2, (self.height() - self._band_h()) / 2 + 6
        return QRectF(cx - side / 2, cy - side / 2, side, side)

    def _edges(self, pos):
        e, c = self.EDGE, 18                                 # edge band, corner grab area
        x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
        l, t, r, b = x < e, y < e, x > w - e, y > h - e
        if (x < c or x > w - c) and (y < c or y > h - c) and (l or t or r or b):
            l, r, t, b = x < c, x > w - c, y < c, y > h - c    # near a corner: grab the corner
        return (l, t, r, b)                                   # left, top, right, bottom

    def _hit(self, pos):
        c = self._close_center()
        controls = self.ctrl > 0.4
        if controls and (pos.x() - c.x()) ** 2 + (pos.y() - c.y()) ** 2 <= (self.CLOSE_R + 4) ** 2:
            return "close"
        if controls and self._grip_rect().contains(pos):
            return "grip"
        if any(self._edges(pos)):
            return "edge"
        if self.player and controls:
            if self._seek_rect().adjusted(0, -8, 0, 8).contains(pos) and not self._live():
                return "seek"
            if self._mute_rect().contains(pos):
                return "mute"
            if self._vol_open and QRectF(38, self.height() - 38, 88, 28).contains(pos):
                return "vol"
            pc = self._play_center()
            if (pos.x() - pc.x()) ** 2 + (pos.y() - pc.y()) ** 2 <= 30 ** 2:
                return "play"
            for name, dx in (("prev", -62), ("next", 62)):
                if (pos.x() - pc.x() - dx) ** 2 + (pos.y() - pc.y()) ** 2 <= 22 ** 2:
                    return name
        if self.kind == "other" and self._icon_rect().contains(pos):
            return "icon"
        return "body"

    # ---------------------------------------------------------------- fading controls
    def set_taskbar(self, on):
        """Show this float as a button on the taskbar (so it's easy to get back to), or not."""
        geo, vis = self.geometry(), self.isVisible()
        self.setWindowFlag(Qt.Tool, not on)
        self.setWindowFlag(Qt.Window, True)
        self.setGeometry(geo)
        if vis:
            self.show()

    def set_on_top(self, on):
        self.on_top = bool(on)
        geo = self.geometry()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, self.on_top)
        self.setGeometry(geo)
        self.show()
        self._pin_changed()

    def _taskbar_tick(self):
        """A video or song playing in this float shows how far it got on its taskbar button (yellow when paused),
        like a media player. Nothing for live streams, pictures and icons."""
        if not winsys.IS_WIN or settings().value("float_taskbar", "true") != "true":
            return
        try:
            p = self.player
            dur = p.duration() if p is not None else 0
            if p is None or dur <= 0 or self._live():
                state, pos = winsys.TB_NONE, 0
            else:
                state = winsys.TB_NORMAL if self._playing() else winsys.TB_PAUSED
                pos = p.position()
            if state == winsys.TB_NONE and self._tb_state in (None, winsys.TB_NONE):
                return
            winsys.taskbar_progress(int(self.winId()), state, int(pos), int(dur))
            self._tb_state = state
        except RuntimeError:
            return

    def _keep_tick(self):
        """Every float stays open after a restart (or update) until you close it: it's remembered as soon as it has
        something in it, then every few seconds, with where a video or song had got to."""
        try:
            if self._placing or not self._has_content() or getattr(self, "_reopening", False):
                return
            if not self.pin_id:
                if self._no_keep or settings().value("float_keep", "true") != "true":
                    return
                self.set_pinned(True, startup=False)
            elif self.player is not None and not self._live():
                self._save_pin()
        except RuntimeError:
            return

    # ---------------------------------------------------------------- reopen when Windows starts
    def set_pinned(self, on, startup=True):
        pins = [x for x in _float_pins() if x.get("id") != self.pin_id]
        if not on:
            self._no_keep = True                         # you turned it off: don't keep it again by itself
        if on:
            import uuid
            self._no_keep = False
            self.pin_id = self.pin_id or uuid.uuid4().hex[:12]
            _save_float_pins(pins)
            self._save_pin()
            if startup and not winsys.startup_enabled():          # DragWheel itself has to start with Windows
                try:
                    winsys.set_startup(True)
                except Exception as e:
                    winsys.log(f"startup: {e}")
        else:
            self.pin_id = None
            _save_float_pins(pins)

    def _pin_changed(self):
        if getattr(self, "pin_id", None) and not getattr(self, "_placing", False):
            self._pin_timer.start()

    def state(self) -> dict:
        """Everything needed to bring this float back: file or link, place, size, playback."""
        g = self.geometry()
        st = {"id": self.pin_id, "src": self.link["page"] if self.link else str(self.path), "link": bool(self.link),
              "title": (self.link or {}).get("title", ""),
              "x": g.x(), "y": g.y(), "w": g.width(), "h": g.height(), "on_top": self.on_top}
        if getattr(self, "free_shape", False):
            st["free"] = True
        if self.player is not None and not self._live():
            st["pos"] = int(self.player.position())
            st["playing"] = bool(self._playing())
        return st

    def _save_pin(self):
        if not self.pin_id:
            return
        entry = self.state()
        entry["playing"] = False                         # after a restart it waits where it was, paused
        old = next((x for x in _float_pins() if x.get("id") == self.pin_id), None)
        if old == entry:                                 # nothing changed: don't write the setting again
            return
        pins = [x for x in _float_pins() if x.get("id") != self.pin_id] + [entry]
        _save_float_pins(pins)

    def moveEvent(self, e):
        super().moveEvent(e)
        self._pin_changed()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._pin_changed()

    def reopen(self, play=None):
        """Close this float and open it again: same size, place and media, from the same point."""
        if _APP is None or not self._has_content() or getattr(self, "_reopening", False):
            return
        self._reopening = True
        st = self.state()
        if play is not None:
            st["playing"] = bool(play)
        if self.link:
            st["src"] = self.link.get("saved") or self.link.get("page")
        winsys.log("float: reopen")
        self._pin_timer.stop()
        self.hide()
        QTimer.singleShot(0, self.close)                 # stays pinned to Windows start (not closed by you)
        QTimer.singleShot(120, lambda: _APP.open_float_state(st))

    def close_by_user(self):
        """Closed with ✕, Esc or the menu: it no longer reopens with Windows."""
        if self.pin_id:
            self.set_pinned(False)
        self.close()

    def _set_ctrl(self, v):
        self.ctrl = float(v)
        self.update()

    def _fade_to(self, target):
        if abs(self.ctrl - target) < 0.01 and self._fade.state() != QVariantAnimation.Running:
            return
        self._fade.stop()
        self._fade.setStartValue(self.ctrl)
        self._fade.setEndValue(float(target))
        self._fade.start()

    def _maybe_hide_controls(self):
        if not self.underMouse() and self._press is None:
            self._fade_to(0.0)

    def enterEvent(self, e):
        self._fade_to(1.0)

    def leaveEvent(self, e):
        self.hover = None
        self._vol_open = False
        if self._press is None:
            self._fade_to(0.0)
        self.update()

    # ---------------------------------------------------------------- paint
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        clip = QPainterPath()
        clip.addRoundedRect(r, self.RADIUS, self.RADIUS)
        p.setClipPath(clip)
        bare = self.kind == "other" and not self.link and quick_setting("float_icon_only", "true") == "true"
        if bare:                                            # just the icon and its name: no panel, frame or highlight
            p.fillRect(r, QColor(0, 0, 0, 1))               # (all but invisible, so the float still takes the mouse)
        else:
            p.fillRect(r, QColor(0, 0, 0) if self.kind == "video" else C("panel"))
        media = self.kind in ("image", "video") or self.art
        if self.kind == "image" or self.art:
            if self.free_shape:                             # any shape: the whole picture, centred, not stretched
                if self._scaled is None or getattr(self, "_scaled_for", None) != self.size():
                    self._scaled = self.src.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self._scaled_for = self.size()
                p.fillRect(r, QColor(0, 0, 0))
                p.drawPixmap((self.width() - self._scaled.width()) // 2, (self.height() - self._scaled.height()) // 2,
                             self._scaled)
            else:
                if self._scaled is None or self._scaled.size() != self.size():
                    self._scaled = self.src.scaled(self.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                p.drawPixmap(0, 0, self._scaled)
        elif self.kind == "video":
            if self.frame is not None:
                fr = QSizeF(self.frame.size()).scaled(QSizeF(self.size()), Qt.KeepAspectRatio)
                p.drawImage(QRectF((self.width() - fr.width()) / 2, (self.height() - fr.height()) / 2,
                                   fr.width(), fr.height()), self.frame)
        elif self.kind == "empty":
            box = r.adjusted(10, 10, -10, -10)
            pen = QPen(ACCENT if self._drop_hover else C("line"), 1.6, Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(box, 10, 10)
            p.setPen(C("text"))
            p.setFont(QFont(i18n.ui_font(), 11, QFont.DemiBold))
            p.drawText(box.adjusted(12, 0, -12, -box.height() / 2 + 6), Qt.AlignHCenter | Qt.AlignBottom, tr("Drop a file here"))
            p.setPen(C("dim"))
            p.setFont(QFont(i18n.ui_font(), 9))
            p.drawText(box.adjusted(14, box.height() / 2 + 8, -14, -8), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                       tr("or press Ctrl+V to play a copied link · right-click for saved links"))
        else:                                               # icon, centred; highlights on hover
            ir = self._icon_rect()
            if self.hover == "icon" and not bare:
                hl = QColor(ACCENT)
                hl.setAlpha(46)
                p.setPen(QPen(ACCENT, 1.5))
                p.setBrush(hl)
                p.drawRoundedRect(ir.adjusted(-12, -12, 12, 12), 16, 16)
            want = (int(ir.width()), int(ir.height()), self.src.cacheKey())
            if getattr(self, "_icon_for", None) != want:     # scale once per size, not on every repaint
                self._icon_px = self.src.scaled(want[0], want[1], Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self._icon_for = want
            p.drawPixmap(ir.toRect(), self._icon_px)
            if bare and not self._name_hidden():           # the name under the icon
                st = float_label(self.path)
                pt = float(st.get("size") or self._auto_label_pt())
                nf = QFont(st.get("font") or "Segoe UI")
                nf.setPointSizeF(pt)
                nf.setBold(st.get("bold", True))
                p.setFont(nf)
                nr = QRectF(6, ir.bottom() + pt * 0.4, self.width() - 12, pt * 3)
                txt = QFontMetrics(nf).elidedText(st.get("name") or self._default_label(), Qt.ElideRight, int(nr.width()))
                if st.get("hover"):                         # only while the mouse is over the float (fades)
                    p.setOpacity(max(0.0, min(1.0, self.ctrl)))
                col = QColor(st.get("color") or "#ffffff")
                dark = col.lightnessF() < 0.4                # a dark name gets a light outline, so it reads anywhere
                p.setPen(QColor(255, 255, 255, 170) if dark else QColor(0, 0, 0, 170))
                for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1), (0, 1.5)):
                    p.drawText(nr.translated(dx, dy), Qt.AlignHCenter | Qt.AlignTop, txt)
                p.setPen(col)
                p.drawText(nr, Qt.AlignHCenter | Qt.AlignTop, txt)
                p.setOpacity(1.0)
        # ---- subtitles (above the controls when they are showing)
        if self.kind == "video" and self.player:
            text = self._current_subtitle()
            if text:
                self._paint_subtitle(p, text)
        if getattr(self, "_busy", False) and self.kind == "video" and (self.player is not None or (self.link or {}).get("pending")):
            self._paint_busy(p)
        # ---- overlay controls (fade with the cursor)
        if self.ctrl > 0.01:
            p.setOpacity(self.ctrl)
            band = self._band_h()
            if media:
                g = QLinearGradient(0, self.height() - band - 30, 0, self.height())
                g.setColorAt(0, QColor(0, 0, 0, 0))
                g.setColorAt(1, QColor(0, 0, 0, 175))
                p.fillRect(QRectF(0, self.height() - band - 30, self.width(), band + 30), g)
            fg = QColor("#ffffff") if media else C("text")
            f = QFont(i18n.ui_font(), 9)
            p.setFont(f)
            left = 14
            if self.player:
                self._paint_player(p, fg)
                left = 44
                if self._vol_open:                         # volume slider next to the speaker
                    vr = self._vol_rect()
                    p.setPen(Qt.NoPen)
                    p.setBrush(QColor(255, 255, 255, 70) if (self.kind == "video" or self.art) else C("busy_track"))
                    p.drawRoundedRect(vr, 3, 3)
                    vol = 0.0 if self.audio.isMuted() else self.audio.volume()
                    p.setBrush(ACCENT)
                    p.drawRoundedRect(QRectF(vr.left(), vr.top(), vr.width() * vol, vr.height()), 3, 3)
                    p.drawEllipse(QPointF(vr.left() + vr.width() * vol, vr.center().y()), 6, 6)
                    left = 130
                t = ("● " + tr("LIVE")) if self._live() else f"{_fmt_time(self.player.position())} / {_fmt_time(self.player.duration())}"
                if not self._live() and self.repeat in ("one", "all"):
                    t += "   ↻" + ("1" if self.repeat == "one" or self.link else "")
                p.setPen(fg)
                tw = QFontMetrics(f).horizontalAdvance(t) + 12
                p.drawText(QRectF(left, self.height() - 38, tw, 28), Qt.AlignVCenter | Qt.AlignLeft, t)
                left += tw
            name_r = QRectF(left, self.height() - 38, self._grip_rect().left() - left - 6, 28)
            if not bare:                                    # (a bare icon has its name under it all the time)
                p.setPen(fg)
                p.drawText(name_r, Qt.AlignVCenter | Qt.AlignLeft,
                           QFontMetrics(f).elidedText(self.display_name(), Qt.ElideMiddle, int(max(0, name_r.width()))))
            gr = self._grip_rect()
            p.setPen(Qt.NoPen)
            p.setBrush(ACCENT if self.hover == "grip" else (QColor(255, 255, 255, 46) if media else C("grip")))
            p.drawRoundedRect(gr, 7, 7)
            p.setBrush(ON_ACCENT if self.hover == "grip" else fg)
            for i in range(3):
                for j in range(2):
                    p.drawEllipse(QPointF(gr.center().x() - 3 + j * 6, gr.center().y() - 5 + i * 5), 1.6, 1.6)
            c = self._close_center()
            p.setBrush(C("danger") if self.hover == "close" else QColor(20, 20, 22, 190))
            p.setPen(QPen(QColor(255, 255, 255, 70), 1))
            p.drawEllipse(c, self.CLOSE_R, self.CLOSE_R)
            pen = QPen(QColor("#ffffff"), 2)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            d = 4.2
            p.drawLine(QPointF(c.x() - d, c.y() - d), QPointF(c.x() + d, c.y() + d))
            p.drawLine(QPointF(c.x() + d, c.y() - d), QPointF(c.x() - d, c.y() + d))
            p.setOpacity(1.0)
        # border
        p.setClipping(False)
        p.setBrush(Qt.NoBrush)
        if self._drop_hover:                                # a file is being dragged over: drop replaces
            p.setPen(QPen(ACCENT, 3))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), self.RADIUS, self.RADIUS)
        else:
            col = QColor(ACCENT if (self.hover and self.hover != "icon") else C("line"))
            if bare:                                        # icon only: never a frame
                col.setAlphaF(0.0)
            if col.alphaF() > 0.01:
                p.setPen(QPen(col, 1.2))
                p.drawRoundedRect(r, self.RADIUS, self.RADIUS)

    def _paint_subtitle(self, p, text):
        size = max(10, min(22, self.height() / 18))
        f = QFont(i18n.ui_font(), 1)
        f.setPointSizeF(size)
        f.setWeight(QFont.DemiBold)
        fm = QFontMetrics(f)
        bottom = self.height() - (self._band_h() + 8) * self.ctrl - 12
        width = self.width() - 32
        rect = fm.boundingRect(QRect(0, 0, int(width), 1000), Qt.AlignHCenter | Qt.TextWordWrap, text)
        box = QRectF((self.width() - rect.width()) / 2 - 8, bottom - rect.height() - 4, rect.width() + 16, rect.height() + 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(box, 6, 6)
        p.setFont(f)
        p.setPen(QColor("#ffffff"))
        p.drawText(box, Qt.AlignCenter | Qt.TextWordWrap, text)

    def _paint_player(self, p, fg):
        # big play / pause in the middle (hidden while the loading circle shows, like YouTube)
        pc = self._play_center()
        p.setPen(Qt.NoPen)
        if getattr(self, "_busy", False) and self.kind == "video":
            p.setOpacity(0.0)
        p.setBrush(ACCENT if self.hover == "play" else QColor(20, 20, 22, 170))
        p.drawEllipse(pc, 26, 26)
        p.setBrush(ON_ACCENT if self.hover == "play" else QColor("#ffffff"))
        if self._playing():
            p.drawRoundedRect(QRectF(pc.x() - 8, pc.y() - 10, 6, 20), 2, 2)
            p.drawRoundedRect(QRectF(pc.x() + 2, pc.y() - 10, 6, 20), 2, 2)
        else:
            tri = QPolygonF([QPointF(pc.x() - 7, pc.y() - 11), QPointF(pc.x() - 7, pc.y() + 11), QPointF(pc.x() + 11, pc.y())])
            p.drawPolygon(tri)
        # previous / next in the folder (dimmed at the ends)
        for name, dx, d in (("prev", -62, -1), ("next", 62, 1)):
            c = QPointF(pc.x() + dx, pc.y())
            have = self._neighbour(d) is not None
            p.setOpacity(0.0 if (getattr(self, "_busy", False) and self.kind == "video") else self.ctrl * (1.0 if have else 0.35))
            p.setBrush(ACCENT if (self.hover == name and have) else QColor(20, 20, 22, 150))
            p.drawEllipse(c, 18, 18)
            p.setBrush(ON_ACCENT if (self.hover == name and have) else QColor("#ffffff"))
            sgn = 1 if d > 0 else -1
            p.drawPolygon(QPolygonF([QPointF(c.x() - 5 * sgn, c.y() - 7), QPointF(c.x() - 5 * sgn, c.y() + 7),
                                     QPointF(c.x() + 4 * sgn, c.y())]))
            p.drawRect(QRectF(c.x() + 4 * sgn - (2 if sgn > 0 else 0), c.y() - 7, 2, 14))
        p.setOpacity(self.ctrl)
        # seek bar
        sr = self._seek_rect()
        p.setBrush(QColor(255, 255, 255, 70) if (self.kind == "video" or self.art) else C("busy_track"))
        p.drawRoundedRect(sr, 2, 2)
        dur = self.player.duration()
        if dur > 0 and not self._live():
            frac = min(1.0, self.player.position() / dur)
            p.setBrush(ACCENT)
            p.drawRoundedRect(QRectF(sr.left(), sr.top(), sr.width() * frac, sr.height()), 2, 2)
            p.drawEllipse(QPointF(sr.left() + sr.width() * frac, sr.center().y()), 6 if self.hover == "seek" else 4.5,
                          6 if self.hover == "seek" else 4.5)
        # speaker (click to mute)
        mr = self._mute_rect()
        cx, cy = mr.center().x(), mr.center().y()
        p.setBrush(ACCENT if self.hover == "mute" else fg)
        p.drawPolygon(QPolygonF([QPointF(cx - 8, cy - 3), QPointF(cx - 4, cy - 3), QPointF(cx + 1, cy - 8),
                                 QPointF(cx + 1, cy + 8), QPointF(cx - 4, cy + 3), QPointF(cx - 8, cy + 3)]))
        pen = QPen(ACCENT if self.hover == "mute" else fg, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if self.audio.isMuted():
            p.drawLine(QPointF(cx + 4, cy - 4), QPointF(cx + 10, cy + 4))
            p.drawLine(QPointF(cx + 10, cy - 4), QPointF(cx + 4, cy + 4))
        else:
            p.drawArc(QRectF(cx - 3, cy - 6, 10, 12), -50 * 16, 100 * 16)
            p.drawArc(QRectF(cx - 3, cy - 10, 16, 20), -50 * 16, 100 * 16)
        p.setPen(Qt.NoPen)

    # ---------------------------------------------------------------- mouse
    def _seek_to(self, x):
        sr = self._seek_rect()
        if self.player and self.player.duration() > 0:
            frac = min(1.0, max(0.0, (x - sr.left()) / max(1.0, sr.width())))
            self.player.setPosition(int(self.player.duration() * frac))

    last_used = None                 # the float the keyboard media keys control

    def mousePressEvent(self, e):
        FloatWindow.last_used = self
        if e.button() == Qt.RightButton:
            self._menu(e.globalPosition().toPoint())
            return
        if e.button() != Qt.LeftButton:
            return
        hit = self._hit(e.position())
        gp = e.globalPosition().toPoint()
        if hit == "close":
            self.close_by_user()
            return
        if hit == "mute":
            self.audio.setMuted(not self.audio.isMuted())
            self.update()
            return
        if hit == "vol":
            self._vol_drag = True
            self._set_volume_x(e.position().x())
            return
        if hit == "seek":
            self._seeking = True
            self._seek_to(e.position().x())
        if hit == "edge":
            self._press = ("edge", gp, e.position(), self.geometry(), self._edges(e.position()))
        else:
            self._press = (hit, gp, e.position(), self.geometry(), None)

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._vol_drag:
            self._set_volume_x(pos.x())
            return
        if self._press is not None:
            kind, gp0, lp0, geo0, edges = self._press
            gp = e.globalPosition().toPoint()
            moved = (gp - gp0).manhattanLength()
            if self._seeking:
                self._seek_to(pos.x())
            elif kind == "grip":
                if moved > 6:
                    self._press = None
                    self._drag_out()
            elif kind == "edge":
                self._resize_drag(gp - gp0, geo0, edges)
            elif moved > 3 or kind == "moving":
                if kind != "moving":
                    self._press = ("moving", gp0, lp0, geo0, None)
                self.move(geo0.topLeft() + (gp - gp0))
            return
        h = self._hit(pos)
        vol_open = h in ("mute", "vol")
        if vol_open != self._vol_open:
            self._vol_open = vol_open
            h = self._hit(pos)
            self.update()
        if h != self.hover:
            self.hover = h
            if h == "edge":
                l, t, r, b = self._edges(pos)
                cur = (Qt.SizeFDiagCursor if (l and t) or (r and b) else Qt.SizeBDiagCursor if (r and t) or (l and b)
                       else Qt.SizeHorCursor if (l or r) else Qt.SizeVerCursor)
            else:
                cur = {"close": Qt.PointingHandCursor, "grip": Qt.OpenHandCursor, "icon": Qt.PointingHandCursor,
                       "play": Qt.PointingHandCursor, "prev": Qt.PointingHandCursor, "next": Qt.PointingHandCursor, "seek": Qt.PointingHandCursor, "mute": Qt.PointingHandCursor, "vol": Qt.PointingHandCursor
                       }.get(h, Qt.SizeAllCursor)
            self.setCursor(cur)
            self.update()

    def _resize_drag(self, delta, geo0, edges):
        l, t, r, b = edges
        x, y, w, h = geo0.x(), geo0.y(), geo0.width(), geo0.height()
        dw = (delta.x() if r else -delta.x() if l else 0)
        dh = (delta.y() if b else -delta.y() if t else 0)
        nw, nh = w + dw, h + dh
        a = self._ratio()
        if a:                                 # keep the picture's shape
            if (l or r) and (t or b):         # corner: follow the mouse in any direction (project on the diagonal)
                k = (dw * a + dh) / (a ** 2 + 1)
                nw, nh = w + k * a, h + k
            elif l or r:
                nh = nw / a
            else:
                nw = nh * a
        self._apply_size(nw, nh)
        nw, nh = self.width(), self.height()
        nx = x + (w - nw) if l else x
        ny = y + (h - nh) if t else y
        if a and (t or b) and not (l or r):                    # grow sideways around the centre
            nx = x + (w - nw) // 2
        if a and (l or r) and not (t or b):
            ny = y + (h - nh) // 2
        self.move(int(nx), int(ny))

    def mouseReleaseEvent(self, e):
        self._vol_drag = False
        press, self._press = self._press, None
        was_seeking, self._seeking = self._seeking, False
        if press is None or was_seeking or e.button() != Qt.LeftButton:
            return
        kind = press[0]
        if kind == "icon":
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))
        elif kind in ("prev", "next"):
            self._step(-1 if kind == "prev" else 1)
        elif kind == "play" or (kind == "body" and self.kind == "video"):
            self._toggle_play()
        if not self.underMouse():
            self._fade_to(0.0)

    def mouseDoubleClickEvent(self, e):
        if self._hit(e.position()) in ("body", "icon") and self._nothing_playing():
            self._press = None
            QTimer.singleShot(0, self._browse_file)                       # nothing showing or playing: double-click picks a file
            return
        if self._hit(e.position()) == "body" and self.kind == "image":
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.path))

    def wheelEvent(self, e):
        if self.player and self.hover in ("mute", "vol"):          # scroll over the speaker = volume
            v = min(1.0, max(0.0, self.audio.volume() + (0.05 if e.angleDelta().y() > 0 else -0.05)))
            self.audio.setVolume(v)
            self.audio.setMuted(False)
            settings().setValue("float_volume", round(v, 3))
            self.update()
            return
        step = 1.1 if e.angleDelta().y() > 0 else 1 / 1.1
        g0 = self.geometry()
        self._apply_size(self.width() * step, (self._height_for(self.width() * step) if self._ratio()
                                                else self.height() * step))
        dw, dh = self.width() - g0.width(), self.height() - g0.height()
        if dw or dh:                                 # grow or shrink around the middle; at a limit it stays put
            self._grow_left = getattr(self, "_grow_left", 0.0) + dw / 2
            self._grow_top = getattr(self, "_grow_top", 0.0) + dh / 2
            mx, my = int(self._grow_left), int(self._grow_top)    # whole pixels, the rest kept for next time
            self._grow_left -= mx
            self._grow_top -= my
            self.move(g0.x() - mx, g0.y() - my)

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.Paste):
            f = _clipboard_media_file()
            if f:                                    # a copied video/song (or its path) plays here
                self._play_now = True
                self._load(f)
                self._fade_to(1.0)
                self.come_forward()
                QTimer.singleShot(1600, self._maybe_hide_controls)
            elif _APP is not None:
                _APP.play_link(target=self)
            return
        if e.key() == Qt.Key_Escape:
            self.close_by_user()
        elif e.key() == Qt.Key_Space and self.player:
            self._toggle_play()
        elif e.key() == Qt.Key_R and self.player:                             # R: repeat off → this one → all
            order = ["off", "one"] if self.link else ["off", "one", "all"]
            self.set_repeat(order[(order.index(self.repeat) + 1) % len(order)] if self.repeat in order else "off")
        elif e.key() in (Qt.Key_PageUp, Qt.Key_PageDown) and self.player:     # media keys: DragWheelApp._media_tick
            self._step(-1 if e.key() == Qt.Key_PageUp else 1)
        elif e.key() in (Qt.Key_Left, Qt.Key_Right) and self.player:
            self.player.setPosition(max(0, self.player.position() + (5000 if e.key() == Qt.Key_Right else -5000)))

    def _drag_out(self):
        md = QMimeData()
        md.setUrls([QUrl(self.link["page"]) if self.link else QUrl.fromLocalFile(self.path)])
        drag = QDrag(self)
        drag.setMimeData(md)
        thumb = QPixmap.fromImage(self.frame) if (self.kind == "video" and self.frame is not None) else self.src
        drag.setPixmap(thumb.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        drag.exec(Qt.CopyAction | Qt.MoveAction | Qt.LinkAction, Qt.CopyAction)

    def _menu(self, at):
        m = QMenu(self)
        if self.kind == "video" and self.player:
            self._add_track_menus(m)
        if self.player and not self._live():
            rm = m.addMenu(tr("Repeat"))
            for key, label in (("off", tr("Off")), ("one", tr("Repeat this one")),
                               ("all", tr("Loop all (the whole folder)") if not self.link else tr("Loop"))):
                if self.link and key == "all":
                    continue
                a = rm.addAction(label)
                a.setCheckable(True)
                a.setChecked(bool(self.repeat == key or (self.link and key == "one" and self.repeat == "all")))
                a.triggered.connect(lambda _=False, k=key: self.set_repeat(k))
            sp = m.addMenu(tr("Speed"))
            cur = self.player.playbackRate()
            for rate in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
                a = sp.addAction(f"{rate:g}×" + ("  (" + tr("Normal") + ")" if rate == 1.0 else ""))
                a.setCheckable(True)
                a.setChecked(abs(cur - rate) < 0.01)
                a.triggered.connect(lambda _=False, r=rate: self.set_rate(r))
        if self.player:
            m.addSeparator()
        m.addAction(tr("Open"), self._open_original)
        if self.link:
            m.addAction(tr("Copy"), lambda: QGuiApplication.clipboard().setText(self.link["page"]))
        elif self._has_content():
            m.addAction(tr("Show in Explorer"), lambda: winsys.reveal(self.path))
            m.addAction(tr("Copy path"), lambda: QGuiApplication.clipboard().setText(str(Path(self.path))))
        if self.link:
            m.addAction(tr("Refresh"), self.refresh_link)
            qm = m.addMenu(tr("Quality"))
            cur = settings().value("link_quality", "1080p")
            for q in engine.LINK_QUALITIES:
                a = qm.addAction(q + (f"  ({tr('now playing')})" if self.link.get("height") and str(self.link.get("height")) + "p" == q else ""))
                a.setCheckable(True)
                a.setChecked(q == cur)
                a.triggered.connect(lambda _=False, q=q: self._set_quality(q))
        if _APP is not None:
            m.addAction(tr("Paste link"), lambda: _APP.play_link(target=self))
            saved = saved_links()
            cur_key = self.link and (self.link.get("saved") or self.link.get("page"))
            is_saved = bool(cur_key) and any(x["url"] == cur_key for x in saved)
            if cur_key and not is_saved:
                m.addAction(tr("Save this link"), lambda _=False, k=cur_key: (
                    remember_link(k, self.link.get("title") if self.link else None), self.update()))
            sm = m.addMenu(tr("Saved links"))
            if not saved:
                a = sm.addAction(tr("Links you save show up here"))
                a.setEnabled(False)
            for it in saved[:5]:                            # the last five; all of them in Manage saved links
                title = link_name(it)
                title = title if len(title) <= 60 else title[:57] + "…"
                a = sm.addAction(title, lambda _=False, u=it["url"]: _APP.play_link(target=self, url=u))
                a.setToolTip(it["url"])
            if saved:
                sm.addSeparator()
                cur_key = next((x["url"] for x in saved if self.link and x["url"] in (self.link.get("saved"), self.link.get("page"))), None)
                if cur_key:
                    sm.addAction(tr("Rename this link…"), self._rename_link)
                    sm.addAction(tr("Remove this link from the list"), lambda _=False, k=cur_key: forget_link(k))
                sm.addAction(tr("Manage saved links…"),
                             lambda: SavedLinksDialog(lambda u: _APP.play_link(target=self, url=u)).exec())
                sm.addAction(tr("Clear the list"), lambda: settings().setValue("float_links", "[]"))
            sm.setToolTipsVisible(True)
            rm = m.addMenu(tr("Recently played"))
            recent = recent_played()
            if not recent:
                a = rm.addAction(tr("Links and files you play in Float show up here"))
                a.setEnabled(False)
            for it in recent[:10]:
                t = it.get("title") or it["key"]
                t = t if len(t) <= 60 else t[:57] + "…"
                a = rm.addAction(("🔗  " if it["kind"] == "link" else "🎞  ") + t,
                                 lambda _=False, it=it: self._play_recent(it))
                a.setToolTip(it["key"])
            if recent:
                rm.addSeparator()
                rm.addAction(tr("Manage recently played…"), lambda: RecentPlayedDialog(self._play_recent).exec())
                rm.addAction(tr("Clear the list"), lambda: forget_played())
            rm.setToolTipsVisible(True)
        if self.kind == "other" and not self.link and self._has_content():     # an app, folder, shortcut…
            nm = m.addMenu(tr("Name and icon"))
            shown = nm.addAction(tr("Show the name"))
            shown.setCheckable(True)
            shown.setChecked(not self._name_hidden())
            shown.toggled.connect(self._set_name_shown)
            hov = nm.addAction(tr("Auto hide name"))
            hov.setCheckable(True)
            hov.setChecked(bool(float_label(self.path).get("hover")))
            hov.setEnabled(not self._name_hidden())
            hov.toggled.connect(self._set_name_hover)
            nm.addAction(tr("Rename…"), self._rename_float)
            nm.addAction(tr("Font, size and colour…"), self._name_style)
            nm.addSeparator()
            nm.addAction(tr("Change icon…"), self._change_icon)
            if float_label(self.path).get("icon"):
                nm.addAction(tr("Use the normal icon"), lambda: self._set_icon(None))
            if float_label(self.path):
                nm.addSeparator()
                nm.addAction(tr("Back to normal"),
                             lambda: (self._set_icon(None), set_float_label(self.path, {}), self.update()))
            if settings().value("float_icon_only", "true") != "true":    # the name shows only on a bare icon
                for a in nm.actions():
                    if a.text() not in (tr("Rename…"), tr("Change icon…"), tr("Use the normal icon")):
                        a.setEnabled(False)
                hint = nm.addAction(tr("Turn on Settings → Float → Remove float border to show it"))
                hint.setEnabled(False)
        m.addSeparator()
        if self.aspect and self.kind in ("image", "video"):
            kr = m.addAction(tr("Keep aspect ratio"))
            kr.setCheckable(True)
            kr.setChecked(not self.free_shape)
            kr.setToolTip(tr("Off: resize the float to any shape (the picture isn't stretched)"))
            kr.toggled.connect(self.set_keep_ratio)
        top = m.addAction(tr("Always on top"))
        top.setCheckable(True)
        top.setChecked(self.on_top)
        top.toggled.connect(self.set_on_top)
        boot = m.addAction(tr("Keep open after restart"))
        boot.setCheckable(True)
        boot.setChecked(bool(self.pin_id))
        boot.setToolTip(tr("This float comes back at the same place, with the same file or link, until you close it"))
        boot.toggled.connect(self.set_pinned)
        if self._has_content() and _APP is not None:
            m.addAction(tr("Reopen"), lambda: self.reopen())
        m.addAction(tr("Close"), self.close_by_user)
        m.exec(at)

    def closeEvent(self, e):
        self._keep_timer.stop()
        self._tb_timer.stop()
        self._pin_timer.stop()
        self._drop_companion()
        self._stop_relay()
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())
        self.closed.emit()
        super().closeEvent(e)
