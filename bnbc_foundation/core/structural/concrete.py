"""Reinforced-concrete design helpers per BNBC 2020 Part 6, Chapters 6 and 8."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..units import clamp


@dataclass
class FlexureResult:
    As_req: float = 0.0          # mm2 per metre width
    As_min: float = 0.0
    rho: float = 0.0
    a: float = 0.0               # mm
    phi_Mn: float = 0.0          # kN.m per metre
    ok: bool = True
    note: str = ""


@dataclass
class BarLayout:
    diameter: float = 16.0       # mm
    spacing: float = 200.0       # mm
    As_provided: float = 0.0     # mm2 per metre
    count_per_metre: float = 5.0
    ok: bool = True
    note: str = ""


def beta1(f_c: float) -> float:
    if f_c <= 28.0:
        return 0.85
    return clamp(0.85 - 0.05 * (f_c - 28.0) / 7.0, 0.65, 0.85)


def min_flexural_steel(b_mm: float, h_mm: float, f_c: float, f_y: float,
                       slab_like: bool = True) -> float:
    """Minimum reinforcement, mm2, for a section."""
    if slab_like:
        return max(0.0018 * b_mm * h_mm, 0.0)
    return max(0.25 * math.sqrt(f_c) / f_y, 1.4 / f_y) * b_mm * max(h_mm - 50.0, 1.0)


def flexural_design(
    Mu_kNm_per_m: float,
    b_mm: float,
    d_mm: float,
    h_mm: float,
    f_c: float,
    f_y: float,
    phi: float = 0.90,
    slab_like: bool = True,
) -> FlexureResult:
    """Design a rectangular section per metre width.

    Mu is kN.m per metre. Returns required steel in mm2 per metre.
    """
    Mu = max(Mu_kNm_per_m, 0.0) * 1e6  # N.mm per metre
    as_min = min_flexural_steel(b_mm, h_mm, f_c, f_y, slab_like)
    if Mu <= 0:
        return FlexureResult(As_req=as_min, As_min=as_min, rho=as_min / (b_mm * d_mm),
                             a=0.0, phi_Mn=0.0, ok=True)
    rn = Mu / (phi * b_mm * d_mm ** 2)
    term = 1.0 - 2.0 * rn / (0.85 * f_c)
    if term <= 0:
        return FlexureResult(As_req=as_min, As_min=as_min, ok=False,
                             note="Section too small for the applied moment")
    rho = (0.85 * f_c / f_y) * (1.0 - math.sqrt(term))
    as_req = max(rho * b_mm * d_mm, as_min)
    a = as_req * f_y / (0.85 * f_c * b_mm)
    phi_mn = phi * as_req * f_y * (d_mm - a / 2.0) / 1e6  # kN.m per metre
    ok = phi_mn >= Mu_kNm_per_m - 1e-6
    return FlexureResult(As_req=as_req, As_min=as_min, rho=rho, a=a, phi_Mn=phi_mn, ok=ok,
                         note="" if ok else "Increase depth or steel")


def select_bars(
    As_req_mm2_per_m: float,
    bar_diameters: list[float],
    max_spacing: float = 300.0,
    min_spacing: float = 100.0,
    practical_max_diameter: float = 25.0,
) -> BarLayout:
    """Select a single bar size and spacing to provide the required steel."""
    if As_req_mm2_per_m <= 0:
        return BarLayout(diameter=12.0, spacing=max_spacing, As_provided=0.0, ok=False)
    candidates = [d for d in sorted(bar_diameters) if d <= practical_max_diameter] or sorted(bar_diameters)
    best: BarLayout | None = None
    for db in candidates:
        area = math.pi * db ** 2 / 4.0
        spacing = area * 1000.0 / As_req_mm2_per_m
        spacing = clamp(spacing, min_spacing, max_spacing)
        # Round down to a 5 mm practical spacing, then ensure the area is met.
        spacing = max(min_spacing, math.floor(spacing / 5.0) * 5.0)
        as_provided = area * 1000.0 / spacing
        layout = BarLayout(
            diameter=db,
            spacing=spacing,
            As_provided=as_provided,
            count_per_metre=1000.0 / spacing,
            ok=as_provided >= As_req_mm2_per_m - 1e-6,
        )
        if layout.ok:
            # Prefer the smallest diameter that works, with a practical spacing.
            if best is None or db < best.diameter:
                best = layout
    if best is not None:
        return best
    # Fall back to the largest bar at minimum spacing.
    db = max(candidates)
    area = math.pi * db ** 2 / 4.0
    as_provided = area * 1000.0 / min_spacing
    return BarLayout(diameter=db, spacing=min_spacing, As_provided=as_provided,
                     count_per_metre=1000.0 / min_spacing, ok=False,
                     note="Required steel cannot be provided with practical spacing")


def one_way_shear_capacity(b_mm: float, d_mm: float, f_c: float, phi: float = 0.75) -> float:
    """Design one-way shear strength, kN."""
    vc = 0.17 * math.sqrt(f_c) * b_mm * d_mm  # N
    return phi * vc / 1000.0


def punching_shear_capacity(
    b0_mm: float,
    d_mm: float,
    f_c: float,
    beta: float = 1.0,
    alpha_s: float = 40.0,
    phi: float = 0.75,
) -> float:
    """Design punching shear strength, kN, per BNBC 6.4.10 / ACI 318."""
    if b0_mm <= 0 or d_mm <= 0:
        return 0.0
    vc1 = 0.33 * math.sqrt(f_c)
    vc2 = 0.17 * (1.0 + 2.0 / max(beta, 0.1)) * math.sqrt(f_c)
    vc3 = 0.083 * (2.0 + alpha_s * d_mm / b0_mm) * math.sqrt(f_c)
    vc = min(vc1, vc2, vc3)
    return phi * vc * b0_mm * d_mm / 1000.0


def punching_geometry(
    c_l_mm: float,
    c_b_mm: float,
    d_mm: float,
    circular: bool = False,
) -> tuple[float, float, float]:
    """Return ``(b0_mm, critical_area_mm2, beta)`` at ``d/2`` from a column face.

    A circular column uses the actual circular critical perimeter
    ``b0 = pi * (D + d)`` and an area ``pi * (D + d)^2 / 4``.  A rectangular
    column uses the ACI rectangular perimeter.  ``beta`` is the ratio of long
    to short side and is 1.0 for circular sections.
    """
    c_l = max(c_l_mm, 1.0)
    c_b = max(c_b_mm, 1.0)
    if circular:
        diameter = max(c_l, c_b) + d_mm
        b0 = math.pi * diameter
        area = math.pi * diameter ** 2 / 4.0
        return b0, area, 1.0
    b0 = 2.0 * ((c_l + d_mm) + (c_b + d_mm))
    area = (c_l + d_mm) * (c_b + d_mm)
    beta = max(c_l, c_b) / max(min(c_l, c_b), 1.0)
    return b0, area, beta


def inside_punching_zone(
    x_m: float,
    y_m: float,
    c_l_mm: float,
    c_b_mm: float,
    d_mm: float,
    circular: bool = False,
) -> bool:
    """True if a point lies inside the critical punching perimeter."""
    x_mm, y_mm = x_m * 1000.0, y_m * 1000.0
    if circular:
        return math.hypot(x_mm, y_mm) <= max(c_l_mm, c_b_mm) / 2.0 + d_mm
    return (
        abs(x_mm) <= c_l_mm / 2.0 + d_mm
        and abs(y_mm) <= c_b_mm / 2.0 + d_mm
    )


@dataclass
class CrackWidthResult:
    width: float = 0.0               # mm
    limit: float = 0.30              # mm
    ok: bool = True
    sigma_s: float = 0.0             # MPa, service steel stress
    rho_eff: float = 0.0
    spacing: float = 0.0             # mm, maximum crack spacing
    note: str = ""


def crack_width_check(
    M_service_kNm_per_m: float,
    As_mm2_per_m: float,
    b_mm: float,
    h_mm: float,
    d_mm: float,
    f_c: float,
    cover_mm: float,
    bar_diameter_mm: float,
    limit_mm: float = 0.30,
    k1: float = 0.8,
    k2: float = 0.5,
) -> CrackWidthResult:
    """Service crack width by the EC2/BNBC 6.8.9 simplified formula.

    ``w_k = s_r,max * (eps_sm - eps_cm)`` with
    ``s_r,max = 3.4c + 0.425 k1 k2 phi / rho_p,eff``.  The concrete tension
    contribution is based on ``f_ctm = 0.30 f'c^(2/3)``.  The result is a
    design aid and must be checked against the project durability class.
    """
    b = max(b_mm, 1.0)
    d = max(d_mm, 1.0)
    h = max(h_mm, 1.0)
    As = max(As_mm2_per_m, 0.0)
    limit = max(limit_mm, 0.01)
    if As <= 1e-9:
        return CrackWidthResult(
            width=999.0, limit=limit, ok=False, spacing=0.0,
            note="No reinforcement provided for crack control",
        )
    sigma_s = abs(M_service_kNm_per_m) * 1e6 / (As * 0.90 * d)  # MPa
    # Effective tension area: 2.5 x distance from tension face to centroid.
    h_ce = min(2.5 * max(h - d, 1.0), h / 2.0)
    rho_eff = As / max(b * h_ce, 1e-9)
    es = 200000.0
    alpha_e = es / (4700.0 * math.sqrt(max(f_c, 15.0)))
    f_ctm = 0.30 * max(f_c, 15.0) ** (2.0 / 3.0)
    spacing = 3.4 * max(cover_mm, 10.0) + 0.425 * k1 * k2 * max(
        bar_diameter_mm, 6.0
    ) / max(rho_eff, 1e-9)
    strain = max(
        sigma_s / es
        - 0.60 * f_ctm / (es * max(rho_eff, 1e-9)) * (1.0 + alpha_e * rho_eff),
        0.0,
    )
    width = spacing * strain
    ok = width <= limit + 1e-9
    note = "" if ok else (
        f"Crack width {width:.3f} mm > {limit:.2f} mm; reduce bar spacing "
        "or increase reinforcement"
    )
    return CrackWidthResult(width, limit, ok, sigma_s, rho_eff, spacing, note)


@dataclass
class PilePMResult:
    utilization: float = 0.0
    axial_utilization: float = 0.0
    moment_utilization: float = 0.0
    phi_Pn: float = 0.0              # kN
    phi_Mn: float = 0.0              # kN.m
    ok: bool = True
    note: str = ""


def pile_pm_interaction(
    diameter: float,
    P: float,
    M: float,
    f_c: float,
    f_y: float,
    pile_type: str = "Bored",
    reinforcement_ratio: float | None = None,
    cover_mm: float = 75.0,
) -> PilePMResult:
    """Simplified axial-moment (P-M) interaction check for a circular pile.

    The axial design strength uses the usual spiral/ties factor and the moment
    capacity uses the reinforcement ring with a 0.6D lever arm.  A convex
    interaction curve ``(P/phiPn)^1.5 + M/phiMn <= 1`` is used, together with
    the pure axial and pure bending limits.
    """
    d_mm = max(diameter * 1000.0, 100.0)
    ag = math.pi * d_mm ** 2 / 4.0
    if reinforcement_ratio is None:
        if ag <= 0.5e6:
            reinforcement_ratio = 0.005
        elif ag <= 1.0e6:
            reinforcement_ratio = 0.00375
        else:
            reinforcement_ratio = 0.0025
    as_mm2 = max(reinforcement_ratio, 0.0025) * ag
    phi_pn = 0.65 * (
        0.85 * f_c * (ag - as_mm2) + f_y * as_mm2
    ) / 1000.0
    lever = max(0.60 * d_mm - cover_mm - 8.0, 0.25 * d_mm)
    phi_mn = 0.90 * as_mm2 * f_y * lever / 1e6
    # Minimum eccentricity moment (construction tolerance and slenderness).
    m_design = max(abs(M), abs(P) * 0.05 * max(diameter, 0.1))
    p_util = abs(P) / max(phi_pn, 1e-9)
    m_util = m_design / max(phi_mn, 1e-9)
    utilization = p_util ** 1.5 + m_util if p_util <= 1.0 else p_util + m_util
    ok = p_util <= 1.0 and m_util <= 1.0 and utilization <= 1.0 + 1e-9
    note = "" if ok else (
        f"P-M utilization {utilization:.2f} > 1.0 for D={d_mm:.0f} mm pile"
    )
    return PilePMResult(utilization, p_util, m_util, phi_pn, phi_mn, ok, note)


def development_length(db_mm: float, f_c: float, f_y: float, top_bar: bool = False,
                       epoxy: bool = False) -> float:
    """Approximate tension development length, mm (BNBC Ch. 8 / ACI 318)."""
    psi_t = 1.3 if top_bar else 1.0
    psi_e = 1.2 if epoxy else 1.0
    ld = (f_y * psi_t * psi_e / (1.1 * math.sqrt(max(f_c, 1.0)))) * db_mm
    return max(ld, 300.0)


def bar_weight_per_metre(db_mm: float) -> float:
    """Mass of a reinforcing bar, kg/m."""
    return math.pi * (db_mm / 1000.0) ** 2 / 4.0 * 7850.0
