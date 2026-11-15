"""Deep-foundation capacity, group layout and pile-cap sizing."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .models import Borehole, Element, FoundationOptions, SoilLayer
from .soil import (
    bearing_capacity_factors,
    soil_modulus,
    vertical_stress,
)
from .structural.concrete import pile_pm_interaction
from .units import clamp


@dataclass
class PileCapacity:
    diameter: float = 0.0                 # m
    length: float = 0.0                   # m
    skin_ultimate: float = 0.0            # kN
    end_ultimate: float = 0.0             # kN
    weight: float = 0.0                   # kN
    ultimate: float = 0.0                 # kN
    allowable_geotech: float = 0.0        # kN
    structural_capacity: float = 0.0      # kN
    allowable: float = 0.0                # kN
    fs: float = 3.0
    method: str = "SPT"
    note: str = ""
    # Additional checks (all kN unless noted).
    downdrag: float = 0.0                 # negative skin friction
    net_allowable: float = 0.0            # allowable after downdrag
    uplift_capacity: float = 0.0          # allowable uplift resistance
    lateral_capacity: float = 0.0         # allowable lateral resistance (Broms)
    lateral_ultimate: float = 0.0
    pm_utilization: float = 0.0
    pm_ok: bool = True


@dataclass
class PileGroupDesign:
    count: int = 1
    diameter: float = 0.6
    length: float = 20.0
    spacing: float = 1.5
    cap_length: float = 2.0
    cap_width: float = 2.0
    cap_thickness: float = 0.9
    positions: list[tuple[float, float]] = field(default_factory=list)
    angle_deg: float = 0.0                 # cap orientation (wall caps follow the wall)
    max_pile_load: float = 0.0
    min_pile_load: float = 0.0
    group_capacity: float = 0.0
    block_capacity: float = 0.0
    efficiency: float = 1.0
    utilization: float = 0.0
    settlement: float = 0.0
    status: str = "OK"
    note: str = ""
    downdrag: float = 0.0
    uplift_utilization: float = 0.0
    lateral_utilization: float = 0.0
    pm_utilization: float = 0.0
    uplift_ok: bool = True
    lateral_ok: bool = True
    pm_ok: bool = True


# ---------------------------------------------------------------------------
# Single-pile capacity
# ---------------------------------------------------------------------------


def _is_silt(layer: SoilLayer) -> bool:
    return "silt" in layer.soil_type.lower() or "ml" in layer.soil_type.lower() or "mh" in layer.soil_type.lower()


def _spt_skin_end(layer: SoilLayer, pile_type: str, pile_length: float, diameter: float) -> tuple[float, float]:
    """Ultimate unit skin friction and end bearing from SPT, kPa (BNBC 3.10.1.13/16, 3.10.4.5/7)."""
    n60 = layer.effective_n60()
    bored = pile_type.lower().startswith("bored") or "drilled" in pile_type.lower()
    if layer.is_cohesive():
        if bored:
            fs = min(1.2 * n60, 70.0)
            qb = min(25.0 * n60, 4000.0)
        else:
            fs = min(1.8 * n60, 70.0)
            qb = min(45.0 * n60, 4000.0)
        return fs, qb

    # Cohesionless: sand versus non-plastic silt.
    if _is_silt(layer):
        if bored:
            fs = min(0.9 * n60, 60.0)
            qb = min(10.0 * n60 * max(pile_length / max(diameter, 0.1), 1.0), 100.0 * n60, 4000.0)
        else:
            fs = min(1.7 * n60, 60.0)
            qb = min(30.0 * n60 * max(pile_length / max(diameter, 0.1), 1.0), 300.0 * n60, 11000.0)
        return fs, qb

    if bored:
        fs = min(1.0 * n60, 60.0)
        qb = min(15.0 * n60 * max(pile_length / max(diameter, 0.1), 1.0), 150.0 * n60, 4000.0)
    else:
        fs = min(2.0 * n60, 60.0)
        qb = min(40.0 * n60 * max(pile_length / max(diameter, 0.1), 1.0), 400.0 * n60, 11000.0)
    return fs, qb


def _static_skin_end(
    borehole: Borehole,
    layer: SoilLayer,
    top: float,
    bottom: float,
    pile_type: str,
    pile_length: float,
    diameter: float,
) -> tuple[float, float]:
    """Ultimate unit skin friction and end bearing from static soil parameters, kPa."""
    mid = 0.5 * (top + bottom)
    sigma_v, u, sigma_eff = vertical_stress(borehole, mid)
    bored = pile_type.lower().startswith("bored") or "drilled" in pile_type.lower()
    if layer.is_cohesive():
        cu = layer.cu if layer.cu > 0 else max(layer.cohesion, 0.0)
        if cu <= 0:
            return _spt_skin_end(layer, pile_type, pile_length, diameter)
        alpha = 1.0 if cu <= 25 else 0.5 if cu >= 70 else 1.0 - (cu - 25.0) / 45.0 * 0.5
        fs = alpha * cu
        qb = min(9.0 * cu, 4000.0)
        if bored:
            fs *= 2.0 / 3.0
            qb *= 1.0 / 3.0
        return fs, qb

    phi = layer.friction_angle
    if phi <= 0:
        return _spt_skin_end(layer, pile_type, pile_length, diameter)
    # Critical depth: cap effective stress for skin friction and end bearing.
    n60 = layer.effective_n60()
    if n60 < 10:
        critical = 10.0 * diameter
    elif n60 < 30:
        critical = 15.0 * diameter
    else:
        critical = 20.0 * diameter
    z_crit = min(max(top, critical), max(bottom, critical))
    sigma_crit = vertical_stress(borehole, max(z_crit, top))[2]
    sigma_eff = min(sigma_eff, sigma_crit)
    beta = 0.10 if phi <= 33 else 0.20 if phi <= 35 else 0.35
    if phi < 33:
        beta = 0.10 + max(0.0, phi - 28.0) / 5.0 * 0.10
    elif phi < 37:
        beta = 0.20 + (phi - 35.0) / 2.0 * 0.15
    fs = beta * sigma_eff
    nc, nq, ng = bearing_capacity_factors(phi)
    qb = min(sigma_eff * nq, 11000.0)
    if bored:
        fs *= 2.0 / 3.0
        qb *= 1.0 / 3.0
    return fs, qb


def _cpt_qc_fs(layer: SoilLayer) -> tuple[float, float]:
    """Cone resistance (MPa) and sleeve friction (kPa) for a layer.

    Direct CPT values are used when supplied; otherwise a simple SPT
    correlation provides a preliminary fallback: ``qc = 0.40 N60`` MPa for
    cohesionless soil and ``qc = 0.20 N60`` MPa for cohesive soil.
    """
    n60 = max(layer.effective_n60(), 0.0)
    qc = layer.qc if layer.qc and layer.qc > 0 else (
        0.20 * n60 if layer.is_cohesive() else 0.40 * n60
    )
    fs = layer.cpt_fs if layer.cpt_fs and layer.cpt_fs > 0 else max(0.5 * qc * 1000.0 / 100.0, 0.0)
    return max(qc, 0.0), max(fs, 0.0)


def _cpt_skin_end(
    layer: SoilLayer,
    pile_type: str,
    pile_length: float,
    diameter: float,
) -> tuple[float, float]:
    """Ultimate unit skin friction and end bearing from CPT, kPa.

    The preliminary Schmertmann/Nottingham approach is used: driven piles take
    the measured sleeve friction and cone resistance; bored piles take 60% of
    the sleeve friction and 50% of the cone resistance.  Values are capped to
    the same practical limits as the SPT method.
    """
    qc_mpa, fs_kpa = _cpt_qc_fs(layer)
    bored = pile_type.lower().startswith("bored") or "drilled" in pile_type.lower()
    if bored:
        fs = min(0.60 * fs_kpa, 70.0)
        qb = min(0.50 * qc_mpa * 1000.0, 4000.0)
    else:
        fs = min(fs_kpa, 100.0)
        qb = min(qc_mpa * 1000.0, 11000.0)
    return fs, qb


def _downdrag_unit(
    borehole: Borehole,
    layer: SoilLayer,
    top: float,
    bottom: float,
) -> float:
    """Ultimate negative skin friction, kPa, for a compressible layer."""
    name = layer.soil_type.lower()
    if "rock" in name or "shale" in name:
        return 0.0
    n60 = layer.effective_n60()
    cohesive = layer.is_cohesive()
    is_fill = "fill" in name or "organic" in name or name in ("ol", "oh")
    compressible = is_fill or (
        cohesive and (layer.cu <= 25.0 or layer.cu <= 0.0) and n60 < 8
    ) or (not cohesive and n60 < 8 and "gravel" not in name)
    if not compressible:
        return 0.0
    mid = 0.5 * (max(top, 0.0) + max(bottom, top))
    _, _, sigma_eff = vertical_stress(borehole, mid)
    if cohesive:
        cu = layer.cu if layer.cu > 0 else max(5.85 * n60, 5.0)
        return min(0.25 * cu, 40.0)
    return min(0.20 * sigma_eff, 40.0)


def broms_lateral_capacity(
    borehole: Borehole,
    diameter: float,
    length: float,
    pile_type: str = "Bored",
    fs_lateral: float = 2.5,
    f_c: float = 30.0,
    f_y: float = 420.0,
) -> tuple[float, float]:
    """Ultimate and allowable free-head lateral pile capacity by Broms.

    Cohesive soil: ``Hu = 9 cu D (L - 1.5D)``.
    Cohesionless soil: ``Hu = 1.5 gamma D L^2 Kp``.
    The short-pile mechanism is used; for long piles the result is capped by
    the pile yield moment ``Hu <= 2 My / (L + 1.5D)``.  A minimum factor of
    safety of 2.5 is applied to the allowable value.
    """
    diameter = max(diameter, 0.1)
    length = max(length, 1.0)
    layers = borehole.sorted_layers()
    if not layers:
        return 0.0, 0.0
    cu_sum = phi_sum = gamma_sum = weight = 0.0
    top = 0.0
    for layer in layers:
        bottom = min(layer.bottom_depth, length)
        thickness = max(bottom - top, 0.0)
        if thickness <= 0:
            if bottom >= length:
                break
            continue
        cu = layer.cu if layer.cu > 0 else max(5.85 * layer.effective_n60(), 0.0)
        cu_sum += cu * thickness
        phi_sum += (layer.friction_angle if layer.friction_angle > 0 else 30.0) * thickness
        gamma_sum += (layer.gamma_sat or layer.gamma) * thickness
        weight += thickness
        top = layer.bottom_depth
        if top >= length:
            break
    if weight <= 0:
        return 0.0, 0.0
    cu_avg = cu_sum / weight
    phi_avg = phi_sum / weight
    gamma_avg = gamma_sum / weight
    tip = borehole.layer_at_depth(length)
    cohesive = tip.is_cohesive() if tip is not None else cu_avg > 0 and phi_avg <= 5.0
    if cohesive:
        hu = 9.0 * max(cu_avg, 1.0) * diameter * max(length - 1.5 * diameter, 0.0)
    else:
        phi = math.radians(clamp(phi_avg, 20.0, 45.0))
        kp = math.tan(math.pi / 4.0 + phi / 2.0) ** 2
        hu = 1.5 * max(gamma_avg, 10.0) * diameter * length ** 2 * kp
    # Long-pile cap from the pile moment capacity.  The free-head lever arm is
    # taken as 1.5D plus one quarter of the pile length; using the full length
    # grossly underestimates the lateral resistance of a flexible pile.
    _, _, as_mm2, phi_mn = _pile_section_properties(diameter, f_c, f_y)
    lever = 1.5 * diameter + 0.25 * length
    hu = min(hu, 2.0 * phi_mn / max(lever, 0.1))
    return max(hu, 0.0), max(hu, 0.0) / max(fs_lateral, 1.0)


def _pile_section_properties(
    diameter: float,
    f_c: float,
    f_y: float,
    reinforcement_ratio: float | None = None,
) -> tuple[float, float, float, float]:
    """Return ``(Ag, phiPn, As, phiMn)`` for a circular pile section."""
    from .structural.concrete import pile_pm_interaction

    d_mm = max(diameter * 1000.0, 100.0)
    ag = math.pi * d_mm ** 2 / 4.0
    if reinforcement_ratio is None:
        reinforcement_ratio = 0.005 if ag <= 0.5e6 else 0.00375 if ag <= 1.0e6 else 0.0025
    result = pile_pm_interaction(diameter, 0.0, 0.0, f_c, f_y)
    as_mm2 = max(reinforcement_ratio, 0.0025) * ag
    return ag, result.phi_Pn, as_mm2, result.phi_Mn


def pile_structural_capacity(
    diameter: float,
    f_c: float,
    f_y: float,
    pile_type: str = "Bored",
    reinforcement_ratio: float | None = None,
) -> float:
    """Design axial structural capacity of a concrete pile, kN (BNBC Ch. 6)."""
    d_mm = diameter * 1000.0
    ag = math.pi * d_mm ** 2 / 4.0
    if reinforcement_ratio is None:
        if ag <= 0.5e6:
            reinforcement_ratio = 0.005
        elif ag <= 1.0e6:
            reinforcement_ratio = 0.00375
        else:
            reinforcement_ratio = 0.0025
    as_mm2 = reinforcement_ratio * ag
    pn = 0.85 * f_c * (ag - as_mm2) + f_y * as_mm2  # N
    phi = 0.65
    return phi * pn / 1000.0


def compute_pile_capacity(
    borehole: Borehole,
    pile_type: str,
    diameter: float,
    length: float,
    options: FoundationOptions,
    f_c: float = 30.0,
    f_y: float = 420.0,
    direct_capacity: float | None = None,
) -> PileCapacity:
    """Compute ultimate and allowable capacity of a single pile."""
    diameter = max(diameter, 0.1)
    length = max(length, 1.0)
    perimeter = math.pi * diameter
    area = math.pi * diameter ** 2 / 4.0
    method = options.pile_design_method
    mu = method.upper()
    fs = options.fs_pile
    if mu == "SPT":
        fs = max(fs, 3.5)
    elif mu == "CPT":
        fs = max(fs, 2.5)
    skin = 0.0
    end = 0.0
    downdrag = 0.0
    note_parts = []

    layers = borehole.sorted_layers()
    current = 0.0
    tip_layer = None
    for layer in layers:
        l_top = current
        l_bottom = layer.bottom_depth
        current = l_bottom
        if l_top >= length:
            break
        if l_bottom <= 0:
            continue
        seg_top = max(l_top, 0.0)
        seg_bottom = min(l_bottom, length)
        if seg_bottom <= seg_top:
            continue
        tip_layer = layer
        is_tip = length <= l_bottom + 1e-9
        if mu == "DIRECT" or (mu in ("SPT", "CPT") and _has_direct_pile(layer, pile_type)):
            fs_unit, qb_unit = _direct_skin_end(layer, pile_type)
        elif mu == "STATIC":
            fs_unit, qb_unit = _static_skin_end(
                borehole, layer, seg_top, seg_bottom, pile_type, length, diameter
            )
        elif mu == "CPT":
            fs_unit, qb_unit = _cpt_skin_end(layer, pile_type, length, diameter)
        else:
            fs_unit, qb_unit = _spt_skin_end(layer, pile_type, length, diameter)
        skin += fs_unit * perimeter * (seg_bottom - seg_top)
        if options.pile_downdrag_check and not is_tip:
            downdrag += _downdrag_unit(
                borehole, layer, seg_top, seg_bottom
            ) * perimeter * (seg_bottom - seg_top)
        if is_tip:
            end = qb_unit * area

    if tip_layer is None:
        tip_layer = layers[-1] if layers else SoilLayer()
        if mu == "DIRECT" or (mu in ("SPT", "CPT") and _has_direct_pile(tip_layer, pile_type)):
            _, qb_unit = _direct_skin_end(tip_layer, pile_type)
        elif mu == "STATIC":
            _, qb_unit = _static_skin_end(
                borehole, tip_layer, max(length - 1.0, 0.0), length, pile_type, length, diameter
            )
        elif mu == "CPT":
            _, qb_unit = _cpt_skin_end(tip_layer, pile_type, length, diameter)
        else:
            _, qb_unit = _spt_skin_end(tip_layer, pile_type, length, diameter)
        end = qb_unit * area

    weight = 24.0 * area * length
    ultimate = skin + end - weight
    allowable_geotech = max(ultimate, 0.0) / max(fs, 1.0)
    net_ultimate = max(ultimate - downdrag, 0.0)
    if downdrag > 0:
        allowable_geotech = net_ultimate / max(fs, 1.0)
        note_parts.append(
            f"Downdrag {downdrag:.0f} kN deducted (FS {fs:.1f})"
        )
    structural = pile_structural_capacity(diameter, f_c, f_y, pile_type)
    if direct_capacity is not None and direct_capacity > 0:
        allowable_geotech = direct_capacity
        note_parts.append("Direct allowable capacity from report")
    allowable = min(allowable_geotech, structural)
    if structural < allowable_geotech:
        note_parts.append("Structural capacity governs")
    if mu == "SPT":
        note_parts.append("SPT preliminary method, FS >= 3.5 (BNBC 3.10.1.13/16)")
    elif mu == "CPT":
        note_parts.append("CPT Schmertmann/Nottingham preliminary method, FS >= 2.5")

    # Uplift and lateral resistance (allowable values).
    uplift_capacity = (
        0.70 * skin + weight
    ) / max(options.pile_uplift_fs, 1.0)
    lateral_ultimate, lateral_capacity = broms_lateral_capacity(
        borehole, diameter, length, pile_type, options.pile_lateral_fs,
        f_c=f_c, f_y=f_y,
    )
    return PileCapacity(
        diameter=diameter,
        length=length,
        skin_ultimate=skin,
        end_ultimate=end,
        weight=weight,
        ultimate=ultimate,
        allowable_geotech=allowable_geotech,
        structural_capacity=structural,
        allowable=allowable,
        fs=fs,
        method=method,
        note="; ".join(note_parts),
        downdrag=downdrag,
        net_allowable=allowable,
        uplift_capacity=uplift_capacity,
        lateral_capacity=lateral_capacity,
        lateral_ultimate=lateral_ultimate,
    )


def _has_direct_pile(layer: SoilLayer, pile_type: str) -> bool:
    bored = pile_type.lower().startswith("bored") or "drilled" in pile_type.lower()

    def present(*values: float | None) -> bool:
        return any(value is not None and value > 0 for value in values)

    if bored:
        return present(layer.pile_skin_bored, layer.pile_skin,
                       layer.pile_end_bored, layer.pile_end)
    return present(layer.pile_skin_driven, layer.pile_skin,
                   layer.pile_end_driven, layer.pile_end)


def _direct_skin_end(layer: SoilLayer, pile_type: str) -> tuple[float, float]:
    bored = pile_type.lower().startswith("bored") or "drilled" in pile_type.lower()
    if bored:
        fs = layer.pile_skin_bored if layer.pile_skin_bored is not None else layer.pile_skin
        qb = layer.pile_end_bored if layer.pile_end_bored is not None else layer.pile_end
    else:
        fs = layer.pile_skin_driven if layer.pile_skin_driven is not None else layer.pile_skin
        qb = layer.pile_end_driven if layer.pile_end_driven is not None else layer.pile_end
    # Fall back to SPT if a direct value is missing.
    if fs is None or qb is None:
        sfs, sqb = _spt_skin_end(layer, pile_type, 10.0, 0.6)
        fs = sfs if fs is None else fs
        qb = sqb if qb is None else qb
    return max(fs, 0.0), max(qb, 0.0)


# ---------------------------------------------------------------------------
# Group layout and cap
# ---------------------------------------------------------------------------


def _grid_layout(
    n: int,
    kind: str,
    wall_length: float | None = None,
    spacing: float = 1.0,
    diameter: float = 0.6,
    edge_cover: float = 0.10,
) -> tuple[int, int]:
    """Return a compact (columns, rows) pile arrangement.

    Wall caps are kept close to the actual wall length: piles are arranged in
    as many columns as fit within the wall plus a short overhang, and excess
    piles move to additional rows.  For columns a compact rectangular grid is
    used.
    """
    if n <= 1:
        return 1, 1
    if kind == "wall" and wall_length and wall_length > 0:
        # Allow the cap to project up to 0.75 m beyond each end of the wall.
        usable = max(wall_length + 1.5 - diameter - 2.0 * edge_cover, 0.0)
        max_cols = int(math.floor(usable / max(spacing, 1e-6) + 1e-9)) + 1
        cols = max(1, min(n, max_cols))
        rows = math.ceil(n / cols)
        return cols, rows
    if n == 2:
        return 2, 1
    if n == 3:
        return 3, 1
    if n == 4:
        return 2, 2
    cols = math.ceil(math.sqrt(n))
    rows = math.ceil(n / cols)
    return cols, rows


def _pile_positions(nx: int, ny: int, spacing: float) -> list[tuple[float, float]]:
    x0 = -(nx - 1) * spacing / 2.0
    y0 = -(ny - 1) * spacing / 2.0
    return [(x0 + i * spacing, y0 + j * spacing) for j in range(ny) for i in range(nx)]


def _pile_loads(
    positions: list[tuple[float, float]], P: float, Mx: float, My: float
) -> tuple[float, float]:
    n = len(positions)
    if n == 0:
        return 0.0, 0.0
    sx = sum(x * x for x, _ in positions)
    sy = sum(y * y for _, y in positions)
    loads = []
    for x, y in positions:
        p = P / n
        if sy > 0:
            p += Mx * y / sy
        if sx > 0:
            p += My * x / sx
        loads.append(p)
    return max(loads), min(loads)


def design_pile_group(
    element: Element,
    borehole: Borehole,
    options: FoundationOptions,
    materials_f_c: float = 30.0,
    materials_f_y: float = 420.0,
    pile_type: str | None = None,
    direct_capacity: float | None = None,
    cap_width_limit: float | None = None,
) -> tuple[PileGroupDesign, PileCapacity] | None:
    """Search pile diameter/length/count combinations for a feasible group.

    ``cap_width_limit`` optionally restricts the transverse cap dimension, for
    example to keep a wall cap between adjacent column footings.
    """
    pile_type = pile_type or options.pile_type
    from .loads import service_combinations, factored_combinations, governing_service, governing_factored
    if element.kind == "wall":
        service = max(
            (element.wall_local_reaction(r) for r in service_combinations(element) or [element.max_service()]),
            key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My),
        )
        factored = max(
            (element.wall_local_reaction(r) for r in factored_combinations(element) or [element.max_factored()]),
            key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My),
        )
    else:
        service = governing_service(element)
        factored = governing_factored(element)
    p_service = max(service.P, 1.0)
    p_factored = max(factored.P, p_service)
    wall_length = element.wall_length if element.kind == "wall" else None
    angle_deg = element.wall_angle_deg if element.kind == "wall" else 0.0

    best_ok: tuple[PileGroupDesign, PileCapacity] | None = None
    best_check: tuple[PileGroupDesign, PileCapacity] | None = None
    best_check_severity = float("inf")
    for diameter in options.pile_diameters:
        if element.kind == "column" and options.allow_single_pile and diameter < options.single_pile_min_diameter and p_service < 600:
            # Still allow a group; only the single-pile option requires >= 600 mm.
            pass
        for length in options.pile_lengths:
            if length > options.max_pile_length:
                continue
            cap = compute_pile_capacity(
                borehole, pile_type, diameter, length, options,
                materials_f_c, materials_f_y, direct_capacity=direct_capacity,
            )
            if cap.allowable <= 0:
                continue
            n_min = max(1, math.ceil(p_service / cap.allowable))
            if element.kind == "column" and n_min == 1 and diameter < options.single_pile_min_diameter:
                n_min = 2
            if element.kind == "wall":
                # A wall needs at least two piles; single-pile caps are only
                # considered for columns.
                n_min = max(n_min, 2)
            for n in range(n_min, n_min + 12):
                spacing_factor = (
                    options.pile_spacing_end_bearing
                    if _is_end_bearing(borehole, length)
                    else options.pile_spacing_friction
                )
                spacing = max(options.min_pile_spacing, spacing_factor * diameter)
                nx, ny = _grid_layout(
                    n,
                    element.kind,
                    wall_length=wall_length,
                    spacing=spacing,
                    diameter=diameter,
                    edge_cover=options.cap_edge_cover,
                )
                if element.kind == "wall" and nx > 1:
                    # Spread the outer piles toward the wall ends so the cap
                    # covers the full wall footprint and develops the in-plane
                    # wall moment over a sensible lever arm.
                    spacing = max(
                        spacing,
                        max((wall_length or 0.0) - diameter, 0.0) / (nx - 1),
                    )
                positions = _pile_positions(nx, ny, spacing)
                count = len(positions)
                max_load, min_load = _pile_loads(
                    positions, service.P, service.Mx, service.My
                )
                tension = max(-min_load, 0.0)
                uplift_util = tension / max(cap.uplift_capacity, 1e-9)
                lateral_per_pile = math.hypot(service.Vx, service.Vy) / max(count, 1)
                lateral_util = lateral_per_pile / max(cap.lateral_capacity, 1e-9)
                pile_moment = math.hypot(service.Mx, service.My) / max(count, 1)
                pm = pile_pm_interaction(
                    diameter, max(max_load, 0.0), pile_moment,
                    materials_f_c, materials_f_y, pile_type,
                )
                uplift_ok = (
                    not options.uplift_check or uplift_util <= 1.0 + 1e-9
                )
                lateral_ok = (
                    not options.pile_lateral_check or lateral_util <= 1.0 + 1e-9
                )
                pm_ok = (
                    not options.pile_pm_check or pm.ok
                )
                if (
                    max_load <= cap.allowable * 1.001
                    and min_load >= -cap.uplift_capacity * 1.001
                    and uplift_ok and lateral_ok and pm_ok
                ):
                    cap_length = (nx - 1) * spacing + diameter + 2.0 * options.cap_edge_cover
                    cap_width = (ny - 1) * spacing + diameter + 2.0 * options.cap_edge_cover
                    if cap_width_limit is not None and cap_width > cap_width_limit + 1e-9:
                        continue
                    cap_thickness = max(options.cap_min_thickness / 1000.0, 1.0 * diameter)
                    eff = options.group_efficiency
                    group_capacity = count * cap.allowable * eff
                    block = _block_capacity(borehole, length, cap_length, cap_width, cap.allowable, count)
                    utilization = max(
                        p_service / max(group_capacity, 1e-6),
                        max_load / max(cap.allowable, 1e-6),
                        uplift_util, lateral_util, pm.utilization,
                    )
                    settlement = _pile_group_settlement(borehole, length, cap_length, cap_width, p_service, count)
                    tip_layer = borehole.layer_at_depth(length)
                    limit = (
                        options.settlement_limit_clay
                        if tip_layer is not None and tip_layer.is_cohesive()
                        else options.settlement_limit_sand
                    )
                    status = "OK" if utilization <= 1.0 and settlement <= limit else "CHECK"
                    design = PileGroupDesign(
                        count=count, diameter=diameter, length=length, spacing=spacing,
                        cap_length=cap_length, cap_width=cap_width, cap_thickness=cap_thickness,
                        positions=positions, angle_deg=angle_deg,
                        max_pile_load=max_load, min_pile_load=min_load,
                        group_capacity=group_capacity, block_capacity=block, efficiency=eff,
                        utilization=utilization, settlement=settlement, status=status,
                        note=f"{pile_type} pile, {cap.method} method",
                        downdrag=cap.downdrag, uplift_utilization=uplift_util,
                        lateral_utilization=lateral_util,
                        pm_utilization=pm.utilization, uplift_ok=uplift_ok,
                        lateral_ok=lateral_ok, pm_ok=pm_ok,
                    )
                    if utilization <= 1.0:
                        if status == "OK":
                            if best_ok is None or count < best_ok[0].count:
                                best_ok = (design, cap)
                                break
                        else:
                            # Keep a near-feasible group as a fallback so the
                            # selector can trade a small settlement overrun for
                            # avoiding a hard geometric clash.
                            severity = settlement / max(limit, 1e-6)
                            better = severity < best_check_severity - 1e-9 or (
                                abs(severity - best_check_severity) <= 1e-9
                                and (best_check is None or count < best_check[0].count)
                            )
                            if severity <= 2.5 and better:
                                best_check = (design, cap)
                                best_check_severity = severity
            if best_ok is not None and best_ok[0].count <= 2:
                break
        if best_ok is not None and best_ok[0].count <= 1:
            break
    return best_ok or best_check


def _is_end_bearing(borehole: Borehole, length: float) -> bool:
    layer = borehole.layer_at_depth(length)
    if layer is None:
        return True
    return not layer.is_cohesive()


def _block_capacity(borehole: Borehole, length: float, cap_l: float, cap_w: float,
                    single_capacity: float, n: int) -> float:
    """Simplified block failure capacity, kN."""
    layer = borehole.layer_at_depth(length)
    if layer is None:
        return n * single_capacity
    if layer.is_cohesive() and layer.cu > 0:
        perimeter = 2.0 * (cap_l + cap_w)
        base = cap_l * cap_w
        return (layer.cu * perimeter * length + 9.0 * layer.cu * base)
    return n * single_capacity


def _pile_group_settlement(borehole: Borehole, length: float, cap_l: float,
                           cap_w: float, P: float, n: int) -> float:
    """Approximate pile-group settlement, mm."""
    layer = borehole.layer_at_depth(length)
    if layer is None:
        return 0.0
    es = soil_modulus(borehole, layer, max(length - 1.0, 0.0))
    b_group = math.sqrt(max(cap_l * cap_w, 0.01))
    q = P / max(cap_l * cap_w, 0.01)
    s = q * b_group * (1.0 - 0.3 ** 2) / max(es, 1.0) * 1000.0
    # Group interaction factor (simplified).
    return s * (1.0 + 0.10 * max(n - 1, 0))


def single_pile_design(
    element: Element,
    borehole: Borehole,
    options: FoundationOptions,
    f_c: float = 30.0,
    f_y: float = 420.0,
) -> tuple[PileCapacity, str] | None:
    """Try a single pile (no group cap beyond a simple connection)."""
    if not options.allow_single_pile:
        return None
    from .loads import governing_service
    service = governing_service(element)
    best = None
    for diameter in options.pile_diameters:
        if diameter < options.single_pile_min_diameter:
            continue
        for length in options.pile_lengths:
            if length > options.max_pile_length:
                continue
            cap = compute_pile_capacity(borehole, options.pile_type, diameter, length, options, f_c, f_y)
            if cap.allowable >= service.P:
                if best is None or length < best[1].length or diameter < best[1].diameter:
                    best = (cap, f"Single {options.pile_type.lower()} pile D={diameter*1000:.0f} mm, L={length:.1f} m")
                break
        if best is not None:
            break
    return best
