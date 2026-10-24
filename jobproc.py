"""Runs one conversion/tool in a separate process so Cancel can stop it instantly.

Parent side:  JobProcess(group, op_id, paths, params).run(should_cancel) -> ("done", [paths]) |
              ("error", message) | ("cancelled", None)
Child side:   child_main() — rebuilds the operation from its id and runs it with the engine.

Every output file and temp folder the child creates is reported to the parent as it is
allocated, so a killed job leaves nothing behind.
"""
from __future__ import annotations

import multiprocessing as mp
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


# ----------------------------------------------------------------------------- child
def child_main(group, op_id, paths, params, output_dir, q, cancel_evt):
    if sys.platform == "win32":
        try:   # below normal priority (inherited by ffmpeg & co.) so floats keep playing smoothly
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = ctypes.c_void_p
            k32.SetPriorityClass(ctypes.c_void_p(k32.GetCurrentProcess()), 0x00004000)
        except Exception:
            pass
    try:
        import engine
        engine.OUTPUT_DIR = output_dir
        token = engine.CancelToken()
        token.on_path = lambda kind, p: q.put((kind, p))

        def watch():
            cancel_evt.wait()
            token.cancel()
        threading.Thread(target=watch, daemon=True).start()

        ops = engine.conversions(paths) if group == "convert" else engine.tools(paths)
        op = next((o for o in ops if o.id == op_id), None)
        if op is None:
            q.put(("error", f"Unknown operation: {op_id}"))
            return
        outs = engine.run_op(op, paths, params, token=token)
        q.put(("done", [str(o) for o in outs if o]))
    except BaseException as e:            # noqa: BLE001 — report everything to the parent
        try:
            import engine
            if isinstance(e, engine.Cancelled):
                q.put(("cancelled", None))
                return
        except Exception:
            pass
        q.put(("error", str(e) or e.__class__.__name__))


# ----------------------------------------------------------------------------- parent
def kill_tree(pid: int):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, creationflags=NO_WINDOW)
        return
    try:
        import psutil
        parent = psutil.Process(pid)
        for c in parent.children(recursive=True):
            c.kill()
        parent.kill()
    except Exception:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def _remove(path: str):
    p = Path(path)
    for cand in (p, p.with_name(p.name + ".part")):
        try:
            if cand.is_dir():
                shutil.rmtree(cand, ignore_errors=True)
            elif cand.exists():
                cand.unlink()
        except Exception:
            pass


class JobProcess:
    def __init__(self, group, op_id, paths, params, output_dir, on_progress=None):
        self.args = (group, op_id, list(paths), dict(params or {}), output_dir)
        self.on_progress = on_progress
        self.outputs: list[str] = []     # planned output paths
        self.temps: list[str] = []

    def run(self, should_cancel) -> tuple[str, object]:
        ctx = mp.get_context("spawn")
        q = ctx.Queue()
        cancel_evt = ctx.Event()
        proc = ctx.Process(target=child_main, args=(*self.args, q, cancel_evt), daemon=True)
        proc.start()
        result = None
        cancel_at = None
        try:
            while result is None:
                if should_cancel() and cancel_at is None:
                    cancel_evt.set()                      # polite: lets the child stop ffmpeg itself…
                    cancel_at = time.monotonic()
                if cancel_at is not None and time.monotonic() - cancel_at > 0.7:
                    kill_tree(proc.pid)                   # …and if it doesn't within 0.7 s, kill it
                    result = ("cancelled", None)
                    break
                try:
                    kind, val = q.get(timeout=0.15)
                except queue.Empty:
                    if not proc.is_alive():
                        # drain anything left in the queue, then decide
                        try:
                            while True:
                                kind, val = q.get_nowait()
                                self._note(kind, val)
                                if kind in ("done", "error", "cancelled"):
                                    result = (kind, val)
                                    break
                        except queue.Empty:
                            pass
                        if result is None:
                            result = ("cancelled", None) if cancel_at else \
                                ("error", f"The worker stopped unexpectedly (code {proc.exitcode})")
                    continue
                self._note(kind, val)
                if kind in ("done", "error", "cancelled"):
                    result = (kind, val)
        finally:
            if proc.is_alive():
                proc.join(timeout=2)
            if proc.is_alive():
                kill_tree(proc.pid)
            for t in self.temps:                        # temp folders never outlive the job
                shutil.rmtree(t, ignore_errors=True)
        if result[0] == "cancelled" or (result[0] == "done" and should_cancel()):
            for p in reversed(self.outputs):
                _remove(p)
            return ("cancelled", None)
        if result[0] == "error":
            for p in reversed(self.outputs):            # failed jobs don't leave half files either
                pp = Path(p)
                if pp.with_name(pp.name + ".part").exists():
                    _remove(p)
        return result

    def _note(self, kind, val):
        if kind == "progress":
            if self.on_progress:
                try:
                    self.on_progress(float(val))
                except Exception:
                    pass
        elif kind == "out":
            self.outputs.append(val)
        elif kind == "tmp":
            self.temps.append(val)
