#!/usr/bin/env python
"""Reject git write operations issued outside the delivery pipeline.

=============================================================================
WHY THIS FILE EXISTS

Process documentation instructing an agent to use the delivery pipeline is a
request, not a control. On 2026-09-20 an agent ran `git commit` directly three
times while `scripts/delivery.py` sat unused, and nothing in the repository
observed it: the client hooks were not installed, and the server only sees a
push. This file is the enforcement point that acts *before* the tool call
runs, evaluated by the harness rather than chosen by the model.

It is deliberately narrow. It refuses the write verbs and names the pipeline
command that replaces each one, so the caller can correct course instead of
retrying the same invocation.

=============================================================================
THE KNOWN WAYS PAST THIS GUARD, WRITTEN ON PURPOSE.

A guard whose weakness is written down is a guard. A guard whose weakness is
left unsaid is theatre. The official documentation is explicit that a Bash
rule "doesn't match the same program invoked in a different form, so a deny or
ask rule covers the invocation Claude usually produces and isn't a security
boundary around the program." Concretely, this file does NOT stop:

  1. `bash -c 'git commit -m x'` -- the outer command is `bash`, and the git
     verb lives inside a quoted string this matcher does not decompose.
  2. `/usr/bin/git commit` or any absolute or relative path to the binary.
  3. A shell alias, a function, or an intermediate script that calls git
     internally: the harness sees the wrapper, never the git call inside it.
  4. Any session on a machine where this repository's `.claude/settings.json`
     is absent, since the configuration is read from the working copy.
  5. `.claude/settings.local.json`, which takes precedence over the versioned
     file and is not committed, so a local override can relax this.
  6. A human at a terminal. This guard binds tool calls made by an agent, not
     hands on a keyboard.
  7. `git checkout <branch-that-exists-only-on-a-remote>`, which git turns into
     a new local branch (DWIM). Telling it apart from an ordinary checkout of an
     existing branch means asking the repository which refs exist, and this file
     decides from the command string alone. Measured on 2026-09-21: allowed.
  8. `git stash pop`/`apply` onto a detached HEAD, and any other shape that
     reaches a new ref through a second command whose text does not name it.

Items 7 and 8 were found by measuring, not by reasoning: review ran every form
below against real git in a throwaway repository and kept the ones that created
a branch. That is the standard this list is held to, and the reason it grows.

What remains when this guard does not apply: the client hooks in
`scripts/git-hooks/` and the ruleset on the server. Those are the layers that
do not depend on this file existing.

=============================================================================
SCOPE

This control vigora on the workstation whose working copy carries it. It is
the third of four layers, ordered by resistance to bypass: process text
(none), client hook (bypassable with `--no-verify`), this harness control,
and the server-side ruleset (applies to every client).
"""

from __future__ import annotations

import json
import re
import sys

# Read verbs are unaffected: inspecting the repository is not delivery.
# A global option may sit between `git` and the verb, and a quote around either is removed by the
# shell before git sees the word. Measured on 2026-09-21: `-c color.ui=false` alone walked the
# guard past `switch -c`, and `"switch"` past it as well. The SAME hole was in `WRITE_VERB`, which
# predates this slice by five slices: `git -c a=b commit -m x` was allowed. One prefix now, so the
# next verb added inherits the coverage instead of repeating the defect.
#
# THE PREFIX ADMITS ANY GLOBAL OPTION, not a list of four. Review measured the first version of
# this line, which named `-c`, `-C`, `--no-pager` and `--literal-pathspecs`, and walked past it in
# real git with `git -p commit`, `git --work-tree=. commit` and `git --exec-path=/x reset --hard`.
# A list of the options somebody thought of is not a boundary: `git --help` documents fifteen and
# accepts abbreviations of each. The options that consume a SEPARATE argument are spelled out
# first, because otherwise their value is what the verb pattern would try to match; everything
# else is any remaining token that begins with a dash.
_Q = "[\"']?"
_GIT_OPTION = (
    r"(?:-[cC]\s+\S+"
    r"|--(?:exec-path|work-tree|git-dir|namespace|super-prefix|config-env|attr-source)"
    r"(?:=\S+|\s+\S+)"
    r"|--?[A-Za-z][\w-]*(?:=\S+)?)"
)
_GIT = _Q + r"\bgit\b" + _Q + r"\s+(?:" + _GIT_OPTION + r"\s+)*"


