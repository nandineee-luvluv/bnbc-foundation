"""Detailed design of isolated, combined and strip/wall footings."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..bearing import (
    check_shallow_uplift,
    check_stability,
    pressure_distribution,
    size_isolated_footing,
)
from ..models import Borehole, Element, FoundationOptions, Materials, Reaction
from ..settlement import estimate_shallow_settlement
from ..soil import vertical_stress
from ..units import ceil_to
from .concrete import (
    BarLayout,
    CrackWidthResult,
    crack_width_check,
    flexural_design,
    one_way_shear_capacity,
    punching_geometry,
    punching_shear_capacity,
    select_bars,
)


@dataclass
class FootingDesign:
    length: float = 1.0
    width: float = 1.0
    thickness: float = 0.45          # m
    depth: float = 1.5               # m
    origin_x: float = 0.0            # m, lower-left corner in the design frame
    origin_y: float = 0.0
    center_x: float = 0.0            # m, plan centre
    center_y: float = 0.0
    angle_deg: float = 0.0           # rotation about the centre (wall footings)
    q_service_max: float = 0.0
    q_allow: float = 0.0
    q_factored: float = 0.0
    utilization: float = 0.0
    settlement: float = 0.0
    settlement_limit: float = 0.0
    status: str = "OK"
    governing: str = ""
    remarks: str = ""
    bottom_x: BarLayout = field(default_factory=BarLayout)
    bottom_y: BarLayout = field(default_factory=BarLayout)
    top_x: BarLayout = field(default_factory=BarLayout)
    top_y: BarLayout = field(default_factory=BarLayout)
    Mu_x: float = 0.0                 # kN.m/m
    Mu_y: float = 0.0
    Vu_x: float = 0.0                 # kN/m
    Vu_y: float = 0.0
    punching_vu: float = 0.0          # kN
    punching_capacity: float = 0.0    # kN
    sliding_fs: float = 0.0
    overturning_fs: float = 0.0
    crack_width: float = 0.0
    crack_limit: float = 0.30
    crack_ok: bool = True
    uplift_fs: float = 999.0
    uplift: float = 0.0
    uplift_ok: bool = True
    concrete_volume: float = 0.0
    steel_weight: float = 0.0
    details: dict = field(default_factory=dict)


def _governing_crack(
    M_service: float,
    As_provided: float,
    b_mm: float,
    h_mm: float,
    d_mm: float,
    materials: Materials,
    bar_diameter: float,
    limit_mm: float = 0.30,
) -> CrackWidthResult:
    return crack_width_check(
        M_service, As_provided, b_mm, h_mm, d_mm,
        materials.f_c, materials.cover, bar_diameter, limit_mm=limit_mm,
    )


def _governing_service(element: Element) -> Reaction:
    from ..loads import service_combinations
    candidates = service_combinations(element) or [element.max_service()]
    return max(candidates, key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My))


def _governing_factored(element: Element) -> Reaction:
    from ..loads import factored_combinations
    candidates = factored_combinations(element) or [element.max_factored()]
    return max(candidates, key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My))


def _governing_wall_service(element: Element) -> Reaction:
    from ..loads import service_combinations
    candidates = service_combinations(element) or [element.max_service()]
    local = [element.wall_local_reaction(r) for r in candidates]
    return max(local, key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My))


def _governing_wall_factored(element: Element) -> Reaction:
    from ..loads import factored_combinations
    candidates = factored_combinations(element) or [element.max_factored()]
    local = [element.wall_local_reaction(r) for r in candidates]
    return max(local, key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My))


def _minimum_service(element: Element) -> Reaction:
    """Service reaction with the smallest vertical load (uplift-critical)."""
    from ..loads import service_combinations
    candidates = service_combinations(element) or element.service_reactions() or [Reaction()]
    return min(candidates, key=lambda r: r.P)


def _service_ok(element: Element, L: float, B: float, thickness: float,
                q_allow: float, concrete_unit_weight: float) -> tuple[bool, float, Reaction]:
    from ..loads import service_combinations
    self_weight = concrete_unit_weight * L * B * thickness
    ok = True
    max_q = 0.0
    gov = None
    for r in service_combinations(element) or [element.max_service()]:
        p = pressure_distribution(r.P + self_weight, r.Mx, r.My, L, B)
        limit = q_allow * (1.33 if r.includes_lateral else 1.0)
        if p.q_max > limit + 1e-6 or not p.kern_ok:
            ok = False
        utilization = p.q_max / max(limit, 1e-6)
        if gov is None or utilization > max_q:
            max_q = utilization
            gov = r
    return ok, max_q, gov or element.max_service()


def _net_service_pressure(
    element: Element,
    L: float,
    B: float,
    thickness: float,
    concrete_unit_weight: float,
    borehole: Borehole | None = None,
    depth: float = 0.0,
) -> float:
    gov = _governing_service(element)
    self_weight = concrete_unit_weight * L * B * thickness
    p = pressure_distribution(gov.P + self_weight, gov.Mx, gov.My, L, B)
    # Settlement is driven by the net increase in effective stress at the
    # footing base, so remove the existing soil overburden.
    overburden = vertical_stress(borehole, depth)[2] if borehole is not None and depth > 0 else 0.0
    return max(p.q_avg - overburden, 0.0)


def _minimum_depth(element: Element, borehole: Borehole, options: FoundationOptions) -> float:
    layer = borehole.layer_at_depth(max(-element.base_elev, 0.0) + 0.1) if borehole else None
    cohesive = layer.is_cohesive() if layer else True
    required = options.min_depth_cohesive if cohesive else options.min_depth_cohesionless
    return max(options.min_depth_general, required, abs(min(element.base_elev, 0.0)))


def _design_thickness(
    P_u: float, Mx_u: float, My_u: float, L: float, B: float,
    c_l: float, c_b: float, materials: Materials, options: FoundationOptions,
    start: float, circular: bool = False,
) -> tuple[float, dict]:
    """Increase thickness until one-way and punching shear pass."""
    cover = materials.cover
    db = 16.0
    thickness = max(start, options.min_thickness_soil / 1000.0)
    details: dict = {}
    for _ in range(80):
        d = thickness * 1000.0 - cover - db / 2.0
        if d <= 20:
            thickness += 0.025
            continue
        a = max((L * 1000.0 - c_l) / 2.0, 0.0)
        b = max((B * 1000.0 - c_b) / 2.0, 0.0)
        q_u = P_u / max(L * B, 1e-6) + abs(Mx_u) / (L * B * B / 6.0) + abs(My_u) / (B * L * L / 6.0)
        q_avg = P_u / max(L * B, 1e-6)
        vu_x = q_u * max(a - d, 0.0) / 1000.0
        vu_y = q_u * max(b - d, 0.0) / 1000.0
        phi_vc = one_way_shear_capacity(1000.0, d, materials.f_c, materials.phi_shear)
        b0, critical_area, beta = punching_geometry(c_l, c_b, d, circular=circular)
        vu_p = max(P_u - q_avg * critical_area / 1e6, 0.0)
        phi_vp = punching_shear_capacity(b0, d, materials.f_c, beta=beta,
                                         alpha_s=40.0, phi=materials.phi_shear)
        details.update({
            "d_mm": d, "one_way_vu_x": vu_x, "one_way_vu_y": vu_y,
            "one_way_capacity": phi_vc, "punching_vu": vu_p, "punching_capacity": phi_vp,
            "b0_mm": b0, "punching_area_m2": critical_area / 1e6,
            "circular": circular, "q_u": q_u, "q_avg": q_avg,
        })
        if vu_x <= phi_vc + 1e-6 and vu_y <= phi_vc + 1e-6 and vu_p <= phi_vp + 1e-6:
            break
        thickness += 0.025
    return thickness, details


def design_isolated(
    element: Element,
    borehole: Borehole,
    q_allow: float,
    options: FoundationOptions,
    materials: Materials,
) -> FootingDesign:
    service = _governing_service(element)
    factored = _governing_factored(element)
    depth = _minimum_depth(element, borehole, options)
    thickness = max(options.min_thickness_soil / 1000.0, 0.45)
    L, B, pressure = size_isolated_footing(
        service.P, service.Mx, service.My, q_allow, options, thickness,
        materials.gamma_concrete,
    )

    # Iterate plan dimensions if any service combination fails.
    for _ in range(30):
        ok, _, _ = _service_ok(element, L, B, thickness, q_allow, materials.gamma_concrete)
        if ok:
            break
        if pressure.e_x > L / 6.0:
            L += options.footing_dim_step
        elif pressure.e_y > B / 6.0:
            B += options.footing_dim_step
        elif L <= B:
            L += options.footing_dim_step
        else:
            B += options.footing_dim_step
        L = min(L, options.max_footing_dim)
        B = min(B, options.max_footing_dim)
        pressure = pressure_distribution(
            service.P + materials.gamma_concrete * L * B * thickness,
            service.Mx, service.My, L, B,
        )
        if L >= options.max_footing_dim and B >= options.max_footing_dim:
            break

    # Factored structural design.
    self_weight_u = 1.2 * materials.gamma_concrete * L * B * thickness
    P_u = factored.P + self_weight_u
    c_l = element.section_projection_x * 1000.0
    c_b = element.section_projection_y * 1000.0
    thickness, shear_details = _design_thickness(
        P_u, factored.Mx, factored.My, L, B,
        c_l, c_b,
        materials, options, thickness,
        circular=element.is_circular,
    )
    q_u = P_u / (L * B) + abs(factored.Mx) / (L * B * B / 6.0) + abs(factored.My) / (B * L * L / 6.0)
    d = thickness * 1000.0 - materials.cover - 16.0 / 2.0
    a = max((L * 1000.0 - c_l) / 2.0, 0.0)
    b = max((B * 1000.0 - c_b) / 2.0, 0.0)
    Mu_x = q_u * (a / 1000.0) ** 2 / 2.0
    Mu_y = q_u * (b / 1000.0) ** 2 / 2.0
    fx = flexural_design(Mu_x, 1000.0, d, thickness * 1000.0, materials.f_c, materials.f_y, materials.phi_flexure)
    fy = flexural_design(Mu_y, 1000.0, d, thickness * 1000.0, materials.f_c, materials.f_y, materials.phi_flexure)
    bx = select_bars(fx.As_req, materials.bar_diameters, materials.max_bar_spacing, materials.min_bar_spacing)
    by = select_bars(fy.As_req, materials.bar_diameters, materials.max_bar_spacing, materials.min_bar_spacing)
    # Minimum top mesh for crack control / structural integrity.
    top_req = 0.0018 * 1000.0 * thickness * 1000.0 * 0.5
    top = select_bars(top_req, materials.bar_diameters, materials.max_bar_spacing, materials.min_bar_spacing)

    q_service = max(pressure.q_max, 0.0)
    q_limit = q_allow * (1.33 if service.includes_lateral else 1.0)
    service_moment_x = q_service * (a / 1000.0) ** 2 / 2.0
    service_moment_y = q_service * (b / 1000.0) ** 2 / 2.0
    crack_x = _governing_crack(
        service_moment_x, bx.As_provided, 1000.0, thickness * 1000.0, d,
        materials, bx.diameter, options.crack_width_limit,
    )
    crack_y = _governing_crack(
        service_moment_y, by.As_provided, 1000.0, thickness * 1000.0, d,
        materials, by.diameter, options.crack_width_limit,
    )
    crack = crack_x if crack_x.width >= crack_y.width else crack_y
    if not options.crack_check:
        crack_ok = True
    else:
        crack_ok = crack_x.ok and crack_y.ok
    min_service = _minimum_service(element)
    uplift = check_shallow_uplift(
        borehole, depth, L, B, thickness, min_service.P,
        materials.gamma_concrete, max(min_service.buoyancy, 0.0),
        options.uplift_fs,
    )
    uplift_ok = uplift.ok if options.uplift_check else True
    settlement = estimate_shallow_settlement(
        borehole, depth, L, B,
        _net_service_pressure(
            element, L, B, thickness, materials.gamma_concrete, borehole, depth
        ),
        options,
    )
    stability = check_stability(
        service.P, service.Mx, service.My, service.Vx, service.Vy, L, B, depth,
        cohesion=borehole.layer_at_depth(depth).cohesion if borehole.layer_at_depth(depth) else 0.0,
        friction_angle=borehole.layer_at_depth(depth).friction_angle if borehole.layer_at_depth(depth) else 0.0,
    )
    status = "OK"
    notes = []
    if q_service > q_limit + 1e-6:
        status = "FAIL"
        notes.append(f"Bearing pressure {q_service:.1f} > {q_limit:.1f} kPa")
    if not settlement.ok:
        status = "CHECK" if status == "OK" else status
        notes.append(settlement.note)
    if not stability.ok:
        status = "CHECK" if status == "OK" else status
        notes.append(stability.note)
    if not (fx.ok and fy.ok and bx.ok and by.ok):
        status = "CHECK" if status == "OK" else status
        notes.append("Reinforcement/depth check requires attention")
    if not crack_ok:
        status = "CHECK" if status == "OK" else status
        notes.append(crack.note)
    if not uplift_ok:
        status = "CHECK" if status == "OK" else status
        notes.append(uplift.note)

    concrete_volume = L * B * thickness
    steel = _mat_steel_weight(bx, by, top, top, L, B)
    center_x, center_y = element.center
    return FootingDesign(
        length=L, width=B, thickness=thickness, depth=depth,
        origin_x=center_x - L / 2.0, origin_y=center_y - B / 2.0,
        center_x=center_x, center_y=center_y, angle_deg=0.0,
        q_service_max=q_service, q_allow=q_limit, q_factored=q_u,
        utilization=max(q_service / max(q_limit, 1e-6), shear_details.get("punching_vu", 0.0) / max(shear_details.get("punching_capacity", 1e-6), 1e-6)),
        settlement=settlement.total, settlement_limit=settlement.limit,
        status=status, governing="BNBC 3.9.1/3.9.3 bearing; 6.8 flexure/shear",
        remarks="; ".join(notes),
        bottom_x=bx, bottom_y=by, top_x=top, top_y=top, Mu_x=Mu_x, Mu_y=Mu_y,
        Vu_x=shear_details.get("one_way_vu_x", 0.0), Vu_y=shear_details.get("one_way_vu_y", 0.0),
        punching_vu=shear_details.get("punching_vu", 0.0),
        punching_capacity=shear_details.get("punching_capacity", 0.0),
        sliding_fs=stability.sliding_fs, overturning_fs=stability.overturning_fs,
        crack_width=crack.width, crack_limit=crack.limit, crack_ok=crack_ok,
        uplift_fs=uplift.fs, uplift=uplift.uplift, uplift_ok=uplift_ok,
        concrete_volume=concrete_volume, steel_weight=steel,
        details={"shear": shear_details, "flexure_x": fx, "flexure_y": fy,
                 "settlement": settlement, "stability": stability,
                 "crack_x": crack_x, "crack_y": crack_y, "uplift": uplift},
    )


def _beam_moment_envelope(
    origin: float,
    length: float,
    line_load: float,
    point_loads: list[tuple[float, float]],
    line_load_end: float | None = None,
) -> tuple[float, float]:
    """Exact moment envelope for a free-free beam on a linear line load.

    ``line_load`` is the net upward pressure per metre (kN/m) at the left end
    and ``line_load_end`` at the right end; omit it for a uniform load.
    ``point_loads`` are downward column loads at global x positions.  Within a
    segment the load varies linearly, so the shear is quadratic and the moment
    cubic; the extrema are evaluated at segment ends and at zero-shear points.
    """
    if length <= 0.0:
        return 0.0, 0.0
    w0 = max(line_load, 0.0)
    w1 = w0 if line_load_end is None else max(line_load_end, 0.0)
    if w0 <= 0.0 and w1 <= 0.0 and not point_loads:
        return 0.0, 0.0
    slope = (w1 - w0) / length

    events: list[tuple[float, float]] = []
    for x, p in sorted(point_loads):
        local = min(max(x - origin, 0.0), length)
        if events and abs(local - events[-1][0]) < 1e-9:
            events[-1] = (local, events[-1][1] + p)
        else:
            events.append((local, p))

    moments = [0.0]
    shear = 0.0
    moment = 0.0
    previous = 0.0

    def add_segment(span: float) -> None:
        nonlocal shear, moment, previous
        if span <= 1e-12:
            return
        a0 = w0 + slope * previous
        shear_end = shear - a0 * span - 0.5 * slope * span ** 2
        roots: list[float] = []
        if abs(slope) < 1e-12:
            if abs(a0) > 1e-12:
                roots.append(shear / a0)
        else:
            disc = a0 * a0 + 2.0 * slope * shear
            if disc >= 0.0:
                sq = math.sqrt(disc)
                roots.extend([(-a0 + sq) / slope, (-a0 - sq) / slope])
        for t in roots:
            if 0.0 < t < span:
                moments.append(
                    moment + shear * t - a0 * t ** 2 / 2.0 - slope * t ** 3 / 6.0
                )
        moment += shear * span - a0 * span ** 2 / 2.0 - slope * span ** 3 / 6.0
        shear = shear_end
        previous += span
        moments.append(moment)

    for position, load in events:
        add_segment(position - previous)
        shear += load
        previous = position
    add_segment(length - previous)
    return max(moments), min(moments)


def _mat_steel_weight(bx: BarLayout, by: BarLayout, tx: BarLayout, ty: BarLayout,
                      L: float, B: float) -> float:
    """Approximate steel mass for a rectangular mat, kg."""
    total = 0.0
    for layout, span in ((bx, L), (tx, L)):
        if layout.As_provided > 0:
            total += layout.As_provided / 1e6 * B * span * 7850.0
    for layout, span in ((by, B), (ty, B)):
        if layout.As_provided > 0:
            total += layout.As_provided / 1e6 * L * span * 7850.0
    return total


def design_strip(
    element: Element,
    borehole: Borehole,
    q_allow: float,
    options: FoundationOptions,
    materials: Materials,
) -> FootingDesign:
    """Design a strip/wall footing, analysed per metre length.

    Wall moments are rotated into wall-local axes first: ``Mx`` acts about the
    wall axis (pressure varies across the strip width) and ``My`` is the
    in-plane moment about the wall normal.
    """
    service = _governing_wall_service(element)
    factored = _governing_wall_factored(element)
    wall_length = max(element.wall_length, 1.0)
    line_p = service.P / wall_length
    line_mx = service.Mx / wall_length
    line_my = service.My / wall_length
    depth = _minimum_depth(element, borehole, options)
    thickness = max(options.min_thickness_soil / 1000.0, 0.45)
    wall_t = max(element.wall_thickness, 0.10)
    B = max(options.min_footing_dim, math.sqrt(max(line_p / max(q_allow, 1e-6), 0.0)))
    B = ceil_to(B, options.footing_dim_step)
    pressure = pressure_distribution(line_p, line_mx, line_my, 1.0, B)
    for _ in range(100):
        if pressure.q_max <= q_allow and pressure.kern_ok:
            break
        B += options.footing_dim_step
        pressure = pressure_distribution(line_p, line_mx, line_my, 1.0, B)
        if B > options.max_footing_dim:
            break
    # Structural design per metre.
    self_weight_u = 1.2 * materials.gamma_concrete * B * thickness
    P_u = factored.P / wall_length + self_weight_u
    thickness, shear = _design_thickness(
        P_u, factored.Mx / wall_length, factored.My / wall_length, 1.0, B,
        min(wall_t, B) * 1000.0, 1000.0, materials, options, thickness,
    )
    d = thickness * 1000.0 - materials.cover - 8.0
    q_u_avg = P_u / B
    q_u = pressure_distribution(
        P_u, factored.Mx / wall_length, factored.My / wall_length, 1.0, B
    ).q_max
    projection = max((B * 1000.0 - wall_t * 1000.0) / 2.0, 0.0)
    Mu = max(q_u, q_u_avg) * (projection / 1000.0) ** 2 / 2.0
    fx = flexural_design(Mu, 1000.0, d, thickness * 1000.0, materials.f_c, materials.f_y, materials.phi_flexure)
    bx = select_bars(fx.As_req, materials.bar_diameters, materials.max_bar_spacing, materials.min_bar_spacing)
    long_req = 0.0018 * 1000.0 * thickness * 1000.0
    by = select_bars(long_req, materials.bar_diameters, materials.max_bar_spacing, materials.min_bar_spacing)
    q_service = pressure.q_max
    service_moment = q_service * (projection / 1000.0) ** 2 / 2.0
    crack = _governing_crack(
        service_moment, bx.As_provided, 1000.0, thickness * 1000.0, d,
        materials, bx.diameter, options.crack_width_limit,
    )
    crack_ok = crack.ok if options.crack_check else True
    min_service = _minimum_service(element)
    uplift = check_shallow_uplift(
        borehole, depth, wall_length, B, thickness, min_service.P,
        materials.gamma_concrete, max(min_service.buoyancy, 0.0),
        options.uplift_fs,
    )
    uplift_ok = uplift.ok if options.uplift_check else True
    q_net = max(
        line_p / max(B, 1e-6) + materials.gamma_concrete * thickness
        - vertical_stress(borehole, depth)[2],
        0.0,
    )
    settlement = estimate_shallow_settlement(
        borehole, depth, wall_length, B, q_net, options
    )
    layer = borehole.layer_at_depth(depth) if borehole else None
    stability = check_stability(
        service.P, service.Mx, service.My, service.Vx, service.Vy,
        wall_length, B, depth,
        cohesion=layer.cohesion if layer else 0.0,
        friction_angle=layer.friction_angle if layer else 0.0,
    )
    status = "OK" if (
        pressure.q_max <= q_allow and settlement.ok and stability.ok
        and crack_ok and uplift_ok and fx.ok and bx.ok
    ) else "CHECK"
    notes = []
    if pressure.q_max > q_allow:
        notes.append(f"Bearing pressure {pressure.q_max:.1f} > {q_allow:.1f} kPa")
    if not settlement.ok:
        notes.append(settlement.note)
    if not stability.ok:
        notes.append(stability.note)
    if not crack_ok:
        notes.append(crack.note)
    if not uplift_ok:
        notes.append(uplift.note)
    if not (fx.ok and bx.ok):
        notes.append("Reinforcement/depth check requires attention")
    center_x, center_y = element.center
    return FootingDesign(
        length=wall_length, width=B, thickness=thickness, depth=depth,
        origin_x=center_x - wall_length / 2.0, origin_y=center_y - B / 2.0,
        center_x=center_x, center_y=center_y, angle_deg=element.wall_angle_deg,
        q_service_max=q_service, q_allow=q_allow, q_factored=q_u,
        utilization=max(q_service / max(q_allow, 1e-6), shear.get("punching_vu", 0.0) / max(shear.get("punching_capacity", 1e-6), 1e-6)),
        settlement=settlement.total, settlement_limit=settlement.limit,
        status=status, governing="BNBC 3.8.2 / 6.8 strip footing",
        remarks="; ".join(notes), bottom_x=bx, bottom_y=by, top_x=by, top_y=by,
        Mu_x=Mu, Mu_y=0.0, concrete_volume=wall_length * B * thickness,
        steel_weight=_mat_steel_weight(bx, by, by, by, wall_length, B),
        sliding_fs=stability.sliding_fs,
        overturning_fs=stability.overturning_fs,
        crack_width=crack.width, crack_limit=crack.limit, crack_ok=crack_ok,
        uplift_fs=uplift.fs, uplift=uplift.uplift, uplift_ok=uplift_ok,
        details={"shear": shear, "flexure": fx, "settlement": settlement,
                 "stability": stability, "crack": crack, "uplift": uplift,
                 "local_moments": {"Mx": service.Mx, "My": service.My}},
    )


def design_combined(
    elements: list[Element],
    borehole: Borehole,
    q_allow: float,
    options: FoundationOptions,
    materials: Materials,
) -> FootingDesign:
    """Design a combined footing supporting two or more columns.

    The footing is analysed as a rigid beam with uniform upward factored pressure.
    """
    if not elements:
        return FootingDesign(status="FAIL", remarks="No columns for combined footing")
    from ..bearing import size_combined_footing

    service = {e.id: _governing_service(e) for e in elements}
    loads = [
        (e.center_x, service[e.id].P, service[e.id].Mx, service[e.id].My)
        for e in elements
    ]
    thickness = max(options.min_thickness_soil / 1000.0, 0.60)
    L, B, _origin, _pressure = size_combined_footing(
        loads, q_allow, options, thickness, materials.gamma_concrete
    )
    service_total = sum(r.P for r in service.values())
    mx_total = sum(r.Mx for r in service.values())
    my_total = sum(r.My for r in service.values())
    depth = max(_minimum_depth(e, borehole, options) for e in elements)

    # Place the footing centroid at the resultant of the vertical loads and
    # make the plan cover every column section.  The centre offsets (dx, dy)
    # therefore move the footing, rather than only shifting the reaction
    # moments used by the pressure check.
    x_bar = sum(e.center_x * service[e.id].P for e in elements) / max(service_total, 1e-9)
    y_bar = sum(e.center_y * service[e.id].P for e in elements) / max(service_total, 1e-9)
    clear = 0.30
    x_min = min(e.center_x - e.section_projection_x / 2.0 for e in elements) - clear
    x_max = max(e.center_x + e.section_projection_x / 2.0 for e in elements) + clear
    y_min = min(e.center_y - e.section_projection_y / 2.0 for e in elements) - clear
    y_max = max(e.center_y + e.section_projection_y / 2.0 for e in elements) + clear
    L = ceil_to(max(L, 2.0 * max(x_bar - x_min, x_max - x_bar)),
                options.footing_dim_step)
    B = ceil_to(max(B, 2.0 * max(y_bar - y_min, y_max - y_bar)),
                options.footing_dim_step)
    origin = x_bar - L / 2.0
    center_x = x_bar
    center_y = y_bar
    pressure = pressure_distribution(
        service_total + materials.gamma_concrete * L * B * thickness,
        mx_total, my_total, L, B,
    )

    # Iterate plan width if pressure fails.
    for _ in range(40):
        if pressure.q_max <= q_allow and pressure.kern_ok:
            break
        B += options.footing_dim_step
        pressure = pressure_distribution(service_total + materials.gamma_concrete * L * B * thickness,
                                         mx_total, my_total, L, B)
        if B > options.max_footing_dim:
            break

    # Factored beam analysis along the length.  The contact pressure used for
    # the beam is the net column load divided by the plan area; the footing
    # self-weight increases the gross contact pressure but is balanced by the
    # downward self-weight and therefore does not bend the footing.
    factored = [(e, _governing_factored(e)) for e in elements]
    column_load_u = sum(r.P for _, r in factored)
    self_weight_u = 1.2 * materials.gamma_concrete * L * B * thickness
    P_u = column_load_u + self_weight_u
    q_u = P_u / max(L * B, 1e-6)
    q_beam = column_load_u / max(L * B, 1e-6)
    # Include the global moment as a linear variation of the upward line load,
    # so the beam envelope sees the pressure peak instead of only the average.
    line_avg = column_load_u / max(L, 1e-9)
    line_moment = 6.0 * abs(my_total) / max(L * L, 1e-9)
    line_start = max(line_avg - line_moment, 0.0)
    line_end = line_avg + line_moment
    # Exact shear/moment envelope for the free-free beam.
    M_pos, M_neg = _beam_moment_envelope(
        origin, L, line_start,
        [(e.center_x, r.P) for e, r in factored],
        line_load_end=line_end,
    )
    Mu_long = max(abs(M_pos), 0.0) / max(B, 0.1)  # kN.m per metre width, bottom
    Mu_top = max(abs(M_neg), 0.0) / max(B, 0.1)   # kN.m per metre width, top
    # Transverse design at the most heavily loaded column.
    heaviest = max(elements, key=lambda e: _governing_service(e).P)
    c_l = heaviest.section_projection_x * 1000.0
    c_b = heaviest.section_projection_y * 1000.0
    thickness, shear_details = _design_thickness(
        P_u, mx_total, my_total, L, B,
        c_l, c_b, materials, options, thickness,
    )
    d = thickness * 1000.0 - materials.cover - 8.0
    q_u_max = P_u / (L * B) + abs(mx_total) / (L * B * B / 6.0) + abs(my_total) / (B * L * L / 6.0)
    b = max((B * 1000.0 - c_b) / 2.0, 0.0)
    Mu_trans = q_u_max * (b / 1000.0) ** 2 / 2.0
    fx = flexural_design(Mu_long, 1000.0, d, thickness * 1000.0, materials.f_c, materials.f_y, materials.phi_flexure)
    fy = flexural_design(Mu_trans, 1000.0, d, thickness * 1000.0, materials.f_c, materials.f_y, materials.phi_flexure)
    bx = select_bars(fx.As_req, materials.bar_diameters, materials.max_bar_spacing, materials.min_bar_spacing)
    by = select_bars(fy.As_req, materials.bar_diameters, materials.max_bar_spacing, materials.min_bar_spacing)
    d_top = max(thickness * 1000.0 - 50.0 - 8.0, 50.0)
    f_top = flexural_design(Mu_top, 1000.0, d_top, thickness * 1000.0,
                            materials.f_c, materials.f_y, materials.phi_flexure)
    top = select_bars(max(f_top.As_req, 0.0018 * 1000.0 * thickness * 1000.0 * 0.5),
                      materials.bar_diameters, materials.max_bar_spacing, materials.min_bar_spacing)
    q_service = pressure.q_max
    # Service beam moments for crack control (net column load only).
    column_service = sum(service[e.id].P for e in elements)
    m_pos_s, m_neg_s = _beam_moment_envelope(
        origin, L, column_service / max(L, 1e-9),
        [(e.center_x, service[e.id].P) for e in elements],
    )
    crack_long = _governing_crack(
        max(abs(m_pos_s), 0.0) / max(B, 0.1), bx.As_provided,
        1000.0, thickness * 1000.0, d, materials, bx.diameter,
        options.crack_width_limit,
    )
    crack_top = _governing_crack(
        max(abs(m_neg_s), 0.0) / max(B, 0.1), top.As_provided,
        1000.0, thickness * 1000.0, d_top, materials, top.diameter,
        options.crack_width_limit,
    )
    crack_trans = _governing_crack(
        q_service * (b / 1000.0) ** 2 / 2.0, by.As_provided,
        1000.0, thickness * 1000.0, d, materials, by.diameter,
        options.crack_width_limit,
    )
    crack = max((crack_long, crack_top, crack_trans), key=lambda c: c.width)
    crack_ok = all(c.ok for c in (crack_long, crack_top, crack_trans)) or not options.crack_check
    min_total = sum(_minimum_service(e).P for e in elements)
    buoyancy = sum(max(_minimum_service(e).buoyancy, 0.0) for e in elements)
    uplift = check_shallow_uplift(
        borehole, depth, L, B, thickness, min_total,
        materials.gamma_concrete, buoyancy, options.uplift_fs,
    )
    uplift_ok = uplift.ok if options.uplift_check else True
    q_net = max(pressure.q_avg - vertical_stress(borehole, depth)[2], 0.0)
    settlement = estimate_shallow_settlement(borehole, depth, L, B, q_net, options)
    layer = borehole.layer_at_depth(depth) if borehole else None
    stability = check_stability(
        service_total, mx_total, my_total,
        sum(r.Vx for r in service.values()), sum(r.Vy for r in service.values()),
        L, B, depth,
        cohesion=layer.cohesion if layer else 0.0,
        friction_angle=layer.friction_angle if layer else 0.0,
    )
    status = "OK" if (
        q_service <= q_allow and settlement.ok and stability.ok
        and crack_ok and uplift_ok
        and fx.ok and fy.ok and f_top.ok
        and bx.ok and by.ok and top.ok
    ) else "CHECK"
    notes = []
    if q_service > q_allow:
        notes.append(f"Bearing pressure {q_service:.1f} > {q_allow:.1f} kPa")
    if not settlement.ok:
        notes.append(settlement.note)
    if not stability.ok:
        notes.append(stability.note)
    if not crack_ok:
        notes.append(crack.note)
    if not uplift_ok:
        notes.append(uplift.note)
    if not (fx.ok and fy.ok and f_top.ok and bx.ok and by.ok and top.ok):
        notes.append("Reinforcement/depth check requires attention")
    if L > options.max_footing_dim + 1e-9 or B > options.max_footing_dim + 1e-9:
        notes.append(
            f"Combined footing {L:.2f} x {B:.2f} m exceeds the "
            f"{options.max_footing_dim:.2f} m plan limit"
        )
        status = "FAIL"
    return FootingDesign(
        length=L, width=B, thickness=thickness, depth=depth,
        origin_x=origin, origin_y=center_y - B / 2.0,
        center_x=center_x, center_y=center_y, angle_deg=0.0,
        q_service_max=q_service, q_allow=q_allow, q_factored=q_u,
        utilization=max(q_service / max(q_allow, 1e-6), shear_details.get("punching_vu", 0.0) /
                        max(shear_details.get("punching_capacity", 1e-6), 1e-6)),
        settlement=settlement.total, settlement_limit=settlement.limit,
        status=status, governing="BNBC 3.9.6.2 combined footing; 6.8 flexure/shear",
        remarks="; ".join(notes), bottom_x=bx, bottom_y=by, top_x=top, top_y=by,
        Mu_x=Mu_long, Mu_y=Mu_trans, concrete_volume=L * B * thickness,
        steel_weight=_mat_steel_weight(bx, by, top, by, L, B),
        sliding_fs=stability.sliding_fs,
        overturning_fs=stability.overturning_fs,
        crack_width=crack.width, crack_limit=crack.limit, crack_ok=crack_ok,
        uplift_fs=uplift.fs, uplift=uplift.uplift, uplift_ok=uplift_ok,
        details={"shear": shear_details, "moment_envelope": (M_pos, M_neg),
                 "beam_net_pressure": q_beam,
                 "self_weight_factored": self_weight_u,
                 "flexure_long": fx, "flexure_trans": fy, "flexure_top": f_top,
                 "settlement": settlement, "stability": stability,
                 "crack_long": crack_long, "crack_top": crack_top,
                 "crack_trans": crack_trans, "uplift": uplift},
    )
