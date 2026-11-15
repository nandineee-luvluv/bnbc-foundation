# Architecture

[Back to map](MAP.md) · Related: [context.md](context.md) · [units.md](units.md) · [verification.md](verification.md)

## Package layout

```text
run.py                       entry point: normal, --project, --smoke
requirements.txt             PySide6, numpy, pandas, openpyxl, matplotlib, reportlab, pytest
bnbc_foundation/
  core/
    models.py                data classes, JSON serialization, synthetic sample
    geometry.py              rotated polygons, footprint overlap, clearance, site checks
    units.py                 SI/US conversion registry, narrative conversion, rounding
    loads.py                 service/factored BNBC combinations
    soil.py                  stress, SPT corrections, bearing capacity, liquefaction
    bearing.py               pressure, sizing, stability, shallow uplift
    settlement.py            immediate, consolidation, secondary, differential settlement
    piles.py                 SPT/static/CPT/direct pile capacity, downdrag, uplift,
                             Broms lateral capacity, group layout and cap sizing
    structural/
      concrete.py            flexure, shear, punching, development, bars, crack width, P-M
      footing.py             isolated, combined and strip footing design
      pilecap.py             pile-cap flexure, one-way shear, punching, strut-and-tie
      raft_design.py         raft thickness iteration, top/bottom steel, shear/punching
    rebar.py                 project-wide bar schedule and bar bending schedule
    raft.py                  rigid, Winkler strip and 16-DOF Kirchhoff plate analysis
    selector.py              foundation selection, clash checks, cost ranking, run_design
    report.py                Excel/PDF/CSV/JSON exports, imports, warnings
  ui/
    main_window.py           navigation, worker thread, project/export actions
    common.py                stylesheet, tables, cards, input helpers
    pages/                   project, materials, soil, loads, options, results, export
tests/                       pytest suite (91 tests, offscreen Qt smoke test)
samples/                     generated Excel, PDF, CSV, JSON and import template
.opencode/                   detailed build/audit/plan history
.xcontext/                   this durable context knowledge base
```

## Data flow

```text
GUI pages / Excel-CSV import
        |
        v
Project models (always SI)
  info, materials, boreholes, elements, reactions, options
        |
        v
selector.run_design(project)
  loads -> geometry/clash/site -> candidate types -> analyses -> checks
        |
        v
DesignResult list (SI values + details/checks/remarks/alternatives)
        |
        +--> ResultsPage cards, schedule, detail, site plan
        +--> core/report.py Excel / PDF / CSV / JSON / template
```

## Key models

- `Project` — `info`, `materials`, `boreholes`, `elements`, `options`, `results`, `warnings`.
- `ProjectInfo` — name, location, engineer, date, design code, `units`.
- `Materials` — `f_c`, `f_y`, concrete unit weight, cover, bar diameters, resistance factors.
- `Borehole` / `SoilLayer` — depth, classification, strength/stiffness, SPT, CPT, lab data, direct pile capacities.
- `Element` / `Reaction` — column or wall geometry, insertion point/offset, rotation, service/factored or named load cases.
- `FoundationOptions` — allowed types, dimensions, factors of safety, pile options, raft options, site bounds, cost rates.
- `DesignResult` — selected type, size, quantities, status, utilization, checks, remarks, alternatives.

## Calculation pipeline

1. **Loads** — choose governing service/factored reaction; combine DL/LL/WL/EQ when provided.
2. **Geometry** — transform reactions to column centre; rotate/project sections; build footprint polygons.
3. **Candidates** — isolated, combined, strip, single pile, pile group, raft as allowed.
4. **Geotechnical checks** — bearing pressure/kern, settlement, sliding, overturning, uplift, pile capacity/group, downdrag, lateral, P-M.
5. **Structural checks** — flexure, one-way shear, punching, development, crack width, pile-cap strut-and-tie.
6. **Selection** — discard infeasible/clashing/outside-site options; rank by preference or cost; keep alternatives.
7. **Reporting** — build schedule rows, detailed calculation text, warnings and export tables.

## Important conventions

- Engine and JSON numeric values are SI: kN, kPa, kN.m, m, mm.
- Column `(x,y)` is the insertion/reaction point; centre is `(x+dx, y+dy)`.
- Reaction moments are moved to the centre with `Mx_c = Mx - P*dy` and `My_c = My - P*dx`.
- Wall local axes: `M_u = Mx*cos(theta) + My*sin(theta)` and `M_v = My*cos(theta) - Mx*sin(theta)`.
- Rectangular sections rotate counter-clockwise; walls and caps follow the wall axis.
- Site/clash checks use actual polygons with 0.10 m clearance.
- CPT: `qc` in MPa, `fs` in kPa. Direct pile capacities bypass correlations when present.
- JSON stores SI numbers; `info.units` only records the display system.

## Extension points

- **New foundation type:** model/options, selector candidate, design module, report rows, UI option.
- **New unit quantity:** `core/units.py` registry, GUI `set_spin/get_spin`, import/export/report boundary, tests.
- **New export:** `core/report.py` plus export page and tests.
- **New check:** `DesignResult.details["checks"]`, status/remarks, Excel/PDF rows, regression test.

## Related records

- [context.md](context.md) — objective and decisions.
- [units.md](units.md) — SI/US boundary rules.
- [verification.md](verification.md) — how the architecture is tested.
- [`.opencode/context.md`](../.opencode/context.md) — original architecture notes.
