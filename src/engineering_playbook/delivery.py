from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from .attestation import (
        SIGNER_WORKFLOW_PATH,
        attestation_covers_tree,
        repository_identity,
        verdict_is_expected,
    )
    from .core import (
        ROOT,
        GhUnavailableError,
        GitUnavailableError,
        git_branch,
        git_capture,
        git_head,
        git_ref_exists,
        git_status,
        git_tree,
        load_yaml,
        utc_now,
        validate_conventional_title,
        verify_root,
        write_yaml_atomic,
    )
except ImportError:
    from engineering_playbook.attestation import (
        SIGNER_WORKFLOW_PATH,
        attestation_covers_tree,
        repository_identity,
        verdict_is_expected,
    )
    from engineering_playbook.core import (
        ROOT,
        GhUnavailableError,
        GitUnavailableError,
        git_branch,
        git_capture,
        git_head,
        git_ref_exists,
        git_status,
        git_tree,
        load_yaml,
        utc_now,
        validate_conventional_title,
        verify_root,
        write_yaml_atomic,
    )

MAIN_BRANCHES = {"main", "master"}
BRANCH_TYPES = {
    "feat",
    "fix",
    "perf",
    "refactor",
    "test",
    "docs",
    "build",
    "ci",
    "chore",
    "spike",
}
REMOTE_COMMANDS = {"publish", "merge"}
PREPARE_FILE = ".project/delivery/prepare.yml"
STATE_FILE = ".project/state.yml"
PR_BODY_FILE = ".project/delivery/pr.md"
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]+['\"]"),
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
]


def run(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=root, text=True, capture_output=True, check=False)


def validate_branch_name(branch: str) -> bool:
    pattern = (
        r"^(feat|fix|perf|refactor|test|docs|build|ci|chore|spike)"
        r"/[0-9]{3,6}-[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    return bool(re.match(pattern, branch))


def build_branch_name(change_type: str, item_id: str, slug: str) -> str:
    if change_type not in BRANCH_TYPES:
        raise ValueError(f"invalid branch type: {change_type}")
    if not re.match(r"^[0-9]{3,6}$", item_id):
        raise ValueError(f"invalid spec/issue number: {item_id}")
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
        raise ValueError(f"invalid slug: {slug}")
    return f"{change_type}/{item_id}-{slug}"


def validate_pr_title(title: str) -> bool:
    return validate_conventional_title(title)


# =============================================================================
# THE ISSUE GATE -- one question, two callers, and its known weaknesses.
#
# `command_publish` and `command_validate_ci` both refuse work that is not tied
# to an existing, OPEN GitHub issue (spec 002, FR-002/FR-003/FR-004). Both call
# `issue_is_open` below instead of each growing its own answer to "does this
# issue satisfy the contract" -- two implementations of the same question is
# the defect spec 015 measured in the other repository.
#
# THE KNOWN WAYS PAST THIS GUARD, WRITTEN ON PURPOSE.
#
# A guard whose weakness is written down is a guard. A guard whose weakness is
# left unsaid is theatre. So:
#
#   1. `command_publish` only runs when someone actually runs
#      `scripts/delivery.py publish`. A push done by hand (`git push` followed
#      by `gh pr create` outside this script) never calls it at all.
#   2. The CI side (`validate-ci --pr-body`) only runs `if: github.event_name
#      == 'pull_request'` (see `.github/workflows/quality.yml`), so a direct
#      push to a branch that never goes through a pull request never reaches
#      it either. The ruleset in `.github/rulesets/main.yml` that would force
#      every change through a pull request says of itself that it is a
#      "declarative proposal only", not applied remotely.
#   3. `issue_from_pr_body` only reads the closing keywords GitHub itself
#      recognizes (`Closes #N`, `Fixes #N`, `Resolves #N`, and their tenses).
#      It confirms an open issue number is PRESENT in the body, never that it
#      is the RIGHT issue for the change in the diff -- a PR body pointing at
#      an unrelated, still-open issue passes exactly the same as a correct one.
#   4. `issue_is_open` tells "issue does not exist" apart from "gh could not
#      answer" by matching known substrings in `gh`'s stderr (see
#      `ISSUE_NOT_FOUND_MARKERS`). If GitHub ever changes that wording, a real
#      outage could be misread as "issue not found" (still a refusal, safe by
#      NFR-003, but the wrong message) or a nonexistent issue could be misread
#      as an outage (also still a refusal, never a silent pass).
#   5. `command_publish`'s own "cartao declarado" check only reads the `issue`
#      field out of `.project/state.yml`. That file is not signed by anyone;
#      hand-editing it to the number of an unrelated, still-open issue passes
#      this gate the same as a genuine one, for the same reason as point 3.
#   6. Both callers depend on `gh` itself being authenticated and able to see
#      the issue (`GH_TOKEN` locally, `secrets.GITHUB_TOKEN` plus `issues:
#      read` permission in CI). A token that can reach GitHub but lacks
#      permission on this repository's issues can produce the same
#      not-found-shaped answer as an issue that truly does not exist.
# =============================================================================


class IssueLookupError(RuntimeError):
    """`gh` could not answer whether an issue exists and is open.

    Covers `gh` missing from PATH, no network reaching GitHub, and no
    authentication configured. NFR-003 treats all three the same way: an
    environment that cannot measure refuses, it never passes silently.
    """


ISSUE_NOT_FOUND_MARKERS = (
    "could not resolve to an issue",
    "no default remote repository",
)

CLOSING_KEYWORD_PATTERN = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s*#(\d+)\b"
)


def issue_from_pr_body(body: str) -> int | None:
    """The issue number a pull request body closes, via GitHub's own closing keywords.

    This reads the exact mechanism GitHub itself uses to link a pull request to an
    issue (`Closes #N`, `Fixes #N`, `Resolves #N`, and their tenses), off the PR body
    the CI event already carries. The `issue` field in `.project/state.yml` is
    deliberately not consulted here: CI runs on a checkout, not on the author's
    machine, and that field records the contributor's own bookkeeping for whatever
    fatia they currently have active -- not a GitHub-verified closing relationship
    for the exact pull request under review. The two can point at different issues
    without anything local catching it (see weakness 5 above).
    """
    match = CLOSING_KEYWORD_PATTERN.search(body or "")
    return int(match.group(1)) if match else None


def issue_is_open(root: Path, number: int) -> bool:
    """True only when issue `number` exists on GitHub AND is currently open.

    A closed issue and a nonexistent issue are answered the same way here -- False
    -- because FR-004 treats both as not satisfying the contract; a caller that
    wants a different message for the two asks `gh` again on its own reporting path.

    Raises `IssueLookupError` when `gh` itself could not answer -- see the module
    note above for exactly which cases and their known blind spots.
    """
    try:
        completed = run(root, ["gh", "issue", "view", str(number), "--json", "state"])
    except OSError as failure:  # gh missing from PATH
        raise IssueLookupError(f"gh nao pode ser executado: {failure}") from None
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        if any(marker in stderr.lower() for marker in ISSUE_NOT_FOUND_MARKERS):
            return False
        raise IssueLookupError(
            f"gh issue view {number} saiu com {completed.returncode}, portanto a "
            f"existencia da issue nao foi medida: {stderr or 'sem stderr'}"
        )
    data: dict[str, Any] = json.loads(completed.stdout)
    return data.get("state") == "OPEN"


def resolve_base(root: Path, remote: str, base: str) -> str:
    """THE one place `--base` is turned into a ref, for every command that reads it.

    T219 / FR-005. Measured on 2026-09-21, in this repository, on a branch whose work was already
    integrated:

        git rev-list --count HEAD ^refs/heads/main            -> 8
        git rev-list --count HEAD ^refs/remotes/origin/main   -> 0

    Same flag, same default value, two answers. `start` resolved `refs/remotes/<remote>/<base>`
    and refused correctly; `publish` and `status` resolved `refs/heads/<base>` and would have
    reported eight commits as unpublished that the base on the server already had. It is the same
    defect as #36 seen from the other side: a command reasoning about a reference that is not the
    one the server will use.

    WHICH ONE WINS, and why. The remote ref, when it exists. Integration happens on the server, so
    the base that matters is the server's -- `refs/heads/<base>` is whatever this checkout last
    did locally, which after a squash merge is routinely behind and, in a worktree that never
    checks `main` out, may not exist at all.

    THE FALLBACK IS DECLARED, not silent: with no remote-tracking ref, the local branch is used,
    because a repository that has never fetched has nothing better and refusing every command
    there would be worse than answering from what is present. `start` is the exception and refuses
    instead, because creating a branch from an unmeasured base is the defect #36 recorded.
    """
    remote_ref = f"refs/remotes/{remote}/{base}"
    if git_ref_exists(root, remote_ref):
        return remote_ref
    return base


