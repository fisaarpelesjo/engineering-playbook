from __future__ import annotations

from playbook_core import parse_args, verify_root


def main() -> int:
    args = parse_args("Inspect migration needs without overwriting customizations.")
    result = verify_root(args.root)
    if result.errors:
        print("Migration inspection found issues; resolve manually before applying migrations.")
        for error in result.errors:
            print(f"- {error}")
        return 1
    print("No migration required.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
