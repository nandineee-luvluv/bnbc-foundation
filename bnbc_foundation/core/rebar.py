"""Reinforcement schedule and bar bending schedule (BBS) generation."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any

from .structural.concrete import bar_weight_per_metre


@dataclass
class RebarItem:
    mark: str = ""
    member: str = ""
    element_id: str = ""
    description: str = ""
    diameter: float = 0.0          # mm
    shape: str = "Straight"
    count: int = 0
    cut_length: float = 0.0        # m
    total_length: float = 0.0      # m
    weight: float = 0.0            # kg
    spacing: float = 0.0           # mm
    notes: str = ""

    def schedule_row(self) -> list[Any]:
        return [
            self.mark, self.member, self.element_id, self.description,
            f"{self.diameter:.0f}", self.shape, self.count,
            round(self.cut_length, 3), round(self.total_length, 2),
            round(self.weight, 2), self.notes,
        ]

    def bbs_row(self) -> list[Any]:
        return [
            self.mark, self.element_id, self.description,
            f"{self.diameter:.0f}", self.shape, self.count,
            round(self.cut_length * 1000.0, 0),
            round(self.total_length, 2), round(self.weight, 2), self.notes,
        ]


def layout_dict(layout) -> dict:
    """Convert a BarLayout dataclass (or dict) into a plain dictionary."""
    if layout is None:
        return {}
    if isinstance(layout, dict):
        return dict(layout)
    return asdict(layout)


def _geometry(result) -> tuple[float, float, float, float]:
    """Return (length, width, thickness, cover) in m/mm for a result."""
    ftype = (result.foundation_type or "").lower()
    if "pile" in ftype and result.cap_length:
        return result.cap_length, result.cap_width, result.cap_thickness / 1000.0, 50.0
    if "raft" in ftype:
        return result.length, result.width, result.thickness / 1000.0, 75.0
    return result.length, result.width, result.thickness / 1000.0, 75.0


def build_rebar_schedule(results: list, start_mark: int = 1) -> list[RebarItem]:
    """Build a project-wide reinforcement schedule from design results.

    ``results`` may contain ``details["rebar_layouts"]`` with keys
    ``bottom_x``, ``bottom_y``, ``top_x`` and ``top_y``.
    """
    items: list[RebarItem] = []
    mark = start_mark
    for result in results:
        details = result.details if isinstance(result.details, dict) else {}
        layouts = details.get("rebar_layouts", {})
        if not layouts:
            continue
        length, width, thickness, cover = _geometry(result)
        if length <= 0 or width <= 0:
            continue
        ftype = (result.foundation_type or "").lower()
        raft = "raft" in ftype
        for key, layout in layouts.items():
            if not layout:
                continue
            db = float(layout.get("diameter", 0) or 0)
            spacing = float(layout.get("spacing", 0) or 0)
            if db <= 0 or spacing <= 0:
                continue
            if key.endswith("_x"):
                span = length
                across = width
                direction = "X"
            else:
                span = width
                across = length
                direction = "Y"
            count = max(2, int(math.ceil((across * 1000.0 - 2.0 * cover) / spacing)) + 1)
            if raft:
                cut_length = max(span - 2.0 * cover / 1000.0, 0.3)
                shape = "Straight"
                notes = "Straight raft bar"
            else:
                hook = 10.0 * db / 1000.0 if "top" in key else 8.0 * db / 1000.0
                cut_length = max(span - 2.0 * cover / 1000.0 + 2.0 * hook, 0.3)
                shape = "90 deg end hooks"
                notes = f"{2} x {10 if 'top' in key else 8}db hooks"
            item = RebarItem(
                mark=f"B{mark}",
                member=result.element_id,
                element_id=result.element_id,
                description=f"{result.foundation_type} {key.replace('_', ' ').title()} {direction}-bars",
                diameter=db,
                shape=shape,
                count=count,
                cut_length=cut_length,
                total_length=count * cut_length,
                weight=count * cut_length * bar_weight_per_metre(db),
                spacing=spacing,
                notes=notes,
            )
            items.append(item)
            mark += 1
    return items


def rebar_summary(items: list[RebarItem]) -> list[dict]:
    """Aggregate the schedule by bar diameter."""
    summary: dict[float, dict] = {}
    for item in items:
        row = summary.setdefault(item.diameter, {"diameter": item.diameter, "count": 0,
                                                 "length": 0.0, "weight": 0.0})
        row["count"] += item.count
        row["length"] += item.total_length
        row["weight"] += item.weight
    return [summary[d] for d in sorted(summary)]


def bbs_totals(items: list[RebarItem]) -> dict:
    return {
        "items": len(items),
        "bars": sum(i.count for i in items),
        "length_m": sum(i.total_length for i in items),
        "weight_kg": sum(i.weight for i in items),
    }
