"""Tests for :mod:`src.ingestion.project_structure` (TASK-002)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.ingestion.project_structure import (
    CLIENT_SUBFOLDERS,
    ProjectAlreadyExistsError,
    create_client_project,
)


def test_creates_all_top_level_folders(tmp_path: Path) -> None:
    """AC-1: five top-level folders are created under {base_path}/{client_id}."""
    project_root = create_client_project("client-001", tmp_path)

    assert project_root == tmp_path / "client-001"
    assert project_root.is_dir()
    for subfolder in CLIENT_SUBFOLDERS:
        assert (project_root / subfolder).is_dir()


def test_returns_path_object_pointing_at_client_root(tmp_path: Path) -> None:
    """The return value is a Path to the created client project root."""
    result = create_client_project("client-002", tmp_path)

    assert isinstance(result, Path)
    assert result.name == "client-002"
    assert result.parent == tmp_path


def test_accepts_str_base_path(tmp_path: Path) -> None:
    """base_path may be supplied either as ``str`` or as ``Path``."""
    result = create_client_project("client-003", str(tmp_path))

    assert result == tmp_path / "client-003"
    assert result.is_dir()


def test_creates_missing_base_path_with_parents(tmp_path: Path) -> None:
    """A not-yet-existing base_path is created together with parents."""
    nested = tmp_path / "does" / "not" / "exist"

    project_root = create_client_project("client-004", nested)

    assert project_root.is_dir()
    for subfolder in CLIENT_SUBFOLDERS:
        assert (project_root / subfolder).is_dir()


def test_raises_when_project_already_exists(tmp_path: Path) -> None:
    """AC-2: a second call for the same client_id raises."""
    create_client_project("client-005", tmp_path)

    with pytest.raises(ProjectAlreadyExistsError):
        create_client_project("client-005", tmp_path)


def test_does_not_overwrite_existing_data(tmp_path: Path) -> None:
    """AC-2: existing files are preserved when the exception is raised."""
    project_root = create_client_project("client-006", tmp_path)
    marker = project_root / "01-transcripts" / "important.txt"
    marker.write_text("keep me", encoding="utf-8")

    with pytest.raises(ProjectAlreadyExistsError):
        create_client_project("client-006", tmp_path)

    assert marker.read_text(encoding="utf-8") == "keep me"


def test_rejects_empty_client_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        create_client_project("", tmp_path)


def test_rejects_whitespace_only_client_id(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        create_client_project("   ", tmp_path)


@pytest.mark.parametrize(
    "bad_client_id",
    ["../escape", "a/b", "a\\b", ".", "..", "nested/child"],
)
def test_rejects_path_traversal_client_id(
    tmp_path: Path, bad_client_id: str
) -> None:
    """client_id must not be able to escape base_path."""
    with pytest.raises(ValueError):
        create_client_project(bad_client_id, tmp_path)


def test_raises_oserror_when_base_path_is_a_file(tmp_path: Path) -> None:
    """A base_path pointing at an existing file yields an OSError."""
    file_path = tmp_path / "not_a_directory"
    file_path.write_text("", encoding="utf-8")

    with pytest.raises(OSError):
        create_client_project("client-007", file_path)