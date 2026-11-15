# SI / US Customary Units

[Back to map](MAP.md) · Related: [context.md](context.md) · [architecture.md](architecture.md) · [verification.md](verification.md)

## Core rule

The calculation engine and every stored numeric value are **SI**. Conversion
happens only at the boundaries:

```text
GUI input  ──to_si──►  SI Project model  ──convert──►  GUI output
import     ──to_si──►  SI Project model  ──convert──►  Excel/CSV/PDF
JSON load  ──SI────►   SI Project model  ──convert──►  reports
JSON save  ◄──SI────   SI Project model      info.units = display system
```

`info.units` records `SI` or `US` for the display view only. It never changes
the numeric values stored in JSON.

## Conversion registry

`bnbc_foundation/core/units.py` provides:

- `convert(value, quantity, system)` — SI → selected display units.
- `to_si(value, quantity, system)` — selected display units → SI.
- `factor(quantity, system)` — SI → display multiplier.
- `label(quantity, system)` — unit label.
- `normalize_system(system)` / `system_of(project)`.
- `convert_text(text, system)` — converts SI unit tokens embedded in generated
  requirement/size/remarks narratives.

| Quantity | SI | US customary |
|---|---|---|
| Length | m | ft |
| Thickness, pile diameter, bar size | mm | in |
| Force | kN | kip |
| Moment | kN.m | kip.ft |
| Moment per unit length | kN.m/m | kip.ft/ft |
| Pressure / bearing | kPa | ksf |
| Stress | MPa | ksi |
| Unit weight | kN/m3 | pcf |
| Subgrade modulus | kN/m3 | kcf |
| Settlement | mm | in |
| Area | m2 | ft2 |
| Volume | m3 | ft3 |
| Mass | kg | lb |
| Cost per volume | per m3 | per ft3 |
| Cost per length | per m | per ft |
| Cost per mass | per kg | per lb |
| Cost per area | per m2 | per ft2 |

Angle, ratio and currency are identity conversions.

## Where conversion is applied

- **GUI:** `set_spin`, `get_spin`, `dspin` seed SI bounds and convert display
  values. The Project page selector reloads Materials, Options, Soil, Loads,
  Results and Export.
- **Dynamic labels:** soil/load table headers, materials bar diameter, pile
  diameters/lengths, raft outline, cost-rate suffixes, Results cards, calculation
  detail, PDF/GUI site-plan axes and SPT depth axes.
- **Imports:** Excel/CSV reaction, soil and element imports convert to SI.
- **Exports:** Excel/CSV/PDF headers, schedule values, quantities, soil/CPT/
  liquefaction rows and narrative text use the display system. JSON stays SI.
- **Cost rates:** `cost_per_volume`, `cost_per_length`, `cost_per_mass` and
  `cost_per_area` keep the engine rate in SI while the GUI shows the selected
  system.

## Gotchas

- Spin-box display rounding can make a US→SI round trip slightly lossy. Example:
  a 12000 per-m3 rate shows as ~339.80 per-ft3 and returns as ~11999.92; tests
  use a tolerance.
- `convert_text` is required for generated narratives because they embed SI
  numbers and unit strings directly.
- Adding a new quantity requires: registry entry, GUI bindings, import/export/
  report conversion and tests.
- The US PDF check expects `kip`, `ksf`, `ft`, `in`, `kip.ft`, `Concrete (ft3)`
  and `Steel (lb)`, with no `kPa` or `kN.m/m` headers.

## Tests

`tests/test_units.py` has 8 cases: registry round-trips, factors/labels,
narrative conversion, US CSV and Excel output, cost rates, dynamic GUI labels,
and the offscreen SI↔US toggle (including opening directly in US and switching
back to SI).

## Related records

- [state.json](state.json) — current unit-related quality state.
- [verification.md](verification.md) — US export evidence.
- [`core/units.py`](../bnbc_foundation/core/units.py) — implementation.
