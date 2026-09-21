"""Issue #11 / FR-003 / AC-003: `next_checkpoint_id` used to count `.project/checkpoints/
CP-<date>-*.yml` files in ONE working tree, so two branches that had each produced zero
checkpoints so far, on the same day, computed the IDENTICAL id -- an add/add git conflict
invisible until a rebase.

This builds two SEPARATE working trees (no shared filesystem state, no git history at all --
`next_checkpoint_id` never reads git) that are in the exact same state: an empty
`.project/checkpoints/` directory, on the same day. Against the old counting rule this pair
of calls returns the same string; that is precisely the defect.
"""

from __future__ import annotations

import re
from pathlib import Path

from engineering_playbook.core import next_checkpoint_id


def test_two_trees_in_the_same_state_produce_distinct_ids(tmp_path: Path) -> None:
    tree_a = tmp_path / "tree-a"
    tree_b = tmp_path / "tree-b"
    (tree_a / ".project" / "checkpoints").mkdir(parents=True)
    (tree_b / ".project" / "checkpoints").mkdir(parents=True)

    id_a = next_checkpoint_id(tree_a)
    id_b = next_checkpoint_id(tree_b)

    assert id_a != id_b, (
        f"two working trees with an identical, empty checkpoint history produced the same "
        f"id ({id_a!r}) -- exactly the collision issue #11 measured"
    )


def test_repeated_calls_in_the_same_tree_also_stay_distinct(tmp_path: Path) -> None:
    """Not just cross-tree: two checkpoints written back-to-back in ONE tree, before either
    is persisted to disk between calls, must not collide either.
    """
    root = tmp_path / "repo"
    (root / ".project" / "checkpoints").mkdir(parents=True)

    first = next_checkpoint_id(root)
    second = next_checkpoint_id(root)

    assert first != second


def test_the_shape_stays_recognizable_as_a_checkpoint_id(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / ".project" / "checkpoints").mkdir(parents=True)

    checkpoint_id = next_checkpoint_id(root)

    assert re.match(r"^CP-[0-9]{8}-[0-9a-f]{8}$", checkpoint_id), checkpoint_id
