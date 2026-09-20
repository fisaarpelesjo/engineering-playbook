"""T201: `.github/rulesets/main.yml` must match what is actually applied on the server.

FR-002 / AC-006: divergence between the declared file and the applied ruleset is a gate
failure. NFR-002: a control unable to obtain its measurement (no `gh`, no network, not
authenticated) returns failure, never a silent pass. Both are exercised adversarially below:
the first by feeding a file that disagrees with a fabricated "applied" response, the second
by making the `gh` call itself fail.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from engineering_playbook import core
from engineering_playbook.commands import command_verify_ruleset
from engineering_playbook.core import GhUnavailableError, check_ruleset_reconciliation

APPLIED_RULESET: dict[str, Any] = {
    "id": 23734100,
    "name": "protect-main",
    "target": "branch",
    "enforcement": "active",
    "bypass_actors": [],
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 0,
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": False,
                "require_last_push_approval": False,
                "required_review_thread_resolution": True,
                "allowed_merge_methods": ["squash"],
            },
        },
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": True,
                "required_status_checks": [
                    {"context": "delivery-policy"},
                    {"context": "quality"},
                ],
            },
        },
    ],
}

RECONCILED_FILE = """
name: protect-main
target: branch
enforcement: active
bypass_actors: []
rules:
  - type: deletion
  - type: non_fast_forward
  - type: pull_request
    parameters:
      required_approving_review_count: 0
      dismiss_stale_reviews_on_push: true
      require_code_owner_review: false
      require_last_push_approval: false
      required_review_thread_resolution: true
      allowed_merge_methods:
        - squash
  - type: required_status_checks
    parameters:
      strict_required_status_checks_policy: true
      required_status_checks:
        - context: delivery-policy
        - context: quality
"""

DIVERGENT_FILE = RECONCILED_FILE.replace(
    "required_approving_review_count: 0", "required_approving_review_count: 1"
)


def _write_ruleset(tmp_path: Path, text: str) -> None:
    ruleset_dir = tmp_path / ".github" / "rulesets"
    ruleset_dir.mkdir(parents=True)
    (ruleset_dir / "main.yml").write_text(text, encoding="utf-8")


def _fake_gh_capture(responses: dict[str, str]):
    def fake(root: Path, *args: str) -> str:
        key = " ".join(args)
        if key not in responses:
            raise AssertionError(f"unexpected gh invocation in test: gh {key}")
        return responses[key]

    return fake


def _applied_responses() -> dict[str, str]:
    return {
        "api repos/:owner/:repo/rulesets": json.dumps(
            [{"id": APPLIED_RULESET["id"], "name": APPLIED_RULESET["name"]}]
        ),
        f"api repos/:owner/:repo/rulesets/{APPLIED_RULESET['id']}": json.dumps(APPLIED_RULESET),
    }


# --- adversarial: file diverges from the applied ruleset (AC-006) --------------------------


def test_reconciliation_rejects_a_divergent_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_ruleset(tmp_path, DIVERGENT_FILE)
    monkeypatch.setattr(core, "gh_capture", _fake_gh_capture(_applied_responses()))

    result = check_ruleset_reconciliation(tmp_path)

    assert not result.ok, (
        "a file declaring review_count=1 against an applied review_count=0 must fail"
    )
    assert any("pull_request" in error for error in result.errors)


def test_reconciliation_accepts_a_file_that_matches_the_applied_ruleset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other half: a reconciled file must not be rejected -- not a one-sided guard."""
    _write_ruleset(tmp_path, RECONCILED_FILE)
    monkeypatch.setattr(core, "gh_capture", _fake_gh_capture(_applied_responses()))

    result = check_ruleset_reconciliation(tmp_path)

    assert result.ok, f"a reconciled file was rejected: {result.errors}"


# --- adversarial: NFR-002, absence of measurement must never read as a pass -----------------


def test_command_verify_ruleset_fails_closed_when_gh_cannot_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_ruleset(tmp_path, RECONCILED_FILE)

    def unavailable(root: Path, *args: str) -> str:
        raise GhUnavailableError("gh api ... nao pode ser executado: network unreachable")

    monkeypatch.setattr(core, "gh_capture", unavailable)

    exit_code = command_verify_ruleset(tmp_path)

    assert exit_code == 1, "absence of network must fail the control, not pass it silently"
    captured = capsys.readouterr()
    assert "gh nao respondeu" in captured.out


def test_fetch_applied_ruleset_raises_when_no_matching_ruleset_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An absent server-side ruleset is not 'nothing to compare' -- FR-001 requires it exist."""
    _write_ruleset(tmp_path, RECONCILED_FILE)
    monkeypatch.setattr(
        core, "gh_capture", _fake_gh_capture({"api repos/:owner/:repo/rulesets": json.dumps([])})
    )

    with pytest.raises(GhUnavailableError):
        check_ruleset_reconciliation(tmp_path)


# --- the decision documented: this control does not run inside the offline verify_root ------


def test_verify_root_never_calls_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """verify_root backs `doctor`/`verify`, which run locally and offline (see the docstring
    of check_ruleset_reconciliation). If verify_root ever called gh_capture, this would raise
    and fail the test, proving the network-dependent control stayed out of the offline path.
    """

    def forbidden(root: Path, *args: str) -> str:
        raise AssertionError("verify_root must never call gh_capture")

    monkeypatch.setattr(core, "gh_capture", forbidden)

    core.verify_root(tmp_path)  # must not raise
