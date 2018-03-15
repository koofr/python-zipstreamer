# -*- coding: utf-8 -*-

# chokidar "**/*.py" -i env -c nosetests

from __future__ import unicode_literals

import datetime
import unittest
import zipfile

from zipstreamer import (
    ZipStream, ZipFile, FileNameTooLong, ZipFileSizeRequired, ZipFileInProgress)
from zipstreamer.compat import BytesIO, IS_PY2


class DummyFile(object):
    def __init__(self, size):
        self.size = size
        self.cur = 0
        self.buf = ''

    def read(self, size):
        if self.cur + size > self.size:
            size = self.size - self.cur

        self.cur += size

        if len(self.buf) != size:
            self.buf = ''.join(b'a' for i in range(size))

        return self.buf


class TestZipStream(unittest.TestCase):
    maxDiff = None

    def test_generate(self):
        z = ZipStream(files=[
            ZipFile('file.txt', 4, lambda: BytesIO(b'test'), datetime.datetime(2008, 11, 10, 17, 53, 59), None),
            ZipFile('dir/', None, None, datetime.datetime(2011, 4, 16, 6, 24, 31), None),
            ZipFile(u'dir/ČŠŽ', 3, lambda: BytesIO(b'\x42\x42\x42'), datetime.datetime(2011, 4, 16, 6, 24, 31), b'lorem ipsum'),
        ], comment=b'zip comment')

        data = BytesIO()

        for chunk in z.generate():
            data.write(chunk)

        # import hexdump; hexdump.hexdump(data.getvalue())

        # with open('test.zip', 'wb') as f:
        #     f.write(data.getvalue())

        zf = zipfile.ZipFile(BytesIO(data.getvalue()))

        entries = [
            {
                key: getattr(entry, key)
                for key in zipfile.ZipInfo.__slots__
                if not key.startswith('_')
            }
            for entry in zf.infolist()
        ]

        self.assertEqual(entries, [
            {
                'orig_filename': b'file.txt' if IS_PY2 else 'file.txt',
                'filename': 'file.txt',
                'date_time': (2008, 11, 10, 17, 53, 58),
                'compress_type': 0,
                'comment': b'',
                'extra': b'\x55\x54\x05\x00\x01\x37\x75\x18\x49',
                'create_system': 0,
                'create_version': 20,
                'extract_version': 20,
                'reserved': 0,
                'flag_bits': 8,
                'volume': 0,
                'internal_attr': 0,
                'external_attr': 0,
                'header_offset': 0,
                'CRC': 3632233996,
                'compress_size': 4,
                'file_size': 4,
            },
            {
                'orig_filename': b'dir/' if IS_PY2 else 'dir/',
                'filename': 'dir/',
                'date_time': (2011, 4, 16, 6, 24, 30), # seconds // 2
                'compress_type': 0,
                'comment': b'',
                'extra': b'\x55\x54\x05\x00\x01\x1f\x36\xa9\x4d',
                'create_system': 0,
                'create_version': 20,
                'extract_version': 20,
                'reserved': 0,
                'flag_bits': 8,
                'volume': 0,
                'internal_attr': 0,
                'external_attr': 0x10,
                'header_offset': 67,
                'CRC': 0,
                'compress_size': 0,
                'file_size': 0,
            },
            {
                'orig_filename': b'dir/\xc4\x8c\xc5\xa0\xc5\xbd' if IS_PY2 else 'dir/ČŠŽ',
                'filename': 'dir/ČŠŽ',
                'date_time': (2011, 4, 16, 6, 24, 30), # seconds // 2
                'compress_type': 0,
                'comment': b'lorem ipsum',
                'extra': b'\x55\x54\x05\x00\x01\x1f\x36\xa9\x4d',
                'create_system': 0,
                'create_version': 20,
                'extract_version': 20,
                'reserved': 0,
                'flag_bits': 2056,
                'volume': 0,
                'internal_attr': 0,
                'external_attr': 0,
                'header_offset': 126,
                'CRC': 3603074439,
                'compress_size': 3,
                'file_size': 3,
            }
        ])

        self.assertEqual(zf.open('file.txt').read(), b'test')
        self.assertEqual(zf.open('dir/').read(), b'')
        self.assertEqual(zf.open(u'dir/ČŠŽ').read(), b'BBB')

        self.assertEqual(zf.comment, b'zip comment')

        self.assertEqual(z.size(), len(data.getvalue()))

    def test_generate_zip64_size(self):
        z = ZipStream(files=[
            ZipFile(b'file.txt', 5 * 1024 * 1024 * 1024, lambda: None, datetime.datetime(2008, 11, 10, 17, 53, 59), None),
        ])

        self.assertEqual(z.size(), 5 * 1024 * 1024 * 1024 + 260)

    # this test takes 23s so its disabled by default
    # def test_generate_zip64(self):
    #     f = DummyFile(5 * 1024 * 1024 * 1024)

    #     z = ZipStream(files=[
    #         ZipFile('file.txt', None, lambda: f, datetime.datetime(2008, 11, 10, 17, 53, 59), None),
    #     ])

    #     size = 0

    #     with open('test_5G.zip', 'wb') as zf:
    #         for chunk in z.generate():
    #             zf.write(chunk)
    #             size += len(chunk)

    #     self.assertEqual(size, 5 * 1024 * 1024 * 1024 + 260)

    def test_filename_too_long(self):
        filename = ''.join('a' for i in range(100000))

        z = ZipStream(files=[
            ZipFile(filename, None, lambda: BytesIO(b'test'), None, None),
        ])

        with self.assertRaises(FileNameTooLong):
            for _ in z.generate():
                pass

    def test_size_required(self):
        z = ZipStream(files=[
            ZipFile('file.txt', None, lambda: BytesIO(b'test'), None, None),
        ])

        with self.assertRaises(ZipFileSizeRequired):
            z.size()

    def test_size_while_generate(self):
        z = ZipStream(files=[
            ZipFile('file.txt', 4, lambda: BytesIO(b'test'), None, None),
        ])

        it = iter(z.generate())
        next(it)

        with self.assertRaises(ZipFileInProgress):
            z.size()

    def test_generate_while_generate(self):
        z = ZipStream(files=[
            ZipFile('file.txt', 4, lambda: BytesIO(b'test'), None, None),
        ])

        it1 = iter(z.generate())
        next(it1)

        with self.assertRaises(ZipFileInProgress):
            it2 = iter(z.generate())
            next(it2)


