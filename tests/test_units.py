"""SI / US customary unit interchangeability checks.

The engine keeps every stored value in SI.  These tests cover the conversion
layer, generated narrative text, exports and the offscreen GUI toggle so a
regression at any boundary is visible.
"""

from __future__ import annotations

import csv
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from openpyxl import load_workbook
from PySide6.QtWidgets import QApplication

from bnbc_foundation.core.models import sample_project
from bnbc_foundation.core.report import export_csv, export_excel
from bnbc_foundation.core.selector import run_design
from bnbc_foundation.core.units import (
    SI,
    US,
    convert,
    convert_text,
    factor,
    label,
    normalize_system,
    system_of,
    to_si,
    unit_system_name,
)


QUANTITIES = (
    "length",
    "length_mm",
    "force",
    "moment",
    "moment_per_length",
    "pressure",
    "stress",
    "unit_weight",
    "subgrade",
    "area",
    "volume",
    "mass",
    "settlement",
    "angle",
    "ratio",
    "currency",
    "cost_per_volume",
    "cost_per_length",
    "cost_per_mass",
    "cost_per_area",
)


def test_every_quantity_round_trips_between_systems():
    for quantity in QUANTITIES:
        for value in (0.0, 1.0, 12.5, 1234.5):
            display = convert(value, quantity, US)
            assert to_si(display, quantity, US) == pytest.approx(value, rel=1e-12)
            assert convert(value, quantity, SI) == pytest.approx(value)
            assert to_si(value, quantity, SI) == pytest.approx(value)


def test_us_factors_and_labels_match_known_conversions():
    assert factor("length", US) == pytest.approx(3.280839895013123)
    assert factor("force", US) == pytest.approx(0.2248089430997105)
    assert factor("pressure", US) == pytest.approx(1.0 / 47.88025898033584)
    assert factor("stress", US) == pytest.approx(1.0 / 6.894757293168361)
    assert factor("settlement", US) * 25.4 == pytest.approx(1.0)
    assert convert(1.0, "unit_weight", US) == pytest.approx(6.365880385)
    assert convert(1.0, "volume", US) == pytest.approx(35.31466672148859)
    assert convert(1.0, "mass", US) == pytest.approx(2.204622621848776)
    assert factor("cost_per_volume", US) == pytest.approx(1.0 / 35.31466672148859)
    assert factor("cost_per_length", US) == pytest.approx(0.3048)
    assert factor("cost_per_mass", US) == pytest.approx(0.45359237)
    assert factor("cost_per_area", US) == pytest.approx(0.09290304)
    assert convert(12000.0, "cost_per_volume", US) == pytest.approx(339.8, rel=1e-3)

    assert label("length", SI) == "m"
    assert label("length", US) == "ft"
    assert label("length_mm", US) == "in"
    assert label("force", US) == "kip"
    assert label("moment", US) == "kip.ft"
    assert label("moment_per_length", US) == "kip.ft/ft"
    assert label("pressure", US) == "ksf"
    assert label("stress", US) == "ksi"
    assert label("settlement", US) == "in"
    assert label("cost_per_volume", US) == "per ft3"
    assert label("cost_per_length", US) == "per ft"
    assert label("cost_per_mass", US) == "per lb"
    assert label("cost_per_area", US) == "per ft2"
    assert unit_system_name(US) == "US customary"
    assert unit_system_name(SI) == "SI"


def test_normalize_system_accepts_common_labels():
    assert normalize_system("US") == US
    assert normalize_system("usc") == US
    assert normalize_system("Imperial") == US
    assert normalize_system("FPS") == US
    assert normalize_system("English") == US
    assert normalize_system("SI") == SI
    assert normalize_system("") == SI
    assert normalize_system(None) == SI


def test_project_system_reads_project_info():
    project = sample_project()
    assert system_of(project) == SI
    project.info.units = "US customary"
    assert system_of(project) == US


def test_convert_text_handles_compound_sizes_and_narratives():
    text = (
        "Support C1: service P=900 kN, Mx=30 kN.m, My=25 kN.m; "
        "q_allow=294.2 kPa"
    )
    expected = (
        "Support C1: service P=202.3 kip, Mx=22.1 kip.ft, My=18.4 kip.ft; "
        "q_allow=6.1 ksf"
    )
    assert convert_text(text, US) == expected
    assert convert_text(text, SI) == text

    size = "1.95 x 1.95 m, t=450 mm, depth=2.00 m"
    assert convert_text(size, US) == "6.4 ft x 6.4 ft, t=17.7 in, depth=6.6 ft"

    cap = "3 x diameter 1200 mm, L=20.0 m; cap 7.40 x 1.40 x 1200 mm"
    assert convert_text(cap, US) == (
        "3 x diameter 47.2 in, L=65.6 ft; cap 24.3 ft x 4.6 ft x 47.2 in"
    )

    reinforcement = (
        "Development length available 475 mm < required 1394 mm; "
        "Group settlement 31.0 mm > 25.0 mm"
    )
    assert convert_text(reinforcement, US) == (
        "Development length available 18.7 in < required 54.9 in; "
        "Group settlement 1.2 in > 1.0 in"
    )


