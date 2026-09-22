"""The harness control is exercised as a process, not reimplemented here.

A test that asserts the guard exists proves nothing; these tests feed the script
the event payload the harness feeds it and read the decision it writes back.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / ".claude/hooks/enforce_delivery_pipeline.py"
SETTINGS = ROOT / ".claude/settings.json"

NO_DECISION = "no-decision"


def decide(command: str) -> dict[str, Any]:
    """Run the hook the way the harness runs it and return its decision."""
    event = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    completed = subprocess.run(
        [sys.executable, str(HOOK)],
        input=event,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    if not completed.stdout.strip():
        return {}
    return cast("dict[str, Any]", json.loads(completed.stdout))


def field(command: str, name: str) -> str:
    """Read one field of the decision envelope, or report that none was made."""
    payload = decide(command)
    if not payload:
        return NO_DECISION
    output = cast("dict[str, Any]", payload["hookSpecificOutput"])
    return str(output[name])


def permission(command: str) -> str:
    return field(command, "permissionDecision")


def test_the_hook_file_exists() -> None:
    """Every other test in this file is vacuous if the script is gone."""
    assert HOOK.is_file(), f"{HOOK} is missing"


def test_a_direct_commit_is_refused() -> None:
    assert permission('git commit -m "direct"') == "deny"


def test_a_direct_push_is_refused() -> None:
    assert permission("git push origin feat/001-example") == "deny"


def test_a_pull_request_merge_through_gh_is_refused() -> None:
    assert permission("gh pr merge 23 --squash") == "deny"


def test_a_write_verb_reached_through_a_compound_command_is_refused() -> None:
    """`&&` does not launder a write: the whole command string is examined."""
    assert permission("uv run pytest -q && git push origin main") == "deny"


def test_a_global_option_before_the_verb_does_not_launder_a_write() -> None:
    """#61. The branch guard was widened for exactly this and `WRITE_VERB` was left as it was, so
    the older half of the same file still let `git -c a=b commit` through. Git accepts any number of
    `-c k=v` before the verb, and it changes nothing about what the verb then does.
    """
    for command in (
        "git -c user.email=x@example.com commit -m direct",
        "git -c a=b -c c=d push origin main",
        "git --no-pager merge origin/main",
        'git "commit" -m direct',
        # The first version of this test named the family and listed only the four options the
        # pattern already admitted. Review ran the rest against real git: each of these produced
        # a commit, a push or a reset with the guard saying nothing.
        "git -p commit -m x",
        "git --paginate push origin main",
        "git --work-tree=. commit -m x",
        "git --exec-path=/x reset --hard HEAD~1",
        "git --git-dir=/x commit -m x",
        "git --literal-pathspecs rebase origin/main",
        # A redirection before the verb. `&` was read as a command separator by every rule in the
        # hook, so `2>&1` truncated the scan and hid whatever followed. This gate -- T205, the
        # first one this file ever had -- was open from the day it was written until the sixth
        # round of review on issue #61 found it.
        "git 2>&1 commit -m x",
        "git 1>&2 push origin main",
        "git &>log commit -m x",
        "git 2>/dev/null reset --hard HEAD~1",
    ):
        assert permission(command) == "deny", f"the hook allowed {command!r}"


def test_a_global_option_before_a_read_verb_is_still_left_alone() -> None:
    """The other side of the same widening: `-c` is how anyone forces colour off in a script."""
    for command in (
        "git -c color.ui=false status",
        "git --no-pager log --oneline -5",
        "git -p log",
        "git --git-dir=/x status",
        "git status 2>&1",
        "git log --oneline -5 > out.txt",
    ):
        assert permission(command) != "deny", f"the hook refused {command!r}, which only reads"


def test_a_write_verb_inside_a_substitution_is_refused() -> None:
    assert permission('echo "$(git commit -m x)"') == "deny"


def test_reading_the_repository_is_left_alone() -> None:
    for command in (
        "git status --porcelain",
        "git log --oneline -5",
        "git diff --stat",
        "git rev-parse HEAD",
        "git -C ../other status",
    ):
        assert permission(command) == NO_DECISION, command


def test_a_command_unrelated_to_git_is_left_alone() -> None:
    assert permission("uv run pytest -q") == NO_DECISION


def test_the_refusal_names_the_pipeline_command_to_use_instead() -> None:
    """A refusal without a remedy makes the caller retry the same invocation."""
    reason = field("git commit -m x", "permissionDecisionReason")
    assert "scripts/delivery.py commit" in reason, reason


def test_the_known_bypass_vectors_are_written_in_the_guard() -> None:
    """FR-009: the weakness of a guard belongs in the guard, not in folklore."""
    text = HOOK.read_text(encoding="utf-8")
    for vector in ("bash -c", "/usr/bin/git", "alias", "settings.local.json"):
        assert vector in text, f"{vector} is not declared as a known bypass vector"


def test_the_versioned_settings_declare_both_layers() -> None:
    """The deny rules and the hook are complementary, so both must be present.

    Deny rules take precedence and need no runtime; the hook carries the reason
    that tells the caller which pipeline command replaces the refused one.
    """
    settings = cast("dict[str, Any]", json.loads(SETTINGS.read_text(encoding="utf-8")))
    permissions = cast("dict[str, Any]", settings["permissions"])
    deny = [str(rule) for rule in cast("list[Any]", permissions["deny"])]
    for rule in ("Bash(git commit:*)", "Bash(git push:*)", "Bash(gh pr merge:*)"):
        assert rule in deny, f"{rule} is not denied"
    hooks = cast("dict[str, Any]", settings["hooks"])
    assert "PreToolUse" in hooks
