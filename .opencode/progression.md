# Progression Log

## 2026-11-13 to 2026-11-14

### Completed

1. **Environment**
   - Confirmed empty workspace.
   - System Python 3.13.5 lacks `pip`, `venv` and `tkinter`; `uv` is available.
   - Created `.venv` with Python 3.14.10.
   - Installed PySide6 6.12, numpy, pandas, openpyxl, matplotlib, reportlab and
     pytest.

2. **Project decisions**
   - PySide6 desktop app.
   - Full detailed geotechnical + structural design.
   - SPT and direct soil-capacity values.
   - Single pile under column.
   - Auto-select shear-wall foundation.
   - Auto raft analysis.
   - Both pre-combined and load-case reactions.
   - Full rebar schedule + BBS.
   - Synthetic sample first.

3. **Core models** (`bnbc_foundation/core/models.py`)
   - `ProjectInfo`, `Materials`
   - `SoilLayer`, `Borehole`
   - `Reaction`, `Element`
   - `FoundationOptions`
   - `DesignResult`
   - `Project`
   - JSON serialization helpers
   - Synthetic sample project with five columns and one shear wall

4. **Units** (`bnbc_foundation/core/units.py`)
   - SI conversion helpers, rounding, interpolation and clamping.

5. **Loads** (`bnbc_foundation/core/loads.py`)
   - Case normalisation.
   - BNBC 3.9.2 service combinations.
   - BNBC 2.7.3.1 strength combinations.
   - Governing reaction helpers.

6. **Soil** (`bnbc_foundation/core/soil.py`)
   - Total/effective stress with water table.
   - SPT correction and N60.
   - Phi, cu, Es and subgrade modulus correlations.
   - Meyerhof ultimate and allowable bearing capacity.
   - Direct and presumptive bearing values.
   - Simplified SPT liquefaction check.

7. **Shallow bearing** (`bnbc_foundation/core/bearing.py`)
   - Biaxial pressure distribution, kern check and tension detection.
   - Isolated and combined footing sizing.
   - Sliding and overturning checks.
   - Service-combination pressure check.

8. **Settlement** (`bnbc_foundation/core/settlement.py`)
   - Immediate elastic settlement.
   - One-dimensional primary consolidation.
   - Secondary compression.
   - 2:1 stress distribution.
   - Differential settlement and angular distortion.
   - BNBC settlement limits.

9. **Piles** (`bnbc_foundation/core/piles.py`)
   - Driven/bored SPT capacity for clay, sand and silt.
   - Static alpha/beta capacity.
   - Direct capacity overrides.
   - Structural axial capacity.
   - Single-pile selection.
   - Group layout, spacing, efficiency, block capacity and settlement.
   - Pile cap plan sizing.

10. **Structural concrete** (`bnbc_foundation/core/structural/concrete.py`)
    - Flexural design and minimum steel.
    - Bar selection and spacing.
    - One-way shear capacity.
    - Punching shear capacity.
    - Development length.
    - Steel weight helpers.

11. **Footings** (`bnbc_foundation/core/structural/footing.py`)
    - Isolated footing structural design: flexure, one-way shear, punching,
      minimum steel, top mesh, settlement and stability.
    - Strip/wall footing design.
    - Combined footing design with beam shear/moment envelope.

12. **Scaffold and corrections**
    - Added package initialisers, `requirements.txt`, `.gitignore`.
    - Fixed `service_pressure_candidates` to compare utilization directly.
    - Piles and combined footings now use generated BNBC service/factored
      combinations instead of a single raw reaction.
    - Combined-footing top steel now comes from a proper flexural design.

13. **Pile caps** (`bnbc_foundation/core/structural/pilecap.py`)
    - Rigid-cap pile reaction distribution including cap self-weight.
    - Flexure at column faces in both directions.
    - One-way shear at `d` from the column face.
    - Punching at the column and at the heaviest pile.
    - Simplified strut-and-tie angle, force, strut capacity and tie steel.
    - Iterative cap thickness; bottom mat; nominal top mat; development check.

