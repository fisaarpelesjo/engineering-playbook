"""Issue #36: `start` asked nothing about the HEAD it branched from.

Measured on 2026-09-21, delivering the slice that closes #24. The operator's HEAD held six
commits that `main` had already absorbed as the squash `48639d3`, so the branch replayed history
the base already had:

    git rev-list --left-right --count origin/main...HEAD   ->   1  7
    gh pr view 35 --json mergeable                          ->   CONFLICTING
    git diff --name-only origin/main HEAD                   ->   only the new slice's files

The content did not collide; two histories carrying the same content did. That is the ordinary
state of the working copy after every squash merge, not an unusual one, so the branch was born
unviable and only said so in the pull request. Cost: a full turn of the cycle.

This suite builds that shape out of git objects -- no mocking of git itself -- and holds three
claims apart: the refusal fires on it, the ordinary case still passes, and a measurement that
cannot be taken refuses rather than assuming the answer it wanted.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from engineering_playbook import delivery
from engineering_playbook.delivery import command_start, parse_args, unmerged_base_refusal


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def repo_after_a_squash_merge(root: Path) -> None:
    """A working copy in the state every squash merge leaves behind.

    `origin/main` carries a commit whose tree is the branch's, parented on the old base. The
    checked-out HEAD is the pre-squash branch tip: same content, different identity, and not an
    ancestor of the base any more.
    """
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    old_base = git(root, "rev-parse", "HEAD")

    git(root, "switch", "-qc", "feat/001-previous-slice")
    (root / "b.txt").write_text("the previous slice\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "the previous slice")
    branch_tree = git(root, "rev-parse", "HEAD^{tree}")

    squash = git(root, "commit-tree", branch_tree, "-p", old_base, "-m", "squash: previous slice")
    git(root, "update-ref", "refs/remotes/origin/main", squash)


def repo_in_step_with_its_base(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    git(root, "update-ref", "refs/remotes/origin/main", git(root, "rev-parse", "HEAD"))


def start_args(root: Path, **overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "root": root,
        "type": "fix",
        "number": "036",
        "slug": "example",
        "allow_dirty": True,
        "remote": "origin",
        "base": "main",
        "allow_unmerged_head": False,
        "from_base": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_the_post_squash_shape_is_what_it_looks_like(tmp_path: Path) -> None:
    """The precondition, built rather than quoted. If HEAD were still contained in the base, the
    assertions below would pass for a reason that has nothing to do with the control.
    """
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)

    assert git(root, "rev-list", "--count", "HEAD", "^origin/main") == "1"
    assert git(root, "rev-parse", "HEAD^{tree}") == git(root, "rev-parse", "origin/main^{tree}"), (
        "the squash must carry the same content, or this is not the measured situation"
    )


def test_start_refuses_a_head_the_base_has_already_absorbed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """THE claim. The branch that would have been born conflicting is not created at all."""
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)
    branches_before = git(root, "branch", "--format=%(refname:short)")

    exit_code = command_start(start_args(root))

    assert exit_code == 1
    output = capsys.readouterr().out
    assert "1 commit(s) que origin/main nao contem" in output
    assert "--from-base" in output, (
        "the refusal must name a way out that stays inside the pipeline; pointing at a raw "
        "`git switch` would tell the operator to bypass the esteira the gate belongs to"
    )
    assert git(root, "branch", "--format=%(refname:short)") == branches_before, (
        "a branch was created despite the refusal"
    )


def test_start_still_works_from_a_base_that_contains_head(tmp_path: Path) -> None:
    """The other side: a control that refused everything would satisfy the test above too."""
    root = tmp_path / "repo"
    repo_in_step_with_its_base(root)

    exit_code = command_start(start_args(root, slug="in-step"))

    assert exit_code == 0
    assert git(root, "branch", "--show-current") == "fix/036-in-step"


def test_a_base_that_cannot_be_read_refuses_rather_than_assuming(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """NFR-002. Without a local `origin/main` the question cannot be asked, and "I could not ask"
    is not "the answer is yes". The refusal names the fetch that makes it answerable.
    """
    root = tmp_path / "repo"
    repo_in_step_with_its_base(root)
    git(root, "update-ref", "-d", "refs/remotes/origin/main")

    exit_code = command_start(start_args(root))

    assert exit_code == 1
    assert "git fetch origin" in capsys.readouterr().out


def test_the_override_is_explicit_and_says_what_it_overrides(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Stacking a slice on one not yet integrated is legitimate, so the control has an escape --
    named in the operator's own command line, never inferred, and it announces itself. It is
    listed as a known bypass vector in `unmerged_base_refusal`'s docstring (FR-009).
    """
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)

    exit_code = command_start(start_args(root, slug="stacked", allow_unmerged_head=True))

    assert exit_code == 0
    assert "--allow-unmerged-head" in capsys.readouterr().out
    assert git(root, "branch", "--show-current") == "fix/036-stacked"


