# Build Plan

## 1. Deliverable

A desktop PySide6 application that:

1. Imports or accepts soil-report data and base reactions for any number of columns
   and shear walls.
2. Evaluates isolated, combined, strip, raft, single-pile and pile-group
   foundations.
3. Performs full detailed geotechnical and structural design per BNBC 2020.
4. Exports a foundation schedule with type, requirement, size, number, utilization,
   reinforcement, quantities and governing code clause.
5. Exports Excel, PDF, CSV and JSON project files.

## 2. User flow

1. Open the app or load the synthetic sample project.
2. Enter project information and materials.
3. Enter boreholes, soil layers, SPT values and direct report capacities.
4. Enter column and shear-wall reactions, either as service/factored envelopes or
   as DL/LL/W/EQ load cases.
5. Set foundation options, site boundaries, pile options and cost rates.
6. Run the design.
7. Review results by element and by foundation type; inspect detailed calculations.
8. Export the schedule, report and quantities.

## 3. Calculation engine

### 3.1 Loads

- Normalise DL/LL/WL/EQ/buoyancy cases.
- Generate BNBC 3.9.2 service combinations.
- Generate BNBC 2.7.3.1 strength combinations.
- Support pre-combined service and factored envelopes.
- Build governing envelopes for bearing, settlement and structural design.

### 3.2 Soil

- Layer interpolation and groundwater-aware total/effective stress.
- SPT overburden correction and N60.
- Correlations for phi, cu, Es and modulus of subgrade reaction.
- Meyerhof bearing capacity with shape and depth factors.
- Direct allowable bearing and pile capacity overrides.
- Presumptive bearing values from Table 6.3.7.
- Simplified SPT liquefaction trigger/FS.
- CPT capacity option using measured cone resistance and sleeve friction with
  SPT-based fallback correlations.
- Shallow-footing buoyancy/uplift check including hydrostatic and explicit uplift.

### 3.3 Shallow foundations

- Required area from service load and allowable pressure.
- Biaxial eccentricity, kern check and 33% lateral overstress.
- Practical dimension selection in 50 mm increments.
- Minimum depth and thickness checks.
- Immediate, consolidation and secondary settlement; differential and angular
  distortion.
- Sliding and overturning checks.
- Buoyancy/uplift check with permanent load and footing/soil weight.
- Isolated, combined and strip/wall footing structural design:
  flexure, one-way shear, punching shear, development length, minimum steel and
  service crack width.
- Optional top reinforcement where negative moments occur.

### 3.4 Deep foundations

- Driven precast, bored cast-in-situ and drilled-shaft capacity by SPT, static
  alpha/beta, CPT and direct report values.
- Critical-depth effects, pile weight and FS by construction control.
- Structural axial capacity and minimum reinforcement.
- Downdrag/negative skin friction from soft or loose layers.
- Pile uplift capacity and Broms short-pile lateral capacity.
- Simplified P-M interaction check.
- Single pile under a column where D >= 600 mm.
- Group layout, spacing, efficiency, block failure, group settlement and cap
  sizing; group results carry uplift, lateral and P-M utilizations.
- Pile cap structural design: flexure, one-way shear, punching, strut-and-tie
  where applicable and service crack width.

### 3.5 Raft

- Rigid raft contact pressure with biaxial eccentricity.
- Beam-on-elastic-foundation (Winkler) strip analysis using 2-node Hermite beam
  elements and nodal springs.
- Auto-select plate for custom/large outlines and Winkler strips for regular
  rafts.
- Optional finite-difference plate on Winkler springs for large/irregular rafts,
  with elements outside a custom outline masked.
- Optional imported convex raft outline with exact polygon area, centroid and
  second moments.
- Raft flexure, one-way shear and punching design; top and bottom steel.
- Raft service crack-width check.
- Buoyancy and settlement checks. Sliding/overturning checks for rafts are outside
  the current scope.

### 3.6 Plan geometry

- Column `(x, y)` is the reaction/insertion point; `(dx, dy)` offsets it to the
  column centre and transforms moments to the centre.
