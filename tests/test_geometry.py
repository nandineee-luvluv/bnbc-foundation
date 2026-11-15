"""Plan geometry, column offsets, wall orientation and footprint checks."""

import math

import pytest

from bnbc_foundation.core.geometry import (
    point_in_polygon,
    polygon_area,
    polygon_within_rect,
    polygons_overlap,
    rotated_rectangle_polygon,
    segment_rectangle_polygon,
)
from bnbc_foundation.core.models import Element, Reaction, sample_project
from bnbc_foundation.core.loads import governing_factored
from bnbc_foundation.core.piles import design_pile_group
from bnbc_foundation.core.selector import _q_allow_pair
from bnbc_foundation.core.structural.concrete import punching_geometry
from bnbc_foundation.core.structural.footing import (
    design_combined,
    design_isolated,
    design_strip,
)
from bnbc_foundation.core.structural.pilecap import design_pilecap


def test_column_offset_transforms_reaction_to_centre():
    element = Element(
        "C1", "column", 1.0, 2.0, length=0.40, width=0.60, dx=0.20, dy=-0.30
    )
    reaction = Reaction("Service", 1000.0, 50.0, 40.0)

    assert element.center == pytest.approx((1.20, 1.70))
    centred = element.reaction_at_center(reaction)
    assert centred.P == pytest.approx(1000.0)
    assert centred.Mx == pytest.approx(50.0 - 1000.0 * -0.30)
    assert centred.My == pytest.approx(40.0 - 1000.0 * 0.20)
    # The stored reaction is not mutated.
    assert reaction.Mx == pytest.approx(50.0)
    assert reaction.My == pytest.approx(40.0)


def test_column_without_offset_keeps_reaction():
    element = Element("C1", "column", 1.0, 2.0, length=0.5, width=0.5)
    reaction = Reaction("Service", 700.0, 12.0, -8.0)
    assert element.reaction_at_center(reaction) == reaction


def test_circular_column_footprint_and_section():
    element = Element(
        "C2", "column", 6.0, 0.0, length=0.60, width=0.60,
        shape="Circular", diameter=0.60,
    )
    assert element.is_circular
    assert element.section_length == pytest.approx(0.60)
    assert element.section_width == pytest.approx(0.60)
    assert element.footprint_area == pytest.approx(math.pi * 0.60 ** 2 / 4.0)
    polygon = element.footprint_polygon
    assert len(polygon) >= 8
    assert polygon_area(polygon) == pytest.approx(
        math.pi * 0.60 ** 2 / 4.0, rel=0.01
    )


def test_circular_punching_geometry_uses_round_perimeter():
    b0, area, beta = punching_geometry(600.0, 600.0, 400.0, circular=True)
    assert b0 == pytest.approx(math.pi * 1000.0)
    assert area == pytest.approx(math.pi * 1000.0 ** 2 / 4.0)
    assert beta == pytest.approx(1.0)

    rect_b0, rect_area, rect_beta = punching_geometry(600.0, 400.0, 400.0)
    assert rect_b0 == pytest.approx(2.0 * (1000.0 + 800.0))
    assert rect_area == pytest.approx(1000.0 * 800.0)
    assert rect_beta == pytest.approx(1.5)


def test_circular_isolated_footing_reports_circular_punching():
    project = sample_project()
    circular = next(e for e in project.elements if e.id == "C2")
    design = design_isolated(
        circular, project.boreholes[0], 300.0, project.options, project.materials
    )
    shear = design.details["shear"]
    assert shear["circular"] is True
    assert shear["b0_mm"] == pytest.approx(
        math.pi * (circular.section_length * 1000.0 + shear["d_mm"])
    )


def test_wall_endpoints_angle_and_local_moments():
    wall = Element(
        "W1", "wall", 0.0, 0.0, length=5.0, wall_thickness=0.25,
        x1=0.0, y1=0.0, x2=3.0, y2=4.0,
    )
    assert wall.has_wall_endpoints()
    assert wall.wall_length == pytest.approx(5.0)
    angle = math.degrees(math.atan2(4.0, 3.0))
    assert wall.wall_angle_deg == pytest.approx(angle)
    assert wall.center == pytest.approx((1.5, 2.0))

    reaction = Reaction("Service", 1000.0, 30.0, 40.0)
    m_along, m_normal = wall.wall_local_moments(reaction)
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    assert m_along == pytest.approx(30.0 * ca + 40.0 * sa)
    assert m_normal == pytest.approx(40.0 * ca - 30.0 * sa)
    local = wall.wall_local_reaction(reaction)
    assert local.Mx == pytest.approx(m_along)
    assert local.My == pytest.approx(m_normal)


def test_legacy_wall_falls_back_to_centre_and_length():
    wall = Element(
        "W2", "wall", 6.0, 3.5, 0.0, 6.0, 0.25, wall_thickness=0.25
    )
    assert not wall.has_wall_endpoints()
    assert wall.wall_endpoints == pytest.approx((3.0, 3.5, 9.0, 3.5))
    assert wall.wall_length == pytest.approx(6.0)
    assert wall.wall_angle_deg == pytest.approx(0.0)
    polygon = wall.footprint_polygon
    assert len(polygon) == 4
    assert segment_rectangle_polygon(3.0, 3.5, 9.0, 3.5, 0.25) == polygon