#: The shortest prefix git itself accepts for each long option, MEASURED rather than reasoned
#: about: one throwaway repository per candidate length, keeping the first one git does not call
#: ambiguous (`scripts/` has no home for a probe that needs to create branches, so the measurement
#: lives in this comment and in the test cases below).
#:
#: A single `minimum=3` stood here first, justified by one observation (`--c` is ambiguous)
#: generalised to seven options. Review measured it wrong for five of them: `git branch --d`
#: deletes, `--mo` renames, `--cr` creates, `--or` orphans and `--tr` tracks, and every one of
#: those walked past the guard that this function exists to close. The numbers below are what git
#: answered on 2026-09-21; a future git that adds an option starting with the same letters raises
#: its own minimum, which is why the test cases assert the prefix and not the table.
_MIN_PREFIX = {
    "delete": 1,
    "move": 2,
    "copy": 3,
    "force": 4,
    "create": 2,
    "orphan": 2,
    "track": 2,
}


def _long(name: str) -> str:
    """Match any abbreviation of a long option git itself would accept."""
    minimum = _MIN_PREFIX[name]
    tail = ""
    for character in reversed(name[minimum:]):
        tail = f"(?:{character}{tail})?"
    return "--" + name[:minimum] + tail


READ_ONLY = re.compile(
    _GIT + r"(?:status|log|diff|show|branch|rev-parse|"
    r"merge-base|rev-list|for-each-ref|ls-tree|ls-files|cat-file|describe|"
    r"remote|config|stash\s+list|worktree\s+list|cherry|blame)\b"
)

# Each write verb maps to the pipeline command that performs it with a record.
REPLACEMENTS = {
    "commit": "uv run python scripts/delivery.py commit",
    "push": "uv run python scripts/delivery.py publish --yes-remote",
    "merge": "uv run python scripts/delivery.py merge --auto --yes-remote",
    "rebase": "uv run python scripts/delivery.py start, then reapply the work",
    "reset": "uv run python scripts/delivery.py status, then decide deliberately",
}

WRITE_VERB = re.compile(
    _GIT + _Q + r"(commit|push|merge|rebase|reset)" + _Q + r"\b",
)
GH_MERGE = re.compile(r"\bgh\s+pr\s+merge\b")

