"""Soil stress, SPT and bearing-capacity checks."""

import math

import pytest

from bnbc_foundation.core.models import Borehole, SoilLayer
from bnbc_foundation.core.soil import (
    allowable_bearing_pressure,
    corrected_n60,
    liquefaction_assessment,
    liquefaction_fs,
    presumptive_bearing,
    spt_overburden_correction,
    ultimate_bearing_capacity,
    vertical_stress,
)
from bnbc_foundation.core.units import clamp


def simple_borehole():
    return Borehole(id="BH", gwt=2.0, layers=[
        SoilLayer(bottom_depth=10.0, soil_type="SM", gamma=18.0, gamma_sat=20.0,
                  friction_angle=32.0, n_raw=20, n60=18, es=20000.0),
    ])


def test_vertical_stress_with_water_table():
    bh = simple_borehole()
    sigma, u, eff = vertical_stress(bh, 5.0)
    assert sigma == pytest.approx(18.0 * 2.0 + 20.0 * 3.0)
    assert u == pytest.approx(9.81 * 3.0)
    assert eff == pytest.approx(sigma - u)
    assert eff > 0


def test_spt_correction_bounds():
    assert spt_overburden_correction(100.0) == pytest.approx(1.0)
    assert spt_overburden_correction(10.0) == pytest.approx(1.7)
    assert spt_overburden_correction(1000.0) == pytest.approx(0.5)
    assert corrected_n60(20.0, 100.0) == pytest.approx(20.0)
    assert corrected_n60(-4.0, 100.0) == 0.0


def test_bearing_capacity_positive_and_depth_effect():
    bh = simple_borehole()
    q1 = ultimate_bearing_capacity(bh, 2.0, 2.0, 2.0)
    q2 = ultimate_bearing_capacity(bh, 5.0, 2.0, 2.0)
    assert q1 > 0 and q2 > q1
    qa = allowable_bearing_pressure(bh, 2.0, 2.0, 2.0, fs=2.5)
    assert qa == pytest.approx(q1 / 2.5 - vertical_stress(bh, 2.0)[2] / 2.5, rel=1e-9)


def test_direct_allowable_override():
    bh = simple_borehole()
    bh.layers[0].allowable_bearing = 240.0
    assert allowable_bearing_pressure(bh, 2.0, 2.0, 2.0) == 240.0
    assert allowable_bearing_pressure(bh, 2.0, 2.0, 2.0, direct_value=300.0) == 300.0


def test_presumptive_values():
    assert presumptive_bearing("Sand") == 200.0
    assert presumptive_bearing("CL") == 150.0
    assert presumptive_bearing("Rock") == 440.0


def test_liquefaction_assessment_flags_loose_saturated_sand():
    bh = Borehole(id="BH", gwt=1.0, layers=[
        SoilLayer(
            bottom_depth=3.0, soil_type="SM", gamma=18.0, gamma_sat=19.0,
            n_raw=6, n60=5, fines=10.0,
        ),
        SoilLayer(
            bottom_depth=8.0, soil_type="CL", gamma=18.0, gamma_sat=19.0,
            cu=50.0, n_raw=8, n60=7, fines=70.0,
        ),
    ])
    results = liquefaction_assessment(bh, 0.30)
    assert len(results) == 1
    assert results[0].borehole_id == "BH"
    assert results[0].soil_type == "SM"
    assert results[0].top == pytest.approx(0.0)
    assert results[0].bottom == pytest.approx(3.0)
    assert results[0].n60 == pytest.approx(5.0)
    assert results[0].fs < 1.0
    assert results[0].triggered

    # The same profile at a higher blow count should not trigger.
    bh.layers[0].n60 = 40.0
    assert not liquefaction_assessment(bh, 0.30)[0].triggered
    # No PGA means no screening result, rather than a silent pass.
    assert liquefaction_assessment(bh, 0.0) == []
