"""`pre-push`'s ruleset-reconciliation step, invoked as a real process.

`test_git_hooks.py` covers `pre-commit`; this file is the same discipline for the piece
`pre-push` gained on top of `local_ci.py`: a check that `.github/rulesets/main.yml` still
matches what GitHub has applied on the server, run through `scripts/verify_ruleset.py`.

`uv run python <script>` is stubbed with a fake `uv` placed first on `PATH`, so these tests
never touch a real `gh` process or the network: they drive the exact two outputs
`command_verify_ruleset` can produce (`GhUnavailableError`'s "gh nao respondeu, portanto ..."
line, or `print_result`'s "ERROR: ..." lines) and assert the hook's decision on each,
without depending on this machine's own `gh` state. `scripts/local_ci.py` is stubbed to
exit 0 unconditionally, because it is not what these tests are about.

NFR-002 (spec 003) governs the "could not measure" case: a control unable to obtain its
measurement returns failure, not a pass, so the default here is REFUSAL, with a single
named escape valve (`PLAYBOOK_ALLOW_UNMEASURED_RULESET=1`) that must print, every time it
is used, that the push went out unmeasured. "Measured and diverges" has no escape valve at
all, ever.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
from pathlib import Path

# Windows resolves a bare "bash" through `CreateProcess`'s own search order, which checks
# `System32` (home to a WSL launcher stub named `bash.exe`) before it ever looks at `PATH` --
# measured directly: `subprocess.run(["bash", "-c", "uname -a"])` printed a WSL2 kernel
# banner even with a git-bash-first `PATH`, and that WSL process does not inherit the `PATH`
# override these tests rely on to swap in a fake `uv`. `shutil.which` walks `PATH` itself and
# does not hit that stub, so resolving `bash` once, up front, and always invoking it by this
# absolute path avoids the collision. On a Linux CI runner this is just `/usr/bin/bash`.
_BASH = shutil.which("bash") or "bash"

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "git-hooks" / "pre-push"
RESOURCE_HOOK = (
    ROOT / "src" / "engineering_playbook" / "resources" / "scripts" / "git-hooks" / "pre-push"
)

_FAKE_UV = """#!/usr/bin/env bash
# Fake `uv` for tests: dispatches "uv run python <script>" on the script's name and lets
# the two scripts pre-push cares about be driven entirely by environment variables, rather
# than by a real local_ci run or a real `gh` process.
if [ "$1" = "run" ] && [ "$2" = "python" ]; then
    case "$3" in
        *local_ci.py)
            exit "${FAKE_LOCAL_CI_EXIT:-0}"
            ;;
        *verify_ruleset.py)
            if [ -n "${FAKE_RULESET_OUTPUT:-}" ]; then
                printf '%s\\n' "$FAKE_RULESET_OUTPUT"
            fi
            exit "${FAKE_RULESET_EXIT:-0}"
            ;;
    esac
