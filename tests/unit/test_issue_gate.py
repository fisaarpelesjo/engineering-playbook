"""The issue gate: `publish` and `validate-ci` both refuse work with no live card.

Spec 002 ("A issue e o contrato"). Both `command_publish` and `command_validate_ci`
answer the same underlying question -- "does an existing, OPEN GitHub issue back
this change" -- through the single `issue_is_open` function in
`engineering_playbook.delivery`. Every test here fakes `engineering_playbook.
delivery.run`; none makes a real call to `gh` or the network (NFR-002).
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from engineering_playbook.core import load_yaml, write_yaml_atomic
from engineering_playbook.delivery import (
    PR_BODY_FILE,
    PREPARE_FILE,
    STATE_FILE,
    IssueLookupError,
    command_publish,
    command_validate_ci,
    issue_from_pr_body,
    issue_is_open,
)

NOT_FOUND_STDERR = (
    "GraphQL: Could not resolve to an Issue with the number of 999. (repository.issue)"
)
UNREACHABLE_STDERR = "dial tcp: lookup api.github.com: no such host"


# --- fixtures ---------------------------------------------------------------------------------


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def repo_ready_to_publish(root: Path, *, issue: int | None) -> str:
    """A repository on a feature branch, `prepare`d and ready for `publish` --
    the exact state `command_prepare`/`command_commit` leave behind, with an
    optional `issue` field in `.project/state.yml`.
    """
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "switch", "-qc", "feat/123-example")
    (root / "feature.txt").write_text("feature\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "feature")
    head = git(root, "rev-parse", "HEAD")
    branch = git(root, "branch", "--show-current")
    state: dict[str, Any] = {
        "schema_version": "1.0.0",
        "status": "verified",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    if issue is not None:
        state["issue"] = issue
    write_yaml_atomic(root / STATE_FILE, state)
    write_yaml_atomic(
        root / PREPARE_FILE,
        {
            "schema_version": "1.0.0",
            "status": "approved",
            "head": head,
            "branch": branch,
            "title": "feat: example",
            "body": "body",
            "files": [],
        },
    )
    (root / PR_BODY_FILE).parent.mkdir(parents=True, exist_ok=True)
    (root / PR_BODY_FILE).write_text("body", encoding="utf-8")
    return branch


def publish_args(root: Path) -> argparse.Namespace:
    return argparse.Namespace(root=root, yes_remote=True, remote="origin", base="main")


def fixed_run(*, returncode: int = 0, stdout: str = "", stderr: str = ""):
    """A stand-in for `delivery.run` that answers every call the same way --
    used where the test only cares about a single `gh` call's outcome.
    """

    def fake(root: Path, cmd_args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(cmd_args, returncode, stdout, stderr)

    return fake


def refuse_any_call(calls: list[list[str]]):
    """A stand-in for `delivery.run` that fails the test the moment anything is run --
    used to prove `publish` refuses before touching the pull request at all.
    """

    def fake(root: Path, cmd_args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd_args)
        raise AssertionError(f"publish must not run anything, but ran: {cmd_args}")

    return fake


# --- issue_from_pr_body: parsing GitHub's own closing keywords -------------------------------


@pytest.mark.parametrize(
    "body,expected",
    [
        ("Closes #7", 7),
        ("fixes #42", 42),
        ("Resolved: #9", 9),
        ("Some prose.\n\nFixed #3 in this change.", 3),
        ("no reference here at all", None),
        ("", None),
        (None, None),
    ],
)
def test_issue_from_pr_body_reads_the_closing_keyword(
    body: str | None, expected: int | None
) -> None:
    assert issue_from_pr_body(body) == expected  # type: ignore[arg-type]


# --- issue_is_open: the shared function both gates call ---------------------------------------


def test_issue_is_open_is_true_only_for_an_open_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        fixed_run(stdout=json.dumps({"state": "OPEN"})),
    )
    assert issue_is_open(tmp_path, 7) is True


def test_issue_is_open_is_false_for_a_closed_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        fixed_run(stdout=json.dumps({"state": "CLOSED"})),
    )
    assert issue_is_open(tmp_path, 7) is False


def test_issue_is_open_is_false_for_a_nonexistent_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        fixed_run(returncode=1, stderr=NOT_FOUND_STDERR),
    )
    assert issue_is_open(tmp_path, 999) is False


def test_issue_is_open_refuses_to_guess_when_gh_cannot_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NFR-003: an environment that cannot measure (network down here) refuses --
    it must raise, never silently return True or False.
    """
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        fixed_run(returncode=1, stderr=UNREACHABLE_STDERR),
    )
    with pytest.raises(IssueLookupError):
        issue_is_open(tmp_path, 7)


