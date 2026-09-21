"""Issue #15: `scripts/agent_watch` had no tests at all.

Measured when the issue was opened: `git ls-tree -r --name-only main | grep -i agent.watch` returned
six files, all under `scripts/agent_watch/`, none under `tests/`. The slice had passed `pyright`
strict and `ruff`, so the boundary was typed and no behaviour was asserted anywhere.

The issue named two consequences, and both are what this suite is built around.

THE FIRST, and the one that was a live defect. The module's own docstring states the contract:
"every unknown shape degrades to a ("raw", preview) event instead of raising". The typing pass
replaced the exception path with `isinstance` guards and, for a field of the wrong type, turned
"degrade to raw" into "drop in silence" -- declared in that commit message, asserted nowhere. For
a viewer whose entire purpose is showing what a subagent did, silence is the worst of the three
possible answers: raising is loud, raw is honest, dropping quietly is a viewer that lies about the
transcript. The tests below fix the contract in place, in both directions: odd shapes surface, and
ordinary shapes are not turned into noise.

THE SECOND: `rich` is an optional runtime import in `watch_grid.py`, neither installed nor
declared, so nothing failed if that import path rotted. It is exercised here with `rich` made
genuinely unimportable.

What is deliberately NOT tested: the terminal rendering itself. `watch_stream.emit` and
`watch_grid.grid` produce strings for a human to look at; pinning their exact layout would make
every cosmetic change a test failure, which is how a suite teaches people to ignore it. The
parsing, the tailing, the counters and the import contract are what other code depends on.
"""

from __future__ import annotations

import builtins
import importlib
import importlib.util
import json
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from agent_watch import subagent_feed as feed  # noqa: E402


def line(**payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False)


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


# --------------------------------------------------------------------------------------
# The contract: odd shapes surface as `raw`, they are never dropped
# --------------------------------------------------------------------------------------


#: Shapes the reader has no rule for. Typed explicitly because inference over a literal list of
#: heterogeneous payloads produces a union pyright's strict mode calls partially unknown.
UNKNOWN_SHAPES: list[tuple[str, dict[str, Any]]] = [
    ("message is a string, not an object", {"message": "totally new shape"}),
    ("message is a list", {"message": [1, 2, 3]}),
    ("message is a number", {"message": 7}),
    ("content is a number", {"message": {"content": 42}}),
    ("content is an object", {"message": {"content": {"unexpected": "shape"}}}),
    ("a content block is a string", {"message": {"content": ["not-a-block"]}}),
    ("a content block is a list", {"message": {"content": [[1, 2]]}}),
    ("a content block is null", {"message": {"content": [None]}}),
    # The shape the contract is actually about, and the one the first version of this
    # slice still dropped: a block type nobody here has heard of. A harness that changes
    # format does not send `message: 7`; it adds a block type. All three below are real
    # ones in this family.
    ("an image block", {"message": {"content": [{"type": "image", "source": {}}]}}),
    ("a redacted thinking block", {"message": {"content": [{"type": "redacted_thinking"}]}}),
    ("a server tool use block", {"message": {"content": [{"type": "server_tool_use"}]}}),
    ("a block with no type at all", {"message": {"content": [{"name": "Bash"}]}}),
    # A recognised block type whose payload is not text disappeared just as quietly.
    (
        "a text block whose text is a number",
        {"message": {"content": [{"type": "text", "text": 42}]}},
    ),
    (
        "a thinking block whose thinking is an object",
        {"message": {"content": [{"type": "thinking", "thinking": {"a": 1}}]}},
    ),
    (
        "a tool result whose items are not blocks",
        {"message": {"content": [{"type": "tool_result", "content": [1, 2]}]}},
    ),
]


@pytest.mark.parametrize(("label", "payload"), UNKNOWN_SHAPES)
def test_an_unknown_shape_surfaces_as_raw(label: str, payload: dict[str, Any]) -> None:
    """THE regression this suite exists for. Each of these used to reach the reader as `raw`
    through the exception path, and after the typing pass reached nobody at all.
    """
    events = feed.parse_line(line(**payload), 80)

    assert events, f"{label}: the line produced no events at all, so the reader never saw it"
    assert any(kind == "raw" for kind, _text in events), (
        f"{label}: an unknown shape was classified as something other than raw: {events}"
    )


