from __future__ import annotations

import shutil

from playbook_core import git_branch, git_head, git_status, parse_args, print_result, verify_root


def main() -> int:
    args = parse_args("Diagnose environment and repository health without writing.")
    result = verify_root(args.root)
    for command in ["python", "uv", "git"]:
        if shutil.which(command) is None:
            result.errors.append(f"Missing command: {command}")
    print(f"branch: {git_branch(args.root)}")
    print(f"head: {git_head(args.root)}")
    print(f"dirty_paths: {len(git_status(args.root))}")
    return print_result(result)


if __name__ == "__main__":
    raise SystemExit(main())
