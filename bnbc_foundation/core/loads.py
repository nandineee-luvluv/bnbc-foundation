"""Load combinations per BNBC 2020 Part 6, Chapter 2 and Chapter 3.

Service combinations (geotechnical):
    3.9.2(a): D+L; D+L+W/E; 0.9D + buoyancy
    3.9.2(b): sand D+L / D+L+W/E; clay D+0.5L
Strength combinations (structural, 2.7.3.1):
    1.4(D+F)
    1.2(D+F+T) + 1.6(L+H) + 0.5(Lr or R)
    1.2D + 1.6(Lr or R) + (L or 0.8W)
    1.2D + 1.6W + L + 0.5(Lr or R)
    1.2D + 1.0E + L
    0.9D + 1.6W + 1.6H
    0.9D + 1.0E + 1.6H
"""

from __future__ import annotations

from dataclasses import replace

from .models import Element, Reaction


def normalise_case(name: str) -> str:
    n = name.strip().upper().replace(" ", "").replace("_", "").replace("-", "")
    if n in {"DL", "D", "DEAD"}:
        return "D"
    if n in {"LL", "L", "LIVE"}:
        return "L"
    if n in {"WL", "W", "WIND"}:
        return "W"
    if n in {"EQ", "E", "EARTHQUAKE", "SEISMIC"}:
        return "E"
    if n in {"LR", "ROOF", "ROOFLIVE"}:
        return "Lr"
    if n in {"BUOY", "BUOYANCY", "UPLIFT"}:
        return "B"
    return name.strip()


def _components(element: Element) -> dict[str, Reaction]:
    """Aggregate reactions by case. Missing cases are zero."""
    out: dict[str, Reaction] = {}
    for r in element.reactions_at_center():
        case = normalise_case(r.case) if not r.factored else r.case.upper()
        if case not in out:
            out[case] = Reaction(case=case)
        agg = out[case]
        agg.P += r.P
        agg.Mx += r.Mx
        agg.My += r.My
        agg.Vx += r.Vx
        agg.Vy += r.Vy
        agg.buoyancy += r.buoyancy
        agg.includes_lateral = agg.includes_lateral or r.includes_lateral
    return out


def _combine(parts: dict[str, tuple[float, Reaction]], case_name: str,
             factored: bool, includes_lateral: bool = False) -> Reaction:
    out = Reaction(case=case_name, factored=factored, includes_lateral=includes_lateral)
    for factor, r in parts.values():
        out.P += factor * r.P
        out.Mx += factor * r.Mx
        out.My += factor * r.My
        out.Vx += factor * r.Vx
        out.Vy += factor * r.Vy
        out.buoyancy += factor * r.buoyancy
    return out


def service_combinations(element: Element) -> list[Reaction]:
    """Return the service-load candidates for an element.

    If the user supplied already-combined service reactions (case names such as
    "Service" or "Combined"), those are returned directly. If separate D/L/W/E
    cases exist, the BNBC 3.9.2 combinations are generated.
    """
    service = [r for r in element.reactions if not r.factored]
    if not service:
        return []

    comps = _components(element)
    known = {"D", "L", "Lr", "W", "E", "B"}
    if not (set(comps) & known):
        return service

    d = comps.get("D", Reaction("D"))
    l = comps.get("L", Reaction("L"))
    lr = comps.get("Lr", Reaction("Lr"))
    w = comps.get("W", Reaction("W"))
    e = comps.get("E", Reaction("E"))
    b = comps.get("B", Reaction("B"))

    out = [
        _combine({"D": (1.0, d), "L": (1.0, l), "Lr": (1.0, lr)}, "D + L"),
        _combine({"D": (1.0, d), "L": (1.0, l), "W": (1.0, w)}, "D + L + W", includes_lateral=True),
        _combine({"D": (1.0, d), "L": (1.0, l), "E": (1.0, e)}, "D + L + E", includes_lateral=True),
    ]
    if b.P or b.Mx or b.My or b.buoyancy:
        out.append(_combine({"D": (0.9, d), "B": (1.0, b)}, "0.9D + buoyancy"))
    # Clay settlement combination is handled separately by the settlement engine.
    return out


def factored_combinations(element: Element) -> list[Reaction]:
    """Return the strength-design candidates per BNBC 2.7.3.1."""
    factored = [r for r in element.reactions if r.factored]
    if factored:
        return factored

    comps = _components(element)
    known = {"D", "L", "Lr", "W", "E", "B"}
    if not (set(comps) & known):
        s = element.max_service()
        return [replace(s, case="1.4 x service", P=1.4 * s.P, Mx=1.4 * s.Mx,
                        My=1.4 * s.My, Vx=1.4 * s.Vx, Vy=1.4 * s.Vy,
                        factored=True, includes_lateral=s.includes_lateral)]

    d = comps.get("D", Reaction("D"))
    l = comps.get("L", Reaction("L"))
    lr = comps.get("Lr", Reaction("Lr"))
    w = comps.get("W", Reaction("W"))
    e = comps.get("E", Reaction("E"))

    out = [
        _combine({"D": (1.4, d)}, "1.4D", factored=True),
        _combine({"D": (1.2, d), "L": (1.6, l), "Lr": (0.5, lr)}, "1.2D+1.6L+0.5Lr", factored=True),
        _combine({"D": (1.2, d), "Lr": (1.6, lr), "L": (1.0, l)}, "1.2D+1.6Lr+L", factored=True),
        _combine({"D": (1.2, d), "W": (1.6, w), "L": (1.0, l), "Lr": (0.5, lr)},
                 "1.2D+1.6W+L+0.5Lr", factored=True, includes_lateral=True),
        _combine({"D": (1.2, d), "E": (1.0, e), "L": (1.0, l)},
                 "1.2D+1.0E+L", factored=True, includes_lateral=True),
        _combine({"D": (0.9, d), "W": (1.6, w)}, "0.9D+1.6W", factored=True, includes_lateral=True),
        _combine({"D": (0.9, d), "E": (1.0, e)}, "0.9D+1.0E", factored=True, includes_lateral=True),
    ]
    return out


def governing_service(element: Element) -> Reaction:
    candidates = service_combinations(element) or [Reaction()]
    return max(candidates, key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My))


def governing_factored(element: Element) -> Reaction:
    candidates = factored_combinations(element) or [Reaction()]
    return max(candidates, key=lambda r: abs(r.P) + abs(r.Mx) + abs(r.My))


def envelope(elements: list[Element]) -> tuple[float, float, float]:
    """Project-level service P, Mx, My envelope (absolute sums are conservative)."""
    p = sum(e.max_service().P for e in elements)
    mx = sum(abs(e.max_service().Mx) for e in elements)
    my = sum(abs(e.max_service().My) for e in elements)
    return p, mx, my


def group_by_case(element: Element) -> dict[str, Reaction]:
    return _components(element)
