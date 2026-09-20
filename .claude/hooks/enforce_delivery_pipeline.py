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
READ_ONLY = re.compile(
    r"\bgit\s+(?:-C\s+\S+\s+)?(?:status|log|diff|show|branch|rev-parse|"
    r"merge-base|rev-list|for-each-ref|ls-tree|ls-files|cat-file|describe|"
    r"remote|config|stash\s+list|worktree\s+list|cherry|blame|fetch)\b"
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
    r"\bgit\s+(?:-C\s+\S+\s+)?(commit|push|merge|rebase|reset)\b",
)
GH_MERGE = re.compile(r"\bgh\s+pr\s+merge\b")


def decide(command: str) -> tuple[str, str] | None:
    """Return the refusal reason for `command`, or None to stay out of the way.

    The whole command string is examined, including compound forms, because a
    write verb reached through `&&`, a pipe or a substitution is still a write.
    """
    if GH_MERGE.search(command):
        return (
            "gh pr merge bypasses the delivery pipeline",
            "Run `uv run python scripts/delivery.py merge --auto --yes-remote`. It "
            "reads the merge result back from the pull request, records the squash "
            "commit as verified, and deletes the remote branch.",
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
    if READ_ONLY.search(command) and WRITE_VERB.search(command) is None:
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