# WHY THE DENY LIST IN `.claude/settings.json` DOES NOT MIRROR THIS FILE. That list matches on a
# command prefix and cannot tell a read from a write: `Bash(git branch:*)` would refuse
# `git branch --list`, and `Bash(git switch:*)` would refuse moving between branches at all. So
# the two layers the same settings file switches on deliberately cover different sets, and the
# prefix list carries only the verbs with no read form: `git update-ref` is there, `symbolic-ref`
# is not, because `git symbolic-ref HEAD` reads the current branch and is how scripts ask for it.
# Deciding per command is this file's job.
#
# WHERE THIS GUARD REFUSES TOO MUCH, declared because a limit left unsaid is the same defect as a
# bypass left unsaid. The decision reads the whole command string, deliberately, so a write verb
# reached through a pipe or a substitution is still caught -- and so is *writing about* these
# commands. Measured on 2026-09-21 over the 374 files this slice leaves versioned: 221 lines in
# 32 files would be refused if they appeared inside a shell invocation, 121 of them in 12 files
# from the branch guard alone, 92 of those under `tests/`. `scripts/git-hooks/pre-commit` is among
# them -- it prints, as advice, a command this file refuses, which is why it now names
# `delivery.py start` first.
# Documentation, specifications, mutation entries and the tests that assert on these very strings
# all hit it. The workaround is to write such text through a file rather than through the shell.
# Narrowing this without losing the compound-command coverage is its own slice. The widening in
# this change accounts for 101 of the 221: 82 in the test files that enumerate the forms, 12 in
# this file's own comments, 6 in the mutation inventory that names the forms it removes, and 1 in
# a docstring that quotes the command this round found -- the guard reading its own evidence.
#
# (An earlier version of this sentence said `38 of 39`,
# which was the branch-guard count for one test file rather than the breakdown the sentence
# described, and a later one was measured before the last two inventory entries existed.
# Both were found by review. A number here is only true of the tree it was taken from.)
#
# It used to refuse `git checkout <ref> -- <path>` whenever the path contained `-c`, `-C`, `-b`,
# `-B` or `-t` followed by a non-word character -- `git checkout main -- my-c.txt` restores a
# file and was read as creating a branch. `-c`, `-C`, `-b` and `-B` did that from T221 onwards;
# `-t` was added by this slice and briefly widened it to `notes-t.txt`. Both spellings are allowed
# now, with and without a ref before the separator, and both are pinned in
# `tests/unit/test_one_base_one_meaning.py`. (The first fix covered only the form WITH a ref, and
# the pinned cases all had one, so nothing noticed until review measured the other half.)
#
# WITH ONE QUALIFICATION that sentence does not carry: a pathspec BUILT BY A SUBSTITUTION is read
# from the raw string, by the rule in `branch_creation`, so it is refused again when it happens to
# contain `-c`, `-b` or `-t` before a non-word character. `git checkout main -- $(ls *-t.txt)` is
# refused; `git checkout main -- 'file$(x).txt'`, `-- $(cat list.txt)` and `-- $(git diff
# --name-only)` are not. Measured. That is the price of deciding substitutions from the raw string
# instead of finding where they end, and it is paid knowingly.
#
# IT STILL REFUSES `git worktree add <path> <existing-local-branch>`, which checks that branch out
# instead of creating one. Measured: with a name that is NOT already a local branch the same
# command creates it, and the command string cannot tell the two apart without asking the
# repository which refs exist -- the same undecidability as item 7 above. Refusing is the side
# this errs to, and the operator's route is `delivery.py start`.
#
# T221 / FR-011 / AC-007. Creating a branch is a write the pipeline records and this hook did not
# see: measured on 2026-09-21, `git switch -c`, `git checkout -b` and `git branch <name>` were all
# allowed, so the precondition T218 put into `start` -- refusing a HEAD the base already absorbed
# -- was reachable around with a single command. `start` gained `--from-base` in that same slice,
# which is what makes closing this vector possible without stranding an operator on an absorbed
# HEAD with no way to reach the base.
#
# Listing stays allowed, and that is the whole difficulty: `git branch` with no argument, or with
# only flags like `-a`, `-r`, `-v`, `--list`, `--show-current`, is how anyone looks at the
# repository. Only a form that names something, or that moves or deletes, is a write.
# `[^|&;\n\r]` on purpose: excluding the newline matters as much as excluding the pipe. Without
# it, `checkout main` followed on the next line by `python -c ...` read as one `checkout -c`, and
# four ordinary read commands were refused (measured over this repository's own files).
# `-t`/`--track` is here because `git checkout -t origin/x` creates a local branch, which review
# measured passing. The bare DWIM form (`git checkout <branch-only-on-the-remote>`) creates one
# too and is NOT here: it is indistinguishable from an ordinary checkout without asking the
# repository what refs exist, so it is declared in the header instead of guessed at.
BRANCH_CREATION = re.compile(
    _GIT
    + _Q
    + r"(?:switch|checkout)"
    + _Q
    + r"\s+[^|&;\n\r]*?(?:-c|-C|-b|-B|-t|"
    + _long("create")
    + "|"
    + _long("orphan")
    + "|"
    + _long("track")
    + r")\b"
)
#: `git branch` is the one verb where shape does not decide. Review measured `git branch -q novo`
#: creating a ref past a pattern whose rule was "the first token after the verb does not start
#: with a dash". The table that replaced it classified options by what their names suggest, and
#: review measured NINE of them wrong: `--sort=-committerdate novo`, `--format=%09 novo`,
#: `--column novo`, `--omit-empty novo`, `-i novo` and `--abbrev=7 novo` all leave a branch
#: behind while the guard said nothing, because "sounds like listing" was treated as "is listing".
#:
#: These three sets are DERIVED FROM MEASUREMENT, not from the names: every option in
#: `git branch -h` was run with a branch name beside it, in a throwaway repository, comparing
#: `for-each-ref` before and after. Only these put git into listing mode, where a following token
#: is a pattern rather than a name:
_BRANCH_LIST_MODE = frozenset(
    {
        "-l",
        "--list",
        "--show-current",
        # git itself refuses a name with these two, so either classification is safe; they are
        # here so that `git branch -a` and `git branch -r` stay readable.
        "-a",
        "--all",
        "-r",
        "--remotes",
        # These take a value AND list; both facts are needed, so they appear below as well.
        "--contains",
        "--no-contains",
        "--merged",
        "--no-merged",
        "--points-at",
    }
)
#: Options whose next token is their value and therefore not a branch name. `--sort refname novo`
#: and `--format %(refname) novo` both CREATE `novo`: the value is consumed, the name is not.
_BRANCH_CONSUMES_VALUE = frozenset(
    {
        "--contains",
        "--no-contains",
        "--merged",
        "--no-merged",
        "--points-at",
        "--sort",
        "--format",
        "--set-upstream-to",
        "-u",
    }
)
#: Options that change configuration and never a ref. `git branch -u main existing` rewrites the
#: upstream of a branch that already exists and leaves `for-each-ref` untouched; `git branch -u
#: main <new>` is refused by git itself. Either way there is no ref write to refuse, and counting
#: the branch name as a creation refused a read.
_BRANCH_CONFIG_ONLY = frozenset({"-u", "--set-upstream-to", "--unset-upstream"})
#: `-t`/`--track` are deliberately in NONE of the three sets, and this line is the reason. They
#: were in the set above, measured as "git refuses the combination" -- which git does, with TWO
#: arguments (`git branch -t <name> <start>`). With one, `git branch -t novo` creates `novo`, and
#: consuming the next token made that name the option's value: names=0, allowed. The measurement
#: was real and taken in the form the defect does not live in.
#: Deliberately in NEITHER set, because measurement put them there: `--column`, `--no-column`,
#: `--omit-empty`, `-i`, `--ignore-case`, `--abbrev=<n>`, `--color`, `-v`, `-q` and their long
#: spellings change how output looks and change nothing about whether a name creates a branch.
#: An option absent from both sets counts as neither listing nor value-consuming, so a name beside
#: it is a write -- which is the default this file wants, and the reason the sets name only what
#: was measured to belong in them.
BRANCH_VERB = re.compile(_GIT + _Q + r"branch" + _Q + r"(?=\s|$)")
BRANCH_WRITE_FLAG = re.compile(
    r"^(?:-[dDmMcCf]$|"
    + _long("delete")
    + r"$|"
    + _long("move")
    + r"$|"
    + _long("copy")
    + r"$|"
    + _long("force")
    + r"$)"
)


