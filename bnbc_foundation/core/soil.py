"""Soil mechanics helpers, SPT correlations and shallow bearing capacity."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Borehole, SoilLayer
from .units import clamp

GAMMA_W = 9.81  # kN/m3


# ---------------------------------------------------------------------------
# Stress and SPT
# ---------------------------------------------------------------------------


def vertical_stress(borehole: Borehole, z: float) -> tuple[float, float, float]:
    """Return total vertical stress, pore pressure and effective stress at depth z.

    Depths and stresses are in m and kPa. The water table is measured from the
    ground surface. Layers are integrated using bulk unit weight above the water
    table and saturated unit weight below it.
    """
    if z <= 0:
        return 0.0, 0.0, 0.0
    layers = borehole.sorted_layers()
    sigma = 0.0
    top = 0.0
    gwt = max(borehole.gwt, 0.0)
    for layer in layers:
        bottom = min(layer.bottom_depth, z)
        if bottom <= top:
            continue
        # Split the layer at the water table.
        segments = [(top, bottom)]
        if top < gwt < bottom:
            segments = [(top, gwt), (gwt, bottom)]
        for a, b in segments:
            if b <= a:
                continue
            if a >= gwt:
                gamma = layer.gamma_sat or layer.gamma
            elif b <= gwt:
                gamma = layer.gamma
            else:
                gamma = layer.gamma
            sigma += gamma * (b - a)
        top = layer.bottom_depth
        if top >= z:
            break
    if z > top:
        # Extrapolate the last layer.
        layer = layers[-1] if layers else SoilLayer()
        gamma = layer.gamma_sat if z > gwt else layer.gamma
        sigma += gamma * (z - top)
    u = GAMMA_W * max(0.0, z - gwt)
    return sigma, u, max(sigma - u, 0.0)


def spt_overburden_correction(sigma_v_eff: float) -> float:
    if sigma_v_eff <= 0:
        return 1.0
    return clamp(math.sqrt(100.0 / sigma_v_eff), 0.5, 1.7)


def corrected_n60(n_raw: float, sigma_v_eff: float, energy_ratio: float = 60.0) -> float:
    """Correct a raw SPT blow count to N60.

    energy_ratio is the hammer energy in percent (60 for the standard N60).
    """
    return max(0.0, n_raw) * (energy_ratio / 60.0) * spt_overburden_correction(sigma_v_eff)


def layer_n60(borehole: Borehole, layer: SoilLayer, top: float) -> float:
    if layer.n60 and layer.n60 > 0:
        return layer.n60
    mid = max(top + 0.01, (top + layer.bottom_depth) / 2.0)
    _, _, sigma_eff = vertical_stress(borehole, mid)
    return corrected_n60(layer.n_raw, sigma_eff)


def phi_from_spt(n60: float) -> float:
    """Peck/Hanson correlation, capped for practical foundation design."""
    return clamp(27.0 + 0.30 * max(n60, 0.0), 26.0, 45.0)


def cu_from_spt(n60: float) -> float:
    """Terzaghi-Peck style undrained strength correlation, kPa."""
    return max(0.0, 5.85 * n60)


def es_from_spt(n60: float, cohesive: bool = False) -> float:
    n60 = max(n60, 0.0)
    if cohesive:
        return max(3000.0, 500.0 * max(cu_from_spt(n60), 5.0))
    return max(2000.0, 1000.0 * n60)


def k_from_spt(n60: float, cohesive: bool = False) -> float:
    """Indicative modulus of subgrade reaction, kN/m3 (BNBC Tables 6.3.9a/b)."""
    if cohesive:
        cu = max(cu_from_spt(n60), 25.0)
        if cu <= 100:
            return 27000.0
        if cu <= 200:
            return 40500.0
        return 81000.0
    if n60 < 10:
        return 15000.0
    if n60 < 30:
        return 15000.0 + (n60 - 10.0) / 20.0 * 32000.0
    return 47000.0 + min((n60 - 30.0) / 20.0, 1.0) * 133000.0


def soil_modulus(borehole: Borehole, layer: SoilLayer, top: float) -> float:
    if layer.es and layer.es > 0:
        return layer.es
    n60 = layer_n60(borehole, layer, top)
    return es_from_spt(n60, layer.is_cohesive())


def subgrade_modulus(borehole: Borehole, layer: SoilLayer, top: float) -> float:
    if layer.k_subgrade and layer.k_subgrade > 0:
        return layer.k_subgrade
    n60 = layer_n60(borehole, layer, top)
    return k_from_spt(n60, layer.is_cohesive())


# ---------------------------------------------------------------------------
# Bearing capacity
# ---------------------------------------------------------------------------


def bearing_capacity_factors(phi_deg: float) -> tuple[float, float, float]:
    phi = math.radians(clamp(phi_deg, 0.0, 50.0))
    if phi < 1e-6:
        return 5.14, 1.0, 0.0
    nq = math.exp(math.pi * math.tan(phi)) * math.tan(math.pi / 4.0 + phi / 2.0) ** 2
    nc = (nq - 1.0) / math.tan(phi)
    ng = 2.0 * (nq + 1.0) * math.tan(phi)
    return nc, nq, ng


def _mean_unit_weight(borehole: Borehole, top: float, bottom: float, gwt: float) -> float:
    """Average total unit weight between two depths."""
    if bottom <= top:
        return 18.0
    layers = borehole.sorted_layers()
    total = 0.0
    length = 0.0
    current = 0.0
    for layer in layers:
        a = max(top, current)
        b = min(bottom, layer.bottom_depth)
        if b > a:
            total += layer.gamma * (b - a)
            length += b - a
        current = layer.bottom_depth
        if current >= bottom:
            break
    return total / length if length > 0 else 18.0


def ultimate_bearing_capacity(
    borehole: Borehole,
    depth: float,
    width: float,
    length: float,
    cohesion: float | None = None,
    phi_deg: float | None = None,
    gamma: float | None = None,
) -> float:
    """Gross ultimate bearing capacity by the Meyerhof method, kPa.

    The soil properties are taken from the layer at the foundation base unless
    explicit values are supplied. Water-table effects are included.
    """
    layer = borehole.layer_at_depth(depth)
    if layer is None:
        return 0.0
    c = layer.cohesion if cohesion is None else cohesion
    phi = layer.friction_angle if phi_deg is None else phi_deg
    if layer.is_cohesive() and c <= 0 and layer.cu > 0:
        c = layer.cu
        phi = 0.0
    if not layer.is_cohesive() and phi <= 0:
        n60 = layer.effective_n60()
        phi = phi_from_spt(n60)
    if gamma is None:
        gamma = _mean_unit_weight(borehole, max(depth - width, 0.0), depth + width, borehole.gwt)

    nc, nq, ng = bearing_capacity_factors(phi)
    b = max(width, 0.1)
    l = max(length, b)
    d = max(depth, 0.0)

    # Shape factors (Meyerhof).
    sc = 1.0 + 0.2 * (b / l)
    sq = 1.0 + 0.1 * (b / l)
    sg = 1.0 - 0.1 * (b / l)

    # Depth factors.
    phi_rad = math.radians(clamp(phi, 0.0, 50.0))
    tan_term = math.tan(math.pi / 4.0 + phi_rad / 2.0)
    dc = 1.0 + 0.2 * (d / b) * tan_term
    dq = dg = 1.0 + 0.1 * (d / b) * tan_term
    dc = min(dc, 1.5)
    dq = dg = min(dq, 1.5)

    # Effective surcharge at base and effective unit weight in the wedge.
    sigma_v, u, sigma_eff = vertical_stress(borehole, d)
    q = sigma_eff
    if d > borehole.gwt:
        gamma_wedge = max(gamma - GAMMA_W, 1.0)
    else:
        gamma_wedge = gamma

    q_ult = (
        c * nc * sc * dc
        + q * nq * sq * dq
        + 0.5 * gamma_wedge * b * ng * sg * dg
    )
    return max(q_ult, 0.0)


def allowable_bearing_pressure(
    borehole: Borehole,
    depth: float,
    width: float,
    length: float,
    fs: float = 2.5,
    direct_value: float | None = None,
) -> float:
    """Net allowable bearing pressure, kPa.

    If a direct report value is available at the founding layer it overrides the
    computed value.
    """
    if direct_value is not None and direct_value > 0:
        return direct_value
    layer = borehole.layer_at_depth(depth)
    if layer is not None and layer.allowable_bearing and layer.allowable_bearing > 0:
        return layer.allowable_bearing
    q_ult = ultimate_bearing_capacity(borehole, depth, width, length)
    _, _, sigma_eff = vertical_stress(borehole, depth)
    q_net = max(q_ult - sigma_eff, 0.0)
    return q_net / max(fs, 1.0)


def bearing_from_spt(borehole: Borehole, depth: float, width: float, fs: float = 2.5) -> float:
    """SPT-based net allowable pressure for preliminary sizing, kPa."""
    layer = borehole.layer_at_depth(depth)
    if layer is None:
        return 0.0
    n60 = layer.effective_n60()
    if layer.is_cohesive():
        cu = layer.cu if layer.cu > 0 else cu_from_spt(n60)
        q_ult = 5.14 * cu
    else:
        phi = layer.friction_angle if layer.friction_angle > 0 else phi_from_spt(n60)
        q_ult = ultimate_bearing_capacity(borehole, depth, width, width, phi_deg=phi)
        return max(q_ult * 0.5, 0.0) / max(fs, 1.0)
    return q_ult / max(fs, 1.0)


def presumptive_bearing(soil_type: str) -> float:
    """BNBC Table 6.3.7 presumptive values, kPa (light structures)."""
    s = soil_type.lower()
    if "rock" in s or "shale" in s:
        return 440.0
    if any(k in s for k in ("gw", "gp", "gm", "gc", "gravel")):
        return 400.0
    if any(k in s for k in ("sw", "sp", "sm", "sc", "sand")):
        return 200.0
    if "silt" in s or "ml" in s or "mh" in s:
        return 150.0
    if any(k in s for k in ("cl", "ch", "clay")):
        return 150.0
    return 100.0


# ---------------------------------------------------------------------------
# Liquefaction (simplified SPT procedure)
# ---------------------------------------------------------------------------


def cyclic_stress_ratio(pga_g: float, depth: float, sigma_v: float, sigma_eff: float) -> float:
    if sigma_eff <= 0:
        return 0.0
    rd = clamp(1.0 - 0.015 * depth, 0.5, 1.0)
    return 0.65 * pga_g * (sigma_v / sigma_eff) * rd


def cyclic_resistance_ratio(n60: float, fines_percent: float = 0.0) -> float:
    """Youd et al. (2001) SPT-based CRR for clean sand, with a fines adjustment."""
    n160 = clamp(n60, 0.0, 60.0)
    if n160 <= 0:
        return 0.0
    # The published SPT CRR curve is defined up to N1,60 of about 30.  Dense
    # soils above that range are treated as non-liquefiable; extrapolating the
    # polynomial would wrongly reduce CRR again at high blow counts.
    if n160 >= 30.0:
        return 1.0
    crr = (
        1.0 / (34.0 - n160)
        + n160 / 135.0
        + 50.0 / (10.0 * n160 + 45.0) ** 2
        - 1.0 / 200.0
    )
    # Increase resistance with fines content (simplified, capped).
    if fines_percent > 5.0:
        crr *= 1.0 + min((fines_percent - 5.0) / 100.0, 0.35)
    return max(crr, 0.0)


def liquefaction_fs(n60: float, depth: float, sigma_v: float, sigma_eff: float,
                   pga_g: float, fines_percent: float = 0.0) -> float:
    csr = cyclic_stress_ratio(pga_g, depth, sigma_v, sigma_eff)
    crr = cyclic_resistance_ratio(n60, fines_percent)
    return crr / csr if csr > 0 else 999.0


@dataclass
class LiquefactionResult:
    """Simplified SPT liquefaction check for one saturated soil layer."""

    borehole_id: str = ""
    layer_index: int = 0
    top: float = 0.0
    bottom: float = 0.0
    mid: float = 0.0
    soil_type: str = ""
    n60: float = 0.0
    fs: float = 999.0
    triggered: bool = False


def liquefaction_susceptible_layers(
    borehole: Borehole,
) -> list[tuple[int, SoilLayer, float, float]]:
    """Return saturated, non-cohesive layers that require a liquefaction check.

    Each item is ``(layer_index, layer, top_depth, mid_depth)``. Ground above
    the water table and cohesive/rock layers are excluded.
    """
    out: list[tuple[int, SoilLayer, float, float]] = []
    top = 0.0
    for index, layer in enumerate(borehole.sorted_layers()):
        bottom = layer.bottom_depth
        mid = 0.5 * (top + bottom)
        name = layer.soil_type.lower()
        if (
            mid > borehole.gwt + 1e-9
            and not layer.is_cohesive()
            and "rock" not in name
            and "shale" not in name
        ):
            out.append((index, layer, top, mid))
        top = bottom
    return out


def liquefaction_assessment(
    borehole: Borehole, pga_g: float
) -> list[LiquefactionResult]:
    """Run the simplified SPT liquefaction trigger for a borehole.

    A factor of safety below 1.0 indicates a liquefaction trigger. The check is
    deliberately screening-level and must be verified with project-specific
    cyclic testing and site response analysis.
    """
    if pga_g <= 0:
        return []
    results: list[LiquefactionResult] = []
    for index, layer, top, mid in liquefaction_susceptible_layers(borehole):
        sigma_v, _, sigma_eff = vertical_stress(borehole, mid)
        n60 = layer_n60(borehole, layer, top)
        fs = (
            liquefaction_fs(
                n60, mid, sigma_v, sigma_eff, pga_g, layer.fines
            )
            if n60 > 0
            else 0.0
        )
        results.append(
            LiquefactionResult(
                borehole_id=borehole.id,
                layer_index=index,
                top=top,
                bottom=layer.bottom_depth,
                mid=mid,
                soil_type=layer.soil_type,
                n60=n60,
                fs=fs,
                triggered=n60 > 0 and fs < 1.0,
            )
        )
    return results
