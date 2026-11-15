"""Shallow-foundation bearing pressure, sizing and stability checks."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .geometry import polygon_area, polygon_centroid, polygon_second_moments
from .models import Borehole, FoundationOptions
from .soil import GAMMA_W
from .units import ceil_to, clamp, safe_div


@dataclass
class PressureResult:
    q_max: float = 0.0
    q_min: float = 0.0
    q_avg: float = 0.0
    e_x: float = 0.0
    e_y: float = 0.0
    kern_ok: bool = True
    tension: bool = False


def pressure_distribution(P: float, Mx: float, My: float, L: float, B: float) -> PressureResult:
    """Linear contact pressure for a rectangular footing.

    L is the dimension along x, B along y. Mx is the moment about the x-axis
    (varying pressure along y) and My about the y-axis (varying along x).
    """
    L = max(L, 1e-6)
    B = max(B, 1e-6)
    A = L * B
    if P <= 0:
        return PressureResult(0.0, 0.0, 0.0, 0.0, 0.0, False, True)
    sx = L * B * B / 6.0
    sy = B * L * L / 6.0
    q_avg = P / A
    q_max = q_avg + abs(Mx) / sx + abs(My) / sy
    q_min = q_avg - abs(Mx) / sx - abs(My) / sy
    e_x = abs(My) / P
    e_y = abs(Mx) / P
    kern_ok = e_x <= L / 6.0 + 1e-9 and e_y <= B / 6.0 + 1e-9
    return PressureResult(q_max, q_min, q_avg, e_x, e_y, kern_ok, q_min < -1e-6)


def polygon_pressure(
    P: float,
    Mx: float,
    My: float,
    polygon: list[tuple[float, float]],
) -> PressureResult:
    """Linear contact pressure beneath an arbitrary convex mat outline.

    The pressure plane ``q = a + b*x' + c*y'`` (primed axes through the
    polygon centroid) is fitted to the applied vertical load and biaxial
    moment resultants.  Extrema of a linear function over a convex polygon
    occur at its vertices, so no grid sampling is needed.
    """
    pts = list(polygon)
    if len(pts) < 3:
        return PressureResult(0.0, 0.0, 0.0, 0.0, 0.0, False, True)
    area = polygon_area(pts)
    if P <= 0.0 or area < 1e-9:
        return PressureResult(0.0, 0.0, 0.0, 0.0, 0.0, False, True)
    cx, cy = polygon_centroid(pts)
    _, ixx, iyy, ixy = polygon_second_moments(pts)
    a = P / area
    det = ixx * iyy - ixy * ixy
    if abs(det) < 1e-12:
        b = c = 0.0
    else:
        b = (My * ixx - Mx * ixy) / det
        c = (Mx * iyy - My * ixy) / det
    values = [a + b * (x - cx) + c * (y - cy) for x, y in pts]
    q_max = max(values)
    q_min = min(values)
    e_x = abs(My) / P
    e_y = abs(Mx) / P
    return PressureResult(
        q_max=q_max, q_min=q_min, q_avg=P / area,
        e_x=e_x, e_y=e_y, kern_ok=q_min >= -1e-9, tension=q_min < -1e-9,
    )


@dataclass
class UpliftResult:
    uplift: float = 0.0               # kN, buoyancy/uplift force
    resistance: float = 0.0           # kN, permanent load plus footing/soil weight
    fs: float = 999.0
    ok: bool = True
    note: str = ""


def check_shallow_uplift(
    borehole: Borehole,
    depth: float,
    length: float,
    width: float,
    thickness: float,
    P: float,
    concrete_unit_weight: float = 24.0,
    buoyancy: float = 0.0,
    uplift_fs: float = 1.10,
    soil_unit_weight: float = 18.0,
) -> UpliftResult:
    """Buoyancy and hydrostatic uplift check for a shallow footing.

    Uplift comes from an explicit reaction component plus the hydrostatic
    pressure on the base below the water table.  Resistance is the permanent
    column load, the footing self-weight and the submerged weight of soil above
    the footing projection.  Passive resistance of the sides is ignored.
    """
    length = max(length, 0.01)
    width = max(width, 0.01)
    thickness = max(thickness, 0.01)
    area = length * width
    gwt = max(borehole.gwt, 0.0)
    head = max(depth - gwt, 0.0)
    hydrostatic = GAMMA_W * head * area
    uplift = max(hydrostatic + max(buoyancy, 0.0), 0.0)
    footing_weight = concrete_unit_weight * area * thickness
    soil_depth = max(depth - thickness, 0.0)
    soil_weight = area * soil_depth * soil_unit_weight
    if depth > gwt:
        submerged = min(soil_depth, max(depth - max(gwt, thickness), 0.0))
        soil_weight -= submerged * area * GAMMA_W
    resistance = max(P, 0.0) + footing_weight + max(soil_weight, 0.0)
    fs = resistance / uplift if uplift > 1e-9 else 999.0
    ok = fs >= uplift_fs - 1e-9
    note = ""
    if not ok:
        note = (
            f"Uplift FS {fs:.2f} < {uplift_fs:.2f}; provide tension piles, "
            "anchors or increase the footing weight"
        )
    return UpliftResult(uplift, resistance, fs, ok, note)


def required_area(P: float, q_allow: float) -> float:
    return safe_div(max(P, 0.0), max(q_allow, 1e-6), 0.0)


def size_isolated_footing(
    P: float,
    Mx: float,
    My: float,
    q_allow: float,
    options: FoundationOptions,
    thickness: float = 0.45,
    concrete_unit_weight: float = 24.0,
    aspect: float = 1.0,
) -> tuple[float, float, PressureResult]:
    """Choose a practical rectangular footing in plan.

    Returns (L, B, pressure). The footing self-weight is included iteratively.
    """
    step = options.footing_dim_step
    target_area = required_area(P, q_allow) * 1.10
    base = math.sqrt(max(target_area, options.min_footing_dim ** 2))
    L = max(options.min_footing_dim, ceil_to(base * math.sqrt(aspect), step))
    B = max(options.min_footing_dim, ceil_to(base / math.sqrt(aspect), step))
    L = min(L, options.max_footing_dim)
    B = min(B, options.max_footing_dim)

    def evaluate(l: float, b: float) -> PressureResult:
        self_weight = concrete_unit_weight * l * b * thickness
        return pressure_distribution(P + self_weight, Mx, My, l, b)

    pressure = evaluate(L, B)
    # Increase the smaller dimension first, then both, until pressure passes.
    for _ in range(400):
        if pressure.q_max <= q_allow + 1e-6 and pressure.kern_ok:
            break
        if pressure.e_x > L / 6.0 + 1e-9:
            L += step
        elif pressure.e_y > B / 6.0 + 1e-9:
            B += step
        elif L <= B:
            L += step
        else:
            B += step
        if L > options.max_footing_dim and B > options.max_footing_dim:
            break
        L = min(L, options.max_footing_dim)
        B = min(B, options.max_footing_dim)
        pressure = evaluate(L, B)
    return L, B, evaluate(L, B)


def size_combined_footing(
    loads: list[tuple[float, float, float, float]],
    q_allow: float,
    options: FoundationOptions,
    thickness: float = 0.60,
    concrete_unit_weight: float = 24.0,
    clear_projection: float = 0.30,
) -> tuple[float, float, float, PressureResult]:
    """Size a rectangular combined footing for two or more column loads.

    loads: list of (x_position, P, Mx, My) in m and kN/kN.m.
    Returns (L, B, x_origin, pressure).
    """
    if not loads:
        return 0.0, 0.0, 0.0, PressureResult()
    xs = [x for x, _, _, _ in loads]
    p_total = sum(p for _, p, _, _ in loads)
    mx_total = sum(mx for _, _, mx, _ in loads)
    my_total = sum(my for _, _, _, my in loads)
    x_min = min(xs) - clear_projection
    x_max = max(xs) + clear_projection
    # Resultant position; place the footing centroid on the resultant where possible.
    x_bar = sum(x * p for x, p, _, _ in loads) / max(p_total, 1e-9)
    half = max(x_bar - x_min, x_max - x_bar, 0.75)
    length = max(2.0 * half, 2.0 * clear_projection + (max(xs) - min(xs)))
    length = max(options.min_footing_dim, ceil_to(length, options.footing_dim_step))
    origin = x_bar - length / 2.0

    # Iterate width until bearing pressure is acceptable.
    width = max(options.min_footing_dim, math.sqrt(max(p_total / max(q_allow, 1e-6), 0.0)))
    width = ceil_to(width, options.footing_dim_step)
    for _ in range(200):
        self_weight = concrete_unit_weight * length * width * thickness
        p = p_total + self_weight
        # Moment about the footing centroid, including column moments and eccentricity.
        mx = mx_total + sum((x - x_bar) * 0.0 for x, _, _, _ in loads)
        my = my_total + sum(p_i * (x - x_bar) for x, p_i, _, _ in loads)
        pressure = pressure_distribution(p, mx, my, length, width)
        if pressure.q_max <= q_allow + 1e-6 and pressure.kern_ok:
            return length, width, origin, pressure
        width += options.footing_dim_step
        if width > options.max_footing_dim:
            break
    return length, width, origin, pressure_distribution(
        p_total + concrete_unit_weight * length * width * thickness,
        mx_total, my_total, length, width
    )


@dataclass
class StabilityResult:
    sliding_fs: float = 0.0
    overturning_fs: float = 0.0
    ok: bool = True
    note: str = ""


def check_stability(
    P: float,
    Mx: float,
    My: float,
    Vx: float,
    Vy: float,
    L: float,
    B: float,
    depth: float,
    cohesion: float = 0.0,
    friction_angle: float = 0.0,
) -> StabilityResult:
    """Sliding and overturning checks for a shallow footing.

    Passive resistance is conservatively ignored. A minimum FS of 1.5 is used
    for both checks.
    """
    p = max(P, 0.0)
    v = math.hypot(Vx, Vy)
    # Sliding resistance: base friction plus a small cohesion term.
    delta = math.radians(clamp(friction_angle * 0.67, 0.0, 35.0))
    base_area = max(L * B, 1e-6)
    resistance = p * math.tan(delta) + cohesion * base_area
    sliding_fs = resistance / v if v > 1e-6 else 999.0

    # Overturning about the toe in the critical direction.
    m = math.hypot(Mx, My)
    m_overturn = m + v * max(depth, 0.0)
    m_resist = p * min(L, B) / 2.0
    overturning_fs = m_resist / m_overturn if m_overturn > 1e-6 else 999.0
    ok = sliding_fs >= 1.5 and overturning_fs >= 1.5
    notes = []
    if sliding_fs < 1.5:
        notes.append("Sliding FS < 1.5")
    if overturning_fs < 1.5:
        notes.append("Overturning FS < 1.5")
    return StabilityResult(sliding_fs, overturning_fs, ok, "; ".join(notes))
