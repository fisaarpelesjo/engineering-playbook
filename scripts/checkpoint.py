from __future__ import annotations

from playbook_core import (
    git_branch,
    git_head,
    git_status,
    load_yaml,
    next_checkpoint_id,
    parse_args,
    utc_now,
    verify_root,
    write_yaml_atomic,
)


def main() -> int:
    args = parse_args("Persist state and checkpoint atomically.")
    result = verify_root(args.root)
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}")
        return 1
    state_path = args.root / ".project/state.yml"
    state = load_yaml(state_path)
    checkpoint_id = next_checkpoint_id(args.root)
    checkpoint_rel = f".project/checkpoints/{checkpoint_id}.yml"
    passed = state.get("validation", {}).get("passed", [])
    failed = state.get("validation", {}).get("failed", [])
    checkpoint_command = "uv run python scripts/checkpoint.py"
    if checkpoint_command not in passed:
        passed = [*passed, checkpoint_command]
    checkpoint = {
        "schema_version": "1.0.0",
        "checkpoint_id": checkpoint_id,
        "created_at": utc_now(),
        "workstream": state["active_workstream"],
        "task": state["active_task"],
        "branch": git_branch(args.root),
        "head": git_head(args.root),
        "working_tree": {
            "status": "dirty" if git_status(args.root) else "clean",
            "modified_paths": git_status(args.root),
        },
        "completed_work": ["Implemented playbook artifacts or recorded current progress."],
        "commands": passed + failed,
        "validation": state.get("validation", {}),
        "blockers": state.get("blockers", []),
        "next_action": state.get("next_actions", ["Run resume."])[0],
    }
    write_yaml_atomic(args.root / checkpoint_rel, checkpoint)
    state["last_checkpoint"] = checkpoint_rel
    state["updated_at"] = checkpoint["created_at"]
    state["current_branch"] = checkpoint["branch"]
    state["validation"]["passed"] = passed
    write_yaml_atomic(state_path, state)
    print(checkpoint_rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
