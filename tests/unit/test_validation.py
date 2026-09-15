"""Unit tests for src/ingestion/validation.py (TASK-003)."""
from __future__ import annotations

import pytest

from src.ingestion.validation import (
    InvalidPathComponentError,
    validate_path_component,
)


@pytest.mark.parametrize(
    "value",
    [
        "abc",
        "file.txt",
        "UPPER",
        "with-dash",
        "with_underscore",
        "123",
        "batch-20260908-120000",
        "sample.txt",
        "data.xlsx",
        "my.file.name.md",
    ],
)
def test_validate_path_component_accepts_valid(value: str) -> None:
    # Must not raise. Single dots (filename extensions) are allowed.
    validate_path_component(value, "field")


@pytest.mark.parametrize("value", ["", " ", "   ", "\t", "\n"])
def test_validate_path_component_rejects_empty_and_whitespace(value: str) -> None:
    with pytest.raises(InvalidPathComponentError):
        validate_path_component(value, "field")


def test_validate_path_component_rejects_single_dot() -> None:
    """'.' is the current directory and is rejected as an exact value."""
    with pytest.raises(InvalidPathComponentError):
        validate_path_component(".", "field")


def test_validate_path_component_rejects_double_dot_exact() -> None:
    """'..' is caught by the substring check (it contains '..')."""
    with pytest.raises(InvalidPathComponentError):
        validate_path_component("..", "field")


@pytest.mark.parametrize(
    "value",
    [
        "foo..bar",
        "a..b",
        "batch..001",
        "..hidden",
        "hidden..",
        "x..",
    ],
)
def test_validate_path_component_rejects_dotdot_substring(value: str) -> None:
    """C-001 (iter 5): '..' must be rejected as a substring, not only exact."""
    with pytest.raises(InvalidPathComponentError):
        validate_path_component(value, "field")


@pytest.mark.parametrize(
    "value",
    ["a/b", "a\\b", "/leading", "trailing/", "a/../b", "..\\x", "c:\\tmp"],
)
def test_validate_path_component_rejects_separators(value: str) -> None:
    with pytest.raises(InvalidPathComponentError):
        validate_path_component(value, "field")


@pytest.mark.parametrize("value", [" leading", "trailing "])
def test_validate_path_component_rejects_surrounding_whitespace(value: str) -> None:
    with pytest.raises(InvalidPathComponentError):
        validate_path_component(value, "field")


def test_validate_path_component_rejects_null_byte() -> None:
    with pytest.raises(InvalidPathComponentError):
        validate_path_component("a\x00b", "field")


def test_validate_path_component_rejects_non_string() -> None:
    with pytest.raises(InvalidPathComponentError):
        validate_path_component(123, "field")  # type: ignore[arg-type]


def test_validate_path_component_error_mentions_field_name() -> None:
    with pytest.raises(InvalidPathComponentError, match="batch_id"):
        validate_path_component("a/b", "batch_id")


def test_validate_path_component_error_mentions_dotdot_for_substring() -> None:
    with pytest.raises(InvalidPathComponentError, match="\\.\\."):
        validate_path_component("foo..bar", "batch_id")
