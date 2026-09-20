"""T204: the raw git hook and the `pre-commit` framework must never both be active.

FR-004: "Coexistencia nao arbitrada de dois mecanismos de hook e eliminada." The decision in
`docs/decisions/0001-single-client-hook-mechanism.md` removed `.pre-commit-config.yaml`; this
guards against its silent reintroduction while `core.hooksPath` is active, which is the exact
state the decision eliminated. The adversarial test recreates that exact state and asserts the
rejection is observed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engineering_playbook.core import verify_root


def init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def install_hooks_dir(root: Path) -> None:
    hooks_dir = root / "scripts" / "git-hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "pre-commit").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")


def test_verify_rejects_both_mechanisms_active_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The adversarial attempt: reintroduce .pre-commit-config.yaml with hooksPath active."""
    # The hooks block this check lives in is skipped under CI, where client hooks
    # are meaningless. This test is about the guard firing, so it states the
    # environment it needs instead of inheriting the runner's.
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    init_repo(tmp_path)
    install_hooks_dir(tmp_path)
    subprocess.run(
        ["git", "config", "core.hooksPath", "scripts/git-hooks"], cwd=tmp_path, check=True
    )
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")

    result = verify_root(tmp_path)

    assert any(
        "Two incompatible hook mechanisms are active at once" in error for error in result.errors
    ), (
        f"verify_root did not reject the coexistence of both hook mechanisms; "
        f"errors: {result.errors}"
    )


def test_verify_allows_the_config_file_when_hooks_path_is_not_active(tmp_path: Path) -> None:
    """The other half: a stray file with no active raw hook is a different (unmeasured) case.

    This asserts the control is not a blanket "file must never exist" rule that would fire
    even where the two mechanisms cannot actually collide -- it fires on simultaneous
    activation, which is what FR-004 names.
    """
    init_repo(tmp_path)
    install_hooks_dir(tmp_path)
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")

    result = verify_root(tmp_path)

    assert not any(
        "Two incompatible hook mechanisms are active at once" in error for error in result.errors
    )


def test_pre_commit_config_yaml_was_removed_from_both_copies() -> None:
    """FR-004's chosen arbitration: one mechanism removed, not merely declared secondary."""
    root = Path(__file__).resolve().parents[2]
    assert not (root / ".pre-commit-config.yaml").exists()
    assert not (root / "src/engineering_playbook/resources/.pre-commit-config.yaml").exists()


def test_the_decision_is_recorded() -> None:
    root = Path(__file__).resolve().parents[2]
    decisions = list((root / "docs" / "decisions").glob("*.md"))
    assert any("hook" in path.name for path in decisions), (
        "no decision file under docs/decisions/ documents the hook mechanism arbitration"
    )
