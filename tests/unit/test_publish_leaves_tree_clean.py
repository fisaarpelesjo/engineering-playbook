"""Issue #64 / FR-001: `publish` wrote the pipeline's own records AFTER pushing, and left them
uncommitted.

This is the same defect as issue #12, one stage later. #12 closed it for `commit` (T303): the
state write is folded into a second, minimal commit so the operator is handed back a clean tree.
`publish` was never given the same treatment, so it wrote `.project/state.yml` -- the delivery
record, which cannot exist until GitHub has answered with a pull request number -- and appended a
file under `.project/checkpoints/`, both after the push and neither committed.

It is not cosmetic. `start` refuses to begin on a dirty tree, correctly, so the pipeline blocked
its own next slice. Measured while delivering #61, from a tree that `commit` had left clean:

    publish  -> M .project/state.yml, M .project/last-ci-run.yml, ?? .project/checkpoints/CP-...
    commit   -> clean
    publish  -> dirty again
    commit   -> clean
    merge    -> dirty again

The way out was committing bookkeeping by hand with an invented message, or discarding what the
pipeline had just written. Both happened twice.

WHAT THESE TESTS MEASURE is the tree AFTER the command, not the contents of any file. The defect
was never what gets written -- every one of those writes is wanted -- it is that it stays
uncommitted.

`origin` here is a real bare repository on disk, so the pushes are real pushes and the second one
can be checked on the receiving end. Only `gh` is faked.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import pytest

from engineering_playbook.core import load_yaml, write_yaml_atomic
from engineering_playbook.delivery import (
    PREPARE_FILE,
    STATE_FILE,
    command_publish,
    commit_bookkeeping,
    delivery_state,
)

BRANCH = "fix/064-example"

#: A value `scan_for_secrets` recognises, built from two halves so that no single literal
#: in this repository looks like a credential.
LOOKS_LIKE_A_CREDENTIAL = "ghp_" + "0123456789abcdefghijklmnopqrstuvwxyzAB"


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def porcelain(root: Path) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True
    ).stdout


def a_repo_ready_to_publish(tmp_path: Path) -> Path:
    """A branch with one unpublished commit, a fresh approved prepare, and a real `origin`."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)

    root = tmp_path / "repo"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / ".gitignore").write_text(".project/delivery/\n", encoding="utf-8")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    write_yaml_atomic(
        root / STATE_FILE,
        {
            "schema_version": "1.0.0",
            "status": "verified",
            "issue": 64,
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "remote", "add", "origin", str(origin))
    git(root, "push", "-q", "-u", "origin", "main")

    git(root, "switch", "-qc", BRANCH)
    (root / "feature.txt").write_text("feature\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "fix: the work itself")

    write_yaml_atomic(
        root / PREPARE_FILE,
        delivery_state(root, "fix: the work itself", "body text", ["feature.txt"]),
    )
    prepare = load_yaml(root / PREPARE_FILE)
    prepare["status"] = "approved"
    prepare["head"] = git(root, "rev-parse", "HEAD")
    prepare["branch"] = BRANCH
    write_yaml_atomic(root / PREPARE_FILE, prepare)
    (root / ".project/delivery/pr.md").write_text("## Summary\n\nCloses #64\n", encoding="utf-8")
    return root


@pytest.fixture
def gh_is_faked(monkeypatch: pytest.MonkeyPatch):
    """Only `gh` and `uv` are intercepted. Every git command, including both pushes, is real."""
    real_run = subprocess.run

    def fake(root: Path, cmd_args: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd_args[:1] == ["gh"]:
            if cmd_args[:3] == ["gh", "issue", "view"]:
                return subprocess.CompletedProcess(cmd_args, 0, json.dumps({"state": "OPEN"}), "")
            if cmd_args[:3] == ["gh", "pr", "view"]:
                payload = {"number": 72, "url": "https://example.invalid/pull/72"}
                return subprocess.CompletedProcess(cmd_args, 0, json.dumps(payload), "")
            if cmd_args[:3] == ["gh", "pr", "create"]:
                return subprocess.CompletedProcess(
                    cmd_args, 0, "https://example.invalid/pull/72", ""
                )
            return subprocess.CompletedProcess(cmd_args, 0, "", "")
        if cmd_args[:1] == ["uv"]:
            # Stands in for `scripts/checkpoint.py`, whose only relevant effect here is that it
            # appends an untracked file under `.project/checkpoints/`.
            checkpoint = root / ".project/checkpoints/CP-20260922-test.yml"
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_text("id: CP-20260922-test\n", encoding="utf-8")
            return subprocess.CompletedProcess(cmd_args, 0, "", "")
        return real_run(cmd_args, cwd=root, capture_output=True, text=True)

    monkeypatch.setattr("engineering_playbook.delivery.run", fake)


def args_for(root: Path) -> argparse.Namespace:
    return argparse.Namespace(root=root, yes_remote=True, remote="origin", base="main", force=False)


def test_after_publish_the_tree_is_clean(tmp_path: Path, gh_is_faked: None) -> None:
    """The defect, stated as the operator experiences it."""
    root = a_repo_ready_to_publish(tmp_path)
    assert porcelain(root) == "", "precondition: commit leaves a clean tree"

    exit_code = command_publish(args_for(root))

    assert exit_code == 0
    assert porcelain(root) == "", (
        "publish left the working tree dirty -- issue #64, the exact defect this test measures. "
        "`start` refuses a dirty tree, so this is the pipeline blocking its own next slice."
    )


def test_the_records_publish_wrote_are_in_a_commit_and_on_the_remote(
    tmp_path: Path, gh_is_faked: None
) -> None:
    """Clean is not enough: the records have to have been COMMITTED, not discarded, and the
    branch on the server has to carry them -- otherwise the next `publish` pushes them anyway.
    """
    root = a_repo_ready_to_publish(tmp_path)
    before = git(root, "rev-parse", "HEAD")

    assert command_publish(args_for(root)) == 0

    log = git(root, "log", "--oneline", f"{before}..HEAD").splitlines()
    assert len(log) == 1, f"expected exactly one bookkeeping commit, got: {log}"
    recorded = git(root, "show", "--name-only", "--format=", "HEAD").split()
    assert ".project/state.yml" in recorded
    assert any(name.startswith(".project/checkpoints/") for name in recorded), (
        f"the checkpoint publish appended is not in the bookkeeping commit: {recorded}"
    )
    assert load_yaml(root / STATE_FILE)["delivery"]["pr_number"] == 72

    # `git rev-parse origin/<branch>` reads this clone's own remote-tracking mirror, not the
    # repository that received the push. It would still bite, but the claim being made here is
    # about the receiving end, so the receiving end is what gets asked.
    origin = git(root, "remote", "get-url", "origin")
    on_the_server = subprocess.run(
        ["git", f"--git-dir={origin}", "rev-parse", BRANCH],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert git(root, "rev-parse", "HEAD") == on_the_server, (
        "the bookkeeping commit was not pushed, so the branch on the server is behind the tree "
        "that was just declared clean"
    )


def test_the_prepare_still_points_at_the_head_publish_left(
    tmp_path: Path, gh_is_faked: None
) -> None:
    """The bookkeeping commit moves HEAD, and a prepare pinned to the old one is stale.

    This is the same trap `command_commit` hit when T303 landed: the step after it refused a
    prepare that had just been used successfully. A step that only recorded what the previous
    step measured must not force the operator to repeat the one before it.
    """
    root = a_repo_ready_to_publish(tmp_path)

    assert command_publish(args_for(root)) == 0

    assert load_yaml(root / PREPARE_FILE)["head"] == git(root, "rev-parse", "HEAD")


def test_a_publish_that_recorded_nothing_makes_no_empty_commit(
    tmp_path: Path, gh_is_faked: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit nobody needed is the same nuisance pointing the other way."""
    root = a_repo_ready_to_publish(tmp_path)
    before = git(root, "rev-parse", "HEAD")
    code, committed = commit_bookkeeping(root, "chore(delivery): nothing to record")

    assert code == 0
    assert committed is False
    assert git(root, "rev-parse", "HEAD") == before
    assert porcelain(root) == ""


def test_work_the_operator_staged_is_never_swept_into_a_bookkeeping_commit(
    tmp_path: Path, gh_is_faked: None
) -> None:
    """A command that stages on the operator's behalf must not commit what they did not choose.

    Without this, `git add --` of the bookkeeping paths followed by `git commit` would carry
    anything else already in the index into a commit whose message the operator never wrote.
    """
    root = a_repo_ready_to_publish(tmp_path)
    (root / "half-finished.txt").write_text("not ready\n", encoding="utf-8")
    git(root, "add", "half-finished.txt")
    before = git(root, "rev-parse", "HEAD")

    code, committed = commit_bookkeeping(root, "chore(delivery): record the publish")

    assert code == 1
    assert committed is False
    assert git(root, "rev-parse", "HEAD") == before
    assert "half-finished.txt" in porcelain(root)


def test_work_in_progress_outside_the_index_is_left_exactly_where_it_was(
    tmp_path: Path, gh_is_faked: None
) -> None:
    """The strongest claim this file makes, and the one nothing held until review broke it.

    Every other test here starts from the clean tree `a_repo_ready_to_publish` leaves, and the
    refusal test puts its decoy in the INDEX -- which is where `commit_bookkeeping` looks. So the
    suite never once had a non-bookkeeping file that was modified-or-untracked but UNSTAGED, and
    review measured what that costs: change `git add -- *present` to `git add -A` and all five
    tests stayed green, while `publish` would sweep the operator's unfinished work into a commit
    whose message they never wrote and push it to the remote.

    A test that cannot tell `git add -- <paths>` from `git add -A` is not holding the mechanism it
    is named after.
    """
    root = a_repo_ready_to_publish(tmp_path)
    (root / "work-in-progress.txt").write_text("not ready to ship\n", encoding="utf-8")
    (root / "feature.txt").write_text("edited, not staged\n", encoding="utf-8")

    assert command_publish(args_for(root)) == 0

    recorded = git(root, "show", "--name-only", "--format=", "HEAD").split()
    assert "work-in-progress.txt" not in recorded, (
        "publish committed an untracked file the operator had not staged"
    )
    assert "feature.txt" not in recorded, (
        "publish committed an unstaged edit the operator had not chosen to commit"
    )
    assert all(name.startswith(".project/") for name in recorded), (
        f"the bookkeeping commit carries something that is not bookkeeping: {recorded}"
    )

    after = porcelain(root)
    assert "work-in-progress.txt" in after and "feature.txt" in after, (
        "the operator's work is gone from the working tree -- it was swept into the bookkeeping "
        f"commit instead of being left alone. Status after publish: {after!r}"
    )


def test_a_secret_in_the_pipelines_own_records_stops_the_commit(
    tmp_path: Path, gh_is_faked: None
) -> None:
    """This commit is pushed, so it pays the scan `commit` pays.

    `scan_for_secrets` lived only inside `command_commit`, and review measured that anything
    reaching the index through the prefix hole went to the remote unscanned.
    """
    root = a_repo_ready_to_publish(tmp_path)
    (root / ".project/state.yml").write_text(
        "schema_version: '1.0.0'\nstatus: verified\nissue: 64\n"
        # Assembled at runtime, deliberately. Written as one literal this file would itself
        # carry a credential-shaped string, and `command_commit` would refuse to commit the
        # test that proves the scan runs. Measured: it did exactly that, on the first attempt
        # to deliver this slice.
        + f"token: {LOOKS_LIKE_A_CREDENTIAL}\n",
        encoding="utf-8",
    )
    before = git(root, "rev-parse", "HEAD")

    code, committed = commit_bookkeeping(root, "chore(delivery): record the publish")

    assert code == 1
    assert committed is False
    assert git(root, "rev-parse", "HEAD") == before


def test_a_path_that_merely_begins_like_a_record_is_not_one(
    tmp_path: Path, gh_is_faked: None
) -> None:
    """Prefix is not boundary. Review broke the first version of this with four real paths.

    `.project/state.yml.bak` and `.project/checkpoints-archive/` begin with a listed string
    without being the file or the directory that string names, and each was committed AND pushed
    inside a bookkeeping commit while the docstring promised a refusal.
    """
    root = a_repo_ready_to_publish(tmp_path)
    (root / ".project/state.yml.bak").write_text("SECRET=hunter2\n", encoding="utf-8")
    (root / ".project/checkpoints-archive").mkdir(parents=True, exist_ok=True)
    (root / ".project/checkpoints-archive/old.yml").write_text("SECRET=hunter2\n", encoding="utf-8")
    git(root, "add", ".project/state.yml.bak", ".project/checkpoints-archive/old.yml")
    before = git(root, "rev-parse", "HEAD")

    code, committed = commit_bookkeeping(root, "chore(delivery): record the publish")

    assert code == 1, "a path that only starts like a record was accepted as one"
    assert committed is False
    assert git(root, "rev-parse", "HEAD") == before


def test_a_record_nested_somewhere_else_is_not_a_record(tmp_path: Path, gh_is_faked: None) -> None:
    """The boundary rule must not go the other way either: matching is anchored at the root."""
    root = a_repo_ready_to_publish(tmp_path)
    (root / "docs/.project/checkpoints").mkdir(parents=True, exist_ok=True)
    (root / "docs/.project/checkpoints/x.yml").write_text("id: x\n", encoding="utf-8")
    git(root, "add", "docs/.project/checkpoints/x.yml")
    before = git(root, "rev-parse", "HEAD")

    code, committed = commit_bookkeeping(root, "chore(delivery): record the publish")

    assert code == 1
    assert committed is False
    assert git(root, "rev-parse", "HEAD") == before