- Rectangular columns use `L x W` with optional counter-clockwise `rotation`;
  circular columns use diameter `d`.
- Shear walls use centreline endpoints `(x1, y1)-(x2, y2)` plus thickness `t`,
  with a legacy centre/length fallback.
- Wall moments are resolved into wall-local along-wall and normal components.
- Foundation footprints are convex polygons: rotated rectangles for columns,
  wall caps and strips, circles for circular columns, and wall segments for shear
  walls.
- Site-boundary and adjacent-foundation checks use the polygons with a 0.10 m
  clearance; plotting uses the same geometry.

### 3.7 Selection

- Column: isolated -> combined -> raft -> single pile -> pile group with cap.
- Shear wall: strip footing -> pile cap along wall -> raft.
- Check site boundary, adjacent-footing overlap and property-line constraints.
- Rank feasible options by preference or estimated cost.
- Record alternatives, utilization and governing clause for every element.
- Propagate uplift, lateral, P-M, downdrag and crack-width checks into candidate
  status, remarks and check dictionaries.

## 4. GUI

PySide6 main window with tabs or sidebar pages:

- **Project**: name, location, engineer, date, code, units, notes.
- **Materials**: f'c, fy, cover, bar sizes, spacing limits, phi factors.
- **Soil**: borehole selector, GWT, layer table, SPT, CPT `qc`/`fs`, lab data,
  direct capacities, SPT plot.
- **Loads**: columns and walls table with insertion coordinates, centre offsets,
  section shape/dimensions/rotation, wall endpoints and thickness,
  service/factored reactions, optional load cases, paste/import from Excel/CSV
  and ETABS/SAFE reaction CSV import.
- **Options**: allowed foundation types, geometry limits, FS, pile options
  (including CPT method), raft options and imported outline, site boundary,
  crack/uplift/downdrag/lateral/P-M checks and cost rates.
- **Results**: summary cards, schedule table, per-element detail, site plan and
  foundation outlines, warnings.
- **Export**: Excel schedule, PDF report, CSV, JSON save/load, import template.

All long calculations run in a worker thread so the UI stays responsive.

## 5. Reports

### Excel

Sheets:

1. Summary
2. Foundation Schedule
3. Geotech Checks
4. Structural Checks
5. Supplemental Checks
6. Rebar Schedule
7. Bar Bending Schedule
8. Quantities
9. Soil Inputs
10. Code Basis

### PDF

- Cover and project information
- Design basis and assumptions
- Soil profile
- Site plan
- Foundation schedule
- Detailed calculations per element
- Warnings and limitations

### CSV

- Plain foundation schedule.

### JSON

- Complete project save/reload.

## 6. Testing and validation

- Unit tests for SPT correction, bearing capacity, pressure distribution, pile
  capacity, flexure, shear, punching and selection logic.
- Regression tests for column rotation, CPT capacity/fallbacks, crack width,
  shallow uplift, downdrag, pile uplift, Broms lateral capacity, P-M interaction,
  polygon pressure/non-rectangular rafts and ETABS/SAFE reaction import.
- Round-trip JSON test.
- Excel/PDF export smoke tests.
- GUI smoke test with Qt offscreen platform.
- Synthetic sample project validated against hand calculations.
- Later: validate against user-provided soil report and ETABS/SAFE reactions.

## 7. Implementation phases

### Phase 1 - Foundation and core models

- Project scaffold and dependency file.
- Data models and JSON serialization.
- Synthetic sample project.
- Unit helpers.

### Phase 2 - Geotechnical engine

- Load combinations.
- Soil stress, SPT and bearing capacity.
- Shallow sizing, pressure, stability and settlement.
- Pile capacity, group and cap sizing.
- Liquefaction.

### Phase 3 - Structural engine

- Concrete flexure, shear, punching and development helpers.
- Isolated, combined and strip footing design.
- Pile cap design.
- Raft analysis and design.
- Rebar selection and BBS.

### Phase 4 - Selection and reporting