14. **Raft analysis** (`bnbc_foundation/core/raft.py`)
    - Rigid biaxial contact pressure and kern check.
    - Free-end beam-on-elastic-foundation strips with point loads and applied moments.
    - Tributary-width strip assignment with load spreading over effective patches.
    - 16-DOF bicubic Hermite Kirchhoff plate on Winkler springs with free edges.
    - Verified Gauss integration area factor and uniform-load patch test.
    - Auto method choice: plate for large/irregular rafts, strips otherwise.
    - Settlement, differential deflection, one-way shear, punching and buoyancy checks.

15. **Raft design** (`bnbc_foundation/core/structural/raft_design.py`)
    - Thickness iteration for shear and punching.
    - Top and bottom reinforcement in both directions.
    - Flexure, shear, punching and bearing utilization; concrete and steel quantities.

16. **Rebar schedule** (`bnbc_foundation/core/rebar.py`)
    - Project-wide bar marks from all foundation types.
    - Cut lengths, hook allowances, counts, spacing, weights and totals.
    - Aggregated summary by diameter and BBS rows.

17. **Selection** (`bnbc_foundation/core/selector.py`)
    - Isolated, combined, strip, single-pile, pile-group and global-raft candidates.
    - Shear-wall strip versus pile-cap/raft selection.
    - Site-boundary, kern and adjacent-foundation clash checks.
    - Cost ranking, preferred-type overrides and per-element alternatives.
    - Forced global raft via `raft_trigger` or an element preference.
    - Wall pile caps are laid out along the actual wall length with piles spread
      toward the wall ends, and are width-constrained to clear adjacent column
      footings. Near-feasible groups are retained as CHECK fallbacks when that is
      preferable to a hard geometric clash.

18. **Reports and exports** (`bnbc_foundation/core/report.py`)
    - Excel workbook: Summary, Foundation Schedule, Geotech Checks, Structural Checks,
      Rebar Schedule, BBS, Quantities, Soil Inputs and Code Basis.
    - Landscape PDF report with cover, basis, SPT plot, site plan, schedule, detailed
      checks, rebar/BBS, quantities and warnings.
    - CSV schedule, JSON project save/load, Excel import template and Excel/CSV parsers.
    - Tested export to `samples/` and JSON round-trip (results reload successfully).

19. **PySide6 user interface** (`bnbc_foundation/ui/`)
    - Main window with sidebar navigation, header, status bar, progress bar and menus.
    - Seven pages: Project, Materials, Soil profile, Columns & walls, Options,
      Results and Export.
    - Project JSON open/save, sample loading, new-project flow and confirm-discard.
    - Soil layer table, borehole management, SPT profile plot and Excel/CSV import.
    - Columns/walls table with pre-combined envelopes and a DL/LL/WL/EQ load-case
      editor dialog.
    - Options page for foundation types, geometry, factors of safety, piles, site
      limits, settlement limits and cost rates.
    - Results page with summary cards, schedule table, per-element HTML calculation
      detail, site plan, warnings and alternative listing.
    - Export page for Excel, PDF, CSV, JSON, template and export-all; messages logged.
    - Worker thread keeps the interface responsive during design.

20. **Entry point, validation and packaging notes**
    - `run.py` supports normal launch, `--project <json>` and `--smoke`.
    - Input validation for missing elements/boreholes/layers, duplicate IDs and
      invalid site limits.
    - README with installation, launch, workflow, input conventions, design basis,
      exports, testing and PyInstaller instructions.
    - Optional PyInstaller command documented; Windows build must be produced on
      Windows.

21. **Formal test suite** (`tests/`)
    - Soil stress, SPT correction, bearing capacity and direct overrides.
    - Pressure distribution, kern, flexure, bar selection, shear and punching.
    - Pile capacity, direct overrides and pile-group design.
    - Selection coverage, forced raft and stored results/warnings.
    - JSON round-trip, Excel/PDF/CSV exports, import template and CSV parser.
    - Offscreen PySide6 construction and design-run worker test.
    - Full suite: `26 passed` with `QT_QPA_PLATFORM=offscreen`.

