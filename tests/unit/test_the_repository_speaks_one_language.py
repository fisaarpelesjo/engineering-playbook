"""The repository is written in English, and the files that are not yet are named.

The owner decided on 2026-09-22: everything in English. Before that decision the split was by
layer and written down nowhere -- code, tests and commit messages in English; specs,
`docs/agents/`, `AGENTS.md` and `.claude/agents/` in Portuguese -- with outliers fitting neither.
Measured the same day: 196 files carried Portuguese, 1131 lines in total.

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

DECLARED LIMIT, per NFR-005: this measures words, not meaning. A sentence written in English that
quotes a Portuguese matrix row -- `| 14 | Execucao da bateria ... | ausente |` -- counts as
Portuguese here, and that is correct: the vocabulary of the matrix is Portuguese and changes when
the specification does, not before. Translating a quotation would stop it being a quotation.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#: Function words that do not occur in English prose, plus the accented characters. Two or more on
#: one line is the threshold: a single `que` or `para` shows up in identifiers and in quoted paths.
PORTUGUESE = re.compile(
    r"[ãõçáéíóúâêôàÃÕÇÁÉÍÓÚÂÊÔÀ]"
    r"|\b(?:nao|sao|esta|este|isso|porque|portanto|como|para|com|sem|pela|pelo|pelos|uma|umas|"
    r"dos|das|nos|nas|que|qual|quais|onde|quando|medido|medicao|arvore|ficheiro|ficheiros|etapa|"
    r"etapas|entrega|fatia|fatias|recusa|recusar|alcance|mecanismo|mecanismos|declarado|"
    r"declarada|coberta|aberto|fechado|parcial|ausente|corrida|corre|escreve|verificacao|"
    r"integracao|criacao|excepcao|razao|numero|numeros|ambos|apenas|ainda|depois|antes|sobre|"
    r"entre|cada|todos|toda|todas|outro|outra|mesmo|mesma|servidor|requisito|requisitos|"
    r"especificacao|tarefa|tarefas|proprio|propria|seguinte|primeiro|segunda)\b",
    re.IGNORECASE,
)

#: Extensions whose contents are prose or carry prose. Binary and lock files are not read.
TEXT_SUFFIXES = {".md", ".py", ".yml", ".yaml", ".json", ".txt", ".toml", ".cfg", ".ini"}

#: Paths excluded with their reason, so the exclusion is a decision and not a gap. Read by
#: `test_every_exclusion_is_still_needed`, which refuses an exclusion that stopped mattering.
EXCLUDED_PREFIXES = {
    ".project/checkpoints/": "a record of what happened, which a translation would falsify",
    "tests/fixtures/": "fixture content is data under test, not prose the repository speaks",
    "tests/unit/test_the_repository_speaks_one_language.py": (
        "this guard has to name Portuguese words in order to find them"
    ),
}


def tracked_text_files() -> list[str]:
    """Every tracked file this guard reads, in repository-relative posix form."""
    listed = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    return sorted(
        name
        for name in (line.strip() for line in listed)
        if name and Path(name).suffix in TEXT_SUFFIXES and not _is_excluded(name)
    )


def _is_excluded(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def portuguese_lines(name: str) -> list[str]:
    """The lines of this file that carry Portuguese, by the threshold above."""
    try:
        text = (ROOT / name).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    return [line for line in text.splitlines() if len(PORTUGUESE.findall(line)) >= 2]


def speaking_portuguese() -> set[str]:
    return {name for name in tracked_text_files() if portuguese_lines(name)}


#: Every tracked file that still carries Portuguese, measured on 2026-09-22: 97 files,
#: 1210 lines, out of 246 tracked text files read.
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
        ".project/last-ci-run.yml",
        ".project/state.yml",
        "AGENTS.md",
        "CLAUDE.md",
        "CONTRIBUTING.md",
        "ENGINEERING.md",
        "GEMINI.md",
        "MIGRATIONS.md",
        "README.md",
        "SECURITY.md",
        "bootstrap-engineering-template.yml",
        "docs/agents/AGENT_POLICY.md",
        "docs/agents/HANDOFF_PROTOCOL.md",
        "docs/agents/LOOP.md",
        "docs/agents/OWNER_STANDING_ORDERS.md",
        "docs/agents/RECOVERY_PROTOCOL.md",
        "docs/agents/REPORTING_CONTRACT.md",
        "docs/context/constraints.md",
        "docs/context/product.md",
        "docs/context/terminology.md",
        "docs/decisions/0001-single-client-hook-mechanism.md",
        "docs/delivery/README.md",
        "docs/requirements/README.md",
        "docs/requirements/project-requirements.md",
        "docs/standards/common/README.md",
        "profiles/stacks/README.md",
        "scripts/agent_watch/README.md",
        "scripts/agent_watch/watch_grid.py",
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
        "src/engineering_playbook/resources/SECURITY.md",
        "src/engineering_playbook/resources/docs/agents/AGENT_POLICY.md",
        "src/engineering_playbook/resources/docs/agents/HANDOFF_PROTOCOL.md",
        "src/engineering_playbook/resources/docs/agents/LOOP.md",
        "src/engineering_playbook/resources/docs/agents/OWNER_STANDING_ORDERS.md",
        "src/engineering_playbook/resources/docs/agents/RECOVERY_PROTOCOL.md",
        "src/engineering_playbook/resources/docs/agents/REPORTING_CONTRACT.md",
        "src/engineering_playbook/resources/docs/context/constraints.md",
        "src/engineering_playbook/resources/docs/context/product.md",
        "src/engineering_playbook/resources/docs/context/terminology.md",
        "src/engineering_playbook/resources/docs/delivery/README.md",
        "src/engineering_playbook/resources/docs/requirements/README.md",
        "src/engineering_playbook/resources/docs/requirements/project-requirements.md",
        "src/engineering_playbook/resources/docs/standards/common/README.md",
        "src/engineering_playbook/resources/profiles/stacks/README.md",
        "src/engineering_playbook/resources/templates/madr/template.md",
        "src/engineering_playbook/resources/templates/project/README.md",
        "src/engineering_playbook/resources/templates/project/requirements.md",
        "templates/madr/template.md",
        "templates/project/README.md",
        "templates/project/requirements.md",
        "tests/unit/test_ci_receipt.py",
        "tests/unit/test_coverage_matrix_is_measured.py",
        "tests/unit/test_delivery_git_failures.py",
        "tests/unit/test_git_hooks_pre_push_ruleset.py",
        "tests/unit/test_hook_mechanism_coexistence.py",
        "tests/unit/test_hooks_path_activation.py",
        "tests/unit/test_issue_gate.py",
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
    listed = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
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
