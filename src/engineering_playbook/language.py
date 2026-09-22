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

THE THRESHOLDS. One marker in a title, two in a line of prose. A title is a sentence fragment and
never reaches two -- `publish e merge escrevem bookkeeping depois do push`, a real title from this
board, carries exactly one after stripping.

THE REACH, measured on BOTH sides, because the first version of this paragraph measured only one
and read as a sufficiency claim it had not earned. Review caught that: over the 45 issue titles on
this board, the one-marker threshold produces ZERO false positives -- but against ten Portuguese
titles, real and idiomatic, the word list as first written caught three. Articles, prepositions
and common verbs were missing, so any short title built from them scored nothing.

Function words were added and then mostly taken back out, and the measurement is why. With
`de`, `da`, `em`, `era`, `ate`, `ha`, `num` and `numa` in the list the same ten titles measure 7
of 10 -- and ordinary English sentences are refused: `an em dash`, `de facto defaults`, `da
Vinci`, `the modern era`, `the build ate the cache`, `rename num to count`. Without them the word
list alone caught 4 of 10; with the morphology rule below it catches 6 of 10, and `validacao` and
`duplicacao` are two of the two it gained.

Those ten titles are no longer a number in a paragraph. They are `PORTUGUESE_TITLES` in
`tests/unit/test_the_repository_speaks_one_language.py`, and the 6 is pinned there in both
directions, because this figure was quoted through five revisions of this docstring and verified
in none of them -- review said it could not reproduce it, and it was right.

The other side was verified against the API rather than reasoned about, on 2026-09-22: all 45
issue titles on this board, open and closed, and the detector flags ZERO of them.

The trade was decided by this repository's own ledger: a gate that goes red on correct work is a
gate somebody switches off. A missed Portuguese title is caught later by the file guard and by
review; a refused English title blocks a correct pull request with no override.

So the list carries no word English also uses. `do`, `so`, `no`, `a`, `e`, `o`, `as`, `de`, `da`,
`em`, `era`, `ate`, `num` all stay out, however common they are in Portuguese.

DECLARED LIMIT, per NFR-005: the reach is 6 of 10 on that sample, and a Portuguese title built
only from articles, prepositions and verbs English also uses passes -- `A issue e o contrato`,
`O estado do pipeline` and `Corrigir o erro do hook` are the three in the sample that do. What
this control guarantees is that the two titles which actually got through -- both carrying
content words -- would not get through again.

THREE MORE WAYS PAST IT, measured by review rather than reasoned about, and declared because a
weakness left unsaid is the defect this repository keeps paying for:

- a marker glued to a hyphen is invisible, and `requisitos nao-funcionais` is ordinary Portuguese
  spelling. The boundary that removes `para-virtualized` removes this too; it is the price.
- a marker glued to this repository's own `--` em-dash is invisible for the same reason.
- a line wrapped ENTIRELY in backticks scores zero. "Quoting is not speaking" is the rule, and
  nothing here distinguishes a quotation from a whole line wrapped to look like one.