def test_us_csv_headers_and_values_are_converted():
    project = sample_project()
    project.info.units = US
    run_design(project)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = export_csv(project, os.path.join(tmp, "schedule.csv"))
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))

    header = rows[0]
    assert "Thickness (in)" in header
    assert "Pile D (in)" in header
    assert "Pile L (ft)" in header
    assert "q max (ksf)" in header
    assert "q allow (ksf)" in header
    assert "Settlement (in)" in header
    assert "Thickness (mm)" not in header
    assert "q max (kPa)" not in header

    index = {name: i for i, name in enumerate(header)}
    wall = next(row for row in rows[1:] if row[0] == "W1")
    assert wall[index["Thickness (in)"]] == "47"
    assert wall[index["Pile D (in)"]] == "47"
    assert wall[index["Pile L (ft)"]] == "65.6"
    assert wall[index["q max (ksf)"]] == "25.2"
    assert wall[index["q allow (ksf)"]] == "30.3"
    assert wall[index["Settlement (in)"]] == "1.2"
    assert " kip" in wall[index["Requirement"]]
    assert " ft" in wall[index["Size"]]
    assert " in" in wall[index["Remarks"]]


def test_us_excel_workbook_uses_converted_headers_and_summary():
    project = sample_project()
    project.info.units = US
    run_design(project)
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = export_excel(project, os.path.join(tmp, "report.xlsx"))
        workbook = load_workbook(path, data_only=True)

    all_text = {
        str(cell.value)
        for sheet in workbook.worksheets
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    }
    assert "Units" in all_text
    assert "US customary" in all_text
    assert "Thickness (in)" in all_text
    assert "q max (ksf)" in all_text
    assert "Settlement (in)" in all_text
    assert "Concrete (ft3)" in all_text
    assert "Steel (lb)" in all_text
    assert "qc (ksi)" in all_text
    assert "CPT fs (ksf)" in all_text
    assert "Thickness (mm)" not in all_text
    assert "Concrete (m3)" not in all_text


def test_gui_units_toggle_reloads_inputs_without_changing_si_values():
    from bnbc_foundation.ui.main_window import MainWindow
    from bnbc_foundation.ui.pages.loads_page import SERVICE_P_COL, X_COL

    app = QApplication.instance() or QApplication([])
    window = MainWindow(sample_project())
    window.show()
    app.processEvents()

    try:
        assert window.project_page.units.currentText() == SI
        assert window.materials_page.f_y.suffix().strip() == "MPa"
        assert window.materials_page.f_y.value() == pytest.approx(420.0)

        window.project_page.units.setCurrentText(US)
        app.processEvents()

        assert window.project.info.units == US
        assert "US customary" in window.units_label.text()
        assert window.materials_page.f_y.suffix().strip() == "ksi"
        assert window.materials_page.f_y.value() == pytest.approx(
            convert(420.0, "stress", US), rel=1e-3
        )
        assert "in" in window.materials_page.bar_label.text()
        assert window.soil_page.table.horizontalHeaderItem(0).text() == "Bottom (ft)"
        assert window.soil_page.table.horizontalHeaderItem(5).text() == "c' (ksf)"
        assert window.loads_page.table.horizontalHeaderItem(X_COL).text() == "X (ft)"
        assert "kip" in window.loads_page.table.horizontalHeaderItem(SERVICE_P_COL).text()
        assert "kip.ft" in window.loads_page.table.horizontalHeaderItem(SERVICE_P_COL + 1).text()
        assert "ft" in window.options_page.raft_outline_label.text()
        assert "in" in window.options_page.pile_form.labelForField(
            window.options_page.pile_diameters
        ).text()
        assert window.options_page.cost_concrete.suffix().strip() == "per ft3"
        assert window.options_page.cost_steel.suffix().strip() == "per lb"
        assert window.options_page.cost_concrete.value() == pytest.approx(
            convert(12000.0, "cost_per_volume", US), rel=1e-3
        )

        row = next(
            row for row in range(window.loads_page.table.rowCount())
            if window.loads_page.table.item(row, 0).text() == "C1"
        )
        assert float(
            window.loads_page.table.item(row, SERVICE_P_COL).text()
        ) == pytest.approx(convert(900.0, "force", US), abs=0.1)

        # The page edit is read back in display units, then stored as SI.
        window.loads_page.apply_to_project(window.project)
        window.options_page.apply_to_project(window.project)
        column = next(e for e in window.project.elements if e.id == "C1")
        service = max(
            (r for r in column.reactions if not r.factored),
            key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My),
        )
        assert service.P == pytest.approx(900.0, rel=1e-4)
        assert window.project.options.cost_concrete == pytest.approx(12000.0, rel=1e-4)

        window.project_page.units.setCurrentText(SI)
        app.processEvents()
        assert window.project.info.units == SI
        assert window.materials_page.f_y.suffix().strip() == "MPa"
        assert window.materials_page.f_y.value() == pytest.approx(420.0)
        assert window.soil_page.table.horizontalHeaderItem(0).text() == "Bottom (m)"
        assert window.loads_page.table.horizontalHeaderItem(X_COL).text() == "X (m)"
        assert window.options_page.cost_concrete.value() == pytest.approx(12000.0, rel=1e-3)
    finally:
        window.close()

    # A project that opens directly in US must still scale spin-box ranges
    # correctly when the user switches back to SI.
    us_project = sample_project()
    us_project.info.units = US
    window = MainWindow(us_project)
    window.show()
    app.processEvents()
    try:
        assert window.materials_page.f_y.suffix().strip() == "ksi"
        assert window.materials_page.f_y.value() == pytest.approx(
            convert(420.0, "stress", US), rel=1e-3
        )
        window.project_page.units.setCurrentText(SI)
        app.processEvents()
        assert window.materials_page.f_y.suffix().strip() == "MPa"
        assert window.materials_page.f_y.value() == pytest.approx(420.0)
    finally:
        window.close()
