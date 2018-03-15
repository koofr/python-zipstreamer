# -*- coding: utf-8 -*-

"""
zipstreamer
~~~~~~~~~~~~~~~
ZipStreamer is a Python library for generating ZIP files on-the-fly with ZIP
file size information.
"""

# pylint: disable=missing-docstring,too-many-locals,too-many-branches
# pylint: disable=too-many-statements

from __future__ import unicode_literals

from binascii import crc32
import datetime
from collections import namedtuple
import struct
import time
import calendar

from .compat import str  # pylint: disable=redefined-builtin

__all__ = [
    'ZipStream',
    'ZipFile',
    'ZipStreamError',
    'FileNameTooLong',
    'ZipFileSizeRequired',
    'ZipFileInProgress',
]

ZIP_MODE_STORED = 0

STRUCT_FILE_HEADER = '<4s2B4HL2L2H'
STRING_FILE_HEADER = b'PK\x03\x04'

STRUCT_DATA_DESCRIPTOR = '<4sLLL'
STRUCT_DATA_DESCRIPTOR64 = '<4sLQQ'
# de-facto standard, required by OS X Finder
STRING_DATA_DESCRIPTOR = b'PK\x07\x08'

STRUCT_CENTRAL_DIR = '<4s4B4HL2L5H2L'
STRING_CENTRAL_DIR = b'PK\x01\x02'

STRUCT_ZIP64_EXTRA = '<2H3Q'
ZIP64_EXTRA_ID = 0x0001  # Zip64 extended information
ZIP64_EXTRA_SIZE = 24  # 3x uint64

STRUCT_EXT_TIME_EXTRA = '<2HBL'
EXT_TIME_EXTRA_ID = 0x5455  # Extended timestamp
EXT_TIME_EXTRA_SIZE = 5  # uint8 + uint32
EXT_TIME_EXTRA_FLAGS = 1  # ModTime

STRUCT_END_ARCHIVE = '<4s4H2LH'
STRING_END_ARCHIVE = b'PK\x05\x06'

STRUCT_END_ARCHIVE64_LOCATOR = '<4sLQL'
STRING_END_ARCHIVE64_LOCATOR = b'PK\x06\x07'

STRUCT_END_ARCHIVE64 = '<4sQ2H2L4Q'
STRING_END_ARCHIVE64 = b'PK\x06\x06'

UINT16_MAX = (1 << 16) - 1
UINT32_MAX = (1 << 32) - 1

ZIP_VERSION_20 = 20  # 2.0
ZIP_VERSION_45 = 45  # 4.5 (reads and writes zip64 archives)


class ZipStreamError(Exception):
    pass


class FileNameTooLong(ZipStreamError):
    pass


class ZipFileSizeRequired(ZipStreamError):
    pass


class ZipFileInProgress(ZipStreamError):
    pass


class ZipFileBytesRequired(ZipStreamError):
    pass


ZipFile = namedtuple('ZipFile', [
    'filename', 'size', 'create_fp', 'datetime', 'comment',
])


DirEntry = namedtuple('DirEntry', [
    'filename', 'extra', 'comment', 'create_version',
    'extract_version', 'flag_bits', 'dostime', 'dosdate',
    'file_crc', 'file_size', 'external_attr', 'offset', 'is_zip64',
])