def test_issue_is_open_refuses_when_gh_itself_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError("gh")

    monkeypatch.setattr("engineering_playbook.delivery.run", missing)
    with pytest.raises(IssueLookupError):
        issue_is_open(tmp_path, 7)


# --- command_publish: recusa sem cartao, e recusa issue morta ---------------------------------


def test_publish_without_a_declared_issue_refuses_and_touches_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    repo_ready_to_publish(root, issue=None)
    calls: list[list[str]] = []
    monkeypatch.setattr("engineering_playbook.delivery.run", refuse_any_call(calls))

    exit_code = command_publish(publish_args(root))

    assert exit_code != 0
    assert calls == []
    state = load_yaml(root / STATE_FILE)
    assert "delivery" not in state


def test_publish_with_an_open_declared_issue_creates_the_pull_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    repo_ready_to_publish(root, issue=7)
    calls: list[list[str]] = []
    first_view_done = {"value": False}

    def fake(root: Path, cmd_args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd_args)
        if cmd_args[:3] == ["gh", "issue", "view"]:
            assert cmd_args[3] == "7"
            return subprocess.CompletedProcess(cmd_args, 0, json.dumps({"state": "OPEN"}), "")
        if cmd_args[:1] == ["uv"]:
            return subprocess.CompletedProcess(cmd_args, 0, "", "")
        if cmd_args[:3] == ["git", "remote", "get-url"]:
            return subprocess.CompletedProcess(cmd_args, 0, "https://example.invalid/x/y.git", "")
        if cmd_args[:2] == ["git", "push"]:
            return subprocess.CompletedProcess(cmd_args, 0, "", "")
        if cmd_args[:3] == ["gh", "pr", "view"] and "number,url" in cmd_args:
            if not first_view_done["value"]:
                first_view_done["value"] = True
                return subprocess.CompletedProcess(cmd_args, 1, "", "no pull requests found")
            return subprocess.CompletedProcess(
                cmd_args, 0, json.dumps({"number": 1, "url": "https://example.invalid/pull/1"}), ""
            )
        if cmd_args[:3] == ["gh", "pr", "create"]:
            return subprocess.CompletedProcess(cmd_args, 0, "https://example.invalid/pull/1", "")
        # Issue #64: `publish` folds its own records into a commit instead of leaving them
        # uncommitted. `test_publish_leaves_tree_clean.py` owns that behaviour against a real
        # repository; here the commands are only recognised, so this test keeps measuring the
        # issue gate rather than failing on a step it does not own.
        if cmd_args[:4] == ["git", "diff", "--cached", "--name-only"]:
            return subprocess.CompletedProcess(cmd_args, 0, ".project/state.yml\n", "")
        if cmd_args[:2] == ["git", "add"]:
            return subprocess.CompletedProcess(cmd_args, 0, "", "")
        if cmd_args[:2] == ["git", "commit"]:
            return subprocess.CompletedProcess(cmd_args, 0, "[branch abc1234] chore", "")
        raise AssertionError(f"unexpected command: {cmd_args}")

    monkeypatch.setattr("engineering_playbook.delivery.run", fake)

    exit_code = command_publish(publish_args(root))

    assert exit_code == 0
    assert any(c[:3] == ["gh", "pr", "create"] for c in calls)
    state = load_yaml(root / STATE_FILE)
    assert state["delivery"]["pr_number"] == 1
    assert any(c[:2] == ["git", "commit"] for c in calls), (
        "publish did not record its own writes -- issue #64"
    )
    pushes = [c for c in calls if c[:2] == ["git", "push"]]
    assert len(pushes) == 2, (
        f"expected the branch push and the bookkeeping push, got: {pushes}. The second push is "
        "the declared cost of leaving no dirty tree behind."
    )


def test_publish_refuses_when_the_declared_issue_does_not_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    repo_ready_to_publish(root, issue=999)
    calls: list[list[str]] = []

    def fake(root: Path, cmd_args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd_args)
        if cmd_args[:3] == ["gh", "issue", "view"]:
            return subprocess.CompletedProcess(cmd_args, 1, "", NOT_FOUND_STDERR)
        raise AssertionError(f"publish must stop right after the issue check: {cmd_args}")

    monkeypatch.setattr("engineering_playbook.delivery.run", fake)

    exit_code = command_publish(publish_args(root))

    assert exit_code != 0
    assert not any(c[:3] == ["gh", "pr", "create"] for c in calls)
    assert not any(c[:2] == ["git", "push"] for c in calls)


