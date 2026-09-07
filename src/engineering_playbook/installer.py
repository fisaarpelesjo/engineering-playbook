from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, cast

from . import __version__
from .core import load_yaml, utc_now, write_yaml_atomic

LOCK_FILE = ".project/playbook.lock.yml"
PROJECT_FILE = ".project/project.yml"
STATE_FILE = ".project/state.yml"
PRD_TEMPLATE = "templates/project/requirements.md"
PRD_TARGET = "docs/requirements/project-requirements.md"
DISTRIBUTION_MANIFEST = ".project/distribution.yml"

PROFILES = {"lite", "standard", "strict"}
CI_OPTIONS = {"github", "none"}
AGENT_ADAPTERS = {
    "codex": {"AGENTS.md"},
    "claude": {"CLAUDE.md"},
    "claude-code": {"CLAUDE.md"},
    "gemini": {"GEMINI.md"},
    "gemini-cli": {"GEMINI.md"},
    "github-copilot": {".github/copilot-instructions.md"},
    "copilot": {".github/copilot-instructions.md"},
    "cursor": {".cursor/rules/engineering.mdc"},
    "windsurf": {".devin/rules/engineering.md"},
}
AGENT_ALIASES = {
    "claude": "claude-code",
    "gemini": "gemini-cli",
    "copilot": "github-copilot",
}
SOURCE_ONLY_MARKERS = [
    "bootstrap-engineering-template.yml",
    "specs/001-engineering-playbook",
    ".project/checkpoints",
    ".project/workstreams",
    "tests",
    ".venv",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
]


@dataclass(frozen=True)
class InstallPlan:
    root: Path
    project_name: str
    profile: str
    stack: str
    agents: list[str]
    ci: str
    managed: list[str]
    customizable: list[str]
    project_owned: list[str]
    create_dirs: list[str]
    conflicts: list[str]
    actions: list[str]


def resource_root() -> Path:
    return cast(Path, resources.files("engineering_playbook.resources"))


def read_resource_text(rel_path: str) -> str:
    return (resource_root() / rel_path).read_text(encoding="utf-8")


def read_resource_bytes(rel_path: str) -> bytes:
    return (resource_root() / rel_path).read_bytes()


def resource_exists(rel_path: str) -> bool:
    return (resource_root() / rel_path).is_file()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def normalize_rel(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    if not normalized or normalized.startswith("../") or "/../" in normalized:
        raise ValueError(f"unsafe relative path: {path}")
    if Path(normalized).is_absolute():
        raise ValueError(f"absolute paths are not allowed: {path}")
    return normalized


def parse_agents(value: str) -> list[str]:
    agents: list[str] = []
    for raw in value.split(","):
        item = raw.strip()
        if not item:
            continue
        item = AGENT_ALIASES.get(item, item)
        if item not in AGENT_ADAPTERS:
            raise ValueError(f"unsupported agent: {raw.strip()}")
        if item not in agents:
            agents.append(item)
    return agents or ["codex"]


def safe_root(path: Path) -> Path:
    candidate = path.expanduser()
    if candidate.exists() and candidate.is_symlink():
        raise ValueError(f"destination must not be a symlink: {candidate}")
    for parent in [candidate, *candidate.parents]:
        if parent.exists():
            if parent.is_symlink():
                raise ValueError(f"destination parent must not be a symlink: {parent}")
            break
    root = candidate.resolve(strict=False)
    if root.anchor == str(root):
        raise ValueError(f"refusing unsafe destination: {root}")
    return root


def ensure_safe_child(root: Path, rel_path: str) -> Path:
    rel = normalize_rel(rel_path)
    target = (root / rel).resolve(strict=False)
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"path escapes destination: {rel_path}") from exc
    current = root
    for part in Path(rel).parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ValueError(f"refusing to write through symlink: {current}")
    return target


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def iter_resource_files(directory: str) -> list[str]:
    base = resource_root() / directory
    if not base.is_dir():
        return []
    paths: list[str] = []
    for item in base.rglob("*"):
        if item.is_file():
            rel = str(item.relative_to(resource_root())).replace("\\", "/")
            if not is_discardable(rel):
                paths.append(rel)
    return sorted(paths)


