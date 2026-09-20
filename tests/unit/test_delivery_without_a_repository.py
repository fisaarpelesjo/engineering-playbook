"""A delivery command in a project whose repository vanished refuses, cleanly.

`prepare_is_fresh` asks git for HEAD and for the branch. When the repository
is gone -- a clone deleted, a `.git` removed, a prepare file left behind --
git answers with an error, and that error used to reach the user as a
traceback from whichever command happened to ask first.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def run_delivery(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts/delivery.py"), "--root", str(root), *args],
        capture_output=True,
        text=True,
        cwd=root,
        check=False,
    )


def project_whose_repository_vanished(root: Path) -> Path:
    """A real bootstrapped project, its `.git` removed, a prepare left behind."""
    target = root / "project"
    created = subprocess.run(
        [sys.executable, str(REPO / "scripts/bootstrap.py"), "--target", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    shutil.rmtree(target / ".git", ignore_errors=True)
    prepare = target / ".project/delivery"
    prepare.mkdir(parents=True, exist_ok=True)
    (prepare / "prepare.yml").write_text(
        "schema_version: 1.0.0\nstatus: approved\nbranch: main\nhead: deadbeef\n",
        encoding="utf-8",
    )
    return target


def test_status_says_it_could_not_check_instead_of_raising(tmp_path: Path) -> None:
    target = project_whose_repository_vanished(tmp_path)

    result = run_delivery(target, "status")

    assert "Traceback" not in result.stderr
    assert "git did not answer" in result.stdout


def test_commit_refuses_without_a_traceback(tmp_path: Path) -> None:
    target = project_whose_repository_vanished(tmp_path)

    result = run_delivery(target, "commit")

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "git did not answer" in (result.stdout + result.stderr)
