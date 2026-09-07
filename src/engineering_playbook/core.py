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

ROOT = Path.cwd()

BASE_REQUIRED_FILES = [
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
    ".project/schemas/playbook-lock.schema.json",
    "profiles/workflows/lite.yml",
    "profiles/workflows/standard.yml",
    "profiles/workflows/strict.yml",
    "profiles/stacks/README.md",
    "templates/benchmark/benchmark.yml",
    "templates/madr/template.md",
    "templates/project/requirements.md",
    "templates/project/README.md",
    "docs/requirements/README.md",
    "docs/delivery/README.md",
    "docs/delivery/github-ruleset.md",
    ".github/rulesets/main.yml",
    "scripts/bootstrap.py",
    "scripts/delivery.py",
    "scripts/verify.py",
    "scripts/doctor.py",
    "scripts/checkpoint.py",
    "scripts/resume.py",
    "scripts/reconcile.py",
    "scripts/migrate.py",
]

SOURCE_ONLY_REQUIRED_FILES = [
    ".project/distribution.yml",
    "specs/001-engineering-playbook/spec.md",
    "specs/001-engineering-playbook/plan.md",
    "specs/001-engineering-playbook/tasks.md",
    "src/engineering_playbook/__init__.py",
    "src/engineering_playbook/cli.py",
    "src/engineering_playbook/commands.py",
    "src/engineering_playbook/core.py",
    "src/engineering_playbook/delivery.py",
    "src/engineering_playbook/installer.py",
    "src/engineering_playbook/resources/__init__.py",
    "src/engineering_playbook/resources/.project/distribution.yml",
    "src/engineering_playbook/resources/templates/project/requirements.md",
]

REQUIRED_FILES = [*BASE_REQUIRED_FILES, *SOURCE_ONLY_REQUIRED_FILES]

REQUIRED_PRD_SECTIONS = [
    "Instrucoes de uso",
    "Metadados e controle do documento",
    "Historico de alteracoes",
    "Aprovacoes",
    "Resumo executivo",
    "Problema ou oportunidade",
    "Evidencias do problema",
    "Visao do produto",
    "Proposta de valor",
    "Objetivos",
    "Metricas e criterios de sucesso",
    "Nao objetivos",
    "Itens fora de escopo",
    "Stakeholders",
    "Usuarios e personas",
    "Necessidades dos stakeholders",
    "Responsabilidades e ownership",
    "Contexto e situacao atual",
    "Sistemas e processos relacionados",
    "Escopo e fronteiras do produto",
    "Diagrama de contexto",
    "Glossario e linguagem do dominio",
    "Premissas",
    "Dependencias",
    "Restricoes",
    "Jornadas dos usuarios",
    "Casos de uso e cenarios",
    "Fluxos principais",
    "Fluxos alternativos",
    "Fluxos de erro e recuperacao",
    "Regras de negocio",
    "Requisitos funcionais",
    "Requisitos nao funcionais",
    "Modelo e requisitos de dados",
    "Interfaces e integracoes",
    "APIs, eventos e contratos externos",
    "Seguranca",
    "Privacidade",
    "Autorizacao e controle de acesso",
    "Auditoria e rastreabilidade",
    "Conformidade legal e regulatoria",
    "Acessibilidade",
    "Observabilidade",
    "Operacao e suporte",
    "Backup, recuperacao e continuidade",
    "Migracao e compatibilidade",
    "Ambientes e implantacao",
    "Restricoes tecnologicas justificadas",
    "Criterios globais de aceitacao",
    "Estrategia de verificacao e validacao",
    "Riscos e mitigacoes",
    "Alternativas consideradas",
    "Decisoes que exigem ADR",
    "Releases e marcos",
    "Matriz de rastreabilidade",
    "Questoes abertas",
    "Decisoes pendentes",
    "Waiting room ou requisitos futuros",
    "Referencias e anexos",
]

PRD_ALLOWED_STATUSES = {"draft", "in_review", "approved", "superseded"}
REQUIREMENT_TYPES = {"FR", "NFR", "BR", "CON", "SC"}
REQUIREMENT_STATUSES = {
    "proposed",
    "accepted",
    "implemented",
    "verified",
    "rejected",
    "deprecated",
}
REQUIREMENT_PRIORITIES = {"must", "should", "could", "wont"}
VERIFICATION_METHODS = {"inspection", "analysis", "demonstration", "test"}

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

