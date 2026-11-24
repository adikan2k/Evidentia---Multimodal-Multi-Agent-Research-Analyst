# Decisions

One entry per decision. Each says what was chosen, why, what else was considered and the trade-off.
New entries go at the bottom. Aditya approves an entry before the module it covers is created.

## D-001. Package layout and tooling

Approved by Aditya on 2026-11-23.

**What.** A new `evidentia/` package at the repo root with one root `pyproject.toml` and `tests/`
beside it, managed with `uv`. Exact pins: `ruff==0.17.6`, `pytest==9.2.0`, build backend
`hatchling==1.33.0`. Python 3.11 or newer. Ruff checks `evidentia` and `tests` only; the old
`backend` and `frontend` folders are excluded.

**Why.** The plan names `evidentia/`, and M1 needs `python -m evidentia "question"` to work from the
repo root. `uv` writes a lockfile, so every machine and CI run installs the same versions.

**Considered.**
- A `src/` layout. Safer against importing the local folder by accident, but one more folder and
  not what the plan names.
- Building inside `backend/`. It would sit the new code next to old code we must not import.
- pip with `requirements.txt`. No lockfile, so transitive versions drift.

**Trade-off.** With a flat layout, tests can import the local folder instead of the installed
package, so a packaging mistake can go unnoticed. Acceptable because this is never published as a
library.
