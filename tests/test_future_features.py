"""Regression tests for the features previously listed as future work.

Covers column plan rotation, CPT pile capacity, CPT fallback correlations,
crack width, shallow-footing uplift, downdrag, pile uplift, Broms lateral
capacity, P-M interaction, non-rectangular raft outlines and the ETABS/SAFE
CSV reaction importer.
"""

import csv
import math

import pytest

from bnbc_foundation.core.bearing import (
    check_shallow_uplift,
    polygon_pressure,
    pressure_distribution,
)
from bnbc_foundation.core.geometry import polygon_area, rectangle_polygon
from bnbc_foundation.core.models import (
    Borehole,
    Element,
    FoundationOptions,
    SoilLayer,
    project_from_dict,
    project_to_dict,
    sample_project,
)
from bnbc_foundation.core.piles import (
    _cpt_qc_fs,
    broms_lateral_capacity,
    compute_pile_capacity,
)
from bnbc_foundation.core.raft import analyze_raft, raft_outline
from bnbc_foundation.core.report import import_reactions_csv
from bnbc_foundation.core.structural.concrete import (
    crack_width_check,
    pile_pm_interaction,
)


# ---------------------------------------------------------------------------
# Arbitrary column rotation
# ---------------------------------------------------------------------------


def test_rectangular_column_rotation_changes_footprint_and_projection():
    column = Element(
        id="C1", kind="column", x=0.0, y=0.0,
        length=0.60, width=0.40, rotation=30.0,
    )
    a = math.radians(30.0)
    assert column.section_angle_deg == pytest.approx(30.0)
    assert column.section_projection_x == pytest.approx(
        0.60 * math.cos(a) + 0.40 * math.sin(a)
    )
    assert column.section_projection_y == pytest.approx(
        0.60 * math.sin(a) + 0.40 * math.cos(a)
    )
    xmin, ymin, xmax, ymax = column.footprint_bounds
    assert (xmax - xmin) == pytest.approx(column.section_projection_x)
    assert (ymax - ymin) == pytest.approx(column.section_projection_y)
    assert len(column.footprint_polygon) == 4
    assert column.footprint_area == pytest.approx(0.60 * 0.40)


def test_rotation_survives_json_roundtrip_and_walls_follow_the_axis():
    project = sample_project()
    data = project_to_dict(project)
    restored = project_from_dict(data)
    c3 = next(e for e in restored.elements if e.id == "C3")
    assert c3.rotation == pytest.approx(30.0)
    wall = next(e for e in restored.elements if e.id == "W1")
    assert wall.section_angle_deg == pytest.approx(wall.wall_angle_deg)


# ---------------------------------------------------------------------------
# CPT pile capacity
# ---------------------------------------------------------------------------


def test_cpt_pile_capacity_uses_cone_data():
    project = sample_project()
    project.options.pile_design_method = "CPT"
    capacity = compute_pile_capacity(
        project.boreholes[0], "Bored", 0.6, 25.0, project.options
    )
    assert capacity.allowable > 0
    assert "CPT" in capacity.note
    assert capacity.fs >= 2.5
    assert capacity.lateral_capacity > 0
    assert capacity.uplift_capacity > 0


def test_cpt_fallback_correlation_uses_n60():
    sand = SoilLayer(soil_type="SP", n60=20)
    clay = SoilLayer(soil_type="CL", n60=20)
    qc_sand, fs_sand = _cpt_qc_fs(sand)
    qc_clay, fs_clay = _cpt_qc_fs(clay)
    assert qc_sand == pytest.approx(0.40 * 20.0)
    assert qc_clay == pytest.approx(0.20 * 20.0)
    assert fs_sand > 0 and fs_clay > 0
    # Direct measurements always take precedence over correlations.
    direct = SoilLayer(soil_type="SP", n60=20, qc=12.0, cpt_fs=110.0)
    assert _cpt_qc_fs(direct) == pytest.approx((12.0, 110.0))


# ---------------------------------------------------------------------------
# Crack width
# ---------------------------------------------------------------------------


def test_crack_width_decreases_with_more_reinforcement():
    heavy = crack_width_check(
        800.0, 5000.0, 1000.0, 600.0, 520.0, 30.0, 50.0, 16.0, 0.40
    )
    light = crack_width_check(
        800.0, 1500.0, 1000.0, 600.0, 520.0, 30.0, 50.0, 16.0, 0.30
    )
    assert heavy.width < light.width
    assert heavy.ok
    assert not light.ok
    huge = crack_width_check(
        900.0, 400.0, 1000.0, 600.0, 520.0, 30.0, 50.0, 16.0, 0.30
    )
    assert not huge.ok
    assert "Crack width" in huge.note


