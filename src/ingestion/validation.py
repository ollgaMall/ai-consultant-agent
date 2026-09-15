"""Path-component validation utilities shared across ingestion modules.

Extracted as a separate module so that multiple ingestion modules
(currently material_upload, later possibly project_structure after the
TASK-002 refactoring) can reuse the same rules for user-provided strings
that participate in building filesystem paths.
"""
from __future__ import annotations


class InvalidPathComponentError(ValueError):
    """Raised when a user-provided string is not safe as a single path component."""


# Exact values that must be rejected in full.
#
# ``.`` (current directory) makes no sense as a filename or batch folder;
# ``..`` is handled by the substring check below (it would also be caught
# here, but we keep the substring path as the single source of truth for
# that marker).
_FORBIDDEN_WHOLE = frozenset({"."})

# Substrings that must be rejected anywhere in the value.
#
# ``/``  - path separator on POSIX.
# ``\\``  - path separator on Windows; rejected everywhere for portability.
# ``\x00`` - NUL byte, never valid in a filename.
# ``..`` - directory-traversal marker; AC-3 (TASK-003) and the analogous
#         AC in TASK-002 both read 'contains ..', so this is enforced as
#         a substring, not only as an exact match.
#
# NOTE: ``.`` is deliberately NOT in this list. A single dot inside a
# filename (``sample.txt``, ``data.xlsx``) is a normal, required case for
# REQ-01 (DOCX/XLSX/TXT/MD uploads) and must be accepted. Only a value
# that consists solely of ``.`` is rejected (see _FORBIDDEN_WHOLE).
_FORBIDDEN_SUBSTRINGS = ("/", "\\", "\x00", "..")


def validate_path_component(value: str, field_name: str) -> None:
    """Validate that *value* is safe to use as a single path component.

    Rejects:
        - empty or whitespace-only strings;
        - strings with leading or trailing whitespace;
        - a value that is exactly ``.`` (current directory);
        - any string containing ``/``, ``\\``, ``\x00``, or the
          directory-traversal marker ``..`` (as a substring, per the
          'contains ..' wording of AC-3 in TASK-003).

    A single ``.`` inside the value (e.g. ``sample.txt``) is allowed.

    Parameters
    ----------
    value : str
        The user-provided string to validate.
    field_name : str
        Human-readable name of the field; included in error messages so the
        caller knows which input was rejected.

    Raises
    ------
    InvalidPathComponentError
        If *value* is unsafe to use as a path component.
    """
    if not isinstance(value, str):
        raise InvalidPathComponentError(
            f"{field_name} must be a string, got {type(value).__name__}"
        )
    if not value:
        raise InvalidPathComponentError(f"{field_name} must not be empty")
    if not value.strip():
        raise InvalidPathComponentError(
            f"{field_name} must not consist only of whitespace"
        )
    if value != value.strip():
        raise InvalidPathComponentError(
            f"{field_name} must not have leading or trailing whitespace"
        )
    if value in _FORBIDDEN_WHOLE:
        raise InvalidPathComponentError(
            f"{field_name} must not be {value!r} (current directory)"
        )
    for bad in _FORBIDDEN_SUBSTRINGS:
        if bad in value:
            raise InvalidPathComponentError(
                f"{field_name} must not contain {bad!r}"
            )
