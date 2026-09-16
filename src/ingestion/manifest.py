'''Module for maintaining the human-readable materials manifest.

This module implements TASK-004: append_to_manifest().
It does not upload files, compute hashes, validate source formats,
generate batch_id, or analyse document contents.
'''

from __future__ import annotations

import re
from pathlib import Path

from .material_upload import MaterialRecord

MANIFEST_FILENAME = 'manifest.md'

_NL = chr(10)
_BACKSLASH = chr(92)
_PIPE = '|'

_TABLE_HEADER = (
    '| Путь | Тип | Batch ID | Краткое описание | Дата загрузки |' + _NL +
    '|---|---|---|---|---|' + _NL
)

_WHITESPACE_RE = re.compile(r'\s+')


def _escape_markdown_cell(value: object) -> str:
    '''Escape a value for safe inclusion in a Markdown table cell.

    Whitespace runs (spaces, tabs, newlines, carriage returns and other
    Unicode whitespace) are collapsed to a single space so the value
    cannot accidentally split a table row.  A backslash is duplicated
    and a pipe is prefixed with a backslash (standard Markdown table
    escape, kept as literal backslash-pipe so it survives any text or
    HTML viewer without being decoded).  The result round-trips through
    _parse_row_cells.
    '''
    if value is None:
        return ''
    text = _WHITESPACE_RE.sub(' ', str(value))
    text = text.replace(_BACKSLASH, _BACKSLASH + _BACKSLASH)
    text = text.replace(_PIPE, _BACKSLASH + _PIPE)
    return text.strip()


def _path_to_posix(value: object) -> str:
    '''Render a path-like value with forward slashes.

    Path.as_posix() is used when available.  For plain strings the
    backslash is replaced by the forward slash.  The TASK-003 AC
    specifies the storage layout as 05-client-materials/{batch_id}/{filename}
    with forward slashes, so the manifest reflects that regardless of
    the host OS.
    '''
    if value is None:
        return ''
    if hasattr(value, 'as_posix'):
        try:
            return value.as_posix()
        except (AttributeError, TypeError):
            pass
    return str(value).replace(_BACKSLASH, '/')


def _format_uploaded_at(record: MaterialRecord) -> str:
    '''Return a string representation of record.uploaded_at.'''
    value = getattr(record, 'uploaded_at', '')
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _derive_description(record: MaterialRecord) -> str:
    '''Return a brief description for the record.

    If the record exposes an optional description attribute (not part
    of the TASK-003 contract, but harmless to support), it is used as-is.
    Otherwise the original file name is extracted from record.path so
    the manifest always has a non-empty «Краткое описание» column, as
    required by REQ-03.
    '''
    explicit = getattr(record, 'description', None)
    if explicit:
        return str(explicit)
    posix = _path_to_posix(getattr(record, 'path', ''))
    if not posix:
        return ''
    return posix.rsplit('/', 1)[-1]


def _format_row(record: MaterialRecord, description: str = '') -> str:
    '''Format one MaterialRecord as a Markdown table row.'''
    return (
        f'| {_escape_markdown_cell(_path_to_posix(getattr(record, "path", "")))} '
        f'| {_escape_markdown_cell(getattr(record, "type", ""))} '
        f'| {_escape_markdown_cell(getattr(record, "batch_id", ""))} '
        f'| {_escape_markdown_cell(description)} '
        f'| {_escape_markdown_cell(_format_uploaded_at(record))} |' + _NL
    )


def _parse_row_cells(line: str) -> list[str]:
    '''Split a Markdown table row into raw (still-escaped) cell values.

    A backslash escapes the following character; an unescaped pipe is a
    column separator.  The returned cells keep their escape sequences so
    that _record_already_present can compare them directly against
    _escape_markdown_cell(record_value).
    '''
    stripped = line.strip()
    if not stripped.startswith(_PIPE):
        return []
    stripped = stripped[1:]
    if stripped.endswith(_PIPE):
        stripped = stripped[:-1]

    cells: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(stripped)
    while i < n:
        ch = stripped[i]
        if ch == _BACKSLASH and i + 1 < n:
            buf.append(stripped[i])
            buf.append(stripped[i + 1])
            i += 2
            continue
        if ch == _PIPE:
            cells.append(''.join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    cells.append(''.join(buf).strip())
    return cells


def _record_already_present(manifest_text: str, record: MaterialRecord) -> bool:
    '''Check whether a row for this (batch_id, path) already exists.

    The composite key (batch_id, path) is used deliberately.  The
    TASK-003 contract defines batch_id as a single upload event that
    may contain several distinct files, so idempotency must be evaluated
    per file inside the batch, not per batch alone.  Using only
    batch_id would wrongly drop the 2nd..N-th material of one batch;
    using only path would ignore the batch dimension altogether.
    '''
    target_path = _escape_markdown_cell(_path_to_posix(getattr(record, 'path', '')))
    target_batch = _escape_markdown_cell(getattr(record, 'batch_id', ''))
    for line in manifest_text.splitlines():
        cells = _parse_row_cells(line)
        if len(cells) >= 3 and cells[0] == target_path and cells[2] == target_batch:
            return True
    return False


def append_to_manifest(
    client_project_path: Path,
    record: MaterialRecord,
) -> None:
    '''Append a material record to manifest.md.

    Creates {client_project_path}/manifest.md with a Markdown table
    header if the file does not exist yet.  A record is considered
    already present when the manifest contains a row with the same
    (batch_id, path) pair — this allows several materials from the
    same upload batch to be appended sequentially without duplicates
    when the same record is passed again.

    The «Краткое описание» column is filled from the optional
    description attribute of the record if present, otherwise from
    the original file name extracted from record.path.

    The path column is normalized to forward slashes via Path.as_posix()
    (or an equivalent string replacement for non-Path values) so the
    stored path matches the format documented in TASK-003 AC:
    05-client-materials/{batch_id}/{filename}.

    Args:
        client_project_path: Path to the client project directory
            created by TASK-002.  The manifest is written to
            client_project_path / 'manifest.md'.
        record: Material record produced by TASK-003.

    Raises:
        OSError: If reading or writing the manifest fails.  The original
            exception is preserved as the cause.
    '''
    manifest_path = Path(client_project_path) / MANIFEST_FILENAME

    try:
        if manifest_path.exists():
            with manifest_path.open('r', encoding='utf-8') as handle:
                manifest_text = handle.read()
        else:
            manifest_text = ''

        if _record_already_present(manifest_text, record):
            return

        description = _derive_description(record)
        row = _format_row(record, description=description)

        if not manifest_text:
            mode = 'w'
            content = _TABLE_HEADER + row
        else:
            mode = 'a'
            content = row

        with manifest_path.open(mode, encoding='utf-8') as handle:
            handle.write(content)
    except OSError as exc:
        raise OSError(
            f'Failed to append material to manifest {manifest_path}: {exc}'
        ) from exc
