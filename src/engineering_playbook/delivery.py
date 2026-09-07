from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any

try:
    from .core import (
        ROOT,
        git_branch,
        git_capture,
        git_head,
        git_status,
        load_yaml,
        utc_now,
        validate_conventional_title,
        verify_root,
        write_yaml_atomic,
    )
except ImportError:
    from engineering_playbook.core import (
        ROOT,
        git_branch,
        git_capture,
        git_head,
        git_status,
        load_yaml,
        utc_now,
        validate_conventional_title,
        verify_root,
        write_yaml_atomic,
    )

MAIN_BRANCHES = {"main", "master"}
BRANCH_TYPES = {
    "feat",
    "fix",
    "perf",
    "refactor",
    "test",
    "docs",
    "build",
    "ci",
    "chore",
    "spike",
}
REMOTE_COMMANDS = {"publish", "merge"}
PREPARE_FILE = ".project/delivery/prepare.yml"
PR_BODY_FILE = ".project/delivery/pr.md"
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]+['\"]"),
    re.compile(r"ghp_[A-Za-z0-9_]{20,}"),
]


def run(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=root, text=True, capture_output=True, check=False)


def validate_branch_name(branch: str) -> bool:
    pattern = (
        r"^(feat|fix|perf|refactor|test|docs|build|ci|chore|spike)"
        r"/[0-9]{3,6}-[a-z0-9]+(?:-[a-z0-9]+)*$"
    )
    return bool(re.match(pattern, branch))


def build_branch_name(change_type: str, item_id: str, slug: str) -> str:
    if change_type not in BRANCH_TYPES:
        raise ValueError(f"invalid branch type: {change_type}")
    if not re.match(r"^[0-9]{3,6}$", item_id):
        raise ValueError(f"invalid spec/issue number: {item_id}")
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", slug):
        raise ValueError(f"invalid slug: {slug}")
    return f"{change_type}/{item_id}-{slug}"


def validate_pr_title(title: str) -> bool:
    return validate_conventional_title(title)


def local_commits(root: Path, base: str = "main") -> list[str]:
    output = git_capture(root, "log", "--oneline", f"{base}..HEAD")
    return [line for line in output.splitlines() if line.strip()]


def staged_files(root: Path) -> list[str]:
    output = git_capture(root, "diff", "--cached", "--name-only")
    return [line for line in output.splitlines() if line.strip()]


def changed_files(root: Path) -> list[str]:
    output = git_capture(root, "diff", "--name-only")
    files = [line for line in output.splitlines() if line.strip()]
    files.extend(staged_files(root))
    return sorted(set(files))


def branch_is_main(branch: str) -> bool:
    return branch in MAIN_BRANCHES


def validate_publish_plan(branch: str, *, force: bool = False) -> list[str]:
    errors: list[str] = []
    if branch_is_main(branch):
        errors.append("refusing to push main")
    if force:
        errors.append("force push is forbidden")
    if not validate_branch_name(branch):
        errors.append(f"invalid branch name: {branch}")
    return errors


def ci_checks_passed(checks: dict[str, str]) -> bool:
    required = {"delivery-policy", "quality"}
    return required <= checks.keys() and all(checks[name] == "success" for name in required)


def scan_for_secrets(root: Path, files: list[str]) -> list[str]:
    findings: list[str] = []
    for rel_path in files:
        path = root / rel_path
        if not path.is_file() or path.stat().st_size > 1_000_000:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(rel_path)
                break
    return findings


def ownership_allows(root: Path, files: list[str]) -> bool:
    state = load_yaml(root / ".project/state.yml")
    workstream_id = state.get("active_workstream")
    if not workstream_id:
        return True
    matches = sorted((root / ".project/workstreams").glob(f"{workstream_id}-*.yml"))
    workstream_path = (
        matches[0] if matches else root / ".project/workstreams" / f"{workstream_id}.yml"
    )
    if not workstream_path.exists():
        return True
    workstream = load_yaml(workstream_path)
    owned = workstream.get("owned_paths", [])
    if "." in owned:
        return True
    return all(any(path == item or path.startswith(f"{item}/") for item in owned) for path in files)


