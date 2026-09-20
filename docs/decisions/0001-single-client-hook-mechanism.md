# Single client hook mechanism: raw git hooks, not the `pre-commit` framework

## Status

Accepted

## Deviation

None. This does not depart from any prior baseline decision; `.pre-commit-config.yaml` and
`scripts/git-hooks` coexisted without prior arbitration, which is exactly what this decision
resolves.

## Consumers

T204 (`specs/003-no-stage-without-a-mechanism/tasks.md`), FR-004, the coexistence guard in
`verify_root` (`src/engineering_playbook/core.py`), and every derived project that installs
this template's `scripts/git-hooks`.

## Supersedes

Nothing written down previously; this is the first record of the choice between the two
mechanisms.

## Context and Problem Statement

This repository shipped two client-side hook mechanisms at once: a raw git hook
(`scripts/git-hooks/pre-commit`, `scripts/git-hooks/pre-push`) installed via `core.hooksPath`,
and `.pre-commit-config.yaml` configuring the third-party `pre-commit` framework (`ruff`,
`ruff-format`). Neither was arbitrated: `CONTRIBUTING.md` described them side by side as "isto
e um hook de git bruto ... diferente do framework `pre-commit`", without saying which one a
contributor's clone actually runs.

The two are not merely redundant, they are incompatible by construction: the `pre-commit`
framework refuses to install its own hooks when `core.hooksPath` is already set to a
non-default value (https://github.com/pre-commit/pre-commit/issues/3630). Once T203 makes
`engineering-playbook init`/`update` configure `core.hooksPath` unconditionally, running
`pre-commit install` in the same clone would fail outright. Shipping both was not "belt and
braces"; it was an unresolved conflict waiting for the first `core.hooksPath` activation to
surface it.

## Decision Drivers

- NFR-001: no new tool for an already-solved problem; the existing raw hook is kept.
- The raw hook's own `pre-push` already runs `scripts/local_ci.py`, which derives its steps
  from `.github/workflows/quality.yml` and includes `ruff format --check`, `ruff check`,
  `pyright`, `pytest`, and `scripts/verify.py` -- a strict superset of what the `pre-commit`
  framework config ran (`ruff --fix`, `ruff-format`).
- The two mechanisms cannot both be installed once `core.hooksPath` is configured
  (pre-commit/pre-commit#3630), so "keep both, let the developer choose" is not an available
  option once T203 lands.
- FR-009: whichever mechanism is kept documents its own bypass vectors in its own file;
  `scripts/git-hooks/pre-commit` and `pre-push` already do this.

## Considered Options

- Keep the raw git hook, remove `.pre-commit-config.yaml`.
- Keep `.pre-commit-config.yaml`, remove the raw git hook and reimplement the "no commit born
  on `main`" and CI-derived pre-push checks as `pre-commit` hooks.
- Keep both, and let each contributor choose which one to install.

## Decision Outcome

Keep `scripts/git-hooks` (installed via `core.hooksPath`) as the only client-side hook
mechanism. Remove `.pre-commit-config.yaml` from the repository root and from
`src/engineering_playbook/resources/`.

## Positive Consequences

- One mechanism, one thing to activate (`core.hooksPath`), one thing `doctor`/`verify` check.
- The raw hook already covers everything the `pre-commit` config covered (ruff) plus branch
  protection at commit time and the full CI-derived battery at push time.
- No dependency on the `pre-commit` framework or its Python environment for stacks in
  `profiles/stacks/` that are not Python (C++, Go, Rust, .NET, ...) -- consistent with the
  reasoning already written in `scripts/git-hooks/pre-commit`'s own header for why it avoids
  a Python-only reuse of `src/engineering_playbook/delivery.py`.

## Negative Consequences

- `ruff --fix` no longer runs automatically at commit time to auto-correct formatting before
  the commit is made; `pre-push` still catches the same violations, but only at push time, and
  it fails rather than auto-fixing. A contributor who wants pre-commit auto-fix now runs
  `uv run ruff check --fix .` / `uv run ruff format .` by hand.
- Any derived project that had installed `.pre-commit-config.yaml` from an earlier version of
  this template keeps its local copy; `engineering-playbook update` only manages files present
  in its own lock file entry for that path, and a project that already has `scripts/git-hooks`
  active would hit the same conflict this decision resolves for the template itself.

## Alternatives Considered

| Alternativa | Recusada porque |
|---|---|
| Manter `.pre-commit-config.yaml`, remover o hook bruto | Perderia a recusa de commit nascido em `main` e a bateria completa derivada do CI no `pre-push`; o framework `pre-commit` teria de reimplementar ambos, reintroduzindo a ferramenta que a NFR-001 pede para nao introduzir. |
| Manter os dois, sem arbitragem | Tecnicamente impossivel assim que `core.hooksPath` for configurado (T203): `pre-commit install` recusa-se a instalar (pre-commit/pre-commit#3630). Nao e uma opcao residual, e um estado que deixa de existir. |

## Evidence

- `pre-commit`'s refusal to install alongside `core.hooksPath`:
  https://github.com/pre-commit/pre-commit/issues/3630
- `scripts/git-hooks/pre-push` derives and runs `ruff format --check`, `ruff check`,
  `pyright`, `pytest`, and `scripts/verify.py` via `scripts/local_ci.py`, reading
  `.github/workflows/quality.yml` -- measured by reading that file's own header comment.
- `.pre-commit-config.yaml` (removed) configured only `ruff` and `ruff-format`, a strict
  subset of the above.
