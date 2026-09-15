"""Material upload and registration (TASK-003 / REQ-01).

Provides:
    - :class:`MaterialRecord`        - dataclass describing one uploaded material.
    - :func:`register_material`      - copy a source file into the client project,
                                       unchanged, into a per-batch subfolder.
    - :func:`generate_batch_id`      - produce a batch identifier; MUST be called by
                                       the caller ONCE per upload action, NOT inside
                                       :func:`register_material` (see its docstring).
    - :class:`UnsupportedMaterialTypeError`,
      :class:`MaterialAlreadyExistsError`,
      :class:`SourceFileNotFoundError` - domain-specific error types.

Security model (after ChatGPT review, iterations 1-5):

    * **No check-then-use anywhere on the write path.** Every directory in
      the destination chain - including the root ``client_project_path`` -
      is opened by the kernel with ``O_NOFOLLOW | O_DIRECTORY`` and pinned
      as a file descriptor. Subsequent operations target those fds, so a
      concurrent rename+symlink substitution of any path component cannot
      redirect the write.

    * **Descriptor-relative, symlink-safe writes.**
          - The root ``client_project_path`` is opened with
            ``O_RDONLY | O_DIRECTORY | O_NOFOLLOW``.
          - ``05-client-materials`` and ``{batch_id}`` are opened or created
            via ``os.open(name, O_RDONLY | O_DIRECTORY | O_NOFOLLOW,
            dir_fd=parent_fd)`` / ``os.mkdir(name, dir_fd=parent_fd)``.
          - The target file is created via
            ``os.open(name, O_CREAT | O_EXCL | O_WRONLY | O_NOFOLLOW,
            dir_fd=batch_fd)``.

    * **Atomic collision semantics.** ``O_EXCL`` guarantees exactly one
      writer succeeds for a given ``(batch_id, filename)`` pair; the loser
      receives ``MaterialAlreadyExistsError``.

    * **Full-buffer writes.** ``os.write`` may perform a short write; the
      module loops until the entire buffer has been written (see
      ``_write_all``).

    * **Platform gate.** Descriptor-relative operations require ``dir_fd``,
      ``O_DIRECTORY``, and ``O_NOFOLLOW`` (POSIX). On platforms that lack
      them (notably Windows) there is no equivalent atomic mechanism in the
      Python standard library, so :func:`register_material` refuses to run
      with an explicit ``OSError`` rather than silently falling back to an
      unsafe check-then-use implementation.

    * **Every filesystem call is inside ``try/except OSError``.** This
      includes ``os.open`` / ``os.mkdir`` / ``os.write`` / ``os.read`` /
      ``os.lseek`` / ``os.unlink`` / ``os.close`` / ``os.fchmod`` /
      ``os.utime``, ``Path.open`` / ``Path.stat`` / ``Path.exists`` /
      ``Path.is_file`` / ``Path.is_dir``, and ``Path.resolve``. The only
      ``Path.resolve`` call in the module lives inside
      :func:`_default_config_path` (lazy, runtime-only) and is itself
      wrapped in ``try/except OSError`` - no filesystem access happens at
      module import time.

    * **Threat-model boundary (N-001, iteration 3).** A concurrent rename of
      the client project root *after* the root fd has been successfully
      opened is NOT in scope of this module: the fd remains bound to the
      inode that existed at open time, and the OS is responsible for the
      rest. :class:`MaterialRecord.path` reflects the intended location at
      the moment of the successful call.
"""
from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from src.ingestion.validation import validate_path_component

MATERIALS_SUBDIR = "05-client-materials"
_CONFIG_ENV_VAR = "MATERIAL_UPLOAD_CONFIG"
_CONFIG_RELATIVE_PATH = (
    "config",
    "material_upload.yaml",
)

_DEFAULT_BATCH_ID_STRATEGY = "uuid4"
_DEFAULT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S-%f"

# Feature detection for descriptor-relative filesystem operations.
# These are required to close the symlink-race (review C-001).
_HAS_DIR_FD_SUPPORT = (
    hasattr(os, "O_DIRECTORY")
    and hasattr(os, "O_NOFOLLOW")
    and isinstance(getattr(os, "supports_dir_fd", None), (set, frozenset))
    and os.open in os.supports_dir_fd
    and os.mkdir in os.supports_dir_fd
)


