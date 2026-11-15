# Repository and Publication

[Back to map](MAP.md) · Related: [backup.md](backup.md) · [context.md](context.md) · [handoff.md](handoff.md)

## Public repository

- **URL:** https://github.com/nandineee-luvluv/bnbc-foundation
- **Owner:** Nandini Shahnewaz (`nandineee-luvluv`)
- **Visibility:** Public
- **Default branch:** `main`
- **License:** MIT (detected by GitHub)
- **Topics:** `bnbc`, `civil-engineering`, `foundation-design`,
  `geotechnical-engineering`, `pyside6`, `python`, `structural-engineering`

## Commit history at context creation

| Commit | Message | Contents |
|---|---|---|
| `073dbb9` | Initial public release: BNBC 2020 foundation designer | 56 files, 1.1 MB: application, tests, samples, docs, LICENSE, README |
| `8c419db` | Add zip backup ignore rules | `.zipignore` and archive/backup rules in `.gitignore` |

The commit that adds `.xcontext/` becomes the next `main` HEAD. Use `git log`
for the exact current hash rather than hardcoding it in these files.

## Git identity used

```text
Nandini Shahnewaz <267397396+nandineee-luvluv@users.noreply.github.com>
```

## Tracked and excluded

**Tracked:** `bnbc_foundation/`, `tests/`, `samples/`, `.opencode/` project
docs, `.xcontext/`, `README.md`, `LICENSE`, `requirements.txt`, `run.py`,
`.gitignore`, `.zipignore`.

**Ignored:** `.venv/`, `venv/`, `__pycache__/`, `*.py[cod]`, `.pytest_cache/`,
`.mypy_cache/`, `.ruff_cache/`, coverage/test output, `build/`, `dist/`,
`*.spec`, `exports/`, logs, generated `.xlsx/.pdf/.csv` outside `samples/`,
archives (`*.zip`, `*.7z`, `*.tar*`, `*.tgz`), `backups/`, internal
`.opencode/skills/`, OS/editor files.

## Ownership and license

Copyright (c) 2026 Nandini Shahnewaz. The MIT license permits free use, copying,
modification, distribution, sublicensing and sale, provided the original
copyright and permission notice are retained in all copies or substantial
portions. The license does not transfer ownership or authorship of the original
project. See [`LICENSE`](../LICENSE) and the License section of
[`README.md`](../README.md).

## Publishing updates

```bash
git add -A
git commit -m "Describe the change"
git push origin main
```

The repository was created with:

```bash
gh repo create nandineee-luvluv/bnbc-foundation \
  --public --source=. --remote=origin --push \
  --description "A PySide6 desktop application for BNBC 2020 foundation design with SI/US units, shallow/pile/raft analysis, and Excel/PDF/CSV/JSON exports."
```

## Rules for future sessions

- Do not commit secrets, personal paths, virtualenvs or generated exports.
- Keep samples in `samples/`; `.gitignore` explicitly whitelists them.
- Keep `.xcontext/` current when architecture, verification or repository state
  changes.
- The archive backup is local and ignored by git; do not commit it.