def prepare_is_fresh(root: Path) -> tuple[bool, str]:
    path = root / PREPARE_FILE
    if not path.exists():
        return False, "prepare file is missing"
    data = load_yaml(path)
    if data.get("head") != git_head(root):
        return False, "prepare is obsolete: HEAD changed"
    if data.get("branch") != git_branch(root):
        return False, "prepare is obsolete: branch changed"
    if data.get("status") != "approved":
        return False, "prepare is not approved"
    return True, "prepare is fresh"


def delivery_state(
    root: Path,
    title: str,
    body: str,
    files: list[str],
    review: str = "approved_with_notes",
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "status": "approved",
        "created_at": utc_now(),
        "branch": git_branch(root),
        "head": git_head(root),
        "title": title,
        "body_file": PR_BODY_FILE,
        "review": review,
        "convergence": "checked",
        "files": files,
        "body": body,
    }


def pr_body(title: str, files: list[str]) -> str:
    file_lines = "\n".join(f"- `{path}`" for path in files) or "- No changed files detected."
    return f"""## Summary

{title}

## Problem and motivation

Prepared by `scripts/delivery.py prepare` from repository state.

## Specification and requirements

See active `.project/state.yml`, specs, ADRs and PRD references.

## Changes

{file_lines}

## Validation evidence

- `uv run python scripts/resume.py`
- `uv run python scripts/doctor.py`
- `uv run ruff format --check .`
- `uv run ruff check .`
- `uv run pyright`
- `uv run pytest`
- `uv run python scripts/verify.py`

## Benchmarks when applicable

N/A - not applicable unless performance requirements changed.

## Risks and limitations

Remote operations are not executed by prepare.

## Reviewer checklist

- [ ] Requirements trace to tasks and evidence.
- [ ] Tests and validations listed were actually executed.
- [ ] No secrets, personal data or invented evidence.
- [ ] State and checkpoint are updated when applicable.
"""


def command_start(args: argparse.Namespace) -> int:
    branch = build_branch_name(args.type, args.number, args.slug)
    if git_status(args.root) and not args.allow_dirty:
        print("ERROR: working tree is dirty. Use --allow-dirty only after preserving work.")
        return 1
    if not validate_branch_name(branch):
        print(f"ERROR: invalid branch name: {branch}")
        return 1
    completed = run(args.root, ["git", "switch", "-c", branch])
    if completed.returncode != 0:
        print(completed.stderr.strip())
        return completed.returncode
    print(branch)
    return 0


def command_prepare(args: argparse.Namespace) -> int:
    branch = git_branch(args.root)
    if branch_is_main(branch):
        print("ERROR: prepare requires a branch different from main.")
        return 1
    title = args.title or f"{branch.split('/', 1)[0]}: {branch.split('-', 1)[-1].replace('-', ' ')}"
    if not validate_pr_title(title):
        print(f"ERROR: invalid Conventional Commit title: {title}")
        return 1
    commands = [
        ["uv", "run", "python", "scripts/resume.py"],
        ["uv", "run", "python", "scripts/doctor.py"],
        ["uv", "run", "ruff", "format", "--check", "."],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "pyright"],
        ["uv", "run", "pytest"],
        ["uv", "run", "python", "scripts/verify.py"],
    ]
    for command in commands:
        completed = run(args.root, command)
        print("$ " + " ".join(command))
        if completed.stdout:
            print(completed.stdout.strip())
        if completed.returncode != 0:
            print(completed.stderr.strip())
            return completed.returncode
    result = verify_root(args.root)
    if result.errors:
        for error in result.errors:
            print(f"ERROR: {error}")
        return 1
    files = changed_files(args.root)
    body = pr_body(title, files)
    write_yaml_atomic(args.root / PREPARE_FILE, delivery_state(args.root, title, body, files))
    (args.root / PR_BODY_FILE).write_text(body, encoding="utf-8", newline="\n")
    run(args.root, ["uv", "run", "python", "scripts/checkpoint.py"])
    print("Prepared delivery. Files:")
    for path in files:
        print(f"- {path}")
    print(f"Title: {title}")
    print(f"PR body: {PR_BODY_FILE}")
    return 0