def local_commits(root: Path, base: str = "main") -> list[str]:
    """Commits on HEAD that `base` does not have yet.

    `git log {base}..HEAD` fails with "unknown revision" (exit 128) when `base` itself
    has not been born -- a fresh repository, or a base branch this checkout never
    fetched. That is the same legitimate "not yet" `git_head`/`git_parent` already grant
    an unborn ref, so it is answered the same way, with `git_ref_exists` rather than by
    reading absence into whatever git happened to print. Once `base` resolves, `git log`
    answering with an empty, exit-0 result IS "no commits ahead" -- that case needs no
    special handling, `git_capture` already returns "" for it. Any other failure is real
    and is left to raise `GitUnavailableError`.
    """
    if not git_ref_exists(root, base):
        return []
    output = git_capture(root, "log", "--oneline", f"{base}..HEAD")
    return [line for line in output.splitlines() if line.strip()]


def staged_files(root: Path) -> list[str]:
    """Paths staged for commit. "Nothing staged" is exit 0 with empty stdout, not a
    failure -- `git diff --cached --name-only` answers that way whether or not the
    repository has any commits yet. No fallback is needed here: `git_capture` already
    returns "" for that legitimate case and raises `GitUnavailableError` for a real one
    (not a repository, index.lock held).
    """
    output = git_capture(root, "diff", "--cached", "--name-only")
    return [line for line in output.splitlines() if line.strip()]


def changed_files(root: Path) -> list[str]:
    """Paths changed in the working tree or the index, combined. Same reasoning as
    `staged_files`: "nothing changed" is a legitimate exit-0 empty answer, not a
    fallback value, and a real git failure still raises `GitUnavailableError` unmodified.
    """
    output = git_capture(root, "diff", "--name-only")
    files = [line for line in output.splitlines() if line.strip()]
    files.extend(staged_files(root))
    return sorted(set(files))


def branch_is_main(branch: str) -> bool:
    return branch in MAIN_BRANCHES


def validate_publish_plan(branch: str, *, force: bool = False) -> list[str]:
    errors: list[str] = []
    if branch_is_main(branch):
        errors.append("refusing to push main")
    if force:
        errors.append("force push is forbidden")
    if not validate_branch_name(branch):
        errors.append(f"invalid branch name: {branch}")
    return errors


def ci_checks_passed(checks: dict[str, str]) -> bool:
    required = {"delivery-policy", "quality"}
    return required <= checks.keys() and all(checks[name] == "success" for name in required)


def scan_for_secrets(root: Path, files: list[str]) -> list[str]:
    findings: list[str] = []
    for rel_path in files:
        path = root / rel_path
        if not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(rel_path)
                break
    return findings


def ownership_allows(root: Path, files: list[str]) -> bool:
    state = load_yaml(root / ".project/state.yml")
    workstream_id = state.get("active_workstream")
    if not workstream_id:
        return True
    matches = sorted((root / ".project/workstreams").glob(f"{workstream_id}-*.yml"))
    workstream_path = (
        matches[0] if matches else root / ".project/workstreams" / f"{workstream_id}.yml"
    )
    if not workstream_path.exists():
        return True
    workstream = load_yaml(workstream_path)
    owned = workstream.get("owned_paths", [])
    if "." in owned:
        return True
    return all(any(path == item or path.startswith(f"{item}/") for item in owned) for path in files)


def prepare_invalidated_by_own_checkpoint(
    root: Path, recorded_head: str, current_head: str
) -> bool:
    """True when every commit between `recorded_head` and `current_head` only touched
    the bookkeeping paths `prepare` itself produces -- `.project/checkpoints/` (via the
    `scripts/checkpoint.py` call `command_prepare` makes) and `.project/state.yml`.

    This is issue #13's exact shape: `prepare` records `head`, then generates a
    checkpoint; if that checkpoint is later committed on its own, HEAD moves for a
    reason entirely internal to the pipeline, not because anyone changed the slice's
    actual content. FR-002 requires that self-invalidation be signaled explicitly
    where it happens rather than surfacing later as an unexplained rejection -- see
    `prepare_is_fresh` below, which calls this to choose its message.

    A commit that ALSO touches any other path is deliberately NOT covered here: mixed
    content means the staleness has a real cause beyond prepare's own artifact, and the
    generic message is the honest one for that case.
    """
    try:
        if not git_ref_exists(root, recorded_head):
            return False
        changed = git_capture(root, "diff", "--name-only", recorded_head, current_head)
    except GitUnavailableError:
        return False
    paths = [line for line in changed.splitlines() if line.strip()]
    if not paths:
        return False
    return all(path.startswith(".project/checkpoints/") or path == STATE_FILE for path in paths)


def prepare_is_fresh(root: Path) -> tuple[bool, str]:
    path = root / PREPARE_FILE
    if not path.exists():
        return False, "prepare file is missing"
    data = load_yaml(path)
    # A prepare file can outlive the repository it described -- a clone gone,
    # a .git removed. Git failing here is not a stale prepare and not a fresh
    # one: it is an answer we do not have, so say that instead of raising a
    # traceback at whichever command asked.
    try:
        head = git_head(root)
        branch = git_branch(root)
    except GitUnavailableError as failure:
        return False, f"prepare could not be checked: git did not answer: {failure}"
    if data.get("head") != head:
        recorded_head = str(data.get("head") or "")
        # T304/FR-002: name the self-invalidation explicitly, with the corrective
        # action, instead of leaving this as the same generic message a genuine
        # content change would also produce.
        if recorded_head and prepare_invalidated_by_own_checkpoint(root, recorded_head, head):
            return False, (
                f"prepare is obsolete: its own checkpoint step moved HEAD "
                f"({recorded_head} -> {head}) by committing only bookkeeping paths "
                "(.project/checkpoints/, .project/state.yml). Corrective action: "
                "run `scripts/delivery.py prepare` again -- the slice's content was "
                "not what changed, only the recorded HEAD is stale."
            )
        return False, "prepare is obsolete: HEAD changed"
    if data.get("branch") != branch:
        return False, "prepare is obsolete: branch changed"
    if data.get("status") != "approved":
        return False, "prepare is not approved"
    return True, "prepare is fresh"


def delivery_state(
    root: Path,
    title: str,
    body: str,
    files: list[str],
    review: str = "approved_with_notes",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "status": "approved",
        "created_at": utc_now(),
        "branch": git_branch(root),
        "head": git_head(root),
        "title": title,
        "body_file": PR_BODY_FILE,
        "review": review,
        "convergence": "checked",
        "files": files,
        "body": body,
    }


def pr_body(title: str, files: list[str], issue: int | None = None) -> str:
    """Build the pull request body, including the closing keyword when a card exists.

    The closing line has to originate here. `publish` rewrites the body from this
    file on every run, so a `Closes #N` added by hand afterwards is erased on the
    next publish and the CI gate then refuses the pull request -- measured on run
    35533507737, where exactly that happened.
    """
    closes = f"\n\nCloses #{issue}" if issue is not None else ""
    file_lines = "\n".join(f"- `{path}`" for path in files) or "- No changed files detected."
    return f"""## Summary

{title}{closes}

## Problem and motivation

Prepared by `scripts/delivery.py prepare` from repository state.

## Specification and requirements

See active `.project/state.yml`, specs, ADRs and PRD references.

## Changes

{file_lines}

## Validation evidence

- `uv run python scripts/resume.py`
- `uv run python scripts/doctor.py`
- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run pyright`
- `uv run pytest`
- `uv run python scripts/verify.py`

## Benchmarks when applicable

N/A - not applicable unless performance requirements changed.

## Risks and limitations

Remote operations are not executed by prepare.

## Reviewer checklist

- [ ] Requirements trace to tasks and evidence.
- [ ] Tests and validations listed were actually executed.
- [ ] No secrets, personal data or invented evidence.
- [ ] State and checkpoint are updated when applicable.
"""


def base_ref_name(remote: str, base: str) -> str:
    """`refs/remotes/<remote>/<base>`, spelled in full on purpose.

    `origin/main` is a DWIM name, and `refs/tags/` wins over `refs/remotes/` when both exist. A
    review of this slice built that case: with a tag literally named `origin/main`, `rev-parse
    origin/main` resolved to the tag, the containment count came back 0, and `start` accepted the
    very state it exists to refuse -- silently, because git's ambiguity warning goes to stderr and
    a successful `git_capture` discards it. Exotic, and free to close.
    """
    return f"refs/remotes/{remote}/{base}"


