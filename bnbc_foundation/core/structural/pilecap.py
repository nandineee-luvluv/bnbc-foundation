"""Structural design of pile caps.

The cap is treated as a rigid slab supported by the pile reactions and loaded by
the column (or wall) above.  Flexure, one-way shear, punching shear and a
supplementary strut-and-tie check are performed per BNBC 2020 Part 6, Chapter 6
(Sections 6.8.4, 6.8.5 and Appendix I) and Chapter 3 (Section 3.10.1.20).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..models import Element, FoundationOptions, Materials
from ..piles import PileGroupDesign
from .concrete import (
    BarLayout,
    bar_weight_per_metre,
    crack_width_check,
    development_length,
    flexural_design,
    inside_punching_zone,
    one_way_shear_capacity,
    punching_geometry,
    punching_shear_capacity,
    select_bars,
)


@dataclass
class PileCapDesign:
    length: float = 1.0                 # m
    width: float = 1.0                  # m
    thickness: float = 0.9              # m
    effective_depth: float = 800.0      # mm
    pile_count: int = 1
    pile_diameter: float = 0.6
    positions: list[tuple[float, float]] = field(default_factory=list)
    angle_deg: float = 0.0                # cap orientation in plan (wall caps)
    center_x: float = 0.0
    center_y: float = 0.0
    pile_reactions: list[float] = field(default_factory=list)
    max_pile_reaction: float = 0.0
    min_pile_reaction: float = 0.0
    factored_column_load: float = 0.0
    Mu_x: float = 0.0                    # kN.m per metre width
    Mu_y: float = 0.0
    Vu_x: float = 0.0                    # kN total across the critical section
    Vu_y: float = 0.0
    one_way_capacity_x: float = 0.0
    one_way_capacity_y: float = 0.0
    punching_vu: float = 0.0
    punching_capacity: float = 0.0
    pile_punching_vu: float = 0.0
    pile_punching_capacity: float = 0.0
    strut_angle: float = 0.0             # degrees
    strut_force: float = 0.0             # kN
    strut_capacity: float = 0.0          # kN
    tie_As_req: float = 0.0              # mm2
    development_available: float = 0.0  # mm
    development_required: float = 0.0   # mm
    crack_width: float = 0.0             # mm
    crack_limit: float = 0.30            # mm
    crack_ok: bool = True
    bottom_x: BarLayout = field(default_factory=BarLayout)
    bottom_y: BarLayout = field(default_factory=BarLayout)
    top_x: BarLayout = field(default_factory=BarLayout)
    top_y: BarLayout = field(default_factory=BarLayout)
    utilization: float = 0.0
    status: str = "OK"
    governing: str = "BNBC 6.8.5 pile cap flexure/shear/punching"
    remarks: str = ""
    concrete_volume: float = 0.0
    steel_weight: float = 0.0
    details: dict = field(default_factory=dict)


def _pile_reactions(
    positions: list[tuple[float, float]],
    P: float,
    Mx: float,
    My: float,
    cap_weight: float,
) -> list[float]:
    """Pile reactions for a rigid cap, compression positive."""
    n = len(positions)
    if n == 0:
        return []
    sx = sum(x * x for x, _ in positions)
    sy = sum(y * y for _, y in positions)
    total = P + cap_weight
    out = []
    for x, y in positions:
        r = total / n
        if sy > 0:
            r += Mx * y / sy
        if sx > 0:
            r += My * x / sx
        out.append(r)
    return out


def _moment_at_column_face(
    positions: list[tuple[float, float]],
    reactions: list[float],
    face_x: float,
    face_y: float,
) -> tuple[float, float]:
    """Bending moments across the full cap width at both column faces.

    Returns (Mx, My): Mx is bending about the y-axis (lever along x) and My is
    bending about the x-axis (lever along y), in kN.m for the full cap width.
    """
    mx = 0.0
    my = 0.0
    for (x, y), r in zip(positions, reactions):
        if x > face_x:
            mx += r * (x - face_x)
        elif x < -face_x:
            mx += r * (-face_x - x)
        if y > face_y:
            my += r * (y - face_y)
        elif y < -face_y:
            my += r * (-face_y - y)
    return max(mx, 0.0), max(my, 0.0)


def _shear_at_section(
    positions: list[tuple[float, float]],
    reactions: list[float],
    section_x: float,
    section_y: float,
) -> tuple[float, float]:
    """One-way shear across a section at a distance from the column face."""
    vx = sum(r for (x, _), r in zip(positions, reactions) if abs(x) > section_x)
    vy = sum(r for (_, y), r in zip(positions, reactions) if abs(y) > section_y)
    return max(vx, 0.0), max(vy, 0.0)


def _strut_and_tie(
    positions: list[tuple[float, float]],
    reactions: list[float],
    column_length: float,
    column_width: float,
    d_mm: float,
    f_c: float,
    f_y: float,
    phi_st: float = 0.75,
) -> tuple[float, float, float, float]:
    """Simplified strut-and-tie check for a pile cap.

    Returns (angle_deg, strut_force_kN, strut_capacity_kN, tie_As_req_mm2).
    The force is based on the most heavily loaded pile and the lever arm from the
    column face to that pile centre.
    """
    if not positions:
        return 0.0, 0.0, 0.0, 0.0
    index = max(range(len(positions)), key=lambda i: reactions[i])
    x, y = positions[index]
    face_x = column_length / 2.0
    face_y = column_width / 2.0
    lever_x = max(abs(x) - face_x, 0.0)
    lever_y = max(abs(y) - face_y, 0.0)
    lever = math.hypot(lever_x, lever_y)
    if lever <= 0.0 or d_mm <= 0.0:
        return 90.0, 0.0, 0.0, 0.0
    depth = d_mm / 1000.0
    theta = math.atan2(depth, lever)
    angle_deg = math.degrees(theta)
    force = max(reactions[index], 0.0) / max(math.sin(theta), 0.05)
    # Cracked concrete strut: fce = 0.6 f'c; width taken as the column face
    # projected through the cap, with a lower bound of 250 mm.
    strut_width = max(column_length, column_width, 0.25) * 1000.0
    strut_capacity = phi_st * 0.60 * f_c * strut_width * d_mm / 1000.0
    tie_force = force * math.cos(theta)
    tie_as = tie_force * 1000.0 / (phi_st * f_y)
    return angle_deg, force, strut_capacity, tie_as


def _steel_weight(cap: PileCapDesign) -> float:
    total = 0.0
    for layout, span in (
        (cap.bottom_x, cap.length),
        (cap.top_x, cap.length),
        (cap.bottom_y, cap.width),
        (cap.top_y, cap.width),
    ):
        if layout.As_provided > 0:
            # Bars run in the direction of the span; the perpendicular extent is
            # the other cap dimension.
            perpendicular = cap.width if span == cap.length else cap.length
            count = max(2, math.ceil(perpendicular * 1000.0 / max(layout.spacing, 1.0)) + 1)
            total += count * span * bar_weight_per_metre(layout.diameter)
    return total


def design_pilecap(
    element: Element,
    group: PileGroupDesign,
    materials: Materials,
    options: FoundationOptions,
) -> PileCapDesign:
    """Design a pile cap for an already-sized pile group."""
    from ..loads import governing_factored, governing_service

    cap = PileCapDesign(
        length=group.cap_length,
        width=group.cap_width,
        thickness=max(group.cap_thickness, options.cap_min_thickness / 1000.0, 0.60),
        pile_count=group.count,
        pile_diameter=group.diameter,
        positions=list(group.positions),
        angle_deg=group.angle_deg,
        center_x=element.center_x,
        center_y=element.center_y,
    )
    if element.kind == "wall":
        from ..loads import factored_combinations
        factored = max(
            (element.wall_local_reaction(r) for r in factored_combinations(element) or [element.max_factored()]),
            key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My),
        )
    else:
        factored = governing_factored(element)
    P_u = max(factored.P, 0.0)
    cap.factored_column_load = P_u
    if element.kind == "wall":
        c_l = max(element.section_projection_x, 1.0) * 1000.0
        c_b = max(element.section_projection_y, 0.20) * 1000.0
    else:
        c_l = max(getattr(element, "section_projection_x", element.section_length), 0.25) * 1000.0
        c_b = max(getattr(element, "section_projection_y", element.section_width), 0.25) * 1000.0

    db_main = 20.0
    cover = max(options.cap_cover, 50.0)
    notes: list[str] = []
    shear_details: dict = {}

    # Iterate cap thickness until all shear and strut checks pass.
    for _ in range(120):
        d_mm = cap.thickness * 1000.0 - cover - db_main / 2.0
        if d_mm <= 50.0:
            cap.thickness += 0.025
            continue
        cap_weight = 1.2 * materials.gamma_concrete * cap.length * cap.width * cap.thickness
        reactions = _pile_reactions(cap.positions, P_u, factored.Mx, factored.My, cap_weight)
        cap.pile_reactions = reactions
        cap.max_pile_reaction = max(reactions) if reactions else 0.0
        cap.min_pile_reaction = min(reactions) if reactions else 0.0

        face_x = c_l / 2000.0
        face_y = c_b / 2000.0
        mx_full, my_full = _moment_at_column_face(cap.positions, reactions, face_x, face_y)
        cap.Mu_x = mx_full / max(cap.width, 0.1)
        cap.Mu_y = my_full / max(cap.length, 0.1)

        section_x = face_x + d_mm / 1000.0
        section_y = face_y + d_mm / 1000.0
        cap.Vu_x, cap.Vu_y = _shear_at_section(cap.positions, reactions, section_x, section_y)
        cap.one_way_capacity_x = one_way_shear_capacity(
            cap.width * 1000.0, d_mm, materials.f_c, materials.phi_shear
        )
        cap.one_way_capacity_y = one_way_shear_capacity(
            cap.length * 1000.0, d_mm, materials.f_c, materials.phi_shear
        )

        circular = element.kind == "column" and element.is_circular
        b0, critical_area, beta = punching_geometry(
            c_l, c_b, d_mm, circular=circular
        )
        inside = sum(
            r
            for (x, y), r in zip(cap.positions, reactions)
            if inside_punching_zone(x, y, c_l, c_b, d_mm, circular=circular)
        )
        cap.punching_vu = max(P_u - inside, 0.0)
        cap.punching_capacity = punching_shear_capacity(
            b0, d_mm, materials.f_c, beta=beta, alpha_s=40.0, phi=materials.phi_shear
        )

        # Punching around the most heavily loaded pile.
        pile_b0 = math.pi * (cap.pile_diameter * 1000.0 + d_mm)
        cap.pile_punching_vu = cap.max_pile_reaction
        cap.pile_punching_capacity = punching_shear_capacity(
            pile_b0, d_mm, materials.f_c, beta=1.0, alpha_s=20.0, phi=materials.phi_shear
        )

        angle, force, strut_cap, tie_as = _strut_and_tie(
            cap.positions, reactions, c_l / 1000.0, c_b / 1000.0,
            d_mm, materials.f_c, materials.f_y,
        )
        cap.strut_angle = angle
        cap.strut_force = force
        cap.strut_capacity = strut_cap
        cap.tie_As_req = tie_as

        one_way_ok = (
            cap.Vu_x <= cap.one_way_capacity_x + 1e-6
            and cap.Vu_y <= cap.one_way_capacity_y + 1e-6
        )
        punching_ok = (
            cap.punching_vu <= cap.punching_capacity + 1e-6
            and cap.pile_punching_vu <= cap.pile_punching_capacity + 1e-6
        )
        strut_ok = angle >= 25.0 and force <= strut_cap + 1e-6
        shear_details = {
            "d_mm": d_mm, "b0_mm": b0,
            "one_way_ok": one_way_ok, "punching_ok": punching_ok,
            "strut_ok": strut_ok, "cap_weight": cap_weight,
        }
        if one_way_ok and punching_ok and strut_ok:
            break
        cap.thickness += 0.025
        if cap.thickness > 2.50:
            notes.append("Cap thickness exceeds 2.50 m; review pile layout")
            break

    d_mm = cap.thickness * 1000.0 - cover - db_main / 2.0
    cap.effective_depth = d_mm
    flex_x = flexural_design(
        cap.Mu_x, 1000.0, d_mm, cap.thickness * 1000.0,
        materials.f_c, materials.f_y, materials.phi_flexure,
    )
    flex_y = flexural_design(
        cap.Mu_y, 1000.0, d_mm, cap.thickness * 1000.0,
        materials.f_c, materials.f_y, materials.phi_flexure,
    )
    # The strut-and-tie tie steel is distributed over the cap; convert it to a
    # per-metre requirement and take the larger of the two methods.
    tie_per_m_x = cap.tie_As_req / max(cap.width, 0.1)
    tie_per_m_y = cap.tie_As_req / max(cap.length, 0.1)
    cap.bottom_x = select_bars(
        max(flex_x.As_req, tie_per_m_x), materials.bar_diameters,
        materials.max_bar_spacing, materials.min_bar_spacing,
    )
    cap.bottom_y = select_bars(
        max(flex_y.As_req, tie_per_m_y), materials.bar_diameters,
        materials.max_bar_spacing, materials.min_bar_spacing,
    )
    top_req = 0.0018 * 1000.0 * cap.thickness * 1000.0 * 0.5
    cap.top_x = select_bars(top_req, materials.bar_diameters, materials.max_bar_spacing, materials.min_bar_spacing)
    cap.top_y = select_bars(top_req, materials.bar_diameters, materials.max_bar_spacing, materials.min_bar_spacing)

    # Development length from the column face to the outer bar end.  Use each
    # direction's selected bar and take the largest requirement against the
    # shortest available anchorage.
    req_x = development_length(cap.bottom_x.diameter, materials.f_c, materials.f_y)
    req_y = development_length(cap.bottom_y.diameter, materials.f_c, materials.f_y)
    cap.development_required = max(req_x, req_y)
    bar_end_cover = max(cover, options.cap_edge_cover * 1000.0)
    avail_x = (cap.length * 1000.0 - c_l) / 2.0 - bar_end_cover
    avail_y = (cap.width * 1000.0 - c_b) / 2.0 - bar_end_cover
    cap.development_available = min(avail_x, avail_y)
    development_ok = cap.development_available >= cap.development_required
    if not development_ok:
        notes.append(
            f"Development length available {cap.development_available:.0f} mm < "
            f"required {cap.development_required:.0f} mm; provide hooks or extend cap"
        )

    utilization = max(
        cap.Mu_x / max(flex_x.phi_Mn, 1e-6),
        cap.Mu_y / max(flex_y.phi_Mn, 1e-6),
        cap.Vu_x / max(cap.one_way_capacity_x, 1e-6),
        cap.Vu_y / max(cap.one_way_capacity_y, 1e-6),
        cap.punching_vu / max(cap.punching_capacity, 1e-6),
        cap.pile_punching_vu / max(cap.pile_punching_capacity, 1e-6),
        cap.strut_force / max(cap.strut_capacity, 1e-6),
    )
    status = "OK"
    if utilization > 1.0 or cap.strut_angle < 25.0:
        status = "CHECK"
    if not development_ok:
        status = "CHECK"
    if cap.min_pile_reaction < -1e-6:
        status = "CHECK"
        notes.append("Pile in tension under factored load; provide uplift capacity")
    if not (flex_x.ok and flex_y.ok and cap.bottom_x.ok and cap.bottom_y.ok):
        status = "CHECK"
        notes.append("Reinforcement selection requires review")

    # Service crack-width check using service pile reactions.
    service = governing_service(element)
    service_weight = materials.gamma_concrete * cap.length * cap.width * cap.thickness
    service_reactions = _pile_reactions(
        cap.positions, max(service.P, 0.0), service.Mx, service.My, service_weight,
    )
    msx_full, msy_full = _moment_at_column_face(
        cap.positions, service_reactions, c_l / 2000.0, c_b / 2000.0
    )
    crack_x = crack_width_check(
        msx_full / max(cap.width, 0.1), cap.bottom_x.As_provided,
        1000.0, cap.thickness * 1000.0, d_mm, materials.f_c,
        cover, cap.bottom_x.diameter, limit_mm=options.crack_width_limit,
    )
    crack_y = crack_width_check(
        msy_full / max(cap.length, 0.1), cap.bottom_y.As_provided,
        1000.0, cap.thickness * 1000.0, d_mm, materials.f_c,
        cover, cap.bottom_y.diameter, limit_mm=options.crack_width_limit,
    )
    crack = crack_x if crack_x.width >= crack_y.width else crack_y
    cap.crack_width = crack.width
    cap.crack_limit = crack.limit
    cap.crack_ok = crack_x.ok and crack_y.ok
    if not options.crack_check:
        cap.crack_ok = True
    if not cap.crack_ok:
        status = "CHECK"
        notes.append(crack.note)

    cap.utilization = utilization
    cap.status = status
    cap.remarks = "; ".join(notes)
    cap.concrete_volume = cap.length * cap.width * cap.thickness
    cap.steel_weight = _steel_weight(cap)
    cap.details = {
        "shear": shear_details,
        "flexure_x": flex_x,
        "flexure_y": flex_y,
        "pile_reactions": cap.pile_reactions,
        "service_pile_reactions": service_reactions,
        "crack_x": crack_x,
        "crack_y": crack_y,
        "cover_mm": cover,
    }
    return cap
