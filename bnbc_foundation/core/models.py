"""Data models for the BNBC 2020 foundation design tool.

All units are SI unless stated otherwise:
    length          m (plan dimensions, depths, pile lengths)
    thickness       mm (structural thickness, cover, bar diameters)
    force           kN
    moment          kN.m
    pressure        kPa (kN/m2)
    stress          MPa (N/mm2)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import date
import math
from typing import Any

from .geometry import (
    circle_polygon,
    polygon_bounds,
    rotated_rectangle_polygon,
    segment_rectangle_polygon,
)
from .units import convert, convert_text


# ---------------------------------------------------------------------------
# Project and materials
# ---------------------------------------------------------------------------


@dataclass
class ProjectInfo:
    name: str = "Untitled Foundation Project"
    location: str = ""
    engineer: str = ""
    date: str = field(default_factory=lambda: date.today().isoformat())
    code: str = "BNBC 2020"
    units: str = "SI"
    notes: str = ""


@dataclass
class Materials:
    f_c: float = 30.0                 # MPa, cylinder strength
    f_y: float = 420.0                # MPa
    gamma_concrete: float = 24.0      # kN/m3
    cover: float = 75.0               # mm, bottom cover for footings/pile caps
    phi_flexure: float = 0.90
    phi_shear: float = 0.75
    phi_bearing: float = 0.65
    bar_diameters: list[float] = field(default_factory=lambda: [12.0, 16.0, 20.0, 25.0])
    max_bar_spacing: float = 300.0    # mm
    min_bar_spacing: float = 100.0    # mm
    concrete_unit_weight: float = 24.0  # kN/m3, kept for backwards compatibility

    def bar_areas(self) -> dict[float, float]:
        return {d: 3.141592653589793 * d * d / 4.0 for d in self.bar_diameters}


# ---------------------------------------------------------------------------
# Soil
# ---------------------------------------------------------------------------


SOIL_TYPES = [
    "Fill",
    "CL", "CH", "ML", "MH", "OL", "OH",
    "SM", "SC", "SP", "SW", "GP", "GW", "GM", "GC",
    "Silt", "Sand", "Clay", "Rock",
]


def is_cohesive(soil_type: str) -> bool:
    s = soil_type.lower()
    return any(k in s for k in ("cl", "ch", "ml", "mh", "ol", "oh", "clay", "silt"))


def is_cohesionless(soil_type: str) -> bool:
    s = soil_type.lower()
    return any(k in s for k in ("sand", "gravel", "sp", "sw", "gp", "gw", "sm", "sc", "gm", "gc"))


@dataclass
class SoilLayer:
    bottom_depth: float = 1.0         # m below ground
    soil_type: str = "CL"
    description: str = ""
    gamma: float = 18.0               # kN/m3, moist/bulk
    gamma_sat: float = 19.0           # kN/m3, saturated
    cohesion: float = 0.0             # kPa, c'
    friction_angle: float = 0.0       # degrees, phi'
    cu: float = 0.0                   # kPa, undrained shear strength
    n_raw: float = 0.0                # raw SPT blow count
    n60: float = 0.0                  # corrected N60 (0 => derive from n_raw)
    cc: float = 0.0                   # compression index
    e0: float = 0.0                   # initial void ratio
    ocr: float = 1.0                  # overconsolidation ratio
    ll: float = 0.0                   # liquid limit, %
    pl: float = 0.0                   # plastic limit, %
    fines: float = 0.0                # fines content, %
    es: float = 0.0                   # soil modulus, kPa (0 => correlate)
    k_subgrade: float = 0.0           # kN/m3 (0 => correlate)
    allowable_bearing: float | None = None   # kPa, direct report value
    pile_skin: float | None = None           # kPa, direct report value
    pile_end: float | None = None            # kPa, direct report value
    pile_skin_driven: float | None = None    # kPa, direct report overrides
    pile_end_driven: float | None = None
    pile_skin_bored: float | None = None
    pile_end_bored: float | None = None
    # Cone-penetration-test data (optional).  ``qc`` is the measured cone
    # resistance in MPa and ``cpt_fs`` is the sleeve friction in kPa.
    qc: float = 0.0
    cpt_fs: float = 0.0
    cpt_u2: float = 0.0               # pore pressure, kPa (optional)

    def effective_n60(self) -> float:
        if self.n60 and self.n60 > 0:
            return self.n60
        return max(self.n_raw, 0.0)

    def is_cohesive(self) -> bool:
        return is_cohesive(self.soil_type)


@dataclass
class Borehole:
    id: str = "BH-1"
    x: float = 0.0
    y: float = 0.0
    gwt: float = 2.0                  # m below ground
    layers: list[SoilLayer] = field(default_factory=list)

    def sorted_layers(self) -> list[SoilLayer]:
        return sorted(self.layers, key=lambda l: l.bottom_depth)

    def layer_top(self, index: int) -> float:
        layers = self.sorted_layers()
        return 0.0 if index == 0 else layers[index - 1].bottom_depth

    def layer_at_depth(self, z: float) -> SoilLayer | None:
        layers = self.sorted_layers()
        top = 0.0
        for layer in layers:
            if top <= z <= layer.bottom_depth + 1e-9:
                return layer
            top = layer.bottom_depth
        return layers[-1] if layers else None

    def layer_index_at_depth(self, z: float) -> int:
        layers = self.sorted_layers()
        top = 0.0
        for i, layer in enumerate(layers):
            if top <= z <= layer.bottom_depth + 1e-9:
                return i
            top = layer.bottom_depth
        return max(len(layers) - 1, 0)

    def total_depth(self) -> float:
        layers = self.sorted_layers()
        return layers[-1].bottom_depth if layers else 0.0

    def spt_at_depth(self, z: float) -> float:
        layer = self.layer_at_depth(z)
        return layer.effective_n60() if layer else 0.0

    def allowable_bearing_at(self, z: float) -> float | None:
        layer = self.layer_at_depth(z)
        return layer.allowable_bearing if layer else None

    def average_n60(self, top: float, bottom: float) -> float:
        layers = self.sorted_layers()
        total = 0.0
        weighted = 0.0
        current = 0.0
        for layer in layers:
            l_top = current
            l_bottom = layer.bottom_depth
            overlap = max(0.0, min(bottom, l_bottom) - max(top, l_top))
            if overlap > 0:
                weighted += layer.effective_n60() * overlap
                total += overlap
            current = l_bottom
        return weighted / total if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Loads
# ---------------------------------------------------------------------------


@dataclass
class Reaction:
    case: str = "Service"
    P: float = 0.0                   # kN, compression positive
    Mx: float = 0.0                  # kN.m about x-axis
    My: float = 0.0                  # kN.m about y-axis
    Vx: float = 0.0                  # kN
    Vy: float = 0.0                  # kN
    factored: bool = False
    includes_lateral: bool = False
    buoyancy: float = 0.0            # kN uplift


@dataclass
class Element:
    id: str = "C1"
    kind: str = "column"             # "column" or "wall"
    x: float = 0.0                   # m, insertion/reaction point (column) or wall reference point
    y: float = 0.0                   # m, insertion/reaction point (column) or wall reference point
    base_elev: float = 0.0           # m, relative to ground surface (negative = below)
    length: float = 0.5              # m, column section along x / wall length (legacy fallback)
    width: float = 0.5               # m, column section along y
    wall_thickness: float = 0.25     # m
    preferred: str = "Auto"          # Auto / Isolated / Combined / Strip / Single pile / Pile group / Raft
    reactions: list[Reaction] = field(default_factory=lambda: [Reaction()])
    notes: str = ""
    # Geometry additions. They are appended after ``notes`` so existing
    # positional Element(...) construction remains compatible.
    dx: float = 0.0                  # m, insertion point to column centre, +x
    dy: float = 0.0                  # m, insertion point to column centre, +y
    shape: str = "Rectangular"       # Rectangular / Circular
    diameter: float = 0.0            # m, circular column diameter
    x1: float | None = None          # wall centreline start
    y1: float | None = None
    x2: float | None = None          # wall centreline end
    y2: float | None = None
    rotation: float = 0.0            # deg, CCW rotation of a rectangular column

    # -- basic geometry ---------------------------------------------------

    @property
    def is_wall(self) -> bool:
        return self.kind == "wall"

    @property
    def is_circular(self) -> bool:
        if self.kind != "column":
            return False
        return "circ" in self.shape.lower() or "round" in self.shape.lower()

    def has_wall_endpoints(self) -> bool:
        return (
            self.kind == "wall"
            and self.x1 is not None and self.y1 is not None
            and self.x2 is not None and self.y2 is not None
            and math.hypot(self.x2 - self.x1, self.y2 - self.y1) > 1e-9
        )

    @property
    def wall_endpoints(self) -> tuple[float, float, float, float]:
        """Wall centreline endpoints, falling back to legacy x/y/length input."""
        if self.has_wall_endpoints():
            return (float(self.x1), float(self.y1), float(self.x2), float(self.y2))
        half = max(self.length, 0.0) / 2.0
        return (self.x - half, self.y, self.x + half, self.y)

    @property
    def wall_length(self) -> float:
        if self.has_wall_endpoints():
            x1, y1, x2, y2 = self.wall_endpoints
            return math.hypot(x2 - x1, y2 - y1)
        return max(self.length, 0.01)

    @property
    def wall_angle_deg(self) -> float:
        if self.has_wall_endpoints():
            x1, y1, x2, y2 = self.wall_endpoints
            return math.degrees(math.atan2(y2 - y1, x2 - x1))
        return 0.0

    @property
    def column_center(self) -> tuple[float, float]:
        return (self.x + self.dx, self.y + self.dy)

    @property
    def center(self) -> tuple[float, float]:
        """Actual plan centroid: column centre or wall centreline midpoint."""
        if self.kind == "wall" and self.has_wall_endpoints():
            x1, y1, x2, y2 = self.wall_endpoints
            return (0.5 * (x1 + x2), 0.5 * (y1 + y2))
        if self.kind == "column":
            return self.column_center
        return (self.x, self.y)

    @property
    def center_x(self) -> float:
        return self.center[0]

    @property
    def center_y(self) -> float:
        return self.center[1]

    @property
    def section_length(self) -> float:
        """Column dimension along x (diameter for a circular column)."""
        if self.is_circular:
            return max(self.diameter if self.diameter > 0 else self.length, 0.01)
        return max(self.length, 0.01)

    @property
    def section_width(self) -> float:
        """Column dimension along y (diameter for a circular column)."""
        if self.is_circular:
            return max(self.diameter if self.diameter > 0 else self.width, 0.01)
        return max(self.width, 0.01)

    @property
    def footprint_area(self) -> float:
        if self.kind == "wall":
            return max(self.wall_length, 0.01) * max(self.wall_thickness, 0.01)
        if self.is_circular:
            d = self.section_length
            return math.pi * d * d / 4.0
        return max(self.length, 0.01) * max(self.width, 0.01)

    @property
    def footprint_polygon(self) -> list[tuple[float, float]]:
        if self.kind == "wall":
            x1, y1, x2, y2 = self.wall_endpoints
            return segment_rectangle_polygon(x1, y1, x2, y2, self.wall_thickness)
        cx, cy = self.center
        if self.is_circular:
            return circle_polygon(cx, cy, self.section_length)
        return rotated_rectangle_polygon(
            cx, cy, self.section_length, self.section_width, self.section_angle_deg
        )

    @property
    def section_angle_deg(self) -> float:
        """Plan rotation of the column section (walls follow the wall axis)."""
        return self.wall_angle_deg if self.kind == "wall" else self.rotation

    @property
    def section_projection_x(self) -> float:
        """Projected section width on the global x-axis after rotation."""
        if self.is_circular:
            return self.section_length
        a = math.radians(self.section_angle_deg)
        return abs(self.section_length * math.cos(a)) + abs(
            self.section_width * math.sin(a)
        )

    @property
    def section_projection_y(self) -> float:
        """Projected section width on the global y-axis after rotation."""
        if self.is_circular:
            return self.section_width
        a = math.radians(self.section_angle_deg)
        return abs(self.section_length * math.sin(a)) + abs(
            self.section_width * math.cos(a)
        )

    @property
    def footprint_bounds(self) -> tuple[float, float, float, float]:
        return polygon_bounds(self.footprint_polygon)

    # -- reaction transformation -----------------------------------------

    def reaction_at_center(self, reaction: Reaction) -> Reaction:
        """Move a column reaction from its insertion point to the column centre.

        Analysis packages usually report the reaction at the insertion point.
        A column centre offset ``(dx, dy)`` adds the moment of the vertical
        reaction about the centre: ``Mx_c = Mx - P*dy`` and
        ``My_c = My - P*dx``. Wall reactions are already taken about the wall
        centreline and are returned unchanged.
        """
        if self.kind != "column" or (abs(self.dx) < 1e-12 and abs(self.dy) < 1e-12):
            return reaction
        return replace(
            reaction,
            Mx=reaction.Mx - reaction.P * self.dy,
            My=reaction.My - reaction.P * self.dx,
        )

    def reactions_at_center(self) -> list[Reaction]:
        return [self.reaction_at_center(r) for r in self.reactions]

    def service_reactions(self) -> list[Reaction]:
        return [r for r in self.reactions_at_center() if not r.factored]

    def factored_reactions(self) -> list[Reaction]:
        return [r for r in self.reactions_at_center() if r.factored]

    def wall_local_moments(self, reaction: Reaction) -> tuple[float, float]:
        """Return ``(M_along_wall, M_normal_to_wall)`` for a wall reaction.

        ``M_along_wall`` is the moment about the wall axis and produces pressure
        variation across the wall thickness. ``M_normal`` is the in-plane moment
        about the normal axis and drives the pile group along the wall.
        """
        theta = math.radians(self.wall_angle_deg)
        ca, sa = math.cos(theta), math.sin(theta)
        m_along = reaction.Mx * ca + reaction.My * sa
        m_normal = reaction.My * ca - reaction.Mx * sa
        return m_along, m_normal

    def wall_local_reaction(self, reaction: Reaction) -> Reaction:
        m_along, m_normal = self.wall_local_moments(reaction)
        return replace(reaction, Mx=m_along, My=m_normal)

    def max_service(self) -> Reaction:
        candidates = self.service_reactions() or self.reactions
        if not candidates:
            return Reaction()
        return max(candidates, key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My))

    def max_factored(self) -> Reaction:
        candidates = self.factored_reactions()
        if candidates:
            return max(candidates, key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My))
        # Conservative default when only service data is supplied:
        s = self.max_service()
        return Reaction(
            case="Derived factored envelope",
            P=1.4 * s.P,
            Mx=1.4 * s.Mx,
            My=1.4 * s.My,
            Vx=1.4 * s.Vx,
            Vy=1.4 * s.Vy,
            factored=True,
            includes_lateral=s.includes_lateral,
        )


# ---------------------------------------------------------------------------
# Design options
# ---------------------------------------------------------------------------


@dataclass
class FoundationOptions:
    # Allowed foundation systems
    allow_isolated: bool = True
    allow_combined: bool = True
    allow_raft: bool = True
    allow_single_pile: bool = True
    allow_pile_group: bool = True
    allow_strip: bool = True
    prefer_shallow: bool = True
    optimize_cost: bool = False

    # Shallow foundation geometry
    min_footing_dim: float = 0.80
    max_footing_dim: float = 8.00
    footing_dim_step: float = 0.05
    min_thickness_soil: float = 150.0       # mm
    min_thickness_pile: float = 300.0       # mm
    min_depth_cohesive: float = 1.5         # m, exterior
    min_depth_cohesionless: float = 2.0     # m, exterior
    min_depth_general: float = 0.5          # m

    # Factors of safety and control
    fs_shallow: float = 2.5
    fs_pile: float = 3.0
    pile_control: str = "Normal"             # Good / Normal / Poor / Very Poor
    pile_design_method: str = "SPT"          # SPT / Static / Direct

    # Piles
    pile_type: str = "Bored"                 # Driven / Bored / Drilled shaft
    pile_diameters: list[float] = field(default_factory=lambda: [0.40, 0.50, 0.60, 0.75, 0.90, 1.20])
    pile_lengths: list[float] = field(default_factory=lambda: [10.0, 15.0, 20.0, 25.0, 30.0])
    max_pile_length: float = 40.0
    pile_spacing_end_bearing: float = 2.5
    pile_spacing_friction: float = 3.0
    min_pile_spacing: float = 0.75
    cap_edge_cover: float = 0.10             # m
    cap_embedment: float = 0.075             # m
    cap_min_thickness: float = 300.0         # mm
    cap_cover: float = 50.0                  # mm
    group_efficiency: float = 1.0
    single_pile_min_diameter: float = 0.60

    # Settlement / serviceability
    settlement_limit_sand: float = 25.0      # mm
    settlement_limit_clay: float = 40.0      # mm
    differential_limit: float = 20.0         # mm
    angular_limit: float = 1.0 / 500.0

    # Seismic / liquefaction
    pga_g: float = 0.0                      # peak ground acceleration, g (0 => not assessed)

    # Raft
    raft_overhang: float = 0.5               # m beyond outermost element
    raft_min_thickness: float = 500.0        # mm
    raft_analysis: str = "Auto"              # Auto / Rigid / Winkler strips / Plate
    raft_k: float = 0.0                      # kN/m3, 0 => correlated
    raft_trigger: str = "Auto"               # Auto / Always / Never
    raft_outline: list[list[float]] = field(default_factory=list)  # [[x,y], ...] imported mat outline

    # Additional serviceability / pile checks
    crack_width_limit: float = 0.30          # mm, service crack width limit
    crack_check: bool = True
    uplift_check: bool = True
    uplift_fs: float = 1.10                  # buoyancy/uplift factor of safety
    pile_uplift_fs: float = 2.00             # pile uplift factor of safety
    pile_lateral_fs: float = 2.50            # Broms lateral factor of safety
    pile_pm_check: bool = True
    pile_downdrag_check: bool = True
    pile_lateral_check: bool = True

    # Site constraints
    site_xmin: float = -1000.0
    site_xmax: float = 1000.0
    site_ymin: float = -1000.0
    site_ymax: float = 1000.0
    max_footing_area_ratio: float = 0.50

    # Cost rates (optional)
    cost_concrete: float = 0.0               # per m3
    cost_excavation: float = 0.0             # per m3
    cost_pile: float = 0.0                   # per m
    cost_steel: float = 0.0                  # per kg
    cost_raft: float = 0.0                   # per m2


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class DesignResult:
    element_id: str = ""
    element_kind: str = "column"
    foundation_type: str = ""
    requirement: str = ""
    quantity: int = 1
    size: str = ""
    length: float = 0.0
    width: float = 0.0
    thickness: float = 0.0
    depth: float = 0.0
    pile_diameter: float = 0.0
    pile_length: float = 0.0
    pile_count: int = 0
    cap_length: float = 0.0
    cap_width: float = 0.0
    cap_thickness: float = 0.0
    service_load: float = 0.0
    factored_load: float = 0.0
    q_service_max: float = 0.0
    q_allow: float = 0.0
    utilization: float = 0.0
    settlement: float = 0.0
    settlement_limit: float = 0.0
    status: str = "OK"
    governing: str = ""
    remarks: str = ""
    alternatives: list[str] = field(default_factory=list)
    covers: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    concrete_volume: float = 0.0
    steel_weight: float = 0.0
    pile_length_total: float = 0.0
    cost: float = 0.0

    def schedule_row(self, units: str = "SI") -> list[Any]:
        return [
            self.element_id,
            self.element_kind,
            self.foundation_type,
            convert_text(self.requirement, units),
            self.quantity,
            convert_text(self.size, units),
            f"{convert(self.thickness, 'length_mm', units):.0f}" if self.thickness else "-",
            f"{convert(self.pile_diameter * 1000, 'length_mm', units):.0f}" if self.pile_diameter else "-",
            f"{convert(self.pile_length, 'length', units):.1f}" if self.pile_length else "-",
            self.pile_count or "-",
            f"{convert(self.cap_length, 'length', units):.1f}x"
            f"{convert(self.cap_width, 'length', units):.1f}x"
            f"{convert(self.cap_thickness / 1000, 'length', units):.2f}"
            if self.cap_length else "-",
            f"{convert(self.q_service_max, 'pressure', units):.1f}" if self.q_service_max else "-",
            f"{convert(self.q_allow, 'pressure', units):.1f}" if self.q_allow else "-",
            f"{self.utilization:.2f}" if self.utilization else "-",
            f"{convert(self.settlement, 'settlement', units):.1f}" if self.settlement else "-",
            convert_text(self.governing, units),
            self.status,
            convert_text(self.remarks, units),
        ]


# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------


@dataclass
class Project:
    info: ProjectInfo = field(default_factory=ProjectInfo)
    materials: Materials = field(default_factory=Materials)
    boreholes: list[Borehole] = field(default_factory=list)
    elements: list[Element] = field(default_factory=list)
    options: FoundationOptions = field(default_factory=FoundationOptions)
    results: list[DesignResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def nearest_borehole(self, x: float, y: float) -> Borehole | None:
        if not self.boreholes:
            return None
        return min(self.boreholes, key=lambda b: (b.x - x) ** 2 + (b.y - y) ** 2)

    def project_bounds(self) -> tuple[float, float, float, float]:
        if not self.elements:
            return (0.0, 0.0, 0.0, 0.0)
        bounds = [e.footprint_bounds for e in self.elements]
        return (
            min(b[0] for b in bounds),
            max(b[2] for b in bounds),
            min(b[1] for b in bounds),
            max(b[3] for b in bounds),
        )

    def total_service_load(self) -> float:
        return sum(e.max_service().P for e in self.elements)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _clean(value: Any) -> Any:
    """Convert dataclass output to JSON-safe structures.

    Design details contain NumPy arrays (raft grids) and NumPy scalar types, so
    they are converted to plain lists/floats before saving.  Unknown objects are
    reduced to strings rather than breaking the whole project save.
    """
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_clean(v) for v in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if hasattr(value, "tolist"):
        return _clean(value.tolist())
    if hasattr(value, "item"):
        try:
            return _clean(value.item())
        except (ValueError, TypeError):
            pass
    return str(value)


def project_to_dict(project: Project) -> dict[str, Any]:
    return _clean(asdict(project))


def _build(cls, data: dict[str, Any]):
    """Build a dataclass from a dict, ignoring unknown keys."""
    field_names = {f.name for f in cls.__dataclass_fields__.values()}
    return cls(**{k: v for k, v in data.items() if k in field_names})


def _optional_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def project_from_dict(data: dict[str, Any]) -> Project:
    info = _build(ProjectInfo, data.get("info", {}))
    materials_data = dict(data.get("materials", {}))
    # Migrate old key if present
    if "concrete_unit_weight" in materials_data and "gamma_concrete" not in materials_data:
        materials_data["gamma_concrete"] = materials_data["concrete_unit_weight"]
    materials = _build(Materials, materials_data)
    options = _build(FoundationOptions, data.get("options", {}))

    boreholes = []
    for bd in data.get("boreholes", []):
        layers = [_build(SoilLayer, ld) for ld in bd.get("layers", [])]
        boreholes.append(
            Borehole(
                id=bd.get("id", "BH-1"),
                x=float(bd.get("x", 0.0)),
                y=float(bd.get("y", 0.0)),
                gwt=float(bd.get("gwt", 2.0)),
                layers=layers,
            )
        )

    elements = []
    for ed in data.get("elements", []):
        reactions = [_build(Reaction, rd) for rd in ed.get("reactions", [])]
        elements.append(
            Element(
                id=ed.get("id", "C1"),
                kind=ed.get("kind", "column"),
                x=float(ed.get("x", 0.0)),
                y=float(ed.get("y", 0.0)),
                base_elev=float(ed.get("base_elev", 0.0)),
                length=float(ed.get("length", 0.5)),
                width=float(ed.get("width", 0.5)),
                wall_thickness=float(ed.get("wall_thickness", 0.25)),
                preferred=ed.get("preferred", "Auto"),
                reactions=reactions or [Reaction()],
                notes=ed.get("notes", ""),
                dx=float(ed.get("dx", 0.0)),
                dy=float(ed.get("dy", 0.0)),
                shape=str(ed.get("shape", "Rectangular")),
                diameter=float(ed.get("diameter", 0.0)),
                x1=_optional_float(ed.get("x1")),
                y1=_optional_float(ed.get("y1")),
                x2=_optional_float(ed.get("x2")),
                y2=_optional_float(ed.get("y2")),
                rotation=float(ed.get("rotation", 0.0)),
            )
        )

    results = [_build(DesignResult, rd) for rd in data.get("results", [])]
    return Project(
        info=info,
        materials=materials,
        boreholes=boreholes,
        elements=elements,
        options=options,
        results=results,
        warnings=[str(w) for w in data.get("warnings", [])],
    )


def sample_project() -> Project:
    """A realistic synthetic project used for demos and smoke tests."""
    borehole = Borehole(
        id="BH-1",
        x=0.0,
        y=0.0,
        gwt=2.0,
        layers=[
            SoilLayer(
                bottom_depth=3.0, soil_type="Fill", description="Loose silty fill",
                gamma=17.0, gamma_sat=18.5, cohesion=0.0, friction_angle=26.0,
                n_raw=6, n60=5, es=4000.0,
            ),
            SoilLayer(
                bottom_depth=8.0, soil_type="CL", description="Soft to medium clay",
                gamma=17.5, gamma_sat=18.5, cohesion=5.0, friction_angle=0.0,
                cu=35.0, n_raw=7, n60=6, cc=0.28, e0=0.95, ocr=1.0,
                ll=42.0, pl=20.0, fines=70.0, es=6000.0,
            ),
            SoilLayer(
                bottom_depth=16.0, soil_type="SM", description="Medium dense silty sand",
                gamma=18.5, gamma_sat=19.5, cohesion=0.0, friction_angle=32.0,
                n_raw=18, n60=16, cc=0.05, e0=0.65, es=18000.0,
                qc=8.0, cpt_fs=70.0,
            ),
            SoilLayer(
                bottom_depth=25.0, soil_type="SP", description="Dense sand",
                gamma=19.5, gamma_sat=20.5, cohesion=0.0, friction_angle=36.0,
                n_raw=35, n60=32, cc=0.02, e0=0.50, es=35000.0,
                qc=16.0, cpt_fs=140.0,
            ),
            SoilLayer(
                bottom_depth=35.0, soil_type="CL", description="Very stiff clay",
                gamma=19.0, gamma_sat=20.0, cohesion=25.0, friction_angle=0.0,
                cu=120.0, n_raw=28, n60=26, cc=0.15, e0=0.70, ocr=2.0,
                ll=38.0, pl=18.0, fines=80.0, es=25000.0,
            ),
        ],
    )

    elements = [
        Element(
            "C1", "column", 0.0, 0.0, 0.0, 0.45, 0.45,
            reactions=[Reaction("Service", 900.0, 30.0, 25.0, 20.0, 15.0),
                       Reaction("Factored", 1260.0, 42.0, 35.0, 28.0, 21.0, factored=True)],
            notes="Rectangular column, 0.15 m centre offset in x",
            dx=0.15, dy=0.0, shape="Rectangular",
        ),
        Element(
            "C2", "column", 6.0, 0.0, 0.0, 0.60, 0.60,
            reactions=[Reaction("Service", 1800.0, 70.0, 45.0, 40.0, 25.0),
                       Reaction("Factored", 2520.0, 98.0, 63.0, 56.0, 35.0, factored=True)],
            notes="Circular column, 0.60 m diameter, 0.10 m centre offset in y",
            dx=0.0, dy=0.10, shape="Circular", diameter=0.60,
        ),
        Element(
            "C3", "column", 12.0, 0.0, 0.0, 0.45, 0.45,
            reactions=[Reaction("Service", 1150.0, 40.0, 30.0, 25.0, 18.0),
                       Reaction("Factored", 1610.0, 56.0, 42.0, 35.0, 25.2, factored=True)],
            notes="Rectangular column, 0.10 m offset in -x, rotated 30 degrees",
            dx=-0.10, dy=0.05, shape="Rectangular", rotation=30.0,
        ),
        Element(
            "C4", "column", 0.0, 7.0, 0.0, 0.50, 0.50,
            reactions=[Reaction("Service", 2400.0, 90.0, 60.0, 55.0, 35.0),
                       Reaction("Factored", 3360.0, 126.0, 84.0, 77.0, 49.0, factored=True)],
            notes="Rectangular column, 0.10 m offset in x and -y",
            dx=0.10, dy=-0.10, shape="Rectangular",
        ),
        Element(
            "C5", "column", 6.0, 7.0, 0.0, 0.55, 0.55,
            reactions=[Reaction("Service", 1350.0, 45.0, 35.0, 30.0, 20.0),
                       Reaction("Factored", 1890.0, 63.0, 49.0, 42.0, 28.0, factored=True)],
            notes="Circular column, 0.55 m diameter",
            dx=-0.05, dy=0.0, shape="Circular", diameter=0.55,
        ),
        Element(
            "C6", "column", 12.0, 7.0, 0.0, 0.50, 0.50,
            reactions=[Reaction("Service", 2100.0, 80.0, 55.0, 50.0, 30.0),
                       Reaction("Factored", 2940.0, 112.0, 77.0, 70.0, 42.0, factored=True)],
            notes="Rectangular column, 0.10 m centre offset in y",
            dx=0.0, dy=0.10, shape="Rectangular",
        ),
        Element(
            "W1", "wall", 6.0, 3.5, 0.0, 6.08, 0.25,
            wall_thickness=0.25,
            reactions=[Reaction("Service", 3200.0, 180.0, 900.0, 220.0, 60.0, includes_lateral=True),
                       Reaction("Factored", 4480.0, 252.0, 1260.0, 308.0, 84.0, factored=True, includes_lateral=True)],
            notes="Angled shear wall from (3.0, 2.8) to (9.0, 4.2)",
            x1=3.0, y1=2.8, x2=9.0, y2=4.2,
        ),
    ]

    return Project(
        info=ProjectInfo(name="Sample Residential Building", location="Dhaka, Bangladesh",
                         engineer="Design Engineer", notes="Synthetic demonstration project"),
        materials=Materials(),
        boreholes=[borehole],
        elements=elements,
        options=FoundationOptions(
            site_xmin=-3.0, site_xmax=15.0, site_ymin=-3.0, site_ymax=10.0,
            pga_g=0.20,
            cost_concrete=12000.0, cost_excavation=500.0, cost_pile=3500.0,
            cost_steel=95.0,
        ),
    )