def unmerged_base_refusal(root: Path, remote: str, base: str) -> str | None:
    """Why this HEAD must not become the parent of a new slice, or None when it may.

    THE DEFECT THIS EXISTS FOR (issue #36, measured 2026-09-21). `start` created the branch from
    whatever HEAD happened to be checked out and asked nothing about it. After a squash merge the
    operator's HEAD holds the pre-squash commits, and `main` holds one new commit carrying the
    same content under a different identity. A branch started there therefore replays history the
    base already has:

        git rev-list --left-right --count origin/main...HEAD   ->   1  7
        gh pr view 35 --json mergeable                          ->   CONFLICTING
        git diff --name-only origin/main HEAD                   ->   only the new slice's files

    The content did not collide. Two histories carrying the same content did. The cost was a full
    turn of the cycle -- branch, battery, commit, publish, pull request, CI run and attestation --
    all discarded and redone from the base, because the alternative was a force push, which
    `ENGINEERING.md` rules out.

    WHAT IS MEASURED: whether the base contains HEAD, as `git rev-list --count HEAD ^<base>` == 0.
    Containment, not currency: a HEAD strictly behind the base passes, because branching from an
    older ancestor produces no conflict, only a rebase someone may want later.

    WHY THE MEASUREMENT IS TAKEN AGAINST THE LOCAL REMOTE REF, WITHOUT FETCHING. `start` is a
    local command, and a command that quietly reaches the network is a command whose failures
    surprise. A stale base ref then errs toward refusing rather than accepting -- the older the
    ref, the fewer commits it contains -- WHICH HOLDS ONLY WHILE THE BASE ADVANCES BY
    FAST-FORWARD. A review of this slice produced the counter-example: rewrite the base
    non-fast-forward upstream, and the stale ref accepts a HEAD the fresh ref refuses. On `main`
    the server forbids force pushes (coverage matrix line 12), so the property holds there; a
    `--base` without that protection does not inherit it. The refusal says to fetch, and the
    operator decides.

    WHEN THE MEASUREMENT CANNOT BE TAKEN. No such local ref, or no commit at HEAD yet: refused,
    each with its own message, because "I could not ask" is not "the answer is yes" (NFR-002).

    KNOWN BYPASS VECTORS, per FR-009. Stated as measured, not as hoped:

    - `--allow-unmerged-head`, for the legitimate case this would otherwise block: stacking a
      slice on one not yet integrated. Explicit, named in the operator's own command line, and it
      announces itself. It leaves no machine-readable trace, so an audit cannot later tell that a
      branch was born under it -- recorded as debt, task T220.
    - `git switch -c`, `git checkout -b` and `git branch` run directly, bypassing `start`
      entirely. NOT mitigated, for an automated agent or for a human: the harness `PreToolUse`
      control (FR-011) matches `commit|push|merge|rebase|reset`, and `branch` is on its read-only
      list. Measured against `.claude/hooks/enforce_delivery_pipeline.py` during this slice's
      review: `git switch -c feat/001-x`, `git checkout -b feat/001-x` and `git branch feat/001-x`
      are all allowed. Closing it means widening that hook, which is task T221 rather than this
      slice, because widening it without `--from-base` below would leave an operator no way to
      reach the base at all.
    """
    if not remote or not base:
        return (
            f"ERROR: remote e base nao podem ser vazios (remote={remote!r}, base={base!r}), "
            "portanto nao ha ref contra o qual medir. Nenhuma branch foi criada."
        )
    ref = base_ref_name(remote, base)
    if not git_ref_exists(root, ref):
        return (
            f"ERROR: {ref} nao existe neste repositorio local, portanto nao se sabe se o HEAD "
            f"actual ja foi integrado. Execute `git fetch {remote}` e repita. Nenhuma branch foi "
            "criada."
        )
    if not git_ref_exists(root, "HEAD"):
        return (
            "ERROR: este repositorio ainda nao tem commit algum, portanto nao ha HEAD a medir "
            "contra a base. Nenhuma branch foi criada."
        )
    unmerged = git_capture(root, "rev-list", "--count", "HEAD", f"^{ref}")
    if unmerged == "0":
        return None
    return (
        f"ERROR: o HEAD actual tem {unmerged} commit(s) que {remote}/{base} nao contem, portanto "
        f"uma branch criada aqui replica historico que a base ja integrou -- tipicamente sob "
        f"outra identidade, apos um squash merge, o que a pull request so revela como conflito. "
        f"Nenhuma branch foi criada.\n"
        f"Repita com --from-base para partir de {remote}/{base} mantendo as alteracoes por "
        f"commitar, ou com --allow-unmerged-head se esta deliberadamente a empilhar esta fatia "
        f"sobre outra ainda por integrar."
    )


ORIGIN_FILE = ".project/delivery/branch-origin.yml"


def record_branch_origin(
    root: Path, branch: str, base_ref: str, started_from: str, override: str | None
) -> None:
    """Write how this branch came to exist, so a later reader does not have to take it on trust.

    T220 / FR-009 / FR-012. `--allow-unmerged-head` printed a warning and nothing else. The
    warning lived in the terminal of whoever ran the command; nothing reached
    `.project/delivery/`, so an audit -- or the next stage of this same pipeline -- could not tell
    that a branch had been created under an exception.

    Everything else in this pipeline leaves a record that an instrument can read: `prepare` writes
    its receipt, `checkpoint` writes its own, the state carries the verdict cache, CI writes the
    run receipt. This was the one step whose exception existed only as words on a screen.

    WHY THE COMMIT AND NOT ONLY THE NAME. The first version stored `base_ref: "HEAD"`
    whenever the branch was not started with `--from-base` -- which is exactly the path
    `--allow-unmerged-head` enables, and therefore the only path where this record has audit
    value. By the time anyone reads the file, `HEAD` names the new branch, so the record said
    an exception had happened and could not say what it started from. Review measured that;
    `started_from` carries the resolved commit, read before the switch.

    WRITTEN: by `start`, once, immediately after the branch exists.
    INVALIDATED: by the next `start`, which overwrites it. The file describes the branch currently
    being worked on and makes no claim about any earlier one -- `.project/delivery/` is git-ignored
    scratch, so this is a record for the operator and the pipeline, not a history.
    """
    write_yaml_atomic(
        root / ORIGIN_FILE,
        {
            "branch": branch,
            "base_ref": base_ref,
            "started_from": started_from,
            "override": override,
            "created_at": utc_now(),
        },
    )


def command_start(args: argparse.Namespace) -> int:
    branch = build_branch_name(args.type, args.number, args.slug)
    if git_status(args.root) and not args.allow_dirty:
        print("ERROR: working tree is dirty. Use --allow-dirty only after preserving work.")
        return 1
    if not validate_branch_name(branch):
        print(f"ERROR: invalid branch name: {branch}")
        return 1
    if args.allow_unmerged_head:
        print(
            "NOTE: --allow-unmerged-head. The base-containment check is being overridden, so "
            "this branch may replay history the base already integrated. Deliberate stacking is "
            "the one case that warrants it; anything else produces a conflicting pull request "
            "(issue #36)."
        )
    elif not args.from_base:
        try:
            refusal = unmerged_base_refusal(args.root, args.remote, args.base)
        except GitUnavailableError as failure:
            print(f"ERROR: git nao respondeu, portanto a base nao foi medida: {failure}")
            return 1
        if refusal is not None:
            print(refusal)
            return 1
    # `--from-base` makes the refusal actionable WITHOUT leaving the pipeline. Without it the
    # only way out of a HEAD the base has absorbed is a raw `git switch -c <branch> origin/main`,
    # so the gate would be telling the operator to bypass the very pipeline it belongs to -- and
    # closing the harness hook over `switch` (task T221) would then leave no way out at all.
    # Uncommitted work travels across the switch, which is the ordinary shape of a slice being
    # started: the content is in the working tree, not in the commits being left behind.
    # Resolved before the switch: afterwards `HEAD` names the branch being created, so a
    # record taken then cannot say where it came from (review finding on this slice).
    try:
        started_from = git_head(args.root)
    except GitUnavailableError:
        started_from = "unmeasured"
    switch = ["git", "switch", "-c", branch]
    if args.from_base:
        switch.append(base_ref_name(args.remote, args.base))
    completed = run(args.root, switch)
    if completed.returncode != 0:
        print(completed.stderr.strip())
        return completed.returncode
    override = "allow-unmerged-head" if args.allow_unmerged_head else None
    record_branch_origin(
        args.root,
        branch,
        base_ref_name(args.remote, args.base) if args.from_base else "HEAD",
        started_from,
        override,
    )
    print(branch)
    return 0


