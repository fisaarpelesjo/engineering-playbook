from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "ENGINEERING.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "REVIEW.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "MIGRATIONS.md",
    "SECURITY.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "pyproject.toml",
    "uv.lock",
    ".pre-commit-config.yaml",
    ".gitignore",
    ".github/copilot-instructions.md",
    ".github/pull_request_template.md",
    ".github/ISSUE_TEMPLATE/feature.yml",
    ".github/ISSUE_TEMPLATE/bug.yml",
    ".github/workflows/quality.yml",
    ".cursor/rules/engineering.mdc",
    ".devin/rules/engineering.md",
    "docs/agents/AGENT_POLICY.md",
    "docs/agents/HANDOFF_PROTOCOL.md",
    "docs/agents/RECOVERY_PROTOCOL.md",
    "docs/context/product.md",
    "docs/context/architecture.md",
    "docs/context/terminology.md",
    "docs/context/constraints.md",
    "docs/decisions/0000-use-madr.md",
    ".project/project.yml",
    ".project/state.yml",
    ".project/schemas/project.schema.json",
    ".project/schemas/state.schema.json",
    ".project/schemas/workstream.schema.json",
    ".project/schemas/checkpoint.schema.json",
    ".project/schemas/benchmark.schema.json",
    "profiles/workflows/lite.yml",
    "profiles/workflows/standard.yml",
    "profiles/workflows/strict.yml",
    "profiles/stacks/README.md",
    "templates/benchmark/benchmark.yml",
    "templates/madr/template.md",
    "templates/project/README.md",
    "scripts/bootstrap.py",
    "scripts/verify.py",
    "scripts/doctor.py",
    "scripts/checkpoint.py",
    "scripts/resume.py",
    "scripts/reconcile.py",
    "scripts/migrate.py",
    "specs/001-engineering-playbook/spec.md",
    "specs/001-engineering-playbook/plan.md",
    "specs/001-engineering-playbook/tasks.md",
]

REQUIRED_STACKS = [
    "python",
    "cpp",
    "cuda",
    "rust",
    "go",
    "typescript",
    "java",
    "dotnet",
    "kotlin",
    "swift",
    "r",
    "julia",
    "sql",
]

VALID_TRANSITIONS = {
    "proposed": {"clarified", "planned", "abandoned", "blocked"},
    "clarified": {"planned", "blocked", "abandoned"},
    "planned": {"ready", "in_progress", "blocked", "abandoned"},
    "ready": {"in_progress", "blocked", "abandoned"},
    "in_progress": {"review", "changes_requested", "verified", "blocked", "paused"},
    "review": {"changes_requested", "verified", "blocked"},
    "changes_requested": {"in_progress", "blocked", "abandoned"},
    "verified": {"converged", "changes_requested"},
    "converged": {"done", "archived"},
    "done": {"archived"},
    "archived": set(),
    "blocked": {"in_progress", "abandoned", "superseded"},
    "paused": {"in_progress", "abandoned"},
    "abandoned": set(),
    "superseded": set(),
}


@dataclass
class CheckResult:
    errors: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors

    def add(self, condition: bool, message: str) -> None:
        if not condition:
            self.errors.append(message)


