"""The CI receipt reader, and its refusal wired into `command_checkpoint`.

Absence of `.project/last-ci-run.yml` must never read as green -- these tests measure the
three answers `check_ci_receipt` can give (COVERS / STALE / MISSING), one test per concrete
staleness reason, and the checkpoint's refusal to write a green claim it cannot verify.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Any

from engineering_playbook.commands import command_checkpoint
from engineering_playbook.core import load_yaml, write_yaml_atomic
from engineering_playbook.installer import command_init
from engineering_playbook.receipt import (
    CiReceiptStatus,
    battery_claims,
    check_ci_receipt,
)

# --- fixtures ---------------------------------------------------------------------------------


def init_git(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)


def head_of(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def build_derived_project(root: Path) -> Path:
    """A fully installed derived project, verify_root-clean, with one commit."""
    args = argparse.Namespace(
        path=root,
        project_name=None,
        profile="standard",
        stack="python",
        agents="codex",
        ci="github",
        dry_run=False,
        source="package",
    )
    assert command_init(args) == 0
    init_git(root)
    commit_all(root, "init")
    return root


def full_green_receipt(head: str, **overrides: Any) -> dict[str, Any]:
    receipt = {
        "schema_version": 1,
        "kind": "local_ci_receipt",
        "ran_at": "2026-09-20T00:00:00Z",
        "head": head,
        "head_before_run": head,
        "tree_was_dirty_before_run": False,
        "tree_changed_during_run": False,
        "tree_was_dirty": False,
        "dirty_paths": 0,
        "red": 0,
        "partial": 0,
        "green": 3,
        "affected_mode": False,
        "dry_run": False,
        "workflows_available": 3,
        "workflows_requested": 3,
        "workflows_run": 3,
    }
    receipt.update(overrides)
    return receipt


def write_receipt(root: Path, receipt: dict[str, Any]) -> None:
    write_yaml_atomic(root / ".project/last-ci-run.yml", receipt)


def claim_battery_ran(root: Path) -> None:
    state_path = root / ".project/state.yml"
    state: dict[str, Any] = load_yaml(state_path)
    validation: dict[str, Any] = state.get("validation") or {
        "passed": [],
        "failed": [],
        "not_run": [],
    }
    passed: list[Any] = validation.get("passed") or []
    validation["passed"] = [*passed, "uv run python scripts/local_ci.py"]
    state["validation"] = validation
    write_yaml_atomic(state_path, state)


# --- battery_claims: structural first, textual fallback ---------------------------------------


def test_battery_claims_is_empty_without_any_claim() -> None:
    state = {"validation": {"passed": ["uv run pytest"], "failed": [], "not_run": []}}
    assert battery_claims(state) == []


def test_battery_claims_matches_the_textual_marker_case_insensitively() -> None:
    state = {"validation": {"passed": ["UV RUN python scripts/LOCAL_CI.py"], "failed": []}}
    assert battery_claims(state) == ["UV RUN python scripts/LOCAL_CI.py"]


def test_battery_claims_prefers_the_structured_key_over_text() -> None:
    state = {
        "validation": {
            "passed": ["uv run pytest"],  # no textual marker here at all
            "battery_runs": ["local_ci@abc123"],
        }
    }
    assert battery_claims(state) == ["local_ci@abc123"]


# --- check_ci_receipt: MISSING --------------------------------------------------------------


def test_missing_receipt_is_missing_never_green(tmp_path: Path) -> None:
    check = check_ci_receipt(tmp_path, "deadbeef")
    assert check.status is CiReceiptStatus.MISSING
    assert check.receipt is None
    assert "nao existe" in (check.reason or "")


# --- check_ci_receipt: COVERS ----------------------------------------------------------------


def test_a_full_green_receipt_for_this_head_covers(tmp_path: Path) -> None:
    write_receipt(tmp_path, full_green_receipt("abc123"))
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.COVERS
    assert check.reason is None


# --- check_ci_receipt: STALE, one test per concrete reason ------------------------------------


def test_stale_when_the_receipt_measured_another_commit(tmp_path: Path) -> None:
    write_receipt(tmp_path, full_green_receipt("other-commit"))
    check = check_ci_receipt(tmp_path, "current-head")
    assert check.status is CiReceiptStatus.STALE
    assert "noutro commit" in (check.reason or "")


def test_stale_when_tree_was_dirty_before_run(tmp_path: Path) -> None:
    write_receipt(tmp_path, full_green_receipt("abc123", tree_was_dirty_before_run=True))
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.STALE
    assert "SUJA antes" in (check.reason or "")


def test_stale_when_tree_was_dirty(tmp_path: Path) -> None:
    write_receipt(tmp_path, full_green_receipt("abc123", tree_was_dirty=True, dirty_paths=2))
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.STALE
    assert "SUJA" in (check.reason or "")


def test_stale_when_it_was_a_dry_run(tmp_path: Path) -> None:
    write_receipt(tmp_path, full_green_receipt("abc123", dry_run=True))
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.STALE
    assert "dry_run" in (check.reason or "")


def test_stale_when_it_ran_in_affected_mode(tmp_path: Path) -> None:
    write_receipt(tmp_path, full_green_receipt("abc123", affected_mode=True))
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.STALE
    assert "afetado" in (check.reason or "")


def test_stale_when_workflow_counts_are_absent(tmp_path: Path) -> None:
    receipt = full_green_receipt("abc123")
    del receipt["workflows_run"]
    write_receipt(tmp_path, receipt)
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.STALE
    assert "recibo incompleto" in (check.reason or "")


def test_stale_when_fewer_workflows_ran_than_are_available(tmp_path: Path) -> None:
    write_receipt(
        tmp_path,
        full_green_receipt("abc123", workflows_requested=1, workflows_run=1, workflows_available=3),
    )
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.STALE
    assert "nao e a corrida inteira" in (check.reason or "")


def test_stale_when_red_is_above_zero(tmp_path: Path) -> None:
    write_receipt(tmp_path, full_green_receipt("abc123", red=1, green=2))
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.STALE
    assert "vermelho" in (check.reason or "")


def test_stale_when_partial_is_above_zero(tmp_path: Path) -> None:
    write_receipt(tmp_path, full_green_receipt("abc123", partial=3, green=0))
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.STALE
    assert "parcial" in (check.reason or "")


def test_stale_when_green_does_not_cover_every_available_workflow(tmp_path: Path) -> None:
    # red=0, partial=0, but green(2) < available(3): the counts simply do not add up to a
    # full green, which must be refused just as loudly as an explicit red or partial.
    write_receipt(tmp_path, full_green_receipt("abc123", green=2))
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.STALE
    assert "nem tudo ficou verde" in (check.reason or "")


def test_stale_when_the_tree_changed_during_the_run(tmp_path: Path) -> None:
    write_receipt(
        tmp_path,
        full_green_receipt("abc123", head_before_run="other", tree_changed_during_run=True),
    )
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.STALE
    assert "mudou durante" in (check.reason or "")


def test_stale_when_the_receipt_is_not_a_yaml_mapping(tmp_path: Path) -> None:
    (tmp_path / ".project").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".project/last-ci-run.yml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    check = check_ci_receipt(tmp_path, "abc123")
    assert check.status is CiReceiptStatus.STALE
    assert "mapeamento" in (check.reason or "")


# --- command_checkpoint: refusal wired to the receipt ------------------------------------------


def test_checkpoint_is_written_normally_without_any_battery_claim(tmp_path: Path) -> None:
    root = build_derived_project(tmp_path / "derived")

    exit_code = command_checkpoint(root)

    assert exit_code == 0
    checkpoints = list((root / ".project/checkpoints").glob("CP-*.yml"))
    assert len(checkpoints) == 1
    written = load_yaml(checkpoints[0])
    assert written["battery_claim_divergent"] is False


def test_checkpoint_is_written_when_the_receipt_covers_head(tmp_path: Path) -> None:
    root = build_derived_project(tmp_path / "derived")
    claim_battery_ran(root)
    write_receipt(root, full_green_receipt(head_of(root)))

    exit_code = command_checkpoint(root)

    assert exit_code == 0
    checkpoints = list((root / ".project/checkpoints").glob("CP-*.yml"))
    assert len(checkpoints) == 1
    assert load_yaml(checkpoints[0])["battery_claim_divergent"] is False


def test_checkpoint_refuses_a_green_claim_with_no_receipt_at_all(tmp_path: Path) -> None:
    root = build_derived_project(tmp_path / "derived")
    claim_battery_ran(root)

    exit_code = command_checkpoint(root)

    assert exit_code == 1
    assert list((root / ".project/checkpoints").glob("CP-*.yml")) == []


def test_checkpoint_refuses_a_green_claim_measured_on_another_commit(tmp_path: Path) -> None:
    root = build_derived_project(tmp_path / "derived")
    claim_battery_ran(root)
    write_receipt(root, full_green_receipt("some-other-commit-entirely"))

    exit_code = command_checkpoint(root)

    assert exit_code == 1
    assert list((root / ".project/checkpoints").glob("CP-*.yml")) == []


def test_checkpoint_refuses_a_green_claim_over_a_partial_run(tmp_path: Path) -> None:
    root = build_derived_project(tmp_path / "derived")
    claim_battery_ran(root)
    write_receipt(root, full_green_receipt(head_of(root), partial=2, green=1))

    exit_code = command_checkpoint(root)

    assert exit_code == 1
    assert list((root / ".project/checkpoints").glob("CP-*.yml")) == []


def test_allow_divergent_writes_the_checkpoint_but_marks_it_and_still_exits_nonzero(
    tmp_path: Path,
) -> None:
    root = build_derived_project(tmp_path / "derived")
    claim_battery_ran(root)
    write_receipt(root, full_green_receipt("some-other-commit-entirely"))

    exit_code = command_checkpoint(root, allow_divergent=True)

    assert exit_code == 1, "a divergent stop must not look like a clean one"
    checkpoints = list((root / ".project/checkpoints").glob("CP-*.yml"))
    assert len(checkpoints) == 1
    written = load_yaml(checkpoints[0])
    assert written["battery_claim_divergent"] is True


def test_checkpoint_ignores_the_receipt_state_when_nothing_claims_a_battery_ran(
    tmp_path: Path,
) -> None:
    # No claim in validation.passed at all: an absent/stale receipt must not block a checkpoint
    # that never asserted a green battery in the first place.
    root = build_derived_project(tmp_path / "derived")

    exit_code = command_checkpoint(root)

    assert exit_code == 0
    checkpoints = list((root / ".project/checkpoints").glob("CP-*.yml"))
    assert len(checkpoints) == 1
    assert load_yaml(checkpoints[0])["battery_claim_divergent"] is False
