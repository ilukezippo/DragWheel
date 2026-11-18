"""DragWheel: File actions (don't use the engine)

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


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
            A("rename", "Rename…", self.rename, "several at once"),
            A("hash", "Checksum", self.checksum, "SHA-256"),
            A("unblock", "Unblock", self.unblock, "downloaded files"),
            A("phone", "Send to phone", self.phone),
            A("shred", "Shred…", self.shred, "can't be undone"),
        ] + ([A("readqr", "Read QR code", self.read_qr)]
             if paths and all(engine.EXT_CATEGORY.get(engine.ext_of(x)) == "image" for x in paths) else [])

    def read_qr(self, paths, p):
        """What the QR codes in these pictures say."""
        def work(state):
            out = []
            for f in paths:
                out += find_codes_in_file(f)
            return out

        def finish(codes):
            if codes:
                self.app.show_qr_result(codes)
            else:
                self.app.toast.show_msg(tr("Read QR code"), tr("No QR code found in this picture."), "err", 5000)
        self._background(tr("Read QR code"), Path(paths[0]).name, work, finish)

    def rename(self, paths, p):
        dlg = BatchRenameDialog(paths)
        if dlg.exec() != QDialog.Accepted:
            return
        try:
            done = dlg.apply()
        except OSError as e:
            self.app.toast.show_msg(tr("Couldn't rename"), str(e), "err", 8000)
            return
        winsys.log("renamed: " + "; ".join(f"{Path(o).name} -> {Path(n).name}" for o, n in done[:50]))
        self.app.toast.show_result(tr("Renamed {n} files", n=len(done)), [n for _, n in done])

    def _background(self, title, name, work, finish, progress=None):
        """Run `work(state)` off the main thread so the wheel and floats stay responsive; a card shows it's busy
        (with `progress(state)` text) and has a Cancel button that sets state["stop"]. `finish(result)` runs here."""
        state, result = {"stop": False}, {}
        card = self.app.toast.show_busy(title, name, lambda: state.update(stop=True))

        def run():
            try:
                result["ok"] = work(state)
            except Exception as e:
                result["err"] = e

        def check():
            if not result:
                if progress is not None and card in self.app.toast.cards:
                    text = progress(state)
                    if text:
                        card.body.setText(text)
                QTimer.singleShot(200, check)
                return
            if card in self.app.toast.cards:
                card.close_card()
            if "err" in result:
                winsys.log(f"{title}: {result['err']}")
                self.app.toast.show_msg(title, str(result["err"]), "err", 8000)
                return
            finish(result["ok"])
        threading.Thread(target=run, daemon=True).start()
        QTimer.singleShot(200, check)

    def unblock(self, paths, p):
        """Remove Windows' "This file came from another computer" mark (folders: everything inside)."""
        name = Path(paths[0]).name if len(paths) == 1 else tr("{n} files", n=len(paths))

        def work(st):
            return winsys.unblock(paths, progress=lambda n: st.update(n=n), stop=lambda: st["stop"])

        def finish(r):
            n, blocked, failed = r
            if failed:
                self.app.toast.show_msg(tr("Unblock"), tr("{n} files couldn't be unblocked", n=failed), "err", 6000)
            elif blocked:
                self.app.toast.show_msg(tr("Unblocked {n} files", n=blocked), tr("Windows won't warn about them any more."), "ok", 5000)
            else:
                self.app.toast.show_msg(tr("Unblock"), tr("Nothing was blocked ({n} files checked)", n=n), "info", 5000)
        self._background(tr("Unblock") + "…", name, work, finish,
                         lambda st: tr("{n} files checked", n=f"{st['n']:,}") if st.get("n") else None)

    def checksum(self, paths, p):
        files = [Path(x) for x in paths if Path(x).is_file()]
        if not files:
            self.app.toast.show_msg(tr("Checksum"), tr("Pick files, not folders"), "err", 4000)
            return
        card = self.app.toast.show_busy(tr("Checksum"), files[0].name if len(files) == 1 else tr("{n} files", n=len(files)))
        result = {}
        clip = QGuiApplication.clipboard().text().strip().lower()

        def work():
            try:
                result["ok"] = [(f, file_sha256(f)) for f in files]
            except Exception as e:
                result["err"] = str(e)

        def check():
            if not result:
                QTimer.singleShot(150, check)
                return
            if card in self.app.toast.cards:
                card.close_card()
            if "err" in result:
                self.app.toast.show_msg(tr("Checksum"), result["err"], "err", 6000)
                return
            pairs = result["ok"]
            text = "\n".join(f"{h}  {f.name}" for f, h in pairs)
            import re as _re
            if _re.fullmatch(r"[0-9a-f]{64}", clip):                     # a hash was copied: compare
                match = next((f for f, h in pairs if h == clip), None)
                if match:
                    self.app.toast.show_msg("✓ " + tr("Checksum matches"), tr("{name} is the genuine file.", name=match.name), "ok", 10000)
                else:
                    self.app.toast.show_msg("✗ " + tr("Checksum doesn't match"),
                                            tr("The copied checksum is different — the file may be damaged or not the original."),
                                            "err", 12000)
                return
            QGuiApplication.clipboard().setText(text)
            short = pairs[0][1][:16] + "…" if len(pairs) == 1 else tr("{n} files", n=len(pairs))
            self.app.toast.show_msg(tr("SHA-256 copied"), f"{short}<br><small>{tr('Copy a published checksum first to compare it instead.')}</small>", "ok", 9000)
        threading.Thread(target=work, daemon=True).start()
        QTimer.singleShot(150, check)

    def phone(self, paths, p):
        chooser = SendChooser(paths)
        ok = chooser.exec() == QDialog.Accepted
        choice = chooser.choice if ok else None
        mode = {"wifi": "wifi", "pclink": "tunnel"}.get(choice)
        key = share_key(paths)
        live = getattr(self.app, "_live_phone", {})
        for k, w in list(live.items()):                    # shares kept going: same way again = same window
            try:
                gone = w.ended
            except RuntimeError:
                gone = True
            if gone:
                live.pop(k, None)
        self.app._live_phone = live
        if not ok:
            return
        if (mode, key) in live:
            w = live[(mode, key)]
            w.back = lambda: self.phone(paths, p)
            w.show()
            w.raise_()
            w.activateWindow()
            return
        if chooser.choice == "quick":
            self.quick_share(paths)
            return
        if chooser.choice == "bluetooth":
            self.bluetooth(paths)
            return
        def open_window(w):
            w.back = lambda: self.phone(paths, p)
            self.app._phone_windows = getattr(self.app, "_phone_windows", [])
            self.app._phone_windows.append(w)
            if isinstance(w, PhoneShare):
                self.app._live_phone[(w.mode, key)] = w
            w.show()
            w.raise_()
        if chooser.choice == "pclink":
            self.app._ensure_model("cloudflared", tr("Link from this PC"),
                                   lambda: open_window(PhoneShare(paths, mode="tunnel")))
            return
        if chooser.choice in ("internet", "cloud"):        # already shared and the link still works: the same code
            item = live_share(chooser.choice, paths)
            if item:
                fresh = (lambda: open_window(InternetShare(paths))) if chooser.choice == "internet" else \
                    (lambda: open_window(CloudShare(paths)))
                open_window(ShareQR(item, tr("Internet link") if chooser.choice == "internet" else tr("Cloud link"),
                                    new=fresh))
                return
        if chooser.choice == "cloud":
            open_window(CloudShare(paths))
            return
        open_window(PhoneShare(paths) if chooser.choice == "wifi" else InternetShare(paths))

    def quick_share(self, paths):
        exe = winsys.quick_share_installed()
        ok = False
        if exe:
            try:                                          # the same call Quick Share's own right-click entry makes
                import subprocess
                subprocess.Popen([exe, "--files-from=context-menu", *[str(Path(p)) for p in paths]],
                                 creationflags=engine.NO_WINDOW)
                winsys.log(f"quick share: started with {len(paths)} item(s)")
                ok = True
            except Exception as e:
                winsys.log(f"quick share: {e}")
        if ok:
            self.app.toast.show_msg(tr("Quick Share"), tr("Pick your phone in the Quick Share window, then tap Accept on the phone."), "info", 6000)
            return
        box = QMessageBox()
        box.setWindowTitle(f"{APP} — " + tr("Quick Share"))
        box.setWindowIcon(app_icon())
        box.setStyleSheet(i18n.css(DIALOG_CSS))
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        if exe:
            box.setText(tr("Quick Share is installed but didn't offer to send these files. Opening it — drag the files into its window."))
            box.exec()
            os.startfile(exe)
            winsys.reveal(paths)
            return
        box.setText("<b>" + tr("Quick Share isn't installed") + "</b><br><br>" +
                    tr("It's free from Google and sends files to nearby Android phones (Samsung phones have it built in). "
                       "Install it once, then choose Quick Share again."))
        get = box.addButton(tr("Get Quick Share"), QMessageBox.AcceptRole)
        box.addButton(tr("Close"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is get:
            QDesktopServices.openUrl(QUrl(QUICK_SHARE_URL))

    def bluetooth(self, paths):
        """Windows' own Bluetooth file sender, with the files already chosen (what Send To → Bluetooth does)."""
        exe = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "fsquirt.exe"
        files = [str(Path(p)) for p in paths if Path(p).is_file()]
        if not exe.exists():
            self.app.toast.show_msg(tr("Bluetooth"), tr("This PC has no Bluetooth file sending."), "err", 6000)
            return
        if not files:
            self.app.toast.show_msg(tr("Bluetooth"), tr("Pick files, not folders"), "err", 5000)
            return
        ok = False
        link = winsys.sendto_entry("bluetooth")
        if link is not None:
            try:                                          # what right-click → Send to → Bluetooth device does
                ok = winsys.drop_files_on(link, files)
            except Exception as e:
                winsys.log(f"bluetooth drop: {e}")
        if not ok:
            import subprocess
            subprocess.Popen([str(exe), *files])
        self.app.toast.show_msg(tr("Bluetooth"), tr("Choose your phone in the Bluetooth window, then accept the files on the phone. "
                                                    "The phone must be paired with this PC first."), "info", 8000)

    def shred(self, paths, p):
        box = QMessageBox()
        box.setWindowTitle(f"{APP} — " + tr("Shred…").rstrip("…"))
        box.setWindowIcon(app_icon())
        box.setStyleSheet(i18n.css(DIALOG_CSS))
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        box.setIcon(QMessageBox.Warning)
        names = "<br>".join("• " + Path(x).name for x in paths[:6]) + ("<br>…" if len(paths) > 6 else "")
        box.setText("<b>" + tr("Destroy {n} item(s) for good?", n=len(paths)) + "</b><br><br>" + names + "<br><br>" +
                    tr("They're overwritten and deleted. They won't go to the Recycle Bin and can't be recovered."))
        go = box.addButton(tr("Shred"), QMessageBox.DestructiveRole)
        box.addButton(tr("Cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not go:
            return
        card = self.app.toast.show_busy(tr("Shredding…"), Path(paths[0]).name)
        result = {}

        def work():
            errs = []
            for x in paths:
                try:
                    shred_path(x)
                except Exception as e:
                    errs.append(f"{Path(x).name}: {e}")
            result["errs"] = errs

        def check():
            if not result:
                QTimer.singleShot(200, check)
                return
            if card in self.app.toast.cards:
                card.close_card()
            winsys.log(f"shredded {len(paths)} item(s); errors: {result['errs']}")
            if result["errs"]:
                self.app.toast.show_msg(tr("Some items couldn't be shredded"), "<br>".join(result["errs"][:4]), "err", 10000)
            else:
                self.app.toast.show_msg(tr("Shredded"), tr("{n} item(s) destroyed", n=len(paths)), "ok", 4000)
        threading.Thread(target=work, daemon=True).start()
        QTimer.singleShot(200, check)

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

        def work(st):
            done = []
            for x in paths:
                if st["stop"]:
                    break
                target = engine.unique_path(Path(d) / Path(x).name)
                shutil.move(x, target)
                done.append(target)
                st["n"] = len(done)
            return done
        self._background(tr("Move to").rstrip("…") + "…", Path(paths[0]).name if len(paths) == 1 else tr("{n} files", n=len(paths)),
                         work, lambda done: self.app.toast.show_result(tr("Moved"), done),
                         lambda st: tr("{a} of {b} done", a=st.get("n", 0), b=len(paths)) if len(paths) > 1 else None)

    def copy_to(self, paths, p):
        import shutil
        self._first = paths[0]
        d = self._pick_dir(tr("Copy to"))
        if not d:
            return

        def work(st):
            done = []
            for x in paths:
                if st["stop"]:
                    break
                target = engine.unique_path(Path(d) / Path(x).name)
                (shutil.copytree if Path(x).is_dir() else shutil.copy2)(x, target)
                done.append(target)
                st["n"] = len(done)
            return done
        self._background(tr("Copy to").rstrip("…") + "…", Path(paths[0]).name if len(paths) == 1 else tr("{n} files", n=len(paths)),
                         work, lambda done: self.app.toast.show_result(tr("Copied"), done),
                         lambda st: tr("{a} of {b} done", a=st.get("n", 0), b=len(paths)) if len(paths) > 1 else None)

    def terminal(self, paths, p):
        x = Path(paths[0])
        winsys.open_terminal(str(x if x.is_dir() else x.parent))

    def float(self, paths, p):
        for x in paths[:6]:
            if engine.ext_of(x) in NOTE_EXTS:            # a text file: an editable sticky note
                self.app.open_note(x)
                continue
            w = FloatWindow(x)
            self.app.floats.append(w)
            w.closed.connect(lambda w=w: self.app.floats.remove(w) if w in self.app.floats else None)
            w.show()
            w.come_forward()

    def reveal(self, paths, p):
        winsys.reveal(paths[0])

    def open_with(self, paths, p):
        winsys.open_with(paths[0])
