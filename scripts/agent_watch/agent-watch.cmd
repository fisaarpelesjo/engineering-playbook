@echo off
REM Live view of this session's Claude Code subagents, for a second terminal.
REM
REM   tools\agent-watch\agent-watch.cmd                 stream: one scrolling feed
REM   tools\agent-watch\agent-watch.cmd --grid          grid: one box per agent
REM   tools\agent-watch\agent-watch.cmd --grid --only-active
REM
REM   set WATCH_DIR=<repo>      project to watch (default: current directory)
REM   set WATCH_PYTHON=<path>   interpreter to use (default: py, then python)
chcp 65001 >nul
title Claude subagents
setlocal enabledelayedexpansion
if not "%WATCH_DIR%"=="" cd /d "%WATCH_DIR%"
set "PYTHONIOENCODING=utf-8"

set "VIEW=%~dp0watch_stream.py"
set "ARGS="
for %%a in (%*) do (
  if "%%a"=="--grid" (
    set "VIEW=%~dp0watch_grid.py"
  ) else (
    set "ARGS=!ARGS! %%a"
  )
)

REM A project venv usually lacks rich, so prefer an interpreter that has it.
if not "%WATCH_PYTHON%"=="" goto :run
set "WATCH_PYTHON=py"
py -c "import rich" >nul 2>&1 && goto :run
set "WATCH_PYTHON=python"

:run
"%WATCH_PYTHON%" -u "%VIEW%"!ARGS!
pause
