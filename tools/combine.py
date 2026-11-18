"""Print dragwheel.pyw with its parts (dwparts/) put back in place, as one file, for linters.

    python tools/combine.py > combined_dragwheel.py
"""
import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
main = (root / "dragwheel.pyw").read_text(encoding="utf-8")
parts = re.search(r"PARTS = \[(.*?)\]", main, re.S).group(1)
names = re.findall(r'"(p\d\d_\w+)"', parts)
out = []
for line in main.split("\n"):
    if line.strip() == "load_parts(globals())":
        for n in names:
            src = (root / "dwparts" / f"{n}.py").read_text(encoding="utf-8")
            src = "\n".join(x for x in src.split("\n") if x.strip() not in (
                "from __future__ import annotations", "# ruff: noqa: F821, F405, F403"))
            out.append(f"# ---- dwparts/{n}.py\n{src}")
        continue
    out.append(line)
sys.stdout.write("\n".join(out))
