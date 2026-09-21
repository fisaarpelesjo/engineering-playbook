"""Issue #12 / FR-001 / AC-001 / T303: `command_commit` used to create the content
commit and only THEN call `record_verified_commit`, which rewrote `.project/state.yml`
-- leaving every slice's working tree dirty by construction, with the operator having
to recognize and discard that dirt by hand (measured seven times on 2026-09-20).

`command_commit` now folds that write into a second, minimal commit created in the same
call, so the working tree the operator is handed back is clean and the end state needs
no interpretation.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from engineering_playbook.core import load_yaml, write_yaml_atomic
from engineering_playbook.delivery import (
    PREPARE_FILE,
    STATE_FILE,
    command_commit,
    delivery_state,
)


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def git_porcelain(root: Path) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=True
    ).stdout


def set_up_ready_to_commit(root: Path) -> str:
    """A repo, on `main`, with a `converged` state and a fresh, approved `prepare`
    pointing at the current HEAD -- everything `command_commit` requires to proceed,
    and `record_verified_commit` requires to actually write `state.yml`.
    """
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / ".gitignore").write_text(".project/delivery/\n", encoding="utf-8")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    write_yaml_atomic(
        root / STATE_FILE,
        {
            "schema_version": "1.0.0",
            "status": "converged",
            "updated_at": "2026-01-01T00:00:00Z",
            "last_verified_commit": None,
            "last_verified_tree": None,
        },
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    head = git(root, "rev-parse", "HEAD")

    write_yaml_atomic(
        root / PREPARE_FILE,
        delivery_state(root, "feat: add a file", "body text", ["b.txt"]),
    )
    prepare = load_yaml(root / PREPARE_FILE)
    prepare["status"] = "approved"
    prepare["head"] = head
    prepare["branch"] = "main"
    write_yaml_atomic(root / PREPARE_FILE, prepare)
    return head


def test_after_a_full_commit_cycle_the_tree_is_declared_and_clean(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    base_head = set_up_ready_to_commit(root)
    (root / "b.txt").write_text("feature\n", encoding="utf-8")
    git(root, "add", "-A")

    exit_code = command_commit(argparse.Namespace(root=root, message=None))

    assert exit_code == 0
    assert git_porcelain(root) == "", (
        "the working tree was left dirty after a full commit cycle -- issue #12, the "
        "exact defect this test measures"
    )

    state = load_yaml(root / STATE_FILE)
    log = git(root, "log", "--oneline", f"{base_head}..HEAD").splitlines()
    assert len(log) == 2, f"expected a content commit plus a bookkeeping commit, got: {log}"
    content_commit = git(root, "rev-parse", "HEAD^")
    assert state["last_verified_commit"] == content_commit
    assert state["last_verified_tree"] == git(root, "rev-parse", f"{content_commit}^{{tree}}")


def test_when_nothing_needed_recording_no_bookkeeping_commit_is_made(tmp_path: Path) -> None:
    """`record_verified_commit` is a no-op when `state.status` is not verified/converged/
    done; `command_commit` must not manufacture an empty bookkeeping commit in that case.
    """
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / ".gitignore").write_text(".project/delivery/\n", encoding="utf-8")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    write_yaml_atomic(
        root / STATE_FILE,
        {"schema_version": "1.0.0", "status": "in_progress", "updated_at": "2026-01-01T00:00:00Z"},
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    head = git(root, "rev-parse", "HEAD")
    write_yaml_atomic(
        root / PREPARE_FILE, delivery_state(root, "feat: add a file", "body text", ["b.txt"])
    )
    prepare = load_yaml(root / PREPARE_FILE)
    prepare["status"] = "approved"
    prepare["head"] = head
    prepare["branch"] = "main"
    write_yaml_atomic(root / PREPARE_FILE, prepare)
    (root / "b.txt").write_text("feature\n", encoding="utf-8")
    git(root, "add", "-A")

    exit_code = command_commit(argparse.Namespace(root=root, message=None))

    assert exit_code == 0
    log = git(root, "log", "--oneline", f"{head}..HEAD").splitlines()
    assert len(log) == 1, f"expected exactly one commit (no bookkeeping needed), got: {log}"
    assert git_porcelain(root) == ""
