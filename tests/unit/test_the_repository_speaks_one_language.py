"""The repository is written in English, and the files that are not yet are named.

The owner decided on 2026-09-22: everything in English. Before that decision the split was by
layer and written down nowhere -- code, tests and commit messages in English; specs,
`docs/agents/`, `AGENTS.md` and `.claude/agents/` in Portuguese -- with outliers fitting neither.
The count that stood here was taken with a different word list and a different file set, and no
instrument reproduced it; the one that counts is in the inventory below, measured by this file's
own rule.

WHY A GUARD AND NOT A TRANSLATION. Thirty-nine issues were normalised by hand that morning:
nineteen Portuguese bodies, two Portuguese titles, two issues with no label, two whose body
claimed `Sub-issue of #26` while the API relationship did not exist, and a Portuguese repository
description. Every one of them had passed every existing gate for weeks. Fixing them by hand is
the "identical by discipline, not by mechanism" state this repository refuses to call a
guarantee, and without a guard the next file drifts back the same way.

HOW THE INVENTORY WORKS, and why it is pinned in BOTH directions. `STILL_PORTUGUESE` names every
tracked file that still carries Portuguese. A file that starts carrying it fails here, and a file
that stops carrying it fails here too -- the second half is what makes the inventory shrink as
translation lands, instead of becoming a list nobody prunes. A one-way check would be satisfied by
adding a name, which is the fraud `test_coverage_matrix_is_measured.py` exists to refuse.

So this file is born with a long inventory on purpose. The inventory shrinking IS the progress
report for issue #65, and the day it empties this becomes the gate that keeps it empty.

WHAT IS OUT, declared rather than forgotten:

- `.project/checkpoints/*`: records of what happened at a point in time. Rewriting one would make
  a record say something it did not say. New checkpoints are written in English from this slice
  onward, so the boundary is visible in the history itself.
- `tests/fixtures/`: fixture content is data under test, not prose the repository speaks. A
  Portuguese requirements document is exactly what `validate_prd_document` has to accept.
- This file, which has to name Portuguese words in order to find them.
- `src/engineering_playbook/language.py`, the detector itself, for the same reason: its word list
  is nine lines of Portuguese, which is what it is for. It was added to the exclusions to close a
  review blocker and NOT added to this list, in the section titled "declared rather than
  forgotten" -- which review then pointed out.

DECLARED LIMIT, per NFR-005: this measures words, not meaning. A sentence written in English that
quotes a Portuguese matrix row -- `| 14 | Execucao da bateria ... | ausente |` -- counts as
Portuguese here, and that is correct: the vocabulary of the matrix is Portuguese and changes when
the specification does, not before. Translating a quotation would stop it being a quotation.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from engineering_playbook.language import document_speaks_portuguese, speaks_portuguese

ROOT = Path(__file__).resolve().parents[2]

#: The detector lives in `engineering_playbook.language`, used by this guard AND by
#: `delivery.issue_contract_problems`. Review measured two copies of it already diverging -- 83
#: words here, 58 there, and the `TODO` collision handled on one side only -- which is the
#: "identical by discipline" state this repository refuses everywhere else.

#: Extensions whose contents are prose or carry prose. Binary and lock files are not read.
#:
#: The empty string is here on purpose: a tracked file with no extension is usually a script, and
#: review measured two of them -- `scripts/git-hooks/pre-push` and its mirror -- carrying 22
#: Portuguese lines each, outside the inventory, outside the exclusions, and invisible to a guard
#: whose docstring claimed to name every tracked file that speaks Portuguese.
#:
#: A `NOT_TEXT = {"LICENSE"}` set stood here briefly and was removed: `LICENSE` decodes cleanly and
#: carries no Portuguese, so the exclusion protected nothing; it named only the root copy and not
#: the mirrored one; and its comment claimed an audit that no test performed. An exclusion with
#: none of the three properties it advertises is the #49 defect in miniature. A file that really
#: cannot be read now raises rather than being quietly declared English.
TEXT_SUFFIXES = {"", ".md", ".py", ".yml", ".yaml", ".json", ".txt", ".toml", ".cfg", ".ini"}

#: Paths excluded with their reason, so the exclusion is a decision and not a gap. Read by
#: `test_every_exclusion_is_still_needed`, which refuses an exclusion that stopped mattering.
EXCLUDED_PREFIXES = {
    ".project/checkpoints/": "a record of what happened, which a translation would falsify",
    "tests/fixtures/": "fixture content is data under test, not prose the repository speaks",
    "tests/unit/test_the_repository_speaks_one_language.py": (
        "this guard has to name Portuguese words in order to find them"
    ),
    "src/engineering_playbook/language.py": (
        "the detector itself: its word list is nine lines of Portuguese, which is what it is for. "
        "The exclusion was on the test file alone until review measured that the detector had "
        "moved to `src/` and its reason to be excluded had not moved with it"
    ),
}


#: Directories a filesystem walk must not descend into. Only consulted by the fallback below.
SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".pyright",
    "node_modules",
}


def listed_files() -> list[str]:
    """Every candidate file, from git when there is a repository and from the tree when not.

    `git ls-files` is the right source: it says TRACKED, so a scratch file someone left in the
    working directory is not held to the repository's language. But the mutation harness copies
    this tree into a sandbox with no `.git`, and that sandbox is exactly where this guard is put
    on trial -- without the fallback the entry that mutates it reports `unusable`, which means the
    run proved nothing. Measured on 2026-09-22, that is what it reported.

    The fallback walks instead, so it sees untracked files that `git ls-files` would not. Review
    measured that mattering: `build_sandbox` copied `.project/delivery/`, which is gitignored
    scratch, and the guard then reported a file that is not in the repository at all -- a clean
    sandbox red before any mutation was applied. The sandbox now excludes that directory, so the
    two listings agree on what a sandbox contains.
    """
    done = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if done.returncode == 0:
        return [line.strip() for line in done.stdout.split("\n") if line.strip()]
    found: list[str] = []
    for path in ROOT.rglob("*"):
        if path.is_file() and not any(part in SKIP_DIRS for part in path.parts):
            found.append(path.relative_to(ROOT).as_posix())
    return found


def tracked_text_files() -> list[str]:
    """Every file this guard reads, in repository-relative posix form."""
    return sorted(
        name
        for name in listed_files()
        if Path(name).suffix in TEXT_SUFFIXES and not _is_excluded(name)
    )


#: Suffixes where `"` is a quotation mark rather than a string delimiter. Everything else is read
#: as code, so a Portuguese message inside `print("...")` stays visible -- review measured that
#: stripping quotes everywhere hid 235 lines, including every error this software shows its
#: operator, and made seventeen files leave the inventory as if they had been translated.
PROSE_SUFFIXES = {".md", ".txt"}


def _is_prose(name: str) -> bool:
    return Path(name).suffix in PROSE_SUFFIXES


def _is_excluded(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


class UnreadableFileError(Exception):
    """A file this guard was told to read and could not.

    NFR-002: a control that cannot measure refuses. The first version returned `[]` here, which
    made an undecodable file count as English -- a fail-OPEN in a guard whose whole argument is
    failing closed, and the exact path a wrong entry in `TEXT_SUFFIXES` would take.
    """


def portuguese_lines(name: str) -> list[str]:
    """The lines of this file that carry Portuguese, by the shared detector's threshold."""
    try:
        text = (ROOT / name).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as failure:
        raise UnreadableFileError(
            f"{name} was selected for reading and could not be read ({failure}); either it is not "
            "text, in which case name it in `NOT_TEXT` or keep its suffix out of `TEXT_SUFFIXES`, "
            "or this guard is measuring nothing where it claims to measure"
        ) from failure
    return [line for line in text.splitlines() if speaks_portuguese(line, prose=_is_prose(name))]


