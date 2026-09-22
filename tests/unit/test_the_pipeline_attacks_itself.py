"""T215 / FR-017 / FR-018 / AC-012: the enumerated vectors get a suite that attacks them.

The mutation harness in `engineering_playbook.mutation` removes each mechanism and reports whether
anything noticed. Running it takes minutes, so it runs as its own CI job; what runs here is
everything that keeps the inventory honest between those runs.

WHY THE INVENTORY NEEDS ITS OWN GUARD. An inventory of controls is a second copy of the truth, and
this repository has now watched a second copy rot three separate times: the coverage matrix drifted
in both directions (#39), the skip inventory was right on one platform and wrong on the one CI
uses (#42), and the very first run of the harness produced one entry that had gone stale and one
that mutated a refusal's wording rather than the refusal. The pattern is stable enough to plan
around: whatever is duplicated gets pinned, or it lies.

WHAT IS NOT CLAIMED HERE. Passing these tests does not mean the pipeline has no bypass vectors.
NFR-005 is explicit that no such claim is made anywhere, and the vector table in spec 003 lists
four that are open. What is claimed is narrower: every mechanism the inventory names is held by a
test that fails without it, and the inventory has not drifted away from the code it names.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from engineering_playbook.mutation import (
    COVERED_STAGES,
    MUTATIONS,
    Mutation,
    apply_mutation,
    build_sandbox,
    classify,
)

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "specs/003-no-stage-without-a-mechanism/spec.md"


#: The mechanisms this inventory is pinned to -- EVERY one of them, and the equality below is
#: what makes that true rather than aspirational.
#:
#: Review measured that a floor -- `len >= 14` -- is edited on the same line as the thing it
#: guards: two edits emptied the harness to a single entry and both the suite and the CI job
#: reported total success. A named set cannot be relaxed by relaxing a number.
#:
#: WHY EQUALITY AND NOT `>=`. The subset form catches a mechanism being REMOVED and is blind to one
#: being ADDED without a name here -- so a new entry could be deleted later, with the matrix count
#: corrected in the same edit, and the whole suite would stay green. Review raised that in the
#: first round of #49, two entries were pinned, and the entry added in the third round repeated it.
#: Counting the eight inherited from earlier slices, the class returned more than three times, and
#: `ENGINEERING.md` is explicit about what happens then: the unit does not continue until there is
#: automated prevention that catches the whole class, not only the case that revealed it.
#:
#: So the gate is two-way. A mechanism that leaves the inventory fails here, and a mechanism that
#: joins it without being named here fails too. Adding an entry now costs one line in this set,
#: which is the point: the decision is written rather than implied.
PINNED_MECHANISMS = frozenset(
    {
        "a schema that drifts from the shipped copy is refused",
        "the shipped workflow is the root workflow minus the job it cannot run",
        "start refuses a HEAD the base already absorbed",
        "start refuses when the base ref cannot be read",
        "a specification claims the changed code",
        "a truncated file list is refused rather than reported on",
        "the escape must travel in the diff it excuses",
        "CI must invoke the specification-claims-this-code gate",
        "merge refuses content no run has signed",
        "merge refuses when gh cannot answer",
        "the signing job depends on every battery",
        "no other job holds the signing identity",
        "exactly one job mints the verdict",
        "an undeclared skip fails the run",
        "a declaration that stopped skipping is refused",
        "a stage cannot be closed by editing prose",
        "the shipped workflow matches the root outside the unshipped job, comments too",
        # Inherited from earlier slices, unpinned until now because `>=` could not notice them.
        "a branch records how it came to exist",
        "abbreviated long options are refused at git's own minimum",
        "base means the ref the server will use",
        "branch arguments are read the way git reads them",
        "listing options keep a pattern from reading as a branch name",
        "publish measures against the base the server will use",
        "status reports against the base the server will use",
        "the harness refuses branch writes outside the pipeline",
        "a file that still speaks Portuguese stays named",
        "the detector reaches Portuguese no word list can hold",
        "publish leaves no tree behind it",
        "a bookkeeping commit carries only bookkeeping",
        "publish stages its own records and nothing else",
        "a record is matched at a path boundary, not by prefix",
        "one marker in a short file is still a marker",
        "an issue may not claim a parent the API does not report",
        "CI must invoke the card-conforms-to-the-contract gate",
    }
)


def test_the_inventory_still_holds_every_mechanism_it_was_pinned_to() -> None:
    """A harness over an emptied inventory reports total success and measures nothing.

    Both directions, in ONE assertion, because the two sequential asserts this replaced diagnosed
    a rename badly: pytest stops at the first, so renaming a mechanism without updating the set
    read as "these mechanisms left the inventory" when none had left. The operator fixed half,
    re-ran, and only then saw the other half. Measured by review.

    The duplicate check is the last member of the class the two-way pin closes. A set of names
    cannot tell two entries apart when they share one, so a twenty-sixth entry pasted from an
    existing one joins the inventory unpinned and this guard sees twenty-five names either way.
    """
    mechanisms = [mutation.mechanism for mutation in MUTATIONS]
    held = set(mechanisms)

    assert len(held) == len(mechanisms), (
        "two entries share a `mechanism` name, so the pinned set below cannot tell them apart and "
        "an entry added by copy-paste would join the inventory without anyone naming it: "
        f"{sorted({name for name in mechanisms if mechanisms.count(name) > 1})}"
    )

    missing = sorted(PINNED_MECHANISMS - held)
    unpinned = sorted(held - PINNED_MECHANISMS)
    both = missing and unpinned
    assert not missing and not unpinned, (
        (
            f"this looks like a rename: {missing} left the inventory and {unpinned} arrived. "
            "Both change in the same edit -- the pinned set is the place the decision is written."
        )
        if both
        else (
            f"these mechanisms left the inventory: {missing}. Removing one is a decision, and a "
            "decision is made here by name rather than by editing a count."
        )
        if missing
        else (
            f"these mechanisms are in the inventory and not named here: {unpinned}. Add them: an "
            "entry nobody pinned can be deleted later with the matrix count corrected in the same "
            "edit, and nothing would notice."
        )
    )


@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: m.mechanism)
def test_every_entry_still_finds_the_code_it_claims_to_remove(mutation: Mutation) -> None:
    """The `inert` case, caught before the slow harness runs.

    An entry whose `find` text has moved removes nothing, and a mutation that removes nothing
    cannot be caught by any test -- so the harness would report it as an escape and send whoever
    reads it hunting for a missing test that is not missing. One entry was already in this state
    on the harness's first run.
    """
    target = ROOT / mutation.file

    assert target.is_file(), f"{mutation.file} does not exist"
    occurrences = target.read_text(encoding="utf-8").count(mutation.find)
    assert occurrences == 1, (
        f"the text this entry removes occurs {occurrences} times in {mutation.file}; an entry has "
        "to name exactly one control, or it removes more or less than it says"
    )


def test_every_entry_names_tests_that_exist_and_can_be_collected() -> None:
    """Pertinence, not just existence.

    The first version asserted the target FILE existed. One entry then pointed at
    `tests/unit/test_core.py`, which exists and contains nothing that exercises the control -- and
    that file is red inside the sandbox for unrelated reasons, so the harness read a pre-existing
    failure as a detection. Node ids are collected here, so an entry naming a test that does not
    exist fails before the slow harness ever runs.
    """
    targets = sorted({target for mutation in MUTATIONS for target in mutation.proves})
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-p",
            "no:cacheprovider",
            *targets,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, (
        f"the inventory names tests pytest cannot collect: {completed.stdout[-2000:]}"
    )


@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: m.mechanism)
def test_every_entry_names_a_node_id_rather_than_a_whole_file(mutation: Mutation) -> None:
    """A file-level target runs tests unrelated to the control, which is how a pre-existing
    failure got read as a detection.
    """
    for target in mutation.proves:
        assert "::" in target, f"{mutation.mechanism} targets the whole of {target}"


@pytest.mark.parametrize("mutation", MUTATIONS, ids=lambda m: m.mechanism)
def test_every_entry_cites_a_requirement_the_specification_defines(mutation: Mutation) -> None:
    """A mechanism held for no stated reason is a mechanism nobody can argue about."""
    defined = set(
        re.findall(r"^- ((?:N?FR|AC)-\d{3}):", SPEC.read_text(encoding="utf-8"), flags=re.MULTILINE)
    )
    cited = set(re.findall(r"(?:N?FR|AC)-\d{3}", mutation.requirement))

    assert cited, f"{mutation.mechanism} cites no requirement"
    assert cited <= defined, f"{mutation.mechanism} cites {sorted(cited - defined)}, undefined"


def test_a_mutation_actually_changes_the_sandbox(tmp_path: Path) -> None:
    """The harness's own arm, exercised: applying an entry has to alter the file it names.

    Without this, a harness bug that silently skipped the edit would report every mechanism as
    escaped, and a reader would conclude the suite covers nothing.
    """
    mutation = MUTATIONS[0]
    sandbox = tmp_path / "sandbox"
    build_sandbox(ROOT, sandbox)
    before = (sandbox / mutation.file).read_text(encoding="utf-8")

    refusal = apply_mutation(sandbox, mutation)

    assert refusal is None, refusal
    assert (sandbox / mutation.file).read_text(encoding="utf-8") != before


def test_a_stale_entry_is_reported_rather_than_applied(tmp_path: Path) -> None:
    """`inert` exists so a drifted inventory cannot read as a covered mechanism."""
    sandbox = tmp_path / "sandbox"
    build_sandbox(ROOT, sandbox)
    stale = Mutation(
        mechanism="a control that has moved",
        requirement="FR-017",
        stage=9,
        file=MUTATIONS[0].file,
        find="this text is not in any file in this repository",
        replace="",
        proves=MUTATIONS[0].proves,
    )

    refusal = apply_mutation(sandbox, stale)

    assert refusal is not None
    assert "no longer in the file" in refusal


def test_an_ambiguous_entry_is_refused(tmp_path: Path) -> None:
    """A fragment matching twice removes more than the entry names, so the result would not say
    which control was measured.
    """
    sandbox = tmp_path / "sandbox"
    build_sandbox(ROOT, sandbox)
    ambiguous = Mutation(
        mechanism="a fragment that is not one control",
        requirement="FR-017",
        stage=9,
        file=MUTATIONS[0].file,
        find="    return None",
        replace="    return None  # mutated",
        proves=MUTATIONS[0].proves,
    )

    refusal = apply_mutation(sandbox, ambiguous)

    assert refusal is not None
    assert "occurs" in refusal and "times" in refusal


def test_the_harness_reads_the_tree_and_never_writes_it(tmp_path: Path) -> None:
    """The self-reference this repository spent four slices removing, kept out of the harness.

    A mutation harness that edited the working tree to measure it would be doing exactly what
    `last_verified_commit` did: changing the thing it is reporting on.
    """
    mutation = MUTATIONS[0]
    original = (ROOT / mutation.file).read_text(encoding="utf-8")
    sandbox = tmp_path / "sandbox"

    build_sandbox(ROOT, sandbox)
    apply_mutation(sandbox, mutation)

    assert (ROOT / mutation.file).read_text(encoding="utf-8") == original, (
        "the harness modified the repository it was measuring"
    )


def test_every_open_vector_is_named_in_the_specification() -> None:
    """FR-018 asks the suite to exercise each enumerated vector. The ones still open cannot be
    exercised -- there is nothing to assert a refusal from -- so what is held here is that they
    stay enumerated rather than quietly disappearing from the table.
    """
    table = SPEC.read_text(encoding="utf-8").split("## Vectores de bypass", 1)[1]
    table = table.split("## Exclusoes", 1)[0]
    rows = [line for line in table.splitlines() if line.startswith("|") and "---" not in line]
    states = [row.split("|")[2].strip() for row in rows[1:]]

    assert states, "the vector table stopped parsing"
    assert states.count("aberto") >= 1, (
        "every vector reads as closed; NFR-005 says this specification does not establish the "
        "absence of bypass vectors, so a table with none open is a claim it declines to make"
    )
    assert states.count("fechado") >= 4, (
        f"only {states.count('fechado')} vectors read as closed; they were 4 on 2026-09-21 and "
        "closing one is a slice, not an edit"
    )


def synthetic(**overrides: object) -> Mutation:
    fields: dict[str, object] = {
        "mechanism": "a synthetic control",
        "requirement": "FR-017",
        "stage": 9,
        "file": MUTATIONS[0].file,
        "find": MUTATIONS[0].find,
        "replace": MUTATIONS[0].replace,
        "proves": ("tests/unit/t.py::test_x",),
    }
    fields.update(overrides)
    return Mutation(**fields)  # type: ignore[arg-type]


def test_a_named_test_that_was_green_and_went_red_is_the_only_detection() -> None:
    """THE decision, and the one the first version got wrong.

    `returncode != 0` means four different things -- a test failed, a module failed to import,
    pytest was misused, nothing was collected -- and only the first is a mechanism being held.
    """
    result = classify(synthetic(), 0, set(), None, {"tests/unit/t.py::test_x"})

    assert result.verdict == "caught"
    assert "tests/unit/t.py::test_x" in result.detail


def test_a_failure_that_was_already_there_is_not_a_detection() -> None:
    """The measured defect: an entry pointed at a file already red in the sandbox, and the failure
    set was identical with and without the mutation. It reported a detection for free.
    """
    already = {"tests/unit/t.py::test_x"}

    result = classify(synthetic(), 0, already, None, already)

    assert result.verdict == "escaped", (
        "a failure present before the mutation was counted as caused by it"
    )


def test_a_red_baseline_is_unusable_rather_than_caught() -> None:
    """If the targets were not green to begin with, nothing follows from them failing after."""
    result = classify(synthetic(), 1, {"tests/unit/t.py::test_x"}, None, None)

    assert result.verdict == "unusable"
    assert "not green before the mutation" in result.detail


def test_a_red_baseline_with_no_named_failure_says_so() -> None:
    """pytest exits non-zero for a collection error too, and that reads as nothing at all unless
    the report says which of the two happened.
    """
    result = classify(synthetic(), 2, set(), None, None)

    assert result.verdict == "unusable"
    assert "other than a failing test" in result.detail


def test_an_edit_that_did_nothing_is_inert_rather_than_escaped() -> None:
    """Both are failures of this harness, and conflating them would send whoever reads the report
    hunting for a missing test that is not missing.
    """
    result = classify(synthetic(), 0, set(), "the text is no longer in the file", None)

    assert result.verdict == "inert"
    assert not result.ok


def test_the_inventory_declares_the_matrix_rows_it_reaches() -> None:
    """HIGH finding from review: the inventory covers 6 of the 20 stages, and the prose implied
    it covered what the matrix calls closed. The reach is a fact read off the entries, and the
    vector table is classified against this number rather than against an impression.
    """
    assert {mutation.stage for mutation in MUTATIONS} == COVERED_STAGES
    assert len(COVERED_STAGES) <= 20
    assert {4, 15, 16, 17}.issubset(COVERED_STAGES)


def test_the_suite_records_what_it_does_not_claim() -> None:
    """T217: the NFR-005 limit is recorded in this suite, and the record is verified by reading
    the suite's own text -- which is the mechanism the task names.

    Without this, the paragraph saying what is NOT claimed can be deleted and nothing notices,
    leaving a suite that reads as proof of an absence nobody measured.
    """
    text = Path(__file__).read_text(encoding="utf-8")

    assert "WHAT IS NOT CLAIMED HERE" in text
    assert "NFR-005" in text
    assert "no bypass vectors" in text, (
        "the record has to say what is not claimed, not merely cite the requirement"
    )


def _terminators(data: bytes) -> set[str]:
    """Which line-ending styles this file uses.

    The STYLE, not the count. A mutation replaces text with text of a different shape, so the
    number of lines legitimately moves -- the first version of this test compared counts and
    reported three entries as rewriting endings when all they had done was replace a three-line
    block with a two-line one. What must not change is which terminators appear at all: a
    CRLF file staying CRLF, an LF file staying LF, and neither growing the other.
    """
    crlf = data.count(b"\r\n")
    bare_lf = data.count(b"\n") - crlf
    return {name for name, count in (("crlf", crlf), ("lf", bare_lf)) if count}


def test_applying_an_entry_does_not_rewrite_the_line_endings(tmp_path: Path) -> None:
    """The harness must change the one thing the entry names, and nothing else.

    Measured by review: `apply_mutation` used to read and write through `Path.read_text` /
    `write_text`, which translate `\n` to `os.linesep` on write. On Windows that rewrote every
    line of the file. Harmless while every target was compared by meaning -- and not harmless the
    moment entries appeared whose target is compared BYTE FOR BYTE, because then the harness's own
    write turns the target red with no drift planted at all, and `caught` stops being evidence.

    Asserted over every entry rather than the two that exposed it, so the next entry against a
    byte-compared artifact inherits the guarantee instead of rediscovering the defect.

    WHAT IT COMPARES, after review measured the first version comparing the wrong thing: the
    line-ending STYLE, not the count. A mutation replaces text with text of another shape, so the
    number of lines legitimately moves, and the count form reported three innocent entries as
    rewriting endings when all they had done was swap a three-line block for a two-line one.

    WHAT IT CANNOT SEE, declared per NFR-005 rather than left for the next reader to discover:
    this test reads the repository's own files, so it only bites where those files carry CRLF --
    a Windows working tree. On `ubuntu-latest`, where git hands every blob to the checkout as LF
    and `os.linesep` is `\n`, reverting `apply_mutation` to `write_text` changes nothing and this
    test stays green. Measured on 2026-09-22, both ways. Holding it on both platforms needs a
    synthetic CRLF fixture rather than the checkout's own endings, and that is worth doing.
    """
    problems: list[str] = []
    for entry in MUTATIONS:
        source = ROOT / entry.file
        if not source.is_file():
            continue
        target = tmp_path / entry.file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())

        before = target.read_bytes()
        refusal = apply_mutation(tmp_path, entry)
        if refusal is not None:
            problems.append(f"{entry.mechanism}: {refusal}")
            continue
        after = target.read_bytes()

        if _terminators(before) != _terminators(after):
            problems.append(
                f"{entry.mechanism}: applying it changed the file's line-ending style "
                f"({sorted(_terminators(before))} before, {sorted(_terminators(after))} after)"
            )

    assert problems == [], "\n".join(problems)
