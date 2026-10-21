"""Minimal read-only PE, map and managed-metadata inspection."""

import csv
import io
from pathlib import Path
import struct
import uuid

from .common import ObservationError, need


def _data(path):
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise ObservationError('pe-read ' + str(path) + ': ' + str(error))
    need(len(data) >= 0x40, 'pe-too-small ' + str(path))
    return data


def _unpack(fmt, data, offset, label):
    try:
        return struct.unpack_from(fmt, data, offset)
    except (struct.error, IndexError):
        raise ObservationError('pe-truncated ' + label)


def u16(data, offset, label='u16'):
    return _unpack('<H', data, offset, label)[0]


def u32(data, offset, label='u32'):
    return _unpack('<I', data, offset, label)[0]


def pe_info(path):
    data = _data(path)
    pe = u32(data, 0x3c, 'e_lfanew')
    need(pe + 24 <= len(data), 'pe-header-too-small ' + str(path))
    need(data[pe:pe + 4] == b'PE\0\0', 'pe-signature ' + str(path))
    machine = u16(data, pe + 4, 'machine')
    count = u16(data, pe + 6, 'section-count')
    optional = u16(data, pe + 20, 'optional-size')
    start = pe + 24
    need(start + optional <= len(data), 'pe-optional-truncated ' + str(path))
    magic = u16(data, start, 'optional-magic')
    need(magic in (0x10b, 0x20b), 'pe-optional-magic ' + hex(magic))
    data_dirs = start + (112 if magic == 0x20b else 96)
    directories = [(u32(data, data_dirs + index * 8, 'directory-rva'),
                    u32(data, data_dirs + index * 8 + 4, 'directory-size'))
                   for index in range(16)]
    sections = []
    section_start = start + optional
    need(section_start + count * 40 <= len(data), 'pe-sections-truncated ' + str(path))
    for index in range(count):
        at = section_start + index * 40
        name = data[at:at + 8].rstrip(b'\0').decode('ascii', errors='replace')
        virtual_size, va, raw_size, raw_ptr = _unpack('<IIII', data, at + 8, 'section')
        flags = u32(data, at + 36, 'section-flags')
        sections.append({'name': name, 'va': va, 'vsize': virtual_size,
                         'rawsize': raw_size, 'rawptr': raw_ptr, 'flags': flags,
                         'size': max(virtual_size, raw_size)})
    return data, machine, directories, sections


def rva_to_offset(rva, sections):
    for section in sections:
        if section['va'] <= rva < section['va'] + section['size']:
            return section['rawptr'] + rva - section['va']
    raise ObservationError('rva-not-mapped ' + hex(rva))


def mvid(path):
    data, machine, directories, sections = pe_info(path)
    cli_rva, cli_size = directories[14]
    need(cli_rva != 0 and cli_size >= 16, 'cli-directory ' + str(path))
    cli = rva_to_offset(cli_rva, sections)
    metadata_rva = u32(data, cli + 8, 'metadata-rva')
    metadata = rva_to_offset(metadata_rva, sections)
    need(u32(data, metadata, 'metadata-signature') == 0x424A5342,
         'metadata-signature ' + str(path))
    version = u32(data, metadata + 12, 'metadata-version')
    at = metadata + 16 + version
    at += 2
    streams = u16(data, at, 'metadata-stream-count')
    at += 2
    heaps = {}
    for _ in range(streams):
        offset = u32(data, at, 'stream-offset')
        size = u32(data, at + 4, 'stream-size')
        at += 8
        try:
            end = data.index(b'\0', at)
        except ValueError:
            raise ObservationError('metadata-stream-name ' + str(path))
        name = data[at:end].decode('ascii', errors='replace')
        at = (end + 1 + 3) & ~3
        heaps[name] = (metadata + offset, size)
    need('#~' in heaps and '#GUID' in heaps, 'metadata-heaps ' + str(path))
    table, table_size = heaps['#~']
    need(table + 24 <= len(data), 'metadata-table ' + str(path))
    heap_flags = data[table + 6]
    valid = _unpack('<Q', data, table + 8, 'metadata-valid')[0]
    at = table + 24
    rows = {}
    for index in range(64):
        if valid >> index & 1:
            rows[index] = u32(data, at, 'metadata-rows')
            at += 4
    need(0 in rows and rows[0] >= 1, 'module-row ' + str(path))
    string_size = 4 if heap_flags & 1 else 2
    guid_size = 4 if heap_flags & 2 else 2
    at += 2
    at += string_size
    idx = u16(data, at, 'mvid-index') if guid_size == 2 else u32(data, at, 'mvid-index')
    need(idx > 0, 'mvid-index-zero ' + str(path))
    guid, guid_size_bytes = heaps['#GUID']
    guid_at = guid + (idx - 1) * 16
    need(guid_at + 16 <= len(data), 'guid-heap ' + str(path))
    raw = data[guid_at:guid_at + 16]
    return str(uuid.UUID(bytes_le=raw))


def pdata(path):
    """Read PE directory 3 as RUNTIME_FUNCTION records.

    Directory 3 is the PE exception directory. Managed R2R images may place
    that directory in .text rather than in a section literally named .pdata;
    this helper name is retained from the reviewed source.
    """
    data, machine, directories, sections = pe_info(path)
    rva, size = directories[3]
    if rva == 0:
        need(size == 0, 'pdata-size-without-rva ' + str(path))
        return []
    # R2R images retain a trailing 4-byte terminator after the 12-byte
    # RUNTIME_FUNCTION records; parse the complete records and ignore it.
    need(size % 12 in (0, 4), 'pdata-size ' + str(size))
    offset = rva_to_offset(rva, sections)
    need(offset + size <= len(data), 'pdata-truncated ' + str(path))
    result = []
    for index in range(size // 12):
        begin, end, unwind = _unpack('<III', data, offset + index * 12, 'runtime-function')
        result.append({'begin': begin, 'end': end, 'unwind': unwind})
    return result


def executable_sections(path):
    data, machine, directories, sections = pe_info(path)
    return [{'name': section['name'], 'va': section['va'], 'size': section['size'],
             'flags': section['flags']}
            for section in sections if section['flags'] & 0x20000000]


def map_method(path, symbol):
    try:
        text = Path(path).read_text(encoding='utf-8-sig')
    except OSError as error:
        raise ObservationError('map-read ' + str(path) + ': ' + str(error))
    rows = list(csv.reader(io.StringIO(text)))
    hits = [row for row in rows[1:] if len(row) >= 6 and row[4] == symbol]
    need(len(hits) == 1, 'map-symbol-count ' + str(len(hits)) + ' ' + symbol)
    row = hits[0]
    try:
        rva = int(row[0], 16)
    except ValueError:
        raise ObservationError('map-rva ' + repr(row[0]))
    length = int(row[1]) if row[1] else None
    return {'rva': rva, 'length': length, 'symbol': symbol, 'section': row[3]}
