"""FR-004 / AC-004 / T302: a checkpoint identifier reused with DIFFERENT content on
another local branch is rejected by an executable control (`verify`), instead of
surfacing later as a raw add/add conflict during a rebase (issue #11).

NFR-002 requires the control to tolerate the pre-existing `CP-<date>-<NNN>` filename
shape without treating it as a defect, and to tolerate a genuinely identical duplicate
(the historical measurement in spec 004 found six identifiers assigned by more than one
commit, every one byte-identical) -- only DIVERGENT content under the same name is a
collision.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from engineering_playbook.core import checkpoint_id_collisions, verify_root

REAL_CHECKPOINT_SCHEMA = (
    Path(__file__).resolve().parents[2] / ".project" / "schemas" / "checkpoint.schema.json"
)


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")


def commit_checkpoint(root: Path, branch: str, filename: str, content: str) -> None:
    git(root, "switch", "-qc", branch)
    path = root / ".project" / "checkpoints" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", f"checkpoint on {branch}")


def test_divergent_content_under_the_same_id_is_rejected(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    commit_checkpoint(
        root, "feat/1-a", "CP-20260919-001.yml", "checkpoint_id: CP-20260919-001\nbranch: a\n"
    )
    git(root, "switch", "-q", "main")
    commit_checkpoint(
        root, "feat/2-b", "CP-20260919-001.yml", "checkpoint_id: CP-20260919-001\nbranch: b\n"
    )
    git(root, "switch", "-q", "feat/1-a")  # only THIS branch's copy exists in the working tree

    findings = checkpoint_id_collisions(root)

    assert findings, (
        "a checkpoint id shared with different content on another local branch was not flagged"
    )
    assert "CP-20260919-001.yml" in findings[0]

    schema_dst = root / ".project" / "schemas" / "checkpoint.schema.json"
    schema_dst.parent.mkdir(parents=True, exist_ok=True)
    schema_dst.write_bytes(REAL_CHECKPOINT_SCHEMA.read_bytes())
    result = verify_root(root)
    assert any("collision" in error.lower() for error in result.errors), result.errors


def test_identical_content_under_the_same_id_is_tolerated(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    same_content = "checkpoint_id: CP-20260919-002\nbranch: shared\n"
    commit_checkpoint(root, "feat/3-a", "CP-20260919-002.yml", same_content)
    git(root, "switch", "-q", "main")
    commit_checkpoint(root, "feat/4-b", "CP-20260919-002.yml", same_content)
    git(root, "switch", "-q", "feat/3-a")

    findings = checkpoint_id_collisions(root)

    assert findings == [], (
        f"byte-identical duplicates across branches must be tolerated: {findings}"
    )


def test_the_old_filename_shape_is_not_treated_as_a_defect_by_itself(tmp_path: Path) -> None:
    """NFR-002: the pre-T301 `CP-<date>-<NNN>` shape, alone with no divergence, passes."""
    root = tmp_path / "repo"
    init_repo(root)
    (root / ".project" / "checkpoints").mkdir(parents=True)
    old_style = root / ".project" / "checkpoints" / "CP-20260919-001.yml"
    old_style.write_text("checkpoint_id: CP-20260919-001\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "old-style checkpoint, single branch")

    assert checkpoint_id_collisions(root) == []


def test_no_other_local_branch_means_no_findings(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    init_repo(root)
    (root / ".project" / "checkpoints").mkdir(parents=True)

    assert checkpoint_id_collisions(root) == []