def is_discardable(rel_path: str) -> bool:
    parts = set(rel_path.split("/"))
    return bool(
        {".venv", ".pytest_cache", ".ruff_cache", ".pyright", "__pycache__"} & parts
    ) or rel_path.endswith(".pyc")


def should_skip_agent_adapter(rel_path: str, agents: set[str]) -> bool:
    for agent, paths in AGENT_ADAPTERS.items():
        canonical = AGENT_ALIASES.get(agent, agent)
        if rel_path in paths and canonical not in agents:
            return True
    return False


def classify_file(rel_path: str) -> str:
    if rel_path in {PROJECT_FILE, STATE_FILE, PRD_TARGET, "pyproject.toml"}:
        return "project_owned"
    if rel_path.startswith(("docs/context/", "docs/decisions/")):
        return "project_owned"
    if rel_path.startswith((".project/schemas/", "profiles/", "templates/", "scripts/")):
        return "managed"
    if rel_path.startswith(".github/workflows/") or rel_path.startswith(".github/rulesets/"):
        return "managed"
    return "customizable"


def manifest_paths() -> tuple[list[str], list[str]]:
    manifest = load_yaml_from_resource(DISTRIBUTION_MANIFEST)
    excluded = set(manifest.get("exclude", {}).get("paths", []))
    generated = set(manifest.get("generated", {}).values())
    excluded.update(generated)
    paths: list[str] = list(manifest.get("include", {}).get("files", []))
    for directory in manifest.get("include", {}).get("directories", []):
        paths.extend(iter_resource_files(directory))
    allowed = []
    for path in sorted(set(paths)):
        rel = normalize_rel(path)
        if any(rel == item or rel.startswith(f"{item}/") for item in excluded):
            continue
        if is_discardable(rel):
            continue
        allowed.append(rel)
    return allowed, list(manifest.get("empty_directories", []))


def load_yaml_from_resource(rel_path: str) -> Any:
    return load_yaml_text(read_resource_text(rel_path))


def load_yaml_text(text: str) -> Any:
    import yaml

    return yaml.safe_load(text)


def render_project_yml(
    project_name: str, profile: str, stack: str, agents: list[str]
) -> dict[str, Any]:
    source = load_yaml_from_resource(PROJECT_FILE)
    commands = {
        "init": "engineering-playbook init",
        "verify": "engineering-playbook verify",
        "doctor": "engineering-playbook doctor",
        "checkpoint": "engineering-playbook checkpoint",
        "delivery": "engineering-playbook delivery",
        "resume": "engineering-playbook resume",
        "reconcile_inspect": "engineering-playbook reconcile",
        "reconcile_apply": "engineering-playbook reconcile --apply",
        "update": "engineering-playbook update",
        "tests": "uv run pytest",
    }
    return {
        "schema_version": source["schema_version"],
        "project": {
            "name": project_name,
            "language": source["project"]["language"],
            "default_workflow_profile": profile,
            "stack": stack,
        },
        "spec_kit": source["spec_kit"],
        "commands": commands,
        "sources": source["sources"],
        "supported_agents": agents,
    }


def render_pyproject(project_name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.-]+", "-", project_name).strip("-") or "project"
    return f"""[project]
name = "{normalized}"
version = "0.1.0"
requires-python = ">=3.11"

[tool.pytest.ini_options]
testpaths = ["tests"]
"""


def render_state() -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "updated_at": utc_now(),
        "active_workstream": None,
        "current_branch": "unknown",
        "current_phase": "requirements",
        "status": "proposed",
        "active_specification": None,
        "active_plan": None,
        "active_tasks": None,
        "active_task": None,
        "last_checkpoint": None,
        "last_verified_commit": None,
        "validation": {"passed": [], "failed": [], "not_run": []},
        "blockers": [],
        "next_actions": ["Fill docs/requirements/project-requirements.md."],
    }


def strip_source_prd(text: str) -> str:
    text = re.sub(r"document_id:\s*.*", "document_id: TODO", text, count=1)
    text = re.sub(r"title:\s*.*", "title: Project Requirements Document", text, count=1)
    text = re.sub(r"status:\s*.*", "status: draft", text, count=1)
    text = re.sub(r"related_specs:\s*\[[^\]]*\]", "related_specs: []", text, count=1)
    return text.replace("001-engineering-playbook", "TODO")