No counts in this paragraph. Two stood here, went stale twice, and the second time they hid a
blocker: they told a reader the strippers cost eleven lines while the double-quote rule was
costing two hundred and forty-six. What the strippers currently remove is measurable from the
inventory itself, which is under a gate; a number retyped here is not.
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
    r"|(?<![\w.-])(?:ao|aos|ser|sera|foi|seu|sua|seus|suas|ja|mais|"
    r"muito|tambem|entao|assim|porem|contudo|alem|desde|durante|conforme|perante|"
    r"nao|sao|esta|este|isso|porque|portanto|como|para|com|sem|pela|pelo|pelos|"
    r"uma|umas|"
    r"dos|das|nos|nas|que|qual|quais|onde|quando|medido|medicao|arvore|ficheiro|ficheiros|etapa|"
    r"etapas|entrega|fatia|fatias|recusa|recusar|alcance|mecanismo|mecanismos|declarado|"
    r"declarada|coberta|aberto|fechado|parcial|ausente|corrida|corre|escreve|verificacao|"
    r"integracao|criacao|excepcao|razao|numero|numeros|ambos|apenas|ainda|depois|antes|sobre|"
    r"entre|cada|todos|toda|todas|outro|outra|mesmo|mesma|servidor|requisito|requisitos|"
    r"especificacao|tarefa|tarefas|proprio|propria|seguinte|primeiro|segunda)(?![\w-])"
    # Morphology, not vocabulary. A word list cannot reach accent-stripped Portuguese written in
    # content words: `profiles/workflows/standard.yml` is Portuguese from its first line to its
    # last -- `funcionalidade normal`, `correcao nao critica`, `refatoracao delimitada` -- and
    # carried exactly ONE listed marker, which left it out of the inventory entirely.
    #
    # These endings have no English counterpart, and that claim was measured rather than assumed:
    # across every alphabetic token of four letters or more in every tracked text file, 425 tokens
    # match and 424 are Portuguese. The single exception decides the shape of the rule.
    #
    # `-vel` and `-veis` are deliberately NOT here, and `toplevel` is the exception that keeps them
    # out. `level`, `novel`, `travel` and `marvel` are excluded only by the four-character prefix,
    # which is a margin too thin to trust in a corpus this one does not control. The cost is
    # `disponivel`, `estavel`, `possivel` and `variavel`; measured, every file carrying those
    # carries one of the endings below as well, so no file is lost by leaving them out.
    r"|(?<![\w.-])\w{4,}(?:coes|cao|dade|dades|ncia|ncias|mente)(?![\w-])",
    re.IGNORECASE,
)

#: A full URL, and this repository's own `TODO`. Hosts and hyphenated compounds are handled by the
#: boundaries in the pattern above rather than by stripping, so nothing is removed here that could
#: have hidden prose.
NOT_PROSE = re.compile(
    # An inline code span -- NOT a fenced block: both callers split by lines before asking, so a
    # fenced alternative could never match and review measured it unreachable. A fenced Portuguese
    # block is therefore still counted, line by line, which is the answer this guard wants.
    #
    # Text inside backticks is QUOTED, not written: this repository
    # quotes its own Portuguese constantly -- the matrix row `| 14 | Execucao da bateria ... |`,
    # the vocabulary tokens for a stage's classification, the half-Portuguese error string that
    # `traceability_refusal` prints. Translating a quotation stops it being a quotation, so
    # quoting one must not count as speaking it. Measured: the body of issue #65 itself, written
    # in English ABOUT Portuguese, was refused by this control before this line existed.
    r"`[^`\n]*`"
    r"|https?://\S+"
    r"|\bTODOs?\b",
)

#: Double-quoted spans, stripped ONLY from prose. In an issue body or a Markdown document `"` is a
#: quotation mark, and review measured a real pull request body refused for naming this
#: repository's own ledger section in ordinary English. In Python, YAML and JSON `"` is a string
#: delimiter, and 145 of the 254 text files this guard reads carry one of those three suffixes --
#: 80 `.py`, 50 `.yml`, 15 `.json` -- against 99 of `.md`. The number that stood here was 195,
#: which no reading of the tree reproduces; it was written from memory in the paragraph explaining
#: why hand-written numbers had just been removed from this file.
#:
#: DECLARED LIMIT, per NFR-005. A fenced code block inside a `.md` file is read as prose, so a
#: double-quoted Portuguese string inside one is stripped and not counted. Measured across the
#: whole tree: 16 lines, 12 of them inside fences, and ZERO files change verdict -- every file
#: carrying one is already in the inventory for other lines. The undercount is 16 lines of 1590.
#: Compare the state this switch replaced, which hid 235 lines and 17 whole files.
#:
#: Stripping it everywhere made every Portuguese message the software PRINTS TO ITS OPERATOR
#: invisible -- `git nao esta disponivel, portanto nada foi medido`, `a base nao foi medida`,
#: `nenhum arquivo mudado cai sob os caminhos que este workflow declara`. Measured: 235 of the 246
#: lines the strippers removed, and 17 of the 18 files that left the inventory left because of it
#: rather than because anything was translated. It was reported as progress.
QUOTED_PROSE = re.compile(r'"[^"\n]*"')


