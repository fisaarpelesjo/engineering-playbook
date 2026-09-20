"""Run this repository's own CI, derived from `.github/workflows`, before spending an Actions
minute.

**It reads `.github/workflows` and derives the commands. It does not carry a copy of them.** A
second list of commands maintained by hand is a list that lies the day a workflow changes --
"rodar o CI por lembranca" is exactly the failure mode this module exists to remove.

This intentionally stays far smaller than a per-package CI runner: this repository ships one
workflow file (`quality.yml`), with two jobs and eight `run:` steps between them. There is no
per-package ownership graph to fold paths through here -- `--affected` below answers a much
plainer question than that shape would need.

Every `run:` step is put in exactly one bucket:

* **needs the GitHub runner** -- the command reads a `${{ }}` expression, or a `$GITHUB_*` /
  `$RUNNER_*` environment variable the Actions runner sets before the step starts. Nothing local
  can honestly stand in for `${{ github.event.pull_request.title }}`.
* **builds the environment** -- `uv sync`, `pip install`, `python -m venv`. Skipped on purpose:
  this tool runs against whatever environment the caller already has (the same choice a `uv run`
  from a shell makes), rather than mutating `.venv` as a side effect of asking "is the code OK".
* **code** -- everything else. Executed, its exit code read, never its tail.

Usage:
    python scripts/local_ci.py                 # every workflow in .github/workflows
    python scripts/local_ci.py quality          # by file stem
    python scripts/local_ci.py --list           # what would run, without running
    python scripts/local_ci.py --affected       # only if the diff touches what this workflow reads
    python scripts/local_ci.py --affected --base origin/main

**This is not the merge gate.** The evidence a merge needs is the green run GitHub itself
produces, in a clean environment, by a party other than whoever wrote the change. This tool only
tells the author whether they broke something before paying for that Actions minute.
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict, cast

import yaml

#: A step whose `run:` text needs a construct only the GitHub runner expands: a `${{ }}`
#: expression, or a `$GITHUB_*` / `$RUNNER_*` environment variable the runner sets before the step
#: starts. Checked BEFORE the environment markers below -- a step could match both, and the
#: honest reason is the one that would still stop it if the other were solved.
_RUNNER_MARKER = re.compile(r"\$\{\{|\$GITHUB_[A-Z_]+|\$\{GITHUB_[A-Z_]+|\$RUNNER_[A-Z_]+")

#: A step that installs or builds the environment rather than checking code already there.
#: Skipped: `uv sync --locked` mutates `.venv`, and running it as a side effect of "is the code
#: OK" would make this tool's own execution change the answer to that question.
_ENVIRONMENT_MARKERS = ("uv sync", "pip install", "python -m pip", "python -m venv", "uv venv")

#: A bare `.` argument -- `ruff check .`, `ruff format --check .` -- names the whole repository
#: rather than a path this module could otherwise derive and fold. A code step matching this is
#: treated as reading the entire tree for `--affected` purposes: claiming a narrower scope than
#: "everything" for a command that scans everything would be the false "not affected" that lets a
#: workflow silently not run.
_WHOLE_REPO_ARGUMENT = re.compile(r"(?:^|\s)\.(?:\s|$)")

#: A repo-relative path token: two or more slash-separated segments, so a dotted module name with
#: no slash (`engineering_playbook.cli`) does not qualify.
_PATH_TOKEN = re.compile(r"\b[\w.-]+(?:/[\w.*-]+)+")


@dataclass
class StepResult:
    name: str
    status: str  # "ok" | "failed" | "skipped"
    detail: str = ""


@dataclass
class WorkflowResult:
    name: str
    path: Path
    steps: list[StepResult] = field(default_factory=list[StepResult])

    @property
    def failed(self) -> StepResult | None:
        return next((s for s in self.steps if s.status == "failed"), None)

    @property
    def counts(self) -> tuple[int, int, int]:
        ok = sum(1 for s in self.steps if s.status == "ok")
        skipped = sum(1 for s in self.steps if s.status == "skipped")
        failed = sum(1 for s in self.steps if s.status == "failed")
        return ok, skipped, failed

    @property
    def verdict(self) -> str:
        """`VERDE` only when every step ran and passed -- a skip makes this a `PARCIAL`, never a
        silent green, because in CI vocabulary green means "everything ran", and this runner
        cannot run the runner-only or environment-building steps.
        """
        _ok, skipped, failed = self.counts
        if failed:
            return "VERMELHO"
        if skipped:
            return "PARCIAL"
        return "VERDE"


def classify(command: str, condition: str = "") -> str | None:
    """Why a step cannot run here, or `None` when it can.

    `condition` is the step's own `if:` guard. Actions lets that field be written either bare
    (`github.event_name == 'pull_request'`) or wrapped (`${{ github.event_name == ... }}`), so it
    is checked against the GitHub *context* prefixes directly rather than only `_RUNNER_MARKER`,
    which looks for the `${{ }}` wrapper. A step gated this way needs the runner just as much as
    one whose `run:` text does, even when the command text itself is clean.
    """
    if _RUNNER_MARKER.search(command):
        return "precisa do runner do GitHub (${{ }} ou $GITHUB_*/$RUNNER_*)"
    if condition and re.search(r"\b(github|steps|runner|needs|inputs)\.", condition):
        return "o 'if:' do passo precisa do contexto do GitHub"
    if any(marker in command for marker in _ENVIRONMENT_MARKERS):
        return "constroi o ambiente"
    return None


#: `defaults.run` (top-level or per-job): only `working-directory` is read here. Functional
#: syntax because the hyphen makes it an illegal class-body identifier.
_RunDefaults = TypedDict("_RunDefaults", {"working-directory": str}, total=False)


class _Defaults(TypedDict, total=False):
    run: _RunDefaults


class _WorkflowJob(TypedDict, total=False):
    defaults: _Defaults
    steps: list[dict[str, Any]]


class _WorkflowDocument(TypedDict, total=False):
    """The slice of a workflow YAML document this module reads at its one untyped boundary
    (`yaml.safe_load`, below). Not the full Actions schema -- only what `load_workflow` reads;
    a step itself keeps the looser `dict[str, Any]` shape its callers (`owned_paths_of`,
    `run_workflow`) already declare and the tests already construct by hand.
    """

    name: str
    defaults: _Defaults
    jobs: dict[str, _WorkflowJob]


def load_workflow(path: Path) -> tuple[str, list[dict[str, Any]], str | None]:
    """Name, every job's steps flattened in order, and the job-level default working directory.

    A step-level `working-directory` still wins over this default, exactly as Actions resolves it
    -- see `run_workflow`.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    # yaml.safe_load's return is untyped (`Any`); the GitHub Actions workflow schema (fixed, not
    # derived here) shapes it from this one boundary conversion onward.
    document = cast(_WorkflowDocument, raw or {})
    name = str(document.get("name") or path.stem)
    top_defaults: _Defaults = document.get("defaults") or {}
    top_run: _RunDefaults = top_defaults.get("run") or {}
    default_directory: str | None = top_run.get("working-directory")
    steps: list[dict[str, Any]] = []
    jobs: dict[str, _WorkflowJob] = document.get("jobs") or {}
    for job in jobs.values():
        job_defaults: _Defaults = job.get("defaults") or {}
        job_run: _RunDefaults = job_defaults.get("run") or {}
        job_default = job_run.get("working-directory")
        if job_default:
            default_directory = str(job_default)
        steps.extend(job.get("steps") or [])
    return name, steps, default_directory


