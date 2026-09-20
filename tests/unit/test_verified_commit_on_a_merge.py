"""A state verified on the branch stays verified on the pull request merge.

GitHub builds a pull request on a merge commit whose FIRST parent is the base
branch and whose second is the branch under review. Reading only `HEAD^` asks
about the base, so the gate used to go red on every pull request whose state
had been verified on the branch -- red for a reason unrelated to the work.
This was measured on run 35488539941 of this repository: the push job passed
and the pull_request job failed, on the same commit.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from engineering_playbook.core import git_head, git_parents


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def repository_with_a_merge(root: Path) -> tuple[str, str]:
    """A merge of a branch into main; returns (branch tip, merge commit)."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")

    git(root, "switch", "-qc", "feature")
    (root / "feature.txt").write_text("feature\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "feature")
    branch_tip = git(root, "rev-parse", "HEAD")

    git(root, "switch", "-q", "main")
    (root / "other.txt").write_text("other\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "other")
    git(root, "merge", "-q", "--no-ff", "-m", "merge", "feature")
    return branch_tip, git(root, "rev-parse", "HEAD")


def test_the_branch_tip_is_a_parent_of_the_merge(tmp_path: Path) -> None:
    branch_tip, merge = repository_with_a_merge(tmp_path / "repo")
    root = tmp_path / "repo"

    parents = git_parents(root)

    assert git_head(root) == merge
    assert len(parents) == 2
    assert branch_tip in parents
    assert branch_tip != parents[0]  # the first parent is the base branch


def test_a_repository_without_commits_has_no_parents(tmp_path: Path) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")

    assert git_parents(root) == []


def test_a_first_commit_has_no_parents(tmp_path: Path) -> None:
    root = tmp_path / "one"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "first")

    assert git_parents(root) == []