def test_publish_refuses_when_the_declared_issue_is_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    repo_ready_to_publish(root, issue=8)
    calls: list[list[str]] = []

    def fake(root: Path, cmd_args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd_args)
        if cmd_args[:3] == ["gh", "issue", "view"]:
            return subprocess.CompletedProcess(cmd_args, 0, json.dumps({"state": "CLOSED"}), "")
        raise AssertionError(f"publish must stop right after the issue check: {cmd_args}")

    monkeypatch.setattr("engineering_playbook.delivery.run", fake)

    exit_code = command_publish(publish_args(root))

    assert exit_code != 0
    assert not any(c[:3] == ["gh", "pr", "create"] for c in calls)
    assert not any(c[:2] == ["git", "push"] for c in calls)


def test_publish_refuses_when_gh_cannot_measure_the_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    repo_ready_to_publish(root, issue=8)
    calls: list[list[str]] = []

    def fake(root: Path, cmd_args: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(cmd_args)
        if cmd_args[:3] == ["gh", "issue", "view"]:
            return subprocess.CompletedProcess(cmd_args, 1, "", UNREACHABLE_STDERR)
        raise AssertionError(f"publish must stop right after the issue check: {cmd_args}")

    monkeypatch.setattr("engineering_playbook.delivery.run", fake)

    exit_code = command_publish(publish_args(root))

    assert exit_code != 0
    assert not any(c[:3] == ["gh", "pr", "create"] for c in calls)
    assert not any(c[:2] == ["git", "push"] for c in calls)


# --- command_validate_ci: recusa PR sem issue existente e aberta -------------------------------


def validate_ci_args(pr_body: str | None, root: Path) -> argparse.Namespace:
    return argparse.Namespace(root=root, branch=None, pr_title=None, pr_body=pr_body)


def test_validate_ci_refuses_a_pull_request_whose_body_does_not_close_an_issue(
    tmp_path: Path,
) -> None:
    exit_code = command_validate_ci(validate_ci_args("no issue reference here", tmp_path))
    assert exit_code != 0


def test_validate_ci_accepts_a_pull_request_that_closes_an_open_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An open issue is now the first of two conditions, not the only one.

    T212 added the rest of the chain -- the issue has to connect to a specification, through a
    parent or by naming one. This test is about the issue being open, so the chain is satisfied
    here rather than exercised; `tests/unit/test_the_chain_is_verified.py` owns it, including the
    four ways it breaks.
    """
    spec_dir = tmp_path / "specs/003-no-stage-without-a-mechanism"
    spec_dir.mkdir(parents=True)

    def answers(_root: Path, command: list[str], **_kwargs: object) -> Any:
        if command[:2] == ["gh", "api"]:
            body = {"body": "Refs `specs/003-no-stage-without-a-mechanism/spec.md`."}
            return subprocess.CompletedProcess(command, 0, json.dumps(body), "")
        return subprocess.CompletedProcess(command, 0, json.dumps({"state": "OPEN"}), "")

    monkeypatch.setattr("engineering_playbook.delivery.run", answers)

    assert command_validate_ci(validate_ci_args("Closes #7", tmp_path)) == 0


def test_validate_ci_refuses_a_pull_request_that_closes_a_nonexistent_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        fixed_run(returncode=1, stderr=NOT_FOUND_STDERR),
    )
    exit_code = command_validate_ci(validate_ci_args("Closes #999", tmp_path))
    assert exit_code != 0


def test_validate_ci_refuses_a_pull_request_that_closes_a_closed_issue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        fixed_run(stdout=json.dumps({"state": "CLOSED"})),
    )
    exit_code = command_validate_ci(validate_ci_args("Fixes #8", tmp_path))
    assert exit_code != 0


def test_validate_ci_refuses_when_the_issue_lookup_cannot_measure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "engineering_playbook.delivery.run",
        fixed_run(returncode=1, stderr=UNREACHABLE_STDERR),
    )
    exit_code = command_validate_ci(validate_ci_args("Closes #7", tmp_path))
    assert exit_code != 0


def test_validate_ci_ignores_the_issue_gate_when_no_pr_body_is_given(tmp_path: Path) -> None:
    """Only the `pull_request` CI event supplies `--pr-body` at all (see
    `.github/workflows/quality.yml`); a push-only invocation must not fail this
    check just because there is nothing to check.
    """
    exit_code = command_validate_ci(
        argparse.Namespace(root=tmp_path, branch=None, pr_title=None, pr_body=None)
    )
    assert exit_code == 0
