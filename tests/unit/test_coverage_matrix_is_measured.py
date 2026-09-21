"""T214 / FR-016 / AC-011: the coverage matrix is read by an instrument, not by a reader.

The matrix in `specs/003-no-stage-without-a-mechanism/spec.md` is the closing criterion of the
parent issue: AC-011 says it may contain no stage classified `ausente`. Until this suite existed,
nothing read it. It was prose, and prose drifts in both directions -- both measured on 2026-09-21,
both found by accident:

- Line 14 still read `ausente, hook nao instalado` long after T203 landed the control, with its
  bypass vectors documented in `core.py` and adversarial tests in
  `tests/unit/test_hooks_path_activation.py`. A stage that had been closed still counted as open.
- Line 18 read `ausente` while `.claude/hooks/enforce_delivery_pipeline.py` existed and was
  covered by tests -- and yet was not fully covered either, since `WRITE_VERB` turned out not to
  include `switch`. Prose cannot tell `ausente` from `parcial`.

WHY THIS IS NOT SIMPLY "REJECT EVERY `ausente`". That is AC-011's end state, and four stages are
still open, so a literal AC-011 assertion would be born red and get switched off -- which is how a
gate becomes decoration. What has value today is a PINNED INVENTORY, one per open classification:
the guard knows exactly which stages are `ausente` and which are `parcial`, knows the task that
closes each, and fails when either set changes without its inventory changing in the same edit.

THE ESCAPE THIS SUITE'S FIRST DRAFT LEFT OPEN, found by review and measured: reclassify an
`ausente` stage as `parcial, <anything containing a comma>`, drop it from the inventory, and the
whole suite stayed green -- AC-011 satisfied by editing prose. Two things close it. `parcial` is
pinned exactly like `ausente`, so leaving `ausente` means arriving somewhere equally declared. And
every row, in any classification, must cite an artifact that exists: a task in `tasks.md`, or a
path in this repository. `coberta` on its own was a claim no reader could check, which is what
made the fraudulent close indistinguishable from a real one.

DECLARED LIMIT, per NFR-005. The pins force the matrix and this file to change together; they do
not verify that the cited artifact actually implements the stage. A row can cite a real test that
tests something else. What is measured here is coordination and existence, not adequacy -- the
adequacy of each mechanism is what its own adversarial suite is for (FR-017).

A NOTE FOR T210, which closes stage 16: that task introduces the control that refuses a skipped
test case with no declared justification (FR-008/AC-005). The last test below is a deliberate,
justified skip. It must be written in whatever shape T210 ends up requiring, or that slice will
have to come back and rewrite this file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "specs/003-no-stage-without-a-mechanism/spec.md"
TASKS = ROOT / "specs/003-no-stage-without-a-mechanism/tasks.md"

#: The header the matrix opens with. The table is delimited by this line and the first blank line
#: after it, rather than by "whatever the row regex happened to match": a row written with a
#: leading space, or without its trailing pipe, is then a parse failure inside a known block
#: instead of a line silently skipped. Review measured both of those going unnoticed.
MATRIX_HEADER = "| # | Etapa | Classificacao | Requisito que a cobre |"

#: Stages with no enforcement point, and the task that closes each, keyed by row number and a
#: stable fragment of the stage's own text -- the pin is positional otherwise, and renumbering
#: would silently repoint it at other stages.
OPEN_STAGES: dict[int, tuple[str, str]] = {}

#: Stages with a mechanism and a known bypass vector, pinned the same way so that leaving
#: `ausente` means arriving somewhere equally declared rather than somewhere unexamined.
PARTIAL_STAGES: dict[int, tuple[str, str]] = {
    9: ("Ordem", "T207"),
    14: ("Execucao da bateria", "T203"),
    17: ("Verificacao do veredicto", "T208"),
    18: ("Sujeicao do agente", "T221"),
    20: ("Cadeia de rastreabilidade", "T212"),
}

_ROW = re.compile(r"^\|\s*(\d+)\s*\|([^|]*)\|([^|]*)\|(.*)\|\s*$")
_TASK = re.compile(r"\bT\d{3}\b")
_PATH = re.compile(r"`([\w./-]+\.(?:py|yml|yaml|json|md))`")


class Row:
    def __init__(self, number: int, stage: str, classification: str, notes: str) -> None:
        self.number = number
        self.stage = stage.strip()
        self.classification = classification.strip()
        self.notes = notes.strip()

    @property
    def verdict(self) -> str:
        """The classification proper, before any qualifier.

        Rows read `parcial, alcance limitado a ...` -- the qualifier is where the reach of a
        partial mechanism is stated, which FR-012 requires, so it stays in the text and is
        stripped only for the comparison.
        """
        return self.classification.split(",", 1)[0].strip()

    @property
    def text(self) -> str:
        return f"{self.classification} {self.notes}"


def matrix_block() -> list[str]:
    """The lines of the matrix table, header and separator included."""
    lines = SPEC.read_text(encoding="utf-8").splitlines()
    start = lines.index(MATRIX_HEADER)
    block: list[str] = []
    for line in lines[start:]:
        if not line.strip():
            break
        block.append(line)
    return block


@pytest.fixture(scope="module")
def block() -> list[str]:
    parsed = matrix_block()
    assert len(parsed) > 2, "the matrix table has no rows at all -- its shape changed"
    return parsed


@pytest.fixture(scope="module")
def rows(block: list[str]) -> list[Row]:
    parsed: list[Row] = []
    for line in block[2:]:
        match = _ROW.match(line)
        assert match is not None, (
            f"this line sits inside the matrix table and could not be parsed, so nothing below "
            f"can see it: {line!r}"
        )
        number, stage, classification, notes = match.groups()
        parsed.append(Row(int(number), stage, classification, notes))
    return parsed


def test_every_line_of_the_table_is_read(block: list[str], rows: list[Row]) -> None:
    """Integrity by delimitation, not by counting.

    Review measured two edits the counting version could not see: a stage appended with a leading
    space, and a stage appended without its trailing pipe. Both added an unmeasured stage to the
    matrix while the suite stayed green, and appending a stage is the most likely future edit.
    """
    assert len(rows) == len(block) - 2, "a line inside the table was not turned into a row"
    numbers = [row.number for row in rows]
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"the matrix rows are not a contiguous run starting at 1: {numbers}"
    )
    assert len(numbers) >= 20, (
        f"only {len(numbers)} stages are present; the matrix measured 20 on 2026-09-20 and "
        "stages are not removed, only reclassified"
    )


def test_the_vocabulary_is_the_one_the_specification_defines(rows: list[Row]) -> None:
    """The classification words are read out of the specification's own definitions paragraph.

    Held as a literal list in this file, the vocabulary was a second copy nothing pinned: review
    measured that adding a word here and using it in the matrix passed the whole suite. That is
    the same drift this slice exists to stop, one file over.
    """
    spec_text = SPEC.read_text(encoding="utf-8")
    paragraph = spec_text.split("Classificacao dos pontos de enforcement", 1)[1].split("\n\n", 1)[0]
    defined = set(re.findall(r"`([A-Za-z]+)`:", paragraph))

    assert defined >= {"servidor", "CI", "parcial", "ausente"}, (
        f"the specification stopped defining the classifications it used to: {sorted(defined)}"
    )
    unknown = {row.number: row.classification for row in rows if row.verdict not in defined}
    assert unknown == {}, (
        f"these stages carry a classification the specification never defines: {unknown}. "
        f"Defined there: {sorted(defined)}"
    )


def test_every_row_cites_something_that_exists(rows: list[Row]) -> None:
    """A row saying only `coberta` is a claim no reader can check.

    Review measured the consequence: reclassifying the four open stages and emptying the
    inventory in one edit was indistinguishable, to this suite, from four mechanisms being built.
    Every row now has to name a task or a path, and it has to resolve.
    """
    declared_tasks = TASKS.read_text(encoding="utf-8")
    uncited: list[int] = []
    dangling: dict[int, list[str]] = {}
    for row in rows:
        tasks = set(_TASK.findall(row.text))
        paths = set(_PATH.findall(row.text))
        if not tasks and not paths:
            uncited.append(row.number)
            continue
        missing = sorted(task for task in tasks if f"- {task}:" not in declared_tasks)
        missing += sorted(path for path in paths if not (ROOT / path).exists())
        if missing:
            dangling[row.number] = missing

    assert uncited == [], (
        f"these stages cite neither a task nor a path, so their classification cannot be "
        f"checked by anyone: {uncited}"
    )
    assert dangling == {}, f"these stages cite artifacts that do not exist: {dangling}"

    # A CLOSED STAGE MUST NAME AN ARTIFACT, NOT A PLAN. This is what stops the last escape the
    # review measured: reclassify the four `ausente` stages as `servidor` and empty the
    # inventory in one edit, and every check above still passed -- the rows went on citing the
    # tasks that were supposed to close them, and a task is a plan. `servidor` and `CI` are
    # claims that something exists and runs, so they have to point at a file somebody can open.
    planned_only = sorted(
        row.number
        for row in rows
        if row.verdict in {"servidor", "CI"} and not _PATH.findall(row.text)
    )
    assert planned_only == [], (
        f"these stages claim an active mechanism while citing only a task, which is a plan and "
        f"not a mechanism: {planned_only}. A `servidor` or `CI` row names the file that carries "
        "the control."
    )


def test_every_requirement_a_row_cites_exists(rows: list[Row]) -> None:
    spec_text = SPEC.read_text(encoding="utf-8")
    defined = set(re.findall(r"^- ((?:N?FR|AC)-\d{3}):", spec_text, flags=re.MULTILINE))
    assert defined, "no requirements were parsed from the specification at all"

    dangling: dict[int, list[str]] = {}
    for row in rows:
        cited = set(re.findall(r"(?:N?FR|AC)-\d{3}", row.text))
        unresolved = sorted(cited - defined)
        if unresolved:
            dangling[row.number] = unresolved

    assert dangling == {}, (
        f"these rows cite requirements the specification does not define: {dangling}"
    )


def _pin_holds(rows: list[Row], verdict: str, pin: dict[int, tuple[str, str]]) -> None:
    actual = {row.number for row in rows if row.verdict == verdict}
    assert actual == set(pin), (
        f"the matrix classifies stages {sorted(actual)} as `{verdict}`, while the pinned "
        f"inventory says {sorted(pin)}. Changing a stage's classification means changing this "
        "inventory in the same edit; doing either alone fails here."
    )
    by_number = {row.number: row for row in rows}
    misnamed = {
        number: by_number[number].stage
        for number, (fragment, _task) in pin.items()
        if fragment.lower() not in by_number[number].stage.lower()
    }
    assert misnamed == {}, (
        f"the pin is keyed by row number AND by a fragment of the stage's text so that "
        f"renumbering cannot silently repoint it; these no longer match: {misnamed}"
    )
    declared = TASKS.read_text(encoding="utf-8")
    absent = {
        number: task for number, (_fragment, task) in pin.items() if f"- {task}:" not in declared
    }
    assert absent == {}, f"these stages are pinned to tasks absent from tasks.md: {absent}"


def test_the_stages_without_a_mechanism_are_exactly_the_ones_declared_open(
    rows: list[Row],
) -> None:
    """THE pin, and the reason this suite exists. Line 14 read `ausente` for days after T203
    closed it, because nothing compared the matrix to anything.
    """
    _pin_holds(rows, "ausente", OPEN_STAGES)


def test_the_partial_stages_are_exactly_the_ones_declared_partial(rows: list[Row]) -> None:
    """The escape the first draft left open: `ausente` -> `parcial, <anything>` plus a one-line
    deletion from the inventory, and AC-011 reported itself satisfied. Leaving `ausente` now means
    arriving somewhere equally declared.
    """
    _pin_holds(rows, "parcial", PARTIAL_STAGES)


def test_a_partial_mechanism_states_its_reach(rows: list[Row]) -> None:
    """FR-012: the reach of each mechanism is declared. `parcial` alone is the claim "there is a
    bypass vector" without saying which, which is the assertion this specification exists to
    refuse. A comma is not a qualifier, so the qualifier has to carry words.
    """
    bare = {
        row.number: row.classification
        for row in rows
        if row.verdict == "parcial" and len(row.classification.split(",", 1)[-1].split()) < 3
    }

    assert bare == {}, f"these stages are `parcial` without naming what is not covered: {bare}"


def test_no_stage_is_left_without_a_mechanism(rows: list[Row]) -> None:
    """AC-011 itself, which this guard turns into a gate the moment the inventory empties.

    Written as a skip rather than an xfail so the remaining count stays visible in every run: the
    closing criterion of the parent issue is a number someone can read, not a state someone has to
    derive. It is a report with a latent assertion, not a gate -- stated plainly because a green
    skip in a CI log is otherwise read as "AC-011 verified".
    """
    absent = sorted(row.number for row in rows if row.verdict == "ausente")
    if absent:
        pytest.skip(
            f"AC-011 not yet satisfiable: {len(absent)} stage(s) still without a mechanism "
            f"({absent}), pinned to {sorted({task for _f, task in OPEN_STAGES.values()})}"
        )

    assert absent == []