#: `2>&1`, `>out.txt`, `2> err.log`, `&>log`: shell plumbing, not arguments to git. Removed from
#: the command ONCE, before any of the four rules look at it, because every one of them treats
#: `&` as a command separator and `2>&1` contains one. Review measured what that cost: the scan
#: stopped at the `&`, so anything after a redirection was invisible. `git branch 2>&1 -D old`
#: deleted a branch, `git switch 2>&1 -c novo` created one, and `git 2>&1 commit -m x` walked
#: through the oldest gate in this file -- open since T205 and found only at the sixth review.
#:
#: Four of those had been refused by accident until this slice: `2>&1` was a token with no dash
#: in front, which was the old definition of a branch name. Teaching the guard to ignore
#: redirections token by token removed the accident that was saving it, which is why the removal
#: now happens here, once, rather than inside one of the rules.
#:
#: `&&` is left alone on purpose: the `&>` alternative requires the `>`, so a logical AND is
#: still a separator. There is a case for that.
#: `(?!\()` because `<(` and `>(` open a process substitution, not a redirection. Without it
#: the strip removed the opener, and the substitution behind a pathspec was allowed again --
#: a hole this slice had closed one round earlier, reopened by the fix for the next one. The
#: suites from every previous round are re-run after each change for exactly this reason.
#: `[^\S\n]*` rather than `\s*`: horizontal space only, so the search for the redirection's
#: target cannot cross a line break. A redirection followed by a newline is a syntax error in
#: bash (measured with `bash -n`), so nothing was exploitable either way -- but with `\s*` the
#: safety came from bash refusing the command rather than from this pattern, and review asked
#: for the narrower invariant.
REDIRECTION = re.compile(r"(?:\d*[<>]{1,2}|&>)(?!\()(?:&\d+|[^\S\n]*[^\s|&;<>]+)?")


def without_redirections(command: str) -> str:
    """Strip shell redirections, so `&` means only what the scanners think it means.

    THIS IS NOT LEXICAL ANALYSIS and does not pretend to be. It removes anything shaped like a
    redirection wherever it appears, quotes included: `--format='%(refname)>x'` reaches the rules
    below as `--format='%(refname) `. Measured, and harmless -- but harmless for one reason that
    has to survive the next edit.

    THE INVARIANT: the replacement is a SPACE, never the empty string. That is what makes this
    operation only ever subtract. Substituting `""` -- an entirely plausible simplification --
    would let the strip join two tokens into a command that was never written, and a guard that
    can invent commands is worse than one that misses some. Anything removed here can hide a
    write from the rules; nothing removed here can manufacture one.
    """
    return REDIRECTION.sub(" ", command)


