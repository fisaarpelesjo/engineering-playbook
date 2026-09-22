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

#: Gitignored scratch that must not reach the sandbox: the prepare receipt, the pull request body,
#: the branch origin record. It made the language guard report a file that is not in the repository
#: at all, so a clean sandbox was red before any mutation was applied.
#:
#: Matched by PATH, not by name. `shutil.ignore_patterns` compares basenames, and `delivery` is
#: also the name of `docs/delivery/` -- ignoring the name dropped a documentation directory from
#: the sandbox and made the inventory look stale there. Measured, one edit after the first attempt.
SANDBOX_IGNORED_PATHS = (".project/delivery",)

DELIVERY = "src/engineering_playbook/delivery.py"
CORE = "src/engineering_playbook/core.py"
SKIP_POLICY = "tests/skip_policy.py"
SPEC = "specs/003-no-stage-without-a-mechanism/spec.md"
HOOK = ".claude/hooks/enforce_delivery_pipeline.py"

START = "tests/unit/test_start_measures_its_base.py"
CLAIMS = "tests/unit/test_code_names_its_spec.py"
VERDICT = "tests/unit/test_signed_verdict_leaves_the_tree.py"
SKIPS = "tests/unit/test_a_skip_is_declared.py"
MATRIX = "tests/unit/test_coverage_matrix_is_measured.py"
BASE = "tests/unit/test_one_base_one_meaning.py"
MIRROR = "tests/unit/test_resource_mirror_parity.py"
GUARD = "tests/unit/test_the_repository_speaks_one_language.py"

#: The tree `publish` hands back, measured after the command.
PUBLISH_CLEAN_GUARD = "tests/unit/test_publish_leaves_tree_clean.py"
CHAIN = "tests/unit/test_the_chain_is_verified.py"
#: The line that puts the pipeline's own records into the index. Without it `publish` commits
#: nothing and hands back the dirty tree that `start` then refuses -- issue #64.
BOOKKEEPING_STAGED = '    staged = run(root, ["git", "add", "--", *present])'

#: The refusal that keeps work the operator staged out of a commit whose message they never wrote.
BOOKKEEPING_REFUSES_UNRELATED = "    if unrelated:"

#: The pathspec itself. Review changed this one token to `git add -A` and the whole five-test suite
#: stayed green, because every test started from a clean tree and the one decoy sat in the index,
#: where the refusal already looks. `publish` would have swept unfinished work into a commit the
#: operator never wrote a message for and pushed it.
BOOKKEEPING_PATHSPEC = '    staged = run(root, ["git", "add", "--", *present])'

#: Path boundary rather than string prefix. `.project/state.yml.bak` and
#: `.project/checkpoints-archive/` begin with a listed string without being the file or the
#: directory it names; under the first version of this line all four of review's planted paths were
#: committed and pushed inside a bookkeeping commit.
BOOKKEEPING_BOUNDARY = (
    '    return any(path == item or path.startswith(f"{item}/") for item in BOOKKEEPING_PATHS)'
)

#: The line that decides a piece of text is Portuguese, in the shared detector both guards call.
#: Raising the threshold is the cheapest way to make them measure nothing while still passing:
#: at three markers a line, the whole inventory reads as already translated.
LANGUAGE = "src/engineering_playbook/language.py"
LANGUAGE_THRESHOLD = "    return len(portuguese_markers(text, prose=prose)) >= threshold"

#: The morphology alternative, which is what reaches accent-stripped Portuguese written in content
#: words. Neutering it takes the detector back to a word list.
#:
#: It is replaced by an EMPTY pattern fragment rather than deleted. Deleting the line leaves the
#: string literal above it without its trailing comma, so the module stops importing and every
#: target errors on collection -- which this harness reported as `escaped`. That verdict is red,
#: so the entry failed closed rather than passing silently, but it measured nothing: a mutant that
#: does not run cannot show that a test would have caught it. An empty fragment concatenates
#: harmlessly and removes exactly the rule under test, and nothing else.
LANGUAGE_MORPHOLOGY = r'    r"|(?<![\w.-])\w{4,}(?:coes|cao|dade|dades|ncia|ncias|mente)(?![\w-])",'

