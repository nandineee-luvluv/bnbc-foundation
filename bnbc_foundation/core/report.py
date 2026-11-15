"""Excel, PDF, CSV, JSON and import-template reporting for the design tool.

The report layer is deliberately independent of the GUI so exports can be tested
from the command line.  All exported tables use SI units unless a column header
states otherwise (thickness and bar sizes in mm).
"""

from __future__ import annotations

import csv
import io
import json
import math
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .models import (
    Borehole,
    DesignResult,
    Element,
    Project,
    Reaction,
    SoilLayer,
    project_from_dict,
    project_to_dict,
)
from .rebar import bbs_totals, build_rebar_schedule, rebar_summary
from .soil import liquefaction_assessment
from .units import convert, convert_text, label, system_of, unit_system_name

# ---------------------------------------------------------------------------
# Selected results and tabular data
# ---------------------------------------------------------------------------

SCHEDULE_HEADERS = [
    "Element",
    "Kind",
    "Foundation type",
    "Requirement",
    "Qty",
    "Size",
    "Thickness (mm)",
    "Pile D (mm)",
    "Pile L (m)",
    "Piles",
    "Pile cap LxWxH (m)",
    "q max (kPa)",
    "q allow (kPa)",
    "Utilization",
    "Settlement (mm)",
    "Governing provision",
    "Status",
    "Remarks",
]


def selected_results(project: Project) -> list[DesignResult]:
    """Results that form the selected scheme (excludes the raft alternative)."""
    return [
        r for r in project.results
        if r.details.get("selected", True) is not False
    ]


def all_warning_lines(project: Project) -> list[str]:
    """Project-level and per-element warnings, de-duplicated for reports."""
    lines: list[str] = []
    seen: set[str] = set()
    for warning in project.warnings:
        text = str(warning).strip()
        if text and text not in seen:
            seen.add(text)
            lines.append(text)
    for result in selected_results(project):
        if not result.remarks:
            continue
        text = f"{result.element_id}: {result.remarks}"
        if text not in seen:
            seen.add(text)
            lines.append(text)
    return lines


def _u(value: float, quantity: str, system: str) -> float:
    return convert(value, quantity, system)


def schedule_headers(project: Project) -> list[str]:
    s = system_of(project)
    headers = list(SCHEDULE_HEADERS)
    headers[6] = f"Thickness ({label('length_mm', s)})"
    headers[7] = f"Pile D ({label('length_mm', s)})"
    headers[8] = f"Pile L ({label('length', s)})"
    headers[10] = f"Pile cap LxWxH ({label('length', s)})"
    headers[11] = f"q max ({label('pressure', s)})"
    headers[12] = f"q allow ({label('pressure', s)})"
    headers[14] = f"Settlement ({label('settlement', s)})"
    return headers


def geotech_headers(project: Project) -> list[str]:
    s = system_of(project)
    L, F = label("length", s), label("force", s)
    P, S = label("pressure", s), label("settlement", s)
    return [
        "Element", "Foundation", f"Depth ({L})", f"Service P ({F})",
        f"q max ({P})", f"q allow ({P})", "Bearing util.",
        f"Settlement ({S})", f"Limit ({S})", "Settlement OK",
        "Sliding FS", "Overturning FS", "Status", "Remarks",
    ]


def structural_headers(project: Project) -> list[str]:
    s = system_of(project)
    return [
        "Element", "Foundation", f"Thickness ({label('length_mm', s)})",
        "Flexure util.", "Shear util.", "Punching util.", "Overall util.",
        "Status", "Governing provision", "Bearing util.",
    ]


def supplemental_headers(project: Project) -> list[str]:
    s = system_of(project)
    return [
        "Element", "Foundation", f"Crack width ({label('settlement', s)})",
        f"Crack limit ({label('settlement', s)})", "Crack OK",
        f"Uplift ({label('force', s)})", "Uplift FS", "Uplift OK",
        f"Downdrag ({label('force', s)})", "Uplift util.", "Lateral util.",
        "P-M util.", "Pile checks OK",
    ]


def design_schedule_rows(project: Project) -> list[list[Any]]:
    system = system_of(project)
    return [r.schedule_row(system) for r in selected_results(project)]


def _fmt(value: Any, digits: int = 2, dash: str = "-") -> str:
    if value is None or value == "":
        return dash
    if isinstance(value, (int,)):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return dash
        if abs(value) < 1e-12:
            return "0"
        return f"{value:.{digits}f}"
    return str(value)


def geotech_rows(project: Project) -> list[list[Any]]:
    rows: list[list[Any]] = []
    s = system_of(project)
    for r in selected_results(project):
        checks = r.details.get("checks", {}) or {}
        d = r.details.get("design", {}) or {}
        rows.append([
            r.element_id,
            r.foundation_type,
            _fmt(_u(r.depth, "length", s), 2),
            _fmt(_u(r.service_load, "force", s), 1),
            _fmt(_u(r.q_service_max, "pressure", s), 1),
            _fmt(_u(r.q_allow, "pressure", s), 1),
            _fmt(r.q_service_max / max(r.q_allow, 1e-9), 3),
            _fmt(_u(r.settlement, "settlement", s), 1),
            _fmt(_u(r.settlement_limit, "settlement", s), 1),
            "YES" if checks.get("settlement_ok", r.settlement <= r.settlement_limit + 1e-6) else "NO",
            _fmt(d.get("sliding_fs"), 2),
            _fmt(d.get("overturning_fs"), 2),
            r.status,
            r.remarks,
        ])
    return rows


def liquefaction_rows(project: Project) -> list[list[Any]]:
    """Screening-level SPT liquefaction rows for reports."""
    pga = project.options.pga_g
    if pga <= 0:
        return []
    s = system_of(project)
    rows: list[list[Any]] = []
    for borehole in project.boreholes:
        for item in liquefaction_assessment(borehole, pga):
            rows.append([
                borehole.id,
                f"{_u(item.top, 'length', s):.2f}-{_u(item.bottom, 'length', s):.2f}",
                item.soil_type,
                f"{item.n60:.1f}",
                f"{pga:.2f}",
                f"{item.fs:.2f}" if item.n60 > 0 else "-",
                "YES" if item.triggered else "NO",
            ])
    return rows


def structural_rows(project: Project) -> list[list[Any]]:
    rows: list[list[Any]] = []
    s = system_of(project)
    for r in selected_results(project):
        checks = r.details.get("checks", {}) or {}
        d = r.details.get("design", {}) or {}
        ftype = (r.foundation_type or "").lower()
        flexure = 0.0
        shear = 0.0
        punching = 0.0
        if "raft" in ftype:
            flexure = d.get("flexure_utilization", 0.0)
            shear = d.get("shear_utilization", 0.0)
            punching = d.get("punching_utilization", 0.0)
        elif "pile" in ftype or "cap" in ftype:
            # Pile cap checks are expressed as demand / capacity.
            details = d.get("details", {}) or {}
            flex_x = details.get("flexure_x", {}) or {}
            flex_y = details.get("flexure_y", {}) or {}
            flexure = max(
                d.get("Mu_x", 0.0) / max(flex_x.get("phi_Mn", 0.0), 1e-9),
                d.get("Mu_y", 0.0) / max(flex_y.get("phi_Mn", 0.0), 1e-9),
            )
            shear = max(
                d.get("Vu_x", 0.0) / max(d.get("one_way_capacity_x", 0.0), 1e-9),
                d.get("Vu_y", 0.0) / max(d.get("one_way_capacity_y", 0.0), 1e-9),
            )
            punching = max(
                d.get("punching_vu", 0.0) / max(d.get("punching_capacity", 0.0), 1e-9),
                d.get("pile_punching_vu", 0.0) / max(d.get("pile_punching_capacity", 0.0), 1e-9),
            )
        else:
            # Footing design reports total Vu and punching capacities.
            punching = d.get("punching_vu", 0.0) / max(d.get("punching_capacity", 0.0), 1e-9)
        rows.append([
            r.element_id,
            r.foundation_type,
            _fmt(_u(r.thickness, "length_mm", s), 0),
            _fmt(flexure, 3),
            _fmt(shear, 3),
            _fmt(punching, 3),
            _fmt(r.utilization, 3),
            r.status,
            r.governing,
            _fmt(checks.get("bearing_utilization"), 3),
        ])
    return rows


