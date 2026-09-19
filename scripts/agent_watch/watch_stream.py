"""Stream view of Claude Code subagents: one scrolling feed, all agents mixed.

    python scripts/agent_watch/watch_stream.py              # newest session, project of cwd
    python scripts/agent_watch/watch_stream.py --all        # every session of that project
    python scripts/agent_watch/watch_stream.py --thinking   # show reasoning too
    python scripts/agent_watch/watch_stream.py --project business-intelligence

For one box per agent instead, use watch_grid.py. Parsing and discovery live in
subagent_feed.py, shared by both views.
"""

import argparse
import contextlib
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subagent_feed as feed_mod  # noqa: E402

if os.name == "nt":
    os.system("")
# sys.stdout is a plain TextIO to a type checker, so reach for reconfigure
# defensively: it exists on CPython's TextIOWrapper and is what makes the
# box-drawing characters survive a cp1252 console.
_reconfigure = getattr(sys.stdout, "reconfigure", None)
if _reconfigure is not None:
    with contextlib.suppress(Exception):
        _reconfigure(encoding="utf-8", errors="replace")
UTF = (getattr(sys.stdout, "encoding", "") or "").lower().startswith("utf")

C = {
    "dim": "\033[2m",
    "red": "\033[31m",
    "grn": "\033[32m",
    "yel": "\033[33m",
    "blu": "\033[94m",
    "mag": "\033[35m",
    "cyn": "\033[36m",
    "off": "\033[0m",
    "bold": "\033[1m",
}
AGENT_COLORS = ["cyn", "mag", "yel", "grn", "blu", "red"]
KIND_COLOR = {
    "tool": "blu",
    "res": "dim",
    "err": "red",
    "text": "off",
    "think": "dim",
    "prompt": "grn",
    "raw": "dim",
}


def emit(tag, kind, text, glyphs):
    colour = C[KIND_COLOR.get(kind, "off")]
    stamp = time.strftime("%H:%M:%S")
    glyph = glyphs.get(kind, "-")
    line = f"{C['dim']}{stamp}{C['off']} {tag} {colour}{glyph} {text}{C['off']}"
    try:
        print(line)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="substring of the project slug")
    ap.add_argument(
        "--all",
        action="store_true",
        dest="all_sessions",
        help="watch every session, not just the newest",
    )
    ap.add_argument("--thinking", action="store_true", help="show reasoning")
    ap.add_argument("--width", type=int, default=150, help="max chars per line")
    ap.add_argument("--interval", type=float, default=0.4)
    ap.add_argument(
        "--from-start", action="store_true", help="replay existing lines instead of only new ones"
    )
    args = ap.parse_args()

    project = feed_mod.pick_project(args.project)
    if project is None:
        sys.exit("nenhum projeto em ~/.claude/projects")

    glyphs = feed_mod.GLYPHS if UTF else feed_mod.GLYPHS_ASCII
    feed = feed_mod.Feed(project, args.all_sessions, args.from_start)
    colors = {}

    print(
        f"{C['bold']}subagentes{C['off']} {C['dim']}{project.name}{C['off']}  (ctrl+c para sair)\n"
    )
    while True:
        for tail in feed.discover():
            colors[tail.id] = AGENT_COLORS[len(colors) % len(AGENT_COLORS)]
            colour = C[colors[tail.id]]
            print(
                f"\n{colour}+ {tail.id[:8]}{C['off']} "
                f"{C['bold']}{tail.type}{C['off']} "
                f"{C['dim']}{tail.description}{C['off']}"
            )
        for tail, events in feed.poll(args.width):
            tag = f"{C[colors[tail.id]]}{tail.id[:8]}{C['off']}"
            for kind, text in events:
                if kind == "think" and not args.thinking:
                    continue
                emit(tag, kind, text, glyphs)
        sys.stdout.flush()
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nbye")
