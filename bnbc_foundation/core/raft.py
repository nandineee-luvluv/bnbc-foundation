"""Raft/mat analysis: rigid pressure, Winkler strips and a Winkler plate solver.

Three methods are available and can be selected automatically:

* ``Rigid`` - statically equivalent linear contact pressure over the raft.
* ``Winkler strips`` - orthogonal beam-on-elastic-foundation strips, solved with
  a finite-difference beam formulation and free ends.
* ``Plate`` - a rectangular Kirchhoff plate on Winkler springs, solved with a
  16-DOF bicubic Hermite finite element and free edges.

The plate solver is used for large or irregular rafts, the strip solver for
regular rafts, and the rigid method always supplies the code bearing-pressure
check.  All results are per metre width unless stated otherwise.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .bearing import polygon_pressure, pressure_distribution
from .geometry import (
    ensure_ccw,
    point_in_polygon,
    polygon_area,
    polygon_centroid,
    rectangle_polygon,
)
from .models import Borehole, Element, FoundationOptions, Materials
from .settlement import estimate_shallow_settlement
from .soil import subgrade_modulus
from .structural.concrete import (
    one_way_shear_capacity,
    punching_geometry,
    punching_shear_capacity,
)


@dataclass
class RaftAnalysis:
    method: str = "Rigid"
    x0: float = 0.0
    y0: float = 0.0
    length: float = 1.0
    width: float = 1.0
    thickness: float = 0.6
    area: float = 1.0
    outline: list[tuple[float, float]] = field(default_factory=list)
    depth: float = 1.5
    k_subgrade: float = 0.0
    q_service_max: float = 0.0
    q_service_min: float = 0.0
    q_service_avg: float = 0.0
    q_factored_avg: float = 0.0
    q_local_max: float = 0.0
    q_local_min: float = 0.0
    q_allow: float = 0.0
    e_x: float = 0.0
    e_y: float = 0.0
    kern_ok: bool = True
    service_load: float = 0.0
    factored_load: float = 0.0
    settlement: float = 0.0
    settlement_limit: float = 0.0
    differential: float = 0.0
    differential_checked: bool = False
    deflection: float = 0.0
    moment_x_pos: float = 0.0
    moment_x_neg: float = 0.0
    moment_y_pos: float = 0.0
    moment_y_neg: float = 0.0
    service_moment_x_pos: float = 0.0
    service_moment_x_neg: float = 0.0
    service_moment_y_pos: float = 0.0
    service_moment_y_neg: float = 0.0
    shear_x: float = 0.0
    shear_y: float = 0.0
    punching_vu: float = 0.0
    punching_capacity: float = 0.0
    one_way_utilization: float = 0.0
    buoyancy_uplift: float = 0.0
    status: str = "OK"
    governing: str = "BNBC 3.8.10 / 3.9.6.3 raft"
    remarks: str = ""
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Geometry and loads
# ---------------------------------------------------------------------------


def raft_geometry(elements: list[Element], options: FoundationOptions) -> tuple[float, float, float, float]:
    """Return (x0, y0, L, B) for the raft bounding rectangle."""
    if not elements:
        return 0.0, 0.0, 0.0, 0.0
    bounds = [e.footprint_bounds for e in elements]
    xmin = min(b[0] for b in bounds) - options.raft_overhang
    xmax = max(b[2] for b in bounds) + options.raft_overhang
    ymin = min(b[1] for b in bounds) - options.raft_overhang
    ymax = max(b[3] for b in bounds) + options.raft_overhang
    # Respect known site boundaries when they are meaningful.
    if options.site_xmax - options.site_xmin < 5000:
        xmin = max(xmin, options.site_xmin)
        xmax = min(xmax, options.site_xmax)
    if options.site_ymax - options.site_ymin < 5000:
        ymin = max(ymin, options.site_ymin)
        ymax = min(ymax, options.site_ymax)
    return xmin, ymin, max(xmax - xmin, 1.0), max(ymax - ymin, 1.0)


def raft_outline(
    elements: list[Element], options: FoundationOptions
) -> list[tuple[float, float]]:
    """Mat outline polygon: an imported outline or the automatic rectangle."""
    raw = options.raft_outline or []
    points: list[tuple[float, float]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            try:
                points.append((float(item[0]), float(item[1])))
            except (TypeError, ValueError):
                continue
    if len(points) >= 3:
        return ensure_ccw(points)
    x0, y0, length, width = raft_geometry(elements, options)
    return rectangle_polygon(x0, y0, x0 + length, y0 + width)


def _governing_service(element: Element):
    from .loads import governing_service
    return governing_service(element)


def _governing_factored(element: Element):
    from .loads import governing_factored
    return governing_factored(element)


def _total_loads(elements: list[Element], factored: bool) -> tuple[float, float, float, float, float]:
    p = mx = my = vx = vy = 0.0
    for e in elements:
        r = _governing_factored(e) if factored else _governing_service(e)
        p += r.P
        mx += r.Mx
        my += r.My
        vx += r.Vx
        vy += r.Vy
    return p, mx, my, vx, vy


def _centroid(elements: list[Element]) -> tuple[float, float]:
    total = sum(max(e.max_service().P, 0.0) for e in elements)
    if total <= 0:
        return (
            sum(e.center_x for e in elements) / max(len(elements), 1),
            sum(e.center_y for e in elements) / max(len(elements), 1),
        )
    return (
        sum(e.center_x * max(e.max_service().P, 0.0) for e in elements) / total,
        sum(e.center_y * max(e.max_service().P, 0.0) for e in elements) / total,
    )


# ---------------------------------------------------------------------------
# Rigid contact pressure
# ---------------------------------------------------------------------------


def rigid_pressure(
    elements: list[Element],
    length: float,
    width: float,
    thickness: float,
    concrete_unit_weight: float = 24.0,
    factored: bool = False,
    polygon: list[tuple[float, float]] | None = None,
):
    p, mx, my, _, _ = _total_loads(elements, factored)
    area = polygon_area(polygon) if polygon and len(polygon) >= 3 else length * width
    self_weight = concrete_unit_weight * area * thickness * (1.2 if factored else 1.0)
    total = p + self_weight
    if polygon and len(polygon) >= 3:
        xc, yc = polygon_centroid(polygon)
    else:
        xc = sum(e.center_x for e in elements) / max(len(elements), 1)
        yc = sum(e.center_y for e in elements) / max(len(elements), 1)
    # Move column forces and moments to the raft centroid.
    mx_c = mx + sum(
        (_governing_factored(e).P if factored else _governing_service(e).P) * (e.center_y - yc)
        for e in elements
    )
    my_c = my + sum(
        (_governing_factored(e).P if factored else _governing_service(e).P) * (e.center_x - xc)
        for e in elements
    )
    pressure = (
        polygon_pressure(total, mx_c, my_c, polygon)
        if polygon and len(polygon) >= 3
        else pressure_distribution(total, mx_c, my_c, length, width)
    )
    return pressure, total


# ---------------------------------------------------------------------------
# Beam on elastic foundation (finite differences, free ends)
# ---------------------------------------------------------------------------


def _beam_on_elastic_foundation(
    x: np.ndarray,
    point_loads: list[tuple[float, float]],
    moment_loads: list[tuple[float, float]],
    EI: float,
    k_line: float,
    q_self: float,
) -> dict:
    """Solve EI w'''' + k w = q for a free-free beam on Winkler springs.

    ``x`` in m, point loads in kN, moments in kN.m, EI in kN.m2, k_line in
    kN/m/m and q_self in kN/m.
    """
    n = len(x)
    if n < 5:
        return {"w": np.zeros(n), "M": np.zeros(n), "V": np.zeros(n),
                "q": np.zeros(n), "x": x}
    h = float(x[1] - x[0])
    q = np.full(n, q_self)

    def add_point(load: float, position: float) -> None:
        if n < 2:
            q[0] += load / max(h, 1e-9)
            return
        t = (position - x[0]) / h
        i = int(math.floor(t))
        if i < 0:
            q[0] += load / h
        elif i >= n - 1:
            q[-1] += load / h
        else:
            frac = t - i
            q[i] += load * (1.0 - frac) / h
            q[i + 1] += load * frac / h

    for position, load in point_loads:
        add_point(load, position)
    # A moment is applied as a couple of vertical forces.
    dx = max(h, 0.10)
    for position, moment in moment_loads:
        add_point(-moment / (2.0 * dx), position - dx)
        add_point(moment / (2.0 * dx), position + dx)

    A = np.zeros((n, n))
    b = q.copy()
    f = EI / h ** 4
    for i in range(n):
        if i == 0:
            A[i, 0] += 2.0 * f + k_line
            A[i, 1] += -4.0 * f
            A[i, 2] += 2.0 * f
        elif i == 1:
            A[i, 0] += -2.0 * f
            A[i, 1] += 5.0 * f + k_line
            A[i, 2] += -4.0 * f
            A[i, 3] += f
        elif i == n - 2:
            A[i, n - 4] += f
            A[i, n - 3] += -4.0 * f
            A[i, n - 2] += 5.0 * f + k_line
            A[i, n - 1] += -2.0 * f
        elif i == n - 1:
            A[i, n - 3] += 2.0 * f
            A[i, n - 2] += -4.0 * f
            A[i, n - 1] += 2.0 * f + k_line
        else:
            A[i, i - 2] += f
            A[i, i - 1] += -4.0 * f
            A[i, i] += 6.0 * f + k_line
            A[i, i + 1] += -4.0 * f
            A[i, i + 2] += f

    # A tiny diagonal term avoids singularity for a completely unloaded beam.
    A += np.eye(n) * max(np.max(np.abs(np.diag(A))), 1.0) * 1e-12
    try:
        w = np.linalg.solve(A, b)
    except np.linalg.LinAlgError:
        w = np.linalg.lstsq(A, b, rcond=None)[0]

    curvature = np.zeros(n)
    curvature[1:-1] = (w[:-2] - 2.0 * w[1:-1] + w[2:]) / h ** 2
    M = -EI * curvature
    V = np.gradient(M, x) if n > 2 else np.zeros(n)
    soil_pressure = k_line * w
    return {"w": w, "M": M, "V": V, "q": soil_pressure, "x": x}


def _strip_lines(elements: list[Element], lower: float, upper: float, coordinate: str) -> tuple[list[float], list[float]]:
    values = sorted(
        {e.center_x if coordinate == "x" else e.center_y for e in elements}
    )
    if not values:
        values = [(lower + upper) / 2.0]
    # Keep unique lines at least 0.5 m apart; merge very close columns.
    merged: list[float] = []
    for value in values:
        value = min(max(value, lower + 0.05), upper - 0.05)
        if not merged or abs(value - merged[-1]) > 0.5:
            merged.append(value)
    return merged, []


def _tributary_widths(lines: list[float], lower: float, upper: float) -> list[float]:
    widths: list[float] = []
    for i, line in enumerate(lines):
        lo = lower if i == 0 else 0.5 * (lines[i - 1] + line)
        hi = upper if i == len(lines) - 1 else 0.5 * (line + lines[i + 1])
        widths.append(max(hi - lo, 0.10))
    return widths


def _winkler_strips(
    elements: list[Element],
    x0: float,
    y0: float,
    length: float,
    width: float,
    thickness: float,
    k: float,
    E: float,
    concrete_unit_weight: float,
    factored: bool,
    n_nodes: int = 81,
) -> dict:
    """Analyse orthogonal strip lines and return envelope results."""
    I_unit = thickness ** 3 / 12.0  # m4 per metre width
    mi = 1.2 if factored else 1.0
    q_self = concrete_unit_weight * thickness * mi
    result = {
        "moment_x_pos": 0.0, "moment_x_neg": 0.0,
        "moment_y_pos": 0.0, "moment_y_neg": 0.0,
        "shear_x": 0.0, "shear_y": 0.0,
        "q_max": 0.0, "q_min": 0.0, "deflection": 0.0,
        "differential": 0.0, "strips_x": 0, "strips_y": 0,
    }

    def analyse(direction: str) -> None:
        nonlocal result
        if direction == "x":
            lines, _ = _strip_lines(elements, y0, y0 + width, "y")
            widths = _tributary_widths(lines, y0, y0 + width)
            span_low, span_high = x0, x0 + length
        else:
            lines, _ = _strip_lines(elements, x0, x0 + length, "x")
            widths = _tributary_widths(lines, x0, x0 + length)
            span_low, span_high = y0, y0 + width
        bounds = [span_low]
        for i in range(len(lines) - 1):
            bounds.append(0.5 * (lines[i] + lines[i + 1]))
        bounds.append(span_high)
        n = max(n_nodes, 21)
        x = np.linspace(span_low, span_high, n)
        for idx, line in enumerate(lines):
            trib = widths[idx]
            lo, hi = bounds[idx], bounds[idx + 1]
            point_loads = []
            moment_loads = []
            for e in elements:
                b = e.footprint_bounds
                if direction == "x":
                    e_lo, e_hi = b[1], b[3]
                    patch = max((b[3] - b[1]) + 2.0 * thickness, 0.6)
                    center = e.center_x
                else:
                    e_lo, e_hi = b[0], b[2]
                    patch = max((b[2] - b[0]) + 2.0 * thickness, 0.6)
                    center = e.center_y
                overlap = max(0.0, min(e_hi, hi) - max(e_lo, lo))
                if overlap <= 1e-9:
                    continue
                weight = overlap / max(e_hi - e_lo, 1e-9)
                r = _governing_factored(e) if factored else _governing_service(e)
                load = r.P * weight
                moment = (r.My if direction == "x" else r.Mx) * weight
                # Spread the column load over an effective patch to avoid a
                # singular point load in the strip model.
                samples = 5
                for k in range(samples):
                    offset = (k - (samples - 1) / 2.0) * patch / samples
                    point_loads.append((center + offset, load / samples))
                moment_loads.append((center, moment))
            EI = E * I_unit * trib
            k_line = max(k, 1000.0) * trib
            solved = _beam_on_elastic_foundation(x, point_loads, moment_loads, EI, k_line, q_self * trib)
            m = solved["M"] / max(trib, 1e-6)
            v = solved["V"] / max(trib, 1e-6)
            qs = solved["q"] / max(trib, 1e-6)  # k*w, kPa
            if direction == "x":
                result["moment_x_pos"] = max(result["moment_x_pos"], float(np.max(m)))
                result["moment_x_neg"] = max(result["moment_x_neg"], float(-np.min(m)))
                result["shear_x"] = max(result["shear_x"], float(np.max(np.abs(v))))
                result["strips_x"] += 1
            else:
                result["moment_y_pos"] = max(result["moment_y_pos"], float(np.max(m)))
                result["moment_y_neg"] = max(result["moment_y_neg"], float(-np.min(m)))
                result["shear_y"] = max(result["shear_y"], float(np.max(np.abs(v))))
                result["strips_y"] += 1
            result["q_max"] = max(result["q_max"], float(np.max(qs)))
            result["q_min"] = min(result["q_min"], float(np.min(qs)))
            result["deflection"] = max(result["deflection"], float(np.max(np.abs(solved["w"]))))
            result["differential"] = max(
                result["differential"],
                float(np.max(solved["w"]) - np.min(solved["w"])),
            )

    analyse("x")
    analyse("y")
    return result


# ---------------------------------------------------------------------------
# Kirchhoff plate on Winkler springs (bicubic Hermite finite element)
# ---------------------------------------------------------------------------


def _hermite(s: float):
    return (
        (1.0 - 3.0 * s ** 2 + 2.0 * s ** 3, -6.0 * s + 6.0 * s ** 2, -6.0 + 12.0 * s),
        (s - 2.0 * s ** 2 + s ** 3, 1.0 - 4.0 * s + 3.0 * s ** 2, -4.0 + 6.0 * s),
        (3.0 * s ** 2 - 2.0 * s ** 3, 6.0 * s - 6.0 * s ** 2, 6.0 - 12.0 * s),
        (-s ** 2 + s ** 3, -2.0 * s + 3.0 * s ** 2, -2.0 + 6.0 * s),
    )


def _plate_basis(kind: int, si: int, ti: int, s: float, t: float, a: float, b: float):
    """Return N, N_x, N_y, N_xx, N_yy, N_xy for a Hermite plate DOF."""
    hs, hsp, hspp = _hermite(s)[si]
    ht, htp, htpp = _hermite(t)[ti]
    if kind == 0:  # w
        return (hs * ht, hsp * ht / a, hs * htp / b,
                hspp * ht / a ** 2, hs * htpp / b ** 2, hsp * htp / (a * b))
    if kind == 1:  # w_x
        return (a * hs * ht, hsp * ht, a * hs * htp / b,
                hspp * ht / a, a * hs * htpp / b ** 2, hsp * htp / b)
    if kind == 2:  # w_y
        return (b * hs * ht, b * hsp * ht / a, hs * htp,
                b * hspp * ht / a ** 2, hs * htpp / b, hsp * htp / a)
    # w_xy
    return (a * b * hs * ht, b * hsp * ht, a * hs * htp,
            b * hspp * ht / a, a * hs * htpp / b, hsp * htp)


def _plate_element(a: float, b: float, t: float, E: float, nu: float, k: float):
    """16x16 stiffness and load vector for a rectangular plate element."""
    D = E * t ** 3 / (12.0 * (1.0 - nu ** 2)) * np.array(
        [[1.0, nu, 0.0], [nu, 1.0, 0.0], [0.0, 0.0, (1.0 - nu) / 2.0]]
    )
    gauss = np.polynomial.legendre.leggauss(4)
    gp = [(0.5 * (x + 1.0), 0.5 * w) for x, w in zip(*gauss)]
    K = np.zeros((16, 16))
    f_uniform = np.zeros(16)
    node_si = [0, 2, 2, 0]
    node_ti = [0, 0, 2, 2]
    for s, ws in gp:
        for tt, wt in gp:
            jac = a * b * ws * wt
            B = np.zeros((3, 16))
            Nvec = np.zeros(16)
            for node in range(4):
                for kind in range(4):
                    si = node_si[node] + (1 if kind in (1, 3) else 0)
                    ti = node_ti[node] + (1 if kind in (2, 3) else 0)
                    N, Nx, Ny, Nxx, Nyy, Nxy = _plate_basis(kind, si, ti, s, tt, a, b)
                    j = node * 4 + kind
                    B[:, j] = (-Nxx, -Nyy, -2.0 * Nxy)
                    Nvec[j] = N
            K += B.T @ D @ B * jac + k * np.outer(Nvec, Nvec) * jac
            f_uniform += Nvec * jac
    return K, f_uniform, node_si, node_ti


def _winkler_plate(
    elements: list[Element],
    x0: float,
    y0: float,
    length: float,
    width: float,
    thickness: float,
    k: float,
    E: float,
    nu: float,
    concrete_unit_weight: float,
    factored: bool,
    max_elements: int = 16,
    outline: list[tuple[float, float]] | None = None,
) -> dict:
    """Finite-element plate on Winkler springs with free edges.

    When an imported outline is supplied, elements whose centre lies outside the
    polygon are retained for plate continuity but their soil springs and
    self-weight are removed.  This gives a stiffness-equivalent masked mat.
    """
    target = 1.5
    nx = max(4, min(max_elements, int(round(length / target))))
    ny = max(4, min(max_elements, int(round(width / target))))
    dx = length / nx
    dy = width / ny
    n_nodes_x = nx + 1
    n_nodes_y = ny + 1
    n_nodes = n_nodes_x * n_nodes_y
    ndof = 4 * n_nodes

    def node_index(i: int, j: int) -> int:
        return j * n_nodes_x + i

    K = np.zeros((ndof, ndof))
    F = np.zeros(ndof)
    q_uniform = concrete_unit_weight * thickness * (1.2 if factored else 1.0)
    Ke, fe, node_si, node_ti = _plate_element(dx, dy, thickness, E, nu, k)
    Ke_void, _, _, _ = _plate_element(dx, dy, thickness, E, nu, 0.0)
    element_inside: dict[tuple[int, int], bool] = {}

    def inside(px: float, py: float) -> bool:
        return point_in_polygon((px, py), outline) if outline else True

    # Assemble each rectangular element.  Local node order: (0,0), (1,0),
    # (1,1), (0,1).
    for j in range(ny):
        for i in range(nx):
            local_nodes = [
                node_index(i, j), node_index(i + 1, j),
                node_index(i + 1, j + 1), node_index(i, j + 1),
            ]
            dofs = []
            for node in local_nodes:
                dofs.extend([4 * node + 0, 4 * node + 1, 4 * node + 2, 4 * node + 3])
            active = inside(x0 + (i + 0.5) * dx, y0 + (j + 0.5) * dy)
            element_inside[(i, j)] = active
            K[np.ix_(dofs, dofs)] += Ke if active else Ke_void
            if active:
                F[dofs] += fe * q_uniform

    def add_point_load(load: float, px: float, py: float) -> None:
        if abs(load) < 1e-12:
            return
        i = min(max(int((px - x0) / dx), 0), nx - 1)
        j = min(max(int((py - y0) / dy), 0), ny - 1)
        s = min(max((px - x0 - i * dx) / dx, 0.0), 1.0)
        t = min(max((py - y0 - j * dy) / dy, 0.0), 1.0)
        # Evaluate the shape functions at the load point.
        local_nodes = [
            node_index(i, j), node_index(i + 1, j),
            node_index(i + 1, j + 1), node_index(i, j + 1),
        ]
        for node in range(4):
            for kind in range(4):
                si = node_si[node] + (1 if kind in (1, 3) else 0)
                ti = node_ti[node] + (1 if kind in (2, 3) else 0)
                N = _plate_basis(kind, si, ti, s, t, dx, dy)[0]
                F[4 * local_nodes[node] + kind] += load * N

    def add_patch_load(load: float, cx: float, cy: float, sx: float, sy: float) -> None:
        sx = max(sx, 1.0)
        sy = max(sy, 1.0)
        samples = 3
        for ii in range(samples):
            fx = (ii + 0.5) / samples - 0.5
            for jj in range(samples):
                fy = (jj + 0.5) / samples - 0.5
                add_point_load(load / (samples * samples), cx + fx * sx, cy + fy * sy)

    # Column loads; moments are applied as vertical couples.  Loads are spread
    # over an effective patch (column face + 2 x raft thickness) so the plate
    # results are not dominated by a mesh-dependent point singularity.
    for e in elements:
        r = _governing_factored(e) if factored else _governing_service(e)
        if not inside(e.center_x, e.center_y):
            continue
        b = e.footprint_bounds
        sx = max((b[2] - b[0]) + 2.0 * thickness, 1.2 * dx)
        sy = max((b[3] - b[1]) + 2.0 * thickness, 1.2 * dy)
        add_patch_load(r.P, e.center_x, e.center_y, sx, sy)
        dx_m = max(min(sx / 2.0, 0.5), 0.1)
        dy_m = max(min(sy / 2.0, 0.5), 0.1)
        add_point_load(r.My / (2.0 * dx_m), e.center_x - dx_m, e.center_y)
        add_point_load(-r.My / (2.0 * dx_m), e.center_x + dx_m, e.center_y)
        add_point_load(r.Mx / (2.0 * dy_m), e.center_x, e.center_y - dy_m)
        add_point_load(-r.Mx / (2.0 * dy_m), e.center_x, e.center_y + dy_m)

    # Small stabilisation for nearly singular rotational modes.
    diag = np.max(np.abs(np.diag(K)))
    K += np.eye(ndof) * max(diag, 1.0) * 1e-9
    try:
        u = np.linalg.solve(K, F)
    except np.linalg.LinAlgError:
        u = np.linalg.lstsq(K, F, rcond=None)[0]

    w = u[0::4].reshape((n_nodes_y, n_nodes_x))
    x = np.linspace(x0, x0 + length, n_nodes_x)
    y = np.linspace(y0, y0 + width, n_nodes_y)
    d2w_dx2 = np.gradient(np.gradient(w, x, axis=1), x, axis=1)
    d2w_dy2 = np.gradient(np.gradient(w, y, axis=0), y, axis=0)
    D = E * thickness ** 3 / (12.0 * (1.0 - nu ** 2))
    Mx = -D * (d2w_dx2 + nu * d2w_dy2)
    My = -D * (d2w_dy2 + nu * d2w_dx2)
    Vx = np.gradient(Mx, x, axis=1)
    Vy = np.gradient(My, y, axis=0)
    q = k * w
    mask = np.array([
        [inside(xi, yj) for xi in x] for yj in y
    ])
    if not mask.any():
        mask[:] = True
    active_w = w[mask]
    active_mx = Mx[mask]
    active_my = My[mask]
    active_vx = Vx[mask]
    active_vy = Vy[mask]
    active_q = q[mask]
    return {
        "moment_x_pos": float(np.max(active_mx)) if active_mx.size else 0.0,
        "moment_x_neg": float(-np.min(active_mx)) if active_mx.size else 0.0,
        "moment_y_pos": float(np.max(active_my)) if active_my.size else 0.0,
        "moment_y_neg": float(-np.min(active_my)) if active_my.size else 0.0,
        "shear_x": float(np.max(np.abs(active_vx))) if active_vx.size else 0.0,
        "shear_y": float(np.max(np.abs(active_vy))) if active_vy.size else 0.0,
        "q_max": float(np.max(active_q)) if active_q.size else 0.0,
        "q_min": float(np.min(active_q)) if active_q.size else 0.0,
        "deflection": float(np.max(np.abs(active_w))) if active_w.size else 0.0,
        "differential": float(np.max(active_w) - np.min(active_w)) if active_w.size else 0.0,
        "w": w, "x": x, "y": y, "Mx": Mx, "My": My,
        "nodes_x": n_nodes_x, "nodes_y": n_nodes_y,
    }


# ---------------------------------------------------------------------------
# Combined raft analysis
# ---------------------------------------------------------------------------


def analyze_raft(
    elements: list[Element],
    borehole: Borehole,
    q_allow: float,
    options: FoundationOptions,
    materials: Materials,
    thickness: float | None = None,
    method: str | None = None,
) -> RaftAnalysis:
    if not elements:
        return RaftAnalysis(status="FAIL", remarks="No elements for raft analysis")
    x0, y0, length, width = raft_geometry(elements, options)
    outline = raft_outline(elements, options)
    thickness = max(
        thickness if thickness is not None else options.raft_min_thickness / 1000.0,
        0.30,
    )
    method = method or options.raft_analysis or "Auto"
    if method.lower().startswith("auto"):
        area = polygon_area(outline)
        line_count = len({round(e.center_x, 2) for e in elements}) + len({round(e.center_y, 2) for e in elements})
        custom_outline = len(options.raft_outline or []) >= 3
        method = "Plate" if (custom_outline or area > 80.0 or line_count > 6) else "Winkler strips"

    base_elev = min(e.base_elev for e in elements)
    base_layer = borehole.layer_at_depth(max(abs(base_elev), 0.5))
    cohesive = base_layer.is_cohesive() if base_layer else True
    depth = max(
        abs(min(base_elev, 0.0)),
        options.min_depth_cohesive if cohesive else options.min_depth_cohesionless,
        options.min_depth_general,
    )
    k = options.raft_k if options.raft_k > 0 else (
        subgrade_modulus(borehole, base_layer, depth) if base_layer else 15000.0
    )
    k = max(k, 1000.0)
    E = 4700.0 * math.sqrt(max(materials.f_c, 15.0)) * 1000.0  # kPa
    nu = 0.20

    rigid_service, service_total = rigid_pressure(
        elements, length, width, thickness, materials.gamma_concrete,
        factored=False, polygon=outline,
    )
    rigid_factored, factored_total = rigid_pressure(
        elements, length, width, thickness, materials.gamma_concrete,
        factored=True, polygon=outline,
    )

    area = polygon_area(outline)
    settlement = estimate_shallow_settlement(
        borehole, depth, math.sqrt(area), math.sqrt(area),
        max(rigid_service.q_avg - 18.0 * depth, 0.0), options,
    )

    analysis = RaftAnalysis(
        method=method,
        x0=x0, y0=y0, length=length, width=width, thickness=thickness, area=area,
        outline=outline,
        depth=depth, k_subgrade=k,
        q_service_max=rigid_service.q_max,
        q_service_min=rigid_service.q_min,
        q_service_avg=rigid_service.q_avg,
        q_factored_avg=rigid_factored.q_avg,
        q_allow=q_allow,
        e_x=rigid_service.e_x, e_y=rigid_service.e_y, kern_ok=rigid_service.kern_ok,
        service_load=service_total, factored_load=factored_total,
        settlement=settlement.total, settlement_limit=settlement.limit,
    )

    strip_result = None
    plate_result = None
    if method.lower().startswith("plate"):
        plate_result = _winkler_plate(
            elements, x0, y0, length, width, thickness, k, E, nu,
            materials.gamma_concrete, factored=True, outline=outline,
        )
        plate_service = _winkler_plate(
            elements, x0, y0, length, width, thickness, k, E, nu,
            materials.gamma_concrete, factored=False, outline=outline,
        )
        analysis.moment_x_pos = plate_result["moment_x_pos"]
        analysis.moment_x_neg = plate_result["moment_x_neg"]
        analysis.moment_y_pos = plate_result["moment_y_pos"]
        analysis.moment_y_neg = plate_result["moment_y_neg"]
        analysis.shear_x = plate_result["shear_x"]
        analysis.shear_y = plate_result["shear_y"]
        analysis.deflection = plate_result["deflection"]
        analysis.differential = plate_result["differential"]
        analysis.differential_checked = True
        analysis.q_local_max = plate_service["q_max"]
        analysis.q_local_min = plate_service["q_min"]
        analysis.service_moment_x_pos = plate_service["moment_x_pos"]
        analysis.service_moment_x_neg = plate_service["moment_x_neg"]
        analysis.service_moment_y_pos = plate_service["moment_y_pos"]
        analysis.service_moment_y_neg = plate_service["moment_y_neg"]
        analysis.details["plate"] = plate_result
        analysis.details["plate_service"] = plate_service
    elif method.lower().startswith("rigid"):
        analysis.details["rigid"] = {
            "q_max": rigid_service.q_max, "q_min": rigid_service.q_min,
            "q_avg": rigid_service.q_avg,
        }
    else:
        strip_result = _winkler_strips(
            elements, x0, y0, length, width, thickness, k, E,
            materials.gamma_concrete, factored=True,
        )
        strip_service = _winkler_strips(
            elements, x0, y0, length, width, thickness, k, E,
            materials.gamma_concrete, factored=False,
        )
        analysis.moment_x_pos = strip_result["moment_x_pos"]
        analysis.moment_x_neg = strip_result["moment_x_neg"]
        analysis.moment_y_pos = strip_result["moment_y_pos"]
        analysis.moment_y_neg = strip_result["moment_y_neg"]
        analysis.shear_x = strip_result["shear_x"]
        analysis.shear_y = strip_result["shear_y"]
        analysis.deflection = strip_result["deflection"]
        analysis.differential = strip_result["differential"]
        analysis.differential_checked = True
        analysis.q_local_max = strip_service["q_max"]
        analysis.q_local_min = strip_service["q_min"]
        analysis.service_moment_x_pos = strip_service["moment_x_pos"]
        analysis.service_moment_x_neg = strip_service["moment_x_neg"]
        analysis.service_moment_y_pos = strip_service["moment_y_pos"]
        analysis.service_moment_y_neg = strip_service["moment_y_neg"]
        analysis.details["strips"] = strip_result
        analysis.details["strips_service"] = strip_service
    if strip_result is None and plate_result is not None:
        strip_result = _winkler_strips(
            elements, x0, y0, length, width, thickness, k, E,
            materials.gamma_concrete, factored=True,
        )
        analysis.details["strips_check"] = strip_result
        if not analysis.differential_checked:
            analysis.differential = strip_result["differential"]
            analysis.differential_checked = True

    # Factored contact pressure for punching / one-way shear checks.
    q_u_avg = rigid_factored.q_avg
    d = max(thickness * 1000.0 - materials.cover - 10.0, 50.0)
    punching_vu = 0.0
    punching_cap = 0.0
    for e in elements:
        r = _governing_factored(e)
        if e.kind == "wall":
            c_l = max(e.section_projection_x, 0.25) * 1000.0
            c_b = max(e.section_projection_y, 0.20) * 1000.0
        else:
            c_l = max(e.section_projection_x, 0.25) * 1000.0
            c_b = max(e.section_projection_y, 0.25) * 1000.0
        circular = e.kind == "column" and e.is_circular
        b0, critical_area, beta = punching_geometry(
            c_l, c_b, d, circular=circular
        )
        vu = max(r.P - q_u_avg * critical_area / 1e6, 0.0)
        cap = punching_shear_capacity(
            b0, d, materials.f_c, beta=beta, alpha_s=40.0, phi=materials.phi_shear
        )
        if vu / max(cap, 1e-6) > punching_vu / max(punching_cap, 1e-6):
            punching_vu, punching_cap = vu, cap
    analysis.punching_vu = punching_vu
    analysis.punching_capacity = punching_cap
    one_way_cap = one_way_shear_capacity(1000.0, d, materials.f_c, materials.phi_shear)
    analysis.one_way_utilization = max(
        analysis.shear_x / max(one_way_cap, 1e-6),
        analysis.shear_y / max(one_way_cap, 1e-6),
    )

    # Buoyancy check: uplift pressure on the raft soffit.
    gwt = borehole.gwt
    if depth > gwt:
        uplift_pressure = 9.81 * (depth - gwt)
        analysis.buoyancy_uplift = uplift_pressure * area
    else:
        analysis.buoyancy_uplift = 0.0

    notes: list[str] = []
    status = "OK"
    if analysis.q_service_max > q_allow * 1.0 + 1e-6:
        status = "FAIL"
        notes.append(f"Contact pressure {analysis.q_service_max:.1f} > {q_allow:.1f} kPa")
    if analysis.q_local_max > 1.5 * q_allow:
        notes.append(
            f"Local strip/plate pressure {analysis.q_local_max:.1f} kPa is high; "
            "check local bearing/punching"
        )
    if not analysis.kern_ok:
        status = "CHECK" if status == "OK" else status
        notes.append("Resultant outside the kern; check raft eccentricity")
    if not settlement.ok:
        status = "CHECK" if status == "OK" else status
        notes.append(settlement.note)
    diff_mm = analysis.differential * 1000.0
    if analysis.differential_checked and diff_mm > options.differential_limit + 1e-6:
        status = "CHECK" if status == "OK" else status
        notes.append(
            f"Differential deflection {diff_mm:.1f} mm > "
            f"{options.differential_limit:.1f} mm"
        )
    if not analysis.differential_checked:
        notes.append(
            f"Differential deflection not checked for the {method} method; "
            "verify with a plate or strip analysis"
        )
    if analysis.punching_vu > analysis.punching_capacity + 1e-6:
        status = "CHECK" if status == "OK" else status
        notes.append("Punching shear at a column exceeds capacity")
    if analysis.one_way_utilization > 1.0 + 1e-6:
        status = "CHECK" if status == "OK" else status
        notes.append("One-way shear exceeds capacity")
    if analysis.buoyancy_uplift > analysis.service_load:
        status = "CHECK" if status == "OK" else status
        notes.append("Buoyancy uplift exceeds service dead load; provide anchorage")
    if method.lower().startswith("plate"):
        notes.append("Plate method: Kirchhoff plate on Winkler springs; free edges")
    elif method.lower().startswith("winkler"):
        notes.append("Winkler strips: orthogonal beam strips with free ends")
        if len(options.raft_outline or []) >= 3:
            notes.append(
                "Non-rectangular outline with Winkler strips is approximate; "
                "use Plate analysis for the exact masked mat"
            )
    if len(options.raft_outline or []) >= 3:
        notes.append(f"Imported raft outline: {len(outline)} vertices, area {area:.2f} m2")

    analysis.status = status
    analysis.remarks = "; ".join(notes)
    analysis.details.update({
        "rigid_service": {
            "q_max": rigid_service.q_max, "q_min": rigid_service.q_min,
            "q_avg": rigid_service.q_avg, "e_x": rigid_service.e_x,
            "e_y": rigid_service.e_y, "total": service_total,
        },
        "rigid_factored": {
            "q_max": rigid_factored.q_max, "q_min": rigid_factored.q_min,
            "q_avg": rigid_factored.q_avg, "total": factored_total,
        },
        "settlement": settlement,
        "d_mm": d,
        "one_way_capacity": one_way_cap,
        "base_layer": base_layer.soil_type if base_layer else "",
    })
    return analysis
