"""Every mirrored file the resources copy ships, not just the one pre-commit hook.

`test_git_hooks.py::test_the_distributed_copy_matches_the_source_of_truth` guards exactly one
pair: the `pre-commit` hook. Derived projects install from `src/engineering_playbook/resources/`,
so any other file that exists at the same relative path in both the repository root and the
resources tree ships stale the moment the two drift, silently.

Excluded, and why -- measured, not guessed:

- `uv.lock`: structural, not drift -- but the count that used to stand here had expired. Measured
  on 2026-09-22: `diff uv.lock src/engineering_playbook/resources/uv.lock` shows 45 differing
  lines, not the one this paragraph claimed. `source = { editable = "." }` at the root versus
  `source = { virtual = "." }` in the resources copy is one of them; the rest are the optional
  `watch` extra and the `rich`, `markdown-it-py` and `mdurl` packages it pulls in, which exist in
  the root `pyproject.toml` and not in the distributed one because `agent_watch` is not shipped.
  This repository is an installable package with an extra; a derived project is neither. The
  reason is still valid and the number was not -- which is the exact defect T224 is named for,
  sitting in the same docstring.
- `.github/workflows/quality.yml`: NOT excluded any more, and not compared byte for byte either.
  The root copy carries an `adversarial` job that is deliberately not shipped -- a derived project
  installs neither `scripts/mutation.py` nor the inventory it reads, so the job would fail its
  first run and, because `attest` needs it, would stop the signed verdict being minted there at
  all. Those two differences are named below and everything else must match. Measured on
  2026-09-22: exactly two, the job block and the `needs:` line of `attest`.

  It used to be excluded because another workstream was editing it. That reason expired, and
  while it held, the file was edited by hand several times in one session (#49) -- no exact
  count, because `git log` sees commits and not sessions and nothing here reproduces it. The two
  copies were identical by discipline each time, which is the state this repository refuses to
  call a
  mechanism.
- `.project/project.yml`, `pyproject.toml`, `docs/requirements/project-requirements.md`: listed
  under `distribution.yml`'s `generated:` mapping. The installer renders these from the resources
  copy (`render_project_yml`, `render_pyproject`, `strip_source_prd`); they are templates, not
  literal mirrors, and coincidentally matching today is not a contract.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, cast

import yaml

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT / "src" / "engineering_playbook" / "resources"
WORKFLOW = ".github/workflows/quality.yml"

_SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".pyright"}

_EXCLUDED_PAIRS = frozenset(
    {
        "uv.lock",
        ".github/workflows/quality.yml",
        ".project/project.yml",
        "pyproject.toml",
        "docs/requirements/project-requirements.md",
    }
)

#: `.project/schemas/` is NO LONGER excluded. Measured on 2026-09-22: all seven schema files are
#: byte-identical across the two trees, so the exclusion was hiding nothing and protecting
#: nothing -- it only meant that the next hand edit to one side would ship a stale copy in
#: silence. `no_spec_reason` was added by hand to ONE of them, `state.schema.json`, in both
#: trees -- measured, after an earlier wording said `two of them` with `all seven schema
#: files` as its antecedent.


def _is_excluded(rel: str) -> bool:
    return rel in _EXCLUDED_PAIRS


def _mirrored_pairs() -> list[str]:
    pairs: list[str] = []
    for dirpath, dirnames, filenames in os.walk(RESOURCES):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for filename in filenames:
            resource_path = Path(dirpath) / filename
            rel = str(resource_path.relative_to(RESOURCES)).replace("\\", "/")
            if _is_excluded(rel):
                continue
            if (ROOT / rel).is_file():
                pairs.append(rel)
    return sorted(pairs)


def test_at_least_the_known_families_are_covered() -> None:
    """A guard over an empty list passes for the wrong reason; pin the measured floor."""
    pairs = _mirrored_pairs()
    # Raised from 75 when the schemas stopped being excluded and the measured count went from
    # 78 to 85. A floor rather than an exact number, so a file legitimately leaving the resources
    # tree does not fail this -- but ten pairs can no longer vanish in silence.
    assert len(pairs) >= 85, (
        f"only {len(pairs)} mirrored pairs were discovered; the walk may be broken "
        "rather than the repository having shrunk"
    )


def test_every_mirrored_pair_matches_byte_for_byte() -> None:
    pairs = _mirrored_pairs()
    mismatches = [
        rel for rel in pairs if (ROOT / rel).read_bytes() != (RESOURCES / rel).read_bytes()
    ]
    assert mismatches == [], (
        "these files have drifted between the repository root and "
        f"src/engineering_playbook/resources/, so derived projects install a stale copy: "
        f"{mismatches}"
    )


#: The job the root workflow runs and a derived project cannot. Everything else about the two
#: copies has to match.
UNSHIPPED_JOB = "adversarial"
#: The line the mutation inventory plants on, and the marker whose absence from the shipped copy
#: is asserted directly rather than inferred from the comparison.
ADVERSARIAL_JOB_MARKER = "  adversarial:\n"
UNSHIPPED_STEP = "scripts/mutation.py"
#: The job that follows the unshipped one. Used as an explicit END anchor rather than guessing
#: where a block stops from indentation, which is what the first version did and what review
#: measured failing open: a blank line, or any line not indented by exactly two spaces, ended the
#: scan early or swallowed what came after it.
NEXT_JOB_MARKER = "  attest:\n"
ATTEST_NEEDS_ROOT = "    needs: [delivery-policy, quality, adversarial]\n"
ATTEST_NEEDS_SHIPPED = "    needs: [delivery-policy, quality]\n"


def _workflow_as_shipped(text: str) -> dict[str, object]:
    """The root workflow as a derived project should receive it, compared as a STRUCTURE.

    The first version of this removed the job by scanning lines and guessing where the block
    ended from indentation. Review measured it failing open in both directions with a single
    edit to the real file: a blank line before `  attest:` was swallowed along with whatever
    followed, so real drift passed; and the same blank line mirrored correctly into BOTH copies
    turned the guard red. A gate that gives a false red on a correct mirror is a gate somebody
    switches off.

    Parsing removes the whole class. Formatting -- blank lines, comments, indentation, the order
    of the job keys, the line terminator -- stops participating in the comparison, and what is
    compared is what the workflow MEANS. The two legitimate differences are named as data: the
    job that is not shipped, and the `needs:` entry that refers to it.
    """
    document = cast(dict[str, Any], yaml.safe_load(text))
    jobs = cast(dict[str, Any], dict(document.get("jobs") or {}))
    jobs.pop(UNSHIPPED_JOB, None)
    for name, raw in list(jobs.items()):
        job = cast(dict[str, Any], raw)
        needs = job.get("needs")
        if isinstance(needs, list):
            kept = [cast(str, item) for item in cast(list[Any], needs) if item != UNSHIPPED_JOB]
            jobs[name] = {**job, "needs": kept}
    return {**document, "jobs": jobs}


def test_the_shipped_workflow_is_the_root_workflow_minus_the_job_it_cannot_run() -> None:
    """#49. This file was edited by hand in several places in one session while it sat on the
    exclusion list, and the two copies stayed identical by discipline. An omission in any one of
    them would have shipped a stale workflow to every derived project with nothing to notice.

    Byte parity is the wrong assertion here, because one difference is deliberate: the
    `adversarial` job runs this repository's mutation inventory, which a derived project does not
    install. So the shipped copy is compared against the parsed root copy with that job removed
    -- the difference is named, and every other difference is drift.

    DECLARED LIMIT, per NFR-005: this compares meaning, so a difference that YAML considers
    insignificant is a difference this test does not see -- comment text, key order, quoting
    style. Those reach a derived project verbatim and are invisible here. What is asserted
    instead, below, is that the one thing that must not travel does not travel.
    """
    root_text = (ROOT / WORKFLOW).read_bytes().decode("utf-8")
    shipped_text = (RESOURCES / WORKFLOW).read_bytes().decode("utf-8")

    assert ADVERSARIAL_JOB_MARKER in root_text, (
        "the root workflow no longer has an `adversarial:` job, so this comparison is describing "
        "a repository that does not exist any more"
    )
    assert ADVERSARIAL_JOB_MARKER not in shipped_text, (
        "the `adversarial` job header reached the resources copy; a derived project installs "
        "neither `scripts/mutation.py` nor the inventory it reads, so its first CI run would "
        "fail and `attest` would never mint a verdict there"
    )
    # Review measured the header being absent while the BODY survived: a comment indented by two
    # spaces ended the old scan early and left `run: uv run python scripts/mutation.py` in the
    # shipped copy, with the guard green and its own error message describing the state it let
    # through. This asserts ONE line of that body directly -- a tripwire a reader can check at a
    # glance. The rest of the body is still inferred, now from two comparisons instead of one:
    # review built a residue mentioning neither the header nor the script, and both comparisons
    # caught it while both of these marker assertions passed.
    assert UNSHIPPED_STEP not in shipped_text, (
        f"the shipped workflow still runs `{UNSHIPPED_STEP}`, which a derived project does not "
        "install, even though the `adversarial:` header is gone"
    )
    assert _workflow_as_shipped(root_text) == yaml.safe_load(shipped_text), (
        "the two copies of quality.yml differ by something other than the `adversarial` job; a "
        "derived project is installing a stale workflow"
    )


def _root_text_without_the_unshipped_job(text: str) -> str:
    """The root workflow as TEXT, with the unshipped job cut between explicit anchors.

    The structural comparison above is immune to formatting, which is its strength and its blind
    spot: a comment, a blank line or a different quoting style reaches a derived project verbatim
    and YAML cannot see it. This one sees exactly that, and is safe to write in text because the
    boundaries are literals asserted to occur once, not a guess at where indentation ends.

    The two checks are deliberately redundant. Structure catches a reordering that text would
    call drift; text catches a comment that structure calls identical. Neither alone covers the
    claim this file makes.
    """
    start = text.index(ADVERSARIAL_JOB_MARKER)
    end = text.index(NEXT_JOB_MARKER, start)
    cut = (text[:start] + text[end:]).replace(ATTEST_NEEDS_ROOT, ATTEST_NEEDS_SHIPPED, 1)
    return _without_blank_lines_at_the_seam(cut)


def _without_blank_lines_at_the_seam(text: str) -> str:
    """Drop blank lines immediately before the job that follows the removed one.

    DECLARED, because it is the one place this comparison is deliberately blind. A blank line
    separating `adversarial:` from `attest:` belongs to the block being removed, and in the
    shipped copy there is no such block for it to belong to.

    WHERE TO LOOK, since the name is about the text AFTER the cut and a reader checks the files:
    in the root workflow the invisible lines are the ones before `  adversarial:` -- the tail of
    the `quality` job -- and in the shipped copy the ones before `  attest:`. A line of spaces is
    not blank to `rstrip("\n")`, so it is still compared; that asymmetry errs closed and costs
    nothing.

    Cutting the span leaves the root without it and a hand-mirrored copy with it, so a correct
    mirror would read as drift -- and a gate that goes red on correct work is a gate somebody
    switches off.

    Applied to BOTH sides, so the only thing invisible here is whitespace at that one seam.
    Comments, ordering, quoting and blank lines anywhere else are compared exactly.
    """
    assert NEXT_JOB_MARKER in text, (
        f"no {NEXT_JOB_MARKER.strip()!r} in this copy of the workflow, so the seam has no "
        "position. A copy that lost that job, or whose line endings drifted to CRLF, arrives "
        "here -- and a ValueError from `str.index` names neither."
    )
    index = text.index(NEXT_JOB_MARKER)
    head = text[:index].rstrip("\n")
    return f"{head}\n{text[index:]}"


def test_the_shipped_workflow_matches_byte_for_byte_outside_the_unshipped_job() -> None:
    """Everything outside the `adversarial` job has to be identical, comments included.

    Review measured the structural comparison passing when a blank line was added to the root
    copy alone -- correct for YAML, and still a difference a derived project receives. This is
    the assertion that makes "every other difference is drift" true as written.

    One exception, declared in `_without_blank_lines_at_the_seam` and applied to both sides:
    blank lines immediately before the job that follows the removed one. Everything else,
    comments included, has to match exactly.
    """
    root_text = (ROOT / WORKFLOW).read_bytes().decode("utf-8")
    shipped_text = (RESOURCES / WORKFLOW).read_bytes().decode("utf-8")

    for marker, name in (
        (ADVERSARIAL_JOB_MARKER, "adversarial:"),
        (NEXT_JOB_MARKER, "attest:"),
        (ATTEST_NEEDS_ROOT, "attest's needs:"),
    ):
        assert root_text.count(marker) == 1, (
            f"the anchor for {name} occurs {root_text.count(marker)} times in the root workflow, "
            "so the cut below is not well defined"
        )
    # Not just "comes after": IMMEDIATELY after. The cut runs from one anchor to the other, so a
    # job inserted between them is swallowed whole -- and review measured that happening with a
    # job mirrored correctly into both copies, which then read as drift that did not exist.
    # `yaml.safe_load` preserves insertion order, so this is measurable rather than assumed.
    order = list(cast(dict[str, Any], cast(dict[str, Any], yaml.safe_load(root_text))["jobs"]))
    position = order.index(UNSHIPPED_JOB)
    assert order[position + 1 :][:1] == ["attest"], (
        f"the end anchor assumes `attest` comes immediately after `{UNSHIPPED_JOB}`; the jobs are "
        f"now {order}. Update the anchors -- anything between them is being cut away silently."
    )

    assert _root_text_without_the_unshipped_job(root_text) == _without_blank_lines_at_the_seam(
        shipped_text
    ), (
        "the two copies of quality.yml differ outside the `adversarial` job -- including in "
        "whitespace or comments, which the structural comparison cannot see"
    )


def test_the_two_copies_agree_on_their_line_endings() -> None:
    """The one pair taken off the exclusion list is the one pair whose bytes nothing asserts.

    `Path.read_text` opens in text mode with universal newlines, so `\r\n` arrives as `\n` and a
    copy that drifted to CRLF compares equal to one that did not. There is no `.gitattributes`
    in this repository and git has warned about CRLF in the working tree during this session, so
    the drift is reachable. Measured by review, not imagined.
    """
    root_bytes = (ROOT / WORKFLOW).read_bytes()
    shipped_bytes = (RESOURCES / WORKFLOW).read_bytes()

    assert (b"\r\n" in root_bytes) == (b"\r\n" in shipped_bytes), (
        "the two copies of quality.yml disagree about line endings, which the structural "
        "comparison cannot see because it parses both"
    )


def test_the_needs_rewrite_actually_rewrites_something() -> None:
    """`str.replace` used to do the rewriting, and a replace that matches nothing is a silent
    no-op: review measured that a root `attest` which had lost `adversarial` from its `needs:`
    compared equal to the shipped copy, so the test passed on a root workflow that was wrong.

    The rewrite is structural now, so this asserts the precondition it depends on instead: the
    root really does declare the dependency this comparison exists to strip.
    """
    root = yaml.safe_load((ROOT / WORKFLOW).read_bytes().decode("utf-8"))
    attest_needs = root["jobs"]["attest"]["needs"]

    assert UNSHIPPED_JOB in attest_needs, (
        f"the root `attest` job no longer needs `{UNSHIPPED_JOB}`, so the signing verdict no "
        "longer depends on the mutation battery -- a change this test would otherwise hide"
    )


def test_the_removal_leaves_a_workflow_that_still_has_its_other_jobs() -> None:
    """The transformation above is only honest if it removes one job and not the file. Without
    this, a bug that emptied `jobs` would make the comparison trivially true.
    """
    rendered = _workflow_as_shipped((ROOT / WORKFLOW).read_bytes().decode("utf-8"))
    jobs = cast(dict[str, Any], rendered["jobs"])

    assert set(jobs) == {"delivery-policy", "quality", "attest"}, (
        f"the transformation left {sorted(jobs)}, which is not the root workflow minus one job"
    )
    attest = cast(dict[str, Any], jobs["attest"])
    assert UNSHIPPED_JOB not in cast(list[str], attest["needs"])