def command_prepare(args: argparse.Namespace) -> int:
    """Run the gates once and record the approval that `commit`/`publish` consume.

    WRITTEN: `.project/delivery/prepare.yml` and `.project/delivery/pr.md`
    (git-ignored scratch, both rewritten every call) once all gates below pass; then
    `scripts/checkpoint.py` is invoked, which writes its own checkpoint file plus
    `.project/state.yml` fields (see `commands.command_checkpoint`'s own declaration).
    INVALIDATED: by any later change to HEAD or the current branch (`prepare_is_fresh`
    compares both against what was recorded here). T304/FR-002: the checkpoint this
    very function triggers, above, is itself a common cause of that HEAD change once
    it is committed -- `prepare_is_fresh` names that specific case explicitly instead
    of leaving it to read as a generic, unexplained rejection.
    """
    branch = git_branch(args.root)
    if branch_is_main(branch):
        print("ERROR: prepare requires a branch different from main.")
        return 1
    title = args.title or f"{branch.split('/', 1)[0]}: {branch.split('-', 1)[-1].replace('-', ' ')}"
    if not validate_pr_title(title):
        print(f"ERROR: invalid Conventional Commit title: {title}")
        return 1
    commands = [
        ["uv", "run", "python", "scripts/resume.py"],
        ["uv", "run", "python", "scripts/doctor.py"],
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "pyright"],
        ["uv", "run", "pytest"],
        ["uv", "run", "python", "scripts/verify.py"],
    ]
    for command in commands:
        completed = run(args.root, command)
        print("$ " + " ".join(command))
        if completed.stdout:
            print(completed.stdout.strip())
        if completed.returncode != 0:
            print(completed.stderr.strip())
            return completed.returncode
    result = verify_root(args.root)
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}")
        return 1
    try:
        files = changed_files(args.root)
    except GitUnavailableError as failure:
        print(
            f"ERROR: git nao respondeu, portanto os arquivos alterados nao foram medidos: {failure}"
        )
        return 1
    declared_issue = load_yaml(args.root / ".project/state.yml").get("issue")
    body = pr_body(title, files, declared_issue if isinstance(declared_issue, int) else None)
    write_yaml_atomic(args.root / PREPARE_FILE, delivery_state(args.root, title, body, files))
    (args.root / PR_BODY_FILE).write_text(body, encoding="utf-8", newline="\n")
    run(args.root, ["uv", "run", "python", "scripts/checkpoint.py"])
    print("Prepared delivery. Files:")
    for path in files:
        print(f"- {path}")
    print(f"Title: {title}")
    print(f"PR body: {PR_BODY_FILE}")
    return 0


def command_commit(args: argparse.Namespace) -> int:
    """Create the content commit for the current slice, then record it as verified.

    WRITTEN: `.project/delivery/commit-message.txt` (git-ignored scratch, rewritten
    every call) before `git commit` runs; `.project/state.yml` at most once per call,
    folded into a SECOND, separate commit right after the content commit (T303,
    FR-001) -- `record_verified_commit` cannot be written before `git commit` because
    the commit id it records does not exist yet, and leaving it uncommitted after was
    issue #12: every slice ended with a dirty `state.yml` the operator had to
    recognize and discard by hand. `core.accepted_verified_trees` already accepts
    HEAD's tree OR the tree of any parent of HEAD (issue #10/#30, a PR merge ref), so
    this bookkeeping commit becoming the new HEAD does not invalidate the verdict
    recorded on its own parent.
    INVALIDATED: the whole call refuses up front when `prepare_is_fresh` says the
    approval on file no longer matches this HEAD/branch (see that function, and T304
    below, for when the mismatch is prepare's own doing).
    """
    fresh, reason = prepare_is_fresh(args.root)
    if not fresh:
        print(f"ERROR: {reason}")
        return 1
    try:
        files = staged_files(args.root)
    except GitUnavailableError as failure:
        print(f"ERROR: git nao respondeu, portanto os arquivos staged nao foram medidos: {failure}")
        return 1
    if not files:
        print("ERROR: no staged files.")
        return 1
    if scan_for_secrets(args.root, files):
        print("ERROR: staged files contain possible secrets.")
        return 1
    if not ownership_allows(args.root, files):
        print("ERROR: staged files are outside active ownership.")
        return 1
    prepare = load_yaml(args.root / PREPARE_FILE)
    title = args.message or prepare["title"]
    if not validate_conventional_title(title):
        print(f"ERROR: invalid Conventional Commit title: {title}")
        return 1
    prepare = load_yaml(args.root / PREPARE_FILE)
    message_file = args.root / ".project/delivery/commit-message.txt"
    message_file.parent.mkdir(parents=True, exist_ok=True)
    message_file.write_text(f"{title}\n\n{prepare['body']}", encoding="utf-8", newline="\n")
    completed = run(args.root, ["git", "commit", "-F", str(message_file)])
    if completed.returncode != 0:
        print(completed.stderr.strip())
        return completed.returncode
    committed = git_head(args.root)
    prepare["head"] = committed
    write_yaml_atomic(args.root / PREPARE_FILE, prepare)
    wrote_state = record_verified_commit(args.root, committed, git_tree(args.root, "HEAD"))
    print(completed.stdout.strip())
    if wrote_state:
        # T303/FR-001: fold the bookkeeping write into a second, minimal commit right
        # here instead of leaving `.project/state.yml` modified-but-uncommitted --
        # see this function's own docstring above for why the write cannot happen
        # before `git commit` instead.
        add_state = run(args.root, ["git", "add", "--", STATE_FILE])
        if add_state.returncode != 0:
            print(add_state.stderr.strip())
            return add_state.returncode
        bookkeeping = run(
            args.root,
            ["git", "commit", "-m", f"chore(state): record verified commit {committed[:12]}"],
        )
        if bookkeeping.returncode != 0:
            print(bookkeeping.stderr.strip())
            return bookkeeping.returncode
        print(bookkeeping.stdout.strip())
        # The bookkeeping commit moves HEAD, which is exactly the condition
        # `prepare_invalidated_by_own_checkpoint` reports -- measured on the first
        # real use of this path, where `publish` then refused a prepare that had
        # just been used successfully. The prepare follows HEAD here, so a step
        # that only recorded what the previous step measured does not force the
        # operator to repeat the one before it.
        prepare["head"] = git_head(args.root)
        write_yaml_atomic(args.root / PREPARE_FILE, prepare)
    return 0


def record_verified_commit(root: Path, commit: str, tree: str | None = None) -> bool:
    """Move the verified state to the commit (and tree) whose content was measured.

    `prepare` runs the gates against the working tree and `commit` turns that
    exact tree into a commit, so that commit is what was verified. Leaving the
    field behind makes the next `verify` fail for bookkeeping reasons, and the
    only way out was editing the state by hand -- which is how a state file
    starts claiming what nobody measured.

    `last_verified_commit` stays for humans reading `.project/state.yml`; the
    gate in `core.verify_root` reads `last_verified_tree` instead (issue #30),
    because only the tree survives a squash unchanged. `tree` is optional so
    callers that only ever had a commit id (nothing left calls this without
    one) still work; when it is omitted, `last_verified_tree` is simply not
    touched here.

    WRITTEN: from `command_commit`, immediately after `git commit` creates the
    content commit -- once per commit, only when the recorded fields actually
    change (an unchanged call below is a no-op, on purpose: a write nobody
    needed is exactly what dirties a tree that closed clean). Also called from
    `command_merge` after a squash merge is confirmed on the server.
    INVALIDATED: by the next commit that changes `state.status` away from
    {verified, converged, done}, or by a later call recording a different
    commit/tree -- never by this function itself.

    Returns True exactly when `.project/state.yml` was written, so the caller
    (T303, FR-001) knows whether a follow-up bookkeeping commit is needed to
    keep the working tree clean, and False when there was nothing to record.
    """
    state_path = root / STATE_FILE
    if not state_path.is_file():
        return False
    state = load_yaml(state_path)
    if state.get("status") not in {"verified", "converged", "done"}:
        return False
    if state.get("last_verified_commit") == commit and (
        tree is None or state.get("last_verified_tree") == tree
    ):
        return False
    state["last_verified_commit"] = commit
    if tree is not None:
        state["last_verified_tree"] = tree
    state["updated_at"] = utc_now()
    write_yaml_atomic(state_path, state)
    return True


