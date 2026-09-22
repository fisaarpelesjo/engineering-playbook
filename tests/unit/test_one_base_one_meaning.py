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

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pytest

from engineering_playbook.delivery import (
    command_publish,
    command_status,
    resolve_base,
)

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

    # `refs/heads/main`, spelled in full, and not the bare name: a tag called `main` outranks the
    # branch under DWIM resolution, so the bare name reintroduces the ambiguity this slice closes.
    assert resolve_base(root, "origin", "main") == "refs/heads/main"


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
        "git branch -d old",
        # Compound and quoted forms. The decision reads the whole command string, so a write
        # reached after `;` or `&&` is still a write.
        "cd /tmp && git switch -c feat/001-x",
        "git switch -c feat/001-x; echo done",
        'git "switch" -c feat/001-x',
        # Global options before the verb. `-c color.ui=false` alone walked the first version of
        # this guard past the very command the matrix row names (#61).
        "git -c color.ui=false switch -c feat/001-x",
        "git -c user.name=x checkout -b feat/001-x",
        "git -c a=b -c c=d switch -c feat/001-x",
        "git -C /abs/path switch -c feat/001-x",
        # Forced writes to an existing branch. `-f` moves a pointer and `-C` overwrites a branch;
        # neither creates one, and both were allowed.
        "git branch -f main origin/main",
        "git branch -C old new",
        "git branch --force main origin/main",
        # Branches created without naming `switch`, `checkout` or `branch` at all. The worktree
        # form matters most: `AGENT_POLICY` tells agents to use worktrees.
        "git worktree add -b feat/001-x ../wt",
        "git worktree add -B feat/001-x ../wt",
        "git checkout --orphan feat/001-x",
        "git update-ref refs/heads/feat-x HEAD",
        "git symbolic-ref refs/heads/x refs/heads/y",
        "git fetch origin main:feat/001-x",
        # Found by the independent review of this slice, each one confirmed creating a branch in
        # real git, not only passing the regex. The write-verb half of the same finding lives in
        # `test_delivery_pipeline_hook.py`, next to the guard it belongs to.
        "git -p switch -c feat/y",
        "git --work-tree=/x switch -c y",
        # Abbreviated long options. `--forc` works, `--for` is ambiguous and git itself refuses
        # it, which is why three characters is where the pattern starts.
        "git switch --creat feat/x",
        "git checkout --orph feat/x",
        "git branch --cop main copiada",
        "git branch --mov a b",
        "git branch --forc main origin/main",
        # `-m <message>` pushed `refs/heads/` off the position the first pattern anchored it to.
        "git update-ref -m msg refs/heads/x HEAD",
        # Two more ways to reach a new branch without naming one of the three verbs.
        "git stash branch from-stash",
        "git checkout -t origin/feat-x",
        "git switch --track origin/x",
        # Second review round. The first version of `_long` assumed three characters was the
        # shortest prefix git accepts; measured against git itself, that is true for two of the
        # seven options. `--d` deletes, `--mo` renames, `--cr` creates, `--or` orphans, `--tr`
        # tracks. Each case below is at the measured minimum, so it asserts the property rather
        # than the five strings a reviewer happened to send.
        "git branch --d old",
        "git branch --de old",
        "git branch --mo old new",
        "git switch --cr short-create",
        "git checkout --or short-orphan",
        "git checkout --tr origin/remote-only",
        # And the rule for `branch` itself, which was "the first token has no dash in front".
        # Measured: `-q`, `-v`, `--quiet`, `--color`, `--create-reflog`, `--no-track` and `-t` all
        # leave a branch behind, and none of them made the old pattern fire.
        "git branch -q novo",
        "git branch --quiet novo",
        "git branch -v novo",
        "git branch -vv novo",
        "git branch --verbose novo",
        "git branch --create-reflog novo",
        "git branch --no-track novo main",
        "git branch -t novo main",
        "git branch --track novo main",
        "git branch --color novo",
        "git branch --cre novo",
        # `worktree add <path>` names the branch after the path and needs no `-b` at all.
        "git worktree add ../wt-auto",
        "git worktree add ../wt feature",
        # Third review round. The table that replaced the pattern classified nine options by
        # what their names suggest; measured against git, every one of these leaves a branch
        # behind. "Sounds like listing" is not "is listing", and the sets are now derived from
        # running each option in `git branch -h` with a name beside it.
        "git branch --column n-col",
        "git branch --no-column n-nocol",
        "git branch --omit-empty n-oe",
        "git branch --sort=-committerdate n-sort",
        "git branch --sort refname n-sort2",
        "git branch --format=%09 n-fmt",
        "git branch --format %(refname) n-fmt2",
        "git branch --abbrev=7 n-abbrev",
        "git branch -i n-icase",
        "git branch --ignore-case n-icase2",
        "git branch --color n-color",
        "git branch -- n-dashdash",
        # A pathspec must not launder what comes after it.
        "git checkout -- x && git switch -c y",
        "git checkout main -- x; git branch novo",
        # `worktree add <path> <name>` creates unless the name is already a local branch, which
        # the command string cannot tell. Refusing is the side this errs to.
        "git worktree add ../w2 remote-only",
        "git worktree add ../w3",
        # Sixth review round, and the widest hole of the six. Every rule here reads `&` as a
        # command separator, and `2>&1` contains one, so the scan stopped at the redirection and
        # everything after it was invisible. Four of these were refused before this slice only by
        # accident -- `2>&1` was a token with no dash in front, which was the old definition of a
        # branch name -- and teaching the guard to ignore redirections removed the accident.
        "git branch 2>&1 novo",
        "git branch &>log novo",
        "git branch 2>&1 -D old",
        "git branch 2>&1 -d old",
        "git branch >out.txt novo",
        "git switch 2>&1 -c novo",
        "git checkout 2>&1 -b novo",
        "git worktree 2>&1 add ../wt",
        "git update-ref 2>&1 refs/heads/x HEAD",
        # A separator is still a separator: the strip must not swallow `&&`.
        "git status && git branch novo",
        "git status ; git switch -c novo",
        "git status | tee log && git branch -D old",
    ],
)
def test_branch_writes_are_refused(command: str) -> None:
    """The vector T218 left open: its precondition lived in `start`, and this is the one
    command that walked past `start` entirely.

    The list is the record of what was measured, not a sample. #61 measured 51 forms against
    the first version of this guard and found six families passing; every one of them is a
    case here. It is still a list and not a proof of exhaustion, which is why the matrix row
    reads `parcial`.
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
        "git rev-parse HEAD",
        "git show-ref",
        # `fetch` without a refspec writes no local branch, and `worktree list` writes nothing at
        # all. Both had to stay allowed while the refspec form became a refusal.
        "git worktree list",
        "git fetch origin",
        "git fetch --all --prune",
        # The newline family (#61). A multi-line shell block arrives as one command string, and
        # `[^|&;]` did not exclude the line break, so the NEXT line's `-c` was read as a flag of
        # the previous `switch`. Four ordinary reads were refused this way.
        "git checkout main\npython -c 'print(1)'",
        "git switch main\nmake -C build",
        "git switch main\ngrep -c foo file.txt",
        "git fetch origin\npython -c 'print(1)'",
        # ALTO 2 of the review: the first version of the `fetch` rule matched any colon after
        # the verb, so it refused a URL and refused the refspec shape that writes no local
        # branch at all -- one undue refusal traded for another.
        "git fetch https://github.com/o/r.git main",
        "git fetch git@github.com:owner/repo.git main",
        "git fetch origin +refs/heads/*:refs/remotes/origin/*",
        "git fetch origin refs/heads/main:refs/remotes/origin/main",
        "git stash list",
        "git symbolic-ref HEAD",
        "git -p log",
        "git -c color.ui=false status",
        # The listing forms, measured one by one against git: with any of these present the
        # non-flag token is a pattern, not a branch name. This is the inverse of the rule above
        # and the reason the guard can refuse `branch -q novo` without refusing `branch -v`.
        "git branch -v",
        "git branch --list feat/*",
        "git branch --contains HEAD",
        "git branch --merged main",
        "git branch --no-merged main",
        "git branch --points-at HEAD",
        "git branch --sort=refname",
        "git branch --format=%(refname)",
        "git branch -i --list MAIN",
        "git branch --column",
        # A pathspec is not an option. `-t` refused these until the `--` separator was excluded,
        # and `-c`/`-b` had been refusing the same shape since T221.
        "git checkout main -- notes-t.txt",
        "git checkout main -- my-c.txt",
        "git checkout main -- a-B.txt",
        "git checkout main -- scripts/run-t.sh",
        "git switch main -- ignore-t.txt",
        "git worktree add --detach ../wt HEAD",
        # The canonical "throw this file away" has no ref before the separator, and the first
        # version of the pathspec exclusion needed one. The four cases pinned then all had a ref,
        # so nothing noticed that half the family was still refused.
        "git checkout -- my-c.txt",
        "git checkout -- notes-t.txt",
        "git checkout -- src/a-b.py",
        "git checkout -- x-C.txt",
        "git checkout -- a-B.txt",
        "git restore -- my-c.txt",
        # Aggregated short flags: `-al` is `-a -l`, and without expanding it the pattern beside
        # it read as a branch name.
        "git branch -al rem*",
        "git branch -lv",
        # The options that really do put git in listing mode, so the token beside them is a
        # pattern. These six are the entire measured set, and `-a`/`-r` join them because git
        # refuses a name with those outright.
        "git branch --contains HEAD n",
        "git branch --merged main n",
        "git branch --no-merged main n",
        "git branch --points-at HEAD n",
        "git branch -l feat/*",
        # The reads the same strip has to keep allowing.
        "git branch 2>&1",
        "git branch > out.txt",
        "git branch >> out.txt",
        "git branch 2> err.log",
        "git branch < in.txt",
        "git branch 2>/dev/null",
        "git branch >out.txt",
        "git branch --list feat/* 2>&1",
        "git status && git branch -a",
        # Configuration, never a ref: measured with `for-each-ref` either side.
        "git branch -u main existing",
        "git branch --set-upstream-to main existing",
        "git branch --unset-upstream existing",
        # The redirection strip is not a lexer: it removes a `>` inside quotes too, together
        # with the token after it. Harmless because the replacement is a SPACE and never the
        # empty string, so the operation can only subtract -- it can never join two tokens into
        # a command nobody wrote. These pin the harmless half of that.
        "git branch --format='%(refname)>x'",
        "git branch --format='%(refname)->%(objectname)'",
        "git log --format='%h -> %s'",
    ],
)
def test_looking_at_the_repository_stays_allowed(command: str) -> None:
    """The whole difficulty of this change. `git branch` is how anyone looks at branches, and
    a control that refuses reading is a control somebody turns off.
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