def owned_paths_of(steps: list[dict[str, Any]], default_directory: str | None) -> set[str] | None:
    """Repo-relative paths this workflow's steps read, or `None` when it reads the whole tree.

    `None` (not an empty set) is the "everything" answer -- `quality.yml`'s `ruff check .` names
    no path token at all, and folding that into an empty *owned* set would make
    `workflow_is_affected` read it as "declares nothing", not as "declares everything". Those are
    opposite answers to `--affected`, and the derivation must not blur them.
    """
    texts: list[str] = []
    for step in steps:
        command = step.get("run")
        if not command:
            continue
        text = str(command)
        texts.append(text)
        if _WHOLE_REPO_ARGUMENT.search(text):
            return None
        directory = step.get("working-directory") or default_directory
        if directory:
            texts.append(str(directory))

    owned: set[str] = set()
    for text in texts:
        for match in _PATH_TOKEN.finditer(text):
            token = match.group(0)
            if "${{" in token or token.startswith("$"):
                continue
            segments = token.split("/")
            owned.add("/".join(segments[:2]) if len(segments) > 1 else token)
    return owned


def workflow_is_affected(
    owned: set[str] | None, changed: list[str], workflow_path: Path, root: Path
) -> tuple[bool, str]:
    """Whether the workflow file itself changed, it declares no narrower scope, or a changed path
    falls under one it does declare.
    """
    workflow_rel = workflow_path.relative_to(root).as_posix()
    if workflow_rel in changed:
        return True, f"o proprio workflow mudou: {workflow_rel}"
    if owned is None:
        return True, "um passo le a arvore inteira (ex.: 'ruff check .')"
    if not owned:
        return True, "nenhum caminho proprio foi derivado; correndo por seguranca"
    for prefix in sorted(owned):
        for changed_path in changed:
            if changed_path == prefix or changed_path.startswith(f"{prefix}/"):
                return True, f"{changed_path} esta sob o caminho declarado '{prefix}'"
    return False, "nenhum arquivo mudado cai sob os caminhos que este workflow declara"


