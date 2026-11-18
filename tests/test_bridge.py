import io
import json
import struct


def test_native_messages(dw, tmp_path, monkeypatch):
    import bridge
    sent = []
    bridge._SEND, bridge._VERSION = (lambda m: sent.append(m) or True), "9.9"
    assert bridge.handle({"type": "ping"}) == {"ok": True, "version": "9.9"}
    assert bridge.handle({"type": "float", "url": "https://example.com/v"})["ok"]
    assert sent[-1] == {"paths": ["https://example.com/v"], "flags": ["--play-url"]}
    assert not bridge.handle({"type": "float", "url": "file:///c:/x"})["ok"]
    msg = json.dumps({"type": "ping"}).encode()
    assert bridge._read(io.BytesIO(struct.pack("<I", len(msg)) + msg)) == {"type": "ping"}
    assert bridge.is_host_launch(["chrome-extension://abc/"])
    assert bridge.is_host_launch(["C:/x/host.json", bridge.FIREFOX_ID])
    assert not bridge.is_host_launch(["photo.png"])