# Reference implementation in Go

'''
package main

import (
        "archive/zip"
        "os"
        "time"
)

func expect(err error) {
        if err != nil {
                panic(err)
        }
}

func main() {
        f, err := os.Create("testgo.zip")
        expect(err)
        w := zip.NewWriter(f)

        fw, err := w.CreateHeader(&zip.FileHeader{
                Name:           "file.txt",
                Comment:        "",
                CreatorVersion: 20,
                ReaderVersion:  20,
                Flags:          0,
                Method:         zip.Store,
                Modified:       time.Date(2008, 11, 10, 17, 53, 59, 0, time.UTC),
        })
        expect(err)
        _, err = fw.Write([]byte("test"))
        expect(err)

        fw, err = w.CreateHeader(&zip.FileHeader{
                Name:           "dir/",
                Comment:        "",
                CreatorVersion: 20,
                ReaderVersion:  20,
                Flags:          0,
                Method:         zip.Store,
                Modified:       time.Date(2011, 4, 16, 6, 24, 31, 0, time.UTC),
        })
        expect(err)
        fw, err = w.CreateHeader(&zip.FileHeader{
                Name:           "dir/ČŠŽ",
                Comment:        "lorem ipsum",
                CreatorVersion: 20,
                ReaderVersion:  20,
                Flags:          0,
                Method:         zip.Store,
                Modified:       time.Date(2011, 4, 16, 6, 24, 31, 0, time.UTC),
        })
        expect(err)
        _, err = fw.Write([]byte{0x42, 0x42, 0x42})
        expect(err)

        err = w.Close()
        expect(err)

        f, err = os.Create("testgo_5G.zip")
        expect(err)
        w = zip.NewWriter(f)

        fw, err = w.CreateHeader(&zip.FileHeader{
                Name:           "file.txt",
                Comment:        "",
                CreatorVersion: 20,
                ReaderVersion:  20,
                Flags:          0,
                Method:         zip.Store,
                Modified:       time.Date(2008, 11, 10, 17, 53, 59, 0, time.UTC),
        })
        expect(err)
        buf := make([]byte, 4096)
        for i := 0; i < 4096; i++ {
                buf[i] = 'a'
        }
        for i := 0; i < (5*1024*1024*1024)/4096; i++ {
                _, err = fw.Write(buf)
                expect(err)
        }

        err = w.Close()
        expect(err)
}
'''
