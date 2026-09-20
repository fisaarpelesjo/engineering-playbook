"""The closing keyword must originate in the pipeline, not in a human edit.

Measured on run 35533507737: `publish` rewrites the pull request body from
`.project/delivery/pr.md` on every run, so a `Closes #N` added by hand after the
pull request was opened is erased by the next publish, and the CI gate then
refuses the pull request for having no linked issue. The body therefore has to
carry the declared card itself.
"""

from __future__ import annotations

from engineering_playbook.delivery import issue_from_pr_body, pr_body


def test_the_body_closes_the_declared_issue() -> None:
    body = pr_body("fix(x): something", ["src/a.py"], issue=25)

    assert "Closes #25" in body
    assert issue_from_pr_body(body) == 25, (
        "the gate reads the body with the same function GitHub's keywords imply; "
        "if it cannot find the issue here, CI will refuse the pull request"
    )


def test_a_body_without_a_declared_card_carries_no_closing_keyword() -> None:
    """Silence is honest: a slice with no card must not fabricate one."""
    body = pr_body("fix(x): something", ["src/a.py"], issue=None)

    assert issue_from_pr_body(body) is None, body
