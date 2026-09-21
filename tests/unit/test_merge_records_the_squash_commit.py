"""`merge` names the squash commit GitHub made, not the branch tip it erased.

`gh pr merge --auto --squash` creates a NEW commit on main; the branch tip that
used to be written to `last_verified_commit` is not in main's history once the
squash lands, so `git merge-base --is-ancestor <that sha> origin/main` answers
NAO and the next `verify`/`resume` on main reports a material divergence for
bookkeeping reasons alone. Measured on two real pull requests (PR 5 and PR 6):
main HEAD = 8db0c1f, state.last_verified_commit = 2af1716 (the branch tip),
and `git merge-base --is-ancestor 2af1716 origin/main` said NAO.

The same two pull requests also measured a second defect, issue #18: the tree was
already dirty before `merge` ever ran -- `publish` had already written
`.project/state.yml` -- so `gh pr merge --auto --squash --delete-branch` failed
with "Your local changes to the following files would be overwritten by
checkout ... Aborting" while trying to check out main to delete the branch,
even though the squash merge had already succeeded on the server. `command_merge`
returned that non-zero exit code as if the merge itself had failed, so
`record_merge_commit` was never reached and the squash SHA was never recorded.
Measured on PR #17: `gh pr merge` exited non-zero while `gh pr view --json
state,mergeCommit` for the same branch read `MERGED` on the server.
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


@pytest.fixture(autouse=True)
def a_signed_verdict_covers_this_content(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #24 added a precondition ahead of every merge: the content being integrated must
    carry a verdict signed by the workflow identity (`delivery.signed_verdict_refusal`). These
    tests are about what `merge` RECORDS once it runs, so that precondition is satisfied here
    rather than exercised -- `test_signed_verdict_leaves_the_tree.py` owns the gate itself,
    including the two ways it refuses.
    """

    def signed(_root: Path, tree: str, _slug: str | None = None) -> tuple[bool, str]:
        return True, f"signed verdict for {tree}"

    def public_repository(_root: Path) -> tuple[str, bool]:
        return "owner/name", True

    monkeypatch.setattr("engineering_playbook.delivery.attestation_covers_tree", signed)
    monkeypatch.setattr("engineering_playbook.delivery.repository_identity", public_repository)


def gh_fake_run(
    calls: list[list[str]],
    *,
    merged: bool,
    merge_commit: str | None,
    merge_returncode: int = 0,
    merge_stderr: str = "",
):
    """A stand-in for `delivery.run` that never shells out to a real `gh` or `git`."""

    def fake(root: Path, cmd_args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd_args)
        if cmd_args[:3] == ["gh", "pr", "view"] and "title,number,headRefOid" in cmd_args:
            # `headRefOid` is deliberately absent from the payload: the gate then measures the
            # local HEAD, which is what these tests check out. `headRefOid` being present and
            # DIFFERENT is its own scenario, owned by
            # test_signed_verdict_leaves_the_tree.py, in
            # `test_the_gate_measures_the_head_the_server_will_integrate`.
            return subprocess.CompletedProcess(
                cmd_args, 0, json.dumps({"title": "feat: example", "number": 1}), ""
            )
        if cmd_args[:3] == ["gh", "pr", "merge"]:
            if merge_returncode != 0:
                return subprocess.CompletedProcess(cmd_args, merge_returncode, "", merge_stderr)
            return subprocess.CompletedProcess(cmd_args, 0, "Merge activated.", "")
        if cmd_args[:3] == ["gh", "pr", "view"] and "state,mergeCommit" in cmd_args:
            payload = {
                "state": "MERGED" if merged else "OPEN",
                "mergeCommit": {"oid": merge_commit} if merge_commit else None,
            }
            return subprocess.CompletedProcess(cmd_args, 0, json.dumps(payload), "")
        if cmd_args[:2] == ["git", "fetch"]:
            return subprocess.CompletedProcess(cmd_args, 0, "", "")
        if cmd_args[:4] == ["git", "push", "origin", "--delete"]:
            # Deleting the remote branch needs no local checkout, unlike `--delete-branch`
            # passed straight to `gh pr merge` -- see the module docstring.
            return subprocess.CompletedProcess(cmd_args, 0, "", "")
        if cmd_args[:1] == ["uv"]:
            return subprocess.CompletedProcess(cmd_args, 0, "", "")
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


CHECKOUT_STDERR = (
    "error: Your local changes to the following files would be overwritten by checkout:\n"
    "\t.project/state.yml\nAborting"
)


def test_a_successful_server_merge_exits_zero_even_when_gh_pr_merge_itself_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issue #18, measured on PR #17: `gh pr merge` itself exited non-zero -- not a later,
    separate cleanup step -- because `publish` had already dirtied the tree before `merge`
    ever ran, and the checkout `--delete-branch` needs choked on it. This is what the old
    version of this test modeled wrong: it made `scripts/checkpoint.py` (run AFTER `gh pr
    merge`) fail, so `gh pr merge` itself always exited 0 and the exact failure that
    reached production -- `gh pr merge` returning non-zero for a merge that had already
    succeeded on the server -- was never exercised.
    """
    root = tmp_path / "repo"
    repo_on_a_pull_request_branch(root)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        gh_fake_run(
            calls,
            merged=True,
            merge_commit=SQUASH_COMMIT,
            merge_returncode=1,
            merge_stderr=CHECKOUT_STDERR,
        ),
    )

    exit_code = command_merge(args_for(root))

    assert exit_code == 0
    state = load_yaml(root / STATE_FILE)
    assert state["last_verified_commit"] == SQUASH_COMMIT
    # The PR's own state -- not `gh pr merge`'s exit code -- is what decided this was a
    # success; a real failure (below) still returns non-zero from the very same call.
    merge_index = next(i for i, c in enumerate(calls) if c[:3] == ["gh", "pr", "merge"])
    checkpoint_index = next(i for i, c in enumerate(calls) if c[:1] == ["uv"])
    assert checkpoint_index > merge_index


def test_a_gh_pr_merge_failure_that_really_did_not_merge_stays_a_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other side of issue #18: a non-zero `gh pr merge` must not be waved through as
    success just because *some* non-zero exit can mean "already merged, cleanup failed".
    When the pull request itself is not MERGED, this is a real failure and nothing is
    recorded.
    """
    root = tmp_path / "repo"
    branch_tip = repo_on_a_pull_request_branch(root)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        gh_fake_run(
            calls,
            merged=False,
            merge_commit=None,
            merge_returncode=1,
            merge_stderr="error: GraphQL: Pull request is not mergeable",
        ),
    )

    exit_code = command_merge(args_for(root))

    assert exit_code != 0
    assert not any(c[:2] == ["git", "fetch"] for c in calls)
    state = load_yaml(root / STATE_FILE)
    assert state["last_verified_commit"] == branch_tip


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
