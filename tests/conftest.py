"""T210 / FR-008 / AC-005: a skipped test is not a passing test until its reason is declared.

A skipped case does not fail, and a green suite carrying skips reads as coverage that does not
exist. The task names the mechanism exactly: an assertion over the **execution report**, not over
the exit code -- because the exit code of a run full of skips is zero, which is the whole problem.

WHAT "DECLARED" MEANS HERE, and why a written reason is not enough. `pytest.skip("x")` carries a
reason. It declares nothing: it is the author talking to themselves at the moment of writing. A
declared skip is one somebody accepted, in a versioned inventory that has to change when the skip
changes -- the same shape the coverage matrix's own guard uses (T214), for the same reason.

WHAT IS COLLECTED, measured against pytest 9.1.1 rather than assumed:

  * `setup`, `call` and `teardown` skips, whose `longrepr` is a `(path, lineno, reason)` tuple;
  * module-level skips -- `pytest.skip(..., allow_module_level=True)` and `pytest.importorskip`
    -- which never produce a runtest report at all and arrive as collect reports instead. That is
    the most common way a whole file of coverage disappears, and this repository already ships an
    optional dependency (`rich`) that invites it;
  * `xfail`, whose report is `skipped` with an `ExceptionChainRepr` rather than a tuple, so its
    reason is read from `report.wasxfail`. An xfail is a case that asserted nothing and did not
    fail, which is what FR-008 is about; it is declarable like any other.

`xpass` is not collected: pytest reports it as a pass, and a strict xpass already fails the run.

WHAT IS NOT COLLECTED, named here because FR-009 requires each enforcement point to carry its own
bypass vectors:

  * a run narrowed by `-k`, `-m`, `--deselect`, or an explicit path argument. Those legitimately
    do not reach the tests whose skips are declared, and failing on them would make every focused
    run red -- which is how a gate stops being run;
  * `--collect-only`, `--fixtures`, `--markers`, `--setup-plan` and `--setup-only`, which execute
    nothing. This repository's own MEASURER agent counts tests with `pytest --collect-only`, and a
    gate that turns the repository's documented measuring instrument red teaches agents to ignore
    it;
  * plugin suppression (`-p no:...`), or running pytest from a directory where this file is not
    collected. Neither is what CI does.

HOW IT REFUSES: `pytest_sessionfinish` sets a non-zero exit status after reading the reports. It
does not raise inside a test, because the condition is a property of the run rather than of any
one case. When the run already has a real failure the problems are printed but the run is not
failed on their account: the operator needs the real failure first, and CI runs the whole suite on
every push, so the next otherwise-clean run fails on them.

REACH, declared per FR-012: this lives in the suite of THIS repository. A derived project keeps its
own tests and does not inherit the inventory, which is a limit to state rather than a defect.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

import pytest

from tests.skip_policy import Declaration, skip_policy_problems

if TYPE_CHECKING:  # pragma: no cover - typing only
    from _pytest.reports import CollectReport, TestReport

pytest_plugins = ["pytester"]

#: True on the platform whose condition three of the entries below encode. CI runs Linux
#: (`runs-on: ubuntu-latest`), where those tests run and pass instead of skipping.
_ON_WINDOWS = os.name == "nt"

#: nodeid -> what was accepted. The key is the test's own id, so moving or renaming a test forces
#: its entry to be revisited; the reason is a prefix rather than the whole string because several
#: of these end in a measured number that changes on its own.
#:
#: Adding an entry here is the act of declaring. It is deliberately not automatic: the point is
#: that a second reading happened.
DECLARED_SKIPS: dict[str, Declaration] = {
    # POSIX permission bits, on a platform that has none. Not a gap in coverage: these three
    # assert an attribute the filesystem under them cannot carry, and they run for real on the
    # Linux runner -- which is why they are expected only on Windows.
    "tests/unit/test_installer_modes.py::test_a_shebang_file_is_written_executable": Declaration(
        "Windows ignores the execute bit", expected=_ON_WINDOWS
    ),
    "tests/unit/test_installer_modes.py::test_a_plain_file_is_not_made_executable": Declaration(
        "Windows ignores the execute bit", expected=_ON_WINDOWS
    ),
    "tests/unit/test_installer_modes.py::test_the_execute_bit_follows_read_and_the_umask": (
        Declaration("Windows ignores the execute bit", expected=_ON_WINDOWS)
    ),
}

#: Options that mean "this run is not the whole suite". Narrowed runs and runs that execute
#: nothing are both exempt, for different reasons -- see the module docstring.
_NARROWING_OPTIONS = ("keyword", "markexpr", "deselect", "file_or_dir")
_NON_EXECUTING_OPTIONS = ("collectonly", "showfixtures", "markers", "setupplan", "setuponly")

_OBSERVED: dict[str, str] = {}


def _normalise(nodeid: str) -> str:
    """`tests\\unit\\x.py::t` and `tests/unit/x.py::t` are the same test on two platforms."""
    return nodeid.replace("\\", "/")


def _reason_of(report: TestReport | CollectReport) -> str:
    """The reason as the author wrote it, whatever shape the report carries it in."""
    wasxfail = getattr(report, "wasxfail", None)
    if isinstance(wasxfail, str):
        return wasxfail or "(no reason given)"
    longrepr = report.longrepr
    if isinstance(longrepr, tuple) and len(longrepr) == 3:
        return str(longrepr[2]).removeprefix("Skipped: ")
    return str(longrepr or "")


def pytest_sessionstart(session: pytest.Session) -> None:
    _OBSERVED.clear()


@pytest.hookimpl(trylast=True)
def pytest_runtest_logreport(report: TestReport) -> None:
    if report.skipped:
        _OBSERVED[_normalise(report.nodeid)] = _reason_of(report)


@pytest.hookimpl(trylast=True)
def pytest_collectreport(report: CollectReport) -> None:
    """Module-level skips arrive here and nowhere else.

    `pytest.skip(..., allow_module_level=True)` and `pytest.importorskip` produce no runtest
    report at all: measured against pytest 9.1.1, a file skipped that way printed `1 skipped` and
    the first version of this gate saw nothing at all.
    """
    if report.skipped:
        _OBSERVED[_normalise(report.nodeid)] = _reason_of(report)


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """The assertion over the report, run once the whole report exists."""
    option = session.config.option
    if any(getattr(option, name, None) for name in _NARROWING_OPTIONS):
        return
    if any(getattr(option, name, False) for name in _NON_EXECUTING_OPTIONS):
        return

    problems = skip_policy_problems(_OBSERVED, DECLARED_SKIPS)
    if not problems:
        return

    already_failing = bool(session.testsfailed)
    reporter: Any = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        heading = (
            "skips that are not declared (informational: this run already failed)"
            if already_failing
            else "skips that are not declared"
        )
        reporter.write_sep("=", heading, red=not already_failing)
        for problem in problems:
            reporter.write_line(problem)
    if not already_failing:
        session.exitstatus = 1
