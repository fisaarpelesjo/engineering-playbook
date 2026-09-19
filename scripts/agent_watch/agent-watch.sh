#!/usr/bin/env bash
# Live view of this session's Claude Code subagents, for a second terminal.
#
#   scripts/agent_watch/agent-watch.sh                    stream: one scrolling feed
#   scripts/agent_watch/agent-watch.sh --grid             grid: one box per agent
#   scripts/agent_watch/agent-watch.sh --grid --only-active
#   scripts/agent_watch/agent-watch.sh --grid --thinking --all
#
# Environment:
#   WATCH_DIR=<repo>     project to watch (default: the current directory)
#   WATCH_PYTHON=<path>  interpreter to use (default: first one that fits)
#
# The grid needs `rich`; the stream needs nothing beyond the standard library.
# A project virtualenv usually lacks `rich`, so the interpreter is probed
# rather than taken from PATH alone.
set -u

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${WATCH_DIR:-$PWD}" || exit 1
export PYTHONIOENCODING=utf-8

view="$here/watch_stream.py"
needs_rich=0
args=()
for a in "$@"; do
  if [ "$a" = "--grid" ]; then
    view="$here/watch_grid.py"
    needs_rich=1
  else
    args+=("$a")
  fi
done

# On Windows, `python3` is often the Microsoft Store stub: it exists on PATH
# and fails on the first run. So every candidate has to prove it runs.
pick_python() {
  local candidate probe="import sys"
  [ "$needs_rich" -eq 1 ] && probe="import rich"
  for candidate in "${WATCH_PYTHON:-}" python3 python py; do
    [ -n "$candidate" ] || continue
    command -v "$candidate" >/dev/null 2>&1 || continue
    if "$candidate" -c "$probe" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

py="$(pick_python || true)"
if [ -z "${py:-}" ]; then
  echo "no interpreter with 'rich' found (the grid needs it)." >&2
  echo "  pip install rich        # outside the project venv is fine" >&2
  echo "  WATCH_PYTHON=/path/to/python scripts/agent_watch/agent-watch.sh --grid" >&2
  echo "the stream view works without it: scripts/agent_watch/agent-watch.sh" >&2
  exit 1
fi

exec "$py" -u "$view" ${args[@]+"${args[@]}"}
