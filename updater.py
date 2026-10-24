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
    installer_sha256: str = ""


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
        installer_sha256=((asset.get("digest") or "").split("sha256:")[-1].lower()
                          if asset and (asset.get("digest") or "").startswith("sha256:") else ""),
    )


UPDATE_DIR = Path(tempfile.gettempdir()) / "DragWheel-update"     # %TEMP%\\DragWheel-update


def sha256_of(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def cached_installer(name: str, size: int = 0, sha256: str = "", folder: Path | None = None) -> Path | None:
    """An installer downloaded earlier (e.g. setup was cancelled) that is complete and unchanged."""
    target = (folder or UPDATE_DIR) / name
    try:
        if not target.is_file() or (size and target.stat().st_size != size):
            return None
        if sha256 and sha256_of(target) != sha256:
            return None
        return target
    except OSError:
        return None


def cleanup(current_version: str):
    """Delete downloaded installers once they are installed (version <= the running one), plus leftovers."""
    try:
        for f in UPDATE_DIR.iterdir():
            m = re.match(r"DragWheel-Setup-(.+?)\.exe(\.part)?$", f.name, re.I)
            if f.name.endswith(".part") or (m and not is_newer(m.group(1), current_version)):
                f.unlink(missing_ok=True)
    except OSError:
        pass


def download(url: str, name: str, progress=None, should_stop=lambda: False, parts: int = 8,
             size: int = 0, sha256: str = "", folder: Path | None = None) -> Path:
    """Download to %TEMP%\\DragWheel-update\\name. progress(done_bytes, total_bytes).

    An installer already downloaded and verified is reused instead of downloading it again.

    GitHub's file server limits the speed of each connection, so the file is fetched in
    `parts` pieces at the same time (HTTP Range requests). Falls back to one stream when the
    server doesn't support ranges.
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor

    cached = cached_installer(name, size, sha256, folder)
    if cached:
        if progress:
            progress(cached.stat().st_size, cached.stat().st_size)
        return cached
    folder = folder or UPDATE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    part = target.with_suffix(target.suffix + ".part")

    # Probe: follows the redirect to the real file URL and tells us the size + range support.
    with _get_file(url, rng=(0, 0)) as r:
        final_url = r.geturl()
        total = 0
        if r.status == 206:
            m = re.search(r"/(\d+)$", r.headers.get("Content-Range", ""))
            total = int(m.group(1)) if m else 0
        ranged = r.status == 206 and total > 4 * 1048576

    lock = threading.Lock()
    done = [0]
    stopped = threading.Event()

    def report(n):
        with lock:
            done[0] += n
            d = done[0]
        if progress:
            progress(d, total)

    def fetch(start, end):
        """Fetch bytes start..end (inclusive), or the whole file if start is None."""
        for attempt in range(3):
            got = 0
            try:
                rng = None if start is None else (start + got, end)
                with _get_file(final_url, rng=rng) as resp, open(part, "r+b") as fh:
                    if start is not None:
                        fh.seek(start)
                    while True:
                        if should_stop() or stopped.is_set():
                            stopped.set()
                            return
                        chunk = resp.read(256 * 1024)
                        if not chunk:
                            break
                        fh.write(chunk)
                        got += len(chunk)
                        report(len(chunk))
                if start is None or got == end - start + 1:
                    return
            except Exception:
                if attempt == 2:
                    raise
            report(-got)              # retry this piece from its start
        raise IOError("download incomplete")

    with open(part, "wb") as fh:
        if ranged:
            fh.truncate(total)
    try:
        if ranged:
            size = -(-total // parts)
            pieces = [(a, min(a + size, total) - 1) for a in range(0, total, size)]
            with ThreadPoolExecutor(len(pieces)) as ex:
                for f in [ex.submit(fetch, a, b) for a, b in pieces]:
                    f.result()
        else:
            fetch(None, None)
        if should_stop() or stopped.is_set():
            raise InterruptedError("download cancelled")
        if total and part.stat().st_size != total:
            raise IOError("download incomplete")
        if sha256 and sha256_of(part) != sha256:
            raise IOError("downloaded file is damaged (checksum mismatch), please try again")
    except BaseException:
        stopped.set()
        part.unlink(missing_ok=True)
        raise
    os.replace(part, target)
    return target


def _get_file(url: str, rng=None, timeout=30):
    headers = {"User-Agent": USER_AGENT, "Accept": "application/octet-stream"}
    if rng:
        headers["Range"] = f"bytes={rng[0]}-{rng[1]}"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout)
