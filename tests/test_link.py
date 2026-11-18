import json
import subprocess
import types

import engine


def _fake(info, rc=0):
    def run(cmd, **kw):
        assert engine._YT_FAST in cmd and engine._YT_CLIENTS not in cmd
        return types.SimpleNamespace(returncode=rc, stdout=json.dumps(info).encode(), stderr=b"")
    return run


def _fmt(h, v=True, a=False):
    return {"url": f"https://x/{h}{v}{a}", "protocol": "https", "height": h if v else None,
            "vcodec": "avc1" if v else "none", "acodec": "mp4a" if a else "none",
            "ext": "mp4" if v else "m4a"}


def test_quick_player_used_when_quality_is_there(monkeypatch):
    info = {"formats": [_fmt(1080), _fmt(720), _fmt(0, v=False, a=True)]}
    monkeypatch.setattr(subprocess, "run", _fake(info))
    got, _, rc = engine._fast_youtube(["yt", "--extractor-args", engine._YT_CLIENTS], "u", 1080)
    assert rc == 0 and got == info


def test_quick_player_skipped_for_live_and_low_quality(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _fake({"is_live": True, "formats": [_fmt(1080, a=True)]}))
    assert engine._fast_youtube(["yt"], "u", 1080)[2] == 1
    monkeypatch.setattr(subprocess, "run", _fake({"formats": [_fmt(360), _fmt(0, v=False, a=True)],
                                                  "_note": "only low"}))
    assert engine._fast_youtube(["yt"], "u", 1080)[2] == 0     # 360 is the best the video has
    monkeypatch.setattr(subprocess, "run", _fake({}, rc=1))
    assert engine._fast_youtube(["yt"], "u", 1080)[2] == 1