class UnsupportedMaterialTypeError(ValueError):
    """Raised when material_type is not in the configured supported set."""


class MaterialAlreadyExistsError(FileExistsError):
    """Raised on a filename collision inside a single batch folder."""


class SourceFileNotFoundError(FileNotFoundError):
    """Raised when source_file is missing or is not a regular file."""


@dataclass(frozen=True)
class MaterialRecord:
    """Registration record for a single material file.

    Attributes
    ----------
    path : Path
        Intended location of the copied file inside the client project
        (``05-client-materials/<batch_id>/<filename>``). See the module
        docstring, section 'Threat-model boundary': a concurrent rename of
        the project root after the successful call is out of scope, so
        ``path`` is not guaranteed to keep pointing at the same inode under
        adversarial concurrent modification of the project tree.
    type : str
        Material type tag exactly as supplied by the caller (e.g. ``'TXT'``
        or ``'txt'``). Validation is case-insensitive; the stored value is
        preserved as provided.
    batch_id : str
        Batch identifier shared by all files uploaded in the same action.
    uploaded_at : datetime
        Timezone-aware UTC timestamp of registration.
    """

    path: Path
    type: str
    batch_id: str
    uploaded_at: datetime


def generate_batch_id() -> str:
    """Generate a new batch identifier for one upload action.

    IMPORTANT: this function MUST be called EXACTLY ONCE per upload action
    (i.e. per group of files uploaded together by the consultant), by the
    caller - NOT inside :func:`register_material`. All files belonging to
    the same upload action must share the same ``batch_id``; generating a
    new one per file would break grouping in the manifest (TASK-004) and
    defeat the purpose of the ``batch_id`` field.

    The strategy is read from ``config/material_upload.yaml`` (or from the
    file pointed to by the ``MATERIAL_UPLOAD_CONFIG`` environment variable).
    Supported strategies: ``'uuid4'`` (default) and ``'timestamp'``.

    Returns
    -------
    str
        New batch identifier.

    Raises
    ------
    FileNotFoundError
        If the config file cannot be found.
    ValueError
        If the configured strategy is not recognised.
    """
    config = _load_config()
    batch_cfg = config.get("batch_id") or {}
    strategy = batch_cfg.get("strategy", _DEFAULT_BATCH_ID_STRATEGY)

    if strategy == "uuid4":
        return str(uuid.uuid4())
    if strategy == "timestamp":
        fmt = batch_cfg.get("timestamp_format", _DEFAULT_TIMESTAMP_FORMAT)
        return datetime.now(timezone.utc).strftime(fmt)
    raise ValueError(
        f"Unknown batch_id strategy: {strategy!r}. "
        f"Supported: 'uuid4', 'timestamp'."
    )


