# Project Context

## Objective

Build a Python desktop application that exports foundation type, requirement, size and
number for isolated, combined, raft, single-pile and pile-with-cap foundations, based
on BNBC 2020 and soil-report data plus base reactions for any number of columns and
shear walls.

## Confirmed decisions

| Item | Decision |
|---|---|
| GUI | PySide6 desktop application |
| Design depth | Full detailed geotechnical + structural design |
| Soil input | SPT/layer data **and** direct report values |
| "Just pile" | One pile under a column, with a simple cap/connection |
| Shear walls | Auto-select strip footing, pile cap along wall or raft |
| Raft analysis | Auto: plate solver for custom/large rafts, Winkler strips otherwise; rigid contact pressure always reported |
| Raft outline | Optional imported convex polygon with exact polygon pressure and masked plate elements |
| Reactions | Pre-combined envelopes **or** DL/LL/W/EQ load cases; ETABS/SAFE CSV import |
| Column geometry | Insertion point `(x,y)`, centre offset `(dx,dy)`, rectangular `L x W` (arbitrary CCW rotation) or circular diameter `d` |
| Wall geometry | Centreline endpoints `(x1,y1)-(x2,y2)` plus thickness `t`; legacy centre/length fallback |
| Plan checks | Actual footprint polygons, rotated columns and wall caps, 0.10 m clearance between foundations |
| Pile capacity | SPT, static, direct report or CPT (qc/fs) methods |
| Supplementary checks | Crack width, shallow-footing uplift, pile downdrag, pile uplift, Broms lateral capacity and P-M interaction |
| Rebar output | Full schedule + bar bending schedule |
| Sample data | Synthetic sample first; refine with user files |
| Units | SI or US customary at the entry/export boundary; all internal calculations and JSON storage in SI (kN, kPa, kN.m, m, mm) |
| Code | BNBC 2020, Part 6, Chapters 2, 3, 6 and 8 |

## Environment

- Workspace: the project root (repository root)
- Python: 3.14.10 inside `.venv` (created with `uv`)
- Dependencies installed: PySide6, numpy, pandas, openpyxl, matplotlib, reportlab,
  pytest
- System Python lacks tkinter; PySide6 is the intended GUI toolkit.

## Key BNBC 2020 provisions used

### Shallow foundations

- Bearing pressure with biaxial eccentricity; resultant preferably within `B/6`
  (Clause 3.9.1).
- Service combinations: `D+L`, `D+L+W/E`, `0.9D+buoyancy` (Clause 3.9.2).
- FS 2.0–3.0 on ultimate bearing; 33% overstress for wind/seismic (Clause 3.9.3).
- Minimum depth: 1.5 m cohesive, 2.0 m cohesionless for exterior footings; at least
  500 mm below ground generally (Clauses 3.8.2 and 3.8.6).
- Minimum RC thickness: 150 mm on soil, 300 mm on piles (Clauses 3.8.3 and 6.8.7).
- Settlement limits: 25 mm sand / 40 mm clay for isolated footings; 20 mm
  differential; Table 6.3.8 angular distortion (Clause 3.9.4.7).
- Sliding and overturning FS 1.5 for shallow footings, including combined and
  strip/wall footings.
- Simplified SPT liquefaction screening with a user-supplied PGA; FS below 1.0
  triggers a review warning.
- Raft: uniform loading, contact pressure, eccentricity, buoyancy (Clauses 3.8.10
  and 3.9.6.3).

### Deep foundations

- Driven pile SPT:
  - Clay: `fs = 1.8 N60 <= 70 kPa`, `qb = 45 N60 <= 4000 kPa`.
  - Sand: `fs = 2 N60 <= 60 kPa`,
    `qb = 40 N60 (D/B) <= 400 N60 and <= 11000 kPa`.
- Bored pile SPT:
  - Clay: `fs = 1.2 N60 <= 70 kPa`, `qb = 25 N60 <= 4000 kPa`.
  - Sand: `fs = 1.0 N60 <= 60 kPa`,
    `qb = 15 N60 (D/B) <= 150 N60 and <= 4000 kPa`.
- Preliminary SPT design FS = 3.5; final FS 2.0–3.0 depending on construction
  control/load test (Clauses 3.10.1.13, 3.10.1.16, 3.10.4.5, 3.10.4.7,
  Table 6.3.10a).
- Pile spacing: >= 750 mm or 2.5D end-bearing, 3.0D friction (Clause 3.10.1.30).
- Pile cap: pile embedment >= 75 mm, cap extends >= 100 mm beyond pile edge, cover
  >= 50 mm (Clause 3.10.1.20).
- Bored pile minimum diameter 400 mm, in 50 mm increments; single pile not
  recommended below 600 mm (Clauses 3.10.4.2 and 3.10.4.11).
- Group efficiency 1.0 except friction piles in clay; pile settlement checked
  against shallow-foundation limits (Clauses 3.10.1.19 and 3.10.5).

### Structural design

