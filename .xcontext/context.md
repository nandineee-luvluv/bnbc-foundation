# Project Context

[Back to map](MAP.md) · Related: [architecture.md](architecture.md) · [decisions.json](decisions.json) · [handoff.md](handoff.md)

## Identity

- **Name:** BNBC 2020 Foundation Designer
- **Package:** `bnbc_foundation`
- **Entry point:** `run.py` (`--project` opens a JSON project, `--smoke` starts and exits)
- **GUI:** PySide6 desktop application
- **Design code:** BNBC 2020, Part 6, Chapters 2, 3, 6 and 8
- **Repository:** https://github.com/nandineee-luvluv/bnbc-foundation
- **Owner:** Nandini Shahnewaz
- **License:** MIT

## Objective

Build a desktop application that accepts soil-report data and base reactions for
any number of columns and shear walls, evaluates isolated, combined, strip, raft,
single-pile and pile-group foundations, performs detailed geotechnical and
structural design to BNBC 2020, and exports a foundation schedule, calculation
report, quantities, rebar schedule/BBS and a reloadable project file.

## User workflow

1. **Project** — project details, unit system, notes.
2. **Materials** — concrete/reinforcement strengths and resistance factors.
3. **Soil** — any number of boreholes, layers, SPT, CPT, laboratory data, groundwater.
4. **Loads** — columns/walls, geometry, service/factored reactions or DL/LL/WL/EQ cases.
5. **Options** — foundation types, geometry/safety limits, piles, site constraints, cost rates.
6. **Run design** — background worker evaluates all elements.
7. **Results** — summary cards, schedule, per-element calculations, site plan, alternatives, warnings.
8. **Export** — Excel, PDF, CSV, JSON project and Excel import template.

## Confirmed decisions

| Area | Decision |
|---|---|
| Units | SI is used internally and for all stored numeric values. SI/US customary conversion happens only at GUI, import, export and report boundaries. JSON records the display system in `info.units` but stores SI numbers. |
| Geometry | Column `(x,y)` is the reaction/insertion point; the plan centre is `(x+dx, y+dy)`. Rectangular sections may rotate counter-clockwise. Wall moments are transformed into wall-local axes. Selection, clash, site and plan checks use actual footprint polygons. |
| Foundation selection | Feasible types are compared per element, including site containment and adjacent-footing clashes. Preference or estimated cost ranks options; alternatives are retained for review. |
| Raft analysis | Rigid contact pressure is always reported. Large/custom rafts use a 16-DOF Kirchhoff plate on Winkler springs; otherwise Winkler strips are used. A custom outline must be convex and is handled with exact polygon pressure and masked plate elements. |
| Pile capacity | SPT, static, CPT and direct-report methods. CPT uses `qc` in MPa and `fs` in kPa. Downdrag, uplift, Broms lateral capacity and P-M interaction are included. |
| Loads | Pre-combined service/factored envelopes, separate DL/LL/WL/EQ cases combined to BNBC 2020, or ETABS/SAFE CSV import. Numeric lateral tokens such as `1.2D+1.6W` are recognised. |
| Outputs | Excel workbook (ten sheets), printable PDF, CSV schedule, JSON project and Excel import template. The workbook includes schedule, geotech, structural, supplemental, rebar, BBS, quantities, soil and code-basis sheets. |
| Audit | All 17 Ponytail findings are fixed. Each functional fix has regression coverage in `tests/test_regressions.py`. |
| Ownership | MIT license; copyright remains with Nandini Shahnewaz. Others may use, modify, distribute and sell the software but must retain the copyright and permission notice. |
| Backup | A local zip honours `.zipignore`, excludes virtualenvs/caches/tooling and includes the source, tests, samples, docs and `.git` history. Archives are ignored by git. |

## Current state

- Functionally complete and smoke-tested.
- **91 tests pass** with `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`.
- `.venv/bin/python run.py --smoke` exits `0`.
- All 17 audit fixes are closed; `compileall` passes and an AST scan finds no unused imports.
- The synthetic sample produces 8 results: W1 pile group plus C1–C6 isolated
  footings selected, all `CHECK` on the deliberately soft clay; RAFT-1 remains an
  alternative. It reports 5 project warnings and 12 report warning/review lines.
- Public GitHub repository is live under the MIT license.
- Local zip backup exists inside the project folder and is excluded from git and
  from future backups.

## Limits and assumptions

- This is a design aid. A qualified foundation engineer must review and approve
  all output before construction.
- Soil-report PDF OCR is not automatic; data is entered through the GUI or the
  Excel template.
- Full 3D soil–structure FEM is not included. ETABS/SAFE reactions can be
  imported, but their analysis results are not embedded.
- Liquefaction is a simplified SPT trigger. Downdrag, pile uplift, Broms lateral
  capacity and P-M interaction are simplified code-level checks.
- Crack width uses the EC2/BNBC simplified formula; where only factored raft
  moments exist they are divided by 1.4 as an approximation.
- Real soil-report and ETABS/SAFE reaction files are still unavailable. The
  synthetic sample is the current validation case.
- A Windows executable must be built on Windows with PyInstaller.

## Detailed history

The full build and audit history is in
[`.opencode/progression.md`](../.opencode/progression.md). The fix plan is
[`.opencode/ponyfix.md`](../.opencode/ponyfix.md). The current machine-readable
status is [state.json](state.json).
