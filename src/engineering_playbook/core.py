from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

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

VALID_TRANSITIONS: dict[str, set[str]] = {
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
    """Validate ``data_path`` against ``schema_path``. Every error names the file AND the field.

    ``error.message`` alone names the field for a missing-required-property violation ("'x' is
    a required property"), but not for a type or enum violation on an existing nested field
    ("12345 is not of type 'string'" says nothing about which field held 12345). ``error.path``
    supplies that -- it is prepended whenever jsonschema populated it.
    """
    data = load_yaml(root / data_path)
    schema = load_json(root / schema_path)
    validator = Draft202012Validator(schema)
    errors: list[str] = []
    # jsonschema's bundled stub (validators.pyi) leaves `instance` untyped on both
    # `iter_errors` overloads, so the member itself is reported partially unknown
    # regardless of how `data` is typed here -- a third-party stub limitation.
    for error in sorted(
        validator.iter_errors(data),  # pyright: ignore[reportUnknownMemberType]
        key=str,
    ):
        field = ".".join(str(part) for part in error.path)
        label = f"{data_path}.{field}" if field else data_path
        errors.append(f"{label}: {error.message}")
    return errors


class GitUnavailableError(RuntimeError):
    """git could not answer: it exited non-zero, or the executable itself could not run.

    A check that cannot run is an error, never a pass. This does NOT cover a ref that simply
    does not exist yet (empty repository, first commit without a parent) -- that is a
    legitimate state, not a failure, and callers distinguish it with `git_ref_exists` before
    ever raising this.
    """


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as failure:  # git off PATH, or not executable
        raise GitUnavailableError(
            f"git {' '.join(args)} nao pode ser executado: {failure}"
        ) from None


def git_capture(root: Path, *args: str) -> str:
    """Run git and return stdout. Raises GitUnavailableError on any non-zero exit.

    There used to be a silent `return ""` here on failure, and callers guarded with
    `... or "fallback"` -- so a git that could not answer (not a repository, index.lock held,
    git off PATH) read the same as a git that answered "nothing". A caller that may
    legitimately be asking about a ref that does not exist yet (unborn HEAD, no parent commit)
    must confirm that with `git_ref_exists` first, not infer it from an empty return value.
    """
    completed = _run_git(root, *args)
    if completed.returncode != 0:
        raise GitUnavailableError(
            f"git {' '.join(args)} saiu com {completed.returncode}: "
            f"{completed.stderr.strip() or 'sem stderr'}"
        )
    return completed.stdout.strip()


def git_ref_exists(root: Path, ref: str) -> bool:
    """True when `ref` resolves. False only for the legitimate "not yet" case.

    `rev-parse --verify --quiet` exits 1, with no stderr, exactly when the ref is absent -- an
    empty repository asked about HEAD, or a first commit asked about HEAD^. Any other non-zero
    exit (not a repository, corrupt object database, a lock held by a concurrent process) is a
    real failure and raises GitUnavailableError instead of being folded into False.
    """
    completed = _run_git(root, "rev-parse", "--verify", "--quiet", ref)
    if completed.returncode == 0:
        return True
    if completed.returncode == 1:
        return False
    raise GitUnavailableError(
        f"git rev-parse --verify --quiet {ref} saiu com {completed.returncode}: "
        f"{completed.stderr.strip() or 'sem stderr'}"
    )


def git_config_get(root: Path, key: str) -> str | None:
    """The value of a git config key, or None when it is simply unset.

    `git config --get` exits 1 with empty stdout exactly when the key does not exist -- a
    legitimate answer, not a failure of git itself, the same distinction `git_ref_exists`
    already draws for refs. Any other non-zero exit (not a repository, unreadable config)
    is a real failure and raises GitUnavailableError instead of being folded into None.
    """
    completed = _run_git(root, "config", "--get", key)
    if completed.returncode == 0:
        return completed.stdout.strip()
    if completed.returncode == 1:
        return None
    raise GitUnavailableError(
        f"git config --get {key} saiu com {completed.returncode}: "
        f"{completed.stderr.strip() or 'sem stderr'}"
    )


def git_branch(root: Path) -> str:
    """The current branch name.

    "unknown" now means exactly one thing: detached HEAD, where `--show-current` answers ""
    with exit 0 -- a real, successful answer. A git that cannot answer at all raises
    GitUnavailableError instead of reaching this fallback.
    """
    return git_capture(root, "branch", "--show-current") or "unknown"


def git_head(root: Path) -> str:
    if not git_ref_exists(root, "HEAD"):
        return "unborn"
    return git_capture(root, "rev-parse", "--verify", "HEAD")


def git_parent(root: Path) -> str:
    if not git_ref_exists(root, "HEAD^"):
        return "unborn"
    return git_capture(root, "rev-parse", "--verify", "HEAD^")


def git_parents(root: Path) -> list[str]:
    """Every parent of HEAD, not only the first.

    A pull request is built on a merge commit whose FIRST parent is the base
    branch and whose second is the branch under review. Reading only `HEAD^`
    there answers about main, so a state verified on the branch reads as
    unverified and the gate goes red for a reason that has nothing to do with
    the work. An unborn HEAD has no parents, which is an answer, not an error.
    """
    if not git_ref_exists(root, "HEAD"):
        return []
    line = git_capture(root, "rev-list", "--parents", "-n", "1", "HEAD")
    return line.split()[1:]


def git_tree(root: Path, ref: str) -> str:
    """The tree object `ref` resolves to -- the part of a commit that is a pure
    function of content. A commit id also encodes parent, author, message and
    timestamp, so a squash merge mints a brand-new id every time even when the
    content it carries is identical to the branch tip that was actually
    verified. The tree does not: `git commit-tree` proves this directly (see
    `tests/unit/test_tree_survives_the_squash.py`).

    Only `ref` itself is checked for existence, mirroring `git_head`: a ref
    that resolves but has no parent (a root commit asked with `HEAD^`) is a
    caller error, not this function's concern.
    """
    if not git_ref_exists(root, ref):
        return "unborn"
    return git_capture(root, "rev-parse", "--verify", f"{ref}^{{tree}}")


def accepted_verified_trees(root: Path) -> set[str]:
    """The trees a recorded verdict may name and still count as covering HEAD right now.

    HEAD's own tree, plus the tree of every parent of HEAD -- see `git_parents`'s docstring for
    why a parent matters (a PR's merge ref) and `git_tree`'s for why a tree, not a commit id,
    is what a squash leaves intact (issue #9/#30).

    THE ONE PLACE this predicate is decided: `verify_root` (the CI-only gate on
    `last_verified_tree`), `command_reconcile` (the staleness finding on the same field) and
    `check_ci_receipt` (the CI receipt's `tree`) all call this instead of comparing trees
    inline. Issue #10 was exactly two readers of the same field computing this differently and
    disagreeing; a second inline copy of this set would only recreate it.
    """
    return {git_tree(root, "HEAD")} | {git_tree(root, parent) for parent in git_parents(root)}


def git_status(root: Path) -> list[str]:
    output = git_capture(root, "status", "--short")
    return [line for line in output.splitlines() if line.strip()]


class GhUnavailableError(RuntimeError):
    """`gh` could not answer: network absent, not authenticated, or missing entirely.

    NFR-002: a control that cannot obtain its measurement returns failure, never a silent
    pass. Every caller of `fetch_applied_ruleset`/`check_ruleset_reconciliation` is required
    to let this propagate into a non-zero exit rather than swallow it into "OK".
    """


def _run_gh(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gh", *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as failure:  # gh off PATH, or not executable
        raise GhUnavailableError(f"gh {' '.join(args)} nao pode ser executado: {failure}") from None


def gh_capture(root: Path, *args: str) -> str:
    """Run `gh` and return stdout. Raises GhUnavailableError on any non-zero exit.

    Mirrors `git_capture`'s contract on purpose: a `gh` that cannot answer (no network, no
    `gh auth login`/`GH_TOKEN`, rate-limited, `gh` off PATH) must never be read as "nothing to
    report" -- that would turn an unmeasured control green, which NFR-002 forbids.
    """
    completed = _run_gh(root, *args)
    if completed.returncode != 0:
        raise GhUnavailableError(
            f"gh {' '.join(args)} saiu com {completed.returncode}: "
            f"{completed.stderr.strip() or 'sem stderr'}"
        )
    return completed.stdout.strip()


def fetch_applied_ruleset(root: Path, *, ruleset_name: str = "protect-main") -> dict[str, Any]:
    """The branch ruleset actually applied on the server, read through `gh api`.

    Two calls, not one: `repos/:owner/:repo/rulesets` lists rulesets by id and name only, and
    the detail (`rules`, `bypass_actors`, `enforcement`) lives at
    `repos/:owner/:repo/rulesets/{id}`. `gh`'s `:owner/:repo` shorthand resolves from the
    repository whose remote `origin` this `root` is checked out from -- no owner/repo is
    hardcoded here.

    Raises GhUnavailableError when the measurement cannot be obtained, or when no ruleset
    named `ruleset_name` exists on the server (an absent ruleset is not "nothing to compare
    against"; FR-001 requires server-side protection to exist at all).
    """
    rulesets = cast(
        list[dict[str, Any]],
        json.loads(gh_capture(root, "api", "repos/:owner/:repo/rulesets")),
    )
    matches = [item for item in rulesets if item.get("name") == ruleset_name]
    if not matches:
        raise GhUnavailableError(
            f"nenhum ruleset '{ruleset_name}' foi encontrado em repos/:owner/:repo/rulesets"
        )
    ruleset_id = matches[0]["id"]
    detail = json.loads(gh_capture(root, "api", f"repos/:owner/:repo/rulesets/{ruleset_id}"))
    return cast(dict[str, Any], detail)


def check_ruleset_reconciliation(
    root: Path, *, ruleset_path: str = ".github/rulesets/main.yml"
) -> CheckResult:
    """Compare the versioned ruleset file against the ruleset applied on the server (FR-002,
    AC-006). T201's control.

    WHERE THIS RUNS, AND WHY, WRITTEN DOWN ON PURPOSE:

    This is deliberately NOT wired into `verify_root`, even though `verify_root` backs both
    `doctor` and `verify`. Those two run locally, frequently, and offline: `resume` and
    `checkpoint` call `verify_root` on every invocation, including on a laptop with no
    network at all. Embedding a `gh api` call there would mean NFR-002's "no measurement is
    failure, never a pass" turns every offline `resume`/`checkpoint`/`doctor` red for a
    reason that has nothing to do with the working tree -- a cost imposed on every offline
    developer, permanently, to catch a divergence that can only be introduced by editing
    files or the server configuration, both already reviewed at pull-request time.

    Instead this runs as a distinct, named CI step (`.github/workflows/quality.yml`, job
    `delivery-policy`, step "Ruleset reconciliation"), which always has network and a
    `GH_TOKEN`. `scripts/verify_ruleset.py` and the `verify-ruleset` CLI subcommand exist so a
    contributor can still run the exact same check locally, on demand, when they do have
    `gh` authenticated -- but nothing calls it for them implicitly.

    Known bypass vectors, written on purpose (FR-009):
      1. Editing the server ruleset directly, without a pull request: the next PR's CI run
         is what surfaces the resulting divergence, not something watching continuously.
      2. Running this outside CI, on a machine without `gh auth`: `GhUnavailableError`
         propagates and `command_verify_ruleset` returns 1 -- NFR-002, never a silent pass.
      3. This compares `rules` (type + parameters) and `bypass_actors`. It does NOT compare
         the `settings:` block in the file (`allow_auto_merge`, `delete_branch_on_merge`):
         those are repository settings, not part of the ruleset object the API returns for
         this endpoint, and comparing them would need a second, different endpoint. That gap
         is declared here rather than silently claimed as covered.
    """
    result = CheckResult(errors=[], warnings=[])
    declared_text = (root / ruleset_path).read_text(encoding="utf-8")
    declared = yaml.safe_load(declared_text)
    applied = fetch_applied_ruleset(root, ruleset_name=str(declared.get("name", "protect-main")))

    result.add(
        applied.get("enforcement") == declared.get("enforcement"),
        f"Ruleset enforcement diverges: file={declared.get('enforcement')!r} "
        f"applied={applied.get('enforcement')!r}",
    )

    declared_rules = {
        cast(str, rule["type"]): rule.get("parameters", {}) for rule in declared.get("rules", [])
    }
    applied_rules = {
        cast(str, rule["type"]): rule.get("parameters", {}) for rule in applied.get("rules", [])
    }
    result.add(
        set(declared_rules) <= set(applied_rules),
        f"Ruleset file declares rule types absent from the applied ruleset: "
        f"{sorted(set(declared_rules) - set(applied_rules))}",
    )
    for rule_type, declared_params in declared_rules.items():
        applied_params = applied_rules.get(rule_type)
        if applied_params is None:
            continue
        # The file states intent; the API answers with intent plus every server
        # default, and that set grows as GitHub adds fields. Measured on the
        # first real run: the API returned `required_reviewers`,
        # `require_extra_approval_for_unattributed_changes` and
        # `do_not_enforce_on_create`, none of which the file declares. Demanding
        # equality would make this control red for a reason nobody here chose.
        #
        # DECLARED LIMIT: only the parameters the file names are compared. A
        # server-side change to a parameter the file stays silent about passes
        # unnoticed. Naming a parameter in the file is what places it under this
        # control.
        compared_applied = {
            key: value for key, value in applied_params.items() if key in declared_params
        }
        result.add(
            declared_params == compared_applied,
            f"Ruleset rule '{rule_type}' parameters diverge: file={declared_params} "
            f"applied={applied_params}",
        )

    declared_bypass = declared.get("bypass_actors", [])
    applied_bypass = applied.get("bypass_actors", [])
    result.add(
        declared_bypass == applied_bypass,
        f"Ruleset bypass_actors diverge: file={declared_bypass} applied={applied_bypass}",
    )
    return result


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def next_checkpoint_id(root: Path) -> str:
    """A checkpoint identifier, unique across working trees without coordination
    between them (FR-003/AC-003).

    WRITTEN: by `commands.command_checkpoint`, immediately before the checkpoint file
    itself is created -- the identifier IS the checkpoint's filename.
    INVALIDATED: never. Once assigned, an identifier names a fact about the past;
    NFR-002 forbids reassigning one already on disk, in either this shape or the
    pre-existing `CP-<date>-<NNN>` one still carried by older commits.

    The previous rule counted `CP-<date>-*.yml` files in THIS working tree only, so two
    branches that had each created zero checkpoints so far, on the same day, produced
    the IDENTICAL id (issue #11) -- an add/add git conflict invisible until a rebase.
    Two alternatives named in the plan were rejected first, and why:
      - the commit the checkpoint rests on: collides exactly in AC-003's own scenario,
        two trees sharing the SAME HEAD (right after `git switch -c`, before either has
        committed anything of its own);
      - wall-clock time: collides at whatever precision two machines' clocks happen to
        agree on, and this function has no way to assume clock skew away.
    A random suffix needs no clock, no commit, and no cross-tree coordination at all --
    that is a UUID4's entire purpose. Readability of the suffix is deliberately not
    optimized: the plan's own criterion is uniqueness over legibility when they
    conflict.
    """
    today = datetime.now(UTC).strftime("%Y%m%d")
    suffix = uuid.uuid4().hex[:8]
    return f"CP-{today}-{suffix}"


CHECKPOINT_PATH_PATTERN = re.compile(r"^\.project/checkpoints/CP-[0-9A-Za-z-]+\.yml$")


def checkpoint_id_collisions(root: Path) -> list[str]:
    """Checkpoint filenames that name DIFFERENT content on another local branch
    (FR-004/AC-004) -- the exact shape an add/add merge conflict takes (issue #11)
    before a rebase or merge ever surfaces it.

    WRITTEN: never -- this is read-only, called from `verify_root` on every `verify`/
    `resume`/`checkpoint`/`doctor` invocation, against local git refs only.
    INVALIDATED: not applicable; there is nothing here to invalidate, only to detect.

    TOLERATES, on purpose (NFR-002): a checkpoint file that exists identically on
    another branch is not a collision -- the historical measurement in spec 004's
    "Evidencia historica" found six identifiers assigned by more than one commit,
    every one byte-identical. It also tolerates the pre-T301 `CP-<date>-<NNN>`
    filename shape without exception: the collision is about DIVERGENT CONTENT under
    the same name, never the name's shape.

    DECLARED LIMIT: only `refs/heads` this clone already knows about are compared. A
    CI checkout (`fetch-depth: 2`, a single ref present) has nothing else to compare
    against and this returns no findings there -- the check's teeth are in a full
    local clone before a push/rebase, which is exactly where issue #11 went unnoticed
    until the conflict itself.
    """
    checkpoints_dir = root / ".project" / "checkpoints"
    if not checkpoints_dir.is_dir():
        return []
    try:
        current_branch = git_branch(root)
        branches = [
            branch
            for branch in git_capture(
                root, "for-each-ref", "--format=%(refname:short)", "refs/heads"
            ).splitlines()
            if branch.strip() and branch.strip() != current_branch
        ]
    except GitUnavailableError:
        return []
    if not branches:
        return []
    findings: list[str] = []
    for checkpoint_file in sorted(checkpoints_dir.glob("CP-*.yml")):
        rel = str(checkpoint_file.relative_to(root)).replace("\\", "/")
        if not CHECKPOINT_PATH_PATTERN.match(rel):
            continue
        local_text = checkpoint_file.read_text(encoding="utf-8")
        for branch in branches:
            completed = _run_git(root, "show", f"{branch}:{rel}")
            if completed.returncode != 0:
                continue  # absent on that branch, or branch unreadable: not a signal
            if completed.stdout.rstrip("\n") != local_text.rstrip("\n"):
                findings.append(f"{rel} diverges between the working tree and branch {branch!r}")
    return findings


def validate_transition(old: str, new: str) -> bool:
    return new in VALID_TRANSITIONS.get(old, set[str]())


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
    metadata: dict[str, Any] = yaml.safe_load(text[4:end]) or {}
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
            # Boundary conversion: a YAML block confirmed to be a mapping with the
            # two keys every requirement block must carry.
            blocks.append(cast(dict[str, Any], loaded))
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
            for raw_criterion in cast(list[Any], criteria):
                if not isinstance(raw_criterion, dict):
                    errors.append(f"{path}: requirement {requirement_id} has invalid criterion")
                    continue
                criterion = cast(dict[str, Any], raw_criterion)
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
    # A derived project declaring `ci: none` has no Actions workflow, therefore no workflow
    # identity and nothing that could attest a tree. Owner decision (issue #30): those
    # projects keep the pre-existing commit/ancestry mechanism below rather than the
    # tree-based one, so this flag is read again further down, at the state gate.
    derived_ci_none = False
    if not source_repository:
        lock_path = root / ".project/playbook.lock.yml"
        if lock_path.exists():
            lock = load_yaml(lock_path)
            selected_agents = set(lock.get("playbook", {}).get("agents", []))
            ci = lock.get("playbook", {}).get("ci", "github")
            derived_ci_none = ci == "none"
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
        ("templates/benchmark/benchmark.yml", ".project/schemas/benchmark.schema.json"),
        (".project/playbook.lock.yml", ".project/schemas/playbook-lock.schema.json"),
    ]
    for data_path, schema_path in schema_pairs:
        if (root / data_path).exists() and (root / schema_path).exists():
            result.errors.extend(validate_schema(root, data_path, schema_path))
    workstream_schema = root / ".project/schemas/workstream.schema.json"
    if workstream_schema.exists():
        # Every workstream file, not just the one this repository happens to have today --
        # a second workstream must be validated too, not silently skipped.
        for workstream_file in sorted((root / ".project/workstreams").glob("WS-*.yml")):
            result.errors.extend(
                validate_schema(
                    root,
                    str(workstream_file.relative_to(root)),
                    ".project/schemas/workstream.schema.json",
                )
            )
    for checkpoint in sorted((root / ".project" / "checkpoints").glob("CP-*.yml")):
        result.errors.extend(
            validate_schema(
                root,
                str(checkpoint.relative_to(root)),
                ".project/schemas/checkpoint.schema.json",
            )
        )
    for collision in checkpoint_id_collisions(root):
        result.errors.append(f"Checkpoint identifier collision: {collision}")

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
            # THE VERDICT: TREE NOW, ATTESTATION LATER (issue #30, spec 003 FR-006/FR-007).
            #
            # `last_verified_commit` cannot survive a squash by construction: no commit can
            # name the SHA that only exists once the squash creates it. Measured on runs
            # 35526666891 and 35527933400: `git merge-base --is-ancestor <recorded>
            # origin/main` answered NAO on main right after a clean squash merge. A commit is
            # `tree + parent + author + message`; only the tree is a pure function of
            # content. With this repository's ruleset requiring
            # `strict_required_status_checks_policy: true` (a branch must be up to date with
            # its base before merging), the squash GitHub creates has a tree identical to the
            # branch tip that was actually verified -- so the tree, not the commit id, is
            # what this gate compares.
            #
            # DECLARED LIMIT, on purpose: this closes the squash-survival mechanic. It does
            # NOT satisfy FR-006. `last_verified_tree` is still written and read by the same
            # actor that delivers the change -- there is no separation between the executor
            # and the emitter of the verdict, and no proof a third party can check without
            # trusting this file. That separation is the next slice, with a signed
            # attestation (`actions/attest` or equivalent) under explicit owner authorization.
            # `last_verified_commit` remains in the schema as an informative field only: it
            # is still written for humans reading `.project/state.yml`, but nothing in this
            # function gates on it any more.
            #
            # DERIVED PROJECTS WITHOUT CI (owner decision, same issue): a project declaring
            # `ci: none` has no Actions workflow, therefore no workflow identity to trust
            # even at this reduced level. Those projects keep the pre-existing
            # commit/ancestry mechanism unchanged below.
            #
            # ONE PREDICATE, THREE READERS (issue #10): `accepted_verified_trees` below is the
            # only place "which trees still count as HEAD" is decided. `command_reconcile`
            # (commands.py) and `check_ci_receipt` (receipt.py, issue #9's CI receipt) call the
            # same function rather than each inlining their own comparison -- two readers of
            # `last_verified_tree` computing this differently is exactly how #10 happened.
            # COVERAGE, stated plainly: this predicate proves the recorded tree is reachable as
            # HEAD or a parent of HEAD RIGHT NOW, on THIS checkout. It does not prove the
            # tree was ever actually built or tested by anyone -- that is what
            # `last_verified_commit`/`last_verified_tree` being written and read by the same
            # actor still does not give FR-006 (declared above), and what the CI receipt's own
            # `tree` field does not give either: a receipt is self-reported by the same run
            # that measured it, not attested by a third party.
            if derived_ci_none:
                try:
                    accepted_commits = {git_head(root), *git_parents(root)}
                except GitUnavailableError as failure:
                    result.errors.append(
                        f"git nao respondeu, portanto last_verified_commit nao foi comparado: "
                        f"{failure}"
                    )
                else:
                    result.add(
                        state.get("last_verified_commit") in accepted_commits,
                        "Verified/converged state requires last_verified_commit to match HEAD "
                        "or one of its parent commits",
                    )
            else:
                try:
                    accepted_trees = accepted_verified_trees(root)
                except GitUnavailableError as failure:
                    result.errors.append(
                        f"git nao respondeu, portanto last_verified_tree nao foi comparado: "
                        f"{failure}"
                    )
                else:
                    result.add(
                        state.get("last_verified_tree") in accepted_trees,
                        "Verified/converged state requires last_verified_tree to match "
                        "HEAD's tree or the tree of one of its parent commits",
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

    project: dict[str, Any] = (
        load_yaml(root / ".project/project.yml") if (root / ".project/project.yml").exists() else {}
    )
    spec_kit: dict[str, Any] = project.get("spec_kit", {})
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

    # FR-003 / AC-002: client hooks are not a control until `core.hooksPath` actually points
    # at them. This only applies to a real git working tree that ships this template's hooks
    # (guarded on both below) -- a directory that is not a git repository at all, or a repo
    # that never received `scripts/git-hooks` (e.g. a bare fixture in a unit test), has
    # nothing to activate and is not a case this check speaks to.
    #
    # Known bypass vectors, written on purpose (FR-009), matching the header of
    # `scripts/git-hooks/pre-commit` itself:
    #   1. `git config core.hooksPath` can be unset or repointed after this check last ran;
    #      nothing here runs continuously, only on the next `doctor`/`verify` invocation.
    #   2. `git commit --no-verify` / `git push --no-verify` skip the hooks even while
    #      `core.hooksPath` is correctly configured; this check cannot see that at all,
    #      because it inspects configuration, not individual invocations.
    #   3. This check runs locally, on the machine that happens to run `doctor`/`verify`;
    #      per FR-012 it has no effect on a clone where nobody ever runs those commands.
    #   4. A continuous integration runner checks out the repository and never configures
    #      client hooks, because it has no commits of its own to guard. Measured on run
    #      35532861087, where this check turned every job red for a condition that is
    #      meaningless there. It is therefore skipped when the environment declares itself
    #      to be CI, and the cost of that skip is stated plainly: a CI run cannot testify
    #      about the hooks on the workstation that produced the commit.
    hooks_dir = root / "scripts" / "git-hooks"
    running_in_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
    if (root / ".git").exists() and hooks_dir.is_dir() and not running_in_ci:
        expected_hooks_path = "scripts/git-hooks"
        normalized = ""
        try:
            configured_hooks_path = git_config_get(root, "core.hooksPath")
        except GitUnavailableError as failure:
            result.errors.append(
                f"git nao respondeu, portanto core.hooksPath nao foi medido: {failure}"
            )
        else:
            normalized = (configured_hooks_path or "").replace("\\", "/").rstrip("/")
            result.add(
                normalized == expected_hooks_path,
                "Client git hooks are not active: core.hooksPath is "
                f"{configured_hooks_path!r}, expected {expected_hooks_path!r}. Run "
                "`engineering-playbook init` or `update`, or "
                f"`git config core.hooksPath {expected_hooks_path}` directly.",
            )

        # FR-004: the raw hook above and the `pre-commit` framework are incompatible by
        # design -- the framework refuses to install once `core.hooksPath` is set
        # (https://github.com/pre-commit/pre-commit/issues/3630). The decision recorded in
        # `docs/decisions/` removed `.pre-commit-config.yaml` in favor of the raw hooks; this
        # guards against silent reintroduction of the file this decision removed, active at
        # the same time as the raw hooks it conflicts with. Known bypass vector: a
        # `.pre-commit-config.yaml` added back while `core.hooksPath` points elsewhere would
        # not be caught here -- it is the *simultaneous* activation this check watches for.
        pre_commit_config_active = normalized == expected_hooks_path
        result.add(
            not ((root / ".pre-commit-config.yaml").exists() and pre_commit_config_active),
            "Two incompatible hook mechanisms are active at once: .pre-commit-config.yaml "
            "exists and core.hooksPath points at scripts/git-hooks. See "
            "docs/decisions/ for the arbitration; the pre-commit framework refuses to "
            "install while core.hooksPath is set, so this state should not occur.",
        )

    for tasks_path in sorted(root.glob("specs/*/tasks.md")):
        task_ids = re.findall(r"^- (T[0-9]{3}):", tasks_path.read_text(encoding="utf-8"), re.M)
        duplicates = sorted({item for item in task_ids if task_ids.count(item) > 1})
        result.add(
            not duplicates,
            f"Duplicate task IDs found in {tasks_path.relative_to(root)}: {', '.join(duplicates)}",
        )

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
        # FR-005/T305: every function that writes an accounting artifact (spec 004's
        # own definition of "Contabilidade": .project/state.yml, .project/checkpoints/,
        # .project/delivery/) declares, next to the write, WHEN in the flow it runs and
        # WHAT invalidates it -- so a reader never has to reconstruct that from the
        # write call alone. DECLARED LIMIT: this only checks the markers are PRESENT,
        # not that the prose next to them stays accurate as the code around it changes.
        checkpoint_body = _function_source(commands_text, "command_checkpoint")
        result.add(
            "WRITTEN:" in checkpoint_body,
            "command_checkpoint must declare WRITTEN: (FR-005)",
        )
        result.add(
            "INVALIDATED:" in checkpoint_body,
            "command_checkpoint must declare INVALIDATED: (FR-005)",
        )

    delivery_path = root / "src/engineering_playbook/delivery.py"
    if delivery_path.exists():
        delivery_text = delivery_path.read_text(encoding="utf-8")
        # Same FR-005/T305 declaration, for the accounting writes that live in
        # delivery.py rather than commands.py.
        for name in ["record_verified_commit", "command_prepare", "command_commit"]:
            body = _function_source(delivery_text, name)
            result.add("WRITTEN:" in body, f"{name} must declare WRITTEN: (FR-005)")
            result.add("INVALIDATED:" in body, f"{name} must declare INVALIDATED: (FR-005)")

    workstreams: list[dict[str, Any]] = []
    for path in (root / ".project/workstreams").glob("*.yml"):
        workstreams.append(load_yaml(path))
    owners: dict[str, str] = {}
    for ws in workstreams:
        # workstream.schema.json fixes owned_paths as an array of strings.
        for owned in cast(list[str], ws.get("owned_paths", [])):
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
