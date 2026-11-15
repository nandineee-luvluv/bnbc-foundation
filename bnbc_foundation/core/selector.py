"""Foundation selection, ranking and project-level design orchestration."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

from .models import (
    Borehole,
    DesignResult,
    Element,
    FoundationOptions,
    Materials,
    Project,
    _clean,
)
from .geometry import (
    distance_between_polygons,
    polygon_bounds,
    polygon_within_rect,
    polygons_overlap,
    rectangle_polygon,
    rotated_rectangle_polygon,
)
from .loads import governing_factored, governing_service
from .piles import (
    PileGroupDesign,
    design_pile_group,
    single_pile_design,
)
from .structural.concrete import pile_pm_interaction
from .rebar import layout_dict
from .settlement import differential_ok
from .soil import (
    allowable_bearing_pressure,
    liquefaction_assessment,
    liquefaction_susceptible_layers,
    presumptive_bearing,
    soil_modulus,
)
from .structural.footing import (
    design_combined,
    design_isolated,
    design_strip,
)
from .structural.pilecap import design_pilecap
from .structural.raft_design import design_raft


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    result: DesignResult
    kind: str
    rect: tuple[float, float, float, float]
    cost: float = 0.0
    polygon: list[tuple[float, float]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.polygon:
            self.polygon = rectangle_polygon(*self.rect)


@dataclass
class DesignRun:
    results: list[DesignResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _min_depth(element: Element, borehole: Borehole, options: FoundationOptions) -> float:
    base = max(abs(min(element.base_elev, 0.0)), options.min_depth_general)
    layer = borehole.layer_at_depth(base + 0.10)
    cohesive = layer.is_cohesive() if layer else True
    required = options.min_depth_cohesive if cohesive else options.min_depth_cohesionless
    return max(base, required)


def _q_allow(
    element: Element,
    borehole: Borehole,
    options: FoundationOptions,
    load: float | None = None,
) -> tuple[float, float]:
    depth = _min_depth(element, borehole, options)
    p = max(load if load is not None else governing_service(element).P, 1.0)
    trial = max(1.0, math.sqrt(p / 150.0))
    q = allowable_bearing_pressure(borehole, depth, trial, trial, options.fs_shallow)
    if q <= 0:
        layer = borehole.layer_at_depth(depth)
        q = presumptive_bearing(layer.soil_type) if layer else 100.0
    return max(q, 10.0), depth


def _q_allow_pair(
    elements: list[Element],
    borehole: Borehole,
    options: FoundationOptions,
) -> tuple[float, float]:
    depth = max(_min_depth(e, borehole, options) for e in elements)
    p = sum(max(governing_service(e).P, 0.0) for e in elements)
    trial = max(1.0, math.sqrt(max(p, 1.0) / 120.0))
    q = allowable_bearing_pressure(borehole, depth, trial, trial, options.fs_shallow)
    if q <= 0:
        layer = borehole.layer_at_depth(depth)
        q = presumptive_bearing(layer.soil_type) if layer else 100.0
    return max(q, 10.0), depth


def _footprint(rect: tuple[float, float, float, float]) -> list[tuple[float, float]]:
    return rectangle_polygon(*rect)


def _site_polygon_ok(
    polygon: list[tuple[float, float]], options: FoundationOptions
) -> bool:
    if options.site_xmax - options.site_xmin >= 5000.0:
        return True
    if options.site_ymax - options.site_ymin >= 5000.0:
        return True
    return polygon_within_rect(
        polygon, (options.site_xmin, options.site_ymin, options.site_xmax, options.site_ymax)
    )


def _rect_from_oriented(
    center_x: float,
    center_y: float,
    length: float,
    width: float,
    angle_deg: float = 0.0,
) -> tuple[tuple[float, float, float, float], list[tuple[float, float]]]:
    polygon = rotated_rectangle_polygon(center_x, center_y, length, width, angle_deg)
    return polygon_bounds(polygon), polygon


def _wall_width_limit(
    element: Element,
    blocked: list[tuple[float, float, float, float]],
    clearance: float = 0.10,
) -> float | None:
    """Largest symmetric wall-cap width that clears nearby foundations.

    Obstacles are projected onto wall-local axes (u along the wall, v normal to
    it). Only obstacles overlapping the projected cap length are considered. A
    wall whose centreline passes through an obstacle returns zero.
    """
    if element.kind != "wall":
        return None
    cx, cy = element.center
    theta = math.radians(element.wall_angle_deg)
    ux, uy = math.cos(theta), math.sin(theta)
    vx, vy = -uy, ux
    half_length = element.wall_length / 2.0 + 0.75
    below_top: float | None = None
    above_bottom: float | None = None
    for rect in blocked:
        x0, y0, x1, y1 = rect
        corners = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        u_vals = [((x - cx) * ux + (y - cy) * uy) for x, y in corners]
        v_vals = [((x - cx) * vx + (y - cy) * vy) for x, y in corners]
        if max(u_vals) + clearance < -half_length or min(u_vals) - clearance > half_length:
            continue
        v_min, v_max = min(v_vals), max(v_vals)
        if v_min <= 0.0 <= v_max:
            return 0.0
        if v_max <= 0.0:
            below_top = v_max if below_top is None else max(below_top, v_max)
        else:
            above_bottom = v_min if above_bottom is None else min(above_bottom, v_min)
    half_limits = []
    if below_top is not None:
        half_limits.append(abs(below_top) - clearance)
    if above_bottom is not None:
        half_limits.append(above_bottom - clearance)
    if not half_limits:
        return None
    return max(0.0, 2.0 * min(half_limits))


def _cost(result: DesignResult, options: FoundationOptions) -> float:
    area = max(result.length, 0.0) * max(result.width, 0.0)
    cost = result.concrete_volume * options.cost_concrete
    cost += area * max(result.depth, 0.0) * options.cost_excavation
    cost += result.steel_weight * options.cost_steel
    cost += result.pile_length_total * options.cost_pile
    if "raft" in result.foundation_type.lower():
        cost += area * options.cost_raft
    return cost


def _pile_volume(diameter: float, length: float) -> float:
    return math.pi * diameter ** 2 / 4.0 * length


def _pile_steel_kg(diameter: float, length: float, count: int) -> float:
    if diameter <= 0.50:
        ratio = 0.005
    elif diameter <= 1.00:
        ratio = 0.00375
    else:
        ratio = 0.0025
    return _pile_volume(diameter, length) * count * ratio * 7850.0


def _merged_remarks(*parts: str) -> str:
    """Join remark fragments, dropping duplicates and empty entries."""
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        for chunk in str(part or "").split(";"):
            chunk = chunk.strip()
            if chunk and chunk not in seen:
                seen.add(chunk)
                out.append(chunk)
    return "; ".join(out)


def _pile_result_remarks(group, limit: float, cap) -> str:
    notes = [group.note]
    if group.settlement > limit + 1e-6:
        notes.append(
            f"Group settlement {group.settlement:.1f} mm > {limit:.1f} mm"
        )
    if not group.uplift_ok:
        notes.append("Pile uplift capacity is insufficient")
    if not group.lateral_ok:
        notes.append("Pile lateral capacity is insufficient")
    if not group.pm_ok:
        notes.append("Pile P-M interaction check fails")
    return _merged_remarks(*notes, cap.remarks)


def _single_pile_settlement(
    element: Element, borehole: Borehole, diameter: float, length: float
) -> float:
    layer = borehole.layer_at_depth(length)
    if layer is None:
        return 0.0
    es = soil_modulus(borehole, layer, max(length - 1.0, 0.0))
    area = math.pi * diameter ** 2 / 4.0
    q = max(governing_service(element).P, 1.0) / max(area, 0.01)
    return q * diameter * (1.0 - 0.30 ** 2) / max(es, 1.0) * 1000.0


def _settlement_limit(borehole: Borehole, length: float, options: FoundationOptions) -> float:
    layer = borehole.layer_at_depth(length)
    if layer is not None and layer.is_cohesive():
        return options.settlement_limit_clay
    return options.settlement_limit_sand


def _rebar_layouts(design) -> dict:
    keys = ("bottom_x", "bottom_y", "top_x", "top_y")
    return {
        key: layout_dict(getattr(design, key))
        for key in keys
        if hasattr(design, key) and getattr(design, key) is not None
    }


def _load_summary(elements: list[Element]) -> dict:
    service_p = sum(governing_service(e).P for e in elements)
    factored_p = sum(governing_factored(e).P for e in elements)
    return {
        "service": {
            "P": service_p,
            "Mx": sum(governing_service(e).Mx for e in elements),
            "My": sum(governing_service(e).My for e in elements),
            "cases": [governing_service(e).case for e in elements],
        },
        "factored": {
            "P": factored_p,
            "Mx": sum(governing_factored(e).Mx for e in elements),
            "My": sum(governing_factored(e).My for e in elements),
            "cases": [governing_factored(e).case for e in elements],
        },
    }


def _result_common(
    result: DesignResult,
    elements: list[Element],
    options: FoundationOptions,
    rect: tuple[float, float, float, float],
    polygon: list[tuple[float, float]] | None = None,
) -> Candidate:
    result.covers = [e.id for e in elements] if not result.covers else result.covers
    polygon = list(polygon or _footprint(rect))
    result.cost = _cost(result, options)
    result.details.setdefault("rect", list(rect))
    result.details.setdefault("footprint", polygon)
    result.details.setdefault("site_ok", _site_polygon_ok(polygon, options))
    result.details.setdefault("loads", _load_summary(elements))
    if not result.details.get("site_ok"):
        result.status = "FAIL" if result.status == "OK" else result.status
        note = "Footing/foundation extends beyond the site boundary"
        result.remarks = f"{result.remarks}; {note}".strip("; ")
    return Candidate(
        result=result, kind=result.foundation_type, rect=rect,
        cost=result.cost, polygon=polygon,
    )


# ---------------------------------------------------------------------------
# Candidate design functions
# ---------------------------------------------------------------------------


def _try_isolated(
    element: Element,
    borehole: Borehole,
    options: FoundationOptions,
    materials: Materials,
) -> Candidate | None:
    if not options.allow_isolated:
        return None
    q_allow, depth = _q_allow(element, borehole, options)
    design = design_isolated(element, borehole, q_allow, options, materials)
    result = DesignResult(
        element_id=element.id,
        element_kind="column",
        foundation_type="Isolated footing",
        requirement=(
            f"Support {element.id}: service P={governing_service(element).P:.0f} kN, "
            f"Mx={governing_service(element).Mx:.0f} kN.m, My={governing_service(element).My:.0f} kN.m; "
            f"q_allow={q_allow:.1f} kPa"
        ),
        quantity=1,
        size=(
            f"{design.length:.2f} x {design.width:.2f} m, "
            f"t={design.thickness * 1000:.0f} mm, depth={design.depth:.2f} m"
        ),
        length=design.length, width=design.width,
        thickness=design.thickness * 1000.0, depth=design.depth,
        service_load=governing_service(element).P,
        factored_load=governing_factored(element).P,
        q_service_max=design.q_service_max, q_allow=design.q_allow,
        utilization=design.utilization,
        settlement=design.settlement, settlement_limit=design.settlement_limit,
        status=design.status, governing=design.governing, remarks=design.remarks,
        concrete_volume=design.concrete_volume, steel_weight=design.steel_weight,
    )
    result.details.update({
        "design": _clean(asdict(design)),
        "rebar_layouts": _rebar_layouts(design),
        "checks": {
            "bearing_utilization": design.q_service_max / max(design.q_allow, 1e-6),
            "settlement_ok": design.settlement <= design.settlement_limit + 1e-6,
            "sliding_fs": design.sliding_fs,
            "overturning_fs": design.overturning_fs,
            "crack_width": design.crack_width,
            "crack_ok": design.crack_ok,
            "uplift_fs": design.uplift_fs,
            "uplift_ok": design.uplift_ok,
        },
    })
    rect, polygon = _rect_from_oriented(
        design.center_x, design.center_y, design.length, design.width, design.angle_deg
    )
    return _result_common(result, [element], options, rect, polygon)


def _try_strip(
    element: Element,
    borehole: Borehole,
    options: FoundationOptions,
    materials: Materials,
) -> Candidate | None:
    if not options.allow_strip:
        return None
    q_allow, _ = _q_allow(element, borehole, options)
    design = design_strip(element, borehole, q_allow, options, materials)
    result = DesignResult(
        element_id=element.id,
        element_kind="wall",
        foundation_type="Strip footing",
        requirement=(
            f"Support shear wall {element.id}: service P={governing_service(element).P:.0f} kN, "
            f"Mx={governing_service(element).Mx:.0f} kN.m, My={governing_service(element).My:.0f} kN.m; "
            f"q_allow={q_allow:.1f} kPa"
        ),
        quantity=1,
        size=(
            f"{design.length:.2f} x {design.width:.2f} m, "
            f"t={design.thickness * 1000:.0f} mm, depth={design.depth:.2f} m"
        ),
        length=design.length, width=design.width,
        thickness=design.thickness * 1000.0, depth=design.depth,
        service_load=governing_service(element).P,
        factored_load=governing_factored(element).P,
        q_service_max=design.q_service_max, q_allow=design.q_allow,
        utilization=design.utilization,
        settlement=design.settlement, settlement_limit=design.settlement_limit,
        status=design.status, governing=design.governing, remarks=design.remarks,
        concrete_volume=design.concrete_volume, steel_weight=design.steel_weight,
    )
    result.details.update({
        "design": _clean(asdict(design)),
        "rebar_layouts": _rebar_layouts(design),
        "checks": {
            "bearing_utilization": design.q_service_max / max(design.q_allow, 1e-6),
            "settlement_ok": design.settlement <= design.settlement_limit + 1e-6,
            "crack_width": design.crack_width,
            "crack_ok": design.crack_ok,
            "uplift_fs": design.uplift_fs,
            "uplift_ok": design.uplift_ok,
        },
    })
    rect, polygon = _rect_from_oriented(
        design.center_x, design.center_y, design.length, design.width, design.angle_deg
    )
    return _result_common(result, [element], options, rect, polygon)


def _try_combined(
    first: Element,
    second: Element,
    borehole: Borehole,
    options: FoundationOptions,
    materials: Materials,
) -> Candidate | None:
    if not options.allow_combined:
        return None
    q_allow, _ = _q_allow_pair([first, second], borehole, options)
    design = design_combined([first, second], borehole, q_allow, options, materials)
    result = DesignResult(
        element_id=f"{first.id}+{second.id}",
        element_kind="combined",
        foundation_type="Combined footing",
        requirement=(
            f"Support {first.id}+{second.id}: total service P="
            f"{governing_service(first).P + governing_service(second).P:.0f} kN; "
            f"q_allow={q_allow:.1f} kPa"
        ),
        quantity=1,
        size=(
            f"{design.length:.2f} x {design.width:.2f} m, "
            f"t={design.thickness * 1000:.0f} mm, depth={design.depth:.2f} m"
        ),
        length=design.length, width=design.width,
        thickness=design.thickness * 1000.0, depth=design.depth,
        service_load=governing_service(first).P + governing_service(second).P,
        factored_load=governing_factored(first).P + governing_factored(second).P,
        q_service_max=design.q_service_max, q_allow=design.q_allow,
        utilization=design.utilization,
        settlement=design.settlement, settlement_limit=design.settlement_limit,
        status=design.status, governing=design.governing, remarks=design.remarks,
        concrete_volume=design.concrete_volume, steel_weight=design.steel_weight,
        covers=[first.id, second.id],
    )
    result.details.update({
        "design": _clean(asdict(design)),
        "rebar_layouts": _rebar_layouts(design),
        "combined_elements": [first.id, second.id],
        "checks": {
            "bearing_utilization": design.q_service_max / max(design.q_allow, 1e-6),
            "settlement_ok": design.settlement <= design.settlement_limit + 1e-6,
            "crack_width": design.crack_width,
            "crack_ok": design.crack_ok,
            "uplift_fs": design.uplift_fs,
            "uplift_ok": design.uplift_ok,
        },
    })
    rect, polygon = _rect_from_oriented(
        design.center_x, design.center_y, design.length, design.width, design.angle_deg
    )
    return _result_common(result, [first, second], options, rect, polygon)


def _try_single_pile(
    element: Element,
    borehole: Borehole,
    options: FoundationOptions,
    materials: Materials,
) -> Candidate | None:
    if not options.allow_single_pile or element.kind == "wall":
        return None
    found = single_pile_design(
        element, borehole, options, materials.f_c, materials.f_y,
    )
    if found is None:
        return None
    pile, message = found
    service = governing_service(element)
    moment = math.hypot(service.Mx, service.My)
    # A single pile is only sensible for modest base moments; larger moments
    # require a group or a pile designed for P-M.
    if moment > 0.40 * max(service.P, 1.0) * max(pile.diameter, 0.1):
        return None
    cap_length = pile.diameter + 2.0 * options.cap_edge_cover
    cap_thickness = max(options.cap_min_thickness / 1000.0, 0.75 * pile.diameter)
    settlement = _single_pile_settlement(element, borehole, pile.diameter, pile.length)
    limit = _settlement_limit(borehole, pile.length, options)
    tension = max(-service.P, 0.0)
    uplift_util = tension / max(pile.uplift_capacity, 1e-9)
    lateral_per_pile = math.hypot(service.Vx, service.Vy)
    lateral_util = lateral_per_pile / max(pile.lateral_capacity, 1e-9)
    pm = pile_pm_interaction(
        pile.diameter, max(service.P, 0.0), moment,
        materials.f_c, materials.f_y, options.pile_type,
    )
    uplift_ok = not options.uplift_check or uplift_util <= 1.0 + 1e-9
    lateral_ok = not options.pile_lateral_check or lateral_util <= 1.0 + 1e-9
    pm_ok = not options.pile_pm_check or pm.ok
    status = "OK" if (
        service.P <= pile.allowable and settlement <= limit
        and uplift_ok and lateral_ok and pm_ok
    ) else "CHECK"
    group = PileGroupDesign(
        count=1, diameter=pile.diameter, length=pile.length, spacing=0.0,
        cap_length=cap_length, cap_width=cap_length, cap_thickness=cap_thickness,
        positions=[(0.0, 0.0)], max_pile_load=service.P, min_pile_load=service.P,
        group_capacity=pile.allowable, block_capacity=pile.allowable, efficiency=1.0,
        utilization=max(service.P / max(pile.allowable, 1e-6), uplift_util,
                        lateral_util, pm.utilization),
        settlement=settlement, status=status, note=message,
        downdrag=pile.downdrag, uplift_utilization=uplift_util,
        lateral_utilization=lateral_util, pm_utilization=pm.utilization,
        uplift_ok=uplift_ok, lateral_ok=lateral_ok, pm_ok=pm_ok,
    )
    cap = design_pilecap(element, group, materials, options)
    result = DesignResult(
        element_id=element.id,
        element_kind="column",
        foundation_type="Single pile",
        requirement=(
            f"One pile under {element.id}: service P={service.P:.0f} kN; "
            f"allowable pile capacity={pile.allowable:.0f} kN; FS={pile.fs:.1f}"
        ),
        quantity=1,
        size=(
            f"1 x diameter {pile.diameter * 1000:.0f} mm, L={pile.length:.1f} m; "
            f"cap {cap.length:.2f} x {cap.width:.2f} x {cap.thickness * 1000:.0f} mm"
        ),
        length=cap.length, width=cap.width, thickness=cap.thickness * 1000.0,
        depth=max(abs(element.base_elev), 1.0) + cap.thickness,
        pile_diameter=pile.diameter, pile_length=pile.length, pile_count=1,
        cap_length=cap.length, cap_width=cap.width, cap_thickness=cap.thickness * 1000.0,
        service_load=service.P, factored_load=governing_factored(element).P,
        q_service_max=group.max_pile_load,
        q_allow=group.group_capacity / max(group.count, 1),
        utilization=max(cap.utilization, group.utilization),
        settlement=settlement, settlement_limit=limit,
        status="OK" if cap.status == "OK" and status == "OK" else "CHECK",
        governing="BNBC 3.10.4 bored pile; 6.8.5 pile cap",
        remarks=_pile_result_remarks(group, limit, cap),
        concrete_volume=cap.concrete_volume + _pile_volume(pile.diameter, pile.length),
        steel_weight=cap.steel_weight + _pile_steel_kg(pile.diameter, pile.length, 1),
        pile_length_total=pile.length,
    )
    result.details.update({
        "design": _clean(asdict(cap)),
        "pile_group": _clean(asdict(group)),
        "pile_capacity": _clean(asdict(pile)),
        "rebar_layouts": _rebar_layouts(cap),
        "checks": {
            "pile_utilization": group.utilization,
            "cap_utilization": cap.utilization,
            "settlement_ok": settlement <= limit + 1e-6,
            "uplift_utilization": group.uplift_utilization,
            "lateral_utilization": group.lateral_utilization,
            "pm_utilization": group.pm_utilization,
            "downdrag": group.downdrag,
            "uplift_ok": group.uplift_ok,
            "lateral_ok": group.lateral_ok,
            "pm_ok": group.pm_ok,
            "crack_width": cap.crack_width,
            "crack_ok": cap.crack_ok,
        },
    })
    rect, polygon = _rect_from_oriented(
        cap.center_x, cap.center_y, cap.length, cap.width, cap.angle_deg
    )
    return _result_common(result, [element], options, rect, polygon)


def _try_pile_group(
    element: Element,
    borehole: Borehole,
    options: FoundationOptions,
    materials: Materials,
    cap_width_limit: float | None = None,
) -> Candidate | None:
    if not options.allow_pile_group:
        return None
    found = design_pile_group(
        element, borehole, options, materials.f_c, materials.f_y,
        cap_width_limit=cap_width_limit,
    )
    if found is None:
        return None
    group, pile = found
    cap = design_pilecap(element, group, materials, options)
    limit = _settlement_limit(borehole, group.length, options)
    service = governing_service(element)
    result = DesignResult(
        element_id=element.id,
        element_kind=element.kind,
        foundation_type="Pile group with cap",
        requirement=(
            f"Support {element.id}: service P={service.P:.0f} kN; "
            f"{group.count} x diameter {group.diameter * 1000:.0f} mm piles at "
            f"{group.spacing:.2f} m spacing; allowable per pile={pile.allowable:.0f} kN"
        ),
        quantity=1,
        size=(
            f"{group.count} x diameter {group.diameter * 1000:.0f} mm, L={group.length:.1f} m; "
            f"cap {cap.length:.2f} x {cap.width:.2f} x {cap.thickness * 1000:.0f} mm"
        ),
        length=cap.length, width=cap.width, thickness=cap.thickness * 1000.0,
        depth=max(abs(element.base_elev), 1.0) + cap.thickness,
        pile_diameter=group.diameter, pile_length=group.length, pile_count=group.count,
        cap_length=cap.length, cap_width=cap.width, cap_thickness=cap.thickness * 1000.0,
        service_load=service.P, factored_load=governing_factored(element).P,
        q_service_max=group.max_pile_load,
        q_allow=group.group_capacity / max(group.count, 1),
        utilization=max(cap.utilization, group.utilization),
        settlement=group.settlement, settlement_limit=limit,
        status="OK" if cap.status == "OK" and group.status == "OK" else "CHECK",
        governing="BNBC 3.10.1/3.10.4 piles; 6.8.5 pile cap",
        remarks=_pile_result_remarks(group, limit, cap),
        concrete_volume=cap.concrete_volume + group.count * _pile_volume(group.diameter, group.length),
        steel_weight=cap.steel_weight + _pile_steel_kg(group.diameter, group.length, group.count),
        pile_length_total=group.count * group.length,
    )
    result.details.update({
        "design": _clean(asdict(cap)),
        "pile_group": _clean(asdict(group)),
        "pile_capacity": _clean(asdict(pile)),
        "rebar_layouts": _rebar_layouts(cap),
        "checks": {
            "pile_utilization": group.utilization,
            "cap_utilization": cap.utilization,
            "settlement_ok": group.settlement <= limit + 1e-6,
            "block_capacity": group.block_capacity,
            "uplift_utilization": group.uplift_utilization,
            "lateral_utilization": group.lateral_utilization,
            "pm_utilization": group.pm_utilization,
            "downdrag": group.downdrag,
            "uplift_ok": group.uplift_ok,
            "lateral_ok": group.lateral_ok,
            "pm_ok": group.pm_ok,
            "crack_width": cap.crack_width,
            "crack_ok": cap.crack_ok,
        },
    })
    rect, polygon = _rect_from_oriented(
        cap.center_x, cap.center_y, cap.length, cap.width, cap.angle_deg
    )
    return _result_common(result, [element], options, rect, polygon)


def _try_raft(
    project: Project,
    borehole: Borehole,
    q_allow: float,
    method: str | None = None,
) -> Candidate | None:
    options = project.options
    if not options.allow_raft:
        return None
    design = design_raft(
        project.elements, borehole, q_allow, options, project.materials, method=method,
    )
    analysis = design.analysis
    result = DesignResult(
        element_id="RAFT-1",
        element_kind="raft",
        foundation_type="Raft",
        requirement=(
            f"Global raft supporting {len(project.elements)} elements; "
            f"total service P={analysis.service_load:.0f} kN; q_allow={q_allow:.1f} kPa; "
            f"analysis={analysis.method}"
        ),
        quantity=1,
        size=(
            f"Raft {analysis.length:.2f} x {analysis.width:.2f} m, "
            f"t={design.thickness * 1000:.0f} mm, depth={analysis.depth:.2f} m"
        ),
        length=analysis.length, width=analysis.width,
        thickness=design.thickness * 1000.0, depth=analysis.depth,
        service_load=analysis.service_load, factored_load=analysis.factored_load,
        q_service_max=analysis.q_service_max, q_allow=q_allow,
        utilization=design.utilization,
        settlement=analysis.settlement, settlement_limit=analysis.settlement_limit,
        status=design.status, governing=design.governing, remarks=design.remarks,
        concrete_volume=design.concrete_volume, steel_weight=design.steel_weight,
        covers=[e.id for e in project.elements],
    )
    rect = (analysis.x0, analysis.y0, analysis.x0 + analysis.length, analysis.y0 + analysis.width)
    outline = [tuple(p) for p in (analysis.outline or [])]
    result.details.update({
        "design": _clean(asdict(design)),
        "raft_analysis": _clean(asdict(analysis)),
        "rebar_layouts": _rebar_layouts(design),
        "checks": {
            "bearing_utilization": analysis.q_service_max / max(q_allow, 1e-6),
            "settlement_ok": analysis.settlement <= analysis.settlement_limit + 1e-6,
            "shear_utilization": design.shear_utilization,
            "punching_utilization": design.punching_utilization,
            "flexure_utilization": design.flexure_utilization,
            "crack_width": design.crack_width,
            "crack_ok": design.crack_ok,
            "uplift": analysis.buoyancy_uplift,
            "outline_vertices": len(outline),
            "outline_area": analysis.area,
        },
    })
    return _result_common(result, project.elements, options, rect, outline or None)


# ---------------------------------------------------------------------------
# Ranking and orchestration
# ---------------------------------------------------------------------------


def _preference_key(result: DesignResult, order: dict[str, int]) -> int:
    ftype = result.foundation_type
    for name, rank in order.items():
        if name.lower() in ftype.lower():
            return rank
    return 99


def _clash_count(
    polygon: list[tuple[float, float]],
    blocked: list[list[tuple[float, float]]],
    clearance: float = 0.10,
) -> int:
    return sum(1 for other in blocked if polygons_overlap(polygon, other, clearance))


def _choose(
    candidates: list[Candidate],
    options: FoundationOptions,
    order: dict[str, int],
    preferred: str = "Auto",
    blocked: list[list[tuple[float, float]]] | None = None,
) -> Candidate | None:
    if not candidates:
        return None
    blocked = blocked or []
    pool = candidates
    if preferred and preferred.lower() != "auto":
        wanted = preferred.lower()
        matched = [c for c in candidates if wanted in c.result.foundation_type.lower()]
        if matched:
            pool = matched
    if options.optimize_cost:
        feasible = [
            c for c in pool
            if c.result.status == "OK" and c.cost > 0
            and _clash_count(c.polygon, blocked) == 0
            and _site_polygon_ok(c.polygon, options)
        ]
        if feasible:
            return min(feasible, key=lambda c: c.cost)
    status_rank = {"OK": 0, "CHECK": 1, "FAIL": 2}

    def key(c: Candidate):
        return (
            _clash_count(c.polygon, blocked),
            0 if _site_polygon_ok(c.polygon, options) else 1,
            status_rank.get(c.result.status, 3),
            _preference_key(c.result, order),
            c.cost if c.cost > 0 else 0.0,
            c.result.utilization,
        )

    return min(pool, key=key)


def _alternative_texts(candidates: list[Candidate], chosen: Candidate) -> list[str]:
    out = []
    for candidate in candidates:
        if candidate is chosen:
            continue
        r = candidate.result
        out.append(
            f"{r.foundation_type}: {r.size} | util {r.utilization:.2f} | {r.status}"
        )
    return out[:5]


def _nearest_partner(
    element: Element,
    elements: list[Element],
    covered: set[str],
    options: FoundationOptions,
) -> Element | None:
    others = [
        e for e in elements
        if e.id != element.id and e.id not in covered and e.kind == "column"
    ]
    if not others:
        return None
    partner = min(
        others,
        key=lambda e: (e.center_x - element.center_x) ** 2
        + (e.center_y - element.center_y) ** 2,
    )
    distance = math.hypot(
        partner.center_x - element.center_x, partner.center_y - element.center_y
    )
    if distance > max(options.max_footing_dim * 1.5, 8.0):
        return None
    return partner


def _append_liquefaction_warnings(project: Project, warnings: list[str]) -> None:
    """Add SPT liquefaction screening results or a missing-PGA warning."""
    options = project.options
    if options.pga_g and options.pga_g > 0:
        for borehole in project.boreholes:
            for item in liquefaction_assessment(borehole, options.pga_g):
                if item.triggered:
                    warnings.append(
                        f"{borehole.id}: liquefaction FS {item.fs:.2f} < 1.0 at "
                        f"{item.top:.1f}-{item.bottom:.1f} m ({item.soil_type})."
                    )
        return
    if any(liquefaction_susceptible_layers(bh) for bh in project.boreholes):
        warnings.append(
            "Liquefaction assessment not performed: peak ground acceleration (PGA) "
            "is not provided."
        )


def design_project(project: Project) -> DesignRun:
    """Analyse every element and return the selected foundation schedule."""
    warnings: list[str] = []
    if not project.elements:
        return DesignRun([], ["No columns or shear walls have been defined."])
    if not project.boreholes:
        return DesignRun([], ["No borehole/soil profile has been defined."])

    options = project.options
    _append_liquefaction_warnings(project, warnings)
    materials = project.materials
    elements = project.elements
    # Design shear walls first: they are long, stiff elements and their caps
    # constrain where the adjacent column foundations can fit.
    design_order = (
        [e for e in elements if e.kind == "wall"]
        + [e for e in elements if e.kind != "wall"]
    )
    boreholes = {
        e.id: project.nearest_borehole(e.center_x, e.center_y) or project.boreholes[0]
        for e in elements
    }

    # Forced global raft mode.
    force_raft = (
        options.raft_trigger.lower() == "always"
        or any(e.preferred.lower() == "raft" for e in elements)
    )
    if force_raft:
        centroid_x = sum(e.center_x for e in elements) / len(elements)
        centroid_y = sum(e.center_y for e in elements) / len(elements)
        bh = project.nearest_borehole(centroid_x, centroid_y) or project.boreholes[0]
        trial = max(math.sqrt(max(project.total_service_load(), 1.0) / 100.0), 2.0)
        depth = max(_min_depth(e, bh, options) for e in elements)
        q = allowable_bearing_pressure(bh, depth, trial, trial, options.fs_shallow)
        if q <= 0:
            layer = bh.layer_at_depth(depth)
            q = presumptive_bearing(layer.soil_type) if layer else 100.0
        raft = _try_raft(project, bh, max(q, 10.0))
        if raft is not None:
            raft.result.details["selected"] = True
            if raft.result.status != "OK":
                warnings.append("The requested global raft requires review: " + raft.result.remarks)
            return DesignRun([raft.result], warnings)
        warnings.append("Global raft was requested but could not be designed.")

    # Preliminary isolated footings for columns (also used for clash checks).
    preliminary: dict[str, Candidate] = {}
    for e in elements:
        if e.kind == "column" and options.allow_isolated:
            candidate = _try_isolated(e, boreholes[e.id], options, materials)
            if candidate is not None:
                preliminary[e.id] = candidate

    selected: list[DesignResult] = []
    covered: set[str] = set()
    blocked_polygons: list[list[tuple[float, float]]] = []
    column_order = {"Isolated footing": 0, "Combined footing": 1,
                    "Single pile": 2, "Pile group with cap": 3}
    wall_order = {"Strip footing": 0, "Pile group with cap": 1}

    for element in design_order:
        if element.id in covered:
            continue
        bh = boreholes[element.id]
        candidates: list[Candidate] = []
        if element.kind == "wall":
            strip = _try_strip(element, bh, options, materials)
            if strip is not None:
                candidates.append(strip)
            # Account for the preliminary column footings when choosing a wall
            # foundation, even though those columns are designed afterwards.
            wall_blocked_rects = [
                other.rect for other in preliminary.values()
            ]
            wall_blocked_polys = [
                other.polygon for other in preliminary.values()
            ]
            width_limit = _wall_width_limit(element, wall_blocked_rects)
            if options.allow_pile_group:
                group = _try_pile_group(
                    element, bh, options, materials, cap_width_limit=width_limit,
                )
                if group is not None:
                    candidates.append(group)
            chosen = _choose(
                candidates, options, wall_order, element.preferred, wall_blocked_polys
            )
        else:
            isolated = preliminary.get(element.id)
            if isolated is not None:
                candidates.append(isolated)
            problem = (
                isolated is None
                or isolated.result.status == "FAIL"
                or not isolated.result.details.get("site_ok", True)
                or _clash_count(isolated.polygon, blocked_polygons) > 0
            )
            if isolated is not None and not problem:
                for other_id, other in preliminary.items():
                    if (
                        other_id != element.id
                        and other_id not in covered
                        and polygons_overlap(isolated.polygon, other.polygon, 0.10)
                    ):
                        problem = True
                        break
            if element.preferred.lower() == "combined":
                problem = True
            if problem and options.allow_combined:
                partner = _nearest_partner(element, elements, covered, options)
                if partner is not None:
                    combined = _try_combined(element, partner, bh, options, materials)
                    if combined is not None:
                        candidates.append(combined)
            if options.allow_single_pile:
                single = _try_single_pile(element, bh, options, materials)
                if single is not None:
                    candidates.append(single)
            if options.allow_pile_group:
                group = _try_pile_group(element, bh, options, materials)
                if group is not None:
                    candidates.append(group)
            chosen = _choose(
                candidates, options, column_order, element.preferred, blocked_polygons
            )

        if chosen is None:
            result = DesignResult(
                element_id=element.id,
                element_kind=element.kind,
                foundation_type="No feasible foundation",
                requirement=(
                    f"Support {element.id}: service P={governing_service(element).P:.0f} kN"
                ),
                quantity=1,
                size="-",
                service_load=governing_service(element).P,
                factored_load=governing_factored(element).P,
                status="FAIL",
                remarks="No feasible foundation type was found for the current input and options.",
                alternatives=_alternative_texts(candidates, Candidate(result=DesignResult(), kind="", rect=(0, 0, 0, 0))),
            )
            selected.append(result)
            covered.add(element.id)
            warnings.append(f"No feasible foundation for {element.id}.")
            continue

        chosen.result.alternatives = _alternative_texts(candidates, chosen)
        chosen.result.details["selected"] = True
        selected.append(chosen.result)
        blocked_polygons.append(chosen.polygon)
        if chosen.kind == "Combined footing":
            covered.update(chosen.result.covers)
        else:
            covered.add(element.id)

    # Auto raft alternative.  It is retained in the results as a project-level
    # option; if every element foundation is unsatisfactory and the raft is
    # satisfactory, the raft becomes the selected scheme.
    if options.allow_raft and options.raft_trigger.lower() != "never":
        centroid_x = sum(e.center_x for e in elements) / len(elements)
        centroid_y = sum(e.center_y for e in elements) / len(elements)
        bh = project.nearest_borehole(centroid_x, centroid_y) or project.boreholes[0]
        trial = max(math.sqrt(max(project.total_service_load(), 1.0) / 100.0), 2.0)
        depth = max(_min_depth(e, bh, options) for e in elements)
        q = allowable_bearing_pressure(bh, depth, trial, trial, options.fs_shallow)
        if q <= 0:
            layer = bh.layer_at_depth(depth)
            q = presumptive_bearing(layer.soil_type) if layer else 100.0
        raft = _try_raft(project, bh, max(q, 10.0))
        if raft is not None:
            raft.result.details["selected"] = False
            raft.result.remarks = (
                "Raft alternative evaluated, not selected. " + raft.result.remarks
            ).strip()
            if raft.result.status == "OK" and not any(r.status == "OK" for r in selected):
                raft.result.details["selected"] = True
                raft.result.remarks = raft.result.remarks.replace(
                    "Raft alternative evaluated, not selected. ", ""
                )
                selected = [raft.result]
                warnings.append(
                    "The global raft was selected because no individual foundation was satisfactory."
                )
            else:
                selected.append(raft.result)
            if raft.result.status != "OK":
                warnings.append("Raft alternative requires review: " + raft.result.remarks)

    # Final site-boundary and clash checks for selected shallow/pile foundations.
    shallow = [
        r for r in selected
        if r.element_kind != "raft" and r.details.get("footprint")
    ]
    for i, first in enumerate(shallow):
        p1 = [tuple(v) for v in first.details["footprint"]]
        if not _site_polygon_ok(p1, options):
            first.status = "CHECK" if first.status == "OK" else first.status
            warnings.append(f"{first.element_id}: foundation extends beyond the site boundary.")
        for second in shallow[i + 1:]:
            p2 = [tuple(v) for v in second.details["footprint"]]
            if polygons_overlap(p1, p2, 0.10):
                first.status = "CHECK" if first.status == "OK" else first.status
                second.status = "CHECK" if second.status == "OK" else second.status
                warnings.append(
                    f"{first.element_id} and {second.element_id}: foundation outlines overlap."
                )

    # Differential and angular-distortion checks between adjacent foundations.
    for i, first in enumerate(shallow):
        p1 = [tuple(v) for v in first.details["footprint"]]
        for second in shallow[i + 1:]:
            p2 = [tuple(v) for v in second.details["footprint"]]
            if distance_between_polygons(p1, p2) > 1.50:
                continue
            if first.settlement <= 0.0 or second.settlement <= 0.0:
                continue
            c1x = sum(v[0] for v in p1) / len(p1)
            c1y = sum(v[1] for v in p1) / len(p1)
            c2x = sum(v[0] for v in p2) / len(p2)
            c2y = sum(v[1] for v in p2) / len(p2)
            spacing = math.hypot(c1x - c2x, c1y - c2y)
            ok, note = differential_ok(
                first.settlement, second.settlement, spacing, options
            )
            if not ok:
                first.status = "CHECK" if first.status == "OK" else first.status
                second.status = "CHECK" if second.status == "OK" else second.status
                warnings.append(
                    f"{first.element_id} and {second.element_id}: {note}."
                )

    if any(r.status == "FAIL" for r in selected):
        warnings.append("One or more elements have no satisfactory foundation; review the schedule.")
    return DesignRun(selected, warnings)


def run_design(project: Project) -> DesignRun:
    """Run the complete design and store the results on the project."""
    run = design_project(project)
    project.results = run.results
    project.warnings = run.warnings
    return run
