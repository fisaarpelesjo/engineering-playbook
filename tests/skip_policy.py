"""The rule a skipped test has to satisfy, as a pure function over the execution report.

T210 / FR-008 / AC-005. Kept apart from `conftest.py` so the rule can be exercised directly: a
policy that can only be tested by arranging a whole pytest session is a policy nobody tests at the
edges, and the edges -- repurposed entries, stale entries, entries that only apply on one platform
-- are where an inventory rots.

`conftest.py` holds the wiring (which reports to collect, when to stay quiet, how to fail the run)
and the inventory itself. This holds the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Declaration:
    """One accepted skip: the justification, and whether it is expected to happen here.

    `expected` exists because a declaration is not always unconditional. Three of this
    repository's skips are `skipif(os.name == "nt")`: on Windows they skip, on the Linux runner
    CI uses they run and pass. An inventory that cannot say so reports three "stale declaration"
    problems on every CI run -- a false red on a suite where nothing is wrong, which is how a gate
    gets switched off in its first week. Review measured exactly that against the first version of
    this file.

    `expected=False` still subjects the entry to the undeclared and repurposed rules: if the test
    skips anyway, it skips with the reason declared here or it is a problem.
    """

    reason: str
    expected: bool = True


def skip_policy_problems(observed: dict[str, str], declared: dict[str, Declaration]) -> list[str]:
    """Everything wrong with this run's skips, as sentences for whoever has to fix them.

    Three kinds, and the third is the one people forget:

    * UNDECLARED -- a skip nobody accepted. `pytest.skip("x")` carries a reason and declares
      nothing; the reason is the author talking to themselves at the moment of writing.
    * REPURPOSED -- a declared entry whose reason changed underneath it. Reusing an existing
      entry for a new condition is how an inventory keeps its size while losing its meaning.
    * STALE -- a declared skip that was expected here and did not happen. Left alone, the
      inventory drifts away from the suite in the quiet direction, which is exactly how the
      coverage matrix rotted (#39). Entries marked `expected=False` are exempt from this one, and
      only from this one.
    """
    problems: list[str] = []
    for nodeid, reason in sorted(observed.items()):
        declaration = declared.get(nodeid)
        if declaration is None:
            problems.append(
                f"undeclared skip: {nodeid} was skipped with {reason!r}. A written reason is not "
                "a declared one -- add it to DECLARED_SKIPS in tests/conftest.py, which is where "
                "a skip stops being the author talking to themselves (FR-008/AC-005)."
            )
        elif not reason.startswith(declaration.reason):
            problems.append(
                f"repurposed skip: {nodeid} is declared as {declaration.reason!r} but was "
                f"skipped with {reason!r}. Declare the new reason rather than reusing the old "
                "entry."
            )
    for nodeid in sorted(set(declared) - set(observed)):
        if not declared[nodeid].expected:
            continue
        problems.append(
            f"stale declaration: {nodeid} is declared as a skip expected here and did not skip. "
            "Remove the entry, or mark it expected=False if it only applies on another platform "
            "-- an inventory nobody prunes is an inventory drifting away from the suite."
        )
    return problems