def _expand(token: str) -> list[str]:
    """`-al` is `-a -l`. Without this, an aggregated form is one unrecognised token and the
    pattern beside it reads as a branch name: `git branch -al 'rem*'` was refused, and git lists.
    """
    if len(token) > 2 and token.startswith("-") and not token.startswith("--"):
        return [f"-{character}" for character in token[1:]]
    return [token]


def _branch_arguments_write(arguments: str) -> bool:
    """Decide one `git branch` invocation from its arguments, by git's own measured behaviour."""
    tokens = [part for token in arguments.split() for part in _expand(token)]
    listing = False
    configuring = False
    names = 0
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if BRANCH_WRITE_FLAG.match(token):
            return True
        head = token.split("=", 1)[0]
        if head in _BRANCH_CONFIG_ONLY:
            configuring = True
        if head in _BRANCH_LIST_MODE:
            listing = True
        if head in _BRANCH_CONSUMES_VALUE:
            skip_next = "=" not in token
            continue
        if head in _BRANCH_LIST_MODE:
            continue
        if not token.startswith("-"):
            names += 1
    if configuring:
        return False
    return names > 0 and not listing


#: The openers that start a command inside another command. NOT a delimiter: the first attempt at
#: this extracted the text between `$(` and `)` with a regex, which cannot cross a parenthesis, so
#: `$(git switch -c x-$(date +%s))` was invisible -- the same hole as before with one `$(` more.
#: Chasing it with a third delimiter would invite a fourth. What is asked instead is a yes/no
#: question a regex can answer honestly: does the text that was cut away contain any way to start
#: a command? If it does, the cut is not trusted and the raw string decides.
SUBSTITUTION_OPENER = ("$(", "`", "<(", ">(", "${")


def _without_pathspecs(command: str) -> str:
    """Drop everything after a standalone `--` in each command, because it is a list of paths.

    `git checkout -- my-c.txt` restores a file; the `-c` inside the filename is not an option, and
    neither is the `-t` in `notes-t.txt`. The first attempt at this excluded the separator with a
    per-character lookahead, which needed whitespace in front of the `--` and therefore only
    worked when a ref sat between the verb and the separator. Review measured the half that was
    left: the form with no ref -- the one people actually type -- was still refused.

    Done per segment, so a pathspec cannot hide a later command: `git checkout -- x && git switch
    -c y` keeps its second half.
    """
    kept: list[str] = []
    for segment in re.split(r"([|&;\n\r]+)", command):
        if re.fullmatch(r"[|&;\n\r]+", segment):
            kept.append(segment)
            continue
        tokens = segment.split()
        if "--" in tokens:
            tokens = tokens[: tokens.index("--")]
        kept.append(" ".join(tokens))
    return "".join(kept)


def branch_creation(command: str) -> bool:
    """True when this command creates a branch through `switch` or `checkout`.

    Two passes, because the two rules disagree about the same text: the pathspec cut says "what
    follows a `--` is a filename", and `decide`'s contract says "the whole string is examined,
    substitutions included". So the cut decides only when what it removed looks like filenames.
    The moment the removed text contains `$(`, a backtick, `<(`, `>(` or `${`, the raw string
    decides instead -- no attempt is made to find where the substitution ends, because the two
    versions of this that did try were each defeated by one more nesting level.

    DECLARED LIMIT, per NFR-005: this is not shell parsing and does not become it. A command that
    hides a write verb from a regex by other means -- `bash -c`, a variable holding the verb, an
    alias -- is out of reach here and is item 1 of the list at the top of this file.
    """
    trimmed = _without_pathspecs(command)
    if BRANCH_CREATION.search(trimmed) is not None:
        return True
    # What the cut removed. A pathspec is a list of filenames; if it holds an opener it is not
    # only that, and the whole raw string is read instead -- nesting, quoting and process
    # substitution included, because nothing here tries to find where the substitution ends.
    removed = command[len(trimmed) :] if command.startswith(trimmed) else command
    if any(opener in removed for opener in SUBSTITUTION_OPENER):
        return BRANCH_CREATION.search(command) is not None
    return False


def branch_write(command: str) -> bool:
    """True when any `git branch` in this command string writes a ref."""
    for match in BRANCH_VERB.finditer(command):
        rest = command[match.end() :]
        for separator in ("|", "&", ";", "\n", "\r"):
            rest = rest.split(separator, 1)[0]
        if _branch_arguments_write(rest):
            return True
    return False