def remote_url(root: Path, remote: str) -> str | None:
    """URL configured for `remote`, or None when it is simply not configured.

    `git remote get-url <name>` exits 2 with "No such remote" for a repository that
    never had that remote added -- a legitimate state (nothing has been pushed from
    here yet), not a git failure, so it is read directly instead of going through
    `git_capture` (which would raise on that exit code). Any other non-zero exit (not a
    repository, corrupt config) is a real failure and raises `GitUnavailableError`.
    """
    completed = run(root, ["git", "remote", "get-url", remote])
    if completed.returncode == 2:
        return None
    if completed.returncode != 0:
        raise GitUnavailableError(
            f"git remote get-url {remote} saiu com {completed.returncode}: "
            f"{completed.stderr.strip() or 'sem stderr'}"
        )
    return completed.stdout.strip()


def require_remote_authorization(args: argparse.Namespace) -> bool:
    if not getattr(args, "yes_remote", False):
        print("ERROR: remote operation requires --yes-remote.")
        return False
    return True


def command_publish(args: argparse.Namespace) -> int:
    if not require_remote_authorization(args):
        return 1
    state_for_issue = load_yaml(args.root / STATE_FILE)
    declared_issue = state_for_issue.get("issue")
    if not declared_issue:
        print(
            "ERROR: no issue declared. Add `issue: <number>` to "
            f"{STATE_FILE}, pointing at the GitHub issue this fatia closes, then retry."
        )
        return 1
    try:
        issue_open = issue_is_open(args.root, declared_issue)
    except IssueLookupError as failure:
        print(f"ERROR: could not verify issue #{declared_issue}, refusing to publish: {failure}")
        return 1
    if not issue_open:
        print(
            f"ERROR: issue #{declared_issue} does not exist or is not open. "
            "Declare an existing, open issue before publishing."
        )
        return 1
    branch = git_branch(args.root)
    publish_errors = validate_publish_plan(branch)
    if publish_errors:
        for error in publish_errors:
            print(f"ERROR: {error}.")
        return 1
    fresh, reason = prepare_is_fresh(args.root)
    if not fresh:
        print(f"ERROR: {reason}")
        return 1
    try:
        commits_to_publish = local_commits(
            args.root, resolve_base(args.root, args.remote, args.base)
        )
    except GitUnavailableError as failure:
        print(f"ERROR: git nao respondeu, portanto os commits locais nao foram medidos: {failure}")
        return 1
    if not commits_to_publish:
        print("ERROR: no local commit to publish.")
        return 1
    remote = args.remote or "origin"
    try:
        resolved_remote_url = remote_url(args.root, remote)
    except GitUnavailableError as failure:
        print(f"ERROR: git nao respondeu, portanto o remote nao foi verificado: {failure}")
        return 1
    if not resolved_remote_url:
        print(f"ERROR: remote not found: {remote}")
        return 1
    run(args.root, ["uv", "run", "python", "scripts/checkpoint.py"])
    push = run(args.root, ["git", "push", "-u", remote, branch])
    if push.returncode != 0:
        print(push.stderr.strip())
        return push.returncode
    prepare = load_yaml(args.root / PREPARE_FILE)
    view = run(args.root, ["gh", "pr", "view", branch, "--json", "number,url"])
    if view.returncode == 0:
        gh_args = [
            "gh",
            "pr",
            "edit",
            branch,
            "--title",
            prepare["title"],
            "--body-file",
            PR_BODY_FILE,
        ]
    else:
        gh_args = [
            "gh",
            "pr",
            "create",
            "--base",
            args.base,
            "--head",
            branch,
            "--title",
            prepare["title"],
            "--body-file",
            PR_BODY_FILE,
        ]
    pr = run(args.root, gh_args)
    if pr.returncode != 0:
        print(pr.stderr.strip())
        return pr.returncode
    output = pr.stdout.strip()
    print(output)
    pr_view = run(args.root, ["gh", "pr", "view", branch, "--json", "number,url"])
    pr_data: dict[str, Any] = (
        json.loads(pr_view.stdout) if pr_view.returncode == 0 and pr_view.stdout else {}
    )
    state_path = args.root / ".project/state.yml"
    state = load_yaml(state_path)
    state["delivery"] = {
        "branch": branch,
        "base": args.base,
        "remote": remote,
        "pr_number": pr_data.get("number"),
        "pr_url": pr_data.get("url", output),
        "updated_at": utc_now(),
    }
    write_yaml_atomic(state_path, state)
    return 0


def command_merge(args: argparse.Namespace) -> int:
    if not args.auto:
        print("ERROR: merge requires --auto.")
        return 1
    if not require_remote_authorization(args):
        return 1
    workflow = args.root / SIGNER_WORKFLOW_PATH
    if not workflow.exists():
        print("ERROR: CI workflow is missing.")
        return 1
    branch = git_branch(args.root)
    if branch_is_main(branch):
        print("ERROR: merge requires a pull request branch.")
        return 1
    pr = run(args.root, ["gh", "pr", "view", branch, "--json", "title,number,headRefOid"])
    if pr.returncode != 0:
        print("ERROR: PR is missing.")
        return 1
    pr_data: dict[str, Any] = json.loads(pr.stdout)
    title = pr_data["title"]
    verdict = signed_verdict_refusal(args.root, pr_data.get("headRefOid"))
    if verdict is not None:
        print(verdict)
        return 1
    # `--delete-branch` is deliberately not passed to `gh pr merge` here: it makes `gh`
    # check out the base branch locally to remove the merged branch, and that checkout
    # is what failed with "Your local changes ... would be overwritten by checkout" on
    # two real pull requests -- the tree was already dirty from `publish` writing
    # `.project/state.yml` before `merge` ever ran, nothing this command did itself.
    # Deleting the branch on the remote afterwards (below, once the merge is confirmed)
    # needs no local checkout at all, so it cannot be broken by that same dirty tree.
    merge = run(
        args.root,
        ["gh", "pr", "merge", branch, "--auto", "--squash", "--subject", title],
    )
    if merge.returncode == 0:
        print(merge.stdout.strip())
    else:
        # A non-zero exit here is not proof the merge failed: `gh pr merge` can still
        # exit non-zero after the server has already merged, e.g. because a follow-up
        # step choked. `record_merge_commit` asks the pull request itself before this
        # is reported as a failure.
        print(merge.stderr.strip())
    run(args.root, ["uv", "run", "python", "scripts/checkpoint.py"])
    return record_merge_commit(
        args.root, branch, merge_returncode=merge.returncode, merge_stderr=merge.stderr.strip()
    )


