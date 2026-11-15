# Todo

## Environment and scaffold

- [x] Create project folder structure
- [x] Create Python virtual environment with `uv`
- [x] Install PySide6, numpy, pandas, openpyxl, matplotlib, reportlab, pytest
- [x] Add `requirements.txt`
- [x] Add package `__init__.py` files
- [x] Add `run.py` entry point (`--project`, `--smoke`)
- [x] Add `.gitignore`

## Core models and data

- [x] Project, materials, borehole, soil layer and element models
- [x] Service and factored reaction models
- [x] Foundation options model
- [x] Design result model with schedule-row output
- [x] JSON serialization helpers (`project_to_dict`, `project_from_dict`)
- [x] Synthetic sample project
- [x] GUI-friendly validation layer
- [x] Excel/CSV import template and parser
- [x] JSON save/load smoke test

## Plan geometry

- [x] Rotated rectangle, circle and wall-segment footprint helpers
- [x] Column insertion point plus `dx`/`dy` centre offset
- [x] Reaction-to-centre moment transformation
- [x] Rectangular `L x W` and circular diameter sections
- [x] Wall centreline endpoints, angle and legacy centre/length fallback
- [x] Wall-local along-wall and normal moment components
- [x] Geometry-aware isolated, strip, combined and pile-cap design
- [x] Wall pile layout and cap orientation along the wall
- [x] Polygon-based foundation clash and site-boundary checks with 0.10 m clearance
- [x] Geometry-aware PDF and GUI site plans
- [x] Geometry fields in JSON, Excel/CSV import and Excel template
- [x] Geometry tests for offsets, circular punching, wall orientation and rotated footprints
- [x] Arbitrary plan rotation for rectangular columns
- [x] Non-rectangular rafts and imported raft outlines

## Loads

- [x] Normalise DL/LL/WL/EQ/buoyancy cases
- [x] BNBC 3.9.2 service combinations
- [x] BNBC 2.7.3.1 strength combinations
- [x] Governing service/factored reaction helpers
- [x] Load-case GUI table (pre-combined or DL/LL/WL/EQ)
- [x] Load import from ETABS/SAFE CSV

## Soil and geotechnical

- [x] Layer interpolation
- [x] Groundwater-aware total/effective stress
- [x] SPT overburden correction and N60
- [x] Phi, cu, Es and subgrade modulus correlations
- [x] Meyerhof bearing capacity with shape/depth factors
- [x] Direct allowable bearing capacity override
- [x] Presumptive bearing values
- [x] Simplified SPT liquefaction FS
- [x] CPT-based capacity option
- [x] Soil profile plot widget

## Shallow foundations

- [x] Biaxial pressure distribution and kern check
- [x] Required area and practical isolated-footing sizing
- [x] Combined-footing plan sizing
- [x] Service combination pressure check with 33% lateral overstress
- [x] Sliding and overturning checks
- [x] Sliding/overturning checks for combined and strip/wall footings
- [x] Immediate, consolidation and secondary settlement
- [x] Differential and angular distortion helpers
- [x] Adjacent-foundation differential settlement and angular distortion checks
- [x] Isolated footing structural design
- [x] Strip/wall footing structural design
- [x] Combined footing structural design
- [x] Exact combined-footing beam moment envelope
- [x] Top/bottom reinforcement optimisation for combined footings
- [x] Crack-width check for isolated, combined, strip, raft and pile-cap designs
- [x] Buoyancy/uplift check for shallow footings

## Deep foundations

- [x] Driven pile SPT capacity (clay and sand)
- [x] Bored pile SPT capacity (clay and sand)
- [x] Static alpha/beta capacity
- [x] Direct pile capacity override
- [x] Critical depth and pile weight
- [x] Pile structural axial capacity
- [x] Single-pile selection
- [x] Pile group layout and spacing
- [x] Group efficiency and block capacity
- [x] Group settlement estimate
- [x] Pile cap structural design
- [x] Pile-cap strut-and-tie check verified against a worked example
- [x] Wall pile layout constrained to the wall length and adjacent footings
- [x] Near-feasible pile-group fallback for clash avoidance
- [x] Downdrag / negative skin friction
- [x] Pile uplift capacity
- [x] Lateral pile capacity (Broms)
- [x] P-M interaction for piles

## Raft

- [x] Rigid raft contact pressure
- [x] Beam-on-elastic-foundation (Winkler) strip solver
- [x] Auto-select plate for custom/large outlines and Winkler strips otherwise
- [x] Kirchhoff plate on Winkler springs with masked elements outside imported outlines
- [x] Raft structural design (top/bottom steel, shear, punching)
- [x] Raft buoyancy and settlement checks
- [x] Non-rectangular/imported raft outlines with exact polygon pressure and masked plate elements
- [x] Raft crack-width check

## Selection and results

- [x] Isolated -> combined -> raft -> single pile -> group selection
- [x] Shear-wall strip/pile-cap/raft auto-selection
- [x] Site boundary and adjacent-footing clash checks
- [x] Cost ranking
- [x] Per-element alternative reporting
- [x] Project-level raft trigger

## Reports and exports

- [x] Excel foundation schedule
- [x] Excel detailed geotech/structural sheets
- [x] SPT liquefaction table in Excel and PDF
- [x] Project and element warning lines in Excel and PDF
- [x] Excel rebar schedule and BBS
- [x] Quantity summary
- [x] PDF report
- [x] CSV schedule
- [x] Excel import template
- [x] JSON save/load UI

