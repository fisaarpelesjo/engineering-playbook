"""Remove each mechanism and report whether the suite noticed (T216 / FR-017 / AC-012).

    uv run python scripts/mutation.py

Exits non-zero when any mechanism escapes its mutation, or when an entry has gone inert because
the code it names has moved. Runs against a copy under a temporary directory; the working tree is
read and never written.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from engineering_playbook.mutation import MUTATIONS, run_all

GLYPH = {"caught": "CAUGHT ", "escaped": "ESCAPED", "inert": "INERT  "}


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    print(f"removing {len(MUTATIONS)} mechanisms, one at a time\n")
    with tempfile.TemporaryDirectory(prefix="mutation-") as workdir:
        results = run_all(root, Path(workdir))

    for result in results:
        print(f"{GLYPH[result.verdict]}  {result.mutation.mechanism}")
        print(f"           {result.mutation.requirement} -- {result.detail}")

    unheld = [result for result in results if not result.ok]
    print()
    if not unheld:
        print(
            f"every one of the {len(results)} mechanisms is held by a test that failed without it"
        )
        return 0
    print(f"{len(unheld)} of {len(results)} mechanisms are not held:")
    for result in unheld:
        print(f"  {result.mutation.mechanism} ({result.verdict})")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