def signed_verdict_refusal(root: Path, head_oid: str | None = None) -> str | None:
    """The reason this content must not be integrated, or None when a signed verdict covers it.

    THE GATE THAT REPLACED THE STATE FIELD (issue #24, spec 003 FR-006, T208/T209). Until this
    existed, the only thing standing between unmeasured content and `main` was a field the same
    process wrote on its way past -- `last_verified_commit`, then `last_verified_tree`, each
    defeated by the same self-reference: the record changes the content it is a record of. This
    asks GitHub instead, about a signature produced by an identity no step here can reach.

    WHEN IT REFUSES, AND WHY EACH CASE IS A REFUSAL RATHER THAN A PASS:

    - `gh` could not answer at all: refused. NFR-002 -- a control that cannot take its
      measurement fails; an unreachable network is not a conformance verdict.
    - no attestation covers this tree: refused. The ordinary cause is a run still in flight,
      because `publish` pushes the branch and the verdict is minted at the end of that run. The
      answer is to wait for it, not to merge ahead of it, which is why this refuses instead of
      queueing an auto-merge against content no run has signed.

    WHEN IT DOES NOT APPLY, and why each exemption is measured rather than assumed. A gate nobody
    can pass is a gate that gets deleted, and deleting it removes the control for everyone, so
    each case below is checked against the thing that actually decides it:

    - a derived project with `ci: none`, or no workflow at all: read off the tree by
      `verdict_is_expected`. No workflow means no workflow identity means nothing to sign with.
    - a PRIVATE repository: asked of GitHub, not inferred. Attestations need a public repository
      or a plan that includes them, so `.github/workflows/quality.yml` mints nothing for a private
      one. This predicate and that `if:` condition are the two halves of one limit; they were
      written apart once, and a private derived project would have inherited a merge that could
      never succeed. FR-020 requires the limit be declared rather than the fix asserted
      universally -- these projects keep the commit/ancestry mechanism in `core.verify_root`.

    The exemption is announced, never silent: a reader has to be able to tell "this content has no
    verdict" from "nothing here can have one".

    THE CONTENT MEASURED IS THE CONTENT THE SERVER WILL INTEGRATE. `head_oid` is the pull
    request's head as GitHub reports it, not the local HEAD: those are the same commit in the
    ordinary flow and are not the same commit whenever the local checkout is behind the branch on
    the server. Gating on the local tree would then verify content the server is not about to
    merge, which is a pass that proves nothing. When the server's head is not present in the local
    object store, this refuses and says to fetch, rather than fetching behind the operator's back
    or falling back to a tree it can reach.

    DECLARED LIMIT, not closed here: `gh pr merge --auto` may integrate later, when the checks go
    green, against whatever the head is at that moment. A head that moved after this measurement
    is content this gate did not see. The server's required checks still run against that new
    head; the signed verdict is not re-read. Closing it needs the verification to be a required
    check on the server rather than a step in this command -- recorded as open in
    `specs/003-no-stage-without-a-mechanism/spec.md`, matrix line 15.
    """
    if not verdict_is_expected(root):
        return None
    ref = head_oid or "HEAD"
    if head_oid is not None:
        # `rev-parse --verify` accepts any well-formed 40-hex string, present or not, so asking
        # it whether the server's head exists here answers about spelling rather than about the
        # object store. `cat-file -t` reads the object itself.
        try:
            head_type = git_capture(root, "cat-file", "-t", head_oid)
        except GitUnavailableError:
            head_type = ""
        if head_type != "commit":
            return (
                f"ERROR: o head da pull request ({head_oid}) nao existe neste repositorio local, "
                "portanto o conteudo que o servidor vai integrar nao foi medido. Execute "
                "`git fetch origin` e repita; nada foi integrado."
            )
    try:
        tree = git_tree(root, ref)
    except GitUnavailableError as failure:
        return f"ERROR: git nao respondeu, portanto a tree a integrar nao foi medida: {failure}"
    if tree == "unborn":
        return (
            f"ERROR: {ref} nao resolve para nenhum commit, portanto nao ha conteudo a medir. "
            "Nada foi integrado."
        )
    try:
        slug, is_public = repository_identity(root)
    except GhUnavailableError as failure:
        return (
            "ERROR: gh nao respondeu, portanto nao se sabe sequer se este repositorio pode ter "
            f"veredicto assinado, e indisponibilidade nao equivale a conformidade (NFR-002): "
            f"{failure}"
        )
    if not is_public:
        print(
            f"NOTE: {slug} is private, so no signed verdict can exist for it -- attestations "
            "need a public repository or a plan that includes them. The signed-verdict gate "
            "does not apply here (declared limit, spec 003 FR-020); this repository keeps the "
            "commit/ancestry mechanism as its only check."
        )
        return None
    try:
        covered, detail = attestation_covers_tree(root, tree, slug)
    except GhUnavailableError as failure:
        return (
            "ERROR: gh nao respondeu, portanto o veredicto assinado nao foi medido, e "
            f"indisponibilidade nao equivale a conformidade (NFR-002): {failure}"
        )
    if covered:
        return None
    return (
        f"ERROR: {detail}\n"
        "Nothing was merged. The verdict is minted by the quality run for this branch, at the "
        "end of it; re-run `merge --auto --yes-remote` once that run has finished, or run "
        "`uv run python scripts/attest.py verify` to see the same answer directly."
    )


def record_merge_commit(
    root: Path, branch: str, *, merge_returncode: int = 0, merge_stderr: str = ""
) -> int:
    """Resolve the squash commit GitHub created for `branch` and record it as verified.

    `gh pr merge --auto` merges immediately when checks already passed, but only queues
    auto-merge -- and returns before any squash commit exists -- when checks are still
    running. The branch tip that `record_verified_commit` used to be given here is the
    commit the squash on main erases from history, so `verify`/`resume` on main then see a
    `last_verified_commit` that `git merge-base --is-ancestor` answers NAO to. Only a commit
    this function actually measured on the remote is written; a merge still in flight is
    reported, not guessed at or waited for.

    `merge_returncode` is the exit code `gh pr merge` itself returned, kept separate from
    what actually happened on the server: it was measured non-zero (PR #17) even though the
    squash merge had already succeeded, because a local-only cleanup step failed afterwards.
    The pull request's own state -- not that exit code -- decides success here; a non-zero
    `merge_returncode` only changes what a NOT-merged answer means: still queued (when `gh`
    itself reported success) versus a real failure (when `gh` itself reported none).

    THE TREE RECORDED HERE (issue #30): this function does not fetch and inspect the squash
    commit's tree object -- `--delete-branch` is already avoided above specifically to keep
    this command from checking anything out, and nothing here calls `git checkout` either.
    Instead it records `git_tree(root, "HEAD")`, the tree of the branch tip still checked
    out locally at this point. That is deliberate, not an approximation: this repository's
    ruleset requires `strict_required_status_checks_policy: true`, so a branch must already
    be up to date with `main` before GitHub allows the merge, and squashing an up-to-date
    branch onto its base produces a commit whose tree is identical to the branch tip's own
    tree. DECLARED LIMIT: if that ruleset setting is ever relaxed, this equality is no longer
    guaranteed and this function would need to resolve `merge_commit`'s tree directly instead
    (after `git fetch origin`, once the object is locally available).
    """
    merge_failed = merge_returncode != 0
    view = run(root, ["gh", "pr", "view", branch, "--json", "state,mergeCommit"])
    if view.returncode != 0:
        print(f"ERROR: could not query the merge result for {branch}: {view.stderr.strip()}")
        return merge_returncode if merge_failed else 1
    data: dict[str, Any] = json.loads(view.stdout)
    merge_commit_field: dict[str, Any] = data.get("mergeCommit") or {}
    merge_commit: str | None = merge_commit_field.get("oid")
    if data.get("state") != "MERGED" or not merge_commit:
        if merge_failed:
            print(
                f"ERROR: gh pr merge failed for {branch} and the pull request is not "
                f"merged: {merge_stderr}"
            )
            return merge_returncode
        print(
            f"Merge for {branch} is queued for auto-merge; the checks have not "
            "finished and no squash commit exists yet. Nothing was recorded. Re-run "
            "`merge --auto --yes-remote` once the pull request has actually merged."
        )
        return 2
    if merge_failed:
        print(
            f"NOTE: gh pr merge exited {merge_returncode} for {branch}, but the pull "
            f"request is MERGED on the server ({merge_commit}). Treating this as success; "
            f"only local cleanup failed: {merge_stderr}"
        )
    fetch = run(root, ["git", "fetch", "origin"])
    if fetch.returncode != 0:
        print(
            f"ERROR: git fetch failed, the squash commit was not confirmed locally: "
            f"{fetch.stderr.strip()}"
        )
        return 1
    try:
        squash_tree = git_tree(root, "HEAD")
    except GitUnavailableError as failure:
        print(f"ERROR: git nao respondeu, portanto a tree do squash nao foi medida: {failure}")
        return 1
    record_verified_commit(root, merge_commit, squash_tree)
    print(f"Recorded squash merge commit as verified: {merge_commit} (tree {squash_tree})")
    delete = run(root, ["git", "push", "origin", "--delete", branch])
    if delete.returncode != 0:
        print(
            f"WARNING: could not delete remote branch {branch} (the server merge already "
            f"succeeded): {delete.stderr.strip()}"
        )
    return 0


def command_status(args: argparse.Namespace) -> int:
    # status reports the reason either way, so the freshness flag itself is
    # not read here -- only the sentence that explains it.
    _, reason = prepare_is_fresh(args.root)
    # status is a diagnostic: it reports what it could not measure and keeps
    # going, rather than dying on the first question git cannot answer.
    try:
        print(f"branch: {git_branch(args.root)}")
        print(f"head: {git_head(args.root)}")
        print(f"dirty_paths: {len(git_status(args.root))}")
    except GitUnavailableError as failure:
        print(f"branch: unmeasured (git did not answer: {failure})")
    print(f"prepare: {reason}")
    if (args.root / ORIGIN_FILE).exists():
        origin = load_yaml(args.root / ORIGIN_FILE)
        override = origin.get("override")
        print(f"branch_from: {origin.get('base_ref', 'unknown')}")
        print(f"branch_started_from: {origin.get('started_from', 'unknown')}")
        # Printed whichever way it went. An exception that only shows up when it was used reads,
        # to anyone scanning output, exactly like a line somebody forgot to look for.
        print(f"branch_override: {override or 'none'}")
    if (args.root / PREPARE_FILE).exists():
        prepare = load_yaml(args.root / PREPARE_FILE)
        print(f"reviewer: {prepare.get('review', 'unknown')}")
        print(f"convergence: {prepare.get('convergence', 'unknown')}")
    else:
        print("reviewer: not prepared")
        print("convergence: not prepared")
    state = load_yaml(args.root / ".project/state.yml")
    delivery = state.get("delivery", {})
    print(f"pr: {delivery.get('pr_url', 'not recorded')}")
    print("ci: not queried")
    try:
        commit_count = len(
            local_commits(args.root, resolve_base(args.root, args.remote, args.base))
        )
    except GitUnavailableError as failure:
        print(f"local_commits: unmeasured (git nao respondeu: {failure})")
    else:
        print(f"local_commits: {commit_count}")
    print("remote: not queried")
    print("next: run prepare, commit, publish or merge according to the current gate")
    return 0