def speaking_portuguese() -> set[str]:
    """Every file this guard calls Portuguese, by either rule -- per line, or whole document."""
    speaking: set[str] = set()
    for name in tracked_text_files():
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as failure:
            raise UnreadableFileError(f"{name} could not be read: {failure}") from failure
        if document_speaks_portuguese(text.splitlines(), prose=_is_prose(name)):
            speaking.add(name)
    return speaking


#: Every tracked file that still carries Portuguese, measured on 2026-09-22: 113 files,
#: 1589 lines, out of 256 tracked text files read.
#:
#: This list is the work item of issue #65 made countable. It shrinks as translation lands, and
#: the test below refuses both directions -- a file joining it, and a file that stopped needing
#: to be in it. The second half is what makes it shrink honestly instead of becoming a list
#: nobody prunes.
STILL_PORTUGUESE = frozenset(
    {
        ".claude/agents/implementer.md",
        ".claude/agents/measurer.md",
        ".claude/agents/researcher.md",
        ".claude/agents/reviewer.md",
        ".claude/agents/security-reviewer.md",
        ".claude/agents/test-engineer.md",
        "AGENTS.md",
        "CLAUDE.md",
        "CONTRIBUTING.md",
        "ENGINEERING.md",
        "GEMINI.md",
        "MIGRATIONS.md",
        "README.md",
        "REVIEW.md",
        "SECURITY.md",
        "bootstrap-engineering-template.yml",
        "docs/agents/AGENT_POLICY.md",
        "docs/agents/HANDOFF_PROTOCOL.md",
        "docs/agents/LOOP.md",
        "docs/agents/OWNER_STANDING_ORDERS.md",
        "docs/agents/RECOVERY_PROTOCOL.md",
        "docs/agents/REPORTING_CONTRACT.md",
        "docs/context/architecture.md",
        "docs/context/constraints.md",
        "docs/context/product.md",
        "docs/context/terminology.md",
        "docs/decisions/0000-use-madr.md",
        "docs/decisions/0001-single-client-hook-mechanism.md",
        "docs/delivery/README.md",
        "docs/requirements/README.md",
        "docs/requirements/project-requirements.md",
        "docs/standards/common/README.md",
        "extensions/README.md",
        "profiles/stacks/README.md",
        "profiles/workflows/lite.yml",
        "profiles/workflows/standard.yml",
        "profiles/workflows/strict.yml",
        "scripts/agent_watch/README.md",
        "scripts/agent_watch/watch_grid.py",
        "scripts/git-hooks/pre-push",
        "specs/001-engineering-playbook/plan.md",
        "specs/001-engineering-playbook/spec.md",
        "specs/001-engineering-playbook/tasks.md",
        "specs/002-the-issue-is-the-contract/plan.md",
        "specs/002-the-issue-is-the-contract/spec.md",
        "specs/002-the-issue-is-the-contract/tasks.md",
        "specs/003-no-stage-without-a-mechanism/plan.md",
        "specs/003-no-stage-without-a-mechanism/spec.md",
        "specs/003-no-stage-without-a-mechanism/tasks.md",
        "specs/004-the-pipeline-state/plan.md",
        "specs/004-the-pipeline-state/spec.md",
        "specs/004-the-pipeline-state/tasks.md",
        "src/engineering_playbook/attestation.py",
        "src/engineering_playbook/commands.py",
        "src/engineering_playbook/core.py",
        "src/engineering_playbook/delivery.py",
        "src/engineering_playbook/local_ci.py",
        "src/engineering_playbook/mutation.py",
        "src/engineering_playbook/receipt.py",
        "src/engineering_playbook/resources/.claude/agents/implementer.md",
        "src/engineering_playbook/resources/.claude/agents/measurer.md",
        "src/engineering_playbook/resources/.claude/agents/researcher.md",
        "src/engineering_playbook/resources/.claude/agents/reviewer.md",
        "src/engineering_playbook/resources/.claude/agents/security-reviewer.md",
        "src/engineering_playbook/resources/.claude/agents/test-engineer.md",
        "src/engineering_playbook/resources/AGENTS.md",
        "src/engineering_playbook/resources/CLAUDE.md",
        "src/engineering_playbook/resources/CONTRIBUTING.md",
        "src/engineering_playbook/resources/ENGINEERING.md",
        "src/engineering_playbook/resources/GEMINI.md",
        "src/engineering_playbook/resources/MIGRATIONS.md",
        "src/engineering_playbook/resources/README.md",
        "src/engineering_playbook/resources/REVIEW.md",
        "src/engineering_playbook/resources/SECURITY.md",
        "src/engineering_playbook/resources/docs/agents/AGENT_POLICY.md",
        "src/engineering_playbook/resources/docs/agents/HANDOFF_PROTOCOL.md",
        "src/engineering_playbook/resources/docs/agents/LOOP.md",
        "src/engineering_playbook/resources/docs/agents/OWNER_STANDING_ORDERS.md",
        "src/engineering_playbook/resources/docs/agents/RECOVERY_PROTOCOL.md",
        "src/engineering_playbook/resources/docs/agents/REPORTING_CONTRACT.md",
        "src/engineering_playbook/resources/docs/context/architecture.md",
        "src/engineering_playbook/resources/docs/context/constraints.md",
        "src/engineering_playbook/resources/docs/context/product.md",
        "src/engineering_playbook/resources/docs/context/terminology.md",
        "src/engineering_playbook/resources/docs/decisions/0000-use-madr.md",
        "src/engineering_playbook/resources/docs/delivery/README.md",
        "src/engineering_playbook/resources/docs/requirements/README.md",
        "src/engineering_playbook/resources/docs/requirements/project-requirements.md",
        "src/engineering_playbook/resources/docs/standards/common/README.md",
        "src/engineering_playbook/resources/extensions/README.md",
        "src/engineering_playbook/resources/profiles/stacks/README.md",
        "src/engineering_playbook/resources/profiles/workflows/lite.yml",
        "src/engineering_playbook/resources/profiles/workflows/standard.yml",
        "src/engineering_playbook/resources/profiles/workflows/strict.yml",
        "src/engineering_playbook/resources/scripts/git-hooks/pre-push",
        "src/engineering_playbook/resources/templates/madr/template.md",
        "src/engineering_playbook/resources/templates/project/README.md",
        "src/engineering_playbook/resources/templates/project/requirements.md",
        "templates/madr/template.md",
        "templates/project/README.md",
        "templates/project/requirements.md",
        "tests/unit/test_ci_receipt.py",
        "tests/unit/test_code_names_its_spec.py",
        "tests/unit/test_coverage_matrix_is_measured.py",
        "tests/unit/test_delivery_git_failures.py",
        "tests/unit/test_git_hooks_pre_push_ruleset.py",
        "tests/unit/test_hook_mechanism_coexistence.py",
        "tests/unit/test_hooks_path_activation.py",
        "tests/unit/test_issue_gate.py",
        "tests/unit/test_ruleset_reconciliation.py",
        "tests/unit/test_signed_verdict_leaves_the_tree.py",
        "tests/unit/test_start_measures_its_base.py",
        "tests/unit/test_the_chain_is_verified.py",
    }
)


