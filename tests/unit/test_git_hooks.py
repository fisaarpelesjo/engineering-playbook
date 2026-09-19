from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "git-hooks" / "pre-commit"
RESOURCE_HOOK = (
    ROOT / "src" / "engineering_playbook" / "resources" / "scripts" / "git-hooks" / "pre-commit"
)


def _git(repository: Path, *arguments: str) -> None:
    """Run git in a throwaway repository, and fail loudly rather than skip."""
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


def _run_hook(repository: Path) -> subprocess.CompletedProcess[str]:
    """Run the real hook file inside a throwaway repository, invoked by bare name.

    The hook is copied in and run as ``bash pre-commit`` rather than by an absolute path,
    and rather than by relying on the executable bit: `git ls-files -s` on the tracked
    file is `100644` (no executable bit is tracked, and the installer that copies this
    file into a derived project does not set one either -- see `pre-commit`'s own header
    and the delivery report for that gap). Invoking it by bare name through `bash`
    measures the hook's actual decision without depending on a bit this repository does
    not promise to set.
    """
    copied = repository / "pre-commit"
    copied.write_bytes(HOOK.read_bytes())
    return subprocess.run(
        ("bash", "pre-commit"),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_hook_exists_and_names_the_order_it_serves() -> None:
    """A hook whose reason is not written is a hook somebody deletes as noise."""
    assert HOOK.is_file(), f"{HOOK} is missing"
    text = HOOK.read_text(encoding="utf-8")
    assert "--no-verify" in text, (
        "the hook does not write down that `--no-verify` walks past it; an unspoken "
        "weakness is what makes a gate theatre"
    )
    assert "core.hooksPath" in text, (
        "the hook does not write down that `core.hooksPath` can be pointed elsewhere"
    )


def test_the_distributed_copy_matches_the_source_of_truth() -> None:
    """The resources mirror is what actually ships; a stale copy ships a stale guard."""
    assert RESOURCE_HOOK.is_file(), f"{RESOURCE_HOOK} is missing"
    assert RESOURCE_HOOK.read_bytes() == HOOK.read_bytes(), (
        "src/engineering_playbook/resources/scripts/git-hooks/pre-commit has drifted "
        "from scripts/git-hooks/pre-commit; derived projects install from the resources "
        "copy, so a divergence here ships the wrong guard silently"
    )


def test_the_hook_refuses_a_commit_whose_branch_is_main(tmp_path: Path) -> None:
    """The bite, measured -- not the absence of a bite inferred from a green suite."""
    repository = tmp_path / "on-main"
    repository.mkdir()
    _git(repository, "init", "--initial-branch=main")

    result = _run_hook(repository)

    assert result.returncode == 1, (
        f"the hook did not refuse with its own exit code; it exited {result.returncode}. "
        f"stderr: {result.stderr!r}"
    )
    assert "main" in result.stderr
    assert "git switch -c" in result.stderr, (
        "the refusal does not say what to do instead; a gate that only says no costs a "
        "round trip every time it bites"
    )


def test_the_hook_refuses_a_commit_whose_branch_is_master(tmp_path: Path) -> None:
    """`master` is the other name this template's own delivery policy treats as main."""
    repository = tmp_path / "on-master"
    repository.mkdir()
    _git(repository, "init", "--initial-branch=master")

    result = _run_hook(repository)

    assert result.returncode == 1
    assert "master" in result.stderr


def test_the_hook_lets_a_commit_be_born_on_any_other_branch(tmp_path: Path) -> None:
    """The other half, and it is not decoration.

    A hook that refused everything would pass the node above while making the
    repository unusable. Both directions are asserted so neither can be satisfied by
    breaking the other.
    """
    repository = tmp_path / "on-a-branch"
    repository.mkdir()
    _git(repository, "init", "--initial-branch=feat/001-example")

    result = _run_hook(repository)

    assert result.returncode == 0, (
        f"the hook refused a commit on a branch that is not main/master. stderr: {result.stderr!r}"
    )


def test_the_hook_protects_the_first_commit_of_a_fresh_repository(tmp_path: Path) -> None:
    """The exact case that made `symbolic-ref` the right call instead of `rev-parse`.

    A repository with zero commits has an unborn `HEAD`. `git rev-parse --abbrev-ref
    HEAD` fails there and, piped through the usual fallback, resolves to the literal
    string `"HEAD"` rather than the branch name -- which would let this exact commit,
    the one nobody can move later without rewriting the root, slip through unguarded.
    This node is the regression test for that specific failure mode, not a restatement
    of the node above.
    """
    repository = tmp_path / "fresh"
    repository.mkdir()
    _git(repository, "init", "--initial-branch=main")

    result = _run_hook(repository)

    assert result.returncode == 1, (
        f"the hook let a repository's first commit through on `main`; stderr: {result.stderr!r}"
    )
