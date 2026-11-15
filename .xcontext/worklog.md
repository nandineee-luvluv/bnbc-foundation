# Work Log

[Back to map](MAP.md) · Related: [timeline.json](timeline.json) · [audit.md](audit.md) · [repository.md](repository.md) · [backup.md](backup.md) · [`.opencode/progression.md`](../.opencode/progression.md)

## 2026-11-13 — Build foundation

- Created the Python package, PySide6 shell, data models, JSON serialization and
  synthetic sample project.
- Added plan geometry (rotated rectangles, circular sections, wall segments),
  inserted-point offsets and reaction-to-centre moment transfer.
- Implemented loads, soil/SPT/bearing/settlement, pile capacity, raft analysis,
  structural concrete checks, rebar schedule/BBS, foundation selection and
  Excel/PDF/CSV/JSON/import-template exports.
- Added the seven GUI pages, worker thread, offscreen smoke test and initial test
  suite.

## 2026-11-13 to 2026-11-14 — Feature completion

- Added ETABS/SAFE reaction import, CPT data, arbitrary convex raft outlines,
  combined-footing beam checks, pile-cap strut-and-tie, crack width, uplift,
  downdrag, pile uplift, Broms lateral capacity and P-M interaction.
- Extended the sample with column offsets, circular columns, rotation and an
  angled shear wall.
- Regenerated sample outputs and updated user documentation.

## 2026-11-14 — Ponytail audit and fixes

- Ran a whole-build audit and confirmed 17 issues: 8 Must fix, 7 Should fix and
  2 Nice to have. Recorded them in `.opencode/ponyfix.md`.
- Fixed all 17:
  - raft differential units and Winkler-strip reporting
  - pile-cap anchorage and flexure utilization
  - strip/combined status and peak-pressure flexure
  - reaction CSV replacement semantics
  - Broms project material strengths
  - rotated-column projections
  - CPT soil import
  - net-pressure settlement
  - mat steel weight
  - PDF raft moments
  - rotated site-plan polygons
  - numeric lateral tokens
  - direct end bearing without skin
  - merged pile remarks
  - dead code/unused imports
- Added `tests/test_regressions.py`: 17 functions, 18 cases.
- Added SI/US customary interchangeability in `core/units.py`, wired through the
  GUI, importers, exports and reports, with `tests/test_units.py` (8 cases).
- Updated `README.md`, `.opencode/{context,plan,todo,progression,ponyfix}.md`,
  regenerated `samples/`, and confirmed **91 passed** plus smoke exit `0`.

## 2026-11-15 — Verification and publication

- Completed the final documentation consistency pass, including cost-rate units,
  dynamic GUI labels and JSON `info.units` semantics.
- Re-ran the full suite (**91 passed**), smoke (`0`), `compileall` and the
  unused-import AST scan.
- Regenerated all five sample outputs: 8 results, 7 selected, all `CHECK` on the
  soft demonstration clay; RAFT-1 alternative; 5 warnings and 12 report lines.
- Verified the US export: `kip`, `ksf`, `ft`, `in`, `kip.ft`,
  `Concrete (ft3)`, `Steel (lb)`; no SI headers; W1 CSV spot values as expected.
- Created the public GitHub repository
  https://github.com/nandineee-luvluv/bnbc-foundation with the MIT license,
  topics and the initial commit `073dbb9`.
- Added `.zipignore` and archive rules to `.gitignore`; committed as `8c419db`.
- Created the local zip backup, initially in a sibling `backups/` folder, then
  removed that copy and recreated the archive inside the project root as
  requested.
- Verified the pre-context archive in a clean extraction: clean git status,
  smoke `0`, full suite **91 passed**, sample checksums matched.
- Added `.xcontext/` as the durable next-session context and map.

## Detailed history

The full chronological build log, with all feature phases and verification
details, is in [`.opencode/progression.md`](../.opencode/progression.md).
The audit instructions are in
[`.opencode/ponyfix.md`](../.opencode/ponyfix.md).