#: Path prefixes whose contents are code in the sense FR-014 means: things that change what the
#: software does, what the pipeline enforces, or what a derived project receives. Plain filenames
#: are prefixes too, which is why `pyproject.toml` and `uv.lock` appear here directly.
#:
#: Some of these are configuration by file extension and enforcement by effect, and that is the
#: test applied. `pyproject.toml` carries `typeCheckingMode = "strict"`, the ruff selection and
#: pytest's `--strict-markers`: a one-line edit there weakens three of the five checks in the
#: quality job. `.claude/settings.json` is what switches the `PreToolUse` hook on, so the hook
#: being gated while its switch was not made the mechanism removable without a specification.
#: `profiles/`, `templates/` and the bootstrap file are copied verbatim into every derived
#: project by `installer.py`, so they are that product's behaviour.
#:
#: DELIBERATELY OUT, so the omission is a decision and not an oversight: the canonical instruction
#: files (`ENGINEERING.md`, `AGENTS.md`, `REVIEW.md`, `docs/agents/`) change how agents are asked
#: to behave and are not executable, and the specification's own plan/2 of the matrix treats
#: process documentation as not constituting a control (spec 003, "Principio ordenador"). Also
#: out: `docs/`, `.project/` bookkeeping, and the specifications themselves, which are the thing
#: a change is supposed to be associated WITH.
CODE_PREFIXES = (
    "src/",
    "scripts/",
    "tests/",
    "extensions/",
    "profiles/",
    "templates/",
    ".claude/hooks/",
    ".claude/settings.json",
    ".github/workflows/",
    ".github/rulesets/",
    "pyproject.toml",
    "uv.lock",
    "bootstrap-engineering-template.yml",
)

STATE_RELATIVE = STATE_FILE.replace("\\", "/")


#: A specification directory as an issue names it: `specs/003-no-stage-without-a-mechanism`.
SPEC_REFERENCE = re.compile(r"\bspecs/(\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*)")


def issue_payload(root: Path, number: int) -> dict[str, Any]:
    """The issue as GitHub reports it, or a refusal to guess.

    Raises `IssueLookupError` for the same reasons `issue_is_open` does: `gh` missing, no network,
    no authentication. NFR-002 -- a chain that could not be read is not a chain that is intact.
    """
    completed = run(root, ["gh", "api", f"repos/:owner/:repo/issues/{number}"])
    if completed.returncode != 0:
        raise IssueLookupError(
            f"gh api could not read issue #{number}: {completed.stderr.strip() or 'no stderr'}"
        )
    try:
        payload: dict[str, Any] = json.loads(completed.stdout)
    except json.JSONDecodeError as failure:
        raise IssueLookupError(f"gh returned something that is not an issue: {failure}") from None
    return payload


def specification_named_by(body: str, root: Path) -> tuple[str | None, str | None]:
    """The specification an issue names, and why it does not count when it does not.

    Returns `(directory, problem)`. A body naming `specs/005-agent-throughput` when no such
    directory exists resolves to nothing: measured on 2026-09-21, issue #28 names exactly that,
    and the specification has not been written. A link to a document nobody wrote is the shape of
    traceability without the substance.
    """
    match = SPEC_REFERENCE.search(body or "")
    if match is None:
        return None, None
    directory = f"specs/{match.group(1)}"
    if not (root / directory).is_dir():
        return None, f"names {directory}, which does not exist in this repository"
    return directory, None


def traceability_refusal(root: Path, issue_number: int) -> str | None:
    """Why this pull request is not connected to anything above it, or None when it is.

    FR-013 / FR-015 / AC-009, coverage matrix stage 6. The chain the requirement asks for is
    pull request -> sub-issue -> parent issue -> `specs/NNN/`, each link verified and the missing
    one named. Until now only the first link existed: `issue_from_pr_body` plus `issue_is_open`
    proved a card exists and is open, and nothing asked what the card belongs to.

    HOW THE PARENT IS FOUND, measured rather than inferred. `GET /repos/:owner/:repo/issues/<n>`
    carries `parent_issue_url` directly on a sub-issue's payload -- verified on 2026-09-21 against
    issue #42, which returned the URL of #26. No walk over candidate parents is needed, and
    `issues: read` already covers that endpoint.

    THE TWO SHAPES THIS ACCEPTS, both measured in this repository's own board:

    * a sub-issue whose parent names a specification that exists. Issue #26 names
      `specs/003-no-stage-without-a-mechanism`, and every slice of that epic hangs from it.
    * a standalone issue that names a specification itself.

    AND THE ONE IT EXCUSES. A defect fix belongs to no epic and needs no specification: issues
    #15, #36, #45 and #46 are all of that kind, and a rule refusing them would be a rule that gets
    removed. Such a slice declares `no_spec_reason` in the state, the same sentence T213 already
    asks for, rather than being silently exempt.

    KNOWN BYPASS VECTORS, per FR-009:

    * the link from an issue to a specification is a string in prose. Nothing stops an issue from
      naming a specification it has nothing to do with; what is removed is naming none at all, or
      naming one that does not exist.
    * the parent relationship lives on GitHub, not in the tree, so it can be changed after the
      fact without any commit. The check is a snapshot taken when the pull request runs.
    """
    try:
        issue = issue_payload(root, issue_number)
    except IssueLookupError as failure:
        return (
            f"ERROR: the chain above this pull request was not read, and a chain that could not "
            f"be read is not a chain that is intact (NFR-002): {failure}"
        )

    parent_url = str(issue.get("parent_issue_url") or "")
    if parent_url:
        parent_number = parent_url.rsplit("/", 1)[-1]
        try:
            parent = issue_payload(root, int(parent_number))
        except (IssueLookupError, ValueError) as failure:
            return (
                f"ERROR: issue #{issue_number} declares parent #{parent_number} and it was not "
                f"read, so the chain is unverified (NFR-002): {failure}"
            )
        directory, problem = specification_named_by(str(parent.get("body") or ""), root)
        if directory is not None:
            return None
        detail = problem or "names no specification at all"
        return (
            f"ERROR: the chain breaks at the parent. Pull request -> issue #{issue_number} -> "
            f"parent issue #{parent_number}, which {detail}. FR-015: an issue mae sem "
            "especificacao correspondente constitui falha de gate. Name the `specs/NNN-slug/` "
            "this epic decomposes, in the parent issue's body."
        )

    directory, problem = specification_named_by(str(issue.get("body") or ""), root)
    if directory is not None:
        return None

    state_path = root / STATE_FILE
    state: dict[str, Any] = load_yaml(state_path) if state_path.is_file() else {}
    if str(state.get("no_spec_reason") or "").strip():
        return None

    detail = problem or "has no parent issue and names no specification"
    return (
        f"ERROR: the chain breaks at the card. Issue #{issue_number} {detail}, so this pull "
        "request connects to nothing above it. Either make it a sub-issue of the epic whose "
        "specification it belongs to, or name the `specs/NNN-slug/` in its body, or declare "
        f"`no_spec_reason` in {STATE_RELATIVE} -- a defect fix that belongs to no specification "
        "is legitimate and says so."
    )