def portuguese_markers(text: str, *, prose: bool = False) -> list[str]:
    """The Portuguese markers in this text, with the known English collisions removed first.

    `prose=True` also drops double-quoted spans. Pass it for an issue title, an issue body or a
    Markdown document -- anywhere `"` means a quotation. Leave it off for source, YAML and JSON,
    where `"` delimits a string and dropping it hides the messages the software prints.
    """
    cleaned = NOT_PROSE.sub(" ", text)
    if prose:
        cleaned = QUOTED_PROSE.sub(" ", cleaned)
    return PORTUGUESE.findall(cleaned)


def speaks_portuguese(text: str, *, threshold: int = 2, prose: bool = False) -> bool:
    """True when this one line, or title, carries enough markers to be Portuguese."""
    return len(portuguese_markers(text, prose=prose)) >= threshold


#: Markers per non-empty line, above which a WHOLE document is Portuguese even though no single
#: line reaches the per-line threshold. Measured on 2026-09-22 over every tracked text file outside
#: the inventory: the genuinely Portuguese documents sit at 0.33 to 0.38 -- `REVIEW.md`, which is
#: two Portuguese sentences, and `docs/context/architecture.md`, a page of short bullets -- and the
#: English test files that merely quote a Portuguese token sit at 0.006 to 0.009. The floor is
#: placed in that gap, not at a round number.
DOCUMENT_DENSITY = 0.15


#: Markers that make a document Portuguese however long it is. A ratio alone dilutes: ten
#: Portuguese lines in a twenty-line file flag, and the same ten in a hundred-line file do not --
#: measured. That is blind exactly where the inventory is meant to be useful, because a partly
#: translated file is the normal state of this work.
DOCUMENT_MARKERS = 6

#: Below this many markers the ratio is not consulted at all. It is 1, which is to say the ratio
#: always decides -- and it stood at 2 for one review round, which is the more useful fact.
#:
#: The argument for 2 was sound: one stray marker in a file of six written lines or fewer clears
#: the density floor, and 58 tracked files are that short, so a lone `Sao Paulo` in a README would
#: flag it. The measurement refused the argument. Across the whole tree a floor of 2 changes the
#: verdict on exactly two files, `extensions/README.md` in both copies, and both are Portuguese
#: end to end. It prevented nothing, because there was no false positive to prevent: at a floor
#: of 1 the inventory holds 114 files and every one of them carries Portuguese.
#:
#: It stays at 1 because of an asymmetry this file keeps rediscovering. A false positive HERE is
#: one extra name in a pinned inventory, read by a human when it changes and removable in one
#: line. A false positive in `issue_contract_problems` refuses a correct pull request with no
#: override, which is the cost that justified taking the function words out of the list above.
#: That cost does not transfer, and treating the two guards as one control is what produced 2.
DENSITY_FLOOR_MARKERS = 1


def document_speaks_portuguese(lines: list[str], *, prose: bool = False) -> bool:
    """True when this file is Portuguese, by any of three rules.

    Per line, because that is the ordinary case. By absolute count, because a Portuguese section
    inside a long English document must not dilute away as the rest is translated. And by density,
    because a page of short bullets never reaches two markers on any single line.

    The density rule is the smallest of the three and is kept for a measured reason: it alone
    reaches `docs/context/architecture.md` and `extensions/README.md`, in both copies -- four of
    the 114 files in the inventory. Review found the rule by noticing `REVIEW.md` was missing;
    morphology later made that one a per-line catch, which is why the example moved. The rule
    stayed, because the files it holds are still held by nothing else.
    """
    if any(speaks_portuguese(line, prose=prose) for line in lines):
        return True
    written = [line for line in lines if line.strip()]
    if not written:
        return False
    markers = sum(len(portuguese_markers(line, prose=prose)) for line in written)
    if markers >= DOCUMENT_MARKERS:
        return True
    return markers >= DENSITY_FLOOR_MARKERS and markers / len(written) >= DOCUMENT_DENSITY
