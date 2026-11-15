"""Regression tests for the verified Ponytail audit fixes.

One test per audit item keeps the failure mode visible: the assertion describes
what the old code got wrong, not just what the new code happens to return.
"""

from __future__ import annotations

import csv
import math
import shutil
import subprocess

import pytest

from bnbc_foundation.core.loads import governing_factored
from bnbc_foundation.core.models import (
    Borehole,
    Element,
    Reaction,
    SoilLayer,
    sample_project,
)
from bnbc_foundation.core.piles import (
    _has_direct_pile,
    broms_lateral_capacity,
    compute_pile_capacity,
)
from bnbc_foundation.core.raft import analyze_raft
from bnbc_foundation.core.report import (
    SOIL_EXAMPLE,
    SOIL_HEADERS,
    _reaction_includes_lateral,
    export_import_template,
    export_pdf,
    import_reactions_csv,
    import_soil_csv,
    import_soil_excel,
    structural_rows,
)
from bnbc_foundation.core.selector import _q_allow, run_design
from bnbc_foundation.core.settlement import estimate_shallow_settlement
from bnbc_foundation.core.soil import vertical_stress
from bnbc_foundation.core.structural.concrete import (
    BarLayout,
    FlexureResult,
    development_length,
)
from bnbc_foundation.core.structural.footing import (
    _beam_moment_envelope,
    _mat_steel_weight,
    _net_service_pressure,
    design_combined,
    design_isolated,
    design_strip,
)
from bnbc_foundation.core.structural import footing as footing_module


# ---------------------------------------------------------------------------
# 1. Raft differential check uses millimetres and never treats 0 as a pass
# ---------------------------------------------------------------------------


def test_raft_differential_uses_millimetres_and_rigid_is_not_checked():
    project = sample_project()
    plate = analyze_raft(
        project.elements, project.boreholes[0], 300.0,
        project.options, project.materials, method="Plate",
    )
    assert plate.differential_checked
    assert plate.differential * 1000.0 > project.options.differential_limit
    assert plate.differential * 1000.0 == pytest.approx(27.6, abs=0.2)
    assert "Differential deflection 27.6 mm > 20.0 mm" in plate.remarks
    assert plate.status == "CHECK"

    rigid = analyze_raft(
        project.elements, project.boreholes[0], 300.0,
        project.options, project.materials, method="Rigid",
    )
    assert not rigid.differential_checked
    assert "not checked" in rigid.remarks
    assert "Differential deflection not checked" in rigid.remarks


# ---------------------------------------------------------------------------
# 2. Pile-cap anchorage uses the selected bars and controls the status
# ---------------------------------------------------------------------------


def test_pile_cap_anchorage_uses_selected_bars_and_controls_status():
    project = sample_project()
    run_design(project)
    wall = next(e for e in project.elements if e.id == "W1")
    result = next(r for r in project.results if r.element_id == "W1")
    cap = result.details["design"]

    db_x = cap["bottom_x"]["diameter"]
    db_y = cap["bottom_y"]["diameter"]
    expected_required = max(
        development_length(db_x, project.materials.f_c, project.materials.f_y),
        development_length(db_y, project.materials.f_c, project.materials.f_y),
    )
    assert cap["development_required"] == pytest.approx(expected_required)

    c_l = max(wall.section_projection_x, 1.0) * 1000.0
    c_b = max(wall.section_projection_y, 0.20) * 1000.0
    edge_cover = max(
        project.options.cap_cover, project.options.cap_edge_cover * 1000.0
    )
    expected_available = min(
        (cap["length"] * 1000.0 - c_l) / 2.0 - edge_cover,
        (cap["width"] * 1000.0 - c_b) / 2.0 - edge_cover,
    )
    assert cap["development_available"] == pytest.approx(expected_available)
    assert cap["development_available"] < cap["development_required"]
    assert result.status == "CHECK"
    assert "Development length available" in result.remarks


# ---------------------------------------------------------------------------
# 3. Strip and combined status includes flexure and bar flags
# ---------------------------------------------------------------------------


def _failing_flexure(*args, **kwargs):
    return FlexureResult(As_req=120.0, As_min=0.0, ok=False, note="forced flexure failure")


@pytest.mark.parametrize("crack_check", [True, False])
def test_strip_and_combined_status_include_flexure_failure(monkeypatch, crack_check):
    monkeypatch.setattr(footing_module, "flexural_design", _failing_flexure)
    project = sample_project()
    project.options.crack_check = crack_check
    borehole = project.boreholes[0]

    wall = next(e for e in project.elements if e.id == "W1")
    strip = design_strip(wall, borehole, 350.0, project.options, project.materials)
    assert strip.status == "CHECK"
    assert "Reinforcement/depth check requires attention" in strip.remarks

    first = Element(
        "A", "column", 0.0, 0.0, 0.0, 0.45, 0.45,
        reactions=[Reaction("Service", 600.0, 0.0, 0.0)],
    )
    second = Element(
        "B", "column", 3.0, 0.0, 0.0, 0.45, 0.45,
        reactions=[Reaction("Service", 600.0, 0.0, 0.0)],
    )
    combined = design_combined(
        [first, second], borehole, 300.0, project.options, project.materials
    )
    assert combined.status == "CHECK"
    assert "Reinforcement/depth check requires attention" in combined.remarks