def register_material(
    client_project_path: Path,
    source_file: Path,
    material_type: str,
    batch_id: str,
) -> MaterialRecord:
    """Register a client material: validate inputs, copy the original
    unchanged into ``<client_project>/05-client-materials/<batch_id>/``,
    and return a :class:`MaterialRecord`.

    The write path is fully descriptor-relative (see module docstring) and
    is safe against symlink traversal and TOCTOU races. On platforms without
    ``dir_fd`` / ``O_DIRECTORY`` / ``O_NOFOLLOW`` support this function
    raises ``OSError`` rather than falling back to a non-atomic path.

    Parameters
    ----------
    client_project_path : Path
        Root of the client project (created by ``create_client_project``,
        TASK-002). Must exist, be a directory, and not be a symlink (the
        root is opened with ``O_NOFOLLOW``).
    source_file : Path
        Path to the source file to copy. Must exist and be a regular file.
    material_type : str
        Material type tag, e.g. ``'DOCX'``, ``'TXT'``, ``'AUDIO'``.
        Must be listed under ``supported_material_types`` in the config
        (validation is case-insensitive).
    batch_id : str
        Batch identifier shared by all files uploaded in a single action.
        Must be generated ONCE per upload action by the caller using
        :func:`generate_batch_id` - this function does NOT generate it
        internally.

    Returns
    -------
    MaterialRecord
        Registration record for the copied file.

    Raises
    ------
    InvalidPathComponentError
        If ``batch_id`` or the source filename is unsafe as a path
        component: contains ``/``, ``\\``, ``\x00``, or the directory-
        traversal marker ``..`` (as a substring), is empty, whitespace-only,
        or has leading/trailing whitespace. A single ``.`` inside the value
        (e.g. ``sample.txt``) is allowed.
    UnsupportedMaterialTypeError
        If ``material_type`` is not in the configured supported set.
    SourceFileNotFoundError
        If ``source_file`` does not exist or is not a regular file.
    FileNotFoundError
        If ``client_project_path`` does not exist.
    NotADirectoryError
        If ``client_project_path`` exists but is not a directory.
    MaterialAlreadyExistsError
        On a filename collision inside the target batch folder (enforced
        atomically via ``O_CREAT | O_EXCL``).
    OSError
        On any other filesystem error, on symlink traversal attempts
        (including a symlinked ``client_project_path`` itself), or on
        platforms without ``dir_fd`` support.
    """
    if not _HAS_DIR_FD_SUPPORT:
        raise OSError(
            "register_material requires POSIX descriptor-relative filesystem "
            "operations (os.open / os.mkdir with dir_fd, O_DIRECTORY, "
            "O_NOFOLLOW) to guarantee symlink-safe storage. This platform "
            "does not support them; refusing to fall back to a non-atomic "
            "path (see ChatGPT review C-001, iteration 2)."
        )

    config = _load_config()

    # ------------------------------------------------------------------
    # 1. Pure input validation - no filesystem access yet.
    # ------------------------------------------------------------------
    validate_path_component(batch_id, "batch_id")
    source_path = Path(source_file)
    source_name = source_path.name
    validate_path_component(source_name, "source_file.name")
    _validate_material_type(material_type, config)

    # ------------------------------------------------------------------
    # 2. Verify the client project root exists and is a directory.
    #    The definitive symlink check is O_NOFOLLOW at open time (step 5).
    # ------------------------------------------------------------------
    project_path = Path(client_project_path)
    try:
        if not project_path.exists():
            raise FileNotFoundError(
                f"client_project_path does not exist: {project_path}"
            )
        if not project_path.is_dir():
            raise NotADirectoryError(
                f"client_project_path is not a directory: {project_path}"
            )
    except (FileNotFoundError, NotADirectoryError):
        raise
    except OSError as exc:
        raise OSError(
            f"Failed to inspect client_project_path {project_path}: {exc}"
        ) from exc

    # ------------------------------------------------------------------
    # 3. Verify the source file is a regular file.
    # ------------------------------------------------------------------
    try:
        if not source_path.exists():
            raise SourceFileNotFoundError(
                f"source_file does not exist: {source_path}"
            )
        if not source_path.is_file():
            raise SourceFileNotFoundError(
                f"source_file is not a regular file: {source_path}"
            )
    except SourceFileNotFoundError:
        raise
    except OSError as exc:
        raise OSError(
            f"Failed to inspect source_file {source_path}: {exc}"
        ) from exc

    # ------------------------------------------------------------------
    # 4. Hash the source BEFORE copying, so integrity can be checked after.
    # ------------------------------------------------------------------
    source_hash = _file_sha256(source_path)

    # ------------------------------------------------------------------
    # 5. Descriptor-relative copy (symlink-safe, race-free).
    # ------------------------------------------------------------------
    return _copy_material_fd_safe(
        project_path=project_path,
        source_path=source_path,
        source_name=source_name,
        source_hash=source_hash,
        material_type=material_type,
        batch_id=batch_id,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _default_config_path() -> Path:
    """Resolve the default config path lazily at call time.

    The resolution is deliberately NOT done at import time: (a) module
    import should not depend on filesystem state; (b) ``Path.resolve`` is a
    filesystem operation and must be wrapped in ``try/except OSError`` per
    the TASK-003 contract (ChatGPT review C-002, iteration 4).
    """
    try:
        module_path = Path(__file__).resolve()
    except OSError as exc:
        raise OSError(
            f"Failed to resolve module path for {__file__}: {exc}"
        ) from exc
    return module_path.parents[2].joinpath(*_CONFIG_RELATIVE_PATH)


def _get_config_path() -> Path:
    """Resolve the config path (env override wins over default)."""
    override = os.environ.get(_CONFIG_ENV_VAR)
    if override:
        return Path(override)
    return _default_config_path()


def _load_config() -> dict:
    """Load the material_upload YAML config."""
    config_path = _get_config_path()
    try:
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"material_upload config not found: {config_path}"
        ) from exc
    except OSError as exc:
        raise OSError(
            f"Failed to read material_upload config {config_path}: {exc}"
        ) from exc
    return data or {}


