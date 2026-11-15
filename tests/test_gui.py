"""Offscreen GUI smoke test."""

import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from bnbc_foundation.core.models import sample_project
from bnbc_foundation.ui.main_window import MainWindow


def _app():
    return QApplication.instance() or QApplication([])


def test_main_window_smoke(monkeypatch):
    for name in ("warning", "critical", "information", "question", "about"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Yes))
    app = _app()
    window = MainWindow(sample_project())
    window.show()
    app.processEvents()
    assert window.stack.count() == 7
    assert window.nav.count() == 7
    assert window.loads_page.table.rowCount() == 7
    assert window.soil_page.table.rowCount() == 5
    assert window._collect()
    assert window._validate()
    window.close()


def test_loads_page_geometry_roundtrip():
    app = _app()
    window = MainWindow(sample_project())
    window.show()
    app.processEvents()
    window.loads_page.apply_to_project(window.project)
    by_id = {e.id: e for e in window.project.elements}
    assert by_id["C1"].dx == 0.15
    assert by_id["C2"].is_circular
    assert by_id["C2"].diameter == 0.60
    assert by_id["C3"].rotation == 30.0
    assert by_id["C5"].is_circular
    assert by_id["W1"].has_wall_endpoints()
    assert by_id["W1"].wall_endpoints == (3.0, 2.8, 9.0, 4.2)
    assert window._validate()
    window.close()


def test_gui_design_run(monkeypatch):
    for name in ("warning", "critical", "information", "question", "about"):
        monkeypatch.setattr(QMessageBox, name, staticmethod(lambda *a, **k: QMessageBox.Yes))
    app = _app()
    window = MainWindow(sample_project())
    window.show()
    app.processEvents()
    window.run_design()
    for _ in range(150):
        app.processEvents()
        time.sleep(0.05)
        if window._thread is None:
            break
    assert window._thread is None
    assert window.project.results
    assert window.results_page.table.rowCount() >= 1
    assert window.nav.currentRow() == 5
    window.close()
