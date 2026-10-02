from __future__ import annotations

import dataclasses
import datetime as dt
from pathlib import Path

import pytest

from src.ingestion.manifest import append_to_manifest, MANIFEST_FILENAME
from src.ingestion.material_upload import MaterialRecord

BS = chr(92)
NL = chr(10)


def _make_record(
    path: str = '05-client-materials/batch-1/file.txt',
    type_: str = 'TXT',
    batch_id: str = 'batch-1',
    uploaded_at: dt.datetime | None = None,
) -> MaterialRecord:
    if uploaded_at is None:
        uploaded_at = dt.datetime(2026, 9, 8, 12, 0, 0)
    return MaterialRecord(
        path=Path(path),
        type=type_,
        batch_id=batch_id,
        uploaded_at=uploaded_at,
    )


def _data_rows(text: str) -> list[str]:
    return [
        line for line in text.splitlines()
        if line.startswith('|') and not line.startswith('|---')
    ]


def test_manifest_created_if_missing(tmp_path: Path) -> None:
    record = _make_record()
    append_to_manifest(tmp_path, record)
    manifest = tmp_path / MANIFEST_FILENAME
    assert manifest.exists()


def test_header_is_correct(tmp_path: Path) -> None:
    record = _make_record()
    append_to_manifest(tmp_path, record)
    text = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8')
    assert '| Путь | Тип | Batch ID | Краткое описание | Дата загрузки |' in text
    assert '|---|---|---|---|---|' in text


def test_one_record_added(tmp_path: Path) -> None:
    record = _make_record(path='05-client-materials/batch-1/a.txt', batch_id='batch-1')
    append_to_manifest(tmp_path, record)
    text = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8')
    assert 'a.txt' in text
    assert 'TXT' in text
    assert 'batch-1' in text


def test_record_fields_present(tmp_path: Path) -> None:
    record = _make_record(
        path='05-client-materials/batch-2/file.docx',
        type_='DOCX',
        batch_id='batch-2',
        uploaded_at=dt.datetime(2026, 9, 8, 13, 45, 0),
    )
    append_to_manifest(tmp_path, record)
    text = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8')
    # Path must be stored with forward slashes (see TASK-003 AC and
    # _path_to_posix).  On Windows Path() would otherwise emit backslashes.
    assert '05-client-materials/batch-2/file.docx' in text
    assert 'DOCX' in text
    assert 'batch-2' in text
    assert 'file.docx' in text
    assert '2026-09-08T13:45:00' in text


def test_description_column_is_not_empty(tmp_path: Path) -> None:
    record = _make_record(
        path='05-client-materials/batch-d/report_final.xlsx',
        type_='XLSX',
        batch_id='batch-d',
    )
    append_to_manifest(tmp_path, record)
    text = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8')
    data_lines = _data_rows(text)
    assert len(data_lines) == 2
    header_cells = [c.strip() for c in data_lines[0].strip('|').split('|')]
    row_cells = [c.strip() for c in data_lines[1].strip('|').split('|')]
    description_index = header_cells.index('Краткое описание')
    assert row_cells[description_index] != ''
    assert row_cells[description_index] == 'report_final.xlsx'


def test_path_normalized_to_forward_slashes(tmp_path: Path) -> None:
    # Build a Path object the same way TASK-003 would; on Windows the
    # resulting str() contains backslashes.  The manifest must still
    # contain forward slashes.
    record = MaterialRecord(
        path=Path('05-client-materials') / 'batch-w' / 'file.txt',
        type='TXT',
        batch_id='batch-w',
        uploaded_at=dt.datetime(2026, 9, 8, 12, 0, 0),
    )
    append_to_manifest(tmp_path, record)
    text = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8')
    assert '05-client-materials/batch-w/file.txt' in text
    # The path cell must not contain backslashes at all.
    data_lines = _data_rows(text)
    assert len(data_lines) == 2
    path_cell = data_lines[1].strip('|').split('|')[0].strip()
    assert BS not in path_cell