def build_plan(
    path: Path,
    *,
    project_name: str | None = None,
    profile: str,
    stack: str,
    agents: list[str],
    ci: str,
) -> InstallPlan:
    if profile not in PROFILES:
        raise ValueError(f"unsupported profile: {profile}")
    if ci not in CI_OPTIONS:
        raise ValueError(f"unsupported ci: {ci}")
    root = safe_root(path)
    all_paths, dirs = manifest_paths()
    selected_agents = set(agents)
    managed: list[str] = []
    customizable: list[str] = []
    project_owned = [PROJECT_FILE, STATE_FILE, PRD_TARGET, "pyproject.toml"]
    conflicts: list[str] = []
    actions: list[str] = []
    existing_install = (root / LOCK_FILE).exists()

    for rel in all_paths:
        if should_skip_agent_adapter(rel, selected_agents):
            continue
        if ci == "none" and rel.startswith(".github/workflows/"):
            continue
        if ci == "none" and rel.startswith(".github/rulesets/"):
            continue
        category = classify_file(rel)
        if category == "managed":
            managed.append(rel)
        elif category == "customizable":
            customizable.append(rel)
        else:
            project_owned.append(rel)
        target = ensure_safe_child(root, rel)
        if target.exists():
            if (
                target.is_file()
                and resource_exists(rel)
                and file_sha256(target) == sha256_bytes(read_resource_bytes(rel))
            ):
                actions.append(f"preserve unchanged {rel}")
            else:
                conflicts.append(rel)
        else:
            actions.append(f"create {rel}")

    for rel in [PROJECT_FILE, STATE_FILE, PRD_TARGET, "pyproject.toml"]:
        target = ensure_safe_child(root, rel)
        if target.exists() and existing_install:
            actions.append(f"preserve project-owned {rel}")
        elif target.exists():
            conflicts.append(rel)
        else:
            actions.append(f"create {rel}")

    for directory in dirs:
        ensure_safe_child(root, directory)
        actions.append(f"ensure directory {directory}")

    return InstallPlan(
        root=root,
        project_name=project_name or root.name,
        profile=profile,
        stack=stack,
        agents=agents,
        ci=ci,
        managed=sorted(set(managed)),
        customizable=sorted(set(customizable)),
        project_owned=sorted(set(project_owned)),
        create_dirs=dirs,
        conflicts=sorted(set(conflicts)),
        actions=actions,
    )


def build_lock(plan: InstallPlan, source: str) -> dict[str, Any]:
    managed_entries = []
    for rel in plan.managed:
        if resource_exists(rel):
            managed_entries.append(
                {"path": rel, "checksum": sha256_bytes(read_resource_bytes(rel))}
            )
    return {
        "schema_version": "1.0.0",
        "playbook": {
            "name": "engineering-playbook",
            "version": __version__,
            "installed_at": utc_now(),
            "source": source,
            "profile": plan.profile,
            "stack": plan.stack,
            "agents": plan.agents,
            "ci": plan.ci,
        },
        "files": {
            "managed": managed_entries,
            "customizable": plan.customizable,
            "project_owned": plan.project_owned,
        },
        "migrations": [],
    }


