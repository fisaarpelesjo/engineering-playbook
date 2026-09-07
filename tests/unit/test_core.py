from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.playbook_core import (
    validate_conventional_title,
    validate_transition,
    verify_root,
)

ROOT = Path(__file__).resolve().parents[2]


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_verify_current_repository() -> None:
    result = verify_root(ROOT)
    assert result.errors == []


def test_state_transition_rejects_planned_to_done() -> None:
    assert not validate_transition("planned", "done")
    assert validate_transition("planned", "ready")


def test_conventional_title_validation() -> None:
    assert validate_conventional_title("feat(playbook): add checkpoint command")
    assert not validate_conventional_title("updates")
    assert not validate_conventional_title("fix: Bad title.")


def test_resume_is_read_only() -> None:
    before = (ROOT / ".project/state.yml").read_text(encoding="utf-8")
    completed = run_script("scripts/resume.py")
    after = (ROOT / ".project/state.yml").read_text(encoding="utf-8")
    assert before == after
    assert completed.returncode == 0


def test_reconcile_without_apply_is_read_only() -> None:
    before = (ROOT / ".project/state.yml").read_text(encoding="utf-8")
    completed = run_script("scripts/reconcile.py")
    after = (ROOT / ".project/state.yml").read_text(encoding="utf-8")
    assert before == after
    assert completed.returncode in {0, 1}


def test_required_fixture_inventory_exists() -> None:
    fixtures = {
        "valid-project",
        "missing-spec",
        "stale-checkpoint",
        "wrong-branch",
        "dirty-working-tree",
        "missing-test-reference",
        "duplicate-requirement-id",
        "invalid-state-transition",
        "conflicting-agent-rules",
        "overlapping-workstream-ownership",
        "outdated-verified-commit",
        "forgotten-placeholder",
    }
    existing = {path.name for path in (ROOT / "tests/fixtures").iterdir() if path.is_dir()}
    assert fixtures <= existing
