"""The CI receipt: proof that a local battery ran, against which commit, and how completely.

Absence must never read as green. This module is the READER half of a contract; it defines,
in its own docstrings, what a future WRITER has to emit, and it turns a receipt plus the
current HEAD into exactly one of three answers (`CiReceiptStatus`):

* ``COVERS``  -- the receipt measured this HEAD, with a clean tree, the whole battery, all green.
* ``STALE``   -- a receipt exists but does not cover this HEAD; ``reason`` names why.
* ``MISSING`` -- no receipt file at all.

## The contract a writer must fulfil

No local-CI runner exists in this repository yet (2026-09-19). Whichever script writes
``.project/last-ci-run.yml`` -- a `scripts/local_ci.py`, most likely -- must emit a mapping
matching ``.project/schemas/ci-receipt.schema.json``:

    schema_version: 1
    kind: local_ci_receipt
    ran_at: '<UTC ISO-8601, when the run finished>'
    head: '<git rev-parse HEAD, measured AFTER the run>'
    head_before_run: '<git rev-parse HEAD, measured BEFORE the run>'
    tree_was_dirty_before_run: <bool>
    tree_changed_during_run: <bool>     # HEAD or dirtiness differed between start and end
    tree_was_dirty: <bool>              # dirty at the instant this receipt was written
    dirty_paths: <int>                  # a COUNT of `git status --short` lines, not a list
    red: <int>
    partial: <int>
    green: <int>
    affected_mode: <bool>               # true when filtered by --affected/name: not the whole run
    dry_run: <bool>                     # true for a --list/no-op invocation: nothing ran
    workflows_available: <int>
    workflows_requested: <int>
    workflows_run: <int>

This reader is deliberately tolerant of a receipt that is missing one of these fields --
missing instrumentation is itself read as staleness (see `check_ci_receipt`), never as a
crash and never as a pass. It does not depend on which script becomes the writer, only on the
shape above.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, TypedDict, cast

import yaml

#: Where the receipt lives, relative to the project root.
CI_RECEIPT_RELATIVE = ".project/last-ci-run.yml"

#: The schema this reader was written against.
CI_RECEIPT_SCHEMA_RELATIVE = ".project/schemas/ci-receipt.schema.json"

#: Phrases in `state.validation.passed` that CLAIM a full local battery ran, matched
#: case-insensitively as a substring because that sentence is free text written by hand.
_BATTERY_CLAIM_MARKERS = ("local_ci", "bateria completa", "bateria local")

#: A structured list, once a writer emits one, of battery claims that does not depend on
#: which of the free-text phrases above was chosen. Checked first by `battery_claims`; the
#: textual match is only the fallback for as long as no producer emits this key.
_STRUCTURED_BATTERY_CLAIMS_KEY = "battery_runs"


class CiReceiptStatus(StrEnum):
    """The three, and only three, answers this reader gives."""

    COVERS = "covers"
    STALE = "stale"
    MISSING = "missing"


class CiReceiptData(TypedDict, total=False):
    """The shape a writer must emit, per the module docstring above.

    ``total=False`` because this reader is deliberately tolerant of a receipt missing one of
    these fields (see `check_ci_receipt`); a missing key is read as staleness, never a crash.
    """

    schema_version: int
    kind: str
    ran_at: str
    head: str
    head_before_run: str
    tree_was_dirty_before_run: bool
    tree_changed_during_run: bool
    tree_was_dirty: bool
    dirty_paths: int
    red: int
    partial: int
    green: int
    affected_mode: bool
    dry_run: bool
    workflows_available: int
    workflows_requested: int
    workflows_run: int


@dataclass(frozen=True)
class CiReceiptCheck:
    """The result of checking a receipt against a HEAD.

    ``reason`` is populated for ``STALE`` and ``MISSING`` alike, always naming the concrete
    fact that failed (missing file, mismatched commit, dirty tree, partial run, ...), never a
    generic "not green".
    """

    status: CiReceiptStatus
    reason: str | None
    receipt_path: str
    receipt: CiReceiptData | None


def battery_claims(state: dict[str, Any]) -> list[str]:
    """Every claim in ``state`` that a full local battery ran, structural first, textual fallback.

    A structural claim under ``validation.battery_runs`` is read whole, regardless of wording.
    Only when that key is absent does this fall back to the substring match on
    ``validation.passed``, because free text is the only format any writer has produced so far.
    """
    validation: dict[str, Any] = state.get("validation") or {}
    structured = validation.get(_STRUCTURED_BATTERY_CLAIMS_KEY)
    if structured:
        return [str(item) for item in structured]
    passed: list[Any] = validation.get("passed") or []
    return [
        str(line)
        for line in passed
        if any(marker in str(line).lower() for marker in _BATTERY_CLAIM_MARKERS)
    ]


def _shown_path(root: Path, path: Path) -> str:
    """The receipt's path as a reader should see it: relative to the project when possible.

    ``relative_to`` raises for a path outside the tree, and a guard whose error message
    crashes reports nothing at all.
    """
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def check_ci_receipt(root: Path, head: str) -> CiReceiptCheck:
    """Whether ``.project/last-ci-run.yml`` under ``root`` covers ``head``.

    Never infers green from absence, from a corrupt file, or from a receipt that admits, in
    its own fields, that it did not measure the whole thing.
    """
    receipt_path = root / CI_RECEIPT_RELATIVE
    shown = _shown_path(root, receipt_path)
    if not receipt_path.is_file():
        return CiReceiptCheck(
            status=CiReceiptStatus.MISSING,
            reason=f"nao existe {shown}: nenhuma bateria foi registrada.",
            receipt_path=shown,
            receipt=None,
        )

    try:
        loaded = yaml.safe_load(receipt_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as failure:
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=f"{shown} nao pode ser lido como YAML: {failure}",
            receipt_path=shown,
            receipt=None,
        )
    if not isinstance(loaded, dict):
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=f"{shown} nao e um mapeamento valido.",
            receipt_path=shown,
            receipt=None,
        )
    # `loaded` is confirmed a dict by the isinstance check above; yaml.safe_load's return is
    # untyped (`Any`), and the schema this reader is written against (module docstring) fixes
    # the shape from here on -- this is the one boundary conversion, not a scattered cast.
    receipt = cast(CiReceiptData, loaded)

    measured_head = str(receipt.get("head", ""))
    if measured_head != head:
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=(
                f"{shown} mediu {measured_head[:12] or '(vazio)'}, o HEAD atual e {head[:12]}. "
                "Um recibo medido noutro commit nao cobre este."
            ),
            receipt_path=shown,
            receipt=receipt,
        )
    if receipt.get("tree_was_dirty_before_run"):
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=f"{shown} rodou com a arvore SUJA antes de comecar.",
            receipt_path=shown,
            receipt=receipt,
        )
    if receipt.get("tree_was_dirty"):
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=(
                f"{shown} registra a arvore SUJA ({receipt.get('dirty_paths')} caminho(s)). "
                "Um verde sobre trabalho nao commitado nao prova nada sobre este commit."
            ),
            receipt_path=shown,
            receipt=receipt,
        )
    if receipt.get("dry_run"):
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=f"{shown} tem dry_run: true -- nenhum passo foi de fato executado.",
            receipt_path=shown,
            receipt=receipt,
        )
    if receipt.get("affected_mode"):
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=f"{shown} correu em modo afetado/filtrado -- isso nao e a bateria inteira.",
            receipt_path=shown,
            receipt=receipt,
        )

    available = receipt.get("workflows_available")
    requested = receipt.get("workflows_requested")
    run = receipt.get("workflows_run")
    if available is None or requested is None or run is None:
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=(
                f"{shown} nao registra workflows_available/workflows_requested/workflows_run "
                "(recibo incompleto). Sem isso nao da para confirmar que a corrida foi o "
                "conjunto inteiro."
            ),
            receipt_path=shown,
            receipt=receipt,
        )
    if int(run) != int(available) or int(requested) != int(available):
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=(
                f"{shown} diz {run} rodado(s) / {requested} pedido(s) de {available} "
                "disponivel(is) -- nao e a corrida inteira."
            ),
            receipt_path=shown,
            receipt=receipt,
        )
    if int(receipt.get("red", 0) or 0) > 0:
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=f"{shown} mede {receipt.get('red')} vermelho(s) neste HEAD.",
            receipt_path=shown,
            receipt=receipt,
        )
    if int(receipt.get("partial", 0) or 0) > 0:
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=(
                f"{shown} mede {receipt.get('partial')} parcial(is) -- nao e um verde inteiro."
            ),
            receipt_path=shown,
            receipt=receipt,
        )
    green = int(receipt.get("green", 0) or 0)
    if green != int(available):
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=f"{shown} mede {green} verde(s) de {available} -- nem tudo ficou verde.",
            receipt_path=shown,
            receipt=receipt,
        )
    if receipt.get("tree_changed_during_run"):
        return CiReceiptCheck(
            status=CiReceiptStatus.STALE,
            reason=(
                f"{shown} diz que a arvore mudou durante a propria corrida (antes: "
                f"{str(receipt.get('head_before_run', ''))[:12] or '(vazio)'}, depois: "
                f"{measured_head[:12]}). Parte da bateria mediu uma arvore diferente do que "
                "terminou medindo."
            ),
            receipt_path=shown,
            receipt=receipt,
        )
    return CiReceiptCheck(
        status=CiReceiptStatus.COVERS,
        reason=None,
        receipt_path=shown,
        receipt=receipt,
    )