# A branch is also created by `worktree add -b`, by writing the ref directly, and by a fetch
# refspec whose right-hand side is a local branch. All three were measured passing.
BRANCH_INDIRECT = re.compile(
    # `git worktree add ../wt-auto` creates a branch called `wt-auto` with no `-b` anywhere in
    # the command: measured. `--detach` is the form that does not, so it is the exception
    # rather than `-b` being the trigger.
    _GIT + _Q + r"worktree" + _Q + r"\s+add\b(?![^|&;\n\r]*?--detach\b)"
    # `refs/heads/` anywhere in the arguments, not pinned to the position right after the verb:
    # `git update-ref -m <message> refs/heads/x HEAD` wrote the ref straight past the anchored
    # version, which this same slice had written for this very verb.
    r"|" + _GIT + _Q + r"(?:update-ref|symbolic-ref)" + _Q + r"\s+[^|&;\n\r]*?refs/heads/"
    # `git stash branch <name>` creates a branch from a stash entry. Measured passing.
    r"|" + _GIT + _Q + r"stash" + _Q + r"\s+branch\b"
    # A refspec writes a LOCAL ref only when its right-hand side is one. The first version matched
    # any colon after `fetch`, which refused `git fetch https://host/o/r.git` (the `https:`) and
    # `git fetch origin +refs/heads/*:refs/remotes/origin/*` -- the shape that writes no local
    # branch at all. `(?!//)` drops URL schemes; the two negative lookaheads drop the remote and
    # tag namespaces, which `fetch` is supposed to write.
    r"|" + _GIT + _Q + r"fetch" + _Q + r"\s+[^|&;\n\r]*?(?:^|\s)\+?[\w.^~*/-]+:"
    r"(?!//|refs/remotes/|refs/tags/)[\w.*/-]+"
)


def decide(command: str) -> tuple[str, str] | None:
    """Return the refusal reason for `command`, or None to stay out of the way.

    The whole command string is examined, including compound forms, because a
    write verb reached through `&&`, a pipe or a substitution is still a write.
    Redirections are removed first, once: `&` is read as a command separator by
    every rule below, and `2>&1` contains one, so without this a four-character
    prefix hid everything after it.

    ONE QUALIFICATION, added after review measured it missing: `branch_creation`
    also drops everything after a `--` separator, since that is a list of paths
    and not options. That cut is honoured only while what it removed looks like
    filenames; if it contains anything that starts a command, the raw string
    decides. The other three checks never cut anything.
    """
    command = without_redirections(command)
    if GH_MERGE.search(command):
        return (
            "gh pr merge bypasses the delivery pipeline",
            "Run `uv run python scripts/delivery.py merge --auto --yes-remote`. It "
            "reads the merge result back from the pull request, records the squash "
            "commit as verified, and deletes the remote branch.",
        )
    if branch_creation(command) or branch_write(command) or BRANCH_INDIRECT.search(command):
        return (
            "creating, moving or deleting a branch outside the delivery pipeline",
            "Run `uv run python scripts/delivery.py start --type <t> --number <n> "
            "--slug <s>` instead, with `--from-base` when the current HEAD is one the base "
            "already absorbed. `start` measures that before the branch exists; a direct git "
            "invocation does not, and a branch born from an absorbed HEAD only says so "
            "later, as a conflicting pull request.",
        )
    match = WRITE_VERB.search(command)
    if match is None:
        return None
    verb = match.group(1)
    return (
        f"git {verb} bypasses the delivery pipeline",
        f"Run `{REPLACEMENTS[verb]}` instead. The pipeline records what was "
        "measured, which a direct git invocation does not.",
    )


def main() -> int:
    try:
        event: object = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        # A guard that cannot read the event cannot judge it. Staying silent
        # here is the honest outcome: refusing every tool call on a malformed
        # payload would break the session for a reason unrelated to delivery.
        return 0
    if not isinstance(event, dict):
        return 0
    tool_input = event.get("tool_input")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if not isinstance(command, str) or not command.strip():
        return 0
    # The same removal as in `decide`, for the same reason: this short circuit reads the command
    # too, and a redirection would truncate its scan and let a write through as a read.
    command = without_redirections(command)
    writes_branch = (
        branch_creation(command) or branch_write(command) or BRANCH_INDIRECT.search(command)
    )
    if READ_ONLY.search(command) and WRITE_VERB.search(command) is None and not writes_branch:
        return 0
    verdict = decide(command)
    if verdict is None:
        return 0
    reason, remedy = verdict
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"{reason}. {remedy}",
            }
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
