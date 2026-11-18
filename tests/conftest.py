"""Loads dragwheel.pyw (and its parts) once, without starting the app, for the tests. Qt runs offscreen."""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_DW = {}
_KEEP = []


@pytest.fixture(scope="session")
def dw():
    if not _DW:
        from PySide6.QtCore import QCoreApplication, QSettings
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        _KEEP.append(app)
        QCoreApplication.setOrganizationName("DragWheelTests")
        ns = {"__name__": "dragwheel_test", "__file__": str(ROOT / "dragwheel.pyw")}
        code = compile((ROOT / "dragwheel.pyw").read_text(encoding="utf-8"), str(ROOT / "dragwheel.pyw"), "exec")
        exec(code, ns)
        ns["settings"] = lambda: QSettings("DragWheelTests", "DragWheelTests")
        _DW.update(ns)
    return _DW


@pytest.fixture()
def qapp(dw):
    from PySide6.QtWidgets import QApplication
    return QApplication.instance()