fi
exit 0
"""


def _git(repository: Path, *arguments: str) -> None:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, (
        f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
    )


def _make_repository(tmp_path: Path, *, with_ruleset_script: bool) -> Path:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "--initial-branch=feat/example")

    bin_dir = repository / "fake-bin"
    bin_dir.mkdir()
    fake_uv = bin_dir / "uv"
    fake_uv.write_text(_FAKE_UV, encoding="utf-8", newline="\n")
    fake_uv.chmod(fake_uv.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    if with_ruleset_script:
        scripts_dir = repository / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "verify_ruleset.py").write_text("", encoding="utf-8")

    (repository / "pre-push").write_bytes(HOOK.read_bytes())
    return repository


def _run_hook(
    repository: Path, *, env_overrides: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    fake_bin = str(repository / "fake-bin")
    env["PATH"] = fake_bin + os.pathsep + env.get("PATH", "")
    env.update(env_overrides or {})
    return subprocess.run(
        (_BASH, "pre-push"),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_the_hook_names_the_two_verdicts_and_its_one_escape_valve() -> None:
    """A control that folds its escape valve into a silent pass is what NFR-002 forbids."""
    text = HOOK.read_text(encoding="utf-8")
    assert "gh nao respondeu" in text, (
        "the hook does not name the exact GhUnavailableError text it distinguishes on"
    )
    assert "NAO CONSEGUI MEDIR" in text
    assert "DIVERGE" in text
    assert "PLAYBOOK_ALLOW_UNMEASURED_RULESET" in text, (
        "the escape valve's name is not written down in the hook itself"
    )
    assert "NFR-002" in text


def test_the_distributed_copy_matches_the_source_of_truth() -> None:
    assert RESOURCE_HOOK.is_file(), f"{RESOURCE_HOOK} is missing"
    assert RESOURCE_HOOK.read_bytes() == HOOK.read_bytes(), (
        "src/engineering_playbook/resources/scripts/git-hooks/pre-push has drifted from "
        "scripts/git-hooks/pre-push; derived projects install from the resources copy"
    )


def test_the_hook_skips_the_ruleset_check_when_the_script_is_absent(tmp_path: Path) -> None:
    """A derived project without this control must not have its push break because of it."""
    repository = _make_repository(tmp_path, with_ruleset_script=False)

    result = _run_hook(repository)

    assert result.returncode == 0, (
        f"the hook failed to push with no ruleset script present. "
        f"stdout: {result.stdout!r} stderr: {result.stderr!r}"
    )
    assert "ruleset" not in result.stderr.lower()


def test_the_hook_refuses_a_push_when_the_ruleset_was_measured_and_diverges(
    tmp_path: Path,
) -> None:
    """The bite: `gh` answered, the comparison ran, and the file disagrees with the server."""
    repository = _make_repository(tmp_path, with_ruleset_script=True)

    result = _run_hook(
        repository,
        env_overrides={
            "FAKE_RULESET_EXIT": "1",
            "FAKE_RULESET_OUTPUT": (
                "ERROR: Ruleset enforcement diverges: file='active' applied='disabled'"
            ),
        },
    )

    assert result.returncode == 1, (
        f"the hook let a measured divergence through. stderr: {result.stderr!r}"
    )
    assert "PUSH RECUSADO" in result.stderr
    assert "DIVERGE" in result.stderr
    assert "NAO CONSEGUI MEDIR" not in result.stderr, (
        "a measured divergence must not be reported as an unmeasurable state"
    )


_GH_UNAVAILABLE_OUTPUT = (
    "ERROR: gh nao respondeu, portanto o ruleset aplicado nao foi medido: "
    "gh api repos/:owner/:repo/rulesets saiu com 1: not authenticated"
)


def test_the_hook_refuses_a_push_when_gh_could_not_answer_and_the_valve_is_unset(
    tmp_path: Path,
) -> None:
    """NFR-002's default: a control that could not measure returns failure, not a pass --
    no network/auth is not the same fact as a divergence, but it still blocks by default."""
    repository = _make_repository(tmp_path, with_ruleset_script=True)

    result = _run_hook(
        repository,
        env_overrides={
            "FAKE_RULESET_EXIT": "1",
            "FAKE_RULESET_OUTPUT": _GH_UNAVAILABLE_OUTPUT,
        },
    )

    assert result.returncode == 1, (
        f"the hook let an unmeasured ruleset through with no escape valve set. "
        f"stderr: {result.stderr!r}"
    )
    assert "PUSH RECUSADO" in result.stderr
    assert "NAO CONSEGUI MEDIR" in result.stderr
    assert "PLAYBOOK_ALLOW_UNMEASURED_RULESET" in result.stderr, (
        "the refusal must name the escape valve so the developer knows it exists"
    )


def test_the_hook_lets_the_push_through_when_the_escape_valve_is_set(tmp_path: Path) -> None:
    """The one deliberate relief NFR-002 keeps: named, opt-in, and never silent about the
    fact that the push went out without a measurement."""
    repository = _make_repository(tmp_path, with_ruleset_script=True)

    result = _run_hook(
        repository,
        env_overrides={
            "FAKE_RULESET_EXIT": "1",
            "FAKE_RULESET_OUTPUT": _GH_UNAVAILABLE_OUTPUT,
            "PLAYBOOK_ALLOW_UNMEASURED_RULESET": "1",
        },
    )

    assert result.returncode == 0, (
        f"the escape valve did not let the push through. stderr: {result.stderr!r}"
    )
    assert "PUSH RECUSADO" not in result.stderr
    assert "PLAYBOOK_ALLOW_UNMEASURED_RULESET" in result.stderr, (
        "using the valve must still print that the push was not measured -- never silent"
    )
    assert "NAO MEDIDO" in result.stderr or "NAO CONSEGUI MEDIR" in result.stderr


def test_the_hook_lets_a_reconciled_push_through(tmp_path: Path) -> None:
    """The measured-and-matching case: nothing to warn about, nothing to block."""
    repository = _make_repository(tmp_path, with_ruleset_script=True)

    result = _run_hook(
        repository,
        env_overrides={"FAKE_RULESET_EXIT": "0", "FAKE_RULESET_OUTPUT": "OK"},
    )

    assert result.returncode == 0, f"stderr: {result.stderr!r}"
    assert "PUSH RECUSADO" not in result.stderr
    assert "NAO CONSEGUI MEDIR" not in result.stderr


def test_the_hook_treats_an_unrecognized_ruleset_failure_as_environment_not_divergence(
    tmp_path: Path,
) -> None:
    """A crash that is neither the gh-unavailable marker nor an ERROR: line (e.g. a
    traceback from a broken environment) must not be silently read as a measured
    divergence -- it did not measure anything either."""
    repository = _make_repository(tmp_path, with_ruleset_script=True)

    result = _run_hook(
        repository,
        env_overrides={
            "FAKE_RULESET_EXIT": "1",
            "FAKE_RULESET_OUTPUT": "Traceback (most recent call last):\nModuleNotFoundError",
        },
    )

    assert result.returncode == 1, f"stderr: {result.stderr!r}"
    assert "BLOQUEADO POR AMBIENTE" in result.stderr
    assert "PUSH RECUSADO" not in result.stderr