def test_crack_width_without_steel_is_not_ok():
    result = crack_width_check(
        100.0, 0.0, 1000.0, 600.0, 520.0, 30.0, 50.0, 16.0
    )
    assert not result.ok
    assert result.width > result.limit


# ---------------------------------------------------------------------------
# Shallow-footing buoyancy / uplift
# ---------------------------------------------------------------------------


def test_shallow_uplift_uses_hydrostatic_pressure_and_resistance():
    borehole = Borehole(
        gwt=0.0,
        layers=[SoilLayer(bottom_depth=10.0, soil_type="SP", gamma_sat=20.0)],
    )
    result = check_shallow_uplift(
        borehole, depth=2.0, length=2.0, width=2.0, thickness=0.5,
        P=50.0, uplift_fs=1.10,
    )
    assert result.uplift == pytest.approx(9.81 * 2.0 * 4.0)
    assert result.resistance > result.uplift
    assert result.ok
    # A lightweight footing over a high water table fails the check.
    light = check_shallow_uplift(
        borehole, depth=4.0, length=1.0, width=1.0, thickness=0.20,
        P=1.0, uplift_fs=1.10,
    )
    assert not light.ok
    assert light.fs < 1.10
    assert "Uplift FS" in light.note


def test_shallow_uplift_includes_explicit_buoyancy():
    borehole = Borehole(
        gwt=5.0, layers=[SoilLayer(bottom_depth=10.0, soil_type="SP")]
    )
    dry = check_shallow_uplift(borehole, 1.0, 2.0, 2.0, 0.4, P=100.0)
    wet = check_shallow_uplift(
        borehole, 1.0, 2.0, 2.0, 0.4, P=100.0, buoyancy=150.0
    )
    assert dry.uplift == pytest.approx(0.0)
    assert wet.uplift == pytest.approx(150.0)
    assert wet.fs < dry.fs


# ---------------------------------------------------------------------------
# Downdrag, pile uplift and Broms lateral capacity
# ---------------------------------------------------------------------------


def _soft_profile() -> Borehole:
    return Borehole(
        id="BH-SOFT",
        gwt=2.0,
        layers=[
            SoilLayer(
                bottom_depth=6.0, soil_type="Fill", description="Soft fill",
                gamma=17.0, gamma_sat=18.0, cohesion=10.0,
                n_raw=4, n60=3,
            ),
            SoilLayer(
                bottom_depth=25.0, soil_type="SP", description="Dense sand",
                gamma=19.0, gamma_sat=20.0, friction_angle=36.0,
                n_raw=28, n60=26,
            ),
        ],
    )


def test_downdrag_reduces_allowable_pile_capacity():
    borehole = _soft_profile()
    with_drag = compute_pile_capacity(
        borehole, "Bored", 0.6, 20.0,
        FoundationOptions(pile_design_method="SPT", pile_downdrag_check=True),
    )
    without_drag = compute_pile_capacity(
        borehole, "Bored", 0.6, 20.0,
        FoundationOptions(pile_design_method="SPT", pile_downdrag_check=False),
    )
    assert with_drag.downdrag > 0
    assert without_drag.downdrag == 0.0
    assert with_drag.allowable < without_drag.allowable
    assert with_drag.net_allowable == pytest.approx(with_drag.allowable)
    assert "Downdrag" in with_drag.note


def test_pile_uplift_capacity_uses_skin_friction_and_weight():
    project = sample_project()
    options = FoundationOptions(pile_uplift_fs=2.0)
    capacity = compute_pile_capacity(
        project.boreholes[0], "Bored", 0.6, 20.0, options
    )
    expected = (0.70 * capacity.skin_ultimate + capacity.weight) / 2.0
    assert capacity.uplift_capacity == pytest.approx(expected)
    assert capacity.uplift_capacity > 0


def test_broms_lateral_capacity_increases_with_diameter():
    borehole = _soft_profile()
    ult_small, allow_small = broms_lateral_capacity(
        borehole, 0.6, 20.0, "Bored", fs_lateral=2.5
    )
    ult_large, allow_large = broms_lateral_capacity(
        borehole, 0.9, 20.0, "Bored", fs_lateral=2.5
    )
    assert ult_small > 0
    assert allow_small == pytest.approx(ult_small / 2.5)
    assert ult_large > ult_small
    assert allow_large == pytest.approx(ult_large / 2.5)


def test_pile_group_design_reports_new_checks():
    from bnbc_foundation.core.piles import design_pile_group

    project = sample_project()
    found = design_pile_group(
        project.elements[1], project.boreholes[0], project.options,
        project.materials.f_c, project.materials.f_y,
    )
    assert found is not None
    group, capacity = found
    assert group.downdrag == pytest.approx(capacity.downdrag)
    assert 0.0 <= group.lateral_utilization
    assert 0.0 <= group.pm_utilization
    assert group.uplift_ok and group.lateral_ok and group.pm_ok