# ---------------------------------------------------------------------------
# 4. Strip and combined flexure use the peak pressure, not the average
# ---------------------------------------------------------------------------


def test_strip_flexure_uses_peak_pressure():
    project = sample_project()
    wall = next(e for e in project.elements if e.id == "W1")
    q_allow, _ = _q_allow(wall, project.boreholes[0], project.options)
    design = design_strip(
        wall, project.boreholes[0], q_allow, project.options, project.materials
    )
    projection = max((design.width - max(wall.wall_thickness, 0.10)) / 2.0, 0.0)
    average_moment = (
        design.details["shear"]["q_avg"] * projection ** 2 / 2.0
    )
    assert design.Mu_x > average_moment * 1.5
    assert design.details["shear"]["q_u"] > design.details["shear"]["q_avg"]


def test_combined_beam_includes_global_moment_in_the_line_load():
    project = sample_project()
    borehole = project.boreholes[0]

    def build(total_my: float):
        first = Element(
            "A", "column", 0.0, 0.0, 0.0, 0.45, 0.45,
            reactions=[
                Reaction("Service", 600.0, 0.0, total_my / 2.0),
                Reaction("Strength", 840.0, 0.0, total_my * 0.7 / 2.0, factored=True),
            ],
        )
        second = Element(
            "B", "column", 3.0, 0.0, 0.0, 0.45, 0.45,
            reactions=[
                Reaction("Service", 600.0, 0.0, total_my / 2.0),
                Reaction("Strength", 840.0, 0.0, total_my * 0.7 / 2.0, factored=True),
            ],
        )
        return design_combined(
            [first, second], borehole, 600.0, project.options, project.materials
        )

    design = build(900.0)
    columns = [
        (e.center_x, governing_factored(e).P)
        for e in (
            Element(
                "A", "column", 0.0, 0.0, 0.0, 0.45, 0.45,
                reactions=[Reaction("Strength", 840.0, 0.0, 315.0, factored=True)],
            ),
            Element(
                "B", "column", 3.0, 0.0, 0.0, 0.45, 0.45,
                reactions=[Reaction("Strength", 840.0, 0.0, 315.0, factored=True)],
            ),
        )
    ]
    line_avg = sum(p for _, p in columns) / design.length
    uniform_pos, _ = _beam_moment_envelope(
        design.origin_x, design.length, line_avg, columns
    )
    peak_pos, _ = design.details["moment_envelope"]
    assert peak_pos > uniform_pos * 1.5
    assert design.Mu_x == pytest.approx(peak_pos / design.width)


# ---------------------------------------------------------------------------
# 5. Reaction CSV replace keeps every load case
# ---------------------------------------------------------------------------


def test_reaction_csv_replace_keeps_all_load_cases(tmp_path):
    project = sample_project()
    path = tmp_path / "reactions.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Element", "Case", "P (kN)", "Mx (kN.m)", "My (kN.m)"])
        writer.writerow(["C1", "DL", 900.0, 30.0, 25.0])
        writer.writerow(["C1", "LL", 300.0, 10.0, 5.0])

    report = import_reactions_csv(project, path, replace=True)
    column = next(e for e in project.elements if e.id == "C1")
    assert len(column.reactions) == 2
    assert {r.case for r in column.reactions} == {"DL", "LL"}
    assert report["cases"] == ["DL", "LL"]
    assert column.reactions[0].P == pytest.approx(900.0)
    assert column.reactions[1].P == pytest.approx(300.0)


# ---------------------------------------------------------------------------
# 6. Broms lateral capacity respects the specified steel strength
# ---------------------------------------------------------------------------


def test_broms_lateral_capacity_uses_requested_steel_strength():
    project = sample_project()
    borehole = project.boreholes[0]
    _, allow_250 = broms_lateral_capacity(
        borehole, 0.6, 20.0, "Bored", 2.5, f_c=30.0, f_y=250.0
    )
    _, allow_420 = broms_lateral_capacity(
        borehole, 0.6, 20.0, "Bored", 2.5, f_c=30.0, f_y=420.0
    )
    assert allow_250 < allow_420
    assert allow_250 == pytest.approx(11.95, abs=0.1)
    assert allow_420 == pytest.approx(20.07, abs=0.1)