# --------------------------------------------------------------------------------------
# #61: the commands themselves, not only the resolver
#
# The tests above exercise `resolve_base` in isolation. Measured in a sandbox copy, reverting BOTH
# call sites to the pre-T219 referent (`local_commits(args.root, args.base)` in `command_publish`
# and in `command_status`) left the whole suite with exactly the failures of the unmutated
# baseline: the 480 tests the suite had on 2026-09-21, none newly red. The correction this slice
# exists for could be undone in full with the NFR-004 gate reporting green. What follows drives
# each command end to end in the post-squash repository and asserts the number the operator sees.
# --------------------------------------------------------------------------------------


def argv_namespace(**fields: object) -> argparse.Namespace:
    return argparse.Namespace(**fields)


def a_branch_at_the_squash(root: Path, branch: str = "feat/001-x") -> None:
    """Put a real branch on the integrated content, because the detached HEAD the fixture leaves
    behind is not a state `publish` accepts, and `publish` is half of what is being measured.
    """
    git(root, "switch", "-c", branch)


def a_project_state(root: Path, body: str = "issue: 61\n") -> None:
    """`status` and `publish` both read `.project/state.yml` unconditionally."""
    (root / ".project").mkdir(parents=True, exist_ok=True)
    (root / ".project/state.yml").write_text(body, encoding="utf-8")