def command_commit(args: argparse.Namespace) -> int:
    fresh, reason = prepare_is_fresh(args.root)
    if not fresh:
        print(f"ERROR: {reason}")
        return 1
    files = staged_files(args.root)
    if not files:
        print("ERROR: no staged files.")
        return 1
    if scan_for_secrets(args.root, files):
        print("ERROR: staged files contain possible secrets.")
        return 1
    if not ownership_allows(args.root, files):
        print("ERROR: staged files are outside active ownership.")
        return 1
    prepare = load_yaml(args.root / PREPARE_FILE)
    title = args.message or prepare["title"]
    if not validate_conventional_title(title):
        print(f"ERROR: invalid Conventional Commit title: {title}")
        return 1
    prepare = load_yaml(args.root / PREPARE_FILE)
    completed = run(args.root, ["git", "commit", "-m", title, "-m", prepare["body"]])
    if completed.returncode != 0:
        print(completed.stderr.strip())
        return completed.returncode
    prepare["head"] = git_head(args.root)
    write_yaml_atomic(args.root / PREPARE_FILE, prepare)
    print(completed.stdout.strip())
    return 0


def require_remote_authorization(args: argparse.Namespace) -> bool:
    if not getattr(args, "yes_remote", False):
        print("ERROR: remote operation requires --yes-remote.")
        return False
    return True


def command_publish(args: argparse.Namespace) -> int:
    if not require_remote_authorization(args):
        return 1
    branch = git_branch(args.root)
    publish_errors = validate_publish_plan(branch)
    if publish_errors:
        for error in publish_errors:
            print(f"ERROR: {error}.")
        return 1
    fresh, reason = prepare_is_fresh(args.root)
    if not fresh:
        print(f"ERROR: {reason}")
        return 1
    if not local_commits(args.root, args.base):
        print("ERROR: no local commit to publish.")
        return 1
    remote = args.remote or "origin"
    remote_url = git_capture(args.root, "remote", "get-url", remote)
    if not remote_url:
        print(f"ERROR: remote not found: {remote}")
        return 1
    run(args.root, ["uv", "run", "python", "scripts/checkpoint.py"])
    push = run(args.root, ["git", "push", "-u", remote, branch])
    if push.returncode != 0:
        print(push.stderr.strip())
        return push.returncode
    prepare = load_yaml(args.root / PREPARE_FILE)
    view = run(args.root, ["gh", "pr", "view", branch, "--json", "number,url"])
    if view.returncode == 0:
        gh_args = [
            "gh",
            "pr",
            "edit",
            branch,
            "--title",
            prepare["title"],
            "--body-file",
            PR_BODY_FILE,
        ]
    else:
        gh_args = [
            "gh",
            "pr",
            "create",
            "--base",
            args.base,
            "--head",
            branch,
            "--title",
            prepare["title"],
            "--body-file",
            PR_BODY_FILE,
        ]
    pr = run(args.root, gh_args)
    if pr.returncode != 0:
        print(pr.stderr.strip())
        return pr.returncode
    output = pr.stdout.strip()
    print(output)
    pr_view = run(args.root, ["gh", "pr", "view", branch, "--json", "number,url"])
    pr_data = json.loads(pr_view.stdout) if pr_view.returncode == 0 and pr_view.stdout else {}
    state_path = args.root / ".project/state.yml"
    state = load_yaml(state_path)
    state["delivery"] = {
        "branch": branch,
        "base": args.base,
        "remote": remote,
        "pr_number": pr_data.get("number"),
        "pr_url": pr_data.get("url", output),
        "updated_at": utc_now(),
    }
    write_yaml_atomic(state_path, state)
    return 0