#: The floor below which the density rule is not consulted. Raising it to 2 is the exact edit that
#: shipped for one review round and silently removed a file from the inventory.
LANGUAGE_FLOOR = "DENSITY_FLOOR_MARKERS = 1"
#: The claim-versus-structure comparison. Removing it leaves a control that checks a parent
#: exists -- which `traceability_refusal` already does -- and stops checking that the parent
#: the body advertises is the one the API reports.
ISSUE_CLAIM_CHECKED = "    if claim is not None and claim.group(1) != actual:"
#: The line in `verify_root` that makes the contract check a STEP and not just a function.
#: Review measured that deleting the step from both copies of the workflow left the whole
#: suite green, which is the same gap T213 closed for `--pr-files` one slice earlier.
CONTRACT_STEP_REQUIRED = '            "validate-ci --issue-contract-body" in workflow_text,'
#: The two files whose fidelity the mirror guard exists to protect. Perturbing them is how the
#: guard is removed for the purposes of this inventory: there is nothing to delete from the test
#: itself that would make it FAIL -- excluding a path makes it pass -- so what is removed here is
#: the fidelity of the shipped artifact, and the mechanism is whatever notices.
SHIPPED_SCHEMA = "src/engineering_playbook/resources/.project/schemas/state.schema.json"
ROOT_WORKFLOW = ".github/workflows/quality.yml"
ORIGIN = "tests/unit/test_the_override_leaves_a_trace.py"

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
ORIGIN_RECORDED = "    record_branch_origin(\n"
REMOTE_REF_WINS = "    if git_ref_exists(root, remote_ref):\n        return remote_ref"
HOOK_SEES_BRANCHES = (
    "    if branch_creation(command) or branch_write(command) or BRANCH_INDIRECT.search(command):"
)
#: The rule `git branch` is decided by. Review measured `git branch -q novo` creating a ref past
#: the pattern this replaced, so the mechanism is the reading of the arguments, not the pattern.
HOOK_READS_BRANCH_ARGUMENTS = "    return names > 0 and not listing"
#: The measured prefix table. A wrong minimum here is not a syntax error and not a failing import:
#: it silently lets `git switch --cr <name>` through, which is exactly how it shipped the first
#: time. Raising `create` past its real minimum is the cheapest way to prove a test notices.
HOOK_KNOWS_PREFIX_MINIMUMS = '    "create": 2,'
#: The line that makes a listing option mean "the token beside it is a pattern". Removing it
#: turns every `git branch --list <pattern>` into a refusal, which no enumerated case would
#: necessarily notice -- the generated suite does, because it asks git what each option does.
HOOK_HONOURS_LISTING = (
    "        if head in _BRANCH_LIST_MODE:\n            listing = True\n"
    "        if head in _BRANCH_CONSUMES_VALUE:"
)
PUBLISH_RESOLVES_BASE = (
    "        commits_to_publish = local_commits(\n"
    "            args.root, resolve_base(args.root, args.remote, args.base)\n"
    "        )"
)
STATUS_RESOLVES_BASE = "        base_ref = resolve_base(args.root, args.remote, args.base)"
#: A line every schema in this repository carries, so the edit is a drift and not a syntax error.
SHIPPED_SCHEMA_FIELD = '"$schema"'
#: A step that appears ONCE, in a job the derived project does receive. `Sync` appears twice, and
#: `Every mechanism is held...` sits inside the `adversarial` job, which the comparison strips --
#: mutating either would prove nothing. This plants on the root side the kind of unmirrored edit
#: #49 measured happening repeatedly by hand in a single session.
ROOT_WORKFLOW_STEP = "      - name: Typecheck\n"
#: A COMMENT, and deliberately nothing else. The structural comparison parses both copies, so
#: YAML discards this line and the two still compare equal -- only the textual comparison
#: between literal anchors sees it. Without this entry, half of the redundancy the matrix
#: cell claims would have no mechanism proving it bites.
ROOT_WORKFLOW_COMMENT = "      # The title is attacker-controlled text on a public repository"

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
        mechanism="base means the ref the server will use",
        requirement="FR-005, T219",
        stage=9,
        file=DELIVERY,
        find=REMOTE_REF_WINS,
        replace="    if False:\n        return remote_ref",
        proves=(f"{BASE}::test_the_remote_ref_is_what_base_means",),
    ),
    Mutation(
        # Separate from the resolver entry above on purpose. #61 measured that reverting BOTH
        # call sites left every one of the 480 tests the suite then had green: the resolver was
        # covered, using it was
        # not. A mechanism is where the decision is consumed, not only where it is computed.
        mechanism="publish measures against the base the server will use",
        requirement="FR-005, T219",
        stage=9,
        file=DELIVERY,
        find=PUBLISH_RESOLVES_BASE,
        replace="        commits_to_publish = local_commits(args.root, args.base)",
        proves=(f"{BASE}::test_publish_refuses_work_the_server_already_has",),
    ),
    Mutation(
        mechanism="status reports against the base the server will use",
        requirement="FR-005, T219",
        stage=9,
        file=DELIVERY,
        find=STATUS_RESOLVES_BASE,
        replace="        base_ref = args.base",
        proves=(f"{BASE}::test_status_counts_against_the_server_base",),
    ),
    Mutation(
        mechanism="the harness refuses branch writes outside the pipeline",
        requirement="FR-011, AC-007, T221",
        stage=18,
        file=HOOK,
        find=HOOK_SEES_BRANCHES,
        replace="    if False:",
        proves=(f"{BASE}::test_branch_writes_are_refused[git switch -c feat/001-x]",),
    ),
    Mutation(
        # Separate from the entry above: that one removes the call, this one removes the decision
        # the call consults. `git branch -q novo` creates a ref and looks nothing like a write,
        # which is why the guard reads the arguments rather than matching their shape.
        mechanism="branch arguments are read the way git reads them",
        requirement="FR-011, AC-007, T221",
        stage=18,
        file=HOOK,
        find=HOOK_READS_BRANCH_ARGUMENTS,
        replace="    return False",
        proves=(f"{BASE}::test_branch_writes_are_refused[git branch -q novo]",),
    ),
    Mutation(
        mechanism="abbreviated long options are refused at git's own minimum",
        requirement="FR-011, AC-007, T221",
        stage=18,
        file=HOOK,
        find=HOOK_KNOWS_PREFIX_MINIMUMS,
        replace='    "create": 6,',
        proves=(f"{BASE}::test_branch_writes_are_refused[git switch --cr short-create]",),
    ),
    Mutation(
        # Proved by the GENERATED suite rather than by an enumerated case, which is the point of
        # that file: the cases come from `git branch --git-completion-helper` and from running
        # each option, so a table that stops matching git fails without anyone having thought of
        # the particular option that broke.
        mechanism="listing options keep a pattern from reading as a branch name",
        requirement="FR-011, AC-007, T221",
        stage=18,
        file=HOOK,
        find=HOOK_HONOURS_LISTING,
        replace=(
            "        if False:\n            listing = True\n"
            "        if head in _BRANCH_CONSUMES_VALUE:"
        ),
        # The node id is an ENUMERATED case, not a generated one, although the generated suite
        # catches this too. A generated id carries the name of a git option, so a git that stops
        # declaring `--list` would make this entry report `unusable` -- the coupling to git's
        # naming that the generated file exists to remove, reintroduced by the inventory.
        proves=(f"{BASE}::test_looking_at_the_repository_stays_allowed[git branch -l feat/*]",),
    ),
    Mutation(
        mechanism="a branch records how it came to exist",
        requirement="FR-009, FR-012, T220",
        stage=9,
        file=DELIVERY,
        find=ORIGIN_RECORDED,
        replace="    if False:\n        record_branch_origin(\n",
        proves=(f"{ORIGIN}::test_the_override_is_recorded_where_an_instrument_reads_it",),
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
        # Stage 11 named this test as its evidence while the guard excluded `.project/schemas/`
        # and `.github/workflows/quality.yml` -- the two families most likely to drift, one of
        # them edited by hand repeatedly in a single session. Measured on 2026-09-22: the
        # seven schema pairs were already identical, so the exclusion protected nothing and hid
        # the next hand edit.
        mechanism="a schema that drifts from the shipped copy is refused",
        requirement="FR-018, #49",
        stage=11,
        file=SHIPPED_SCHEMA,
        find=SHIPPED_SCHEMA_FIELD,
        replace='"$schema_drifted"',
        proves=(f"{MIRROR}::test_every_mirrored_pair_matches_byte_for_byte",),
    ),
    Mutation(
        # The workflow cannot be pinned byte for byte: the root copy carries an `adversarial` job
        # a derived project cannot run. So the shipped copy is compared against the root copy with
        # that job removed, and this entry plants the drift the comparison exists to catch.
        mechanism="the shipped workflow is the root workflow minus the job it cannot run",
        requirement="FR-018, #49",
        stage=11,
        file=ROOT_WORKFLOW,
        find=ROOT_WORKFLOW_STEP,
        replace="      - name: Typecheck\n      - name: Unmirrored\n",
        proves=(
            f"{MIRROR}::test_the_shipped_workflow_is_the_root_workflow_minus_the_job_it_cannot_run",
        ),
    ),
    Mutation(
        mechanism="the shipped workflow matches the root outside the unshipped job, comments too",
        requirement="FR-018, #49",
        stage=11,
        file=ROOT_WORKFLOW,
        find=ROOT_WORKFLOW_COMMENT,
        replace="      # The title is attacker controlled text on a public repository",
        proves=(
            f"{MIRROR}::test_the_shipped_workflow_matches_byte_for_byte_outside_the_unshipped_job",
        ),
    ),
    Mutation(
        # Same shape as the matrix guard below: the language guard IS a test, so what gets mutated
        # is the rule it applies. At three markers a line, every file in the inventory reads as
        # translated and the inventory's second half -- the one that refuses a stale name -- fires.
        mechanism="a file that still speaks Portuguese stays named",
        requirement="FR-016, #65",
        stage=11,
        file=LANGUAGE,
        find=LANGUAGE_THRESHOLD,
        replace="    return len(portuguese_markers(text, prose=prose)) >= threshold + 1",
        proves=(f"{GUARD}::test_a_translated_file_leaves_the_inventory",),
    ),
    Mutation(
        # Stage 9 of the matrix, and the half of it that was declared `parcial`. The tree AFTER
        # the command is what these measure: every write `publish` makes is wanted, the defect was
        # that it stayed uncommitted.
        mechanism="publish leaves no tree behind it",
        requirement="FR-001, #64",
        stage=9,
        file=DELIVERY,
        find=BOOKKEEPING_STAGED,
        replace='    staged = run(root, ["git", "status", "--porcelain"])',
        proves=(f"{PUBLISH_CLEAN_GUARD}::test_after_publish_the_tree_is_clean",),
    ),
    Mutation(
        mechanism="a bookkeeping commit carries only bookkeeping",
        requirement="FR-001, #64",
        stage=9,
        file=DELIVERY,
        find=BOOKKEEPING_REFUSES_UNRELATED,
        replace="    if False:",
        proves=(
            f"{PUBLISH_CLEAN_GUARD}"
            "::test_work_the_operator_staged_is_never_swept_into_a_bookkeeping_commit",
        ),
    ),
    Mutation(
        mechanism="publish stages its own records and nothing else",
        requirement="FR-001, #64",
        stage=9,
        file=DELIVERY,
        find=BOOKKEEPING_PATHSPEC,
        replace='    staged = run(root, ["git", "add", "-A"])',
        proves=(
            f"{PUBLISH_CLEAN_GUARD}"
            "::test_work_in_progress_outside_the_index_is_left_exactly_where_it_was",
        ),
    ),
    Mutation(
        mechanism="a record is matched at a path boundary, not by prefix",
        requirement="FR-001, #64",
        stage=9,
        file=DELIVERY,
        find=BOOKKEEPING_BOUNDARY,
        replace="    return any(path.startswith(item) for item in BOOKKEEPING_PATHS)",
        proves=(f"{PUBLISH_CLEAN_GUARD}::test_a_path_that_merely_begins_like_a_record_is_not_one",),
    ),
    Mutation(
        # The inventory cannot hold either of the next two. It is regenerated FROM the detector, so
        # weakening the detector shrinks the inventory, the pin is updated to match, and the
        # shrinking reads as translation progress. What holds them is a fixed corpus of real lines.
        mechanism="the detector reaches Portuguese no word list can hold",
        requirement="FR-016, #65",
        stage=11,
        file=LANGUAGE,
        find=LANGUAGE_MORPHOLOGY,
        replace='    r"",',
        proves=(f"{GUARD}::test_the_detector_still_catches_what_it_was_built_to_catch",),
    ),
    Mutation(
        mechanism="one marker in a short file is still a marker",
        requirement="FR-016, #65",
        stage=11,
        file=LANGUAGE,
        find=LANGUAGE_FLOOR,
        replace="DENSITY_FLOOR_MARKERS = 2",
        proves=(f"{GUARD}::test_the_detector_still_catches_what_it_was_built_to_catch",),
    ),
    Mutation(
        mechanism="an issue may not claim a parent the API does not report",
        requirement="FR-013, FR-015, #65",
        stage=6,
        file=DELIVERY,
        find=ISSUE_CLAIM_CHECKED,
        replace="    if False:",
        proves=(f"{CHAIN}::test_a_parentage_claim_the_api_does_not_confirm_is_refused",),
    ),
    Mutation(
        mechanism="CI must invoke the card-conforms-to-the-contract gate",
        requirement="FR-013, FR-015, #65",
        stage=6,
        file=CORE,
        find=CONTRACT_STEP_REQUIRED,
        replace="            True,",
        proves=(f"{CLAIMS}::test_verify_refuses_a_workflow_that_never_invokes_the_contract_gate",),
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
#: asserted. No count is written here on purpose: it is derived on the next line, it changed from
#: six to seven to eight while this sentence still said six, and
#: `test_the_matrix_reports_the_inventory_it_actually_has` compares the matrix cell against this
#: set -- so the number has exactly one home.
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
    """Copy what git tracks, minus the scratch that is not part of the repository.

    THIS USED TO BE AN ALLOWLIST -- a tuple of directories and a tuple of root files, "what the
    targets need". It failed three times in one slice, each time the same way and each time
    silently: a root file the language guard reads was missing, so its inventory looked already
    translated; the checkpoints were dropped, so an exclusion audit found nothing to audit; and
    `extensions/` was never listed at all. Every one of those made a clean sandbox RED before any
    mutation was applied, which the harness reports as `unusable` -- a run that proves nothing.

    A list of what the targets need has to be edited whenever a target starts needing more, and
    nothing says when that happened. `git ls-files` needs no maintenance and matches what
    `actions/checkout` hands CI, which is the tree these results are supposed to describe.

    Scratch is excluded by path, not by name: `.project/delivery/` is gitignored anyway, but the
    fallback walk in the language guard would find it, and `delivery` is also the name of
    `docs/delivery/` -- ignoring the NAME dropped a documentation directory and made the inventory
    look stale there. Measured, one edit after the first attempt.
    """
    sandbox.mkdir(parents=True, exist_ok=True)
    listed = subprocess.run(
        ["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    tracked = [line.strip() for line in listed if line.strip()]
    missing: list[str] = []
    if len(tracked) < 200:
        raise FileNotFoundError(
            f"git lists only {len(tracked)} tracked files under {root}; a sandbox built from that "
            "would be silently incomplete, which is the condition that makes a meaningless result "
            "read as a detection"
        )
    for name in tracked:
        if any(name.startswith(prefix) for prefix in SANDBOX_IGNORED_PATHS):
            continue
        source = root / name
        if not source.is_file():
            missing.append(name)
            continue
        destination = sandbox / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    # The allowlist this replaced raised on a missing piece; the first version of the rewrite
    # skipped it silently, which is the property the rewrite existed to remove. A file git tracks
    # and the working tree does not have is ordinary mid-slice -- deleted and not yet staged --
    # and it degrades the sandbox to `unusable`, safely but without saying so.
    if missing:
        raise FileNotFoundError(
            f"git tracks {len(missing)} file(s) the working tree does not have, so this sandbox "
            f"would be a copy of neither: {sorted(missing)[:5]}"
        )


def apply_mutation(sandbox: Path, mutation: Mutation) -> str | None:
    """Apply it, or say why it could not be applied."""
    target = sandbox / mutation.file
    if not target.is_file():
        return f"{mutation.file} is not in the sandbox"
    # `newline=""` on both sides: without it `write_text` translates every `\n` to
    # `os.linesep`, and on Windows that rewrites the entire file. Review measured the two
    # stage-11 entries going red with NO drift planted -- the harness's own write was the
    # mutation. Harmless while every target was a `.py` or `.md` compared by meaning; not
    # harmless now that entries exist whose target compares bytes.
    # `Path.read_text` only grew a `newline` parameter in 3.13 and this project targets 3.11,
    # so the handle is opened explicitly. `newline=""` keeps the file's own terminators, which is
    # what stops this write from rewriting every line -- and it is only half the job: the `find`
    # literals in the inventory are written with `\n`, so on a CRLF working tree, which is the
    # ordinary state of a Windows checkout, no multi-line literal would match and every entry
    # carrying one would report `inert`. Measured here on 2026-09-22, after the #49 fix did the
    # preserving half alone.
    #
    # So: read raw, match on a normalised copy, write back through the file's own terminator.
    with target.open("r", encoding="utf-8", newline="") as handle:
        raw = handle.read()
    terminator = "\r\n" if "\r\n" in raw else "\n"
    text = raw.replace("\r\n", "\n")
    occurrences = text.count(mutation.find)
    if occurrences == 0:
        return "the text this entry removes is no longer in the file"
    if occurrences > 1:
        return f"the text this entry removes occurs {occurrences} times, so it is not one control"
    with target.open("w", encoding="utf-8", newline=terminator) as handle:
        handle.write(text.replace(mutation.find, mutation.replace, 1))
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
