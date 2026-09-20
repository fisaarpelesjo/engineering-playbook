"""Every mirrored file the resources copy ships, not just the one pre-commit hook.

`test_git_hooks.py::test_the_distributed_copy_matches_the_source_of_truth` guards exactly one
pair: the `pre-commit` hook. Derived projects install from `src/engineering_playbook/resources/`,
so any other file that exists at the same relative path in both the repository root and the
resources tree ships stale the moment the two drift, silently.

Excluded, and why -- measured, not guessed:

- `uv.lock`: `diff uv.lock src/engineering_playbook/resources/uv.lock` shows exactly one line,
  `source = { editable = "." }` at the root versus `source = { virtual = "." }` in the resources
  copy. This repository is an installable package; a derived project is not. The difference is
  structural, not drift.
- `.github/workflows/quality.yml` and everything under `.project/schemas/`: owned by a workstream
  editing them concurrently with this guard (`git status --porcelain` shows both modified at the
  time this test was written). Parity for those paths is that workstream's responsibility, not
  asserted here.
- `.project/project.yml`, `pyproject.toml`, `docs/requirements/project-requirements.md`: listed
  under `distribution.yml`'s `generated:` mapping. The installer renders these from the resources
  copy (`render_project_yml`, `render_pyproject`, `strip_source_prd`); they are templates, not
  literal mirrors, and coincidentally matching today is not a contract.
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT / "src" / "engineering_playbook" / "resources"

_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".pyright"}

_EXCLUDED_PAIRS = frozenset(
    {
        "uv.lock",
        ".github/workflows/quality.yml",
        ".project/project.yml",
        "pyproject.toml",
        "docs/requirements/project-requirements.md",
    }
)


def _is_excluded(rel: str) -> bool:
    return rel in _EXCLUDED_PAIRS or rel.startswith(".project/schemas/")


def _mirrored_pairs() -> list[str]:
    pairs: list[str] = []
    for dirpath, dirnames, filenames in os.walk(RESOURCES):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for filename in filenames:
            resource_path = Path(dirpath) / filename
            rel = str(resource_path.relative_to(RESOURCES)).replace("\\", "/")
            if _is_excluded(rel):
                continue
            if (ROOT / rel).is_file():
                pairs.append(rel)
    return sorted(pairs)


def test_at_least_the_known_families_are_covered() -> None:
    """A guard over an empty list passes for the wrong reason; pin the measured floor."""
    pairs = _mirrored_pairs()
    assert len(pairs) >= 75, (
        f"only {len(pairs)} mirrored pairs were discovered; the walk may be broken "
        "rather than the repository having shrunk"
    )


def test_every_mirrored_pair_matches_byte_for_byte() -> None:
    pairs = _mirrored_pairs()
    mismatches = [
        rel for rel in pairs if (ROOT / rel).read_bytes() != (RESOURCES / rel).read_bytes()
    ]
    assert mismatches == [], (
        "these files have drifted between the repository root and "
        f"src/engineering_playbook/resources/, so derived projects install a stale copy: "
        f"{mismatches}"
    )