def test_no_file_starts_speaking_portuguese() -> None:
    """The half that protects the future: nothing new arrives in Portuguese."""
    arrived = sorted(speaking_portuguese() - STILL_PORTUGUESE)

    assert arrived == [], (
        f"these files carry Portuguese and are not in the inventory: {arrived}. The repository "
        "is written in English (owner's decision, 2026-09-22); if one of these is quoted evidence "
        "that must stay as it is, add it to the inventory with the reason, or to "
        "`EXCLUDED_PREFIXES` if it is not prose the repository speaks."
    )


def test_a_translated_file_leaves_the_inventory() -> None:
    """The half that makes the inventory shrink: a name kept after the file was translated is a
    claim that work remains where it does not, and the list stops being a measurement.
    """
    stale = sorted(STILL_PORTUGUESE - speaking_portuguese())

    assert stale == [], (
        f"these files no longer carry Portuguese and are still listed: {stale}. Remove them "
        "from `STILL_PORTUGUESE` -- the inventory is the progress report for #65, and a name "
        "nobody removes turns it into decoration."
    )


def test_every_exclusion_is_still_needed() -> None:
    """An exclusion whose reason expired is the defect #49 was opened for, one directory over.

    Measured there: `.project/schemas/*` sat on an exclusion list long after the two copies had
    become identical, protecting nothing and hiding the next hand edit. So each exclusion here has
    to still match something, or be removed.
    """
    listed = listed_files()
    unused = sorted(
        prefix
        for prefix in EXCLUDED_PREFIXES
        if not any(name.startswith(prefix) for name in listed)
    )

    assert unused == [], (
        f"these exclusions match nothing in the repository any more: {unused}. An exclusion "
        "whose reason expired is how a guard stops guarding without anyone noticing."
    )


