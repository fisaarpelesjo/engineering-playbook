"""Shared reader for Claude Code subagent transcripts.

Both views (`watch_stream.py`, the stream, and `watch_grid.py`, the grid)
import this module so the parsing lives in one place.

Source of truth on disk:
    ~/.claude/projects/<project-slug>/<session-id>/subagents/agent-<id>.jsonl
    ~/.claude/projects/<project-slug>/<session-id>/subagents/agent-<id>.meta.json

The harness appends to the .jsonl while a subagent works, so tailing it is a
live feed. The format is internal and can change between Claude Code releases:
every unknown shape degrades to a ("raw", preview) event instead of raising.
"""

import json
import re
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Literal, cast

# One transcript line, parsed from JSON, before we know its actual shape.
JSONObj = dict[str, object]

Kind = Literal["tool", "res", "err", "text", "think", "prompt", "raw"]
Event = tuple[Kind, str]

SKIP_TYPES: set[str] = {"attachment", "system", "summary"}
GLYPHS: dict[Kind, str] = {
    "tool": "→",
    "res": "←",
    "err": "✗",
    "text": "●",
    "think": "~",
    "prompt": "▶",
    "raw": "?",
}
GLYPHS_ASCII: dict[Kind, str] = {
    "tool": ">",
    "res": "<",
    "err": "x",
    "text": "*",
    "think": "~",
    "prompt": "|",
    "raw": "?",
}


def _as_json_obj(value: object) -> JSONObj | None:
    """Narrow an untyped JSON value to an object, or None if it isn't one."""
    return cast(JSONObj, value) if isinstance(value, dict) else None


def _as_json_list(value: object) -> list[object] | None:
    """Narrow an untyped JSON value to an array, or None if it isn't one."""
    return cast(list[object], value) if isinstance(value, list) else None


def _str(value: object, default: str = "") -> str:
    """Narrow an untyped JSON value to str, or fall back to `default`."""
    return value if isinstance(value, str) else default


