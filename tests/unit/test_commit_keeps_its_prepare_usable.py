"""The step that records what the previous step measured must not undo it.

Measured on the first real use of the bookkeeping commit introduced by T303:
`commit` succeeded, and `publish` then refused with "prepare is obsolete: its own
checkpoint step moved HEAD". The signal was correct -- HEAD had moved -- but the
mover was the pipeline itself, recording a verdict it had just produced. Making
the operator run `prepare` again for that is the pipeline contradicting its own
bookkeeping, which is the defect this specification exists to remove.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from engineering_playbook.delivery import command_commit, prepare_is_fresh
from tests.unit.test_commit_leaves_tree_clean import git, set_up_ready_to_commit


def test_the_prepare_survives_the_bookkeeping_commit_it_caused(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    set_up_ready_to_commit(root)
    (root / "b.txt").write_text("feature\n", encoding="utf-8")
    git(root, "add", "-A")

    exit_code = command_commit(argparse.Namespace(root=root, message=None))
    assert exit_code == 0

    fresh, reason = prepare_is_fresh(root)

    assert fresh, f"the pipeline invalidated the prepare it had just used: {reason}"
