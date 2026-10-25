"""DragWheel from the command line, for scripts.

    dragwheel convert photo.heic --to jpg [--out D:\\Pictures]
    dragwheel tool compress video.mp4 [--set "Quality=Smaller file"]
    dragwheel list photo.heic

The installed `dragwheel` command (dragwheel.cmd) runs DragWheel.exe and waits for it; DragWheel.exe writes to the
console it was started from. Exit code 0 = everything worked, 1 = some files failed, 2 = wrong command.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

USAGE = """DragWheel command line

  dragwheel convert <files…> --to <format> [--out <folder>]
  dragwheel tool <tool> <files…> [--out <folder>] [--set "Name=value"]…
  dragwheel list <file>             what a file can be converted to, and its tools

Examples
  dragwheel convert IMG_0001.heic IMG_0002.heic --to jpg
  dragwheel convert *.png --to webp --out D:\\web
  dragwheel tool compress clip.mp4
"""


def _attach_console():
    """DragWheel.exe is a window app: borrow the console of whoever started it, so print() shows up."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.AttachConsole(-1):          # ATTACH_PARENT_PROCESS
            sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace", buffering=1)
            sys.stderr = sys.stdout
    except Exception:
        pass


def _expand(args):
    """Windows' cmd doesn't expand *.png itself."""
    import glob
    out = []
    for a in args:
        hits = glob.glob(a) if any(c in a for c in "*?[") else []
        out.extend(sorted(hits) or [a])
    return out


def _parse(argv):
    files, opts, sets = [], {}, {}
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--to", "--out", "--set") and i + 1 < len(argv):
            if a == "--set":
                k, _, v = argv[i + 1].partition("=")
                sets[k.strip()] = v.strip()
            else:
                opts[a[2:]] = argv[i + 1]
            i += 2
            continue
        files.append(a)
        i += 1
    return _expand(files), opts, sets


def _progress(frac):
    bar = int(frac * 30)
    sys.stdout.write(f"\r  [{'#' * bar}{'.' * (30 - bar)}] {int(frac * 100):3d}%")
    sys.stdout.flush()


def _run(engine, op, files, sets, out):
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        engine.OUTPUT_DIR = str(Path(out).resolve())
    params = {k: (v[0] if isinstance(v, (list, tuple)) and v else v) for k, v in (op.ask or [])}
    params.update(sets)
    if op.ui or op.group == "action":
        print(f"'{op.label}' needs a window; use it from the wheel instead.")
        return 2
    if op.model and not engine.model_ready(op.model):
        print(f"'{op.label}' needs a one-time download. Use it once from the wheel first.")
        return 2
    failed = 0
    for f in files:
        print(f"{Path(f).name} → {op.label}")
        token = engine.CancelToken()
        token.on_path = lambda kind, val: _progress(float(val)) if kind == "progress" else None
        try:
            outs = engine.run_op(op, [f], params, token=token)
            sys.stdout.write("\r" + " " * 46 + "\r")
            for o in outs:
                if o and not str(o).startswith("info:"):
                    print(f"  saved {o}")
                elif o:
                    print(f"  {str(o)[5:]}")
        except Exception as e:
            sys.stdout.write("\r" + " " * 46 + "\r")
            print(f"  failed: {e}")
            failed += 1
    return 1 if failed else 0


def main(argv) -> int:
    _attach_console()
    print()
    if not argv or argv[0] in ("help", "-h", "--help", "/?"):
        print(USAGE)
        return 0 if argv else 2
    import engine
    cmd, rest = argv[0].lower(), argv[1:]
    if cmd == "list":
        files, _o, _s = _parse(rest)
        if not files or not os.path.exists(files[0]):
            print("Give a file that exists, e.g.  dragwheel list photo.heic")
            return 2
        conv = engine.conversions(files[:1])
        tools = engine.tools(files[:1])
        print(f"{Path(files[0]).name}")
        print("  convert --to " + ", ".join(o.id[3:] if o.id.startswith("to_") else o.id for o in conv))
        print("  tools:")
        for o in tools:
            if o.ui:
                continue
            extra = ("   options: " + ", ".join(f"{k}={v}" for k, v in o.ask)) if o.ask else ""
            print(f"    {o.id:<14} {o.label}{extra}")
        return 0
    if cmd == "convert":
        files, opts, sets = _parse(rest)
        fmt = (opts.get("to") or "").lower().lstrip(".")
        if not files or not fmt:
            print(USAGE)
            return 2
        bad = [f for f in files if not os.path.exists(f)]
        if bad:
            print("Not found: " + ", ".join(bad))
            return 2
        op = next((o for o in engine.conversions(files[:1]) if o.id in (f"to_{fmt}", fmt)), None)
        if op is None:
            print(f"{Path(files[0]).name} can't be converted to {fmt}. Try:  dragwheel list \"{files[0]}\"")
            return 2
        return _run(engine, op, files, sets, opts.get("out"))
    if cmd == "tool":
        if not rest:
            print(USAGE)
            return 2
        name, files_args = rest[0].lower(), rest[1:]
        files, opts, sets = _parse(files_args)
        if not files:
            print(USAGE)
            return 2
        op = next((o for o in engine.tools(files[:1]) if o.id.lower() == name or o.label.lower().rstrip("…") == name), None)
        if op is None:
            print(f"No tool '{name}' for {Path(files[0]).name}. Try:  dragwheel list \"{files[0]}\"")
            return 2
        return _run(engine, op, files, sets, opts.get("out"))
    print(USAGE)
    return 2
