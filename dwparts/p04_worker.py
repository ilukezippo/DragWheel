"""DragWheel: Background worker

Run by dragwheel.pyw in its own namespace (see dwparts/__init__.py).
"""
# ruff: noqa: F821, F405, F403
from __future__ import annotations


# ============================================================================
# Background worker
# ============================================================================
CANCELLED = "__cancelled__"


class WorkerSignals(QObject):
    done = Signal(object, object, object)   # worker, outputs, error
    progress = Signal(object, float)         # worker, 0..1
    count = Signal(object, int, int)         # worker, files done, files in the batch


class Worker(QRunnable):
    def __init__(self, op, paths, params):
        super().__init__()
        self.op, self.paths, self.params = op, paths, params
        self.sig = WorkerSignals()
        self.cancel_requested = False
        self.card = None
        self.failed = []
        self.count = (0, len(paths))

    def cancel(self):
        self.cancel_requested = True

    def run(self):
        """The job runs in its own process (jobproc) so Cancel can stop it instantly."""
        try:
            import jobproc
            job = jobproc.JobProcess(self.op.group, self.op.id, self.paths, self.params,
                                     getattr(self, "output_dir", None) or engine.OUTPUT_DIR,
                                     on_progress=lambda f: self.sig.progress.emit(self, f),
                                     on_count=lambda a, b: self.sig.count.emit(self, a, b))
            kind, val = job.run(lambda: self.cancel_requested)
            self.failed = list(job.failed)
            if kind == "done":
                result = ([Path(v) for v in val], None)
            elif kind == "cancelled":
                result = (None, CANCELLED)
            else:
                result = (None, str(val))
        except Exception as e:
            traceback.print_exc()
            result = (None, str(e) or e.__class__.__name__)
        try:
            self.sig.done.emit(self, *result)
        except RuntimeError:            # DragWheel is closing and the signal's owner is gone
            return


# ============================================================================
# Update check / download (background)
# ============================================================================
class UpdateSignals(QObject):
    checked = Signal(object, object, bool)     # release | None, error | None, manual
    progress = Signal(int, int)
    downloaded = Signal(object, object)        # path | None, error | None


class UpdateCheck(QRunnable):
    def __init__(self, manual):
        super().__init__()
        self.manual = manual
        self.sig = UpdateSignals()

    def run(self):
        try:
            self.sig.checked.emit(updater.latest_release(), None, self.manual)
        except Exception as e:
            self.sig.checked.emit(None, str(e), self.manual)


class UpdateDownload(QRunnable):
    def __init__(self, release):
        super().__init__()
        self.release = release
        self.stop = False
        self.sig = UpdateSignals()

    def run(self):
        try:
            path = updater.download(self.release.installer_url, self.release.installer_name,
                                    progress=lambda d, t: self.sig.progress.emit(d, t),
                                    should_stop=lambda: self.stop,
                                    size=self.release.installer_size, sha256=self.release.installer_sha256)
            self.sig.downloaded.emit(path, None)
        except InterruptedError:
            self.sig.downloaded.emit(None, CANCELLED)
        except Exception as e:
            self.sig.downloaded.emit(None, str(e))


_APP = None          # the running DragWheelApp (floats use it for "Play copied link")


class LinkSignals(QObject):
    done = Signal(object, object)          # info dict | None, error | None


class LinkResolve(QRunnable):
    def __init__(self, url, quality=None):
        super().__init__()
        self.url = url
        self.quality = quality or settings().value("link_quality", "1080p")
        self.sig = LinkSignals()

    def run(self):
        try:
            self.sig.done.emit(engine.resolve_link(self.url, self.quality), None)
        except Exception as e:
            self.sig.done.emit(None, str(e))


class ModelDownload(QRunnable):
    """Downloads an AI model once into %LOCALAPPDATA%\\DragWheel\\models (checksum-verified)."""
    def __init__(self, name):
        super().__init__()
        self.name = name
        self.stop = False
        self.sig = UpdateSignals()

    def run(self):
        m = engine.MODELS[self.name]
        try:
            path = updater.download(m["url"], m["file"], progress=lambda d, t: self.sig.progress.emit(d, t),
                                    should_stop=lambda: self.stop, size=m["size"], sha256=m["sha256"],
                                    folder=engine.models_dir())
            engine.mark_model_ready(self.name)
            self.sig.downloaded.emit(path, None)
        except InterruptedError:
            self.sig.downloaded.emit(None, CANCELLED)
        except Exception as e:
            self.sig.downloaded.emit(None, str(e))
