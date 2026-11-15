"""Bearing pressure and structural-concrete checks."""

import math

import pytest

from bnbc_foundation.core.bearing import pressure_distribution
from bnbc_foundation.core.structural.concrete import (
    flexural_design,
    one_way_shear_capacity,
    punching_shear_capacity,
    select_bars,
)


def test_pressure_centre_load():
    p = pressure_distribution(1000.0, 0.0, 0.0, 2.0, 2.0)
    assert p.q_avg == pytest.approx(250.0)
    assert p.q_max == pytest.approx(250.0)
    assert p.q_min == pytest.approx(250.0)
    assert p.kern_ok


def test_pressure_biaxial_eccentricity():
    p = pressure_distribution(1000.0, 100.0, 80.0, 2.0, 2.0)
    assert p.e_x == pytest.approx(0.08)
    assert p.e_y == pytest.approx(0.10)
    assert p.q_max > p.q_avg > p.q_min
    assert p.kern_ok
    assert p.q_min > 0


def test_pressure_outside_kern():
    p = pressure_distribution(100.0, 0.0, 80.0, 2.0, 2.0)
    assert not p.kern_ok
    assert p.e_x > 2.0 / 6.0


def test_flexural_design_meets_moment():
    result = flexural_design(250.0, 1000.0, 500.0, 600.0, 30.0, 420.0)
    assert result.As_req >= result.As_min
    assert result.phi_Mn >= 250.0 - 1e-6
    assert result.ok


def test_bar_selection_provides_steel():
    layout = select_bars(1200.0, [12, 16, 20, 25], max_spacing=300, min_spacing=100)
    assert layout.ok
    assert layout.As_provided >= 1200.0
    assert 100.0 <= layout.spacing <= 300.0


def test_shear_and_punching_capacities():
    v = one_way_shear_capacity(1000.0, 400.0, 30.0)
    p_square = punching_shear_capacity(2400.0, 400.0, 30.0, beta=1.0)
    p_long = punching_shear_capacity(2400.0, 400.0, 30.0, beta=2.0)
    assert v > 0
    assert p_square > 0
    assert p_long <= p_square + 1e-9
