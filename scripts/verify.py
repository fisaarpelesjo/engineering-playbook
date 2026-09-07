from __future__ import annotations

from playbook_core import parse_args, print_result, verify_root


def main() -> int:
    args = parse_args("Validate playbook structure, schemas and policies.")
    return print_result(verify_root(args.root))


if __name__ == "__main__":
    raise SystemExit(main())
