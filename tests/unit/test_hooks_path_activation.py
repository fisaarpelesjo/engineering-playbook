"""T203: `core.hooksPath` is a control only once `doctor`/`verify` reject its absence.

FR-003 / AC-002: "Repositorio com core.hooksPath nao configurado produz falha em doctor."
Each adversarial test below performs exactly the attempt the control must reject (an
unconfigured, or wrongly configured, `core.hooksPath`) and asserts the rejection is observed
in `verify_root`'s own output -- not inferred from the control merely existing (NFR-004).
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from engineering_playbook import installer as installer_module
from engineering_playbook.core import GitUnavailableError, git_config_get, verify_root
from engineering_playbook.installer import command_init, configure_hooks_path


def init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=root, check=True)


def install_hooks_dir(root: Path) -> None:
    hooks_dir = root / "scripts" / "git-hooks"
    hooks_dir.mkdir(parents=True)
    (hooks_dir / "pre-commit").write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")


# --- git_config_get: the primitive the check is built on -----------------------------------


def test_git_config_get_is_none_when_the_key_is_unset(tmp_path: Path) -> None:
    init_repo(tmp_path)
    assert git_config_get(tmp_path, "core.hooksPath") is None


def test_git_config_get_returns_the_configured_value(tmp_path: Path) -> None:
    init_repo(tmp_path)
    subprocess.run(
        ["git", "config", "core.hooksPath", "scripts/git-hooks"], cwd=tmp_path, check=True
    )
    assert git_config_get(tmp_path, "core.hooksPath") == "scripts/git-hooks"


def test_git_config_get_raises_on_a_real_error_not_none(tmp_path: Path) -> None:
    # `git config --get` outside any repository still succeeds (it just has no local config
    # to read), so a missing `.git` is not the real-error case here -- a config file git
    # itself refuses to parse is: measured with `git config --get` against a corrupted
    # `.git/config`, which exits 128, not 1.
    init_repo(tmp_path)
    config_path = tmp_path / ".git" / "config"
    with config_path.open("a", encoding="utf-8") as handle:
        handle.write("[core\nbroken\n")
    with pytest.raises(GitUnavailableError):
        git_config_get(tmp_path, "core.hooksPath")


# --- verify_root: the adversarial attempt, and the rejection it must produce (AC-002) -------


def test_doctor_verify_rejects_an_unconfigured_hooks_path(tmp_path: Path) -> None:
    """The exact attempt AC-002 names: hooks shipped, core.hooksPath never configured."""
    init_repo(tmp_path)
    install_hooks_dir(tmp_path)

    result = verify_root(tmp_path)

    assert any("Client git hooks are not active" in error for error in result.errors), (
        f"verify_root did not reject an unconfigured core.hooksPath; errors: {result.errors}"
    )


def test_doctor_verify_rejects_a_hooks_path_pointed_elsewhere(tmp_path: Path) -> None:
    """Configured, but not at this template's hooks -- still not active for FR-003's purpose."""
    init_repo(tmp_path)
    install_hooks_dir(tmp_path)
    subprocess.run(
        ["git", "config", "core.hooksPath", "/tmp/somewhere-else"], cwd=tmp_path, check=True
    )

    result = verify_root(tmp_path)

    assert any("Client git hooks are not active" in error for error in result.errors)


def test_doctor_verify_accepts_a_correctly_configured_hooks_path(tmp_path: Path) -> None:
    """The other half: a correct configuration must not be flagged (not a one-sided guard)."""
    init_repo(tmp_path)
    install_hooks_dir(tmp_path)
    subprocess.run(
        ["git", "config", "core.hooksPath", "scripts/git-hooks"], cwd=tmp_path, check=True
    )

    result = verify_root(tmp_path)

    assert not any("Client git hooks are not active" in error for error in result.errors), (
        f"a correctly configured core.hooksPath was rejected; errors: {result.errors}"
    )


def test_verify_root_does_not_require_hooks_path_outside_a_git_repository(tmp_path: Path) -> None:
    """A directory with no .git at all has nothing to activate; this is not FR-003's target."""
    install_hooks_dir(tmp_path)

    result = verify_root(tmp_path)

    assert not any("Client git hooks are not active" in error for error in result.errors)


# --- installer.configure_hooks_path: the mechanism side of the same requirement -------------


def test_configure_hooks_path_sets_the_config_when_hooks_are_present(tmp_path: Path) -> None:
    init_repo(tmp_path)
    install_hooks_dir(tmp_path)

    configure_hooks_path(tmp_path)

    assert git_config_get(tmp_path, "core.hooksPath") == "scripts/git-hooks"


def test_configure_hooks_path_is_a_silent_no_op_without_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `.git` means nothing to configure; this must not even shell out to git."""
    install_hooks_dir(tmp_path)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> None:
        calls.append(command)

    monkeypatch.setattr(installer_module.subprocess, "run", fake_run)

    configure_hooks_path(tmp_path)  # must not raise

    assert calls == [], "configure_hooks_path shelled out to git for a non-git directory"


def test_engineering_playbook_init_activates_the_hooks_it_installs(tmp_path: Path) -> None:
    """T203's bootstrap integration, measured through the real installer, not assumed."""
    init_repo(tmp_path)
    args = argparse.Namespace(
        path=tmp_path,
        project_name=None,
        profile="standard",
        stack="python",
        agents="codex",
        ci="github",
        dry_run=False,
        source="package",
    )

    assert command_init(args) == 0
    assert (tmp_path / "scripts" / "git-hooks" / "pre-commit").is_file()
    assert git_config_get(tmp_path, "core.hooksPath") == "scripts/git-hooks"
