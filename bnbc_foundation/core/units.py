"""Unit systems and conversion helpers.

The calculation engine works in SI units at all times.  The user interface,
importers, exporters and reports convert at their boundary with the helpers in
this module, so every input or result can be entered or read in either SI or
US customary units.

Quantities are identified by a short key; ``convert`` maps a value from SI to
the selected display system and ``to_si`` maps it back.  Conversion factors are
exact or NIST-consistent to the precision used by engineering calculations.
"""

from __future__ import annotations

import math
import re
from typing import Any

G = 9.81  # m/s2

SI = "SI"
US = "US"

# factor: SI -> US; label: (SI label, US label)
_UNITS: dict[str, tuple[float, tuple[str, str]]] = {
    "length": (3.280839895013123, ("m", "ft")),
    "length_mm": (1.0 / 25.4, ("mm", "in")),
    "force": (0.2248089430997105, ("kN", "kip")),
    "moment": (0.7375621492772654, ("kN.m", "kip.ft")),
    "moment_per_length": (0.2248089430997105, ("kN.m/m", "kip.ft/ft")),
    "pressure": (1.0 / 47.88025898033584, ("kPa", "ksf")),
    "stress": (1.0 / 6.894757293168361, ("MPa", "ksi")),
    "unit_weight": (6.365880385, ("kN/m3", "pcf")),
    "subgrade": (0.006365880385, ("kN/m3", "kcf")),
    "area": (10.76391041670972, ("m2", "ft2")),
    "volume": (35.31466672148859, ("m3", "ft3")),
    "mass": (2.204622621848776, ("kg", "lb")),
    "settlement": (1.0 / 25.4, ("mm", "in")),
    "angle": (1.0, ("deg", "deg")),
    "ratio": (1.0, ("", "")),
    "currency": (1.0, ("", "")),
    "cost_per_volume": (1.0 / 35.31466672148859, ("per m3", "per ft3")),
    "cost_per_length": (0.3048, ("per m", "per ft")),
    "cost_per_mass": (0.45359237, ("per kg", "per lb")),
    "cost_per_area": (0.09290304, ("per m2", "per ft2")),
}

SYSTEMS = (SI, US)


def normalize_system(value: Any) -> str:
    """Return ``SI`` or ``US`` for free-text unit settings."""
    text = str(value or "").strip().upper()
    if text in ("US", "USC", "IMPERIAL", "FPS", "FT", "ENGLISH"):
        return US
    if text.startswith(("US", "IMPERIAL", "FPS", "ENGLISH")):
        return US
    return SI


def system_of(project: Any) -> str:
    info = getattr(project, "info", None)
    return normalize_system(getattr(info, "units", SI))


def factor(quantity: str, system: str = SI) -> float:
    """SI-to-display factor for a quantity."""
    if normalize_system(system) == SI:
        return 1.0
    return _UNITS.get(quantity, (1.0, ("", "")))[0]


def convert(value: float, quantity: str, system: str = SI) -> float:
    """Convert a value from internal SI units to the display system."""
    return float(value) * factor(quantity, system)


def to_si(value: float, quantity: str, system: str = SI) -> float:
    """Convert a display value back to internal SI units."""
    f = factor(quantity, system)
    return float(value) / f if abs(f) > 1e-15 else float(value)


def label(quantity: str, system: str = SI) -> str:
    """Unit suffix for a quantity in the selected system."""
    labels = _UNITS.get(quantity, (1.0, ("", "")))[1]
    return labels[1] if normalize_system(system) == US else labels[0]


def unit_system_name(system: str = SI) -> str:
    return "US customary" if normalize_system(system) == US else "SI"


# SI unit tokens that can appear in generated narrative text.  Longer tokens
# must come first so "kN.m" is not consumed as "kN" and "mm" is not consumed
# as "m".
_TEXT_PATTERNS = (
    (re.compile(r"(-?\d+(?:\.\d+)?)\s*kN\.m\b"), "moment"),
    (re.compile(r"(-?\d+(?:\.\d+)?)\s*kN/m3\b"), "unit_weight"),
    (re.compile(r"(-?\d+(?:\.\d+)?)\s*kPa\b"), "pressure"),
    (re.compile(r"(-?\d+(?:\.\d+)?)\s*kN\b"), "force"),
    (re.compile(r"(-?\d+(?:\.\d+)?)\s*mm\b"), "length_mm"),
    (re.compile(r"(-?\d+(?:\.\d+)?)\s*m3\b"), "volume"),
    (re.compile(r"(-?\d+(?:\.\d+)?)\s*kg\b"), "mass"),
    (re.compile(r"(-?\d+(?:\.\d+)?)\s*m\b"), "length"),
)


def _narrative_number(value: float) -> str:
    text = f"{value:.1f}"
    if abs(value) >= 10 and text.endswith(".0"):
        return text[:-2]
    return text


_TRIPLE_MM = re.compile(
    r"(-?\d+(?:\.\d+)?)(\s*x\s*)(-?\d+(?:\.\d+)?)(\s*x\s*)"
    r"(-?\d+(?:\.\d+)?)\s*mm\b"
)
_PAIR_M = re.compile(
    r"(-?\d+(?:\.\d+)?)(\s*x\s*)(-?\d+(?:\.\d+)?)\s*m\b"
)


def convert_text(text: str, system: str = SI) -> str:
    """Convert SI values embedded in generated narrative text.

    Size, requirement and remark strings contain values such as ``1.95 m`` or
    ``450 mm``.  The calculation engine builds them in SI; this helper rewrites
    them for display without touching the underlying numeric results.
    """
    if not text or normalize_system(system) == SI:
        return text
    out = str(text)
    # Compound strings such as "7.40 x 1.40 x 1200 mm" mix metres and
    # millimetres; convert each component and label it so the result is
    # unambiguous ("24.3 ft x 4.6 ft x 47.2 in").
    out = _TRIPLE_MM.sub(
        lambda m: (
            f"{_narrative_number(convert(float(m.group(1)), 'length', system))} "
            f"{label('length', system)}{m.group(2)}"
            f"{_narrative_number(convert(float(m.group(3)), 'length', system))} "
            f"{label('length', system)}{m.group(4)}"
            f"{_narrative_number(convert(float(m.group(5)), 'length_mm', system))} "
            f"{label('length_mm', system)}"
        ),
        out,
    )
    out = _PAIR_M.sub(
        lambda m: (
            f"{_narrative_number(convert(float(m.group(1)), 'length', system))} "
            f"{label('length', system)}{m.group(2)}"
            f"{_narrative_number(convert(float(m.group(3)), 'length', system))} "
            f"{label('length', system)}"
        ),
        out,
    )
    for pattern, quantity in _TEXT_PATTERNS:
        target = label(quantity, system)
        out = pattern.sub(
            lambda m: f"{_narrative_number(convert(float(m.group(1)), quantity, system))} {target}",
            out,
        )
    return out


# ---------------------------------------------------------------------------
# Small numerical utilities
# ---------------------------------------------------------------------------


def ceil_to(value: float, step: float) -> float:
    if step <= 0:
        return value
    return math.ceil(value / step - 1e-9) * step


def safe_div(a: float, b: float, default: float = 0.0) -> float:
    return a / b if abs(b) > 1e-12 else default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def interp(x: float, xs: list[float], ys: list[float]) -> float:
    if not xs:
        return 0.0
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            t = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + t * (ys[i] - ys[i - 1])
    return ys[-1]