## GUI

- [x] PySide6 main window and sidebar navigation
- [x] Project page
- [x] Materials page
- [x] Soil page with layer table
- [x] Loads page with columns/walls table, geometry columns and load-case dialog
- [x] Options page
- [x] Results page with schedule and calculation-detail panel
- [x] Site-plan and SPT plots
- [x] Worker thread for design run
- [x] Validation and warning messages
- [x] Export page with output-folder selection
- [x] Menu: new/open/save/sample/run
- [x] JSON project open/save and Excel/CSV element/soil import
- [x] Application stylesheet and summary cards

## Testing and documentation

- [x] Unit tests for SPT correction and soil stress
- [x] Unit tests for bearing capacity and direct overrides
- [x] Unit tests for pressure/eccentricity and kern
- [x] Unit tests for pile capacity and pile groups
- [x] Unit tests for flexure/shear/punching and bar selection
- [x] Unit tests for selection logic, raft trigger and coverage
- [x] Unit tests for column offsets, circular sections/punching and wall orientation
- [x] Unit tests for rotated footprint clash and site containment
- [x] Unit tests for liquefaction triggering and missing-PGA reporting
- [x] Unit tests for combined/strip footing stability
- [x] Unit tests for column rotation, CPT capacity and CPT fallbacks
- [x] Unit tests for crack width, shallow uplift and explicit buoyancy
- [x] Unit tests for downdrag, pile uplift and Broms lateral capacity
- [x] Unit tests for pile P-M interaction
- [x] Unit tests for polygon pressure and non-rectangular raft outlines
- [x] Unit tests for ETABS/SAFE reaction import (sign, cases and merging)
- [x] Closed-form test for the combined-footing beam moment envelope
- [x] Worked-example test for pile-cap strut-and-tie capacity
- [x] JSON round-trip test including geometry fields
- [x] Excel/PDF/CSV export smoke tests and import parsers
- [x] Excel import template with rectangular, circular and wall examples
- [x] Qt offscreen GUI construction and design-run tests
- [x] Full pytest suite (91 passed)
- [x] Supplemental check sheet in Excel and per-element PDF check details
- [x] README and user guide
- [x] PyInstaller packaging notes
- [x] Final sample exports in `samples/`

## Ponytail audit fixes (2026-11-14, completed)

Detailed instructions, file references and tests are in `.opencode/ponyfix.md`.
Every item is fixed and covered by a regression test; the full suite is green.

### Must fix

- [x] Fix 1: raft differential unit conversion and strip differential value
- [x] Fix 2: pile-cap anchorage - selected bar diameter, minimum available length, CHECK status
- [x] Fix 3: strip/combined status - include flexure and bar `ok` flags and notes
- [x] Fix 4: strip/combined flexure - use peak pressure or integrate the linear pressure
- [x] Fix 5: reaction CSV `replace=True` - clear once per element and keep all cases
- [x] Fix 6: Broms lateral capacity - pass `f_c`/`f_y`, remove hardcoded 30/420
- [x] Fix 7: column rotation - projected section dimensions in footing, raft punching and pile cap
- [x] Fix 8: soil CPT import - parse `qc (MPa)` and `CPT fs (kPa)` in Excel/CSV

### Should fix

- [x] Fix 9: shallow settlement - use net pressure after overburden subtraction
- [x] Fix 10: mat steel weight - remove the 0.5 factor
- [x] Fix 11: PDF raft moments - read from `design["analysis"]`
- [x] Fix 12: Structural Checks - compute pile-cap flexure utilization
- [x] Fix 13: site plan - draw rotated column polygons, not axis-aligned rectangles
- [x] Fix 14: lateral detection - handle numeric tokens such as `1.2D+1.6W`
- [x] Fix 15: direct pile end bearing - recognize `pile_end` without a skin value

### Nice to have

- [x] Fix 16: pile result remarks - merge group and cap remarks
- [x] Fix 17: remove dead code and unused imports (~180 lines, no dependency changes)

### Verification

- [x] Add regression tests for fixes 1-16; fix 17 is verified by grep and the existing suite
- [x] Run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` (91 passed)
- [x] Run `.venv/bin/python run.py --smoke` (exit 0)
- [x] Regenerate `samples/`
- [x] Update `context.md`, `plan.md`, `progression.md`, `README.md` and mark the finished items

## SI/US unit interchangeability (2026-11-14, completed)

- [x] Conversion registry keyed by quantity in `core/units.py`
- [x] `convert`, `to_si`, `factor`, `label`, `normalize_system`, `system_of`
- [x] `convert_text` for SI values embedded in requirement/size/remarks narratives
- [x] Project page SI/US selector and live reload of every input page
- [x] Unit-aware Materials, Options, Soil and Loads pages and load-case dialog
- [x] Unit-aware reaction CSV import
- [x] Unit-aware Excel, CSV and PDF headers and values
- [x] Unit-aware schedule, geotech, structural, supplemental, quantity, soil and liquefaction rows
- [x] Unit-aware Results cards, calculation detail and site plan
- [x] Unit-aware cost rates: per m3/m/kg/m2 in SI, per ft3/ft/lb/ft2 in US
- [x] Dynamic soil/load table headers, materials/pile/raft labels, cost suffixes and PDF/GUI plan and SPT axes
- [x] JSON storage remains SI with `info.units` recording the display system
- [x] `tests/test_units.py` conversion, export, cost-rate, dynamic-label and offscreen GUI-toggle tests
