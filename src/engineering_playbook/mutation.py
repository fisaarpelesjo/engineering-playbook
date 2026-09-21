"""T216 / FR-017 / AC-012: remove each mechanism and watch a named test go red.

A test that only confirms a control is present does not satisfy NFR-004. What satisfies it is a
test whose failure is *induced* by removing the control. That is a claim about the suite, and the
only honest way to make it is to remove each control and look.

WHY A BASELINE RUN COMES FIRST, and it is the whole correctness of this file. The first version
declared a mutation `caught` whenever the targeted run came back non-zero. Review measured what
that actually means:

* one entry pointed at `tests/unit/test_core.py`, which is ALREADY RED inside the sandbox -- 15
  failures caused by files the sandbox did not copy. The entry reported `caught` with a failure
  set identical to the run without any mutation at all. It measured nothing, and the "14 of 14"
  written into the specification was false for it.
* a mutation that produced a syntax error also reported `caught`. pytest exits non-zero for a
  collection error, for a usage error, and for collecting nothing -- none of which is a test
  noticing that a control disappeared.

So every entry now runs its targets twice: once clean, once mutated. A clean run that is not green
makes the entry `unusable` rather than `caught`, and the mutated run has to produce a failing node
id the clean run did not. "It went red" is not evidence; "this named test went red, and it was
green a moment ago" is.

TARGETS ARE NODE IDS, not files. A file-level target runs tests that have nothing to do with the
control, which is how a pre-existing failure got read as a detection; it also makes each entry pay
for a whole module. Naming the test that must notice states the claim precisely and is what the
guard checks for pertinence.

HOW IT RUNS: each mutation is applied to a COPY under a temporary directory, and the targets run
there. The repository being worked in is read and never written -- a harness that edits the tree it
measures is the self-reference this repository spent four slices removing.

VERDICTS:

* `caught`   -- a named target was green before and failed after. The mechanism is held.
* `escaped`  -- the targets stayed green. Nothing holds that mechanism.
* `inert`    -- the edit changed nothing; the inventory has drifted away from the code.
* `unusable` -- the targets were not green before the mutation, so nothing can be concluded.

The last two are failures of this harness rather than of the pipeline, and they are reported
apart from `escaped` so a broken instrument cannot read as a covered mechanism.

WHAT IS NOT CLAIMED. This does not establish the absence of bypass vectors, which NFR-005
explicitly declines to claim anywhere. It does not cover every stage of the coverage matrix: the
inventory reaches the stages named in `COVERED_STAGES` and no others, and the matrix records that
reach rather than implying completeness.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

#: Copied into each sandbox. `README.md`, `REVIEW.md`, `docs`, `templates` and `uv.lock` are here
#: because `verify_root` and the CLI reach for them: without them the sandbox starts red, which is
#: exactly the condition that made a meaningless result look like a detection.
SANDBOX_CONTENTS = (
    "src",
    "tests",
    "scripts",
    ".github",
    "specs",
    ".project",
    ".claude",
    "docs",
    "templates",
    "profiles",
)
SANDBOX_FILES = ("pyproject.toml", "uv.lock", "README.md", "REVIEW.md", "ENGINEERING.md")
#: Not copied: 80-odd checkpoint files no target reads.
SANDBOX_IGNORES = ("__pycache__", "*.pyc", ".pytest_cache", "CP-*.yml")

DELIVERY = "src/engineering_playbook/delivery.py"
CORE = "src/engineering_playbook/core.py"
SKIP_POLICY = "tests/skip_policy.py"
SPEC = "specs/003-no-stage-without-a-mechanism/spec.md"

START = "tests/unit/test_start_measures_its_base.py"
CLAIMS = "tests/unit/test_code_names_its_spec.py"
VERDICT = "tests/unit/test_signed_verdict_leaves_the_tree.py"
SKIPS = "tests/unit/test_a_skip_is_declared.py"
MATRIX = "tests/unit/test_coverage_matrix_is_measured.py"

# Long source fragments, named so the entries stay readable and the literals stay exact.
BASE_CONTAINS_HEAD = '    if unmerged == "0":\n        return None'
BASE_REF_MISSING = "    if not git_ref_exists(root, ref):"
SPEC_DIR_TOUCHED = (
    "    if spec_dir and any(path.startswith(spec_dir) for path in changed_paths):\n"
    "        return None"
)
TRUNCATION_CHECK = "    if declared_total is not None and declared_total != len(changed_paths):"
ESCAPE_IN_DIFF = "        if STATE_RELATIVE not in changed_paths:"
VERDICT_COVERS = "    if covered:\n        return None"
GH_UNAVAILABLE = (
    "    except GhUnavailableError as failure:\n"
    "        return (\n"
    '            "ERROR: gh nao respondeu, portanto o veredicto assinado nao foi medido, e "'
)
GH_UNAVAILABLE_REMOVED = (
    "    except GhUnavailableError:\n"
    "        return None\n"
    "    if False:\n"
    "        return (\n"
    '            "ERROR: gh nao respondeu, portanto o veredicto assinado nao foi medido, e "'
)
SIGNING_NEEDS = "    missing = sorted(set(jobs) - {signing_job_name} - set(declared_needs))"
SIGNING_LEAK = (
    '        leaked = [key for key in ["id-token", "attestations"] if other.get(key) == "write"]'
)
ONE_SIGNING_JOB = "    if len(signing_jobs) != 1:"
PR_FILES_STEP = '            "validate-ci --pr-files" in workflow_text,'
SKIP_UNDECLARED = "        if declaration is None:"
SKIP_STALE = "    for nodeid in sorted(set(declared) - set(observed)):"
#: No stage reads `ausente` any more -- AC-011 is satisfied -- so the fraud this mutation plants
#: is the next one along: promoting a `parcial` stage to a closed classification by editing the
#: word, which the PARTIAL_STAGES pin exists to refuse.
STAGE_TWENTY_PARTIAL = (
    "| 20 | Cadeia de rastreabilidade entre pull request e PRD | parcial, o elo ate ao "
)
STAGE_TWENTY_BY_PROSE = (
    "| 20 | Cadeia de rastreabilidade entre pull request e PRD | CI | o elo ate ao "
)


@dataclass(frozen=True)
class Mutation:
    """One control, removed one way, and the named tests that must notice.

    `find` is matched literally and must occur exactly once: a fragment matching twice removes
    more than the entry names, and one matching nothing is an inventory that has drifted.
    """

    mechanism: str
    requirement: str
    stage: int
    file: str
    find: str
    replace: str
    proves: tuple[str, ...]


#: THE INVENTORY. One entry per mechanism, with the smallest edit that takes it away and the node
#: id of the test that must go red. `stage` is the coverage-matrix row the mechanism belongs to,
#: so the reach of this inventory is a fact the guard can read rather than a claim in prose.
MUTATIONS: tuple[Mutation, ...] = (
    Mutation(
        mechanism="start refuses a HEAD the base already absorbed",
        requirement="FR-005, T218",
        stage=9,
        file=DELIVERY,
        find=BASE_CONTAINS_HEAD,
        replace="    if True:\n        return None",
        proves=(f"{START}::test_start_refuses_a_head_the_base_has_already_absorbed",),
    ),
    Mutation(
        mechanism="start refuses when the base ref cannot be read",
        requirement="NFR-002, T218",
        stage=9,
        file=DELIVERY,
        find=BASE_REF_MISSING,
        replace="    if False:",
        proves=(f"{START}::test_a_base_that_cannot_be_read_refuses_rather_than_assuming",),
    ),
    Mutation(
        mechanism="a specification claims the changed code",
        requirement="FR-014, T213",
        stage=4,
        file=DELIVERY,
        find=SPEC_DIR_TOUCHED,
        replace="    if True:\n        return None",
        proves=(
            f"{CLAIMS}::test_code_touched_alone_is_refused_and_the_message_names_the_directory",
        ),
    ),
    Mutation(
        mechanism="a truncated file list is refused rather than reported on",
        requirement="NFR-002, T213",
        stage=4,
        file=DELIVERY,
        find=TRUNCATION_CHECK,
        replace="    if False:",
        proves=(f"{CLAIMS}::test_a_truncated_file_list_is_refused_rather_than_reported_on",),
    ),
    Mutation(
        mechanism="the escape must travel in the diff it excuses",
        requirement="FR-014, T213",
        stage=4,
        file=DELIVERY,
        find=ESCAPE_IN_DIFF,
        replace="        if False:",
        proves=(f"{CLAIMS}::test_the_escape_must_live_in_the_diff_it_excuses",),
    ),
    Mutation(
        mechanism="CI must invoke the specification-claims-this-code gate",
        requirement="FR-014, T213",
        stage=4,
        file=CORE,
        find=PR_FILES_STEP,
        replace="            True,",
        proves=(f"{CLAIMS}::test_verify_refuses_a_workflow_that_never_invokes_the_gate",),
    ),
    Mutation(
        mechanism="merge refuses content no run has signed",
        requirement="FR-006, T208",
        stage=17,
        file=DELIVERY,
        find=VERDICT_COVERS,
        replace="    if True:\n        return None",
        proves=(f"{VERDICT}::test_merge_refuses_content_no_run_has_signed",),
    ),
    Mutation(
        # The first draft rewrote the refusal's WORDING and the suite stayed green, because the
        # refusal still happened and the assertion matched a word on the next line. A mutation
        # that edits a message proves nothing; this removes the refusal itself.
        mechanism="merge refuses when gh cannot answer",
        requirement="NFR-002, T208",
        stage=17,
        file=DELIVERY,
        find=GH_UNAVAILABLE,
        replace=GH_UNAVAILABLE_REMOVED,
        proves=(f"{VERDICT}::test_merge_refuses_when_gh_cannot_answer",),
    ),
    Mutation(
        mechanism="the signing job depends on every battery",
        requirement="FR-006, T208",
        stage=15,
        file=CORE,
        find=SIGNING_NEEDS,
        replace="    missing = []",
        proves=(f"{VERDICT}::test_each_removal_from_the_signing_job_fails_verify",),
    ),
    Mutation(
        mechanism="no other job holds the signing identity",
        requirement="FR-006, T208",
        stage=15,
        file=CORE,
        find=SIGNING_LEAK,
        replace="        leaked = []",
        proves=(f"{VERDICT}::test_each_removal_from_the_signing_job_fails_verify",),
    ),
    Mutation(
        mechanism="exactly one job mints the verdict",
        requirement="FR-006, T208",
        stage=15,
        file=CORE,
        find=ONE_SIGNING_JOB,
        replace="    if False:",
        proves=(f"{VERDICT}::test_each_removal_from_the_signing_job_fails_verify",),
    ),
    Mutation(
        mechanism="an undeclared skip fails the run",
        requirement="FR-008, T210",
        stage=16,
        file=SKIP_POLICY,
        find=SKIP_UNDECLARED,
        replace="        if False:",
        proves=(f"{SKIPS}::test_a_written_reason_is_not_a_declared_one",),
    ),
    Mutation(
        mechanism="a declaration that stopped skipping is refused",
        requirement="FR-008, T210",
        stage=16,
        file=SKIP_POLICY,
        find=SKIP_STALE,
        replace="    for nodeid in sorted(set()):",
        proves=(f"{SKIPS}::test_a_declaration_that_stopped_skipping_is_refused",),
    ),
    Mutation(
        # The matrix guard IS a test, so removing it to prove it would be circular. What gets
        # mutated is the DATA it reads: a stage closed by editing prose, which is the fraud the
        # guard exists to refuse (#39).
        mechanism="a stage cannot be closed by editing prose",
        requirement="FR-016, AC-011, T214",
        stage=20,
        file=SPEC,
        find=STAGE_TWENTY_PARTIAL,
        replace=STAGE_TWENTY_BY_PROSE,
        proves=(f"{MATRIX}::test_the_partial_stages_are_exactly_the_ones_declared_partial",),
    ),
)

#: The coverage-matrix rows this inventory reaches, measured from the entries above rather than
#: asserted. Six of twenty: the matrix says so, and the vector table is classified accordingly.
COVERED_STAGES = frozenset(mutation.stage for mutation in MUTATIONS)


@dataclass(frozen=True)
class MutationResult:
    mutation: Mutation
    verdict: str  # "caught" | "escaped" | "inert" | "unusable"
    detail: str

    @property
    def ok(self) -> bool:
        return self.verdict == "caught"


def build_sandbox(root: Path, sandbox: Path) -> None:
    """Copy what the targets need, and refuse quietly missing pieces.

    A silently incomplete sandbox starts red, and a red baseline is what let a meaningless result
    read as a detection.
    """
    sandbox.mkdir(parents=True, exist_ok=True)
    ignore = shutil.ignore_patterns(*SANDBOX_IGNORES)
    for name in SANDBOX_CONTENTS:
        source = root / name
        if not source.is_dir():
            raise FileNotFoundError(f"the sandbox declares {name}/ and the repository has none")
        shutil.copytree(source, sandbox / name, dirs_exist_ok=True, ignore=ignore)
    for name in SANDBOX_FILES:
        source = root / name
        if not source.is_file():
            raise FileNotFoundError(f"the sandbox declares {name} and the repository has none")
        shutil.copy2(source, sandbox / name)


def apply_mutation(sandbox: Path, mutation: Mutation) -> str | None:
    """Apply it, or say why it could not be applied."""
    target = sandbox / mutation.file
    if not target.is_file():
        return f"{mutation.file} is not in the sandbox"
    text = target.read_text(encoding="utf-8")
    occurrences = text.count(mutation.find)
    if occurrences == 0:
        return "the text this entry removes is no longer in the file"
    if occurrences > 1:
        return f"the text this entry removes occurs {occurrences} times, so it is not one control"
    target.write_text(text.replace(mutation.find, mutation.replace, 1), encoding="utf-8")
    return None


_FAILED = re.compile(r"^FAILED (\S+)", re.MULTILINE)


def run_targets(sandbox: Path, targets: tuple[str, ...]) -> tuple[int, set[str]]:
    """Run the named tests and return the exit code plus the node ids that failed."""
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *targets],
        cwd=sandbox,
        capture_output=True,
        text=True,
        timeout=600,
    )
    failed = {match.replace("\\", "/") for match in _FAILED.findall(completed.stdout)}
    return completed.returncode, failed


def classify(
    mutation: Mutation,
    clean_code: int,
    clean_failures: set[str],
    refusal: str | None,
    mutated_failures: set[str] | None,
) -> MutationResult:
    """The decision, as a pure function, because it is where the first version was wrong.

    Review measured that `returncode != 0` alone means four different things -- a test failed, a
    module failed to import, pytest was misused, nothing was collected -- and that one entry's
    targets were red before any mutation was applied. Both read as detections. The rule here is
    narrower and checkable: a node id that was green and is now failing.
    """
    if clean_code != 0:
        reason = (
            ", ".join(sorted(clean_failures))
            or "pytest refused for a reason other than a failing test"
        )
        return MutationResult(
            mutation,
            "unusable",
            f"the targets were not green before the mutation ({reason}), so nothing can be "
            "concluded from them failing after it",
        )
    if refusal is not None:
        return MutationResult(mutation, "inert", refusal)
    newly_failing = sorted((mutated_failures or set()) - clean_failures)
    if newly_failing:
        return MutationResult(mutation, "caught", ", ".join(newly_failing))
    return MutationResult(
        mutation,
        "escaped",
        f"{', '.join(mutation.proves)} stayed green without the control",
    )


def run_mutation(root: Path, mutation: Mutation, sandbox: Path) -> MutationResult:
    build_sandbox(root, sandbox)
    clean_code, clean_failures = run_targets(sandbox, mutation.proves)
    if clean_code != 0:
        return classify(mutation, clean_code, clean_failures, None, None)
    refusal = apply_mutation(sandbox, mutation)
    if refusal is not None:
        return classify(mutation, clean_code, clean_failures, refusal, None)
    _code, mutated_failures = run_targets(sandbox, mutation.proves)
    return classify(mutation, clean_code, clean_failures, None, mutated_failures)


def run_all(root: Path, workdir: Path) -> list[MutationResult]:
    return [
        run_mutation(root, mutation, workdir / f"m{index:02d}")
        for index, mutation in enumerate(MUTATIONS)
    ]
