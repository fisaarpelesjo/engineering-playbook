from __future__ import annotations

from playbook_core import git_branch, git_head, load_yaml, parse_args, utc_now, write_yaml_atomic


def main() -> int:
    args = parse_args("Inspect or apply non-destructive state reconciliation.")
    state_path = args.root / ".project/state.yml"
    state = load_yaml(state_path)
    branch = git_branch(args.root)
    head = git_head(args.root)
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
    if not args.apply:
        print("No changes written. Re-run with --apply for safe state metadata updates.")
        return 1
    state["current_branch"] = branch
    state["updated_at"] = utc_now()
    write_yaml_atomic(state_path, state)
    print("Applied non-destructive state metadata reconciliation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