class ZipStream(object):
    def __init__(self, files, comment=None):
        if isinstance(comment, str):
            raise ZipFileBytesRequired('ZIP comment should bytes')

        self.files = files
        self.comment = comment

        self._dir = None
        self._pos = None
        self._generating = False
        self._calculate_size = False

    def generate(self):
        if self._generating:
            raise ZipFileInProgress('ZipFile generator already in progress')

        self._generating = True

        try:
            for chunk in self._generate_zip_file():
                yield chunk
        finally:
            self._generating = False

    def size(self):
        if self._generating:
            raise ZipFileInProgress(
                'ZipFile generator already in progress. You need to call'
                ' size() before generate()')

        self._calculate_size = True

        try:
            for _ in self.generate():
                pass
        finally:
            self._calculate_size = False

        return self._pos

    def _incr(self, buf):
        assert not isinstance(buf, str)

        self._pos += len(buf)

        return buf

    def _generate_file(self, zip_file):
        offset = self._pos

        file_dt = zip_file.datetime

        if isinstance(file_dt, datetime.datetime):
            file_dt = file_dt.timetuple()

        if file_dt is None:
            file_dt = time.localtime(time.time())

        create_version = ZIP_VERSION_20
        extract_version = ZIP_VERSION_20

        filename, flag_bits = encode_filename_flags(zip_file.filename, 8)

        if len(filename) > UINT16_MAX:
            raise FileNameTooLong('File name is too long: %d' % len(filename))

        extra = b''

        ext_time_extra_modtime = int(calendar.timegm(file_dt))
        ext_time_extra = struct.pack(
            STRUCT_EXT_TIME_EXTRA, EXT_TIME_EXTRA_ID, EXT_TIME_EXTRA_SIZE,
            EXT_TIME_EXTRA_FLAGS, ext_time_extra_modtime)
        extra += ext_time_extra

        dosdate = (file_dt[0] - 1980) << 9 | file_dt[1] << 5 | file_dt[2]
        dostime = file_dt[3] << 11 | file_dt[4] << 5 | (file_dt[5] // 2)

        header = struct.pack(
            STRUCT_FILE_HEADER, STRING_FILE_HEADER, extract_version, 0,
            flag_bits, ZIP_MODE_STORED, dostime, dosdate, 0, 0, 0,
            len(filename), len(extra))

        yield self._incr(header)
        yield self._incr(filename)
        yield self._incr(extra)

        file_crc = 0
        file_size = 0

        if zip_file.create_fp is not None:
            if self._calculate_size:
                if zip_file.size is None:
                    raise ZipFileSizeRequired(
                        'ZipFile.size is required to calculate zip file'
                        ' size: %s' % filename)

                file_size = zip_file.size
                self._pos += zip_file.size
            else:
                file_obj = zip_file.create_fp()

                try:
                    while True:
                        buf = file_obj.read(4096)
                        if not buf:
                            break

                        if isinstance(buf, str):
                            raise ZipFileBytesRequired(
                                'File object should contain bytes')

                        file_size = file_size + len(buf)
                        file_crc = crc32(buf, file_crc) & 0xffffffff

                        yield self._incr(buf)
                finally:
                    if hasattr(file_obj, 'close'):
                        file_obj.close()

        is_zip64 = file_size > UINT32_MAX

        if is_zip64:
            extract_version = ZIP_VERSION_45
            data_descriptor = struct.pack(
                STRUCT_DATA_DESCRIPTOR64, STRING_DATA_DESCRIPTOR, file_crc,
                file_size, file_size)
        else:
            data_descriptor = struct.pack(
                STRUCT_DATA_DESCRIPTOR, STRING_DATA_DESCRIPTOR, file_crc,
                file_size, file_size)

        yield self._incr(data_descriptor)

        comment = b'' if zip_file.comment is None else zip_file.comment

        if isinstance(comment, str):
            raise ZipFileBytesRequired('File comment should bytes')

        external_attr = 0

        is_dir = file_size == 0 and filename.endswith(b'/')

        if is_dir:
            external_attr |= 0x10

        dir_entry = DirEntry(
            filename=filename,
            extra=extra,
            comment=comment,
            create_version=create_version,
            extract_version=extract_version,
            flag_bits=flag_bits,
            dostime=dostime,
            dosdate=dosdate,
            file_crc=file_crc,
            file_size=file_size,
            external_attr=external_attr,
            offset=offset,
            is_zip64=is_zip64,
        )

        self._dir.append(dir_entry)

    def _generate_dir_entry(self, entry):
        extra = entry.extra
        file_size = entry.file_size
        offset = entry.offset
        create_system = 0
        reserved = 0
        compress_type = ZIP_MODE_STORED
        disk_number_start = 0
        internal_attr = 0

        central_dir_file_size = file_size
        central_dir_offset = min(offset, UINT32_MAX)

        if entry.is_zip64:
            central_dir_file_size = UINT32_MAX

            zip64_extra = struct.pack(
                STRUCT_ZIP64_EXTRA, ZIP64_EXTRA_ID, ZIP64_EXTRA_SIZE,
                file_size, file_size, offset)

            extra += zip64_extra

        central_dir = struct.pack(
            STRUCT_CENTRAL_DIR, STRING_CENTRAL_DIR, entry.create_version,
            create_system, entry.extract_version, reserved, entry.flag_bits,
            compress_type, entry.dostime, entry.dosdate, entry.file_crc,
            central_dir_file_size, central_dir_file_size, len(entry.filename),
            len(extra), len(entry.comment), disk_number_start, internal_attr,
            entry.external_attr, central_dir_offset)

        yield self._incr(central_dir)
        yield self._incr(entry.filename)
        yield self._incr(extra)
        yield self._incr(entry.comment)

    def _generate_zip_file(self):
        self._dir = []
        self._pos = 0

        for zip_file in self.files:
            for chunk in self._generate_file(zip_file):
                yield chunk

        start = self._pos

        for entry in self._dir:
            for chunk in self._generate_dir_entry(entry):
                yield chunk

        end = self._pos

        cent_dir_count = len(self._dir)
        cent_dir_size = end - start
        cent_dir_offset = start

        if cent_dir_count >= UINT16_MAX or cent_dir_size >= UINT32_MAX or \
                cent_dir_offset >= UINT32_MAX:
            zip64_end_rec = struct.pack(
                STRUCT_END_ARCHIVE64, STRING_END_ARCHIVE64, 44, ZIP_VERSION_45,
                ZIP_VERSION_45, 0, 0, cent_dir_count, cent_dir_count,
                cent_dir_size, cent_dir_offset)

            yield self._incr(zip64_end_rec)

            zip64_loc_rec = struct.pack(
                STRUCT_END_ARCHIVE64_LOCATOR, STRING_END_ARCHIVE64_LOCATOR, 0,
                end, 1)

            yield self._incr(zip64_loc_rec)

            cent_dir_count = UINT16_MAX
            cent_dir_size = UINT32_MAX
            cent_dir_offset = UINT32_MAX

        eocd_comment = b'' if self.comment is None else self.comment

        endrec = struct.pack(
            STRUCT_END_ARCHIVE, STRING_END_ARCHIVE, 0, 0, cent_dir_count,
            cent_dir_count, cent_dir_size, cent_dir_offset, len(eocd_comment))

        yield self._incr(endrec)
        yield self._incr(eocd_comment)


def encode_filename_flags(filename, flag_bits):
    if isinstance(filename, str):
        try:
            return filename.encode('ascii'), flag_bits
        except UnicodeEncodeError:
            return filename.encode('utf-8'), flag_bits | 0x800
    else:
        return filename, flag_bits
