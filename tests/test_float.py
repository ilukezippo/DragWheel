import sys

import pytest
from PIL import Image


def test_picture_float_shape(dw, qapp, tmp_path):
    f = tmp_path / "p.png"
    Image.new("RGB", (400, 200), (10, 20, 30)).save(f)
    w = dw["FloatWindow"](str(f))
    w.show()
    qapp.processEvents()
    assert abs(w.width() / w.height() - 2) < 0.05
    w.set_keep_ratio(False)                      # any shape: resizing doesn't keep 2:1
    w._apply_size(300, 300)
    assert (w.width(), w.height()) == (300, 300)
    assert w.state().get("free") is True
    w.set_keep_ratio(True)
    assert abs(w.width() / w.height() - 2) < 0.05
    w.grab()                                     # paints without errors
    w.close()


def test_float_labels(dw, qapp, tmp_path):
    p = str(tmp_path / "app.exe")
    dw["set_float_label"](p, {"name": "My app", "color": "#ff0000", "size": None})
    assert dw["float_label"](p) == {"name": "My app", "color": "#ff0000"}
    dw["set_float_label"](p, {})
    assert dw["float_label"](p) == {}


def test_siblings_cached(dw, qapp, tmp_path):
    for n in ("a1.mp3", "a2.mp3", "a10.mp3", "x.txt"):
        (tmp_path / n).write_bytes(b"")
    w = dw["FloatWindow"].__new__(dw["FloatWindow"])
    w.link, w.path = None, str(tmp_path / "a2.mp3")
    names = [p.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] for p in w._siblings()]
    assert names == ["a1.mp3", "a2.mp3", "a10.mp3"]
    (tmp_path / "a3.mp3").write_bytes(b"")
    assert len(w._siblings()) == 3               # cached for a few seconds
    assert len(w._siblings(fresh=True)) == 4


@pytest.mark.skipif(sys.platform != "win32", reason="Qt's sound devices need Windows (Linux CI has none)")
def test_sound_follows_the_default_device(dw, qapp):
    from PySide6.QtMultimedia import QAudioOutput, QMediaDevices
    audio = QAudioOutput()
    watch = dw["_FollowDefaultOutput"](audio)
    watch._last = "something else"                # as if Windows switched to another device
    watch.check()
    assert watch._last == QMediaDevices.defaultAudioOutput().id()
    assert audio.device().id() == QMediaDevices.defaultAudioOutput().id()


def test_link_still_good_after_pause(dw):
    import time
    good = dw["_link_still_good"]
    later, soon = int(time.time()) + 4 * 3600, int(time.time()) + 300
    u = "https://rr1.googlevideo.com/videoplayback?expire={}&itag=137"
    assert good({"url": u.format(later), "audio": u.format(later), "page": "p"})
    assert not good({"url": u.format(later), "audio": u.format(soon), "page": "p"})   # sound link about to stop
    assert not good({"url": "https://x/no-expiry.m3u8", "page": "p"})
    assert not good({"url": u.format(later), "live": True, "page": "p"})
