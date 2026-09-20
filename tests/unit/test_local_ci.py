from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

from engineering_playbook import local_ci
from engineering_playbook.local_ci import classify, main, owned_paths_of, run_workflow

#: Resolved, never a bare `"bash"`, for the hook-invoking helpers below. On this platform a bare
#: `"bash"` handed to `subprocess.run` from a Python process is resolved by Windows' own
#: `CreateProcess` search order, which checks `System32` *before* `PATH` -- and `System32` carries
#: WSL's `bash.exe` launcher. That is a different OS environment (its own filesystem, its own
#: installed tools), not the Git Bash the hook and its workflows are written for. `shutil.which`
#: walks `PATH` directly and correctly returns Git's `bash.exe`; resolving it once here and using
#: the full path everywhere below sidesteps the ambiguity instead of silently testing WSL.
_BASH = shutil.which("bash")
assert _BASH is not None, "bash must be on PATH for the hook tests below to run at all"
BASH: str = _BASH

ROOT = Path(__file__).resolve().parents[2]
SHIM = ROOT / "scripts" / "local_ci.py"
RESOURCE_SHIM = ROOT / "src" / "engineering_playbook" / "resources" / "scripts" / "local_ci.py"
HOOK = ROOT / "scripts" / "git-hooks" / "pre-push"
RESOURCE_HOOK = (
    ROOT / "src" / "engineering_playbook" / "resources" / "scripts" / "git-hooks" / "pre-push"
)


