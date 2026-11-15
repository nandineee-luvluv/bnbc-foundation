"""Plan-geometry helpers for columns, shear walls and foundation outlines.

The design code uses two coordinate systems:

* global site coordinates ``(x, y)`` in metres, and
* local wall coordinates ``(u, v)`` where ``u`` runs along the wall and
  ``v`` is normal to it.

All polygons returned here are convex and ordered counter-clockwise.  They are
used for plotting, site-boundary checks and overlap checks between foundations.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

Point = tuple[float, float]
Rect = tuple[float, float, float, float]


def rotate(point: Point, angle_deg: float, origin: Point = (0.0, 0.0)) -> Point:
    """Rotate *point* about *origin* by *angle_deg* (counter-clockwise)."""
    a = math.radians(angle_deg)
    ca, sa = math.cos(a), math.sin(a)
    x, y = point[0] - origin[0], point[1] - origin[1]
    return (origin[0] + x * ca - y * sa, origin[1] + x * sa + y * ca)


def rectangle_polygon(x0: float, y0: float, x1: float, y1: float) -> list[Point]:
    """Axis-aligned rectangle polygon."""
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def rotated_rectangle_polygon(
    center_x: float,
    center_y: float,
    length: float,
    width: float,
    angle_deg: float = 0.0,
) -> list[Point]:
    """Rectangle centred at ``(center_x, center_y)``, rotated about its centre."""
    hl, hw = max(length, 0.0) / 2.0, max(width, 0.0) / 2.0
    corners = [(-hl, -hw), (hl, -hw), (hl, hw), (-hl, hw)]
    return [rotate((center_x + x, center_y + y), angle_deg, (center_x, center_y))
            for x, y in corners]


def segment_rectangle_polygon(
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    thickness: float,
) -> list[Point]:
    """Rectangle representing a wall of thickness *thickness* between endpoints."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return [(x1, y1), (x1, y1), (x1, y1), (x1, y1)]
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    half = max(thickness, 0.0) / 2.0
    return [
        (x1 + nx * half, y1 + ny * half),
        (x2 + nx * half, y2 + ny * half),
        (x2 - nx * half, y2 - ny * half),
        (x1 - nx * half, y1 - ny * half),
    ]


def circle_polygon(cx: float, cy: float, diameter: float, segments: int = 32) -> list[Point]:
    """Polygonal approximation of a circular column footprint."""
    r = max(diameter, 0.0) / 2.0
    n = max(int(segments), 8)
    return [
        (cx + r * math.cos(2.0 * math.pi * i / n),
         cy + r * math.sin(2.0 * math.pi * i / n))
        for i in range(n)
    ]


def polygon_bounds(polygon: Sequence[Point]) -> Rect:
    if not polygon:
        return (0.0, 0.0, 0.0, 0.0)
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return (min(xs), min(ys), max(xs), max(ys))


def rect_polygon(rect: Rect) -> list[Point]:
    x0, y0, x1, y1 = rect
    return rectangle_polygon(x0, y0, x1, y1)


def polygon_area(polygon: Sequence[Point]) -> float:
    if len(polygon) < 3:
        return 0.0
    area = 0.0
    for i, (x0, y0) in enumerate(polygon):
        x1, y1 = polygon[(i + 1) % len(polygon)]
        area += x0 * y1 - x1 * y0
    return abs(area) / 2.0


def signed_polygon_area(polygon: Sequence[Point]) -> float:
    """Signed area (positive for counter-clockwise ordering)."""
    if len(polygon) < 3:
        return 0.0
    area = 0.0
    for i, (x0, y0) in enumerate(polygon):
        x1, y1 = polygon[(i + 1) % len(polygon)]
        area += x0 * y1 - x1 * y0
    return area / 2.0


def ensure_ccw(polygon: Sequence[Point]) -> list[Point]:
    pts = [tuple(p) for p in polygon]
    return pts if signed_polygon_area(pts) >= 0.0 else list(reversed(pts))


def polygon_centroid(polygon: Sequence[Point]) -> Point:
    """Area centroid of a simple polygon."""
    pts = ensure_ccw(polygon)
    if len(pts) < 3:
        return (0.0, 0.0)
    a = signed_polygon_area(pts)
    if abs(a) < 1e-12:
        return (
            sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts),
        )
    cx = cy = 0.0
    for i, (x0, y0) in enumerate(pts):
        x1, y1 = pts[(i + 1) % len(pts)]
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    return (cx / (6.0 * a), cy / (6.0 * a))


