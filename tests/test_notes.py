def test_note_saves_and_reloads(dw, qapp, tmp_path, monkeypatch):
    monkeypatch.setitem(dw, "notes_folder", lambda: tmp_path)
    p = tmp_path / "n.txt"
    p.write_bytes(b"")
    note = dw["StickyNote"](str(p), {"x": 10, "y": 10, "w": 200, "h": 180, "color": "Blue"})
    note.edit.setPlainText("hello\nworld")
    note._write()
    assert p.read_bytes() == b"hello\r\nworld"
    st = note.state()
    assert st["color"] == "Blue" and st["path"] == str(p)
    p.write_bytes(b"changed")
    note._outside_change(str(p))
    assert note.edit.toPlainText() == "changed"
    note.close_by_user()
    qapp.processEvents()


def test_note_keeps_encoding(dw, qapp, tmp_path):
    p = tmp_path / "bom.txt"
    p.write_bytes(b"\xef\xbb\xbfcaf\xc3\xa9\n")
    note = dw["StickyNote"](str(p), {})
    assert note.edit.toPlainText() == "café\n"
    note.edit.setPlainText("café!\n")
    note._write()
    assert p.read_bytes() == b"\xef\xbb\xbfcaf\xc3\xa9!\n"
    note.close()