def test_rotated_footprints_clash_and_site_containment():
    first = rotated_rectangle_polygon(0.0, 0.0, 4.0, 1.0, 45.0)
    second = rotated_rectangle_polygon(0.0, 2.0, 4.0, 1.0, 45.0)
    assert not polygons_overlap(first, second, clearance=0.10)
    assert polygons_overlap(first, second, clearance=0.50)

    inner = rotated_rectangle_polygon(0.5, 0.5, 0.60, 0.60, 30.0)
    assert polygon_within_rect(inner, (0.0, 0.0, 1.0, 1.0))
    outer = rotated_rectangle_polygon(0.5, 0.5, 1.40, 0.20, 45.0)
    assert not polygon_within_rect(outer, (0.0, 0.0, 1.0, 1.0))


def test_wall_pile_group_and_cap_follow_wall_orientation():
    project = sample_project()
    wall = next(e for e in project.elements if e.id == "W1")
    result = design_pile_group(
        wall, project.boreholes[0], project.options,
        project.materials.f_c, project.materials.f_y,
    )
    assert result is not None
    group, _ = result
    assert group.angle_deg == pytest.approx(wall.wall_angle_deg)
    assert group.cap_length >= wall.wall_length

    cap = design_pilecap(wall, group, project.materials, project.options)
    assert cap.angle_deg == pytest.approx(wall.wall_angle_deg)
    assert cap.center_x == pytest.approx(wall.center_x)
    assert cap.center_y == pytest.approx(wall.center_y)


def test_combined_footing_uses_centres_and_covers_offset_columns():
    project = sample_project()
    first = Element(
        "C1", "column", 0.0, 0.0, 0.0, 0.45, 0.45,
        reactions=[Reaction("Service", 600.0, 20.0, 10.0)],
        dx=0.20, dy=0.10,
    )
    second = Element(
        "C2", "column", 3.0, 2.0, 0.0, 0.45, 0.45,
        reactions=[Reaction("Service", 700.0, 25.0, 15.0)],
        dx=-0.10, dy=-0.10,
    )
    q_allow, _ = _q_allow_pair([first, second], project.boreholes[0], project.options)
    design = design_combined(
        [first, second], project.boreholes[0], q_allow,
        project.options, project.materials,
    )

    total = 600.0 + 700.0
    expected_x = (600.0 * first.center_x + 700.0 * second.center_x) / total
    expected_y = (600.0 * first.center_y + 700.0 * second.center_y) / total
    assert design.center_x == pytest.approx(expected_x)
    assert design.center_y == pytest.approx(expected_y)
    assert design.status in ("OK", "CHECK")

    footprint = rotated_rectangle_polygon(
        design.center_x, design.center_y, design.length, design.width,
        design.angle_deg,
    )
    for element in (first, second):
        assert point_in_polygon(element.center, footprint)
        for corner in element.footprint_polygon:
            assert point_in_polygon(corner, footprint)

    # Transverse steel is governed by the projection beyond the column face in
    # the width direction, not by the longitudinal projection.
    b = (design.width * 1000.0 - second.section_width * 1000.0) / 2.0
    expected_mu = design.details["shear"]["q_u"] * (b / 1000.0) ** 2 / 2.0
    assert design.Mu_y == pytest.approx(expected_mu)
    assert design.sliding_fs > 0
    assert design.overturning_fs > 0
    assert "stability" in design.details


def test_combined_footing_moment_envelope_matches_closed_form():
    project = sample_project()
    first = Element(
        "A", "column", 0.0, 0.0, 0.0, 0.45, 0.45,
        reactions=[Reaction("Service", 600.0, 0.0, 0.0)],
    )
    second = Element(
        "B", "column", 3.0, 0.0, 0.0, 0.45, 0.45,
        reactions=[Reaction("Service", 600.0, 0.0, 0.0)],
    )
    q_allow, _ = _q_allow_pair([first, second], project.boreholes[0], project.options)
    design = design_combined(
        [first, second], project.boreholes[0], q_allow,
        project.options, project.materials,
    )

    # Closed-form free-free beam: uniform net upward line load w, equal point
    # loads P over an overhang a.  The hogging moment at the column is w*a^2/2
    # and the sagging peak is that value plus the area of the shear triangle.
    w = design.details["beam_net_pressure"] * design.width
    a = first.center_x - design.origin_x
    p = governing_factored(first).P
    left_moment = -0.5 * w * a ** 2
    expected_pos = left_moment + max(p - w * a, 0.0) ** 2 / (2.0 * w)

    m_pos, m_neg = design.details["moment_envelope"]
    assert m_pos == pytest.approx(expected_pos, rel=1e-9)
    assert m_neg == pytest.approx(left_moment, rel=1e-9)
    expected_q = (governing_factored(first).P + governing_factored(second).P) / (
        design.length * design.width
    )
    assert design.details["beam_net_pressure"] == pytest.approx(expected_q)


def test_strip_footing_includes_stability_checks():
    project = sample_project()
    wall = next(e for e in project.elements if e.id == "W1")
    design = design_strip(
        wall, project.boreholes[0], 250.0,
        project.options, project.materials,
    )
    assert design.length == pytest.approx(wall.wall_length)
    assert design.angle_deg == pytest.approx(wall.wall_angle_deg)
    assert design.sliding_fs > 0
    assert design.overturning_fs > 0
    assert "stability" in design.details
