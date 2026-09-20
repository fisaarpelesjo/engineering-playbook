from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from engineering_playbook.core import load_yaml, validate_schema, verify_root, write_yaml_atomic

ROOT = Path(__file__).resolve().parents[2]


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


# --- validate_schema: the unit that verify_root's schema checks are built on ---------------


def test_validate_schema_names_the_file_and_the_missing_field(tmp_path: Path) -> None:
    (tmp_path / ".project/schemas").mkdir(parents=True)
    shutil.copy(
        ROOT / ".project/schemas/state.schema.json",
        tmp_path / ".project/schemas/state.schema.json",
    )
    write_yaml_atomic(tmp_path / ".project/state.yml", {"schema_version": "1.0.0"})

    errors = validate_schema(tmp_path, ".project/state.yml", ".project/schemas/state.schema.json")

    assert errors, "an incomplete state.yml must not validate"
    assert any(
        ".project/state.yml" in error and "'status' is a required property" in error
        for error in errors
    )


def test_validate_schema_names_the_file_and_the_field_for_a_type_violation(
    tmp_path: Path,
) -> None:
    (tmp_path / ".project/schemas").mkdir(parents=True)
    shutil.copy(
        ROOT / ".project/schemas/state.schema.json",
        tmp_path / ".project/schemas/state.schema.json",
    )
    state = load_yaml(ROOT / ".project/state.yml")
    state["status"] = 12345
    write_yaml_atomic(tmp_path / ".project/state.yml", state)

    errors = validate_schema(tmp_path, ".project/state.yml", ".project/schemas/state.schema.json")

    # A type/enum violation's own message does not name the field ("12345 is not of type
    # 'string'") -- the field name must come from the JSON path validate_schema prepends.
    assert any(error.startswith(".project/state.yml.status:") for error in errors)


def test_validate_schema_passes_the_real_state_and_project_documents() -> None:
    assert validate_schema(ROOT, ".project/state.yml", ".project/schemas/state.schema.json") == []
    assert (
        validate_schema(ROOT, ".project/project.yml", ".project/schemas/project.schema.json") == []
    )


# --- verify_root: every workstream is checked, not only the first one ----------------------


def test_verify_root_validates_every_workstream_file(tmp_path: Path) -> None:
    target = tmp_path / "derived"
    assert run_script("scripts/bootstrap.py", "--target", str(target)).returncode == 0

    workstreams_dir = target / ".project/workstreams"
    workstreams_dir.mkdir(parents=True, exist_ok=True)
    valid = load_yaml(ROOT / ".project/workstreams/WS-001-engineering-playbook.yml")
    write_yaml_atomic(workstreams_dir / "WS-001-valid.yml", valid)
    # A second workstream, missing every required field: the pre-fix code only ever looked at
    # a single hardcoded filename, so this file would have been silently skipped.
    write_yaml_atomic(workstreams_dir / "WS-002-broken.yml", {"id": "WS-002"})

    result = verify_root(target)

    assert any("WS-002-broken.yml" in error for error in result.errors)
    assert not any("WS-001-valid.yml" in error for error in result.errors)


def test_verify_root_rejects_a_broken_state_document(tmp_path: Path) -> None:
    target = tmp_path / "derived"
    assert run_script("scripts/bootstrap.py", "--target", str(target)).returncode == 0

    state = load_yaml(target / ".project/state.yml")
    del state["status"]
    write_yaml_atomic(target / ".project/state.yml", state)

    result = verify_root(target)

    assert any(
        ".project/state.yml" in error and "'status' is a required property" in error
        for error in result.errors
    )
