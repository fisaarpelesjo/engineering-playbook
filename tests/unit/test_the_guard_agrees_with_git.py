"""The cases are taken from git, not written by whoever wrote the guard.

WHY THIS FILE EXISTS. Four rounds of independent review on one slice (#61) found the same defect
four times, in four different places:

- the prefix admitting global options was measured on the four options someone had written down,
  and `git -p commit` walked past it;
- `_long`'s minimum was measured on one option (`--c` is ambiguous) and generalised to seven, and
  `git branch --d`, `--mo`, `--cr`, `--or` and `--tr` walked past it;
- the listing/writing table was filled in by reading option NAMES, and nine options that sound
  like listing -- `--sort`, `--format`, `--column`, `-i`, `--abbrev` among them -- create a branch;
- `-t` was measured in the two-argument form, where git refuses it, while `git branch -t <name>`
  with one argument creates.

Every one of those measurements was real. Each was taken on a sample chosen by the same reasoning
that produced the thing being tested, so each sample covered exactly what the hypothesis predicted
and nothing else. More rounds of review do not fix that; a different source of cases does.

So this file asks git twice over. `git branch --git-completion-helper` is git declaring its own
long options, and the trailing `=` on some of them is git declaring which take a value; `git
branch -h` supplies the short ones. Each option is then run against a real repository in several
argument shapes, `for-each-ref` says whether a ref appeared or moved, and the guard must have
reached the same verdict. Nothing here enumerates an option by hand: a future git that adds one,
or changes what one does, changes the cases without anyone editing this file.

It found two things on its first run, before ever being committed: the guard refused
`git branch -h 2>&1`, because a shell redirection is a token with no dash in front and that is
this guard's definition of a branch name; and the first version of this file shared one repository
across options, so `-m` renamed the branch HEAD pointed at and every later case measured a
different repository than it thought. Both are fixed; the second is why the fixture is per-option.

WHAT IT DOES NOT COVER, declared per NFR-005. Only `git branch` is generated this way, because it
is the verb whose decision is a table this file can falsify. `switch`, `checkout`, `worktree`,
`update-ref` and `fetch` keep their enumerated cases in `test_one_base_one_meaning.py`; extending
generation to them is worth doing and is not done here. A shape git itself refuses is not asserted
in either direction: git having refused, the guard's answer changes nothing.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

import pytest

HOOK_PATH = Path(__file__).resolve().parents[2] / ".claude/hooks/enforce_delivery_pipeline.py"

#: A value for each option that needs one, so the shape is exercised rather than rejected.
VALUES = {
    "--contains": "HEAD",
    "--no-contains": "HEAD",
    "--merged": "main",
    "--no-merged": "main",
    "--points-at": "HEAD",
    "--sort": "refname",
    "--format": "%(refname)",
    "--abbrev": "7",
    "--set-upstream-to": "main",
    "-u": "main",
    "--color": "never",
    "--column": "always",
    "--track": "direct",
    "-t": "direct",
}

#: Options that talk to something outside the repository, or that open an editor.
EXCLUDED = {"--edit-description", "--recurse-submodules"}

#: Options git refuses in every shape this file tries, so the guard is never compared for them.
#: Pinned, because "the guard agreed" and "nothing was compared" look identical in a green run,
#: and review found ten options sitting in the second state while the file claimed the first.
#: Four of these are the ones git rejects with `the -a, and -r, options to 'git branch' do not
#: take a branch name`. `--unset-upstream` is here because every branch in the fixture has no
#: upstream to unset, so git refuses that too. All five measured, none assumed.
UNMEASURABLE = {"-a", "--all", "-r", "--remotes", "--unset-upstream"}


def load_decide() -> Callable[[str], object]:
    spec = importlib.util.spec_from_file_location("delivery_hook", HOOK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.decide


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def refs(root: Path) -> dict[str, str]:
    lines = git(root, "for-each-ref", "--format=%(refname) %(objectname)").stdout.splitlines()
    return dict(line.split(" ", 1) for line in lines if " " in line)


def declared_options() -> list[str]:
    """What git says its own options are, long ones from the completion helper and short ones
    from the usage text. The helper is the authority: it is what git offers a shell completing
    this command, and it marks value-taking options with a trailing `=`.
    """
    # Asked inside a repository this function makes for itself, never in the working directory.
    # The completion helper answers `fatal: not a git repository` anywhere else, and discovery
    # would fall back to the short options alone without saying so. Measured: the mutation harness
    # runs the suite from a copy with no `.git`, and the entry that points here reported
    # `unusable` until the discovery brought its own repository.
    workspace = Path(tempfile.mkdtemp(prefix="git-options-"))
    try:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=workspace, capture_output=True)
        helper = subprocess.run(
            ["git", "branch", "--git-completion-helper"],
            cwd=workspace,
            capture_output=True,
            text=True,
        )
        usage = subprocess.run(
            ["git", "branch", "-h"], cwd=workspace, capture_output=True, text=True
        )
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
    options = [token.rstrip("=") for token in helper.stdout.split() if token.startswith("--")]
    for match in re.finditer(r"(?<![\w-])(-[a-zA-Z])(?![\w-])", usage.stdout + usage.stderr):
        if match.group(1) not in options:
            options.append(match.group(1))
    return [option for option in options if option not in EXCLUDED and option != "--"]


def shapes(option: str) -> list[list[str]]:
    """The argument shapes each option is tried in.

    Both the one-argument and the two-argument form, because `-t` is the option that hid behind
    having only one of them: git refuses `branch -t <name> <start>` and creates for
    `branch -t <name>`, and the table was written from the form that refuses.
    """
    forms = [
        [option, "NAME"],
        [option, "NAME", "main"],
        # A name that ALREADY EXISTS. Without it, `-d`, `-D` and `--delete` were handed a branch
        # that was never there, git answered "branch not found", and the shape was skipped as one
        # git refuses -- so the three spellings of deleting a branch, which the guard decides with
        # its own flag table, were never once compared against git. Review measured ten options
        # in that position. `EXISTING` is created by the fixture.
        [option, "EXISTING"],
        [option, "EXISTING", "main"],
    ]
    if option in VALUES:
        forms.append([option, VALUES[option], "NAME"])
        forms.append([f"{option}={VALUES[option]}", "NAME"])
        forms.append([option, VALUES[option], "EXISTING"])
    return forms


OPTIONS = declared_options()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """One repository per option. Shared state is not an economy here: `-m` and `-M` rename the
    branch HEAD points at, and the first version of this file measured every later option against
    a repository it no longer described.
    """
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "user.name", "Test")
    (root / "a.txt").write_text("a\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    # `existing` is left BEHIND the tip on purpose. With it at the same commit as HEAD,
    # `git branch -f existing` and `git branch -C existing` rewrite the ref to the value it
    # already had, `for-each-ref` sees nothing move, and a real write is measured as a read --
    # which is how this file reported the guard as wrong about `-f` and `-C` when the guard was
    # right. A ref write that writes the same bytes is still a write.
    git(root, "branch", "existing")
    (root / "b.txt").write_text("b\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "second")
    git(root, "update-ref", "refs/remotes/origin/only-remote", "HEAD")
    return root


@pytest.mark.parametrize("option", OPTIONS, ids=OPTIONS)
def test_the_guard_agrees_with_git_about_this_option(option: str, repository: Path) -> None:
    """A ref appearing or moving must be a refusal; no ref changing must not be."""
    decide = load_decide()
    disagreements: list[str] = []
    measured = 0
    for index, form in enumerate(shapes(option)):
        name = f"generated-{index}"
        arguments = [
            name if part == "NAME" else "existing" if part == "EXISTING" else part for part in form
        ]
        before = refs(repository)
        head = git(repository, "symbolic-ref", "-q", "HEAD").stdout.strip()
        done = git(repository, "branch", *arguments)
        after = refs(repository)

        # Put the repository back before the next shape, HEAD included.
        for ref in set(after) - set(before):
            git(repository, "update-ref", "-d", ref)
        for ref, oid in before.items():
            if after.get(ref) != oid:
                git(repository, "update-ref", ref, oid)
        if head:
            git(repository, "symbolic-ref", "HEAD", head)

        wrote = after != before
        if not wrote and done.returncode != 0:
            continue
        measured += 1
        command = "git branch " + " ".join(arguments)
        refused = decide(command) is not None
        if refused != wrote:
            disagreements.append(
                f"git {'wrote a ref' if wrote else 'wrote nothing'} for {command!r}, "
                f"and the guard {'refused' if refused else 'allowed'} it"
            )

    assert disagreements == [], "\n".join(disagreements)

    # A green test that compared nothing is the failure mode this file was written to remove, so
    # the options git refuses in every shape are pinned rather than passing quietly. Both
    # directions: one falling silent is a failure, and one that starts being measurable is too.
    if measured == 0:
        assert option in UNMEASURABLE, (
            f"{option} was not compared against git in any shape, and is not declared unmeasurable"
        )
    else:
        assert option not in UNMEASURABLE, (
            f"{option} is declared unmeasurable but {measured} shape(s) were compared"
        )


def test_the_generation_found_something_to_measure() -> None:
    """The file is vacuous if git stops answering. A floor rather than an exact count: the point
    is to catch a helper that changed shape, not to pin a number that moves with git's version.
    """
    assert len(OPTIONS) >= 20, f"only {len(OPTIONS)} options came back from git: {OPTIONS}"
    # Deliberately not `--force`: git's completion helper offers `-f` and no long spelling for
    # it, which is itself a reminder that this list is git's and not mine.
    for expected in ("--list", "--delete", "--move", "--sort", "--track", "-d", "-f", "-m"):
        assert expected in OPTIONS, f"{expected} missing from git's own declaration: {OPTIONS}"
