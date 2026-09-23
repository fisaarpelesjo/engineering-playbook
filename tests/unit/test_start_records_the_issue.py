"""Issue #73: `start` knows the issue number, and the next `prepare` has to close that issue.

`start --number 064` built `fix/064-...` and wrote the number nowhere, so `.project/state.yml`
kept the previous slice's `issue: 65` and `prepare` wrote `Closes #65` into the pull request
body. It failed closed only because #65 happened to be closed already; with two slices open, the
merge would have closed an issue the work never addressed.

The tests measure the state AFTER `start`, and the refusal in `prepare`, not the file at rest.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from engineering_playbook import delivery
from engineering_playbook.core import load_yaml, write_yaml_atomic
from engineering_playbook.delivery import (
    PREPARE_FILE,
    STATE_FILE,
    command_prepare,
    command_start,
    issue_from_branch,
)


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def repo_after_a_merged_slice(root: Path) -> None:
    """`main` carrying the state the previous slice left: its issue and its pull request."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    write_yaml_atomic(
        root / STATE_FILE,
        {
            "schema_version": "1.0.0",
            "current_branch": "feat/065-previous",
            "issue": 65,
            "delivery": {"branch": "feat/065-previous", "pr_number": 70},
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")


def start_args(root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        root=root,
        type="fix",
        number="064",
        slug="example",
        allow_dirty=False,
        remote="origin",
        base="main",
        allow_unmerged_head=False,
        from_base=False,
    )


def test_start_points_the_state_at_the_slice_it_opened(tmp_path: Path) -> None:
    """THE claim, measured the way #73 reproduced it: `start --number 064` after #65."""
    root = tmp_path / "repo"
    repo_after_a_merged_slice(root)

    assert command_start(start_args(root)) == 0

    state = load_yaml(root / STATE_FILE)
    assert state["issue"] == 64
    assert state["current_branch"] == "fix/064-example"
    assert "delivery" not in state, "the previous slice's pull request is not this branch's"


def test_start_does_not_invent_a_state_file(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    repo_after_a_merged_slice(root)
    git(root, "rm", "-q", STATE_FILE)
    git(root, "commit", "-qm", "no state")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")

    assert command_start(start_args(root)) == 0

    assert not (root / STATE_FILE).exists()


class GateReachedError(Exception):
    pass


def gates_must_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """The refusal has to come before the gates; reaching one is the failure being measured."""

    def first_gate(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        raise GateReachedError(args)

    monkeypatch.setattr(delivery, "run", first_gate)


def prepare_args(root: Path) -> argparse.Namespace:
    return argparse.Namespace(root=root, title=None)


def test_prepare_refuses_a_state_that_names_another_issue(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A state edited by hand after `start`, or a branch switched to outside the pipeline."""
    root = tmp_path / "repo"
    repo_after_a_merged_slice(root)
    git(root, "switch", "-qc", "fix/064-example")
    gates_must_not_run(monkeypatch)

    assert command_prepare(prepare_args(root)) == 1

    output = capsys.readouterr().out
    assert "#64" in output and "65" in output
    assert not (root / PREPARE_FILE).exists(), "a refused prepare leaves no approval behind"


def test_prepare_refuses_a_state_that_declares_no_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    repo_after_a_merged_slice(root)
    state = load_yaml(root / STATE_FILE)
    del state["issue"]
    write_yaml_atomic(root / STATE_FILE, state)
    git(root, "switch", "-qc", "fix/064-example")
    gates_must_not_run(monkeypatch)

    assert command_prepare(prepare_args(root)) == 1


def test_prepare_refuses_an_issue_written_as_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`issue: '64'` is not the integer `pr_body` and the schema expect; say so rather than
    printing a mismatch between two values that read the same.
    """
    root = tmp_path / "repo"
    repo_after_a_merged_slice(root)
    state = load_yaml(root / STATE_FILE)
    state["issue"] = "64"
    write_yaml_atomic(root / STATE_FILE, state)
    git(root, "switch", "-qc", "fix/064-example")
    gates_must_not_run(monkeypatch)

    assert command_prepare(prepare_args(root)) == 1

    assert "not an integer" in capsys.readouterr().out


def test_prepare_refuses_rather_than_crashing_without_a_state_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    repo_after_a_merged_slice(root)
    git(root, "switch", "-qc", "fix/064-example")
    (root / STATE_FILE).unlink()
    gates_must_not_run(monkeypatch)

    assert command_prepare(prepare_args(root)) == 1


def test_start_leaves_a_state_that_is_not_a_mapping_alone(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    repo_after_a_merged_slice(root)
    (root / STATE_FILE).write_text("", encoding="utf-8")
    git(root, "commit", "-qam", "empty state")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")

    assert command_start(start_args(root)) == 0

    assert (root / STATE_FILE).read_text(encoding="utf-8") == ""


def test_start_refuses_issue_zero_before_creating_the_branch(tmp_path: Path) -> None:
    """`issue: 0` would break the schema's `minimum: 1`, found only later by `verify`."""
    root = tmp_path / "repo"
    repo_after_a_merged_slice(root)
    args = start_args(root)
    args.number = "000"

    assert command_start(args) == 1

    assert git(root, "branch", "--show-current") == "main"
    assert load_yaml(root / STATE_FILE)["issue"] == 65


def test_prepare_goes_on_to_the_gates_when_the_two_agree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal bites only on disagreement: a matching state reaches the first gate."""
    root = tmp_path / "repo"
    repo_after_a_merged_slice(root)
    assert command_start(start_args(root)) == 0
    gates_must_not_run(monkeypatch)

    with pytest.raises(GateReachedError):
        command_prepare(prepare_args(root))


@pytest.mark.parametrize(
    ("branch", "expected"),
    [
        ("fix/064-example", 64),
        ("feat/001234-long-number", 1234),
        ("main", None),
        ("fix/example-without-number", None),
    ],
)
def test_the_issue_is_read_back_from_the_branch_name(branch: str, expected: int | None) -> None:
    assert issue_from_branch(branch) == expected
