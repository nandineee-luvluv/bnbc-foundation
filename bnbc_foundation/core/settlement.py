"""Settlement calculations for shallow foundations.

Methods are deliberately transparent and use the data normally available in a
Bangladeshi soil report. Missing parameters are correlated from SPT and flagged
by the calling code rather than silently assumed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .models import Borehole, FoundationOptions, SoilLayer
from .soil import soil_modulus, vertical_stress


@dataclass
class SettlementResult:
    immediate: float = 0.0          # mm
    consolidation: float = 0.0      # mm
    secondary: float = 0.0          # mm
    total: float = 0.0              # mm
    limit: float = 0.0              # mm
    ok: bool = True
    note: str = ""


def settlement_limit(options: FoundationOptions, cohesive: bool) -> float:
    return options.settlement_limit_clay if cohesive else options.settlement_limit_sand


def immediate_settlement(
    q_net: float,
    width: float,
    length: float,
    es: float,
    poisson: float = 0.30,
    influence: float = 1.0,
) -> float:
    """Elastic immediate settlement, mm.

    q_net in kPa, width/length in m, Es in kPa. The influence factor defaults to
    1.0 and can be adjusted by the caller.
    """
    if es <= 0 or width <= 0:
        return 0.0
    b = min(width, length)
    s_m = q_net * b * (1.0 - poisson ** 2) * influence / es
    return max(s_m * 1000.0, 0.0)


def consolidation_settlement(
    layer: SoilLayer,
    thickness: float,
    sigma0: float,
    delta_sigma: float,
) -> float:
    """One-dimensional primary consolidation settlement, mm.

    Uses Cc/(1+e0) for normally consolidated soil and Cr for the recompression
    portion when an OCR is supplied. If Cc or e0 are missing, returns zero.
    """
    if layer.cc <= 0 or layer.e0 <= 0 or thickness <= 0 or sigma0 <= 0:
        return 0.0
    sigma_final = sigma0 + max(delta_sigma, 0.0)
    if sigma_final <= sigma0:
        return 0.0
    ocr = max(layer.ocr, 1.0)
    sigma_p = sigma0 * ocr
    cr = layer.cc * 0.10
    if sigma_final <= sigma_p:
        s = (cr / (1.0 + layer.e0)) * thickness * math.log10(sigma_final / sigma0)
    else:
        s_recomp = (cr / (1.0 + layer.e0)) * thickness * math.log10(sigma_p / sigma0)
        s_virgin = (layer.cc / (1.0 + layer.e0)) * thickness * math.log10(sigma_final / sigma_p)
        s = s_recomp + s_virgin
    return max(s * 1000.0, 0.0)


def secondary_settlement(
    layer: SoilLayer,
    thickness: float,
    c_alpha: float = 0.0,
    t1_years: float = 1.0,
    t2_years: float = 50.0,
) -> float:
    """Secondary compression settlement, mm.

    c_alpha is the secondary compression index. If not supplied, 0.02*Cc is used
    for organic/plastic soils and zero otherwise.
    """
    if thickness <= 0 or layer.e0 <= 0:
        return 0.0
    ca = c_alpha if c_alpha > 0 else (0.02 * layer.cc if layer.cc > 0 else 0.0)
    if ca <= 0 or t2_years <= t1_years:
        return 0.0
    s = (ca / (1.0 + layer.e0)) * thickness * math.log10(t2_years / t1_years)
    return max(s * 1000.0, 0.0)


def stress_increase_2to1(q_net: float, width: float, length: float, z: float) -> float:
    """Boussinesq/2:1 approximate vertical stress increase at depth z, kPa."""
    if z < 0:
        return 0.0
    return q_net * (width * length) / ((width + z) * (length + z))


def estimate_shallow_settlement(
    borehole: Borehole,
    depth: float,
    width: float,
    length: float,
    q_net: float,
    options: FoundationOptions,
    influence_depth_factor: float = 2.0,
) -> SettlementResult:
    """Estimate immediate + consolidation settlement below a footing base."""
    layers = borehole.sorted_layers()
    top = depth
    bottom_limit = depth + influence_depth_factor * max(width, length)
    immediate = 0.0
    consolidation = 0.0
    secondary = 0.0
    cohesive = False
    current = 0.0
    for layer in layers:
        l_top = max(current, top)
        l_bottom = min(layer.bottom_depth, bottom_limit)
        current = layer.bottom_depth
        if l_bottom <= l_top:
            continue
        mid = 0.5 * (l_top + l_bottom)
        sigma0, _, sigma0_eff = vertical_stress(borehole, mid)
        ds = stress_increase_2to1(q_net, width, length, mid - depth)
        es = soil_modulus(borehole, layer, l_top)
        immediate += immediate_settlement(q_net, width, length, es) * (l_bottom - l_top) / max(
            influence_depth_factor * max(width, length), 1e-6
        )
        if layer.is_cohesive():
            cohesive = True
            consolidation += consolidation_settlement(layer, l_bottom - l_top, sigma0_eff, ds)
            secondary += secondary_settlement(layer, l_bottom - l_top)

    total = immediate + consolidation + secondary
    limit = settlement_limit(options, cohesive)
    return SettlementResult(
        immediate=immediate,
        consolidation=consolidation,
        secondary=secondary,
        total=total,
        limit=limit,
        ok=total <= limit + 1e-6,
        note="" if total <= limit + 1e-6 else f"Total settlement {total:.1f} mm exceeds {limit:.1f} mm",
    )


def angular_distortion(settlement_a: float, settlement_b: float, spacing: float) -> float:
    if spacing <= 0:
        return 0.0
    return abs(settlement_a - settlement_b) / (spacing * 1000.0)


def differential_ok(settlement_a: float, settlement_b: float, spacing: float,
                    options: FoundationOptions) -> tuple[bool, str]:
    diff = abs(settlement_a - settlement_b)
    distortion = angular_distortion(settlement_a, settlement_b, spacing)
    ok = diff <= options.differential_limit + 1e-6 and distortion <= options.angular_limit + 1e-9
    note = ""
    if diff > options.differential_limit:
        note = f"Differential settlement {diff:.1f} mm > {options.differential_limit:.1f} mm"
    elif distortion > options.angular_limit:
        note = f"Angular distortion 1/{1/max(distortion,1e-9):.0f} exceeds 1/{1/options.angular_limit:.0f}"
    return ok, note
