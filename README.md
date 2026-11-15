# BNBC 2020 Foundation Designer

Created and maintained by [Nandini Shahnewaz](https://github.com/nandineee-luvluv).

A PySide6 desktop application for the geotechnical and structural design of
foundations from soil-report data and column/shear-wall base reactions. The
application selects foundation types, sizes them, checks them to BNBC 2020, and
exports a foundation schedule, calculation report, rebar schedule and bar bending
schedule.

## Features

- **Foundation types:** isolated, combined, strip/wall, single pile with cap,
  pile group with cap, and raft/mat.
- **Plan geometry:** column insertion/reaction points with centre offsets,
  rectangular `L x W` (with optional counter-clockwise rotation) or circular
  diameter sections, and shear walls defined by start/end centreline points and
  thickness. Foundation selection, clash checks, site-boundary checks and
  site-plan plotting all use the actual (rotated) footprints.
- **Soil input:** any number of boreholes and soil layers, SPT values, CPT cone
  resistance/sleeve friction, laboratory data, groundwater table, and direct
  allowable bearing or pile skin/end capacities from a soil report. A
  user-supplied peak ground acceleration enables simplified SPT liquefaction
  screening; triggered layers are reported in the warnings, Excel workbook and
  PDF.
- **Load input:** pre-combined service and factored reactions, separate
  DL/LL/WL/EQ cases that are combined to BNBC 2020, or ETABS/SAFE reaction CSV
  import (including automatic compression-positive sign and case detection).
- **Automatic selection:** compares feasible foundation types per element, checks
  site boundaries and adjacent-foundation clashes, and ranks by preference or
  estimated cost.
- **Shear walls:** chooses between a strip footing, a pile cap along the wall (or
  a pile group), and a raft where appropriate.
- **Raft analysis:** rigid contact pressure, Winkler strip analysis, and a
  16-DOF Kirchhoff plate on Winkler springs for large or irregular rafts.
  Optional imported convex outline with exact polygon pressure and masked plate
  elements.
- **Detailed design:** bearing pressure and kern, settlement, sliding and
  overturning, shallow buoyancy/uplift, pile capacity (SPT, static, CPT or
  direct), downdrag, uplift, Broms lateral capacity, P-M interaction, group
  checks, pile-cap flexure/shear/punching/strut-and-tie, raft
  flexure/shear/punching, service crack width, development length, and
  reinforcement selection.
- **Outputs:** Excel workbook (ten sheets), printable PDF, CSV schedule, JSON
  project file, and an Excel import template.
- **Units:** SI or US customary, selected on the Project page. Every input,
  result, export and report follows the selected system while the engine keeps
  all calculations in SI.

Positive axial load `P` is compression.

### Unit systems

| Quantity | SI | US customary |
|---|---|---|
| Length | m | ft |
| Thickness, pile diameter, bar size | mm | in |
| Force | kN | kip |
| Moment | kN.m | kip.ft |
| Moment per unit length | kN.m/m | kip.ft/ft |
| Pressure / bearing | kPa | ksf |
| Stress, concrete and steel strength | MPa | ksi |
| Unit weight | kN/m3 | pcf |
| Subgrade modulus | kN/m3 | kcf |
| Settlement | mm | in |
| Area | m2 | ft2 |
| Volume | m3 | ft3 |
| Mass | kg | lb |
| Cost rate | per m3, per m, per kg, per m2 | per ft3, per ft, per lb, per ft2 |

Switch **Units** on the Project page to reload the input pages in the selected
system. Soil and load table headers, materials and pile labels, raft-outline
labels, cost-rate suffixes, Results cards, site-plan and SPT axes all follow the
selection. Stored project values remain SI, so switching back and exporting is
lossless. Excel, CSV and PDF headers, schedule values, quantities, soil inputs,
liquefaction and calculation narratives all use the selected system; JSON stores
SI numeric values and records the display system in `info.units`.

## Installation

The repository is tested with Python 3.14 in a local `.venv`. Any Python 3.11+
should work.

```bash
uv venv .venv
uv pip install -r requirements.txt
```

Alternatively, with the standard library tools:

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Launching

```bash
.venv/bin/python run.py
```

The application starts with the synthetic sample project loaded so every page
and the design workflow can be explored immediately.

Open a saved project directly:

```bash
.venv/bin/python run.py --project samples/Sample_Residential_Building.json
```

Run a headless start-up check:

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python run.py --smoke
```

## Workflow

1. **Project** - enter the project name, location, engineer, date, design code,
   unit system and notes. Changing **Units** between `SI` and `US` reloads every
   input page in the chosen system. Use **Load sample** to restore the
   demonstration project, or **Open JSON**/**Save JSON** for project files.
2. **Materials** - set `f'c`, `fy`, concrete unit weight, cover, available bar
   diameters, spacing limits and strength-reduction factors.
3. **Soil profile** - add boreholes with coordinates and groundwater depth, then
   enter soil layers from top to bottom. Layers are defined by bottom depth and
   include soil type, unit weights, strength parameters, SPT `N`/`N60`, CPT `qc`
   and sleeve friction `fs`, compressibility, subgrade modulus and optional direct
   capacities. The SPT profile plot updates from the entered data.
4. **Columns & walls** - enter the base reactions and plan geometry for each
   column and shear wall. Columns use `X`/`Y` as the reaction or insertion point,
   `dx`/`dy` to offset that point to the column centre, either `L` x `W` for a
   rectangular section (with optional `Rotation` in degrees) or `Shape =
   Circular` with a diameter. Walls use the `Wall x1/y1` and `Wall x2/y2`
   centreline endpoints plus `Wall t`; blank endpoints fall back to `X`/`Y`,
   `Length` and `Wall t`. Columns accept pre-combined service and factored
   envelopes, use **Edit load cases...** for separate DL/LL/WL/EQ reactions, or
   use **Import ETABS/SAFE reactions...** for a reaction CSV.
5. **Options** - enable/disable foundation systems, set geometry limits, factors
   of safety, pile diameters/lengths/spacing and capacity method (SPT, Static,
   CPT or Direct), site boundaries, settlement limits and optional cost rates.
   **Raft trigger** can be `Auto`, `Always` or `Never`; **Raft analysis** can be
   `Auto`, `Rigid`, `Winkler strips` or `Plate`; an optional raft outline can be
   typed or imported from CSV. Serviceability and supplementary checks cover
   crack width, shallow uplift, downdrag, pile uplift, Broms lateral capacity and
   P-M interaction.
6. **Run design** - the calculation runs in a worker thread. Review the summary
   cards, foundation schedule, per-element calculation details, site plan,
   alternatives and warnings on the **Results** page.
7. **Export** - choose an output folder and write the Excel workbook, PDF report,
   CSV schedule, JSON project and Excel import template. Export all files at
   once with **Export all**.

## Input conventions

- Soil layer bottom depths must increase from the ground surface.
- Leave a direct bearing or pile-capacity cell blank to use the built-in SPT or
  static correlation. Enter a value to override it with the soil-report value.
- For a pre-combined envelope, fill the service `P`, `Mx`, `My`, `Vx`, `Vy`
  columns and, if available, the factored envelope. If the factored row is left
  at zero, the service envelope is used to build strength combinations.
- For explicit load cases, use **Edit load cases...** on the Columns & walls
  page. The engine generates BNBC service and strength combinations and uses the
  governing values for bearing, settlement and structural design.
- A column `X`/`Y` is the reaction (insertion) point. The actual column centre is
  `(X + dx, Y + dy)`. Moving the reaction to the centre adds the offset moments
  `Mx_centre = Mx - P*dy` and `My_centre = My - P*dx`. Footings and pile caps are
  placed on the column centre, while the reaction marker remains at the insertion
  point on the site plan.
- ETABS/SAFE reaction CSV import accepts `Label`, `Load Case/Combo`, `FZ`, `MX`,
  `MY`, `FX` and `FY` columns (with common synonyms). ETABS/SAFE `FZ` tension-
  positive values are converted to compression-positive `P`; case names
  containing factors or `1.4D`-style tokens are marked factored, and names with
  `W`/`E`/`EQ` are marked lateral. Rows are merged by load case unless
  `Replace existing` is selected.
- CPT capacity uses `qc` in MPa and `fs` in kPa. Leave them blank to fall back to
  `qc = 0.40 N60` MPa in cohesionless soil or `0.20 N60` MPa in cohesive soil,
  with `fs` derived from `qc`.
- A shear wall is defined by its centreline endpoints `(x1, y1)` and `(x2, y2)`
  and its thickness. Wall caps and strip footings are oriented along that line;
  their footprint is a rotated rectangle, not an axis-aligned bounding box. A
  wall without endpoints falls back to the legacy representation: centre `(X, Y)`,
  length along x and `Wall t`.
- Wall reactions are rotated into wall-local axes: `M_along = Mx*cos(theta) +
  My*sin(theta)` and `M_normal = My*cos(theta) - Mx*sin(theta)`, where `theta` is
  the wall angle from the global x-axis. The in-plane moment drives the pile
  group along the wall; the out-of-plane moment varies pressure across the cap or
  strip width.
- Site and clash checks use the actual foundation footprint polygons with a
  0.10 m clearance between adjacent foundations. Rotated wall caps are compared
  as polygons rather than by their bounding boxes.
- Site limits of +/-5000 m or wider are treated as "no site boundary"; set real
  property-line coordinates to activate boundary warnings.

## Excel and CSV import

Use **Write Excel import template** on the Export page, or import an existing
Excel/CSV file from the Soil or Columns & walls pages. The template contains:

- `Elements` - one row per column or wall with insertion coordinates, centre
  offsets, section shape/dimensions/rotation, wall endpoints and thickness,
  preferred foundation type, service/factored reactions and notes. The template
  includes illustrative rectangular, circular, rotated-column and wall rows.
- `Soil Layers` - one row per borehole layer with depth, classification, unit
  weights, strength, SPT, CPT `qc`/`fs`, compressibility and direct capacity
  values.

The element/soil importers replace the corresponding data in the current
project. Check the imported values on the page before running the design.

## Design basis

The calculations follow BNBC 2020, Part 6, Chapters 2, 3, 6 and 8:

- Service combinations for geotechnical checks: `D+L`, `D+L+W/E`,
  `0.9D+buoyancy`, with the clay `D+0.5L` case and 33% lateral overstress where
  applicable.
- Strength combinations for structural design: `1.4(D+F)`,
  `1.2(D+F+T)+1.6(L+H)+0.5(Lr or R)`, `1.2D+1.6(Lr or R)+(L or 0.8W)`,
  `1.2D+1.6W+L+0.5(Lr or R)`, `1.2D+1.0E+L`, `0.9D+1.6W+1.6H` and
  `0.9D+1.0E+1.6H`.
- Bearing pressure with biaxial eccentricity and a preferred resultant within the
  middle third.
- Settlement limits of 25 mm on sand, 40 mm on clay and 20 mm differential, with
  angular-distortion checks.
- Sliding and overturning checks with a minimum FS of 1.5 for shallow,
  combined and strip/wall footings.
- Simplified SPT liquefaction screening using a user-supplied peak ground
  acceleration; a factor of safety below 1.0 raises a review warning.
- Driven and bored pile SPT correlations, static alpha/beta capacity, CPT
  cone/sleeve capacity, direct capacity overrides, structural axial capacity,
  group efficiency, block failure and group settlement; minimum spacing of 2.5D
  end-bearing or 3.0D friction and 750 mm.
- Pile downdrag from fill/organic, very soft cohesive and loose cohesionless
  layers; unit negative skin friction is capped at 40 kPa.
- Pile uplift capacity `(0.70 skin + weight)/FS` (default FS 2.0) and Broms
  short-pile lateral capacity capped by pile yield moment (default FS 2.5).
- Simplified pile P-M interaction `(P/phi_Pn)^1.5 + M/phi_Mn <= 1` with
  `phi_Pn = 0.65` and `phi_Mn = 0.90`.
- Shallow-footing buoyancy/uplift check: hydrostatic plus explicit uplift versus
  permanent load and footing/soil weight (default FS 1.10; passive resistance
  ignored).
- Service crack-width checks to the EC2/BNBC 6.8.9 simplified formula, default
  limit 0.30 mm, for isolated, combined, strip, raft and pile-cap designs.
- Pile caps checked for flexure, one-way shear, column and pile punching, a
  supplementary strut-and-tie check and service crack width.
- Raft contact pressure, Winkler/plate analysis, imported outline geometry,
  settlement, punching, one-way shear, buoyancy, crack width and reinforcement
  design.
- Strength-reduction factors of 0.90 flexure, 0.75 shear and 0.65 bearing.

The synthetic sample is deliberately founded on soft clay, so several shallow
foundations report `CHECK` for settlement and the raft alternative also reports
`CHECK`. This demonstrates the warning and review workflow; it is not a claim
that the sample scheme is constructible as shown.

## Outputs

- **Excel workbook:** Summary, Foundation Schedule, Geotech Checks, Structural
  Checks, Supplemental Checks, Rebar Schedule, Bar Bending Schedule, Quantities,
  Soil Inputs and Code Basis. The Supplemental Checks sheet lists crack width,
  uplift/buoyancy, downdrag, lateral and P-M utilizations; the PDF detailed
  calculations show the same checks per element. Headers and values follow the
  project unit system.
- **PDF report:** cover, design basis, SPT profile, site plan, foundation
  schedule, detailed checks, rebar/BBS, quantities and warnings, in the project
  unit system.
- **CSV:** plain foundation schedule in the project unit system.
- **JSON:** complete project, including results, for save/reload. Every numeric
  engineering value is stored in SI; `info.units` records the display system
  that was active at save time, so reloading restores the same view without
  changing the stored numbers.
- **Excel template:** input sheets with illustrative rectangular-column,
  circular-column and wall rows.

Sample outputs are generated in `samples/`. The current files are
`Sample_Residential_Building.{xlsx,pdf,csv,json}` and
`Sample_Residential_Building_import_template.xlsx`.

## Testing

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

The suite covers soil stress and SPT correction, bearing capacity, pressure
distribution, flexure/shear/punching, circular punching geometry, pile capacity
and groups, column offsets/rotation and wall-local moments, rotated-footprint
clash/site checks, polygon pressure, adjacent-foundation differential settlement,
CPT capacity and fallbacks, crack width, shallow uplift, downdrag, pile uplift,
Broms lateral capacity, P-M interaction, raft outlines, ETABS/SAFE reaction
import, foundation selection, JSON round-trip, Excel/PDF/CSV export, import
templates/parsers, and an offscreen PySide6 design run. Regression tests cover all
17 audit fixes, and unit tests cover the SI/US conversion registry, narrative
conversion, US exports and the GUI unit toggle. The current suite reports **91
passing tests**.

## Packaging

A desktop executable can be built with PyInstaller:

```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name BNBC-Foundation-Designer run.py
```

Build the Windows executable on Windows, and the Linux binary on Linux. The
application has no runtime data files outside the Python package, so no extra
`--add-data` entries are normally required; PyInstaller's hooks collect
PySide6, matplotlib, numpy, pandas, openpyxl and reportlab.

## Limitations

- This is a design aid. All output must be reviewed and approved by a qualified
  foundation engineer before construction.
- Soil-report PDF OCR is not automatic; enter data through the GUI or the Excel
  template.
- A full 3D soil-structure finite-element analysis is not included. Raft design
  uses rigid, Winkler strip or plate methods; ETABS/SAFE reactions can be
  imported, but their analysis results are not embedded.
- Liquefaction screening is a simplified SPT trigger; site response, cyclic
  testing and post-liquefaction settlement require separate geotechnical study.
- Downdrag, pile uplift, Broms lateral capacity and P-M interaction are
  simplified code-level checks. They do not replace project-specific pile load
  tests, lateral analyses or detailed soil-structure interaction.
- Crack width uses the EC2/BNBC simplified formula with service moments; where
  only factored raft moments are available they are divided by 1.4 as an
  approximation.
- Raft registration for a custom outline is treated as a convex footprint; highly
  re-entrant mat shapes should be approximated or checked separately.
- Missing parameters are flagged and correlations are used only where the input
  is insufficient; verify all correlated values against the project soil report.

## Audit status

A whole-build Ponytail audit on 2026-11-14 confirmed 17 issues: 8
correctness/safety fixes, 7 quality/reporting fixes and 2 cleanup items. All 17
are now fixed, each with regression coverage, and the SI/US unit system was added
at the same time. The actionable record is `.opencode/ponyfix.md`, with completed
checkboxes in `.opencode/todo.md`.

The regenerated sample selects the W1 pile group and the C1-C6 isolated footings;
all seven report `CHECK` because the demonstration soil is deliberately soft
clay. RAFT-1 is retained as an alternative. The sample reports five project
warnings (liquefaction trigger, raft-alternative review and three adjacent
differential-settlement warnings). Regenerate the outputs with the Export page
after changing the project.

## Project context

Durable session notes, architecture, audit, unit-system, verification, repository
and backup records live in [`.xcontext/MAP.md`](.xcontext/MAP.md). Read that map
first when resuming development.

## License

Copyright (c) 2026 Nandini Shahnewaz.

Released under the MIT License. You may use, copy, modify, merge, publish,
distribute, sublicense, and sell copies of this software, including for
commercial work, provided the original copyright notice and permission notice
are retained in all copies or substantial portions. The license grants usage
rights only; it does not transfer ownership or authorship of the original
project. See [LICENSE](LICENSE).
