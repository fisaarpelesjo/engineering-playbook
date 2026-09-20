# GitHub Ruleset

`.github/rulesets/main.yml` documents the `main` protection policy APPLIED on the server
since 2026-09-20 (ruleset id 23734100, `gh api repos/:owner/:repo/rulesets/23734100`). It is
not a proposal: FR-001 requires server-side enforcement, verified by reading the API, not
declared in a file nobody applied.

Applied policy:

- prohibit direct push to `main`;
- require pull request, with `required_approving_review_count: 0` -- a single-maintainer
  repository cannot require a second approver, because GitHub refuses a self-approval; see
  the comment in `.github/rulesets/main.yml` itself;
- no bypass actor (`current_user_can_bypass: never`, `bypass_actors: []`), by the owner's
  decision, kept without exception;
- require mandatory checks (`delivery-policy`, `quality`);
- prohibit force push;
- prohibit deletion of `main`;
- require conversation resolution;
- allow only squash merge;
- allow auto-merge after gates;
- remove branch after merge.

`.github/workflows/quality.yml`'s `delivery-policy` job runs `scripts/verify_ruleset.py`
(step "Ruleset reconciliation") on every push and pull request: it reads the applied ruleset
through `gh api` and fails the check the moment this file and the server disagree (FR-002,
AC-006). Any change to this policy must land in `.github/rulesets/main.yml` AND be applied to
the server through `gh api` or the GitHub UI -- one without the other now fails CI.