def command_merge(args: argparse.Namespace) -> int:
    if not args.auto:
        print("ERROR: merge requires --auto.")
        return 1
    if not require_remote_authorization(args):
        return 1
    workflow = args.root / ".github/workflows/quality.yml"
    if not workflow.exists():
        print("ERROR: CI workflow is missing.")
        return 1
    branch = git_branch(args.root)
    if branch_is_main(branch):
        print("ERROR: merge requires a pull request branch.")
        return 1
    run(args.root, ["uv", "run", "python", "scripts/checkpoint.py"])
    pr = run(args.root, ["gh", "pr", "view", branch, "--json", "title,number"])
    if pr.returncode != 0:
        print("ERROR: PR is missing.")
        return 1
    title = json.loads(pr.stdout)["title"]
    merge = run(
        args.root,
        ["gh", "pr", "merge", branch, "--auto", "--squash", "--delete-branch", "--subject", title],
    )
    if merge.returncode != 0:
        print(merge.stderr.strip())
        return merge.returncode
    print(merge.stdout.strip())
    return 0


def command_status(args: argparse.Namespace) -> int:
    fresh, reason = prepare_is_fresh(args.root)
    print(f"branch: {git_branch(args.root)}")
    print(f"head: {git_head(args.root)}")
    print(f"dirty_paths: {len(git_status(args.root))}")
    print(f"prepare: {reason}")
    if (args.root / PREPARE_FILE).exists():
        prepare = load_yaml(args.root / PREPARE_FILE)
        print(f"reviewer: {prepare.get('review', 'unknown')}")
        print(f"convergence: {prepare.get('convergence', 'unknown')}")
    else:
        print("reviewer: not prepared")
        print("convergence: not prepared")
    state = load_yaml(args.root / ".project/state.yml")
    delivery = state.get("delivery", {})
    print(f"pr: {delivery.get('pr_url', 'not recorded')}")
    print("ci: not queried")
    print(f"local_commits: {len(local_commits(args.root, args.base))}")
    print("remote: not queried")
    print("next: run prepare, commit, publish or merge according to the current gate")
    return 0


def command_validate_ci(args: argparse.Namespace) -> int:
    failed = False
    if args.branch and args.branch not in MAIN_BRANCHES and not validate_branch_name(args.branch):
        print(f"ERROR: invalid branch name: {args.branch}")
        failed = True
    if args.pr_title and not validate_pr_title(args.pr_title):
        print(f"ERROR: invalid PR title: {args.pr_title}")
        failed = True
    return 1 if failed else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safe Git delivery pipeline.")
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start")
    start.add_argument("--type", required=True)
    start.add_argument("--number", required=True)
    start.add_argument("--slug", required=True)
    start.add_argument("--allow-dirty", action="store_true")

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--title")

    commit = subparsers.add_parser("commit")
    commit.add_argument("--message")

    publish = subparsers.add_parser("publish")
    publish.add_argument("--yes-remote", action="store_true")
    publish.add_argument("--remote", default="origin")
    publish.add_argument("--base", default="main")

    merge = subparsers.add_parser("merge")
    merge.add_argument("--auto", action="store_true")
    merge.add_argument("--yes-remote", action="store_true")

    status = subparsers.add_parser("status")
    status.add_argument("--base", default="main")

    validate_ci = subparsers.add_parser("validate-ci")
    validate_ci.add_argument("--branch")
    validate_ci.add_argument("--pr-title")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    commands = {
        "start": command_start,
        "prepare": command_prepare,
        "commit": command_commit,
        "publish": command_publish,
        "merge": command_merge,
        "status": command_status,
        "validate-ci": command_validate_ci,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
