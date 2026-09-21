"""T210 / FR-008 / AC-005: a skipped test is not a passing test until its reason is declared.

The task names the mechanism and rules out the easy version of it: an assertion over the
**execution report**, not over the exit code. The exit code of a run full of skips is zero, which
is the whole problem -- `pytest -q` prints `331 passed, 4 skipped` and returns success, and the
four cases that asserted nothing count, to every reader and every gate above, as coverage.

Two halves, kept apart on purpose:

* the RULE, as a pure function over what the report said (`tests/skip_policy.py`), where the edges
  live -- repurposed entries, stale entries, entries that only apply on one platform;
* the WIRING, exercised by running pytest inside pytest with the real `conftest.py` copied in, so
  "it fails the run" is measured rather than assumed, and so is every case where it must NOT fail
  the run. A guard that fires on an ordinary focused run gets switched off within the week, which
  makes the exemptions as load-bearing as the refusal.

Everything the wiring collects was measured against pytest 9.1.1, not inferred: a module-level
skip produces no runtest report at all, an xfail is reported as `skipped` with its reason in
`report.wasxfail` rather than in a tuple, and a teardown skip prints in the summary like any
other. The first version of this slice saw none of those three.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.conftest import DECLARED_SKIPS
from tests.skip_policy import Declaration, skip_policy_problems

REPO_TESTS = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------------------
# The rule
# --------------------------------------------------------------------------------------


def test_a_declared_skip_is_accepted() -> None:
    problems = skip_policy_problems(
        {"tests/unit/t.py::test_x": "Windows ignores the execute bit"},
        {"tests/unit/t.py::test_x": Declaration("Windows ignores the execute bit")},
    )

    assert problems == []


def test_a_written_reason_is_not_a_declared_one() -> None:
    """THE distinction the task is about. `pytest.skip("x")` carries a reason and declares
    nothing: it is the author talking to themselves at the moment of writing.
    """
    problems = skip_policy_problems({"tests/unit/t.py::test_x": "x"}, {})

    assert len(problems) == 1
    assert "undeclared skip" in problems[0]
    assert "tests/unit/t.py::test_x" in problems[0]
    assert "FR-008" in problems[0], "the refusal names the requirement it enforces"


def test_an_empty_reason_is_refused_like_any_other() -> None:
    assert skip_policy_problems({"tests/unit/t.py::test_x": ""}, {}) != []


def test_a_declaration_may_be_a_prefix_of_a_reason_that_carries_a_measurement() -> None:
    """Several real reasons end in a number that moves on its own -- "3 stage(s) still without a
    mechanism" is one. Pinning the whole string would make the inventory churn for no reason.
    """
    problems = skip_policy_problems(
        {"tests/unit/t.py::test_x": "AC-011 not yet satisfiable: 3 stage(s) remain"},
        {"tests/unit/t.py::test_x": Declaration("AC-011 not yet satisfiable")},
    )

    assert problems == []


def test_an_entry_reused_for_a_different_reason_is_refused() -> None:
    """Keeping the inventory the same size while changing what it means is how a declaration
    becomes a rubber stamp.
    """
    problems = skip_policy_problems(
        {"tests/unit/t.py::test_x": "flaky on CI, will look later"},
        {"tests/unit/t.py::test_x": Declaration("Windows ignores the execute bit")},
    )

    assert len(problems) == 1
    assert "repurposed skip" in problems[0]


def test_a_declaration_that_stopped_skipping_is_refused() -> None:
    """The direction people forget. An entry nobody prunes is an inventory drifting away from the
    suite in the quiet direction -- which is exactly how the coverage matrix rotted (#39).
    """
    problems = skip_policy_problems({}, {"tests/unit/t.py::test_x": Declaration("some reason")})

    assert len(problems) == 1
    assert "stale declaration" in problems[0]


def test_a_declaration_for_another_platform_is_not_stale_here() -> None:
    """THE finding that would have turned CI red on the first push of this slice.

    Three of this repository's skips are `skipif(os.name == "nt")`. On the Linux runner CI uses
    they run and pass -- they do not skip -- so an inventory that could not say "expected
    elsewhere" reported three stale declarations on a suite where nothing was wrong. A gate whose
    first contact with CI is a false red is a gate that gets switched off.
    """
    declared = {"t.py::test_x": Declaration("posix only", expected=False)}

    assert skip_policy_problems({}, declared) == []


def test_a_declaration_for_another_platform_is_still_held_to_its_reason() -> None:
    """`expected=False` exempts an entry from the stale rule and from nothing else. If the test
    skips anyway, it skips for the declared reason or it is a problem.
    """
    problems = skip_policy_problems(
        {"t.py::test_x": "something else entirely"},
        {"t.py::test_x": Declaration("posix only", expected=False)},
    )

    assert len(problems) == 1
    assert "repurposed skip" in problems[0]


def test_every_kind_of_problem_is_reported_at_once() -> None:
    """One at a time would mean one run per fix. The suite is two minutes long."""
    problems = skip_policy_problems(
        {
            "tests/unit/t.py::undeclared": "whatever",
            "tests/unit/t.py::repurposed": "a new reason",
        },
        {
            "tests/unit/t.py::repurposed": Declaration("the old reason"),
            "tests/unit/t.py::vanished": Declaration("gone"),
        },
    )

    assert len(problems) == 3
    assert {problem.split(":")[0] for problem in problems} == {
        "undeclared skip",
        "repurposed skip",
        "stale declaration",
    }


def test_the_repositorys_own_inventory_is_not_empty() -> None:
    """A guard over an empty inventory passes for the wrong reason. If this ever reaches zero,
    the mechanism should be removed rather than left running over nothing.
    """
    assert DECLARED_SKIPS, "the inventory emptied -- either the skips went away or it was deleted"
    assert all(entry.reason.strip() for entry in DECLARED_SKIPS.values()), (
        "an inventory entry with a blank justification declares nothing"
    )


# --------------------------------------------------------------------------------------
# The wiring: what it catches, and what it must leave alone
# --------------------------------------------------------------------------------------


@pytest.fixture
def suite(pytester: pytest.Pytester) -> pytest.Pytester:
    """A throwaway repository carrying THIS repository's real conftest and real rule.

    Copied rather than imported, so the wiring runs as pytest loads it, in a session of its own.
    The inventory is replaced by appending a new binding rather than by editing the literal out of
    the text: brace-matching someone else's source is a fixture that breaks on a reworded
    annotation, and each test below sets the inventory it needs through `declare`.
    """
    (pytester.path / "tests").mkdir()
    (pytester.path / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (pytester.path / "tests" / "skip_policy.py").write_text(
        (REPO_TESTS / "skip_policy.py").read_text(encoding="utf-8"), encoding="utf-8"
    )
    (pytester.path / "conftest.py").write_text(
        (REPO_TESTS / "conftest.py").read_text(encoding="utf-8") + "\nDECLARED_SKIPS = {}\n",
        encoding="utf-8",
    )
    return pytester


def declare(suite: pytest.Pytester, nodeid: str, entry: Declaration) -> None:
    """Give the throwaway suite an inventory, so the exemption tests are not vacuous.

    Review measured that with an empty inventory the narrowed-run test passed whether or not the
    guard existed: nothing was declared, so nothing could be reported stale. A test named for a
    guard that passes without it measures nothing.
    """
    conftest = suite.path / "conftest.py"
    conftest.write_text(
        conftest.read_text(encoding="utf-8")
        + f"\nDECLARED_SKIPS = {{{nodeid!r}: Declaration({entry.reason!r}, "
        f"expected={entry.expected})}}\n",
        encoding="utf-8",
    )


SKIPPING_SUITE = """
    import pytest

    def test_that_skips():
        pytest.skip("nobody accepted this")

    def test_that_passes():
        assert True
    """


def test_an_undeclared_skip_fails_the_run(suite: pytest.Pytester) -> None:
    """THE claim, measured end to end: the run returns non-zero even though every test passed.

    Without this, the policy is a function nobody calls at the moment it matters.
    """
    suite.makepyfile(test_something=SKIPPING_SUITE)

    result = suite.runpytest_subprocess("-q")

    assert result.ret != 0, "a run whose only anomaly is an undeclared skip reported success"
    result.stdout.fnmatch_lines(["*undeclared skip*test_that_skips*"])


def test_the_recorded_reason_is_the_one_the_author_wrote(suite: pytest.Pytester) -> None:
    """pytest hands the reason over prefixed with `Skipped: `. Stripping it is what makes the
    inventory's prefixes match real reasons, and nothing measured that until this test.
    """
    suite.makepyfile(test_something=SKIPPING_SUITE)

    result = suite.runpytest_subprocess("-q")

    result.stdout.fnmatch_lines(["*'nobody accepted this'*"])
    assert "Skipped: nobody accepted this" not in result.stdout.str()


def test_a_declared_skip_passes_the_run(suite: pytest.Pytester) -> None:
    declare(suite, "test_something.py::test_that_skips", Declaration("nobody accepted this"))
    suite.makepyfile(test_something=SKIPPING_SUITE)

    assert suite.runpytest_subprocess("-q").ret == 0


def test_a_skip_raised_in_teardown_is_seen(suite: pytest.Pytester) -> None:
    """The summary counts it; the first version of this gate did not, because it looked only at
    `setup` and `call`.
    """
    suite.makepyfile(
        test_teardown="""
        import pytest

        @pytest.fixture
        def fixture_that_skips_late():
            yield
            pytest.skip("teardown skip, undeclared")

        def test_uses_it(fixture_that_skips_late):
            assert True
        """
    )

    result = suite.runpytest_subprocess("-q")

    assert result.ret != 0
    result.stdout.fnmatch_lines(["*undeclared skip*teardown skip*"])


def test_a_module_level_skip_is_seen(suite: pytest.Pytester) -> None:
    """The most common way a whole file of coverage disappears: an optional dependency goes
    missing and `importorskip` takes the file with it. Those produce no runtest report at all, so
    the first version of this gate reported `1 skipped` and exit 0.
    """
    suite.makepyfile(
        test_module_level="""
        import pytest

        pytest.skip("whole module unavailable", allow_module_level=True)

        def test_never_runs():
            assert False
        """,
        test_green="""
        def test_that_passes():
            assert True
        """,
    )

    result = suite.runpytest_subprocess("-q")

    assert result.ret != 0
    result.stdout.fnmatch_lines(["*undeclared skip*whole module unavailable*"])


def test_an_xfail_is_declarable_rather_than_unfixable(suite: pytest.Pytester) -> None:
    """An xfail asserts nothing and does not fail, which is what FR-008 is about, so it is
    collected. Its reason lives in `report.wasxfail` rather than in a tuple -- read from the wrong
    place, every xfail came out with an empty reason, which made it simultaneously undeclared and
    impossible to declare.
    """
    suite.makepyfile(
        test_xfail="""
        import pytest

        @pytest.mark.xfail(reason="known bug #1")
        def test_that_fails():
            assert False
        """
    )

    undeclared = suite.runpytest_subprocess("-q")
    assert undeclared.ret != 0
    undeclared.stdout.fnmatch_lines(["*undeclared skip*known bug #1*"])

    declare(suite, "test_xfail.py::test_that_fails", Declaration("known bug #1"))
    assert suite.runpytest_subprocess("-q").ret == 0


def test_a_run_with_no_skips_at_all_is_left_alone(suite: pytest.Pytester) -> None:
    """The other side. A guard that fails clean runs would be removed within the day."""
    suite.makepyfile(
        test_clean="""
        def test_that_passes():
            assert True
        """
    )

    assert suite.runpytest_subprocess("-q").ret == 0


def test_a_narrowed_run_does_not_fail_on_declarations_it_never_reached(
    suite: pytest.Pytester,
) -> None:
    """`-k` legitimately does not reach the declared skip, so the stale rule must stay quiet.

    The inventory here is NOT empty, which is what makes this measure the guard: with nothing
    declared there was nothing to report stale, and the test passed whether or not the guard
    existed.
    """
    declare(suite, "test_narrow.py::test_that_skips", Declaration("nobody accepted this"))
    suite.makepyfile(test_narrow=SKIPPING_SUITE)

    assert suite.runpytest_subprocess("-q", "-k", "passes").ret == 0


def test_a_deselected_run_does_not_fail_either(suite: pytest.Pytester) -> None:
    """`--deselect` narrows a run exactly as `-k` does, and the first version of this file
    promised that exemption in its docstring while not implementing it.
    """
    declare(suite, "test_deselected.py::test_that_skips", Declaration("nobody accepted this"))
    suite.makepyfile(test_deselected=SKIPPING_SUITE)

    result = suite.runpytest_subprocess("-q", "--deselect", "test_deselected.py::test_that_skips")

    assert result.ret == 0


def test_collect_only_is_left_alone(suite: pytest.Pytester) -> None:
    """`pytest --collect-only` executes nothing, so every declaration would read as stale. It is
    also this repository's own documented way of counting tests, in `.claude/agents/measurer.md`:
    a gate that turns the measuring instrument red teaches agents to ignore the gate.
    """
    declare(suite, "test_counted.py::test_that_skips", Declaration("nobody accepted this"))
    suite.makepyfile(test_counted=SKIPPING_SUITE)

    assert suite.runpytest_subprocess("--collect-only", "-q").ret == 0


def test_a_real_failure_is_reported_first_and_does_not_hide_the_skip(
    suite: pytest.Pytester,
) -> None:
    """When something genuinely failed, that is the message the operator needs, and the run is
    already red for the right reason. The problems are still printed -- informationally -- because
    erasing them costs a second two-minute run to learn what this one already knew.
    """
    suite.makepyfile(
        test_failing="""
        import pytest

        def test_that_skips():
            pytest.skip("nobody accepted this")

        def test_that_fails():
            assert False
        """
    )

    result = suite.runpytest_subprocess("-q")

    assert result.ret != 0
    result.stdout.fnmatch_lines(["*informational*", "*undeclared skip*"])


def test_the_real_inventory_is_clean_on_the_platform_ci_actually_runs() -> None:
    """The acceptance test for the blocker. CI runs `ubuntu-latest`; this workstation is Windows.

    The three `skipif(os.name == "nt")` entries must be `expected` exactly where they skip, or the
    inventory is right on one platform and wrong on the other -- and the one it is wrong on is the
    one that gates merges. Both directions are checked here rather than only the local one.
    """
    posix_only = {
        nodeid: entry for nodeid, entry in DECLARED_SKIPS.items() if "installer_modes" in nodeid
    }
    assert len(posix_only) == 3, "the posix-only entries moved; this test is pinned to them"
    assert all(entry.expected == (os.name == "nt") for entry in posix_only.values()), (
        "a posix-only skip must be expected on Windows and not expected elsewhere"
    )

    on_linux = {
        nodeid: Declaration(entry.reason, expected=False) if nodeid in posix_only else entry
        for nodeid, entry in DECLARED_SKIPS.items()
    }
    observed_on_linux = {
        nodeid: entry.reason for nodeid, entry in DECLARED_SKIPS.items() if nodeid not in posix_only
    }

    assert skip_policy_problems(observed_on_linux, on_linux) == [], (
        "the run CI performs would have been red on an inventory that is correct"
    )