def _validate_material_type(material_type: str, config: dict) -> None:
    """Validate material_type against the config-supported set."""
    supported = config.get("supported_material_types") or []
    supported_set = {str(item).upper() for item in supported}
    if (
        not isinstance(material_type, str)
        or material_type.upper() not in supported_set
    ):
        raise UnsupportedMaterialTypeError(
            f"Unsupported material_type: {material_type!r}. "
            f"Supported: {sorted(supported_set)}"
        )


def _open_or_create_dir_at(name: str, parent_fd: int, field_name: str) -> int:
    """Open ``name`` as a directory relative to ``parent_fd``, creating it
    if it does not exist.

    Symlink-safe and race-safe by construction:
        - ``O_DIRECTORY`` rejects entries that are not directories;
        - ``O_NOFOLLOW`` rejects symlinks at this path component;
        - the returned fd is bound to the inode that existed at open time,
          so a later rename of the path (or replacement with a symlink)
          cannot redirect subsequent dir_fd-relative operations.

    Returns
    -------
    int
        Open file descriptor for the directory. Caller is responsible for
        closing it.

    Raises
    ------
    OSError
        If the component exists but is not a real directory, or if any
        other filesystem error occurs while opening or creating it.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        pass  # fall through to create it below
    except OSError as exc:
        raise OSError(
            f"Failed to open {field_name} ({name!r}): {exc}"
        ) from exc

    try:
        os.mkdir(name, dir_fd=parent_fd)
    except FileExistsError:
        # Raced with another creator; the open below re-validates.
        pass
    except OSError as exc:
        raise OSError(
            f"Failed to create {field_name} ({name!r}): {exc}"
        ) from exc

    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise OSError(
            f"Failed to open {field_name} ({name!r}) after create: {exc}"
        ) from exc


def _copy_material_fd_safe(
    *,
    project_path: Path,
    source_path: Path,
    source_name: str,
    source_hash: str,
    material_type: str,
    batch_id: str,
) -> MaterialRecord:
    """Descriptor-relative, symlink-safe, atomic copy.

    See module docstring for the security rationale. The root
    ``project_path`` is opened with ``O_NOFOLLOW`` so that a symlinked
    client project root is rejected at the very first step, before any
    dir_fd-relative traversal begins.
    """
    try:
        project_fd = os.open(
            str(project_path),
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
    except OSError as exc:
        raise OSError(
            f"Failed to open client project {project_path} "
            f"(O_NOFOLLOW rejects a symlinked root): {exc}"
        ) from exc

    materials_fd = -1
    batch_fd = -1
    target_fd = -1
    target_path = project_path / MATERIALS_SUBDIR / batch_id / source_name

    try:
        materials_fd = _open_or_create_dir_at(
            MATERIALS_SUBDIR, project_fd, MATERIALS_SUBDIR
        )
        batch_fd = _open_or_create_dir_at(
            batch_id,
            materials_fd,
            f"batch directory for batch_id={batch_id!r}",
        )

        # Atomic create with O_EXCL + O_NOFOLLOW, relative to batch_fd.
        # - O_EXCL: exactly one winner under contention (TOCTOU closed).
        # - O_NOFOLLOW: a pre-existing symlink with this name is rejected
        #   without ever being followed.
        try:
            target_fd = os.open(
                source_name,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o644,
                dir_fd=batch_fd,
            )
        except FileExistsError as exc:
            raise MaterialAlreadyExistsError(
                f"Material already registered in this batch: {target_path}"
            ) from exc
        except OSError as exc:
            raise OSError(
                f"Failed to create target file {target_path}: {exc}"
            ) from exc

        # Copy bytes straight into the open fd, then set metadata via fchmod
        # and utime on the fd - never by re-opening the path.
        try:
            _copy_bytes_into_fd(source_path, target_fd)
        except OSError as exc:
            _safe_close(target_fd)
            target_fd = -1
            _safe_unlink_at(batch_fd, source_name)
            raise OSError(
                f"Failed to copy {source_path} -> {target_path}: {exc}"
            ) from exc

        # Post-copy integrity check, read back through the same fd.
        try:
            os.lseek(target_fd, 0, os.SEEK_SET)
            target_hash = _fd_sha256(target_fd)
        except OSError as exc:
            _safe_close(target_fd)
            target_fd = -1
            _safe_unlink_at(batch_fd, source_name)
            raise OSError(
                f"Failed to hash target {target_path}: {exc}"
            ) from exc

        if source_hash != target_hash:
            _safe_close(target_fd)
            target_fd = -1
            _safe_unlink_at(batch_fd, source_name)
            raise OSError(
                f"Hash mismatch after copy: source={source_hash} "
                f"target={target_hash}"
            )
    finally:
        if target_fd != -1:
            _safe_close(target_fd)
        if batch_fd != -1:
            _safe_close(batch_fd)
        if materials_fd != -1:
            _safe_close(materials_fd)
        _safe_close(project_fd)

    return MaterialRecord(
        path=target_path,
        type=material_type,
        batch_id=batch_id,
        uploaded_at=datetime.now(timezone.utc),
    )


def _copy_bytes_into_fd(source_path: Path, target_fd: int) -> None:
    """Write ``source_path`` contents into the already-open ``target_fd``,
    then copy mode and timestamps via fd-relative calls.

    Uses :func:`_write_all` so that a short write from ``os.write`` cannot
    silently truncate the destination.
    """
    try:
        with source_path.open("rb") as src_fh:
            while True:
                chunk = src_fh.read(65536)
                if not chunk:
                    break
                _write_all(target_fd, chunk)

        st = source_path.stat()
        os.fchmod(target_fd, st.st_mode & 0o7777)
        os.utime(target_fd, (st.st_atime, st.st_mtime))
    except OSError as exc:
        raise OSError(
            f"Failed to write target from {source_path}: {exc}"
        ) from exc


def _write_all(fd: int, data: bytes) -> None:
    """Write the entire *data* buffer to *fd*, looping on short writes.

    ``os.write`` is permitted to write fewer bytes than requested. A return
    value of 0 is treated as an error to avoid an infinite loop.
    """
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(
                f"os.write returned {written}, expected > 0"
            )
        view = view[written:]


def _file_sha256(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file by path (used for the
    source, which is outside the protected tree)."""
    digest = hashlib.sha256()
    try:
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                digest.update(chunk)
    except OSError as exc:
        raise OSError(f"Failed to hash {path}: {exc}") from exc
    return digest.hexdigest()


def _fd_sha256(fd: int) -> str:
    """Compute the SHA-256 hex digest of the file referenced by ``fd``,
    starting from the current position.

    ``os.read`` is wrapped in ``try/except OSError`` with local context
    (ChatGPT review C-001, iteration 4).
    """
    digest = hashlib.sha256()
    try:
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            digest.update(chunk)
    except OSError as exc:
        raise OSError(
            f"Failed to read from file descriptor {fd} for hashing: {exc}"
        ) from exc
    return digest.hexdigest()


def _safe_close(fd: int) -> None:
    """Best-effort close; never raises."""
    try:
        os.close(fd)
    except OSError:
        pass


def _safe_unlink_at(parent_fd: int, name: str) -> None:
    """Best-effort unlink relative to ``parent_fd``; never raises."""
    try:
        os.unlink(name, dir_fd=parent_fd)
    except OSError:
        pass
