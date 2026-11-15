# Verification Record

[Back to map](MAP.md) · Related: [audit.md](audit.md) · [units.md](units.md) · [backup.md](backup.md) · [state.json](state.json)

## Full suite

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
```

Result at the latest verification: **91 passed**.

Test inventory:

| File | Cases |
|---|---:|
| `tests/test_bearing_concrete.py` | 6 |
| `tests/test_future_features.py` | 19 |
| `tests/test_geometry.py` | 12 |
| `tests/test_gui.py` | 3 |
| `tests/test_piles.py` | 5 |
| `tests/test_regressions.py` | 18 (17 functions; crack-width case parametrized) |
| `tests/test_report.py` | 8 |
| `tests/test_selection.py` | 6 |
| `tests/test_soil.py` | 6 |
| `tests/test_units.py` | 8 |
| **Total** | **91** |

## Smoke, compile and static checks

```bash
.venv/bin/python run.py --smoke          # exit 0
.venv/bin/python -m compileall -q bnbc_foundation tests
```

An AST scan over `bnbc_foundation/**/*.py` found **no unused imports**. The scan
checks every imported name against loaded `ast.Name` nodes and skips
`__future__` imports.

## Sample project

The synthetic sample is deliberately founded on soft clay. Current output:

- **8 results:** W1 pile group plus C1–C6 isolated footings selected (7);
  RAFT-1 retained as an alternative.
- **Status:** all selected foundations report `CHECK`; this is intentional
  demonstration behaviour, not a constructible final design.
- **Warnings:** 5 project warnings; 12 report warning/review lines.
- **Files:** `samples/Sample_Residential_Building.{xlsx,pdf,csv,json}` and
  `samples/Sample_Residential_Building_import_template.xlsx`.

## US customary export check

A US-unit export was generated and inspected independently of the SI sample:

- PDF contains `kip`, `ksf`, `ft`, `in`, `kip.ft`, `Concrete (ft3)` and
  `Steel (lb)`.
- SI headers `kPa` and `kN.m/m` are absent.
- W1 CSV spot check: thickness `47 in`, pile diameter `47 in`, pile length
  `65.6 ft`, `q max` `25.2 ksf`, `q allow` `30.3 ksf`, settlement `1.2 in`.
- JSON `info.units` is `US` in the US export, while numeric engineering values
  remain SI.

## Backup restore check

The pre-`.xcontext` archive (153 entries, 718,312 bytes, SHA-256
`57c74d1f43d9bae829e9233ae286a6a20966ad1c4e7634347933dd8ef382059b`) was
extracted into a clean directory and checked:

- `git status` clean at commit `8c419db`.
- `run.py --smoke` → exit `0`.
- Full suite → **91 passed**.
- All five sample files matched the originals byte-for-byte.

After `.xcontext` was added the archive is regenerated, so its size and checksum
change. Re-run the restore check and compute the current hash with:

```bash
sha256sum bnbc-foundation-backup-2026-11-15.zip
```

## Caveats

- Tests and samples use synthetic data. Real soil-report and ETABS/SAFE files
  remain unavailable.
- GUI dialogs are covered by the offscreen smoke test, not interactive testing.
- The Windows executable has not been built; PyInstaller packaging must run on
  Windows.
