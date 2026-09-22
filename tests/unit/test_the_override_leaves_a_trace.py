"""T220 / FR-009 / FR-012: a branch born under an exception says so where an instrument can read it.

`start --allow-unmerged-head` exists for the one legitimate case the base-containment check would
otherwise block: stacking a slice on another that has not been integrated yet. It was explicit on
the command line and it printed a warning.

That warning lived in the terminal of whoever ran the command. Nothing reached
`.project/delivery/`, so neither an audit nor the next stage of this same pipeline could tell that
a branch had been created under an exception. Everything else here leaves a record an instrument
can read -- `prepare` writes its receipt, `checkpoint` writes its own, the state carries the
verdict cache, CI writes the run receipt. This was the one step whose exception existed only as
words on a screen.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from engineering_playbook.core import load_yaml, write_yaml_atomic
from engineering_playbook.delivery import ORIGIN_FILE, command_start, command_status


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def repo_after_a_squash_merge(root: Path) -> None:
    """The ordinary post-squash checkout: HEAD holds commits the base absorbed under other ids."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    old_base = git(root, "rev-parse", "HEAD")

    git(root, "switch", "-qc", "feat/001-previous")
    (root / "b.txt").write_text("previous slice\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "previous slice")
    tree = git(root, "rev-parse", "HEAD^{tree}")

    squash = git(root, "commit-tree", tree, "-p", old_base, "-m", "squash: previous")
    git(root, "update-ref", "refs/remotes/origin/main", squash)


def start_args(root: Path, **overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "root": root,
        "type": "fix",
        "number": "052",
        "slug": "example",
        "allow_dirty": True,
        "remote": "origin",
        "base": "main",
        "allow_unmerged_head": False,
        "from_base": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def status_args(root: Path) -> argparse.Namespace:
    # `status` reads the state file as well as the origin record, so a repository it can report on
    # has to have one.
    write_yaml_atomic(
        root / ".project/state.yml",
        {"schema_version": "1.0.0", "status": "in_progress", "updated_at": "2026-01-01T00:00:00Z"},
    )
    return argparse.Namespace(root=root, base="main", remote="origin")


def test_the_override_is_recorded_where_an_instrument_reads_it(tmp_path: Path) -> None:
    """THE claim. A warning on a terminal is not a record; this is."""
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)

    assert command_start(start_args(root, allow_unmerged_head=True)) == 0

    origin = load_yaml(root / ORIGIN_FILE)
    assert origin["override"] == "allow-unmerged-head"
    assert origin["branch"] == "fix/052-example"
    assert origin["created_at"], "a record with no time is a record nobody can order"


def test_an_ordinary_branch_records_that_it_used_no_override(tmp_path: Path) -> None:
    """Written whichever way it went. A record that only exists when the exception was used reads,
    to anyone scanning, exactly like a line somebody forgot to write.
    """
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)

    assert command_start(start_args(root, from_base=True)) == 0

    origin = load_yaml(root / ORIGIN_FILE)
    assert origin["override"] is None
    assert origin["base_ref"] == "refs/remotes/origin/main"


def test_a_branch_started_from_head_records_that_too(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)
    git(root, "switch", "-q", "main")

    assert command_start(start_args(root)) == 0

    assert load_yaml(root / ORIGIN_FILE)["base_ref"] == "HEAD"


def test_a_refused_start_leaves_no_record(tmp_path: Path) -> None:
    """The record describes a branch that exists. Writing one for a branch the gate refused would
    make the file say a slice began when it did not.
    """
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)

    assert command_start(start_args(root)) == 1
    assert not (root / ORIGIN_FILE).exists()


def test_status_reports_the_origin_either_way(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The next stage reads it. An override nobody surfaces is an override nobody audits."""
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)
    command_start(start_args(root, allow_unmerged_head=True))
    capsys.readouterr()

    command_status(status_args(root))

    out = capsys.readouterr().out
    assert "branch_override: allow-unmerged-head" in out
    assert "branch_from:" in out


def test_status_says_none_when_no_override_was_used(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)
    command_start(start_args(root, from_base=True))
    capsys.readouterr()

    command_status(status_args(root))

    assert "branch_override: none" in capsys.readouterr().out


def test_a_second_start_replaces_the_record(tmp_path: Path) -> None:
    """The file describes the branch being worked on now. `.project/delivery/` is git-ignored
    scratch, so this is a record for the operator and the pipeline, not a history -- and saying so
    is better than letting a reader assume it accumulates.
    """
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)
    command_start(start_args(root, allow_unmerged_head=True))
    git(root, "switch", "-q", "main")

    command_start(start_args(root, slug="second"))

    origin = load_yaml(root / ORIGIN_FILE)
    assert origin["branch"] == "fix/052-second"
    assert origin["override"] is None


def test_the_two_flags_together_record_an_override_that_did_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """#61. `--allow-unmerged-head` with `--from-base` suppresses a check that had nothing to say:
    the branch starts at the base, so there is no absorbed HEAD to carry.

    The first version recorded `override: allow-unmerged-head` all the same, telling an audit a
    risk was taken when none was. The second appended "(not exercised: --from-base)" to the value,
    which fixed the meaning and broke the field: `override` stopped being something a reader can
    compare against. Two fields now, and this test is what stops a third revision from quietly
    dropping either one -- the correction to the first version had no test at all, which is the
    same defect, one order of magnitude smaller, that this whole issue exists to record.
    """
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)

    assert command_start(start_args(root, allow_unmerged_head=True, from_base=True)) == 0
    printed = capsys.readouterr().out

    origin = load_yaml(root / ORIGIN_FILE)
    assert origin["override"] == "allow-unmerged-head", "what the operator asked for is kept"
    assert origin["override_exercised"] is False, "and it is recorded as having done nothing"
    assert "has no effect together with --from-base" in printed, printed


def test_an_override_that_did_something_says_so(tmp_path: Path) -> None:
    """The other side, so the field above cannot be satisfied by always writing False."""
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)

    assert command_start(start_args(root, allow_unmerged_head=True)) == 0

    origin = load_yaml(root / ORIGIN_FILE)
    assert origin["override"] == "allow-unmerged-head"
    assert origin["override_exercised"] is True


def test_status_reports_whether_the_override_was_exercised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A field no command prints is a field the operator has to know to look for."""
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)
    assert command_start(start_args(root, allow_unmerged_head=True, from_base=True)) == 0
    capsys.readouterr()

    assert command_status(status_args(root)) == 0
    printed = capsys.readouterr().out

    assert "branch_override: allow-unmerged-head" in printed, printed
    assert "branch_override_exercised: False" in printed, printed