def slug_for(path: Path | str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def projects_root() -> Path:
    return Path.home() / ".claude" / "projects"


def pick_project(filt: str | None = None, cwd: Path | str | None = None) -> Path | None:
    """Project dir: matching `filt`, else the one for `cwd`, else newest."""
    root = projects_root()
    if not root.is_dir():
        return None
    dirs = [p for p in root.iterdir() if p.is_dir()]
    if filt:
        cands = [p for p in dirs if filt.lower() in p.name.lower()]
    else:
        want = slug_for(cwd or Path.cwd())
        cands = [p for p in dirs if p.name == want] or dirs
    if not cands:
        return None
    return max(cands, key=lambda p: p.stat().st_mtime)


def session_dirs(project: Path, all_sessions: bool = False) -> list[Path]:
    ds = [d for d in project.iterdir() if d.is_dir() and (d / "subagents").is_dir()]
    ds.sort(key=lambda d: (d / "subagents").stat().st_mtime, reverse=True)
    return ds if all_sessions else ds[:1]


def agent_files(project: Path, all_sessions: bool = False) -> Iterator[Path]:
    for sess in session_dirs(project, all_sessions):
        yield from sorted((sess / "subagents").glob("agent-*.jsonl"))


def read_meta(jsonl_path: Path) -> JSONObj:
    mp = jsonl_path.parent / (jsonl_path.stem + ".meta.json")
    try:
        data: object = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return _as_json_obj(data) or {}


def short(s: object, n: int, ellipsis: str = "…") -> str:
    s = " ".join(str(s).split())
    if n <= 1:
        return s[:n]
    return s if len(s) <= n else s[: n - 1] + ellipsis


def tool_line(block: JSONObj, width: int) -> str:
    name = _str(block.get("name"), "?")
    inp = _as_json_obj(block.get("input"))
    if inp is None:
        return name
    for key in ("command", "file_path", "pattern", "path", "query", "url", "prompt", "description"):
        value = inp.get(key)
        if value:
            return f"{name}  {short(value, max(width, 8))}"
    return f"{name}  {short(json.dumps(inp, ensure_ascii=False), max(width, 8))}"


def events_of(obj: JSONObj, width: int) -> list[Event]:
    """One transcript line -> [(kind, text)]. Never raises on odd shapes."""
    if obj.get("type") in SKIP_TYPES:
        return []
    msg = _as_json_obj(obj.get("message")) or {}
    content = msg.get("content")
    out: list[Event] = []
    if isinstance(content, str):
        text = content.strip()
        if text and not obj.get("isMeta"):
            out.append(("prompt", short(text, width)))
    else:
        blocks = _as_json_list(content) or []
        for raw_block in blocks:
            block = _as_json_obj(raw_block)
            if block is None:
                continue
            bt = block.get("type")
            if bt == "text":
                text = _str(block.get("text")).strip()
                if text:
                    out.append(("text", short(text, width)))
            elif bt == "thinking":
                text = _str(block.get("thinking")).strip()
                if text:
                    out.append(("think", short(text, width)))
            elif bt == "tool_use":
                out.append(("tool", tool_line(block, width - 14)))
            elif bt == "tool_result":
                c: object = block.get("content")
                items = _as_json_list(c)
                if items is not None:
                    c = " ".join(_str((_as_json_obj(x) or {}).get("text", "")) for x in items)
                kind: Kind = "err" if block.get("is_error") else "res"
                out.append((kind, short(c or "(vazio)", width)))
    return out


def parse_line(line: str, width: int) -> list[Event]:
    try:
        obj = _as_json_obj(json.loads(line))
        if obj is None:
            raise TypeError("transcript line is not a JSON object")
        return events_of(obj, width)
    except Exception:
        return [("raw", short(line, width))]


class AgentTail:
    """Byte-offset tail of one agent-*.jsonl, plus what we know about it."""

    HANDBACK = "SubagentHandback"

    def __init__(self, path: Path, from_start: bool = False) -> None:
        self.path = path
        self.id = path.stem.replace("agent-", "")
        meta = read_meta(path)
        self.type: str = _str(meta.get("agentType"), "?")
        self.description: str = _str(meta.get("description"))
        self.offset = 0
        self.tools = 0
        self.errors = 0
        self.handed_back = False
        self.last_write = 0.0
        self.first_seen = time.time()
        if not from_start:
            try:
                self.offset = path.stat().st_size
                self.last_write = path.stat().st_mtime
            except OSError:
                pass
            # Tail mode starts at EOF, so an agent that already handed back
            # before we opened would look merely idle. Read the end of the
            # file once to learn it is finished.
            self.handed_back = self._ends_with_handback()

    def _ends_with_handback(self, window: int = 32768) -> bool:
        try:
            with self.path.open("rb") as fh:
                fh.seek(max(0, self.offset - window))
                chunk = fh.read().decode("utf-8", "replace")
        except OSError:
            return False
        return self.HANDBACK in chunk

    def poll(self, width: int) -> list[Event]:
        """New events since the last poll, as [(kind, text)]."""
        try:
            size = self.path.stat().st_size
        except OSError:
            return []
        if size < self.offset:
            self.offset = 0
        if size == self.offset:
            return []
        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as fh:
                fh.seek(self.offset)
                chunk = fh.read()
                self.offset = fh.tell()
        except OSError:
            return []
        self.last_write = time.time()
        events: list[Event] = []
        for line in chunk.splitlines():
            line = line.strip()
            if not line:
                continue
            for kind, text in parse_line(line, width):
                if kind == "tool":
                    self.tools += 1
                    if text.startswith(self.HANDBACK):
                        self.handed_back = True
                elif kind == "err":
                    self.errors += 1
                events.append((kind, text))
        return events

    @property
    def idle_for(self) -> float:
        return time.time() - self.last_write

    def status(self, idle_after: int = 90) -> str:
        if self.handed_back:
            return "fim"
        return "ativo" if self.idle_for < idle_after else "parado"


class Feed:
    """Every agent transcript of a project, discovered as it appears."""

    def __init__(self, project: Path, all_sessions: bool = False, from_start: bool = False) -> None:
        self.project = project
        self.all_sessions = all_sessions
        self.from_start = from_start
        self.agents: dict[str, AgentTail] = {}  # id -> AgentTail, insertion-ordered

    def discover(self) -> list[AgentTail]:
        """New AgentTails since the last call."""
        fresh: list[AgentTail] = []
        for f in agent_files(self.project, self.all_sessions):
            aid = f.stem.replace("agent-", "")
            if aid not in self.agents:
                tail = AgentTail(f, from_start=self.from_start)
                self.agents[aid] = tail
                fresh.append(tail)
        return fresh

    def poll(self, width: int) -> list[tuple[AgentTail, list[Event]]]:
        """[(AgentTail, [(kind, text), ...]), ...] for agents that moved."""
        moved: list[tuple[AgentTail, list[Event]]] = []
        for tail in self.agents.values():
            evs = tail.poll(width)
            if evs:
                moved.append((tail, evs))
        return moved