# ---------------------------------------------------------------------------
# 7. Structural design follows the rotated section projection
# ---------------------------------------------------------------------------


def test_rotated_column_projection_changes_footing_design():
    project = sample_project()
    borehole = project.boreholes[0]
    reactions = [
        Reaction("Service", 900.0, 10.0, 8.0),
        Reaction("Strength", 1260.0, 14.0, 11.0, factored=True),
    ]

    def design(rotation: float):
        column = Element(
            "C", "column", 0.0, 0.0, 0.0, 0.60, 0.40,
            rotation=rotation, reactions=reactions,
        )
        return design_isolated(
            column, borehole, 300.0, project.options, project.materials
        )

    square = design(0.0)
    rotated = design(90.0)
    assert rotated.Mu_x == pytest.approx(square.Mu_y, rel=1e-9)
    assert rotated.Mu_y == pytest.approx(square.Mu_x, rel=1e-9)
    assert (rotated.bottom_x.diameter, rotated.bottom_x.spacing) == (
        square.bottom_y.diameter, square.bottom_y.spacing
    )
    assert (rotated.bottom_y.diameter, rotated.bottom_y.spacing) == (
        square.bottom_x.diameter, square.bottom_x.spacing
    )

    forty_five = design(45.0)
    assert forty_five.Mu_x == pytest.approx(forty_five.Mu_y, rel=1e-9)


# ---------------------------------------------------------------------------
# 8. Soil import reads CPT qc and sleeve friction
# ---------------------------------------------------------------------------


def test_soil_import_reads_qc_and_cpt_sleeve_friction(tmp_path):
    path = export_import_template(tmp_path / "template.xlsx")
    layers = import_soil_excel(path)[0].sorted_layers()
    assert layers[0].qc == pytest.approx(2.0)
    assert layers[0].cpt_fs == pytest.approx(35.0)

    csv_path = tmp_path / "soil.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(SOIL_HEADERS)
        writer.writerow(SOIL_EXAMPLE)
    assert import_soil_csv(csv_path)[0].sorted_layers()[0].qc == pytest.approx(2.0)
    assert import_soil_csv(csv_path)[0].sorted_layers()[0].cpt_fs == pytest.approx(35.0)


# ---------------------------------------------------------------------------
# 9. Shallow settlement uses net pressure after overburden removal
# ---------------------------------------------------------------------------


def test_shallow_settlement_uses_net_pressure():
    project = sample_project()
    borehole = project.boreholes[0]
    column = Element(
        "C9", "column", 0.0, 0.0, 0.0, 0.45, 0.45,
        reactions=[
            Reaction("Service", 400.0, 0.0, 0.0),
            Reaction("Strength", 560.0, 0.0, 0.0, factored=True),
        ],
    )
    design = design_isolated(
        column, borehole, 200.0, project.options, project.materials
    )
    net = _net_service_pressure(
        column, design.length, design.width, design.thickness,
        project.materials.gamma_concrete, borehole, design.depth,
    )
    expected = estimate_shallow_settlement(
        borehole, design.depth, design.length, design.width, net, project.options
    )
    assert design.settlement == pytest.approx(expected.total)
    gross = (
        400.0
        + project.materials.gamma_concrete * design.length * design.width * design.thickness
    ) / (design.length * design.width)
    gross_settlement = estimate_shallow_settlement(
        borehole, design.depth, design.length, design.width, gross, project.options
    )
    assert design.settlement < gross_settlement.total

    first = Element(
        "A", "column", 0.0, 0.0, 0.0, 0.45, 0.45,
        reactions=[Reaction("Service", 600.0, 0.0, 0.0)],
    )
    second = Element(
        "B", "column", 3.0, 0.0, 0.0, 0.45, 0.45,
        reactions=[Reaction("Service", 600.0, 0.0, 0.0)],
    )
    combined = design_combined(
        [first, second], borehole, 300.0, project.options, project.materials
    )
    self_weight = (
        project.materials.gamma_concrete
        * combined.length * combined.width * combined.thickness
    )
    q_avg = (1200.0 + self_weight) / (combined.length * combined.width)
    combined_net = max(q_avg - vertical_stress(borehole, combined.depth)[2], 0.0)
    expected_combined = estimate_shallow_settlement(
        borehole, combined.depth, combined.length, combined.width,
        combined_net, project.options,
    )
    assert combined.settlement == pytest.approx(expected_combined.total)


# ---------------------------------------------------------------------------
# 10. Mat steel weight counts every layout in full
# ---------------------------------------------------------------------------


def test_mat_steel_weight_counts_each_layout_once():
    layout = BarLayout(diameter=16.0, spacing=100.0, As_provided=1005.0)
    weight = _mat_steel_weight(layout, layout, layout, layout, 2.0, 2.0)
    assert weight == pytest.approx(126.2, rel=1e-3)