def polygon_second_moments(
    polygon: Sequence[Point],
) -> tuple[float, float, float, float]:
    """Return ``(area, Ixx, Iyy, Ixy)`` about the polygon centroid.

    ``Ixx`` is the second moment about a horizontal axis through the centroid
    and ``Iyy`` about a vertical axis.  The conventions match the usual
    structural pressure equations ``Mx = E Ixx`` and ``My = E Iyy``.
    """
    pts = ensure_ccw(polygon)
    if len(pts) < 3:
        return 0.0, 0.0, 0.0, 0.0
    a = signed_polygon_area(pts)
    if abs(a) < 1e-12:
        return 0.0, 0.0, 0.0, 0.0
    ixx = iyy = ixy = 0.0
    for i, (x0, y0) in enumerate(pts):
        x1, y1 = pts[(i + 1) % len(pts)]
        cross = x0 * y1 - x1 * y0
        ixx += (y0 * y0 + y0 * y1 + y1 * y1) * cross
        iyy += (x0 * x0 + x0 * x1 + x1 * x1) * cross
        ixy += (x0 * y1 + 2.0 * x0 * y0 + 2.0 * x1 * y1 + x1 * y0) * cross
    ixx /= 12.0
    iyy /= 12.0
    ixy /= 24.0
    cx, cy = polygon_centroid(pts)
    ixx -= a * cy * cy
    iyy -= a * cx * cx
    ixy -= a * cx * cy
    return a, max(ixx, 0.0), max(iyy, 0.0), ixy


def point_in_polygon(point: Point, polygon: Sequence[Point], tol: float = 1e-9) -> bool:
    """Ray-casting point-in-polygon test (boundary counts as inside)."""
    if len(polygon) < 3:
        return False
    x, y = point
    inside = False
    n = len(polygon)
    for i in range(n):
        x0, y0 = polygon[i]
        x1, y1 = polygon[(i + 1) % n]
        # Boundary proximity.
        if _point_segment_distance(point, (x0, y0), (x1, y1)) <= tol:
            return True
        if (y0 > y) != (y1 > y):
            x_cross = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if x < x_cross:
                inside = not inside
    return inside


def _projections(polygon: Sequence[Point], axis: Point) -> tuple[float, float]:
    ax, ay = axis
    values = [p[0] * ax + p[1] * ay for p in polygon]
    return min(values), max(values)


def polygons_overlap(
    first: Sequence[Point],
    second: Sequence[Point],
    clearance: float = 0.0,
) -> bool:
    """True if two convex polygons overlap or are closer than *clearance*."""
    if len(first) < 3 or len(second) < 3:
        return False
    # Separating-axis test.  Clearance is applied by expanding every projection
    # interval; for closely spaced convex footprints this is equivalent to the
    # usual clearance check for axis-aligned and wall-oriented rectangles.
    for polygon in (first, second):
        n = len(polygon)
        for i in range(n):
            x0, y0 = polygon[i]
            x1, y1 = polygon[(i + 1) % n]
            edge = (x1 - x0, y1 - y0)
            length = math.hypot(*edge)
            if length < 1e-12:
                continue
            axis = (-edge[1] / length, edge[0] / length)
            a_min, a_max = _projections(first, axis)
            b_min, b_max = _projections(second, axis)
            if a_max + clearance <= b_min or b_max + clearance <= a_min:
                return False
    return True


def polygon_within_rect(polygon: Sequence[Point], rect: Rect, tol: float = 0.05) -> bool:
    x0, y0, x1, y1 = rect
    return all(
        x0 - tol <= x <= x1 + tol and y0 - tol <= y <= y1 + tol
        for x, y in polygon
    )


def _point_segment_distance(point: Point, a: Point, b: Point) -> float:
    px, py = point
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq <= 1e-18:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def distance_between_polygons(first: Sequence[Point], second: Sequence[Point]) -> float:
    """Minimum distance between two convex polygon boundaries (0 if overlapping)."""
    if polygons_overlap(first, second):
        return 0.0
    best = float("inf")
    for polygon, other in ((first, second), (second, first)):
        n = len(polygon)
        for i in range(n):
            a, b = polygon[i], polygon[(i + 1) % n]
            m = len(other)
            for j in range(m):
                c, d = other[j], other[(j + 1) % m]
                best = min(best, _segment_segment_distance(a, b, c, d))
    return best


def _segment_segment_distance(a: Point, b: Point, c: Point, d: Point) -> float:
    # If the segments cross, the distance is zero.
    def orient(p: Point, q: Point, r: Point) -> float:
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    o1, o2 = orient(a, b, c), orient(a, b, d)
    o3, o4 = orient(c, d, a), orient(c, d, b)
    if (o1 * o2 < 0.0) and (o3 * o4 < 0.0):
        return 0.0
    return min(
        _point_segment_distance(a, c, d),
        _point_segment_distance(b, c, d),
        _point_segment_distance(c, a, b),
        _point_segment_distance(d, a, b),
    )


def footprint_polygon_for_rect(
    center_x: float,
    center_y: float,
    length: float,
    width: float,
    angle_deg: float = 0.0,
) -> list[Point]:
    return rotated_rectangle_polygon(center_x, center_y, length, width, angle_deg)


def merge_bounds(rects: Iterable[Rect]) -> Rect:
    rects = list(rects)
    if not rects:
        return (0.0, 0.0, 0.0, 0.0)
    return (
        min(r[0] for r in rects),
        min(r[1] for r in rects),
        max(r[2] for r in rects),
        max(r[3] for r in rects),
    )