22. **Wall pile-cap geometry refinement**
    - Wall caps now follow the actual wall length instead of placing all piles in
      one long row.
    - Pile columns are spread toward the wall ends so the cap covers the wall
      footprint and develops the in-plane wall moment.
    - Cap width is constrained by adjacent column footings; a near-feasible
      settlement CHECK group can be preferred over a hard overlap.
    - Columns are designed after walls so their foundations account for wall caps.
    - Synthetic sample wall: 6 x 900 mm bored piles, L=20 m, cap 6.20 x 3.65 m,
      inside the site and clear of adjacent footings.

23. **Plan-geometry enhancement**
    - Added `core/geometry.py` with rotated rectangles, circular polygons,
      wall-segment rectangles, bounds, separating-axis overlap, clearance,
      point-in-polygon and site-containment helpers.
    - Extended `Element` with `dx`, `dy`, `shape`, `diameter`, `x1`, `y1`, `x2`
      and `y2`; added centre, footprint, wall-endpoint, wall-length,
      wall-angle and wall-local moment helpers.
    - Column reactions are transformed from the insertion point to the column
      centre with `Mx_c = Mx - P*dy` and `My_c = My - P*dx`.
    - Rectangular columns use `L x W`; circular columns use `diameter` and a
      circular punching perimeter.
    - Walls use centreline endpoints and thickness; legacy centre/length walls
      still work through a fallback.
    - Footing and pile-cap design now use column centres, circular section
      dimensions, wall-local moments, wall endpoint lengths and rotated cap
      angles.
    - Selection, wall width limits, raft layout and plotting use actual footprint
      polygons with a 0.10 m clearance instead of axis-aligned bounding boxes.
    - JSON, Excel/CSV import, the Excel template and the portal-column/wall GUI
      table now carry the geometry fields.
    - Added geometry tests for offsets, circular punching, wall orientation,
      rotated footprint clash/site checks, combined-footing centre coverage and
      JSON/Excel/CSV round-trip.
    - Combined-footing plan sizing now places the centroid at the P-weighted column
      centre, covers every column section plus a 0.30 m projection, and takes the
      transverse steel moment from the width projection.
    - Adjacent foundation footprints within 1.5 m are now checked for differential
      settlement and angular distortion; the soft-clay sample reports three
      differential-settlement warnings in addition to the raft-alternative warning.
    - Updated the synthetic sample with a 0.15 m column offset (C1), circular
      columns (C2, C5), offset rectangular columns (C3, C4, C6) and an angled
      wall with explicit endpoints (W1). Regenerated all `samples/` outputs.

24. **Liquefaction and stability enhancement**
    - Added an optional peak ground acceleration (`pga_g`) to
      `FoundationOptions` and the GUI options page.
    - Added a `LiquefactionResult` model and SPT screening helper that checks
      saturated, non-cohesive layers; FS below 1.0 raises a project warning.
    - Corrected the Youd et al. CRR curve above N60 = 30 so dense sands are not
      incorrectly treated as liquefiable by polynomial extrapolation.
    - Liquefaction results now appear in the Excel Geotech Checks sheet, the PDF
      soil-profile section and the project warnings; a missing PGA is also
      reported when susceptible layers exist.
    - Extended sliding and overturning checks to combined and strip/wall
      footings, with FS 1.5 and the results exported in the geotech tables.
    - Added regression tests for liquefaction triggering, missing-PGA reporting,
      combined-footing stability and strip-footing stability.
    - Regenerated the synthetic sample with PGA = 0.20 g; the 8-16 m silty sand
      reports FS 0.89 and adds a liquefaction warning.

25. **Hand checks and final verification**
    - Fixed combined-footing beam analysis so the net column load, not the gross
      pressure including footing self-weight, drives bending.
    - Replaced sampled beam moments with an exact free-free beam envelope and
      verified `M_pos = 409.5 kN.m` and `M_neg = -57.17 kN.m` for the equal-column
      worked example.
    - Added a closed-form regression test for the combined-footing moment
      envelope.
    - Added a worked four-pile strut-and-tie test: 38.94 degrees, 1272.79 kN
      strut force, 6048 kN strut capacity and 3142.70 mm2 tie steel.
    - Added geometry-limit tests for piles inside the column face and empty caps.
    - Full suite reported 46 passed at that stage; offscreen GUI smoke test was clean.
    - Regenerated `samples/` and verified that Excel and PDF both show the
      liquefaction table and the same 12 warning/review lines.

