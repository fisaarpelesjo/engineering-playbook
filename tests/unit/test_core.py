from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from engineering_playbook.core import (
    load_yaml,
    validate_conventional_title,
    validate_prd_document,
    validate_transition,
    verify_root,
)
from engineering_playbook.delivery import (
    build_branch_name,
    ci_checks_passed,
    delivery_state,
    prepare_is_fresh,
    validate_branch_name,
    validate_pr_title,
    validate_publish_plan,
)

ROOT = Path(__file__).resolve().parents[2]


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_verify_current_repository() -> None:
    result = verify_root(ROOT)
    assert result.errors == []


def test_state_transition_rejects_planned_to_done() -> None:
    assert not validate_transition("planned", "done")
    assert validate_transition("planned", "ready")


def test_conventional_title_validation() -> None:
    assert validate_conventional_title("feat(playbook): add checkpoint command")
    assert not validate_conventional_title("updates")
    assert not validate_conventional_title("fix: Bad title.")


def test_resume_is_read_only() -> None:
    before = (ROOT / ".project/state.yml").read_text(encoding="utf-8")
    completed = run_script("scripts/resume.py")
    after = (ROOT / ".project/state.yml").read_text(encoding="utf-8")
    assert before == after
    assert completed.returncode == 0


def test_reconcile_without_apply_is_read_only() -> None:
    before = (ROOT / ".project/state.yml").read_text(encoding="utf-8")
    completed = run_script("scripts/reconcile.py")
    after = (ROOT / ".project/state.yml").read_text(encoding="utf-8")
    assert before == after
    assert completed.returncode in {0, 1}


def test_required_fixture_inventory_exists() -> None:
    fixtures = {
        "valid-project",
        "missing-spec",
        "stale-checkpoint",
        "wrong-branch",
        "dirty-working-tree",
        "missing-test-reference",
        "duplicate-requirement-id",
        "invalid-state-transition",
        "conflicting-agent-rules",
        "overlapping-workstream-ownership",
        "outdated-verified-commit",
        "forgotten-placeholder",
    }
    existing = {path.name for path in (ROOT / "tests/fixtures").iterdir() if path.is_dir()}
    assert fixtures <= existing


def test_prd_valid_fixtures_pass() -> None:
    fixture_dir = ROOT / "tests/fixtures/requirements"
    for path in fixture_dir.glob("valid-*.md"):
        assert validate_prd_document(path) == []


def test_prd_rejects_duplicate_requirement_id() -> None:
    errors = validate_prd_document(ROOT / "tests/fixtures/requirements/invalid-duplicate-id.md")
    assert any("duplicate requirement id: FR-001" in error for error in errors)


def test_prd_rejects_requirement_without_acceptance_criteria() -> None:
    errors = validate_prd_document(
        ROOT / "tests/fixtures/requirements/invalid-missing-acceptance.md"
    )
    assert any("has no acceptance criteria" in error for error in errors)


def test_prd_rejects_approved_placeholder() -> None:
    errors = validate_prd_document(
        ROOT / "tests/fixtures/requirements/invalid-approved-placeholder.md"
    )
    assert any("approved PRD contains unresolved placeholder markers" in error for error in errors)


def test_prd_rejects_approved_without_human_approval() -> None:
    errors = validate_prd_document(
        ROOT / "tests/fixtures/requirements/invalid-approved-without-approval.md"
    )
    assert any("approved PRD requires at least one approver" in error for error in errors)
    assert any("approved PRD requires approval_date" in error for error in errors)