def test_special_characters_escaped(tmp_path: Path) -> None:
    record = _make_record(
        path='05-client-materials/batch-z/we|ird.txt',
        type_='TXT',
        batch_id='batch-z',
    )
    append_to_manifest(tmp_path, record)
    text1 = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8')
    escaped = 'we' + BS + '|ird.txt'
    assert escaped in text1
    data_lines = _data_rows(text1)
    assert len(data_lines) == 2
    append_to_manifest(tmp_path, record)
    text2 = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8')
    assert text2 == text1


def test_newline_in_path_does_not_break_table(tmp_path: Path) -> None:
    base = _make_record(
        path='placeholder.txt',
        type_='TXT',
        batch_id='batch-n',
    )
    # MaterialRecord is a frozen dataclass: build a new instance rather
    # than mutating .path in place.
    record = dataclasses.replace(
        base,
        path='05-client-materials/batch-n/line1' + NL + 'line2.txt',
    )
    append_to_manifest(tmp_path, record)
    text = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8')
    data_lines = _data_rows(text)
    assert len(data_lines) == 2
    for line in data_lines:
        assert line.count('|') == 6


def test_multiple_materials_same_batch(tmp_path: Path) -> None:
    r1 = _make_record(path='05-client-materials/batch-x/a.txt', batch_id='batch-x')
    r2 = _make_record(path='05-client-materials/batch-x/b.txt', batch_id='batch-x')
    append_to_manifest(tmp_path, r1)
    append_to_manifest(tmp_path, r2)
    text = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8')
    data_lines = _data_rows(text)
    assert len(data_lines) == 3
    assert 'a.txt' in text
    assert 'b.txt' in text


def test_duplicate_record_not_added(tmp_path: Path) -> None:
    record = _make_record()
    append_to_manifest(tmp_path, record)
    append_to_manifest(tmp_path, record)
    text = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8')
    data_lines = _data_rows(text)
    assert len(data_lines) == 2


def test_idempotency_by_batch_and_path(tmp_path: Path) -> None:
    r1 = _make_record(path='05-client-materials/batch-y/a.txt', batch_id='batch-y')
    r2 = _make_record(path='05-client-materials/batch-y/b.txt', batch_id='batch-y')
    append_to_manifest(tmp_path, r1)
    append_to_manifest(tmp_path, r2)
    append_to_manifest(tmp_path, r1)
    text = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8')
    data_lines = _data_rows(text)
    assert len(data_lines) == 3


def test_file_error_not_swallowed(tmp_path: Path) -> None:
    manifest = tmp_path / MANIFEST_FILENAME
    manifest.mkdir()
    record = _make_record()
    with pytest.raises(OSError):
        append_to_manifest(tmp_path, record)


def test_existing_manifest_not_destroyed(tmp_path: Path) -> None:
    manifest = tmp_path / MANIFEST_FILENAME
    manifest.write_text(
        '| Путь | Тип | Batch ID | Краткое описание | Дата загрузки |' + NL +
        '|---|---|---|---|---|' + NL +
        '| old.txt | TXT | old-batch | old | 2026-01-01T00:00:00 |' + NL,
        encoding='utf-8',
    )
    record = _make_record(path='new.txt', batch_id='new-batch')
    append_to_manifest(tmp_path, record)
    text = manifest.read_text(encoding='utf-8')
    assert 'old.txt' in text
    assert 'new.txt' in text
    data_lines = _data_rows(text)
    assert len(data_lines) == 3


def test_valid_markdown_table(tmp_path: Path) -> None:
    r1 = _make_record(path='a.txt', batch_id='b1')
    r2 = _make_record(path='b.txt', batch_id='b2')
    append_to_manifest(tmp_path, r1)
    append_to_manifest(tmp_path, r2)
    lines = (tmp_path / MANIFEST_FILENAME).read_text(encoding='utf-8').splitlines()
    assert len(lines) == 4
    for line in lines:
        assert line.startswith('|')
        assert line.endswith('|')
        assert line.count('|') == 6
