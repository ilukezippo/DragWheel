import os

from PIL import Image


def _dialog(qapp, path):
    import editor
    d = editor.CropResizeDialog(str(path), "")
    d.show()
    qapp.processEvents()
    return d


def test_print_size_turns_with_the_picture(qapp, tmp_path):
    import engine
    f = tmp_path / "land.jpg"
    Image.new("RGB", (4000, 2500), (200, 100, 50)).save(f)
    d = _dialog(qapp, f)
    i = next(k for k in range(d.sizes.count()) if "4×6" in d.sizes.itemText(k))
    d.sizes.setCurrentIndex(i)
    p = d.params()
    assert p["size"] == (1800, 1200) and p["dpi"] == 300
    d._rotate(90)
    assert d.params()["size"] == (1200, 1800)
    out = engine.image_crop_resize(str(f), d.params())
    assert Image.open(out).size == (1200, 1800) and Image.open(out).info["dpi"] == (300, 300)


def test_original_takes_the_whole_picture(qapp, tmp_path):
    from PySide6.QtCore import QRectF
    f = tmp_path / "a.jpg"
    Image.new("RGB", (800, 500)).save(f)
    d = _dialog(qapp, f)
    d.canvas.set_crop(QRectF(50, 50, 200, 200))
    d.aspect_group.button(1).click()                # Original
    assert [round(x) for x in d.params()["box"]] == [0, 0, 800, 500]


def test_overwrite_replaces_the_original(qapp, tmp_path):
    import engine
    f = tmp_path / "photo.jpg"
    Image.new("RGB", (800, 500)).save(f)
    d = _dialog(qapp, f)
    d._percent(50)
    d._save_over()
    out = engine.image_crop_resize(str(f), d.params())
    assert str(out) == str(f) and Image.open(out).size == (400, 250)
    assert sorted(os.listdir(tmp_path)) == ["photo.jpg"]