- Strength combinations per Clause 2.7.3.1:
  `1.4(D+F)`;
  `1.2(D+F+T)+1.6(L+H)+0.5(Lr or R)`;
  `1.2D+1.6(Lr or R)+(L or 0.8W)`;
  `1.2D+1.6W+L+0.5(Lr or R)`;
  `1.2D+1.0E+L`;
  `0.9D+1.6W+1.6H`;
  `0.9D+1.0E+1.6H`.
- Strength reduction factors: 0.90 flexure, 0.75 shear, 0.65 bearing (Clause
  6.2.3.2).
- Footings: flexure, one-way shear, punching shear, development length, minimum
  reinforcement (Chapter 6, especially 6.8; Chapter 8).
- Pile caps: flexure, one-way shear, punching, strut-and-tie where applicable
  (Clauses 6.8.5.3/6.8.5.4 and Appendix I).
- Piles: structural axial capacity and minimum reinforcement (Clause 3.10.4.9 and
  Chapter 6); simplified P-M interaction with `phi_Pn = 0.65` and
  `phi_Mn = 0.90`; downdrag/negative skin friction; uplift capacity; Broms
  short-pile lateral capacity (Clauses 3.10.5 and 6.8).
- Crack width: EC2/BNBC 6.8.9 simplified spacing/strain formula, default limit
  0.30 mm, applied to service moments for isolated, combined, strip, raft and
  pile-cap designs.
- Shallow-footing uplift: hydrostatic buoyancy plus explicit uplift versus
  permanent load and footing/soil weight, default FS 1.10; passive resistance is
  ignored.

## Architecture

```text
run.py
requirements.txt
bnbc_foundation/
  core/
    models.py          data classes, JSON serialization, synthetic sample
    geometry.py        rotated polygons, footprint overlap, clearance and site checks
    units.py           SI/US conversion registry, narrative conversion, rounding
    loads.py           service/factored BNBC combinations
    soil.py            stress, SPT corrections, bearing capacity, liquefaction
    bearing.py         pressure, sizing, stability, shallow uplift
    settlement.py      immediate, consolidation, secondary, differential
    piles.py           pile capacity (SPT/static/CPT), downdrag, uplift, Broms
                       lateral capacity, group layout and cap sizing
    structural/
      concrete.py      flexure, shear, punching, development, bars, crack width,
                       P-M interaction
      footing.py       isolated, combined and strip footing design
      pilecap.py       pile cap design: flexure, one-way shear, punching, strut-and-tie
      raft_design.py   raft thickness iteration, top/bottom steel, shear/punching
    rebar.py           project-wide bar schedule and BBS generation
    raft.py            rigid, Winkler strip and 16-DOF Kirchhoff plate analysis;
                       arbitrary imported raft outlines
    selector.py        foundation selection, clash checks, cost ranking
    report.py          Excel, PDF, CSV, JSON and import-template generation
  ui/                  PySide6 main window, seven pages, worker thread
    main_window.py     navigation, worker, project/export actions
    common.py          shared stylesheet, tables, cards and input helpers
    pages/             project, materials, soil, loads, options, results, export
tests/                 pytest suite (91 tests, offscreen Qt smoke test)
samples/               generated Excel, PDF, CSV, JSON and import template
run.py                 normal, --project and --smoke entry point
README.md              install, workflow, input rules, exports, testing, packaging
```

## Design assumptions and limits

- The tool is a design aid; results require review by a qualified foundation
  engineer.
- Soil-report PDF OCR is not automatic; data is entered through the GUI or an Excel
  template.
- Full 3D soil-structure FEM is not included. Raft analysis uses rigid, Winkler
  strip or plate methods; ETABS/SAFE reactions can be imported from CSV but their
  analysis results are not embedded.
- Missing soil parameters are flagged; correlations are used only with warnings.
- CPT capacity uses measured `qc`/`fs` where available and otherwise falls back
  to `qc = 0.40 N60` MPa in cohesionless soil or `0.20 N60` MPa in cohesive soil,
  with `fs` derived from `qc`.
- Downdrag is applied only to fill/organic, very soft cohesive (`cu <= 25 kPa` or
  `N60 < 8`) and loose cohesionless (`N60 < 8`) layers, with unit negative skin
  friction capped at 40 kPa (`0.25 cu` cohesive, `0.20 sigma_eff` cohesionless).
- Pile uplift capacity is `(0.70 skin + pile weight)/FS`, default FS 2.0.
- Broms lateral capacity uses the short-pile mechanism capped by pile yield
  moment with lever `1.5D + L/4`, default FS 2.5.
- P-M interaction uses `(P/phi_Pn)^1.5 + M/phi_Mn <= 1`, with `phi_Pn = 0.65`
  and `phi_Mn = 0.90`.
- Column `(x,y)` is the reaction/insertion point; the plan centre is
  `(x + dx, y + dy)`. Reactions are moved to the centre with
  `Mx_c = Mx - P*dy` and `My_c = My - P*dx`.
- Wall local axes use `u` along the wall and `v` normal to it:
  `M_u = Mx*cos(theta) + My*sin(theta)` and
  `M_v = My*cos(theta) - Mx*sin(theta)`.
- Rectangular column sections may be rotated counter-clockwise by `rotation`
  degrees; walls and their caps follow the wall axis.