def test_a_block_that_cannot_be_parsed_does_not_hide_its_siblings() -> None:
    """Dropping silently is worse than it first looks: the blocks around the odd one still
    parse, so the reader gets a plausible-looking, incomplete line and no reason to doubt it.
    """
    events = feed.parse_line(
        line(message={"content": [text_block("before"), "broken", text_block("after")]}), 80
    )

    kinds = [kind for kind, _text in events]
    assert kinds == ["text", "raw", "text"], f"the odd block did not keep its place: {events}"


def test_a_line_that_is_not_json_at_all_is_raw() -> None:
    events = feed.parse_line("{this is not json", 80)

    assert [kind for kind, _text in events] == ["raw"]


def test_a_line_that_is_valid_json_but_not_an_object_is_raw() -> None:
    events = feed.parse_line("[1, 2, 3]", 80)

    assert [kind for kind, _text in events] == ["raw"]


def test_a_line_with_no_message_is_quiet_rather_than_raw() -> None:
    """The other side of the contract. If every line without a `message` were reported as raw,
    the view would fill with noise and the mechanism above would be worthless in practice.
    """
    assert feed.parse_line(line(type="user", uuid="abc"), 80) == []


@pytest.mark.parametrize("skipped", sorted(feed.SKIP_TYPES))
def test_the_skipped_types_stay_skipped(skipped: str) -> None:
    assert feed.parse_line(line(type=skipped, message={"content": [text_block("x")]}), 80) == []


# --------------------------------------------------------------------------------------
# The ordinary shapes, so the guard above cannot pass by classifying everything as raw
# --------------------------------------------------------------------------------------


def test_each_known_block_becomes_its_own_kind() -> None:
    events = feed.parse_line(
        line(
            message={
                "content": [
                    text_block("an answer"),
                    {"type": "thinking", "thinking": "a thought"},
                    {"type": "tool_use", "name": "Bash", "input": {"command": "ls -la"}},
                    {"type": "tool_result", "content": "output"},
                    {"type": "tool_result", "content": "boom", "is_error": True},
                ]
            }
        ),
        80,
    )

    assert [kind for kind, _text in events] == ["text", "think", "tool", "res", "err"]
    assert "ls -la" in dict(events)["tool"]


def test_a_string_message_is_the_prompt_unless_it_is_meta() -> None:
    assert feed.parse_line(line(message={"content": "do the thing"}), 80) == [
        ("prompt", "do the thing")
    ]
    assert feed.parse_line(line(isMeta=True, message={"content": "housekeeping"}), 80) == []


def test_a_tool_result_carried_as_blocks_is_joined() -> None:
    events = feed.parse_line(
        line(
            message={
                "content": [{"type": "tool_result", "content": [{"text": "a"}, {"text": "b"}]}]
            }
        ),
        80,
    )

    assert events == [("res", "a b")]


def test_an_empty_tool_result_says_so_rather_than_vanishing() -> None:
    events = feed.parse_line(
        line(message={"content": [{"type": "tool_result", "content": ""}]}), 80
    )

    assert events == [("res", "(vazio)")]


def test_tool_line_prefers_the_input_a_human_would_recognise() -> None:
    assert feed.tool_line({"name": "Read", "input": {"file_path": "/x/y.py"}}, 40) == (
        "Read  /x/y.py"
    )
    assert feed.tool_line({"name": "Bash"}, 40) == "Bash"
    assert feed.tool_line({"name": "Odd", "input": {"zzz": "value"}}, 40).startswith("Odd  {")


def test_short_collapses_whitespace_and_marks_what_it_cut() -> None:
    assert feed.short("  a\n b\tc ", 80) == "a b c"
    assert feed.short("abcdef", 4) == "abc…"
    assert feed.short("abcdef", 1) == "a"


# --------------------------------------------------------------------------------------
# Tailing: the part that keeps state between polls
# --------------------------------------------------------------------------------------


