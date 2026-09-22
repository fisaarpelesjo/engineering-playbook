"""Whether a piece of text is written in Portuguese, decided in one place.

The owner decided on 2026-09-22 that this repository is written in English. Two guards enforce
that: `tests/unit/test_the_repository_speaks_one_language.py` over tracked files, and
`delivery.issue_contract_problems` over the issue a pull request closes. They asked the same
question with two copies of the answer, and review measured the copies already differing -- 83
words in one, 58 in the other, and the `TODO` collision handled in only one of them. Two copies of
a rule is the state this repository refuses to call a mechanism, so the rule lives here.

WHAT IS STRIPPED BEFORE MATCHING, each because it was measured producing a false refusal:

- URLs. `\\b` treats `.` and `-` as word boundaries, so `docs.github.com` contains `com`,
  `para-virtualized` contains `para`, and `sem-ver` contains `sem`. Measured: a title reading
  `Pin the docs link to docs.github.com` was refused as not English, and 217 of the file guard's
  hits came from `com` alone. This repository quotes run URLs constantly.
- `TODO` and `TODOs`, which collide with the Portuguese `todos` and are this repository's own
  vocabulary: the PRD carries eighty and issue #46 is named after that count.

THE THRESHOLDS, measured rather than chosen. One marker in a title, two in a line of prose. A
title is a sentence fragment and never reaches two -- `publish e merge escrevem bookkeeping depois
do push`, a real title from this board, carries exactly one after stripping. Over the 39 titles on
the board, a one-marker threshold produced a single false positive and it was `TODOs`.
"""

from __future__ import annotations

import re

#: Function words that do not occur in English prose, plus the accented characters. One list, used
#: by both guards, so neither can drift from the other.
PORTUGUESE = re.compile(
    r"[ãõçáéíóúâêôàÃÕÇÁÉÍÓÚÂÊÔÀ]"
    # `(?<![\\w.-])` and `(?![\\w-])` instead of `\\b`: a marker preceded by a dot is a host
    # suffix (`docs.github.com`) and one touching a hyphen is part of a compound
    # (`para-virtualized`, `sem-ver`). A TRAILING dot is deliberately not blocked, because that
    # is how a Portuguese sentence ends.
    r"|(?<![\w.-])(?:nao|sao|esta|este|isso|porque|portanto|como|para|com|sem|pela|pelo|pelos|"
    r"uma|umas|"
    r"dos|das|nos|nas|que|qual|quais|onde|quando|medido|medicao|arvore|ficheiro|ficheiros|etapa|"
    r"etapas|entrega|fatia|fatias|recusa|recusar|alcance|mecanismo|mecanismos|declarado|"
    r"declarada|coberta|aberto|fechado|parcial|ausente|corrida|corre|escreve|verificacao|"
    r"integracao|criacao|excepcao|razao|numero|numeros|ambos|apenas|ainda|depois|antes|sobre|"
    r"entre|cada|todos|toda|todas|outro|outra|mesmo|mesma|servidor|requisito|requisitos|"
    r"especificacao|tarefa|tarefas|proprio|propria|seguinte|primeiro|segunda)(?![\w-])",
    re.IGNORECASE,
)

#: A full URL, and this repository's own `TODO`. Hosts and hyphenated compounds are handled by the
#: boundaries in the pattern above rather than by stripping, so nothing is removed here that could
#: have hidden prose.
NOT_PROSE = re.compile(
    # A fenced or inline code span. Text inside backticks is QUOTED, not written: this repository
    # quotes its own Portuguese constantly -- the matrix row `| 14 | Execucao da bateria ... |`,
    # the vocabulary tokens for a stage's classification, the half-Portuguese error string that
    # `traceability_refusal` prints. Translating a quotation stops it being a quotation, so
    # quoting one must not count as speaking it. Measured: the body of issue #65 itself, written
    # in English ABOUT Portuguese, was refused by this control before this line existed.
    r"```[\s\S]*?```"
    r"|`[^`\n]*`"
    r"|https?://\S+"
    r"|\bTODOs?\b",
)


def portuguese_markers(text: str) -> list[str]:
    """The Portuguese markers in this text, with the known English collisions removed first."""
    return PORTUGUESE.findall(NOT_PROSE.sub(" ", text))


def speaks_portuguese(text: str, *, threshold: int = 2) -> bool:
    """True when this one line, or title, carries enough markers to be Portuguese."""
    return len(portuguese_markers(text)) >= threshold
