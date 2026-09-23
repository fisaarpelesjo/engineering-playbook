"""Issue #76: the version of ruff and pyright a gate runs is the version the lock names.

`pyproject.toml` declared `ruff>=0.6.0` and `pyright>=1.1.380`, open lower bounds. `uv.lock` did
pin them, and CI installs with `uv sync --locked`, but nothing measured that the tool which
actually RAN was the locked one: `local_ci.py` deliberately runs in whatever environment the
caller already has, and the pyright wrapper resolves its engine separately from its own package
(`PYRIGHT_PYTHON_FORCE_VERSION=latest` swaps it without touching the lock). A sibling repository
measured the result: the same commit, no line changed, 0 errors in the morning and 2 at night.

One file both gates read: `uv.lock`. This test runs inside `pytest`, which the pre-push hook
(through `local_ci.py`) and CI's `quality` job both run, so each refuses on its own when the tool
it has disagrees with the lock -- the failure `intelligence-agent` hit when only its hook read
the pin. The declared specifier is pinned too, so the lock cannot drift to a new version by a
routine `uv lock --upgrade` without an edit a reviewer sees in `pyproject.toml`.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = ROOT / "src/engineering_playbook/resources"

#: The tools whose verdict is a gate. `pytest` is not here: its version does not change what
#: the suite asserts, and pinning it would be a rule with no measured failure behind it.
GATE_TOOLS = ("ruff", "pyright")


def locked_versions(root: Path = ROOT) -> dict[str, str]:
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    return {package["name"]: package["version"] for package in lock["package"]}


def declared_specifiers(root: Path = ROOT) -> dict[str, str]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    declared: dict[str, str] = {}
    for requirement in project["dependency-groups"]["dev"]:
        match = re.match(r"^([A-Za-z0-9_.-]+)(.*)$", requirement)
        assert match is not None, requirement
        declared[match.group(1).lower()] = match.group(2).strip()
    return declared


def running_version(tool: str) -> str:
    """What the gate actually runs, asked of the tool itself rather than of the package index."""
    done = subprocess.run(
        [sys.executable, "-m", tool, "--version"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    )
    match = re.search(rf"^{tool} (\S+)", done.stdout, re.MULTILINE)
    assert match is not None, f"{tool} --version printed nothing parseable: {done.stdout!r}"
    return match.group(1)


@pytest.mark.parametrize("tool", GATE_TOOLS)
def test_the_declared_version_is_the_locked_one(tool: str) -> None:
    locked = locked_versions()[tool]
    assert declared_specifiers()[tool] == f"=={locked}", (
        f"pyproject.toml declares {tool}{declared_specifiers()[tool]} and uv.lock holds "
        f"{locked}. A range lets `uv lock --upgrade` move the gate with no edit a reviewer reads; "
        f"pin it: `{tool}=={locked}`."
    )


@pytest.mark.parametrize("tool", GATE_TOOLS)
def test_the_running_tool_is_the_locked_one(tool: str) -> None:
    """THE claim. The version a gate ran with is the version the lock names, measured each run."""
    locked = locked_versions()[tool]
    running = running_version(tool)
    assert running == locked, (
        f"{tool} {running} is running and uv.lock names {locked}. The gate's verdict would "
        "depend on the day it ran. Run `uv sync --locked`; for pyright, unset "
        "PYRIGHT_PYTHON_FORCE_VERSION."
    )


def lock_specifiers(root: Path) -> dict[str, str]:
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    for package in lock["package"]:
        if package.get("source", {}).keys() & {"editable", "virtual"}:
            dev = package["metadata"]["requires-dev"]["dev"]
            return {item["name"]: item.get("specifier", "") for item in dev}
    raise AssertionError("no project package in uv.lock")


@pytest.mark.parametrize("tool", GATE_TOOLS)
def test_the_shipped_copies_pin_what_the_root_pins(tool: str) -> None:
    """Review of #76: the mirror parity test excludes both files, so a bump that edits only the
    root pair would leave the shipped pair behind with nothing going red. Scope, declared: derived
    projects render their own `pyproject.toml` without these tools and do not receive this test,
    so the shipped pin is lock metadata, kept equal here and nowhere enforced downstream.
    """
    root_pin = declared_specifiers()[tool]
    assert declared_specifiers(SHIPPED)[tool] == root_pin
    assert lock_specifiers(SHIPPED)[tool] == lock_specifiers(ROOT)[tool] == root_pin