# ---------------------------------------------------------------------------
# 11. PDF detailed raft moments fall back to the analysis dictionary
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("pdftotext") is None, reason="pdftotext unavailable")
def test_pdf_raft_moments_use_analysis_values(tmp_path):
    project = sample_project()
    project.options.raft_trigger = "Always"
    run_design(project)
    path = export_pdf(project, tmp_path / "raft.pdf")
    text = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "Max positive Mx" in text
    assert "Max negative Mx" in text
    assert "97.6" in text
    assert "529.7" in text
    assert "Max positive Mx (kN.m/m)" in text


# ---------------------------------------------------------------------------
# 12. Structural Checks reports pile-cap flexure utilization
# ---------------------------------------------------------------------------


def test_structural_rows_report_pile_cap_flexure():
    project = sample_project()
    project.options.allow_isolated = False
    project.options.allow_combined = False
    project.options.allow_strip = False
    project.options.allow_raft = False
    project.options.raft_trigger = "Never"
    run_design(project)

    rows = {row[0]: row for row in structural_rows(project)}
    caps = {
        r.element_id: r.details["design"]
        for r in project.results
        if "cap" in (r.foundation_type or "").lower()
    }
    assert {"W1", "C2"} <= set(caps)
    for element_id in ("W1", "C2"):
        cap = caps[element_id]
        expected = max(
            cap["Mu_x"] / max(cap["details"]["flexure_x"]["phi_Mn"], 1e-9),
            cap["Mu_y"] / max(cap["details"]["flexure_y"]["phi_Mn"], 1e-9),
        )
        assert expected > 0.0
        assert float(rows[element_id][3]) == pytest.approx(expected, abs=0.001)


# ---------------------------------------------------------------------------
# 13. One shared plan-shape helper returns rotated footprint polygons
# ---------------------------------------------------------------------------


def test_plan_shape_draws_rotated_column_as_a_polygon():
    from bnbc_foundation.core.report import plan_shape

    column = Element(
        "C", "column", 0.0, 0.0, 0.0, 0.60, 0.30, rotation=90.0,
    )
    shape, data = plan_shape(column)
    assert shape == "polygon"
    xs = [point[0] for point in data]
    ys = [point[1] for point in data]
    assert max(xs) - min(xs) == pytest.approx(0.30)
    assert max(ys) - min(ys) == pytest.approx(0.60)

    circular = Element(
        "C2", "column", 0.0, 0.0, 0.0, 0.60, 0.60,
        shape="Circular", diameter=0.60,
    )
    circle_shape, circle_data = plan_shape(circular)
    assert circle_shape == "circle"
    assert circle_data[2] == pytest.approx(0.30)


# ---------------------------------------------------------------------------
# 14. Lateral-load detection strips numeric combination coefficients
# ---------------------------------------------------------------------------


def test_lateral_detection_strips_numeric_coefficients():
    assert _reaction_includes_lateral("1.2D+1.6W")
    assert _reaction_includes_lateral("1.0E")
    assert _reaction_includes_lateral("0.9D+1.6W")
    assert _reaction_includes_lateral("1.2D+1.0EQX")
    assert not _reaction_includes_lateral("1.4D")
    assert not _reaction_includes_lateral("1.2D+1.6L")


# ---------------------------------------------------------------------------
# 15. Direct end-bearing values are recognised without skin values
# ---------------------------------------------------------------------------


def test_direct_end_bearing_is_recognised_without_skin_value():
    project = sample_project()
    project.options.pile_design_method = "SPT"
    base = dict(
        bottom_depth=20.0, soil_type="SP", n_raw=15, n60=15,
        gamma=18.0, gamma_sat=19.0, friction_angle=30.0,
    )
    direct_layer = SoilLayer(**base, pile_end=500.0)
    correlated_layer = SoilLayer(**base)
    assert _has_direct_pile(direct_layer, "Bored")
    assert not _has_direct_pile(correlated_layer, "Bored")

    direct = compute_pile_capacity(
        Borehole(layers=[direct_layer]), "Bored", 0.6, 20.0, project.options
    )
    correlated = compute_pile_capacity(
        Borehole(layers=[correlated_layer]), "Bored", 0.6, 20.0, project.options
    )
    assert direct.end_ultimate == pytest.approx(500.0 * math.pi * 0.3 ** 2)
    assert direct.ultimate != pytest.approx(correlated.ultimate)


# ---------------------------------------------------------------------------
# 16. Pile results merge group and cap remarks
# ---------------------------------------------------------------------------


def test_pile_result_remarks_merge_group_and_cap_notes():
    project = sample_project()
    run_design(project)
    result = next(r for r in project.results if r.element_id == "W1")
    assert "Group settlement" in result.remarks
    assert "Development length" in result.remarks
    assert result.remarks.count("Group settlement") == 1
