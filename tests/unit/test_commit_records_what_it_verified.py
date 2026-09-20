"""The commit that `prepare` measured is the one the state calls verified.

`prepare` runs the gates against the working tree; `commit` turns that exact
tree into a commit. Before this, the commit left `last_verified_commit` behind,
so the next `verify` failed for bookkeeping reasons and the only way forward
was editing the state by hand -- which is how a state file starts claiming
what nobody measured.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from engineering_playbook.core import load_yaml, write_yaml_atomic
from engineering_playbook.delivery import STATE_FILE, record_verified_commit


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def project_at(root: Path, status: str, verified: str | None) -> str:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "first")
    state_path = root / STATE_FILE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(
        state_path,
        {
            "schema_version": "1.0.0",
            "status": status,
            "last_verified_commit": verified,
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )
    return git(root, "rev-parse", "HEAD")


def test_a_verified_state_moves_to_the_commit_just_made(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    head = project_at(root, "verified", "0000000000000000000000000000000000000000")

    record_verified_commit(root, head)

    assert load_yaml(root / STATE_FILE)["last_verified_commit"] == head


def test_an_unverified_state_is_left_alone(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    head = project_at(root, "in_progress", None)

    record_verified_commit(root, head)

    assert load_yaml(root / STATE_FILE)["last_verified_commit"] is None


def test_a_state_already_pointing_there_is_not_rewritten(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    head = project_at(root, "converged", None)
    write_yaml_atomic(
        root / STATE_FILE,
        {
            "schema_version": "1.0.0",
            "status": "converged",
            "last_verified_commit": head,
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    record_verified_commit(root, head)

    assert load_yaml(root / STATE_FILE)["updated_at"] == "2026-01-01T00:00:00Z"


def test_a_project_without_a_state_file_is_not_an_error(tmp_path: Path) -> None:
    root = tmp_path / "bare"
    root.mkdir()

    record_verified_commit(root, "0" * 40)

    assert not (root / STATE_FILE).exists()
