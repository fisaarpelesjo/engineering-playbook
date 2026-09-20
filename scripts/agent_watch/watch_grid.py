"""Grid view of Claude Code subagents: one box per agent, one window.

    python scripts/agent_watch/watch_grid.py                 # newest session, project of cwd
    python scripts/agent_watch/watch_grid.py --thinking      # include reasoning lines
    python scripts/agent_watch/watch_grid.py --all           # every session of the project
    python scripts/agent_watch/watch_grid.py --keep 600      # hold finished agents 10 min

Each box tails one agent-*.jsonl and keeps its own scrollback; the layout
re-flows as agents appear and finish. Reading only — nothing is written and the
main Claude session is untouched. Ctrl+C quits.
"""

import argparse
import contextlib
import os
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, cast

if os.name == "nt":
    # Soft-deprecated in favor of subprocess, but this is the documented way
    # to turn on ANSI/VT100 escapes in a legacy Windows console; a real
    # subprocess call here would be a redesign, not a typing fix.
    os.system("")  # pyright: ignore[reportDeprecated]
# sys.stdout is a plain TextIO to a type checker, so reach for reconfigure
# defensively: it exists on CPython's TextIOWrapper and is what makes the
# box-drawing characters survive a cp1252 console.
_reconfigure = getattr(sys.stdout, "reconfigure", None)
if _reconfigure is not None:
    with contextlib.suppress(Exception):
        _reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import subagent_feed as feed_mod  # noqa: E402

try:
    # rich has no bundled types and is optional at runtime (see except
    # below), so pyright cannot resolve or type these; the aliases are
    # recast right after the block instead of ignoring every call site.
    from rich.console import (  # pyright: ignore[reportMissingImports]
        Console as _Console,  # pyright: ignore[reportUnknownVariableType]
    )
    from rich.console import (  # pyright: ignore[reportMissingImports]
        Group as _Group,  # pyright: ignore[reportUnknownVariableType]
    )
    from rich.live import (  # pyright: ignore[reportMissingImports]
        Live as _Live,  # pyright: ignore[reportUnknownVariableType]
    )
    from rich.panel import (  # pyright: ignore[reportMissingImports]
        Panel as _Panel,  # pyright: ignore[reportUnknownVariableType]
    )
    from rich.table import (  # pyright: ignore[reportMissingImports]
        Table as _Table,  # pyright: ignore[reportUnknownVariableType]
    )
    from rich.text import (  # pyright: ignore[reportMissingImports]
        Text as _Text,  # pyright: ignore[reportUnknownVariableType]
    )
except ImportError:
    sys.exit("falta o pacote rich:  python -m pip install rich")

# rich is optional at runtime (see except above) and ships no type stubs, so
# pyright cannot know its real shapes. Cast once here rather than leaving
# every call site as Unknown or scattering a type: ignore per line.
Console = cast("type[Any]", _Console)
Group = cast("type[Any]", _Group)
Live = cast("type[Any]", _Live)
Panel = cast("type[Any]", _Panel)
Table = cast("type[Any]", _Table)
Text = cast("type[Any]", _Text)

STYLE: dict[feed_mod.Kind, str] = {
    "tool": "bold blue",
    "res": "dim",
    "err": "bold red",
    "text": "white",
    "think": "dim italic",
    "prompt": "green",
    "raw": "dim",
}
STATUS_STYLE: dict[str, str] = {"ativo": "bold green", "parado": "yellow", "fim": "dim"}
MIN_PANEL_W = 34
MIN_PANEL_H = 7


class Box:
    """One agent's scrollback."""

    def __init__(self, tail: feed_mod.AgentTail, maxlen: int = 400) -> None:
        self.tail = tail
        self.lines: deque[feed_mod.Event] = deque(maxlen=maxlen)

    def add(self, events: list[feed_mod.Event], show_thinking: bool) -> None:
        for kind, text in events:
            if kind == "think" and not show_thinking:
                continue
            self.lines.append((kind, text))

    def render(self, width: int, height: int) -> Any:
        t = self.tail
        status = t.status()
        head = Text()
        head.append(t.type, style="bold")
        head.append("  ")
        head.append(status, style=STATUS_STYLE.get(status, ""))
        if t.tools:
            head.append(f"  {t.tools} tools", style="dim")
        if t.errors:
            head.append(f"  {t.errors} err", style="bold red")

        body = Text()
        inner_w = max(width - 4, 10)
        visible = list(self.lines)[-max(height - 4, 1) :]
        if not visible:
            body.append("(sem eventos ainda)", style="dim")
        for i, (kind, text) in enumerate(visible):
            if i:
                body.append("\n")
            body.append(feed_mod.GLYPHS.get(kind, "-") + " ", style=STYLE.get(kind, ""))
            body.append(feed_mod.short(text, inner_w - 2), style=STYLE.get(kind, ""))

        title = Text(
            f"{t.id[:8]} {feed_mod.short(t.description, width - 16)}",
            style=STATUS_STYLE.get(status, ""),
        )
        return Panel(
            Group(head, body),
            title=title,
            title_align="left",
            height=height,
            width=width,
            border_style=STATUS_STYLE.get(status, ""),
        )


