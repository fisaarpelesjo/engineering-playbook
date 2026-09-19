from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from engineering_playbook.core import GitUnavailableError
from engineering_playbook.delivery import (
    changed_files,
    local_commits,
    remote_url,
    staged_files,
)

ROOT = Path(__file__).resolve().parents[2]


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def commit(root: Path, message: str) -> None:
    (root / f"{message}.txt").write_text(message, encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=root, check=True)


# --- "sem remote": a legitimate empty state, not a failure ---------------------------------


def test_remote_url_returns_none_when_no_remote_is_configured(tmp_path: Path) -> None:
    # `git remote get-url origin` exits 2 with "No such remote" here -- measured directly
    # (nothing was ever pushed from this repository). That is a real, common state, not a
    # git failure, so it must come back as a plain None instead of raising GitUnavailableError.
    init_repo(tmp_path)
    commit(tmp_path, "first")
    assert remote_url(tmp_path, "origin") is None


def test_remote_url_returns_the_configured_url(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.invalid/repo.git"],
        cwd=tmp_path,
        check=True,
    )
    assert remote_url(tmp_path, "origin") == "https://example.invalid/repo.git"


def test_remote_url_raises_on_a_real_error_not_none(tmp_path: Path) -> None:
    # tmp_path is not a git repository at all here (exit 128, "fatal: not a git repository")
    # -- that must not be folded into the same None a merely-unconfigured remote returns.
    with pytest.raises(GitUnavailableError):
        remote_url(tmp_path, "origin")


# --- "nada staged": exit 0 with empty stdout already means "nothing", no fallback needed ---


def test_staged_files_is_empty_without_raising_when_nothing_is_staged(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    assert staged_files(tmp_path) == []


def test_staged_files_lists_what_is_actually_staged(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    subprocess.run(["git", "add", "b.txt"], cwd=tmp_path, check=True)
    assert staged_files(tmp_path) == ["b.txt"]


def test_changed_files_is_empty_without_raising_when_nothing_changed(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    assert changed_files(tmp_path) == []


def test_staged_files_raises_on_a_real_error_not_empty(tmp_path: Path) -> None:
    # Not a git repository at all -- must surface, not read the same as "nothing staged".
    with pytest.raises(GitUnavailableError):
        staged_files(tmp_path)


def test_changed_files_raises_on_a_real_error_not_empty(tmp_path: Path) -> None:
    with pytest.raises(GitUnavailableError):
        changed_files(tmp_path)


# --- "sem commits": `base` not existing yet is the same legitimate "not yet" as unborn HEAD -


def test_local_commits_is_empty_when_the_base_branch_does_not_exist_yet(tmp_path: Path) -> None:
    # `main` has not been born (no commit at all) -- `git log main..HEAD` would answer with
    # "fatal: ambiguous argument 'main..HEAD': unknown revision" (measured, exit 128) if asked
    # directly. That is not a git failure, it is the same "not yet" `git_head` already grants
    # an unborn ref, so `local_commits` must read it that way via `git_ref_exists` and answer
    # with an empty list instead of raising.
    init_repo(tmp_path)
    assert local_commits(tmp_path, "main") == []


def test_local_commits_is_empty_with_no_divergence_from_an_existing_base(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    assert local_commits(tmp_path, "main") == []


def test_local_commits_lists_commits_ahead_of_an_existing_base(tmp_path: Path) -> None:
    init_repo(tmp_path)
    commit(tmp_path, "first")
    subprocess.run(["git", "switch", "-q", "-c", "feat/1-x"], cwd=tmp_path, check=True)
    commit(tmp_path, "second")
    assert len(local_commits(tmp_path, "main")) == 1


def test_local_commits_raises_on_a_real_error_not_empty(tmp_path: Path) -> None:
    # Not a git repository at all -- `git_ref_exists` itself cannot answer, so this must
    # raise, not be read the same as "the base branch simply is not born yet".
    with pytest.raises(GitUnavailableError):
        local_commits(tmp_path, "main")


# --- "diretorio que nao e repo git": a real failure refuses cleanly, it never crashes -------


def test_command_commit_refuses_cleanly_when_staged_files_cannot_be_measured(
    tmp_path: Path,
) -> None:
    # A corrupted index breaks `git diff --cached --name-only` for real (measured: exit 128,
    # "index file smaller than expected") while leaving `git rev-parse`/`git branch
    # --show-current` -- what `prepare_is_fresh` checks first -- answering normally. This
    # isolates the failure at the exact call `command_commit` owns (`staged_files`) instead
    # of at an earlier, unrelated git call, and proves the command prints a clear refusal
    # and exits non-zero instead of leaking a raw traceback to the user.
    init_repo(tmp_path)
    commit(tmp_path, "first")
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=tmp_path,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    prepare_dir = tmp_path / ".project/delivery"
    prepare_dir.mkdir(parents=True)
    (prepare_dir / "prepare.yml").write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0.0",
                "status": "approved",
                "branch": "main",
                "head": head,
                "title": "feat(delivery): add safe git delivery pipeline",
                "body": "body",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / ".git/index").write_text("garbage", encoding="utf-8")

    completed = run_script("scripts/delivery.py", "--root", str(tmp_path), "commit")

    assert completed.returncode == 1
    assert "Traceback" not in completed.stdout
    assert "Traceback" not in completed.stderr
    assert "git nao respondeu" in completed.stdout
    assert "arquivos staged" in completed.stdout
