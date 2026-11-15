# Next-Session Handoff

[Back to map](MAP.md) · Related: [state.json](state.json) · [decisions.json](decisions.json) · [worklog.md](worklog.md) · [repository.md](repository.md)

## Start here

1. Read [MAP.md](MAP.md).
2. Read [context.md](context.md) and [state.json](state.json).
3. Check `git status` and `git log -1` in the project root.
4. Run the verification commands below before changing code.

```bash
cd /home/anway/Documents/OpencodeProjects/project01
git pull
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q
.venv/bin/python run.py --smoke
```

Expected: **91 passed**, smoke exit `0`.

## Current state

- All 17 audit findings are closed.
- SI/US unit system is complete, including cost rates, dynamic labels and JSON
  `info.units`.
- Public repository is live at
  https://github.com/nandineee-luvluv/bnbc-foundation under MIT.
- Local zip backup exists at
  `bnbc-foundation-backup-2026-11-15.zip` inside the project root.
- No open correctness or reporting issue is known.
- `.xcontext/` is the durable context record; `.opencode/` holds the detailed
  historical build/audit log.

## Remaining work

1. **Real-project validation** — replace the synthetic sample with a real soil
   report and base-reaction export; verify bearing, settlement, pile, CPT and
   downdrag inputs.
2. **ETABS/SAFE validation** — confirm case naming and sign conventions against
   real exports.
3. **Windows packaging** — build and test the PyInstaller executable on Windows
   (`pyinstaller --noconfirm --windowed --name BNBC-Foundation-Designer run.py`).
4. **User documentation** — add screenshots or a short guide if the app is
   distributed to other engineers.
5. **Review checks against project practice** — the tool remains a design aid;
   a qualified engineer must approve all output.

## Known gotchas

- Use `.venv/bin/python`; the system Python lacks the project dependencies.
- Qt tests must run with `QT_QPA_PLATFORM=offscreen`.
- In regression tests, strength reactions need `Reaction(..., factored=True)`;
  otherwise `governing_service()` may select them.
- `estimate_shallow_settlement` lives in `core.settlement`, not `core.soil`.
- JSON stores SI numeric values; `info.units` is only the display system.
- The synthetic sample is intentionally on soft clay. Selected foundations report
  `CHECK` for settlement/crack width; this is not a bug.
- The backup archive is inside the project root but ignored by git and excluded
  from itself. `.zipignore` controls its contents.
- Do not commit `.venv/`, caches, generated exports, secrets or the zip archive.
- The repository is public and MIT-licensed; copyright remains with Nandini
  Shahnewaz.

## Updating the context after a session

1. Add significant events to [timeline.json](timeline.json).
2. Update [state.json](state.json) with new test/repository/backup facts.
3. Update [worklog.md](worklog.md) and the relevant focused record.
4. Update [manifest.json](manifest.json) if files or relationships change.
5. Regenerate the zip backup and verify it in a clean extraction.
6. Commit and push:

```bash
git add -A
git commit -m "Update project context"
git push origin main
```

## Where to look

| Need | File |
|---|---|
| Project objective and decisions | [context.md](context.md) |
| Code layout and data flow | [architecture.md](architecture.md) |
| Audit fixes | [audit.md](audit.md) |
| SI/US rules | [units.md](units.md) |
| Test/export evidence | [verification.md](verification.md) |
| GitHub/license/commits | [repository.md](repository.md) |
| Zip backup | [backup.md](backup.md) |
| Full chronological history | [worklog.md](worklog.md) and [`.opencode/progression.md`](../.opencode/progression.md) |
| Machine state | [state.json](state.json) |