def supplemental_rows(project: Project) -> list[list[Any]]:
    """Crack width, uplift, downdrag, lateral and P-M check rows."""
    rows: list[list[Any]] = []
    s = system_of(project)
    for r in selected_results(project):
        checks = r.details.get("checks", {}) or {}
        d = r.details.get("design", {}) or {}
        crack_width = checks.get("crack_width", d.get("crack_width"))
        crack_limit = d.get("crack_limit")
        if crack_limit is None and crack_width is not None:
            crack_limit = project.options.crack_width_limit
        crack_ok = checks.get("crack_ok", d.get("crack_ok"))
        uplift = d.get("uplift")
        uplift_fs = checks.get("uplift_fs", d.get("uplift_fs"))
        uplift_ok = checks.get("uplift_ok", d.get("uplift_ok"))
        downdrag = checks.get("downdrag")
        uplift_util = checks.get("uplift_utilization")
        lateral_util = checks.get("lateral_utilization")
        pm_util = checks.get("pm_utilization")
        pile_flags = [
            checks[key] for key in ("uplift_ok", "lateral_ok", "pm_ok")
            if key in checks
        ] if ("pile" in (r.foundation_type or "").lower()
              or "cap" in (r.foundation_type or "").lower()) else []
        pile_ok = all(pile_flags) if pile_flags else None
        rows.append([
            r.element_id,
            r.foundation_type,
            _fmt(_u(crack_width, "settlement", s) if crack_width is not None else None, 3),
            _fmt(_u(crack_limit, "settlement", s) if crack_limit is not None else None, 2),
            "-" if crack_ok is None else ("YES" if crack_ok else "NO"),
            _fmt(_u(uplift, "force", s) if uplift is not None else None, 1),
            _fmt(uplift_fs, 2),
            "-" if uplift_ok is None else ("YES" if uplift_ok else "NO"),
            _fmt(_u(downdrag, "force", s) if downdrag is not None else None, 1),
            _fmt(uplift_util, 3),
            _fmt(lateral_util, 3),
            _fmt(pm_util, 3),
            "-" if pile_ok is None else ("YES" if pile_ok else "NO"),
        ])
    return rows


def quantity_rows(project: Project) -> list[list[Any]]:
    results = selected_results(project)
    grouped: dict[str, dict[str, float]] = defaultdict(
        lambda: {"count": 0, "concrete": 0.0, "steel": 0.0, "pile": 0.0, "cost": 0.0}
    )
    for r in results:
        g = grouped[r.foundation_type or "Unclassified"]
        g["count"] += 1
        g["concrete"] += r.concrete_volume
        g["steel"] += r.steel_weight
        g["pile"] += r.pile_length_total
        g["cost"] += r.cost
    rows = []
    s = system_of(project)
    for name in sorted(grouped):
        g = grouped[name]
        rows.append([
            name, int(g["count"]),
            round(_u(g["concrete"], "volume", s), 2),
            round(_u(g["steel"], "mass", s), 1),
            round(_u(g["pile"], "length", s), 1),
            round(g["cost"], 2),
        ])
    return rows


def soil_rows(project: Project) -> list[list[Any]]:
    rows: list[list[Any]] = []
    s = system_of(project)
    for bh in project.boreholes:
        top = 0.0
        for i, layer in enumerate(bh.sorted_layers(), start=1):
            rows.append([
                bh.id, i,
                round(_u(bh.x, "length", s), 2), round(_u(bh.y, "length", s), 2),
                round(_u(bh.gwt, "length", s), 2),
                round(_u(top, "length", s), 2),
                round(_u(layer.bottom_depth, "length", s), 2),
                layer.soil_type, layer.description,
                round(_u(layer.gamma, "unit_weight", s), 1),
                round(_u(layer.gamma_sat, "unit_weight", s), 1),
                round(_u(layer.cohesion, "pressure", s), 1),
                round(layer.friction_angle, 1),
                round(_u(layer.cu, "pressure", s), 1),
                round(layer.n_raw, 0), round(layer.n60, 0),
                round(_u(layer.qc, "stress", s), 3),
                round(_u(layer.cpt_fs, "pressure", s), 1),
                round(layer.cc, 3), round(layer.e0, 3), round(layer.ocr, 2),
                round(layer.ll, 1), round(layer.pl, 1), round(layer.fines, 1),
                round(_u(layer.es, "pressure", s), 0),
                round(_u(layer.k_subgrade, "subgrade", s), 0),
                _fmt(_u(layer.allowable_bearing, "pressure", s)
                     if layer.allowable_bearing is not None else None, 1),
                _fmt(_u(layer.pile_skin, "pressure", s)
                     if layer.pile_skin is not None else None, 1),
                _fmt(_u(layer.pile_end, "pressure", s)
                     if layer.pile_end is not None else None, 1),
            ])
            top = layer.bottom_depth
    return rows


CODE_BASIS = [
    ("Loads", "BNBC 2020 Part 6, 2.7.3.1", "Strength load combinations."),
    ("Loads", "BNBC 2020 Part 6, 3.9.2", "Service load combinations for bearing and settlement."),
    ("Soil", "BNBC 2020 Part 6, 3.2", "Site investigation and soil parameters."),
    ("Bearing", "BNBC 2020 Part 6, 3.3 / 6.3", "Allowable bearing pressure and presumptive values."),
    ("Settlement", "BNBC 2020 Part 6, 3.8 / 6.3", "Total and differential settlement limits."),
    ("Shallow foundations", "BNBC 2020 Part 6, 6.2-6.5", "Footing sizing, depth and structural design."),
    ("Flexure", "BNBC 2020 Part 6, 6.6.3", "Reinforced concrete flexural strength."),
    ("Shear", "BNBC 2020 Part 6, 6.6.4 / 6.8.3", "One-way shear and punching shear."),
    ("Piles", "BNBC 2020 Part 6, 3.10 / 6.10", "Deep foundation capacity and group behaviour."),
    ("Pile caps", "BNBC 2020 Part 6, 6.8.5", "Pile cap flexure, shear and strut-and-tie."),
    ("Raft", "BNBC 2020 Part 6, 3.8.10 / 6.8", "Mat foundation pressure and structural design."),
    ("Earthquake", "BNBC 2020 Part 6, Chapter 2", "Seismic load cases and combinations."),
    ("Wind", "BNBC 2020 Part 6, Chapter 2", "Wind load cases and combinations."),
    ("Detailing", "BNBC 2020 Part 6, 6.6.8 / 8.7", "Development, spacing and minimum reinforcement."),
]


# ---------------------------------------------------------------------------
# Styles used by the Excel and PDF writers
# ---------------------------------------------------------------------------


def _excel_styles():
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    thin = Side(style="thin", color="C9C9C9")
    return {
        "header_font": Font(name="Calibri", bold=True, color="FFFFFF", size=10),
        "header_fill": PatternFill("solid", fgColor="1F4E79"),
        "header_align": Alignment(horizontal="center", vertical="center", wrap_text=True),
        "body_font": Font(name="Calibri", size=9),
        "body_align": Alignment(vertical="top", wrap_text=True),
        "title_font": Font(name="Calibri", bold=True, size=14, color="1F4E79"),
        "sub_font": Font(name="Calibri", size=9, italic=True, color="555555"),
        "border": Border(left=thin, right=thin, top=thin, bottom=thin),
        "ok_fill": PatternFill("solid", fgColor="E2EFDA"),
        "check_fill": PatternFill("solid", fgColor="FFF2CC"),
        "fail_fill": PatternFill("solid", fgColor="FCE4D6"),
    }


def _write_title(ws, row: int, title: str, subtitle: str = "") -> int:
    st = _excel_styles()
    ws.cell(row=row, column=1, value=title).font = st["title_font"]
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=18)
    row += 1
    if subtitle:
        ws.cell(row=row, column=1, value=subtitle).font = st["sub_font"]
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=18)
        row += 1
    return row + 1


def _write_table(ws, row: int, headers: list[str], rows: Iterable[Iterable[Any]],
                 widths: list[float] | None = None, status_col: int | None = None) -> int:
    st = _excel_styles()
    for col, header in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=header)
        cell.font = st["header_font"]
        cell.fill = st["header_fill"]
        cell.alignment = st["header_align"]
        cell.border = st["border"]
    ws.row_dimensions[row].height = 30
    row += 1
    for data in rows:
        for col, value in enumerate(data, start=1):
            cell = ws.cell(row=row, column=col, value=value)
            cell.font = st["body_font"]
            cell.alignment = st["body_align"]
            cell.border = st["border"]
        if status_col:
            status = str(data[status_col - 1]).upper()
            fill = st["ok_fill"] if status == "OK" else st["check_fill"] if status == "CHECK" else st["fail_fill"]
            ws.cell(row=row, column=status_col).fill = fill
        row += 1
    if widths:
        from openpyxl.utils import get_column_letter
        for i, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(i)].width = width
    return row + 1


def _new_sheet(wb, title):
    ws = wb.create_sheet(title=title)
    ws.sheet_view.showGridLines = False
    ws.freeze_panes = "A3"
    return ws


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------


