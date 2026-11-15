"""JSON, Excel, CSV, PDF and import-template checks."""

import csv
import json
import math
from pathlib import Path

import pytest
from openpyxl import load_workbook

from bnbc_foundation.core.models import sample_project
from bnbc_foundation.core.report import (
    ELEMENT_HEADERS,
    SOIL_HEADERS,
    all_warning_lines,
    export_csv,
    export_excel,
    export_import_template,
    export_pdf,
    import_elements_csv,
    import_elements_excel,
    import_soil_excel,
    load_project,
    save_project,
    selected_results,
)
from bnbc_foundation.core.selector import run_design


def designed_project():
    project = sample_project()
    run_design(project)
    return project


def test_json_roundtrip(tmp_path):
    project = designed_project()
    path = save_project(project, tmp_path / "project.json")
    loaded = load_project(path)
    assert loaded.info.name == project.info.name
    assert len(loaded.elements) == len(project.elements)
    assert len(loaded.boreholes) == len(project.boreholes)
    assert len(loaded.boreholes[0].layers) == len(project.boreholes[0].layers)
    assert len(loaded.results) == len(project.results)
    assert loaded.warnings == project.warnings
    by_id = {e.id: e for e in loaded.elements}
    assert by_id["C1"].dx == pytest.approx(0.15)
    assert by_id["C2"].is_circular
    assert by_id["C2"].diameter == pytest.approx(0.60)
    assert by_id["C5"].is_circular
    wall = by_id["W1"]
    assert wall.has_wall_endpoints()
    assert wall.x1 == pytest.approx(3.0)
    assert wall.y2 == pytest.approx(4.2)
    assert wall.wall_angle_deg == pytest.approx(math.degrees(math.atan2(1.4, 6.0)))
    # NumPy raft grids must be serialised as plain lists.
    raw = json.loads(Path(path).read_text())
    assert isinstance(raw, dict)
    assert raw["results"][0]["details"]


def test_excel_schedule(tmp_path):
    project = designed_project()
    path = export_excel(project, tmp_path / "report.xlsx")
    wb = load_workbook(path)
    required = {
        "Summary", "Foundation Schedule", "Geotech Checks", "Structural Checks",
        "Supplemental Checks", "Rebar Schedule", "Bar Bending Schedule",
        "Quantities", "Soil Inputs", "Code Basis",
    }
    assert required <= set(wb.sheetnames)
    ws = wb["Foundation Schedule"]
    assert ws.max_row >= 2
    header_rows = [
        [c.value for c in row]
        for row in ws.iter_rows(min_row=1, max_row=8)
    ]
    assert any("Foundation type" in [v for v in row if v] for row in header_rows)
    assert any("Qty" in [v for v in row if v] for row in header_rows)
    supplemental = [
        cell.value
        for row in wb["Supplemental Checks"].iter_rows()
        for cell in row
        if cell.value not in (None, "")
    ]
    assert "Crack width (mm)" in supplemental
    assert "P-M util." in supplemental
    assert any(value in ("0.186", "0.166") for value in supplemental)


def test_warning_lines_include_project_and_element_remarks(tmp_path):
    project = designed_project()
    warnings = all_warning_lines(project)
    assert any("Raft alternative requires review" in warning for warning in warnings)
    assert any("Differential settlement" in warning for warning in warnings)
    assert any("liquefaction FS" in warning for warning in warnings)
    assert any("Development length" in warning for warning in warnings)

    path = export_excel(project, tmp_path / "report.xlsx")
    wb = load_workbook(path, data_only=True)
    summary_values = [
        str(cell.value)
        for row in wb["Summary"].iter_rows()
        for cell in row
        if cell.value not in (None, "")
    ]
    assert any("Raft alternative requires review" in value for value in summary_values)
    assert any("Differential settlement" in value for value in summary_values)
    assert any("liquefaction FS" in value for value in summary_values)
    assert any("Development length" in value for value in summary_values)

    geotech_values = [
        str(cell.value)
        for row in wb["Geotech Checks"].iter_rows()
        for cell in row
        if cell.value not in (None, "")
    ]
    assert any("SPT liquefaction screening" in value for value in geotech_values)
    assert any("8.00-16.00" in value for value in geotech_values)


def test_csv_schedule(tmp_path):
    project = designed_project()
    path = export_csv(project, tmp_path / "schedule.csv")
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    assert len(rows) >= 2
    assert len(rows[0]) == 18
    assert rows[0][0] == "Element"


def test_pdf_report(tmp_path):
    project = designed_project()
    path = export_pdf(project, tmp_path / "report.pdf")
    data = Path(path).read_bytes()
    assert data.startswith(b"%PDF")
    assert len(data) > 5000


def test_import_template_and_parsers(tmp_path):
    path = export_import_template(tmp_path / "template.xlsx")
    wb = load_workbook(path)
    assert set(wb.sheetnames) >= {"Elements", "Soil Layers"}
    assert [c.value for c in wb["Elements"][1]] == ELEMENT_HEADERS
    assert [c.value for c in wb["Soil Layers"][1]] == SOIL_HEADERS

    elements = import_elements_excel(path)
    boreholes = import_soil_excel(path)
    assert len(elements) == 3
    by_id = {e.id: e for e in elements}
    column = by_id["C1"]
    assert column.max_service().P == 900.0
    assert column.dx == pytest.approx(0.15)
    circular = by_id["C2"]
    assert circular.is_circular
    assert circular.diameter == pytest.approx(0.60)
    assert circular.dy == pytest.approx(0.10)
    wall = by_id["W1"]
    assert wall.has_wall_endpoints()
    assert wall.wall_endpoints == pytest.approx((3.0, 3.5, 9.0, 3.5))
    assert wall.wall_thickness == pytest.approx(0.25)
    assert len(boreholes) == 1
    assert len(boreholes[0].layers) == 1


def test_import_elements_csv(tmp_path):
    path = tmp_path / "elements.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(ELEMENT_HEADERS)
        writer.writerow([
            "W2", "wall", 3, 4, 0, 0, "Rectangular", 6, 0.25, 0, 15.0,
            2.0, 4.0, 8.0, 4.0, 0.25, 0, "Auto", "Yes",
            800, 20, 60, 10, 5, 1120, 28, 84, 14, 7, "imported",
        ])
    elements = import_elements_csv(path)
    assert len(elements) == 1
    wall = elements[0]
    assert wall.kind == "wall"
    assert wall.max_service().P == 800.0
    assert wall.wall_length == pytest.approx(6.0)
    assert wall.wall_angle_deg == pytest.approx(0.0)
    assert wall.x1 == pytest.approx(2.0)
    assert wall.y2 == pytest.approx(4.0)


def test_selected_results_excludes_alternative():
    project = designed_project()
    selected = selected_results(project)
    assert all(r.details.get("selected", True) for r in selected)
    alternatives = [r for r in project.results if r.details.get("selected") is False]
    assert len(selected) == len(project.results) - len(alternatives)