# ---------------------------------------------------------------------------
# Pile P-M interaction
# ---------------------------------------------------------------------------


def test_pile_pm_interaction_accepts_moderate_loads():
    result = pile_pm_interaction(0.6, 1000.0, 100.0, 30.0, 420.0)
    assert result.ok
    assert 0.0 < result.utilization <= 1.0
    assert result.phi_Pn > 0 and result.phi_Mn > 0


def test_pile_pm_interaction_rejects_excessive_moment():
    result = pile_pm_interaction(0.6, 1000.0, 5000.0, 30.0, 420.0)
    assert not result.ok
    assert result.utilization > 1.0
    assert "P-M utilization" in result.note


# ---------------------------------------------------------------------------
# Non-rectangular raft outlines
# ---------------------------------------------------------------------------


def test_polygon_pressure_matches_rectangular_solution():
    polygon = rectangle_polygon(-1.0, -1.0, 1.0, 1.0)
    poly = polygon_pressure(1000.0, 100.0, 80.0, polygon)
    rect = pressure_distribution(1000.0, 100.0, 80.0, 2.0, 2.0)
    assert poly.q_avg == pytest.approx(rect.q_avg)
    assert poly.q_max == pytest.approx(rect.q_max)
    assert poly.q_min == pytest.approx(rect.q_min)
    assert poly.kern_ok == rect.kern_ok


def test_custom_raft_outline_uses_polygon_area_and_plate_method():
    project = sample_project()
    outline = [
        [-2.0, -2.0], [11.0, -2.0], [11.0, 4.5],
        [7.0, 4.5], [7.0, 7.0], [-2.0, 7.0],
    ]
    project.options.raft_outline = outline
    project.options.raft_analysis = "Auto"
    points = raft_outline(project.elements, project.options)
    assert len(points) == 6
    area = polygon_area(points)
    analysis = analyze_raft(
        project.elements, project.boreholes[0], 150.0,
        project.options, project.materials,
    )
    assert analysis.method.lower().startswith("plate")
    assert analysis.area == pytest.approx(area)
    assert analysis.outline
    assert "Imported raft outline" in analysis.remarks
    assert analysis.q_service_max >= analysis.q_service_avg >= analysis.q_service_min


def test_winkler_outline_warns_about_approximation():
    project = sample_project()
    project.options.raft_outline = [
        [-2.0, -2.0], [12.0, -2.0], [12.0, 8.0], [-2.0, 8.0],
    ]
    project.options.raft_analysis = "Winkler strips"
    analysis = analyze_raft(
        project.elements, project.boreholes[0], 150.0,
        project.options, project.materials,
    )
    assert "Non-rectangular outline" in analysis.remarks


# ---------------------------------------------------------------------------
# ETABS / SAFE CSV reaction import
# ---------------------------------------------------------------------------


def test_import_reactions_csv_flips_etabs_sign_and_marks_cases(tmp_path):
    project = sample_project()
    path = tmp_path / "reactions.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "Label", "Load Case/Combo", "FZ", "MX", "MY", "FX", "FY",
        ])
        writer.writerow(["C1", "1.4D", -1260.0, 42.0, 35.0, 28.0, 21.0])
        writer.writerow(["C2", "D+W", -800.0, 10.0, 5.0, 300.0, 50.0])
        writer.writerow(["CX", "D", -1.0, 0, 0, 0, 0])

    report = import_reactions_csv(project, path)
    assert report["rows"] == 3
    assert report["elements"] == 2
    assert report["unmatched"] == ["CX"]

    by_id = {e.id: e for e in project.elements}
    c1 = next(r for r in by_id["C1"].reactions if r.case == "1.4D")
    assert c1.P == pytest.approx(1260.0)
    assert c1.Mx == pytest.approx(42.0)
    assert c1.factored
    c2 = next(r for r in by_id["C2"].reactions if r.case == "D+W")
    assert c2.P == pytest.approx(800.0)
    assert c2.Vx == pytest.approx(300.0)
    assert c2.includes_lateral
    assert not c2.factored


def test_import_reactions_csv_scale_and_replace(tmp_path):
    project = sample_project()
    path = tmp_path / "reactions.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Element", "Case", "P (kN)", "Mx (kN.m)", "My (kN.m)"])
        writer.writerow(["C1", "Service", 900.0, 30.0, 25.0])
    before = len(next(e for e in project.elements if e.id == "C1").reactions)
    import_reactions_csv(project, path, replace=True, scale=1.0)
    c1 = next(e for e in project.elements if e.id == "C1")
    assert len(c1.reactions) == 1
    assert c1.reactions[0].P == pytest.approx(900.0)
    assert c1.reactions[0].case == "Service"
    assert before >= 1
