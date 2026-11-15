"""Pile capacity and group checks."""

import math

import pytest

from bnbc_foundation.core.models import FoundationOptions, sample_project
from bnbc_foundation.core.piles import compute_pile_capacity, design_pile_group
from bnbc_foundation.core.structural.pilecap import _strut_and_tie


def test_spt_pile_capacity():
    p = sample_project()
    bh = p.boreholes[0]
    cap = compute_pile_capacity(bh, "Bored", 0.6, 25.0, p.options)
    assert cap.ultimate > 0
    assert cap.allowable > 0
    assert cap.allowable <= cap.structural_capacity + 1e-9
    assert cap.fs >= 3.5
    assert cap.end_ultimate > 0


def test_direct_capacity_override():
    p = sample_project()
    cap = compute_pile_capacity(
        p.boreholes[0], "Bored", 0.6, 25.0, p.options, direct_capacity=900.0
    )
    assert cap.allowable_geotech == 900.0 or cap.allowable == 900.0
    assert "Direct allowable capacity" in cap.note


def test_pile_group_design():
    p = sample_project()
    e = p.elements[1]  # C2, 1800 kN
    found = design_pile_group(e, p.boreholes[0], p.options, p.materials.f_c, p.materials.f_y)
    assert found is not None
    group, pile = found
    assert group.count >= 1
    assert group.cap_length >= group.diameter
    assert group.cap_width >= group.diameter
    assert group.positions
    assert group.max_pile_load > 0
    assert group.block_capacity > 0
    assert group.utilization > 0


def test_pilecap_strut_and_tie_matches_worked_example():
    """Worked strut-and-tie check for a four-pile cap.

    Pile centres are at +/-1.0 m, the column is 0.6 x 0.6 m and the effective
    depth is 800 mm.  The governing pile at (-1.0, -1.0) has a 800 kN reaction,
    so the lever arm from the column face is sqrt(0.7^2 + 0.7^2) = 0.98995 m.
    """
    angle, force, capacity, tie_as = _strut_and_tie(
        positions=[(-1.0, -1.0), (1.0, -1.0), (-1.0, 1.0), (1.0, 1.0)],
        reactions=[800.0, 600.0, 600.0, 400.0],
        column_length=0.60,
        column_width=0.60,
        d_mm=800.0,
        f_c=28.0,
        f_y=420.0,
        phi_st=0.75,
    )
    assert angle == pytest.approx(38.9424, abs=1e-4)
    assert force == pytest.approx(1272.79, rel=1e-5)
    # phi * 0.60 f'c * strut width * effective depth
    assert capacity == pytest.approx(6048.0, rel=1e-9)
    assert tie_as == pytest.approx(3142.70, rel=1e-5)


def test_pilecap_strut_and_tie_has_geometry_limits():
    # A pile inside the column face gives no diagonal strut; report zero force.
    assert _strut_and_tie(
        [(0.10, 0.10)], [500.0], 0.60, 0.60, 800.0, 28.0, 420.0
    ) == (90.0, 0.0, 0.0, 0.0)
    # Missing geometry and reactions are also guarded.
    assert _strut_and_tie([], [], 0.60, 0.60, 800.0, 28.0, 420.0) == (
        0.0, 0.0, 0.0, 0.0
    )
