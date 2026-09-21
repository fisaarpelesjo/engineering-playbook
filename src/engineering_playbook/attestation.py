"""The conformance verdict, signed by the run that issued it -- spec 003 FR-006/FR-007, T208/T209.

WHY THIS MODULE EXISTS (issue #24, measured twice, closed by neither previous fix):

`last_verified_commit` could not survive a squash, because no commit can name the SHA that only
comes into existence once the squash creates it. Issue #30 swapped the field for
`last_verified_tree`, which is a pure function of content and does survive the squash. Measured on
run 35535830710, immediately after that slice landed, the defect reappeared one level down:

    recorded in state on main:  36863a3   tree of the code commit
    tree of main HEAD:          5b0a9f1   tree AFTER the chore(state) commit
    tree of main HEAD's parent: c268399

The commit that *records* the verdict changes the tree the verdict is about. Eight consecutive
push runs on `main` failed this way (35525340039 through 35553187426). The pattern is the one
spec 004 named: **the record is produced inside the transaction it describes, and producing it
falsifies what it asserts.** No value written into versioned content escapes it, because the
write is itself content.

WHAT THIS MODULE DOES ABOUT IT: the verdict stops being a field in the tree. It becomes an
attestation minted by the Actions run, signed through the run's OIDC identity, with the content
digest as its subject. SLSA states the requirement this satisfies directly -- the build platform
generates the provenance and the signing material is unreachable from user-defined steps
(https://slsa.dev/spec/v1.0/levels). The delivery executor can write anything it likes into
`.project/state.yml` and cannot mint one of these.

THE SUBJECT IS THE TREE, NOT THE COMMIT. `gh attestation verify` addresses a subject by its
sha256 digest, so what gets attested is a small file whose bytes are a pure function of the git
tree id (`subject_bytes` below). The git tree id is already the Merkle root of the content: it is
identical for the branch tip and for the squash GitHub creates from it, and it changes the moment
any byte of the content changes. Reproducing those bytes locally and handing the file to `gh
attestation verify` is therefore a question about content, not about history -- which is exactly
what a verdict that must survive a squash needs to be.

DECLARED LIMITS, because a mechanism whose reach is not stated is a claim nobody measured:

- Attestations require a public repository or a GitHub plan that includes them, so the verdict is
  minted only when the repository is public. That limit has TWO halves and they have to agree, or
  a private project inherits a gate nothing can pass: the workflow's own `if:` condition, and
  `repository_is_public` below, which `delivery.signed_verdict_refusal` consults before demanding
  a verdict. `verdict_is_expected` alone is not that answer -- it decides only what can be read
  off the tree, offline.
- A derived project declaring `ci: none` has no workflow and no workflow identity. It keeps the
  commit/ancestry gate in `core.verify_root` unchanged (owner decision, issue #30, FR-020).
- WHAT THE SIGNATURE PROVES, stated narrowly on purpose. It proves that a run of a workflow at
  `SIGNER_WORKFLOW_PATH`, in this repository, on a GitHub-hosted runner, signed these bytes. It
  does NOT prove which steps that workflow contained, because the workflow file travels in the
  branch being verified: whoever can push a branch here can push a `quality.yml` with the battery
  removed and obtain a signature from the same identity. Closing that requires a trusted builder
  -- the signing step moved into a reusable workflow on a protected ref, verified with
  `--signer-repo`/`--signer-digest` -- which changes the delivery topology and is the owner's
  call, recorded as open in `specs/003-no-stage-without-a-mechanism/spec.md`. What this does buy,
  and the state field never did: the signature is not forgeable by the delivery executor, and the
  identity that made it is external to that executor.
- The gate that consumes the verdict runs on the client, inside `delivery.command_merge`. Merging
  through the GitHub UI bypasses it. Making it a required status check is the same owner decision
  as above, and is recorded with it.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from .core import (
    GhUnavailableError,
    GitUnavailableError,
    gh_capture,
    git_tree,
    load_yaml,
    run_gh,
)

#: The file name the workflow attests, and the name a verifier reproduces. It travels in the
#: attestation's subject list, so changing it invalidates every verdict already minted.
SUBJECT_FILENAME = "content-verdict.txt"

#: Version marker inside the attested bytes. A change to `subject_bytes`' format changes every
#: digest, so the format carries its own version rather than leaving a verifier to infer one: a
#: verifier reading an old attestation must be able to say "different format", not "different
#: content".
SUBJECT_FORMAT = "engineering-playbook/content-verdict/v1"

#: The workflow whose OIDC identity is the root of trust. `gh attestation verify
#: --signer-workflow` pins the verdict to this path: an attestation minted by any other workflow
#: in the same repository -- one a pull request could add -- does not satisfy the gate.
SIGNER_WORKFLOW_PATH = ".github/workflows/quality.yml"

#: What `gh attestation verify` says when GitHub answered and holds no attestation for the digest,
#: as opposed to when the question could not be asked at all. Measured against this repository on
#: 2026-09-21, before any verdict existed: `Error: HTTP 404: Not Found (.../attestations/sha256:
#: <digest>?per_page=30&predicate_type=...)`. `gh` exits 1 for every failure, so the two are told
#: apart by what it printed; a shape not listed here is treated as a measurement that failed.
NO_ATTESTATION_MARKERS = (
    "no attestations found",
    "http 404",
)


def subject_bytes(tree: str) -> bytes:
    """The exact bytes attested for a content tree, byte-identical in CI and on a verifier.

    Trailing newline included on purpose: a file without one is the kind of difference an editor
    silently repairs, and a repaired byte here is a digest that no longer matches.
    """
    return f"{SUBJECT_FORMAT}\ntree {tree}\n".encode()


def subject_digest(tree: str) -> str:
    """The sha256 `gh attestation verify` matches on, as lowercase hex without a prefix."""
    return hashlib.sha256(subject_bytes(tree)).hexdigest()


class SubjectPathError(RuntimeError):
    """`--out` names a destination the subject file must not be written to."""


def write_subject(root: Path, out: Path, ref: str = "HEAD") -> str:
    """Write the subject file for `ref`'s tree and return that tree id.

    THE DESTINATION IS REFUSED WHEN IT IS INSIDE THE CHECKOUT. The whole point of this module is
    that a verdict artifact must not live in the content it is a verdict about: written into the
    tree, it changes the tree, and then it is the same self-reference one level down. That
    invariant used to be a sentence in a docstring, which is the class of control this repository
    treats as absent, so it is checked here. A symlink destination is refused for the same reason
    it is refused in `installer.ensure_safe_child`: the path that was checked is then not the path
    that gets written.

    An unborn ref is refused rather than signed. `git_tree` answers the sentinel `"unborn"` for a
    ref that does not resolve, and signing `tree unborn` would mint a verdict naming no content at
    all -- a silent default inside a path that is otherwise fail-closed.
    """
    tree = git_tree(root, ref)
    if tree == "unborn":
        raise SubjectPathError(f"{ref} nao resolve para nenhum commit, portanto nao ha conteudo")
    destination = out.expanduser().resolve()
    if destination.is_symlink():
        raise SubjectPathError(f"refusing to write the subject through a symlink: {destination}")
    if destination == root.resolve() or destination.is_relative_to(root.resolve()):
        raise SubjectPathError(
            f"refusing to write the subject inside the checkout ({destination}): an artifact "
            "written into the tree changes the tree it is a verdict about. Use a path outside "
            "the repository, such as the runner's temporary directory."
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(subject_bytes(tree))
    return tree


def repository_identity(root: Path) -> tuple[str, bool]:
    """`(owner/name, is_public)` for the repository `root` belongs to, as GitHub reports it.

    Both halves come from one call because both are needed together and disagreeing about them is
    the defect this function exists to prevent: the workflow mints a verdict only for a public
    repository, so anything that demands a verdict has to ask the same question before demanding
    it. A private repository that inherits a gate it can never pass gets the gate removed, and
    then nobody has it.

    Raises `GhUnavailableError` when `gh` cannot answer -- NFR-002: a control that cannot obtain
    its measurement fails, it does not pass quietly. This call is also what separates the two
    failure modes of `attestation_covers_tree` below: if this succeeded, `gh` exists, is
    authenticated and reached the network, so a verify that then fails is a verdict that is
    missing rather than a measurement that could not be taken.
    """
    data = json.loads(gh_capture(root, "repo", "view", "--json", "nameWithOwner,isPrivate"))
    return data["nameWithOwner"], not bool(data["isPrivate"])


def verdict_is_expected(root: Path) -> bool:
    """The OFFLINE half of "can this repository have a signed verdict at all".

    False for a derived project declaring `ci: none` (no workflow, therefore no workflow identity
    -- owner decision, issue #30) and for a repository without the workflow file. Both are
    readable off the tree, so they are decided here without a network round trip.

    NOT the whole answer: visibility is the other half and only GitHub can answer it. A caller
    that gates on a verdict must also consult `repository_identity` -- see
    `delivery.signed_verdict_refusal`, which does exactly that and treats a `gh` that cannot
    answer as a refusal rather than as permission.
    """
    lock_path = root / ".project/playbook.lock.yml"
    if lock_path.is_file():
        lock = load_yaml(lock_path)
        if lock.get("playbook", {}).get("ci", "github") == "none":
            return False
    return (root / SIGNER_WORKFLOW_PATH).is_file()


def attestation_covers_tree(root: Path, tree: str, slug: str | None = None) -> tuple[bool, str]:
    """Ask GitHub whether a verdict signed by `SIGNER_WORKFLOW_PATH` covers `tree`.

    Returns `(covered, detail)`. Raises `GhUnavailableError` when the measurement could not be
    taken at all, so a caller cannot convert "I could not ask" into "it is fine" (NFR-002).

    The subject file is rebuilt in a temporary directory from `tree` alone -- nothing about the
    local checkout other than that tree id reaches the digest -- and handed to `gh attestation
    verify`, which hashes it, fetches the attestations GitHub holds for that digest, and checks
    the signature and the signer identity. A third party can run the same two steps with no
    access to `.project/state.yml`, which is AC-004 stated as a procedure.
    """
    if slug is None:
        slug, _is_public = repository_identity(root)
    with tempfile.TemporaryDirectory() as workdir:
        subject_path = Path(workdir) / SUBJECT_FILENAME
        subject_path.write_bytes(subject_bytes(tree))
        completed = run_gh(
            root,
            "attestation",
            "verify",
            str(subject_path),
            "--repo",
            slug,
            "--signer-workflow",
            f"{slug}/{SIGNER_WORKFLOW_PATH}",
            # A self-hosted runner is a machine outside GitHub's control, so a signature made on
            # one says nothing about the environment that produced it. This repository's workflow
            # declares `runs-on: ubuntu-latest`; refusing the rest costs nothing here and removes
            # a class of verdict this gate never intended to accept.
            "--deny-self-hosted-runners",
        )
    if completed.returncode == 0:
        return True, f"signed verdict found for tree {tree} (subject {subject_digest(tree)})"
    detail = completed.stderr.strip() or completed.stdout.strip() or "gh reported no detail"
    # "GitHub answered: there is none" and "gh could not answer" are different facts, and a
    # reader who cannot tell them apart concludes the mechanism is broken when it is merely out
    # of reach. `gh attestation verify` exits 1 for both, so the answer is read out of what it
    # said: the absence markers below are the shapes GitHub returns when the digest simply has
    # no attestation. Anything else -- a 5xx, a rate limit, a `gh` without this subcommand --
    # raises, and every caller turns that into a refusal rather than a verdict (NFR-002).
    if not any(marker in detail.lower() for marker in NO_ATTESTATION_MARKERS):
        raise GhUnavailableError(
            f"gh nao conseguiu medir o veredicto para a tree {tree}, e uma medicao falhada nao "
            f"e uma afirmacao de ausencia: {detail}"
        )
    return False, (f"no signed verdict for tree {tree} (subject {subject_digest(tree)}): {detail}")


def command_attest_subject(root: Path, out: Path, ref: str = "HEAD") -> int:
    try:
        tree = write_subject(root, out, ref)
    except GitUnavailableError as failure:
        print(f"ERROR: git nao respondeu, portanto a tree nao foi medida: {failure}")
        return 1
    except SubjectPathError as failure:
        print(f"ERROR: {failure}")
        return 1
    print(f"tree {tree}")
    print(f"subject {subject_digest(tree)}")
    print(f"path {out}")
    return 0


def command_attest_verify(root: Path, ref: str = "HEAD") -> int:
    """AC-004 as a command: is this content's verdict signed, without trusting the state file?"""
    try:
        tree = git_tree(root, ref)
    except GitUnavailableError as failure:
        print(f"ERROR: git nao respondeu, portanto a tree nao foi medida: {failure}")
        return 1
    if tree == "unborn":
        print("ERROR: a ref nao resolve para nenhum commit, portanto nao ha conteudo a verificar")
        return 1
    try:
        slug, is_public = repository_identity(root)
        covered, detail = attestation_covers_tree(root, tree, slug)
    except GhUnavailableError as failure:
        print(f"ERROR: gh nao respondeu, portanto o veredicto assinado nao foi medido: {failure}")
        return 1
    if not is_public and not covered:
        # Reported rather than folded into the failure: "no verdict" and "no verdict is possible
        # here" are different answers, and a reader who cannot tell them apart concludes the
        # mechanism is broken when it is merely out of reach.
        print(
            f"NOTE: {slug} is private, so no verdict can be minted for it -- attestations need a "
            "public repository or a plan that includes them."
        )
    print(("OK: " if covered else "ERROR: ") + detail)
    return 0 if covered else 1
