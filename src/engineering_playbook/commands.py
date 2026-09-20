from __future__ import annotations

import json
import shutil
from pathlib import Path

from .core import (
    GhUnavailableError,
    GitUnavailableError,
    check_ruleset_reconciliation,
    git_branch,
    git_head,
    git_status,
    git_tree,
    load_yaml,
    next_checkpoint_id,
    print_result,
    utc_now,
    verify_root,
    write_yaml_atomic,
)
from .receipt import CiReceiptStatus, battery_claims, check_ci_receipt


def command_verify(root: Path) -> int:
    return print_result(verify_root(root))


def command_verify_ruleset(root: Path) -> int:
    """T201's CI-only control: compare `.github/rulesets/main.yml` against the server.

    Not part of `command_verify`/`verify_root` -- see the docstring of
    `check_ruleset_reconciliation` for why the local/offline path (`doctor`, `verify`,
    `resume`, `checkpoint`) stays unaffected by a network-dependent check.
    """
    try:
        result = check_ruleset_reconciliation(root)
    except GhUnavailableError as failure:
        print(f"ERROR: gh nao respondeu, portanto o ruleset aplicado nao foi medido: {failure}")
        return 1
    return print_result(result)


def command_doctor(root: Path) -> int:
    result = verify_root(root)
    for command in ["python", "uv", "git"]:
        if shutil.which(command) is None:
            result.errors.append(f"Missing command: {command}")
    try:
        branch, head, dirty_paths = git_branch(root), git_head(root), git_status(root)
    except GitUnavailableError as failure:
        result.errors.append(f"git nao respondeu, portanto o estado real nao foi medido: {failure}")
        return print_result(result)
    print(f"branch: {branch}")
    print(f"head: {head}")
    print(f"dirty_paths: {len(dirty_paths)}")
    return print_result(result)


def command_resume(root: Path, output_format: str = "human") -> int:
    state = load_yaml(root / ".project/state.yml")
    result = verify_root(root)
    try:
        branch, head, dirty_paths = git_branch(root), git_head(root), git_status(root)
    except GitUnavailableError as failure:
        result.errors.append(f"git nao respondeu, portanto o estado real nao foi medido: {failure}")
        branch, head, dirty_paths = "unknown", "unknown", []
    context = {
        "project": load_yaml(root / ".project/project.yml")["project"]["name"],
        "branch": branch,
        "head": head,
        "dirty_paths": dirty_paths,
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
    try:
        branch = git_branch(root)
        head = git_head(root)
    except GitUnavailableError as failure:
        print(f"ERROR: git nao respondeu, portanto nada foi reconciliado: {failure}")
        return 1
    findings: list[str] = []
    if state.get("current_branch") != branch:
        findings.append(f"branch mismatch: state={state.get('current_branch')} git={branch}")
    # The gate in `core.verify_root` reads `last_verified_tree`, not `last_verified_commit`
    # (issue #30) -- only the tree survives a squash. This staleness check follows the same
    # field so it never blocks on the commit id that FR-007 makes purely informative.
    try:
        head_tree = git_tree(root, head)
    except GitUnavailableError as failure:
        print(f"ERROR: git nao respondeu, portanto a tree de HEAD nao foi medida: {failure}")
        return 1
    if state.get("last_verified_tree") not in {None, head_tree}:
        findings.append(
            f"stale verified tree: state={state.get('last_verified_tree')} git={head_tree}"
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


def command_checkpoint(root: Path, *, allow_divergent: bool = False) -> int:
    result = verify_root(root)
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}")
        return 1
    state_path = root / ".project/state.yml"
    state = load_yaml(state_path)
    try:
        branch, head, dirty_paths = git_branch(root), git_head(root), git_status(root)
    except GitUnavailableError as failure:
        print(f"ERROR: git nao respondeu, checkpoint nao foi gravado: {failure}")
        return 1

    # A checkpoint that AFFIRMS a green battery (validation.passed claims one ran) must not be
    # written unless the CI receipt covers this exact HEAD. Absence of a receipt, a receipt for
    # another commit, a dirty tree, or a partial/red run are all refused, never read as green.
    # allow_divergent is the explicit escape hatch: it writes the checkpoint anyway, but marks
    # it battery_claim_divergent and the command still exits 1 -- a divergent stop must not look
    # like a clean one.
    battery_claim_divergent = False
    if battery_claims(state):
        receipt_check = check_ci_receipt(root, head)
        if receipt_check.status is not CiReceiptStatus.COVERS:
            if not allow_divergent:
                print(f"checkpoint NAO gravado: {receipt_check.reason}")
                print(
                    "Rode a bateria de novo contra este HEAD, ou passe "
                    "allow_divergent=True para registrar a parada divergente mesmo assim."
                )
                return 1
            print(f"AVISO, e registrado: {receipt_check.reason}")
            battery_claim_divergent = True

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
        "branch": branch,
        "head": head,
        "working_tree": {
            "status": "dirty" if dirty_paths else "clean",
            "modified_paths": dirty_paths,
        },
        "completed_work": ["Implemented playbook artifacts or recorded current progress."],
        "commands": passed + failed,
        "validation": validation,
        "blockers": state.get("blockers", []),
        "next_action": state.get("next_actions", ["Run resume."])[0],
        "battery_claim_divergent": battery_claim_divergent,
    }
    write_yaml_atomic(root / checkpoint_rel, checkpoint)
    state["last_checkpoint"] = checkpoint_rel
    state["updated_at"] = checkpoint["created_at"]
    state["current_branch"] = checkpoint["branch"]
    state["validation"] = validation
    write_yaml_atomic(state_path, state)
    print(checkpoint_rel)
    if battery_claim_divergent:
        print(
            f"{checkpoint_rel} registra uma PARADA DIVERGENTE: a alegacao de bateria em "
            "validation.passed nao foi conferida contra este HEAD. battery_claim_divergent: "
            "true."
        )
        return 1
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