def test_the_guard_reads_something() -> None:
    """A guard over an empty file list passes for the wrong reason. Floor, not an exact count,
    because files are added and removed and the number moves.
    """
    read_files = tracked_text_files()

    assert len(read_files) >= 200, (
        f"only {len(read_files)} tracked text files were read; the walk or `git ls-files` may be "
        "broken rather than the repository having shrunk"
    )
    for expected in ("ENGINEERING.md", "AGENTS.md", "src/engineering_playbook/delivery.py"):
        assert expected in read_files, f"{expected} is not being read by this guard"


#: The sentence that carries the three numbers. Read by the test below, so it cannot go stale.
INVENTORY_HEADLINE = re.compile(
    r"#: Every tracked file that still carries Portuguese, measured on [\d-]+: (\d+) files,\n"
    r"#: (\d+) lines, out of (\d+) tracked text files read\."
)


def test_the_numbers_in_this_file_are_the_numbers_it_measures() -> None:
    """The third occurrence of a class, so the gate catches the class.

    `ENGINEERING.md` ledger row 2 says a number entering a report is measured AFTER the last edit
    of the slice. This file has broken it twice: 1210 when the tree said 1223, then 1248 when it
    said 1251 -- the second time in a sentence that explicitly claimed freshness. Both were found
    by review, neither by anything that runs.

    `ENGINEERING.md` is also explicit about what happens at the third occurrence: the unit does not
    continue until there is automated prevention for the whole class, not for the case that
    revealed it. This is that prevention. The numbers are now unwritable by hand: editing the file
    moves them, and the next run says so.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    found = INVENTORY_HEADLINE.findall(source)

    # `search` took the FIRST match, and review defeated it with a decoy: set the real headline to
    # nonsense and paste a correct-looking copy above it, and this test read the copy and passed
    # while the number was wrong by three orders of magnitude. A positional pin with no uniqueness
    # check is the hazard `test_coverage_matrix_is_measured.py` documents about its own pins.
    assert len(found) == 1, (
        f"the inventory headline matches {len(found)} times, not once. At zero it is gone or "
        "reworded and nothing holds the numbers; above one, this test cannot tell which copy is "
        "the real one, which is exactly how a decoy would pass."
    )
    match = INVENTORY_HEADLINE.search(source)
    assert match is not None

    speaking = sorted(speaking_portuguese())
    claimed = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
    measured = (
        len(speaking),
        sum(len(portuguese_lines(name)) for name in speaking),
        len(tracked_text_files()),
    )

    assert claimed == measured, (
        f"the headline says {claimed} (files, lines, read) and the tree measures {measured}. "
        "Numbers are taken after the last edit of the slice, not before it -- and this file's own "
        "edits move them, which is exactly how the previous two went stale."
    )


#: Real text from this repository, each line paired with the verdict the detector MUST return and
#: with the reason it is here. Every Portuguese sample below was, at some point in this slice,
#: called English by a version of the detector that shipped.
#:
#: WHY THIS EXISTS AND THE INVENTORY DOES NOT COVER IT. `STILL_PORTUGUESE` is regenerated FROM the
#: detector. Weaken the detector and the inventory shrinks, the pin is updated to match, and the
#: shrinking reads as translation progress -- so the one artifact meant to report this work is
#: structurally incapable of reporting its own instrument breaking. It happened twice. Stripping
#: double-quoted spans everywhere dropped 18 files, 17 of them code, and it was reported here as
#: progress; a marker floor of 2 then dropped `extensions/README.md` in both copies, the only
#: files the whole-document rule reaches on its own. Both were caught by review reading prose,
#: which is the "identical by discipline, not by mechanism" state this repository refuses to call
#: a guarantee everywhere else.
#:
#: These samples are fixed. They do not move when the detector does, so a detector that stops
#: seeing them goes red instead of quietly reporting a smaller number.
SPEAKS_PORTUGUESE = (
    # Reached only by morphology, and EVERY marker in these two samples is morphological: the
    # first version of them carried `requisitos` and `nao` as well, the mutation harness removed
    # the morphology alternative, both samples still flagged on the word list alone, and the
    # entry came back `escaped`. A sample that proves a rule has to fail without that rule and
    # without nothing else. `REVIEW.md` is the document a reviewer is required to read first, and
    # `aderencia`, `privacidade`, `portabilidade` and `manutencao` were all invisible in it.
    (
        "REVIEW.md, one marker before morphology",
        ("Priorize aderencia, seguranca e portabilidade.",),
        True,
    ),
    # Also morphology, also morphology-only. Thirteen lines of Portuguese carrying one listed
    # marker, density 0.077 -- under every floor, so the whole file sat outside the inventory.
    (
        "standard.yml, word list blind",
        ('  - "funcionalidade normal"', '  - "refatoracao delimitada"'),
        False,
    ),
    # Caught only once double-quote stripping was scoped to prose. This is a message the software
    # PRINTS TO ITS OPERATOR, and it was invisible to the guard built to find it.
    (
        "an operator-facing message in code",
        ('    raise RuntimeError("git nao esta disponivel, portanto nada foi medido")',),
        False,
    ),
    # The whole-document rule, and nothing else, reaches this one: one marker, two written lines,
    # density 0.50. A floor of 2 removed it, and it is the only file in the tree that a floor of 2
    # removes -- in both copies.
    (
        "extensions/README.md, reached only by density",
        (
            "# Extensions",
            "",
            "Espaco reservado para presets ou extensoes do Spec Kit. Use release estavel fixada.",
        ),
        True,
    ),
)

#: The other direction, and it is the one with teeth. Every line here is ordinary English that a
#: wider detector refused, or would refuse. A false positive in `issue_contract_problems` blocks a
#: correct pull request with no override, so the reach of the word list is bounded by this tuple
#: and not by how much Portuguese it would be satisfying to catch.
STAYS_ENGLISH = (
    # The eight function words that were added, measured, and taken back out: `de`, `da`, `em`,
    # `era`, `ate`, `ha`, `num`, `numa`.
    ("function words", ("The de facto default is an em dash, not a hyphen.",), True),
    ("more function words", ("Rename num to count, and the build ate the cache.",), True),
    # Quoting is not speaking. A real pull request body from this session was refused for naming
    # this repository's own ledger section in English prose.
    (
        "English prose quoting a Portuguese heading",
        ('The ledger section "Erros que ja custaram uma volta" now has two rows.',),
        True,
    ),
    # A host suffix is not a word, which is what the dot in the lookbehind is for.
    ("a host name", ("See docs.github.com for the sub-issues API.",), True),
    # `-vel` and `-veis` are out of the morphology rule because of exactly this line.
    ("English words ending in -vel", ("A toplevel module, a novel approach, travel time.",), True),
)


def test_the_detector_still_catches_what_it_was_built_to_catch() -> None:
    """Each sample was called English by a detector that shipped during this slice."""
    missed = [
        f"{label}: {lines[0]}"
        for label, lines, prose in SPEAKS_PORTUGUESE
        if not document_speaks_portuguese(list(lines), prose=prose)
    ]
    assert not missed, (
        "the detector no longer sees Portuguese it used to see:\n  "
        + "\n  ".join(missed)
        + "\n\nThe inventory above cannot tell you this. It is regenerated from the detector, so "
        "this failure would otherwise arrive as a SMALLER number of files left to translate."
    )


def test_the_detector_still_lets_english_through() -> None:
    """A false positive here refuses a correct pull request, with no override to reach for."""
    refused = [
        f"{label}: {lines[0]}"
        for label, lines, prose in STAYS_ENGLISH
        if document_speaks_portuguese(list(lines), prose=prose)
    ]
    assert not refused, (
        "the detector now refuses ordinary English:\n  "
        + "\n  ".join(refused)
        + "\n\nWidening the word list is bounded by this test. A gate that goes red on correct "
        "work is a gate somebody switches off."
    )


#: The ten Portuguese titles the reach figure in `language.py` is measured against. They lived in
#: that docstring as a number with no sample behind it, quoted through five revisions and checked
#: in none -- review could not reproduce it and said so. A number whose sample is not written down
#: cannot be re-measured after the rule changes, and this rule changed three times.
#:
#: These are written in the register this board actually uses. The first three are the ones the
#: docstring has always named as misses: a title built only from articles, prepositions and verbs
#: English also uses scores nothing, and that is the declared ceiling of a word-list detector.
PORTUGUESE_TITLES = (
    "A issue e o contrato",
    "O estado do pipeline",
    "Corrigir o erro do hook",
    "Publicar deixa a arvore suja",
    "Nenhuma etapa sem um mecanismo",
    "O repositorio fala uma lingua so",
    "Adicionar validacao de dependencias",
    "Melhorar a cobertura da matriz",
    "Remover a duplicacao do detector",
    "O gate nao mede o que declara",
)

#: The reach, pinned in BOTH directions for the reason the inventory is: a one-sided assertion is
#: satisfied by a rule that catches everything, which is the fraud this repository refuses. Going
#: UP is good news and still fails here, because the sentence in `language.py` that declares the
#: limit would otherwise be quietly wrong in the direction that flatters it.
TITLE_REACH = 6


def test_the_declared_reach_over_titles_is_the_measured_one() -> None:
    """`language.py` declares 6 of 10 under NFR-005. This is where that 6 comes from."""
    caught = [
        title for title in PORTUGUESE_TITLES if speaks_portuguese(title, threshold=1, prose=True)
    ]
    assert len(caught) == TITLE_REACH, (
        f"the detector now catches {len(caught)} of {len(PORTUGUESE_TITLES)} sample titles, not "
        f"{TITLE_REACH}. If that is an improvement, say so in the DECLARED LIMIT paragraph of "
        "`language.py` and move this pin -- the limit is declared per NFR-005, and a declared "
        "limit that no longer matches the instrument is worse than no limit at all."
    )
