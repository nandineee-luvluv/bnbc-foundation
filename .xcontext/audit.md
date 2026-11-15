# Ponytail Audit Fixes

[Back to map](MAP.md) · Related: [context.md](context.md) · [verification.md](verification.md) · [`.opencode/ponyfix.md`](../.opencode/ponyfix.md)

The whole-build audit on **2026-11-14** confirmed 17 issues that the original
65-test suite did not catch: **8 Must fix, 7 Should fix and 2 Nice to have**.
All 17 are fixed. `tests/test_regressions.py` contains 17 test functions and
18 collected cases (one crack-width test is parametrized).

## Must fix

1. **Raft differential unit mismatch** — `analysis.differential` is in metres
   but the limit is in millimetres; Winkler strips never set the value. Fixed by
   comparing `differential * 1000.0` and reporting a real value or an explicit
   not-checked note.
   Test: `test_raft_differential_uses_millimetres_and_rigid_is_not_checked`.
2. **Pile-cap anchorage status** — development length ignored the selected bar
   diameter and minimum available length. Fixed with selected `db`, available
   length and `CHECK` when short.
   Test: `test_pile_cap_anchorage_uses_selected_bars_and_controls_status`.
3. **Strip/combined status** — flexure and bar-selection failures were omitted.
   Fixed by including both `ok` flags and remarks in the status.
   Test: `test_strip_and_combined_status_include_flexure_failure`.
4. **Strip/combined flexure pressure** — design used average pressure. Fixed to
   use the peak linear pressure for cantilever and beam moments.
   Test: `test_strip_flexure_uses_peak_pressure` and
   `test_combined_beam_includes_global_moment_in_the_line_load`.
5. **Reaction CSV `replace=True`** — clearing per load case deleted earlier
   cases. Fixed to clear each element once and keep every case.
   Test: `test_reaction_csv_replace_keeps_all_load_cases`.
6. **Broms lateral capacity steel grades** — hardcoded 30/420 MPa. Fixed to pass
   the project `f_c` and `f_y`.
   Test: `test_broms_lateral_capacity_uses_requested_steel_strength`.
7. **Rotated column projections** — footing, raft punching and pile-cap design
   used unrotated dimensions. Fixed to use projected section dimensions.
   Test: `test_rotated_column_projection_changes_footing_design`.
8. **CPT soil import** — `qc (MPa)` and `CPT fs (kPa)` were dropped. Fixed in
   Excel/CSV import and retained on the layer model.
   Test: `test_soil_import_reads_qc_and_cpt_sleeve_friction`.

## Should fix

9. **Shallow settlement net pressure** — settlement used gross pressure. Fixed to
   subtract overburden and use net pressure.
   Test: `test_shallow_settlement_uses_net_pressure`.
10. **Mat steel weight** — an erroneous 0.5 factor halved the weight. Removed.
    Test: `test_mat_steel_weight_counts_each_layout_once`.
11. **PDF raft moments** — values were read from the wrong dictionary and printed
    dashes. Fixed to read `design["analysis"]`.
    Test: `test_pdf_raft_moments_use_analysis_values`.
12. **Pile-cap flexure utilization** — Structural Checks omitted it. Computed and
    exported.
    Test: `test_structural_rows_report_pile_cap_flexure`.
13. **Rotated site plan** — PDF/GUI plans drew axis-aligned rectangles. Fixed to
    draw footprint polygons.
    Test: `test_plan_shape_draws_rotated_column_as_a_polygon`.
14. **Lateral token detection** — `1.2D+1.6W` was not recognized. Fixed by
    stripping numeric coefficients before matching.
    Test: `test_lateral_detection_strips_numeric_coefficients`.
15. **Direct pile end bearing** — a direct end value without skin was ignored.
    Fixed to recognize either direct component.
    Test: `test_direct_end_bearing_is_recognised_without_skin_value`.

## Nice to have

16. **Pile result remarks** — only cap remarks were retained. Fixed to merge and
    deduplicate group and cap notes.
    Test: `test_pile_result_remarks_merge_group_and_cap_notes`.
17. **Dead code and unused imports** — removed after a whole-tree reference scan
    (~180 lines, 32 imports). No dependency changes. Verified by grep, AST scan,
    full suite and smoke test.

## Verification

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` → **91 passed**.
- `.venv/bin/python run.py --smoke` → exit `0`.
- `compileall` passes; AST scan finds no unused imports.
- Samples regenerated; all selected foundations report `CHECK` on the deliberately
  soft demonstration clay, and RAFT-1 remains an alternative.

## Related records

- [verification.md](verification.md) — full evidence.
- [worklog.md](worklog.md) — when the audit and fixes happened.
- [`.opencode/ponyfix.md`](../.opencode/ponyfix.md) — original problem/fix/test detail.