- Site and adjacent-foundation checks use actual footprint polygons with a
  0.10 m clearance; wall caps are not reduced to bounding boxes for these checks.
- Raft outlines are optional imported convex polygons; exact polygon area,
  centroid and second moments drive rigid pressure, and plate elements outside
  the polygon are masked. Auto selects the plate method when a custom outline is
  present; Winkler strips report that a custom outline is approximate.
- The application is cross-platform; packaging a Windows `.exe` must be done on
  Windows with PyInstaller.

## Current state

- Core engine, foundation selection, reporting, PySide6 interface and tests are
  implemented, including geometry-aware selection, design and plotting.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` reports 91 passed.
- Sample outputs are regenerated in `samples/` after the audit fixes and the
  SI/US unit work.
- Units: the Project page selects `SI` or `US`; every input page reloads in the
  selected system and every export converts at its boundary. The engine and JSON
  storage remain SI. The conversion registry covers length, thickness, force,
  moment, moment per unit length, pressure, stress, unit weight, subgrade
  modulus, settlement, area, volume and mass. Cost rates use the unit-aware
  quantities `cost_per_volume`, `cost_per_length`, `cost_per_mass` and
  `cost_per_area`; `convert_text` converts SI values embedded in generated
  requirement/size/remarks narratives. Soil/load table headers, materials and
  pile labels, raft-outline labels, cost suffixes, Results cards and the PDF/GUI
  site-plan and SPT axes are rebuilt from the selected system. JSON numeric
  values stay SI and `info.units` records the display system at save time.
- The Excel workbook includes a Supplemental Checks sheet for crack width,
  uplift/buoyancy, downdrag, lateral and P-M checks; the PDF detailed
  calculations show the same values per element.
- The combined-footing beam moment envelope is checked against a closed-form
  free-free beam solution.
- The pile-cap strut-and-tie force, strut capacity and tie steel are checked
  against a worked four-pile example.
- The synthetic sample demonstrates a 0.15 m column offset (C1), circular
  columns (C2, C5), rectangular columns with offsets (C3, C4, C6), a 30-degree
  rotated column (C3) and an angled shear wall with explicit endpoints (W1).
- The sample soil profile includes CPT `qc`/`fs` values in the SM and SP layers
  so CPT capacity and fallback correlations are demonstrated.
- The sample is on soft clay: W1 selects a CHECK pile group; C1-C6 isolated
  footings and RAFT-1 are CHECK for settlement and/or crack width. This is
  intentional demonstration behaviour; real soil/reaction files are still
  required for final validation.
- The shear-wall cap follows the actual wall endpoints and angle and is
  width-constrained to clear adjacent column footings.
- Adjacent foundation footprints within 1.5 m are checked for differential
  settlement and angular distortion; the three soft-clay W1/column pairs report
  differential-settlement warnings in the synthetic sample.
- SPT liquefaction screening is driven by the optional PGA input; the sample
  reports FS 0.89 in the saturated 8-16 m silty-sand layer. Reports state when
  screening was not performed because PGA was not supplied.
- Sliding and overturning checks are applied to isolated, combined and strip/wall
  footings; the synthetic sample has ample stability factors.
- The sample reports five project warnings and twelve report warning lines,
  including the liquefaction trigger, the raft-alternative settlement/crack-width
  review and three adjacent-foundation differential-settlement warnings.
- Seven of eight results are selected; RAFT-1 is retained as a reviewed
  alternative.
- No git repository exists; changes are not committed.

## Completed audit fixes and unit system (2026-11-14)

- A Ponytail whole-build audit confirmed 17 issues not covered by the original
  65-test suite: 8 Must fix, 7 Should fix and 2 Nice to have. All 17 are now
  fixed. Details and per-item regression tests are in `.opencode/ponyfix.md`;
  the work items are checked in `.opencode/todo.md`.
- Fixed items: raft differential units and strip reporting, pile-cap anchorage
  status, strip/combined flexure status and peak-pressure design, reaction import
  replacement, Broms `f_c`/`f_y`, column rotation projections, CPT soil import,
  net-pressure settlement, mat steel weight, PDF raft moments, pile-cap flexure
  utilization, rotated site-plan polygons, numeric lateral token detection,
  direct end bearing, merged pile remarks, and dead-code/unused-import removal.
- Regression coverage is in `tests/test_regressions.py` (18 tests).
- SI/US interchangeability is implemented in `core/units.py` and wired through
  every GUI input page, importer, export and report. `tests/test_units.py` (8
  tests) covers the registry, narrative conversion, US CSV/Excel output and the
  offscreen GUI toggle.
- Verification: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
  reports 91 passed; `.venv/bin/python run.py --smoke` exits 0; `compileall`
  passes and an AST scan finds no unused imports.
- Sample outputs in `samples/` were regenerated with the current engine. The
  selected scheme is the W1 pile group plus C1-C6 isolated footings, all CHECK on
  the deliberately soft clay; RAFT-1 remains a reviewed alternative, with five
  project warnings.
- Real soil-report and ETABS/SAFE files remain unavailable, so the synthetic
  sample is still the validation case. Windows packaging must be built on
  Windows with PyInstaller.
