"""Unit tests for src/ingestion/material_upload.py (TASK-003 / REQ-01)."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading
import uuid
from pathlib import Path

import pytest

import src.ingestion.material_upload as mu
from src.ingestion.material_upload import (
    _HAS_DIR_FD_SUPPORT,
    MaterialAlreadyExistsError,
    MaterialRecord,
    SourceFileNotFoundError,
    UnsupportedMaterialTypeError,
    generate_batch_id,
    register_material,
)
from src.ingestion.validation import InvalidPathComponentError

pytestmark = pytest.mark.skipif(
    not _HAS_DIR_FD_SUPPORT,
    reason="register_material requires POSIX dir_fd / O_DIRECTORY / O_NOFOLLOW.",
)


@pytest.fixture
def material_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / "material_upload.yaml"
    cfg.write_text(
        "batch_id:\n"
        "  strategy: uuid4\n"
        "  timestamp_format: '%Y%m%d-%H%M%S-%f'\n"
        "supported_material_types:\n"
        "  - DOC\n"
        "  - DOCX\n"
        "  - TXT\n"
        "  - MD\n"
        "  - XLS\n"
        "  - XLSX\n"
        "  - AUDIO\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MATERIAL_UPLOAD_CONFIG", str(cfg))
    return cfg


@pytest.fixture
def client_project(tmp_path: Path) -> Path:
    project = tmp_path / "client-1"
    for sub in (
        "01-transcripts",
        "02-product",
        "03-analysis",
        "04-deliverables",
        "05-client-materials",
    ):
        (project / sub).mkdir(parents=True, exist_ok=True)
    return project


@pytest.fixture
def sample_file(tmp_path: Path) -> Path:
    f = tmp_path / "sample.txt"
    f.write_text("hello world", encoding="utf-8")
    return f


def test_generate_batch_id_uuid4_unique(material_config: Path) -> None:
    ids = {generate_batch_id() for _ in range(50)}
    assert len(ids) == 50
    for bid in ids:
        uuid.UUID(bid)


def test_generate_batch_id_timestamp_strategy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "batch_id:\n"
        "  strategy: timestamp\n"
        "  timestamp_format: '%Y%m%d-%H%M%S'\n"
        "supported_material_types:\n  - TXT\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MATERIAL_UPLOAD_CONFIG", str(cfg))
    bid = generate_batch_id()
    assert re.fullmatch(r"\d{8}-\d{6}", bid)


def test_generate_batch_id_timestamp_microsecond_precision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "batch_id:\n"
        "  strategy: timestamp\n"
        "  timestamp_format: '%Y%m%d-%H%M%S-%f'\n"
        "supported_material_types:\n  - TXT\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MATERIAL_UPLOAD_CONFIG", str(cfg))
    ids = [generate_batch_id() for _ in range(20)]
    assert len(set(ids)) == 20
    assert all(re.fullmatch(r"\d{8}-\d{6}-\d{6}", bid) for bid in ids)


def test_generate_batch_id_unknown_strategy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "batch_id:\n  strategy: totally-bogus\n"
        "supported_material_types:\n  - TXT\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MATERIAL_UPLOAD_CONFIG", str(cfg))
    with pytest.raises(ValueError):
        generate_batch_id()


def test_generate_batch_id_missing_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "MATERIAL_UPLOAD_CONFIG", str(tmp_path / "nope.yaml")
    )
    with pytest.raises(FileNotFoundError):
        generate_batch_id()


def test_register_happy_path(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    record = register_material(client_project, sample_file, "TXT", "batch-001")
    assert isinstance(record, MaterialRecord)
    assert record.type == "TXT"
    assert record.batch_id == "batch-001"
    assert record.path == (
        client_project / "05-client-materials" / "batch-001" / "sample.txt"
    )
    assert record.path.is_file()
    assert record.path.read_text(encoding="utf-8") == "hello world"
    assert record.uploaded_at.tzinfo is not None


def test_register_does_not_move_source(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    register_material(client_project, sample_file, "TXT", "b1")
    assert sample_file.exists()
    assert sample_file.read_text(encoding="utf-8") == "hello world"


def test_register_creates_batch_subdir(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    register_material(client_project, sample_file, "TXT", "b1")
    assert (client_project / "05-client-materials" / "b1").is_dir()


def test_register_preserves_hash(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    record = register_material(client_project, sample_file, "TXT", "b1")
    src_hash = hashlib.sha256(sample_file.read_bytes()).hexdigest()
    dst_hash = hashlib.sha256(record.path.read_bytes()).hexdigest()
    assert src_hash == dst_hash


def test_register_preserves_byte_content(
    material_config: Path, client_project: Path, tmp_path: Path
) -> None:
    payload = bytes(range(0, 256)) * 4
    src = tmp_path / "binary.doc"
    src.write_bytes(payload)
    record = register_material(client_project, src, "DOC", "b1")
    assert record.path.read_bytes() == payload


def test_register_case_insensitive_type(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    record = register_material(client_project, sample_file, "txt", "b1")
    assert record.type == "txt"


def test_register_empty_file(
    material_config: Path, client_project: Path, tmp_path: Path
) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_bytes(b"")
    record = register_material(client_project, empty, "TXT", "b1")
    assert record.path.read_bytes() == b""


def test_register_multiple_files_same_batch(
    material_config: Path, client_project: Path, tmp_path: Path
) -> None:
    bid = "shared-batch"
    for i in range(3):
        f = tmp_path / f"file{i}.txt"
        f.write_text(f"content-{i}", encoding="utf-8")
        register_material(client_project, f, "TXT", bid)
    batch_dir = client_project / "05-client-materials" / bid
    assert sorted(p.name for p in batch_dir.iterdir()) == [
        "file0.txt",
        "file1.txt",
        "file2.txt",
    ]


def test_register_unsupported_type(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    with pytest.raises(UnsupportedMaterialTypeError):
        register_material(client_project, sample_file, "EXE", "b1")
    batch_dir = client_project / "05-client-materials" / "b1"
    assert not batch_dir.exists()


def test_register_invalid_batch_id_with_slash(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    with pytest.raises(InvalidPathComponentError):
        register_material(client_project, sample_file, "TXT", "bad/batch")


def test_register_invalid_batch_id_dotdot(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    with pytest.raises(InvalidPathComponentError):
        register_material(client_project, sample_file, "TXT", "..")


def test_register_invalid_batch_id_with_dotdot_substring(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    with pytest.raises(InvalidPathComponentError):
        register_material(client_project, sample_file, "TXT", "batch..001")


def test_register_invalid_batch_id_empty(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    with pytest.raises(InvalidPathComponentError):
        register_material(client_project, sample_file, "TXT", "")


def test_register_invalid_batch_id_whitespace(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    with pytest.raises(InvalidPathComponentError):
        register_material(client_project, sample_file, "TXT", "   ")


def test_register_invalid_batch_id_with_backslash(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    with pytest.raises(InvalidPathComponentError):
        register_material(client_project, sample_file, "TXT", "bad\\batch")


@pytest.mark.skipif(
    os.name != "posix",
    reason="Backslash is a path separator on Windows; test requires POSIX.",
)
def test_register_invalid_filename_with_backslash(
    material_config: Path, client_project: Path, tmp_path: Path
) -> None:
    bad = tmp_path / "evil\\name.txt"
    bad.write_text("data", encoding="utf-8")
    with pytest.raises(InvalidPathComponentError):
        register_material(client_project, bad, "TXT", "b1")


def test_register_invalid_filename_with_dotdot_substring(
    material_config: Path, client_project: Path, tmp_path: Path
) -> None:
    bad = tmp_path / "foo..bar.txt"
    bad.write_text("data", encoding="utf-8")
    with pytest.raises(InvalidPathComponentError):
        register_material(client_project, bad, "TXT", "b1")
    batch_dir = client_project / "05-client-materials" / "b1"
    assert not batch_dir.exists()


def test_register_invalid_empty_basename(
    material_config: Path, client_project: Path
) -> None:
    with pytest.raises(InvalidPathComponentError):
        register_material(client_project, Path("."), "TXT", "b1")


def test_register_invalid_dotdot_basename(
    material_config: Path, client_project: Path
) -> None:
    with pytest.raises(InvalidPathComponentError):
        register_material(client_project, Path(".."), "TXT", "b1")


def test_register_invalid_whitespace_basename(
    material_config: Path, client_project: Path, tmp_path: Path
) -> None:
    bad = tmp_path / "   "
    try:
        bad.write_text("x", encoding="utf-8")
    except OSError:
        pytest.skip("Filesystem refuses whitespace-only filename")
    with pytest.raises(InvalidPathComponentError):
        register_material(client_project, bad, "TXT", "b1")


def test_register_source_not_found(
    material_config: Path, client_project: Path, tmp_path: Path
) -> None:
    missing = tmp_path / "does-not-exist.txt"
    with pytest.raises(SourceFileNotFoundError):
        register_material(client_project, missing, "TXT", "b1")


def test_register_source_is_directory(
    material_config: Path, client_project: Path, tmp_path: Path
) -> None:
    d = tmp_path / "a-directory.txt"
    d.mkdir()
    with pytest.raises(SourceFileNotFoundError):
        register_material(client_project, d, "TXT", "b1")


def test_register_client_project_missing(
    material_config: Path, sample_file: Path, tmp_path: Path
) -> None:
    missing = tmp_path / "no-such-client"
    with pytest.raises(FileNotFoundError):
        register_material(missing, sample_file, "TXT", "b1")


def test_register_client_project_is_file(
    material_config: Path, sample_file: Path, tmp_path: Path
) -> None:
    f = tmp_path / "not-a-dir"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(NotADirectoryError):
        register_material(f, sample_file, "TXT", "b1")


def test_register_collision_within_same_batch(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    register_material(client_project, sample_file, "TXT", "b1")
    with pytest.raises(MaterialAlreadyExistsError):
        register_material(client_project, sample_file, "TXT", "b1")


def test_register_no_collision_across_batches(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    r1 = register_material(client_project, sample_file, "TXT", "b1")
    r2 = register_material(client_project, sample_file, "TXT", "b2")
    assert r1.path != r2.path
    assert r1.path.read_bytes() == r2.path.read_bytes()
    assert (client_project / "05-client-materials" / "b1").is_dir()
    assert (client_project / "05-client-materials" / "b2").is_dir()


def test_register_atomic_under_contention(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    results: list[str] = []
    barrier = threading.Barrier(2)

    def attempt() -> None:
        barrier.wait()
        try:
            register_material(client_project, sample_file, "TXT", "b1")
            results.append("ok")
        except MaterialAlreadyExistsError:
            results.append("dup")

    t1 = threading.Thread(target=attempt)
    t2 = threading.Thread(target=attempt)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert sorted(results) == ["dup", "ok"]


def test_register_handles_partial_writes(
    material_config: Path,
    client_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_write = mu.os.write

    def tiny_write(fd: int, data) -> int:
        return real_write(fd, bytes(data[:1]))

    monkeypatch.setattr(mu.os, "write", tiny_write)

    payload = b"ABCDEFGHIJ" * 100
    src = tmp_path / "partial.txt"
    src.write_bytes(payload)

    record = register_material(client_project, src, "TXT", "b1")
    assert record.path.read_bytes() == payload


def test_register_read_error_during_hash_rolls_back(
    material_config: Path,
    client_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "hash-fail.txt"
    src.write_text("content that will be hashed", encoding="utf-8")

    def failing_read(fd: int, n: int) -> bytes:
        raise OSError("simulated read failure")

    monkeypatch.setattr(mu.os, "read", failing_read)

    with pytest.raises(OSError, match="Failed to hash target"):
        register_material(client_project, src, "TXT", "b1")

    batch_dir = client_project / "05-client-materials" / "b1"
    assert batch_dir.is_dir()
    assert list(batch_dir.iterdir()) == []


def test_register_hash_mismatch_removes_target(
    material_config: Path,
    client_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "hash-mismatch.txt"
    src.write_text("some content", encoding="utf-8")

    def fake_fd_sha256(fd: int) -> str:
        try:
            while os.read(fd, 65536):
                pass
        except OSError:
            pass
        return "0" * 64

    monkeypatch.setattr(mu, "_fd_sha256", fake_fd_sha256)

    with pytest.raises(OSError, match="Hash mismatch"):
        register_material(client_project, src, "TXT", "b1")

    batch_dir = client_project / "05-client-materials" / "b1"
    assert batch_dir.is_dir()
    assert list(batch_dir.iterdir()) == []


def test_register_write_returns_zero_raises(
    material_config: Path,
    client_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "zero-write.txt"
    src.write_text("payload that will not be written", encoding="utf-8")

    def zero_write(fd: int, data) -> int:
        return 0

    monkeypatch.setattr(mu.os, "write", zero_write)

    with pytest.raises(OSError):
        register_material(client_project, src, "TXT", "b1")

    batch_dir = client_project / "05-client-materials" / "b1"
    assert batch_dir.is_dir()
    assert list(batch_dir.iterdir()) == []


def test_register_write_error_during_copy_rolls_back(
    material_config: Path,
    client_project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    src = tmp_path / "copy-fail.txt"
    src.write_text("data", encoding="utf-8")

    def failing_copy(source_path: Path, target_fd: int) -> None:
        raise OSError("simulated copy failure")

    monkeypatch.setattr(mu, "_copy_bytes_into_fd", failing_copy)

    with pytest.raises(OSError, match="Failed to copy"):
        register_material(client_project, src, "TXT", "b1")

    batch_dir = client_project / "05-client-materials" / "b1"
    assert batch_dir.is_dir()
    assert list(batch_dir.iterdir()) == []


def test_register_rejects_symlinked_materials_dir(
    material_config: Path, client_project: Path, sample_file: Path, tmp_path: Path
) -> None:
    materials_dir = client_project / "05-client-materials"
    shutil.rmtree(materials_dir)
    outside = tmp_path / "outside"
    outside.mkdir()
    materials_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        register_material(client_project, sample_file, "TXT", "b1")
    assert list(outside.iterdir()) == []


def test_register_rejects_symlinked_batch_dir(
    material_config: Path, client_project: Path, sample_file: Path, tmp_path: Path
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    batch_dir = client_project / "05-client-materials" / "b1"
    batch_dir.symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        register_material(client_project, sample_file, "TXT", "b1")
    assert list(outside.iterdir()) == []


def test_register_target_symlink_is_rejected(
    material_config: Path, client_project: Path, sample_file: Path, tmp_path: Path
) -> None:
    batch_dir = client_project / "05-client-materials" / "b1"
    batch_dir.mkdir(parents=True)
    outside_target = tmp_path / "outside.txt"
    outside_target.write_text("malicious", encoding="utf-8")
    (batch_dir / "sample.txt").symlink_to(outside_target)

    with pytest.raises(MaterialAlreadyExistsError):
        register_material(client_project, sample_file, "TXT", "b1")
    assert outside_target.read_text(encoding="utf-8") == "malicious"


def test_register_rejects_symlinked_materials_dir_even_inside_project(
    material_config: Path, client_project: Path, sample_file: Path
) -> None:
    materials_dir = client_project / "05-client-materials"
    shutil.rmtree(materials_dir)
    inside = client_project / "01-transcripts"
    materials_dir.symlink_to(inside, target_is_directory=True)

    with pytest.raises(OSError):
        register_material(client_project, sample_file, "TXT", "b1")
    assert list(inside.iterdir()) == []


def test_register_rejects_symlinked_project_root(
    material_config: Path, sample_file: Path, tmp_path: Path
) -> None:
    real_project = tmp_path / "real-project"
    for sub in (
        "01-transcripts",
        "02-product",
        "03-analysis",
        "04-deliverables",
        "05-client-materials",
    ):
        (real_project / sub).mkdir(parents=True, exist_ok=True)

    link_project = tmp_path / "link-project"
    link_project.symlink_to(real_project, target_is_directory=True)

    with pytest.raises(OSError):
        register_material(link_project, sample_file, "TXT", "b1")

    materials_dir = real_project / "05-client-materials"
    assert list(materials_dir.iterdir()) == []


def test_register_missing_config(
    client_project: Path,
    sample_file: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "MATERIAL_UPLOAD_CONFIG", str(tmp_path / "nope.yaml")
    )
    with pytest.raises(FileNotFoundError):
        register_material(client_project, sample_file, "TXT", "b1")