def _git(repository: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ("git", *arguments), cwd=repository, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, (
        f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
    )
    return completed


def _init_repo(repository: Path) -> None:
    repository.mkdir(parents=True, exist_ok=True)
    _git(repository, "init", "--initial-branch=main", "-q")
    _git(repository, "config", "user.email", "test@example.invalid")
    _git(repository, "config", "user.name", "Test")
    (repository / "placeholder.txt").write_text("x\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "initial")


#: A workflow written to drive classification, not to describe it: one step a runner-only
#: expression touches, one that builds the environment, one that passes, and one that fails --
#: with a step AFTER the failure that must never run, the same "CI stops at the first red" rule
#: `run_workflow` implements.
_FAKE_WORKFLOW = textwrap.dedent(
    """\
    name: fake
    on: [push]
    jobs:
      job:
        runs-on: ubuntu-latest
        steps:
          - name: Checkout
            uses: actions/checkout@v4
          - name: Passes
            run: echo ok
          - name: Only the runner can expand
            run: echo "${{ github.sha }}"
          - name: Builds the environment
            run: pip install -e .
          - name: Fails
            run: exit 1
          - name: Never reached
            run: echo should-not-run
    """
)


def _write_fake_workflow(repository: Path) -> Path:
    workflows = repository / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    path = workflows / "fake.yml"
    path.write_text(_FAKE_WORKFLOW, encoding="utf-8")
    return path


# --- classify() ---------------------------------------------------------------------------


def test_classify_names_a_runner_only_expression() -> None:
    reason = classify('echo "${{ github.sha }}"')
    assert reason is not None
    assert "runner" in reason


def test_classify_names_a_github_star_environment_variable() -> None:
    reason = classify('echo "$GITHUB_HEAD_REF"')
    assert reason is not None
    assert "runner" in reason


def test_classify_names_an_if_condition_that_needs_the_runner_even_with_a_clean_command() -> None:
    reason = classify("echo ok", condition="github.event_name == 'pull_request'")
    assert reason is not None


def test_classify_names_an_environment_building_step() -> None:
    assert classify("uv sync --locked") == "constroi o ambiente"
    assert classify("pip install -e .") == "constroi o ambiente"


def test_classify_lets_a_plain_code_step_through() -> None:
    assert classify("uv run pytest") is None
    assert classify("uv run ruff check .") is None


# --- run_workflow() ------------------------------------------------------------------------


def test_run_workflow_classifies_each_step_and_stops_at_the_first_failure(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _init_repo(repository)
    workflow = _write_fake_workflow(repository)

    result = run_workflow(workflow, repository, dry_run=False)

    names = [step.name for step in result.steps]
    assert names == ["Passes", "Only the runner can expand", "Builds the environment", "Fails"], (
        "the step after the failure ran; CI stops the job at the first red and so must this"
    )
    assert result.steps[0].status == "ok"
    assert result.steps[1].status == "skipped"
    assert result.steps[2].status == "skipped"
    assert result.steps[3].status == "failed"
    assert result.verdict == "VERMELHO"


def test_run_workflow_in_dry_run_mode_executes_nothing(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _init_repo(repository)
    workflow = _write_fake_workflow(repository)

    result = run_workflow(workflow, repository, dry_run=True)

    # The step that would fail for real is reported "ok" under --list, because nothing ran.
    failing_step = next(s for s in result.steps if s.name == "Fails")
    assert failing_step.status == "ok"
    assert "not executed" in failing_step.detail


def test_run_workflow_with_only_passing_code_steps_is_green(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _init_repo(repository)
    workflows = repository / ".github" / "workflows"
    workflows.mkdir(parents=True, exist_ok=True)
    workflow = workflows / "green.yml"
    workflow.write_text(
        textwrap.dedent(
            """\
            name: green
            on: [push]
            jobs:
              job:
                runs-on: ubuntu-latest
                steps:
                  - name: Passes
                    run: echo ok
            """
        ),
        encoding="utf-8",
    )

    result = run_workflow(workflow, repository, dry_run=False)

    assert result.verdict == "VERDE"
    assert result.counts == (1, 0, 0)


# --- owned_paths_of() / --affected --------------------------------------------------------


def test_owned_paths_of_reads_the_whole_repo_when_a_step_uses_a_bare_dot() -> None:
    steps = [{"run": "uv run ruff check ."}]
    assert owned_paths_of(steps, None) is None


def test_owned_paths_of_derives_a_narrower_path_from_a_named_script() -> None:
    steps = [{"run": "uv run python scripts/verify.py"}]
    owned = owned_paths_of(steps, None)
    assert owned == {"scripts/verify.py"}


# --- main(): the receipt --------------------------------------------------------------------


def test_main_writes_a_receipt_naming_the_head_it_measured(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _init_repo(repository)
    _write_fake_workflow(repository)
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "add the fake workflow")
    head = _git(repository, "rev-parse", "HEAD").stdout.strip()

    status = main(["--root", str(repository)])

    assert status == 1, "the fake workflow's failing step must fail the run"
    receipt_path = repository / ".project" / "last-ci-run.yml"
    assert receipt_path.is_file()
    text = receipt_path.read_text(encoding="utf-8")
    assert "kind: local_ci_receipt" in text
    assert f"head: '{head}'" in text
    assert "tree_was_dirty_before_run: false" in text
    assert "red: 1" in text


def test_main_with_list_writes_no_receipt(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _init_repo(repository)
    _write_fake_workflow(repository)

    status = main(["--root", str(repository), "--list"])

    assert status == 0
    assert not (repository / ".project" / "last-ci-run.yml").exists()


def test_main_records_a_dirty_tree_before_the_run(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _init_repo(repository)
    _write_fake_workflow(repository)
    (repository / "uncommitted.txt").write_text("x\n", encoding="utf-8")

    main(["--root", str(repository)])

    text = (repository / ".project" / "last-ci-run.yml").read_text(encoding="utf-8")
    assert "tree_was_dirty_before_run: true" in text


def test_main_returns_2_when_there_is_no_workflows_directory(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    _init_repo(repository)

    assert main(["--root", str(repository)]) == 2


# --- distribution: the shim and its resources mirror ----------------------------------------


def test_the_shim_is_a_thin_wrapper_around_the_package_module() -> None:
    text = SHIM.read_text(encoding="utf-8")
    assert "from engineering_playbook.local_ci import main" in text


def test_the_distributed_shim_matches_the_source_of_truth() -> None:
    assert RESOURCE_SHIM.is_file(), f"{RESOURCE_SHIM} is missing"
    assert RESOURCE_SHIM.read_bytes() == SHIM.read_bytes(), (
        "src/engineering_playbook/resources/scripts/local_ci.py has drifted from "
        "scripts/local_ci.py; derived projects install from the resources copy"
    )


# --- the pre-push hook, run for real ---------------------------------------------------------


def test_the_hook_exists_and_names_its_own_known_leaks() -> None:
    assert HOOK.is_file(), f"{HOOK} is missing"
    text = HOOK.read_text(encoding="utf-8")
    assert "--no-verify" in text
    assert "core.hooksPath" in text


def test_the_distributed_hook_matches_the_source_of_truth() -> None:
    assert RESOURCE_HOOK.is_file(), f"{RESOURCE_HOOK} is missing"
    assert RESOURCE_HOOK.read_bytes() == HOOK.read_bytes(), (
        "src/engineering_playbook/resources/scripts/git-hooks/pre-push has drifted from "
        "scripts/git-hooks/pre-push; derived projects install from the resources copy"
    )


def _run_hook(repository: Path) -> subprocess.CompletedProcess[str]:
    copied = repository / "pre-push"
    copied.write_bytes(HOOK.read_bytes())
    return subprocess.run(
        (BASH, "pre-push"), cwd=repository, capture_output=True, text=True, check=False
    )


def test_the_hook_blocks_on_a_real_red_step_and_names_it_as_code(tmp_path: Path) -> None:
    """Run the actual hook file, in a throwaway repo, against a workflow whose one code step
    fails -- not a description of what the hook is supposed to do.
    """
    repository = tmp_path / "on-red"
    _init_repo(repository)
    scripts_dir = repository / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "local_ci.py").write_text(
        "import sys\nprint('a step of CODE failed on purpose')\nsys.exit(1)\n",
        encoding="utf-8",
    )
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "add a local_ci that always reds")

    result = _run_hook(repository)

    assert result.returncode == 1
    assert "PUSH RECUSADO" in result.stderr
    assert "CODIGO" in result.stderr


def test_the_hook_reports_a_missing_uv_as_environment_not_code(tmp_path: Path) -> None:
    repository = tmp_path / "no-uv"
    _init_repo(repository)
    (repository / "pre-push").write_bytes(HOOK.read_bytes())

    # `git` still has to resolve (the hook's very first act is `git rev-parse --show-toplevel`)
    # and the `cat` builtin used to print the refusal lives in Git's `usr/bin`, not next to
    # `git.exe` itself -- so the stripped `PATH` keeps exactly those two directories and nothing
    # else. `uv` is the one thing missing, which is what this test measures. `BASH` itself is
    # invoked by its resolved path below, not looked up on `PATH`.
    git = shutil.which("git")
    assert git is not None, "git must be on PATH for this test to say anything about uv"
    minimal_path = f"{Path(git).parent}{os.pathsep}{Path(BASH).parent}"

    result = subprocess.run(
        (BASH, "pre-push"),
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": minimal_path},
    )

    assert result.returncode == 1
    assert "AMBIENTE" in result.stderr
    assert "uv" in result.stderr


def test_the_hook_reports_a_signal_death_as_machine_not_code(tmp_path: Path) -> None:
    """POSIX shells report a process killed by a signal as exit `128 + signal`. The hook's own
    classification is driven purely by that number (`$STATUS -gt 128`), not by how it got there
    -- so this drives it with a real subprocess that exits `137` (the value a `SIGKILL`, signal
    9, would produce), rather than sending a real signal. Windows' Python has no `SIGKILL` to
    send in the first place (`signal.SIGKILL` does not exist there), so reproducing the OS-level
    kill itself would make this test platform-dependent for a fact the hook's own arithmetic
    already makes platform-independent.
    """
    repository = tmp_path / "on-signal"
    _init_repo(repository)
    scripts_dir = repository / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "local_ci.py").write_text("import sys\nsys.exit(137)\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "add a local_ci that exits as if signal-killed")

    result = _run_hook(repository)

    assert result.returncode == 1
    assert "MAQUINA" in result.stderr


def test_the_hook_lets_a_real_green_run_through(tmp_path: Path) -> None:
    repository = tmp_path / "on-green"
    _init_repo(repository)
    scripts_dir = repository / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "local_ci.py").write_text("import sys\nsys.exit(0)\n", encoding="utf-8")
    _git(repository, "add", ".")
    _git(repository, "commit", "-q", "-m", "add a local_ci that always greens")

    result = _run_hook(repository)

    assert result.returncode == 0, result.stderr


def test_module_docstring_names_this_is_not_the_merge_gate() -> None:
    """The same disclaimer the derived project's tool carries -- a local green is not merge
    evidence, and the module must say so rather than let a caller infer otherwise.
    """
    assert local_ci.__doc__ is not None
    assert "not the merge gate" in local_ci.__doc__
