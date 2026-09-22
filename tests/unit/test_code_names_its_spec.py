"""T213 / FR-014 / AC-010: code that no specification claims does not reach main.

Coverage matrix stage 4. The requirement is short -- "alteracao de codigo nao associada a
especificacao activa constitui falha de gate" -- and the obvious reading of it measures nothing.

MEASURED, on 2026-09-21, over the last eight merges on `main`: every one declared
`active_specification: specs/001-engineering-playbook/spec.md`, including the commits that closed
specs 002, 003 and 004. The field sat stale across eight slices, because nothing read it. A gate
of the shape "code changed, so the declared specification must exist" would have passed all eight
while the association it claims to check was absent from every one.

So association is asked of the diff instead: a pull request that changes code touches the active
specification's own directory. And because a defect fix may legitimately have no specification --
issues #15 and #36 were exactly that, and a rule without an escape gets removed rather than
satisfied -- a slice may instead declare `no_spec_reason` in the state. The escape is a sentence,
versioned, that travels in the pull request; it is refused when it is too short to act on, by the
same distinction the skip inventory makes between a reason that is written and one that is
declared (T210).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engineering_playbook.core import write_yaml_atomic
from engineering_playbook.delivery import CODE_PREFIXES, spec_precedence_refusal

ACTIVE_SPEC = "specs/003-no-stage-without-a-mechanism/spec.md"


def repo(root: Path, **state: object) -> Path:
    (root / ".project").mkdir(parents=True, exist_ok=True)
    write_yaml_atomic(
        root / ".project/state.yml",
        {"schema_version": "1.0.0", "updated_at": "2026-01-01T00:00:00Z", **state},
    )
    return root


def test_a_change_that_touches_no_code_is_not_this_gates_business(tmp_path: Path) -> None:
    """Documentation, the specifications themselves and the pipeline's own bookkeeping are not
    code. A gate that fired on a typo in a README would be routed around within the day.
    """
    root = repo(tmp_path, active_specification=ACTIVE_SPEC)

    assert spec_precedence_refusal(root, ["README.md", ".project/state.yml", ACTIVE_SPEC]) is None


def test_code_touched_together_with_its_specification_passes(tmp_path: Path) -> None:
    root = repo(tmp_path, active_specification=ACTIVE_SPEC)

    refusal = spec_precedence_refusal(
        root,
        [
            "src/engineering_playbook/delivery.py",
            "specs/003-no-stage-without-a-mechanism/tasks.md",
        ],
    )

    assert refusal is None


def test_code_touched_alone_is_refused_and_the_message_names_the_directory(
    tmp_path: Path,
) -> None:
    """THE claim. The refusal has to say which directory it wanted, or it is a puzzle rather
    than a gate.
    """
    root = repo(tmp_path, active_specification=ACTIVE_SPEC)

    refusal = spec_precedence_refusal(root, ["src/engineering_playbook/delivery.py"])

    assert refusal is not None
    assert "specs/003-no-stage-without-a-mechanism/" in refusal
    assert "no_spec_reason" in refusal, "the refusal names the escape it offers"
    assert "src/engineering_playbook/delivery.py" in refusal


def test_the_stale_field_that_would_have_passed_eight_merges_is_refused(tmp_path: Path) -> None:
    """The measurement this gate exists because of, turned into a test.

    A slice closing spec 003 while the state still declares spec 001 is the exact shape of all
    eight merges measured on 2026-09-21. Existence of the declared file is not association, and
    this is where the obvious rule would have said yes.
    """
    root = repo(tmp_path, active_specification="specs/001-engineering-playbook/spec.md")

    refusal = spec_precedence_refusal(
        root,
        [
            "src/engineering_playbook/core.py",
            "specs/003-no-stage-without-a-mechanism/spec.md",
        ],
    )

    assert refusal is not None, (
        "touching a specification that is not the declared one satisfied the gate, which is the "
        "stale-field defect wearing a different hat"
    )


def test_no_declared_specification_at_all_is_refused(tmp_path: Path) -> None:
    root = repo(tmp_path)

    refusal = spec_precedence_refusal(root, ["src/engineering_playbook/core.py"])

    assert refusal is not None
    assert "declares no active_specification" in refusal


def test_a_declared_reason_lets_a_specless_fix_through(tmp_path: Path) -> None:
    """Issues #15 and #36 were defect fixes with no specification of their own. A rule without
    this escape would have refused both, and a gate that refuses legitimate work is a gate that
    gets deleted rather than satisfied.
    """
    root = repo(
        tmp_path,
        active_specification=ACTIVE_SPEC,
        no_spec_reason=(
            "Defect fix with no specification of its own: restores the contract the "
            "module docstring already states."
        ),
    )

    changed = ["scripts/agent_watch/subagent_feed.py", ".project/state.yml"]

    assert spec_precedence_refusal(root, changed) is None


def test_a_perfunctory_reason_is_not_a_declared_one(tmp_path: Path) -> None:
    """The escape is a sentence a reviewer reads, not a box to tick. `no_spec_reason: "fix"`
    declares nothing, which is the same distinction T210 draws for skips.
    """
    root = repo(tmp_path, active_specification=ACTIVE_SPEC, no_spec_reason="fix")

    refusal = spec_precedence_refusal(
        root, ["src/engineering_playbook/core.py", ".project/state.yml"]
    )

    assert refusal is not None
    assert "too short" in refusal


def test_a_blank_reason_is_the_same_as_none(tmp_path: Path) -> None:
    root = repo(tmp_path, active_specification=ACTIVE_SPEC, no_spec_reason="   ")

    refusal = spec_precedence_refusal(root, ["src/engineering_playbook/core.py"])

    assert refusal is not None
    assert "without touching" in refusal


@pytest.mark.parametrize("prefix", CODE_PREFIXES)
def test_every_declared_code_prefix_is_actually_gated(tmp_path: Path, prefix: str) -> None:
    """The prefix list is the whole reach of this gate, so each entry is exercised rather than
    trusted. A prefix nobody tests is a prefix that can be dropped without anything noticing.
    """
    root = repo(tmp_path, active_specification=ACTIVE_SPEC)

    assert spec_precedence_refusal(root, [f"{prefix}something.py"]) is not None


def test_the_workflows_that_gate_merges_count_as_code(tmp_path: Path) -> None:
    """Configuration by file extension, enforcement by effect. The attestation slice changed what
    may reach `main` by editing a workflow; a change of that kind with no specification behind it
    is precisely what FR-014 refuses.
    """
    root = repo(tmp_path, active_specification=ACTIVE_SPEC)

    assert spec_precedence_refusal(root, [".github/workflows/quality.yml"]) is not None
    assert spec_precedence_refusal(root, [".github/rulesets/main.yml"]) is not None


def test_documentation_and_bookkeeping_are_not_code(tmp_path: Path) -> None:
    """The other side of the prefix list, so it cannot pass by treating everything as code."""
    root = repo(tmp_path, active_specification=ACTIVE_SPEC)

    for path in ["README.md", "docs/delivery/README.md", ".project/checkpoints/CP-1.yml"]:
        assert spec_precedence_refusal(root, [path]) is None, f"{path} was treated as code"


def test_a_truncated_file_list_is_refused_rather_than_reported_on() -> None:
    """THE blocker review measured. `gh pr view --json files` caps at 100 paths and says nothing
    about having cut:

        gh api repos/kubernetes/kubernetes/pulls/142173 --jq .changed_files   -> 167
        gh pr view 142173 --json files --jq '.files | length'                 -> 100

    A gate reporting PASS over a window it did not know it was looking through is worse than no
    gate: it produces a green that means nothing. The true count travels beside the list, and a
    disagreement is a measurement that did not happen (NFR-002).
    """
    refusal = spec_precedence_refusal(Path("."), ["src/a.py"] * 100, 167)

    assert refusal is not None
    assert "167" in refusal and "100" in refusal
    assert "paginate" in refusal


def test_a_list_that_matches_its_declared_count_is_measured_normally(tmp_path: Path) -> None:
    """The other side: the cross-check must not turn every pull request into a refusal."""
    root = repo(tmp_path, active_specification=ACTIVE_SPEC)

    assert spec_precedence_refusal(root, ["README.md"], 1) is None


def test_the_escape_must_live_in_the_diff_it_excuses(tmp_path: Path) -> None:
    """Review measured that the escape was permanent: written once, it sat in the state file and
    exempted every later slice, invisible in their diffs. The sentence is read by the reviewer of
    the pull request that carries it -- so it has to be carried, every time.
    """
    root = repo(
        tmp_path,
        active_specification=ACTIVE_SPEC,
        no_spec_reason=(
            "Defect fix with no specification of its own: restores the contract the "
            "module docstring already states."
        ),
    )

    refusal = spec_precedence_refusal(root, ["src/engineering_playbook/core.py"])

    assert refusal is not None, "an escape written by an earlier slice excused this one silently"
    assert "is not in this pull request" in refusal


def test_a_specification_that_is_not_under_specs_is_refused(tmp_path: Path) -> None:
    """Review measured two shapes that collapsed the comparison. A declared value with no file
    component made `spec_dir` become `specs/`, so touching ANY specification satisfied the gate --
    which is the eight-merge defect wearing a different hat. A value pointing outside `specs/`
    made any touched file satisfy it.
    """
    for declared in ["specs/003-no-stage-without-a-mechanism", "specs/003-x/", "spec.md"]:
        root = repo(tmp_path / declared.replace("/", "_"), active_specification=declared)

        refusal = spec_precedence_refusal(
            root, ["src/engineering_playbook/core.py", "specs/001-engineering-playbook/spec.md"]
        )

        assert refusal is not None, f"active_specification={declared!r} collapsed the comparison"

    outside = repo(tmp_path / "outside", active_specification="docs/requirements/prd.md")
    refusal = spec_precedence_refusal(
        outside, ["src/engineering_playbook/core.py", "docs/requirements/prd.md"]
    )

    assert refusal is not None
    assert "does not name a file under" in refusal


def test_the_reach_of_the_gate_is_pinned_not_merely_iterated() -> None:
    """Review measured that removing `tests/` and `extensions/` from the tuple left the suite
    green: the parametrized test iterates the very list it is supposed to hold, so narrowing the
    gate costs two fewer cases and nothing else.

    These are the paths that decide what this repository enforces and what a derived project
    receives. Each is named, so dropping one is a red test.
    """
    required = {
        "src/",
        "scripts/",
        "tests/",
        "profiles/",
        "templates/",
        ".claude/hooks/",
        ".claude/settings.json",
        ".github/workflows/",
        ".github/rulesets/",
        "pyproject.toml",
        "uv.lock",
        "bootstrap-engineering-template.yml",
    }

    assert required <= set(CODE_PREFIXES), (
        f"the gate stopped covering {sorted(required - set(CODE_PREFIXES))}, which are the files "
        "that decide what CI enforces or what a derived project installs"
    )


def test_the_files_that_decide_what_ci_enforces_are_gated(tmp_path: Path) -> None:
    """Named individually, with the reason each one matters, so the list above is not just a
    list. `pyproject.toml` carries strict typing, the ruff selection and pytest's strict markers;
    `.claude/settings.json` is what switches the PreToolUse hook on -- the hook was gated while
    its switch was not.
    """
    root = repo(tmp_path, active_specification=ACTIVE_SPEC)

    for path in ["pyproject.toml", "uv.lock", ".claude/settings.json", "profiles/workflows/x.yml"]:
        assert spec_precedence_refusal(root, [path]) is not None, f"{path} is not gated"


def test_the_workflow_reads_the_field_the_api_actually_returns() -> None:
    """The wiring that broke twice, pinned.

    `gh pr view --json files` normalises the field to `path`; the REST endpoint
    `pulls/<n>/files` names it `filename`. Swapping one for the other to lift the 100-file cap
    kept `.path`, so every line came back empty and the gate refused twice (runs 35641532687 and
    35642618171) before the filter was right. The Python side cannot see this -- it only receives
    whatever the shell produced -- so the assertion belongs here.
    """
    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/quality.yml").read_text(
        encoding="utf-8"
    )
    # Anchored on the step declaration, not on the phrase: the same words appear in the comment
    # that explains why the job needs `pull-requests: read`, and splitting there read the
    # permissions block instead of the step.
    step = workflow.split("- name: Specification claims this code", 1)[1].split("- name:", 1)[0]

    assert "pulls/$PR_NUMBER/files" in step, "the step stopped using the paginated endpoint"
    assert ".[].filename" in step, (
        "the REST endpoint returns `filename`; `.path` yields empty lines for every file"
    )


def test_verify_refuses_a_workflow_that_never_invokes_the_gate(tmp_path: Path) -> None:
    """The gate is well tested as a function; this holds the line that makes it a gate.

    Review measured that the mutation covering this assertion pointed at `tests/unit/test_core.py`,
    which is already red inside the mutation sandbox -- so it reported a detection while measuring
    nothing, and no test anywhere exercised the assertion. This is that test.
    """
    from engineering_playbook.core import verify_root

    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/quality.yml").read_text(
        encoding="utf-8"
    )
    root = tmp_path / "repo"
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/quality.yml").write_text(
        workflow.replace("validate-ci --pr-files", "validate-ci --nothing"), encoding="utf-8"
    )

    errors = verify_root(root).errors

    assert any("specification claims the changed code" in error for error in errors), (
        f"a workflow that never invokes the gate verified clean: {errors}"
    )


def test_verify_refuses_a_workflow_that_never_invokes_the_contract_gate(tmp_path: Path) -> None:
    """#65. `issue_contract_problems` is covered as a function; this covers it being CALLED.

    Review measured the gap by deleting the step from both copies of `quality.yml` and running the
    whole suite: 732 passed, unchanged. The mechanism this slice exists to add could be removed
    without a single test noticing -- the class the slice was opened to close, inside the slice.
    """
    from engineering_playbook.core import verify_root

    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/quality.yml").read_text(
        encoding="utf-8"
    )
    root = tmp_path / "repo"
    (root / ".github/workflows").mkdir(parents=True)
    (root / ".github/workflows/quality.yml").write_text(
        workflow.replace("validate-ci --issue-contract-body", "validate-ci --nothing"),
        encoding="utf-8",
    )

    errors = verify_root(root).errors

    assert any("card conforms to the contract" in error for error in errors), (
        f"a workflow that never invokes the contract gate verified clean: {errors}"
    )