DERIVED_ADAPTER_FILES = {
    "codex": {"AGENTS.md"},
    "claude-code": {"CLAUDE.md"},
    "gemini-cli": {"GEMINI.md"},
    "github-copilot": {".github/copilot-instructions.md"},
    "cursor": {".cursor/rules/engineering.mdc"},
    "windsurf": {".devin/rules/engineering.md"},
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


def git_parent(root: Path) -> str:
    return git_capture(root, "rev-parse", "--verify", "HEAD^") or "unborn"


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


def extract_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    metadata = yaml.safe_load(text[4:end]) or {}
    return metadata, text[end + 5 :]


def markdown_headings(text: str, level: int = 2) -> list[str]:
    prefix = "#" * level
    headings: list[str] = []
    for line in text.splitlines():
        if line.startswith(f"{prefix} ") and not line.startswith(f"{prefix}#"):
            headings.append(line.removeprefix(f"{prefix} ").strip())
    return headings


def extract_requirement_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    pattern = re.compile(r"```yaml\n(.*?)\n```", re.DOTALL)
    for match in pattern.finditer(text):
        block_text = match.group(1)
        if "acceptance_criteria:" not in block_text or "verification_method:" not in block_text:
            continue
        loaded = yaml.safe_load(block_text)
        if isinstance(loaded, dict) and "id" in loaded and "type" in loaded:
            blocks.append(loaded)
    return blocks


def validate_local_markdown_links(root: Path) -> list[str]:
    errors: list[str] = []
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in root.rglob("*.md"):
        if ".git" in path.parts or ".venv" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            target = match.group(1).split("#", 1)[0].strip()
            if not target or re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            target_path = (path.parent / target).resolve()
            try:
                target_path.relative_to(root.resolve())
            except ValueError:
                errors.append(f"{path.relative_to(root)}: link escapes repository: {target}")
                continue
            if not target_path.exists():
                errors.append(f"{path.relative_to(root)}: broken local link: {target}")
    return errors


def is_discardable_path(path: Path) -> bool:
    parts = set(path.parts)
    return (
        bool({".venv", ".pytest_cache", ".ruff_cache", ".pyright", "__pycache__"} & parts)
        or path.suffix == ".pyc"
    )


def validate_prd_document(path: Path, *, template: bool = False) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    metadata, body = extract_front_matter(text)
    required_metadata = [
        "document_id",
        "title",
        "version",
        "status",
        "owners",
        "reviewers",
        "approvers",
        "created_at",
        "updated_at",
        "approval_date",
        "supersedes",
        "related_specs",
    ]
    for field in required_metadata:
        if field not in metadata:
            errors.append(f"{path}: missing PRD metadata field: {field}")
    status = metadata.get("status")
    if status and status not in PRD_ALLOWED_STATUSES:
        errors.append(f"{path}: invalid PRD status: {status}")
    if status == "approved":
        if not metadata.get("approvers"):
            errors.append(f"{path}: approved PRD requires at least one approver")
        if not metadata.get("approval_date"):
            errors.append(f"{path}: approved PRD requires approval_date")
        if re.search(r"\b(TODO|ASSUMPTION|QUESTION)\b", body):
            errors.append(f"{path}: approved PRD contains unresolved placeholder markers")

    headings = markdown_headings(body)
    for section in REQUIRED_PRD_SECTIONS:
        count = headings.count(section)
        if count != 1:
            errors.append(f"{path}: PRD section must appear exactly once: {section} ({count})")

    blocks = extract_requirement_blocks(text)
    seen_ids: set[str] = set()
    for block in blocks:
        requirement_id = str(block.get("id", ""))
        requirement_type = str(block.get("type", ""))
        if requirement_id in seen_ids:
            errors.append(f"{path}: duplicate requirement id: {requirement_id}")
        seen_ids.add(requirement_id)
        if requirement_type not in REQUIREMENT_TYPES:
            errors.append(
                f"{path}: invalid requirement type for {requirement_id}: {requirement_type}"
            )
        elif not re.match(rf"^{requirement_type}-[0-9]{{3}}$", requirement_id):
            errors.append(f"{path}: invalid requirement id format: {requirement_id}")
        required_fields = [
            "id",
            "title",
            "type",
            "statement",
            "rationale",
            "source",
            "priority",
            "status",
            "acceptance_criteria",
            "verification_method",
            "dependencies",
            "conflicts",
            "related_items",
        ]
        for field in required_fields:
            if field not in block:
                errors.append(f"{path}: requirement {requirement_id} missing field: {field}")
        if block.get("priority") not in REQUIREMENT_PRIORITIES:
            errors.append(f"{path}: invalid priority for {requirement_id}")
        if block.get("status") not in REQUIREMENT_STATUSES:
            errors.append(f"{path}: invalid requirement status for {requirement_id}")
        if block.get("verification_method") not in VERIFICATION_METHODS:
            errors.append(f"{path}: invalid verification method for {requirement_id}")
        criteria = block.get("acceptance_criteria")
        if not criteria:
            errors.append(f"{path}: requirement {requirement_id} has no acceptance criteria")
        elif isinstance(criteria, list):
            for criterion in criteria:
                if not isinstance(criterion, dict):
                    errors.append(f"{path}: requirement {requirement_id} has invalid criterion")
                    continue
                criterion_id = str(criterion.get("id", ""))
                if not re.match(r"^AC-[0-9]{3}$", criterion_id):
                    errors.append(
                        f"{path}: requirement {requirement_id} has invalid criterion id: "
                        f"{criterion_id}"
                    )
                method = criterion.get("verification_method")
                if method not in VERIFICATION_METHODS:
                    errors.append(
                        f"{path}: requirement {requirement_id} has invalid criterion "
                        f"verification method: {method}"
                    )
        if block.get("status") in {"accepted", "implemented", "verified"}:
            unresolved = " ".join(str(value) for value in block.values())
            if re.search(r"\b(TODO|QUESTION)\b|<[^>]+>", unresolved):
                errors.append(f"{path}: accepted requirement {requirement_id} contains placeholder")

    if not template and not blocks:
        errors.append(f"{path}: PRD document must include at least one requirement block")
    return errors


def _function_source(text: str, name: str) -> str:
    match = re.search(rf"\ndef {re.escape(name)}\(.*?(?=\ndef |\Z)", text, re.DOTALL)
    return match.group(0) if match else ""


def collect_markdown(root: Path) -> str:
    parts: list[str] = []
    for path in root.rglob("*.md"):
        if ".git" not in path.parts and ".venv" not in path.parts:
            parts.append(path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def verify_root(root: Path) -> CheckResult:
    result = CheckResult(errors=[], warnings=[])
    source_repository = (root / ".project/distribution.yml").exists()
    required_files = REQUIRED_FILES if source_repository else BASE_REQUIRED_FILES
    if not source_repository:
        lock_path = root / ".project/playbook.lock.yml"
        if lock_path.exists():
            lock = load_yaml(lock_path)
            selected_agents = set(lock.get("playbook", {}).get("agents", []))
            ci = lock.get("playbook", {}).get("ci", "github")
            optional: set[str] = set()
            for agent, paths in DERIVED_ADAPTER_FILES.items():
                if agent not in selected_agents:
                    optional.update(paths)
            if ci == "none":
                optional.update(
                    {
                        ".github/workflows/quality.yml",
                        ".github/rulesets/main.yml",
                        ".github/copilot-instructions.md",
                    }
                )
            required_files = [path for path in required_files if path not in optional]
    for rel in required_files:
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
        (".project/playbook.lock.yml", ".project/schemas/playbook-lock.schema.json"),
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

    prd_template = root / "templates/project/requirements.md"
    if prd_template.exists():
        result.errors.extend(validate_prd_document(prd_template, template=True))
    prd_docs = [
        path
        for path in (root / "tests" / "fixtures" / "requirements").glob("*.md")
        if path.name.startswith("valid-")
    ]
    project_prd = root / "docs/requirements/project-requirements.md"
    if project_prd.exists():
        prd_docs.append(project_prd)
    for path in prd_docs:
        result.errors.extend(validate_prd_document(path))
    result.errors.extend(validate_local_markdown_links(root))

    state_path = root / ".project/state.yml"
    if state_path.exists():
        state = load_yaml(state_path)
        for key in ["active_specification", "active_plan", "active_tasks"]:
            rel = state.get(key)
            if rel:
                result.add((root / rel).is_file(), f"State reference missing: {key}={rel}")
        if state.get("status") in {"blocked", "abandoned", "superseded"}:
            result.add(
                bool(state.get("blockers")),
                f"Status {state.get('status')} requires a blocker/reason",
            )
        if state.get("status") in {"verified", "converged", "done"}:
            result.add(
                state.get("last_verified_commit") in {git_head(root), git_parent(root)},
                "Verified/converged state requires last_verified_commit to match HEAD "
                "or its parent commit",
            )

    if not source_repository:
        lock_path = root / ".project/playbook.lock.yml"
        result.add(lock_path.is_file(), "Derived project must include .project/playbook.lock.yml")
        for forbidden in [
            "bootstrap-engineering-template.yml",
            "specs/001-engineering-playbook",
            "tests/unit/test_core.py",
            "tests/fixtures/requirements",
            ".project/distribution.yml",
        ]:
            result.add(
                not (root / forbidden).exists(),
                f"Derived project must not include source-only path: {forbidden}",
            )
        if state_path.exists():
            state_text = state_path.read_text(encoding="utf-8")
            for forbidden_text in [
                "001-engineering-playbook",
                "24e3d92b4c8866732aa6b98bd630f414e4cb93b1",
            ]:
                result.add(
                    forbidden_text not in state_text,
                    f"Derived state leaks source reference: {forbidden_text}",
                )

    project = (
        load_yaml(root / ".project/project.yml") if (root / ".project/project.yml").exists() else {}
    )
    spec_kit = project.get("spec_kit", {})
    result.add(spec_kit.get("version") == "v1.0.4", "Spec Kit version must be pinned to v1.0.4")

    pyproject_path = root / "pyproject.toml"
    if source_repository and pyproject_path.exists():
        pyproject_text = pyproject_path.read_text(encoding="utf-8")
        result.add(
            'engineering-playbook = "engineering_playbook.cli:main"' in pyproject_text,
            "pyproject.toml must expose engineering-playbook entry point",
        )
        result.add(
            "hatchling.build" in pyproject_text,
            "pyproject.toml must define a package build backend",
        )

    distribution_path = root / ".project/distribution.yml"
    if distribution_path.exists():
        distribution = load_yaml(distribution_path)
        excludes = set(distribution.get("exclude", {}).get("paths", []))
        for required in [
            "bootstrap-engineering-template.yml",
            "specs/001-engineering-playbook",
            ".project/checkpoints",
            ".project/state.yml",
            ".project/workstreams",
            "tests",
        ]:
            result.add(
                required in excludes, f"Distribution must exclude source-only path: {required}"
            )

    resources_distribution = root / "src/engineering_playbook/resources/.project/distribution.yml"
    if resources_distribution.exists():
        resources_text = "\n".join(
            str(path.relative_to(root)).replace("\\", "/")
            for path in (root / "src/engineering_playbook/resources").rglob("*")
        )
        for forbidden in [
            "bootstrap-engineering-template.yml",
            "specs/001-engineering-playbook",
            "tests/fixtures",
            ".project/checkpoints/CP-",
        ]:
            result.add(
                forbidden not in resources_text,
                f"Packaged resources must not include source-only artifact: {forbidden}",
            )

    workflow_path = root / ".github/workflows/quality.yml"
    if workflow_path.exists():
        workflow_text = workflow_path.read_text(encoding="utf-8")
        for action_ref in re.findall(r"uses:\s*[^@\s]+@([^\s#]+)", workflow_text):
            result.add(
                bool(re.fullmatch(r"[0-9a-f]{40}", action_ref)),
                f"GitHub Actions must be pinned by full SHA: {action_ref}",
            )
        result.add("delivery-policy:" in workflow_text, "CI must include delivery-policy job")
        result.add("validate-ci --branch" in workflow_text, "CI must validate branch name")
        result.add("validate-ci --pr-title" in workflow_text, "CI must validate PR title")

    ruleset_path = root / ".github/rulesets/main.yml"
    if ruleset_path.exists():
        ruleset_text = ruleset_path.read_text(encoding="utf-8")
        for required in [
            "pull_request",
            "required_status_checks",
            "non_fast_forward",
            "deletion",
            "required_review_thread_resolution: true",
            "allow_auto_merge: true",
            "delete_branch_on_merge: true",
            "- squash",
        ]:
            result.add(required in ruleset_text, f"Ruleset missing required policy: {required}")

    tasks_path = root / "specs/001-engineering-playbook/tasks.md"
    if tasks_path.exists():
        task_ids = re.findall(r"^- (T[0-9]{3}):", tasks_path.read_text(encoding="utf-8"), re.M)
        duplicates = sorted({item for item in task_ids if task_ids.count(item) > 1})
        result.add(not duplicates, f"Duplicate task IDs found: {', '.join(duplicates)}")

    cursor_rule = root / ".cursor/rules/engineering.mdc"
    if cursor_rule.exists():
        content = cursor_rule.read_text(encoding="utf-8")
        result.add("alwaysApply: true" in content, "Cursor rule must set alwaysApply: true")

    commands_path = root / "src/engineering_playbook/commands.py"
    if commands_path.exists():
        commands_text = commands_path.read_text(encoding="utf-8")
        for name in ["command_doctor", "command_resume"]:
            body = _function_source(commands_text, name)
            result.add("write_yaml_atomic" not in body, f"{name} must be read-only")
        reconcile_body = _function_source(commands_text, "command_reconcile")
        result.add(
            "if not apply" in reconcile_body and "write_yaml_atomic" in reconcile_body,
            "reconcile.py must require --apply for writes",
        )

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
