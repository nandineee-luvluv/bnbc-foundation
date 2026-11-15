# Local Zip Backup

[Back to map](MAP.md) · Related: [repository.md](repository.md) · [verification.md](verification.md) · [handoff.md](handoff.md)

## Archive

- **Location:** `/home/anway/Documents/OpencodeProjects/project01/bnbc-foundation-backup-2026-11-15.zip`
- **Format:** ZIP with a single top-level `bnbc-foundation/` directory.
- **Purpose:** complete local restore point for the working project, independent
  of GitHub.
- **Git status:** ignored by `.gitignore` (`*.zip`) and never committed.

## Contents

The backup includes:

- `bnbc_foundation/` source and PySide6 UI
- `tests/` (91 cases)
- `samples/` (Excel, PDF, CSV, JSON and import template)
- `.opencode/` project history and audit docs
- `.xcontext/` this knowledge base
- `README.md`, `LICENSE`, `requirements.txt`, `run.py`
- `.gitignore`, `.zipignore`
- `.git/` repository history and remote configuration

## Exclusions (`.zipignore`)

- Python virtual environments: `.venv/`, `venv/`, `env/`, `ENV/`
- Python/package/test caches: `__pycache__/`, `*.py[cod]`, `*.egg-info/`,
  `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, coverage output
- Build/output: `build/`, `dist/`, `*.spec`, `exports/`
- Logs and nested archives: `*.log`, `*.zip`, `*.7z`, `*.tar`, `*.tar.gz`, `*.tgz`
- Internal agent tooling: `.opencode/skills/` (project docs are kept)
- OS/editor files: `.DS_Store`, `Thumbs.db`, `.idea/`, `.vscode/`, swap files

`.zipignore` uses shell-glob patterns relative to the project root; a trailing
slash matches a directory and all contents. The archive is built from the
committed working tree, so the `.git` directory inside it is a restorable
repository history.

## Historical verification

The archive created before `.xcontext` was added had:

- 153 entries
- 718,312 bytes
- SHA-256 `57c74d1f43d9bae829e9233ae286a6a20966ad1c4e7634347933dd8ef382059b`

It was extracted to a clean directory and passed `git status`, the smoke test
and all 91 tests; all sample checksums matched. The current archive includes the
new `.xcontext/` files, so its size and checksum differ. Compute the current hash:

```bash
sha256sum bnbc-foundation-backup-2026-11-15.zip
```

## Restore and verify

```bash
rm -rf /tmp/bnbc-restore
mkdir -p /tmp/bnbc-restore
unzip -q bnbc-foundation-backup-2026-11-15.zip -d /tmp/bnbc-restore
cd /tmp/bnbc-restore/bnbc-foundation

git status -sb
QT_QPA_PLATFORM=offscreen /path/to/project01/.venv/bin/python run.py --smoke
QT_QPA_PLATFORM=offscreen /path/to/project01/.venv/bin/python -m pytest -q
```

The archive intentionally excludes `.venv`; use an existing environment or
recreate one from `requirements.txt` before running the checks.

## Regeneration

1. Commit the project changes first, so `.git` history matches the working tree.
2. Read `.zipignore` and build the file list before opening the output archive.
3. Walk the project, pruning ignored directories; skip the archive itself.
4. Write entries with the `bnbc-foundation/` prefix using deflate compression.
5. Verify no `.venv`, caches, `.opencode/skills` or nested `.zip` entries.
6. Extract to a clean directory and run the smoke/test checks.
7. Record the current size and SHA-256 in the session handoff or final response;
   do not hardcode it inside files contained in the archive.

## Why the archive lives inside the project

The backup was intentionally moved from a sibling `backups/` folder into the
project root, per the requested layout. Both `.gitignore` and `.zipignore`
exclude `*.zip`, so the archive cannot accidentally be committed or nested in a
future backup.