def transcript(tmp_path: Path, name: str = "agent-abc123") -> Path:
    path = tmp_path / f"{name}.jsonl"
    path.write_text("", encoding="utf-8")
    return path


def append(path: Path, *lines: str) -> None:
    with path.open("a", encoding="utf-8") as handle:
        for one in lines:
            handle.write(one + "\n")


def test_a_tail_reads_only_what_is_new(tmp_path: Path) -> None:
    path = transcript(tmp_path)
    tail = feed.AgentTail(path, from_start=True)
    append(path, line(message={"content": [text_block("first")]}))

    first = tail.poll(80)
    second = tail.poll(80)
    append(path, line(message={"content": [text_block("second")]}))
    third = tail.poll(80)

    assert first == [("text", "first")]
    assert second == [], "a poll with nothing new must not replay what was already read"
    assert third == [("text", "second")]


def test_a_truncated_file_is_reread_from_the_beginning(tmp_path: Path) -> None:
    """A file shorter than the offset means it was rotated or rewritten. Keeping the old offset
    would silently skip everything up to it.
    """
    path = transcript(tmp_path)
    tail = feed.AgentTail(path, from_start=True)
    append(path, line(message={"content": [text_block("before rotation")]}))
    tail.poll(80)

    path.write_text(line(message={"content": [text_block("after rotation")]}) + "\n", "utf-8")

    assert tail.poll(80) == [("text", "after rotation")]


def test_counters_follow_the_events_they_count(tmp_path: Path) -> None:
    path = transcript(tmp_path)
    tail = feed.AgentTail(path, from_start=True)
    append(
        path,
        line(message={"content": [{"type": "tool_use", "name": "Bash", "input": {}}]}),
        line(message={"content": [{"type": "tool_result", "content": "x", "is_error": True}]}),
        line(message={"content": [text_block("prose counts for neither")]}),
    )

    tail.poll(80)

    assert (tail.tools, tail.errors) == (1, 1)


def test_the_handback_is_what_marks_an_agent_finished(tmp_path: Path) -> None:
    path = transcript(tmp_path)
    tail = feed.AgentTail(path, from_start=True)
    assert tail.status() == "ativo"

    append(path, line(message={"content": [{"type": "tool_use", "name": feed.AgentTail.HANDBACK}]}))
    tail.poll(80)

    assert tail.handed_back is True
    assert tail.status() == "fim"


def test_an_agent_that_finished_before_we_looked_reads_as_finished(tmp_path: Path) -> None:
    """Tail mode starts at end of file, so without this an agent that had already handed back
    would sit in the view as merely idle, forever.
    """
    path = transcript(tmp_path)
    append(path, line(message={"content": [{"type": "tool_use", "name": feed.AgentTail.HANDBACK}]}))

    assert feed.AgentTail(path, from_start=False).handed_back is True


def test_an_idle_agent_is_not_a_finished_one(tmp_path: Path) -> None:
    path = transcript(tmp_path)
    tail = feed.AgentTail(path, from_start=True)
    tail.last_write = 0.0

    assert tail.status(idle_after=90) == "parado"
    assert tail.handed_back is False


def test_a_file_that_disappears_is_not_an_exception(tmp_path: Path) -> None:
    """The harness deletes and rotates these files while the viewer runs."""
    path = transcript(tmp_path)
    tail = feed.AgentTail(path, from_start=True)
    path.unlink()

    assert tail.poll(80) == []


def test_missing_metadata_leaves_the_agent_identifiable(tmp_path: Path) -> None:
    path = transcript(tmp_path)

    tail = feed.AgentTail(path, from_start=True)

    assert tail.id == "abc123"
    assert (tail.type, tail.description) == ("?", "")


def test_metadata_is_read_when_it_is_there(tmp_path: Path) -> None:
    path = transcript(tmp_path)
    (tmp_path / "agent-abc123.meta.json").write_text(
        json.dumps({"agentType": "reviewer", "description": "review the diff"}), encoding="utf-8"
    )

    tail = feed.AgentTail(path, from_start=True)

    assert (tail.type, tail.description) == ("reviewer", "review the diff")


