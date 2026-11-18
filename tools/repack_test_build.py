"""Make a new DragWheel.exe from the 1.2.3 test build: same bootloader and libraries, our modules compiled afresh
from the source folder (Python 3.12.7, the build's own Python). Run with the 3.12.7 venv that has PyInstaller.

usage: repack.py <old DragWheel.exe> <source dir> <new DragWheel.exe>
"""
import marshal, os, struct, sys, zlib, importlib.util
from PyInstaller.archive.readers import CArchiveReader
from PyInstaller.archive.writers import CArchiveWriter

old_exe, src_dir, new_exe = sys.argv[1:4]
assert sys.version_info[:3] == (3, 12, 7), sys.version

OURS_TOP = ["bridge", "cli", "editor", "engine", "i18n", "jobproc", "pdfdocx", "theme", "updater", "winsys"]


def compile_mod(path, co_filename):
    src = open(path, encoding="utf-8").read()
    return compile(src, co_filename, "exec", dont_inherit=True, optimize=0)


ca = CArchiveReader(old_exe)
raw = open(old_exe, "rb").read()
start = ca._start_offset

# ---- new PYZ: old entries kept byte for byte, ours replaced
pyz_off, pyz_len, _, _, _ = ca.toc["PYZ.pyz"]
pyz = raw[start + pyz_off:start + pyz_off + pyz_len]
assert pyz[:4] == b"PYZ\0"
pymagic = pyz[4:8]
toc_offset = struct.unpack("!i", pyz[8:12])[0]
old_toc = marshal.loads(pyz[toc_offset:])
assert pymagic == importlib.util.MAGIC_NUMBER, "python magic differs"

replace = {}
for m in OURS_TOP:
    replace[m] = (compile_mod(os.path.join(src_dir, m + ".py"), m + ".py"), 0)
for f in sorted(os.listdir(os.path.join(src_dir, "dwparts"))):
    if f.endswith(".py"):
        n = f[:-3]
        name = "dwparts" if n == "__init__" else f"dwparts.{n}"
        cofn = os.path.join("dwparts", f).replace("/", "\\")
        replace[name] = (compile_mod(os.path.join(src_dir, "dwparts", f), cofn), 1 if n == "__init__" else 0)
for f in sorted(os.listdir(os.path.join(src_dir, "locales"))):
    if f.endswith(".py"):
        n = f[:-3]
        name = "locales" if n == "__init__" else f"locales.{n}"
        cofn = os.path.join("locales", f).replace("/", "\\")
        replace[name] = (compile_mod(os.path.join(src_dir, "locales", f), cofn), 1 if n == "__init__" else 0)

out = bytearray(b"\0" * 17)
new_toc = []
names_old = {n for n, _ in old_toc}
for name, (typecode, off, length) in old_toc:
    if name in replace:
        data = zlib.compress(marshal.dumps(replace[name][0]), 6)
        new_toc.append((name, (typecode, len(out), len(data))))
        out += data
    else:
        new_toc.append((name, (typecode, len(out), length)))
        out += pyz[off:off + length]
for name, (code, is_pkg) in replace.items():          # modules the old build didn't have
    if name not in names_old:
        data = zlib.compress(marshal.dumps(code), 6)
        new_toc.append((name, (1 if is_pkg else 0, len(out), len(data))))
        out += data
        print("added module", name)
toc_at = len(out)
out += marshal.dumps(new_toc)
out[0:12] = b"PYZ\0" + pymagic + struct.pack("!i", toc_at)
new_pyz = bytes(out)

# ---- new CArchive: same entries, new PYZ and new entry script
# the TOC as stored, in order, with the option entries (pyi-contents-directory _internal…) the reader keeps apart
cookie_at0 = CArchiveReader._find_magic_pattern(open(old_exe, "rb"), CArchiveWriter._COOKIE_MAGIC_PATTERN)
_m, _al, _toff, _tlen, _pv, _pl = struct.unpack(CArchiveWriter._COOKIE_FORMAT,
                                                 raw[cookie_at0:cookie_at0 + CArchiveWriter._COOKIE_LENGTH])
tocraw = raw[start + _toff:start + _toff + _tlen]
raw_toc, pos = [], 0
while pos < len(tocraw):
    el, off, clen, ulen, cflag, tc = struct.unpack("!IIIIBc", tocraw[pos:pos + 18])
    raw_toc.append((tocraw[pos + 18:pos + el].rstrip(b"\0").decode("utf-8"), (off, clen, ulen, cflag, tc.decode())))
    pos += el
assert any(t == "o" for _, (*_x, t) in raw_toc), "no option entries found"
entries = []
for name, (off, clen, ulen, cflag, typecode) in raw_toc:
    blob = raw[start + off:start + off + clen]
    if name == "PYZ.pyz":
        blob, ulen, cflag = new_pyz, len(new_pyz), 0
    elif name == "dragwheel":
        code = compile_mod(os.path.join(src_dir, "dragwheel.pyw"), "dragwheel.py")
        data = marshal.dumps(code)
        ulen = len(data)
        blob, cflag = zlib.compress(data, 6), 1
    entries.append((name, blob, ulen, cflag, typecode))

arch = bytearray()
toc = []
for name, blob, ulen, cflag, typecode in entries:
    toc.append((len(arch), len(blob), ulen, cflag, typecode, name))
    arch += blob
toc_offset = len(arch)
toc_data = CArchiveWriter._serialize_toc(toc)
arch += toc_data
# cookie: same python version / library name as before
cookie_at = CArchiveReader._find_magic_pattern(open(old_exe, "rb"), CArchiveWriter._COOKIE_MAGIC_PATTERN)
magic, alen, toff, tlen, pyvers, pylib = struct.unpack(CArchiveWriter._COOKIE_FORMAT,
                                                       raw[cookie_at:cookie_at + CArchiveWriter._COOKIE_LENGTH])
archive_length = toc_offset + len(toc_data) + CArchiveWriter._COOKIE_LENGTH
arch += struct.pack(CArchiveWriter._COOKIE_FORMAT, magic, archive_length, toc_offset, len(toc_data), pyvers, pylib)
tail = raw[cookie_at + CArchiveWriter._COOKIE_LENGTH:]
assert not tail, f"{len(tail)} bytes after the cookie (signature?)"
open(new_exe, "wb").write(raw[:start] + bytes(arch))
print("ok", new_exe, len(raw[:start]) + len(arch), "modules replaced:", len(replace))
