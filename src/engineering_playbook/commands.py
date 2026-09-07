from __future__ import annotations

import json
import shutil
from pathlib import Path

from .core import (
    git_branch,
    git_head,
    git_status,
    load_yaml,
    next_checkpoint_id,
    print_result,
    utc_now,
    verify_root,
    write_yaml_atomic,
)


def command_verify(root: Path) -> int:
    return print_result(verify_root(root))


def command_doctor(root: Path) -> int:
    result = verify_root(root)
    for command in ["python", "uv", "git"]:
        if shutil.which(command) is None:
            result.errors.append(f"Missing command: {command}")
    print(f"branch: {git_branch(root)}")
    print(f"head: {git_head(root)}")
    print(f"dirty_paths: {len(git_status(root))}")
    return print_result(result)


def command_resume(root: Path, output_format: str = "human") -> int:
    state = load_yaml(root / ".project/state.yml")
    result = verify_root(root)
    context = {
        "project": load_yaml(root / ".project/project.yml")["project"]["name"],
        "branch": git_branch(root),
        "head": git_head(root),
        "dirty_paths": git_status(root),
        "active_workstream": state["active_workstream"],
        "status": state["status"],
        "active_specification": state["active_specification"],
        "active_plan": state["active_plan"],
        "active_tasks": state["active_tasks"],
        "active_task": state["active_task"],
        "next_actions": state["next_actions"],
        "verification_errors": result.errors,
    }
    if output_format == "json":
        print(json.dumps(context, indent=2, ensure_ascii=True))
    else:
        print(f"Project: {context['project']}")
        print(f"Branch: {context['branch']}")
        print(f"HEAD: {context['head']}")
        print(f"Active workstream: {context['active_workstream']} ({context['status']})")
        print(f"Spec: {context['active_specification']}")
        print(f"Plan: {context['active_plan']}")
        print(f"Tasks: {context['active_tasks']}")
        print(f"Active task: {context['active_task']}")
        print("Next actions:")
        for action in context["next_actions"]:
            print(f"- {action}")
        if result.errors:
            print("Material divergences:")
            for error in result.errors:
                print(f"- {error}")
    return 1 if result.errors else 0


def command_reconcile(root: Path, apply: bool = False) -> int:
    state_path = root / ".project/state.yml"
    state = load_yaml(state_path)
    branch = git_branch(root)
    head = git_head(root)
    findings: list[str] = []
    if state.get("current_branch") != branch:
        findings.append(f"branch mismatch: state={state.get('current_branch')} git={branch}")
    if state.get("last_verified_commit") not in {None, head}:
        findings.append(
            f"stale verified commit: state={state.get('last_verified_commit')} git={head}"
        )
    if not findings:
        print("OK")
        return 0
    for finding in findings:
        print(f"FINDING: {finding}")
    if not apply:
        print("No changes written. Re-run with --apply for safe state metadata updates.")
        return 1
    state["current_branch"] = branch
    state["updated_at"] = utc_now()
    write_yaml_atomic(state_path, state)
    print("Applied non-destructive state metadata reconciliation.")
    return 0


def command_checkpoint(root: Path) -> int:
    result = verify_root(root)
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}")
        return 1
    state_path = root / ".project/state.yml"
    state = load_yaml(state_path)
    checkpoint_id = next_checkpoint_id(root)
    checkpoint_rel = f".project/checkpoints/{checkpoint_id}.yml"
    passed = state.get("validation", {}).get("passed", [])
    failed = state.get("validation", {}).get("failed", [])
    checkpoint_command = "engineering-playbook checkpoint"
    if checkpoint_command not in passed:
        passed = [*passed, checkpoint_command]
    validation = state.get("validation", {})
    validation["passed"] = passed
    checkpoint = {
        "schema_version": "1.0.0",
        "checkpoint_id": checkpoint_id,
        "created_at": utc_now(),
        "workstream": state["active_workstream"],
        "task": state["active_task"],
        "branch": git_branch(root),
        "head": git_head(root),
        "working_tree": {
            "status": "dirty" if git_status(root) else "clean",
            "modified_paths": git_status(root),
        },
        "completed_work": ["Implemented playbook artifacts or recorded current progress."],
        "commands": passed + failed,
        "validation": validation,
        "blockers": state.get("blockers", []),
        "next_action": state.get("next_actions", ["Run resume."])[0],
    }
    write_yaml_atomic(root / checkpoint_rel, checkpoint)
    state["last_checkpoint"] = checkpoint_rel
    state["updated_at"] = checkpoint["created_at"]
    state["current_branch"] = checkpoint["branch"]
    state["validation"] = validation
    write_yaml_atomic(state_path, state)
    print(checkpoint_rel)
    return 0


def command_migrate(root: Path) -> int:
    result = verify_root(root)
    if result.errors:
        print("Migration inspection found issues; resolve manually before applying migrations.")
        for error in result.errors:
            print(f"- {error}")
        return 1
    print("No migration required.")
    return 0