26. **Future-feature completion**
    - Rectangular columns now accept a counter-clockwise plan `rotation`; rotated
      footprints and projection dimensions drive punching, clash, site and
      plotting checks, and the field round-trips through JSON, Excel/CSV and the
      GUI.
    - Added optional imported convex raft outlines. Rigid pressure uses exact
      polygon area, centroid and second moments; plate elements outside the
      outline are masked. `Auto` selects plate analysis for custom outlines, and
      Winkler strips warn that the outline is approximate.
    - Added ETABS/SAFE reaction CSV import with column matching, compression-
      positive `FZ` sign conversion, factored-case detection, lateral-case
      detection and case-wise merging/replacement.
    - Added CPT pile capacity (`pile_design_method = "CPT"`) with `qc` (MPa) and
      `cpt_fs` (kPa) soil columns and SPT fallback correlations. The synthetic
      sample carries CPT values in its SM and SP layers.
    - Added EC2/BNBC 6.8.9 service crack-width checks to isolated, combined,
      strip, raft and pile-cap designs, with configurable limit (default 0.30 mm)
      and service-moment fallback where only factored raft moments exist.
    - Added shallow-footing buoyancy/uplift checks (hydrostatic plus explicit
      uplift, permanent load and footing/soil weight, FS 1.10; passive resistance
      ignored).
    - Added pile downdrag/negative skin friction, pile uplift capacity
      `(0.70 skin + weight)/FS`, Broms short-pile lateral capacity capped by yield
      moment, and simplified P-M interaction. Group/single-pile results expose
      uplift, lateral and P-M utilizations and OK flags.
    - GUI: rotation column on the loads page, ETABS/SAFE import action, CPT soil
      columns, raft-outline text/CSV import, CPT method option, crack/uplift/
      downdrag/lateral/P-M toggles and factors of safety.
    - Selector pile-group results now expose uplift, lateral, P-M, downdrag and
      cap-crack fields in their check dictionary; a regression assertion covers
      this integration.
    - Added a Supplemental Checks sheet to the Excel workbook and crack/uplift/
      downdrag/lateral/P-M rows to the PDF detailed calculations, so the new
      checks are visible in exports rather than only in result remarks.
    - Added `tests/test_future_features.py` with regression coverage for every
      feature; updated report/GUI tests for the new fields. Full suite now
      reports `65 passed`; `run.py --smoke` exits cleanly.
    - Regenerated all `samples/` outputs. The sample result set is 8 results
      (7 selected plus RAFT-1 as an alternative), all CHECK on the deliberately
      soft clay, with 5 project warnings and 12 warning/review lines.

### Current status

The application is functionally complete: data entry (including ETABS/SAFE
reaction import, CPT data and SI/US display units), plan geometry with column
rotation and arbitrary raft outlines, geotechnical and structural design,
foundation selection, rebar schedule/BBS, all four export formats, the full
PySide6 interface and the 91-test pytest suite are implemented and smoke-tested.
All 17 Ponytail audit fixes are closed. Sample outputs in `samples/` were
regenerated after the audit fixes and unit work. The remaining work is validation
against real project files and Windows packaging.

### Known issues / next checks

- Pile group search prefers the smallest pile count; cost ranking is applied by the
  selector when `optimize_cost` is enabled.
- The synthetic sample is on soft clay: W1 selects a CHECK pile group; C1-C6
  isolated footings and RAFT-1 report CHECK for settlement and/or crack width.
  This is intentional demonstration behaviour, not a constructible final design.
- Downdrag, uplift, Broms lateral capacity and P-M interaction are simplified
  code-level checks; they do not replace project-specific pile testing or
  detailed soil-structure interaction.
- The wall width constraint is evaluated from the bounding boxes of preliminary
  column foundations; final checks use exact footprint polygons.
- Real soil-report and ETABS/SAFE reaction files are not present; the synthetic
  sample is the current validation case.
- No git repository exists, so changes are not committed.

### Next steps

