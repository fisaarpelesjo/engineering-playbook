"""A shipped script keeps the bit its shebang promises.

`atomic_write_bytes` used to write every resource with the default mode, so a
git hook installed into a derived project was never run by git on Linux or
macOS -- the failure is silent, which is the worst kind for a guard.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from engineering_playbook.installer import atomic_write_bytes

posix_only = pytest.mark.skipif(os.name == "nt", reason="Windows ignores the execute bit")


@posix_only
def test_a_shebang_file_is_written_executable(tmp_path: Path) -> None:
    target = tmp_path / "hooks" / "pre-commit"

    atomic_write_bytes(target, b"#!/usr/bin/env bash\nexit 0\n")

    assert os.access(target, os.X_OK)


@posix_only
def test_a_plain_file_is_not_made_executable(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "note.md"

    atomic_write_bytes(target, b"# note\n")

    assert not os.access(target, os.X_OK)


@posix_only
def test_the_execute_bit_follows_read_and_the_umask(tmp_path: Path) -> None:
    target = tmp_path / "hooks" / "pre-push"
    previous = os.umask(0o077)
    try:
        atomic_write_bytes(target, b"#!/bin/sh\nexit 0\n")
        mode = stat.S_IMODE(target.stat().st_mode)
    finally:
        os.umask(previous)

    assert mode & stat.S_IXUSR
    assert not mode & (stat.S_IXGRP | stat.S_IXOTH)


def test_writing_is_atomic_and_leaves_no_temporary(tmp_path: Path) -> None:
    target = tmp_path / "hooks" / "pre-commit"

    atomic_write_bytes(target, b"#!/usr/bin/env bash\nexit 0\n")

    assert target.read_bytes() == b"#!/usr/bin/env bash\nexit 0\n"
    assert list(target.parent.iterdir()) == [target]
