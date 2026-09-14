"""Creation of the per-client folder structure.

This module implements the first node of the ingestion pipeline (TASK-002):
without a uniform folder layout the downstream modules (material upload,
manifest, digests, analysis output) have no defined place to write to.
"""
from __future__ import annotations

from pathlib import Path

__all__ = [
    "CLIENT_SUBFOLDERS",
    "ProjectAlreadyExistsError",
    "create_client_project",
]


CLIENT_SUBFOLDERS: tuple[str, ...] = (
    "01-transcripts",
    "02-product",
    "03-analysis",
    "04-deliverables",
    "05-client-materials",
)


class ProjectAlreadyExistsError(Exception):
    """Raised when a client project already exists at the target path."""


def create_client_project(client_id: str, base_path: str | Path) -> Path:
    """Create the standard folder structure for a new client project.

    The resulting layout is::

        {base_path}/{client_id}/
            01-transcripts/
            02-product/
            03-analysis/
            04-deliverables/
            05-client-materials/

    ``base_path`` is supplied by the caller (typically read from the
    application configuration) and is never hard-coded in this module.

    Args:
        client_id: Identifier of the client; used verbatim as the folder
            name. Must be a non-empty string without path separators.
        base_path: Root directory under which the client project folder
            is created. Created (with parents) if it does not exist yet.

    Returns:
        Path to the created client project root directory.

    Raises:
        ValueError: If ``client_id`` is empty, whitespace-only, or
            contains path separators / equals ``.`` or ``..``.
        ProjectAlreadyExistsError: If the client project directory
            already exists. Existing data is left untouched.
        OSError: If the underlying filesystem operation fails.
    """
    if not client_id or not client_id.strip():
        raise ValueError("client_id must be a non-empty string")

    if "/" in client_id or "\\" in client_id or client_id in {".", ".."}:
        raise ValueError(
            f"client_id must not contain path separators or be '.'/'..', got {client_id!r}"
        )

    project_root = Path(base_path) / client_id

    try:
        if project_root.exists():
            raise ProjectAlreadyExistsError(
                f"Client project already exists: {project_root}"
            )

        project_root.mkdir(parents=True, exist_ok=False)
        for subfolder in CLIENT_SUBFOLDERS:
            (project_root / subfolder).mkdir(exist_ok=False)
    except ProjectAlreadyExistsError:
        raise
    except OSError as exc:
        raise OSError(
            f"Failed to create client project structure at {project_root}: {exc}"
        ) from exc

    return project_root