def changed_files_since(root: Path, base: str) -> list[str]:
    """What differs from `base`: history since the branch point, plus whatever the working tree
    still carries uncommitted, so a check made before a push sees what that push would carry.
    """
    resolved = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if resolved.returncode != 0:
        raise SystemExit(
            f"base ref nao resolve aqui: {base!r}. Sem uma base fiavel nao ha --affected -- "
            "rode sem a flag para o modo completo."
        )
    merge_base = subprocess.run(
        ["git", "merge-base", base, "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    committed = subprocess.run(
        ["git", "diff", "--name-only", f"{merge_base}..HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    working_tree = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    untracked = [line[3:] for line in status if line.startswith("??")]
    changed = {
        p.strip().replace("\\", "/") for p in (*committed, *working_tree, *untracked) if p.strip()
    }
    return sorted(changed)


def run_workflow(path: Path, root: Path, *, dry_run: bool) -> WorkflowResult:
    name, steps, default_directory = load_workflow(path)
    result = WorkflowResult(name=name, path=path)
    bash = shutil.which("bash")

    for step in steps:
        command = step.get("run")
        if not command:
            continue  # `uses:` -- checkout / setup-uv. This machine already has both.
        label = str(step.get("name") or str(command).strip().splitlines()[0])[:70]
        condition = str(step.get("if") or "")

        if reason := classify(str(command), condition):
            result.steps.append(StepResult(label, "skipped", reason))
            continue

        if dry_run:
            result.steps.append(StepResult(label, "ok", "not executed (--list)"))
            continue

        if not bash:
            result.steps.append(StepResult(label, "failed", "bash nao encontrado no PATH"))
            break

        directory = step.get("working-directory") or default_directory
        cwd = (root / directory) if directory else root
        # Fixed argv; the command text comes from this repo's own workflow file, not user input.
        completed = subprocess.run(
            [bash, "-c", str(command)],
            cwd=cwd,
            env=os.environ,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            result.steps.append(StepResult(label, "ok"))
            continue

        tail = (completed.stdout + completed.stderr).strip().splitlines()
        result.steps.append(StepResult(label, "failed", "\n".join(tail[-20:])))
        break  # CI stops the job at the first failed step; so does this.

    return result


def _measure_git_state(root: Path) -> tuple[str, str]:
    """HEAD and the porcelain dirty listing, read fresh from `root`."""
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=False
    ).stdout.strip()
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "-uall"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    return head, dirty


#: Where a run records what it measured, in the shape of the derived project's own
#: `.project/last-ci-run.yml` (`tools/local-ci/run_local_ci.py` in `intelligence-agent`, measured
#: 2026-09-19). This module's `schema_version`/`kind` fields exist so that once
#: `.project/schemas/ci-receipt.schema.json` and `src/engineering_playbook/receipt.py` exist in
#: this repository, the reader can validate against them without this writer changing shape.
RECEIPT_KIND = "local_ci_receipt"
RECEIPT_SCHEMA_VERSION = 1


def _write_receipt(
    root: Path,
    *,
    red: int,
    partial: int,
    green: int,
    affected: bool,
    dry_run: bool,
    workflows_available: int,
    workflows_requested: int,
    workflows_run: int,
    head_before: str,
    dirty_before: str,
) -> Path:
    head_after, dirty_after = _measure_git_state(root)
    moved = bool(head_before) and head_before != head_after
    dirtiness_flipped = bool(head_before) and bool(dirty_before) != bool(dirty_after)
    changed_during_run = moved or dirtiness_flipped
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    receipt_path = root / ".project" / "last-ci-run.yml"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Escrito por scripts/local_ci.py. NAO editar a mao.",
        "# Diz contra QUE COMMIT esta corrida rodou -- um verde aqui nao vale para outro HEAD.",
        f"schema_version: {RECEIPT_SCHEMA_VERSION}",
        f"kind: {RECEIPT_KIND}",
        f"ran_at: '{stamp}'",
        f"head: '{head_after}'",
        f"head_before_run: '{head_before}'",
        f"tree_was_dirty_before_run: {'true' if dirty_before else 'false'}",
        f"tree_changed_during_run: {'true' if changed_during_run else 'false'}",
        f"tree_was_dirty: {'true' if dirty_after else 'false'}",
        f"dirty_paths: {len(dirty_after.splitlines()) if dirty_after else 0}",
        f"red: {red}",
        f"partial: {partial}",
        f"green: {green}",
        f"affected_mode: {'true' if affected else 'false'}",
        f"dry_run: {'true' if dry_run else 'false'}",
        f"workflows_available: {workflows_available}",
        f"workflows_requested: {workflows_requested}",
        f"workflows_run: {workflows_run}",
    ]
    receipt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return receipt_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("workflows", nargs="*", help="file stems; default is every workflow found")
    parser.add_argument("--list", action="store_true", help="show what would run, without running")
    parser.add_argument(
        "--affected",
        action="store_true",
        help="only run workflows whose declared reach overlaps what changed since --base",
    )
    parser.add_argument("--base", default="origin/main", help="ref --affected diffs against")
    args = parser.parse_args(argv)

    root = args.root.resolve(strict=False)
    workflows_dir = root / ".github" / "workflows"
    available = sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))

    if not available:
        print(f"nenhum workflow em {workflows_dir}", file=sys.stderr)
        return 2

    paths = available
    if args.workflows:
        wanted = set(args.workflows)
        paths = [p for p in paths if p.stem in wanted]
        missing = wanted - {p.stem for p in paths}
        if missing:
            print(f"nao existe: {', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    if not shutil.which("bash") and not args.list:
        print("bash nao encontrado no PATH, e os workflows sao bash. Abortando.", file=sys.stderr)
        return 2

    print(f"lidos de {workflows_dir.relative_to(root)}: {len(paths)} workflow(s)")
    print(f"plataforma: {platform.system()}\n")

    not_affected: list[tuple[str, str]] = []
    if args.affected:
        changed = changed_files_since(root, args.base)
        print(f"--affected: base={args.base}, {len(changed)} arquivo(s) mudado(s):")
        for f in changed:
            print(f"    {f}")
        print()
        selected: list[Path] = []
        for path in paths:
            _name, steps, default_directory = load_workflow(path)
            owned = owned_paths_of(steps, default_directory)
            affected, reason = workflow_is_affected(owned, changed, path, root)
            if affected:
                print(f"[afetado] {path.stem}: {reason}")
                selected.append(path)
            else:
                print(f"[NAO AFETADO] {path.stem}: {reason}")
                not_affected.append((path.stem, reason))
        print()
        paths = selected

    head_before, dirty_before = ("", "") if args.list else _measure_git_state(root)

    results: list[WorkflowResult] = []
    red = 0
    partial = 0
    for path in paths:
        r = run_workflow(path, root, dry_run=args.list)
        results.append(r)

        if not args.list:
            head_now, dirty_now = _measure_git_state(root)
            if (head_now, dirty_now) != (head_before, dirty_before):
                print()
                print(
                    "ABORTADO: a arvore mudou a meio da corrida, entao ela nao mede nenhum "
                    "estado que exista. Nenhum recibo foi escrito."
                )
                if head_now != head_before:
                    print(f"  HEAD: {head_before[:12]} -> {head_now[:12]}")
                print(f"Correu ate: {r.name}. Rode de novo com a arvore parada.")
                return 1

        ok, skipped, failed = r.counts
        verdict = r.verdict
        red += int(verdict == "VERMELHO")
        partial += int(verdict == "PARCIAL")
        suffix = f" -- {skipped} passo(s) NAO rodaram aqui" if skipped else ""
        print(f"[{verdict}{suffix}] {r.name}: {ok} ok, {skipped} pulados, {failed} falhos")
        for step in r.steps:
            if step.status == "skipped":
                print(f"    pulado: {step.name} ({step.detail})")
        if bad := r.failed:
            print(f"    FALHOU em: {bad.name}")
            for line in bad.detail.splitlines():
                print(f"      | {line}")

    green = len(results) - red - partial
    print(f"\n{red} vermelhos | {partial} parciais | {green} verdes")
    total_workflows = len(results) + len(not_affected)
    print(
        f"Isto NAO e o portao: a evidencia de merge e o verde do GitHub para os "
        f"{total_workflows} workflow(s)."
    )

    if args.list:
        print("--list nao executa nada: nenhum recibo foi gravado.")
    else:
        receipt_path = _write_receipt(
            root,
            red=red,
            partial=partial,
            green=green,
            affected=bool(args.affected),
            dry_run=False,
            workflows_available=len(available),
            workflows_requested=len(args.workflows) if args.workflows else len(available),
            workflows_run=len(results),
            head_before=head_before,
            dirty_before=dirty_before,
        )
        print(f"recibo escrito em {receipt_path.relative_to(root)}")

    if args.affected and not_affected:
        print(
            f"--affected NAO roda por inteiro: {len(not_affected)} workflow(s) ficaram de fora "
            "de proposito. Nao use isto como evidencia de merge -- rode sem a flag para o modo "
            "completo."
        )

    return 1 if red else 0


if __name__ == "__main__":
    raise SystemExit(main())