def spec_precedence_refusal(
    root: Path, changed_paths: list[str], declared_total: int | None = None
) -> str | None:
    """Why this pull request must not land, or None when a specification claims its code.

    FR-014 / AC-010, coverage matrix stage 4. A change to code that no specification claims is a
    change nobody wrote down a reason for, and this repository's whole premise is that the reason
    comes first.

    WHY ASSOCIATION IS MEASURED IN THE DIFF AND NOT IN THE STATE FILE. The obvious rule -- "code
    changed, so `active_specification` must exist" -- was measured over the eight first-parent
    commits ending at `48639d30` and would have passed all eight while measuring nothing: every
    one declared `specs/001-engineering-playbook/spec.md`, including the commits that closed specs
    002, 003 and 004. The field sat stale across eight slices because nothing read it. So the
    association asked for here is one the diff can show.

    WHY THE COUNT IS CROSS-CHECKED. `gh pr view --json files` returns at most 100 paths and says
    nothing about having cut: measured against a real pull request of 167 files, it returned 100,
    unsorted. A gate that silently measures a window would report PASS for a slice it never looked
    at. `declared_total` is what the API says the true number is; a disagreement is a measurement
    that did not happen, and NFR-002 makes that a refusal rather than a guess.

    THE DECLARED ESCAPE, and why it is bounded. A defect fix may legitimately have no
    specification of its own; issues #15 and #36 were exactly that, and a rule without an escape
    would have refused both, which is how a gate gets removed instead of satisfied. So a slice may
    write `no_spec_reason` into `.project/state.yml`. Two things keep that from becoming a silent
    default: the reason has to be long enough to act on, and the state file has to be IN THIS
    DIFF. Without the second, the sentence is read once by the reviewer of the pull request that
    introduced it and then exempts every later slice forever, invisibly -- which review measured
    as the escape's real shape before this was added.

    The escape stays available even when `active_specification` is declared and valid, because
    that is the measured case: while #15 and #36 were delivered the state still named spec 003,
    left there by the previous slice. "No specification of its own" is about the change, not about
    whether some specification happens to be named.

    KNOWN BYPASS VECTORS, per FR-009:

    * touching the specification directory is not describing the change. A scratch file under
      `specs/NNN/` satisfies this gate. Diff-level association cannot tell the two apart; what it
      removes is changing code while the specification says nothing at all.
    * `no_spec_reason` can be a plausible sentence rather than a considered one. No textual rule
      separates those; what is removed is doing it silently.
    * `CODE_PREFIXES` is this repository's map of where code lives. A repository that grows code
      somewhere else passes this gate while changing code, which is why the list sits next to the
      function and why the exclusions above are written down rather than implied.
    """
    if declared_total is not None and declared_total != len(changed_paths):
        return (
            f"ERROR: the pull request reports {declared_total} changed files and only "
            f"{len(changed_paths)} paths were handed to this check, so the specification that "
            "claims this code was measured over a window rather than over the change. "
            "`gh pr view --json files` caps at 100; paginate "
            "`gh api --paginate repos/<owner>/<repo>/pulls/<n>/files`. Refusing rather than "
            "reporting on what was not read (NFR-002)."
        )

    code_paths = sorted(path for path in changed_paths if path.startswith(CODE_PREFIXES))
    if not code_paths:
        return None

    state_path = root / STATE_FILE
    state: dict[str, Any] = load_yaml(state_path) if state_path.is_file() else {}
    declared = str(state.get("active_specification") or "").replace("\\", "/")
    # `specs/<slice>/<file>`, three components at least. Two collapse the prefix to `specs/`,
    # and then touching ANY specification satisfies the gate -- the eight-merge defect wearing a
    # different hat, which review built as `active_specification: specs/003-no-stage...` with no
    # filename and watched pass.
    parts = [part for part in declared.split("/") if part not in {"", "."}]
    spec_dir = "/".join(parts[:-1]) + "/" if len(parts) >= 3 and parts[0] == "specs" else ""
    if spec_dir and any(path.startswith(spec_dir) for path in changed_paths):
        return None

    reason = str(state.get("no_spec_reason") or "").strip()
    if reason:
        if len(reason.split()) < 5:
            return (
                f"ERROR: no_spec_reason is {reason!r}, which is too short to be a reason anyone "
                "can act on. Write the sentence a reviewer would need, or associate the change "
                "with a specification."
            )
        if STATE_RELATIVE not in changed_paths:
            return (
                f"ERROR: no_spec_reason is declared but {STATE_RELATIVE} is not in this pull "
                "request, so the sentence was written by an earlier slice and is exempting this "
                "one invisibly. The escape is per slice: write the reason for THIS change, in "
                "this diff, where a reviewer reads it."
            )
        print(
            f"NOTE: no specification claims this code; the state declares why: {reason!r}. "
            "Declared escape, FR-014 -- a reviewer reads this sentence in this diff."
        )
        return None

    changed = ", ".join(code_paths[:5]) + (" ..." if len(code_paths) > 5 else "")
    if not declared:
        return (
            f"ERROR: this pull request changes code ({changed}) and {STATE_RELATIVE} declares no "
            "active_specification. FR-014: code that no specification claims does not reach "
            "main. Declare the specification, or declare `no_spec_reason` in this same diff."
        )
    if not spec_dir:
        return (
            f"ERROR: this pull request changes code ({changed}) and {STATE_RELATIVE} declares "
            f"active_specification as {declared!r}, which does not name a file under "
            "`specs/<slice>/`. A value with no filename collapses the comparison to `specs/`, "
            "and then touching any specification at all would satisfy this gate."
        )
    return (
        f"ERROR: this pull request changes code ({changed}) without touching {spec_dir}, the "
        "directory of the active specification it declares. FR-014 asks for association, and "
        "eight consecutive merges showed that a state field alone does not provide it -- the "
        "field sat on specs/001 while specs 002 to 004 were being closed. Update the "
        "specification, its plan or its tasks with what this change does, or declare "
        f"`no_spec_reason` in {STATE_RELATIVE}, in this diff, saying why this slice has none."
    )


def command_validate_ci(args: argparse.Namespace) -> int:
    failed = False
    if args.branch and args.branch not in MAIN_BRANCHES and not validate_branch_name(args.branch):
        print(f"ERROR: invalid branch name: {args.branch}")
        failed = True
    if args.pr_title and not validate_pr_title(args.pr_title):
        print(f"ERROR: invalid PR title: {args.pr_title}")
        failed = True
    if getattr(args, "pr_body", None) is not None:
        issue_number = issue_from_pr_body(args.pr_body)
        if issue_number is None:
            print(
                "ERROR: pull request body does not close an issue. Add "
                "'Closes #<number>' (or Fixes/Resolves) naming an existing, "
                "open issue to the pull request body."
            )
            failed = True
        else:
            try:
                open_issue = issue_is_open(args.root, issue_number)
            except IssueLookupError as failure:
                print(f"ERROR: could not verify issue #{issue_number}, refusing: {failure}")
                failed = True
            else:
                if not open_issue:
                    print(
                        f"ERROR: issue #{issue_number} does not exist or is not open. "
                        "Link the pull request to an existing, open issue."
                    )
                    failed = True
                else:
                    broken = traceability_refusal(args.root, issue_number)
                    if broken is not None:
                        print(broken)
                        failed = True
    if getattr(args, "pr_files", None) is not None:
        changed = [line.strip() for line in args.pr_files.splitlines() if line.strip()]
        if not changed:
            # An empty file list is a measurement that did not happen, not a pull request that
            # changes nothing: `gh pr view --json files` always reports at least one path for a
            # real pull request. NFR-002 -- refuse rather than pass.
            print(
                "ERROR: no changed paths were provided, so the specification that claims this "
                "code was not measured. Refusing rather than assuming."
            )
            failed = True
        else:
            refusal = spec_precedence_refusal(
                args.root, changed, getattr(args, "pr_file_count", None)
            )
            if refusal is not None:
                print(refusal)
                failed = True
    return 1 if failed else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safe Git delivery pipeline.")
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--type", required=True)
    start.add_argument("--number", required=True)
    start.add_argument("--slug", required=True)
    start.add_argument("--allow-dirty", action="store_true")
    start.add_argument("--remote", default="origin")
    start.add_argument("--base", default="main")
    start.add_argument(
        "--allow-unmerged-head",
        action="store_true",
        help="start from a HEAD the base does not contain, for deliberately stacked slices",
    )
    start.add_argument(
        "--from-base",
        action="store_true",
        help="branch from <remote>/<base> instead of HEAD, carrying uncommitted work across",
    )

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--title")

    commit = subparsers.add_parser("commit")
    commit.add_argument("--message")

    publish = subparsers.add_parser("publish")
    publish.add_argument("--yes-remote", action="store_true")
    publish.add_argument("--remote", default="origin")
    publish.add_argument("--base", default="main")

    merge = subparsers.add_parser("merge")
    merge.add_argument("--auto", action="store_true")
    merge.add_argument("--yes-remote", action="store_true")

    status = subparsers.add_parser("status")
    status.add_argument("--base", default="main")
    # `status` accepted `--base` and not `--remote`, so it could be told which branch to
    # compare against and not which remote the branch belongs to (T219).
    status.add_argument("--remote", default="origin")

    validate_ci = subparsers.add_parser("validate-ci")
    validate_ci.add_argument("--branch")
    validate_ci.add_argument("--pr-title")
    validate_ci.add_argument("--pr-body")
    validate_ci.add_argument(
        "--pr-files",
        help="newline-separated paths the pull request changes, from `gh api --paginate`",
    )
    validate_ci.add_argument(
        "--pr-file-count",
        type=int,
        help="how many files the pull request reports changing, to catch a truncated list",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    commands = {
        "start": command_start,
        "prepare": command_prepare,
        "commit": command_commit,
        "publish": command_publish,
        "merge": command_merge,
        "status": command_status,
        "validate-ci": command_validate_ci,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