- Foundation selection and ranking.
- Excel, PDF and CSV export.
- Excel/CSV import templates.
- Project JSON save/load.

### Phase 5 - GUI

- Main window and navigation.
- Project, materials, soil, loads and options pages.
- Results and detail views.
- Site-plan and SPT plots.
- Worker thread and validation messages.

### Phase 6 - Verification and packaging

- Test suite and sample data.
- GUI smoke test.
- README and user guide.
- Optional PyInstaller packaging notes.

## 8. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Full detailed design scope is large | Build in runnable phases; keep engine independent of GUI |
| Soil reports lack consolidation/liquefaction data | Accept direct values; flag missing data; provide correlations with warnings |
| Raft plate analysis is complex | Auto-use rigid/Winkler strips; plate solver only for irregular/large rafts |
| Pile cap strut-and-tie detailing is complex | Use section design per 6.8.5.4 with optional strut-and-tie check |
| GUI cannot be fully automated | Use Qt offscreen smoke test and manual launch instructions |
| Windows packaging on Linux | Document PyInstaller command and require building on Windows |
| Code clause transcription errors | Keep formula references in result details and add unit tests |

## 9. Acceptance criteria

- App launches and loads the synthetic sample.
- User can add/edit columns, walls, boreholes and layers.
- Design run produces a foundation type, size and number for every element.
- Schedule exports to Excel, PDF and CSV.
- Project saves and reloads as JSON.
- Unit tests pass.
- Every result shows a utilization and governing BNBC clause.
- Missing data produces a visible warning, not a silent assumption.

## 10. Status at 2026-11-14

### Delivered

- Phase 1: models, JSON serialization, sample project and units.
- Phase 2: loads, soil/SPT, bearing, settlement, piles, liquefaction.
- Phase 3: concrete design, isolated/combined/strip footings, pile caps, raft
  analysis/design, rebar schedule and BBS.
- Phase 4: foundation selection, clash checks, cost ranking, Excel/PDF/CSV/JSON
  reports and Excel/CSV importers.
- Phase 5: complete PySide6 interface with seven pages, plots, worker thread,
  validation, results detail and export actions.
- Phase 6: 91-test pytest suite, offscreen GUI smoke tests, README, packaging
  notes and regenerated sample outputs in `samples/`.
- Plan-geometry enhancement: column insertion offsets and centre transformation,
  rectangular/circular sections, wall endpoints and wall-local moments, rotated
  wall caps, polygon-based clash/site checks and geometry-aware plotting.
- Future-feature completion:
  - Arbitrary counter-clockwise rotation for rectangular columns, carried through
    footprints, JSON/Excel/CSV and the GUI.
  - Non-rectangular/imported raft outlines with exact polygon pressure and
    masked plate elements.
  - ETABS/SAFE CSV reaction import with sign, case and lateral/factored detection.
  - CPT pile capacity with SPT fallback correlations and GUI soil columns.
  - Service crack-width checks for isolated, combined, strip, raft and pile caps.
  - Shallow-footing buoyancy/uplift check.
  - Pile downdrag, uplift capacity, Broms lateral capacity and P-M interaction.
- Adjacent-foundation differential settlement and angular-distortion checks.
- SPT liquefaction screening with optional PGA input, Excel/PDF reporting and
  review warnings for triggered layers.
- Sliding and overturning checks extended to combined and strip/wall footings.
- Combined-footing beam moments verified against a closed-form free-free beam
  solution.
- Pile-cap strut-and-tie angle, force, strut capacity and tie steel verified
  against a worked four-pile example.