def parse_args(description: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--format", choices=["human", "markdown", "json"], default="human")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def write_yaml_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(data, handle, allow_unicode=False, sort_keys=False)
    os.replace(tmp, path)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_schema(root: Path, data_path: str, schema_path: str) -> list[str]:
    data = load_yaml(root / data_path)
    schema = load_json(root / schema_path)
    validator = Draft202012Validator(schema)
    return [
        f"{data_path}: {error.message}" for error in sorted(validator.iter_errors(data), key=str)
    ]


def git_capture(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def git_branch(root: Path) -> str:
    return git_capture(root, "branch", "--show-current") or "unknown"


def git_head(root: Path) -> str:
    return git_capture(root, "rev-parse", "--verify", "HEAD") or "unborn"


def git_status(root: Path) -> list[str]:
    output = git_capture(root, "status", "--short")
    return [line for line in output.splitlines() if line.strip()]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def next_checkpoint_id(root: Path) -> str:
    today = datetime.now(UTC).strftime("%Y%m%d")
    checkpoint_dir = root / ".project" / "checkpoints"
    existing = sorted(checkpoint_dir.glob(f"CP-{today}-*.yml"))
    return f"CP-{today}-{len(existing) + 1:03d}"


def validate_transition(old: str, new: str) -> bool:
    return new in VALID_TRANSITIONS.get(old, set())


def find_ids(text: str, prefix: str) -> list[str]:
    return re.findall(rf"\b{prefix}-[0-9]{{3,4}}\b", text)


def validate_conventional_title(title: str) -> bool:
    return bool(
        re.match(
            r"^(feat|fix|perf|refactor|test|docs|build|ci|chore|revert)"
            r"(\([a-z0-9-]+\))?: [a-z].{0,68}[^.]$",
            title,
        )
    )


def collect_markdown(root: Path) -> str:
    parts: list[str] = []
    for path in root.rglob("*.md"):
        if ".git" not in path.parts and ".venv" not in path.parts:
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def verify_root(root: Path) -> CheckResult:
    result = CheckResult(errors=[], warnings=[])
    for rel in REQUIRED_FILES:
        result.add((root / rel).is_file(), f"Missing required file: {rel}")
    for stack in REQUIRED_STACKS:
        result.add(
            (root / "profiles" / "stacks" / f"{stack}.yml").is_file(),
            f"Missing stack profile: {stack}",
        )

    schema_pairs = [
        (".project/project.yml", ".project/schemas/project.schema.json"),
        (".project/state.yml", ".project/schemas/state.schema.json"),
        (
            ".project/workstreams/WS-001-engineering-playbook.yml",
            ".project/schemas/workstream.schema.json",
        ),
        ("templates/benchmark/benchmark.yml", ".project/schemas/benchmark.schema.json"),
    ]
    for data_path, schema_path in schema_pairs:
        if (root / data_path).exists() and (root / schema_path).exists():
            result.errors.extend(validate_schema(root, data_path, schema_path))
    for checkpoint in sorted((root / ".project" / "checkpoints").glob("CP-*.yml")):
        result.errors.extend(
            validate_schema(
                root,
                str(checkpoint.relative_to(root)),
                ".project/schemas/checkpoint.schema.json",
            )
        )

    state_path = root / ".project/state.yml"
    if state_path.exists():
        state = load_yaml(state_path)
        for key in ["active_specification", "active_plan", "active_tasks"]:
            rel = state.get(key)
            result.add(
                bool(rel) and (root / rel).is_file(), f"State reference missing: {key}={rel}"
            )
        if state.get("status") in {"blocked", "abandoned", "superseded"}:
            result.add(
                bool(state.get("blockers")),
                f"Status {state.get('status')} requires a blocker/reason",
            )
        if state.get("status") in {"verified", "converged", "done"}:
            result.add(
                state.get("last_verified_commit") == git_head(root),
                "Verified/converged state requires last_verified_commit to match HEAD",
            )

    project = (
        load_yaml(root / ".project/project.yml") if (root / ".project/project.yml").exists() else {}
    )
    spec_kit = project.get("spec_kit", {})
    result.add(spec_kit.get("version") == "v1.0.4", "Spec Kit version must be pinned to v1.0.4")

    text = collect_markdown(root)
    for prefix in ["FR", "AC", "T"]:
        ids = find_ids(text, prefix)
        duplicates = sorted({item for item in ids if ids.count(item) > 1 and prefix == "T"})
        result.add(not duplicates, f"Duplicate task IDs found: {', '.join(duplicates)}")

    cursor_rule = root / ".cursor/rules/engineering.mdc"
    if cursor_rule.exists():
        content = cursor_rule.read_text(encoding="utf-8")
        result.add("alwaysApply: true" in content, "Cursor rule must set alwaysApply: true")

    for script in ["doctor.py", "resume.py", "reconcile.py"]:
        path = root / "scripts" / script
        if path.exists():
            content = path.read_text(encoding="utf-8")
            if script == "reconcile.py":
                result.add("--apply" in content, "reconcile.py must require --apply for writes")
            else:
                result.add("write_yaml_atomic" not in content, f"{script} must be read-only")

    workstreams = []
    for path in (root / ".project/workstreams").glob("*.yml"):
        workstreams.append(load_yaml(path))
    owners: dict[str, str] = {}
    for ws in workstreams:
        for owned in ws.get("owned_paths", []):
            if owned == ".":
                continue
            result.add(owned not in owners, f"Overlapping workstream ownership: {owned}")
            owners[owned] = ws["id"]

    return result


def print_result(result: CheckResult) -> int:
    for warning in result.warnings:
        print(f"WARN: {warning}")
    for error in result.errors:
        print(f"ERROR: {error}")
    if result.ok:
        print("OK")
        return 0
    return 1