def test_git_failing_is_a_refusal_not_a_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The third way the measurement can fail to happen, kept distinct from the other two."""
    root = tmp_path / "repo"
    repo_in_step_with_its_base(root)

    def unavailable(_root: Path, _remote: str, _base: str) -> str | None:
        raise delivery.GitUnavailableError("git nao esta disponivel")

    monkeypatch.setattr(delivery, "unmerged_base_refusal", unavailable)

    exit_code = command_start(start_args(root))

    assert exit_code == 1
    assert "a base nao foi medida" in capsys.readouterr().out


def test_the_bypass_vectors_say_what_is_mitigated_and_what_is_not() -> None:
    """FR-009: each enforcement point documents its own known bypass vectors. A list kept
    somewhere else goes stale unnoticed -- and a list that claims a mitigation nobody measured is
    worse than no list, because it reads as coverage.

    This assertion is about the CLAIM, not about a word being present. The first draft of that
    docstring said `git switch -c` was "mitigated for automated agents by the harness PreToolUse
    control". It is not: the hook matches `commit|push|merge|rebase|reset`, and `branch` sits on
    its read-only list, so `git switch -c`, `git checkout -b` and `git branch` all pass. Measured
    against the hook itself during review. An assertion on the word "PreToolUse" alone graded
    that false claim as satisfying FR-009.
    """
    documentation = unmerged_base_refusal.__doc__ or ""
    hook = Path(__file__).resolve().parents[2] / ".claude/hooks/enforce_delivery_pipeline.py"

    assert "KNOWN BYPASS VECTORS" in documentation
    assert "--allow-unmerged-head" in documentation
    assert "NOT mitigated" in documentation, (
        "the unmitigated vector must be named as unmitigated, not merely mentioned"
    )
    if hook.is_file():
        write_verbs = hook.read_text(encoding="utf-8").split("WRITE_VERB")[1][:200]
        assert "switch" not in write_verbs, (
            "the harness hook now covers `switch`, so the docstring's claim that this vector is "
            "unmitigated has become false and must be rewritten (task T221)"
        )


def test_the_measurement_uses_the_full_ref_not_a_dwim_name(tmp_path: Path) -> None:
    """`origin/main` is a DWIM name and `refs/tags/` outranks `refs/remotes/`. With a tag of that
    exact name, the count came back 0 and `start` accepted the state it exists to refuse --
    silently, because git's ambiguity warning goes to stderr and a successful capture drops it.
    """
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)
    git(root, "tag", "origin/main", "HEAD")

    assert delivery.base_ref_name("origin", "main") == "refs/remotes/origin/main"
    assert unmerged_base_refusal(root, "origin", "main") is not None, (
        "a tag shadowing the remote ref made the gate accept an unmerged head"
    )


def test_an_unborn_head_is_named_as_such(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A repository with no commit yet is a legitimate state, not a git failure. Blaming git for
    it hands the operator the wrong diagnosis for a situation `core.git_ref_exists` exists to
    tell apart. Shape: `git init` followed by `git fetch` -- a base ref present, no HEAD yet.
    """
    source = tmp_path / "source"
    repo_in_step_with_its_base(source)

    root = tmp_path / "repo"
    root.mkdir(parents=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "fetch", "-q", str(source), "main")
    git(root, "update-ref", "refs/remotes/origin/main", git(root, "rev-parse", "FETCH_HEAD"))

    exit_code = command_start(start_args(root))

    assert exit_code == 1
    assert "ainda nao tem commit algum" in capsys.readouterr().out


def test_an_empty_remote_or_base_refuses_without_inventing_a_command(tmp_path: Path) -> None:
    """The refusal used to print `git fetch ` -- an instruction that cannot be run."""
    root = tmp_path / "repo"
    repo_in_step_with_its_base(root)

    refusal = unmerged_base_refusal(root, "", "main")

    assert refusal is not None
    assert "nao podem ser vazios" in refusal


def test_from_base_branches_from_the_base_and_keeps_uncommitted_work(tmp_path: Path) -> None:
    """The escape the refusal actually points at, and the reason it exists.

    Without it, the only way out of a HEAD the base has absorbed is a raw `git switch -c <branch>
    origin/main` -- the gate telling the operator to step outside the pipeline it belongs to, and
    closing the harness hook over `switch` (task T221) would then leave no way out at all. The
    uncommitted work has to survive the switch, because that work IS the slice being started.
    """
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)
    (root / "work-in-progress.txt").write_text("the slice being started\n", encoding="utf-8")

    exit_code = command_start(start_args(root, slug="from-base", from_base=True))

    assert exit_code == 0
    assert git(root, "branch", "--show-current") == "fix/036-from-base"
    assert git(root, "rev-parse", "HEAD") == git(root, "rev-parse", "refs/remotes/origin/main")
    assert (root / "work-in-progress.txt").read_text(encoding="utf-8") == (
        "the slice being started\n"
    )


def test_the_operator_command_line_reaches_the_gate(tmp_path: Path) -> None:
    """The CLI boundary, which no test in this repository crossed.

    Removing the three `add_argument` lines left the whole suite green while
    `delivery.main([..., "start", ...])` raised `AttributeError: 'Namespace' object has no
    attribute 'allow_unmerged_head'`. A gate nobody can invoke is not a gate.
    """
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)

    args = parse_args(
        ["--root", str(root), "start", "--type", "fix", "--number", "036", "--slug", "via-cli"]
    )
    exit_code = command_start(args)

    assert exit_code == 1, "the gate was not reached through the parser the operator uses"
    assert args.remote == "origin"
    assert args.base == "main"
    assert args.allow_unmerged_head is False
    assert args.from_base is False


def test_remote_and_base_are_honoured_rather_than_hardcoded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Hardcoding `origin/main` inside the check left every test green, because none of them ever
    passed anything else.
    """
    root = tmp_path / "repo"
    repo_after_a_squash_merge(root)
    git(root, "update-ref", "refs/remotes/upstream/develop", "refs/remotes/origin/main")

    exit_code = command_start(start_args(root, remote="upstream", base="develop"))

    assert exit_code == 1
    assert "upstream/develop" in capsys.readouterr().out
