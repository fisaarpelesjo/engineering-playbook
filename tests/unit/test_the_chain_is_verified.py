"""T212 / FR-013 / FR-015 / AC-009: a pull request has to connect to something above it.

Coverage matrix stage 6. The chain the requirement asks for is pull request -> sub-issue -> parent
issue -> `specs/NNN/`, each link verified and the missing one named. Until this slice only the
first link existed: `issue_from_pr_body` plus `issue_is_open` proved a card exists and is open, and
nothing asked what the card belongs to.

MEASURED on this repository's own board, 2026-09-21, which is where the accepted shapes come from:

    #26  parent, names specs/003-no-stage-without-a-mechanism   -> chain resolves
    #28  parent, names specs/005-agent-throughput               -> the directory does not exist
    #55  sub-issue of #26                                       -> resolves through its parent
    #15, #36, #45, #46  standalone, name no specification       -> defect fixes, legitimate

The last row is why the escape exists. A rule refusing those would be a rule somebody removes, and
the #28 row is why naming a specification is not the same as having one: a link to a document
nobody wrote is traceability's shape without its substance.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from engineering_playbook import delivery
from engineering_playbook.core import write_yaml_atomic
from engineering_playbook.delivery import (
    issue_contract_problems,
    specification_named_by,
    traceability_refusal,
)

SPEC_DIR = "specs/003-no-stage-without-a-mechanism"


def repo(root: Path, **state: object) -> Path:
    (root / SPEC_DIR).mkdir(parents=True, exist_ok=True)
    (root / ".project").mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(
        root / ".project/state.yml",
        {"schema_version": "1.0.0", "updated_at": "2026-01-01T00:00:00Z", **state},
    )
    return root


def board(**issues: dict[str, Any]) -> Any:
    """A `delivery.run` that answers `gh api .../issues/<n>` from a dict, and nothing else."""

    def fake(
        _root: Path, command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["gh", "api"] and "/issues/" in command[2]:
            number = command[2].rsplit("/", 1)[-1]
            payload = issues.get(number)
            if payload is None:
                return subprocess.CompletedProcess(command, 1, "", "HTTP 404: Not Found")
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        raise AssertionError(f"unexpected command: {command}")

    return fake


def sub_issue(parent: int) -> dict[str, Any]:
    return {
        "body": "a slice",
        "parent_issue_url": f"https://api.github.com/repos/o/r/issues/{parent}",
    }


# --------------------------------------------------------------------------------------
# The shapes the board actually has
# --------------------------------------------------------------------------------------


def test_a_sub_issue_resolves_through_the_specification_its_parent_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ordinary case, and the one every slice of this session took: #55 hangs from #26, and
    #26 names the specification the epic decomposes.
    """
    root = repo(tmp_path)
    monkeypatch.setattr(
        delivery,
        "run",
        board(**{"55": sub_issue(26), "26": {"body": f"Parent issue for `{SPEC_DIR}/`."}}),
    )

    assert traceability_refusal(root, 55) is None


def test_a_standalone_issue_that_names_its_specification_resolves(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    monkeypatch.setattr(delivery, "run", board(**{"9": {"body": f"Refs `{SPEC_DIR}/spec.md`."}}))

    assert traceability_refusal(root, 9) is None


def test_a_parent_that_names_no_specification_breaks_the_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FR-015 names this case exactly: issue mae sem especificacao correspondente."""
    root = repo(tmp_path)
    monkeypatch.setattr(
        delivery, "run", board(**{"7": sub_issue(3), "3": {"body": "an epic, described in prose"}})
    )

    refusal = traceability_refusal(root, 7)

    assert refusal is not None
    assert "parent issue #3" in refusal, "the refusal has to name the link that is missing"
    assert "names no specification" in refusal


def test_a_parent_naming_a_specification_nobody_wrote_breaks_the_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Measured: issue #28 names `specs/005-agent-throughput`, and that directory does not exist.

    A link to a document nobody wrote is traceability's shape without its substance, so naming is
    not enough -- the specification has to be there.
    """
    root = repo(tmp_path)
    monkeypatch.setattr(
        delivery,
        "run",
        board(
            **{
                "8": sub_issue(28),
                "28": {"body": "Parent issue for `specs/005-agent-throughput/`."},
            }
        ),
    )

    refusal = traceability_refusal(root, 8)

    assert refusal is not None
    assert "specs/005-agent-throughput" in refusal
    assert "does not exist" in refusal


def test_a_standalone_issue_with_no_specification_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)
    monkeypatch.setattr(delivery, "run", board(**{"4": {"body": "something is broken"}}))

    refusal = traceability_refusal(root, 4)

    assert refusal is not None
    assert "connects to nothing above it" in refusal
    assert "no_spec_reason" in refusal, "the refusal names the escape it offers"