def human(seconds: float) -> str:
    """1476346.7 -> '17d'; keeps the footer readable for stale agents."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds // 60:.0f}min"
    if seconds < 86400:
        return f"{seconds // 3600:.0f}h"
    return f"{seconds // 86400:.0f}d"


def visible_boxes(
    boxes: dict[str, Box], keep_seconds: float, only_active: bool = False
) -> list[Box]:
    """Live agents first; finished ones drop off after keep_seconds."""
    alive: list[Box] = []
    for b in boxes.values():
        status = b.tail.status()
        if only_active and status != "ativo":
            continue
        if status == "fim" and b.tail.idle_for > keep_seconds:
            continue
        alive.append(b)
    alive.sort(key=lambda b: (b.tail.status() != "ativo", -b.tail.last_write))
    return alive


def grid(
    boxes: dict[str, Box],
    console: Any,
    keep_seconds: float,
    project_name: str,
    only_active: bool = False,
) -> Any:
    width = console.width
    height = console.height
    shown = visible_boxes(boxes, keep_seconds, only_active)
    if not shown:
        return Panel(
            Text("nenhum subagente ativo — esperando…", style="dim"),
            title=f"subagentes {project_name}",
        )

    cols = max(1, min(len(shown), width // MIN_PANEL_W))
    body_h = max(height - 2, MIN_PANEL_H)
    rows = max(1, body_h // MIN_PANEL_H)
    cap = cols * rows
    overflow = max(0, len(shown) - cap)
    shown = shown[:cap]
    rows_used = (len(shown) + cols - 1) // cols
    panel_w = max(MIN_PANEL_W, width // cols)
    panel_h = max(MIN_PANEL_H, body_h // rows_used)

    table = Table.grid(padding=0)
    for _ in range(cols):
        table.add_column()
    for i in range(0, len(shown), cols):
        table.add_row(*[b.render(panel_w, panel_h) for b in shown[i : i + cols]])

    active = sum(1 for b in boxes.values() if b.tail.status() == "ativo")
    tools = sum(b.tail.tools for b in boxes.values())
    errs = sum(b.tail.errors for b in boxes.values())
    last = min((b.tail.idle_for for b in boxes.values()), default=0)
    foot = Text()
    foot.append(f" {project_name}", style="bold")
    foot.append(f" · ativos {active}", style="bold green")
    foot.append(f" · caixas {len(boxes)}", style="dim")
    foot.append(f" · tools {tools}", style="dim")
    if errs:
        foot.append(f" · err {errs}", style="bold red")
    foot.append(f" · última escrita {human(last)}", style="dim")
    if overflow:
        foot.append(f" · +{overflow} fora da tela", style="yellow")
    foot.append(f" · {time.strftime('%H:%M:%S')}", style="dim")
    return Group(table, foot)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", help="substring of the project slug")
    ap.add_argument("--all", action="store_true", dest="all_sessions")
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument(
        "--keep",
        type=float,
        default=300,
        help="seconds a finished agent stays on screen (default 300)",
    )
    ap.add_argument("--interval", type=float, default=0.4)
    ap.add_argument(
        "--from-start", action="store_true", help="replay each transcript from its first line"
    )
    ap.add_argument(
        "--only-active",
        action="store_true",
        dest="only_active",
        help="show only agents writing right now",
    )
    ap.add_argument(
        "--once", action="store_true", help="print one frame and exit (for pipes and checks)"
    )
    ap.add_argument("--size", help="force terminal size, e.g. 150x40")
    args = ap.parse_args()

    project = feed_mod.pick_project(args.project)
    if project is None:
        sys.exit("nenhum projeto em ~/.claude/projects")

    size: tuple[int, int] | None = None
    if args.size:
        try:
            w, h = args.size.lower().split("x")
            size = (int(w), int(h))
        except ValueError:
            sys.exit("--size espera LARGURAxALTURA, por exemplo 150x40")
    console = Console(width=size[0] if size else None, height=size[1] if size else None)
    if not (console.encoding or "").lower().startswith("utf"):
        feed_mod.GLYPHS = feed_mod.GLYPHS_ASCII

    feed = feed_mod.Feed(project, args.all_sessions, args.from_start)
    boxes: dict[str, Box] = {}

    def tick() -> Any:
        for tail in feed.discover():
            boxes[tail.id] = Box(tail)
        width = max(20, console.width // max(1, min(len(boxes) or 1, console.width // MIN_PANEL_W)))
        for tail, events in feed.poll(width):
            boxes[tail.id].add(events, args.thinking)
        return grid(boxes, console, args.keep, project.name, args.only_active)

    if args.once:
        console.print(tick())
        return

    with Live(
        console=console, screen=console.is_terminal, refresh_per_second=4, transient=False
    ) as live:
        while True:
            live.update(tick())
            time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("bye")
