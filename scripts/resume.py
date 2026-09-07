from __future__ import annotations

import json

from playbook_core import git_branch, git_head, git_status, load_yaml, parse_args, verify_root


def main() -> int:
    args = parse_args("Reconstruct deterministic context without writing.")
    state = load_yaml(args.root / ".project/state.yml")
    result = verify_root(args.root)
    context = {
        "project": load_yaml(args.root / ".project/project.yml")["project"]["name"],
        "branch": git_branch(args.root),
        "head": git_head(args.root),
        "dirty_paths": git_status(args.root),
        "active_workstream": state["active_workstream"],
        "status": state["status"],
        "active_specification": state["active_specification"],
        "active_plan": state["active_plan"],
        "active_tasks": state["active_tasks"],
        "active_task": state["active_task"],
        "next_actions": state["next_actions"],
        "verification_errors": result.errors,
    }
    if args.format == "json":
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


if __name__ == "__main__":
    raise SystemExit(main())
