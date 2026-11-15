"""Structural design of raft/mat foundations."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..models import Borehole, Element, FoundationOptions, Materials
from ..raft import RaftAnalysis, analyze_raft
from .concrete import (
    BarLayout,
    bar_weight_per_metre,
    crack_width_check,
    development_length,
    flexural_design,
    one_way_shear_capacity,
    select_bars,
)


@dataclass
class RaftDesign:
    analysis: RaftAnalysis = field(default_factory=RaftAnalysis)
    thickness: float = 0.6
    bottom_x: BarLayout = field(default_factory=BarLayout)
    bottom_y: BarLayout = field(default_factory=BarLayout)
    top_x: BarLayout = field(default_factory=BarLayout)
    top_y: BarLayout = field(default_factory=BarLayout)
    Mu_bottom_x: float = 0.0
    Mu_bottom_y: float = 0.0
    Mu_top_x: float = 0.0
    Mu_top_y: float = 0.0
    one_way_capacity: float = 0.0
    shear_utilization: float = 0.0
    flexure_utilization: float = 0.0
    punching_utilization: float = 0.0
    crack_width: float = 0.0
    crack_limit: float = 0.30
    crack_ok: bool = True
    utilization: float = 0.0
    status: str = "OK"
    governing: str = "BNBC 3.8.10 raft; 6.8 flexure/shear/punching"
    remarks: str = ""
    concrete_volume: float = 0.0
    steel_weight: float = 0.0
    details: dict = field(default_factory=dict)


def _raft_steel_weight(design: RaftDesign) -> float:
    total = 0.0
    length = design.analysis.length
    width = design.analysis.width
    for layout, span, perpendicular in (
        (design.bottom_x, length, width),
        (design.top_x, length, width),
        (design.bottom_y, width, length),
        (design.top_y, width, length),
    ):
        if layout.As_provided <= 0:
            continue
        count = max(2, math.ceil(perpendicular * 1000.0 / max(layout.spacing, 1.0)) + 1)
        total += count * span * bar_weight_per_metre(layout.diameter)
    return total


def _design_once(
    elements: list[Element],
    borehole: Borehole,
    q_allow: float,
    options: FoundationOptions,
    materials: Materials,
    thickness: float,
    method: str | None,
) -> RaftDesign:
    analysis = analyze_raft(
        elements, borehole, q_allow, options, materials,
        thickness=thickness, method=method,
    )
    design = RaftDesign(analysis=analysis, thickness=analysis.thickness)
    cover_bottom = max(materials.cover, 50.0)
    cover_top = max(materials.cover * 0.67, 40.0)
    db = 20.0
    d_bottom = max(thickness * 1000.0 - cover_bottom - db / 2.0, 50.0)
    d_top = max(thickness * 1000.0 - cover_top - db / 2.0, 50.0)
    h_mm = thickness * 1000.0

    # Positive moments need bottom steel; negative moments need top steel.
    design.Mu_bottom_x = max(analysis.moment_x_pos, 0.0)
    design.Mu_bottom_y = max(analysis.moment_y_pos, 0.0)
    design.Mu_top_x = max(analysis.moment_x_neg, 0.0)
    design.Mu_top_y = max(analysis.moment_y_neg, 0.0)
    min_as = 0.0018 * 1000.0 * h_mm
    fb_x = flexural_design(design.Mu_bottom_x, 1000.0, d_bottom, h_mm,
                           materials.f_c, materials.f_y, materials.phi_flexure)
    fb_y = flexural_design(design.Mu_bottom_y, 1000.0, d_bottom, h_mm,
                           materials.f_c, materials.f_y, materials.phi_flexure)
    ft_x = flexural_design(design.Mu_top_x, 1000.0, d_top, h_mm,
                           materials.f_c, materials.f_y, materials.phi_flexure)
    ft_y = flexural_design(design.Mu_top_y, 1000.0, d_top, h_mm,
                           materials.f_c, materials.f_y, materials.phi_flexure)

    design.bottom_x = select_bars(max(fb_x.As_req, min_as), materials.bar_diameters,
                                  materials.max_bar_spacing, materials.min_bar_spacing)
    design.bottom_y = select_bars(max(fb_y.As_req, min_as), materials.bar_diameters,
                                  materials.max_bar_spacing, materials.min_bar_spacing)
    design.top_x = select_bars(max(ft_x.As_req, min_as), materials.bar_diameters,
                               materials.max_bar_spacing, materials.min_bar_spacing)
    design.top_y = select_bars(max(ft_y.As_req, min_as), materials.bar_diameters,
                               materials.max_bar_spacing, materials.min_bar_spacing)

    design.one_way_capacity = one_way_shear_capacity(
        1000.0, min(d_bottom, d_top), materials.f_c, materials.phi_shear
    )
    design.shear_utilization = max(
        analysis.shear_x / max(design.one_way_capacity, 1e-6),
        analysis.shear_y / max(design.one_way_capacity, 1e-6),
    )
    design.punching_utilization = analysis.punching_vu / max(analysis.punching_capacity, 1e-6)
    design.flexure_utilization = max(
        design.Mu_bottom_x / max(fb_x.phi_Mn, 1e-6),
        design.Mu_bottom_y / max(fb_y.phi_Mn, 1e-6),
        design.Mu_top_x / max(ft_x.phi_Mn, 1e-6),
        design.Mu_top_y / max(ft_y.phi_Mn, 1e-6),
    )
    design.utilization = max(
        design.shear_utilization, design.punching_utilization, design.flexure_utilization,
        analysis.q_service_max / max(q_allow, 1e-6),
    )
    design.concrete_volume = analysis.area * thickness
    design.steel_weight = _raft_steel_weight(design)

    # Service crack-width checks on the governing face of each direction.
    crack_bx = crack_width_check(
        max(analysis.service_moment_x_pos, analysis.moment_x_pos / 1.4),
        design.bottom_x.As_provided, 1000.0, h_mm, d_bottom,
        materials.f_c, cover_bottom, design.bottom_x.diameter,
        limit_mm=options.crack_width_limit,
    )
    crack_by = crack_width_check(
        max(analysis.service_moment_y_pos, analysis.moment_y_pos / 1.4),
        design.bottom_y.As_provided, 1000.0, h_mm, d_bottom,
        materials.f_c, cover_bottom, design.bottom_y.diameter,
        limit_mm=options.crack_width_limit,
    )
    crack_tx = crack_width_check(
        max(analysis.service_moment_x_neg, analysis.moment_x_neg / 1.4),
        design.top_x.As_provided, 1000.0, h_mm, d_top,
        materials.f_c, cover_top, design.top_x.diameter,
        limit_mm=options.crack_width_limit,
    )
    crack_ty = crack_width_check(
        max(analysis.service_moment_y_neg, analysis.moment_y_neg / 1.4),
        design.top_y.As_provided, 1000.0, h_mm, d_top,
        materials.f_c, cover_top, design.top_y.diameter,
        limit_mm=options.crack_width_limit,
    )
    governing_crack = max(
        (crack_bx, crack_by, crack_tx, crack_ty), key=lambda c: c.width
    )
    design.crack_width = governing_crack.width
    design.crack_limit = governing_crack.limit
    design.crack_ok = all(
        c.ok for c in (crack_bx, crack_by, crack_tx, crack_ty)
    ) or not options.crack_check

    notes: list[str] = []
    if analysis.status != "OK":
        notes.append(analysis.remarks)
    if not design.crack_ok:
        notes.append(governing_crack.note)
    if design.shear_utilization > 1.0 + 1e-6:
        notes.append("One-way shear exceeds capacity")
    if design.punching_utilization > 1.0 + 1e-6:
        notes.append("Punching shear exceeds capacity")
    if not (design.bottom_x.ok and design.bottom_y.ok and design.top_x.ok and design.top_y.ok):
        notes.append("Reinforcement selection requires review")
    ld = development_length(db, materials.f_c, materials.f_y)
    design.details["development_length_mm"] = ld
    design.remarks = "; ".join(dict.fromkeys(n for n in notes if n))
    design.status = "OK" if (
        design.utilization <= 1.0
        and analysis.status == "OK"
        and design.bottom_x.ok and design.bottom_y.ok
        and design.top_x.ok and design.top_y.ok
        and design.crack_ok
    ) else "CHECK"
    design.details.update({
        "flexure_bottom_x": fb_x, "flexure_bottom_y": fb_y,
        "flexure_top_x": ft_x, "flexure_top_y": ft_y,
        "d_bottom_mm": d_bottom, "d_top_mm": d_top,
        "min_steel_mm2_per_m": min_as,
        "crack_bottom_x": crack_bx, "crack_bottom_y": crack_by,
        "crack_top_x": crack_tx, "crack_top_y": crack_ty,
    })
    return design


def design_raft(
    elements: list[Element],
    borehole: Borehole,
    q_allow: float,
    options: FoundationOptions,
    materials: Materials,
    method: str | None = None,
) -> RaftDesign:
    """Design a raft, increasing thickness until shear/punching are adequate.

    The geotechnical checks (bearing, settlement, buoyancy) are not solved by
    thickening and remain visible in the returned status/remarks.
    """
    start = max(options.raft_min_thickness / 1000.0, 0.60)
    method = method or options.raft_analysis
    best: RaftDesign | None = None
    for i in range(4):
        thickness = start + 0.15 * i
        design = _design_once(
            elements, borehole, q_allow, options, materials, thickness, method,
        )
        if best is None or design.utilization < best.utilization:
            best = design
        if (design.shear_utilization <= 1.0
                and design.punching_utilization <= 1.0
                and design.flexure_utilization <= 1.0):
            break
    assert best is not None
    return best
