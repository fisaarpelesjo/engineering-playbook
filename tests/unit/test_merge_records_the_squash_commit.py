"""`merge` names the squash commit GitHub made, not the branch tip it erased.

`gh pr merge --auto --squash` creates a NEW commit on main; the branch tip that
used to be written to `last_verified_commit` is not in main's history once the
squash lands, so `git merge-base --is-ancestor <that sha> origin/main` answers
NAO and the next `verify`/`resume` on main reports a material divergence for
bookkeeping reasons alone. Measured on two real pull requests (PR 5 and PR 6):
main HEAD = 8db0c1f, state.last_verified_commit = 2af1716 (the branch tip),
and `git merge-base --is-ancestor 2af1716 origin/main` said NAO.

The same two pull requests also measured a second defect: `command_merge` ran
`scripts/checkpoint.py` -- which writes `.project/state.yml` -- BEFORE
`gh pr merge --delete-branch`, so the tree was already dirty when `--delete-
branch` tried to switch to main, and `gh` failed with "Your local changes to
the following files would be overwritten by checkout ... Aborting" even
though the squash merge had already succeeded on the server.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

from engineering_playbook.core import load_yaml, write_yaml_atomic
from engineering_playbook.delivery import STATE_FILE, command_merge

BRANCH = "feat/1-example"
SQUASH_COMMIT = "a" * 40


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def repo_on_a_pull_request_branch(root: Path) -> str:
    """A repository on `BRANCH`, with a `verified` state pointing at the branch tip --

    exactly what `command_commit`/`record_verified_commit` leaves behind on the branch,
    before any merge to main happens.
    """
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    workflow = root / ".github/workflows/quality.yml"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text("name: quality\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "switch", "-qc", BRANCH)
    (root / "feature.txt").write_text("feature\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "feature")
    branch_tip = git(root, "rev-parse", "HEAD")
    write_yaml_atomic(
        root / STATE_FILE,
        {
            "schema_version": "1.0.0",
            "status": "verified",
            "last_verified_commit": branch_tip,
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    return branch_tip


def args_for(root: Path) -> argparse.Namespace:
    return argparse.Namespace(root=root, auto=True, yes_remote=True)


def gh_fake_run(calls: list[list[str]], *, merged: bool, merge_commit: str | None):
    """A stand-in for `delivery.run` that never shells out to a real `gh` or `git fetch`."""

    def fake(root: Path, cmd_args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd_args)
        if cmd_args[:3] == ["gh", "pr", "view"] and "title,number" in cmd_args:
            return subprocess.CompletedProcess(
                cmd_args, 0, json.dumps({"title": "feat: example", "number": 1}), ""
            )
        if cmd_args[:3] == ["gh", "pr", "merge"]:
            return subprocess.CompletedProcess(cmd_args, 0, "Merge activated.", "")
        if cmd_args[:3] == ["gh", "pr", "view"] and "state,mergeCommit" in cmd_args:
            payload = {
                "state": "MERGED" if merged else "OPEN",
                "mergeCommit": {"oid": merge_commit} if merge_commit else None,
            }
            return subprocess.CompletedProcess(cmd_args, 0, json.dumps(payload), "")
        if cmd_args[:2] == ["git", "fetch"]:
            return subprocess.CompletedProcess(cmd_args, 0, "", "")
        if cmd_args[:1] == ["uv"]:
            # The local cleanup step: made to fail, the way a dirty tree made it fail on
            # the two pull requests this was measured against. A successful server merge
            # must not turn into a non-zero exit because of this.
            return subprocess.CompletedProcess(cmd_args, 1, "", "checkpoint refused: dirty tree")
        raise AssertionError(f"unexpected command: {cmd_args}")

    return fake


def test_a_squash_merge_records_the_squash_commit_not_the_branch_tip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    branch_tip = repo_on_a_pull_request_branch(root)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        gh_fake_run(calls, merged=True, merge_commit=SQUASH_COMMIT),
    )

    exit_code = command_merge(args_for(root))

    assert exit_code == 0
    state = load_yaml(root / STATE_FILE)
    assert state["last_verified_commit"] == SQUASH_COMMIT
    assert state["last_verified_commit"] != branch_tip


def test_a_successful_server_merge_exits_zero_even_when_local_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    repo_on_a_pull_request_branch(root)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        gh_fake_run(calls, merged=True, merge_commit=SQUASH_COMMIT),
    )

    exit_code = command_merge(args_for(root))

    assert exit_code == 0
    # The local cleanup command must run only after `gh pr merge` has already been asked
    # to merge and delete the branch -- never before, which is what dirtied the tree the
    # `--delete-branch` checkout needed clean.
    merge_index = next(i for i, c in enumerate(calls) if c[:3] == ["gh", "pr", "merge"])
    checkpoint_index = next(i for i, c in enumerate(calls) if c[:1] == ["uv"])
    assert checkpoint_index > merge_index


def test_a_queued_auto_merge_records_nothing_and_is_distinct_from_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    branch_tip = repo_on_a_pull_request_branch(root)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        gh_fake_run(calls, merged=False, merge_commit=None),
    )

    exit_code = command_merge(args_for(root))

    assert exit_code == 2
    assert exit_code != 1
    assert not any(c[:2] == ["git", "fetch"] for c in calls)
    state = load_yaml(root / STATE_FILE)
    assert state["last_verified_commit"] == branch_tip
