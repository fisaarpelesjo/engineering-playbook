"""The issue reference on the PR template, and that it actually reaches a derived project.

`.github/pull_request_template.md:7` used to ask for the issue inside an HTML comment --
invisible on the GitHub PR form, so a PR with no issue looked identical to one that had it.
FR-006 requires a visible field; AC-005 requires the installed copy to carry it byte for byte.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from engineering_playbook.installer import command_init

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / ".github/pull_request_template.md"
RESOURCE_TEMPLATE = ROOT / "src/engineering_playbook/resources/.github/pull_request_template.md"


def _strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def test_the_issue_field_is_visible_outside_any_html_comment() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    visible = _strip_html_comments(text)
    assert re.search(r"^##\s*Issue\b", visible, re.M), (
        "the template does not ask for the issue in a visible heading; a PR with no "
        "issue must look wrong to the eye, before CI ever runs"
    )
    assert "#<number>" in visible or re.search(r"closes\s*#", visible, re.I), (
        "the visible Issue field does not show what to fill in"
    )


def test_the_distributed_copy_matches_the_source_of_truth() -> None:
    """Derived projects install from the resources copy; a stale copy ships the old form."""
    assert RESOURCE_TEMPLATE.is_file(), f"{RESOURCE_TEMPLATE} is missing"
    assert RESOURCE_TEMPLATE.read_bytes() == TEMPLATE.read_bytes(), (
        "src/engineering_playbook/resources/.github/pull_request_template.md has drifted "
        "from .github/pull_request_template.md"
    )


def test_a_derived_project_is_installed_with_the_visible_issue_field(tmp_path: Path) -> None:
    """AC-005, measured through the real installer rather than assumed from the manifest."""
    args = argparse.Namespace(
        path=tmp_path,
        project_name=None,
        profile="standard",
        stack="python",
        agents="codex",
        ci="github",
        dry_run=False,
        source="package",
    )
    assert command_init(args) == 0
    installed = tmp_path / ".github/pull_request_template.md"
    assert installed.is_file(), "the installer did not write the pull request template"
    assert installed.read_bytes() == RESOURCE_TEMPLATE.read_bytes()
    visible = _strip_html_comments(installed.read_text(encoding="utf-8"))
    assert re.search(r"^##\s*Issue\b", visible, re.M), (
        "the installed template lost the visible Issue field"
    )
