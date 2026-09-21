"""T219 and T221: two commands that reasoned about references that were not the ones that count.

T219 / FR-005. `--base` had two referents. Measured on 2026-09-21, in this repository, on a branch
whose work the server had already integrated:

    git rev-list --count HEAD ^refs/heads/main            -> 8
    git rev-list --count HEAD ^refs/remotes/origin/main   -> 0

Same flag, same default, two answers. `start` resolved the remote ref and refused correctly, while
`publish` and `status` resolved the local branch and would have reported eight commits as
unpublished that the base on the server already had. It is #36 seen from the other side.

T221 / FR-011 / AC-007. The harness hook covered `commit|push|merge|rebase|reset` and left branch
creation alone, so the precondition T218 put into `start` was reachable around with one command.
That vector could only be closed once `start` had `--from-base`, or an operator on an absorbed HEAD
would have had no way to reach the base at all.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engineering_playbook.delivery import resolve_base

HOOK = Path(__file__).resolve().parents[2] / ".claude/hooks/enforce_delivery_pipeline.py"


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
    return done.stdout.strip()


def repo_whose_work_the_server_already_took(root: Path) -> None:
    """The ordinary state after a squash merge: the remote base has the content, the local branch
    of the same name does not, because nothing checked it out.
    """
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    base = git(root, "rev-parse", "HEAD")

    (root / "b.txt").write_text("the slice\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "the slice")
    tree = git(root, "rev-parse", "HEAD^{tree}")

    squash = git(root, "commit-tree", tree, "-p", base, "-m", "squash: the slice")
    git(root, "update-ref", "refs/remotes/origin/main", squash)
    # HEAD sits on the squash, which is what a checkout looks like after fetching an integrated
    # slice; `refs/heads/main` stays where it was, because nothing checked it out. That gap is the
    # whole point: the local branch of the same name is not the base the server used.
    git(root, "update-ref", "refs/heads/main", base)
    git(root, "checkout", "-q", squash)


# --------------------------------------------------------------------------------------
# T219: one base, one meaning
# --------------------------------------------------------------------------------------


def test_the_remote_ref_is_what_base_means(tmp_path: Path) -> None:
    """THE claim. Integration happens on the server, so the base that counts is the server's."""
    root = tmp_path / "repo"
    repo_whose_work_the_server_already_took(root)

    assert resolve_base(root, "origin", "main") == "refs/remotes/origin/main"


def test_the_two_referents_really_do_disagree(tmp_path: Path) -> None:
    """The measurement this slice exists for, rebuilt: eight against zero in the real repository,
    one against zero here. If they agreed, the resolver would be choosing between equals.
    """
    root = tmp_path / "repo"
    repo_whose_work_the_server_already_took(root)

    against_local = git(root, "rev-list", "--count", "HEAD", "^refs/heads/main")
    against_remote = git(root, "rev-list", "--count", "HEAD", "^refs/remotes/origin/main")

    assert against_local != against_remote, "the fixture does not reproduce the divergence"
    assert against_remote == "0", "the server already has this content"


def test_a_repository_that_never_fetched_falls_back_to_the_local_branch(tmp_path: Path) -> None:
    """Declared, not silent. With no remote-tracking ref there is nothing better to answer from,
    and refusing every command there would be worse than answering from what is present.

    `start` is the exception and refuses instead, because branching from an unmeasured base is the
    defect #36 recorded.
    """
    root = tmp_path / "repo"
    repo_whose_work_the_server_already_took(root)
    git(root, "update-ref", "-d", "refs/remotes/origin/main")

    assert resolve_base(root, "origin", "main") == "main"


def test_the_remote_is_honoured_rather_than_assumed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    repo_whose_work_the_server_already_took(root)
    git(root, "update-ref", "refs/remotes/upstream/develop", "refs/remotes/origin/main")

    assert resolve_base(root, "upstream", "develop") == "refs/remotes/upstream/develop"


def test_status_can_be_told_which_remote_it_is_comparing_against() -> None:
    """`status` accepted `--base` and not `--remote`, so it could be told which branch to compare
    against and not which remote that branch belongs to.
    """
    from engineering_playbook.delivery import parse_args

    args = parse_args(["status", "--base", "develop", "--remote", "upstream"])

    assert (args.base, args.remote) == ("develop", "upstream")


# --------------------------------------------------------------------------------------
# T221: the hook sees branch writes
# --------------------------------------------------------------------------------------


def hook_verdict(command: str) -> bool:
    """True when the harness control refuses this command."""
    completed = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_input": {"command": command}}),
        capture_output=True,
        text=True,
    )
    return "deny" in completed.stdout


@pytest.mark.parametrize(
    "command",
    [
        "git switch -c feat/001-x",
        "git checkout -b feat/001-x",
        "git switch --create feat/001-x",
        "git branch feat/001-x",
        "git branch -D feat/001-x",
        "git branch -m old new",
        "cd /tmp && git switch -c feat/001-x",
    ],
)
def test_branch_writes_are_refused(command: str) -> None:
    """The vector T218 left open: its precondition lived in `start`, and this is the one command
    that walked past `start` entirely.
    """
    assert hook_verdict(command), f"the hook allowed {command!r}"


@pytest.mark.parametrize(
    "command",
    [
        "git branch",
        "git branch -a",
        "git branch -r",
        "git branch --list",
        "git branch --show-current",
        "git switch main",
        "git checkout main",
        "git status --short",
        "git log --oneline -3",
    ],
)
def test_looking_at_the_repository_stays_allowed(command: str) -> None:
    """The whole difficulty of this change. `git branch` is how anyone looks at branches, and a
    control that refuses reading is a control somebody turns off.
    """
    assert not hook_verdict(command), f"the hook refused {command!r}, which only reads"


def test_the_refusal_names_the_command_that_replaces_it() -> None:
    """A refusal that does not say what to run instead teaches people to route around it."""
    completed = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps({"tool_input": {"command": "git switch -c feat/001-x"}}),
        capture_output=True,
        text=True,
    )
    reason = json.loads(completed.stdout)["hookSpecificOutput"]["permissionDecisionReason"]

    assert "delivery.py start" in reason
    assert "--from-base" in reason, (
        "the escape has to be named, or an operator on an absorbed HEAD is stranded"
    )