1. Replace the synthetic sample with a real soil report and base-reaction export when
   the user provides them; verify bearing, settlement, pile, CPT and downdrag
   parameters.
2. Validate the ETABS/SAFE importer against real reaction exports and confirm case
   naming/sign conventions for the user's workflow.
3. Build and test the Windows executable on Windows with PyInstaller.
4. Add screenshots or a short user guide if the application is distributed to other
   engineers.

## 2026-11-14 - Ponytail audit fixes and SI/US units (completed)

### Completed

- Closed all 17 verified audit findings: 8 Must fix, 7 Should fix and 2 Nice to
  have. Each functional fix has a regression test in
  `tests/test_regressions.py` (18 tests).
  1. Raft differential now compares millimetres and Winkler strips report a real
     value or an explicit not-checked note.
  2. Pile-cap anchorage uses the selected bar diameter, the minimum available
     development length and sets `CHECK` when short.
  3. Strip and combined footing status includes flexure and bar-selection flags.
  4. Strip and combined flexure use the peak linear pressure rather than the
     average.
  5. Reaction CSV import with `replace=True` clears each element once and keeps
     every load case.
  6. Broms lateral capacity uses the project `f_c` and `f_y`.
  7. Footing, raft punching and pile-cap design use projected column dimensions
     for rotated sections.
  8. Soil Excel/CSV import retains `qc (MPa)` and `CPT fs (kPa)`.
  9. Shallow settlement uses net pressure after overburden subtraction.
  10. Mat steel weight no longer applies the erroneous 0.5 factor.
  11. PDF raft moments read from `design["analysis"]` instead of printing dashes.
  12. Structural Checks computes pile-cap flexure utilization.
  13. PDF and GUI site plans draw rotated column polygons.
  14. Lateral detection recognizes numeric tokens such as `1.2D+1.6W`.
  15. Direct pile end bearing is recognized without a skin value.
  16. Pile results merge group and cap remarks.
  17. Dead code and unused imports removed after a whole-tree reference scan.
- Added SI/US customary interchangeability in `core/units.py`: conversion
  registry, `convert`, `to_si`, `factor`, `label`, `normalize_system`,
  `system_of` and `convert_text` for narrative values.
- Wired units through the Project, Materials, Options, Soil and Loads pages, the
  load-case dialog, reaction CSV import, Excel/CSV/PDF exports, schedule and
  check rows, Results cards/detail and both site plans. Soil/load headers,
  materials and pile/raft labels, cost-rate suffixes and PDF/GUI plan and SPT
  axes follow the selected system. JSON remains SI with `info.units` recording
  the display system.
- Added unit-aware cost rates (`cost_per_volume`, `cost_per_length`,
  `cost_per_mass`, `cost_per_area`) so SI rates are entered per m3/m/kg/m2 and
  US rates per ft3/ft/lb/ft2.
- Added `tests/test_units.py` (8 tests) for registry round-trips, factors,
  labels, narrative conversion, cost rates, US CSV/Excel/PDF headers and values,
  dynamic GUI labels and the offscreen SI/US toggle.
- Updated `.opencode/context.md`, `.opencode/plan.md`, `.opencode/todo.md`,
  `.opencode/ponyfix.md` and `README.md` to the completed state.
- Regenerated `samples/Sample_Residential_Building.{xlsx,pdf,csv,json}` and
  `Sample_Residential_Building_import_template.xlsx`.

### Verification

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` -> 91 passed.
- `.venv/bin/python run.py --smoke` -> exit 0.
- `compileall` passes; an AST scan finds no unused imports.
- Sample result set: W1 pile group plus C1-C6 isolated footings selected, all
  CHECK on the deliberately soft clay; RAFT-1 retained as an alternative; five
  project warnings.
- US CSV spot check: W1 thickness 47 in, pile diameter 47 in, pile length 65.6 ft,
  q max 25.2 ksf, q allow 30.3 ksf, settlement 1.2 in.

### Remaining

- Real soil-report and ETABS/SAFE reaction files are still unavailable; the
  synthetic sample remains the validation case.
- Windows executable packaging must be built on Windows with PyInstaller.
- No git repository exists, so changes are not committed.
