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

Security model (after ChatGPT review, iterations 1-5, Kimi test-run,
iteration 6, and fix in iteration 7):

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
            ``os.open(name, O_CREAT | O_EXCL | O_RDWR | O_NOFOLLOW,
            dir_fd=batch_fd)``. The descriptor is **O_RDWR, not O_WRONLY**,
            because the post-copy integrity check reads back through the
            same fd. A write-only fd would return ``EBADF`` on that read -
            this was the exact failure mode found by the Kimi test run on
            iteration 6.

    * **Atomic collision semantics.** ``O_EXCL`` guarantees exactly one
      writer succeeds for a given ``(batch_id, filename)`` pair; the loser
      receives ``MaterialAlreadyExistsError``.

    * **Full-buffer writes.** ``os.write`` may perform a short write; the
      module loops until the entire buffer has been written (see
      ``_write_all``).

    * **Post-copy integrity check.** After writing, the module seeks the
      target fd back to offset 0 and hashes it again through the same fd.
      Using the same fd (rather than re-opening the path) preserves the
      inode pin.

    * **Platform gate.** Descriptor-relative operations require ``dir_fd``,
      ``O_DIRECTORY``, and ``O_NOFOLLOW`` (POSIX). On platforms that lack
      them (notably Windows) there is no equivalent atomic mechanism in the
      Python standard library, so :func:`register_material` refuses to run
      with an explicit ``OSError``.

    * **Every filesystem call is inside ``try/except OSError``.** This
      includes ``os.open`` / ``os.mkdir`` / ``os.write`` / ``os.read`` /
      ``os.lseek`` / ``os.unlink`` / ``os.close`` / ``os.fchmod`` /
      ``os.utime``, ``Path.open`` / ``Path.stat`` / ``Path.exists`` /
      ``Path.is_file`` / ``Path.is_dir``, and ``Path.resolve``.

    * **Threat-model boundary.** A concurrent rename of the client project
      root *after* the root fd has been successfully opened is NOT in scope.
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
_CONFIG_RELATIVE_PATH = ("config", "material_upload.yaml")

_DEFAULT_BATCH_ID_STRATEGY = "uuid4"
_DEFAULT_TIMESTAMP_FORMAT = "%Y%m%d-%H%M%S-%f"

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
        (``05-client-materials/<batch_id>/<filename>``).
    type : str
        Material type tag exactly as supplied by the caller.
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
    by the caller - NOT inside :func:`register_material`.

    The strategy is read from ``config/material_upload.yaml`` (or from the
    file pointed to by the ``MATERIAL_UPLOAD_CONFIG`` environment variable).
    Supported strategies: ``'uuid4'`` (default) and ``'timestamp'``.

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

    Raises
    ------
    InvalidPathComponentError
        If ``batch_id`` or the source filename is unsafe as a path
        component.
    UnsupportedMaterialTypeError
        If ``material_type`` is not in the configured supported set.
    SourceFileNotFoundError
        If ``source_file`` does not exist or is not a regular file.
    FileNotFoundError
        If ``client_project_path`` does not exist.
    NotADirectoryError
        If ``client_project_path`` exists but is not a directory.
    MaterialAlreadyExistsError
        On a filename collision inside the target batch folder.
    OSError
        On any other filesystem error, on symlink traversal attempts,
        or on platforms without ``dir_fd`` support.
    """
    if not _HAS_DIR_FD_SUPPORT:
        raise OSError(
            "register_material requires POSIX descriptor-relative filesystem "
            "operations (os.open / os.mkdir with dir_fd, O_DIRECTORY, "
            "O_NOFOLLOW) to guarantee symlink-safe storage. This platform "
            "does not support them; refusing to fall back to a non-atomic "
            "path."
        )

    config = _load_config()

    validate_path_component(batch_id, "batch_id")
    source_path = Path(source_file)
    source_name = source_path.name
    validate_path_component(source_name, "source_file.name")
    _validate_material_type(material_type, config)

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

    source_hash = _file_sha256(source_path)

    return _copy_material_fd_safe(
        project_path=project_path,
        source_path=source_path,
        source_name=source_name,
        source_hash=source_hash,
        material_type=material_type,
        batch_id=batch_id,
    )


def _default_config_path() -> Path:
    """Resolve the default config path lazily at call time."""
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

    Symlink-safe and race-safe: ``O_DIRECTORY`` rejects non-directories,
    ``O_NOFOLLOW`` rejects symlinks, and the returned fd is bound to the
    inode that existed at open time.
    """
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW

    try:
        return os.open(name, flags, dir_fd=parent_fd)
    except FileNotFoundError:
        pass
    except OSError as exc:
        raise OSError(
            f"Failed to open {field_name} ({name!r}): {exc}"
        ) from exc

    try:
        os.mkdir(name, dir_fd=parent_fd)
    except FileExistsError:
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

    The target fd is opened **O_RDWR** (not O_WRONLY) because the
    post-copy hash check reads the same fd. O_WRONLY would return EBADF
    on that read - this was the exact bug found by the Kimi test run.
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

        try:
            target_fd = os.open(
                source_name,
                os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_NOFOLLOW,
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

        try:
            _copy_bytes_into_fd(source_path, target_fd)
        except OSError as exc:
            _safe_close(target_fd)
            target_fd = -1
            _safe_unlink_at(batch_fd, source_name)
            raise OSError(
                f"Failed to copy {source_path} -> {target_path}: {exc}"
            ) from exc

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
    then copy mode and timestamps via fd-relative calls."""
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
    """Write the entire *data* buffer to *fd*, looping on short writes."""
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(
                f"os.write returned {written}, expected > 0"
            )
        view = view[written:]


def _file_sha256(path: Path) -> str:
    """Compute the SHA-256 hex digest of a file by path."""
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

    NOTE: this function requires the fd to be readable. The target fd is
    opened O_RDWR (see _copy_material_fd_safe) precisely so this works.
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