def test_bootstrap_is_idempotent_when_prd_copy_exists() -> None:
    target = ROOT / "docs/requirements/project-requirements.md"
    if not target.exists():
        target.write_text(
            (ROOT / "templates/project/requirements.md").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    before = target.read_text(encoding="utf-8")
    completed = run_script("scripts/bootstrap.py")
    after = target.read_text(encoding="utf-8")
    assert completed.returncode == 0
    assert before == after


def test_bootstrap_distribution_excludes_source_history(tmp_path: Path) -> None:
    target = tmp_path / "derived-project"
    completed = run_script("scripts/bootstrap.py", "--target", str(target))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert not (target / "bootstrap-engineering-template.yml").exists()
    assert not (target / "specs/001-engineering-playbook").exists()
    assert not (target / "tests").exists()
    assert not list((target / ".project/checkpoints").glob("CP-*.yml"))
    assert not (target / ".project/workstreams/WS-001-engineering-playbook.yml").exists()
    assert not (target / ".project/distribution.yml").exists()
    assert (target / ".project/playbook.lock.yml").exists()
    assert not (target / ".venv").exists()
    assert not (target / ".pytest_cache").exists()
    assert not (target / ".ruff_cache").exists()


def test_bootstrap_distribution_creates_new_project_state(tmp_path: Path) -> None:
    target = tmp_path / "derived-project"
    completed = run_script("scripts/bootstrap.py", "--target", str(target))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    state = load_yaml(target / ".project/state.yml")
    project = load_yaml(target / ".project/project.yml")
    assert project["project"]["name"] == "derived-project"
    assert state["status"] == "proposed"
    assert state["current_phase"] == "requirements"
    assert state["active_workstream"] is None
    assert state["active_specification"] is None
    assert state["active_plan"] is None
    assert state["active_tasks"] is None
    assert state["active_task"] is None
    assert state["last_checkpoint"] is None
    assert state["last_verified_commit"] is None
    assert "001-engineering-playbook" not in (target / ".project/state.yml").read_text(
        encoding="utf-8"
    )
    lock = load_yaml(target / ".project/playbook.lock.yml")
    assert lock["playbook"]["name"] == "engineering-playbook"
    assert lock["files"]["managed"]


def test_bootstrap_distribution_is_idempotent_and_preserves_files(tmp_path: Path) -> None:
    target = tmp_path / "derived-project"
    assert run_script("scripts/bootstrap.py", "--target", str(target)).returncode == 0
    prd_path = target / "docs/requirements/project-requirements.md"
    state_path = target / ".project/state.yml"
    prd_path.write_text("custom PRD\n", encoding="utf-8")
    before_state = state_path.read_text(encoding="utf-8")
    completed = run_script("scripts/bootstrap.py", "--target", str(target))
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert prd_path.read_text(encoding="utf-8") == "custom PRD\n"
    assert state_path.read_text(encoding="utf-8") == before_state


def test_bootstrap_distribution_respects_selected_agents(tmp_path: Path) -> None:
    target = tmp_path / "derived-project"
    completed = run_script(
        "scripts/bootstrap.py",
        "--target",
        str(target),
        "--agents",
        "codex,cursor",
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (target / "AGENTS.md").exists()
    assert (target / ".cursor/rules/engineering.mdc").exists()
    assert not (target / "CLAUDE.md").exists()
    assert not (target / "GEMINI.md").exists()
    assert not (target / ".github/copilot-instructions.md").exists()
    assert not (target / ".devin/rules/engineering.md").exists()


def test_bootstrap_distribution_verifies_as_derived_project(tmp_path: Path) -> None:
    target = tmp_path / "derived-project"
    assert run_script("scripts/bootstrap.py", "--target", str(target)).returncode == 0
    completed = run_script("scripts/verify.py", "--root", str(target))
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_delivery_valid_branch_and_pr_title() -> None:
    branch = build_branch_name("feat", "019", "safe-delivery")
    assert branch == "feat/019-safe-delivery"
    assert validate_branch_name(branch)
    assert validate_pr_title("feat(delivery): add safe git delivery pipeline")


def test_delivery_rejects_dirty_start_on_main_by_validation() -> None:
    assert not validate_branch_name("feat/not-a-number")
    assert not validate_branch_name("main")


def test_delivery_protects_main_and_force_push() -> None:
    assert "refusing to push main" in validate_publish_plan("main")
    assert "force push is forbidden" in validate_publish_plan("feat/019-safe-delivery", force=True)


def test_delivery_detects_failing_ci() -> None:
    assert ci_checks_passed({"delivery-policy": "success", "quality": "success"})
    assert not ci_checks_passed({"delivery-policy": "success", "quality": "failure"})


def test_delivery_detects_obsolete_prepare(tmp_path: Path) -> None:
    target = tmp_path / "repo"
    assert run_script("scripts/bootstrap.py", "--target", str(target)).returncode == 0
    prepare_dir = target / ".project/delivery"
    prepare_dir.mkdir(parents=True)
    (prepare_dir / "prepare.yml").write_text(
        "schema_version: 1.0.0\nstatus: approved\nbranch: stale\nhead: stale\n",
        encoding="utf-8",
    )
    fresh, reason = prepare_is_fresh(target)
    assert not fresh
    assert "obsolete" in reason


def test_delivery_rejects_invalid_commit_title() -> None:
    assert not validate_pr_title("update stuff")
    assert not validate_conventional_title("update stuff")


def test_delivery_state_supports_resume_after_network_failure() -> None:
    state = delivery_state(
        ROOT,
        "feat(delivery): add safe git delivery pipeline",
        "body",
        ["scripts/delivery.py"],
    )
    assert state["status"] == "approved"
    assert state["body_file"] == ".project/delivery/pr.md"
    assert state["files"] == ["scripts/delivery.py"]


def test_delivery_publish_idempotence_is_documented() -> None:
    text = (ROOT / "src/engineering_playbook/delivery.py").read_text(encoding="utf-8")
    assert '"gh", "pr", "view"' in text
    assert '"edit"' in text
    assert '"create"' in text


def test_delivery_start_rejects_dirty_tree_without_override(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    (repo / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    completed = run_script(
        "scripts/delivery.py",
        "--root",
        str(repo),
        "start",
        "--type",
        "feat",
        "--number",
        "019",
        "--slug",
        "safe-delivery",
    )
    assert completed.returncode == 1
    assert "working tree is dirty" in completed.stdout


def test_delivery_prepare_rejects_main_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
    completed = run_script(
        "scripts/delivery.py",
        "--root",
        str(repo),
        "prepare",
        "--title",
        "feat(delivery): add safe git delivery pipeline",
    )
    assert completed.returncode == 1
    assert "branch different from main" in completed.stdout


def test_delivery_publish_requires_remote_authorization() -> None:
    completed = run_script("scripts/delivery.py", "publish")
    assert completed.returncode == 1
    assert "--yes-remote" in completed.stdout


def test_delivery_merge_requires_remote_authorization() -> None:
    completed = run_script("scripts/delivery.py", "merge", "--auto")
    assert completed.returncode == 1
    assert "--yes-remote" in completed.stdout


def test_delivery_status_is_read_only() -> None:
    before = (ROOT / ".project/state.yml").read_text(encoding="utf-8")
    completed = run_script("scripts/delivery.py", "status")
    after = (ROOT / ".project/state.yml").read_text(encoding="utf-8")
    assert completed.returncode == 0
    assert before == after
    assert "remote: not queried" in completed.stdout


def test_cli_entry_point_version() -> None:
    completed = subprocess.run(
        ["uv", "run", "engineering-playbook", "version"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "0.1.0"


def test_cli_init_empty_directory_with_options(tmp_path: Path) -> None:
    target = tmp_path / "project with spaces"
    completed = subprocess.run(
        [
            "uv",
            "run",
            "engineering-playbook",
            "init",
            str(target),
            "--profile",
            "standard",
            "--stack",
            "python",
            "--agents",
            "codex,claude",
            "--ci",
            "github",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (target / "docs/requirements/project-requirements.md").exists()
    assert (target / "AGENTS.md").exists()
    assert (target / "CLAUDE.md").exists()
    assert not (target / "GEMINI.md").exists()
    assert (target / ".github/workflows/quality.yml").exists()
    project = load_yaml(target / ".project/project.yml")
    assert project["project"]["default_workflow_profile"] == "standard"
    assert project["project"]["stack"] == "python"
    assert project["supported_agents"] == ["codex", "claude-code"]


def test_cli_init_dry_run_is_read_only(tmp_path: Path) -> None:
    target = tmp_path / "dry-run"
    completed = subprocess.run(
        ["uv", "run", "engineering-playbook", "init", str(target), "--dry-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert not target.exists()
    assert "Dry run" in completed.stdout


def test_cli_init_existing_directory_and_conflict(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    target.mkdir()
    (target / "README.md").write_text("custom\n", encoding="utf-8")
    completed = subprocess.run(
        ["uv", "run", "engineering-playbook", "init", str(target)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "CONFLICT: README.md" in completed.stdout
    assert (target / "README.md").read_text(encoding="utf-8") == "custom\n"


def test_cli_init_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "idempotent"
    first = subprocess.run(
        ["uv", "run", "engineering-playbook", "init", str(target)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    second = subprocess.run(
        ["uv", "run", "engineering-playbook", "init", str(target)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert first.returncode == 0, first.stdout + first.stderr
    assert second.returncode == 0, second.stdout + second.stderr


def test_cli_init_ci_none_skips_ci_files(tmp_path: Path) -> None:
    target = tmp_path / "no-ci"
    completed = subprocess.run(
        ["uv", "run", "engineering-playbook", "init", str(target), "--ci", "none"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert not (target / ".github/workflows/quality.yml").exists()
    assert load_yaml(target / ".project/playbook.lock.yml")["playbook"]["ci"] == "none"


def test_cli_init_does_not_copy_internal_artifacts(tmp_path: Path) -> None:
    target = tmp_path / "clean"
    assert (
        subprocess.run(
            ["uv", "run", "engineering-playbook", "init", str(target)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    state_text = (target / ".project/state.yml").read_text(encoding="utf-8")
    for forbidden in [
        "001-engineering-playbook",
        "CP-20260907-001",
        "CP-20260907-002",
        "CP-20260907-003",
        "CP-20260907-004",
        "24e3d92b4c8866732aa6b98bd630f414e4cb93b1",
    ]:
        assert forbidden not in state_text
    assert not (target / "tests").exists()
    assert not (target / "specs/001-engineering-playbook").exists()
    assert not (target / "bootstrap-engineering-template.yml").exists()


def test_cli_update_preserves_customizable_file(tmp_path: Path) -> None:
    target = tmp_path / "update-custom"
    assert (
        subprocess.run(
            ["uv", "run", "engineering-playbook", "init", str(target)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    readme = target / "README.md"
    readme.write_text("project custom readme\n", encoding="utf-8")
    completed = subprocess.run(
        ["uv", "run", "engineering-playbook", "update", str(target)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert readme.read_text(encoding="utf-8") == "project custom readme\n"


def test_cli_update_detects_managed_conflict(tmp_path: Path) -> None:
    target = tmp_path / "update-conflict"
    assert (
        subprocess.run(
            ["uv", "run", "engineering-playbook", "init", str(target)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    lock_before = (target / ".project/playbook.lock.yml").read_text(encoding="utf-8")
    managed = target / ".project/schemas/state.schema.json"
    managed.write_text('{"custom": true}\n', encoding="utf-8")
    completed = subprocess.run(
        ["uv", "run", "engineering-playbook", "update", str(target)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "CONFLICT: managed file modified locally" in completed.stdout
    assert (target / ".project/playbook.lock.yml").read_text(encoding="utf-8") == lock_before


def test_cli_update_dry_run_without_modifications(tmp_path: Path) -> None:
    target = tmp_path / "update-dry"
    assert (
        subprocess.run(
            ["uv", "run", "engineering-playbook", "init", str(target)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )
    lock_before = (target / ".project/playbook.lock.yml").read_text(encoding="utf-8")
    completed = subprocess.run(
        ["uv", "run", "engineering-playbook", "update", str(target), "--dry-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert (target / ".project/playbook.lock.yml").read_text(encoding="utf-8") == lock_before


def test_cli_init_rejects_unsafe_symlink(tmp_path: Path) -> None:
    target = tmp_path / "symlink"
    try:
        target.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        return
    completed = subprocess.run(
        ["uv", "run", "engineering-playbook", "init", str(target)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "symlink" in completed.stdout


def test_cli_delivery_remote_still_requires_yes_remote() -> None:
    completed = subprocess.run(
        ["uv", "run", "engineering-playbook", "delivery", "publish"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 1
    assert "--yes-remote" in completed.stdout