### Verification

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` -> 91 passed.
- `QT_QPA_PLATFORM=offscreen .venv/bin/python run.py --smoke` -> clean start-up.
- GUI design run on the synthetic sample -> W1 pile group plus C1-C6 isolated
  footings selected, all CHECK on the deliberately soft clay; RAFT-1 retained as
  an alternative; 5 project warnings (raft alternative settlement/crack width,
  liquefaction trigger and three adjacent-foundation differential settlement
  warnings); reports list 12 warning and review lines including per-element
  remarks.
- JSON reload preserves element geometry (including rotation), CPT data, results
  and warnings.
- Sample Excel, PDF, CSV, JSON and import template regenerated with rotation, CPT
  columns, new check rows, audit-fix values, warning tables and SI/US-aware
  headers.

### Remaining

- Validate against real soil-report and reaction files when supplied.
- Build the Windows executable on Windows with PyInstaller.

## 11. Post-audit fixes and unit system (completed 2026-11-14)

A Ponytail whole-build audit confirmed 17 issues that the original 65-test suite
did not catch: 8 Must fix, 7 Should fix and 2 Nice to have. The detailed
instructions, file references, regression tests and acceptance checks are in
`.opencode/ponyfix.md`; `.opencode/todo.md` tracks the completed checkboxes.

### Delivered fixes

1. Raft differential: metres converted to millimetres; Winkler strips now report
   an explicit value or note instead of an automatic pass.
2. Pile-cap anchorage: selected bar diameter, minimum available length and CHECK
   status when development is short.
3. Strip/combined status: flexure and bar-selection flags included in the status
   and remarks.
4. Strip/combined flexure: peak soil pressure drives the cantilever and beam
   moments instead of the average pressure.
5. Reaction CSV import: `replace=True` clears each element once and keeps every
   load case.
6. Broms lateral capacity: project `f_c` and `f_y` passed through, hardcoded
   30/420 MPa removed.
7. Column rotation: projected section dimensions used in footing, raft punching
   and pile-cap design.
8. Soil CPT import: `qc (MPa)` and `CPT fs (kPa)` parsed and retained.
9. Shallow settlement: net pressure after overburden subtraction.
10. Mat steel weight: erroneous 0.5 factor removed.
11. PDF raft moments: read from `design["analysis"]`.
12. Structural Checks: pile-cap flexure utilization computed and exported.
13. Site plan: rotated column polygons drawn in PDF and GUI.
14. Lateral detection: numeric tokens such as `1.2D+1.6W` recognized.
15. Direct pile end bearing: recognized without a skin value.
16. Pile remarks: group and cap remarks merged and deduplicated.
17. Dead code and unused imports removed (~180 lines, no dependency changes).

### SI/US unit system

- `core/units.py` holds the conversion registry, `convert`, `to_si`, `factor`,
  `label`, `normalize_system`, `system_of` and `convert_text`.
- Internal models, calculations and JSON remain SI. GUI inputs, importers,
  exports and reports convert at their boundary.
- The Project page selects SI or US; changing it reloads the Materials, Options,
  Soil, Loads, Results and export views in the selected system.
- Excel, CSV and PDF headers and values, quantities, soil/CPT/liquefaction rows
  and narrative strings all follow the selected system.
- Cost rates are converted with `cost_per_volume`, `cost_per_length`,
  `cost_per_mass` and `cost_per_area`, so SI rates are entered per m3/m/kg/m2
  and US rates per ft3/ft/lb/ft2 while the engine keeps SI rates.
- Soil/load table headers and the materials bar-diameter, pile, raft-outline and
  cost labels are rebuilt on each unit change; PDF and GUI site-plan/SPT axes
  use the selected length unit.
- JSON always stores SI numeric values; `info.units` records the display system
  active at save time.

### Verification and exit criteria

- Every fix has a regression test in `tests/test_regressions.py` (18 tests).
- `tests/test_units.py` (8 tests) covers conversion round-trips, labels,
  narrative conversion, US CSV/Excel output and the offscreen GUI toggle.
- Full suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` -> 91
  passed.
- Smoke: `.venv/bin/python run.py --smoke` exits 0; `compileall` passes and an
  AST scan finds no unused imports.
- Sample outputs regenerated in `samples/`.
- `context.md`, `progression.md`, `todo.md`, `ponyfix.md` and `README.md` updated.
- No Must-fix, Should-fix or Nice-to-have item remains open before real-project
  validation.
