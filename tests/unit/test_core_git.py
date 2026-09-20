from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from engineering_playbook.core import (
    GitUnavailableError,
    git_branch,
    git_capture,
    git_head,
    git_parent,
    git_ref_exists,
    git_status,
)


def init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def commit(root: Path, message: str) -> None:
    (root / f"{message}.txt").write_text(message, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)


# --- git_capture: a real failure raises, it is never folded into "" -----------------------


def test_git_capture_raises_on_a_real_error(tmp_path: Path) -> None:
    # tmp_path is not a git repository at all -- this is not "no answer yet", it is git
    # refusing to run the command, and that must surface, not disappear into "".
    with pytest.raises(GitUnavailableError):
        git_capture(tmp_path, "status", "--short")


def test_git_capture_returns_stdout_on_success(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    output = git_capture(tmp_path, "rev-parse", "--verify", "HEAD")
    assert len(output) == 40


# --- git_ref_exists: the boundary between "not yet" and "cannot answer" -------------------


def test_git_ref_exists_is_false_for_head_in_an_empty_repository(tmp_path: Path) -> None:
    init_repo(tmp_path)
    assert git_ref_exists(tmp_path, "HEAD") is False


def test_git_ref_exists_is_true_once_head_resolves(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    assert git_ref_exists(tmp_path, "HEAD") is True


def test_git_ref_exists_raises_on_a_real_error_not_false(tmp_path: Path) -> None:
    # A directory that is not a git repository at all must not be reported the same as an
    # empty repository whose HEAD has not been born yet -- one is a state, the other a fault.
    with pytest.raises(GitUnavailableError):
        git_ref_exists(tmp_path, "HEAD")


# --- git_head / git_parent: the legitimate "not yet" is a value, the fault is an exception --


def test_git_head_is_unborn_in_an_empty_repository(tmp_path: Path) -> None:
    init_repo(tmp_path)
    assert git_head(tmp_path) == "unborn"


def test_git_head_raises_on_a_real_error_instead_of_reporting_unborn(tmp_path: Path) -> None:
    # This is the distinction the fix exists for: a directory with no git repository at all
    # must not be reported as "unborn" -- that word is reserved for a repository that answered
    # and had nothing yet, not for a git that could not answer at all.
    with pytest.raises(GitUnavailableError):
        git_head(tmp_path)


def test_git_head_resolves_once_a_commit_exists(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    assert len(git_head(tmp_path)) == 40


def test_git_parent_is_unborn_with_a_single_commit(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    assert git_parent(tmp_path) == "unborn"


def test_git_parent_resolves_with_two_commits(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    commit(tmp_path, "second")
    assert len(git_parent(tmp_path)) == 40


# --- git_branch: detached HEAD is a real, successful, empty answer -------------------------


def test_git_branch_is_unknown_on_detached_head_without_raising(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    commit(tmp_path, "second")
    head = git_capture(tmp_path, "rev-parse", "--verify", "HEAD^")
    subprocess.run(["git", "checkout", "-q", head], cwd=tmp_path, check=True)
    assert git_branch(tmp_path) == "unknown"


def test_git_branch_raises_on_a_real_error(tmp_path: Path) -> None:
    with pytest.raises(GitUnavailableError):
        git_branch(tmp_path)


# --- git_status: no branch/commit special-casing needed, it works before the first commit --


def test_git_status_works_before_the_first_commit(tmp_path: Path) -> None:
    init_repo(tmp_path)
    (tmp_path / "untracked.txt").write_text("x", encoding="utf-8")
    assert git_status(tmp_path) == ["?? untracked.txt"]


def test_git_status_raises_on_a_real_error(tmp_path: Path) -> None:
    with pytest.raises(GitUnavailableError):
        git_status(tmp_path)