def test_a_declared_defect_fix_needs_no_specification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Issues #15, #36, #45 and #46 were all defect fixes or decisions belonging to no epic. A
    rule refusing them is a rule somebody removes rather than satisfies.
    """
    root = repo(
        tmp_path,
        no_spec_reason=(
            "Defect fix with no specification of its own: restores a contract the module "
            "docstring already states."
        ),
    )
    monkeypatch.setattr(
        delivery, "run", board(**{"36": {"body": "start branches from a bad HEAD"}})
    )

    assert traceability_refusal(root, 36) is None


# --------------------------------------------------------------------------------------
# What happens when the chain cannot be read at all
# --------------------------------------------------------------------------------------


def test_an_unreadable_issue_is_refused_rather_than_assumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NFR-002. A chain that could not be read is not a chain that is intact."""
    root = repo(tmp_path)
    monkeypatch.setattr(delivery, "run", board())

    refusal = traceability_refusal(root, 99)

    assert refusal is not None
    assert "NFR-002" in refusal


def test_an_unreadable_parent_is_refused_rather_than_assumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The half of the chain that is easy to forget: the child read fine, the parent did not."""
    root = repo(tmp_path)
    monkeypatch.setattr(delivery, "run", board(**{"5": sub_issue(404)}))

    refusal = traceability_refusal(root, 5)

    assert refusal is not None
    assert "parent #404" in refusal
    assert "NFR-002" in refusal


def test_something_that_is_not_an_issue_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo(tmp_path)

    def garbage(
        _root: Path, command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(command, 0, "not json at all", "")

    monkeypatch.setattr(delivery, "run", garbage)

    refusal = traceability_refusal(root, 1)

    assert refusal is not None
    assert "NFR-002" in refusal


# --------------------------------------------------------------------------------------
# The specification reference itself
# --------------------------------------------------------------------------------------


def test_a_reference_resolves_only_when_the_directory_is_there(tmp_path: Path) -> None:
    root = repo(tmp_path)

    found, problem = specification_named_by(f"see `{SPEC_DIR}/plan.md`", root)
    assert (found, problem) == (SPEC_DIR, None)

    found, problem = specification_named_by("see `specs/999-not-written/spec.md`", root)
    assert found is None
    assert problem is not None and "does not exist" in problem

    assert specification_named_by("no reference here", root) == (None, None)
    assert specification_named_by("", root) == (None, None)


# ---------------------------------------------------------------------------------------
# The issue side of the same decision: the contract nothing enforced until #65.
# ---------------------------------------------------------------------------------------


def card(**overrides: object) -> dict[str, object]:
    """A conforming issue payload, so each test below changes exactly one thing."""
    payload: dict[str, object] = {
        "title": "A title in English",
        "body": "Sub-issue of #26. Everything here is English prose.",
        "labels": [{"name": "bug"}],
        "parent_issue_url": "https://api.github.com/repos/o/r/issues/26",
    }
    payload.update(overrides)
    return payload


def problems_for(payload: dict[str, object]) -> list[str]:
    with patch("engineering_playbook.delivery.issue_payload", return_value=payload):
        return issue_contract_problems(Path("."), 1)


def test_a_conforming_card_is_accepted() -> None:
    """Without this the other tests pass by refusing everything."""
    assert problems_for(card()) == []


def test_a_title_not_in_english_is_refused() -> None:
    """Measured from this board: the real title carried exactly one Portuguese marker, which is
    why the threshold for a title is one and not the two a body line needs.
    """
    problems = problems_for(card(title="publish e merge escrevem bookkeeping depois do push"))

    assert len(problems) == 1
    assert "not in English" in problems[0]


def test_a_body_not_in_english_is_refused() -> None:
    problems = problems_for(
        card(body="Sub-issue de #26. Medido em 2026-09-22: a arvore fica suja e nao ha portao.")
    )

    assert len(problems) == 1
    assert "not in English" in problems[0]


def test_an_english_title_carrying_a_todo_marker_is_not_refused() -> None:
    """`TODOs` collides with the Portuguese `todos` and is this repository's own vocabulary: the
    PRD carries eighty and issue #46 is named after the count. Measured across all 39 titles on
    this board, it was the only false positive of a one-marker threshold.
    """
    assert problems_for(card(title="The PRD is a template with 80 TODOs")) == []


def test_a_card_with_no_label_is_refused() -> None:
    problems = problems_for(card(labels=[]))

    assert len(problems) == 1
    assert "no label" in problems[0]


def test_a_parentage_claim_the_api_does_not_confirm_is_refused() -> None:
    """The half `traceability_refusal` cannot see. That one asks whether a parent exists and names
    a specification; this asks whether the parent the body ADVERTISES is the one the API reports.

    Both real: two issues opened by this repository's own agent said `Sub-issue of #26` with no
    relationship at all, and were linked by hand after the mismatch was measured.
    """
    orphan = problems_for(card(parent_issue_url=""))
    assert len(orphan) == 1
    assert "no parent relationship" in orphan[0]

    wrong = problems_for(card(parent_issue_url="https://api.github.com/repos/o/r/issues/8"))
    assert len(wrong) == 1
    assert "reports #8" in wrong[0]


def test_a_body_making_no_claim_is_not_asked_about_parentage() -> None:
    """A standalone issue is legitimate -- `traceability_refusal` accepts one that names a
    specification itself. What is refused is CLAIMING a parent that is not there.
    """
    assert problems_for(card(body="No claim here.", parent_issue_url="")) == []


def test_the_cli_refuses_a_card_outside_the_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The wiring, not the function. Review measured that nothing drove `validate-ci` with this
    flag at all, so the exit code and the refusal branch were unexercised.
    """
    with patch(
        "engineering_playbook.delivery.issue_payload",
        return_value=card(labels=[]),
    ):
        code = delivery.main(["validate-ci", "--issue-contract-body", "Closes #65"])

    assert code == 1
    assert "no label" in capsys.readouterr().out


def test_the_cli_accepts_a_conforming_card(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    with patch("engineering_playbook.delivery.issue_payload", return_value=card()):
        code = delivery.main(["validate-ci", "--issue-contract-body", "Closes #65"])

    assert code == 0
    assert capsys.readouterr().out == ""


def test_the_cli_says_nothing_when_the_body_names_no_issue() -> None:
    """Not this control's refusal: the `--pr-body` step exists for that and says so. Two controls
    refusing one cause give the operator two errors to chase.
    """
    code = delivery.main(["validate-ci", "--issue-contract-body", "No reference at all"])

    assert code == 0


def test_the_cli_fails_closed_when_the_card_cannot_be_read(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """NFR-002. Measured on this very slice: the first version of the workflow step carried no
    `GH_TOKEN`, so `gh` refused, and this is the branch that would have fired.
    """
    with patch(
        "engineering_playbook.delivery.issue_payload",
        side_effect=delivery.IssueLookupError("gh: no token"),
    ):
        code = delivery.main(["validate-ci", "--issue-contract-body", "Closes #65"])

    assert code == 1
    assert "could not be read" in capsys.readouterr().out
