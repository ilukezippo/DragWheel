import subprocess


def test_video_flips(tmp_path):
    import engine
    import imageio_ffmpeg
    v = tmp_path / "v.mp4"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=size=160x120:rate=5", "-t", "1", "-pix_fmt", "yuv420p", str(v)], check=True)
    ops = {o.id: o for o in engine.tools([str(v)])}
    for op_id in ("fliph", "flipv"):
        out = ops[op_id].fn(str(v), {})
        assert out.exists() and out.stat().st_size > 1000


def test_catalog_is_cached():
    import engine
    assert engine.count_catalog() is engine.count_catalog()
