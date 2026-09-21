"""Issue #13 / FR-002 / AC-002 / T304: `prepare` records HEAD, then generates a
checkpoint of its own (`scripts/checkpoint.py`, run at the end of `command_prepare`).
If that checkpoint is later committed on its own, HEAD moves for a reason entirely
internal to the pipeline -- yet `prepare_is_fresh` used to answer with the exact same
generic "prepare is obsolete: HEAD changed" a real content change would also produce.

`prepare_is_fresh` now names the self-invalidation explicitly, with the corrective
action, when every commit between the recorded HEAD and the current one only touched
`.project/checkpoints/` or `.project/state.yml` -- and still uses the generic message
when real content changed too, because that is not purely prepare's own doing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from engineering_playbook.core import write_yaml_atomic
from engineering_playbook.delivery import PREPARE_FILE, prepare_is_fresh


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def init_repo_with_prepare(root: Path) -> str:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / ".gitignore").write_text(".project/delivery/\n", encoding="utf-8")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    head = git(root, "rev-parse", "HEAD")
    write_yaml_atomic(
        root / PREPARE_FILE,
        {
            "schema_version": "1.0.0",
            "status": "approved",
            "branch": "main",
            "head": head,
            "title": "feat: add a file",
            "body": "body",
        },
    )
    return head


def test_a_checkpoint_only_commit_is_named_as_self_invalidation(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo_with_prepare(root)

    checkpoint_path = root / ".project" / "checkpoints" / "CP-20260921-aaaaaaaa.yml"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text("checkpoint_id: CP-20260921-aaaaaaaa\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: checkpoint from prepare")

    fresh, reason = prepare_is_fresh(root)

    assert fresh is False
    assert "its own checkpoint step" in reason, (
        f"expected the specific self-invalidation message naming a corrective action, "
        f"got: {reason!r}"
    )
    assert "scripts/delivery.py prepare" in reason


def test_a_state_yml_only_commit_is_also_named_as_self_invalidation(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo_with_prepare(root)
    (root / ".project" / "state.yml").parent.mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(
        root / ".project" / "state.yml",
        {"schema_version": "1.0.0", "status": "in_progress", "updated_at": "x"},
    )
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore: checkpoint state bookkeeping")

    _fresh, reason = prepare_is_fresh(root)

    assert "its own checkpoint step" in reason


def test_a_real_content_change_keeps_the_generic_message(tmp_path: Path) -> None:
    """Adversarial case: mixed changes (bookkeeping AND real content) are NOT
    misreported as self-invalidation -- the staleness has a genuine cause too.
    """
    root = tmp_path / "repo"
    init_repo_with_prepare(root)

    checkpoint_path = root / ".project" / "checkpoints" / "CP-20260921-bbbbbbbb.yml"
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text("checkpoint_id: CP-20260921-bbbbbbbb\n", encoding="utf-8")
    (root / "b.txt").write_text("someone kept working\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "feat: real content change alongside a checkpoint")

    fresh, reason = prepare_is_fresh(root)

    assert fresh is False
    assert reason == "prepare is obsolete: HEAD changed"


def test_a_recorded_head_this_clone_never_had_falls_back_to_the_generic_message(
    tmp_path: Path,
) -> None:
    """`git diff` needs the recorded HEAD to exist locally; a prepare file copied from
    elsewhere naming an unknown commit must not raise, it must just fall back."""
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    write_yaml_atomic(
        root / PREPARE_FILE,
        {
            "schema_version": "1.0.0",
            "status": "approved",
            "branch": "main",
            "head": "0" * 40,
            "title": "feat: add a file",
            "body": "body",
        },
    )

    fresh, reason = prepare_is_fresh(root)

    assert fresh is False
    assert reason == "prepare is obsolete: HEAD changed"