def test_malformed_metadata_does_not_stop_the_viewer(tmp_path: Path) -> None:
    path = transcript(tmp_path)
    (tmp_path / "agent-abc123.meta.json").write_text("{not json", encoding="utf-8")

    assert feed.AgentTail(path, from_start=True).type == "?"


# --------------------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------------------


def test_a_feed_reports_each_agent_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "project"
    session = project / "session-1" / "subagents"
    session.mkdir(parents=True)
    (session / "agent-one.jsonl").write_text("", encoding="utf-8")

    def files(_project: Path, _all_sessions: bool = False) -> Iterator[Path]:
        return iter(sorted(session.glob("agent-*.jsonl")))

    monkeypatch.setattr(feed, "agent_files", files)
    stream = feed.Feed(project)

    first = stream.discover()
    again = stream.discover()
    (session / "agent-two.jsonl").write_text("", encoding="utf-8")
    third = stream.discover()

    assert [tail.id for tail in first] == ["one"]
    assert again == [], "an agent already known must not be announced a second time"
    assert [tail.id for tail in third] == ["two"]
    assert list(stream.agents) == ["one", "two"], "discovery order is the display order"


def test_a_feed_only_reports_agents_that_moved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    session = project / "session-1" / "subagents"
    session.mkdir(parents=True)
    quiet = session / "agent-quiet.jsonl"
    busy = session / "agent-busy.jsonl"
    quiet.write_text("", encoding="utf-8")
    busy.write_text("", encoding="utf-8")

    def files(_project: Path, _all_sessions: bool = False) -> Iterator[Path]:
        return iter([quiet, busy])

    monkeypatch.setattr(feed, "agent_files", files)
    stream = feed.Feed(project, from_start=True)
    stream.discover()
    append(busy, line(message={"content": [text_block("working")]}))

    moved = stream.poll(80)

    assert [tail.id for tail, _events in moved] == ["busy"]


def test_the_project_slug_survives_separators_and_case() -> None:
    assert feed.slug_for("/a/b/c") == feed.slug_for(Path("/a/b/c"))
    assert "/" not in feed.slug_for("/a/b/c")


# --------------------------------------------------------------------------------------
# The optional dependency
# --------------------------------------------------------------------------------------