def export_excel(project: Project, path: str | os.PathLike) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    path = str(path)
    wb = Workbook()
    wb.remove(wb.active)

    results = selected_results(project)
    s = system_of(project)
    counts = Counter(r.status for r in results)
    total_concrete = sum(r.concrete_volume for r in results)
    total_steel = sum(r.steel_weight for r in results)
    total_pile = sum(r.pile_length_total for r in results)
    total_cost = sum(r.cost for r in results)

    # 1. Summary
    ws = _new_sheet(wb, "Summary")
    row = 1
    ws.cell(row=row, column=1, value="BNBC 2020 FOUNDATION DESIGN REPORT").font = Font(
        name="Calibri", bold=True, size=18, color="1F4E79"
    )
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
    row += 2
    summary = [
        ("Project", project.info.name),
        ("Location", project.info.location),
        ("Engineer", project.info.engineer),
        ("Date", project.info.date or date.today().isoformat()),
        ("Code", project.info.code),
        ("Units", unit_system_name(s)),
        ("Columns", str(sum(1 for e in project.elements if e.kind == "column"))),
        ("Shear walls", str(sum(1 for e in project.elements if e.kind == "wall"))),
        ("Foundations", str(len(results))),
        ("Status OK", str(counts.get("OK", 0))),
        ("Status CHECK", str(counts.get("CHECK", 0))),
        ("Status FAIL", str(counts.get("FAIL", 0))),
        (f"Concrete ({label('volume', s)})", f"{_u(total_concrete, 'volume', s):.2f}"),
        (f"Reinforcement ({label('mass', s)})", f"{_u(total_steel, 'mass', s):.1f}"),
        (f"Pile length ({label('length', s)})", f"{_u(total_pile, 'length', s):.1f}"),
        ("Estimated cost", f"{total_cost:.2f}"),
    ]
    for field, value in summary:
        ws.cell(row=row, column=1, value=field).font = Font(bold=True, size=10)
        ws.cell(row=row, column=2, value=value).font = Font(size=10)
        row += 1
    row += 1
    ws.cell(row=row, column=1, value="Warnings").font = Font(bold=True, size=11, color="C00000")
    row += 1
    warning_lines = all_warning_lines(project) or ["No warnings were generated."]
    for warning in warning_lines:
        c = ws.cell(row=row, column=1, value=warning)
        c.alignment = Alignment(wrap_text=True)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        row += 1
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 42

    # 2. Foundation Schedule
    ws = _new_sheet(wb, "Foundation Schedule")
    row = _write_title(
        ws, 1, "Foundation Schedule",
        "Type, requirement, size and number for every column and shear wall",
    )
    _write_table(
        ws, row, schedule_headers(project), design_schedule_rows(project),
        widths=[12, 10, 20, 45, 7, 38, 11, 11, 10, 8, 22, 10, 10, 10, 12, 30, 10, 42],
        status_col=17,
    )

    # 3. Geotech Checks
    ws = _new_sheet(wb, "Geotech Checks")
    row = _write_title(ws, 1, "Geotechnical Checks", "Bearing, settlement and stability")
    row = _write_table(
        ws, row,
        geotech_headers(project),
        geotech_rows(project),
        widths=[12, 22, 10, 13, 12, 12, 12, 13, 10, 13, 10, 13, 10, 50],
        status_col=13,
    )
    ws.cell(row=row, column=1, value="SPT liquefaction screening").font = Font(
        bold=True, size=11, color="1F4E79"
    )
    row += 1
    if project.options.pga_g > 0:
        if liquefaction_rows(project):
            _write_table(
                ws, row,
                ["BH", f"Depth ({label('length', s)})", "Type", "N60",
                 "PGA (g)", "FS", "Triggered"],
                liquefaction_rows(project),
                widths=[10, 14, 10, 8, 10, 8, 12],
            )
        else:
            ws.cell(
                row=row, column=1,
                value="No saturated cohesionless layers were identified.",
            )
    else:
        ws.cell(
            row=row, column=1,
            value="Not performed: peak ground acceleration (PGA) was not provided.",
        )

    # 4. Structural Checks
    ws = _new_sheet(wb, "Structural Checks")
    row = _write_title(ws, 1, "Structural Checks", "Flexure, shear, punching and governing provisions")
    _write_table(
        ws, row,
        structural_headers(project),
        structural_rows(project),
        widths=[12, 22, 13, 12, 12, 13, 12, 10, 42, 12],
        status_col=8,
    )

    # 5. Supplemental Checks
    ws = _new_sheet(wb, "Supplemental Checks")
    row = _write_title(
        ws, 1, "Supplemental Checks",
        "Crack width, buoyancy/uplift, downdrag, lateral capacity and P-M interaction",
    )
    _write_table(
        ws, row,
        supplemental_headers(project),
        supplemental_rows(project),
        widths=[12, 22, 14, 14, 10, 12, 10, 10, 13, 14, 12, 12, 14],
    )

    # 6. Rebar Schedule
    rebar_items = build_rebar_schedule(results)
    ws = _new_sheet(wb, "Rebar Schedule")
    row = _write_title(ws, 1, "Reinforcement Schedule", "Project-wide bar schedule")
    _write_table(
        ws, row,
        ["Mark", "Member", "Element", "Description", "Dia (mm)", "Shape",
         "No.", "Cut length (m)", "Total length (m)", "Weight (kg)", "Spacing (mm)", "Notes"],
        [item.schedule_row() + [round(item.spacing, 0)] for item in rebar_items],
        widths=[8, 16, 14, 44, 9, 18, 8, 13, 14, 12, 12, 24],
    )
    row = _write_table(
        ws, row, ["Dia (mm)", "Bars", "Length (m)", "Weight (kg)"],
        [[s["diameter"], int(s["count"]), round(s["length"], 1), round(s["weight"], 1)]
         for s in rebar_summary(rebar_items)],
        widths=[10, 12, 14, 14],
    )
    if rebar_items:
        totals = bbs_totals(rebar_items)
        ws.cell(row=row, column=1, value="TOTAL").font = Font(bold=True)
        ws.cell(row=row + 1, column=1, value="Bars").font = Font(bold=True)
        ws.cell(row=row + 1, column=2, value=totals["bars"])
        ws.cell(row=row + 1, column=3, value="Length (m)").font = Font(bold=True)
        ws.cell(row=row + 1, column=4, value=round(totals["length_m"], 1))
        ws.cell(row=row + 1, column=5, value="Weight (kg)").font = Font(bold=True)
        ws.cell(row=row + 1, column=6, value=round(totals["weight_kg"], 1))

    # 6. Bar Bending Schedule
    ws = _new_sheet(wb, "Bar Bending Schedule")
    row = _write_title(ws, 1, "Bar Bending Schedule", "Cutting lengths and hook allowances")
    _write_table(
        ws, row,
        ["Mark", "Element", "Description", "Dia (mm)", "Shape", "No.",
         "Cut length (mm)", "Total length (m)", "Weight (kg)", "Notes"],
        [item.bbs_row() for item in rebar_items],
        widths=[8, 14, 46, 9, 20, 8, 14, 14, 12, 24],
    )

    # 7. Quantities
    ws = _new_sheet(wb, "Quantities")
    row = _write_title(ws, 1, "Quantity Summary", "Concrete, reinforcement and piles")
    row = _write_table(
        ws, row, ["Foundation type", "Count", f"Concrete ({label('volume', s)})",
                  f"Steel ({label('mass', s)})", f"Pile length ({label('length', s)})",
                  "Cost"],
        quantity_rows(project),
        widths=[28, 10, 14, 12, 14, 16],
    )
    ws.cell(row=row, column=1, value="TOTAL").font = Font(bold=True)
    ws.cell(row=row, column=2, value=len(results))
    ws.cell(row=row, column=3, value=round(_u(total_concrete, "volume", s), 2))
    ws.cell(row=row, column=4, value=round(_u(total_steel, "mass", s), 1))
    ws.cell(row=row, column=5, value=round(_u(total_pile, "length", s), 1))
    ws.cell(row=row, column=6, value=round(total_cost, 2))

    # 8. Soil Inputs
    ws = _new_sheet(wb, "Soil Inputs")
    row = _write_title(ws, 1, "Soil Inputs", "Boreholes, layers, SPT and laboratory data")
    _write_table(
        ws, row,
        ["BH", "Layer", "BH x", "BH y", f"GWT ({label('length', s)})",
         f"Top ({label('length', s)})", f"Bottom ({label('length', s)})",
         "Type", "Description", f"gamma ({label('unit_weight', s)})",
         f"gamma sat ({label('unit_weight', s)})", f"c' ({label('pressure', s)})",
         "phi' (deg)", f"cu ({label('pressure', s)})",
         "N raw", "N60", f"qc ({label('stress', s)})",
         f"CPT fs ({label('pressure', s)})", "Cc", "e0", "OCR",
         "LL", "PL", "Fines %", f"Es ({label('pressure', s)})",
         f"k ({label('subgrade', s)})", f"q allow ({label('pressure', s)})",
         f"Skin ({label('pressure', s)})", f"End ({label('pressure', s)})"],
        soil_rows(project),
        widths=[9, 7, 8, 8, 9, 8, 9, 9, 28, 8, 10, 8, 8, 8, 8, 8, 8, 8, 8,
                8, 8, 8, 9, 10, 12, 12, 10, 10],
    )

    # 9. Code Basis
    ws = _new_sheet(wb, "Code Basis")
    row = _write_title(ws, 1, "Code Basis and Assumptions",
                       "BNBC 2020 provisions used by this calculation report")
    _write_table(
        ws, row, ["Topic", "Provision", "Use"], CODE_BASIS,
        widths=[24, 38, 80],
    )
    row += 1
    assumptions = [
        f"All dimensions are in {label('length', s)} and all forces are in "
        f"{label('force', s)} unless labelled otherwise.",
        "Reinforcement diameters, cover and thicknesses are in millimetres.",
        "Service combinations govern bearing pressure and settlement; factored combinations govern strength.",
        "The raft is analysed as a Kirchhoff plate or Winkler strips on elastic springs where selected.",
        "Pile capacity correlations are intended for preliminary design and must be verified by load tests.",
        "This report is a design aid; a qualified engineer must review and approve the final design.",
    ]
    ws.cell(row=row, column=1, value="Assumptions and limitations").font = Font(bold=True, size=11)
    row += 1
    for text in assumptions:
        c = ws.cell(row=row, column=1, value=text)
        c.alignment = Alignment(wrap_text=True)
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        row += 1

    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def export_csv(project: Project, path: str | os.PathLike) -> str:
    path = str(path)
    with open(path, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.writer(fh)
        writer.writerow(schedule_headers(project))
        writer.writerows(design_schedule_rows(project))
    return path


# ---------------------------------------------------------------------------
# JSON save / load
# ---------------------------------------------------------------------------


def save_project(project: Project, path: str | os.PathLike) -> str:
    path = str(path)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(project_to_dict(project), fh, indent=2, ensure_ascii=False)
    return path


def load_project(path: str | os.PathLike) -> Project:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return project_from_dict(data)


# ---------------------------------------------------------------------------
# Excel/CSV import templates and parsers
# ---------------------------------------------------------------------------


ELEMENT_HEADERS = [
    "ID", "Kind", "X (m)", "Y (m)", "dx (m)", "dy (m)", "Shape",
    "Length (m)", "Width (m)", "Diameter (m)", "Rotation (deg)",
    "Wall x1 (m)", "Wall y1 (m)", "Wall x2 (m)", "Wall y2 (m)",
    "Wall thickness (m)", "Base elevation (m)", "Preferred",
    "Includes lateral",
    "Service P (kN)", "Service Mx (kN.m)", "Service My (kN.m)",
    "Service Vx (kN)", "Service Vy (kN)",
    "Factored P (kN)", "Factored Mx (kN.m)", "Factored My (kN.m)",
    "Factored Vx (kN)", "Factored Vy (kN)", "Notes",
]

SOIL_HEADERS = [
    "Borehole", "BH x (m)", "BH y (m)", "GWT (m)", "Bottom depth (m)",
    "Soil type", "Description", "gamma (kN/m3)", "gamma sat (kN/m3)",
    "c' (kPa)", "phi' (deg)", "cu (kPa)", "N raw", "N60", "qc (MPa)",
    "CPT fs (kPa)", "Cc", "e0", "OCR", "LL", "PL", "Fines (%)",
    "Es (kPa)", "k (kN/m3)",
    "Allowable bearing (kPa)", "Pile skin (kPa)", "Pile end (kPa)",
    "Pile skin driven (kPa)", "Pile end driven (kPa)",
    "Pile skin bored (kPa)", "Pile end bored (kPa)",
]

ELEMENT_EXAMPLE = [
    "C1", "column", 0.0, 0.0, 0.15, 0.0, "Rectangular",
    0.45, 0.45, 0.0, 30.0, "", "", "", "", 0.25, 0.0, "Auto", "No",
    900.0, 30.0, 25.0, 20.0, 15.0,
    1260.0, 42.0, 35.0, 28.0, 21.0, "Example offset and rotated column",
]

WALL_ELEMENT_EXAMPLE = [
    "W1", "wall", 6.0, 3.5, 0.0, 0.0, "Rectangular",
    6.0, 0.25, 0.0, 0.0, 3.0, 3.5, 9.0, 3.5, 0.25, 0.0, "Auto", "Yes",
    3200.0, 180.0, 900.0, 220.0, 60.0,
    4480.0, 252.0, 1260.0, 308.0, 84.0, "Example wall with endpoints",
]

CIRCULAR_ELEMENT_EXAMPLE = [
    "C2", "column", 6.0, 0.0, 0.0, 0.10, "Circular",
    0.60, 0.60, 0.60, 0.0, "", "", "", "", 0.25, 0.0, "Auto", "No",
    1800.0, 70.0, 45.0, 40.0, 25.0,
    2520.0, 98.0, 63.0, 56.0, 35.0, "Example circular column",
]

SOIL_EXAMPLE = [
    "BH-1", 0.0, 0.0, 2.0, 3.0, "Fill", "Loose silty fill",
    17.0, 18.5, 0.0, 26.0, 0.0, 6.0, 5.0, 2.0, 35.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0,
    4000.0, 0.0, "", "", "", "", "", "", "",
]


def export_import_template(path: str | os.PathLike) -> str:
    """Write an Excel workbook used for importing elements and soil data."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    path = str(path)
    wb = Workbook()
    ws = wb.active
    ws.title = "Elements"
    ws.append(ELEMENT_HEADERS)
    ws.append(ELEMENT_EXAMPLE)
    ws.append(CIRCULAR_ELEMENT_EXAMPLE)
    ws.append(WALL_ELEMENT_EXAMPLE)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
        cell.alignment = Alignment(wrap_text=True)
    widths = [10, 10, 8, 8, 8, 8, 13, 10, 10, 11, 10, 10, 10, 10, 13, 13, 12,
              11, 14, 14, 14, 14, 14, 14, 14, 14, 14, 14, 34]
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"

    soil = wb.create_sheet("Soil Layers")
    soil.append(SOIL_HEADERS)
    soil.append(SOIL_EXAMPLE)
    for cell in soil[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
        cell.alignment = Alignment(wrap_text=True)
    soil_widths = [10, 8, 8, 8, 12, 10, 26, 12, 12, 8, 8, 8, 8, 8, 8, 8,
                   8, 8, 8, 8, 8, 8, 10, 10, 14, 12, 12, 14, 14, 14, 14]
    for i, width in enumerate(soil_widths, start=1):
        soil.column_dimensions[get_column_letter(i)].width = width
    soil.freeze_panes = "A2"

    info = wb.create_sheet("Instructions")
    info["A1"] = "Import instructions"
    info["A1"].font = Font(bold=True, size=14)
    lines = [
        "1. Fill one row per column or shear wall on the Elements sheet.",
        "2. Columns: X/Y is the reaction/insertion point; dx/dy offset it to the column centre.",
        "3. Rectangular columns use Length x Width; circular columns set Shape=Circular and Diameter.",
        "4. Walls: enter Wall x1/y1 and Wall x2/y2 centreline endpoints and the wall thickness. "
        "Blank endpoints fall back to X/Y, Length and Wall thickness.",
        "5. Fill one row per soil layer on the Soil Layers sheet; use the same Borehole id for all layers in a borehole.",
        "6. Leave direct capacity columns blank to use SPT/static correlations.",
        "7. Save the workbook and use Import in the Loads or Soil page.",
        "8. Only the first 500 element rows are read; duplicated IDs overwrite earlier rows.",
    ]
    for i, line in enumerate(lines, start=3):
        info.cell(row=i, column=1, value=line)
    info.column_dimensions["A"].width = 120
    for row in info.iter_rows(min_row=3, max_row=2 + len(lines), min_col=1, max_col=1):
        row[0].alignment = Alignment(wrap_text=True, vertical="top")
    wb.save(path)
    return path


def _read_workbook(path: str) -> "Any":
    from openpyxl import load_workbook

    if str(path).lower().endswith(".csv"):
        raise ValueError("Use import_elements_csv for CSV files")
    return load_workbook(path, data_only=True)


def _rows_from_sheet(ws) -> list[dict[str, Any]]:
    iterator = ws.iter_rows(values_only=True)
    try:
        headers = [str(h).strip() if h is not None else "" for h in next(iterator)]
    except StopIteration:
        return []
    rows = []
    for values in iterator:
        if values is None or all(v is None or v == "" for v in values):
            continue
        rows.append({headers[i]: values[i] for i in range(min(len(headers), len(values)))})
    return rows


def _num(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_text(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("yes", "y", "true", "1", "lateral")


def _lookup(row: dict[str, Any], *names: str, default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    # Tolerate minor header changes (case/space insensitive).
    norm = {str(k).strip().lower().replace(" ", "").replace("_", ""): v for k, v in row.items()}
    for name in names:
        key = name.strip().lower().replace(" ", "").replace("_", "")
        if key in norm and norm[key] not in (None, ""):
            return norm[key]
    return default


def import_element_rows(rows: list[dict[str, Any]]) -> list[Element]:
    elements: list[Element] = []
    for row in rows[:500]:
        element_id = str(_lookup(row, "ID", "Element", "Element ID", default="")).strip()
        if not element_id:
            continue
        kind = str(_lookup(row, "Kind", "Type", default="column")).strip().lower()
        if kind not in ("column", "wall"):
            kind = "wall" if "wall" in kind else "column"
        shape = str(_lookup(row, "Shape", "Column shape", default="Rectangular")).strip()
        shape = "Circular" if ("circ" in shape.lower() or "round" in shape.lower()) else "Rectangular"
        lateral = _bool_text(_lookup(row, "Includes lateral", "Lateral", default=False))
        sp = _num(_lookup(row, "Service P (kN)", "Service P", "P", default=0.0))
        smx = _num(_lookup(row, "Service Mx (kN.m)", "Service Mx", default=0.0))
        smy = _num(_lookup(row, "Service My (kN.m)", "Service My", default=0.0))
        svx = _num(_lookup(row, "Service Vx (kN)", "Service Vx", default=0.0))
        svy = _num(_lookup(row, "Service Vy (kN)", "Service Vy", default=0.0))
        fp = _num(_lookup(row, "Factored P (kN)", "Factored P", default=0.0))
        fmx = _num(_lookup(row, "Factored Mx (kN.m)", "Factored Mx", default=0.0))
        fmy = _num(_lookup(row, "Factored My (kN.m)", "Factored My", default=0.0))
        fvx = _num(_lookup(row, "Factored Vx (kN)", "Factored Vx", default=0.0))
        fvy = _num(_lookup(row, "Factored Vy (kN)", "Factored Vy", default=0.0))
        reactions = [
            Reaction("Service", sp, smx, smy, svx, svy, includes_lateral=lateral)
        ]
        if any(abs(v) > 1e-9 for v in (fp, fmx, fmy, fvx, fvy)):
            reactions.append(Reaction("Factored", fp, fmx, fmy, fvx, fvy,
                                      factored=True, includes_lateral=lateral))
        length_default = 0.45 if kind == "column" else 3.0
        width_default = 0.45 if kind == "column" else 0.25
        elements.append(Element(
            id=element_id,
            kind=kind,
            x=_num(_lookup(row, "X (m)", "X", default=0.0)),
            y=_num(_lookup(row, "Y (m)", "Y", default=0.0)),
            base_elev=_num(_lookup(row, "Base elevation (m)", "Base elevation", default=0.0)),
            length=_num(_lookup(row, "Length (m)", "Length", default=length_default)),
            width=_num(_lookup(row, "Width (m)", "Width", default=width_default)),
            wall_thickness=_num(
                _lookup(row, "Wall thickness (m)", "Wall thickness", "Wall t (m)",
                        "Wall t", default=0.25)
            ),
            preferred=str(_lookup(row, "Preferred", default="Auto")),
            reactions=reactions,
            notes=str(_lookup(row, "Notes", default="")),
            dx=_num(_lookup(row, "dx (m)", "dx", "Offset x (m)", "Offset x", default=0.0)),
            dy=_num(_lookup(row, "dy (m)", "dy", "Offset y (m)", "Offset y", default=0.0)),
            shape=shape,
            diameter=_num(
                _lookup(row, "Diameter (m)", "Diameter", "Dia. (m)", "Dia", default=0.0)
            ),
            rotation=_num(
                _lookup(row, "Rotation (deg)", "Rotation", "Rot. (deg)",
                        "Plan rotation (deg)", default=0.0)
            ),
            x1=_optional_num(_lookup(row, "Wall x1 (m)", "Wall x1", "x1")),
            y1=_optional_num(_lookup(row, "Wall y1 (m)", "Wall y1", "y1")),
            x2=_optional_num(_lookup(row, "Wall x2 (m)", "Wall x2", "x2")),
            y2=_optional_num(_lookup(row, "Wall y2 (m)", "Wall y2", "y2")),
        ))
    return elements


def import_elements_excel(path: str | os.PathLike) -> list[Element]:
    wb = _read_workbook(path)
    if "Elements" not in wb.sheetnames:
        raise ValueError("Workbook must contain an 'Elements' sheet")
    return import_element_rows(_rows_from_sheet(wb["Elements"]))


def import_elements_csv(path: str | os.PathLike) -> list[Element]:
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    return import_element_rows(rows)


def _reaction_is_factored(case: str) -> bool:
    upper = case.upper()
    tokens = [t for t in upper.replace("-", " ").replace("_", " ").split() if t]
    if any(word in upper for word in ("FACTOR", "ULTIMATE", "STRENGTH", "ENVELOPE")):
        return True
    return any(
        t.startswith(("1.2", "1.4", "1.6", "0.9", "1.0")) for t in tokens
    )


def _reaction_includes_lateral(case: str) -> bool:
    upper = case.upper()
    tokens = [t.strip("()[]") for t in upper.replace("+", " ").replace("-", " ").split()]
    stripped = [re.sub(r"^[0-9.]+", "", t) for t in tokens]
    return any(
        t in ("W", "WL", "WIND", "EQ", "EQX", "EQY", "E", "S", "SEISMIC")
        or t.startswith(("WIND", "EQ", "SEISM"))
        for t in stripped
        if t
    )


def import_reactions_csv(
    project: Project,
    path: str | os.PathLike,
    replace: bool = False,
    scale: float = 1.0,
) -> dict[str, Any]:
    """Import ETABS/SAFE-style base reactions from CSV and attach them.

    Recognised element keys are ``Label``, ``Unique Name``, ``Element``,
    ``Column``, ``Joint`` and ``Node``.  Load-case keys include
    ``Load Case/Combo``, ``Load Case``, ``Combo`` and ``Case``.  Force keys are
    ``P``, ``FZ`` (converted from the ETABS tension-positive convention),
    ``MX/Mx``, ``MY/My``, ``FX`` and ``FY``.  A scale factor converts the file
    units to kN and kN.m.

    Existing service/factored reactions are merged by load-case name unless
    ``replace`` is True.  The return value is a small import report suitable
    for a GUI message box.
    """
    by_id = {e.id.upper(): e for e in project.elements}
    matched: set[str] = set()
    cleared: set[str] = set()
    unmatched: set[str] = set()
    cases: set[str] = set()
    row_count = 0
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            element_id = str(_lookup(
                row, "Label", "Unique Name", "Element", "Element ID",
                "Column", "Joint", "Node", "ID", default="",
            )).strip()
            if not element_id:
                continue
            row_count += 1
            element = by_id.get(element_id.upper())
            if element is None:
                unmatched.add(element_id)
                continue
            case = str(_lookup(
                row, "Load Case/Combo", "Load Case", "Combo", "Case",
                "Output Case", "Load Case Name", default="Service",
            )).strip() or "Service"
            direct_p = _lookup(
                row, "P (kN)", "P", "Axial", "Reaction P", "F3", default=None
            )
            if direct_p is None:
                fz = _lookup(row, "FZ", "Fz", "Fz (kN)", default=None)
                # ETABS reports a downward (compressive) column reaction as a
                # negative FZ, so flip it to the compression-positive convention.
                p = -_num(fz) if fz is not None else 0.0
            else:
                p = _num(direct_p)
            mx = _num(_lookup(row, "MX", "Mx", "Mx (kN.m)", "M2", "Moment X", default=0.0))
            my = _num(_lookup(row, "MY", "My", "My (kN.m)", "M3", "Moment Y", default=0.0))
            vx = _num(_lookup(row, "FX", "Fx", "Vx", "VX", "V2", "Shear X", default=0.0))
            vy = _num(_lookup(row, "FY", "Fy", "Vy", "VY", "V3", "Shear Y", default=0.0))
            factored = _reaction_is_factored(case)
            lateral = _reaction_includes_lateral(case)
            reaction = Reaction(
                case=case, P=p * scale, Mx=mx * scale, My=my * scale,
                Vx=vx * scale, Vy=vy * scale, factored=factored,
                includes_lateral=lateral,
            )
            if replace:
                if element.id not in cleared:
                    element.reactions = []
                    cleared.add(element.id)
                element.reactions.append(reaction)
            else:
                kept = [r for r in element.reactions if r.case != case]
                kept.append(reaction)
                element.reactions = kept
            matched.add(element.id)
            cases.add(case)
    return {
        "rows": row_count,
        "elements": len(matched),
        "matched": sorted(matched),
        "unmatched": sorted(unmatched),
        "cases": sorted(cases),
    }


def import_soil_excel(path: str | os.PathLike) -> list[Borehole]:
    wb = _read_workbook(path)
    if "Soil Layers" not in wb.sheetnames:
        raise ValueError("Workbook must contain a 'Soil Layers' sheet")
    rows = _rows_from_sheet(wb["Soil Layers"])
    boreholes: dict[str, Borehole] = {}
    for row in rows[:1000]:
        bh_id = str(_lookup(row, "Borehole", "BH", "Borehole ID", default="")).strip()
        if not bh_id:
            continue
        bh = boreholes.get(bh_id)
        if bh is None:
            bh = Borehole(
                id=bh_id,
                x=_num(_lookup(row, "BH x (m)", "BH x", default=0.0)),
                y=_num(_lookup(row, "BH y (m)", "BH y", default=0.0)),
                gwt=_num(_lookup(row, "GWT (m)", "GWT", default=2.0)),
                layers=[],
            )
            boreholes[bh_id] = bh
        layer = SoilLayer(
            bottom_depth=_num(_lookup(row, "Bottom depth (m)", "Bottom depth", default=1.0)),
            soil_type=str(_lookup(row, "Soil type", "Type", default="CL")),
            description=str(_lookup(row, "Description", default="")),
            gamma=_num(_lookup(row, "gamma (kN/m3)", "gamma", default=18.0)),
            gamma_sat=_num(_lookup(row, "gamma sat (kN/m3)", "gamma sat", default=19.0)),
            cohesion=_num(_lookup(row, "c' (kPa)", "cohesion", default=0.0)),
            friction_angle=_num(_lookup(row, "phi' (deg)", "phi", default=0.0)),
            cu=_num(_lookup(row, "cu (kPa)", "cu", default=0.0)),
            n_raw=_num(_lookup(row, "N raw", "N_raw", "SPT", default=0.0)),
            n60=_num(_lookup(row, "N60", default=0.0)),
            cc=_num(_lookup(row, "Cc", default=0.0)),
            e0=_num(_lookup(row, "e0", default=0.0)),
            ocr=_num(_lookup(row, "OCR", default=1.0)),
            ll=_num(_lookup(row, "LL", default=0.0)),
            pl=_num(_lookup(row, "PL", default=0.0)),
            fines=_num(_lookup(row, "Fines (%)", "Fines", default=0.0)),
            es=_num(_lookup(row, "Es (kPa)", "Es", default=0.0)),
            k_subgrade=_num(_lookup(row, "k (kN/m3)", "k_subgrade", default=0.0)),
            allowable_bearing=_optional_num(_lookup(row, "Allowable bearing (kPa)", "Allowable bearing")),
            pile_skin=_optional_num(_lookup(row, "Pile skin (kPa)", "Pile skin")),
            pile_end=_optional_num(_lookup(row, "Pile end (kPa)", "Pile end")),
            pile_skin_driven=_optional_num(_lookup(row, "Pile skin driven (kPa)", "Pile skin driven")),
            pile_end_driven=_optional_num(_lookup(row, "Pile end driven (kPa)", "Pile end driven")),
            pile_skin_bored=_optional_num(_lookup(row, "Pile skin bored (kPa)", "Pile skin bored")),
            pile_end_bored=_optional_num(_lookup(row, "Pile end bored (kPa)", "Pile end bored")),
            qc=_num(_lookup(row, "qc (MPa)", "qc", default=0.0)),
            cpt_fs=_num(_lookup(row, "CPT fs (kPa)", "cpt_fs", "CPT fs", default=0.0)),
        )
        bh.layers.append(layer)
    for bh in boreholes.values():
        bh.layers.sort(key=lambda l: l.bottom_depth)
    return list(boreholes.values())


def import_soil_csv(path: str | os.PathLike) -> list[Borehole]:
    """Read soil layers from CSV using the same headers as the template."""
    with tempfile.TemporaryDirectory(prefix="bnbc-import-") as tmp:
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Soil Layers"
        with open(path, newline="", encoding="utf-8-sig") as fh:
            for row in csv.reader(fh):
                ws.append(row)
        tmp_path = os.path.join(tmp, "soil.xlsx")
        wb.save(tmp_path)
        return import_soil_excel(tmp_path)


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------


def _pdf_styles():
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib import colors

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle("TitleX", parent=base["Title"], fontSize=22,
                                leading=27, textColor=colors.HexColor("#1F4E79")),
        "subtitle": ParagraphStyle("SubX", parent=base["Normal"], fontSize=11,
                                   leading=15, textColor=colors.HexColor("#44546A")),
        "h1": ParagraphStyle("H1X", parent=base["Heading1"], fontSize=15, leading=19,
                             spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#1F4E79")),
        "h2": ParagraphStyle("H2X", parent=base["Heading2"], fontSize=11, leading=14,
                             spaceBefore=8, spaceAfter=4, textColor=colors.HexColor("#2E75B6")),
        "body": ParagraphStyle("BodyX", parent=base["BodyText"], fontSize=8.5, leading=11),
        "small": ParagraphStyle("SmallX", parent=base["BodyText"], fontSize=7.2, leading=9),
        "cell": ParagraphStyle("CellX", parent=base["BodyText"], fontSize=7.0, leading=8.5,
                               wordWrap="CJK"),
        "warn": ParagraphStyle("WarnX", parent=base["BodyText"], fontSize=8.2, leading=11,
                               textColor=colors.HexColor("#C00000")),
    }
    return styles


def _pdf_table(data, widths, styles, header=True):
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    table = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B4C6E7")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.0),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ]
    table.setStyle(TableStyle(commands))
    return table


def plan_shape(element) -> tuple[str, Any]:
    """Plan-view shape for an element: circle radius or footprint polygon."""
    if element.kind == "column" and element.is_circular:
        cx, cy = element.center
        return "circle", (cx, cy, element.section_length / 2.0)
    return "polygon", [tuple(p) for p in element.footprint_polygon]


def _site_plan_image(project: Project, path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Circle, Polygon as MplPolygon, Rectangle
    except Exception:
        return False
    try:
        s = system_of(project)
        f = convert(1.0, "length", s)
        unit = label("length", s)
        fig, ax = plt.subplots(figsize=(8.2, 4.8))
        for e in project.elements:
            cx, cy = (v * f for v in e.center)
            shape, data = plan_shape(e)
            if shape == "circle":
                ax.add_patch(Circle(
                    (data[0] * f, data[1] * f), data[2] * f,
                    facecolor="#9DC3E6", edgecolor="#1F4E79", alpha=0.55,
                ))
            else:
                ax.add_patch(MplPolygon(
                    [(p[0] * f, p[1] * f) for p in data], closed=True,
                    facecolor="#9DC3E6", edgecolor="#1F4E79", alpha=0.55,
                ))
            # Mark the reaction/insertion point when it differs from the centre.
            if abs(e.x - cx / f) > 1e-9 or abs(e.y - cy / f) > 1e-9:
                ax.plot(e.x * f, e.y * f, marker="+", color="#C00000", markersize=6)
            ax.text(cx, cy + 0.35 * f, e.id, ha="center", va="bottom", fontsize=7)
        for r in selected_results(project):
            footprint = r.details.get("footprint")
            rect = r.details.get("rect")
            if r.element_kind == "raft":
                continue
            if footprint:
                ax.add_patch(MplPolygon(
                    [(p[0] * f, p[1] * f) for p in footprint], closed=True, fill=False,
                    linestyle="--", linewidth=0.8, edgecolor="#C00000",
                ))
            elif rect:
                x0, y0, x1, y1 = rect
                ax.add_patch(Rectangle((x0 * f, y0 * f), (x1 - x0) * f,
                                       (y1 - y0) * f, fill=False,
                                       linestyle="--", linewidth=0.8, edgecolor="#C00000"))
        o = project.options
        if o.site_xmax - o.site_xmin < 5000 and o.site_ymax - o.site_ymin < 5000:
            ax.add_patch(Rectangle((o.site_xmin * f, o.site_ymin * f),
                                   (o.site_xmax - o.site_xmin) * f,
                                   (o.site_ymax - o.site_ymin) * f,
                                   fill=False, linewidth=1.2, linestyle=":", edgecolor="green"))
        for bh in project.boreholes:
            ax.plot(bh.x * f, bh.y * f, marker="v", color="#7030A0", markersize=7)
            ax.text(bh.x * f, (bh.y - 0.45) * f, bh.id, ha="center", fontsize=7,
                    color="#7030A0")
        ax.set_aspect("equal", adjustable="datalim")
        ax.set_xlabel(f"x ({unit})")
        ax.set_ylabel(f"y ({unit})")
        ax.set_title("Site plan and foundation outlines", fontsize=10)
        ax.grid(True, linestyle=":", linewidth=0.4, alpha=0.6)
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        return True
    except Exception:
        return False


def _spt_plot_image(project: Project, path) -> bool:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return False
    try:
        s = system_of(project)
        f = convert(1.0, "length", s)
        fig, ax = plt.subplots(figsize=(4.2, 5.2))
        for bh in project.boreholes:
            depths, nvals, labels = [], [], []
            top = 0.0
            for layer in bh.sorted_layers():
                mid = 0.5 * (top + layer.bottom_depth)
                depths.append(mid * f)
                nvals.append(layer.effective_n60())
                labels.append(layer.soil_type)
                top = layer.bottom_depth
            ax.plot(nvals, depths, marker="o", linewidth=1.2, label=bh.id)
        ax.invert_yaxis()
        ax.set_xlabel("N60")
        ax.set_ylabel(f"Depth below ground ({label('length', s)})")
        ax.set_title("SPT profile")
        ax.grid(True, linestyle=":", linewidth=0.4)
        if len(project.boreholes) > 1:
            ax.legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)
        return True
    except Exception:
        return False


def export_pdf(project: Project, path: str | os.PathLike) -> str:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Image,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    path = str(path)
    styles = _pdf_styles()
    results = selected_results(project)
    s = system_of(project)
    counts = Counter(r.status for r in results)
    total_concrete = sum(r.concrete_volume for r in results)
    total_steel = sum(r.steel_weight for r in results)
    total_pile = sum(r.pile_length_total for r in results)
    total_cost = sum(r.cost for r in results)
    rebar_items = build_rebar_schedule(results)

    doc = SimpleDocTemplate(
        path, pagesize=landscape(A4),
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=13 * mm, bottomMargin=13 * mm,
        title=project.info.name, author=project.info.engineer or "BNBC Foundation Designer",
    )
    story: list[Any] = []

    # Cover
    story.append(Spacer(1, 28))
    story.append(Paragraph(project.info.name or "Foundation Design Report", styles["title"]))
    story.append(Paragraph("Geotechnical and structural foundation design", styles["subtitle"]))
    story.append(Spacer(1, 8))
    cover = [
        ["Project", project.info.name],
        ["Location", project.info.location or "-"],
        ["Engineer", project.info.engineer or "-"],
        ["Date", project.info.date or date.today().isoformat()],
        ["Code", project.info.code],
        ["Units", unit_system_name(s)],
        ["Columns / walls", f"{sum(1 for e in project.elements if e.kind == 'column')} / "
                            f"{sum(1 for e in project.elements if e.kind == 'wall')}"],
        ["Foundation types", ", ".join(sorted({r.foundation_type for r in results})) or "-"],
        ["Status", f"{counts.get('OK', 0)} OK, {counts.get('CHECK', 0)} CHECK, "
                   f"{counts.get('FAIL', 0)} FAIL"],
    ]
    story.append(_pdf_table(cover, [45 * mm, 190 * mm], styles, header=False))
    story.append(Spacer(1, 12))
    story.append(Paragraph(
        "This report presents the foundation schedule, geotechnical checks, structural "
        "checks, reinforcement schedule and bar bending schedule produced by the BNBC 2020 "
        "Foundation Designer. Results are preliminary and must be reviewed by a qualified "
        "engineer before construction.", styles["body"]))
    story.append(PageBreak())

    # Design basis
    story.append(Paragraph("1. Design basis and assumptions", styles["h1"]))
    basis = [
        ["Item", "Basis"],
        ["Loads", "BNBC 2020 Part 6, 2.7.3.1 strength and 3.9.2 service combinations"],
        ["Soil", "SPT correlations, static bearing capacity and direct report values"],
        ["Shallow foundations", "Meyerhof bearing capacity, biaxial pressure, settlement and stability"],
        ["Piles", "SPT/static capacity with construction-control factors of safety"],
        ["Raft", "Rigid pressure plus Winkler strips or Kirchhoff plate on elastic springs"],
        ["Structural", "BNBC 2020 Part 6 flexure, one-way shear, punching shear and detailing"],
        ["Units", f"{label('force', s)}, {label('pressure', s)}, "
                  f"{label('moment', s)}, {label('length', s)} and {label('length_mm', s)}"],
    ]
    story.append(_pdf_table(basis, [45 * mm, 190 * mm], styles))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Service loads govern bearing pressure and settlement. Factored loads govern "
        "reinforcement and shear. Pile capacity correlations are preliminary and should be "
        "verified by static load tests. The raft plate model assumes linear elastic soil and "
        "free edges; local soft spots require separate investigation.", styles["body"]))

    # Soil profile
    story.append(Paragraph("2. Soil profile", styles["h1"]))
    soil_data = [["BH", "Layer", f"Depth ({label('length', s)})", "Type", "Description",
                  "N60", f"cu ({label('pressure', s)})", "phi (deg)",
                  f"Es ({label('pressure', s)})", f"q allow ({label('pressure', s)})"]]
    for bh in project.boreholes:
        top = 0.0
        for layer in bh.sorted_layers():
            soil_data.append([
                bh.id, "",
                f"{_u(top, 'length', s):.2f}-{_u(layer.bottom_depth, 'length', s):.2f}",
                layer.soil_type,
                layer.description, f"{layer.effective_n60():.0f}",
                f"{_u(layer.cu, 'pressure', s):.1f}",
                f"{layer.friction_angle:.1f}", f"{_u(layer.es, 'pressure', s):.0f}",
                "" if layer.allowable_bearing is None
                else f"{_u(layer.allowable_bearing, 'pressure', s):.1f}",
            ])
            top = layer.bottom_depth
    story.append(_pdf_table(soil_data,
                            [16 * mm, 10 * mm, 22 * mm, 15 * mm, 70 * mm, 12 * mm,
                             14 * mm, 14 * mm, 18 * mm, 24 * mm], styles))
    story.append(Spacer(1, 5))
    story.append(Paragraph("SPT liquefaction screening", styles["h2"]))
    pga = project.options.pga_g
    if pga > 0:
        liq_data = [["BH", f"Depth ({label('length', s)})", "Type", "N60",
                     "PGA (g)", "FS", "Triggered"]]
        liq_data.extend(liquefaction_rows(project))
        if len(liq_data) > 1:
            story.append(_pdf_table(
                liq_data,
                [16 * mm, 30 * mm, 18 * mm, 14 * mm, 16 * mm, 14 * mm, 18 * mm],
                styles,
            ))
        else:
            story.append(Paragraph(
                "No saturated cohesionless layers were identified.", styles["body"]
            ))
    else:
        story.append(Paragraph(
            "Not performed: peak ground acceleration (PGA) was not provided.",
            styles["body"],
        ))
    story.append(Spacer(1, 5))
    spt_buffer = io.BytesIO()
    if _spt_plot_image(project, spt_buffer):
        spt_buffer.seek(0)
        story.append(Image(spt_buffer, width=65 * mm, height=80 * mm))
    story.append(PageBreak())

    # Site plan
    story.append(Paragraph("3. Site plan and foundation outlines", styles["h1"]))
    plan_buffer = io.BytesIO()
    if _site_plan_image(project, plan_buffer):
        plan_buffer.seek(0)
        story.append(Image(plan_buffer, width=220 * mm, height=128 * mm))
    else:
        story.append(Paragraph("Site plan unavailable.", styles["body"]))
    story.append(PageBreak())

    # Schedule
    story.append(Paragraph("4. Foundation schedule", styles["h1"]))
    schedule_data = [["Element", "Kind", "Foundation type", "Qty", "Size",
                      f"q max ({label('pressure', s)})",
                      f"q allow ({label('pressure', s)})", "Util.",
                      f"Settle ({label('settlement', s)})", "Status"]]
    for r in results:
        schedule_data.append([
            r.element_id, r.element_kind, r.foundation_type, str(r.quantity), r.size,
            _fmt(_u(r.q_service_max, "pressure", s), 1),
            _fmt(_u(r.q_allow, "pressure", s), 1), _fmt(r.utilization, 2),
            _fmt(_u(r.settlement, "settlement", s), 1), r.status,
        ])
    story.append(_pdf_table(schedule_data,
                            [15 * mm, 16 * mm, 36 * mm, 8 * mm, 65 * mm, 13 * mm,
                             13 * mm, 11 * mm, 17 * mm, 13 * mm], styles))
    story.append(Spacer(1, 8))
    requirement_data = [["Element", "Requirement / selection basis"]]
    for r in results:
        requirement_data.append([r.element_id, convert_text(r.requirement, s)])
    story.append(_pdf_table(requirement_data, [20 * mm, 215 * mm], styles))
    story.append(PageBreak())

    # Detailed calculations
    story.append(Paragraph("5. Detailed calculations", styles["h1"]))
    for r in results:
        story.append(Paragraph(f"{r.element_id} - {r.foundation_type}", styles["h2"]))
        story.append(Paragraph(
            f"<b>Size:</b> {convert_text(r.size, s)}<br/>"
            f"<b>Service / factored load:</b> "
            f"{_u(r.service_load, 'force', s):.1f} / {_u(r.factored_load, 'force', s):.1f} "
            f"{label('force', s)}<br/>"
            f"<b>Utilization:</b> {r.utilization:.3f}; <b>Status:</b> {r.status}<br/>"
            f"<b>Governing provision:</b> {r.governing}<br/>"
            f"<b>Remarks:</b> {convert_text(r.remarks, s) or '-'}", styles["body"]))
        d = r.details.get("design", {}) or {}
        checks = r.details.get("checks", {}) or {}
        detail_rows = [["Quantity", "Value", "Quantity", "Value"]]
        pairs = []
        if "q_service_max" in d:
            pairs += [(f"q service max ({label('pressure', s)})",
                       _fmt(_u(d.get("q_service_max"), "pressure", s), 1)),
                      (f"q allowable ({label('pressure', s)})",
                       _fmt(_u(d.get("q_allow"), "pressure", s), 1)),
                      (f"Settlement ({label('settlement', s)})",
                       _fmt(_u(d.get("settlement"), "settlement", s), 1)),
                      (f"Settlement limit ({label('settlement', s)})",
                       _fmt(_u(d.get("settlement_limit"), "settlement", s), 1)),
                      ("Sliding FS", _fmt(d.get("sliding_fs"), 2)),
                      ("Overturning FS", _fmt(d.get("overturning_fs"), 2))]
        if "punching_vu" in d:
            pairs += [(f"Punching demand ({label('force', s)})",
                       _fmt(_u(d.get("punching_vu"), "force", s), 1)),
                      (f"Punching capacity ({label('force', s)})",
                       _fmt(_u(d.get("punching_capacity"), "force", s), 1))]
        if "maximum_pile_load" in d or "max_pile_reaction" in d:
            pairs += [(f"Max pile reaction ({label('force', s)})",
                       _fmt(_u(d.get("max_pile_reaction", d.get("max_pile_load")),
                               "force", s), 1)),
                      ("Pile count", str(r.pile_count or d.get("pile_count", ""))),
                      (f"Pile diameter ({label('length_mm', s)})",
                       _fmt(convert((r.pile_diameter or d.get("pile_diameter", 0)) * 1000,
                                    "length_mm", s), 0)),
                      (f"Pile length ({label('length', s)})",
                       _fmt(_u(r.pile_length, "length", s), 1))]
        if "moment_x_pos" in d or "analysis" in d:
            analysis = d.get("analysis", {}) or {}
            pairs += [(f"Raft thickness ({label('length_mm', s)})",
                       _fmt(convert(r.thickness, "length_mm", s), 0)),
                      (f"Max positive Mx ({label('moment_per_length', s)})",
                       _fmt(_u(d.get("moment_x_pos", analysis.get("moment_x_pos")),
                               "moment_per_length", s), 1)),
                      (f"Max negative Mx ({label('moment_per_length', s)})",
                       _fmt(_u(d.get("moment_x_neg", analysis.get("moment_x_neg")),
                               "moment_per_length", s), 1)),
                      (f"Max positive My ({label('moment_per_length', s)})",
                       _fmt(_u(d.get("moment_y_pos", analysis.get("moment_y_pos")),
                               "moment_per_length", s), 1)),
                      (f"Max negative My ({label('moment_per_length', s)})",
                       _fmt(_u(d.get("moment_y_neg", analysis.get("moment_y_neg")),
                               "moment_per_length", s), 1))]
        for key in ("bearing_utilization", "pile_utilization", "cap_utilization",
                    "shear_utilization", "punching_utilization", "flexure_utilization"):
            if key in checks:
                pairs.append((key.replace("_", " ").title(), _fmt(checks[key], 3)))
        crack_width = checks.get("crack_width", d.get("crack_width"))
        crack_limit = d.get("crack_limit")
        if crack_width is not None:
            pairs.append((f"Crack width ({label('settlement', s)})",
                          _fmt(_u(crack_width, "settlement", s), 3)))
            pairs.append((f"Crack limit ({label('settlement', s)})",
                          _fmt(_u(crack_limit, "settlement", s), 2)))
        crack_ok = checks.get("crack_ok", d.get("crack_ok"))
        if crack_ok is not None:
            pairs.append(("Crack OK", "YES" if crack_ok else "NO"))
        if "uplift" in d:
            pairs.append((f"Uplift ({label('force', s)})",
                          _fmt(_u(d.get("uplift"), "force", s), 1)))
        uplift_fs = checks.get("uplift_fs", d.get("uplift_fs"))
        if uplift_fs is not None:
            pairs.append(("Uplift FS", _fmt(uplift_fs, 2)))
        uplift_ok = checks.get("uplift_ok", d.get("uplift_ok"))
        if uplift_ok is not None:
            pairs.append(("Uplift OK", "YES" if uplift_ok else "NO"))
        if "downdrag" in checks:
            pairs.append((f"Downdrag ({label('force', s)})",
                          _fmt(_u(checks.get("downdrag"), "force", s), 1)))
        for key, caption in (
            ("uplift_utilization", "Pile uplift util."),
            ("lateral_utilization", "Lateral util."),
            ("pm_utilization", "P-M util."),
        ):
            if key in checks:
                pairs.append((caption, _fmt(checks[key], 3)))
        for i in range(0, len(pairs), 2):
            first = pairs[i]
            second = pairs[i + 1] if i + 1 < len(pairs) else ("", "")
            detail_rows.append([first[0], first[1], second[0], second[1]])
        if len(detail_rows) > 1:
            story.append(_pdf_table(detail_rows,
                                    [38 * mm, 30 * mm, 55 * mm, 30 * mm], styles))
        if r.alternatives:
            story.append(Paragraph("<b>Alternatives considered:</b> " +
                                   "; ".join(r.alternatives), styles["small"]))
        story.append(Spacer(1, 6))
    story.append(PageBreak())

    # Rebar
    story.append(Paragraph("6. Reinforcement schedule and bar bending schedule", styles["h1"]))
    if rebar_items:
        rebar_data = [["Mark", "Element", "Description", "Dia", "Shape", "No.",
                       "Cut (m)", "Total (m)", "Weight (kg)"]]
        for item in rebar_items:
            rebar_data.append([item.mark, item.element_id, item.description,
                               f"{item.diameter:.0f}", item.shape, str(item.count),
                               f"{item.cut_length:.3f}", f"{item.total_length:.2f}",
                               f"{item.weight:.2f}"])
        story.append(_pdf_table(rebar_data,
                                [12 * mm, 18 * mm, 80 * mm, 12 * mm, 30 * mm,
                                 10 * mm, 16 * mm, 18 * mm, 18 * mm], styles))
        totals = bbs_totals(rebar_items)
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"<b>Totals:</b> {totals['items']} schedule items, {totals['bars']} bars, "
            f"{totals['length_m']:.1f} m, {totals['weight_kg']:.1f} kg.", styles["body"]))
    else:
        story.append(Paragraph("No reinforcement schedule was generated.", styles["body"]))
    story.append(PageBreak())

    # Quantities and warnings
    story.append(Paragraph("7. Quantities, warnings and limitations", styles["h1"]))
    qrows = [["Foundation type", "Count", f"Concrete ({label('volume', s)})",
              f"Steel ({label('mass', s)})", f"Pile length ({label('length', s)})", "Cost"]]
    for row in quantity_rows(project):
        qrows.append([row[0], str(row[1]), f"{row[2]:.2f}", f"{row[3]:.1f}",
                      f"{row[4]:.1f}", f"{row[5]:.2f}"])
    qrows.append(["TOTAL", str(len(results)),
                  f"{_u(total_concrete, 'volume', s):.2f}",
                  f"{_u(total_steel, 'mass', s):.1f}",
                  f"{_u(total_pile, 'length', s):.1f}", f"{total_cost:.2f}"])
    story.append(_pdf_table(qrows, [60 * mm, 18 * mm, 32 * mm, 28 * mm, 32 * mm, 35 * mm], styles))
    story.append(Spacer(1, 8))
    story.append(Paragraph("Warnings and review items", styles["h2"]))
    warnings = all_warning_lines(project)
    if not warnings:
        story.append(Paragraph("No warnings were generated.", styles["body"]))
    for warning in warnings:
        story.append(Paragraph(warning, styles["warn"]))
    story.append(Spacer(1, 6))
    for text in (
        "This report is generated from the input data and correlations selected in the application.",
        "Bearing capacities, pile capacities and settlements must be checked against the project soil report.",
        "Pile capacities are preliminary until verified by static load tests.",
        "The raft analysis assumes elastic, uniform subgrade support; soft spots and cavities require separate analysis.",
        "A qualified engineer must review and approve the design before construction.",
    ):
        story.append(Paragraph("- " + text, styles["body"]))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(14 * mm, 7 * mm, project.info.name)
        canvas.drawRightString(283 * mm, 7 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


# ---------------------------------------------------------------------------
# Convenience dispatch
# ---------------------------------------------------------------------------


def export_all(project: Project, directory: str | os.PathLike) -> dict[str, str]:
    """Write Excel, PDF, CSV and JSON outputs into ``directory``."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stem = "".join(c if c.isalnum() or c in "-_ " else "_" for c in project.info.name).strip() or "foundation"
    stem = stem.replace(" ", "_")
    return {
        "excel": export_excel(project, directory / f"{stem}.xlsx"),
        "pdf": export_pdf(project, directory / f"{stem}.pdf"),
        "csv": export_csv(project, directory / f"{stem}.csv"),
        "json": save_project(project, directory / f"{stem}.json"),
        "template": export_import_template(directory / f"{stem}_import_template.xlsx"),
    }
