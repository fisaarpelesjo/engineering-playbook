"""Issue #30: `last_verified_commit` cannot survive a squash by construction -- no commit can
name the SHA that only exists once the squash creates it. Measured on runs 35526666891 and
35527933400: `git merge-base --is-ancestor <recorded> origin/main` answered NAO on `main` right
after a clean squash merge.

A commit is `tree + parent + author + message`; only the tree is a pure function of content.
This suite proves the claim directly, in a disposable repository, with no mocking of `git`
itself: it builds a branch, forges the exact commit a squash produces with `git commit-tree`,
and shows the old commit no longer being an ancestor while the tree still matches.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from engineering_playbook.core import verify_root, write_yaml_atomic

STATE_FILE = ".project/state.yml"


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def git_returncode(root: Path, *args: str) -> int:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True).returncode


def repo_with_a_squashed_branch(root: Path) -> tuple[str, str, str]:
    """A repository shaped exactly like a squash merge: `main` HEAD is a NEW commit `git
    commit-tree` forged, with the same tree as a branch tip that is no longer its ancestor.

    Returns `(branch_tip, branch_tree, squashed_head)`.
    """
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    base_sha = git(root, "rev-parse", "HEAD")

    git(root, "switch", "-qc", "feat/1-example")
    (root / "b.txt").write_text("feature\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "feature")
    branch_tip = git(root, "rev-parse", "HEAD")
    branch_tree = git(root, "rev-parse", f"{branch_tip}^{{tree}}")

    # Forge the squash GitHub would have created: a NEW commit id, parented on the
    # pre-branch `main` tip, carrying the branch's tree verbatim -- not a real `git merge
    # --squash`, but object-for-object what one produces, without a GitHub round trip.
    squashed_head = git(root, "commit-tree", branch_tree, "-p", base_sha, "-m", "squash: feature")
    git(root, "switch", "-q", "main")
    git(root, "reset", "-q", "--hard", squashed_head)
    return branch_tip, branch_tree, squashed_head


def write_state(root: Path, **fields: object) -> None:
    write_yaml_atomic(
        root / STATE_FILE,
        {
            "schema_version": "1.0.0",
            "status": "converged",
            "updated_at": "2026-01-01T00:00:00Z",
            **fields,
        },
    )


def test_the_squash_breaks_ancestry_the_precondition_this_suite_measures(
    tmp_path: Path,
) -> None:
    """Confirms the forged repository really does reproduce the defect's precondition,
    so the assertions below are not testing a scenario that cannot occur in production.
    """
    root = tmp_path / "repo"
    branch_tip, branch_tree, _squashed_head = repo_with_a_squashed_branch(root)

    assert git_returncode(root, "merge-base", "--is-ancestor", branch_tip, "HEAD") != 0
    assert git(root, "rev-parse", "HEAD^{tree}") == branch_tree


def test_a_tree_recorded_before_the_squash_still_verifies_after_it(tmp_path: Path) -> None:
    """THE central claim: a state that recorded the pre-squash tree still gates green after
    the squash, even though the commit it was originally measured against is gone from
    history. This is the exact scenario `last_verified_commit` cannot survive.
    """
    root = tmp_path / "repo"
    branch_tip, branch_tree, _squashed_head = repo_with_a_squashed_branch(root)
    write_state(
        root,
        last_verified_commit=branch_tip,  # stale: no longer HEAD or a parent of it
        last_verified_tree=branch_tree,  # still HEAD's tree
    )

    result = verify_root(root)

    assert not any("Verified/converged state requires" in error for error in result.errors), (
        f"the tree-based gate rejected a tree that matches HEAD: {result.errors}"
    )


def test_a_tree_that_was_never_verified_is_still_rejected(tmp_path: Path) -> None:
    """The other side: this is not a gate that has quietly stopped checking anything.
    A `last_verified_tree` that matches neither HEAD nor a parent tree must still fail.
    """
    root = tmp_path / "repo"
    repo_with_a_squashed_branch(root)
    write_state(root, last_verified_commit=None, last_verified_tree="0" * 40)

    result = verify_root(root)

    assert any("Verified/converged state requires" in error for error in result.errors), (
        f"the tree-based gate accepted a tree that never matched HEAD: {result.errors}"
    )


def test_derived_project_without_ci_keeps_the_commit_based_gate(tmp_path: Path) -> None:
    """Owner decision (issue #30): a derived project declaring `ci: none` has no Actions
    workflow and no workflow identity, so it keeps the pre-existing commit/ancestry
    mechanism unchanged -- it must not be silently switched onto the tree it never had a
    CI run to measure.
    """
    root = tmp_path / "repo"
    branch_tip, _branch_tree, squashed_head = repo_with_a_squashed_branch(root)
    lock_path = root / ".project/playbook.lock.yml"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(lock_path, {"playbook": {"ci": "none"}})

    # A last_verified_tree that matches HEAD is IGNORED for a ci:none project: only the old
    # commit-based mechanism governs, so this must still fail even though the tree matches.
    squashed_tree = git(root, "rev-parse", f"{squashed_head}^{{tree}}")
    write_state(
        root,
        last_verified_commit=branch_tip,  # stale, exactly the squash-survival defect
        last_verified_tree=squashed_tree,
    )

    result = verify_root(root)

    assert any("last_verified_commit" in error for error in result.errors), (
        f"a ci:none derived project stopped using the commit-based gate: {result.errors}"
    )