def isolate_watch_grid(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let `watch_grid` be imported fresh without leaking into the rest of the session.

    `watch_grid` inserts its own directory on `sys.path` and imports the BARE top-level
    `subagent_feed` before it ever touches rich, so both survive even a refused import. Left
    alone, the process then holds two distinct `subagent_feed` module objects, and a later test
    that patches one of them is patching the copy its subject does not use.
    """
    monkeypatch.setattr(sys, "path", list(sys.path))
    for module in list(sys.modules):
        if module == "subagent_feed" or module.startswith("agent_watch.watch_grid"):
            monkeypatch.delitem(sys.modules, module, raising=False)


def test_the_grid_view_imports_when_rich_is_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Issue #15's second consequence, the half that the refusal test cannot reach.

    `rich` is now declared -- optional extra for users, dev group so this runs -- which is what
    makes this test possible at all. Before, `watch_grid` could not be imported under `uv run`,
    so every name it binds from rich was exactly as unexercised as the issue complained: a
    rename in rich would have broken the grid view with no gate anywhere noticing, and a test
    asserting only the failure would have stayed green through it.
    """
    isolate_watch_grid(monkeypatch)

    grid = importlib.import_module("agent_watch.watch_grid")

    for name in ["Group", "Live", "Panel", "Table", "Text", "Console"]:
        assert getattr(grid, name, None) is not None, f"watch_grid lost its binding for {name}"


def test_the_grid_view_says_what_to_install_when_rich_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal, with rich genuinely present so the blocker below is what produces it.

    While rich was undeclared this test passed for the wrong reason: the package was missing
    anyway, and removing the blocker changed nothing.
    """
    assert importlib.util.find_spec("rich") is not None, (
        "rich must be installed for this test to measure its own mechanism rather than the "
        "environment; it is declared in the dev group for exactly that reason"
    )
    real_import = builtins.__import__

    def without_rich(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "rich" or name.startswith("rich."):
            raise ImportError("No module named 'rich'")
        return real_import(name, *args, **kwargs)

    isolate_watch_grid(monkeypatch)
    monkeypatch.setattr(builtins, "__import__", without_rich)

    with pytest.raises(SystemExit) as refusal:
        importlib.import_module("agent_watch.watch_grid")

    assert "rich" in str(refusal.value)
    assert "install" in str(refusal.value)


def test_the_last_write_is_seeded_from_the_file_in_both_modes(tmp_path: Path) -> None:
    """Named for the thing it measures. Before this, breaking the seeding produced one red test
    called "handback", which points a reader at the wrong defect.

    `from_start` says where to begin reading; it says nothing about what is known of the file.
    While the seeding only happened in tail mode, an agent discovered in `--from-start` read as
    `parado` and sorted last -- `watch_grid.visible_boxes` orders by `last_write` -- however busy
    it actually was, until its first poll.
    """
    path = transcript(tmp_path)
    append(path, line(message={"content": [text_block("busy right now")]}))
    mtime = path.stat().st_mtime

    assert feed.AgentTail(path, from_start=True).last_write == mtime
    assert feed.AgentTail(path, from_start=False).last_write == mtime


def test_a_file_that_cannot_be_measured_is_not_reported_as_the_busiest(tmp_path: Path) -> None:
    """The fallback, pinned to the conservative answer on purpose.

    `time.time()` was the alternative, and it would present a file the tool could not even stat
    as the most recently active agent in the project -- first in the ordering, and driving the
    footer's "last activity" to zero. Unknown sorts last.
    """
    tail = feed.AgentTail(tmp_path / "agent-missing.jsonl", from_start=True)

    assert tail.last_write == 0.0
    assert tail.status() == "parado"


def project_with_sessions(root: Path, slug: str, sessions: list[str]) -> Path:
    project = root / slug
    for session in sessions:
        (project / session / "subagents").mkdir(parents=True)
    return project


def test_only_the_newest_session_is_read_unless_all_is_asked_for(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--all` is a user-facing flag whose entire mechanism is this function, and nothing
    asserted that its default reads exactly one session.
    """
    project = project_with_sessions(tmp_path, "proj", ["older", "newer"])
    # `session_dirs` orders by the mtime of the `subagents` directory, not of the session, so
    # that is what has to differ here for this to measure the ordering at all.
    os.utime(project / "older" / "subagents", (1_000_000, 1_000_000))
    os.utime(project / "newer" / "subagents", (2_000_000, 2_000_000))

    assert [p.name for p in feed.session_dirs(project)] == ["newer"]
    assert sorted(p.name for p in feed.session_dirs(project, all_sessions=True)) == [
        "newer",
        "older",
    ]


def test_picking_a_project_prefers_the_current_directory_then_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first call of both entry points, and the one that can return None and become a
    `sys.exit`. Its branches -- substring filter, slug of the current directory, fallback to the
    newest of everything -- were entirely unmeasured.
    """
    root = tmp_path / "projects"
    here = tmp_path / "work" / "mine"
    here.mkdir(parents=True)
    mine = root / feed.slug_for(here)
    other = root / "some-other-project"
    mine.mkdir(parents=True)
    other.mkdir(parents=True)
    monkeypatch.setattr(feed, "projects_root", lambda: root)

    assert feed.pick_project(cwd=here) == mine, "the current directory's own project wins"
    assert feed.pick_project("some-other", cwd=here) == other, "an explicit filter wins over it"
    # The two "no match" cases are NOT symmetric, and the asymmetry is user-visible: an explicit
    # filter that matches nothing refuses, while standing in a directory with no project of its
    # own falls back to the newest project there is. Pinned because it reads like an oversight
    # and is in fact the more useful pair of behaviours -- asking for a named project and
    # silently getting a different one would be worse than exiting.
    assert feed.pick_project("nothing-matches-this", cwd=here) is None
    assert feed.pick_project(cwd=tmp_path / "unrelated") in {mine, other}


def test_picking_a_project_returns_none_when_there_is_nothing_to_pick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(feed, "projects_root", lambda: tmp_path / "empty")

    assert feed.pick_project() is None
