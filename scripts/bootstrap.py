from __future__ import annotations

from playbook_core import REQUIRED_FILES, parse_args


def main() -> int:
    args = parse_args("Check bootstrap readiness without silent overwrite.")
    missing = [path for path in REQUIRED_FILES if not (args.root / path).exists()]
    if missing:
        for path in missing:
            print(f"MISSING: {path}")
        return 1
    print("Bootstrap is already applied. No files overwritten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