def apply_init(plan: InstallPlan, *, dry_run: bool, source: str) -> int:
    for action in plan.actions:
        print(action)
    if plan.conflicts:
        for conflict in plan.conflicts:
            print(f"CONFLICT: {conflict}")
        return 1
    if dry_run:
        print("Dry run: no files written.")
        return 0
    plan.root.mkdir(parents=True, exist_ok=True)
    for directory in plan.create_dirs:
        ensure_safe_child(plan.root, directory).mkdir(parents=True, exist_ok=True)
    for rel in [*plan.managed, *plan.customizable]:
        target = ensure_safe_child(plan.root, rel)
        if target.exists():
            continue
        atomic_write_bytes(target, read_resource_bytes(rel))
    for rel in plan.project_owned:
        if rel in {PROJECT_FILE, STATE_FILE, PRD_TARGET, "pyproject.toml"}:
            continue
        target = ensure_safe_child(plan.root, rel)
        if target.exists() or not resource_exists(rel):
            continue
        atomic_write_bytes(target, read_resource_bytes(rel))
    if not ensure_safe_child(plan.root, PROJECT_FILE).exists():
        write_yaml_atomic(
            ensure_safe_child(plan.root, PROJECT_FILE),
            render_project_yml(plan.project_name, plan.profile, plan.stack, plan.agents),
        )
    if not ensure_safe_child(plan.root, STATE_FILE).exists():
        write_yaml_atomic(ensure_safe_child(plan.root, STATE_FILE), render_state())
    pyproject = ensure_safe_child(plan.root, "pyproject.toml")
    if not pyproject.exists():
        atomic_write_text(pyproject, render_pyproject(plan.project_name))
    prd = ensure_safe_child(plan.root, PRD_TARGET)
    if not prd.exists():
        atomic_write_text(prd, strip_source_prd(read_resource_text(PRD_TEMPLATE)))
    lock_path = ensure_safe_child(plan.root, LOCK_FILE)
    if not lock_path.exists():
        write_yaml_atomic(lock_path, build_lock(plan, source))
    print(f"Installed engineering-playbook into {plan.root}")
    return 0


def command_init(args: argparse.Namespace) -> int:
    try:
        agents = parse_agents(args.agents)
        plan = build_plan(
            args.path,
            project_name=getattr(args, "project_name", None),
            profile=args.profile,
            stack=args.stack,
            agents=agents,
            ci=args.ci,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1
    return apply_init(plan, dry_run=args.dry_run, source=args.source)


def command_update(args: argparse.Namespace) -> int:
    try:
        root = safe_root(args.path)
        lock_path = ensure_safe_child(root, LOCK_FILE)
    except ValueError as exc:
        print(f"ERROR: {exc}")
        return 1
    if not lock_path.exists():
        print(f"ERROR: missing installation manifest: {LOCK_FILE}")
        return 1
    lock = load_yaml(lock_path)
    managed = lock.get("files", {}).get("managed", [])
    conflicts: list[str] = []
    updates: list[tuple[str, bytes]] = []
    preserved: list[str] = []
    for entry in managed:
        rel = normalize_rel(entry["path"])
        if not resource_exists(rel):
            preserved.append(rel)
            continue
        target = ensure_safe_child(root, rel)
        if not target.exists():
            updates.append((rel, read_resource_bytes(rel)))
            continue
        current = file_sha256(target)
        installed = entry.get("checksum")
        available = sha256_bytes(read_resource_bytes(rel))
        if current != installed:
            conflicts.append(rel)
        elif current != available:
            updates.append((rel, read_resource_bytes(rel)))
        else:
            preserved.append(rel)
    for rel in preserved:
        print(f"preserve {rel}")
    for rel, _ in updates:
        print(f"update {rel}")
    if conflicts:
        for rel in conflicts:
            print(f"CONFLICT: managed file modified locally: {rel}")
        return 1
    if args.dry_run:
        print("Dry run: no files written.")
        return 0
    for rel, data in updates:
        atomic_write_bytes(ensure_safe_child(root, rel), data)
    if updates:
        lock["playbook"]["version"] = __version__
        lock["playbook"]["installed_at"] = utc_now()
        checksums = {rel: sha256_bytes(data) for rel, data in updates}
        for entry in managed:
            if entry["path"] in checksums:
                entry["checksum"] = checksums[entry["path"]]
        lock.setdefault("migrations", []).append(
            {"id": f"update-{__version__}", "applied_at": utc_now(), "files": sorted(checksums)}
        )
        write_yaml_atomic(lock_path, lock)
    print("Update complete.")
    return 0


def legacy_bootstrap(args: argparse.Namespace) -> int:
    if args.target:
        init_args = argparse.Namespace(
            path=args.target,
            project_name=args.project_name,
            profile=args.profile,
            stack=args.stack,
            agents=args.agents,
            ci=args.ci,
            dry_run=False,
            force=False,
            source="legacy-bootstrap",
        )
        return command_init(init_args)
    target = args.root / PRD_TARGET
    if target.exists():
        print("Bootstrap is already applied. No files overwritten.")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.root / PRD_TEMPLATE, target)
    print(f"Created editable PRD copy: {PRD_TARGET}")
    return 0
