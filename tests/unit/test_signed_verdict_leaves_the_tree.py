"""Issue #24: the verdict stops being a field inside the content it is a verdict about.

Two in-tree verdicts were tried and both failed the same way. `last_verified_commit` cannot name
the SHA that only exists once the squash creates it. `last_verified_tree` survives the squash and
not the bookkeeping commit that writes it -- measured on run 35535830710, where the recorded tree
was the code commit's while `main`'s HEAD tree was the one AFTER the record landed. Eight
consecutive push runs on `main` were red for this reason, 35525340039 through 35553187426.

This suite holds three claims apart, because conflating them is how the previous two fixes were
each believed to have closed the issue:

1. The self-reference really does occur -- built here as objects, not asserted from a run log.
2. It no longer turns `main` red: the state field gates nothing (FR-007).
3. Something else does the gating now, and removing it is observable: the workflow mints a
   signed verdict, `merge` refuses content that has none, and a `gh` that cannot answer refuses
   too rather than passing (NFR-002).

Claim 3 is the one that matters. A slice that only deleted the failing gate would satisfy claims
1 and 2 exactly as well, which is why they are not sufficient on their own.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from engineering_playbook import attestation, delivery
from engineering_playbook.attestation import (
    SIGNER_WORKFLOW_PATH,
    subject_bytes,
    subject_digest,
    verdict_is_expected,
)
from engineering_playbook.core import GhUnavailableError, verify_root, write_yaml_atomic

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github/workflows/quality.yml"
STATE_FILE = ".project/state.yml"
BRANCH = "feat/024-signed-verdict"


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def repo_where_the_record_changed_the_tree(root: Path) -> tuple[str, str, str]:
    """`main` as it really looks after a squash merge, reproduced object for object.

    The measured shape of run 35535830710: on the branch, the code commit carries tree T1 and
    the bookkeeping commit that records T1 carries tree T2. The squash GitHub creates on `main`
    carries T2 -- all of the branch's content -- parented on the previous `main` tip. T1, the
    value sitting inside the state file, is therefore the tree of NO commit `main` has: not
    HEAD's, not its parent's. It never appears in `main` at all, because the branch history it
    belonged to was squashed away.

    Returns `(recorded_tree, head_tree, parent_tree)`.
    """
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "code.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")

    git(root, "switch", "-qc", BRANCH)
    (root / "code.txt").write_text("the change under review\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "the code commit")
    recorded_tree = git(root, "rev-parse", "HEAD^{tree}")

    # The bookkeeping commit: it writes the verdict about the tree above, and writing it
    # produces a different tree. Nothing inside the tree avoids this.
    write_state(root, last_verified_tree=recorded_tree)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "chore(state): record the slice as verified")
    branch_tree = git(root, "rev-parse", "HEAD^{tree}")

    squash = git(root, "commit-tree", branch_tree, "-p", base, "-m", "the squash on main")
    git(root, "switch", "-q", "main")
    git(root, "reset", "-q", "--hard", squash)
    return recorded_tree, branch_tree, git(root, "rev-parse", "HEAD^^{tree}")


def write_state(root: Path, **fields: object) -> None:
    write_yaml_atomic(
        root / STATE_FILE,
        {
            "schema_version": "1.0.0",
            "status": "converged",
            "updated_at": "2026-01-01T00:00:00Z",
            **fields,
        },
    )


# --------------------------------------------------------------------------------------
# Claim 1: the self-reference occurs
# --------------------------------------------------------------------------------------


def test_the_record_changes_the_tree_it_records(tmp_path: Path) -> None:
    """The precondition, built rather than quoted: after the bookkeeping commit, the recorded
    tree is neither HEAD's tree nor any parent's. This is what made `main` red, and no value
    written into the tree can escape it.
    """
    root = tmp_path / "repo"
    recorded_tree, head_tree, parent_tree = repo_where_the_record_changed_the_tree(root)

    assert recorded_tree not in {head_tree, parent_tree}, (
        "the fixture did not reproduce the defect: the recorded tree is still reachable "
        "on main, so the assertions below would pass for the wrong reason"
    )


# --------------------------------------------------------------------------------------
# Claim 2: it no longer turns main red (FR-007)
# --------------------------------------------------------------------------------------


def test_a_stale_cache_is_reported_and_gates_nothing(tmp_path: Path) -> None:
    """FR-007. The exact state that failed eight push runs now produces no error.

    It still produces a warning: a reader benefits from knowing the cache is behind. What it
    must not do is fail, because the condition it reports is one the pipeline cannot avoid.
    """
    root = tmp_path / "repo"
    recorded_tree, head_tree, parent_tree = repo_where_the_record_changed_the_tree(root)
    assert recorded_tree not in {head_tree, parent_tree}

    result = verify_root(root)

    assert not any("last_verified_tree" in error for error in result.errors), (
        f"the state field is still a gate, so main stays red between merges: {result.errors}"
    )
    assert any("last_verified_tree" in warning for warning in result.warnings), (
        f"the stale cache was not reported at all, only silenced: {result.warnings}"
    )


def test_derived_project_without_ci_keeps_its_own_gate(tmp_path: Path) -> None:
    """FR-020 and the owner decision behind it. A project declaring `ci: none` has no workflow
    identity and therefore no way to mint a verdict, so nothing here may quietly leave it with
    no verdict at all: its commit/ancestry gate stays, and stays failing on a stale value.
    """
    root = tmp_path / "repo"
    repo_where_the_record_changed_the_tree(root)
    lock = root / ".project/playbook.lock.yml"
    lock.parent.mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(lock, {"playbook": {"ci": "none"}})
    write_state(root, last_verified_commit="0" * 40)

    result = verify_root(root)

    assert any("last_verified_commit" in error for error in result.errors), (
        f"a ci:none derived project lost the only gate it can run: {result.errors}"
    )
    assert not verdict_is_expected(root), (
        "a ci:none project cannot mint a signed verdict, so nothing may demand one from it"
    )


# --------------------------------------------------------------------------------------
# Claim 3: the replacement gate exists, and removing it is observable
# --------------------------------------------------------------------------------------


def test_the_subject_is_a_pure_function_of_the_content(tmp_path: Path) -> None:
    """Why the tree is the subject: two different commits carrying identical content -- which
    is precisely what a branch tip and the squash made from it are -- produce the same attested
    bytes, so a verdict minted before the squash still answers for the content after it.
    """
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("content\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "first")
    tip = git(root, "rev-parse", "HEAD")
    tree = git(root, "rev-parse", "HEAD^{tree}")
    squash = git(root, "commit-tree", tree, "-m", "squash: first")

    assert squash != tip, "sanity: the forged squash must be a different commit"
    assert git(root, "rev-parse", f"{squash}^{{tree}}") == tree
    assert subject_digest(tree) == subject_digest(git(root, "rev-parse", f"{squash}^{{tree}}"))
    assert subject_bytes(tree) != subject_bytes("0" * 40), (
        "different content must not share a subject, or the digest proves nothing"
    )


def plant_workflow(root: Path, workflow: dict[str, Any]) -> list[str]:
    """Write `workflow` into a bare repository and return what `verify_root` says about it."""
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/quality.yml").write_text(
        yaml.safe_dump(workflow, sort_keys=False), encoding="utf-8"
    )
    return verify_root(root).errors


def real_workflow() -> dict[str, Any]:
    return cast("dict[str, Any]", yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")))


def test_the_real_workflow_satisfies_its_own_control(tmp_path: Path) -> None:
    """The baseline the mutations below are measured against: unmodified, it passes. Without
    this, a control that rejected every workflow would satisfy every mutation test there is.
    """
    errors = plant_workflow(tmp_path / "clean", real_workflow())

    assert not any("signing" in error or "attest" in error for error in errors), (
        f"the repository's own workflow fails the control it ships: {errors}"
    )


def test_each_removal_from_the_signing_job_fails_verify(tmp_path: Path) -> None:
    """NFR-004: a test that only confirms the control is present does not count. Each mutation
    below removes one thing that makes the signature mean something, and each has to fail on its
    own -- otherwise the suite is measuring the presence of text.

    The ordering cases are the ones a substring check let through. A review of this slice planted
    the attestation steps ABOVE the battery and `"attest-build-provenance" in text` said the
    workflow was fine; it would have signed content nothing had measured.
    """
    mutations: dict[str, tuple[dict[str, Any], str]] = {}

    without_action = real_workflow()
    without_action["jobs"]["attest"]["steps"] = [
        step for step in without_action["jobs"]["attest"]["steps"] if "uses" not in step
    ]
    mutations["the signing step is gone"] = (without_action, "exactly one job")

    without_permission = real_workflow()
    del without_permission["jobs"]["attest"]["permissions"]["attestations"]
    mutations["the signing permission is gone"] = (without_permission, "attestations: write")

    unordered = real_workflow()
    del unordered["jobs"]["attest"]["needs"]
    mutations["the signing job no longer waits for the battery"] = (unordered, "needs")

    partly_ordered = real_workflow()
    partly_ordered["jobs"]["attest"]["needs"] = ["quality"]
    mutations["the signing job waits for only one battery"] = (partly_ordered, "delivery-policy")

    leaked = real_workflow()
    leaked["jobs"]["quality"]["permissions"] = {"contents": "read", "id-token": "write"}
    mutations["a battery job holds the signing identity"] = (leaked, "must not hold")

    for label, (workflow, marker) in mutations.items():
        errors = plant_workflow(tmp_path / label.replace(" ", "_"), workflow)

        assert any(marker in error for error in errors), (
            f"mutation {label!r} did not fail verify (expected {marker!r}): {errors}"
        )


def repo_on_a_pull_request_branch(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    workflow = root / SIGNER_WORKFLOW_PATH
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text("name: quality\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "switch", "-qc", BRANCH)
    (root / "feature.txt").write_text("feature\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "feature")


def merge_args(root: Path) -> argparse.Namespace:
    return argparse.Namespace(root=root, auto=True, yes_remote=True, command="merge")


@pytest.fixture
def no_merge_reaches_the_server(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record every command `command_merge` would run, and let none of them out.

    A gate that refuses is only proven by the merge NOT being attempted, so the commands are
    captured rather than stubbed away silently.
    """
    attempted: list[list[str]] = []

    def fake_run(root: Path, command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        attempted.append(command)
        if command[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(command, 0, '{"title":"fix: x","number":24}', "")
        return subprocess.CompletedProcess(command, 0, "", "")

    def public_repository(_root: Path) -> tuple[str, bool]:
        return "owner/name", True

    monkeypatch.setattr(delivery, "run", fake_run)
    monkeypatch.setattr(delivery, "repository_identity", public_repository)
    return attempted


def gh_pr_view_returning(
    attempted: list[list[str]], *, head_oid: str
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """A `delivery.run` whose `gh pr view` names `head_oid` as the pull request's head.

    The default stand-in above leaves `headRefOid` out, which makes the gate fall back to the
    local HEAD -- the ordinary case, where the two are the same commit. These tests are about
    when they are not.
    """

    def fake(root: Path, command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        attempted.append(command)
        if command[:3] == ["gh", "pr", "view"]:
            payload = {"title": "fix: x", "number": 24, "headRefOid": head_oid}
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        return subprocess.CompletedProcess(command, 0, "", "")

    return fake


def test_merge_refuses_content_no_run_has_signed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_merge_reaches_the_server: list[list[str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The replacement gate, doing the job the state field used to pretend to do."""
    root = tmp_path / "repo"
    repo_on_a_pull_request_branch(root)

    def unsigned(_root: Path, tree: str, _slug: str | None = None) -> tuple[bool, str]:
        return False, f"no verdict for {tree}"

    monkeypatch.setattr(delivery, "attestation_covers_tree", unsigned)

    exit_code = delivery.command_merge(merge_args(root))

    assert exit_code == 1
    assert "no verdict for" in capsys.readouterr().out
    assert not any(command[:3] == ["gh", "pr", "merge"] for command in no_merge_reaches_the_server)


def test_merge_refuses_when_gh_cannot_answer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_merge_reaches_the_server: list[list[str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """NFR-002. An unreachable GitHub is not a conformance verdict; it is a measurement that
    was not taken, and the pipeline stops rather than assuming the answer it wanted.
    """
    root = tmp_path / "repo"
    repo_on_a_pull_request_branch(root)

    def unavailable(_root: Path, _tree: str, _slug: str | None = None) -> tuple[bool, str]:
        raise GhUnavailableError("gh nao esta autenticado")

    monkeypatch.setattr(delivery, "attestation_covers_tree", unavailable)

    exit_code = delivery.command_merge(merge_args(root))

    assert exit_code == 1
    assert "NFR-002" in capsys.readouterr().out
    assert not any(command[:3] == ["gh", "pr", "merge"] for command in no_merge_reaches_the_server)


def test_merge_proceeds_once_a_signed_verdict_covers_the_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_merge_reaches_the_server: list[list[str]],
) -> None:
    """The other side of the gate: with a verdict present it does not stand in the way. Without
    this, a gate that refused everything would pass both tests above for the wrong reason.
    """
    root = tmp_path / "repo"
    repo_on_a_pull_request_branch(root)

    def signed(_root: Path, tree: str, _slug: str | None = None) -> tuple[bool, str]:
        return True, f"signed verdict for {tree}"

    def already_recorded(*_args: object, **_kwargs: object) -> int:
        return 0

    monkeypatch.setattr(delivery, "attestation_covers_tree", signed)
    monkeypatch.setattr(delivery, "record_merge_commit", already_recorded)

    exit_code = delivery.command_merge(merge_args(root))

    assert exit_code == 0
    assert any(command[:3] == ["gh", "pr", "merge"] for command in no_merge_reaches_the_server)


def test_the_verifier_asks_github_and_never_reads_the_state_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-004 as a procedure. The command that answers "is this content's verdict signed" runs
    `gh attestation verify` against a subject rebuilt from the tree id alone, pinned to the one
    workflow allowed to sign. Nothing it does reads `.project/state.yml` -- which is the whole
    point: a third party holding only the repository can reach the same answer.
    """
    root = tmp_path / "repo"
    repo_on_a_pull_request_branch(root)
    write_state(root, last_verified_tree="deadbeef" * 5)
    seen: list[tuple[str, ...]] = []

    def fake_gh(_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        seen.append(args)
        return subprocess.CompletedProcess(list(args), 0, "", "")

    monkeypatch.setattr(attestation, "run_gh", fake_gh)

    def public_repository(_root: Path) -> tuple[str, bool]:
        return "owner/name", True

    monkeypatch.setattr(attestation, "repository_identity", public_repository)

    exit_code = attestation.command_attest_verify(root)

    assert exit_code == 0
    assert len(seen) == 1
    args = seen[0]
    assert args[:2] == ("attestation", "verify")
    assert "--signer-workflow" in args
    assert "--deny-self-hosted-runners" in args
    assert args[args.index("--signer-workflow") + 1] == f"owner/name/{SIGNER_WORKFLOW_PATH}"
    subject_path = Path(args[2])
    assert subject_path.name == attestation.SUBJECT_FILENAME


def test_a_repository_that_cannot_mint_a_verdict_is_not_gated_on_having_one(
    tmp_path: Path,
) -> None:
    """The declared limit, asserted rather than left in prose: with no workflow there is no
    identity to sign with, so `merge` must not demand a signature. A gate nobody can pass is a
    gate that gets removed, and removing it is how the control is lost for everyone.
    """
    root = tmp_path / "repo"
    root.mkdir(parents=True)

    assert not verdict_is_expected(root)
    assert delivery.signed_verdict_refusal(root) is None


def test_a_private_repository_is_not_gated_on_a_verdict_it_cannot_mint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_merge_reaches_the_server: list[list[str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The limit that was prose in three files and code in none of them.

    Attestations need a public repository or a plan that includes them, so the workflow mints
    nothing for a private one. A gate that demanded a verdict anyway would block every merge in
    every private derived project forever -- and the predictable answer to a gate nobody can pass
    is deleting it, which takes the control away from everyone. The exemption is announced, not
    silent, so "no verdict" stays distinguishable from "no verdict is possible here".
    """
    root = tmp_path / "repo"
    repo_on_a_pull_request_branch(root)

    def private_repository(_root: Path) -> tuple[str, bool]:
        return "owner/private", False

    def never_asked(_root: Path, _tree: str, _slug: str | None = None) -> tuple[bool, str]:
        raise AssertionError("a private repository must not be asked for a verdict at all")

    monkeypatch.setattr(delivery, "repository_identity", private_repository)

    def already_recorded(*_args: object, **_kwargs: object) -> int:
        return 0

    monkeypatch.setattr(delivery, "attestation_covers_tree", never_asked)
    monkeypatch.setattr(delivery, "record_merge_commit", already_recorded)

    exit_code = delivery.command_merge(merge_args(root))

    assert exit_code == 0
    assert "is private" in capsys.readouterr().out
    assert any(command[:3] == ["gh", "pr", "merge"] for command in no_merge_reaches_the_server)


def test_the_workflow_writes_exactly_the_bytes_the_verifier_rebuilds() -> None:
    """The signing job writes the subject in shell instead of calling `scripts/attest.py`, so the
    identity-holding job never installs dependencies or runs this repository's code. That buys a
    second copy of the format, and a second copy drifts -- unless something compares them. This
    runs the workflow's own `printf` line and asserts the bytes equal `subject_bytes`.
    """
    workflow_text = WORKFLOW.read_text(encoding="utf-8")
    printf_lines = [
        line for line in workflow_text.splitlines() if line.strip().startswith("printf")
    ]
    assert len(printf_lines) == 1, f"expected exactly one printf in the workflow: {printf_lines}"

    command = printf_lines[0].strip().split(" > ")[0].replace('"$tree"', "'deadbeef'")
    produced = subprocess.run(["bash", "-c", command], capture_output=True, check=True).stdout

    assert produced == subject_bytes("deadbeef"), (
        "the workflow's subject bytes drifted from attestation.subject_bytes, so every verdict "
        "it mints would be addressed by a digest no verifier reproduces"
    )


def test_the_subject_is_refused_inside_the_checkout(tmp_path: Path) -> None:
    """The module's central invariant, enforced rather than described. A verdict artifact written
    into the tree changes the tree it is a verdict about -- the same self-reference one level
    down. It was a sentence in a docstring, which is the class of control this repository counts
    as absent.
    """
    root = tmp_path / "repo"
    repo_on_a_pull_request_branch(root)

    with pytest.raises(attestation.SubjectPathError):
        attestation.write_subject(root, root / "content-verdict.txt")
    with pytest.raises(attestation.SubjectPathError):
        attestation.write_subject(root, root / "nested" / "content-verdict.txt")

    outside = tmp_path / "elsewhere" / "content-verdict.txt"
    tree = attestation.write_subject(root, outside)

    assert outside.read_bytes() == subject_bytes(tree)


def test_an_unborn_ref_is_refused_rather_than_signed(tmp_path: Path) -> None:
    """`git_tree` answers the sentinel `"unborn"` for a ref that does not resolve. Signing that
    would mint a verdict naming no content at all, a silent default in a path that is otherwise
    fail-closed everywhere else.
    """
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")

    with pytest.raises(attestation.SubjectPathError):
        attestation.write_subject(root, tmp_path / "elsewhere" / "content-verdict.txt")


def gh_answering(returncode: int, stderr: str) -> Callable[..., subprocess.CompletedProcess[str]]:
    def fake(_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(list(args), returncode, "", stderr)

    return fake


def test_absence_and_a_failed_measurement_are_told_apart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The function that takes the measurement, exercised on both of its refusing branches.

    `gh attestation verify` exits 1 whether GitHub answered "there is none" or the question could
    not be asked. Collapsing the two would let an outage be reported as a verdict that is absent,
    which is an assertion of absence with no instrument behind it. The 404 below is the shape
    measured against this repository on 2026-09-21, before any verdict existed.
    """
    root = tmp_path / "repo"
    repo_on_a_pull_request_branch(root)

    def public_repository(_root: Path) -> tuple[str, bool]:
        return "owner/name", True

    monkeypatch.setattr(attestation, "repository_identity", public_repository)

    monkeypatch.setattr(attestation, "run_gh", gh_answering(1, "Error: HTTP 404: Not Found"))
    covered, detail = attestation.attestation_covers_tree(root, "deadbeef")

    assert covered is False
    assert "no signed verdict" in detail

    monkeypatch.setattr(attestation, "run_gh", gh_answering(1, "Error: HTTP 503: Bad Gateway"))
    with pytest.raises(GhUnavailableError):
        attestation.attestation_covers_tree(root, "deadbeef")


def test_the_gate_measures_the_head_the_server_will_integrate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_merge_reaches_the_server: list[list[str]],
) -> None:
    """A local checkout behind the branch on the server would otherwise have the gate verify one
    tree while GitHub integrates another -- a pass that proves nothing about what lands.
    """
    root = tmp_path / "repo"
    repo_on_a_pull_request_branch(root)
    local_tree = git(root, "rev-parse", "HEAD^{tree}")
    (root / "pushed-from-elsewhere.txt").write_text("later\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "the commit the server has")
    remote_head = git(root, "rev-parse", "HEAD")
    remote_tree = git(root, "rev-parse", "HEAD^{tree}")
    git(root, "reset", "-q", "--hard", "HEAD~1")  # the local checkout falls behind
    assert git(root, "rev-parse", "HEAD^{tree}") == local_tree != remote_tree

    measured: list[str] = []

    def record(_root: Path, tree: str, _slug: str | None = None) -> tuple[bool, str]:
        measured.append(tree)
        return True, "signed"

    def already_recorded(*_args: object, **_kwargs: object) -> int:
        return 0

    monkeypatch.setattr(delivery, "attestation_covers_tree", record)
    monkeypatch.setattr(delivery, "record_merge_commit", already_recorded)
    monkeypatch.setattr(
        delivery,
        "run",
        gh_pr_view_returning(no_merge_reaches_the_server, head_oid=remote_head),
    )

    delivery.command_merge(merge_args(root))

    assert measured == [remote_tree], (
        f"the gate measured the local tree instead of the head being merged: {measured}"
    )


def test_a_head_missing_locally_is_refused_rather_than_guessed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_merge_reaches_the_server: list[list[str]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    """When the server's head is not in the local object store there is nothing to measure. The
    refusal says to fetch; it does not fetch behind the operator's back, and it does not fall
    back to a tree it can reach -- falling back is how a gate starts answering about the wrong
    content.
    """
    root = tmp_path / "repo"
    repo_on_a_pull_request_branch(root)

    def never_asked(_root: Path, _tree: str, _slug: str | None = None) -> tuple[bool, str]:
        raise AssertionError("nothing may be asked about content this repository does not have")

    monkeypatch.setattr(delivery, "attestation_covers_tree", never_asked)
    monkeypatch.setattr(
        delivery, "run", gh_pr_view_returning(no_merge_reaches_the_server, head_oid="f" * 40)
    )

    exit_code = delivery.command_merge(merge_args(root))

    assert exit_code == 1
    assert "git fetch origin" in capsys.readouterr().out
    assert not any(command[:3] == ["gh", "pr", "merge"] for command in no_merge_reaches_the_server)
