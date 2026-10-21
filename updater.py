"""Update check against the GitHub releases of ilukezippo/DragWheel.

The only network access DragWheel does: one small request to the GitHub API
(and, if you choose to, downloading the new installer). Can be turned off in Settings.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

REPO = "ilukezippo/DragWheel"
REPO_URL = f"https://github.com/{REPO}"
RELEASES_URL = f"{REPO_URL}/releases/latest"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
USER_AGENT = "DragWheel-updater"


@dataclass
class Release:
    version: str
    tag: str
    page: str
    notes: str
    installer_url: str | None
    installer_name: str | None
    installer_size: int


def parse_version(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(remote: str, local: str) -> bool:
    a, b = parse_version(remote), parse_version(local)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def _get(url: str, timeout=15):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def latest_release() -> Release:
    with _get(API_LATEST) as r:
        data = json.loads(r.read().decode("utf-8"))
    tag = data.get("tag_name") or ""
    asset = next((a for a in data.get("assets", [])
                  if re.match(r"DragWheel-Setup-.*\.exe$", a.get("name", ""), re.I)), None)
    return Release(
        version=tag.lstrip("vV"),
        tag=tag,
        page=data.get("html_url") or RELEASES_URL,
        notes=(data.get("body") or "").strip(),
        installer_url=asset.get("browser_download_url") if asset else None,
        installer_name=asset.get("name") if asset else None,
        installer_size=int(asset.get("size") or 0) if asset else 0,
    )


def download(url: str, name: str, progress=None, should_stop=lambda: False) -> Path:
    """Download to %TEMP%\\DragWheel-update\\name. progress(done_bytes, total_bytes)."""
    folder = Path(tempfile.gettempdir()) / "DragWheel-update"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    part = target.with_suffix(target.suffix + ".part")
    with _get(url, timeout=30) as r:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(part, "wb") as fh:
            while True:
                if should_stop():
                    fh.close()
                    part.unlink(missing_ok=True)
                    raise InterruptedError("download cancelled")
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                fh.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    if total and part.stat().st_size != total:
        part.unlink(missing_ok=True)
        raise IOError("download incomplete")
    os.replace(part, target)
    return target