def an_approved_prepare(root: Path) -> None:
    receipt = root / ".project/delivery/prepare.yml"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        "status: approved\n"
        f"head: {git(root, 'rev-parse', 'HEAD')}\n"
        f"branch: {git(root, 'rev-parse', '--abbrev-ref', 'HEAD')}\n",
        encoding="utf-8",
    )


def test_status_counts_against_the_server_base(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The number the operator reads. Against the server's base this branch is published: 0. Against
    the stale local branch of the same name it is 1, which would send someone to publish work the
    server already integrated.
    """
    root = tmp_path / "repo"
    repo_whose_work_the_server_already_took(root)
    a_branch_at_the_squash(root)
    a_project_state(root)

    exit_code = command_status(argv_namespace(root=root, remote="origin", base="main"))
    printed = capsys.readouterr().out

    assert exit_code == 0
    assert "local_commits: 0" in printed, printed
    assert "base_ref: refs/remotes/origin/main" in printed, printed
    # And the other referent really would have said something else, so the assertion above is
    # discriminating rather than incidentally true.
    assert git(root, "rev-list", "--count", "HEAD", "^refs/heads/main") == "1"


def test_status_says_when_it_fell_back(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A fallback the operator cannot see is a fallback that lies by omission: the same count, from
    a different base, with nothing on screen to tell them apart.
    """
    root = tmp_path / "repo"
    repo_whose_work_the_server_already_took(root)
    a_branch_at_the_squash(root)
    a_project_state(root)
    git(root, "update-ref", "-d", "refs/remotes/origin/main")

    command_status(argv_namespace(root=root, remote="origin", base="main"))
    printed = capsys.readouterr().out

    assert "base_ref: refs/heads/main (no remote-tracking ref; fell back)" in printed, printed
    assert "local_commits: 1" in printed, printed


def test_publish_refuses_work_the_server_already_has(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The consequence of the same defect one stage later. With the pre-T219 referent `publish`
    measures one unpublished commit, passes its own gate, and goes on to push content the base
    already contains.

    `issue_is_open` is the only thing stubbed: it reaches GitHub, and this repository has no
    remote. Everything else -- the branch name, the prepare receipt, the declared issue -- is real
    state built above, because those are the preconditions that decide whether the measured line
    is reached at all.
    """
    root = tmp_path / "repo"
    repo_whose_work_the_server_already_took(root)
    a_branch_at_the_squash(root)
    an_approved_prepare(root)
    a_project_state(root)

    def the_issue_is_open(root: Path, number: object) -> bool:
        return True

    monkeypatch.setattr("engineering_playbook.delivery.issue_is_open", the_issue_is_open)

    exit_code = command_publish(
        argv_namespace(root=root, remote="origin", base="main", yes_remote=True, force=False)
    )
    printed = capsys.readouterr().out

    assert exit_code == 1
    assert "no local commit to publish" in printed, printed
    # Against `refs/heads/main` there IS a commit, so reaching this refusal is a statement about
    # which reference the command used, not about the repository being empty.
    assert git(root, "rev-list", "--count", "HEAD", "^refs/heads/main") == "1"


def test_an_empty_remote_is_refused_and_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """#61. The empty-value guard was added to stop `resolve_base` answering from a reference it
    had not been given. Measured by review: it reached the operator as a traceback, because both
    call sites catch only `GitUnavailableError`.

    `unmerged_base_refusal` answers the identical condition with a sentence the operator can read.
    NFR-002 is about what a control does when it cannot measure; a stack trace is the shape that
    tells them nothing about which flag was wrong.
    """
    root = tmp_path / "repo"
    repo_whose_work_the_server_already_took(root)
    a_branch_at_the_squash(root)
    a_project_state(root)

    exit_code = command_status(argv_namespace(root=root, remote="", base="main"))
    printed = capsys.readouterr().out

    assert exit_code == 0, "status is a diagnostic: it reports what it could not measure"
    assert "local_commits: unmeasured" in printed, printed
    assert "remote and base cannot be empty" in printed, printed


def test_publish_refuses_an_empty_base_rather_than_raising(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The same condition where it decides something: `publish` must refuse, not raise."""
    root = tmp_path / "repo"
    repo_whose_work_the_server_already_took(root)
    a_branch_at_the_squash(root)
    an_approved_prepare(root)
    a_project_state(root)

    def the_issue_is_open(root: Path, number: object) -> bool:
        return True

    monkeypatch.setattr("engineering_playbook.delivery.issue_is_open", the_issue_is_open)

    exit_code = command_publish(
        argv_namespace(root=root, remote="origin", base="", yes_remote=True, force=False)
    )
    printed = capsys.readouterr().out

    assert exit_code == 1
    assert "remote and base cannot be empty" in printed, printed
    assert "Nada foi publicado" in printed, printed
