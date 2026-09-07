from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .commands import (
    command_checkpoint,
    command_doctor,
    command_migrate,
    command_reconcile,
    command_resume,
    command_verify,
)
from .delivery import main as delivery_main
from .installer import command_init, command_update


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="engineering-playbook")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_root(subparser: argparse.ArgumentParser) -> argparse.ArgumentParser:
        subparser.add_argument("--root", dest="command_root", type=Path)
        return subparser

    init = subparsers.add_parser("init", help="Install playbook files into a project.")
    init.add_argument("path", nargs="?", type=Path, default=Path.cwd())
    init.add_argument("--profile", choices=["lite", "standard", "strict"], default="standard")
    init.add_argument("--stack", default="python")
    init.add_argument("--agents", default="codex")
    init.add_argument("--ci", choices=["github", "none"], default="github")
    init.add_argument("--dry-run", action="store_true")
    init.add_argument(
        "--force",
        action="store_true",
        help="Reserved safe acknowledgement; it never overwrites conflicting files.",
    )
    init.add_argument("--source", default="package")

    update = subparsers.add_parser("update", help="Safely update managed playbook files.")
    update.add_argument("path", nargs="?", type=Path, default=Path.cwd())
    update.add_argument("--dry-run", action="store_true")

    add_root(subparsers.add_parser("doctor"))
    add_root(subparsers.add_parser("verify"))
    resume = add_root(subparsers.add_parser("resume"))
    resume.add_argument("--format", choices=["human", "markdown", "json"], default="human")
    reconcile = add_root(subparsers.add_parser("reconcile"))
    reconcile.add_argument("--apply", action="store_true")
    add_root(subparsers.add_parser("checkpoint"))
    add_root(subparsers.add_parser("migrate"))

    subparsers.add_parser("delivery", help="Run the safe Git delivery pipeline.")
    subparsers.add_parser("version")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    if raw_argv and raw_argv[0] == "delivery":
        delivery_args = raw_argv[1:]
        if "--root" not in delivery_args:
            delivery_args = ["--root", str(Path.cwd()), *delivery_args]
        return delivery_main(delivery_args)

    parser = build_parser()
    args = parser.parse_args(argv)
    root_arg = getattr(args, "command_root", None) or args.root
    root = root_arg.resolve(strict=False)
    if args.command == "init":
        return command_init(args)
    if args.command == "update":
        return command_update(args)
    if args.command == "doctor":
        return command_doctor(root)
    if args.command == "verify":
        return command_verify(root)
    if args.command == "resume":
        return command_resume(root, args.format)
    if args.command == "reconcile":
        return command_reconcile(root, args.apply)
    if args.command == "checkpoint":
        return command_checkpoint(root)
    if args.command == "migrate":
        return command_migrate(root)
    if args.command == "version":
        print(__version__)
        return 0
    parser.error("unknown command")
    return 2
