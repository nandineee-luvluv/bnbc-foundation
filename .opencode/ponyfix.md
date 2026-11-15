# Ponytail Fix Plan

Source: Ponytail whole-build audit, 2026-11-14.

Baseline before fixes: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` -> `65 passed`; `.venv/bin/python run.py --smoke` exits 0. Final after fixes and the unit system: `91 passed`; smoke exits 0.

Scope: verified audit findings only. Add one regression test per item. Keep the existing GUI, Excel/PDF/CSV/JSON exports, rebar schedule/BBS and sample outputs working. Calculations and stored values remain SI (kN, kPa, kN.m, m, mm); the GUI, importers, exporters and reports convert to and from US customary units as the user selects. No new dependencies.

Tracking: `.opencode/todo.md` has the completed work items; `.opencode/plan.md` section 11 has the delivered fixes and verification.

Priority: **8 Must fix, 7 Should fix, 2 Nice to have.**

## Must fix

- [x] **1. Raft differential check uses metres against a millimetre limit** (`bnbc_foundation/core/raft.py:626,724,824-829`)
  - **Problem:** `analysis.differential` is in metres (0.0276 m in the sample) but `options.differential_limit` is in millimetres (10-20 mm). `_winkler_strips` never sets `analysis.differential`, so it stays 0 and always passes.
  - **Fix:** Compute `diff_mm = analysis.differential * 1000.0` once and compare that. For strips, set the value from the computed deflections or add an explicit "not checked" note; never leave 0 as a pass.
  - **Test:** Set `differential_limit` below the plate result and assert `CHECK` plus the note. Run a strip analysis and assert the result is either checked or explicitly noted as not checked.

- [x] **2. Pile-cap anchorage check is wrong and does not affect status** (`bnbc_foundation/core/structural/pilecap.py:234,344-355`)
  - **Problem:** `db_main` is fixed at 20 mm, `development_available` uses `max` of the two directions, and a failure only adds a note. Sample W1 has 1394 mm required vs 519 mm available with `status="OK"`.
  - **Fix:** Use the selected bar diameter for each direction, take the `min` available length, and set `status="CHECK"` plus a remark when any direction is short. For a conservative single check, use the largest selected `db` and the smallest available length.
  - **Test:** Heavy cap with 25 mm bars and one short direction; assert `CHECK` and the note. Keep W1 as a regression.

- [x] **3. Strip and combined footing status ignores failed flexure** (`bnbc_foundation/core/structural/footing.py:450-484,609-661`)
  - **Problem:** The status expressions in `design_strip` and `design_combined` omit `fx.ok`, `fy.ok` and the bar `ok` flags. A forced flexure failure still returns `status="OK"` with empty remarks.
  - **Fix:** Add all flexure and bar flags to the status test and append their notes. Keep bearing, settlement, stability, crack and uplift as they are.
  - **Test:** Mock `flexural_design` to return `FlexureResult(ok=False)`; assert `CHECK` and a non-empty remark for strip and combined, with crack check on and off.

- [x] **4. Strip and combined flexure use uniform pressure and miss the peak moment** (`bnbc_foundation/core/structural/footing.py:450-452,590-596`)
  - **Problem:** `design_strip` uses `q_u = P_u / B` and `design_combined` uses `q_beam = column_load_u / (L*B)`, so both ignore the moment-induced pressure peak. The 4.2 m strip example uses 90 kN.m/m where the peak pressure gives 155 kN.m/m (1.72x low).
  - **Fix:** Use `q_max` for cantilever moments, or integrate the linear pressure over the projection. For the combined beam, include the global moment as an equivalent linear line load, or conservatively use `q_max * B`.
  - **Test:** High-eccentricity strip and combined cases; assert the design moment is based on the peak pressure, not the average.

- [x] **5. Reaction CSV import with `replace=True` drops all but the last load case** (`bnbc_foundation/core/report.py:968-973`)
  - **Problem:** `replace=True` assigns `element.reactions = [reaction]` inside the row loop. A DL+LL file for C1 leaves only LL; the import report still lists both cases.
  - **Fix:** Clear each matched element's reactions once, before appending rows. Track cleared element IDs in a set.
  - **Test:** Two-case CSV with `replace=True`; assert both reactions survive and the report cases match.

- [x] **6. Broms lateral capacity hardcodes 420 MPa steel** (`bnbc_foundation/core/piles.py:233-239,286`)
  - **Problem:** `broms_lateral_capacity` calls `_pile_section_properties(diameter, 30.0, 420.0)`, ignoring the user's `f_y` and `f_c`. For a 0.6 m x 20 m pile with `f_y=250 MPa`, it reports 20.1 kN instead of 11.9 kN.
  - **Fix:** Add `f_c` and `f_y` parameters to `broms_lateral_capacity`, pass them from `compute_pile_capacity`, and use them in the section properties. Keep 30/420 as defaults for callers that do not supply values.
  - **Test:** Compare 250 MPa and 420 MPa for the same pile; assert the 250 MPa capacity is lower and matches the section calculation.

- [x] **7. Structural design ignores column rotation** (`bnbc_foundation/core/structural/footing.py:240-251,599-607; bnbc_foundation/core/raft.py:777-785; bnbc_foundation/core/structural/pilecap.py:228-232`)
  - **Problem:** Footing, raft punching and pile-cap design use `section_length` and `section_width` and ignore `rotation`. A 0 degree and 90 degree column give the same moments and bars even though `section_projection_x/y` swap.
  - **Fix:** Use `section_projection_x/y` (bounding-box projection) for critical sections and cantilever projections in `design_isolated`, `design_combined`, raft punching and `design_pilecap`. For arbitrary angles the bounding box is conservative.
  - **Test:** 0 degree vs 90 degree rectangular column; assert the projections swap and the design moments/bars follow the projected dimensions. Add a 45 degree case if cheap.

- [x] **8. Soil Excel/CSV import silently drops CPT data** (`bnbc_foundation/core/report.py:652-661,1005-1031`)
  - **Problem:** `SOIL_HEADERS` includes `qc (MPa)` and `CPT fs (kPa)`, but `import_soil_excel` does not read them; `import_soil_csv` delegates to the Excel importer. A template round-trip gives 0.0/0.0 instead of 2.0/35.0.
  - **Fix:** Add `qc=` and `cpt_fs=` lookups to the `SoilLayer(...)` constructor. One parser change covers both Excel and CSV.
  - **Test:** Export the template, import it, assert `layer.qc == 2.0` and `layer.cpt_fs == 35.0`; repeat through `import_soil_csv`.

## Should fix

- [x] **9. Shallow settlement uses gross pressure and creates false CHECKs** (`bnbc_foundation/core/structural/footing.py:144-151,286-289,471-473,649`)
  - **Problem:** Settlement is driven by `q_net`, but the isolated path passes `P/A + gamma_concrete*t` and the combined path passes gross pressure; neither subtracts the soil overburden. A 2.0 x 2.0 x 0.6 m footing with P=400 kN gives 114.4 kPa -> 26.0 mm (CHECK) instead of 100 kPa -> 22.8 mm (OK).
  - **Fix:** Pass `q_net = (P + gamma_concrete*t*A)/A - sigma_v(depth)` (or the simpler `P/A - sigma_v(depth)`) using `vertical_stress` at the base. Keep the gross pressure for bearing only.
  - **Test:** Case where gross fails and net passes; assert `OK` and settlement near 22.8 mm. Add a combined-footing case.

- [x] **10. Steel weight for mats is half the real value** (`bnbc_foundation/core/structural/footing.py:394-407`)
  - **Problem:** `_mat_steel_weight` multiplies every layout by 0.5. A 2 x 2 m mat with four 1005 mm2/m layouts gives 63.1 kg instead of 126.2 kg.
  - **Fix:** Remove the 0.5 factor and the misleading comment. Each layout already covers the full mat area.
  - **Test:** Assert the 2 x 2 example is 126.2 kg within rounding, and update any sample quantities.

- [x] **11. PDF raft calculations print dashes for all moments** (`bnbc_foundation/core/report.py:1417-1422`)
  - **Problem:** The PDF reads `d["moment_x_pos"]` and the other three keys at the top level, but raft design stores them under `d["analysis"]`; all four print `-`. Sample values are 97.6 and 529.7 kN.m/m.
  - **Fix:** Use `analysis = d.get("analysis", {})` and fall back to it for the four moment keys. Keep the top-level keys for other foundation types.
  - **Test:** Export a PDF with a raft selected, extract text with `pdftotext`, assert the moment values appear and are not `-`.

- [x] **12. Structural Checks sheet always shows zero pile-cap flexure** (`bnbc_foundation/core/report.py:164-173`)
  - **Problem:** `structural_rows` sets `flexure` only for rafts. The pile-cap branch leaves it at 0.0, so a cap with `Mu_x=2353.9 kN.m/m` exports `0.000`.
  - **Fix:** In the pile-cap branch, compute `flexure = max(Mu_x / flex_x.phi_Mn, Mu_y / flex_y.phi_Mn)` from `d["details"]`, or store `flexure_utilization` in `PileCapDesign` and read it here.
  - **Test:** Run the sample with pile groups selected; assert the W1/C2 structural row has flexure > 0 and matches the cap details.

- [x] **13. Site plan draws rotated columns as axis-aligned rectangles** (`bnbc_foundation/core/report.py:1156-1160; bnbc_foundation/ui/pages/results_page.py:221-225`)
  - **Problem:** The site plan uses `Rectangle` from axis-aligned bounds and ignores `rotation`. A 30 degree or 90 degree column is drawn unrotated.
  - **Fix:** Build a `Polygon` from `element.footprint_polygon` (or the rotated rectangle points) in both the PDF and the GUI site plan. Reuse one helper so the two drawings cannot drift.
  - **Test:** Unit-test the plan-shape helper: a 90 degree 0.6 x 0.3 column returns a polygon with swapped x/y extents.

- [x] **14. Lateral-load detection misses combinations with numeric factors** (`bnbc_foundation/core/report.py:896-903`)
  - **Problem:** `_reaction_includes_lateral` only matches whole tokens (`W`, `EQ`). `1.2D+1.6W` and `1.0E` are not detected, so the 33% allowable-bearing increase is skipped.
  - **Fix:** Strip leading numeric coefficients from each token before matching, e.g. `re.sub(r"^[0-9.]+", "", t)`, then keep the existing word and prefix checks.
  - **Test:** Assert true for `1.2D+1.6W`, `1.0E` and `0.9D+1.6W`, and false for `1.4D` and `1.2D+1.6L`.

- [x] **15. Direct end-bearing values are ignored when no skin value is given** (`bnbc_foundation/core/piles.py:458-462`)
  - **Problem:** `_has_direct_pile` only checks skin values. `SoilLayer(pile_end=500)` returns false, so the direct end-bearing value is ignored and an SPT/CPT correlation is used.
  - **Fix:** Return true when either the skin or the end value is present for the selected pile type; `_direct_skin_end` already falls back to SPT for the missing side.
  - **Test:** `_has_direct_pile(SoilLayer(pile_end=500), "Bored") is True`; compute capacity and assert the direct end value changes the result.

## Nice to have

- [x] **16. Pile results show only the cap remarks** (`bnbc_foundation/core/selector.py:556,631`)
  - **Problem:** `selector.py` sets `remarks=cap.remarks` for single piles and groups, so group settlement, uplift, lateral and P-M notes are lost. W1 is CHECK for 31.0 mm > 25 mm group settlement, but its remarks only mention development length.
  - **Fix:** Join group remarks and cap remarks, deduplicated, when building the `DesignResult`. Keep the cap remark for detailing.
  - **Test:** W1 result remarks contain both the settlement reason and the development-length reason.

- [x] **17. About 180 lines of dead code and 32 unused imports** (`bnbc_foundation/core/bearing.py`, `report.py`, `selector.py`, `units.py`, `ui/main_window.py`, and others)
  - **Problem:** A whole-tree grep finds 18 unused top-level functions and about 32 unused import names. Examples: `service_pressure_candidates`, `merge_imported_data`, `_site_ok`, `_overlap`, `steel_weight_kg`, `floor_to`, `round_to`, `mm_to_m`, `m_to_mm`, `kpa_to_ksf`, `launch`.
  - **Fix:** Delete them after one more whole-tree grep, including tests and dynamic references. Do not remove dependencies.
  - **Test:** Grep shows no references; full suite and `run.py --smoke` pass.

## Verification

- [x] Full suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
- [x] Smoke: `.venv/bin/python run.py --smoke`
- [x] Regenerate `samples/Sample_Residential_Building.{xlsx,pdf,csv,json}` and `samples/Sample_Residential_Building_import_template.xlsx`
- [x] Update `README.md`, `.opencode/context.md`, `.opencode/plan.md`, `.opencode/progression.md`, `.opencode/todo.md`
- [x] Confirm no unchecked or Future items remain in `.opencode/todo.md`

## SI/US unit system (completed alongside the fixes)

- [x] `core/units.py` registry covers length, thickness, force, moment, moment per length, pressure, stress, unit weight, subgrade modulus, settlement, area, volume, mass, angle, ratio, currency and cost rates.
- [x] Internal calculations and JSON numeric values remain SI; GUI inputs, importers, exports and reports convert at their boundary.
- [x] Project page SI/US selector reloads Materials, Options, Soil, Loads, Results and export views.
- [x] Soil/load table headers, materials/pile/raft labels, cost suffixes, Results cards and PDF/GUI plan and SPT axes follow the display system.
- [x] Cost rates convert with `cost_per_volume`, `cost_per_length`, `cost_per_mass` and `cost_per_area`.
- [x] JSON records the display system in `info.units` without changing stored SI values.
- [x] `tests/test_units.py` (8 tests) covers round-trips, factors, labels, narrative conversion, cost rates, US CSV/Excel/PDF output, dynamic GUI labels and the offscreen SI/US toggle.

## Out of scope / blocked

- Real soil-report and ETABS/SAFE reaction files are unavailable; synthetic samples remain the validation case.
- Windows executable packaging must be built on Windows with PyInstaller.
- A full BNBC equation-by-equation review is not part of this fix pass.
- GUI dialogs are only covered by the offscreen smoke test.
